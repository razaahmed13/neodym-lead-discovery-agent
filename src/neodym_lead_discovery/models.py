from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CriterionStatus = Literal[
    "missing",
    "very_weak",
    "weak",
    "partial",
    "good",
    "strong",
    "excellent",
]
Confidence = Literal["low", "medium", "high"]


class SourceEvidence(BaseModel):
    """A source-grounded snippet used to justify enrichment or scoring."""

    model_config = ConfigDict(extra="forbid")

    url: str
    label: str | None = None
    snippet: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ContactCandidate(BaseModel):
    """A public contact candidate or suggested decision-maker role."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    role: str
    email: str | None = None
    source_url: str | None = None


class LeadCandidate(BaseModel):
    """Raw lead candidate imported from Apollo CSV, manual CSV, or public discovery."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    website: str | None = None
    industry: str | None = None
    location: str | None = None
    description: str | None = None
    company_size: str | None = None
    source_links: list[str] = Field(default_factory=list)
    raw_sources: list[SourceEvidence] = Field(default_factory=list)
    discovery_source: str = "manual"

    @field_validator("company_name")
    @classmethod
    def company_name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("company_name cannot be blank")
        return value


class EnrichedCompany(BaseModel):
    """Lead candidate plus public website/careers/contact enrichment."""

    model_config = ConfigDict(extra="forbid")

    candidate: LeadCandidate
    website_title: str | None = None
    website_summary: str | None = None
    services_or_products: list[str] = Field(default_factory=list)
    job_signals: list[str] = Field(default_factory=list)
    growth_signals: list[str] = Field(default_factory=list)
    operational_complexity_signals: list[str] = Field(default_factory=list)
    contact_candidates: list[ContactCandidate] = Field(default_factory=list)
    evidence: list[SourceEvidence] = Field(default_factory=list)


class CriterionEvaluation(BaseModel):
    """Codex-returned status and evidence for one scoring criterion."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: CriterionStatus
    evidence: str
    reason: str
    missing_items: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    """Deterministic score details computed from criterion statuses."""

    model_config = ConfigDict(extra="forbid")

    raw_score_100: float = Field(ge=0, le=100)
    fit_score: float = Field(ge=1, le=10)
    criterion_points: dict[str, float] = Field(default_factory=dict)


class QualifiedLead(BaseModel):
    """Final lead output written to lead_list.json and lead_report.md."""

    model_config = ConfigDict(extra="forbid")

    company: str
    website: str | None = None
    industry: str | None = None
    contact: ContactCandidate | None = None
    fit_score: float = Field(ge=1, le=10)
    reason: str
    pain_point: str
    opportunity: str
    source_links: list[str]
    criterion_evaluations: list[CriterionEvaluation] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown | None = None
    confidence: Confidence = "medium"
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("company", "reason", "pain_point", "opportunity")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text fields cannot be blank")
        return value

    @field_validator("source_links")
    @classmethod
    def final_leads_require_source_links(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("qualified leads require at least one source link")
        return value
