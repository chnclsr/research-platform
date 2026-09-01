"""Recall probes built for the run in front of you, instead of rotated from a list.

Recovery used to cycle six hand-written strategy suffixes by round number, knowing nothing
about which gaps were open, what had been tried, or which connectors still answered. Run
01M14A8RP5ZD36NEX889AXRKSP spent 215 connector calls over 28 rounds for zero results, and
the rotation would have kept going.

What the model may decide is deliberately small: a tactic, a focus phrase, a gap and a
connector shortlist. Everything operational is the compiler's, and most of the tests below
exist to keep it that way.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import acting_principal

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import ResearchPipeline
from research_platform.probe_factory import (
    compile_probe_candidate,
    generate_probe_bundle,
    score_probe_candidate,
)
from research_platform.recovery import mission_signature, recovery_missions
from research_platform.repository import Repository
from research_platform.schemas import (
    CoverageGap,
    ProbeCandidate,
    ProbeTactic,
    ResearchProtocol,
    SourceFamily,
)


class ProbeLLM:
    """Returns the scripted bundles, and counts how often it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0
        self.prompts: list[str] = []

    async def complete_json(self, system: str, user: str):
        self.calls += 1
        self.prompts.append(user)
        if not self.answers:
            raise AssertionError("asked more times than the test scripted")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def drain_metrics(self):
        return []


def protocol(**overrides) -> ResearchProtocol:
    payload = {
        "title": "Probe factory",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30, "results_per_connector": 12},
        "research_mode": "literature_scan",
    }
    payload.update(overrides)
    return ResearchProtocol.model_validate(payload)


def gap(**overrides) -> CoverageGap:
    payload = {
        "dimension": "source_family",
        "topic": "external validation",
        "missing_family": "academic",
        "preferred_connectors": ["semantic_scholar"],
        "priority": 0.9,
    }
    payload.update(overrides)
    return CoverageGap.model_validate(payload)


def candidate(**overrides) -> ProbeCandidate:
    payload = {
        "tactic": ProbeTactic.METHODOLOGY_FOCUS,
        "query_focus": "prospective external validation",
        "connector_ids": ["semantic_scholar"],
    }
    payload.update(overrides)
    return ProbeCandidate.model_validate(payload)


HEALTHY = ["semantic_scholar", "arxiv", "europe_pmc"]


def test_the_compiler_keeps_only_connectors_that_are_allowed_and_answering():
    """The model's shortlist is intersected, never trusted."""
    one = gap()
    mission = compile_probe_candidate(
        candidate(connector_ids=["semantic_scholar", "invented_connector", "arxiv"]),
        protocol(),
        [one],
        ["semantic_scholar"],
        set(),
        4,
    )
    assert mission is not None
    assert mission.connector_ids == ["semantic_scholar"]


def test_a_family_the_protocol_excluded_yields_no_connectors_and_no_mission():
    narrow = protocol(connectors={"included_families": ["code_data"]})
    assert compile_probe_candidate(
        candidate(), narrow, [gap()], HEALTHY, set(), 4
    ) is None


def test_a_mission_already_attempted_is_refused():
    """What stops the run asking a question it has already asked."""
    one = gap()
    first = compile_probe_candidate(candidate(), protocol(), [one], HEALTHY, set(), 4)
    assert first is not None
    again = compile_probe_candidate(
        candidate(), protocol(), [one], HEALTHY, {mission_signature(first)}, 4
    )
    assert again is None


def test_operational_values_come_from_the_protocol_not_the_model():
    mission = compile_probe_candidate(
        candidate(), protocol(), [gap()], HEALTHY, set(), 4
    )
    assert mission.result_limit == 12
    assert mission.acquisition_slots == 10
    assert mission.novelty_required is True
    assert mission.required_family == SourceFamily.ACADEMIC
    # The real question anchors the query; the focus phrase only narrows it.
    assert "pulmonary nodules" in mission.query


