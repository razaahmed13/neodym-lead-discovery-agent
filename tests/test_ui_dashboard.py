from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery import cli
from neodym_lead_discovery.models import (
    EnrichedCompany,
    LeadCandidate,
    StructuredCompanyProfile,
)
from neodym_lead_discovery.storage import LeadStorage
from neodym_lead_discovery.ui import load_dashboard_data

runner = CliRunner()


def test_load_dashboard_data_summarizes_candidates_and_enriched_companies(tmp_path: Path):
    db_path = tmp_path / "lead_discovery.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    candidate_id = storage.upsert_candidate(
        LeadCandidate(
            company_name="ABC Logistics",
            website="https://abc.example",
            industry="logistics",
            company_size="85",
            discovery_source="apollo_api",
        )
    )
    storage.save_enriched_company(
        candidate_id,
        EnrichedCompany(
            candidate=LeadCandidate(company_name="ABC Logistics", website="https://abc.example"),
            website_summary="Regional freight operations partner.",
            services_or_products=["Dispatch", "Warehouse coordination"],
            operational_complexity_signals=["dispatch", "scheduling"],
            structured_profile=StructuredCompanyProfile(
                company_name="ABC Logistics",
                website="https://abc.example",
                summary="Regional freight operations partner.",
                llm_context={
                    "pages_crawled": 2,
                    "page_evidence": [
                        {
                            "url": "https://abc.example/services",
                            "page_summary": "Services page summary.",
                            "manual_process_signals": ["Driver scheduling"],
                            "automation_opportunities": ["Automate driver scheduling"],
                            "supporting_excerpt": "schedules drivers",
                            "limitations": ["No explicit manual tooling evidence"],
                        }
                    ],
                },
            ),
        ),
    )

    dashboard = load_dashboard_data(db_path)

    assert dashboard["metrics"] == {
        "candidates": 1,
        "enriched_companies": 1,
        "automation_opportunities": 1,
        "manual_process_signals": 1,
    }
    assert dashboard["candidates"][0]["status"] == "enriched"
    assert dashboard["candidates"][0]["company"] == "ABC Logistics"
    assert dashboard["enriched_companies"][0]["summary"] == "Regional freight operations partner."
    assert dashboard["enriched_companies"][0]["pages_crawled"] == 2
    assert dashboard["enriched_companies"][0]["automation_opportunities"] == [
        "Automate driver scheduling"
    ]


def test_ui_command_launches_streamlit_with_project_dashboard(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "lead_discovery.sqlite"
    calls: list[dict[str, object]] = []

    def fake_run(command, *, env, check):
        calls.append({"command": command, "env": env, "check": check})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = runner.invoke(cli.app, ["ui", "--db", str(db_path), "--port", "8765"])

    assert result.exit_code == 0
    assert "Starting Lead Discovery UI" in result.output
    command = calls[0]["command"]
    assert isinstance(command, list)
    assert command[:3] == [cli.sys.executable, "-m", "neodym_lead_discovery.ui"]
    assert "--db" in command
    assert str(db_path) in command
    assert "--port" in command
    assert "8765" in command
    env = calls[0]["env"]
    assert isinstance(env, dict)
    assert env["LEAD_DISCOVERY_DB"] == str(db_path)
    assert calls[0]["check"] is True
