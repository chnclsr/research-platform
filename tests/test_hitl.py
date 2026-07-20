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
from research_platform.repository import Repository
from research_platform.schemas import HitlConfig, ResearchProtocol, RunStatus, new_id
from research_platform.worker import expire_hitl_interactions


def test_hitl_response_shapes_are_strict():
    assert _validate_hitl_response("plan_review", {"approved": True}) == {"approved": True}
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
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session)
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


@pytest.mark.asyncio
async def test_expired_hitl_interaction_becomes_paused():
    await create_schema()
    protocol = ResearchProtocol(
        title="HITL timeout",
        primary_question="Does unanswered input preserve research state?",
        hitl=HitlConfig(planning_questions=True),
    )
    async with SessionLocal() as session:
        repo = Repository(session)
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
        row = await Repository(session).get_run(row.id)
        assert row.status == RunStatus.PAUSED.value
        assert row.interaction["interaction_id"] == "int-test"


@pytest.mark.asyncio
async def test_source_review_marks_excluded_domain_without_deleting_provenance():
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session)
        run = await repo.create_run(
            ResearchProtocol(
                title="Source review",
                primary_question="Which source domains should be retained?",
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
