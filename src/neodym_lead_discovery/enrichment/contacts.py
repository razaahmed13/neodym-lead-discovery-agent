from __future__ import annotations

import re

from neodym_lead_discovery.models import ContactCandidate

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ROLE_PRIORITY = [
    "Founder and CEO",
    "Founder",
    "CEO",
    "CTO",
    "Head of Operations",
    "VP Engineering",
    "Director of Technology",
]
_ROLE_PATTERN = (
    r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*,\s*"
    r"(?P<role>Founder and CEO|Founder|CEO|CTO|Head of Operations|"
    r"VP Engineering|Director of Technology)"
    r"(?:\s*[-–—]?\s*(?P<email>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}))?"
)
_ROLE_RE = re.compile(_ROLE_PATTERN)


def identify_contact_candidates(text: str, source_url: str | None = None) -> list[ContactCandidate]:
    contacts = []
    for line in text.splitlines():
        match = _ROLE_RE.search(line.strip())
        if not match:
            continue
        email = match.group("email")
        if not email:
            email_match = _EMAIL_RE.search(line)
            email = email_match.group(0) if email_match else None
        contacts.append(
            ContactCandidate(
                name=match.group("name"),
                role=match.group("role"),
                email=email,
                source_url=source_url,
            )
        )
    if contacts:
        return sorted(contacts, key=lambda contact: _role_rank(contact.role))
    return [
        ContactCandidate(name=None, role=_suggest_role(text), email=None, source_url=source_url)
    ]


def _role_rank(role: str) -> int:
    try:
        return _ROLE_PRIORITY.index(role)
    except ValueError:
        return len(_ROLE_PRIORITY)


def _suggest_role(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ["operations", "dispatch", "warehouse", "logistics"]):
        return "Head of Operations"
    if any(term in lower for term in ["software", "platform", "engineering", "technology"]):
        return "CTO"
    return "Founder"
