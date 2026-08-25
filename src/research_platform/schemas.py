from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

import ulid
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .config import get_settings
from .temporal import infer_relative_date_range


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


class AuthorityLevel(StrEnum):
    ANY = "any"
    OFFICIAL = "official"
    PRIMARY = "primary"
    PEER_REVIEWED = "peer_reviewed"
    INDEPENDENT = "independent"


class FamilyTarget(BaseModel):
    minimum_sources: int = Field(1, ge=0, le=100)
    weight: float = Field(1.0, gt=0, le=10)


class AuthorityPolicy(BaseModel):
    minimum_authority: AuthorityLevel = AuthorityLevel.ANY
    strict_for_major_claims: bool = False
    discovery_sources_may_be_non_authoritative: bool = True


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
    minimum_sentinel_recall: float = Field(1.0, ge=0, le=1)
    minimum_estimated_completeness: float = Field(0.75, ge=0, le=1)
    maximum_reserve_false_negative_rate: float = Field(0.10, ge=0, le=1)
    maximum_citation_frontier_novelty: float = Field(0.05, ge=0, le=1)


class ResearchBudget(BaseModel):
    max_rounds: int = Field(4, ge=1, le=12)
    max_sources: int | None = Field(None, ge=1)
    # Deliberately without a default: how long a run may collect is the caller's decision,
    # and a silent 45 minutes was a decision nobody saw being made.
    max_wall_minutes: int = Field(ge=1, le=1440)
    results_per_connector: int = Field(20, ge=1, le=100)
    acquisition_concurrency: int = Field(
        default_factory=lambda: get_settings().acquisition_concurrency,
        ge=1,
        le=16,
    )
    exhaustive_until_budget: bool = True


class HitlConfig(BaseModel):
    """User checkpoints for a single research run.

    `plan_review` defaults on: a run should not start searching before somebody has seen
    what it is about to do. A caller that automates end to end can still send false, and
    the pipeline records that choice as a `plan_skipped` event.
    """

    planning_questions: bool = False
    plan_review: bool = True
    source_review: bool = False
    outline_review: bool = False


class ParserSelection(BaseModel):
    """
    Optional parser overrides for a run.

    The registry picks deterministically from content signals by default, because
    content_hash is derived from parsed text and drives source-version dedup and MinIO
    snapshot keys. An override is a deliberate, recorded decision rather than a per-run
    guess: the chosen parser is written into source_versions.provenance.
    """

    # document type -> parser id, e.g. {"pdf": "pdf_layout"}
    overrides: dict[str, str] = Field(default_factory=dict)


class ConnectorSelection(BaseModel):
    profile: Literal["core", "all", "custom"] = "core"
    included_families: list[SourceFamily] = Field(default_factory=lambda: CORE_FAMILIES.copy())
    excluded_connectors: list[str] = Field(default_factory=list)
    included_connectors: list[str] = Field(default_factory=list)
    required_connectors: list[str] = Field(default_factory=list)
    trusted_domains: list[str] = Field(default_factory=list)
    zotero_collections: list[str] = Field(default_factory=list)
    zotero_tags: list[str] = Field(default_factory=list)
    citation_depth: int = Field(
        default_factory=lambda: get_settings().frontier_max_depth,
        ge=0,
        le=5,
    )

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
    # Set by the protocol validator when wording such as "last 3 months" produced the
    # window above. Recorded rather than recomputed: the inference is time-dependent, so
    # asking again later gives different bounds and cannot prove what happened here.
    dates_inferred: bool = False
    # Set when the user answered the scoping question about dates. Without it, choosing
    # "no date limit" clears the window and the validator immediately infers it back from
    # the same wording -- the answer would be undone by the next revalidation.
    dates_chosen: bool = False


class SentinelSource(BaseModel):
    """A known relevant source used to measure whether discovery misses obvious evidence."""

    title: str = Field(min_length=3, max_length=1000)
    url: str | None = None
    persistent_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    required: bool = True


