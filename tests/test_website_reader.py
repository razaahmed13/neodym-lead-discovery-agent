import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.website_reader import (
    DEFAULT_READER_MODEL,
    DEFAULT_READER_TIMEOUT_SECONDS,
    READER_SCHEMA_KEYS,
    ReaderError,
    build_reader_prompt,
    extract_reader_facts,
    parse_reader_json,
)


def test_default_reader_model_matches_supported_codex_chatgpt_model() -> None:
    assert DEFAULT_READER_MODEL == "gpt-5.5"
    assert DEFAULT_READER_TIMEOUT_SECONDS == 180


def test_extract_reader_facts_uses_codex_cli_with_timeout_and_output_file(monkeypatch, tmp_path):
    output_payload = json.dumps(VALID_READER_JSON)
    captured = {}

    def fake_run(command, *, input, text, capture_output, timeout, check):
        captured["command"] = command
        captured["input"] = input
        captured["timeout"] = timeout
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(output_payload)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("neodym_lead_discovery.website_reader.subprocess.run", fake_run)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    facts = extract_reader_facts(
        "# Website context\nUseful text",
        model="gpt-5-nano",
        timeout_seconds=42,
    )

    assert facts == VALID_READER_JSON
    command = captured["command"]
    assert command[:2] == ["codex", "exec"]
    assert "--skip-git-repo-check" in command
    assert "--sandbox" in command
    assert "read-only" in command
    assert "--model" in command
    assert command[command.index("--model") + 1] == "gpt-5-nano"
    assert command[-1] == "-"
    assert captured["timeout"] == 42
    assert "Return only valid JSON" in captured["input"]


def test_extract_reader_facts_raises_reader_error_on_codex_timeout(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])

    monkeypatch.setattr("neodym_lead_discovery.website_reader.subprocess.run", fake_run)

    try:
        extract_reader_facts("# Website context", timeout_seconds=5)
    except ReaderError as exc:
        assert "Codex Reader timed out after 5s" in str(exc)
    else:
        raise AssertionError("Expected ReaderError for Codex timeout")


VALID_READER_JSON = {
    "core_business_model": "Insurance media and talent development platform",
    "explicit_services_offered": ["advertising", "events", "recruiting"],
    "mentioned_software_or_tools": ["HubSpot"],
    "manual_friction_clues": ["workflow procedures"],
    "key_executives": [
        {"name": "Jane Doe", "post": "CEO", "email": None},
        {"name": "John Smith", "post": None, "email": "john@example.com"},
    ],
    "job_openings": ["Chief Information Security Officer (CISO)"],
    "contact_emails": [
        {"email": "support@example.com", "name": None, "post": "Support"},
        {"email": "jane@example.com", "name": "Jane Doe", "post": "CEO"},
    ],
}


def test_build_reader_prompt_requires_tiny_strict_json_schema() -> None:
    prompt = build_reader_prompt("# Website context\nUseful text")

    assert "Extract only the following 7 data points" in prompt
    assert "Do not write a summary" in prompt
    for key in READER_SCHEMA_KEYS:
        assert f'"{key}"' in prompt
    assert "# Website context" in prompt


def test_build_reader_prompt_defines_manual_friction_as_workflow_signals() -> None:
    prompt = build_reader_prompt("# Website context\nUseful text")

    assert "manual_friction_clues" in prompt
    assert "Do not merely copy generic form fields, phone numbers, or app/portal mentions" in prompt
    assert "human-assisted decisions" in prompt
    assert "phone-based assistance" in prompt
    assert "structured intake that may require downstream review" in prompt
    assert "manual process that could be automated using AI agents or automation" in prompt


def test_build_reader_prompt_requests_jobs_and_contact_email_context() -> None:
    prompt = build_reader_prompt("# Website context\nUseful text")

    assert "job_openings" in prompt
    assert "career page" in prompt
    assert "null if no job openings are explicitly present" in prompt
    assert "contact_emails" in prompt
    assert "raw content" in prompt
    assert "name" in prompt
    assert "post" in prompt
    assert "use null when name or post is not available" in prompt


def test_parse_reader_json_requires_exact_schema_keys() -> None:
    parsed = parse_reader_json(json.dumps(VALID_READER_JSON))

    assert parsed == VALID_READER_JSON


def test_build_reader_prompt_requests_structured_key_executives() -> None:
    prompt = build_reader_prompt("# Website context\nUseful text")

    assert "key_executives" in prompt
    assert "array of objects" in prompt
    assert "exactly name, post, and email" in prompt
    assert "use null when post or email is not available" in prompt


