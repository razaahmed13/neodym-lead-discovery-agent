from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from neodym_lead_discovery.models import LeadCandidate, SourceEvidence

APOLLO_COMPANY_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"
DEFAULT_APOLLO_LOCATIONS = ["United States"]
DEFAULT_APOLLO_INDUSTRIES = [
    "healthcare",
    "legal services",
    "logistics",
    "insurance",
    "staffing and recruiting",
    "professional services",
    "software",
]
DEFAULT_APOLLO_KEYWORDS = [
    "workflow automation",
    "operations",
    "customer support",
    "claims",
    "document processing",
]


class ApolloApiError(RuntimeError):
    """Raised when Apollo API discovery cannot complete."""


@dataclass(frozen=True)
class ApolloSearchConfig:
    """Search options for Apollo company discovery."""

    page: int = 1
    per_page: int = 25
    organization_locations: list[str] = field(
        default_factory=lambda: DEFAULT_APOLLO_LOCATIONS.copy()
    )
    industries: list[str] = field(default_factory=lambda: DEFAULT_APOLLO_INDUSTRIES.copy())
    keywords: list[str] = field(default_factory=lambda: DEFAULT_APOLLO_KEYWORDS.copy())

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": self.page,
            "per_page": self.per_page,
        }
        if self.organization_locations:
            payload["organization_locations"] = self.organization_locations
        if self.industries:
            # Apollo accepts keyword-style organization filters on this endpoint. Keep a
            # broad text query as the stable MVP integration instead of relying on paid
            # list IDs or brittle UI automation.
            payload["q_organization_keyword_tags"] = self.industries
        if self.keywords:
            payload["q_organization_keywords"] = " OR ".join(self.keywords)
        return payload


@dataclass(frozen=True)
class ApolloSearchResult:
    organizations: list[LeadCandidate]
    page: int
    per_page: int
    total_entries: int | None = None


class ApolloClient:
    """Small Apollo API adapter for discovering lead seed companies."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.Client | None = None,
        base_url: str = APOLLO_COMPANY_SEARCH_URL,
    ) -> None:
        if not api_key.strip():
            raise ApolloApiError("Apollo API key is required. Set APOLLO_API_KEY.")
        self.api_key = api_key
        self.http_client = http_client or httpx.Client(timeout=30.0, follow_redirects=True)
        self.base_url = base_url

    def search_companies(self, config: ApolloSearchConfig | None = None) -> ApolloSearchResult:
        config = config or ApolloSearchConfig()
        response = self.http_client.post(
            self.base_url,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=config.to_payload(),
        )
        if response.status_code >= 400:
            body = response.text[:500]
            raise ApolloApiError(
                f"Apollo API request failed with status {response.status_code}: {body}"
            )
        data = response.json()
        organizations = data.get("organizations") or data.get("accounts") or []
        pagination = data.get("pagination") or {}
        return ApolloSearchResult(
            organizations=[
                candidate
                for organization in organizations
                if (candidate := _organization_to_candidate(organization)) is not None
            ],
            page=int(pagination.get("page") or config.page),
            per_page=int(pagination.get("per_page") or config.per_page),
            total_entries=_optional_int(pagination.get("total_entries")),
        )


def discover_from_apollo(
    *,
    client: ApolloClient,
    max_results: int = 50,
    per_page: int = 25,
    locations: list[str] | None = None,
    industries: list[str] | None = None,
    keywords: list[str] | None = None,
) -> list[LeadCandidate]:
    """Fetch company candidates from Apollo until max_results is reached."""
    candidates: list[LeadCandidate] = []
    page = 1
    while len(candidates) < max_results:
        result = client.search_companies(
            ApolloSearchConfig(
                page=page,
                per_page=min(per_page, max_results - len(candidates)),
                organization_locations=locations or DEFAULT_APOLLO_LOCATIONS.copy(),
                industries=industries or DEFAULT_APOLLO_INDUSTRIES.copy(),
                keywords=keywords or DEFAULT_APOLLO_KEYWORDS.copy(),
            )
        )
        if not result.organizations:
            break
        candidates.extend(result.organizations)
        if result.total_entries is not None and len(candidates) >= result.total_entries:
            break
        if len(result.organizations) < result.per_page:
            break
        page += 1
    return candidates[:max_results]


def _organization_to_candidate(organization: dict[str, Any]) -> LeadCandidate | None:
    name = _first_text(organization, "name", "organization_name", "account_name")
    if not name:
        return None
    website = _normalize_website(
        _first_text(organization, "website_url", "website", "primary_domain", "domain")
    )
    linkedin = _first_text(organization, "linkedin_url", "linkedin")
    source_links = [link for link in [website, linkedin] if link]
    description = _first_text(
        organization,
        "short_description",
        "description",
        "seo_description",
        "organization_description",
    )
    evidence_parts = [name]
    if description:
        evidence_parts.append(description)
    return LeadCandidate(
        company_name=name,
        website=website,
        industry=_first_text(organization, "industry", "organization_industry"),
        location=_first_text(
            organization,
            "raw_address",
            "organization_location",
            "city",
            "state",
            "country",
        ),
        description=description,
        company_size=_company_size(organization),
        source_links=source_links,
        raw_sources=[
            SourceEvidence(
                url=website or linkedin or "apollo://organization-search",
                label="apollo_api",
                snippet=" | ".join(evidence_parts),
            )
        ],
        discovery_source="apollo_api",
    )


def _first_text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _company_size(organization: dict[str, Any]) -> str | None:
    employee_count = _first_text(
        organization,
        "estimated_num_employees",
        "num_employees",
        "employee_count",
        "employees",
    )
    return employee_count


def _normalize_website(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith(("http://", "https://")):
        return stripped
    return f"https://{stripped}"


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
