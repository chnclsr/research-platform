from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from arq.constants import default_queue_name, in_progress_key_prefix, result_key_prefix

from sqlalchemy import delete

from conftest import acting_principal
from fake_redis import FakeRedis
from research_platform.auth import Principal
from research_platform.db import ResearchRunRow, SessionLocal, create_schema
from research_platform.queueing import (
    JOB_EXPIRY,
    NORMAL,
    URGENT,
    enqueue_run,
    job_id_for,
    normalize_priority,
    rescore_run,
    score_kwargs,
)
from research_platform.repository import Repository
from research_platform.scheduler import preempt_for, resume_preempted
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.worker import resume_preempted_runs


async def clear_runs() -> None:
    """The scheduler asks whole-queue questions, so leftovers from other tests answer them.

    The suite shares one SQLite file for the whole session by design; these cases are the
    ones that care what else is in the table.
    """
    await create_schema()
    async with SessionLocal() as session:
        await session.execute(delete(ResearchRunRow))
        await session.commit()


def protocol(question: str = "Which methods detect pulmonary nodules on CT?") -> ResearchProtocol:
    return ResearchProtocol(
        title="Priority queue",
        primary_question=question,
        budget={"max_wall_minutes": 30},
    )


def test_the_urgent_band_sits_below_every_normal_job():
    """A fixed offset would not do: a normal job that has waited an hour would still
    score lower than an urgent one enqueued now."""
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    urgent = score_kwargs(URGENT, now=now)["_defer_until"]
    stale_normal = score_kwargs(NORMAL, now=now - timedelta(days=365))["_defer_until"]
    assert urgent < stale_normal


def test_the_band_keeps_first_come_first_served_inside_itself():
    now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    first = score_kwargs(URGENT, now=now)["_defer_until"]
    second = score_kwargs(URGENT, now=now + timedelta(minutes=5))["_defer_until"]
    assert first < second


def test_every_job_states_its_expiry():
    """arq derives the job key's TTL from the score when none is given, which goes
    negative for a back-dated score and makes Redis reject the write outright."""
    for priority in (NORMAL, URGENT):
        assert score_kwargs(priority)["_expires"] == JOB_EXPIRY


def test_an_unknown_priority_does_not_open_a_fast_lane():
    assert normalize_priority("URGENT") == URGENT
    assert normalize_priority("critical") == NORMAL
    assert normalize_priority(None) == NORMAL


@pytest.mark.asyncio
async def test_the_worker_would_pull_the_urgent_run_first():
    redis = FakeRedis()
    await enqueue_run(redis, "NORMAL1", NORMAL)
    await enqueue_run(redis, "NORMAL2", NORMAL)
    await enqueue_run(redis, "URGENT1", URGENT)
    assert redis.order()[0] == job_id_for("URGENT1")
    # The normal band keeps its own arrival order behind it.
    assert redis.order()[1:] == [job_id_for("NORMAL1"), job_id_for("NORMAL2")]


@pytest.mark.asyncio
async def test_a_finished_run_can_be_queued_again_within_keep_result():
    """The resume and HITL paths used random job ids precisely because of this key.

    Random ids cost the run its queue position in the panel and made cancellation unable
    to find the job, so the stale key is cleared instead.
    """
    redis = FakeRedis()
    redis.keys.add(f"{result_key_prefix}{job_id_for('RUN1')}")
    assert await enqueue_run(redis, "RUN1", NORMAL) is not None
    assert job_id_for("RUN1") in redis.queue


@pytest.mark.asyncio
async def test_a_running_job_is_left_alone():
    redis = FakeRedis()
    redis.keys.add(f"{in_progress_key_prefix}{job_id_for('RUN1')}")
    assert await enqueue_run(redis, "RUN1", NORMAL) is None
    assert redis.deleted == []


@pytest.mark.asyncio
async def test_rescoring_moves_a_waiting_job_and_ignores_everything_else():
    redis = FakeRedis()
    await enqueue_run(redis, "RUN1", NORMAL)
    await enqueue_run(redis, "RUN2", NORMAL)
    assert await rescore_run(redis, "RUN1", URGENT) is True
    assert redis.order()[0] == job_id_for("RUN1")
    # Nothing queued under that id: the sorted set must not gain a member.
    assert await rescore_run(redis, "GONE", URGENT) is False
    assert job_id_for("GONE") not in redis.queue


