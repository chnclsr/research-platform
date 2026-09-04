from __future__ import annotations

from types import SimpleNamespace

import pytest

from research_platform.claim_appraisal import (
    AppraisalBundle,
    appraise_claims,
    propose_appraisal,
    select_appraisal_tier,
)
from research_platform.llm import LLMProvider
from research_platform.report_synthesis import source_design_labels
from research_platform.schemas import ConnectorSelection, ResearchProtocol, SourceFamily


def protocol(question="Does the intervention reduce mortality?", families=None):
    return ResearchProtocol(
        title="A run",
        primary_question=question,
        budget={"max_wall_minutes": 30},
        connectors=ConnectorSelection(
            included_families=families or [SourceFamily.ACADEMIC],
        ),
    )


def claim(claim_id="c1", *, status="supported", supporting=2, counter=0, domains=2):
    return SimpleNamespace(
        id=claim_id,
        text="The intervention reduces mortality in the studied population.",
        status=status,
        audit={
            "supporting_evidence": supporting,
            "counter_evidence": counter,
            "independent_domains": domains,
            "question_relevance": 0.8,
        },
    )


def source(source_id, connector_id, title=""):
    return SimpleNamespace(
        id=source_id, connector_id=connector_id, title=title, metadata_json={},
    )


def link(direction, source_obj):
    return (SimpleNamespace(direction=direction, quote="q"), source_obj)


# --- tier selection ----------------------------------------------------------------

def test_tier_stays_universal_for_a_patent_run():
    sources = [source("s1", "epo_ops"), source("s2", "sec_edgar")]
    tier, evidence = select_appraisal_tier(
        protocol("What does the patent landscape show?", [SourceFamily.PATENTS_STANDARDS]),
        sources,
        source_design_labels(sources),
    )
    assert tier == "universal"
    assert evidence["non_biomedical_connector"] is True


def test_tier_becomes_clinical_from_designs_without_europe_pmc():
    """An OpenAlex-only oncology run: a connector-name rule would have missed it."""
    sources = [
        source("s1", "openalex", "A randomized controlled trial of therapy"),
        source("s2", "crossref", "A prospective cohort study"),
        source("s3", "openalex", "A multicentre external validation"),
    ]
    tier, evidence = select_appraisal_tier(
        protocol("Does the therapy reduce mortality in a clinical trial?"),
        sources,
        source_design_labels(sources),
    )
    assert tier == "clinical"
    assert evidence["clinical_design_sources"] >= 3
    assert evidence["biomedical_connector"] is False


def test_one_stray_europe_pmc_source_does_not_make_a_patent_run_clinical():
    sources = [
        source("s1", "epo_ops", "A patent filing"),
        source("s2", "europe_pmc", "A biomedical note"),
    ]
    tier, _ = select_appraisal_tier(
        protocol("Which companies hold the patents?", [SourceFamily.PATENTS_STANDARDS]),
        sources,
        source_design_labels(sources),
    )
    assert tier == "universal"


def test_tier_decision_records_its_own_evidence():
    sources = [source("s1", "europe_pmc", "A randomized controlled trial")]
    tier, evidence = select_appraisal_tier(protocol(), sources, source_design_labels(sources))
    assert tier == "clinical"
    assert set(evidence) == {
        "score", "threshold", "biomedical_connector", "non_biomedical_connector",
        "academic_family", "academic_question", "clinical_design_sources",
    }
    assert evidence["score"] >= evidence["threshold"]


def test_design_labels_match_the_report_classifier():
    """Guards the reuse contract: one regex table, not two that can drift apart."""
    from research_platform.report_synthesis import _classify_design, _source_text

    rows = [source("s1", "openalex", "A randomized controlled trial of therapy")]
    assert source_design_labels(rows) == {
        "s1": _classify_design(_source_text(rows[0], []), True)
    }
    assert source_design_labels(rows)["s1"] == "Kontrollü çalışma"


# --- grading -----------------------------------------------------------------------

def grade_of(appraisals, claim_id="c1"):
    return next(a.grade for a in appraisals if a.claim_id == claim_id)


def test_deterministic_grades_cover_the_ladder():
    claims = [
        claim("c1", supporting=2, counter=0, domains=2),
        claim("c2", supporting=2, counter=1, domains=2),
        claim("c3", status="qualified", supporting=1, counter=0, domains=1),
        claim("c4", status="unresolved", supporting=0, counter=0, domains=0),
    ]
    appraisals, _ = appraise_claims(
        claims, {}, {}, tier="universal", minimum_independent_sources=2, proposal=None,
    )
    assert grade_of(appraisals, "c1") == "strong"
    assert grade_of(appraisals, "c2") == "moderate"
    assert grade_of(appraisals, "c3") == "limited"
    assert grade_of(appraisals, "c4") == "insufficient"


def test_clinical_tier_caps_grade_by_best_supporting_design():
    """Three observational sources cannot carry a claim to `strong`."""
    weak = source("s1", "openalex", "A retrospective cohort study")
    appraisals, _ = appraise_claims(
        [claim("c1")],
        {"c1": [link("supports", weak)]},
        {"s1": "Retrospektif"},
        tier="clinical", minimum_independent_sources=2, proposal=None,
    )
    assert grade_of(appraisals) == "moderate"
    assert "weak_supporting_design" in appraisals[0].reasons


