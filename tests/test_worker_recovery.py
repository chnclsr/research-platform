from __future__ import annotations

import pytest
from conftest import acting_principal
from fake_redis import FakeRedis

from research_platform import worker
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.worker import _recover_interrupted_jobs


@pytest.mark.asyncio
async def test_worker_startup_recovers_orphans_and_finalizes_pending_cancel():
    await create_schema()
    protocol = ResearchProtocol(
        title="Worker recovery",
        primary_question="Can interrupted jobs resume safely?",
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        running = await repo.create_run(protocol)
        await repo.update_run(
            running.id,
            status=RunStatus.RUNNING.value,
            current_stage="SEARCH",
        )
        cancelling = await repo.create_run(protocol)
        await repo.update_run(
            cancelling.id,
            status=RunStatus.CANCEL_REQUESTED.value,
            current_stage="ACQUIRE",
        )

    redis = FakeRedis()
    await _recover_interrupted_jobs({"redis": redis})

    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        recovered = await repo.get_run(running.id)
        cancelled = await repo.get_run(cancelling.id)
        recovery_events = await repo.events_after(running.id)
        cancel_events = await repo.events_after(cancelling.id)

    assert recovered.status == RunStatus.QUEUED.value
    assert cancelled.status == RunStatus.CANCELLED.value
    assert any(item[1] == running.id for item in redis.enqueued)
    assert any(event.event_type == "worker_recovery" for event in recovery_events)
    assert any(
        event.event_type == "cancelled" and event.payload.get("worker_recovery")
        for event in cancel_events
    )


@pytest.mark.asyncio
async def test_telemetry_failures_do_not_replace_pipeline_error_or_hold_the_slot(monkeypatch):
    await create_schema()
    protocol = ResearchProtocol(
        title="Telemetry fail-open",
        primary_question="Does monitoring preserve the research outcome?",
        budget={"max_wall_minutes": 5},
    )
    async with SessionLocal() as session:
        run = await Repository(session, actor=acting_principal()).create_run(protocol)

    released = []
    finalized = []

    class Gate:
        active = 1

        @staticmethod
        async def acquire(*args, **kwargs):
            return type("Capacity", (), {"allowed": 2, "limited_by": "cpu"})()

        @staticmethod
        def release(run_id: str):
            released.append(run_id)

    class Hub:
        @staticmethod
        async def begin(run_id: str):
            return "segment"

        @staticmethod
        async def end(run_id: str):
            raise RuntimeError("telemetry stop failed")

    class Pipeline:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        async def run(run_id: str):
            raise ValueError("research failed")

    async def fail_finalize(run_id: str, settings):
        finalized.append(run_id)
        raise RuntimeError("telemetry artifact failed")

    monkeypatch.setattr(worker, "GATE", Gate())
    monkeypatch.setattr(worker, "HUB", Hub())
    monkeypatch.setattr(worker, "ResearchPipeline", Pipeline)
    monkeypatch.setattr(worker, "finalize_hardware_telemetry", fail_finalize)

    with pytest.raises(ValueError, match="research failed"):
        await worker.execute_research_run({"http": None}, run.id)

    assert finalized == [run.id]
    assert released == [run.id]