ACADEMIC_PUBLICATION_SIGNALS = {
    "academic",
    "article",
    "clinical",
    "doi",
    "journal",
    "literature",
    "paper",
    "papers",
    "preprint",
    "published",
    "publication",
    "radiomics",
    "research",
    "study",
    "studies",
    "trial",
    "arxiv",
    "makale",
    "yayın",
    "yayin",
    "çalışma",
    "calisma",
}


def is_academic_publication_query(question: str) -> bool:
    normalized = question.lower()
    hits = sum(
        bool(re.search(rf"(?<!\w){re.escape(signal)}(?!\w)", normalized))
        for signal in ACADEMIC_PUBLICATION_SIGNALS
    )
    return hits >= 2


class ResearchProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=300)
    # A short snake_case handle for the topic, filled in at VALIDATE_PROTOCOL. Chat clients
    # print it where a ULID would otherwise say nothing about which run is meant. Display
    # only: two runs on one topic share a label, so it never replaces the id.
    label: str | None = Field(None, max_length=64)
    primary_question: str = Field(min_length=5, max_length=5000)
    research_mode: Literal["literature_scan", "focused_answer"] = "literature_scan"
    sub_questions: list[str] = Field(default_factory=list, max_length=30)
    # Research runs in English: the pipeline translates primary_question and sub_questions
    # in place at VALIDATE_PROTOCOL and keeps what the user typed in these three fields.
    # Recorded rather than recomputed, for the same reason as scope.dates_inferred.
    original_question: str | None = None
    original_sub_questions: list[str] = Field(default_factory=list, max_length=30)
    original_language: str = ""
    # What the user asked to be talked to in, when they were asked outright. Kept apart
    # from original_language: that one records which language the question was written in
    # and feeds question_for_report(), while this is a preference and outranks it.
    interaction_language: Literal["tr", "en"] | None = None
    scope: ResearchScope = Field(default_factory=ResearchScope)
    languages: list[str] = Field(default_factory=lambda: ["tr", "en"], min_length=1)
    # Only the two languages the synthesis guard can actually verify: _language_matches()
    # in report_synthesis.py checks Turkish output and passes everything else through, so a
    # third value would promise a language nothing enforces.
    report_language: Literal["tr", "en"] = "tr"
    connectors: ConnectorSelection = Field(default_factory=ConnectorSelection)
    parsers: ParserSelection = Field(default_factory=ParserSelection)
    evidence_policy: EvidencePolicy = Field(default_factory=EvidencePolicy)
    authority_policy: AuthorityPolicy = Field(default_factory=AuthorityPolicy)
    family_targets: dict[SourceFamily, FamilyTarget] = Field(default_factory=dict)
    sentinel_sources: list[SentinelSource] = Field(default_factory=list, max_length=50)
    stopping_criteria: StoppingCriteria = Field(default_factory=StoppingCriteria)
    # No default: a protocol without a stated collection budget cannot be built at all,
    # so no surface can start a run whose duration nobody chose.
    budget: ResearchBudget
    output_mode: Literal["raw", "result", "both"] = "both"
    hitl: HitlConfig = Field(default_factory=HitlConfig)

    @model_validator(mode="after")
    def normalize_targets_and_validate_budget(self) -> "ResearchProtocol":
        if (
            not self.scope.dates_chosen
            and self.scope.start_date is None
            and self.scope.end_date is None
        ):
            inferred = infer_relative_date_range(self.primary_question)
            if inferred:
                self.scope.start_date, self.scope.end_date = inferred
                self.scope.dates_inferred = True
        if (
            self.scope.start_date is not None
            and self.scope.end_date is not None
            and self.scope.start_date > self.scope.end_date
        ):
            raise ValueError("scope.start_date must not be after scope.end_date")
        if not self.family_targets:
            if (
                SourceFamily.ACADEMIC in self.connectors.included_families
                and is_academic_publication_query(self.primary_question)
            ):
                self.family_targets = {
                    SourceFamily.ACADEMIC: FamilyTarget(
                        minimum_sources=(
                            min(2, self.budget.max_sources)
                            if self.budget.max_sources is not None
                            else 2
                        ),
                    ),
                }
            else:
                self.family_targets = {
                    family: FamilyTarget() for family in self.connectors.included_families
                }
        else:
            self.family_targets = {
                family: target
                for family, target in self.family_targets.items()
                if family in self.connectors.included_families
            }
        required = sum(target.minimum_sources for target in self.family_targets.values())
        if self.budget.max_sources is not None and required > self.budget.max_sources:
            raise ValueError(
                f"family_targets require at least {required} sources but max_sources is "
                f"{self.budget.max_sources}"
            )
        normalized_question = self.primary_question.lower()
        if self.authority_policy.minimum_authority == AuthorityLevel.ANY and any(
            term in normalized_question for term in ("resmî", "resmi", "official documentation")
        ):
            self.authority_policy.minimum_authority = AuthorityLevel.OFFICIAL
            self.authority_policy.strict_for_major_claims = True
        return self

    def display_language(self) -> str:
        """The language to talk to this run's owner in.

        An outright choice wins; otherwise the language the request was written in. Not
        report_language, which is a decision about the deliverable rather than about the
        conversation. Runs recorded before either field existed keep the panel's Turkish.
        """
        if self.interaction_language:
            return self.interaction_language
        return self.original_language if self.original_language in {"tr", "en"} else "tr"

    def question_for_report(self) -> str:
        """The question as the report should print it.

        The report is written in report_language, so it shows what the user typed only when
        that is the same language. There is no back-translation: a Turkish report for an
        English question prints the English question rather than inventing a translation.
        """
        if self.original_question and self.original_language == self.report_language:
            return self.original_question
        return self.primary_question

    def sub_questions_for_report(self) -> list[str]:
        if self.original_sub_questions and self.original_language == self.report_language:
            return list(self.original_sub_questions)
        return list(self.sub_questions)

    def primary_questions(self) -> list[str]:
        """The main question alone, in every language the run holds it in.

        Kept separate from research_questions(): the subject and heading gates weigh the
        main question only, and letting short sub-questions in would loosen them for
        reasons that have nothing to do with language.
        """
        items = [self.primary_question]
        if self.original_question:
            items.append(self.original_question)
        return list(dict.fromkeys(item for item in items if item))

    def research_questions(self) -> list[str]:
        """Every phrasing of the question the lexical relevance gates may match against.

        Those gates compare question terms with document text, so an English-only list
        would score a Turkish official document at zero on a Turkish topic -- the mirror
        image of the problem translation solves.
        """
        phrasings = [self.primary_question, *self.sub_questions]
        if self.original_question:
            phrasings.append(self.original_question)
        phrasings.extend(self.original_sub_questions)
        return list(dict.fromkeys(item for item in phrasings if item))


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    PAUSED = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_INCOMPLETE = "completed_incomplete"
    FAILED = "failed"


