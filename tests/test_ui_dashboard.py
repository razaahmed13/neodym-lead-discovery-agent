from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery import cli
from neodym_lead_discovery.models import LeadCandidate
from neodym_lead_discovery.storage import LeadStorage
from neodym_lead_discovery.ui import load_dashboard_data, render_dashboard_html

runner = CliRunner()


def test_load_dashboard_data_summarizes_discovered_candidates(tmp_path: Path):
    db_path = tmp_path / "lead_discovery.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    storage.upsert_candidate(
        LeadCandidate(
            company_name="ABC Logistics",
            website="https://abc.example",
            industry="logistics",
            location="Austin, TX",
            company_size="85",
            discovery_source="apollo_api",
        )
    )

    dashboard = load_dashboard_data(db_path)

    assert dashboard["metrics"] == {"candidates": 1}
    assert dashboard["candidates"][0] == {
        "company": "ABC Logistics",
        "website": "https://abc.example",
        "industry": "logistics",
        "location": "Austin, TX",
        "employees": "85",
        "source": "apollo_api",
        "status": "discovered",
    }
    assert "enriched_companies" not in dashboard


def test_ui_command_launches_project_dashboard(tmp_path: Path, monkeypatch):
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


def test_dashboard_sidebar_lists_candidates_only(tmp_path: Path):
    db_path = tmp_path / "lead_discovery.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    storage.upsert_candidate(
        LeadCandidate(company_name="ABC Logistics", website="https://abc.example")
    )
    storage.upsert_candidate(
        LeadCandidate(company_name="Clearview Health", website="https://clearview.example")
    )

    html = render_dashboard_html(db_path)

    assert '<aside class="sidebar"' in html
    assert "Candidates" in html
    assert "ABC Logistics" in html
    assert "Clearview Health" in html
    assert "Enriched companies" not in html
    assert "enriched-selector" not in html
    assert "data-select-company" not in html
    assert "data-company-card" not in html
    assert "selectCompany" not in html
