from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.storage import LeadStorage

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_no_longer_exposes_enrich_command() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "enrich" not in result.output.lower()


def test_storage_no_longer_creates_or_keeps_enriched_companies_table(tmp_path: Path) -> None:
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    with storage._connect() as conn:  # noqa: SLF001 - schema cleanup regression test
        conn.execute(
            """
            CREATE TABLE enriched_companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL UNIQUE,
                company TEXT NOT NULL,
                website TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    storage.initialize()

    with storage._connect() as conn:  # noqa: SLF001 - schema absence regression test
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()

    assert "enriched_companies" not in {row["name"] for row in rows}
    assert not hasattr(storage, "save_enriched_company")
    assert not hasattr(storage, "list_enriched_companies")


def test_enrichment_models_and_modules_are_removed() -> None:
    import neodym_lead_discovery.models as models

    removed_model_names = [
        "EnrichedCompany",
        "StructuredCompanyProfile",
        "WebsitePageProfile",
    ]

    for model_name in removed_model_names:
        assert not hasattr(models, model_name)

    assert not (PROJECT_ROOT / "src" / "neodym_lead_discovery" / "enrichment").exists()
