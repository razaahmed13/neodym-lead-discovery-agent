from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from neodym_lead_discovery.enrichment.contacts import identify_contact_candidates
from neodym_lead_discovery.models import (
    ContactCandidate,
    EnrichedCompany,
    LeadCandidate,
    SourceEvidence,
    StructuredCompanyProfile,
    WebsitePageProfile,
)

Fetcher = Callable[[str], str]
JavaScriptRenderer = Callable[[str], str]
PageEvidenceAnalyzer = Callable[[LeadCandidate, WebsitePageProfile], dict[str, object]]

_RELEVANT_PAGE_TERMS = {
    "about": "about",
    "services": "services",
    "solutions": "services",
    "industries": "services",
    "contact": "contact",
    "team": "team",
    "leadership": "team",
    "careers": "careers",
    "jobs": "careers",
}
_RELEVANT_PAGE_PRIORITY = ["home", "about", "services", "team", "contact", "careers", "other"]
_OPERATIONAL_TERMS = {
    "dispatch": "dispatch",
    "workflow": "workflow",
    "workflows": "workflow",
    "claims": "claims",
    "intake": "intake",
    "support": "support",
    "compliance": "compliance",
    "warehouse": "warehouse",
    "scheduling": "scheduling",
    "document processing": "document_processing",
    "documents": "document_processing",
    "automation": "automation",
    "operations": "operations",
}
_COMMON_RELEVANT_PATHS = ["/about", "/services", "/solutions", "/team", "/contact", "/careers"]


