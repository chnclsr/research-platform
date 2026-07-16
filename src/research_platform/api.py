from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import httpx
import uvicorn
from arq.constants import (
    default_queue_name,
    in_progress_key_prefix,
    job_key_prefix,
    retry_key_prefix,
)
from arq.connections import RedisSettings, create_pool
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from .config import Settings, get_settings
from .connectors import build_registry
from .db import SessionLocal, create_schema, get_session
from .embeddings import EmbeddingClient
from .passages import retrieve_passages
from .repository import Repository
from .paperqa_adapter import paperqa2_health
from .schemas import (
    ArtifactView, CorpusSearchRequest, DeliveryMode, ResearchRunCreate, RunStatus, RunView,
    SourceFamily, ZoteroSyncRequest, ZoteroSyncResult,
)
from .storage import ObjectStore
from .zotero_sync import ZoteroSyncService

logger = logging.getLogger(__name__)


async def _connect_redis(app: FastAPI, *, attempts: int = 1, delay_s: float = 1.0):
    if app.state.redis is not None:
        try:
            await app.state.redis.ping()
            return app.state.redis
        except Exception:
            try:
                await app.state.redis.aclose()
            except Exception:
                pass
            app.state.redis = None
    settings = get_settings()
    if settings.testing:
        return None
    async with app.state.redis_lock:
        if app.state.redis is not None:
            return app.state.redis
        for attempt in range(1, attempts + 1):
            try:
                app.state.redis = await create_pool(
                    RedisSettings.from_dsn(settings.redis_url)
                )
                return app.state.redis
            except Exception as exc:
                logger.warning(
                    "Redis queue connection failed (%s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    await asyncio.sleep(delay_s)
    return None


async def _reconcile_interrupted_runs(app: FastAPI) -> None:
    redis = app.state.redis
    if redis is None:
        return

    async def discard_stable_job(run_id: str) -> None:
        job_id = f"run:{run_id}"
        await redis.zrem(default_queue_name, job_id)
        await redis.delete(
            f"{job_key_prefix}{job_id}",
            f"{in_progress_key_prefix}{job_id}",
            f"{retry_key_prefix}{job_id}",
        )

    async with SessionLocal() as session:
        repo = Repository(session)
        cancelled = await repo.list_runs_by_statuses({RunStatus.CANCEL_REQUESTED.value})
        for row in cancelled:
            await repo.update_run(row.id, status=RunStatus.CANCELLED.value)
            await repo.event(
                row.id,
                "cancelled",
                {"stage": row.current_stage, "reconciled": True},
            )

        terminal = await repo.list_runs_by_statuses({
            RunStatus.CANCELLED.value,
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_INCOMPLETE.value,
            RunStatus.FAILED.value,
        })
        for row in terminal:
            await discard_stable_job(row.id)

        queued = await repo.list_runs_by_statuses({RunStatus.QUEUED.value})
        for row in queued:
            await redis.enqueue_job(
                "execute_research_run",
                row.id,
                _job_id=f"run:{row.id}",
            )


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
    app.state.redis_lock = asyncio.Lock()
    if not settings.testing:
        await _connect_redis(app, attempts=30)
        await _reconcile_interrupted_runs(app)
    yield
    await app.state.http.aclose()
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="Research Platform API", version="0.4.3",
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
    await _connect_redis(request.app, attempts=1)
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
    required_ok = checks["database"] == "ok" and checks["redis"] == "ok"
    return {"status": "healthy" if required_ok else "degraded", "checks": checks}


@app.post("/v1/research-runs", response_model=RunView, dependencies=[Depends(authorize)])
async def create_research_run(
    body: ResearchRunCreate, request: Request, repo: Repository = Depends(repository)
) -> RunView:
    settings = get_settings()
    redis = await _connect_redis(request.app, attempts=3)
    if redis is None and not settings.testing:
        raise HTTPException(status_code=503, detail="Redis queue unavailable; run was not created")
    row = await repo.create_run(body.protocol)
    if redis is not None:
        try:
            queued = await redis.enqueue_job(
                "execute_research_run",
                row.id,
                _job_id=f"run:{row.id}",
            )
            if queued is None:
                raise RuntimeError("ARQ rejected the research job")
        except Exception as exc:
            await repo.update_run(
                row.id,
                status=RunStatus.FAILED.value,
                error=f"Redis enqueue failed: {type(exc).__name__}: {exc}",
            )
            raise HTTPException(
                status_code=503,
                detail="Research queue rejected the run",
            ) from exc
    elif not settings.testing:
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
    redis = await _connect_redis(request.app, attempts=3)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis queue unavailable")
    row = await repo.update_run(run_id, status=RunStatus.QUEUED.value)
    try:
        queued = await redis.enqueue_job("execute_research_run", run_id)
        if queued is None:
            raise RuntimeError("ARQ rejected the resumed research job")
    except Exception as exc:
        await repo.update_run(
            run_id,
            status=RunStatus.PAUSED.value,
            error=f"Redis resume enqueue failed: {type(exc).__name__}: {exc}",
        )
        raise HTTPException(
            status_code=503,
            detail="Research queue rejected the resumed run",
        ) from exc
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


@app.get(
    "/v1/research-runs/{run_id}/delivery/{mode}",
    dependencies=[Depends(authorize)],
)
async def download_delivery(
    run_id: str, mode: DeliveryMode, repo: Repository = Depends(repository),
) -> Response:
    bundle_by_mode = {
        DeliveryMode.RAW: "raw_bundle.zip",
        DeliveryMode.RESULT: "result_bundle.zip",
        DeliveryMode.BOTH: "research_bundle.zip",
    }
    return await download_artifact(run_id, bundle_by_mode[mode], repo)


@app.get("/v1/connectors", dependencies=[Depends(authorize)])
async def list_connectors(request: Request) -> list[dict]:
    registry = build_registry(get_settings(), request.app.state.http)
    health = [h.model_dump(mode="json") for h in await registry.health()]
    health.append(paperqa2_health(get_settings()))
    return health


@app.get("/v1/zotero/collections", dependencies=[Depends(authorize)])
async def list_zotero_collections(mode: str, request: Request) -> list[dict]:
    if mode not in {"local", "web"}:
        raise HTTPException(status_code=422, detail="mode must be local or web")
    connector = build_registry(get_settings(), request.app.state.http).get(f"zotero_{mode}")
    health = await connector.health()
    if not health.enabled or not health.healthy:
        raise HTTPException(status_code=503, detail=health.detail)
    return await connector.list_collections()


@app.post(
    "/v1/zotero/sync", response_model=ZoteroSyncResult,
    dependencies=[Depends(authorize)],
)
async def sync_zotero(
    body: ZoteroSyncRequest, request: Request,
    session: AsyncSession = Depends(get_session),
) -> ZoteroSyncResult:
    try:
        return await ZoteroSyncService(
            get_settings(), session, request.app.state.http
        ).sync(body)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/v1/research-runs/{run_id}/citation-graph",
    dependencies=[Depends(authorize)],
)
async def citation_graph(run_id: str, repo: Repository = Depends(repository)) -> dict:
    await _required_run(run_id, repo)
    sources = {source.id: source for source in await repo.list_sources(run_id)}
    relations = await repo.list_source_relations(run_id)
    return {
        "nodes": [{
            "id": source.id, "title": source.title, "persistent_id": source.persistent_id,
            "connector_id": source.connector_id,
        } for source in sources.values()],
        "edges": [{
            "source_id": relation.source_id,
            "target_source_id": relation.target_source_id,
            "target_persistent_id": relation.target_persistent_id,
            "relation_type": relation.relation_type,
            "provider": relation.provider,
            "metadata": relation.metadata_json,
        } for relation in relations],
    }


@app.get(
    "/v1/research-runs/{run_id}/academic-coverage",
    dependencies=[Depends(authorize)],
)
async def academic_coverage(run_id: str, repo: Repository = Depends(repository)) -> dict:
    await _required_run(run_id, repo)
    academic = [
        source for source in await repo.list_sources(run_id)
        if source.family == SourceFamily.ACADEMIC.value
    ]
    providers = {
        provider
        for source in academic
        for provider in (source.metadata_json.get("provider_snapshots") or {})
    }
    versions = await repo.list_source_versions(run_id)
    full_text_source_ids = {
        source.id for source, version in versions
        if bool(version.content.strip()) and version.acquisition_method != "zotero_metadata"
    }
    return {
        "academic_sources": len(academic),
        "providers": sorted(providers),
        "with_doi": sum(
            bool((source.metadata_json.get("scholarly_identity") or {}).get("doi"))
            for source in academic
        ),
        "with_full_text": sum(source.id in full_text_source_ids for source in academic),
        "retracted": sum(
            bool(source.metadata_json.get("is_retracted")) for source in academic
        ),
        "citation_edges": len(await repo.list_source_relations(run_id)),
    }


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
    settings = get_settings()
    uvicorn.run(
        "research_platform.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
