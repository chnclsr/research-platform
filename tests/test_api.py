import inspect
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import api_headers, ensure_test_user, acting_principal
from fake_redis import FakeRedis
from research_platform.api import _reconcile_interrupted_runs, app
from research_platform.db import SessionLocal, create_schema
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus


def test_every_entry_surface_demands_a_duration():
    """The schema stops the API; the other surfaces have to ask before they get there."""
    from research_platform.mcp_server import start_research
    from research_platform.telegram_bot import has_explicit_duration

    parameter = inspect.signature(start_research).parameters["max_wall_minutes"]
    assert parameter.default is inspect.Parameter.empty

    assert has_explicit_duration(["--minutes", "30", "lung", "CT"]) is True
    assert has_explicit_duration(["45", "lung", "CT"]) is True
    # No duration in the message: the bot must offer the choice instead of assuming one.
    assert has_explicit_duration(["lung", "CT", "--hitl"]) is False


@pytest.mark.asyncio
async def test_a_run_cannot_be_created_without_stating_its_duration():
    """A silent 45-minute default was a decision nobody saw being made."""
    await ensure_test_user()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        response = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "Durationless request",
                "primary_question": "Can a run start without stating how long it may collect?",
            }
        })
    assert response.status_code == 422, response.text
    locations = [".".join(str(part) for part in error["loc"]) for error in response.json()["detail"]]
    assert any("max_wall_minutes" in item or item.endswith("budget") for item in locations)


@pytest.mark.asyncio
async def test_create_and_read_run():
    await ensure_test_user()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        response = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "API acceptance test",
                "primary_question": "Can the API create a validated research run?",
                "connectors": {"profile": "core"},
                "budget": {"max_wall_minutes": 30},
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


@pytest.mark.asyncio
async def test_run_invocation_source_is_persisted_without_entering_the_protocol():
    await ensure_test_user()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        response = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "Telegram preparation provenance",
                "primary_question": "Which model should prepare this Telegram run?",
                "budget": {"max_wall_minutes": 30},
            },
            "invocation_source": "telegram",
        })
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        row = await Repository(session, actor=acting_principal()).get_run(response.json()["id"])
    assert row.state == {"invocation_source": "telegram"}
    assert "invocation_source" not in row.protocol


@pytest.mark.asyncio
async def test_api_rejects_bad_protocol():
    await ensure_test_user()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        response = client.post("/v1/research-runs", json={
            "protocol": {"title": "x", "primary_question": "short"}
        })
        assert response.status_code == 422


def test_api_rejects_request_without_credential():
    """The TESTING flag used to disable auth entirely; it must not do so any more."""
    with TestClient(app) as client:
        response = client.get("/v1/research-runs")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_startup_reconciles_queued_and_cancel_requested_runs():
    await create_schema()
    protocol = ResearchProtocol(
        title="Queue reconciliation",
        primary_question="Can interrupted queue records be recovered safely?",
        budget={"max_wall_minutes": 30},
    )
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        queued = await repo.create_run(protocol)
        cancelled = await repo.create_run(protocol)
        await repo.update_run(cancelled.id, status=RunStatus.CANCEL_REQUESTED.value)

    redis = FakeRedis()
    fake_app = SimpleNamespace(state=SimpleNamespace(redis=redis))
    await _reconcile_interrupted_runs(fake_app)

    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        cancelled_row = await repo.get_run(cancelled.id)
        assert cancelled_row.status == RunStatus.CANCELLED.value
    assert any(run_id == queued.id for _, run_id, _ in redis.enqueued)
    assert any(job_id == f"run:{cancelled.id}" for _, job_id in redis.removed)
