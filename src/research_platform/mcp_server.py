from __future__ import annotations

import ipaddress
import json
import base64
import hashlib
from pathlib import Path
import secrets
from typing import Literal

from mcp.server.fastmcp import FastMCP
import uvicorn

from .config import get_settings
from .gateway_client import ResearchGatewayClient
from .schemas import DeliveryMode, ResearchBudget, ResearchProtocol


settings = get_settings()
mcp = FastMCP(
    "Research Platform",
    instructions=(
        "Start and inspect evidence-focused research runs on the local research server. "
        "Use raw delivery for collected source data, result delivery for synthesized reports, "
        "and both when the calling agent needs auditable evidence plus the local synthesis."
    ),
    stateless_http=True,
    json_response=True,
    host=settings.mcp_host,
    port=settings.mcp_port,
)


def _client() -> ResearchGatewayClient:
    return ResearchGatewayClient(settings.research_api_url, settings.api_token)


@mcp.tool()
async def start_research(
    question: str,
    title: str = "Agent research request",
    output_mode: Literal["raw", "result", "both"] = "both",
    max_wall_minutes: int = 45,
    max_sources: int = 150,
) -> dict:
    """Start a research run and return its durable run id."""
    protocol = ResearchProtocol(
        title=title,
        primary_question=question,
        output_mode=output_mode,
        budget=ResearchBudget(
            max_wall_minutes=max_wall_minutes,
            max_sources=max_sources,
        ),
    )
    run = await _client().start(protocol)
    return run


@mcp.tool()
async def research_status(run_id: str) -> dict:
    """Get stage, status, source count, claim count, coverage and errors for a run."""
    return await _client().status(run_id)


@mcp.tool()
async def control_research(
    run_id: str,
    action: Literal["pause", "resume", "cancel"],
) -> dict:
    """Pause, resume or cancel a research run at a safe node boundary."""
    return await _client().action(run_id, action)


@mcp.tool()
async def list_research_artifacts(run_id: str) -> list[dict]:
    """List the raw data, report and audit artifacts produced by a completed run."""
    return await _client().artifacts(run_id)


@mcp.tool()
async def read_research_report(
    run_id: str,
    report: Literal[
        "executive_summary", "full_report", "coverage", "audit", "uncertainty"
    ] = "full_report",
    max_chars: int = 100_000,
) -> str:
    """Read a textual result artifact directly into the calling Codex or Claude context."""
    names = {
        "executive_summary": "01_executive_summary.md",
        "full_report": "02_full_research_report.md",
        "coverage": "07_coverage_report.md",
        "audit": "11_audit_report.md",
        "uncertainty": "12_uncertainty_report.md",
    }
    return await _client().read_artifact(run_id, names[report], max_chars=max_chars)


@mcp.tool()
async def read_research_raw_data(
    run_id: str,
    dataset: Literal["sources", "passages"] = "passages",
    offset: int = 0,
    max_chars: int = 100_000,
) -> str:
    """Read collected source versions or normalized passages in repeatable chunks."""
    names = {
        "sources": "13_raw_sources.jsonl",
        "passages": "14_raw_passages.jsonl",
    }
    return await _client().read_artifact(
        run_id,
        names[dataset],
        offset=max(0, offset),
        max_chars=max_chars,
    )


@mcp.tool()
async def download_research_delivery(
    run_id: str,
    mode: Literal["raw", "result", "both"] = "both",
) -> dict:
    """Cache a durable ZIP on the research server; use read_research_delivery_chunk remotely."""
    target = await _client().download(
        run_id,
        DeliveryMode(mode),
        Path(settings.gateway_download_dir),
    )
    return {"run_id": run_id, "mode": mode, "path": str(target), "size_bytes": target.stat().st_size}


@mcp.tool()
async def read_research_delivery_chunk(
    run_id: str,
    mode: Literal["raw", "result", "both"] = "both",
    offset: int = 0,
    max_bytes: int = 65_536,
) -> dict:
    """Read a ZIP delivery as base64 chunks so a remote Codex or Claude can reconstruct it."""
    max_bytes = min(max(1, max_bytes), 262_144)
    target = await _client().download(
        run_id,
        DeliveryMode(mode),
        Path(settings.gateway_download_dir),
    )
    size = target.stat().st_size
    offset = min(max(0, offset), size)
    with target.open("rb") as handle:
        handle.seek(offset)
        payload = handle.read(max_bytes)
    next_offset = offset + len(payload)
    digest = None
    if offset == 0:
        with target.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
    return {
        "run_id": run_id,
        "mode": mode,
        "filename": target.name,
        "offset": offset,
        "next_offset": next_offset,
        "size_bytes": size,
        "complete": next_offset >= size,
        "sha256": digest,
        "base64": base64.b64encode(payload).decode("ascii"),
    }


def run() -> None:
    if settings.mcp_transport == "streamable-http":
        token = settings.mcp_bearer_token or settings.api_token
        if not _is_loopback_host(settings.mcp_host):
            if len(token) < 32 or token.startswith("change-me"):
                raise RuntimeError(
                    "Non-loopback MCP requires a random bearer token of at least 32 characters"
                )
            if not settings.mcp_allowed_networks:
                raise RuntimeError("Non-loopback MCP requires MCP_ALLOWED_NETWORKS")
        uvicorn.run(
            BearerProtectedMCP(
                mcp.streamable_http_app(),
                token=token,
                allowed_origins=set(settings.mcp_allowed_origins),
                allowed_networks=set(settings.mcp_allowed_networks),
            ),
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
        return
    mcp.run(transport="stdio")


class BearerProtectedMCP:
    def __init__(
        self,
        app,
        *,
        token: str,
        allowed_origins: set[str],
        allowed_networks: set[str] | None = None,
    ) -> None:
        self.app = app
        self.token = token
        self.allowed_origins = allowed_origins
        self.allowed_networks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in (allowed_networks or set())
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            supplied = headers.get("authorization", "")
            if not secrets.compare_digest(supplied, f"Bearer {self.token}"):
                await self._reject(send, 401, b"Unauthorized")
                return
            if self.allowed_networks and not self._client_allowed(scope):
                await self._reject(send, 403, b"Client network is not allowed")
                return
            origin = headers.get("origin")
            if origin and origin not in self.allowed_origins:
                await self._reject(send, 403, b"Invalid Origin")
                return
            if scope.get("path") == "/health":
                await self._json(
                    send,
                    200,
                    {
                        "status": "healthy",
                        "service": "research-platform-mcp",
                        "version": "0.5.0",
                    },
                )
                return
        await self.app(scope, receive, send)

    def _client_allowed(self, scope) -> bool:
        client = scope.get("client")
        if not client:
            return False
        try:
            address = ipaddress.ip_address(client[0])
        except ValueError:
            return False
        return any(address in network for network in self.allowed_networks)

    @staticmethod
    async def _reject(send, status: int, body: bytes) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _json(send, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": payload})


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
