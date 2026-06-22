from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from neodym_lead_discovery.models import (
    ContactCandidate,
    CriterionEvaluation,
    EnrichedCompany,
    LeadCandidate,
    QualifiedLead,
    ScoreBreakdown,
    SourceEvidence,
)


def test_qualified_lead_serializes_required_output_fields():
    lead = QualifiedLead(
        company="ABC Logistics",
        website="https://abclogistics.example",
        industry="Logistics",
        contact=ContactCandidate(name=None, role="Head of Operations", email=None, source_url=None),
        fit_score=8.5,
        reason="Strong operations-heavy business with dispatch automation opportunity.",
        pain_point="Manual dispatch and customer communication workflows.",
        opportunity="AI dispatch assistant and support automation.",
        source_links=["https://abclogistics.example/about"],
        criterion_evaluations=[
            CriterionEvaluation(
                id="industry_relevance",
                status="strong",
                evidence="Company describes logistics operations.",
                reason="Logistics is a target vertical.",
                missing_items=[],
            )
        ],
        score_breakdown=ScoreBreakdown(
            raw_score_100=85.0,
            fit_score=8.5,
            criterion_points={"industry_relevance": 17.0},
        ),
        confidence="medium",
        evidence=["Company describes logistics operations."],
        limitations=[],
        generated_at=datetime(2026, 6, 22, tzinfo=UTC),
    )

    data = lead.model_dump(mode="json")

    for field in [
        "company",
        "website",
        "industry",
        "contact",
        "fit_score",
        "reason",
        "pain_point",
        "opportunity",
        "source_links",
    ]:
        assert field in data
    assert data["fit_score"] == 8.5
    assert data["contact"]["role"] == "Head of Operations"


def test_qualified_lead_rejects_score_outside_one_to_ten():
    with pytest.raises(ValidationError):
        QualifiedLead(
            company="Bad Score Inc",
            website=None,
            industry=None,
            contact=None,
            fit_score=10.5,
            reason="Invalid score.",
            pain_point="Unknown.",
            opportunity="Unknown.",
            source_links=["https://example.com"],
        )


def test_qualified_lead_requires_source_links():
    with pytest.raises(ValidationError):
        QualifiedLead(
            company="No Source Inc",
            website=None,
            industry=None,
            contact=None,
            fit_score=5.0,
            reason="Missing source links.",
            pain_point="Unknown.",
            opportunity="Unknown.",
            source_links=[],
        )


def test_lead_candidate_and_enriched_company_keep_source_evidence():
    evidence = SourceEvidence(
        url="https://example.com/about",
        label="about page",
        snippet="Example Co provides claims processing services.",
    )
    candidate = LeadCandidate(
        company_name="Example Co",
        website="https://example.com",
        industry="Insurance",
        location="Texas, USA",
        description="Claims processing firm",
        company_size="51-200",
        source_links=["https://example.com/about"],
        raw_sources=[evidence],
        discovery_source="apollo_export",
    )
    enriched = EnrichedCompany(
        candidate=candidate,
        website_title="Example Co",
        website_summary="Insurance claims processing services.",
        services_or_products=["Claims processing"],
        job_signals=["Hiring operations manager"],
        growth_signals=["Expanding team"],
        operational_complexity_signals=["Claims intake"],
        contact_candidates=[ContactCandidate(name="Jane Doe", role="CEO", email=None, source_url="https://example.com/team")],
        evidence=[evidence],
    )

    assert enriched.candidate.discovery_source == "apollo_export"
    assert enriched.evidence[0].snippet.startswith("Example Co")
