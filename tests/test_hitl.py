from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from fastapi import HTTPException

from research_platform.api import _validate_hitl_response
from research_platform.config import get_settings
from research_platform.db import SessionLocal, SourceRow, create_schema
from research_platform.gateway_client import ResearchGatewayClient
from research_platform.pipeline import PipelineHalted, ResearchPipeline
from conftest import acting_principal
from research_platform.repository import Repository
from research_platform.schemas import HitlConfig, ResearchProtocol, RunStatus, new_id
from research_platform.worker import expire_hitl_interactions


def test_hitl_response_shapes_are_strict():
    assert _validate_hitl_response("plan_review", {"approved": True}) == {"approved": True}
    # Approving the plan is the one place the duration may be revised, so it carries the
    # same bounds as ResearchBudget rather than a looser ad-hoc check.
    assert _validate_hitl_response(
        "plan_review", {"approved": True, "max_wall_minutes": 90}
    ) == {"approved": True, "max_wall_minutes": 90}
    for bad in (0, 1441, "45", True):
        with pytest.raises(HTTPException) as rejected:
            _validate_hitl_response("plan_review", {"approved": True, "max_wall_minutes": bad})
        assert rejected.value.status_code == 400
    assert _validate_hitl_response(
        "source_review",
        {"included_domains": [" SEC.GOV "], "excluded_domains": []},
    ) == {"included_domains": ["sec.gov"], "excluded_domains": []}
    with pytest.raises(HTTPException) as error:
        _validate_hitl_response("planning_questions", {"answers": []})
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_pipeline_checkpoint_waits_and_reuses_response():
    await create_schema()
    protocol = ResearchProtocol(
        title="HITL plan review",
        primary_question="How should evidence review be planned?",
        hitl=HitlConfig(plan_review=True),
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        pipeline = ResearchPipeline(get_settings(), session, client)
        state = {"run_id": row.id, "protocol": row.protocol, "queries": ["evidence"]}
        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline._maybe_hitl(
                state, "plan_review", {"plan": {"queries": ["evidence"]}}, "BUILD_QUERY_BRANCHES"
            )
        waiting = await repo.get_run(row.id)
        assert waiting.status == RunStatus.AWAITING_INPUT.value
        assert waiting.interaction["type"] == "plan_review"
        await repo.update_run(
            row.id,
            status=RunStatus.QUEUED.value,
            interaction=None,
            hitl_history=[
                {
                    "type": "plan_review",
                    "response": {"approved": False, "modifications": "Add standards"},
                }
            ],
        )
        response = await pipeline._maybe_hitl(
            state, "plan_review", {"plan": {}}, "BUILD_QUERY_BRANCHES"
        )
        assert response == {"approved": False, "modifications": "Add standards"}


async def _plan_run(repo, **protocol_overrides):
    payload = {
        "title": "Plan gate",
        "primary_question": "Which methods detect pulmonary nodules on CT?",
        "budget": {"max_wall_minutes": 30},
    }
    payload.update(protocol_overrides)
    return await repo.create_run(ResearchProtocol(**payload))


def _plan_state(row) -> dict:
    return {
        "run_id": row.id,
        "protocol": row.protocol,
        "sub_questions": ["Which datasets are used?"],
        "missions": [{"branch_id": "query:0", "query": "nodule detection"}],
    }


@pytest.mark.asyncio
async def test_plan_gate_is_on_by_default_and_stops_the_run_before_searching():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo)
        assert ResearchProtocol.model_validate(row.protocol).hitl.plan_review is True
        pipeline = ResearchPipeline(get_settings(), session, client)
        protocol = ResearchProtocol.model_validate(row.protocol)
        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline._plan_gate(_plan_state(row), {}, protocol)
        waiting = await repo.get_run(row.id)
        assert waiting.status == RunStatus.AWAITING_INPUT.value
        assert waiting.interaction["type"] == "plan_review"
        plan = waiting.interaction["data"]["plan"]
        assert plan["questions"]["primary"].startswith("Which methods")
        assert plan["budget"]["max_wall_minutes"] == 30
        events = {event.event_type for event in await repo.events_after(row.id)}
        assert "research_plan" in events


@pytest.mark.asyncio
async def test_caller_can_opt_out_of_the_plan_gate_and_the_choice_is_recorded():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(plan_review=False))
        pipeline = ResearchPipeline(get_settings(), session, client)
        protocol = ResearchProtocol.model_validate(row.protocol)
        output = await pipeline._plan_gate(_plan_state(row), {"queries": ["x"]}, protocol)
        assert output == {"queries": ["x"]}
        assert (await repo.get_run(row.id)).status != RunStatus.AWAITING_INPUT.value
        events = {event.event_type for event in await repo.events_after(row.id)}
        assert "plan_skipped" in events


