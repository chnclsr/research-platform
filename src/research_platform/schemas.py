from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

import ulid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def new_id() -> str:
    return str(ulid.new())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceFamily(StrEnum):
    WEB = "web"
    ACADEMIC = "academic"
    BOOKS_THESES = "books_theses"
    PATENTS_STANDARDS = "patents_standards"
    OFFICIAL_LEGAL = "official_legal"
    NEWS_ARCHIVES = "news_archives"
    CODE_DATA = "code_data"
    COMPANY = "company"
    GREY_LITERATURE = "grey_literature"


CORE_FAMILIES = [
    SourceFamily.WEB,
    SourceFamily.ACADEMIC,
    SourceFamily.OFFICIAL_LEGAL,
    SourceFamily.CODE_DATA,
]


class EvidencePolicy(BaseModel):
    minimum_independent_sources: int = Field(2, ge=1, le=10)
    primary_source_preference: bool = True
    counterevidence_required: bool = True


class StoppingCriteria(BaseModel):
    minimum_source_coverage: float = Field(0.80, ge=0, le=1)
    minimum_query_branch_coverage: float = Field(0.90, ge=0, le=1)
    minimum_claim_audit_coverage: float = Field(0.95, ge=0, le=1)
    maximum_new_source_rate: float = Field(0.05, ge=0, le=1)
    unresolved_major_claim_limit: int = Field(5, ge=0)
    saturation_rounds: int = Field(2, ge=1, le=5)


class ResearchBudget(BaseModel):
    max_rounds: int = Field(4, ge=1, le=12)
    max_sources: int = Field(150, ge=1, le=2000)
    max_wall_minutes: int = Field(45, ge=1, le=1440)
    results_per_connector: int = Field(20, ge=1, le=100)
    acquisition_concurrency: int = Field(4, ge=1, le=16)


class ConnectorSelection(BaseModel):
    profile: Literal["core", "all", "custom"] = "core"
    included_families: list[SourceFamily] = Field(default_factory=lambda: CORE_FAMILIES.copy())
    excluded_connectors: list[str] = Field(default_factory=list)
    included_connectors: list[str] = Field(default_factory=list)
    trusted_domains: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def apply_profile(self) -> "ConnectorSelection":
        if self.profile == "all" and self.included_families == CORE_FAMILIES:
            self.included_families = list(SourceFamily)
        return self


class ResearchScope(BaseModel):
    start_date: datetime | None = None
    end_date: datetime | None = None
    geography: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class ResearchProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=300)
    primary_question: str = Field(min_length=5, max_length=5000)
    sub_questions: list[str] = Field(default_factory=list, max_length=30)
    scope: ResearchScope = Field(default_factory=ResearchScope)
    languages: list[str] = Field(default_factory=lambda: ["tr", "en"], min_length=1)
    report_language: str = "tr"
    connectors: ConnectorSelection = Field(default_factory=ConnectorSelection)
    evidence_policy: EvidencePolicy = Field(default_factory=EvidencePolicy)
    stopping_criteria: StoppingCriteria = Field(default_factory=StoppingCriteria)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_INCOMPLETE = "completed_incomplete"
    FAILED = "failed"


class ResearchRunCreate(BaseModel):
    protocol: ResearchProtocol


class CoverageMetrics(BaseModel):
    source_family_coverage: float = 0.0
    query_branch_coverage: float = 0.0
    claim_audit_coverage: float = 0.0
    new_source_rate: float = 1.0
    unresolved_major_claims: int = 0
    saturated_rounds: int = 0
    sufficient: bool = False
    reasons: list[str] = Field(default_factory=list)


class RunView(BaseModel):
    id: str
    status: RunStatus
    current_stage: str
    protocol: ResearchProtocol
    round_number: int = 0
    sources_count: int = 0
    claims_count: int = 0
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class ConnectorCandidate(BaseModel):
    id: str = Field(default_factory=new_id)
    connector_id: str
    family: SourceFamily
    title: str
    url: HttpUrl
    snippet: str = ""
    persistent_id: str | None = None
    published_at: datetime | None = None
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealth(BaseModel):
    id: str
    family: SourceFamily
    enabled: bool
    healthy: bool
    requires_credentials: bool = False
    missing_credentials: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    detail: str = ""


class AcquiredDocument(BaseModel):
    candidate: ConnectorCandidate
    success: bool
    access_status: Literal["open", "restricted", "unavailable"] = "unavailable"
    content: str = ""
    raw_content: str = ""
    content_type: str = "text/plain"
    document_type: Literal["html", "pdf", "json", "xml", "text"] = "text"
    language: str = "und"
    canonical_url: str | None = None
    final_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    acquisition_method: str = "none"
    content_hash: str | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    strategies_tried: list[str] = Field(default_factory=list)
    error: str | None = None


class ExtractedClaim(BaseModel):
    id: str = Field(default_factory=new_id)
    text: str
    importance: Literal["major", "minor"] = "major"
    source_candidate_id: str
    quote: str
    start_char: int = 0
    end_char: int = 0
    direction: Literal["supports", "contradicts", "qualifies"] = "supports"
    confidence: float = Field(0.5, ge=0, le=1)
    passage_id: str | None = None
    section_path: str | None = None
    page_number: int | None = None
    original_start_char: int | None = None
    original_end_char: int | None = None
    retrieval_score: float | None = None


class Passage(BaseModel):
    id: str = Field(default_factory=new_id)
    source_version_id: str
    chunk_index: int
    section_path: str = "Document"
    page_number: int | None = None
    start_char: int
    end_char: int
    text: str
    token_count: int
    content_hash: str
    language: str = "und"
    document_type: str = "text"
    embedding: list[float] = Field(default_factory=list)
    retrieval_score: float = 0.0
    matched_questions: list[str] = Field(default_factory=list)


class ArtifactView(BaseModel):
    name: str
    media_type: str
    size_bytes: int
    download_url: str


class CorpusSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=5000)
    top_k: int = Field(10, ge=1, le=50)
