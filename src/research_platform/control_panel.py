from __future__ import annotations

import asyncio
import ctypes
import ipaddress
import json
import os
import re
import secrets
import socket
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import psutil
import uvicorn
from arq.constants import default_queue_name, health_check_key_suffix, in_progress_key_prefix
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from redis.asyncio import Redis
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import Principal, verify_secret
from .capacity import measure, plan_capacity
from .config import get_settings
from .control_panel_auth import (
    audit,
    clear_session_cookie,
    client_key,
    csrf_token,
    issue_session_cookie,
    login_redirect,
    optional_principal,
    record_failure,
    record_success,
    require_admin,
    require_admin_csrf,
    require_csrf,
    require_user,
    throttled,
)
from .control_panel_metrics import (
    connector_operations,
    llm_summary,
    pipeline_flow,
    pipeline_progress,
    query_branch_summary,
    serialize_event,
    source_funnel,
    stage_timeline,
)
from .control_panel_ui import CONTROL_PANEL_HTML, LOGIN_HTML
from .db import (
    ArtifactRow,
    CheckpointRow,
    ClaimRow,
    EventRow,
    EvidenceRow,
    ResearchRunRow,
    SessionLocal,
    SourceRow,
)
from .hardware_telemetry import SAMPLE_EVENT
from .identity import (
    authenticate,
    format_link_code,
    get_user,
    issue_api_key,
    issue_telegram_link_code,
    list_api_keys,
    revoke_api_key,
    set_password,
    telegram_ids_for,
    unlink_telegram,
)
from .repository import ACTIVE_RUN_STATUSES, Repository
from .schemas import RunStatus
from .version import VERSION

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
SCRIPT_DIR = ROOT / "scripts"
CONTROL_TOKEN = secrets.token_urlsafe(32)
MANAGED_SERVICES = ("api", "worker", "mcp", "telegram")
LOG_SERVICES = {*MANAGED_SERVICES, "control-panel"}
# The panel's own service names predate the compose file, which spells two of them
# differently. Keep the panel-facing names so the UI labels and log routes stay stable.
DOCKER_SERVICES = {
    "api": "api",
    "worker": "worker",
    "mcp": "mcp-gateway",
    "telegram": "telegram-bot",
}
# One definition, shared with the repository's team-activity query. Two copies would
# drift, and the drift would be invisible: the panel would file a run under "recent"
# while the queue view still counted it as pressure on the GPU.
ACTIVE_STATUSES = ACTIVE_RUN_STATUSES
TERMINAL_STATUSES = {
    RunStatus.CANCELLED.value,
    RunStatus.COMPLETED.value,
    RunStatus.COMPLETED_INCOMPLETE.value,
    RunStatus.FAILED.value,
}

action_lock = asyncio.Lock()
action_state: dict[str, Any] = {
    "busy": False,
    "action": None,
    "started_at": None,
    "last_error": None,
}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