def fetch_html(url: str, timeout: float = 10.0) -> str:
    headers = {"User-Agent": "neodym-lead-discovery-agent/0.1 (+public lead research)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def render_javascript_html(url: str, timeout_ms: int = 15_000) -> str | None:
    """Render a JavaScript-heavy page with Playwright when it is installed.

    Playwright is optional so normal static crawling remains lightweight. If the browser
    dependency is unavailable or rendering fails, callers can continue with static HTML.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except Exception:
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def enrich_public_website(
    candidate: LeadCandidate,
    *,
    fetcher: Fetcher = fetch_html,
    javascript_renderer: JavaScriptRenderer | None = None,
    page_evidence_analyzer: PageEvidenceAnalyzer | None = None,
    max_pages: int = 8,
    min_static_text_chars: int = 80,
) -> EnrichedCompany:
    """Crawl relevant public pages and assemble an LLM-ready structured profile."""
    if not candidate.website:
        return _empty_enrichment(candidate)

    home_url = _normalize_url(candidate.website)
    renderer = javascript_renderer or _default_renderer
    queue = [home_url]
    queued = {home_url}
    visited: set[str] = set()
    profiles: list[WebsitePageProfile] = []

    while queue and len(profiles) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetcher(url)
        except Exception:
            continue
        html, rendered = _maybe_render_javascript(
            url,
            html,
            renderer=renderer,
            min_static_text_chars=min_static_text_chars,
        )
        profile = extract_page_profile(url, html, rendered_with_javascript=rendered)
        profiles.append(profile)

        for link in profile.outbound_links:
            if len(queued) >= max_pages * 3:
                break
            if link in queued or not _same_site(home_url, link):
                continue
            if _page_type(link) not in {"about", "services", "team", "contact", "careers"}:
                continue
            queue.append(link)
            queued.add(link)

        if url == home_url:
            for path in _COMMON_RELEVANT_PATHS:
                link = _canonicalize_url(urljoin(home_url, path))
                if link not in queued:
                    queue.append(link)
                    queued.add(link)

    profiles = _dedupe_profiles(profiles)[:max_pages]
    analyzer = page_evidence_analyzer or analyze_page_with_codex
    return build_enriched_company(candidate, profiles, page_evidence_analyzer=analyzer)


def extract_page_profile(
    source_url: str,
    html: str,
    *,
    rendered_with_javascript: bool = False,
) -> WebsitePageProfile:
    soup = BeautifulSoup(html, "html.parser")
    text = _page_text(soup)
    return WebsitePageProfile(
        url=source_url,
        page_type="home" if _is_home_path(source_url) else _page_type(source_url),
        title=_clean(soup.title.get_text(" ")) if soup.title else None,
        meta_description=_meta_description(soup),
        headings=_extract_headings(soup),
        text=text,
        outbound_links=_discover_relevant_links(soup, source_url),
        operational_signals=_detect_operational_signals(text),
        rendered_with_javascript=rendered_with_javascript,
    )


def build_enriched_company(
    candidate: LeadCandidate,
    page_profiles: list[WebsitePageProfile],
    *,
    page_evidence_analyzer: PageEvidenceAnalyzer | None = None,
) -> EnrichedCompany:
    if not page_profiles:
        return _empty_enrichment(candidate)

    title = _first_non_empty([profile.title for profile in page_profiles])
    summary = _first_non_empty([profile.meta_description for profile in page_profiles])
    if summary is None:
        summary = page_profiles[0].text[:240]

    services = _unique(
        heading
        for profile in page_profiles
        if profile.page_type in {"home", "services", "about"}
        for heading in profile.headings
    )
    signals = sorted(
        {signal for profile in page_profiles for signal in profile.operational_signals}
    )
    contact_candidates = _merge_contacts(page_profiles)
    evidence = [
        SourceEvidence(
            url=profile.url,
            label=f"website:{profile.page_type}",
            snippet=profile.text[:500],
        )
        for profile in page_profiles
        if profile.text
    ]
    source_links = _unique([*candidate.source_links, *(profile.url for profile in page_profiles)])
    enriched_candidate = candidate.model_copy(update={"source_links": source_links})
    analyzer = page_evidence_analyzer or _fallback_page_analysis
    structured_profile = StructuredCompanyProfile(
        company_name=candidate.company_name,
        website=candidate.website,
        summary=summary,
        services_or_products=services,
        operational_complexity_signals=signals,
        contact_candidates=contact_candidates,
        source_urls=source_links,
        llm_context={
            "pages_crawled": len(page_profiles),
            "page_evidence": [
                _page_evidence(candidate, profile, analyzer)
                for profile in page_profiles
            ],
            "evidence_text": "\n\n".join(
                f"SOURCE: {profile.url}\n{profile.text[:2000]}" for profile in page_profiles
            ),
        },
    )
    return EnrichedCompany(
        candidate=enriched_candidate,
        website_title=title,
        website_summary=summary,
        services_or_products=services,
        operational_complexity_signals=signals,
        contact_candidates=contact_candidates,
        evidence=evidence,
        page_profiles=page_profiles,
        structured_profile=structured_profile,
    )


def _page_evidence(
    candidate: LeadCandidate,
    profile: WebsitePageProfile,
    analyzer: PageEvidenceAnalyzer,
) -> dict[str, object]:
    analysis = _normalize_page_analysis(analyzer(candidate, profile), profile)
    return {
        "url": profile.url,
        "page_type": profile.page_type,
        "title": profile.title,
        "headings": profile.headings,
        "operational_signals": profile.operational_signals,
        "rendered_with_javascript": profile.rendered_with_javascript,
        **analysis,
    }


def analyze_page_with_codex(
    candidate: LeadCandidate,
    profile: WebsitePageProfile,
    *,
    timeout_seconds: int = 180,
) -> dict[str, object]:
    """Use Codex CLI to summarize one page for automation-relevant lead scoring."""
    prompt = _codex_page_analysis_prompt(candidate, profile)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as output_file:
        output_path = Path(output_file.name)

    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--output-last-message",
        str(output_path),
        "-",
    ]
    try:
        subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=True,
        )
        response_text = output_path.read_text(encoding="utf-8")
        return _normalize_page_analysis(_parse_json_object(response_text), profile)
    except Exception as exc:
        fallback = _fallback_page_analysis(candidate, profile)
        limitations = _string_list(fallback.get("limitations"))
        fallback["limitations"] = [
            *limitations,
            f"Codex page analysis unavailable: {type(exc).__name__}.",
        ]
        return fallback
    finally:
        output_path.unlink(missing_ok=True)


def _codex_page_analysis_prompt(candidate: LeadCandidate, profile: WebsitePageProfile) -> str:
    page_text = profile.text[:6000]
    return f"""Return only one valid JSON object.

You are analyzing one public website page for Neodym's lead discovery agent.
Create a concise, critical page-level analysis for B2B lead scoring.

Focus particularly on processes that appear manual, repetitive, or coordination-heavy and
could plausibly be automated.
Do not invent manual processes. If the page does not prove a process is manual, say so in
limitations.
Use only the provided page text and metadata.

Required JSON keys:
- page_summary: string, 1-3 sentences summarizing the page and any automation-relevant operations.
- manual_process_signals: array of strings. Evidence-backed signals only; use [] if none.
- automation_opportunities: array of strings. Plausible opportunities tied to the evidence;
  use [] if none.
- supporting_excerpt: short exact or near-exact excerpt from the page text that grounds the
  analysis.
- limitations: array of strings describing uncertainty, missing proof, or why the page is not
  useful.

Company: {candidate.company_name}
Website: {candidate.website or "unknown"}
Page URL: {profile.url}
Page type: {profile.page_type}
Title: {profile.title or ""}
Headings: {json.dumps(profile.headings, ensure_ascii=False)}
Detected keyword signals: {json.dumps(profile.operational_signals, ensure_ascii=False)}

Page text:
{page_text}
"""


def _parse_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Codex page analysis must return a JSON object")
    return parsed


def _normalize_page_analysis(
    analysis: dict[str, object],
    profile: WebsitePageProfile,
) -> dict[str, object]:
    return {
        "page_summary": _string_field(analysis.get("page_summary"))
        or _fallback_summary(profile),
        "manual_process_signals": _string_list(analysis.get("manual_process_signals")),
        "automation_opportunities": _string_list(analysis.get("automation_opportunities")),
        "supporting_excerpt": _string_field(analysis.get("supporting_excerpt"))
        or profile.text[:500],
        "limitations": _string_list(analysis.get("limitations")),
    }


def _fallback_page_analysis(
    candidate: LeadCandidate,
    profile: WebsitePageProfile,
) -> dict[str, object]:
    del candidate
    limitations = ["No LLM page summary was generated for this page."]
    if not profile.operational_signals:
        limitations.append("No operational keyword signals were detected in the page text.")
    return {
        "page_summary": _fallback_summary(profile),
        "manual_process_signals": [],
        "automation_opportunities": [],
        "supporting_excerpt": profile.text[:500],
        "limitations": limitations,
    }


def _fallback_summary(profile: WebsitePageProfile) -> str:
    title = f"{profile.title}. " if profile.title else ""
    return f"{title}{profile.text[:240]}".strip()


def _string_field(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def extract_website_profile(
    candidate: LeadCandidate,
    html: str,
    source_url: str,
) -> EnrichedCompany:
    profile = extract_page_profile(source_url, html)
    discovered_links = profile.outbound_links
    source_links = list(dict.fromkeys([*candidate.source_links, source_url, *discovered_links]))
    enriched_candidate = candidate.model_copy(update={"source_links": source_links})
    enriched = build_enriched_company(enriched_candidate, [profile])
    return enriched.model_copy(update={"candidate": enriched_candidate})


def _maybe_render_javascript(
    url: str,
    html: str,
    *,
    renderer: JavaScriptRenderer | None,
    min_static_text_chars: int,
) -> tuple[str, bool]:
    if renderer is None:
        return html, False
    soup = BeautifulSoup(html, "html.parser")
    text = _page_text(soup)
    if len(text) >= min_static_text_chars and not _looks_like_javascript_shell(soup, text):
        return html, False
    rendered = renderer(url)
    return (rendered, True) if rendered else (html, False)


def _default_renderer(url: str) -> str:
    return render_javascript_html(url) or ""


def _looks_like_javascript_shell(soup: BeautifulSoup, text: str) -> bool:
    if len(text) >= 40:
        return False
    script_count = len(soup.find_all("script"))
    root_markers = (
        soup.find(id="root")
        or soup.find(id="app")
        or soup.find(attrs={"data-reactroot": True})
    )
    return bool(script_count and root_markers)


def _empty_enrichment(candidate: LeadCandidate) -> EnrichedCompany:
    return EnrichedCompany(candidate=candidate)


def _meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if not tag:
        return None
    content = tag.get("content")
    return _clean(str(content)) if content else None


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    headings = [_clean(tag.get_text(" ")) for tag in soup.find_all(["h1", "h2", "h3"])]
    return [heading for heading in headings if heading]


def _discover_relevant_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    relevant = []
    for link in soup.find_all("a", href=True):
        label = _clean(link.get_text(" ")).lower()
        href = str(link.get("href"))
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        combined = f"{label} {href}".lower()
        if any(term in combined for term in _RELEVANT_PAGE_TERMS):
            relevant.append(_canonicalize_url(urljoin(base_url, href)))
    return _unique(relevant)


def _detect_operational_signals(text: str) -> list[str]:
    lower = text.lower()
    return sorted({signal for term, signal in _OPERATIONAL_TERMS.items() if term in lower})


def _page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return _clean(soup.get_text(" "))


def _merge_contacts(page_profiles: list[WebsitePageProfile]) -> list[ContactCandidate]:
    contacts: list[ContactCandidate] = []
    suggestions: list[ContactCandidate] = []
    seen: set[tuple[str | None, str, str | None]] = set()
    for profile in page_profiles:
        if profile.page_type not in {"team", "contact", "about", "home"}:
            continue
        for contact in identify_contact_candidates(profile.text, source_url=profile.url):
            key = (contact.name, contact.role, contact.email)
            if key in seen:
                continue
            seen.add(key)
            if contact.name or contact.email:
                contacts.append(contact)
            else:
                suggestions.append(contact)
    return contacts or suggestions


def _page_type(url: str) -> str:
    path = urlparse(url).path.lower()
    for term, page_type in _RELEVANT_PAGE_TERMS.items():
        if term in path:
            return page_type
    return "other"


def _same_site(home_url: str, link: str) -> bool:
    return urlparse(home_url).netloc.lower() == urlparse(link).netloc.lower()


def _is_home_path(url: str) -> bool:
    path = urlparse(url).path.strip("/")
    return path == ""


def _normalize_url(url: str) -> str:
    raw = url.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    return _canonicalize_url(raw)


def _canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or ""
    return urlunparse((scheme, netloc, path, "", "", ""))


def _dedupe_profiles(profiles: list[WebsitePageProfile]) -> list[WebsitePageProfile]:
    deduped = []
    seen = set()
    for profile in profiles:
        if profile.url in seen:
            continue
        seen.add(profile.url)
        deduped.append(profile)
    return sorted(deduped, key=lambda profile: _RELEVANT_PAGE_PRIORITY.index(profile.page_type))


def _first_non_empty(values: list[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _unique(values) -> list:
    return list(dict.fromkeys(value for value in values if value))


def _clean(value: str) -> str:
    return " ".join(value.split())