class DeliveryMode(StrEnum):
    RAW = "raw"
    RESULT = "result"
    BOTH = "both"


class ResearchRunCreate(BaseModel):
    protocol: ResearchProtocol
    # Scheduling, kept beside the protocol rather than inside it: the protocol is the
    # document approved at the plan gate and describes what to research, not when.
    priority: Literal["normal", "urgent"] = "normal"


class RunPriorityRequest(BaseModel):
    priority: Literal["normal", "urgent"]


class HitlRespondRequest(BaseModel):
    interaction_id: str = Field(min_length=3, max_length=100)
    response: dict[str, Any]


class CoverageMetrics(BaseModel):
    source_family_coverage: float = 0.0
    query_branch_coverage: float = 0.0
    claim_audit_coverage: float = 0.0
    new_source_rate: float = 1.0
    unresolved_major_claims: int = 0
    authority_coverage: float = 1.0
    saturated_rounds: int = 0
    sentinel_recall: float = 1.0
    estimated_completeness: float | None = None
    relative_recall: float = 1.0
    citation_frontier_novelty: float = 0.0
    reserve_false_negative_rate: float = 0.0
    critical_connector_coverage: float = 1.0
    discovery_observations: int = 0
    sufficient: bool = False
    reasons: list[str] = Field(default_factory=list)


