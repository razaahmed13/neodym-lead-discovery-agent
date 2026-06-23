from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from trafilatura import extract, fetch_url

DEFAULT_MAX_CHARS = 12_000
WHITELISTED_PATHS = {
    "/",
    "/about",
    "/our-story",
    "/services",
    "/solutions",
    "/what-we-do",
    "/contact",
}


class WebsiteContextError(RuntimeError):
    """Raised when website context extraction cannot produce useful content."""


class _AnchorHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)


def extract_main_markdown(
    html: str,
    url: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Extract the page's main body as compact Markdown using Trafilatura.

    Trafilatura performs the stage-1 anti-boilerplate pass: it scores the DOM and removes
    repeated navigation, footer, sidebars, cookie banners, and ads before Markdown output.
    """
    markdown = extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        deduplicate=True,
    )
    if not markdown or not markdown.strip():
        raise WebsiteContextError("Trafilatura could not extract useful main-body content.")
    return _compact_markdown(markdown, max_chars=max_chars)


def discover_whitelisted_urls(url: str, fetcher=None) -> list[str]:
    """Discover same-domain pages allowed by the strict stage-2 URL router.

    The router only allows the homepage and exact business-context slugs:
    /about, /our-story, /services, /solutions, /what-we-do, and /contact.
    It first tries /sitemap.xml; if no allowed URLs are found there, it falls back to
    homepage links. Blog/news/article/media URLs are excluded by construction.
    """
    fetcher = fetcher or fetch_url
    base_url = _base_url(url)
    sitemap_urls = _discover_from_sitemap(base_url, fetcher=fetcher)
    if sitemap_urls:
        return _dedupe_preserving_order([_canonical_homepage(base_url), *sitemap_urls])

    homepage_html = fetcher(base_url)
    if not homepage_html:
        return [_canonical_homepage(base_url)]
    homepage_urls = _discover_from_homepage(base_url, homepage_html)
    return _dedupe_preserving_order([_canonical_homepage(base_url), *homepage_urls])


def fetch_website_context(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> tuple[str, int]:
    """Fetch whitelisted pages and return compact, LLM-ready website context Markdown."""
    discovered_urls = discover_whitelisted_urls(url)
    page_sections: list[str] = []

    for page_url in discovered_urls:
        html = fetch_url(page_url)
        if not html:
            continue
        try:
            body = extract_main_markdown(html, url=page_url, max_chars=max_chars)
        except WebsiteContextError:
            continue
        page_sections.append(f"## Source: {page_url}\n\n{body}")

    if not page_sections:
        raise WebsiteContextError(
            f"Could not extract useful content from whitelisted pages for: {url}"
        )

    context = "# Website context\n\n" + "\n\n---\n\n".join(page_sections) + "\n"
    return context, len(page_sections)


def write_website_context(
    url: str,
    output_path: Path,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[Path, int]:
    """Fetch and write compact website context to a Markdown file."""
    context, page_count = fetch_website_context(url, max_chars=max_chars)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(context)
    return output_path, page_count


def _discover_from_sitemap(base_url: str, fetcher=fetch_url) -> list[str]:
    sitemap_url = urljoin(base_url, "/sitemap.xml")
    sitemap_xml = fetcher(sitemap_url)
    if not sitemap_xml:
        return []

    urls: list[str] = []
    try:
        root = ElementTree.fromstring(sitemap_xml)
    except ElementTree.ParseError:
        return []

    for element in root.iter():
        if not element.tag.endswith("loc") or not element.text:
            continue
        candidate = element.text.strip()
        if _is_allowed_same_domain(base_url, candidate):
            urls.append(candidate)
    return urls


def _discover_from_homepage(base_url: str, html: str) -> list[str]:
    parser = _AnchorHrefParser()
    parser.feed(html)
    urls: list[str] = []
    for href in parser.hrefs:
        candidate = urljoin(base_url, href)
        if _is_allowed_same_domain(base_url, candidate):
            urls.append(candidate)
    return urls


def _is_allowed_same_domain(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url)
    candidate = urlparse(candidate_url)
    if candidate.scheme not in {"http", "https"}:
        return False
    if candidate.netloc.lower() != base.netloc.lower():
        return False
    normalized_path = candidate.path.rstrip("/") or "/"
    return normalized_path in WHITELISTED_PATHS


def _base_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if not parsed.netloc:
        raise WebsiteContextError(f"Invalid website URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _canonical_homepage(base_url: str) -> str:
    return f"{base_url}/"


def _dedupe_preserving_order(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        key = _dedupe_key(url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(url)
    return deduped


def _dedupe_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def _compact_markdown(markdown: str, max_chars: int) -> str:
    lines: list[str] = []
    previous_blank = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if not previous_blank and lines:
                lines.append("")
            previous_blank = True
            continue
        lines.append(line)
        previous_blank = False

    compact = "\n".join(lines).strip()
    if len(compact) <= max_chars:
        return compact
    truncated = compact[:max_chars].rsplit("\n", 1)[0].rstrip()
    return f"{truncated}\n\n[Truncated to {max_chars} characters for LLM context budget.]"
