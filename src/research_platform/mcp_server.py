from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

from .auth import AuthError
from .config import get_settings
from .db import SessionLocal
from .gateway_client import ResearchGatewayClient
from .identity import principal_from_api_key
from .schemas import DeliveryMode, HitlConfig, ResearchBudget, ResearchProtocol
from .version import VERSION

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


# Who the current request is acting as. Tool functions never see the HTTP request, so the
# credential has to travel out of band: the middleware resolves the presented API key and
# stores the user id here before dispatching.
#
# This is safe because of how MCP 1.x runs a stateless request. The tool body executes in a
# task started from a *long-lived* task group (``self._task_group.start(...)`` in
# ``mcp.server.streamable_http_manager``), which looks like it would lose per-request state.
# It does not: anyio copies the caller's context at ``start()`` time, and the caller is the
# request task. Verified with a replica of that structure -- two sequential requests with
# different keys reached the tool as different actors, with no bleed between them.
_ACTOR: ContextVar[str | None] = ContextVar("mcp_actor_user_id", default=None)


def _client() -> ResearchGatewayClient:
    """A gateway client bound to whoever presented the key on this request.

    The key is not forwarded to the API. The gateway has already verified it, and
    re-presenting it would make the API repeat the scrypt check -- about 60 ms on every
    tool call. Instead this uses the service credential plus ``X-Actor-User``, exactly as
    the Telegram bot does: a trusted intermediary that authenticated its own user and now
    names who it is acting for.
    """
    client = ResearchGatewayClient(
        settings.research_api_url, settings.service_token or settings.api_token
    )
    actor = _ACTOR.get()
    return client.for_actor(actor) if actor else client


