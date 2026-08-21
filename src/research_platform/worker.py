from __future__ import annotations

import httpx
from arq import run_worker
from arq.cron import cron
from arq.connections import RedisSettings

import logging

from .capacity import GATE, startup_ceiling
from .config import get_settings
from .db import SessionLocal, create_schema
from .pipeline import ResearchPipeline
from .auth import Principal
from .queueing import NORMAL, discard_run_jobs, enqueue_run
from .repository import Repository
from .scheduler import resume_preempted
from .schemas import RunStatus
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def _recover_interrupted_jobs(ctx: dict) -> None:
    """Remove locks owned by a previous worker process and resume from checkpoints."""
    redis = ctx["redis"]

    async def discard(run_id: str) -> None:
        await discard_run_jobs(redis, run_id)

    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        cancel_rows = await repo.list_runs_by_statuses({RunStatus.CANCEL_REQUESTED.value})
        for row in cancel_rows:
            await discard(row.id)
            await repo.update_run(row.id, status=RunStatus.CANCELLED.value)
            await repo.event(
                row.id,
                "cancelled",
                {"stage": row.current_stage, "worker_recovery": True},
            )

        resumable = await repo.list_runs_by_statuses(
            {
                RunStatus.RUNNING.value,
                RunStatus.QUEUED.value,
            }
        )
        for row in resumable:
            await discard(row.id)
            await repo.update_run(row.id, status=RunStatus.QUEUED.value)
            await repo.event(
                row.id,
                "worker_recovery",
                {"stage": row.current_stage, "resumed_from_checkpoint": True},
            )
            await enqueue_run(redis, row.id, row.priority)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    ctx["http"] = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=3),
        timeout=settings.request_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )
    await create_schema()
    await _recover_interrupted_jobs(ctx)


async def shutdown(ctx: dict) -> None:
    client = ctx.get("http")
    if client is not None:
        await client.aclose()


async def execute_research_run(ctx: dict, run_id: str) -> None:
    settings = get_settings()
    priority = NORMAL
    async with SessionLocal() as session:
        row = await Repository(session, actor=Principal.system()).get_run(run_id)
        if row is not None:
            priority = row.priority

    async def announce(capacity) -> None:
        # The run keeps its `queued` status while it waits -- it is not executing -- and
        # the event carries the measurement, so "why is this not starting" has an answer
        # instead of a shrug.
        async with SessionLocal() as session:
            await Repository(session, actor=Principal.system()).event(
                run_id, "awaiting_capacity", capacity.as_dict()
            )

    capacity = await GATE.acquire(
        run_id, priority=priority, settings=settings, on_wait=announce
    )
    logger.info(
        "run %s admitted: %d/%d slots, limited by %s",
        run_id,
        GATE.active,
        capacity.allowed,
        capacity.limited_by,
    )
    try:
        async with SessionLocal() as session:
            pipeline = ResearchPipeline(settings, session, ctx["http"])
            await pipeline.run(run_id)
    finally:
        GATE.release(run_id)


async def expire_hitl_interactions(ctx: dict) -> None:
    """Release worker resources while preserving unanswered HITL state."""
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.system())
        rows = await repo.list_runs_by_statuses({RunStatus.AWAITING_INPUT.value})
        now = datetime.now(timezone.utc)
        for row in rows:
            interaction = row.interaction or {}
            expires_at = interaction.get("expires_at")
            if not expires_at:
                continue
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry <= now:
                await repo.update_run(row.id, status=RunStatus.PAUSED.value)
                await repo.event(
                    row.id,
                    "hitl_paused",
                    {
                        "interaction_id": interaction.get("interaction_id"),
                        "type": interaction.get("type"),
                        "reason": "input_timeout",
                    },
                )


async def resume_preempted_runs(ctx: dict) -> None:
    """Give the worker back to a run that was paused for an urgent one.

    On a cron rather than at the end of the urgent job: a worker that crashes instead of
    finishing would otherwise leave the paused run with nothing that ever picks it up.
    """
    async with SessionLocal() as session:
        await resume_preempted(session, ctx["redis"])


class WorkerSettings:
    functions = [execute_research_run, expire_hitl_interactions, resume_preempted_runs]
    cron_jobs = [
        cron(expire_hitl_interactions, second={0, 30}, run_at_startup=True),
        cron(resume_preempted_runs, second={5, 35}, run_at_startup=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # The ceiling arq can never exceed, computed from this machine's hardware at import.
    # arq fixes max_jobs when the Worker is built, so the live decision -- how many runs
    # fit *right now* -- is made by the capacity gate inside execute_research_run.
    #
    # Raising this above 1 also fixes something that was quietly broken: arq puts cron
    # jobs on the same sorted set and only starts them while job_counter < max_jobs, so
    # with one slot the crons never ran while a research run was executing.
    max_jobs = startup_ceiling()
    # Collection has its own budget. Post-processing and final synthesis are
    # allowed to finish after that cutoff instead of being killed mid-report.
    job_timeout = 24 * 60 * 60
    keep_result = 60
    health_check_interval = 30


def run() -> None:
    run_worker(WorkerSettings)
