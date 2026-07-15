from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import uvicorn
from arq.connections import RedisSettings, create_pool
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from .config import Settings, get_settings
from .connectors import build_registry
from .db import create_schema, get_session
from .embeddings import EmbeddingClient
from .passages import retrieve_passages
from .repository import Repository
from .schemas import ArtifactView, CorpusSearchRequest, ResearchRunCreate, RunStatus, RunView
from .storage import ObjectStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_schema()
    settings = get_settings()
    app.state.http = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=3),
        timeout=settings.request_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )
    app.state.redis = None
    if not settings.testing:
        try:
            app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        except Exception:
            app.state.redis = None
    yield
    await app.state.http.aclose()
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="Research Platform API", version="0.2.0",
    description="Local-first, multi-source evidence research platform", lifespan=lifespan,
)


async def authorize(
    authorization: str | None = Header(None), settings: Settings = Depends(get_settings)
) -> None:
    if settings.testing:
        return
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


async def repository(session: AsyncSession = Depends(get_session)) -> Repository:
    return Repository(session)


@app.get("/health")
async def health(request: Request) -> dict:
    settings = get_settings()
    checks = {"database": "ok", "redis": "ok" if request.app.state.redis else "unavailable"}
    try:
        response = await request.app.state.http.get(f"{settings.ollama_url}/api/version", timeout=3)
        checks["ollama"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["ollama"] = "unavailable"
    try:
        response = await request.app.state.http.get(f"{settings.agentsearch_url}/health", timeout=3)
        checks["agentsearch"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["agentsearch"] = "unavailable"
    try:
        response = await request.app.state.http.get(f"{settings.crawl4ai_url}/health", timeout=3)
        checks["crawl4ai"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["crawl4ai"] = "unavailable"
    try:
        scheme = "https" if settings.minio_secure else "http"
        response = await request.app.state.http.get(
            f"{scheme}://{settings.minio_endpoint}/minio/health/live", timeout=3
        )
        checks["minio"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["minio"] = "unavailable"
    return {"status": "healthy" if checks["database"] == "ok" else "degraded", "checks": checks}


@app.post("/v1/research-runs", response_model=RunView, dependencies=[Depends(authorize)])
async def create_research_run(
    body: ResearchRunCreate, request: Request, repo: Repository = Depends(repository)
) -> RunView:
    row = await repo.create_run(body.protocol)
    if request.app.state.redis:
        await request.app.state.redis.enqueue_job("execute_research_run", row.id, _job_id=f"run:{row.id}")
    elif not get_settings().testing:
        await repo.update_run(
            row.id, status=RunStatus.FAILED.value,
            error="Redis queue unavailable; run was not started",
        )
    row = await repo.get_run(row.id)
    return repo.run_view(row)


async def _required_run(run_id: str, repo: Repository) -> object:
    row = await repo.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return row


@app.get("/v1/research-runs/{run_id}", response_model=RunView, dependencies=[Depends(authorize)])
async def get_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    return repo.run_view(await _required_run(run_id, repo))


@app.post("/v1/research-runs/{run_id}/pause", response_model=RunView, dependencies=[Depends(authorize)])
async def pause_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    row = await _required_run(run_id, repo)
    if row.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
        raise HTTPException(status_code=409, detail=f"Cannot pause run in {row.status}")
    return repo.run_view(await repo.update_run(run_id, status=RunStatus.PAUSED.value))


@app.post("/v1/research-runs/{run_id}/resume", response_model=RunView, dependencies=[Depends(authorize)])
async def resume_research_run(
    run_id: str, request: Request, repo: Repository = Depends(repository)
) -> RunView:
    row = await _required_run(run_id, repo)
    if row.status != RunStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail=f"Cannot resume run in {row.status}")
    row = await repo.update_run(run_id, status=RunStatus.QUEUED.value)
    if not request.app.state.redis:
        raise HTTPException(status_code=503, detail="Redis queue unavailable")
    await request.app.state.redis.enqueue_job("execute_research_run", run_id)
    return repo.run_view(row)


@app.post("/v1/research-runs/{run_id}/cancel", response_model=RunView, dependencies=[Depends(authorize)])
async def cancel_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    row = await _required_run(run_id, repo)
    if row.status in {RunStatus.COMPLETED.value, RunStatus.COMPLETED_INCOMPLETE.value, RunStatus.CANCELLED.value}:
        raise HTTPException(status_code=409, detail=f"Cannot cancel run in {row.status}")
    return repo.run_view(await repo.update_run(run_id, status=RunStatus.CANCEL_REQUESTED.value))


@app.get("/v1/research-runs/{run_id}/events", dependencies=[Depends(authorize)])
async def stream_events(run_id: str, repo: Repository = Depends(repository)) -> EventSourceResponse:
    await _required_run(run_id, repo)

    async def generator():
        after_id = 0
        while True:
            rows = await repo.events_after(run_id, after_id)
            for row in rows:
                after_id = row.id
                yield {"id": str(row.id), "event": row.event_type, "data": json.dumps(row.payload, ensure_ascii=False)}
            run = await repo.get_run(run_id)
            if run and run.status in {
                RunStatus.COMPLETED.value, RunStatus.COMPLETED_INCOMPLETE.value,
                RunStatus.CANCELLED.value, RunStatus.FAILED.value,
            } and not rows:
                break
            yield {"event": "heartbeat", "data": "{}"}
            await asyncio.sleep(1)

    return EventSourceResponse(generator())


@app.get("/v1/research-runs/{run_id}/sources", dependencies=[Depends(authorize)])
async def list_sources(run_id: str, repo: Repository = Depends(repository)) -> list[dict]:
    await _required_run(run_id, repo)
    return [{
        "id": s.id, "family": s.family, "connector_id": s.connector_id,
        "title": s.title, "url": s.url, "persistent_id": s.persistent_id,
    } for s in await repo.list_sources(run_id)]


@app.get("/v1/research-runs/{run_id}/claims", dependencies=[Depends(authorize)])
async def list_claims(run_id: str, repo: Repository = Depends(repository)) -> list[dict]:
    await _required_run(run_id, repo)
    return [{
        "id": c.id, "text": c.text, "importance": c.importance,
        "status": c.status, "confidence": c.confidence, "audit": c.audit,
    } for c in await repo.list_claims(run_id)]


@app.get("/v1/research-runs/{run_id}/coverage", dependencies=[Depends(authorize)])
async def get_coverage(run_id: str, repo: Repository = Depends(repository)) -> dict:
    return (await _required_run(run_id, repo)).coverage


@app.get(
    "/v1/research-runs/{run_id}/artifacts", response_model=list[ArtifactView],
    dependencies=[Depends(authorize)],
)
async def list_artifacts(run_id: str, repo: Repository = Depends(repository)) -> list[ArtifactView]:
    await _required_run(run_id, repo)
    return [ArtifactView(
        name=a.name, media_type=a.media_type, size_bytes=a.size_bytes,
        download_url=f"/v1/research-runs/{run_id}/artifacts/{a.name}",
    ) for a in await repo.list_artifacts(run_id)]


@app.get("/v1/research-runs/{run_id}/artifacts/{name}", dependencies=[Depends(authorize)])
async def download_artifact(run_id: str, name: str, repo: Repository = Depends(repository)) -> Response:
    artifacts = {a.name: a for a in await repo.list_artifacts(run_id)}
    artifact = artifacts.get(name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    data = await ObjectStore(get_settings()).get(artifact.object_key)
    return Response(
        data, media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
    )


@app.get("/v1/connectors", dependencies=[Depends(authorize)])
async def list_connectors(request: Request) -> list[dict]:
    registry = build_registry(get_settings(), request.app.state.http)
    return [h.model_dump(mode="json") for h in await registry.health()]


@app.post("/v1/corpus/search", dependencies=[Depends(authorize)])
async def search_local_corpus(
    body: CorpusSearchRequest, request: Request, repo: Repository = Depends(repository),
) -> list[dict]:
    passages = await repo.list_corpus_passages(exclude_run_id="", limit=5000)
    if not passages:
        return []
    try:
        vectors = await EmbeddingClient(get_settings(), request.app.state.http).embed([body.query])
    except Exception:
        vectors = [[]]
    selected = retrieve_passages(passages, [body.query], vectors, per_question=body.top_k)[:body.top_k]
    source_metadata = await repo.source_metadata_for_versions(list({
        passage.source_version_id for passage in selected
    }))
    return [{
        "passage_id": passage.id, "source_version_id": passage.source_version_id,
        "section_path": passage.section_path, "page_number": passage.page_number,
        "start_char": passage.start_char, "end_char": passage.end_char,
        "language": passage.language, "document_type": passage.document_type,
        "score": passage.retrieval_score, "text": passage.text,
        "source": source_metadata.get(passage.source_version_id, {}),
    } for passage in selected]


@app.post("/v1/connectors/{connector_id}/test", dependencies=[Depends(authorize)])
async def test_connector(connector_id: str, request: Request) -> dict:
    registry = build_registry(get_settings(), request.app.state.http)
    connector = registry.get(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    health = await connector.health()
    if not health.enabled:
        return {"ok": False, "health": health.model_dump(mode="json"), "result_count": 0}
    try:
        rows = await connector.search("open research", 1)
        return {"ok": True, "health": health.model_dump(mode="json"), "result_count": len(rows)}
    except Exception as exc:
        return {"ok": False, "health": health.model_dump(mode="json"), "error": str(exc)[:500]}


def run() -> None:
    uvicorn.run("research_platform.api:app", host="0.0.0.0", port=8000, reload=False)
