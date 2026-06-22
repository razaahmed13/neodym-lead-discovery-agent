from __future__ import annotations

from typer.testing import CliRunner

from neodym_lead_discovery import cli
from neodym_lead_discovery.cli import DEFAULT_DB_PATH
from neodym_lead_discovery.models import EnrichedCompany, LeadCandidate, StructuredCompanyProfile
from neodym_lead_discovery.storage import LeadStorage

runner = CliRunner()


def test_enrich_command_crawls_candidates_and_persists_llm_ready_profiles(tmp_path, monkeypatch):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    storage.upsert_candidate(LeadCandidate(company_name="ABC Logistics", website="https://abc.example"))

    def fake_enrich(candidate: LeadCandidate, *, max_pages: int):
        assert max_pages == 4
        return EnrichedCompany(
            candidate=candidate,
            website_title="ABC Logistics",
            structured_profile=StructuredCompanyProfile(
                company_name=candidate.company_name,
                website=candidate.website,
                summary="LLM-ready profile",
                llm_context={"pages_crawled": 1, "evidence_text": "SOURCE: https://abc.example"},
            ),
        )

    monkeypatch.setattr(cli, "enrich_public_website", fake_enrich)

    result = runner.invoke(app=cli.app, args=["enrich", "--db", str(db_path), "--max-pages", "4"])

    assert result.exit_code == 0
    assert "Enriched 1 companies" in result.output
    rows = LeadStorage(db_path).list_enriched_companies()
    assert rows[0].structured_profile is not None
    assert rows[0].structured_profile.summary == "LLM-ready profile"


def test_enrich_uses_project_default_db_when_db_option_is_omitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = LeadStorage(DEFAULT_DB_PATH)
    storage.initialize()
    storage.upsert_candidate(LeadCandidate(company_name="ABC Logistics", website="https://abc.example"))

    def fake_enrich(candidate: LeadCandidate, *, max_pages: int):
        return EnrichedCompany(
            candidate=candidate,
            website_title="ABC Logistics",
            structured_profile=StructuredCompanyProfile(
                company_name=candidate.company_name,
                website=candidate.website,
                summary="Default DB profile",
            ),
        )

    monkeypatch.setattr(cli, "enrich_public_website", fake_enrich)

    result = runner.invoke(app=cli.app, args=["enrich"])

    assert result.exit_code == 0
    assert f"Enriched 1 companies into {DEFAULT_DB_PATH}" in result.output
    rows = LeadStorage(DEFAULT_DB_PATH).list_enriched_companies()
    assert rows[0].structured_profile is not None
    assert rows[0].structured_profile.summary == "Default DB profile"
