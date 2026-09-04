from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from .llm import LLMProvider
from .schemas import ResearchProtocol, SourceFamily, is_academic_publication_query

Tier = Literal["universal", "clinical"]
Grade = Literal["strong", "moderate", "limited", "insufficient"]

# Best first. Explicit rather than implicit: "one well-powered trial outranks three small
# series" is only expressible if the order is written down somewhere a test can read.
DESIGN_RANK: tuple[str, ...] = (
    "Sistematik sentez",
    "Kontrollü çalışma",
    "Çok merkezli",
    "Dış doğrulama",
    "Prospektif",
    "Retrospektif",
    "Gözlemsel",
    "Benchmark / veri seti",
    "Anlatısal derleme",
    "Tasarım belirtilmemiş",
)
CLINICAL_DESIGNS = frozenset({
    "Kontrollü çalışma", "Prospektif", "Retrospektif", "Gözlemsel",
    "Çok merkezli", "Dış doğrulama", "Sistematik sentez",
})
_WEAK_DESIGNS = frozenset({"Gözlemsel", "Retrospektif", "Tasarım belirtilmemiş"})
_GRADES: tuple[Grade, ...] = ("strong", "moderate", "limited", "insufficient")

FALLACIES = (
    "hasty_generalisation", "post_hoc", "cherry_picking",
    "appeal_to_authority", "false_dichotomy", "correlation_as_causation",
)

_SYSTEM_UNIVERSAL = (
    "You review how well a set of research claims is evidenced. "
    "Answer with JSON only: {\"signals\": [{\"claim_id\": \"...\", "
    "\"single_source_dependence\": true|false, \"contradicted\": true|false, "
    "\"replicated\": true|false, \"fallacies\": [\"...\"], \"note\": \"...\"}]}. "
    f"Use only these fallacy names: {', '.join(FALLACIES)}. "
    "Report only what the evidence summary you are given actually shows. "
    "Do not assign a grade, a score or a ranking -- those are not yours to set."
)
_SYSTEM_CLINICAL = _SYSTEM_UNIVERSAL + (
    " Each signal may also carry \"design_ceiling\": the strongest study design "
    "supporting the claim, \"underpowered\": true when the samples are too small to "
    "support the claim, and \"multiplicity_risk\": true when many comparisons were made "
    "without correction."
)


class AppraisalSignal(BaseModel):
    claim_id: str
    single_source_dependence: bool = False
    contradicted: bool = False
    replicated: bool = False
    fallacies: list[str] = Field(default_factory=list, max_length=3)
    design_ceiling: str | None = None
    underpowered: bool = False
    multiplicity_risk: bool = False
    note: str = Field("", max_length=240)


class AppraisalBundle(BaseModel):
    signals: list[AppraisalSignal] = Field(default_factory=list, max_length=60)


@dataclass(frozen=True)
class ClaimAppraisal:
    claim_id: str
    tier: Tier
    grade: Grade
    reasons: tuple[str, ...]
    generated_by: Literal["model", "deterministic"]

    def as_audit_entry(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "grade": self.grade,
            "reasons": list(self.reasons),
            "generated_by": self.generated_by,
        }


