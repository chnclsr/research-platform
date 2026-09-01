"""Build the next recall probe for the run in front of you, not the next one in a list.

Recovery used to rotate six hand-written strategy suffixes by round number. The rotation
knew nothing about which gaps were open, what had already been tried or which connectors
were still answering, so a run could spend its whole collection budget re-asking variations
of a question that had never returned anything: `01M14A8RP5ZD36NEX889AXRKSP` made 215
connector calls across 28 rounds for zero results, and cycling the same six suffixes would
not have rescued it.

What replaced it keeps the model on a short leash. It combines a tactic, a gap and a focus
phrase into at most three `ProbeCandidate`s -- and nothing else. Every operational value
(connectors, family, limits, date scope) is decided here, from the protocol, by code that
does not ask anyone. A candidate that names a connector the protocol excludes, or repeats a
mission already attempted, is refused rather than repaired.
"""

from __future__ import annotations

import json
from typing import Any

from .llm import LLMProvider
from .recovery import FAMILY_CONNECTORS, mission_signature
from .schemas import (
    CoverageGap,
    ProbeBundle,
    ProbeCandidate,
    ProbeTactic,
    ResearchProtocol,
    SearchMission,
)
from .temporal import constrain_text_to_scope

#: How each tactic asks differently. Given to the model as its whole vocabulary, and used
#: by the compiler to shape the query, so the two cannot drift apart.
TACTIC_GUIDE: dict[ProbeTactic, str] = {
    ProbeTactic.TERMINOLOGY_SHIFT: "same subject named the way another field names it",
    ProbeTactic.METHODOLOGY_FOCUS: "how the work was done rather than what it concluded",
    ProbeTactic.COUNTEREVIDENCE: "negative results, limitations, failures, contradictions",
    ProbeTactic.AUTHORITY_FOCUS: "guidance, standards, regulation, institutional positions",
    ProbeTactic.EXACT_IDENTIFIER: "a specific name, identifier, registry or model number",
    ProbeTactic.CITATION_NEIGHBORHOOD: "what cites or is cited by the work already found",
    ProbeTactic.TEMPORAL_UPDATE: "the most recent work, updates and revisions",
    ProbeTactic.POPULATION_CONTEXT: "a different population, setting, region or scale",
}

_SYSTEM = (
    "You propose ways to search again after earlier searches came back empty. "
    "Answer with JSON only: {\"candidates\": [{\"tactic\": \"...\", \"query_focus\": \"...\", "
    "\"target_gap_ids\": [\"...\"], \"connector_ids\": [\"...\"], \"reason\": \"...\"}]}. "
    "At most three candidates. Use only the tactics and connector ids you are given. "
    "query_focus is a short phrase to search for, not a sentence. "
    "Do not choose domains, limits, dates or source families -- those are not yours to set."
)

_MAX_QUERY_CHARS = 240


def _user_prompt(
    protocol: ResearchProtocol,
    gaps: list[CoverageGap],
    healthy_connectors: list[str],
    previous_attempts: list[dict[str, Any]],
) -> str:
    tactics = "\n".join(f"- {tactic.value}: {guide}" for tactic, guide in TACTIC_GUIDE.items())
    gap_lines = "\n".join(
        f"- {gap.id} | {gap.dimension} | {gap.topic}"
        + (f" | missing family: {gap.missing_family.value}" if gap.missing_family else "")
        for gap in gaps[:8]
    ) or "- (none recorded)"
    # A summary, never the raw trajectory: probe context can carry unresolved claim text.
    attempts = json.dumps({"previous_attempts": previous_attempts[-6:]}, ensure_ascii=False)
    return (
        f"Research question:\n{protocol.primary_question}\n\n"
        f"Open gaps:\n{gap_lines}\n\n"
        f"Tactics:\n{tactics}\n\n"
        f"Connectors still answering: {', '.join(healthy_connectors) or '(none)'}\n\n"
        f"What has already been tried and what it returned:\n{attempts}"
    )