def test_universal_tier_does_not_apply_the_clinical_cap():
    weak = source("s1", "openalex", "A retrospective cohort study")
    appraisals, _ = appraise_claims(
        [claim("c1")],
        {"c1": [link("supports", weak)]},
        {"s1": "Retrospektif"},
        tier="universal", minimum_independent_sources=2, proposal=None,
    )
    assert grade_of(appraisals) == "strong"


def test_stronger_contradicting_design_drops_the_grade():
    """One well-powered trial against several small series is the case that motivated this."""
    small = source("s1", "openalex", "A retrospective series")
    trial = source("s2", "europe_pmc", "A randomized controlled trial")
    appraisals, _ = appraise_claims(
        [claim("c1", counter=1)],
        {"c1": [link("supports", small), link("contradicts", trial)]},
        {"s1": "Gözlemsel", "s2": "Kontrollü çalışma"},
        tier="clinical", minimum_independent_sources=2, proposal=None,
    )
    assert grade_of(appraisals) == "limited"
    assert "contradicted_by_stronger_design" in appraisals[0].reasons


def test_narrative_review_only_caps_at_limited():
    review = source("s1", "openalex", "A narrative review")
    appraisals, _ = appraise_claims(
        [claim("c1")],
        {"c1": [link("supports", review)]},
        {"s1": "Anlatısal derleme"},
        tier="clinical", minimum_independent_sources=2, proposal=None,
    )
    assert grade_of(appraisals) == "limited"


# --- model proposal safety ---------------------------------------------------------

def bundle(**fields):
    return AppraisalBundle.model_validate({"signals": [{"claim_id": "c1", **fields}]})


def test_model_signal_without_corroboration_is_rejected():
    """`contradicted` needs counter_evidence in the stored audit to stand."""
    appraisals, rejected = appraise_claims(
        [claim("c1", counter=0, domains=2)], {}, {},
        tier="universal", minimum_independent_sources=2,
        proposal=bundle(contradicted=True),
    )
    assert grade_of(appraisals) == "strong"
    assert rejected == [{"claim_id": "c1", "signal": "contradicted"}]


def test_corroborated_model_signal_lowers_the_grade():
    appraisals, rejected = appraise_claims(
        [claim("c1", counter=1, domains=2)], {}, {},
        tier="universal", minimum_independent_sources=2,
        proposal=bundle(contradicted=True),
    )
    assert grade_of(appraisals) == "limited"
    assert rejected == []


def test_model_signal_can_only_lower_a_grade():
    """`replicated` is not a promotion lever; a thin claim stays thin."""
    appraisals, _ = appraise_claims(
        [claim("c1", status="qualified", supporting=1, domains=1)], {}, {},
        tier="universal", minimum_independent_sources=2,
        proposal=bundle(replicated=True),
    )
    assert grade_of(appraisals) == "limited"


def test_unknown_fallacy_names_are_refused():
    appraisals, rejected = appraise_claims(
        [claim("c1")], {}, {},
        tier="universal", minimum_independent_sources=2,
        proposal=bundle(fallacies=["invented_fallacy"]),
    )
    assert grade_of(appraisals) == "strong"
    assert rejected == [{"claim_id": "c1", "signal": "unknown_fallacy:invented_fallacy"}]


def test_appraisal_is_deterministic_for_the_same_input():
    args = ([claim("c1")], {}, {})
    kwargs = {"tier": "universal", "minimum_independent_sources": 2, "proposal": None}
    first, _ = appraise_claims(*args, **kwargs)
    second, _ = appraise_claims(*args, **kwargs)
    assert [a.as_audit_entry() for a in first] == [a.as_audit_entry() for a in second]


# --- provider behaviour ------------------------------------------------------------

class BrokenLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        raise RuntimeError("provider down")


class StringLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return '{"signals": [{"claim_id": "c1", "contradicted": true}]}'


class MalformedLLM(LLMProvider):
    async def complete_json(self, system: str, user: str):
        return {"signals": [{"no_claim_id": True}]}


@pytest.mark.asyncio
async def test_appraisal_falls_back_when_the_model_is_down():
    assert await propose_appraisal(
        BrokenLLM(), "universal", protocol(), [{"claim_id": "c1"}]
    ) is None


@pytest.mark.asyncio
async def test_appraisal_survives_a_string_json_answer():
    proposal = await propose_appraisal(
        StringLLM(), "universal", protocol(), [{"claim_id": "c1"}]
    )
    assert proposal is not None and proposal.signals[0].contradicted is True


@pytest.mark.asyncio
async def test_appraisal_rejects_a_malformed_bundle():
    assert await propose_appraisal(
        MalformedLLM(), "universal", protocol(), [{"claim_id": "c1"}]
    ) is None


@pytest.mark.asyncio
async def test_appraisal_is_not_requested_without_claims():
    assert await propose_appraisal(BrokenLLM(), "universal", protocol(), []) is None


def test_grades_are_still_produced_when_no_proposal_arrived():
    appraisals, _ = appraise_claims(
        [claim("c1")], {}, {},
        tier="universal", minimum_independent_sources=2, proposal=None,
    )
    assert appraisals[0].generated_by == "deterministic"
    assert appraisals[0].grade == "strong"