def test_parse_reader_json_normalizes_single_string_array_fields() -> None:
    reader_payload = dict(VALID_READER_JSON)
    reader_payload["manual_friction_clues"] = "Quote flow asks users to call an agent"
    reader_payload["job_openings"] = "Chief Information Security Officer (CISO)"

    parsed = parse_reader_json(json.dumps(reader_payload))

    assert parsed["manual_friction_clues"] == ["Quote flow asks users to call an agent"]
    assert parsed["job_openings"] == ["Chief Information Security Officer (CISO)"]


def test_parse_reader_json_allows_null_jobs_contact_emails_and_executives() -> None:
    reader_payload = dict(VALID_READER_JSON)
    reader_payload["key_executives"] = None
    reader_payload["job_openings"] = None
    reader_payload["contact_emails"] = None

    parsed = parse_reader_json(json.dumps(reader_payload))

    assert parsed["key_executives"] is None
    assert parsed["job_openings"] is None
    assert parsed["contact_emails"] is None


def test_parse_reader_json_requires_key_executive_objects() -> None:
    reader_payload = dict(VALID_READER_JSON)
    reader_payload["key_executives"] = [{"name": "Jane Doe", "post": "CEO"}]

    try:
        parse_reader_json(json.dumps(reader_payload))
    except ReaderError as exc:
        assert "key_executives" in str(exc)
        assert "name, post, and email" in str(exc)
    else:
        raise AssertionError("Expected ReaderError for invalid key executive object")


def test_parse_reader_json_requires_contact_email_objects() -> None:
    reader_payload = dict(VALID_READER_JSON)
    reader_payload["contact_emails"] = [{"email": "support@example.com", "name": None}]

    try:
        parse_reader_json(json.dumps(reader_payload))
    except ReaderError as exc:
        assert "contact_emails" in str(exc)
        assert "email, name, and post" in str(exc)
    else:
        raise AssertionError("Expected ReaderError for invalid contact email object")


def test_parse_reader_json_rejects_extra_or_missing_keys() -> None:
    invalid = dict(VALID_READER_JSON)
    invalid["extra_summary"] = "not allowed"

    try:
        parse_reader_json(json.dumps(invalid))
    except ReaderError as exc:
        assert "exactly these keys" in str(exc)
    else:
        raise AssertionError("Expected ReaderError for non-strict schema")


def test_fetch_website_can_write_reader_output_file(tmp_path: Path, monkeypatch) -> None:
    raw_output = tmp_path / "example-context.md"
    reader_output = tmp_path / "example-reader.json"

    def fake_write_website_context(url: str, output_path: Path, max_chars: int):
        output_path.write_text("# Website context\n\nInsurance Nerds offers advertising.")
        return output_path, 1

    def fake_extract_reader_facts(markdown: str, model: str, timeout_seconds: int):
        assert "Insurance Nerds offers advertising" in markdown
        assert model == DEFAULT_READER_MODEL
        assert timeout_seconds == DEFAULT_READER_TIMEOUT_SECONDS
        return VALID_READER_JSON

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.write_website_context",
        fake_write_website_context,
    )
    monkeypatch.setattr(
        "neodym_lead_discovery.cli.extract_reader_facts",
        fake_extract_reader_facts,
    )

    result = CliRunner().invoke(
        app,
        [
            "fetch-website",
            "https://example.com",
            "--output",
            str(raw_output),
            "--reader-output",
            str(reader_output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert raw_output.exists()
    assert json.loads(reader_output.read_text()) == VALID_READER_JSON
    assert "Wrote reader fact sheet" in result.output


def test_reader_output_uses_codex_without_gemini_api_key(tmp_path: Path, monkeypatch) -> None:
    raw_output = tmp_path / "example-context.md"
    reader_output = tmp_path / "example-reader.json"

    def fake_write_website_context(url: str, output_path: Path, max_chars: int):
        output_path.write_text("# Website context\n\nUseful text")
        return output_path, 1

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.write_website_context",
        fake_write_website_context,
    )
    monkeypatch.setattr(
        "neodym_lead_discovery.cli.extract_reader_facts",
        lambda markdown, model, timeout_seconds: VALID_READER_JSON,
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "fetch-website",
            "https://example.com",
            "--output",
            str(raw_output),
            "--reader-output",
            str(reader_output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(reader_output.read_text()) == VALID_READER_JSON