async def generate_probe_bundle(
    llm: LLMProvider,
    protocol: ResearchProtocol,
    gaps: list[CoverageGap],
    healthy_connectors: list[str],
    previous_attempts: list[dict[str, Any]],
) -> ProbeBundle | None:
    """Ask for up to three probe candidates, or return None and let the caller fall back.

    `llm` is the run's own local provider, never the preparation chain: the prompt carries
    gap topics and attempt summaries drawn from the corpus, and that stays inside the
    deployment's existing data boundary.
    """
    try:
        answer = await llm.complete_json(
            _SYSTEM, _user_prompt(protocol, gaps, healthy_connectors, previous_attempts)
        )
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
        return ProbeBundle.model_validate({"candidates": answer.get("candidates") or []})
    except ValueError:
        return None


def _allowed_connectors(protocol: ResearchProtocol) -> set[str]:
    allowed: set[str] = set()
    for family in protocol.connectors.included_families:
        allowed.update(FAMILY_CONNECTORS.get(family, []))
    if protocol.connectors.included_connectors:
        allowed &= set(protocol.connectors.included_connectors)
    return allowed - set(protocol.connectors.excluded_connectors)


def compile_probe_candidate(
    candidate: ProbeCandidate,
    protocol: ResearchProtocol,
    gaps: list[CoverageGap],
    healthy_connectors: list[str],
    attempted: set[str],
    round_number: int,
) -> SearchMission | None:
    """Turn a blueprint into a mission, or refuse it.

    Everything operational is decided here. The model's connector list is intersected with
    what the protocol allows and what is still answering, rather than trusted; the limits
    come from the budget; the query is anchored on the real question and constrained to the
    protocol's date scope. A mission whose signature was already attempted is refused, which
    is what stops the run re-asking a question it has already asked.
    """
    # The gap the model named, or the one that matters most when it named none. A probe
    # without a gap is a probe without a reason to exist, and which gap it serves is a
    # deterministic choice rather than something to leave unset.
    gap = next((item for item in gaps if item.id in candidate.target_gap_ids), None)
    if gap is None and gaps:
        gap = max(gaps, key=lambda item: item.priority)
    healthy = set(healthy_connectors)
    connector_ids = [
        connector_id
        for connector_id in candidate.connector_ids
        if connector_id in _allowed_connectors(protocol) and connector_id in healthy
    ]
    if not connector_ids and gap is not None:
        connector_ids = [
            connector_id
            for connector_id in gap.preferred_connectors
            if connector_id in _allowed_connectors(protocol) and connector_id in healthy
        ]
    if not connector_ids:
        return None
    focus = " ".join(candidate.query_focus.split())[:120]
    query = f"{protocol.primary_question} {focus}".strip()[:_MAX_QUERY_CHARS]
    query = constrain_text_to_scope(query, protocol.scope.start_date, protocol.scope.end_date)
    if not query.strip():
        return None
    mission = SearchMission(
        gap_id=gap.id if gap else None,
        branch_id=f"probe:{candidate.tactic.value}:{round_number}",
        query=query,
        connector_ids=connector_ids[:8],
        required_family=gap.missing_family if gap else None,
        result_limit=protocol.budget.results_per_connector,
        acquisition_slots=min(10, protocol.budget.results_per_connector),
        novelty_required=True,
    )
    if mission_signature(mission) in attempted:
        return None
    return mission


def score_probe_candidate(
    candidate: ProbeCandidate,
    mission: SearchMission,
    gaps: list[CoverageGap],
    previous_attempts: list[dict[str, Any]],
) -> float:
    """Rank the compiled candidates. Deterministic, so the choice can be argued with.

    The model's own order is not the ranking: it is recorded as `suggested_rank` beside the
    scorer's pick, because a selector nobody can disagree with cannot be shown to work.
    """
    score = 0.0
    targeted = [gap for gap in gaps if gap.id in candidate.target_gap_ids]
    if targeted:
        score += 0.35 * max(gap.priority for gap in targeted)
    if mission.required_family is not None:
        score += 0.15
    spent_tactics = {str(item.get("tactic") or "") for item in previous_attempts}
    if candidate.tactic.value not in spent_tactics:
        score += 0.30
    barren = {
        str(item.get("connector") or "")
        for item in previous_attempts
        if not int(item.get("provider_candidates") or 0)
    }
    if not set(mission.connector_ids) & barren:
        score += 0.20
    return round(score, 4)