@pytest.mark.asyncio
async def test_rejecting_a_plan_asks_again_and_carries_the_feedback_forward():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        protocol = ResearchProtocol.model_validate(row.protocol)
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "plan_review",
                    "response": {"approved": False, "modifications": "Add regulatory sources"},
                }
            ],
        )
        # A rejection must produce a fresh question, not replay the rejected answer the
        # way the single-shot checkpoints do.
        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline._plan_gate(_plan_state(row), {}, protocol)
        waiting = await repo.get_run(row.id)
        plan = waiting.interaction["data"]["plan"]
        assert plan["feedback"] == ["Add regulatory sources"]
        assert plan["revision"] == 1
        checkpoint = await repo.latest_checkpoint(row.id)
        # Rewound to DECOMPOSE so the sub-questions are rebuilt with the feedback.
        assert checkpoint.stage == "DECOMPOSE"
        assert checkpoint.state["plan_feedback"] == ["Add regulatory sources"]


class StubDecomposeLLM:
    async def complete_json(self, system: str, user: str):
        return {"sub_questions": ["Which datasets are used?"], "concepts": ["nodules"]}

    def drain_metrics(self):
        return []


@pytest.mark.asyncio
async def test_feedback_reaches_decomposition_on_the_very_next_pass():
    """Read from the answer history, not from the checkpoint.

    The checkpoint is written before the rejection exists, so taking the feedback from
    state applied it one round late -- the rebuilt plan repeated the rejected one.
    """
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = StubDecomposeLLM()
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "plan_review",
                    "response": {"approved": False, "modifications": "Cover FDA clearances"},
                }
            ],
        )
        output = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        )
        assert "Cover FDA clearances" in output["sub_questions"]
        assert output["plan_feedback"] == ["Cover FDA clearances"]


class ScopingLLM:
    """Answers the scoping call with options, and decomposition with fixed sub-questions."""

    def __init__(self, choices=None):
        self.prompts = []
        self.choices = choices if choices is not None else {
            "questions": [
                {"question": "Hangi yön önemli?", "options": ["Klinik", "Maliyet"]},
                {"question": "Hangi kaynaklar?", "options": ["Denemeler", "Kayıtlar"]},
            ]
        }

    async def complete_json(self, system: str, user: str):
        self.prompts.append(user)
        if "scoping a research run" in system:
            return self.choices
        return {"sub_questions": ["Which datasets are used?"], "concepts": ["nodules"]}

    def drain_metrics(self):
        return []


