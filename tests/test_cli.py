from typer.testing import CliRunner

from neodym_lead_discovery import cli as cli_module
from neodym_lead_discovery.cli import app
from neodym_lead_discovery.models import LeadCandidate
from neodym_lead_discovery.storage import LeadStorage
from neodym_lead_discovery.website_reader import ReaderError

runner = CliRunner()


def test_cli_help_lists_pipeline_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    commands = [
        "discover",
        "enrich-websites",
        "analyze",
        "score",
        "report",
        "evaluate",
        "digest",
        "run-all",
    ]
    for command in commands:
        assert command in result.output


def test_enrich_websites_fetches_reader_facts_into_db_without_raw_files(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    storage.upsert_candidate(
        LeadCandidate(
            company_name="SmartTalent",
            website="https://smarttalentstaffing.com/",
            industry="Staffing",
            location="Washington",
            source_links=["https://smarttalentstaffing.com/"],
        )
    )
    captured_markdown = []

    def fake_fetch_website_context(url: str, max_chars=None):
        assert url == "https://smarttalentstaffing.com/"
        assert max_chars is None
        return (
            "# Website context\n\n"
            "## Source: https://smarttalentstaffing.com/\n\n"
            "Raw page text"
        ), 4

    def fake_extract_reader_facts(markdown: str, api_key: str, model: str):
        captured_markdown.append(markdown)
        assert api_key == "test-gemini-key"
        return {
            "core_business_model": "Staffing agency",
            "explicit_services_offered": ["Temporary staffing"],
            "mentioned_software_or_tools": None,
            "manual_friction_clues": ["Candidates wait for text-message follow-up."],
            "key_executives": None,
            "job_openings": None,
            "contact_emails": None,
        }

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.fetch_website_context",
        fake_fetch_website_context,
    )
    monkeypatch.setattr("neodym_lead_discovery.cli.extract_reader_facts", fake_extract_reader_facts)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    result = runner.invoke(app, ["enrich-websites", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Enriched 1 candidate website(s)" in result.output
    assert captured_markdown == [
        "# Website context\n\n## Source: https://smarttalentstaffing.com/\n\nRaw page text"
    ]
    saved = storage.get_candidate_website_facts(1)
    assert saved is not None
    assert saved["company_name"] == "SmartTalent"
    assert saved["facts"]["core_business_model"] == "Staffing agency"
    generated_files = {path.name for path in tmp_path.iterdir()}
    assert generated_files == {"leads.sqlite"}


def test_enrich_websites_retries_reader_rate_limits_and_throttles_between_candidates(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "leads.sqlite"
    storage = LeadStorage(db_path)
    storage.initialize()
    for name in ["First Co", "Second Co"]:
        storage.upsert_candidate(
            LeadCandidate(
                company_name=name,
                website=f"https://{name.split()[0].lower()}.example",
                industry="Insurance",
                source_links=[f"https://{name.split()[0].lower()}.example"],
            )
        )

    reader_calls = []
    sleeps = []

    def fake_fetch_website_context(url: str, max_chars=None):
        return f"# Context for {url}", 1

    def fake_extract_reader_facts(markdown: str, api_key: str, model: str):
        reader_calls.append(markdown)
        if len(reader_calls) == 1:
            raise ReaderError("Gemini Reader request failed: HTTP 429")
        return {
            "core_business_model": "Insurance operations",
            "explicit_services_offered": None,
            "mentioned_software_or_tools": None,
            "manual_friction_clues": None,
            "key_executives": None,
            "job_openings": None,
            "contact_emails": None,
        }

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.fetch_website_context",
        fake_fetch_website_context,
    )
    monkeypatch.setattr("neodym_lead_discovery.cli.extract_reader_facts", fake_extract_reader_facts)
    monkeypatch.setattr(cli_module, "sleep", sleeps.append, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    result = runner.invoke(
        app,
        [
            "enrich-websites",
            "--db",
            str(db_path),
            "--reader-delay-seconds",
            "3",
            "--reader-retries",
            "1",
            "--reader-retry-delay-seconds",
            "7",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Enriched 2 candidate website(s)" in result.output
    assert len(reader_calls) == 3
    assert sleeps == [7.0, 3.0]
    assert storage.get_candidate_website_facts(1) is not None
    assert storage.get_candidate_website_facts(2) is not None

def test_version_option_prints_package_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "neodym-lead-discovery-agent" in result.output
    assert "0.1.0" in result.output