@pytest.mark.asyncio
async def test_an_urgent_run_pauses_the_running_normal_one():
    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        victim = await repo.create_run(protocol())
        await repo.update_run(
            victim.id, status=RunStatus.RUNNING.value, current_stage="ACQUIRE"
        )
        urgent = await repo.create_run(protocol("Urgent question about CT triage?"),
                                       priority=URGENT)

        paused = await preempt_for(session, urgent.id, URGENT)
        assert paused == victim.id

        row = await repo.get_run(victim.id)
        assert row.status == RunStatus.PAUSED.value
        # The marker is what tells auto-resume this pause was not the owner's doing.
        assert row.preempted_at is not None
        events = await repo.events_after(victim.id)
        assert any(event.event_type == "preempted" for event in events)


@pytest.mark.asyncio
async def test_urgent_runs_do_not_preempt_each_other():
    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        running = await repo.create_run(protocol(), priority=URGENT)
        await repo.update_run(running.id, status=RunStatus.RUNNING.value)
        newcomer = await repo.create_run(protocol("Another urgent one?"), priority=URGENT)

        assert await preempt_for(session, newcomer.id, URGENT) is None
        assert (await repo.get_run(running.id)).status == RunStatus.RUNNING.value


@pytest.mark.asyncio
async def test_a_normal_run_preempts_nothing():
    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        running = await repo.create_run(protocol())
        await repo.update_run(running.id, status=RunStatus.RUNNING.value)
        newcomer = await repo.create_run(protocol("A second ordinary question?"))

        assert await preempt_for(session, newcomer.id, NORMAL) is None
        assert (await repo.get_run(running.id)).status == RunStatus.RUNNING.value


@pytest.mark.asyncio
async def test_a_preempted_run_is_given_the_worker_back():
    await clear_runs()
    redis = FakeRedis()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        held = await repo.create_run(protocol())
        await repo.update_run(
            held.id,
            status=RunStatus.PAUSED.value,
            preempted_at=datetime.now(timezone.utc),
        )
        assert await resume_preempted(session, redis) == [held.id]

        row = await repo.get_run(held.id)
        assert row.status == RunStatus.QUEUED.value
        # Cleared, so a second tick does not try to resume it again.
        assert row.preempted_at is None
        assert job_id_for(held.id) in redis.queue


@pytest.mark.asyncio
async def test_a_run_its_owner_paused_stays_paused():
    """The two pauses look identical in `status`; only `preempted_at` tells them apart."""
    await clear_runs()
    redis = FakeRedis()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        mine = await repo.create_run(protocol())
        await repo.update_run(mine.id, status=RunStatus.PAUSED.value)

        assert await resume_preempted(session, redis) == []
        assert (await repo.get_run(mine.id)).status == RunStatus.PAUSED.value
        assert redis.queue == {}


@pytest.mark.asyncio
async def test_nothing_resumes_while_urgent_work_is_still_around():
    await clear_runs()
    redis = FakeRedis()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        held = await repo.create_run(protocol())
        await repo.update_run(
            held.id,
            status=RunStatus.PAUSED.value,
            preempted_at=datetime.now(timezone.utc),
        )
        urgent = await repo.create_run(protocol("Still urgent?"), priority=URGENT)
        await repo.update_run(urgent.id, status=RunStatus.QUEUED.value)

        assert await resume_preempted(session, redis) == []
        assert (await repo.get_run(held.id)).status == RunStatus.PAUSED.value


@pytest.mark.asyncio
async def test_a_run_waiting_on_a_person_is_not_waiting_on_the_queue():
    await clear_runs()
    redis = FakeRedis()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        held = await repo.create_run(protocol())
        await repo.update_run(
            held.id,
            status=RunStatus.PAUSED.value,
            preempted_at=datetime.now(timezone.utc),
            interaction={"interaction_id": "INT1", "type": "plan_review"},
        )
        assert await resume_preempted(session, redis) == []


@pytest.mark.asyncio
async def test_the_scheduler_reads_are_system_only():
    """They cross the ownership boundary by design, so an ordinary actor cannot call them."""
    from research_platform.repository import RunAccessDenied

    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.user("SOMEUSER"))
        for call in (repo.running_normal_run, repo.urgent_work_pending, repo.preempted_runs):
            with pytest.raises(RunAccessDenied):
                await call()


