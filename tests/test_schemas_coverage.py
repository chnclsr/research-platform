import pytest
from pydantic import ValidationError

from research_platform.coverage import calculate_coverage
from research_platform.schemas import (
    AuthorityLevel, ConnectorSelection, ResearchProtocol, SourceFamily,
)


def test_all_profile_expands_families():
    selection = ConnectorSelection(profile="all")
    assert set(selection.included_families) == set(SourceFamily)


def test_a_protocol_cannot_exist_without_a_stated_collection_duration():
    """The requirement lives in the model, so no surface can route around it."""
    with pytest.raises(ValidationError) as missing_budget:
        ResearchProtocol(
            title="No budget at all",
            primary_question="Can a protocol omit its collection budget entirely?",
        )
    assert "budget" in str(missing_budget.value)

    with pytest.raises(ValidationError) as missing_minutes:
        ResearchProtocol(
            title="Budget without a duration",
            primary_question="Can a budget omit the duration but keep the source cap?",
            budget={"max_sources": 5},
        )
    assert "max_wall_minutes" in str(missing_minutes.value)


def test_plan_review_is_the_default_checkpoint():
    protocol = ResearchProtocol(
        title="Default checkpoints",
        primary_question="Which checkpoints does a run get without asking?",
        budget={"max_wall_minutes": 30},
    )
    assert protocol.hitl.plan_review is True
    assert protocol.hitl.planning_questions is False
    assert protocol.hitl.source_review is False
    assert protocol.hitl.outline_review is False


def test_coverage_requires_every_threshold():
    protocol = ResearchProtocol(
        title="Coverage test",
        primary_question="Is the evidence coverage sufficient?",
        connectors={"profile": "custom", "included_families": ["web", "academic"]},
        budget={"max_wall_minutes": 30},
    )
    result = calculate_coverage(
        protocol,
        ["web"] * 5 + ["academic"] * 5,
        {"branch-a": 2, "branch-b": 2},
        major_claims=2,
        audited_major_claims=2,
        unresolved_major_claims=0,
        new_source_rate=0.01,
        prior_saturated_rounds=1,
    )
    assert result.sufficient is True
    assert result.source_family_coverage == 1.0


def test_required_connector_must_be_operational_for_sufficient_coverage():
    protocol = ResearchProtocol(
        title="Critical connector",
        primary_question="Is required connector coverage enforced?",
        connectors={
            "profile": "custom", "included_families": ["web"],
            "required_connectors": ["agentsearch_web"],
        },
        stopping_criteria={"saturation_rounds": 1},
        budget={"max_wall_minutes": 30},
    )
    result = calculate_coverage(
        protocol, ["web"], {"branch": 1}, 0, 0, 0, 0.0, 0,
        claim_audit_required=False, critical_connector_coverage=0.0,
    )
    assert result.sufficient is False
    assert "critical_connector_coverage" in result.reasons


def test_invalid_protocol_rejects_unknown_fields():
    try:
        ResearchProtocol(
            title="Bad protocol", primary_question="Does this reject unknown fields?", unknown=True,
            budget={"max_wall_minutes": 30},
        )
    except Exception as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("Unknown protocol field was accepted")


def test_protocol_rejects_impossible_family_target_budget():
    with pytest.raises(ValueError, match="require at least 4 sources"):
        ResearchProtocol(
            title="Impossible protocol",
            primary_question="Can this impossible source budget be accepted?",
            connectors={
                "profile": "custom",
                "included_families": ["web", "academic"],
            },
            family_targets={
                "web": {"minimum_sources": 2},
                "academic": {"minimum_sources": 2},
            },
            budget={"max_sources": 3, "max_wall_minutes": 30},
        )


def test_protocol_without_source_limit_accepts_large_family_targets():
    protocol = ResearchProtocol(
        title="Unlimited source protocol",
        primary_question="Can collection continue until its time budget expires?",
        connectors={
            "profile": "custom",
            "included_families": ["web", "academic"],
        },
        family_targets={
            "web": {"minimum_sources": 80},
            "academic": {"minimum_sources": 80},
        },
        budget={"max_wall_minutes": 30},
    )
    assert protocol.budget.max_sources is None


def test_official_documentation_question_infers_strict_authority():
    protocol = ResearchProtocol(
        title="Official source protocol",
        primary_question="Codex için resmi dokümantasyon nasıl kullanılmalı?",
        budget={"max_wall_minutes": 30},
    )
    assert protocol.authority_policy.minimum_authority == AuthorityLevel.OFFICIAL
    assert protocol.authority_policy.strict_for_major_claims is True
