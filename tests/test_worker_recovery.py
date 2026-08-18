from __future__ import annotations

import pytest

from research_platform.db import SessionLocal, create_schema
from conftest import acting_principal
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.worker import _recover_interrupted_jobs


class FakeRedis:
    def __init__(self):
        self.deleted: list[tuple[str, ...]] = []
        self.removed: list[tuple[str, str]] = []
        self.enqueued: list[tuple[str, str, str | None]] = []

    async def zrem(self, queue: str, job_id: str):
        self.removed.append((queue, job_id))

    async def delete(self, *keys: str):
        self.deleted.append(keys)

    async def enqueue_job(self, function: str, run_id: str, _job_id: str | None = None):
        self.enqueued.append((function, run_id, _job_id))
        return object()


@pytest.mark.asyncio
async def test_worker_startup_recovers_orphans_and_finalizes_pending_cancel():
    await create_schema()
    protocol = ResearchProtocol(
        title="Worker recovery",
        primary_question="Can interrupted jobs resume safely?",
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