def select_appraisal_tier(
    protocol: ResearchProtocol,
    sources: list[Any],
    design_by_source: dict[str, str],
) -> tuple[Tier, dict[str, Any]]:
    """Which appraisal tier this run gets, and why.

    A score, not a single trigger. `europe_pmc implies clinical` would tell a
    semiconductor-supply-chain run that happened to touch one biomedical record that its
    evidence is underpowered; `academic family implies clinical` would do the same to every
    arXiv machine-learning run. What separates a genuinely clinical corpus from a merely
    academic one is that its SOURCES carry clinical study designs -- which the report
    already classifies, so the labels are read rather than rebuilt.

    The evidence is returned alongside the decision so a misfire is diagnosable rather
    than mysterious.
    """
    connectors = {str(getattr(source, "connector_id", "")) for source in sources}
    clinical_designs = sum(
        1 for label in design_by_source.values() if label in CLINICAL_DESIGNS
    )
    biomedical_connector = "europe_pmc" in connectors
    non_biomedical = bool(connectors & {"epo_ops", "sec_edgar"})
    academic_family = SourceFamily.ACADEMIC in protocol.connectors.included_families
    academic_question = is_academic_publication_query(protocol.primary_question)

    score = 0
    if biomedical_connector:
        score += 2
    if academic_family:
        score += 1
    if academic_question:
        score += 1
    if clinical_designs >= 3:
        score += 2
    if non_biomedical and not biomedical_connector:
        score -= 2

    tier: Tier = "clinical" if score >= 3 else "universal"
    return tier, {
        "score": score,
        "threshold": 3,
        "biomedical_connector": biomedical_connector,
        "non_biomedical_connector": non_biomedical,
        "academic_family": academic_family,
        "academic_question": academic_question,
        "clinical_design_sources": clinical_designs,
    }


def _user_prompt(
    tier: Tier, protocol: ResearchProtocol, summaries: list[dict[str, Any]]
) -> str:
    """A summary per claim -- id, text, counts, designs -- never the corpus itself."""
    payload = json.dumps({"claims": summaries[:60]}, ensure_ascii=False)
    return (
        f"Research question:\n{protocol.primary_question}\n\n"
        f"Appraisal tier: {tier}\n\n"
        f"Claims and what supports them:\n{payload}"
    )


async def propose_appraisal(
    llm: LLMProvider,
    tier: Tier,
    protocol: ResearchProtocol,
    summaries: list[dict[str, Any]],
) -> AppraisalBundle | None:
    """A thin proposal, or None so the caller falls back to the deterministic grade.

    `llm` is the run's own provider, never the preparation chain: the prompt carries claim
    text drawn from the corpus and must stay inside the deployment's data boundary -- the
    same rationale as probe_factory.generate_probe_bundle.
    """
    if not summaries:
        return None
    system = _SYSTEM_CLINICAL if tier == "clinical" else _SYSTEM_UNIVERSAL
    try:
        answer = await llm.complete_json(system, _user_prompt(tier, protocol, summaries))
    except Exception:  # noqa: BLE001 - a model outage falls back, it does not fail the run
        return None
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except (TypeError, ValueError):
            return None
    if not isinstance(answer, dict):
        return None
    try:
        return AppraisalBundle.model_validate({"signals": answer.get("signals") or []})
    except ValueError:
        return None


def _design_rank(label: str) -> int:
    """Lower is stronger. An unknown label sorts last rather than raising."""
    try:
        return DESIGN_RANK.index(label)
    except ValueError:
        return len(DESIGN_RANK)


def _lower(grade: Grade, steps: int = 1) -> Grade:
    return _GRADES[min(_GRADES.index(grade) + steps, len(_GRADES) - 1)]


def _cap(grade: Grade, ceiling: Grade) -> Grade:
    return grade if _GRADES.index(grade) >= _GRADES.index(ceiling) else ceiling


def _deterministic_grade(audit: dict[str, Any], status: str, minimum: int) -> tuple[Grade, list[str]]:
    supporting = int(audit.get("supporting_evidence", 0) or 0)
    counter = int(audit.get("counter_evidence", 0) or 0)
    domains = int(audit.get("independent_domains", 0) or 0)
    reasons: list[str] = []
    if supporting <= 0:
        return "insufficient", ["no_valid_supporting_evidence"]
    if supporting >= minimum and domains >= minimum and counter == 0:
        return "strong", reasons
    if status == "supported":
        if counter:
            reasons.append("counter_evidence_present")
        if domains < minimum:
            reasons.append("few_independent_domains")
        return "moderate", reasons
    if domains <= 1:
        reasons.append("single_independent_domain")
    return "limited", reasons