def test_the_query_is_constrained_to_the_protocol_date_scope():
    dated = protocol(scope={"start_date": "2024-01-01T00:00:00Z", "end_date": "2024-12-31T00:00:00Z"})
    mission = compile_probe_candidate(
        candidate(query_focus="results from 2019"), dated, [gap()], HEALTHY, set(), 4
    )
    assert mission is not None
    assert "2019" not in mission.query


@pytest.mark.asyncio
async def test_three_candidates_cost_one_call():
    """Best-of-N without paying for N calls."""
    llm = ProbeLLM({
        "candidates": [
            {"tactic": "terminology_shift", "query_focus": "lung nodule"},
            {"tactic": "counterevidence", "query_focus": "false positives"},
            {"tactic": "authority_focus", "query_focus": "screening guideline"},
        ]
    })
    bundle = await generate_probe_bundle(llm, protocol(), [gap()], HEALTHY, [])
    assert llm.calls == 1
    assert len(bundle.candidates) == 3


@pytest.mark.asyncio
async def test_a_broken_or_unreachable_model_produces_no_bundle():
    for answer in ({"candidates": [{"tactic": "invented"}]}, "nonsense", RuntimeError("down")):
        assert await generate_probe_bundle(
            ProbeLLM(answer), protocol(), [gap()], HEALTHY, []
        ) is None


def test_the_scorer_prefers_an_unspent_tactic_over_a_repeated_one():
    one = gap()
    spent = [{"tactic": "methodology_focus", "connector": "semantic_scholar",
              "provider_candidates": 3, "new_source_versions": 0}]
    repeated = candidate(target_gap_ids=[one.id])
    fresh = candidate(tactic=ProbeTactic.COUNTEREVIDENCE, target_gap_ids=[one.id])
    mission = compile_probe_candidate(repeated, protocol(), [one], HEALTHY, set(), 4)
    assert score_probe_candidate(fresh, mission, [one], spent) > score_probe_candidate(
        repeated, mission, [one], spent
    )


def test_the_scorer_demotes_a_connector_that_returned_nothing():
    one = gap()
    mission = compile_probe_candidate(candidate(target_gap_ids=[one.id]), protocol(), [one], HEALTHY, set(), 4)
    barren = [{"tactic": "x", "connector": "semantic_scholar",
               "provider_candidates": 0, "new_source_versions": 0}]
    productive = [{"tactic": "x", "connector": "semantic_scholar",
                   "provider_candidates": 9, "new_source_versions": 2}]
    assert score_probe_candidate(candidate(target_gap_ids=[one.id]), mission, [one], barren) < \
        score_probe_candidate(candidate(target_gap_ids=[one.id]), mission, [one], productive)


async def _pipeline(session, client, llm, *, enabled: bool = True):
    settings = get_settings().model_copy(
        update={"probe_strategy_selection_enabled": enabled}
    )
    pipeline = ResearchPipeline(settings, session, client)
    pipeline.llm = llm
    return pipeline


def _state(row, one: CoverageGap, **extra) -> dict:
    """The state a run is in when ordinary gap missions have already been spent.

    That is the only state the probe path exists for: `recovery_missions` builds a mission
    for every open gap, so the probes are reached only once those signatures are attempted.
    """
    spent = [
        mission_signature(mission)
        for mission in recovery_missions(
            ResearchProtocol.model_validate(row.protocol), [one], set()
        )
    ]
    state = {
        "run_id": row.id,
        "protocol": row.protocol,
        "round_number": 3,
        "gaps": [one.model_dump(mode="json")],
        "available_connectors": HEALTHY,
        "connector_success_rates": {name: 1.0 for name in HEALTHY},
        "attempted_missions": spent,
        **extra,
    }
    if "attempted_missions" in extra:
        state["attempted_missions"] = [*spent, *extra["attempted_missions"]]
    return state


async def _run_probe(llm, *, enabled: bool = True, **state_extra):
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol())
        pipeline = await _pipeline(session, client, llm, enabled=enabled)
        one = gap()
        output = await pipeline.plan_recovery(_state(row, one, **state_extra))
        events = {
            name: await repo.events_by_types(row.id, {name})
            for name in (
                "probe_bundle_generated",
                "probe_candidate_selected",
            )
        }
        return output, events


