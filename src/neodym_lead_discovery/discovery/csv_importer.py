from __future__ import annotations

import csv
import re
from pathlib import Path

from neodym_lead_discovery.models import LeadCandidate, SourceEvidence

_FIELD_ALIASES = {
    "company_name": {"company", "company name", "name", "organization", "account name"},
    "website": {"website", "domain", "company website", "url", "website url"},
    "industry": {"industry", "company industry", "industries"},
    "location": {"location", "company location", "city", "state", "headquarters"},
    "description": {"description", "company description", "short description", "about"},
    "company_size": {"employees", "employee count", "company size", "estimated employees"},
    "linkedin": {"linkedin", "linkedin url", "company linkedin", "linkedin company url"},
}


def import_csv(path: str | Path, discovery_source: str = "csv") -> list[LeadCandidate]:
    csv_path = Path(path)
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    return [_candidate_from_row(row, discovery_source) for row in rows if _get(row, "company_name")]


def _candidate_from_row(row: dict[str, str | None], discovery_source: str) -> LeadCandidate:
    company_name = _get(row, "company_name") or ""
    website = _normalize_website(_get(row, "website"))
    linkedin = _get(row, "linkedin")
    source_links = []
    if website:
        source_links.append(website)
    if linkedin:
        source_links.append(linkedin)
    description = _get(row, "description")
    evidence_parts = [company_name]
    if description:
        evidence_parts.append(description)
    raw_sources = [
        SourceEvidence(
            url=website or linkedin or "csv://import",
            label=discovery_source,
            snippet=" | ".join(evidence_parts),
        )
    ]
    return LeadCandidate(
        company_name=company_name,
        website=website,
        industry=_get(row, "industry"),
        location=_get(row, "location"),
        description=description,
        company_size=_get(row, "company_size"),
        source_links=source_links,
        raw_sources=raw_sources,
        discovery_source=discovery_source,
    )


def _get(row: dict[str, str | None], logical_field: str) -> str | None:
    aliases = _FIELD_ALIASES[logical_field]
    for key, value in row.items():
        if _normalize_header(key) in aliases and value is not None:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.replace("_", " ").strip().lower())


def _normalize_website(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith(("http://", "https://")):
        return stripped
    return f"https://{stripped}"