def appraise_claims(
    claims: list[Any],
    evidence_by_claim: dict[str, list[tuple[Any, Any]]],
    design_by_source: dict[str, str],
    *,
    tier: Tier,
    minimum_independent_sources: int,
    proposal: AppraisalBundle | None,
) -> tuple[list[ClaimAppraisal], list[dict[str, str]]]:
    """Every operational value is decided here; the model only proposes.

    Two rules make the proposal safe. A model signal may only LOWER a grade, never raise
    one -- so a confident model cannot talk a thin claim up. And each signal has to be
    corroborated by a fact already in `claim.audit` or the evidence rows: `contradicted`
    needs counter_evidence above zero, `single_source_dependence` needs at most one
    independent domain. Uncorroborated signals are dropped and returned in the second
    element so the run event can record what the model said and why it was refused.
    """
    signals = {s.claim_id: s for s in (proposal.signals if proposal else [])}
    appraisals: list[ClaimAppraisal] = []
    rejected: list[dict[str, str]] = []

    for claim in claims:
        claim_id = str(claim.id)
        audit = dict(getattr(claim, "audit", None) or {})
        status = str(getattr(claim, "status", "unresolved"))
        grade, reasons = _deterministic_grade(audit, status, minimum_independent_sources)

        links = evidence_by_claim.get(claim_id, [])
        supporting_designs = [
            design_by_source.get(str(source.id), "Tasarım belirtilmemiş")
            for link, source in links
            if getattr(link, "direction", "") == "supports"
        ]
        contradicting_designs = [
            design_by_source.get(str(source.id), "Tasarım belirtilmemiş")
            for link, source in links
            if getattr(link, "direction", "") == "contradicts"
        ]

        if tier == "clinical" and supporting_designs:
            best = min(supporting_designs, key=_design_rank)
            if best == "Anlatısal derleme":
                grade = _cap(grade, "limited")
                reasons.append("narrative_review_only")
            elif best in _WEAK_DESIGNS:
                grade = _cap(grade, "moderate")
                reasons.append("weak_supporting_design")
            if contradicting_designs:
                strongest_counter = min(contradicting_designs, key=_design_rank)
                if _design_rank(strongest_counter) < _design_rank(best):
                    grade = _lower(grade)
                    reasons.append("contradicted_by_stronger_design")

        # Per claim, not per run. A run-level "model" would label a claim the model never
        # mentioned -- or one whose every signal was refused -- as model-derived, which is
        # the kind of provenance that overclaims by exactly one step.
        generated_by: Literal["model", "deterministic"] = "deterministic"
        signal = signals.get(claim_id)
        if signal is not None:
            corroborated, refused = _apply_signal(signal, audit)
            for reason in refused:
                rejected.append({"claim_id": claim_id, "signal": reason})
            if corroborated:
                grade = _lower(grade)
                reasons.extend(corroborated)
                generated_by = "model"

        appraisals.append(
            ClaimAppraisal(
                claim_id=claim_id,
                tier=tier,
                grade=grade,
                reasons=tuple(sorted(set(reasons))),
                generated_by=generated_by,
            )
        )
    return appraisals, rejected


def _apply_signal(signal: AppraisalSignal, audit: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Split a model's signals into the corroborated ones and the refused ones."""
    counter = int(audit.get("counter_evidence", 0) or 0)
    domains = int(audit.get("independent_domains", 0) or 0)
    corroborated: list[str] = []
    refused: list[str] = []

    if signal.contradicted:
        (corroborated if counter > 0 else refused).append("contradicted")
    if signal.single_source_dependence:
        (corroborated if domains <= 1 else refused).append("single_source_dependence")
    for fallacy in signal.fallacies:
        if fallacy in FALLACIES:
            corroborated.append(f"fallacy:{fallacy}")
        else:
            refused.append(f"unknown_fallacy:{fallacy}"[:120])
    # `underpowered` and `multiplicity_risk` have no counterpart in the stored audit, so
    # there is nothing to corroborate them against. They are recorded, never acted on.
    return corroborated, refused