@pytest.mark.asyncio
async def test_the_worker_cron_is_wired_to_the_scheduler():
    await clear_runs()
    redis = FakeRedis()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        held = await repo.create_run(protocol())
        await repo.update_run(
            held.id,
            status=RunStatus.PAUSED.value,
            preempted_at=datetime.now(timezone.utc),
        )
    await resume_preempted_runs({"redis": redis})
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        assert (await repo.get_run(held.id)).status == RunStatus.QUEUED.value
    assert redis.queue_name == default_queue_name


@pytest.mark.asyncio
async def test_the_priority_endpoint_only_moves_a_waiting_run():
    from fastapi.testclient import TestClient

    from conftest import api_headers, ensure_test_user
    from research_platform.api import app

    await ensure_test_user()
    await clear_runs()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        created = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "Priority endpoint",
                "primary_question": "Can a waiting run change bands after it was created?",
                "budget": {"max_wall_minutes": 30},
            },
        })
        assert created.status_code == 200, created.text
        run_id = created.json()["id"]
        assert created.json()["priority"] == "normal"

        promoted = client.post(f"/v1/research-runs/{run_id}/priority",
                               json={"priority": "urgent"})
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["priority"] == "urgent"

        # Nothing to reorder once it holds the worker, so the answer is a refusal rather
        # than a change that would not do anything.
        async with SessionLocal() as session:
            repo = Repository(session, actor=acting_principal())
            await repo.update_run(run_id, status=RunStatus.RUNNING.value)
        refused = client.post(f"/v1/research-runs/{run_id}/priority",
                              json={"priority": "normal"})
        assert refused.status_code == 409

        unknown = client.post("/v1/research-runs/01M0NOTAREALRUNIDXXXXXXXXX/priority",
                              json={"priority": "urgent"})
        assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_a_run_is_created_in_the_band_the_caller_asked_for():
    from fastapi.testclient import TestClient

    from conftest import api_headers, ensure_test_user
    from research_platform.api import app

    await ensure_test_user()
    await clear_runs()
    with TestClient(app) as client:
        client.headers.update(api_headers())
        created = client.post("/v1/research-runs", json={
            "protocol": {
                "title": "Urgent creation",
                "primary_question": "Does urgency survive the create call?",
                "budget": {"max_wall_minutes": 30},
            },
            "priority": "urgent",
        })
        assert created.status_code == 200, created.text
        assert created.json()["priority"] == "urgent"


@pytest.mark.asyncio
async def test_a_free_slot_means_nothing_gets_preempted(monkeypatch):
    """Preemption costs the paused run everything its stage did since the last
    checkpoint. Paying that while the machine could simply carry another run is waste."""
    from research_platform import scheduler

    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        running = await repo.create_run(protocol())
        await repo.update_run(running.id, status=RunStatus.RUNNING.value)
        urgent = await repo.create_run(protocol("Urgent, but there is room?"),
                                       priority=URGENT)

        async def has_room(_repo):
            return True

        monkeypatch.setattr(scheduler, "free_slot", has_room)
        assert await preempt_for(session, urgent.id, URGENT) is None
        assert (await repo.get_run(running.id)).status == RunStatus.RUNNING.value


@pytest.mark.asyncio
async def test_a_full_machine_still_makes_room_for_an_urgent_run(monkeypatch):
    from research_platform import scheduler

    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        running = await repo.create_run(protocol())
        await repo.update_run(running.id, status=RunStatus.RUNNING.value)
        urgent = await repo.create_run(protocol("Urgent with no room?"), priority=URGENT)

        async def no_room(_repo):
            return False

        monkeypatch.setattr(scheduler, "free_slot", no_room)
        assert await preempt_for(session, urgent.id, URGENT) == running.id
        assert (await repo.get_run(running.id)).status == RunStatus.PAUSED.value


@pytest.mark.asyncio
async def test_the_running_count_sees_every_owner():
    await clear_runs()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        assert await repo.running_run_count() == 0
        for question in ("First parallel run?", "Second parallel run?"):
            row = await repo.create_run(protocol(question))
            await repo.update_run(row.id, status=RunStatus.RUNNING.value)
        assert await repo.running_run_count() == 2
