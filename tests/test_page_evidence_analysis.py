from __future__ import annotations

import subprocess
from pathlib import Path

from neodym_lead_discovery.enrichment.website import (
    analyze_page_with_codex,
    enrich_public_website,
)
from neodym_lead_discovery.models import LeadCandidate, WebsitePageProfile

HTML = """
<html><head><title>ABC Dispatch</title></head><body>
  <h1>Dispatch services</h1>
  <p>Our operations team coordinates inbound requests, schedules drivers, and handles
  customer updates.</p>
</body></html>
"""


def test_page_evidence_uses_llm_analysis_fields_instead_of_raw_text_excerpt():
    candidate = LeadCandidate(company_name="ABC Dispatch", website="https://abc.example")

    def fetcher(url: str) -> str:
        assert url == "https://abc.example"
        return HTML

    def analyzer(candidate: LeadCandidate, profile: WebsitePageProfile) -> dict[str, object]:
        assert candidate.company_name == "ABC Dispatch"
        assert profile.url == "https://abc.example"
        return {
            "page_summary": (
                "The page describes dispatch services and customer update coordination."
            ),
            "manual_process_signals": [
                "Operations team coordinates inbound requests and schedules drivers."
            ],
            "automation_opportunities": ["Automate inbound request triage and driver scheduling."],
            "supporting_excerpt": "coordinates inbound requests, schedules drivers",
            "limitations": ["The page does not explicitly say the workflow is manual."],
        }

    enriched = enrich_public_website(
        candidate,
        fetcher=fetcher,
        page_evidence_analyzer=analyzer,
        max_pages=1,
    )

    page_evidence = enriched.structured_profile.llm_context["page_evidence"]
    assert isinstance(page_evidence, list)
    first_page = page_evidence[0]
    assert first_page["page_summary"] == (
        "The page describes dispatch services and customer update coordination."
    )
    assert first_page["manual_process_signals"] == [
        "Operations team coordinates inbound requests and schedules drivers."
    ]
    assert first_page["automation_opportunities"] == [
        "Automate inbound request triage and driver scheduling."
    ]
    assert first_page["supporting_excerpt"] == "coordinates inbound requests, schedules drivers"
    assert first_page["limitations"] == ["The page does not explicitly say the workflow is manual."]
    assert "text_excerpt" not in first_page


def test_analyze_page_with_codex_builds_critical_json_prompt_and_parses_response(
    tmp_path: Path, monkeypatch
):
    output_file_seen: list[Path] = []
    prompt_seen: list[str] = []

    def fake_run(command, *, input, text, capture_output, timeout, check):
        assert command[:2] == ["codex", "exec"]
        assert "--output-last-message" in command
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_file_seen.append(output_path)
        prompt_seen.append(input)
        output_path.write_text(
            '{"page_summary":"Dispatch page summary",'
            '"manual_process_signals":["Driver scheduling appears operational."],'
            '"automation_opportunities":["Scheduling intake automation"],'
            '"supporting_excerpt":"schedules drivers",'
            '"limitations":["No explicit manual tool evidence"]}',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    result = analyze_page_with_codex(
        LeadCandidate(company_name="ABC Dispatch", website="https://abc.example"),
        WebsitePageProfile(
            url="https://abc.example/services",
            page_type="services",
            title="Dispatch Services",
            headings=["Dispatch services"],
            text="Our team coordinates inbound requests and schedules drivers for customers.",
            operational_signals=["dispatch", "scheduling"],
        ),
    )

    assert result["page_summary"] == "Dispatch page summary"
    assert result["manual_process_signals"] == ["Driver scheduling appears operational."]
    assert result["automation_opportunities"] == ["Scheduling intake automation"]
    assert result["supporting_excerpt"] == "schedules drivers"
    assert result["limitations"] == ["No explicit manual tool evidence"]
    assert "Return only one valid JSON object" in prompt_seen[0]
    assert "processes that appear manual, repetitive, or coordination-heavy" in prompt_seen[0]
    assert "Do not invent manual processes" in prompt_seen[0]
    assert not output_file_seen[0].exists()
