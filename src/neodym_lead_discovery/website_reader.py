from __future__ import annotations

import json
import re
from typing import Any

import httpx

READER_SCHEMA_KEYS = [
    "core_business_model",
    "explicit_services_offered",
    "mentioned_software_or_tools",
    "manual_friction_clues",
    "key_executives",
]

DEFAULT_READER_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class ReaderError(RuntimeError):
    """Raised when the reader LLM cannot produce the strict fact schema."""


def build_reader_prompt(website_markdown: str) -> str:
    """Build the tiny Reader prompt for extracting a strict five-key fact sheet."""
    schema = {
        "core_business_model": None,
        "explicit_services_offered": None,
        "mentioned_software_or_tools": None,
        "manual_friction_clues": None,
        "key_executives": None,
    }
    return (
        "Scan this website text. Extract only the following 5 data points into this "
        "strict JSON schema. If a point is not explicitly mentioned, write null. "
        "Do not write a summary. Return only valid JSON with exactly these keys.\n\n"
        f"JSON schema:\n{json.dumps(schema, indent=2)}\n\n"
        "Website text:\n"
        f"{website_markdown}"
    )


def extract_reader_facts(
    website_markdown: str,
    api_key: str,
    model: str = DEFAULT_READER_MODEL,
) -> dict[str, Any]:
    """Use Gemini Flash as the cheap Reader to convert Markdown into a compact fact sheet."""
    prompt = build_reader_prompt(website_markdown)
    response_text = _call_gemini(prompt=prompt, api_key=api_key, model=model)
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
            "Reader response must contain exactly these keys: "
            + ", ".join(READER_SCHEMA_KEYS)
        )

    _validate_reader_types(payload)
    return {key: payload[key] for key in READER_SCHEMA_KEYS}


def _call_gemini(prompt: str, api_key: str, model: str) -> str:
    endpoint = GEMINI_ENDPOINT_TEMPLATE.format(model=model)
    response = httpx.post(
        endpoint,
        params={"key": api_key},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        },
        timeout=60,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ReaderError(f"Gemini Reader request failed: HTTP {response.status_code}") from exc

    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReaderError("Gemini Reader response did not contain text output.") from exc


def _strip_json_fences(response_text: str) -> str:
    stripped = response_text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _validate_reader_types(payload: dict[str, Any]) -> None:
    if payload["core_business_model"] is not None and not isinstance(
        payload["core_business_model"],
        str,
    ):
        raise ReaderError("core_business_model must be a string or null.")

    for key in READER_SCHEMA_KEYS[1:]:
        value = payload[key]
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ReaderError(f"{key} must be an array of strings or null.")
