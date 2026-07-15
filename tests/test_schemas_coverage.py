from research_platform.coverage import calculate_coverage
from research_platform.schemas import (
    ConnectorSelection, ResearchProtocol, SourceFamily,
)


def test_all_profile_expands_families():
    selection = ConnectorSelection(profile="all")
    assert set(selection.included_families) == set(SourceFamily)


def test_coverage_requires_every_threshold():
    protocol = ResearchProtocol(
        title="Coverage test",
        primary_question="Is the evidence coverage sufficient?",
        connectors={"profile": "custom", "included_families": ["web", "academic"]},
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


def test_invalid_protocol_rejects_unknown_fields():
    try:
        ResearchProtocol(
            title="Bad protocol", primary_question="Does this reject unknown fields?", unknown=True
        )
    except Exception as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("Unknown protocol field was accepted")