@pytest.mark.asyncio
async def test_scoping_questions_carry_options_and_stop_the_run_before_planning():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(planning_questions=True))
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = ScopingLLM()
        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline.decompose_question(
                {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
            )
        waiting = await repo.get_run(row.id)
        assert waiting.interaction["type"] == "planning_questions"
        questions = waiting.interaction["data"]["questions"]
        # The two binding questions lead and carry protocol values beside their wording;
        # the model's questions follow and carry none, which is what keeps them steering.
        assert [item.get("id") for item in questions] == [
            "date_scope",
            "source_families",
            None,
            None,
        ]
        assert questions[1]["values"] == ["academic", "official", "code_data", "core"]
        assert questions[2]["options"] == ["Klinik", "Maliyet"]
        assert "values" not in questions[2]


def test_repeated_options_are_not_a_choice():
    """Measured on the live model: one question came back with the same option five times,
    and a second question repeated the first one's option set."""
    from research_platform.llm import _choice_questions

    questions = _choice_questions({"questions": [
        {"question": "Which sources count?", "options": ["Trials"] * 5},
        {"question": "Which angle?", "options": ["Clinical", "Cost", "clinical"]},
        {"question": "Restated angle?", "options": ["Cost", "Clinical"]},
    ]})
    # The all-identical question is gone, the duplicate option is folded away, and the
    # question that only restates the previous option set is dropped.
    assert [item["question"] for item in questions] == ["Which angle?"]
    assert questions[0]["options"] == ["Clinical", "Cost"]


@pytest.mark.asyncio
async def test_a_model_that_returns_no_usable_options_still_asks_the_question():
    """Losing the tailored wording is not a reason to skip the checkpoint."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(planning_questions=True))
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = ScopingLLM(choices={"questions": "not a list"})
        with pytest.raises(PipelineHalted, match="awaiting_input"):
            await pipeline.decompose_question(
                {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
            )
        questions = (await repo.get_run(row.id)).interaction["data"]["questions"]
        # Two binding questions plus the first two plain fallbacks: the checkpoint keeps
        # asking, and the part that can actually change the protocol is unaffected by the
        # model having failed.
        assert [item.get("id") for item in questions] == [
            "date_scope",
            "source_families",
            None,
            None,
        ]
        assert all("options" not in item for item in questions[2:])


@pytest.mark.asyncio
async def test_scoping_answers_steer_the_research_instead_of_becoming_sub_questions():
    """A tapped option is a preference, not something to go and find out.

    Appending it verbatim, as an earlier version did, turned "Clinical" into its own
    search branch.
    """
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(planning_questions=True))
        pipeline = ResearchPipeline(get_settings(), session, client)
        llm = ScopingLLM()
        pipeline.llm = llm
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "planning_questions",
                    "response": {"answers": [
                        {"question": "Hangi yön önemli?", "answer": "Klinik"},
                    ]},
                }
            ],
        )
        output = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        )
    assert output["sub_questions"] == ["Which datasets are used?"]
    assert "Klinik" not in output["sub_questions"]
    assert output["planning_answers"] == ["Hangi yön önemli? -> Klinik"]
    # It reached the model as guidance instead.
    assert any("Klinik" in prompt for prompt in llm.prompts)


@pytest.mark.asyncio
async def test_a_bound_answer_reaches_the_protocol_the_next_stage_reads():
    """The complaint this closes: an option that looked like a setting and set nothing."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(planning_questions=True))
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = ScopingLLM()
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "planning_questions",
                    "response": {"answers": [
                        {"question": "Hangi kaynaklar?", "answer": "Resmî",
                         "id": "source_families", "value": "official"},
                        {"question": "Hangi yön önemli?", "answer": "Klinik",
                         "id": "", "value": ""},
                    ]},
                }
            ],
        )
        output = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        )
        families = output["protocol"]["connectors"]["included_families"]
        assert families == ["official_legal", "web", "academic"]
        assert [item["id"] for item in output["applied_settings"]] == ["source_families"]
        # Persisted, not only carried in state: the resumed run and the panel both read
        # the protocol from the row.
        stored = await repo.get_run(row.id)
        assert stored.protocol["connectors"]["included_families"] == families
        # The answer that bound to nothing still reaches the prompts as guidance.
        assert "Hangi yön önemli? -> Klinik" in output["planning_answers"]


@pytest.mark.asyncio
async def test_the_run_is_cancelled_once_the_revision_limit_is_reached():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        protocol = ResearchProtocol.model_validate(row.protocol)
        limit = get_settings().plan_max_revisions
        await repo.update_run(
            row.id,
            hitl_history=[
                {"type": "plan_review", "response": {"approved": False, "modifications": f"no {i}"}}
                for i in range(limit)
            ],
        )
        with pytest.raises(PipelineHalted, match="plan_rejected"):
            await pipeline._plan_gate(_plan_state(row), {}, protocol)
        cancelled = await repo.get_run(row.id)
        assert cancelled.status == RunStatus.CANCELLED.value
        events = {event.event_type for event in await repo.events_after(row.id)}
        assert "plan_rejection_limit" in events


@pytest.mark.asyncio
async def test_approving_the_plan_can_change_the_duration_and_persists_it():
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo)
        pipeline = ResearchPipeline(get_settings(), session, client)
        protocol = ResearchProtocol.model_validate(row.protocol)
        await repo.update_run(
            row.id,
            hitl_history=[
                {"type": "plan_review", "response": {"approved": True, "max_wall_minutes": 90}}
            ],
        )
        state = _plan_state(row)
        output = await pipeline._plan_gate(state, {"queries": ["x"]}, protocol)
        assert output == {"queries": ["x"]}
        # Persisted, because a resumed run reloads its protocol from the row.
        approved = await repo.get_run(row.id)
        assert approved.protocol["budget"]["max_wall_minutes"] == 90
        assert state["protocol"]["budget"]["max_wall_minutes"] == 90
        events = {event.event_type for event in await repo.events_after(row.id)}
        assert {"research_plan_approved", "plan_duration_changed"} <= events


