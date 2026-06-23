import httpx
import pytest

from neodym_lead_discovery.discovery.apollo_api import (
    ALLOWED_APOLLO_INDUSTRIES,
    ApolloApiError,
    ApolloClient,
    ApolloSearchConfig,
    discover_from_apollo,
)


def test_apollo_client_posts_search_payload_and_maps_organizations():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "https://api.apollo.io/api/v1/organizations/search"
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["content-type"] == "application/json"
        payload = httpx.Request("POST", request.url, content=request.content).read()
        assert b'"organization_locations":["United States"]' in payload
        assert b'"organization_num_employees_ranges"' in payload
        assert b'"21,50"' in payload
        assert b'"201,500"' in payload
        assert b'"page":2' in payload
        assert b'"per_page":25' in payload
        return httpx.Response(
            200,
            json={
                "organizations": [
                    {
                        "name": "Acme Claims Inc",
                        "website_url": "acmeclaims.com",
                        "industry": "Insurance",
                        "raw_address": "Boston, MA, United States",
                        "short_description": "Claims operations and support workflow provider.",
                        "estimated_num_employees": 120,
                        "linkedin_url": "https://linkedin.com/company/acme-claims",
                    }
                ],
                "pagination": {"page": 2, "per_page": 25, "total_entries": 1},
            },
        )

    client = ApolloClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.search_companies(
        ApolloSearchConfig(
            page=2,
            per_page=25,
            organization_locations=["United States"],
            keywords=["insurance"],
            min_employees=20,
            max_employees=500,
        )
    )

    assert len(requests) == 1
    assert result.total_entries == 1
    assert result.organizations[0].company_name == "Acme Claims Inc"
    assert result.organizations[0].website == "https://acmeclaims.com"
    assert result.organizations[0].industry == "Insurance"
    assert result.organizations[0].location == "Boston, MA, United States"
    assert result.organizations[0].company_size == "120"
    assert result.organizations[0].discovery_source == "apollo_api"
    assert "https://linkedin.com/company/acme-claims" in result.organizations[0].source_links


def test_default_apollo_search_config_targets_smb_and_mid_market_filters():
    payload = ApolloSearchConfig().to_payload()

    assert payload["organization_locations"] == ["United States"]
    assert payload["organization_num_employees_ranges"] == [
        "11,20",
        "21,50",
        "51,100",
        "101,200",
        "201,500",
    ]
    assert payload["q_organization_keyword_tags"] == ALLOWED_APOLLO_INDUSTRIES
    assert payload["q_organization_keywords"] == (
        "claims processing OR back office OR document processing OR customer operations OR "
        "dispatch OR intake OR scheduling OR compliance"
    )


def test_allowed_apollo_industries_cover_tier_1_and_tier_2_workflow_markets():
    assert ALLOWED_APOLLO_INDUSTRIES == [
        "insurance",
        "hospital & health care",
        "medical practice",
        "mental health care",
        "legal services",
        "law practice",
        "staffing and recruiting",
        "human resources",
        "logistics and supply chain",
        "transportation/trucking/railroad",
        "warehousing",
        "facilities services",
        "construction",
        "real estate",
        "financial services",
        "accounting",
        "consumer services",
        "automotive",
    ]


def test_discover_from_apollo_keeps_allowed_industry_variations_and_rejects_noise():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organizations": [
                    {"name": "Regional Claims Co", "industry": "Insurance"},
                    {"name": "Clinic Ops Group", "industry": "Hospitals and Health Care"},
                    {"name": "Dental Workflow LLC", "industry": "Medical Practices"},
                    {"name": "Trucking Dispatch Inc", "industry": "Truck Transportation"},
                    {"name": "Warehouse Crew Co", "industry": "Warehousing and Storage"},
                    {"name": "Property Desk LLC", "industry": "Real Estate Agents and Brokers"},
                    {"name": "Repair Workflow Shop", "industry": "Motor Vehicle Manufacturing"},
                    {"name": "Book Print Media", "industry": "Publishing"},
                    {"name": "Generic Unknown Ops", "industry": None},
                ],
                "pagination": {"page": 1, "per_page": 25, "total_entries": 9},
            },
        )

    client = ApolloClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = discover_from_apollo(client=client, max_results=10)

    assert [candidate.company_name for candidate in candidates] == [
        "Regional Claims Co",
        "Clinic Ops Group",
        "Dental Workflow LLC",
        "Trucking Dispatch Inc",
        "Warehouse Crew Co",
        "Property Desk LLC",
        "Repair Workflow Shop",
    ]


def test_discover_from_apollo_rejects_publishing_even_when_employee_range_matches():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organizations": [
                    {
                        "name": "Publisher Back Office",
                        "industry": "Publishing",
                        "estimated_num_employees": 120,
                    },
                    {
                        "name": "Accounting Ops Firm",
                        "industry": "Accounting",
                        "estimated_num_employees": 75,
                    },
                ],
                "pagination": {"page": 1, "per_page": 25, "total_entries": 2},
            },
        )

    client = ApolloClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = discover_from_apollo(client=client, max_results=10)

    assert [candidate.company_name for candidate in candidates] == ["Accounting Ops Firm"]


def test_discover_from_apollo_filters_out_companies_outside_employee_range():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organizations": [
                    {
                        "name": "Tiny Solo",
                        "industry": "Insurance",
                        "estimated_num_employees": 5,
                    },
                    {
                        "name": "Regional Claims Co",
                        "industry": "Insurance",
                        "estimated_num_employees": 120,
                    },
                    {
                        "name": "Mega Consulting",
                        "industry": "Insurance",
                        "estimated_num_employees": 465000,
                    },
                ],
                "pagination": {"page": 1, "per_page": 25, "total_entries": 3},
            },
        )

    client = ApolloClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = discover_from_apollo(
        client=client,
        max_results=10,
        min_employees=20,
        max_employees=500,
    )

    assert [candidate.company_name for candidate in candidates] == ["Regional Claims Co"]


def test_discover_from_apollo_paginates_until_requested_limit():
    seen_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        page = body["page"]
        seen_pages.append(page)
        names = {1: ["Alpha Ops", "Beta Support"], 2: ["Gamma Logistics"]}[page]
        return httpx.Response(
            200,
            json={
                "organizations": [
                    {
                        "name": name,
                        "industry": "Logistics and Supply Chain",
                        "website_url": f"https://{name.split()[0].lower()}.example",
                    }
                    for name in names
                ],
                "pagination": {"page": page, "per_page": 2, "total_entries": 3},
            },
        )

    client = ApolloClient(
        api_key="test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = discover_from_apollo(client=client, max_results=3, per_page=2)

    assert seen_pages == [1, 2]
    assert [candidate.company_name for candidate in candidates] == [
        "Alpha Ops",
        "Beta Support",
        "Gamma Logistics",
    ]


def test_apollo_client_raises_helpful_error_for_auth_failure():
    client = ApolloClient(
        api_key="bad-key",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"error": "invalid api key"})
            )
        ),
    )

    with pytest.raises(ApolloApiError, match="Apollo API request failed with status 401"):
        client.search_companies(ApolloSearchConfig())
