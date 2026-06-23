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
    "job_openings",
    "contact_emails",
]
ARRAY_STRING_KEYS = [
    "explicit_services_offered",
    "mentioned_software_or_tools",
    "manual_friction_clues",
    "key_executives",
    "job_openings",
]

DEFAULT_READER_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class ReaderError(RuntimeError):
    """Raised when the reader LLM cannot produce the strict fact schema."""


def build_reader_prompt(website_markdown: str) -> str:
    """Build the tiny Reader prompt for extracting a strict seven-key fact sheet."""
    schema = {
        "core_business_model": "string or null",
        "explicit_services_offered": ["array of strings, or null"],
        "mentioned_software_or_tools": ["array of strings, or null"],
        "manual_friction_clues": ["array of strings, or null"],
        "key_executives": ["array of strings, or null"],
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
        "manual_friction_clues, key_executives, and job_openings, return either an "
        "array of strings or null; never return a bare string. Do not write a summary. "
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
            "Reader response must contain exactly these keys: " + ", ".join(READER_SCHEMA_KEYS)
        )

    _normalize_reader_types(payload)
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


def _normalize_reader_types(payload: dict[str, Any]) -> None:
    """Tolerate common Gemini JSON drift without losing strict output shape."""
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

    _validate_contact_emails(payload["contact_emails"])


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
