from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import uvicorn
from arq.connections import RedisSettings, create_pool
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from .auth import API_KEY_SCHEME, AuthError, Principal
from .capacity import measure, plan_capacity
from .config import Settings, get_settings
from .connectors import build_registry
from .db import SessionLocal, create_schema, get_session
from .document_revision import DocumentRevisionService, editable_targets
from .embeddings import EmbeddingClient
from .identity import principal_from_api_key, principal_from_user_id
from .paperqa_adapter import paperqa2_health
from .parsers import build_parser_registry
from .passages import retrieve_passages
from .queueing import (
    cancel_queued_revision_job,
    discard_run_jobs,
    enqueue_revision,
    enqueue_run,
    normalize_priority,
    rescore_run,
)
from .repository import (
    ActorRequired,
    Repository,
    RevisionConflict,
    RevisionNotFound,
    RunAccessDenied,
)
from .scheduler import preempt_for
from .schemas import (
    AccessIssueView,
    ArtifactVersionView,
    ArtifactView,
    CorpusSearchRequest,
    DeliveryMode,
    DocumentRevisionCreate,
    DocumentRevisionView,
    HitlRespondRequest,
    ResearchRunCreate,
    RevisionFeedbackRequest,
    RevisionPlan,
    RevisionStatus,
    RunPriorityRequest,
    RunStatus,
    RunView,
    SourceFamily,
    ZoteroSyncRequest,
    ZoteroSyncResult,
)
from .storage import ObjectStore
from .version import VERSION
from .zotero_sync import ZoteroSyncService

logger = logging.getLogger(__name__)


def _validate_hitl_response(interaction_type: str, response: dict) -> dict:
    if interaction_type == "planning_questions":
        answers = response.get("answers")
        if not isinstance(answers, list) or not answers:
            raise HTTPException(status_code=400, detail="answers must be a non-empty list")
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("question"), str)
            or not isinstance(item.get("answer"), str)
            or not item["answer"].strip()
            for item in answers
        ):
            raise HTTPException(
                status_code=400, detail="each answer needs question and answer strings"
            )
        # Rebuilt field by field rather than passed through: `id` and `value` are what make
        # an answer bind to a protocol field (see scoping.apply_planning_answers), and
        # everything else a caller sends would otherwise land in hitl_history unchecked.
        return {
            "answers": [
                {
                    "question": item["question"][:500],
                    "answer": item["answer"][:2000],
                    "id": str(item.get("id") or "")[:60],
                    "value": str(item.get("value") or "")[:120],
                }
                for item in answers
            ]
        }
    if interaction_type in {"plan_review", "outline_review"}:
        if not isinstance(response.get("approved"), bool):
            raise HTTPException(status_code=400, detail="approved boolean is required")
        result = {"approved": response["approved"]}
        if response.get("modifications"):
            result["modifications"] = str(response["modifications"])[:5000]
        # The duration was already required to create the run; approving the plan is the
        # one place it can be revised, so the bounds have to match ResearchBudget.
        if interaction_type == "plan_review" and response.get("max_wall_minutes") is not None:
            minutes = response["max_wall_minutes"]
            if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 1440:
                raise HTTPException(
                    status_code=400,
                    detail="max_wall_minutes must be an integer between 1 and 1440",
                )
            result["max_wall_minutes"] = minutes
        return result
    if interaction_type == "source_review":
        included = response.get("included_domains")
        excluded = response.get("excluded_domains")
        if not isinstance(included, list) or not isinstance(excluded, list):
            raise HTTPException(
                status_code=400,
                detail="included_domains and excluded_domains arrays are required",
            )
        return {
            "included_domains": [
                str(item).strip().lower() for item in included if str(item).strip()
            ],
            "excluded_domains": [
                str(item).strip().lower() for item in excluded if str(item).strip()
            ],
        }
    raise HTTPException(status_code=400, detail="Unknown interaction type")


async def _connect_redis(app: FastAPI, *, attempts: int):
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
                app.state.redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
                return app.state.redis
            except Exception as exc:
                logger.warning(
                    "Redis queue connection failed (%s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    await asyncio.sleep(settings.redis_connect_delay_s)
    return None


async def _reconcile_interrupted_runs(app: FastAPI) -> None:
    redis = app.state.redis
    if redis is None:
        return

    async def discard_stable_job(run_id: str) -> None:
        await discard_run_jobs(redis, run_id)

    async with SessionLocal() as session:
        # Startup reconciliation sweeps the whole queue regardless of who owns what.
        repo = Repository(session, actor=Principal.system())
        cancelled = await repo.list_runs_by_statuses({RunStatus.CANCEL_REQUESTED.value})
        for row in cancelled:
            await repo.update_run(row.id, status=RunStatus.CANCELLED.value)
            await repo.event(
                row.id,
                "cancelled",
                {"stage": row.current_stage, "reconciled": True},
            )

        terminal = await repo.list_runs_by_statuses(
            {
                RunStatus.CANCELLED.value,
                RunStatus.COMPLETED.value,
                RunStatus.COMPLETED_INCOMPLETE.value,
                RunStatus.FAILED.value,
            }
        )
        for row in terminal:
            await discard_stable_job(row.id)

        queued = await repo.list_runs_by_statuses({RunStatus.QUEUED.value})
        for row in queued:
            await enqueue_run(redis, row.id, row.priority)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_schema()
    settings = get_settings()
    app.state.http = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=settings.http_transport_retries),
        timeout=settings.request_timeout_s,
        headers={"User-Agent": settings.user_agent},
    )
    app.state.redis = None
    app.state.redis_lock = asyncio.Lock()
    if not settings.testing:
        await _connect_redis(app, attempts=settings.redis_startup_connect_attempts)
        await _reconcile_interrupted_runs(app)
    yield
    await app.state.http.aclose()
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="Research Platform API",
    version=VERSION,
    description="Local-first, multi-source evidence research platform",
    lifespan=lifespan,
)


