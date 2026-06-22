from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from neodym_lead_discovery.models import SourceEvidence


@dataclass(frozen=True)
class JobSignals:
    roles: list[str]
    operational_signals: list[str]
    growth_signals: list[str]
    evidence: SourceEvidence


_COMMON_CAREERS_PATHS = ("/careers", "/jobs", "/work-with-us")
_ROLE_KEYWORDS = {
    "operations": ["operations", "operator", "dispatch", "warehouse"],
    "support": ["support", "customer success", "customer service"],
    "engineering": ["engineer", "developer", "software", "data"],
    "ai_automation": ["ai", "automation", "machine learning", "ml"],
}


def discover_careers_urls(base_url: str, homepage_html: str) -> list[str]:
    soup = BeautifulSoup(homepage_html, "html.parser")
    urls = {urljoin(base_url, path) for path in _COMMON_CAREERS_PATHS}
    for link in soup.find_all("a", href=True):
        text = f"{link.get_text(' ')} {link.get('href')}".lower()
        if any(term in text for term in ["career", "jobs", "work with us"]):
            urls.add(urljoin(base_url, str(link.get("href"))))
    return sorted(urls)


def extract_job_signals(html: str, source_url: str) -> JobSignals:
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ").split())
    roles = _extract_roles(soup)
    combined = f"{text} {' '.join(roles)}".lower()
    operational = []
    growth = []
    for signal, keywords in _ROLE_KEYWORDS.items():
        if any(keyword in combined for keyword in keywords):
            if signal in {"operations", "support"}:
                operational.append(signal)
            else:
                growth.append(signal)
    return JobSignals(
        roles=roles,
        operational_signals=sorted(set(operational)),
        growth_signals=sorted(set(growth)),
        evidence=SourceEvidence(url=source_url, label="careers", snippet=text[:500]),
    )


def _extract_roles(soup: BeautifulSoup) -> list[str]:
    candidates = []
    for tag in soup.find_all(["h1", "h2", "h3", "div", "li", "p"]):
        text = " ".join(tag.get_text(" ").split())
        if not text or len(text) > 80:
            continue
        lower = text.lower()
        if any(keyword in lower for keywords in _ROLE_KEYWORDS.values() for keyword in keywords):
            candidates.append(text)
    return list(dict.fromkeys(candidates))
