from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree

from trafilatura import fetch_url

DEFAULT_MAX_CHARS = 12_000
WHITELISTED_PATHS = {
    # Home page variants.
    "/",
    "/home",
    # About/company variants.
    "/about",
    "/about-us",
    "/who-we-are",
    "/our-story",
    "/our-company",
    "/company",
    "/team",
    "/leadership",
    # Services/solutions/capabilities variants.
    "/services",
    "/solutions",
    "/what-we-do",
    "/capabilities",
    "/industries",
    "/products",
    "/offerings",
    # Career/hiring variants.
    "/career",
    "/careers",
    "/jobs",
    "/join-us",
    "/work-with-us",
    "/open-roles",
    # Contact/support variants.
    "/contact",
    "/contact-us",
    "/get-in-touch",
    "/support",
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


class _VisibleTextParser(HTMLParser):
    SKIPPED_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "head",
        "header",
        "nav",
        "footer",
        "aside",
    }
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self._element_stack: list[tuple[str, bool]] = []
        self.lines: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in self.VOID_TAGS:
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        decoded_email = _extract_email_from_attrs(attr_map)
        should_skip = (
            normalized in self.SKIPPED_TAGS
            or _has_sidebar_attribute(attrs)
            or decoded_email is not None
        )
        self._element_stack.append((normalized, should_skip))
        if decoded_email:
            self.lines.append(decoded_email)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag, attrs

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        while self._element_stack:
            open_tag, _ = self._element_stack.pop()
            if open_tag == normalized:
                break

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text or any(should_skip for _, should_skip in self._element_stack):
            return
        self.lines.append(text)


def extract_main_markdown(
    html: str,
    url: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Extract visible page text while skipping common layout chrome.

    This intentionally avoids aggressive article/main-content pruning. The lead discovery
    workflow needs broad business-context text from the whole page, excluding only obvious
    non-content containers such as headers, footers, nav bars, sidebars, scripts, and styles.
    """
    del url
    markdown = _extract_visible_text_markdown(html)
    if not markdown:
        raise WebsiteContextError("Could not extract useful visible text from HTML.")
    return _compact_markdown(markdown, max_chars=max_chars)


def discover_whitelisted_urls(url: str, fetcher=None) -> list[str]:
    """Discover same-domain pages allowed by the strict stage-2 URL router.

    The router only allows the homepage and exact business-context slugs for the
    required lead-discovery pages: home, about, services, careers, and contact.
    Each page type includes common syntactic and semantic alternatives, for example
    /about-us, /who-we-are, /our-company, /what-we-do, /solutions, /careers,
    /jobs, /contact-us, and /get-in-touch.
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


def _has_sidebar_attribute(attrs: list[tuple[str, str | None]]) -> bool:
    for name, value in attrs:
        if not value or name.lower() not in {"class", "id", "role", "aria-label"}:
            continue
        normalized = value.lower()
        if "sidebar" in normalized or "side-bar" in normalized:
            return True
    return False


def _extract_email_from_attrs(attrs: dict[str, str]) -> str | None:
    href = attrs.get("href", "")
    if href.lower().startswith("mailto:"):
        return unquote(href.split(":", 1)[1].split("?", 1)[0]).strip() or None

    cf_email = attrs.get("data-cfemail", "")
    if cf_email:
        return _decode_cloudflare_email(cf_email)

    return None


def _decode_cloudflare_email(encoded: str) -> str | None:
    try:
        key = int(encoded[:2], 16)
        decoded = "".join(
            chr(int(encoded[index : index + 2], 16) ^ key) for index in range(2, len(encoded), 2)
        )
    except ValueError:
        return None
    return decoded if "@" in decoded else None


def _extract_visible_text_markdown(html: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(html)
    unique_lines = _dedupe_preserving_order(parser.lines)
    return "\n".join(unique_lines).strip()


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