class ControlPanelNetworkGuard:
    """Allow the panel only from loopback or explicitly configured office CIDRs."""

    def __init__(self, app, allowed_networks: list[str] | tuple[str, ...] = ()):
        self.app = app
        self.allowed_networks = tuple(
            ipaddress.ip_network(network, strict=False) for network in allowed_networks
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            client_host = (scope.get("client") or ("", 0))[0]
            allowed = client_host == "testclient"
            if not allowed:
                try:
                    address = ipaddress.ip_address(client_host)
                    allowed = address.is_loopback or any(
                        address in network for network in self.allowed_networks
                    )
                except ValueError:
                    allowed = False
            if not allowed:
                response = PlainTextResponse("Office network access denied", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        import os

        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _native_processes() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for service in MANAGED_SERVICES:
        pid_file = LOG_DIR / f"{service}.pid"
        pid: int | None = None
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                pid = None
        running = bool(pid and _pid_alive(pid))
        result[service] = {
            "running": running,
            "pid": pid,
            "detail": f"PID {pid}" if running else "",
        }
    return result


async def _docker_processes() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {
        service: {"running": False, "pid": None, "detail": ""} for service in MANAGED_SERVICES
    }
    return_code, output = await _run_compose("ps", "--format", "json", "--all", log=False)
    if return_code:
        return result
    by_compose_name = {value: key for key, value in DOCKER_SERVICES.items()}
    # Compose emits one JSON object per line, not a JSON array.
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        service = by_compose_name.get(str(row.get("Service", "")))
        if not service:
            continue
        result[service] = {
            "running": str(row.get("State", "")) == "running",
            "pid": None,
            "detail": str(row.get("Status") or row.get("State") or ""),
        }
    return result


async def _service_processes() -> dict[str, dict[str, Any]]:
    if get_settings().control_panel_deployment == "docker":
        return await _docker_processes()
    return _native_processes()


async def _queue_snapshot() -> dict[str, Any]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
        rows = await redis.zrange(default_queue_name, 0, -1, withscores=True)
        health_key = f"{default_queue_name}{health_check_key_suffix}"
        heartbeat, heartbeat_ttl = await asyncio.gather(
            redis.get(health_key), redis.ttl(health_key)
        )
        jobs = []
        for position, (job_id, score) in enumerate(rows, start=1):
            running = bool(await redis.exists(f"{in_progress_key_prefix}{job_id}"))
            run_id = job_id.removeprefix("run:") if job_id.startswith("run:") else None
            jobs.append(
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "position": position,
                    "running": running,
                    "score": score,
                }
            )
        return {
            "available": True,
            "depth": len(rows),
            "waiting": sum(not item["running"] for item in jobs),
            "running": sum(item["running"] for item in jobs),
            "heartbeat": heartbeat,
            "heartbeat_ttl_seconds": heartbeat_ttl,
            "jobs": jobs,
        }
    except Exception as exc:
        return {
            "available": False,
            "depth": 0,
            "waiting": 0,
            "running": 0,
            "heartbeat": None,
            "heartbeat_ttl_seconds": -2,
            "jobs": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        await redis.aclose()


def _may_see(run: ResearchRunRow, principal: Principal) -> bool:
    """Admins see every run; everyone else sees the ones they own.

    A run with no owner is admin-only, so rows that predate ownership -- or any future
    path that forgets to set one -- hide instead of leaking.
    """
    if principal.is_admin:
        return True
    return run.owner_id is not None and run.owner_id == principal.user_id


async def _run_snapshot(
    queue: dict[str, Any], principal: Principal
) -> dict[str, list[dict[str, Any]]]:
    queue_positions = {
        item["run_id"]: item["position"]
        for item in queue["jobs"]
        if item["run_id"] and not item["running"]
    }
    async with SessionLocal() as session:
        # Straight to the database rather than through the API, so the ownership filter
        # has to be applied here too -- this is the second door the panel reads through.
        statement = select(ResearchRunRow).order_by(ResearchRunRow.created_at.desc())
        if not principal.is_admin:
            statement = statement.where(ResearchRunRow.owner_id == principal.user_id)
        rows = list(await session.scalars(statement.limit(60)))
        # The one cross-owner read, taken through the repository rather than repeated as
        # a query here: the redaction has to have a single implementation or the second
        # copy is the one that eventually returns a title.
        team = await Repository(session, actor=principal).list_team_activity(
            queue_positions=queue_positions
        )
    serialized = []
    for row in rows:
        protocol = row.protocol or {}
        serialized.append(
            {
                "id": row.id,
                "status": row.status,
                "current_stage": row.current_stage,
                "title": protocol.get("title") or "İsimsiz araştırma",
                # What the user typed: the pipeline rewrites primary_question into English
                # so the research side speaks one language, but the list should still show
                # the person their own question.
                "question": protocol.get("original_question")
                or protocol.get("primary_question")
                or "",
                "output_mode": protocol.get("output_mode") or "both",
                "round_number": row.round_number,
                "sources_count": row.sources_count,
                "claims_count": row.claims_count,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "error": row.error,
                "coverage": row.coverage or {},
                "elapsed_seconds": round(
                    max(0.0, (row.updated_at - row.created_at).total_seconds()),
                    2,
                )
                if row.created_at and row.updated_at
                else 0.0,
                "queue_position": queue_positions.get(row.id),
                "priority": row.priority,
                # A run that stopped on its own reads as a mystery unless the panel can
                # say the scheduler did it to make room for an urgent one.
                "preempted_at": row.preempted_at.isoformat() if row.preempted_at else None,
                "progress_percent": pipeline_progress(row.current_stage, row.status),
            }
        )
    return {
        "active": [item for item in serialized if item["status"] in ACTIVE_STATUSES],
        "recent": [item for item in serialized if item["status"] in TERMINAL_STATUSES][:20],
        "team": [asdict(entry) for entry in team],
    }


async def _external_health() -> dict[str, Any]:
    settings = get_settings()
    result: dict[str, Any] = {"api": None, "ollama": None}
    async with httpx.AsyncClient(timeout=2.5) as client:
        try:
            response = await client.get(f"{settings.research_api_url.rstrip('/')}/health")
            result["api"] = response.json() if response.is_success else {"status": "degraded"}
        except Exception:
            result["api"] = {"status": "unavailable", "checks": {}}
        try:
            response = await client.get(f"{settings.ollama_url.rstrip('/')}/api/ps")
            models = response.json().get("models", []) if response.is_success else []
            result["ollama"] = {
                "status": "ok" if response.is_success else "degraded",
                "models": [
                    {
                        "name": model.get("name") or model.get("model"),
                        "size_vram": model.get("size_vram", 0),
                        "context_length": (model.get("details") or {}).get("context_length"),
                    }
                    for model in models
                ],
            }
        except Exception:
            result["ollama"] = {"status": "unavailable", "models": []}
    return result


async def _gpu_snapshot() -> list[dict[str, Any]]:
    command = (
        "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit"
    )
    try:
        process = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            f"--query-gpu={command}",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=3)
        if process.returncode:
            return []
    except (FileNotFoundError, TimeoutError):
        return []
    output = []

    def number(value: str) -> float | None:
        try:
            return float(value)
        except ValueError:
            return None

    for line in stdout.decode("utf-8", errors="replace").splitlines():
        values = [value.strip() for value in line.split(",")]
        if len(values) != 8:
            continue
        try:
            output.append(
                {
                    "index": int(values[0]),
                    "name": values[1],
                    "utilization_percent": number(values[2]),
                    "memory_used_mb": number(values[3]),
                    "memory_total_mb": number(values[4]),
                    "temperature_c": number(values[5]),
                    "power_draw_w": number(values[6]),
                    "power_limit_w": number(values[7]),
                }
            )
        except (TypeError, ValueError):
            continue
    return output


async def _system_telemetry() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(ROOT))
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory": {
            "used_gb": round((memory.total - memory.available) / 1024**3, 2),
            "total_gb": round(memory.total / 1024**3, 2),
            "percent": memory.percent,
        },
        "disk": {
            "used_gb": round(disk.used / 1024**3, 2),
            "total_gb": round(disk.total / 1024**3, 2),
            "percent": disk.percent,
        },
        "gpus": await _gpu_snapshot(),
        # How many runs the machine will carry right now and which resource decides it.
        # Without the reason the number is untunable: "3" says nothing about whether more
        # RAM or fewer background processes would change it.
        "capacity": plan_capacity(await measure()).as_dict(),
    }