class RunView(BaseModel):
    id: str
    status: RunStatus
    current_stage: str
    priority: Literal["normal", "urgent"] = "normal"
    # Filled in while the scheduler is holding this run back for an urgent one, so a
    # client can say why a run stopped on its own rather than showing a bare "paused".
    preempted_at: datetime | None = None
    protocol: ResearchProtocol
    round_number: int = 0
    sources_count: int = 0
    claims_count: int = 0
    coverage: CoverageMetrics = Field(default_factory=CoverageMetrics)
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    hitl_config: HitlConfig = Field(default_factory=HitlConfig)
    interaction: dict[str, Any] | None = None
    hitl_history: list[dict[str, Any]] = Field(default_factory=list)


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


class ScholarlyIdentity(BaseModel):
    doi: str | None = None
    openalex_id: str | None = None
    semantic_scholar_id: str | None = None
    corpus_id: str | None = None
    arxiv_id: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    isbn: str | None = None
    zotero_item_key: str | None = None


class ZoteroSyncRequest(BaseModel):
    mode: Literal["local", "web"] = "local"
    query: str = ""
    collections: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(100, ge=1, le=500)


class ZoteroSyncResult(BaseModel):
    run_id: str
    connector_id: str
    discovered: int
    imported: int
    skipped: int
    library_version: int | None = None


class CitationGraphEdge(BaseModel):
    source_id: str
    target_source_id: str | None = None
    target_persistent_id: str | None = None
    relation_type: Literal[
        "cites",
        "cited_by",
        "is_version_of",
        "is_preprint_of",
        "has_attachment",
        "supplements",
        "related_zotero_item",
    ]
    provider: str
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
    parser_id: str = ""
    # Set by parsers that route work between engines: parse profile, per-page
    # engine, and whether anything degraded. Empty for single-extractor parsers.
    parse_provenance: dict[str, Any] = Field(default_factory=dict)
    # Structure the parser recovered separately from the prose. The same content is also
    # rendered inline in `content`, so passages stay self-contained; these give consumers
    # that need the grid rather than the markdown a direct handle.
    tables: list[dict[str, Any]] = Field(default_factory=list)
    code_blocks: list[str] = Field(default_factory=list)
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


class CoverageGap(BaseModel):
    id: str = Field(default_factory=new_id)
    dimension: Literal[
        "source_family",
        "authority",
        "query_branch",
        "claim_support",
        "counterevidence",
        "version",
        "sentinel",
    ]
    topic: str
    branch_id: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    missing_family: SourceFamily | None = None
    required_authority: AuthorityLevel = AuthorityLevel.ANY
    evidence_direction: Literal["supports", "contradicts", "either"] = "either"
    target_entities: list[str] = Field(default_factory=list)
    target_domains: list[str] = Field(default_factory=list)
    preferred_connectors: list[str] = Field(default_factory=list)
    minimum_novel_sources: int = Field(1, ge=1, le=20)
    priority: float = Field(0.5, ge=0, le=1)
    attempts: int = Field(0, ge=0)
    status: Literal["open", "satisfied", "exhausted", "blocked"] = "open"
    failure_reasons: list[str] = Field(default_factory=list)


class SearchMission(BaseModel):
    id: str = Field(default_factory=new_id)
    gap_id: str | None = None
    branch_id: str
    query: str
    connector_ids: list[str] = Field(default_factory=list)
    seed_urls: list[HttpUrl] = Field(default_factory=list)
    target_entities: list[str] = Field(default_factory=list)
    domain_allowlist: list[str] = Field(default_factory=list)
    domain_denylist: list[str] = Field(default_factory=list)
    required_family: SourceFamily | None = None
    required_authority: AuthorityLevel = AuthorityLevel.ANY
    result_limit: int = Field(10, ge=1, le=100)
    acquisition_slots: int = Field(1, ge=1, le=20)
    novelty_required: bool = True
