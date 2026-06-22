from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.discovery.csv_importer import import_csv
from neodym_lead_discovery.storage import LeadStorage

FIXTURE = Path(__file__).parent / "fixtures" / "sample_companies.csv"


def test_import_csv_maps_apollo_like_headers_to_lead_candidates():
    leads = import_csv(FIXTURE, discovery_source="apollo_export")

    assert len(leads) == 2
    first = leads[0]
    assert first.company_name == "ABC Logistics LLC"
    assert first.website == "https://www.abclogistics.example"
    assert first.industry == "Logistics"
    assert first.location == "Austin, TX"
    assert first.description == "Regional freight and dispatch provider"
    assert first.company_size == "51-200"
    assert first.discovery_source == "apollo_export"
    assert "https://www.abclogistics.example" in first.source_links
    assert "https://linkedin.com/company/abc-logistics" in first.source_links
    assert first.raw_sources[0].label == "apollo_export"


def test_discover_cli_imports_csv_into_sqlite(tmp_path):
    db_path = tmp_path / "leads.sqlite"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "discover",
            "--csv",
            str(FIXTURE),
            "--db",
            str(db_path),
            "--source",
            "apollo_export",
        ],
    )

    assert result.exit_code == 0
    assert "Imported 2 lead candidates" in result.output
    storage = LeadStorage(db_path)
    assert storage.count_candidates() == 2