def _publishable_queue(queue: dict[str, Any], principal: Principal) -> dict[str, Any]:
    """Strip run identifiers out of the ARQ queue listing for non-admins.

    Depth and wait counts are the point of the queue card and stay whole -- they are the
    same load the team view reports. The per-job ``run_id`` is different: it names other
    people's runs, the front end never reads it, and leaving it in would hand out
    uncontrolled exactly what :class:`TeamActivity` is careful to withhold.

    Called on the way out, after ``_run_snapshot`` has used the unredacted queue to
    resolve positions. Redacting earlier would cost every user their own queue position.
    """
    if principal.is_admin:
        return queue
    return {
        **queue,
        "jobs": [
            {key: value for key, value in job.items() if key not in ("job_id", "run_id")}
            for job in queue.get("jobs", [])
        ],
    }


async def build_status(principal: Principal) -> dict[str, Any]:
    processes = await _service_processes()
    try:
        queue = await asyncio.wait_for(_queue_snapshot(), timeout=4)
    except TimeoutError:
        queue = {
            "available": False,
            "depth": 0,
            "waiting": 0,
            "running": 0,
            "heartbeat": None,
            "heartbeat_ttl_seconds": -2,
            "jobs": [],
            "error": "Redis status timeout",
        }
    try:
        runs = await asyncio.wait_for(_run_snapshot(queue, principal), timeout=4)
        database = "ok"
    except Exception as exc:
        runs = {"active": [], "recent": [], "team": []}
        database = f"unavailable: {type(exc).__name__}"
    health, telemetry = await asyncio.gather(_external_health(), _system_telemetry())
    core_running = all(processes[name]["running"] for name in ("api", "worker", "mcp"))
    any_running = any(item["running"] for item in processes.values())
    overall = "running" if core_running else "degraded" if any_running else "stopped"
    return {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "processes": processes,
        "database": database,
        "queue": _publishable_queue(queue, principal),
        "runs": runs,
        "health": health,
        "telemetry": telemetry,
        "action": dict(action_state),
    }


