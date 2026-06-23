import json
from pathlib import Path

from typer.testing import CliRunner

from neodym_lead_discovery.cli import app
from neodym_lead_discovery.website_reader import (
    DEFAULT_READER_MODEL,
    READER_SCHEMA_KEYS,
    ReaderError,
    build_reader_prompt,
    parse_reader_json,
)


def test_default_reader_model_is_available_gemini_flash_model() -> None:
    assert DEFAULT_READER_MODEL == "gemini-2.0-flash"


VALID_READER_JSON = {
    "core_business_model": "Insurance media and talent development platform",
    "explicit_services_offered": ["advertising", "events", "recruiting"],
    "mentioned_software_or_tools": ["HubSpot"],
    "manual_friction_clues": ["workflow procedures"],
    "key_executives": ["Jane Doe - CEO"],
}


def test_build_reader_prompt_requires_tiny_strict_json_schema() -> None:
    prompt = build_reader_prompt("# Website context\nUseful text")

    assert "Extract only the following 5 data points" in prompt
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


def test_parse_reader_json_requires_exact_schema_keys() -> None:
    parsed = parse_reader_json(json.dumps(VALID_READER_JSON))

    assert parsed == VALID_READER_JSON


def test_parse_reader_json_normalizes_single_string_array_fields() -> None:
    gemini_payload = dict(VALID_READER_JSON)
    gemini_payload["manual_friction_clues"] = "Quote flow asks users to call an agent"

    parsed = parse_reader_json(json.dumps(gemini_payload))

    assert parsed["manual_friction_clues"] == ["Quote flow asks users to call an agent"]


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

    def fake_extract_reader_facts(markdown: str, api_key: str, model: str):
        assert "Insurance Nerds offers advertising" in markdown
        assert api_key == "test-gemini-key"
        assert model == DEFAULT_READER_MODEL
        return VALID_READER_JSON

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.write_website_context",
        fake_write_website_context,
    )
    monkeypatch.setattr(
        "neodym_lead_discovery.cli.extract_reader_facts",
        fake_extract_reader_facts,
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

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


def test_reader_output_requires_gemini_api_key(tmp_path: Path, monkeypatch) -> None:
    raw_output = tmp_path / "example-context.md"
    reader_output = tmp_path / "example-reader.json"

    def fake_write_website_context(url: str, output_path: Path, max_chars: int):
        output_path.write_text("# Website context\n\nUseful text")
        return output_path, 1

    monkeypatch.setattr(
        "neodym_lead_discovery.cli.write_website_context",
        fake_write_website_context,
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

    assert result.exit_code == 2
    assert "GEMINI_API_KEY is required" in result.output
    assert not reader_output.exists()
