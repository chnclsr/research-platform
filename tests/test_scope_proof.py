"""Unit tests for the deterministic scope layer.

Every route case here is a shape actually measured in run 01M203HHZXZB61YF59AZZQ2YA4,
where 89 sources with all facets matched were barred because a 4B model reproduces meaning
but not punctuation. The paraphrase cases are the other half of that corpus and must stay
rejected: the point of the ladder is to stop formatting from deciding scope, not to accept
whatever the model writes.
"""

from __future__ import annotations

import pytest

from research_platform.schemas import ResearchScopeCriteria, SourceScopeRole
from research_platform.scope_proof import (
    MIN_QUOTE_SEGMENT_CHARS,
    ScopeHaystack,
    evidence_route,
    exclusion_decision,
    scope_verdict,
    signal_key,
)

# CT2Rep, the most on-topic paper in run 01M203, barred as near-scope by the old predicate.
CT2REP = (
    "CT2Rep: Automated Radiology Report Generation for 3D Medical Imaging. "
    "We introduce the first method to generate radiology reports for 3D chest CT volumes, "
    "and extend it to a longitudinal setting that uses prior scans."
)


def haystack(text: str = CT2REP) -> ScopeHaystack:
    return ScopeHaystack.build(text)


def route(quote: str, text: str = CT2REP, values=(), **kwargs) -> str:
    return evidence_route(quote, haystack(text), values, **kwargs)


# --- routes: the measured failure shapes -------------------------------------------------


def test_raw_substring_is_verbatim():
    """The pre-fix predicate, unchanged. Every later route is added on top of this one."""
    assert route("generate radiology reports for 3D chest CT volumes") == "verbatim"


def test_case_difference_alone_is_verbatim():
    assert route("GENERATE RADIOLOGY REPORTS") == "verbatim"


@pytest.mark.parametrize(
    "quote",
    [
        pytest.param("CT2Rep - Automated Radiology Report Generation", id="punctuation"),
        pytest.param("3D  chest\n  CT volumes", id="whitespace"),
        pytest.param("“CT2Rep”: Automated Radiology Report Generation", id="curly_quotes"),
        pytest.param("CT2Rep — automated radiology report generation", id="em_dash"),
    ],
)
def test_formatting_only_differences_are_normalized(quote):
    """38 of 123 unprovable quotes in run 01M203 differed from the source only like this."""
    assert route(quote) == "normalized"


def test_elided_quote_is_proven_when_every_fragment_is_present_in_order():
    """The largest single shape: two real fragments the model joined with an ellipsis."""
    assert route("We introduce the first method...that uses prior scans") == "elided"
    assert route("We introduce the first method … that uses prior scans") == "elided"
    assert route("We introduce the first method [...] that uses prior scans") == "elided"


def test_several_fragments_are_walked_in_one_pass():
    """Each hop resumes where the previous fragment ended, never before it."""
    quote = (
        "Automated Radiology Report Generation...radiology reports for 3D chest"
        "...that uses prior scans"
    )
    assert route(quote) == "elided"


def test_fragments_adjacent_in_the_source_are_claimed_by_the_earlier_route():
    """Folding drops the ellipsis, so a quote elided at a word gap is simply normalized."""
    assert route("radiology reports for...3D chest CT volumes") == "normalized"


# --- routes: what must stay rejected -----------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        pytest.param("AI in CT imaging", id="high_overlap_paraphrase"),
        pytest.param("the model reports on chest scans", id="paraphrase"),
        pytest.param("trained on 50,000 annotated brain MRI studies", id="invention"),
    ],
)
def test_paraphrase_is_never_proven(quote):
    """39 paraphrases and 8 inventions; token overlap is not a quotation."""
    assert route(quote) == "unproven"


def test_bare_ellipsis_proves_nothing():
    assert route("...") == "unproven"


def test_fragments_must_appear_in_the_source_order():
    """Otherwise the model can stitch a proof out of fragments the source never joined."""
    assert route("that uses prior scans...We introduce the first method") == "unproven"


