from typer.testing import CliRunner

from neodym_lead_discovery.cli import app

runner = CliRunner()


def test_cli_help_lists_pipeline_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    commands = ["discover", "analyze", "score", "report", "evaluate", "digest", "run-all"]
    for command in commands:
        assert command in result.output


def test_version_option_prints_package_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert "neodym-lead-discovery-agent" in result.output
    assert "0.1.0" in result.output