async def _run_detail(run_id: str, principal: Principal) -> dict[str, Any]:
    async with SessionLocal() as session:
        run = await session.get(ResearchRunRow, run_id)
        # A run belonging to someone else reads as missing, exactly as it does over the
        # API. A distinct 403 here would confirm the id exists to a caller probing.
        if run is None or not _may_see(run, principal):
            raise HTTPException(status_code=404, detail="Araştırma bulunamadı")
        events = list(
            await session.scalars(
                select(EventRow)
                .where(EventRow.run_id == run_id, EventRow.event_type != SAMPLE_EVENT)
                .order_by(EventRow.id)
                .limit(5000)
            )
        )
        sources = list(
            await session.scalars(
                select(SourceRow)
                .where(SourceRow.run_id == run_id)
                .order_by(SourceRow.created_at.desc())
                .limit(500)
            )
        )
        claims = list(await session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id)))
        evidence = list(
            (
                await session.scalars(
                    select(EvidenceRow)
                    .join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
                    .where(ClaimRow.run_id == run_id)
                )
            ).all()
        )
        artifacts = list(
            await session.scalars(
                select(ArtifactRow).where(ArtifactRow.run_id == run_id).order_by(ArtifactRow.name)
            )
        )
        checkpoints = list(
            await session.scalars(
                select(CheckpointRow)
                .where(CheckpointRow.run_id == run_id)
                .order_by(CheckpointRow.created_at)
            )
        )
    claim_statuses: dict[str, int] = {}
    for claim in claims:
        claim_statuses[claim.status] = claim_statuses.get(claim.status, 0) + 1
    latest_quality: dict[str, Any] = {}
    for event in events:
        if event.event_type == "coverage_gaps":
            latest_quality = (event.payload or {}).get("discovery_quality", {}) or latest_quality
    created = run.created_at
    updated = run.updated_at
    elapsed = max(0.0, (updated - created).total_seconds()) if created and updated else 0.0
    return {
        "run": {
            "id": run.id,
            "status": run.status,
            "current_stage": run.current_stage,
            "round_number": run.round_number,
            "sources_count": run.sources_count,
            "claims_count": run.claims_count,
            "created_at": created.isoformat() if created else None,
            "updated_at": updated.isoformat() if updated else None,
            "elapsed_seconds": round(elapsed, 2),
            "error": run.error,
            "protocol": run.protocol or {},
            "coverage": run.coverage or {},
            "interaction": run.interaction,
            "hitl_history": run.hitl_history or [],
        },
        "timeline": stage_timeline(events, updated or datetime.now(timezone.utc)),
        "flow": pipeline_flow(
            events,
            current_stage=run.current_stage,
            status=run.status,
            round_number=run.round_number,
            now=updated or datetime.now(timezone.utc),
        ),
        "funnel": source_funnel(events, len(sources)),
        "quality": {**(run.coverage or {}), **latest_quality},
        "query_branches": query_branch_summary(events),
        "llm": llm_summary(events),
        "claim_summary": {
            "total": len(claims),
            "major": sum(claim.importance == "major" for claim in claims),
            "statuses": claim_statuses,
            "evidence_links": len(evidence),
        },
        "sources": [
            {
                "id": source.id,
                "title": source.title,
                "url": source.url,
                "family": source.family,
                "connector_id": source.connector_id,
                "persistent_id": source.persistent_id,
                "created_at": source.created_at.isoformat() if source.created_at else None,
                "admission_tier": (source.metadata_json or {}).get("admission_tier", "accept"),
                "discovery_method": (source.metadata_json or {}).get("discovery_method", "search"),
                "relevance_score": max(
                    _safe_float((source.metadata_json or {}).get("relevance_score")),
                    _safe_float((source.metadata_json or {}).get("content_relevance_score")),
                ),
                "query_branches": (source.metadata_json or {}).get("query_branches", []),
                "published_at": (source.metadata_json or {}).get("published_at"),
            }
            for source in sources
        ],
        "events": [serialize_event(event) for event in events[-150:]],
        "checkpoints": [
            {
                "stage": checkpoint.stage,
                "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
            }
            for checkpoint in checkpoints
        ],
        "artifacts": [
            {
                "name": artifact.name,
                "media_type": artifact.media_type,
                "size_bytes": artifact.size_bytes,
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            for artifact in artifacts
        ],
    }


async def _connector_snapshot() -> list[dict[str, Any]]:
    settings = get_settings()
    health_rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.research_api_url.rstrip('/')}/v1/connectors",
                headers={
                    "Authorization": (
                        f"Bearer {settings.service_token or settings.api_token}"
                    )
                },
            )
            if response.is_success:
                health_rows = response.json()
    except httpx.HTTPError:
        health_rows = []
    async with SessionLocal() as session:
        events = list(
            await session.scalars(
                select(EventRow)
                .where(
                    EventRow.event_type.in_(
                        (
                            "connector_metrics",
                            "connector_error",
                        )
                    )
                )
                .order_by(EventRow.id.desc())
                .limit(2500)
            )
        )
        sources = list(
            await session.scalars(
                select(SourceRow).order_by(SourceRow.created_at.desc()).limit(5000)
            )
        )
    operations = connector_operations(list(reversed(events)))
    accepted_counts: dict[str, int] = {}
    for source in sources:
        accepted_counts[source.connector_id] = accepted_counts.get(source.connector_id, 0) + 1
    ids = {str(row.get("id")) for row in health_rows} | set(operations)
    health_by_id = {str(row.get("id")): row for row in health_rows}
    output = []
    for connector_id in sorted(ids):
        health = health_by_id.get(connector_id, {})
        metrics = operations.get(connector_id, {})
        output.append(
            {
                "id": connector_id,
                "family": health.get("family", "unknown"),
                "enabled": health.get("enabled", False),
                "healthy": health.get("healthy", False),
                "detail": health.get("detail", "Health verisi alınamadı"),
                "capabilities": health.get("capabilities", []),
                "requires_credentials": health.get("requires_credentials", False),
                "missing_credentials": health.get("missing_credentials", []),
                "accepted_sources": accepted_counts.get(connector_id, 0),
                **{
                    "calls": 0,
                    "successes": 0,
                    "success_rate": 0.0,
                    "result_count": 0,
                    "errors": 0,
                    "error_types": {},
                    "average_latency_seconds": 0.0,
                    "p95_latency_seconds": 0.0,
                    "last_success_at": None,
                    "last_error_at": None,
                    **metrics,
                },
            }
        )
    return output


