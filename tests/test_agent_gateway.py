from __future__ import annotations

import httpx
import pytest
import respx
from starlette.responses import JSONResponse
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from research_platform.gateway_client import ResearchGatewayClient
from research_platform.mcp_server import BearerProtectedMCP
from research_platform.telegram_bot import TelegramResearchBot


def _protected_test_app():
    async def endpoint(request):
        return JSONResponse({"ok": True})

    return BearerProtectedMCP(
        Starlette(routes=[Route("/mcp", endpoint)]),
        token="secret",
        allowed_origins={"https://office.example"},
    )


def test_mcp_gateway_requires_bearer_and_validates_origin():
    with TestClient(_protected_test_app()) as client:
        assert client.get("/mcp").status_code == 401
        assert client.get(
            "/mcp", headers={"Authorization": "Bearer secret"}
        ).status_code == 200
        assert client.get(
            "/mcp",
            headers={
                "Authorization": "Bearer secret",
                "Origin": "https://evil.example",
            },
        ).status_code == 403
        assert client.get(
            "/mcp",
            headers={
                "Authorization": "Bearer secret",
                "Origin": "https://office.example",
            },
        ).status_code == 200


def test_mcp_gateway_health_and_network_allowlist():
    async def endpoint(request):
        return JSONResponse({"ok": True})

    inner = Starlette(routes=[Route("/mcp", endpoint)])
    allowed = BearerProtectedMCP(
        inner,
        token="secret",
        allowed_origins=set(),
        allowed_networks={"127.0.0.0/8"},
    )
    with TestClient(allowed, client=("127.0.0.1", 50000)) as client:
        response = client.get(
            "/health",
            headers={"Authorization": "Bearer secret"},
        )
        assert response.status_code == 200
        assert response.json()["service"] == "research-platform-mcp"

    blocked = BearerProtectedMCP(
        inner,
        token="secret",
        allowed_origins=set(),
        allowed_networks={"10.0.10.0/24"},
    )
    with TestClient(blocked, client=("127.0.0.1", 50000)) as client:
        assert client.get(
            "/health",
            headers={"Authorization": "Bearer secret"},
        ).status_code == 403


def test_telegram_requires_non_empty_allowlist():
    bot = object.__new__(TelegramResearchBot)
    bot.allowed_users = set()
    bot.allowed_chats = set()
    message = {"from": {"id": 10}, "chat": {"id": 20}}
    assert not bot._authorized(message)
    bot.allowed_users = {10}
    assert bot._authorized(message)
    bot.allowed_users = set()
    bot.allowed_chats = {20}
    assert bot._authorized(message)


@pytest.mark.asyncio
@respx.mock
async def test_gateway_reads_raw_artifacts_in_chunks():
    route = respx.get(
        "http://research.test/v1/research-runs/RUN1/artifacts/14_raw_passages.jsonl"
    ).mock(return_value=httpx.Response(200, content=b"abcdefghij"))
    client = ResearchGatewayClient("http://research.test", "token")
    result = await client.read_artifact(
        "RUN1", "14_raw_passages.jsonl", offset=2, max_chars=4
    )
    assert route.called
    assert result.startswith("cdef")
    assert "next_offset=6" in result