def test_fragments_under_the_floor_are_dropped_rather_than_matched():
    """Two words, roughly. A three-character fragment neither proves nor blocks."""
    assert len(signal_key("chest CT")) < MIN_QUOTE_SEGMENT_CHARS
    # Nothing survives the floor, so there is no proof at all.
    assert route("3D chest ... prior") == "unproven"
    # What does survive must still be found.
    assert route("chest CT...brain MRI perfusion studies") == "unproven"
    # And it carries the quote alone: the dropped fragment is never checked. That is the
    # cost of the floor, and it is cheaper than letting noise satisfy a segment.
    assert route("MRI...that uses prior scans") == "elided"


def test_absent_fragment_breaks_the_chain():
    assert route("We introduce the first method...on brain MRI perfusion") == "unproven"


# --- routes: accepted values -------------------------------------------------------------


def test_accepted_value_matches_on_whole_tokens_only():
    """The largest false-positive risk this fix introduces: "CT" inside "reconstruction"."""
    text = "The reconstruction acted on the projections and reflected the geometry."
    assert route("", text, ["CT"]) == "unproven"
    assert route("AI in CT imaging", text, ["CT"]) == "unproven"


def test_accepted_value_rescues_a_paraphrase_and_records_which_route_did_it():
    assert route("AI in CT imaging", values=["3D"]) == "accepted_value"
    assert route("", values=["3D"]) == "accepted_value_no_quote"


def test_accepted_values_can_be_withheld():
    """Exclusions take this path: the label's own words are not proof it applies."""
    assert route("AI in CT imaging", values=["3D"], allow_accepted_values=False) == "unproven"


def test_a_one_character_accepted_value_is_ignored():
    assert route("", "a b c", ["a"]) == "unproven"


def test_the_ladder_is_a_strict_superset_of_the_old_predicate():
    """Nothing the pre-fix predicate admitted may be rejected by this module."""
    text = CT2REP.casefold()
    for start in range(0, len(text) - 20, 7):
        quote = text[start : start + 20]
        assert evidence_route(quote, haystack()) != "unproven", quote


# --- signal folding ----------------------------------------------------------------------


def test_signal_key_folds_case_punctuation_and_spacing():
    assert signal_key("PET/CT") == "pet ct"
    assert signal_key("  2D-only   input ") == "2d only input"
    assert signal_key(None) == ""


def test_exclusion_decision_is_reachable_from_its_new_home():
    """Moved from pipeline.py unchanged; test_pipeline.py owns the behavioural corpus."""
    approved = ["2D-only input", "single-slice input"]
    merged = [
        {"exclusion": "2D-only or single-slice input", "matched": False, "reason": "3D"},
    ]
    assert exclusion_decision("2D-only input", merged, approved) is merged[0]
    assert exclusion_decision("input", merged, approved) is None


# --- the deterministic ladder ------------------------------------------------------------


def criteria(
    *,
    task_name: str = "task",
    extra_task: bool = False,
    task_values: list[str] | None = None,
) -> ResearchScopeCriteria:
    facets = [
        {"name": "anatomy", "accepted_values": ["chest"]},
        {"name": "modality", "accepted_values": ["CT"]},
        {"name": task_name, "accepted_values": task_values or ["report generation"]},
    ]
    if extra_task:
        facets.append({"name": "task_type", "accepted_values": ["classification"]})
    return ResearchScopeCriteria.model_validate(
        {"required_facets": facets, "exclusion_signals": ["PET/CT", "2D-only input"]}
    )


def facet(name, matched=True, reason="decided", evidence=""):
    return {"facet": name, "matched": matched, "reason": reason, "evidence": evidence}


def proven_facets(task_name="task"):
    return [
        facet("anatomy", evidence="chest CT volumes"),
        facet("modality", evidence="3D chest CT"),
        facet(task_name, evidence="generate radiology reports"),
    ]


def clear_exclusions():
    return [
        {"exclusion": "PET/CT", "matched": False, "reason": "absent", "evidence": ""},
        {"exclusion": "2D-only input", "matched": False, "reason": "absent", "evidence": ""},
    ]


def verdict(requested, facets=None, exclusions=None, *, crit=None, reason="direct:"):
    return scope_verdict(
        crit or criteria(),
        requested,
        proven_facets() if facets is None else facets,
        clear_exclusions() if exclusions is None else exclusions,
        CT2REP,
        reason,
    )