async def resolve_principal(
    authorization: str | None = Header(None),
    x_actor_user: str | None = Header(None),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Turn the presented credential into the identity the request acts as.

    Three credentials are accepted, in the order a caller is likely to hold one:

    1. A per-user API key (``rp_<prefix>.<secret>``) -- scripts, MCP, Langflow.
    2. The service token plus ``X-Actor-User`` -- the panel and the Telegram bot,
       which authenticate their own users and then say who they are acting for. The
       header alone proves nothing; it is only read once the service token verifies.
    3. The legacy shared ``API_TOKEN``, which now maps to an admin-less system
       principal so existing internal callers keep working during the migration.

    Unlike the token check this replaces, there is no ``settings.testing`` bypass:
    ownership has to hold under test or the tests prove nothing about it.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer credential")
    presented = authorization[len("Bearer ") :].strip()

    if presented.startswith(f"{API_KEY_SCHEME}_"):
        try:
            return await principal_from_api_key(session, presented)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    service_token = settings.service_token or settings.api_token
    if not secrets.compare_digest(presented, service_token):
        raise HTTPException(status_code=401, detail="Invalid bearer credential")

    if x_actor_user:
        try:
            return await principal_from_user_id(session, x_actor_user)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    return Principal.system()


async def require_admin(principal: Principal = Depends(resolve_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return principal


async def repository(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> Repository:
    return Repository(session, actor=principal)


@app.exception_handler(RunAccessDenied)
async def _handle_run_access_denied(_: Request, __: RunAccessDenied) -> JSONResponse:
    """A run the caller cannot see reads as missing.

    Handled centrally rather than per route: with more than a dozen run-scoped
    endpoints, a per-handler try/except is one forgotten block away from leaking a
    403 that confirms the run exists.
    """
    return JSONResponse(status_code=404, content={"detail": "Research run not found"})


@app.exception_handler(ActorRequired)
async def _handle_actor_required(_: Request, exc: ActorRequired) -> JSONResponse:
    """A repository reached a run-scoped read with no actor -- our bug, not the caller's."""
    logger.error("Repository used without an actor: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal authorization error"})


@app.exception_handler(RevisionNotFound)
async def _handle_revision_not_found(_: Request, exc: RevisionNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(RevisionConflict)
async def _handle_revision_conflict(_: Request, exc: RevisionConflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
async def health(request: Request) -> dict:
    settings = get_settings()
    await _connect_redis(request.app, attempts=settings.redis_probe_connect_attempts)
    checks = {"database": "ok", "redis": "ok" if request.app.state.redis else "unavailable"}
    try:
        response = await request.app.state.http.get(
            f"{settings.ollama_url}/api/version", timeout=settings.service_health_timeout_s
        )
        checks["ollama"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["ollama"] = "unavailable"
    try:
        response = await request.app.state.http.get(
            f"{settings.agentsearch_url}/health", timeout=settings.service_health_timeout_s
        )
        checks["agentsearch"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["agentsearch"] = "unavailable"
    try:
        response = await request.app.state.http.get(
            f"{settings.crawl4ai_url}/health", timeout=settings.service_health_timeout_s
        )
        checks["crawl4ai"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["crawl4ai"] = "unavailable"
    # The heavy half of PDF parsing. Carries the device in the value rather than just
    # "ok": CPU and GPU do not produce the same text, so which one answered is the part
    # worth seeing without a shell. "unconfigured" is a deliberate deployment, not a
    # fault -- the router still routes, the pages it routes just keep their fast text.
    if not settings.smart_router_docling_url:
        checks["docling"] = "unconfigured"
    else:
        try:
            response = await request.app.state.http.get(
                f"{settings.smart_router_docling_url.rstrip('/')}/health",
                timeout=settings.service_health_timeout_s,
            )
            device = (response.json().get("device") or "?") if response.is_success else ""
            checks["docling"] = f"ok ({device})" if response.is_success else "degraded"
        except Exception:
            checks["docling"] = "unavailable"
    try:
        scheme = "https" if settings.minio_secure else "http"
        response = await request.app.state.http.get(
            f"{scheme}://{settings.minio_endpoint}/minio/health/live",
            timeout=settings.service_health_timeout_s,
        )
        checks["minio"] = "ok" if response.is_success else "degraded"
    except Exception:
        checks["minio"] = "unavailable"
    required_ok = checks["database"] == "ok" and checks["redis"] == "ok"
    return {
        "status": "healthy" if required_ok else "degraded",
        "checks": checks,
        # Answers "why is my run not starting" without a shell: how many runs fit right
        # now and which resource is the one saying no.
        "capacity": plan_capacity(
            await measure(settings, request.app.state.http)
        ).as_dict(),
    }


@app.post("/v1/research-runs", response_model=RunView, dependencies=[Depends(resolve_principal)])
async def create_research_run(
    body: ResearchRunCreate, request: Request, repo: Repository = Depends(repository)
) -> RunView:
    settings = get_settings()
    if body.invocation_source == "telegram":
        authorization = request.headers.get("Authorization", "")
        presented = authorization.removeprefix("Bearer ").strip()
        service_token = settings.service_token or settings.api_token
        if (
            not request.headers.get("X-Actor-User")
            or not secrets.compare_digest(presented, service_token)
        ):
            # Telegram provenance selects a separately quota-limited external provider;
            # accepting it from a normal API key would let callers spend that quota.
            raise HTTPException(
                status_code=403,
                detail="telegram invocation_source requires an acting service credential",
            )
    redis = await _connect_redis(request.app, attempts=settings.redis_operation_connect_attempts)
    if redis is None and not settings.testing:
        raise HTTPException(status_code=503, detail="Redis queue unavailable; run was not created")
    try:
        row = await repo.create_run(
            body.protocol,
            priority=body.priority,
            invocation_source=body.invocation_source,
        )
    except ActorRequired as exc:
        # The shared service token identifies a service, not a person, and a run with
        # no owner would be invisible to everyone but an admin. Callers using the
        # service token must name the user they are acting for.
        raise HTTPException(
            status_code=400,
            detail="This credential cannot own a run; use a user API key or send X-Actor-User",
        ) from exc
    if redis is not None:
        try:
            queued = await enqueue_run(redis, row.id, row.priority)
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
        # Outside the guard above on purpose: the run is queued and valid either way.
        # Failing to make room for it is a scheduling disappointment, not a reason to
        # fail the run the caller just created.
        await preempt_for(repo.session, row.id, row.priority)
    elif not settings.testing:
        await repo.update_run(
            row.id,
            status=RunStatus.FAILED.value,
            error="Redis queue unavailable; run was not started",
        )
    row = await repo.get_run(row.id)
    return repo.run_view(row)


async def _required_run(run_id: str, repo: Repository) -> object:
    row = await repo.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return row


@app.get("/v1/research-runs/{run_id}", response_model=RunView, dependencies=[Depends(resolve_principal)])
async def get_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    return repo.run_view(await _required_run(run_id, repo))


@app.get("/v1/research-runs", response_model=list[RunView], dependencies=[Depends(resolve_principal)])
async def list_research_runs(
    limit: int = 50,
    repo: Repository = Depends(repository),
) -> list[RunView]:
    return [repo.run_view(row) for row in await repo.list_runs(limit=limit)]


@app.get(
    "/v1/research-runs/{run_id}/access-issues",
    response_model=list[AccessIssueView],
    dependencies=[Depends(resolve_principal)],
)
async def list_access_issues(
    run_id: str,
    repo: Repository = Depends(repository),
) -> list[AccessIssueView]:
    """Searches and sources the run could not reach past a bot check or login wall."""
    await _required_run(run_id, repo)
    return [repo.access_issue_view(row) for row in await repo.list_access_issues(run_id)]


@app.post(
    "/v1/research-runs/{run_id}/pause", response_model=RunView, dependencies=[Depends(resolve_principal)]
)
async def pause_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    row = await _required_run(run_id, repo)
    if row.status not in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
        raise HTTPException(status_code=409, detail=f"Cannot pause run in {row.status}")
    return repo.run_view(await repo.update_run(run_id, status=RunStatus.PAUSED.value))


@app.post(
    "/v1/research-runs/{run_id}/resume", response_model=RunView, dependencies=[Depends(resolve_principal)]
)
async def resume_research_run(
    run_id: str, request: Request, repo: Repository = Depends(repository)
) -> RunView:
    settings = get_settings()
    row = await _required_run(run_id, repo)
    resumable_statuses = {RunStatus.PAUSED.value, RunStatus.FAILED.value}
    if row.status not in resumable_statuses:
        raise HTTPException(status_code=409, detail=f"Cannot resume run in {row.status}")
    if row.status == RunStatus.FAILED.value and await repo.latest_checkpoint(run_id) is None:
        raise HTTPException(
            status_code=409,
            detail="Failed run has no checkpoint to resume from",
        )
    if row.interaction:
        raise HTTPException(status_code=409, detail="Respond to the pending HITL interaction first")
    redis = await _connect_redis(request.app, attempts=settings.redis_operation_connect_attempts)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis queue unavailable")
    previous_status = row.status
    previous_error = row.error
    row = await repo.update_run(
        run_id,
        status=RunStatus.QUEUED.value,
        error=None,
    )
    if previous_status == RunStatus.FAILED.value:
        await repo.event(
            run_id,
            "failed_run_retry_requested",
            {"previous_error": previous_error},
        )
    try:
        queued = await enqueue_run(redis, run_id, row.priority)
        if queued is None:
            raise RuntimeError("ARQ rejected the resumed research job")
    except Exception as exc:
        await repo.update_run(
            run_id,
            status=previous_status,
            error=f"Redis resume enqueue failed: {type(exc).__name__}: {exc}",
        )
        raise HTTPException(
            status_code=503,
            detail="Research queue rejected the resumed run",
        ) from exc
    # A resumed run rejoins the queue in its own band, so an urgent one resuming has to
    # make room for itself the same way a new urgent run would.
    await preempt_for(repo.session, run_id, row.priority)
    return repo.run_view(row)


@app.post(
    "/v1/research-runs/{run_id}/respond",
    response_model=RunView,
    dependencies=[Depends(resolve_principal)],
)
async def respond_to_hitl(
    run_id: str,
    body: HitlRespondRequest,
    request: Request,
    repo: Repository = Depends(repository),
) -> RunView:
    settings = get_settings()
    row = await _required_run(run_id, repo)
    if row.status not in {RunStatus.AWAITING_INPUT.value, RunStatus.PAUSED.value}:
        raise HTTPException(status_code=409, detail=f"Run is not awaiting input: {row.status}")
    interaction = row.interaction or {}
    if interaction.get("interaction_id") != body.interaction_id:
        raise HTTPException(status_code=409, detail="interaction_id mismatch")
    response = _validate_hitl_response(str(interaction.get("type")), body.response)
    responded_at = datetime.now(timezone.utc)
    created_at = datetime.fromisoformat(
        str(interaction.get("created_at", responded_at.isoformat())).replace("Z", "+00:00")
    )
    checkpoint = await repo.latest_checkpoint(run_id)
    if checkpoint:
        checkpoint_state = dict(checkpoint.state or {})
        budget_started = checkpoint_state.get("budget_started_at")
        if budget_started:
            started_at = datetime.fromisoformat(str(budget_started).replace("Z", "+00:00"))
            checkpoint_state["budget_started_at"] = (
                started_at + max(timedelta(0), responded_at - created_at)
            ).isoformat()
            await repo.checkpoint(run_id, checkpoint.stage, checkpoint_state)
    history = [
        *(row.hitl_history or []),
        {
            **interaction,
            "responded_at": responded_at.isoformat(),
            "auto_continued": False,
            "response": response,
        },
    ]
    redis = await _connect_redis(request.app, attempts=settings.redis_operation_connect_attempts)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis queue unavailable")
    row = await repo.update_run(
        run_id,
        status=RunStatus.QUEUED.value,
        interaction=None,
        hitl_history=history,
        error=None,
    )
    await repo.event(
        run_id,
        "hitl_responded",
        {
            "interaction_id": body.interaction_id,
            "type": interaction.get("type"),
            "response": response,
        },
    )
    queued = await enqueue_run(redis, run_id, row.priority)
    if queued is None:
        await repo.update_run(run_id, status=RunStatus.PAUSED.value)
        raise HTTPException(status_code=503, detail="Research queue rejected the HITL response")
    await preempt_for(repo.session, run_id, row.priority)
    return repo.run_view(row)


@app.post(
    "/v1/research-runs/{run_id}/cancel", response_model=RunView, dependencies=[Depends(resolve_principal)]
)
async def cancel_research_run(run_id: str, repo: Repository = Depends(repository)) -> RunView:
    row = await _required_run(run_id, repo)
    if row.status in {
        RunStatus.COMPLETED.value,
        RunStatus.COMPLETED_INCOMPLETE.value,
        RunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail=f"Cannot cancel run in {row.status}")
    # A queued job has no in-flight work to unwind. The worker pre-start guard
    # safely ignores a stale queue entry if Redis has already delivered it.
    status = (
        RunStatus.CANCELLED.value
        if row.status
        in {
            RunStatus.QUEUED.value,
            RunStatus.AWAITING_INPUT.value,
            RunStatus.PAUSED.value,
        }
        else RunStatus.CANCEL_REQUESTED.value
    )
    row = await repo.update_run(run_id, status=status)
    if status == RunStatus.CANCELLED.value:
        await repo.event(run_id, "cancelled", {"stage": row.current_stage, "before_start": True})
    return repo.run_view(row)


@app.post(
    "/v1/research-runs/{run_id}/priority",
    response_model=RunView,
    dependencies=[Depends(resolve_principal)],
)
async def set_research_run_priority(
    run_id: str,
    body: RunPriorityRequest,
    request: Request,
    repo: Repository = Depends(repository),
) -> RunView:
    """Move a run between the two bands after it was created.

    Only while it is waiting. Re-banding a run that already holds the worker changes
    nothing about when it runs, and demoting one would be a confusing way to ask for a
    pause -- that is what the pause endpoint is for.
    """
    settings = get_settings()
    row = await _required_run(run_id, repo)
    if row.status not in {RunStatus.QUEUED.value, RunStatus.PAUSED.value}:
        raise HTTPException(
            status_code=409, detail=f"Cannot change priority of a run in {row.status}"
        )
    priority = normalize_priority(body.priority)
    row = await repo.update_run(run_id, priority=priority)
    await repo.event(run_id, "priority_changed", {"priority": priority})
    redis = await _connect_redis(request.app, attempts=settings.redis_probe_connect_attempts)
    if redis is not None:
        # A paused run has no queued job to move; it enters its new band when it resumes.
        await rescore_run(redis, run_id, priority)
        await preempt_for(repo.session, run_id, priority)
    return repo.run_view(row)


@app.get("/v1/research-runs/{run_id}/events", dependencies=[Depends(resolve_principal)])
async def stream_events(run_id: str, repo: Repository = Depends(repository)) -> EventSourceResponse:
    await _required_run(run_id, repo)

    async def generator():
        after_id = 0
        while True:
            rows = await repo.events_after(run_id, after_id)
            for row in rows:
                after_id = row.id
                yield {
                    "id": str(row.id),
                    "event": row.event_type,
                    "data": json.dumps(row.payload, ensure_ascii=False),
                }
            run = await repo.get_run(run_id)
            if (
                run
                and run.status
                in {
                    RunStatus.COMPLETED.value,
                    RunStatus.COMPLETED_INCOMPLETE.value,
                    RunStatus.CANCELLED.value,
                    RunStatus.FAILED.value,
                }
                and not rows
            ):
                break
            yield {"event": "heartbeat", "data": "{}"}
            await asyncio.sleep(1)

    return EventSourceResponse(generator())


@app.get("/v1/research-runs/{run_id}/sources", dependencies=[Depends(resolve_principal)])
async def list_sources(run_id: str, repo: Repository = Depends(repository)) -> list[dict]:
    await _required_run(run_id, repo)
    return [
        {
            "id": s.id,
            "family": s.family,
            "connector_id": s.connector_id,
            "title": s.title,
            "url": s.url,
            "persistent_id": s.persistent_id,
        }
        for s in await repo.list_sources(run_id)
    ]


@app.get("/v1/research-runs/{run_id}/claims", dependencies=[Depends(resolve_principal)])
async def list_claims(run_id: str, repo: Repository = Depends(repository)) -> list[dict]:
    await _required_run(run_id, repo)
    return [
        {
            "id": c.id,
            "text": c.text,
            "importance": c.importance,
            "status": c.status,
            "confidence": c.confidence,
            "audit": c.audit,
        }
        for c in await repo.list_claims(run_id)
    ]


@app.get("/v1/research-runs/{run_id}/coverage", dependencies=[Depends(resolve_principal)])
async def get_coverage(run_id: str, repo: Repository = Depends(repository)) -> dict:
    return (await _required_run(run_id, repo)).coverage


def _artifact_version_view(row) -> ArtifactVersionView:
    return ArtifactVersionView(
        id=row.id,
        run_id=row.run_id,
        revision_id=row.revision_id,
        logical_name=row.logical_name,
        revision_number=row.revision_number,
        parent_version_id=row.parent_version_id,
        media_type=row.media_type,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        download_url=(
            f"/v1/research-runs/{row.run_id}/artifact-versions/{row.id}"
        ),
        created_at=row.created_at,
    )


async def _document_revision_view(repo: Repository, row) -> DocumentRevisionView:
    versions = await repo.list_artifact_versions(row.run_id, revision_id=row.id)
    return DocumentRevisionView(
        id=row.id,
        run_id=row.run_id,
        parent_revision_id=row.parent_revision_id,
        base_revision_id=row.base_revision_id,
        target_artifact_name=row.target_artifact_name,
        revision_number=row.revision_number,
        status=row.status,
        feedback=row.feedback,
        edit_plan=row.edit_plan,
        format_overrides=row.format_overrides or {},
        requested_by=row.requested_by,
        channel=row.channel,
        conversation_id=row.conversation_id,
        model_id=row.model_id,
        prompt_version=row.prompt_version,
        usage=row.usage or {},
        validation=row.validation or {},
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
        accepted_at=row.accepted_at,
        artifacts=[_artifact_version_view(item) for item in versions],
    )


async def _ensure_initial_document_revision(run_id: str, repo: Repository):
    return await DocumentRevisionService(
        repo, ObjectStore(get_settings()), settings=get_settings()
    ).ensure_initial_revision(run_id)


async def _enqueue_document_revision(request: Request, repo: Repository, row) -> None:
    settings = get_settings()
    redis = await _connect_redis(request.app, attempts=settings.redis_operation_connect_attempts)
    if redis is None:
        if settings.testing:
            return
        await repo.update_document_revision(
            row.run_id,
            row.id,
            status=RevisionStatus.FAILED.value,
            error="Redis queue unavailable; document revision was not started",
        )
        raise HTTPException(status_code=503, detail="Redis revision queue unavailable")
    run = await _required_run(row.run_id, repo)
    queued = await enqueue_revision(redis, row.id, run.priority)
    if queued is None:
        raise HTTPException(status_code=409, detail="Document revision is already running")


@app.post(
    "/v1/research-runs/{run_id}/artifacts/{name}/revisions",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def create_document_revision(
    run_id: str,
    name: str,
    body: DocumentRevisionCreate,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    repo: Repository = Depends(repository),
) -> DocumentRevisionView:
    current = await _ensure_initial_document_revision(run_id, repo)
    current_versions = await repo.list_artifact_versions(run_id, revision_id=current.id)
    editable_names = {
        version.logical_name
        for version in current_versions
        if version.media_type
        in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    }
    if name not in editable_names:
        raise HTTPException(status_code=404, detail="Editable artifact not found")
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 120:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 1-120 characters")
    row = await repo.create_document_revision(
        run_id,
        target_artifact_name=name,
        feedback=body.feedback,
        base_revision_id=body.base_revision_id or current.id,
        parent_revision_id=body.parent_revision_id,
        idempotency_key=idempotency_key,
        channel=body.channel,
        conversation_id=body.conversation_id,
    )
    if row.status == RevisionStatus.QUEUED.value:
        await _enqueue_document_revision(request, repo, row)
    return await _document_revision_view(repo, row)


@app.get(
    "/v1/research-runs/{run_id}/revisions",
    response_model=list[DocumentRevisionView],
    dependencies=[Depends(resolve_principal)],
)
async def list_document_revisions(
    run_id: str, repo: Repository = Depends(repository)
) -> list[DocumentRevisionView]:
    await _ensure_initial_document_revision(run_id, repo)
    return [
        await _document_revision_view(repo, row)
        for row in await repo.list_document_revisions(run_id)
    ]


@app.get(
    "/v1/research-runs/{run_id}/revisions/{revision_id}",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def get_document_revision(
    run_id: str, revision_id: str, repo: Repository = Depends(repository)
) -> DocumentRevisionView:
    return await _document_revision_view(
        repo, await repo.get_document_revision(run_id, revision_id)
    )


@app.get(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/diff",
    dependencies=[Depends(resolve_principal)],
)
async def get_document_revision_diff(
    run_id: str, revision_id: str, repo: Repository = Depends(repository)
) -> dict:
    row = await repo.get_document_revision(run_id, revision_id)
    if row.parent_revision_id is None:
        return {"revision_id": row.id, "changes": [], "format_overrides": {}}
    parent = await repo.get_document_revision(run_id, row.parent_revision_id)
    before = editable_targets(parent.report_model)
    after = editable_targets(row.report_model) if row.report_model else dict(before)
    operations = (row.edit_plan or {}).get("operations") or []
    if not row.report_model:
        for operation in operations:
            target = str(operation.get("target") or "")
            if target in after and operation.get("replacement") is not None:
                after[target] = str(operation["replacement"])
    targets = list(dict.fromkeys(str(item.get("target") or "") for item in operations))
    if row.report_model:
        targets.extend(target for target in before if before.get(target) != after.get(target))
    changes = [
        {
            "target": target,
            "before": before.get(target),
            "after": after.get(target),
        }
        for target in dict.fromkeys(targets)
        if target and before.get(target) != after.get(target)
    ]
    return {
        "revision_id": row.id,
        "parent_revision_id": parent.id,
        "changes": changes,
        "format_overrides": row.format_overrides or {},
    }


@app.post(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/feedback",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def add_document_revision_feedback(
    run_id: str,
    revision_id: str,
    body: RevisionFeedbackRequest,
    request: Request,
    repo: Repository = Depends(repository),
) -> DocumentRevisionView:
    row = await repo.get_document_revision(run_id, revision_id)
    if row.status not in {
        RevisionStatus.AWAITING_FEEDBACK.value,
        RevisionStatus.CLARIFYING.value,
        RevisionStatus.AWAITING_PLAN_APPROVAL.value,
    }:
        raise RevisionConflict(f"Revision is not awaiting feedback: {row.status}")
    feedback = body.feedback.strip()
    if row.feedback:
        feedback = f"{row.feedback}\n\nClarification: {feedback}"
    row = await repo.update_document_revision(
        run_id,
        revision_id,
        feedback=feedback,
        edit_plan=None,
        status=RevisionStatus.QUEUED.value,
        channel_state={},
        error=None,
    )
    await _enqueue_document_revision(request, repo, row)
    return await _document_revision_view(repo, row)


@app.post(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/approve-plan",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def approve_document_revision_plan(
    run_id: str,
    revision_id: str,
    request: Request,
    repo: Repository = Depends(repository),
) -> DocumentRevisionView:
    row = await repo.get_document_revision(run_id, revision_id)
    if row.status != RevisionStatus.AWAITING_PLAN_APPROVAL.value or not row.edit_plan:
        raise RevisionConflict(f"Revision plan cannot be approved in {row.status}")
    plan = RevisionPlan.model_validate(row.edit_plan)
    if plan.classification == "research_extension_required":
        raise RevisionConflict("Feedback requires a new research run")
    row = await repo.update_document_revision(
        run_id,
        revision_id,
        status=RevisionStatus.QUEUED.value,
        channel_state={},
        error=None,
    )
    await _enqueue_document_revision(request, repo, row)
    return await _document_revision_view(repo, row)


@app.post(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/accept",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def accept_document_revision(
    run_id: str, revision_id: str, repo: Repository = Depends(repository)
) -> DocumentRevisionView:
    row = await repo.accept_document_revision(run_id, revision_id)
    await repo.event(
        run_id,
        "document_revision_accepted",
        {"revision_id": revision_id, "revision_number": row.revision_number},
    )
    return await _document_revision_view(repo, row)


@app.post(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/restore",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def restore_document_revision(
    run_id: str, revision_id: str, repo: Repository = Depends(repository)
) -> DocumentRevisionView:
    row = await repo.restore_document_revision(run_id, revision_id)
    await repo.event(
        run_id,
        "document_revision_restore_prepared",
        {"revision_id": row.id, "source_revision_id": revision_id},
    )
    return await _document_revision_view(repo, row)


@app.post(
    "/v1/research-runs/{run_id}/revisions/{revision_id}/cancel",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def cancel_document_revision(
    run_id: str,
    revision_id: str,
    request: Request,
    repo: Repository = Depends(repository),
) -> DocumentRevisionView:
    row = await repo.get_document_revision(run_id, revision_id)
    if row.status in {
        RevisionStatus.ACCEPTED.value,
        RevisionStatus.SUPERSEDED.value,
        RevisionStatus.CANCELLED.value,
        RevisionStatus.FAILED.value,
    }:
        raise RevisionConflict(f"Revision cannot be cancelled in {row.status}")
    row = await repo.update_document_revision(
        run_id, revision_id, status=RevisionStatus.CANCELLED.value
    )
    redis = request.app.state.redis
    if redis is not None:
        await cancel_queued_revision_job(redis, revision_id)
    return await _document_revision_view(repo, row)


@app.get(
    "/v1/research-runs/{run_id}/artifact-versions",
    response_model=list[ArtifactVersionView],
    dependencies=[Depends(resolve_principal)],
)
async def list_artifact_versions(
    run_id: str, repo: Repository = Depends(repository)
) -> list[ArtifactVersionView]:
    await _ensure_initial_document_revision(run_id, repo)
    return [_artifact_version_view(row) for row in await repo.list_artifact_versions(run_id)]


async def _artifact_version_response(row) -> Response:
    data = await ObjectStore(get_settings()).get(row.object_key)
    return Response(
        data,
        media_type=row.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{row.logical_name}"',
            "X-Run-Id": row.run_id,
            "X-Revision-Id": row.revision_id,
            "X-Revision-Number": str(row.revision_number),
            "X-Artifact-Version-Id": row.id,
        },
    )


@app.get(
    "/v1/research-runs/{run_id}/artifact-versions/{version_id}",
    dependencies=[Depends(resolve_principal)],
)
async def download_artifact_version(
    run_id: str, version_id: str, repo: Repository = Depends(repository)
) -> Response:
    return await _artifact_version_response(await repo.get_artifact_version(run_id, version_id))


@app.get(
    "/v1/document-revisions/active",
    response_model=DocumentRevisionView | None,
    dependencies=[Depends(resolve_principal)],
)
async def active_document_revision(
    channel: str,
    conversation_id: str,
    repo: Repository = Depends(repository),
) -> DocumentRevisionView | None:
    row = await repo.active_document_revision(
        channel=channel, conversation_id=conversation_id
    )
    return await _document_revision_view(repo, row) if row else None


@app.get(
    "/v1/document-revisions/{revision_id}",
    response_model=DocumentRevisionView,
    dependencies=[Depends(resolve_principal)],
)
async def get_document_revision_by_id(
    revision_id: str, repo: Repository = Depends(repository)
) -> DocumentRevisionView:
    return await _document_revision_view(
        repo, await repo.get_document_revision_by_id(revision_id)
    )


@app.get("/v1/artifact-versions/{version_id}", dependencies=[Depends(resolve_principal)])
async def download_artifact_version_by_id(
    version_id: str, repo: Repository = Depends(repository)
) -> Response:
    return await _artifact_version_response(await repo.get_artifact_version_by_id(version_id))


@app.get(
    "/v1/research-runs/{run_id}/artifacts",
    response_model=list[ArtifactView],
    dependencies=[Depends(resolve_principal)],
)
async def list_artifacts(run_id: str, repo: Repository = Depends(repository)) -> list[ArtifactView]:
    await _required_run(run_id, repo)
    return [
        ArtifactView(
            name=a.name,
            media_type=a.media_type,
            size_bytes=a.size_bytes,
            download_url=f"/v1/research-runs/{run_id}/artifacts/{a.name}",
        )
        for a in await repo.list_artifacts(run_id)
    ]


@app.get("/v1/research-runs/{run_id}/artifacts/{name}", dependencies=[Depends(resolve_principal)])
async def download_artifact(
    run_id: str, name: str, repo: Repository = Depends(repository)
) -> Response:
    artifacts = {a.name: a for a in await repo.list_artifacts(run_id)}
    artifact = artifacts.get(name)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    data = await ObjectStore(get_settings()).get(artifact.object_key)
    return Response(
        data,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
    )


@app.get(
    "/v1/research-runs/{run_id}/delivery/{mode}",
    dependencies=[Depends(resolve_principal)],
)
async def download_delivery(
    run_id: str,
    mode: DeliveryMode,
    repo: Repository = Depends(repository),
) -> Response:
    bundle_by_mode = {
        DeliveryMode.RAW: "raw_bundle.zip",
        DeliveryMode.RESULT: "result_bundle.zip",
        DeliveryMode.BOTH: "research_bundle.zip",
    }
    return await download_artifact(run_id, bundle_by_mode[mode], repo)


@app.get("/v1/connectors", dependencies=[Depends(resolve_principal)])
async def list_connectors(request: Request) -> list[dict]:
    registry = build_registry(get_settings(), request.app.state.http)
    health = [h.model_dump(mode="json") for h in await registry.health()]
    health.append(paperqa2_health(get_settings()))
    return health


@app.get("/v1/parsers", dependencies=[Depends(resolve_principal)])
async def list_parsers() -> list[dict]:
    registry = build_parser_registry()
    return [health.model_dump(mode="json") for health in registry.health()]


@app.get("/v1/zotero/collections", dependencies=[Depends(resolve_principal)])
async def list_zotero_collections(mode: str, request: Request) -> list[dict]:
    if mode not in {"local", "web"}:
        raise HTTPException(status_code=422, detail="mode must be local or web")
    connector = build_registry(get_settings(), request.app.state.http).get(f"zotero_{mode}")
    health = await connector.health()
    if not health.enabled or not health.healthy:
        raise HTTPException(status_code=503, detail=health.detail)
    return await connector.list_collections()


@app.post(
    "/v1/zotero/sync",
    response_model=ZoteroSyncResult,
    dependencies=[Depends(resolve_principal)],
)
async def sync_zotero(
    body: ZoteroSyncRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> ZoteroSyncResult:
    try:
        return await ZoteroSyncService(
            get_settings(), session, request.app.state.http, actor=principal
        ).sync(body)
    except ActorRequired as exc:
        raise HTTPException(
            status_code=400,
            detail="This credential cannot own a run; use a user API key or send X-Actor-User",
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/v1/research-runs/{run_id}/citation-graph",
    dependencies=[Depends(resolve_principal)],
)
async def citation_graph(run_id: str, repo: Repository = Depends(repository)) -> dict:
    await _required_run(run_id, repo)
    sources = {source.id: source for source in await repo.list_sources(run_id)}
    relations = await repo.list_source_relations(run_id)
    return {
        "nodes": [
            {
                "id": source.id,
                "title": source.title,
                "persistent_id": source.persistent_id,
                "connector_id": source.connector_id,
            }
            for source in sources.values()
        ],
        "edges": [
            {
                "source_id": relation.source_id,
                "target_source_id": relation.target_source_id,
                "target_persistent_id": relation.target_persistent_id,
                "relation_type": relation.relation_type,
                "provider": relation.provider,
                "metadata": relation.metadata_json,
            }
            for relation in relations
        ],
    }


@app.get(
    "/v1/research-runs/{run_id}/academic-coverage",
    dependencies=[Depends(resolve_principal)],
)
async def academic_coverage(run_id: str, repo: Repository = Depends(repository)) -> dict:
    await _required_run(run_id, repo)
    academic = [
        source
        for source in await repo.list_sources(run_id)
        if source.family == SourceFamily.ACADEMIC.value
    ]
    providers = {
        provider
        for source in academic
        for provider in (source.metadata_json.get("provider_snapshots") or {})
    }
    versions = await repo.list_source_versions(run_id)
    full_text_source_ids = {
        source.id
        for source, version in versions
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
        "retracted": sum(bool(source.metadata_json.get("is_retracted")) for source in academic),
        "citation_edges": len(await repo.list_source_relations(run_id)),
    }


@app.post("/v1/corpus/search", dependencies=[Depends(resolve_principal)])
async def search_local_corpus(
    body: CorpusSearchRequest,
    request: Request,
    repo: Repository = Depends(repository),
) -> list[dict]:
    passages = await repo.list_corpus_passages(exclude_run_id="", limit=5000)
    if not passages:
        return []
    try:
        vectors = await EmbeddingClient(get_settings(), request.app.state.http).embed([body.query])
    except Exception:
        vectors = [[]]
    selected = retrieve_passages(passages, [body.query], vectors, per_question=body.top_k)[
        : body.top_k
    ]
    source_metadata = await repo.source_metadata_for_versions(
        list({passage.source_version_id for passage in selected})
    )
    return [
        {
            "passage_id": passage.id,
            "source_version_id": passage.source_version_id,
            "section_path": passage.section_path,
            "page_number": passage.page_number,
            "start_char": passage.start_char,
            "end_char": passage.end_char,
            "language": passage.language,
            "document_type": passage.document_type,
            "score": passage.retrieval_score,
            "text": passage.text,
            "source": source_metadata.get(passage.source_version_id, {}),
        }
        for passage in selected
    ]


@app.post("/v1/connectors/{connector_id}/test", dependencies=[Depends(resolve_principal)])
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