BUNDLE = {
    "candidates": [
        {"tactic": "terminology_shift", "query_focus": "lung nodule screening"},
        {"tactic": "counterevidence", "query_focus": "false positive rate"},
    ]
}


@pytest.mark.asyncio
async def test_a_probe_round_runs_one_candidate_and_keeps_the_rest():
    llm = ProbeLLM(BUNDLE)
    output, events = await _run_probe(llm)
    assert llm.calls == 1
    assert len(output["missions"]) == 1
    # The unspent candidate waits rather than being thrown away and re-bought.
    assert len(output["probe_candidates_pending"]) == 1
    assert len(events["probe_bundle_generated"]) == 1
    selected = events["probe_candidate_selected"][0].payload
    assert selected["selected_by"] == "scorer"
    assert selected["suggested_rank"] in {1, 2}
    assert "disagreed_with_model" in selected


@pytest.mark.asyncio
async def test_the_next_round_spends_no_call_on_the_carried_over_candidate():
    """The point of asking for three at once."""
    llm = ProbeLLM()  # scripted to answer nothing: any call raises
    pending = [
        {
            "candidate_id": "01CARRY",
            "tactic": "counterevidence",
            "query_focus": "false positive rate",
            "connector_ids": ["semantic_scholar"],
            "target_gap_ids": [],
            "reason": "",
        }
    ]
    output, events = await _run_probe(llm, probe_candidates_pending=pending)
    assert llm.calls == 0
    assert len(output["missions"]) == 1
    assert events["probe_candidate_selected"][0].payload["selected_by"] == "carryover"


@pytest.mark.asyncio
async def test_a_failed_generation_falls_back_once_and_never_to_a_rotation():
    llm = ProbeLLM(RuntimeError("model down"))
    output, events = await _run_probe(llm)
    assert len(output["missions"]) == 1
    mission = output["missions"][0]
    # One deterministic probe built from the gap, not the next entry in a strategy list.
    assert mission["branch_id"].startswith("probe:fallback:")
    assert "external validation" in mission["query"]
    assert output["probe_exhausted_reason"] == "probe_generation_failed"
    assert events["probe_candidate_selected"][0].payload["selected_by"] == "fallback"


@pytest.mark.asyncio
async def test_when_even_the_fallback_was_tried_the_run_stops_instead_of_circling():
    """The v0.16.1 exit stays reachable: no missions means completed_incomplete."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol())
        pipeline = await _pipeline(session, client, ProbeLLM(RuntimeError("down")))
        one = gap()
        first = await pipeline.plan_recovery(_state(row, one))
        spent = [mission_signature_of(mission) for mission in first["missions"]]
        again = await pipeline.plan_recovery(
            _state(row, one, attempted_missions=spent, probe_regenerations=1)
        )
    assert again["missions"] == []
    assert again["probe_exhausted_reason"] == "probe_candidates_exhausted"


def mission_signature_of(payload: dict) -> str:
    from research_platform.schemas import SearchMission

    return mission_signature(SearchMission.model_validate(payload))


@pytest.mark.asyncio
async def test_the_flag_off_keeps_the_existing_rotation():
    """Turning the flag off has to leave the current behaviour exactly as it was."""
    llm = ProbeLLM()  # any call would raise
    output, events = await _run_probe(llm, enabled=False)
    assert llm.calls == 0
    assert events["probe_bundle_generated"] == []
    assert output["missions"]
    assert all(
        mission["branch_id"].startswith("literature:") for mission in output["missions"]
    )


@pytest.mark.asyncio
async def test_probe_context_never_reaches_the_preparation_provider():
    """Gap topics and attempt summaries stay inside the deployment's own boundary."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol())
        pipeline = await _pipeline(session, client, ProbeLLM(BUNDLE))
        external = ProbeLLM(BUNDLE)
        pipeline.preparation_llm = external
        pipeline._telegram_preparation = True
        await pipeline.plan_recovery(_state(row, gap()))
    assert pipeline.llm.calls == 1
    assert external.calls == 0