@pytest.mark.parametrize("requested", list(SourceScopeRole))
def test_the_role_is_a_function_of_proof_not_of_the_model_label(requested):
    """The 89-source correction: a self-downgraded source with proven facets is promoted."""
    expected = (
        SourceScopeRole.SUPPORTING_BENCHMARK
        if requested == SourceScopeRole.SUPPORTING_BENCHMARK
        else SourceScopeRole.PRIMARY_IN_SCOPE
    )
    result = verdict(requested)
    assert result.role == expected
    assert result.requested_role == requested
    assert result.unproven_facets == ()
    if requested != expected:
        assert f"role_promoted_from:{requested.value}" in result.reasons


def test_an_unproven_facet_still_bars_a_source_the_model_called_primary():
    """Neither route reaches it: the quote is a paraphrase and no accepted value is present."""
    result = verdict(
        SourceScopeRole.PRIMARY_IN_SCOPE,
        [*proven_facets()[:2], facet("task", evidence="AI in CT imaging")],
        crit=criteria(task_values=["fracture detection"]),
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert result.unproven_facets == ("task",)
    assert "facet_unproven:task" in result.reasons


def test_a_facet_the_model_declined_cannot_be_proven_by_an_accepted_value():
    """`matched: false` is a decision, not a gap for the value route to fill.

    "report generation" is present in the text, so only the guard on `matched` bars this.
    """
    result = verdict(
        SourceScopeRole.PRIMARY_IN_SCOPE,
        [*proven_facets()[:2], facet("task", matched=False, reason="no report generation")],
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert result.unproven_facets == ("task",)


def test_facet_names_are_folded_so_a_backfill_cannot_erase_a_real_decision():
    """Run 01M203 named the facet `application_task`; the model answered "Application Task"."""
    crit = criteria(task_name="application_task")
    facets = [
        *proven_facets()[:2],
        facet("Application Task", evidence="generate radiology reports"),
        facet("application_task", matched=None, reason=""),  # the pipeline's backfill
    ]
    result = scope_verdict(
        crit, SourceScopeRole.NEAR_SCOPE, facets, clear_exclusions(), CT2REP, "direct:"
    )
    assert result.role == SourceScopeRole.PRIMARY_IN_SCOPE
    assert result.proven_facets == ("anatomy", "modality", "application task")


def test_an_undecided_facet_is_a_near_match_not_a_promotion():
    result = verdict(
        SourceScopeRole.PRIMARY_IN_SCOPE,
        [*proven_facets()[:2], facet("task", matched=None, reason="")],
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert "facet_decision_missing:task" in result.reasons


def test_a_missing_classification_reason_short_circuits_everything():
    result = verdict(SourceScopeRole.PRIMARY_IN_SCOPE, reason="  ")
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert result.reasons == ("classification_reason_missing",)


# --- the benchmark lane ------------------------------------------------------------------


def test_benchmark_excuses_a_task_facet_the_model_consciously_declined():
    result = verdict(
        SourceScopeRole.SUPPORTING_BENCHMARK,
        [*proven_facets()[:2], facet("task", matched=False, reason="evaluates, does not generate")],
    )
    assert result.role == SourceScopeRole.SUPPORTING_BENCHMARK
    assert result.excused_facets == ("task",)
    assert "benchmark_task_excused:task" in result.reasons


def test_the_excusal_finds_the_task_facet_by_meaning_not_by_literal_name():
    """`required.discard("task")` silently never fired on run 01M203's `application_task`."""
    crit = criteria(task_name="application_task")
    facets = [
        *proven_facets()[:2],
        facet("application_task", matched=False, reason="evaluates only"),
    ]
    result = scope_verdict(
        crit,
        SourceScopeRole.SUPPORTING_BENCHMARK,
        facets,
        clear_exclusions(),
        CT2REP,
        "direct:",
    )
    assert result.role == SourceScopeRole.SUPPORTING_BENCHMARK
    assert result.excused_facets == ("application task",)


def test_two_task_like_facets_excuse_neither():
    """Same rule as an ambiguous exclusion fragment: what is ambiguous decides nothing."""
    crit = criteria(extra_task=True)
    facets = [
        *proven_facets()[:2],
        facet("task", matched=False, reason="evaluates only"),
        facet("task_type", matched=False, reason="not classification"),
    ]
    result = scope_verdict(
        crit,
        SourceScopeRole.SUPPORTING_BENCHMARK,
        facets,
        clear_exclusions(),
        CT2REP,
        "direct:",
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert result.excused_facets == ()


def test_a_backfilled_non_decision_is_not_a_benchmark_admission():
    result = verdict(
        SourceScopeRole.SUPPORTING_BENCHMARK,
        [*proven_facets()[:2], facet("task", matched=None, reason="")],
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert result.excused_facets == ()


def test_the_primary_lane_never_excuses_a_task_facet():
    result = verdict(
        SourceScopeRole.PRIMARY_IN_SCOPE,
        [*proven_facets()[:2], facet("task", matched=False, reason="evaluates only")],
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE


# --- exclusions --------------------------------------------------------------------------


def test_a_proven_exclusion_outranks_every_proven_facet():
    matched = [
        {
            "exclusion": "PET/CT",
            "matched": True,
            "reason": "whole-body PET/CT",
            "evidence": "CT2Rep - Automated Radiology Report Generation",
        },
        clear_exclusions()[1],
    ]
    result = verdict(SourceScopeRole.PRIMARY_IN_SCOPE, exclusions=matched)
    assert result.role == SourceScopeRole.EXCLUDED
    assert result.proven_exclusions == ("pet ct",)
    assert "exclusion_proven:pet ct" in result.reasons


def test_an_exclusion_may_not_be_proven_by_the_label_appearing_in_the_text():
    """The text says the opposite of the signal, so its words cannot prove it applies."""
    text = "A chest CT report generation model; PET/CT is not used anywhere in this work."
    claimed = [
        {"exclusion": "PET/CT", "matched": True, "reason": "mentions PET/CT", "evidence": ""},
        clear_exclusions()[1],
    ]
    result = scope_verdict(
        criteria(), SourceScopeRole.PRIMARY_IN_SCOPE, proven_facets(), claimed, text, "direct:"
    )
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert "exclusion_claimed_unproven:pet ct" in result.reasons


def test_an_undecided_exclusion_bars_promotion():
    result = verdict(SourceScopeRole.PRIMARY_IN_SCOPE, exclusions=[clear_exclusions()[0]])
    assert result.role == SourceScopeRole.NEAR_SCOPE
    assert "exclusion_decision_missing:2d only input" in result.reasons


# --- what gets recorded ------------------------------------------------------------------


def test_the_audit_entry_carries_everything_needed_to_explain_the_role():
    result = verdict(SourceScopeRole.NEAR_SCOPE)
    entry = result.as_audit_entry()
    assert entry["role"] == SourceScopeRole.PRIMARY_IN_SCOPE.value
    assert entry["requested_role"] == SourceScopeRole.NEAR_SCOPE.value
    assert entry["role_source"] == "deterministic"
    assert entry["proven_facets"] == ["anatomy", "modality", "task"]
    assert entry["unproven_facets"] == []
    assert "role_promoted_from:near_scope" in entry["role_reasons"]


def test_each_facet_records_its_route_and_whether_the_value_was_present():
    result = verdict(SourceScopeRole.PRIMARY_IN_SCOPE)
    by_facet = {p.facet: p for p in result.facet_proofs}
    assert by_facet["anatomy"].route == "verbatim"
    assert by_facet["anatomy"].value_present is True
    assert by_facet["anatomy"].quote_proved is True
    assert [p.as_audit_entry()["facet_key"] for p in result.facet_proofs] == [
        "anatomy",
        "modality",
        "task",
    ]


def test_a_quote_only_promotion_stays_countable():
    """Risk 1 of this fix: only the quote's existence is checked, never its relevance.

    A source promoted on a quote alone, with no accepted value anywhere in the text, is the
    population that would need a stricter gate. `value_present` keeps it a countable set
    instead of an unmeasurable one.
    """
    crit = ResearchScopeCriteria.model_validate(
        {
            "required_facets": [{"name": "task", "accepted_values": ["fracture detection"]}],
            "exclusion_signals": [],
        }
    )
    result = scope_verdict(
        crit,
        SourceScopeRole.NEAR_SCOPE,
        [facet("task", evidence="generate radiology reports")],
        [],
        CT2REP,
        "direct:",
    )
    assert result.role == SourceScopeRole.PRIMARY_IN_SCOPE
    proof = result.facet_proofs[0]
    assert proof.route == "verbatim"
    assert proof.value_present is False
