from __future__ import annotations

from pathlib import Path

from trafilatura import extract, fetch_url

DEFAULT_MAX_CHARS = 12_000


class WebsiteContextError(RuntimeError):
    """Raised when website context extraction cannot produce useful content."""


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


def fetch_website_context(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Fetch a URL and return compact, LLM-ready website context Markdown."""
    html = fetch_url(url)
    if not html:
        raise WebsiteContextError(f"Could not fetch URL: {url}")
    body = extract_main_markdown(html, url=url, max_chars=max_chars)
    return f"# Website context\n\nSource URL: {url}\n\n{body}\n"


def write_website_context(url: str, output_path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> Path:
    """Fetch and write compact website context to a Markdown file."""
    context = fetch_website_context(url, max_chars=max_chars)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(context)
    return output_path


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
