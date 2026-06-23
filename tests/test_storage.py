import json
from datetime import UTC, datetime

from neodym_lead_discovery.models import LeadCandidate, QualifiedLead, ScoreBreakdown
from neodym_lead_discovery.storage import LeadStorage


def test_storage_creates_schema_and_upserts_candidates_by_normalized_domain(tmp_path):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()

    first_id = storage.upsert_candidate(
        LeadCandidate(
            company_name="ABC Logistics LLC",
            website="https://www.abclogistics.example/",
            industry="Logistics",
            source_links=["https://www.abclogistics.example/"],
            discovery_source="apollo_export",
        )
    )
    second_id = storage.upsert_candidate(
        LeadCandidate(
            company_name="ABC Logistics",
            website="http://abclogistics.example",
            industry="Logistics",
            source_links=["http://abclogistics.example"],
            discovery_source="csv",
        )
    )

    assert second_id == first_id
    assert storage.count_candidates() == 1
    saved = storage.get_candidate(first_id)
    assert saved is not None
    assert saved.company_name == "ABC Logistics"
    assert saved.discovery_source == "csv"


def test_storage_saves_structured_website_facts_without_raw_content(tmp_path):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    candidate = LeadCandidate(
        company_name="SmartTalent",
        website="https://smarttalentstaffing.com/",
        industry="Staffing",
        location="Washington",
        source_links=["https://smarttalentstaffing.com/"],
    )
    candidate_id = storage.upsert_candidate(candidate)
    facts = {
        "core_business_model": "Staffing agency",
        "explicit_services_offered": ["Temporary staffing"],
        "mentioned_software_or_tools": None,
        "manual_friction_clues": ["Candidates wait for text-message follow-up."],
        "key_executives": None,
        "job_openings": None,
        "contact_emails": None,
    }

    fact_id = storage.save_candidate_website_facts(candidate_id, candidate, facts, page_count=4)
    saved = storage.get_candidate_website_facts(candidate_id)

    assert fact_id > 0
    assert saved is not None
    assert saved["candidate_id"] == candidate_id
    assert saved["company_name"] == "SmartTalent"
    assert "location" not in saved
    assert saved["industry"] == "Staffing"
    assert saved["website"] == "https://smarttalentstaffing.com/"
    assert saved["page_count"] == 4
    assert saved["facts"] == facts

    with storage._connect() as conn:
        row = conn.execute(
            "SELECT * FROM candidate_website_facts WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
    serialized_row = json.dumps(dict(row))
    assert "Candidates wait for text-message follow-up" in serialized_row
    assert "# Website context" not in serialized_row
    assert "## Source:" not in serialized_row
    row_keys = set(row.keys())
    assert "raw_content" not in row_keys
    assert "context" not in row_keys
    assert "location" not in row_keys


def test_storage_persists_qualified_lead_with_run_state(tmp_path):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    run_id = storage.start_run(stage="score", metadata={"source": "test"})

    lead = QualifiedLead(
        company="ABC Logistics",
        website="https://abclogistics.example",
        industry="Logistics",
        contact=None,
        fit_score=8.5,
        reason="Strong logistics automation fit.",
        pain_point="Manual dispatch workflows.",
        opportunity="AI dispatch assistant.",
        source_links=["https://abclogistics.example"],
        score_breakdown=ScoreBreakdown(raw_score_100=85.0, fit_score=8.5, criterion_points={}),
        generated_at=datetime(2026, 6, 22, tzinfo=UTC),
    )

    lead_id = storage.save_qualified_lead(lead, run_id=run_id)
    storage.finish_run(run_id, status="completed", metadata={"lead_count": 1})

    saved_leads = storage.list_qualified_leads()
    saved_run = storage.get_run(run_id)

    assert lead_id > 0
    assert len(saved_leads) == 1
    assert saved_leads[0].company == "ABC Logistics"
    assert saved_run is not None
    assert saved_run["status"] == "completed"
    assert saved_run["metadata"]["lead_count"] == 1
