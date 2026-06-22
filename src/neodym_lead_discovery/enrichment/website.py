from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from neodym_lead_discovery.models import EnrichedCompany, LeadCandidate, SourceEvidence

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
}


def fetch_html(url: str, timeout: float = 10.0) -> str:
    headers = {"User-Agent": "neodym-lead-discovery-agent/0.1 (+public lead research)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def extract_website_profile(
    candidate: LeadCandidate,
    html: str,
    source_url: str,
) -> EnrichedCompany:
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text(" ")) if soup.title else None
    description = _meta_description(soup)
    text = _page_text(soup)
    discovered_links = _discover_relevant_links(soup, source_url)
    source_links = list(dict.fromkeys([*candidate.source_links, source_url, *discovered_links]))
    enriched_candidate = candidate.model_copy(update={"source_links": source_links})
    snippet = text[:500]
    return EnrichedCompany(
        candidate=enriched_candidate,
        website_title=title,
        website_summary=description or snippet[:240],
        services_or_products=_extract_headings(soup),
        operational_complexity_signals=_detect_operational_signals(text),
        evidence=[SourceEvidence(url=source_url, label="website", snippet=snippet)],
    )


def _meta_description(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"name": "description"})
    if not tag:
        return None
    content = tag.get("content")
    return _clean(str(content)) if content else None


def _extract_headings(soup: BeautifulSoup) -> list[str]:
    headings = [_clean(tag.get_text(" ")) for tag in soup.find_all(["h1", "h2"])]
    return [heading for heading in headings if heading]


def _discover_relevant_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    relevant = []
    for link in soup.find_all("a", href=True):
        label = _clean(link.get_text(" ")).lower()
        href = str(link.get("href"))
        combined = f"{label} {href}".lower()
        relevant_terms = ["about", "services", "contact", "team", "career", "jobs"]
        if any(term in combined for term in relevant_terms):
            relevant.append(urljoin(base_url, href))
    return relevant


def _detect_operational_signals(text: str) -> list[str]:
    lower = text.lower()
    return sorted({signal for term, signal in _OPERATIONAL_TERMS.items() if term in lower})


def _page_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _clean(soup.get_text(" "))


def _clean(value: str) -> str:
    return " ".join(value.split())
