"""Which source families a run searches, when nobody has said.

Every run used to start on CORE_FAMILIES whatever was asked. The synthesis picks from a
closed preset catalogue instead -- but only where there is no choice to overwrite, which is
harder to establish than it looks: an explicit "core" answer and an untouched default carry
identical fields, and the scoping gate that would answer the same question runs later.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import acting_principal

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import ResearchPipeline
from research_platform.protocol_synthesis import synthesize_source_selection
from research_platform.repository import Repository
from research_platform.schemas import HitlConfig, ResearchProtocol, SourceFamily
from research_platform.scoping import (
    _FAMILY_PRESETS,
    FAMILY_PRESET_GUIDE,
    apply_families,
    scoping_text,
)


class ScriptedLLM:
    """Answers with whatever it was given, and counts the asking."""

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
        "title": "Source synthesis",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(overrides)
    return ResearchProtocol.model_validate(payload)


@pytest.mark.asyncio
async def test_a_preset_from_the_catalogue_is_applied_with_its_targets():
    llm = ScriptedLLM({"preset": "academic", "reason": "asks what research has found"})
    updated, event = await synthesize_source_selection(llm, protocol())
    assert updated.connectors.included_families == [SourceFamily.ACADEMIC, SourceFamily.WEB]
    assert updated.connectors.selection_source == "synthesis"
    # Rebuilt for the new families rather than filtered down: the protocol validator only
    # ever narrows an existing map, so a widened list would keep stale targets and miss new.
    assert set(updated.family_targets) == set(updated.connectors.included_families)
    assert event["preset"] == "academic"
    assert event["repaired"] is False
    assert event["call_count"] == 1


@pytest.mark.asyncio
async def test_a_key_outside_the_catalogue_changes_nothing():
    """A guess about what the model meant is the unseen decision this layer avoids."""
    llm = ScriptedLLM({"preset": "everything", "reason": "why not"})
    before = protocol()
    updated, event = await synthesize_source_selection(llm, before)
    assert event is None
    assert updated.connectors.included_families == before.connectors.included_families
    assert updated.connectors.selection_source == "default"


@pytest.mark.asyncio
async def test_a_broken_answer_or_an_outage_leaves_the_default_standing():
    for answer in ({"nothing": "useful"}, "not json at all", RuntimeError("provider down")):
        updated, event = await synthesize_source_selection(ScriptedLLM(answer), protocol())
        assert event is None
        assert updated.connectors.selection_source == "default"


@pytest.mark.asyncio
async def test_a_budget_too_narrow_for_the_preset_is_repaired_once():
    """The reachable failure, which is not the one it looks like.

    Switching preset can never raise on its own: every preset covers fewer families than
    the CORE default the protocol already validated against. What does reach the validator
    is a caller who kept the default families but pinned narrow `family_targets` under a
    small `max_sources` -- applying a preset clears those targets, and the rebuilt ones
    can cost more than the budget allows.
    """
    narrow = protocol(
        budget={"max_wall_minutes": 30, "max_sources": 2},
        family_targets={"web": {"minimum_sources": 1}},
    )
    assert narrow.connectors.selection_source == "default"
    llm = ScriptedLLM(
        {"preset": "official", "reason": "three families"},
        {"preset": "academic", "reason": "fewer families"},
    )
    updated, event = await synthesize_source_selection(llm, narrow)
    assert llm.calls == 2
    assert event["repaired"] is True
    assert event["call_count"] == 2
    assert len(updated.connectors.included_families) == 2
    # The repair prompt carries the validator's own words, not a paraphrase.
    assert "max_sources" in llm.prompts[1]


@pytest.mark.asyncio
async def test_a_second_failure_gives_up_instead_of_asking_again():
    narrow = protocol(
        budget={"max_wall_minutes": 30, "max_sources": 2},
        family_targets={"web": {"minimum_sources": 1}},
    )
    llm = ScriptedLLM(
        {"preset": "official", "reason": "three families"},
        {"preset": "core", "reason": "still too many"},
    )
    updated, event = await synthesize_source_selection(llm, narrow)
    assert llm.calls == 2
    assert event is None
    assert updated.connectors.selection_source == "default"
    assert updated.budget.max_sources == 2


def test_an_explicit_core_selection_is_not_a_default():
    """The distinction the provenance field exists for.

    `core` writes exactly CORE_FAMILIES and profile="core" -- bit-identical to a protocol
    nobody touched -- so comparing the fields cannot tell them apart.
    """
    payload = protocol().model_dump(mode="json")
    apply_families(payload, "core", scoping_text("en"))
    chosen = ResearchProtocol.model_validate(payload)
    untouched = protocol()
    assert chosen.connectors.included_families == untouched.connectors.included_families
    assert chosen.connectors.profile == untouched.connectors.profile
    assert chosen.connectors.selection_source == "scoping"
    assert untouched.connectors.selection_source == "default"


def test_a_caller_that_narrowed_the_families_is_recorded_as_one():
    assert protocol(
        connectors={"included_families": ["academic"]}
    ).connectors.selection_source == "caller"
    # An untouched protocol still round-trips as a default, or synthesis would never run.
    once = protocol()
    again = ResearchProtocol.model_validate(once.model_dump(mode="json"))
    assert again.connectors.selection_source == "default"


def test_the_catalogue_the_model_sees_covers_every_preset():
    """The catalogue is the entire output space; an unlisted preset is unreachable."""
    assert set(FAMILY_PRESET_GUIDE) == set(_FAMILY_PRESETS)


def test_hitl_config_default_would_block_synthesis():
    """Telegram leaves planning_questions on, and its answer overwrites the family list."""
    assert HitlConfig().planning_questions is False
    assert protocol().hitl.planning_questions is False


class GateLLM(ScriptedLLM):
    """Always answers `academic`, so any call at all is visible in the result."""

    def __init__(self):
        super().__init__(*[{"preset": "academic", "reason": "r"}] * 5)


async def _pipeline(session, client, *, enabled: bool):
    settings = get_settings().model_copy(
        update={"protocol_source_synthesis_enabled": enabled}
    )
    pipeline = ResearchPipeline(settings, session, client)
    pipeline.llm = GateLLM()
    pipeline.preparation_llm = None
    return pipeline


async def _run_gate(*, enabled: bool, state_extra: dict | None = None, **overrides):
    """Call the gate on a real pipeline and report what it did."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol(**overrides))
        pipeline = await _pipeline(session, client, enabled=enabled)
        state = {"run_id": row.id, "protocol": row.protocol, **(state_extra or {})}
        updated, done = await pipeline._synthesize_sources(
            state, ResearchProtocol.model_validate(row.protocol)
        )
        stored = await repo.get_run(row.id)
        return pipeline.llm.calls, done, updated, stored