async def _api_request(
    method: str,
    path: str,
    principal: Principal,
    *,
    timeout: float = 15,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    """Call the research API as the signed-in user.

    The panel holds a service credential, not the user's, so it names who it is acting
    for. The API only honours that header once the service token itself verifies --
    see resolve_principal in api.py.
    """
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {settings.service_token or settings.api_token}",
        "X-Actor-User": principal.user_id or "",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.request(
            method,
            f"{settings.research_api_url.rstrip('/')}{path}",
            headers=headers,
            json=json_body,
        )


def _compose_environment() -> dict[str, str]:
    """
    The panel is launched with an office/native env file loaded into its own process
    environment, so DATABASE_URL and friends point at published host ports. Compose
    resolves ${VAR} from the shell before the project .env file, so inheriting that
    environment would push host addresses into the containers and migrations would try
    to reach postgres on 127.0.0.1:5433. Drop every key the project .env defines and let
    compose resolve them itself.
    """
    environment = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match:
                environment.pop(match.group(1), None)
    return environment


async def _run_compose(*args: str, log: bool = True) -> tuple[int, str]:
    """Run a docker compose command from the project root and capture its output."""
    process = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        *args,
        cwd=str(ROOT),
        env=_compose_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    output = stdout.decode("utf-8", errors="replace")
    if log:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "control-panel-actions.log").open("ab") as handle:
            marker = f"\n[{datetime.now(timezone.utc).isoformat()}] docker compose {' '.join(args)}\n"
            handle.write(marker.encode("utf-8"))
            handle.write(stdout)
    return process.returncode or 0, output


def _compose_app_services() -> list[str]:
    """Compose services the panel supervises, mirroring start_native.ps1's telegram rule."""
    services = [DOCKER_SERVICES[name] for name in ("api", "worker", "mcp")]
    if get_settings().telegram_bot_token:
        services.append(DOCKER_SERVICES["telegram"])
    return services


async def _run_compose_action(action: str) -> tuple[int, str]:
    services = _compose_app_services()
    # telegram-bot sits behind a compose profile, so "up" only reaches it when a bot
    # token is configured — the same condition start_native.ps1 applies natively.
    profile = ["--profile", "telegram"] if get_settings().telegram_bot_token else []
    if action == "stop":
        return await _run_compose(*profile, "stop", *services)
    if action == "restart":
        return await _run_compose(*profile, "restart", *services)
    return await _run_compose(*profile, "up", "-d")


async def _run_powershell(script: str) -> tuple[int, str]:
    log_path = LOG_DIR / "control-panel-actions.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as handle:
        marker = f"\n[{datetime.now(timezone.utc).isoformat()}] {script}\n"
        handle.write(marker.encode("utf-8"))
        handle.flush()
        process = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_DIR / script),
            cwd=str(ROOT),
            stdout=handle,
            stderr=asyncio.subprocess.STDOUT,
        )
        return_code = await process.wait()
    output = log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
    return return_code or 0, output


app = FastAPI(
    title="Research Platform Control Panel",
    version=VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
panel_settings = get_settings()
panel_networks = (
    panel_settings.control_panel_allowed_networks or panel_settings.mcp_allowed_networks
)
def _local_addresses() -> list[str]:
    """This machine's own IPv4 addresses, for the Host header check.

    A browser on the LAN sends ``Host: 10.0.10.179``, which is neither loopback nor the
    hostname, so TrustedHostMiddleware would reject it before any of the panel's own
    checks ran. Binding to a LAN address is therefore not enough on its own -- the
    address has to be trusted as a name too.
    """
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)
    except socket.gaierror:
        pass
    return addresses


