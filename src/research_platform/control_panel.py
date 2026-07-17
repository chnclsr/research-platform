from __future__ import annotations

import asyncio
import ctypes
import ipaddress
import secrets
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import psutil
import uvicorn
from arq.constants import default_queue_name, health_check_key_suffix, in_progress_key_prefix
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from redis.asyncio import Redis
from sqlalchemy import select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import get_settings
from .control_panel_metrics import (
    connector_operations,
    llm_summary,
    query_branch_summary,
    serialize_event,
    source_funnel,
    stage_timeline,
)
from .control_panel_ui import CONTROL_PANEL_HTML
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
from .schemas import RunStatus


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
SCRIPT_DIR = ROOT / "scripts"
CONTROL_TOKEN = secrets.token_urlsafe(32)
MANAGED_SERVICES = ("api", "worker", "mcp", "telegram")
LOG_SERVICES = {*MANAGED_SERVICES, "control-panel"}
ACTIVE_STATUSES = {
    RunStatus.QUEUED.value,
    RunStatus.RUNNING.value,
    RunStatus.PAUSED.value,
    RunStatus.CANCEL_REQUESTED.value,
}
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


def _service_processes() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for service in MANAGED_SERVICES:
        pid_file = LOG_DIR / f"{service}.pid"
        pid: int | None = None
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                pid = None
        result[service] = {"running": bool(pid and _pid_alive(pid)), "pid": pid}
    return result


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
            jobs.append({
                "job_id": job_id,
                "run_id": run_id,
                "position": position,
                "running": running,
                "score": score,
            })
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


async def _run_snapshot(queue: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    queue_positions = {
        item["run_id"]: item["position"]
        for item in queue["jobs"]
        if item["run_id"] and not item["running"]
    }
    async with SessionLocal() as session:
        rows = list(await session.scalars(
            select(ResearchRunRow).order_by(ResearchRunRow.created_at.desc()).limit(60)
        ))
    serialized = []
    for row in rows:
        protocol = row.protocol or {}
        serialized.append({
            "id": row.id,
            "status": row.status,
            "current_stage": row.current_stage,
            "title": protocol.get("title") or "İsimsiz araştırma",
            "question": protocol.get("primary_question") or "",
            "output_mode": protocol.get("output_mode") or "both",
            "round_number": row.round_number,
            "sources_count": row.sources_count,
            "claims_count": row.claims_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "error": row.error,
            "coverage": row.coverage or {},
            "elapsed_seconds": round(
                max(0.0, (row.updated_at - row.created_at).total_seconds()), 2,
            ) if row.created_at and row.updated_at else 0.0,
            "queue_position": queue_positions.get(row.id),
        })
    return {
        "active": [item for item in serialized if item["status"] in ACTIVE_STATUSES],
        "recent": [item for item in serialized if item["status"] in TERMINAL_STATUSES][:20],
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
        "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,"
        "power.draw,power.limit"
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
            output.append({
                "index": int(values[0]),
                "name": values[1],
                "utilization_percent": number(values[2]),
                "memory_used_mb": number(values[3]),
                "memory_total_mb": number(values[4]),
                "temperature_c": number(values[5]),
                "power_draw_w": number(values[6]),
                "power_limit_w": number(values[7]),
            })
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
    }


async def build_status() -> dict[str, Any]:
    processes = _service_processes()
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
        runs = await asyncio.wait_for(_run_snapshot(queue), timeout=4)
        database = "ok"
    except Exception as exc:
        runs = {"active": [], "recent": []}
        database = f"unavailable: {type(exc).__name__}"
    health, telemetry = await asyncio.gather(_external_health(), _system_telemetry())
    core_running = all(processes[name]["running"] for name in ("api", "worker", "mcp"))
    any_running = any(item["running"] for item in processes.values())
    overall = "running" if core_running else "degraded" if any_running else "stopped"
    return {
        "version": "0.6.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "processes": processes,
        "database": database,
        "queue": queue,
        "runs": runs,
        "health": health,
        "telemetry": telemetry,
        "action": dict(action_state),
    }


async def _run_detail(run_id: str) -> dict[str, Any]:
    async with SessionLocal() as session:
        run = await session.get(ResearchRunRow, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Araştırma bulunamadı")
        events = list(await session.scalars(
            select(EventRow).where(EventRow.run_id == run_id).order_by(EventRow.id).limit(5000)
        ))
        sources = list(await session.scalars(
            select(SourceRow).where(SourceRow.run_id == run_id)
            .order_by(SourceRow.created_at.desc()).limit(500)
        ))
        claims = list(await session.scalars(
            select(ClaimRow).where(ClaimRow.run_id == run_id)
        ))
        evidence = list((await session.scalars(
            select(EvidenceRow).join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
            .where(ClaimRow.run_id == run_id)
        )).all())
        artifacts = list(await session.scalars(
            select(ArtifactRow).where(ArtifactRow.run_id == run_id)
            .order_by(ArtifactRow.name)
        ))
        checkpoints = list(await session.scalars(
            select(CheckpointRow).where(CheckpointRow.run_id == run_id)
            .order_by(CheckpointRow.created_at)
        ))
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
        },
        "timeline": stage_timeline(events, updated or datetime.now(timezone.utc)),
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
        "sources": [{
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
        } for source in sources],
        "events": [serialize_event(event) for event in events[-150:]],
        "checkpoints": [{
            "stage": checkpoint.stage,
            "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
        } for checkpoint in checkpoints],
        "artifacts": [{
            "name": artifact.name,
            "media_type": artifact.media_type,
            "size_bytes": artifact.size_bytes,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        } for artifact in artifacts],
    }