@pytest.mark.asyncio
async def test_the_flag_off_leaves_the_run_exactly_as_it_was():
    """The default has to stay bit-identical, or the flag is not a flag."""
    calls, done, updated, stored = await _run_gate(enabled=False)
    assert calls == 0
    assert done is False
    assert updated.connectors.selection_source == "default"
    assert stored.protocol["connectors"]["included_families"] == [
        "web", "academic", "official_legal", "code_data"
    ]


@pytest.mark.asyncio
async def test_the_flag_on_applies_the_preset_and_persists_it():
    calls, done, _, stored = await _run_gate(enabled=True)
    assert calls == 1
    assert done is True
    # Persisted, not only carried in state: the resumed run and the panel read the row.
    assert stored.protocol["connectors"]["selection_source"] == "synthesis"
    assert stored.protocol["connectors"]["included_families"] == ["academic", "web"]


@pytest.mark.asyncio
async def test_scoping_questions_being_on_stops_the_call_before_it_is_made():
    """The scoping gate runs later, in DECOMPOSE, and overwrites the family list.

    Synthesising first would spend a call on a value that is about to be replaced, so the
    guard is checked before the provider is reached rather than after.
    """
    calls, done, _, _ = await _run_gate(
        enabled=True, hitl={"planning_questions": True}
    )
    assert calls == 0
    assert done is False


@pytest.mark.asyncio
async def test_a_selection_somebody_already_made_is_left_alone():
    for connectors in ({"included_families": ["academic"]}, {"profile": "all"}):
        calls, done, _, _ = await _run_gate(enabled=True, connectors=connectors)
        assert calls == 0
        assert done is False


@pytest.mark.asyncio
async def test_a_checkpoint_returning_to_this_stage_does_not_pay_twice():
    calls, done, _, _ = await _run_gate(
        enabled=True, state_extra={"synthesis_done": True}
    )
    assert calls == 0
    assert done is False


@pytest.mark.asyncio
async def test_the_run_records_what_was_chosen_and_why():
    """The plan gate shows the protocol; the event is what explains how it got that way."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol())
        pipeline = await _pipeline(session, client, enabled=True)
        await pipeline._synthesize_sources(
            {"run_id": row.id, "protocol": row.protocol},
            ResearchProtocol.model_validate(row.protocol),
        )
        events = await repo.events_by_types(row.id, {"protocol_synthesis"})
    assert len(events) == 1
    payload = events[0].payload
    assert payload["preset"] == "academic"
    assert payload["families"] == ["academic", "web"]
    assert payload["call_count"] == 1
    assert payload["repaired"] is False