app.add_middleware(ControlPanelNetworkGuard, allowed_networks=panel_networks)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "127.0.0.1",
        "localhost",
        "[::1]",
        "testserver",
        panel_settings.mcp_host,
        socket.gethostname(),
        # Explicit entries first (a reverse-proxy hostname, for instance), then the
        # machine's own addresses so a LAN client reaching it by IP is not turned away.
        *panel_settings.control_panel_allowed_hosts,
        *(_local_addresses() if panel_settings.control_panel_host != "127.0.0.1" else []),
    ],
)


def _secure_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/", response_class=HTMLResponse)
async def index(principal: Principal | None = Depends(optional_principal)):
    if principal is None:
        return login_redirect()
    # The CSRF token is derived from the session, so the page a user is served can only
    # drive actions as that user.
    page = CONTROL_PANEL_HTML.replace("__CONTROL_TOKEN__", csrf_token(principal)).replace(
        "__PLATFORM_VERSION__", VERSION
    )
    return _secure_headers(HTMLResponse(page))


@app.get("/login", response_class=HTMLResponse)
async def login_page(principal: Principal | None = Depends(optional_principal)):
    if principal is not None:
        return RedirectResponse(url="/", status_code=303)
    return _secure_headers(HTMLResponse(LOGIN_HTML.replace("__ERROR__", "")))


@app.post("/login")
async def login_submit(request: Request):
    key = client_key(request)
    wait_seconds = throttled(key)
    if wait_seconds:
        return _secure_headers(
            HTMLResponse(
                LOGIN_HTML.replace(
                    "__ERROR__",
                    f'<div class="error">Çok fazla başarısız deneme. '
                    f"{wait_seconds} saniye sonra tekrar deneyin.</div>",
                ),
                status_code=429,
            )
        )
    form = await request.form()
    email = str(form.get("email") or "")
    password = str(form.get("password") or "")
    async with SessionLocal() as session:
        user = await authenticate(session, email, password)
        if user is None:
            record_failure(key, email)
            # One message for a wrong password, an unknown address and a disabled
            # account alike, so the form cannot be used to enumerate accounts.
            return _secure_headers(
                HTMLResponse(
                    LOGIN_HTML.replace(
                        "__ERROR__",
                        '<div class="error">E-posta veya parola hatalı.</div>',
                    ),
                    status_code=401,
                )
            )
        record_success(key, user.id)
        response = RedirectResponse(url="/", status_code=303)
        issue_session_cookie(response, user.id, user.token_version)
        return response


@app.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "research-control-panel", "version": VERSION}


@app.get("/api/session")
async def session_info(principal: Principal = Depends(require_user)) -> dict[str, Any]:
    """Who the panel thinks you are -- drives the header badge and admin-only controls."""
    async with SessionLocal() as session:
        user = await get_user(session, principal.user_id or "")
    return {
        "user_id": principal.user_id,
        "email": user.email if user else None,
        "display_name": user.display_name if user else None,
        "role": principal.role,
        "is_admin": principal.is_admin,
    }


@app.get("/api/status")
async def status(principal: Principal = Depends(require_user)) -> dict[str, Any]:
    return await build_status(principal)


@app.get("/api/runs/{run_id}/detail")
async def run_detail(run_id: str, principal: Principal = Depends(require_user)) -> dict[str, Any]:
    return await _run_detail(run_id, principal)


@app.get("/api/connectors")
async def connectors(_: Principal = Depends(require_user)) -> list[dict[str, Any]]:
    return await _connector_snapshot()


