from __future__ import annotations

import httpx
from arq import run_worker
from arq.connections import RedisSettings

from .config import get_settings
from .db import SessionLocal, create_schema
from .pipeline import ResearchPipeline


async def startup(ctx: dict) -> None:
    settings = get_settings()
    ctx["http"] = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=3),
        timeout=settings.request_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )
    await create_schema()


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
