from __future__ import annotations

from collections import Counter

from .schemas import CoverageMetrics, ResearchProtocol


def calculate_coverage(
    protocol: ResearchProtocol,
    source_families: list[str],
    branch_result_counts: dict[str, int],
    major_claims: int,
    audited_major_claims: int,
    unresolved_major_claims: int,
    new_source_rate: float,
    prior_saturated_rounds: int,
    *,
    authority_coverage: float = 1.0,
    claim_audit_required: bool = True,
    sentinel_recall: float = 1.0,
    estimated_completeness: float | None = None,
    relative_recall: float = 1.0,
    citation_frontier_novelty: float = 0.0,
    reserve_false_negative_rate: float = 0.0,
    critical_connector_coverage: float = 1.0,
    discovery_observations: int = 0,
    quality_diagnostics_active: bool = False,
) -> CoverageMetrics:
    counts = Counter(source_families)
    weighted_scores = []
    total_weight = 0.0
    for family, target in protocol.family_targets.items():
        score = (
            1.0 if target.minimum_sources == 0
            else min(1.0, counts.get(family.value, 0) / target.minimum_sources)
        )
        weighted_scores.append(score * target.weight)
        total_weight += target.weight
    family_coverage = sum(weighted_scores) / total_weight if total_weight else 0.0
    branch_coverage = (
        sum(1 for count in branch_result_counts.values() if count >= 1) / len(branch_result_counts)
        if branch_result_counts else 0.0
    )
    audit_coverage = (
        audited_major_claims / major_claims
        if major_claims
        else (0.0 if claim_audit_required else 1.0)
    )
    stopping = protocol.stopping_criteria
    saturated = prior_saturated_rounds + 1 if new_source_rate <= stopping.maximum_new_source_rate else 0
    reasons = []
    if family_coverage < stopping.minimum_source_coverage:
        reasons.append("source_family_coverage")
    if branch_coverage < stopping.minimum_query_branch_coverage:
        reasons.append("query_branch_coverage")
    if audit_coverage < stopping.minimum_claim_audit_coverage:
        reasons.append("claim_audit_coverage")
    if saturated < stopping.saturation_rounds:
        reasons.append("query_saturation")
    if unresolved_major_claims > stopping.unresolved_major_claim_limit:
        reasons.append("unresolved_major_claims")
    if protocol.authority_policy.strict_for_major_claims and authority_coverage < 1.0:
        reasons.append("authority_coverage")
    if protocol.sentinel_sources and sentinel_recall < stopping.minimum_sentinel_recall:
        reasons.append("sentinel_recall")
    if (
        quality_diagnostics_active
        and discovery_observations >= 5
        and estimated_completeness is not None
        and estimated_completeness < stopping.minimum_estimated_completeness
    ):
        reasons.append("estimated_completeness")
    if (
        quality_diagnostics_active
        and reserve_false_negative_rate > stopping.maximum_reserve_false_negative_rate
    ):
        reasons.append("reserve_false_negative_rate")
    if (
        quality_diagnostics_active
        and citation_frontier_novelty > stopping.maximum_citation_frontier_novelty
    ):
        reasons.append("citation_frontier_novelty")
    if protocol.connectors.required_connectors and critical_connector_coverage < 1.0:
        reasons.append("critical_connector_coverage")
    return CoverageMetrics(
        source_family_coverage=round(family_coverage, 4),
        query_branch_coverage=round(branch_coverage, 4),
        claim_audit_coverage=round(audit_coverage, 4),
        new_source_rate=round(new_source_rate, 4),
        unresolved_major_claims=unresolved_major_claims,
        authority_coverage=round(authority_coverage, 4),
        saturated_rounds=saturated,
        sentinel_recall=round(sentinel_recall, 4),
        estimated_completeness=(
            round(estimated_completeness, 4)
            if estimated_completeness is not None else None
        ),
        relative_recall=round(relative_recall, 4),
        citation_frontier_novelty=round(citation_frontier_novelty, 4),
        reserve_false_negative_rate=round(reserve_false_negative_rate, 4),
        critical_connector_coverage=round(critical_connector_coverage, 4),
        discovery_observations=discovery_observations,
        sufficient=not reasons,
        reasons=reasons,
    )
