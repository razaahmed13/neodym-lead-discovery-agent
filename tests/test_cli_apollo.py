from typer.testing import CliRunner

from neodym_lead_discovery.cli import app

runner = CliRunner()


def test_discover_with_apollo_api_imports_companies_from_env_key(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, api_key: str):
            assert api_key == "env-apollo-key"

    def fake_discover_from_apollo(
        *, client, max_results, per_page, locations, industries, keywords
    ):
        from neodym_lead_discovery.models import LeadCandidate

        assert isinstance(client, FakeClient)
        assert max_results == 2
        assert per_page == 2
        assert locations == ["United States"]
        assert "healthcare" in industries
        assert "workflow automation" in keywords
        return [
            LeadCandidate(
                company_name="Acme Claims",
                website="https://acmeclaims.example",
                industry="Insurance",
                source_links=["https://acmeclaims.example"],
                discovery_source="apollo_api",
            )
        ]

    monkeypatch.setenv("APOLLO_API_KEY", "env-apollo-key")
    monkeypatch.setattr("neodym_lead_discovery.cli.ApolloClient", FakeClient)
    monkeypatch.setattr("neodym_lead_discovery.cli.discover_from_apollo", fake_discover_from_apollo)

    db_path = tmp_path / "leads.sqlite"
    result = runner.invoke(
        app,
        [
            "discover",
            "--apollo-api",
            "--max-results",
            "2",
            "--per-page",
            "2",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "Imported 1 lead candidates" in result.output


def test_discover_defaults_to_apollo_api_when_env_key_exists(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, api_key: str):
            calls.append(api_key)

    def fake_discover_from_apollo(**kwargs):
        return []

    monkeypatch.setenv("APOLLO_API_KEY", "env-apollo-key")
    monkeypatch.setattr("neodym_lead_discovery.cli.ApolloClient", FakeClient)
    monkeypatch.setattr("neodym_lead_discovery.cli.discover_from_apollo", fake_discover_from_apollo)

    result = runner.invoke(app, ["discover", "--db", str(tmp_path / "leads.sqlite")])

    assert result.exit_code == 0
    assert calls == ["env-apollo-key"]
    assert "Imported 0 lead candidates" in result.output


def test_discover_without_csv_or_apollo_key_explains_how_to_automate(monkeypatch, tmp_path):
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)

    result = runner.invoke(app, ["discover", "--db", str(tmp_path / "leads.sqlite")])

    assert result.exit_code == 2
    assert "Set APOLLO_API_KEY" in result.output
    assert "--csv" in result.output
