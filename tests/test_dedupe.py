from neodym_lead_discovery.discovery.dedupe import (
    are_duplicate_candidates,
    canonical_company_key,
    canonical_domain,
)
from neodym_lead_discovery.models import LeadCandidate


def test_canonical_domain_normalizes_scheme_www_path_and_case():
    assert canonical_domain("https://www.Example.com/about?x=1") == "example.com"
    assert canonical_domain("example.com/") == "example.com"


def test_canonical_company_key_removes_common_suffixes_and_punctuation():
    assert canonical_company_key("ABC Logistics, LLC") == "abc logistics"
    assert canonical_company_key("ABC Logistics Inc.") == "abc logistics"


def test_are_duplicate_candidates_matches_domain_or_company_key():
    by_domain_a = LeadCandidate(company_name="ABC Freight", website="https://www.example.com")
    by_domain_b = LeadCandidate(company_name="Different Name", website="http://example.com/about")
    by_name_a = LeadCandidate(company_name="Bright Claims Inc", website=None)
    by_name_b = LeadCandidate(company_name="Bright Claims", website=None)

    assert are_duplicate_candidates(by_domain_a, by_domain_b)
    assert are_duplicate_candidates(by_name_a, by_name_b)
