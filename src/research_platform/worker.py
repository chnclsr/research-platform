from __future__ import annotations

import httpx
from arq import run_worker
from arq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix, retry_key_prefix
from arq.connections import RedisSettings

from .config import get_settings
from .db import SessionLocal, create_schema
from .pipeline import ResearchPipeline
from .repository import Repository
from .schemas import RunStatus


async def _recover_interrupted_jobs(ctx: dict) -> None:
    """Remove locks owned by a previous worker process and resume from checkpoints."""
    redis = ctx["redis"]

    async def discard(run_id: str) -> None:
        job_id = f"run:{run_id}"
        await redis.zrem(default_queue_name, job_id)
        await redis.delete(
            f"{job_key_prefix}{job_id}",
            f"{in_progress_key_prefix}{job_id}",
            f"{retry_key_prefix}{job_id}",
        )

    async with SessionLocal() as session:
        repo = Repository(session)
        cancel_rows = await repo.list_runs_by_statuses({RunStatus.CANCEL_REQUESTED.value})
        for row in cancel_rows:
            await discard(row.id)
            await repo.update_run(row.id, status=RunStatus.CANCELLED.value)
            await repo.event(
                row.id,
                "cancelled",
                {"stage": row.current_stage, "worker_recovery": True},
            )

        resumable = await repo.list_runs_by_statuses({
            RunStatus.RUNNING.value,
            RunStatus.QUEUED.value,
        })
        for row in resumable:
            await discard(row.id)
            await repo.update_run(row.id, status=RunStatus.QUEUED.value)
            await repo.event(
                row.id,
                "worker_recovery",
                {"stage": row.current_stage, "resumed_from_checkpoint": True},
            )
            await redis.enqueue_job(
                "execute_research_run",
                row.id,
                _job_id=f"run:{row.id}",
            )


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
    async with SessionLocal() as session:
        pipeline = ResearchPipeline(settings, session, ctx["http"])
        await pipeline.run(run_id)


class WorkerSettings:
    functions = [execute_research_run]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = 60 * 60
    keep_result = 60
    health_check_interval = 30


def run() -> None:
    run_worker(WorkerSettings)