@mcp.tool()
async def start_research(
    question: str,
    max_wall_minutes: int,
    title: str = "Agent research request",
    output_mode: Literal["raw", "result", "both"] = "both",
    max_sources: int | None = None,
    priority: Literal["normal", "urgent"] = "normal",
    planning_questions: bool = False,
    plan_review: bool = True,
    source_review: bool = False,
    outline_review: bool = False,
) -> dict:
    """Start a research run and return its durable run id.

    `max_wall_minutes` has no default on purpose: how long the run may collect is a
    decision the caller has to make, not one to inherit silently.

    With `plan_review` left on, the run stops at `awaiting_input` before it searches and
    publishes a plan; approve or revise it with `respond_to_research_checkpoint`. Pass
    false only for unattended runs -- the run then records a `plan_skipped` event.

    `priority` picks the queue band. An `urgent` run goes ahead of every waiting normal
    one and pauses a running normal one to take the worker; use it for work that is
    genuinely time-critical, because the run it displaces resumes from its last
    checkpoint and redoes whatever that stage had done since.
    """
    protocol = ResearchProtocol(
        title=title,
        primary_question=question,
        output_mode=output_mode,
        budget=ResearchBudget(
            max_wall_minutes=max_wall_minutes,
            max_sources=max_sources,
        ),
        hitl=HitlConfig(
            planning_questions=planning_questions,
            plan_review=plan_review,
            source_review=source_review,
            outline_review=outline_review,
        ),
    )
    run = await _client().start(protocol, priority=priority)
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
async def respond_to_research_checkpoint(
    run_id: str,
    interaction_id: str,
    response: dict[str, Any],
) -> dict:
    """Answer the active HITL checkpoint; use the response shape shown by research_status."""
    return await _client().respond(run_id, interaction_id, response)


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
    max_chars: int | None = None,
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
    max_chars: int | None = None,
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
    return {
        "run_id": run_id,
        "mode": mode,
        "path": str(target),
        "size_bytes": target.stat().st_size,
    }


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
        # No shared-token strength check any more: there is no shared token. Credentials
        # are per-user API keys, minted with 24 random bytes and stored hashed, so their
        # strength is a property of issue_api_key rather than of someone's .env.
        if not _is_loopback_host(settings.mcp_host) and not settings.mcp_allowed_networks:
            raise RuntimeError("Non-loopback MCP requires MCP_ALLOWED_NETWORKS")
        uvicorn.run(
            BearerProtectedMCP(
                mcp.streamable_http_app(),
                allowed_origins=set(settings.mcp_allowed_origins),
                allowed_networks=set(settings.mcp_allowed_networks),
            ),
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
        return
    mcp.run(transport="stdio")


class BearerProtectedMCP:
    """Authenticates every MCP request as a *person*, not as the gateway.

    Until v0.10.1 this compared the presented bearer against one shared token. That token
    could start research but could not own it -- the API refuses to create a run with no
    owner -- so every agent surface broke the moment per-user isolation landed. The
    credential is now the caller's own API key (``rp_<prefix>.<secret>``), which resolves
    to a real user whose runs show up in their own panel.
    """

    def __init__(
        self,
        app,
        *,
        allowed_origins: set[str],
        allowed_networks: set[str] | None = None,
    ) -> None:
        self.app = app
        self.allowed_origins = allowed_origins
        self.allowed_networks = tuple(
            ipaddress.ip_network(value, strict=False) for value in (allowed_networks or set())
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            # Network and Origin first: they are the perimeter, and a caller outside it
            # gets nothing at all -- not even a liveness answer.
            if self.allowed_networks and not self._client_allowed(scope):
                await self._reject(send, 403, b"Client network is not allowed")
                return
            origin = headers.get("origin")
            if origin and origin not in self.allowed_origins:
                await self._reject(send, 403, b"Invalid Origin")
                return
            # Inside the perimeter, health needs no credential. It carries no data, and the
            # office start/status scripts poll it to decide whether the gateway came up --
            # putting a credential in front of a liveness probe only makes the probe lie.
            if scope.get("path") == "/health":
                await self._json(
                    send,
                    200,
                    {
                        "status": "healthy",
                        "service": "research-platform-mcp",
                        "version": VERSION,
                    },
                )
                return
            actor = await self._resolve_actor(headers.get("authorization", ""))
            if actor is None:
                await self._reject(send, 401, b"Unauthorized")
                return
            _ACTOR.set(actor)
            if scope.get("path", "").startswith("/client/v1/"):
                await self._client_api(scope, send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def _resolve_actor(authorization: str) -> str | None:
        """Return the user id behind the presented API key, or None.

        Every rejection reason -- malformed, unknown, revoked, or belonging to a closed
        account -- returns None and therefore the same 401. Distinguishing them would let
        a caller learn which key prefixes exist.
        """
        scheme, separator, presented = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not presented:
            return None
        try:
            async with SessionLocal() as session:
                principal = await principal_from_api_key(session, presented)
        except AuthError:
            return None
        return principal.user_id

    async def _client_api(self, scope, send) -> None:
        if scope.get("method") != "GET":
            await self._reject(send, 405, b"Method Not Allowed")
            return
        path = scope.get("path", "")
        parts = [part for part in path.split("/") if part]
        try:
            if parts == ["client", "v1", "research-runs"]:
                query = parse_qs(scope.get("query_string", b"").decode("ascii", errors="ignore"))
                limit = int(query.get("limit", ["50"])[0])
                await self._json(send, 200, await _client().runs(limit=limit))
                return
            if len(parts) == 4 and parts[:3] == ["client", "v1", "research-runs"]:
                await self._json(send, 200, await _client().status(parts[3]))
                return
            if (
                len(parts) == 6
                and parts[:3] == ["client", "v1", "research-runs"]
                and parts[4] == "delivery"
            ):
                mode = DeliveryMode(parts[5])
                target = await _client().download(
                    parts[3], mode, Path(settings.gateway_download_dir)
                )
                await self._file(send, target)
                return
        except (ValueError, TypeError):
            await self._reject(send, 400, b"Invalid request")
            return
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            await self._reject(
                send, status if 400 <= status < 600 else 502, b"Upstream request failed"
            )
            return
        except httpx.HTTPError:
            await self._reject(send, 502, b"Research API unavailable")
            return
        await self._reject(send, 404, b"Not Found")

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
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _json(send, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})

    @staticmethod
    async def _file(send, path: Path) -> None:
        size = path.stat().st_size
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/zip"),
                    (b"content-length", str(size).encode("ascii")),
                    (b"content-disposition", f'attachment; filename="{path.name}"'.encode("ascii")),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
