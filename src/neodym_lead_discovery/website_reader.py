from __future__ import annotations

import json
import re
import subprocess
import tempfile
from typing import Any

READER_SCHEMA_KEYS = [
    "core_business_model",
    "explicit_services_offered",
    "mentioned_software_or_tools",
    "manual_friction_clues",
    "key_executives",
    "job_openings",
    "contact_emails",
]
ARRAY_STRING_KEYS = [
    "explicit_services_offered",
    "mentioned_software_or_tools",
    "manual_friction_clues",
    "job_openings",
]

DEFAULT_READER_MODEL = "gpt-5.5"
DEFAULT_READER_TIMEOUT_SECONDS = 180


class ReaderError(RuntimeError):
    """Raised when the reader LLM cannot produce the strict fact schema."""


def build_reader_prompt(website_markdown: str) -> str:
    """Build the tiny Reader prompt for extracting a strict seven-key fact sheet."""
    schema = {
        "core_business_model": "string or null",
        "explicit_services_offered": ["array of strings, or null"],
        "mentioned_software_or_tools": ["array of strings, or null"],
        "manual_friction_clues": ["array of strings, or null"],
        "key_executives": [
            {
                "name": "executive name string",
                "post": "executive role/title string, or null",
                "email": "executive email address string, or null",
            }
        ],
        "job_openings": ["array of job title strings from career page content, or null"],
        "contact_emails": [
            {
                "email": "email address string",
                "name": "associated person name string, or null",
                "post": "associated role/department/title string, or null",
            }
        ],
    }
    return (
        "Scan this website text. Extract only the following 7 data points into this "
        "strict JSON schema. If a point is not explicitly mentioned, write null. "
        "For explicit_services_offered, mentioned_software_or_tools, "
        "manual_friction_clues, and job_openings, return either an array of "
        "strings or null; never return a bare string. Do not write a summary. "
        "Return only valid JSON with exactly these keys.\n\n"
        "For manual_friction_clues, extract higher-level workflow or automation signals, "
        "not raw nearby text. Do not merely copy generic form fields, phone numbers, or "
        "app/portal mentions. Include a clue only when it suggests human-assisted decisions, "
        "phone-based assistance, manual handoffs, repetitive operations, any manual process "
        "that could be automated using AI agents or automation, or structured intake "
        "that may require downstream review. Rewrite clues as concise evidence-backed "
        "business observations, such as: Customers are directed to work with an agent to "
        "choose the right policy; Support and quote flows rely on phone-based assistance; "
        "Claims are submitted through app/portal workflows, suggesting structured intake "
        "that may require downstream review.\n\n"
        "For job_openings, extract job titles from career page content only; use "
        "null if no job openings are explicitly present.\n\n"
        "For key_executives, extract every executive or senior leader explicitly "
        "mentioned in the raw content. Return null if none are present. Otherwise "
        "return an array of objects with exactly name, post, and email. The name "
        "must be the executive's name. The post may be a title or leadership role "
        "such as CEO, Founder, CTO, President, or Head of Operations. use null "
        "when post or email is not available.\n\n"
        "For contact_emails, extract every contact email visible in the raw content. "
        "Return null if none are present. Otherwise return an array of objects with "
        "exactly email, name, and post. use null when name or post is not available. "
        "The post may be a role, title, department, or contact category such as "
        "Support, Sales, Press, Partnerships, CEO, or CTO.\n\n"
        f"JSON schema:\n{json.dumps(schema, indent=2)}\n\n"
        "Website text:\n"
        f"{website_markdown}"
    )


def extract_reader_facts(
    website_markdown: str,
    model: str = DEFAULT_READER_MODEL,
    timeout_seconds: int = DEFAULT_READER_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Use Codex CLI to convert Markdown into a compact fact sheet."""
    prompt = build_reader_prompt(website_markdown)
    response_text = _call_codex_reader(
        prompt=prompt,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    return parse_reader_json(response_text)


def parse_reader_json(response_text: str) -> dict[str, Any]:
    """Parse and validate the Reader's strict JSON response."""
    candidate = _strip_json_fences(response_text)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ReaderError("Reader response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ReaderError("Reader response must be a JSON object.")

    expected_keys = set(READER_SCHEMA_KEYS)
    actual_keys = set(payload.keys())
    if actual_keys != expected_keys:
        raise ReaderError(
            "Reader response must contain exactly these keys: " + ", ".join(READER_SCHEMA_KEYS)
        )

    _normalize_reader_types(payload)
    _validate_reader_types(payload)
    return {key: payload[key] for key in READER_SCHEMA_KEYS}


def _call_codex_reader(prompt: str, model: str, timeout_seconds: int) -> str:
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=True) as output_file:
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--model",
            model,
            "--output-last-message",
            output_file.name,
            "-",
        ]
        try:
            result = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ReaderError("Codex Reader failed: codex CLI was not found on PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ReaderError(f"Codex Reader timed out after {timeout_seconds:g}s") from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            detail = f": {stderr}" if stderr else ""
            raise ReaderError(f"Codex Reader failed with exit code {result.returncode}{detail}")

        response_text = output_file.read().strip()
        if not response_text:
            stdout = result.stdout.strip()
            if stdout:
                return stdout
            raise ReaderError("Codex Reader response did not contain text output.")
        return response_text


def _strip_json_fences(response_text: str) -> str:
    stripped = response_text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _normalize_reader_types(payload: dict[str, Any]) -> None:
    """Tolerate common reader JSON drift without losing strict output shape."""
    for key in ARRAY_STRING_KEYS:
        value = payload[key]
        if isinstance(value, str):
            stripped = value.strip()
            payload[key] = [stripped] if stripped else None


def _validate_reader_types(payload: dict[str, Any]) -> None:
    if payload["core_business_model"] is not None and not isinstance(
        payload["core_business_model"],
        str,
    ):
        raise ReaderError("core_business_model must be a string or null.")

    for key in ARRAY_STRING_KEYS:
        value = payload[key]
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ReaderError(f"{key} must be an array of strings or null.")

    _validate_key_executives(payload["key_executives"])
    _validate_contact_emails(payload["contact_emails"])


def _validate_key_executives(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ReaderError("key_executives must be an array of objects or null.")
    for item in value:
        if not isinstance(item, dict):
            raise ReaderError("key_executives must contain objects.")
        if set(item.keys()) != {"name", "post", "email"}:
            raise ReaderError(
                "key_executives objects must contain exactly name, post, and email."
            )
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise ReaderError("key_executives name must be a non-empty string.")
        if item["post"] is not None and not isinstance(item["post"], str):
            raise ReaderError("key_executives post must be a string or null.")
        if item["email"] is not None and not isinstance(item["email"], str):
            raise ReaderError("key_executives email must be a string or null.")


def _validate_contact_emails(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ReaderError("contact_emails must be an array of objects or null.")

    expected_keys = {"email", "name", "post"}
    for item in value:
        if not isinstance(item, dict) or set(item.keys()) != expected_keys:
            raise ReaderError(
                "contact_emails entries must be objects with exactly email, name, and post."
            )
        if not isinstance(item["email"], str) or not item["email"].strip():
            raise ReaderError("contact_emails email must be a non-empty string.")
        for optional_key in ("name", "post"):
            optional_value = item[optional_key]
            if optional_value is not None and not isinstance(optional_value, str):
                raise ReaderError(f"contact_emails {optional_key} must be a string or null.")