async def _connector_snapshot() -> list[dict[str, Any]]:
    settings = get_settings()
    health_rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.research_api_url.rstrip('/')}/v1/connectors",
                headers={"Authorization": f"Bearer {settings.api_token}"},
            )
            if response.is_success:
                health_rows = response.json()
    except httpx.HTTPError:
        health_rows = []
    async with SessionLocal() as session:
        events = list(await session.scalars(
            select(EventRow).where(EventRow.event_type.in_((
                "connector_metrics", "connector_error",
            ))).order_by(EventRow.id.desc()).limit(2500)
        ))
        sources = list(await session.scalars(
            select(SourceRow).order_by(SourceRow.created_at.desc()).limit(5000)
        ))
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
        output.append({
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
                "calls": 0, "successes": 0, "success_rate": 0.0,
                "result_count": 0, "errors": 0, "error_types": {},
                "average_latency_seconds": 0.0, "p95_latency_seconds": 0.0,
                "last_success_at": None, "last_error_at": None,
                **metrics,
            },
        })
    return output


async def require_control_token(
    x_control_token: str | None = Header(default=None),
) -> None:
    if not x_control_token or not secrets.compare_digest(x_control_token, CONTROL_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid control token")


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
    version="0.6.1",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
panel_settings = get_settings()
panel_networks = (
    panel_settings.control_panel_allowed_networks
    or panel_settings.mcp_allowed_networks
)
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
    ],
)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    response = HTMLResponse(CONTROL_PANEL_HTML.replace("__CONTROL_TOKEN__", CONTROL_TOKEN))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "research-control-panel", "version": "0.6.1"}


@app.get("/api/status", dependencies=[Depends(require_control_token)])
async def status() -> dict[str, Any]:
    return await build_status()


@app.get("/api/runs/{run_id}/detail", dependencies=[Depends(require_control_token)])
async def run_detail(run_id: str) -> dict[str, Any]:
    return await _run_detail(run_id)


@app.get("/api/connectors", dependencies=[Depends(require_control_token)])
async def connectors() -> list[dict[str, Any]]:
    return await _connector_snapshot()


@app.post("/api/connectors/{connector_id}/test", dependencies=[Depends(require_control_token)])
async def connector_test(connector_id: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.research_api_url.rstrip('/')}/v1/connectors/{connector_id}/test",
                headers={"Authorization": f"Bearer {settings.api_token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        raise HTTPException(status_code=response.status_code, detail=response.text[:500])
    return response.json()


@app.get(
    "/api/runs/{run_id}/artifacts/{artifact_name}",
    dependencies=[Depends(require_control_token)],
)
async def artifact_download(run_id: str, artifact_name: str) -> Response:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(
                f"{settings.research_api_url.rstrip('/')}/v1/research-runs/"
                f"{run_id}/artifacts/{artifact_name}",
                headers={"Authorization": f"Bearer {settings.api_token}"},
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


@app.post("/api/system/{action}", dependencies=[Depends(require_control_token)])
async def system_action(action: Literal["start", "stop", "restart"]) -> dict[str, Any]:
    if action_lock.locked():
        raise HTTPException(status_code=409, detail="Başka bir sistem işlemi devam ediyor")
    async with action_lock:
        action_state.update({
            "busy": True,
            "action": action,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        })
        script = "stop_native.ps1" if action == "stop" else "start_office_server.ps1"
        try:
            return_code, output = await _run_powershell(script)
            if return_code:
                action_state["last_error"] = output or f"PowerShell exit code {return_code}"
                raise HTTPException(status_code=500, detail=action_state["last_error"])
            return {"ok": True, "action": action, "message": output.strip()}
        finally:
            action_state.update({"busy": False, "action": None})


@app.post("/api/runs/{run_id}/{action}", dependencies=[Depends(require_control_token)])
async def run_action(
    run_id: str,
    action: Literal["pause", "resume", "cancel"],
) -> dict[str, Any]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.research_api_url.rstrip('/')}/v1/research-runs/{run_id}/{action}",
                headers={"Authorization": f"Bearer {settings.api_token}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Research API erişilemiyor") from exc
    if not response.is_success:
        detail = response.json().get("detail", response.text[:500])
        raise HTTPException(status_code=response.status_code, detail=detail)
    return response.json()


@app.get("/api/logs/{service}", response_class=PlainTextResponse,
         dependencies=[Depends(require_control_token)])
async def logs(service: str) -> PlainTextResponse:
    if service not in LOG_SERVICES:
        raise HTTPException(status_code=404, detail="Bilinmeyen servis")
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
    if (
        settings.control_panel_host not in {"127.0.0.1", "localhost", "::1"}
        and not networks
    ):
        raise RuntimeError("LAN control panel requires CONTROL_PANEL_ALLOWED_NETWORKS")
    uvicorn.run(
        "research_platform.control_panel:app",
        host=settings.control_panel_host,
        port=settings.control_panel_port,
        reload=False,
        access_log=False,
    )
