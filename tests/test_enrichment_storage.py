from __future__ import annotations

import json

from neodym_lead_discovery.models import EnrichedCompany, LeadCandidate, StructuredCompanyProfile
from neodym_lead_discovery.storage import LeadStorage


def test_storage_saves_and_lists_enriched_companies_for_llm_context(tmp_path):
    storage = LeadStorage(tmp_path / "leads.sqlite")
    storage.initialize()
    candidate = LeadCandidate(company_name="ABC Logistics", website="https://abc.example")
    candidate_id = storage.upsert_candidate(candidate)
    enriched = EnrichedCompany(
        candidate=candidate,
        website_title="ABC Logistics",
        structured_profile=StructuredCompanyProfile(
            company_name="ABC Logistics",
            website="https://abc.example",
            summary="Freight workflows",
            llm_context={"pages_crawled": 1, "evidence_text": "SOURCE: https://abc.example"},
        ),
    )

    enriched_id = storage.save_enriched_company(candidate_id, enriched)

    rows = storage.list_enriched_companies()
    assert enriched_id == 1
    assert rows[0].structured_profile is not None
    assert rows[0].structured_profile.llm_context["pages_crawled"] == 1

    with storage._connect() as conn:
        raw = conn.execute("SELECT payload_json FROM enriched_companies").fetchone()["payload_json"]
    evidence_text = json.loads(raw)["structured_profile"]["llm_context"]["evidence_text"]
    assert evidence_text.startswith("SOURCE")


def test_storage_lists_candidates_in_id_order(tmp_path):
    storage = LeadStorage(tmp_path / "leads.sqlite")
    storage.initialize()
    storage.upsert_candidate(LeadCandidate(company_name="First", website="https://first.example"))
    storage.upsert_candidate(LeadCandidate(company_name="Second", website="https://second.example"))

    rows = storage.list_candidates(limit=10)

    assert [row[0] for row in rows] == [1, 2]
    assert [row[1].company_name for row in rows] == ["First", "Second"]
