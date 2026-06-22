from __future__ import annotations

import re
from urllib.parse import urlparse

from neodym_lead_discovery.models import LeadCandidate

_COMPANY_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company)\b\.?",
    re.IGNORECASE,
)


def canonical_domain(website: str | None) -> str | None:
    if not website:
        return None
    raw = website.strip().lower()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host.rstrip("/") or None


def canonical_company_key(name: str) -> str:
    cleaned = name.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = _COMPANY_SUFFIX_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def are_duplicate_candidates(left: LeadCandidate, right: LeadCandidate) -> bool:
    left_domain = canonical_domain(left.website)
    right_domain = canonical_domain(right.website)
    if left_domain and right_domain and left_domain == right_domain:
        return True
    return canonical_company_key(left.company_name) == canonical_company_key(right.company_name)