@pytest.mark.asyncio
async def test_expired_hitl_interaction_becomes_paused():
    await create_schema()
    protocol = ResearchProtocol(
        title="HITL timeout",
        primary_question="Does unanswered input preserve research state?",
        hitl=HitlConfig(planning_questions=True),
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(protocol)
        await repo.update_run(
            row.id,
            status=RunStatus.AWAITING_INPUT.value,
            interaction={
                "interaction_id": "int-test",
                "type": "planning_questions",
                "data": {"questions": []},
                "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            },
        )
    await expire_hitl_interactions({})
    async with SessionLocal() as session:
        row = await Repository(session, actor=acting_principal()).get_run(row.id)
        assert row.status == RunStatus.PAUSED.value
        assert row.interaction["interaction_id"] == "int-test"


@pytest.mark.asyncio
async def test_source_review_marks_excluded_domain_without_deleting_provenance():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(
            ResearchProtocol(
                title="Source review",
                primary_question="Which source domains should be retained?",
                budget={"max_wall_minutes": 30},
            )
        )
        source = SourceRow(
            id=new_id(),
            run_id=run.id,
            dedupe_key="domain-review",
            family="web",
            connector_id="fixture",
            title="Excluded fixture",
            url="https://noise.example/article",
            persistent_id=None,
            metadata_json={},
        )
        session.add(source)
        await session.commit()
        await repo.apply_source_domain_review(run.id, set(), {"noise.example"})
        persisted = (await repo.list_sources(run.id))[0]
        assert persisted.metadata_json["excluded_by_hitl"] is True
        assert persisted.metadata_json["hitl_source_decision"] == "exclude"


@pytest.mark.asyncio
@respx.mock
async def test_gateway_posts_hitl_response():
    route = respx.post("http://research.test/v1/research-runs/RUN1/respond").mock(
        return_value=httpx.Response(200, json={"id": "RUN1", "status": "queued"})
    )
    client = ResearchGatewayClient("http://research.test", "token")
    result = await client.respond("RUN1", "INT1", {"approved": True})
    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer token"
    assert result["status"] == "queued"


@pytest.mark.asyncio
async def test_plan_feedback_naming_a_window_moves_the_protocol():
    """The complaint this closes: "make it the last year" left the dates where they were.

    A rejected plan rewinds to DECOMPOSE, and the rejection reached the prompts only. The
    window the user asked to change was then re-derived from the unchanged scoping answer
    and shown back to them.
    """
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(
            repo, hitl=HitlConfig(planning_questions=True, plan_review=True)
        )
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = ScopingLLM()
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "planning_questions",
                    "response": {"answers": [
                        {"question": "Hangi dönem?", "answer": "Son 3 yıl",
                         "id": "date_scope", "value": "last_3y"},
                    ]},
                },
                {
                    "type": "plan_review",
                    "response": {"approved": False,
                                 "modifications": "Tarih aralığını son 1 yıl yap"},
                },
            ],
        )
        output = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        )
        scope = output["protocol"]["scope"]
        start = datetime.fromisoformat(scope["start_date"])
        end = datetime.fromisoformat(scope["end_date"])
        assert 360 <= (end - start).days <= 370
        # The plan says the dates moved, and that the user is why.
        dates = [item for item in output["applied_settings"] if item["id"] == "date_scope"]
        assert dates and dates[-1]["source"] == "feedback"
        stored = await repo.get_run(row.id)
        assert stored.protocol["scope"]["start_date"] == scope["start_date"]


@pytest.mark.asyncio
async def test_scoping_is_not_re_derived_over_a_later_change():
    """Re-reading the same answers on every pass silently reverted anything applied since."""
    await create_schema()
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await _plan_run(repo, hitl=HitlConfig(planning_questions=True))
        pipeline = ResearchPipeline(get_settings(), session, client)
        pipeline.llm = ScopingLLM()
        await repo.update_run(
            row.id,
            hitl_history=[
                {
                    "type": "planning_questions",
                    "response": {"answers": [
                        {"question": "Hangi kaynaklar?", "answer": "Resmî",
                         "id": "source_families", "value": "official"},
                    ]},
                }
            ],
        )
        first = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": row.protocol, "round_number": 0}
        )
        # Something changed the protocol after scoping settled -- a later gate, or the
        # feedback binder above.
        moved = {**first["protocol"]}
        moved["connectors"] = {**moved["connectors"], "included_families": ["web"]}
        await repo.update_run(row.id, protocol=moved)
        second = await pipeline.decompose_question(
            {"run_id": row.id, "protocol": moved, "round_number": 1}
        )
        assert second["protocol"]["connectors"]["included_families"] == ["web"]
        # The report still names what scoping applied, read back rather than re-derived.
        assert [item["id"] for item in second["applied_settings"]] == ["source_families"]
