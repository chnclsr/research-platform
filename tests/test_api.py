from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from research_platform.api import _reconcile_interrupted_runs, app
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus


def test_create_and_read_run():
    with TestClient(app) as client:
        response = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "API acceptance test",
                "primary_question": "Can the API create a validated research run?",
                "connectors": {"profile": "core"},
            }
        })
        assert response.status_code == 200, response.text
        created = response.json()
        assert created["status"] == "queued"
        fetched = client.get(f"/v1/research-runs/{created['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["protocol"]["title"] == "API acceptance test"
        listed = client.get("/v1/research-runs?limit=10")
        assert listed.status_code == 200
        assert any(run["id"] == created["id"] for run in listed.json())


def test_api_rejects_bad_protocol():
    with TestClient(app) as client:
        response = client.post("/v1/research-runs", json={
            "protocol": {"title": "x", "primary_question": "short"}
        })
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_startup_reconciles_queued_and_cancel_requested_runs():
    await create_schema()
    protocol = ResearchProtocol(
        title="Queue reconciliation",
        primary_question="Can interrupted queue records be recovered safely?",
    )
    async with SessionLocal() as session:
        repo = Repository(session)
        queued = await repo.create_run(protocol)
        cancelled = await repo.create_run(protocol)
        await repo.update_run(cancelled.id, status=RunStatus.CANCEL_REQUESTED.value)

    class FakeRedis:
        def __init__(self):
            self.enqueued = []
            self.removed = []

        async def enqueue_job(self, function, run_id, **kwargs):
            self.enqueued.append((function, run_id, kwargs))
            return object()

        async def zrem(self, key, value):
            self.removed.append(("zrem", key, value))

        async def delete(self, *keys):
            self.removed.append(("delete", *keys))

    redis = FakeRedis()
    fake_app = SimpleNamespace(state=SimpleNamespace(redis=redis))
    await _reconcile_interrupted_runs(fake_app)

    async with SessionLocal() as session:
        repo = Repository(session)
        cancelled_row = await repo.get_run(cancelled.id)
        assert cancelled_row.status == RunStatus.CANCELLED.value
    assert any(run_id == queued.id for _, run_id, _ in redis.enqueued)
    assert any(
        item[0] == "zrem" and item[2] == f"run:{cancelled.id}"
        for item in redis.removed
    )
