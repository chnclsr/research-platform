from __future__ import annotations

from pathlib import Path
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
        budget=ResearchBudget(
            max_wall_minutes=max_wall_minutes,
            max_sources=max_sources,
        ),
    )
    run = await _client().start(protocol)
    run["requested_output_mode"] = output_mode
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
    """Save a durable ZIP delivery on the research server and return its absolute path."""
    target = await _client().download(
        run_id,
        DeliveryMode(mode),
        Path(settings.gateway_download_dir),
    )
    return {"run_id": run_id, "mode": mode, "path": str(target), "size_bytes": target.stat().st_size}


def run() -> None:
    if settings.mcp_transport == "streamable-http":
        uvicorn.run(
            BearerProtectedMCP(
                mcp.streamable_http_app(),
                token=settings.mcp_bearer_token or settings.api_token,
                allowed_origins=set(settings.mcp_allowed_origins),
            ),
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
        return
    mcp.run(transport="stdio")


class BearerProtectedMCP:
    def __init__(self, app, *, token: str, allowed_origins: set[str]) -> None:
        self.app = app
        self.token = token
        self.allowed_origins = allowed_origins

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            if headers.get("authorization") != f"Bearer {self.token}":
                await self._reject(send, 401, b"Unauthorized")
                return
            origin = headers.get("origin")
            if origin and origin not in self.allowed_origins:
                await self._reject(send, 403, b"Invalid Origin")
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send, status: int, body: bytes) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        })
        await send({"type": "http.response.body", "body": body})
