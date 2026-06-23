from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from neodym_lead_discovery.models import LeadCandidate, SourceEvidence

APOLLO_COMPANY_SEARCH_URL = "https://api.apollo.io/api/v1/organizations/search"
DEFAULT_APOLLO_LOCATIONS = ["United States"]
DEFAULT_APOLLO_INDUSTRIES = [
    "logistics",
    "insurance",
    "staffing and recruiting",
    "legal services",
    "healthcare operations",
    "professional services",
]
DEFAULT_APOLLO_KEYWORDS = [
    "claims processing",
    "back office",
    "document processing",
    "customer operations",
    "dispatch",
    "intake",
    "scheduling",
    "compliance",
]
DEFAULT_MIN_EMPLOYEES = 20
DEFAULT_MAX_EMPLOYEES = 500
APOLLO_EMPLOYEE_RANGE_BUCKETS = [
    (1, 10, "1,10"),
    (11, 20, "11,20"),
    (21, 50, "21,50"),
    (51, 100, "51,100"),
    (101, 200, "101,200"),
    (201, 500, "201,500"),
    (501, 1000, "501,1000"),
    (1001, 2000, "1001,2000"),
    (2001, 5000, "2001,5000"),
    (5001, 10000, "5001,10000"),
    (10001, None, "10001,"),
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
    min_employees: int | None = DEFAULT_MIN_EMPLOYEES
    max_employees: int | None = DEFAULT_MAX_EMPLOYEES

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
        employee_ranges = _apollo_employee_ranges(self.min_employees, self.max_employees)
        if employee_ranges:
            payload["organization_num_employees_ranges"] = employee_ranges
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
    min_employees: int | None = DEFAULT_MIN_EMPLOYEES,
    max_employees: int | None = DEFAULT_MAX_EMPLOYEES,
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
                min_employees=min_employees,
                max_employees=max_employees,
            )
        )
        if not result.organizations:
            break
        candidates.extend(
            candidate
            for candidate in result.organizations
            if _candidate_matches_employee_range(candidate, min_employees, max_employees)
        )
        if result.total_entries is not None and len(candidates) >= result.total_entries:
            break
        if len(result.organizations) < result.per_page:
            break
        page += 1
    return candidates[:max_results]


def _apollo_employee_ranges(min_employees: int | None, max_employees: int | None) -> list[str]:
    ranges: list[str] = []
    for lower, upper, label in APOLLO_EMPLOYEE_RANGE_BUCKETS:
        if max_employees is not None and lower > max_employees:
            continue
        if min_employees is not None and upper is not None and upper < min_employees:
            continue
        ranges.append(label)
    return ranges


def _candidate_matches_employee_range(
    candidate: LeadCandidate,
    min_employees: int | None,
    max_employees: int | None,
) -> bool:
    employee_count = _parse_employee_count(candidate.company_size)
    if employee_count is None:
        return True
    if min_employees is not None and employee_count < min_employees:
        return False
    return not (max_employees is not None and employee_count > max_employees)


def _parse_employee_count(value: str | None) -> int | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        return None
    return int(digits)


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
