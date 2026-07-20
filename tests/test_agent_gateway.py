from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import respx
from starlette.responses import JSONResponse
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from research_platform.gateway_client import ResearchGatewayClient
from research_platform.mcp_server import BearerProtectedMCP
from research_platform.telegram_bot import (
    TelegramResearchBot, duration_keyboard, parse_research_request,
)
import research_platform.mcp_server as mcp_module


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
    bot.allow_group_chats = False
    bot.allow_all_users = False
    message = {"from": {"id": 10}, "chat": {"id": 20, "type": "private"}}
    assert not bot._authorized(message)
    bot.allowed_users = {10}
    assert bot._authorized(message)
    bot.allowed_users = set()
    bot.allowed_chats = {20}
    assert bot._authorized(message)


def test_telegram_can_authorize_every_member_of_group_without_opening_private_chats():
    bot = object.__new__(TelegramResearchBot)
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = True
    bot.allow_all_users = False
    assert bot._authorized({
        "from": {"id": 999},
        "chat": {"id": -100123, "type": "supergroup"},
    })
    assert not bot._authorized({
        "from": {"id": 999},
        "chat": {"id": 999, "type": "private"},
    })


def test_telegram_can_authorize_all_private_users_when_explicitly_enabled():
    bot = object.__new__(TelegramResearchBot)
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = True
    assert bot._authorized({
        "from": {"id": 999},
        "chat": {"id": 999, "type": "private"},
    })


def test_telegram_research_defaults_use_time_without_source_ceiling():
    mode, question, budget = parse_research_request(
        ["raw", "akciğer", "BT", "araştırması"],
        default_minutes=20,
        maximum_minutes=180,
        default_sources=None,
        default_rounds=3,
    )
    assert mode.value == "raw"
    assert question == "akciğer BT araştırması"
    assert budget.max_wall_minutes == 20
    assert budget.max_sources is None
    assert budget.max_rounds == 3


def test_telegram_research_allows_bounded_time_and_source_overrides():
    _, question, budget = parse_research_request(
        ["both", "--minutes", "35", "--sources", "80", "zor", "konu"],
        default_minutes=20,
        maximum_minutes=180,
        default_sources=None,
        default_rounds=3,
    )
    assert question == "zor konu"
    assert budget.max_wall_minutes == 35
    assert budget.max_sources == 80

    _, _, large_budget = parse_research_request(
        ["--sources", "5000", "geniş", "tarama"],
        default_minutes=20,
        maximum_minutes=60,
        default_sources=None,
        default_rounds=3,
    )
    assert large_budget.max_sources == 5000

    with pytest.raises(ValueError, match="1-180"):
        parse_research_request(
            ["--minutes", "190", "soru"],
            default_minutes=20,
            maximum_minutes=180,
            default_sources=None,
            default_rounds=3,
        )


def test_duration_keyboard_exposes_four_research_modes():
    keyboard = duration_keyboard("REQ1")["inline_keyboard"]
    assert [row[0]["callback_data"] for row in keyboard] == [
        "research_time:REQ1:10",
        "research_time:REQ1:30",
        "research_time:REQ1:120",
        "research_time:REQ1:180",
    ]


@pytest.mark.asyncio
async def test_telegram_research_waits_for_inline_duration_selection():
    class FakeClient:
        def __init__(self):
            self.posts = []

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return SimpleNamespace()

    class FakeGateway:
        def __init__(self):
            self.protocols = []

        async def start(self, protocol):
            self.protocols.append(protocol)
            return {"id": "RUN1"}

    bot = object.__new__(TelegramResearchBot)
    bot.settings = SimpleNamespace(
        telegram_default_max_wall_minutes=20,
        telegram_max_wall_minutes=180,
        telegram_default_max_sources=None,
        telegram_default_max_rounds=3,
    )
    bot.bot_url = "https://telegram.test/botTOKEN"
    bot.gateway = FakeGateway()
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = True
    bot.pending_research = {}
    client = FakeClient()
    message = {
        "from": {"id": 7},
        "chat": {"id": 11, "type": "private"},
        "text": "/research raw kaynak sınırı olmayan araştırma",
    }

    await bot._handle(client, message)
    assert bot.gateway.protocols == []
    picker = client.posts[-1][1]["json"]["reply_markup"]["inline_keyboard"]
    callback_data = picker[1][0]["callback_data"]

    await bot._handle_callback(client, {
        "id": "CALLBACK1",
        "from": {"id": 7},
        "data": callback_data,
        "message": {"message_id": 99, "chat": {"id": 11, "type": "private"}},
    })

    assert len(bot.gateway.protocols) == 1
    assert bot.gateway.protocols[0].budget.max_wall_minutes == 30
    assert bot.gateway.protocols[0].budget.max_sources is None


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


@pytest.mark.asyncio
@respx.mock
async def test_gateway_lists_recent_runs():
    route = respx.get("http://research.test/v1/research-runs").mock(
        return_value=httpx.Response(200, json=[{"id": "RUN1"}])
    )
    client = ResearchGatewayClient("http://research.test", "token")
    assert await client.runs(limit=25) == [{"id": "RUN1"}]
    assert route.calls[0].request.url.params["limit"] == "25"


def test_authenticated_client_api_lists_status_and_downloads(tmp_path, monkeypatch):
    archive = tmp_path / "RUN1_both.zip"
    archive.write_bytes(b"PK\x03\x04test")

    class FakeGateway:
        async def runs(self, *, limit=50):
            return [{"id": "RUN1", "limit": limit}]

        async def status(self, run_id):
            return {"id": run_id, "status": "completed"}

        async def download(self, run_id, mode, destination):
            return archive

    monkeypatch.setattr(mcp_module, "_client", lambda: FakeGateway())
    protected = BearerProtectedMCP(
        Starlette(routes=[]), token="secret", allowed_origins=set()
    )
    headers = {"Authorization": "Bearer secret"}
    with TestClient(protected) as client:
        listed = client.get("/client/v1/research-runs?limit=12", headers=headers)
        assert listed.status_code == 200
        assert listed.json() == [{"id": "RUN1", "limit": 12}]
        status = client.get("/client/v1/research-runs/RUN1", headers=headers)
        assert status.json()["status"] == "completed"
        delivery = client.get(
            "/client/v1/research-runs/RUN1/delivery/both", headers=headers
        )
        assert delivery.status_code == 200
        assert delivery.content == archive.read_bytes()
        assert delivery.headers["content-type"] == "application/zip"
