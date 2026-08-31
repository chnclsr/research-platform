"""How many external requests one planning round costs.

The preparation stages talk to an outside provider on a quota, and the graph re-enters at
DECOMPOSE after every checkpoint answer -- so the same question used to be decomposed and
re-queried on every pass, including the approval pass whose inputs nobody had touched.
These tests pin the two savings that removed: work is reused while its inputs are unchanged,
and calls that read the same thing are asked together.
"""

from __future__ import annotations

import httpx
import pytest
from conftest import acting_principal

from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.pipeline import PipelineHalted, ResearchPipeline
from research_platform.repository import Repository
from research_platform.research_plan import plan_display_and_strategy
from research_platform.schemas import HitlConfig, ResearchProtocol


class CountingLLM:
    """Answers every preparation prompt, and remembers how often it was asked."""

    def __init__(self, **fields):
        self.calls = 0
        self.systems: list[str] = []
        self.fields = fields

    async def complete_json(self, system: str, user: str):
        self.calls += 1
        self.systems.append(system)
        return {
            "sub_questions": ["Which datasets are used?"],
            "concepts": ["nodules"],
            "search_queries": ["pulmonary nodule detection"],
            "items": ["Hangi veri setleri kullanılıyor?"],
            "strategy": "Önce akademik kaynaklar taranacak.",
            **self.fields,
        }

    def drain_metrics(self):
        return []


async def _run(repo, **overrides):
    payload = {
        "title": "Budget",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30},
        "hitl": HitlConfig(planning_questions=False, plan_review=False),
    }
    payload.update(overrides)
    return await repo.create_run(ResearchProtocol(**payload))


@pytest.mark.asyncio
async def test_an_unchanged_pass_reuses_the_decomposition_and_the_queries():
    """The approval pass reads exactly what the pass before it read."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = CountingLLM()

        state = {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        first = await pipeline.decompose_question(state)
        first = {**state, **first, **await pipeline.build_query_branches({**state, **first})}
        assert pipeline.llm.calls == 2

        # What a resume does: the checkpointed state comes back and the graph re-enters.
        again = await pipeline.decompose_question(first)
        await pipeline.build_query_branches({**first, **again})
        assert pipeline.llm.calls == 2
        assert again["sub_questions"] == first["sub_questions"]


@pytest.mark.asyncio
async def test_a_rejection_still_rebuilds_the_plan_it_was_rejected_for():
    """Reuse must not survive the thing it depends on changing."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = CountingLLM()

        state = {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        first = await pipeline.decompose_question(state)
        first = {**state, **first, **await pipeline.build_query_branches({**state, **first})}
        assert pipeline.llm.calls == 2

        await repo.update_run(
            row.id,
            hitl_history=[{
                "type": "plan_review",
                "response": {"approved": False, "modifications": "Cover FDA clearances"},
            }],
        )
        second = await pipeline.decompose_question(first)
        await pipeline.build_query_branches({**first, **second})
        assert pipeline.llm.calls == 4
        assert "Cover FDA clearances" in second["sub_questions"]


@pytest.mark.asyncio
async def test_a_failed_query_generation_is_not_remembered_as_an_answer():
    """An empty list is a failure, and the next pass deserves a fresh attempt."""

    class FailingQueriesLLM(CountingLLM):
        async def complete_json(self, system: str, user: str):
            if "search_queries" in system:
                self.calls += 1
                raise RuntimeError("provider down")
            return await super().complete_json(system, user)

    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = FailingQueriesLLM()

        state = {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        decomposed = await pipeline.decompose_question(state)
        state = {**state, **decomposed}
        first = await pipeline.build_query_branches(state)
        assert pipeline.llm.calls == 2
        await pipeline.build_query_branches({**state, **first})
        assert pipeline.llm.calls == 3


@pytest.mark.asyncio
async def test_a_translated_request_is_named_without_a_second_request():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(repo, primary_question="Akciğer BT'sinde nodül tespiti nasıl yapılır?")
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = CountingLLM(
            question="How are nodules detected on lung CT?",
            source_language="tr",
            label="lung_ct_nodules",
        )

        output = await pipeline.validate_protocol({"run_id": row.id, "protocol": row.protocol})

        assert pipeline.llm.calls == 1
        assert output["protocol"]["label"].startswith("lung_ct_nodules")


@pytest.mark.asyncio
async def test_a_translation_without_a_label_still_asks_for_one():
    """The merge is an optimisation, not a new requirement on the model."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(repo, primary_question="Akciğer BT'sinde nodül tespiti nasıl yapılır?")
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = CountingLLM(
            question="How are nodules detected on lung CT?",
            source_language="tr",
            label="",
        )

        output = await pipeline.validate_protocol({"run_id": row.id, "protocol": row.protocol})

        assert pipeline.llm.calls == 2
        assert output["protocol"]["label"]


@pytest.mark.asyncio
async def test_the_approval_screen_costs_one_request_for_both_of_its_halves():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _run(
            repo,
            primary_question="Akciğer BT'sinde nodül tespiti nasıl yapılır?",
            original_question="Akciğer BT'sinde nodül tespiti nasıl yapılır?",
            original_language="tr",
            hitl=HitlConfig(planning_questions=False, plan_review=True),
        )
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = CountingLLM()
        protocol = ResearchProtocol.model_validate(row.protocol)
        state = {
            "run_id": row.id,
            "protocol": row.protocol,
            "sub_questions": ["Which datasets are used?"],
            "missions": [{"branch_id": "query:0", "query": "nodule detection"}],
        }

        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline._plan_gate(state, {}, protocol)

        assert pipeline.llm.calls == 1
        plan = (await repo.get_run(row.id)).interaction["data"]["plan"]
        assert plan["questions"]["sub_questions_display"] == [
            "Hangi veri setleri kullanılıyor?"
        ]
        assert plan["strategy_note"] == "Önce akademik kaynaklar taranacak."


@pytest.mark.asyncio
async def test_each_half_of_the_approval_screen_fails_on_its_own():
    class BrokenLLM:
        async def complete_json(self, system: str, user: str):
            raise RuntimeError("provider down")

        def drain_metrics(self):
            return []

    class HalfLLM:
        """A model that answers the note but miscounts the translated list."""

        async def complete_json(self, system: str, user: str):
            return {"items": ["yalnız bir madde"], "strategy": "Kısa not."}

        def drain_metrics(self):
            return []

    plan = {"questions": {}, "budget": {}}
    items = ["Which datasets are used?", "Which cohorts are covered?"]

    assert await plan_display_and_strategy(BrokenLLM(), plan, items, "tr") == ([], "")
    # A list that cannot be lined up one-to-one would put the wrong text beside the wrong
    # question, so it is dropped -- but the note it came with is still worth showing.
    assert await plan_display_and_strategy(HalfLLM(), plan, items, "tr") == ([], "Kısa not.")