@app.post("/api/connectors/{connector_id}/test")
async def connector_test(
    connector_id: str, principal: Principal = Depends(require_admin_csrf)
) -> dict[str, Any]:
    """Reaches out to a third-party service with the installation's credentials."""
    try:
        response = await _api_request(
            "POST", f"/v1/connectors/{connector_id}/test", principal, timeout=45
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        raise HTTPException(status_code=response.status_code, detail=response.text[:500])
    return response.json()


@app.get("/api/runs/{run_id}/artifacts/{artifact_name}")
async def artifact_download(
    run_id: str, artifact_name: str, principal: Principal = Depends(require_user)
) -> Response:
    """Report downloads carry the acting user, so the API applies the ownership check."""
    try:
        response = await _api_request(
            "GET",
            f"/v1/research-runs/{run_id}/artifacts/{artifact_name}",
            principal,
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Artifact indirilemedi") from exc
    if not response.is_success:
        raise HTTPException(status_code=response.status_code, detail=response.text[:500])
    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{artifact_name}"'},
    )


@app.post("/api/system/{action}")
async def system_action(
    action: Literal["start", "stop", "restart"],
    _: Principal = Depends(require_admin_csrf),
) -> dict[str, Any]:
    """Starts and stops the whole stack, so it is an administrator action.

    Before sessions existed this sat behind the same token as everything else, which
    would have meant any signed-in user could stop the worker mid-run.
    """
    if action_lock.locked():
        raise HTTPException(status_code=409, detail="Başka bir sistem işlemi devam ediyor")
    async with action_lock:
        action_state.update(
            {
                "busy": True,
                "action": action,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
            }
        )
        docker = get_settings().control_panel_deployment == "docker"
        try:
            if docker:
                return_code, output = await _run_compose_action(action)
                failure = output or f"docker compose exit code {return_code}"
            else:
                script = "stop_native.ps1" if action == "stop" else "start_office_server.ps1"
                return_code, output = await _run_powershell(script)
                failure = output or f"PowerShell exit code {return_code}"
            if return_code:
                action_state["last_error"] = failure
                raise HTTPException(status_code=500, detail=action_state["last_error"])
            return {"ok": True, "action": action, "message": output.strip()}
        finally:
            action_state.update({"busy": False, "action": None})


@app.post("/api/runs/{run_id}/priority")
async def run_priority(
    run_id: str, body: dict[str, Any], principal: Principal = Depends(require_csrf)
) -> dict[str, Any]:
    """Move a waiting run between the queue bands.

    Declared before the generic action route so ``priority`` is not swallowed by its
    Literal, which would answer 422 instead of doing the thing.
    """
    try:
        response = await _api_request(
            "POST",
            f"/v1/research-runs/{run_id}/priority",
            principal,
            timeout=10,
            json_body={"priority": body.get("priority")},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        detail = response.json().get("detail", response.text[:500])
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.post("/api/runs/{run_id}/{action}")
async def run_action(
    run_id: str,
    action: Literal["pause", "resume", "cancel"],
    principal: Principal = Depends(require_csrf),
) -> dict[str, Any]:
    try:
        response = await _api_request(
            "POST", f"/v1/research-runs/{run_id}/{action}", principal, timeout=10
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        detail = response.json().get("detail", response.text[:500])
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.post("/api/runs/{run_id}/respond")
async def run_respond(
    run_id: str, body: dict[str, Any], principal: Principal = Depends(require_csrf)
) -> dict[str, Any]:
    try:
        response = await _api_request(
            "POST", f"/v1/research-runs/{run_id}/respond", principal, timeout=10, json_body=body
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        detail = response.json().get("detail", response.text[:500])
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.post("/api/runs")
async def create_run(
    body: dict[str, Any], principal: Principal = Depends(require_csrf)
) -> dict[str, Any]:
    """Start a research run owned by the signed-in user.

    The panel had no way to start a run before -- they arrived through the API, the
    bot or Langflow. That left the panel unable to answer "whose run is this?" for
    anything it displayed. Creating them here makes the session user the owner
    directly, which is the cleanest binding of the four surfaces.
    """
    try:
        response = await _api_request(
            "POST", "/v1/research-runs", principal, timeout=30, json_body=body
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        detail = response.json().get("detail", response.text[:500])
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.get("/api/keys")
async def list_keys(principal: Principal = Depends(require_user)) -> list[dict[str, Any]]:
    """API keys let a user reach the platform from scripts, MCP and Langflow as themselves."""
    async with SessionLocal() as session:
        rows = await list_api_keys(session, principal.user_id or "")
    return [
        {
            "id": row.id,
            "name": row.name,
            "prefix": row.prefix,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        }
        for row in rows
    ]


@app.post("/api/keys")
async def create_key(
    body: dict[str, Any], principal: Principal = Depends(require_csrf)
) -> dict[str, Any]:
    async with SessionLocal() as session:
        full_key, row = await issue_api_key(
            session, user_id=principal.user_id or "", name=str(body.get("name") or "panel")
        )
    audit.info("api key issued user=%s prefix=%s", principal.user_id, row.prefix)
    # The only time the secret is ever readable. It is not recoverable afterwards.
    return {"id": row.id, "name": row.name, "prefix": row.prefix, "key": full_key}


@app.delete("/api/keys/{key_id}")
async def delete_key(key_id: str, principal: Principal = Depends(require_csrf)) -> dict[str, Any]:
    async with SessionLocal() as session:
        revoked = await revoke_api_key(session, user_id=principal.user_id or "", key_id=key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Anahtar bulunamadı")
    return {"ok": True}


@app.post("/api/account/password")
async def change_password(
    body: dict[str, Any],
    request: Request,
    principal: Principal = Depends(require_csrf),
) -> Response:
    """Let a signed-in user replace their own password.

    The current password is required. Without it this endpoint would *reduce* security
    rather than add convenience: the panel is served over plain HTTP on the LAN, so
    someone who captured a session cookie could turn a borrowed session into permanent
    account takeover with one request.
    """
    key = client_key(request)
    wait_seconds = throttled(key)
    if wait_seconds:
        raise HTTPException(
            status_code=429,
            detail=f"Çok fazla başarısız deneme. {wait_seconds} saniye sonra tekrar deneyin.",
        )
    current_password = str(body.get("current_password") or "")
    new_password = str(body.get("new_password") or "")
    if not new_password:
        raise HTTPException(status_code=400, detail="Yeni parola boş olamaz")

    async with SessionLocal() as session:
        user = await get_user(session, principal.user_id or "")
        if user is None or not verify_secret(current_password, user.password_hash):
            record_failure(key)
            audit.warning("password change failed user=%s from=%s", principal.user_id, key)
            raise HTTPException(status_code=403, detail="Mevcut parola hatalı")
        await set_password(session, user, new_password)
        token_version = user.token_version

    record_success(key, principal.user_id or "")
    audit.info("password changed user=%s from=%s", principal.user_id, key)
    response = JSONResponse({"ok": True})
    # set_password bumps token_version, which invalidates every cookie this user holds --
    # including the one that just made this request. Re-issuing it keeps the caller signed
    # in while every other device is signed out, which is the behaviour people expect.
    issue_session_cookie(response, user.id, token_version)
    return response


@app.get("/api/telegram")
async def telegram_status(principal: Principal = Depends(require_user)) -> dict[str, Any]:
    async with SessionLocal() as session:
        linked = await telegram_ids_for(session, principal.user_id or "")
    return {"linked": linked, "bot_username": get_settings().telegram_bot_username}


@app.post("/api/telegram/link-code")
async def telegram_link_code(principal: Principal = Depends(require_csrf)) -> dict[str, Any]:
    """Issue a one-time code the user redeems from their own Telegram account.

    Replaces asking an administrator to run ``research-admin link-telegram``: holding a
    panel session already proves who they are, so the code just carries that proof across
    to Telegram. Single use and short-lived, because a leaked code would let someone bind
    *their* Telegram account to this user and act as them.
    """
    settings = get_settings()
    async with SessionLocal() as session:
        code = await issue_telegram_link_code(
            session,
            user_id=principal.user_id or "",
            ttl_seconds=settings.telegram_link_code_ttl_seconds,
        )
    audit.info("telegram link code issued user=%s", principal.user_id)
    deep_link = (
        f"https://t.me/{settings.telegram_bot_username}?start={code}"
        if settings.telegram_bot_username
        else None
    )
    return {
        "code": format_link_code(code),
        "command": f"/baglan {code}",
        "deep_link": deep_link,
        "expires_in_seconds": settings.telegram_link_code_ttl_seconds,
    }


@app.delete("/api/telegram")
async def telegram_unlink(principal: Principal = Depends(require_csrf)) -> dict[str, Any]:
    async with SessionLocal() as session:
        removed = await unlink_telegram(session, user_id=principal.user_id or "")
    audit.info("telegram unlinked user=%s removed=%s", principal.user_id, removed)
    return {"ok": True, "removed": removed}


@app.get("/api/logs/{service}", response_class=PlainTextResponse)
async def logs(service: str, _: Principal = Depends(require_admin)) -> PlainTextResponse:
    """Service logs mix every user's runs together, so they stay administrator-only."""
    if service not in LOG_SERVICES:
        raise HTTPException(status_code=404, detail="Bilinmeyen servis")
    # The panel itself always runs natively, so it keeps its file-based logs even when
    # the services it supervises are containers.
    if get_settings().control_panel_deployment == "docker" and service in DOCKER_SERVICES:
        return_code, output = await _run_compose(
            "logs", "--tail", "400", "--no-color", DOCKER_SERVICES[service], log=False
        )
        if return_code:
            return PlainTextResponse(output or "Container logu alınamadı.")
        return PlainTextResponse(output or "Log bulunamadı.")
    blocks = []
    for stream in ("stderr", "stdout"):
        path = LOG_DIR / f"{service}.{stream}.log"
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace")[-24_000:]
            blocks.append(f"--- {stream.upper()} ---\n{content or '(boş)'}")
    return PlainTextResponse("\n\n".join(blocks) if blocks else "Log bulunamadı.")


def run() -> None:
    settings = get_settings()
    networks = settings.control_panel_allowed_networks or settings.mcp_allowed_networks
    if settings.control_panel_host not in {"127.0.0.1", "localhost", "::1"} and not networks:
        raise RuntimeError("LAN control panel requires CONTROL_PANEL_ALLOWED_NETWORKS")
    uvicorn.run(
        "research_platform.control_panel:app",
        host=settings.control_panel_host,
        port=settings.control_panel_port,
        reload=False,
        access_log=False,
    )
