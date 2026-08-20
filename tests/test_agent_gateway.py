from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
import respx
from starlette.responses import JSONResponse
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from research_platform.db import SessionLocal, create_schema
from research_platform.gateway_client import ResearchGatewayClient
from research_platform.identity import (
    create_user,
    format_link_code,
    get_user,
    get_user_by_email,
    issue_api_key,
    issue_telegram_link_code,
    link_telegram,
    revoke_api_key,
)
from research_platform.mcp_server import BearerProtectedMCP
from research_platform.telegram_bot import (
    TelegramResearchBot, duration_keyboard, has_explicit_duration, parse_research_request,
)
import research_platform.mcp_server as mcp_module


async def _linked_telegram_user(telegram_user_id: int) -> str:
    """Create a platform account and bind a Telegram id to it."""
    await create_schema()
    email = f"telegram-{telegram_user_id}@example.test"
    async with SessionLocal() as session:
        user = await get_user_by_email(session, email)
        if user is None:
            user = await create_user(
                session,
                email=email,
                display_name=f"Telegram {telegram_user_id}",
                password="telegram-test-password",
            )
        await link_telegram(session, telegram_user_id=telegram_user_id, user_id=user.id)
        return user.id


async def _keyed_account(email: str, *, revoked: bool = False, active: bool = True) -> str:
    """An account with an API key, returning the key as a caller would present it."""
    await create_schema()
    async with SessionLocal() as session:
        user = await get_user_by_email(session, email)
        if user is None:
            user = await create_user(
                session,
                email=email,
                display_name=email.split("@")[0],
                password="gateway-test-password",
            )
        key, row = await issue_api_key(session, user_id=user.id, name="mcp-test")
        if revoked:
            await revoke_api_key(session, user_id=user.id, key_id=row.id)
        if not active:
            user.is_active = False
            await session.commit()
        return key


def _protected_test_app():
    async def endpoint(request):
        return JSONResponse({"actor": mcp_module._ACTOR.get()})

    return BearerProtectedMCP(
        Starlette(routes=[Route("/mcp", endpoint)]),
        allowed_origins={"https://office.example"},
    )


@pytest.mark.asyncio
async def test_mcp_gateway_requires_a_personal_key_and_validates_origin():
    key = await _keyed_account("mcp-caller@example.test")
    with TestClient(_protected_test_app()) as client:
        assert client.get("/mcp").status_code == 401
        assert client.get("/mcp", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        assert client.get(
            "/mcp",
            headers={"Authorization": f"Bearer {key}", "Origin": "https://evil.example"},
        ).status_code == 403
        assert client.get(
            "/mcp",
            headers={"Authorization": f"Bearer {key}", "Origin": "https://office.example"},
        ).status_code == 200


@pytest.mark.asyncio
async def test_every_bad_credential_looks_identical():
    """Malformed, unknown, revoked and closed-account keys must be indistinguishable.

    Telling them apart would let a caller learn which key prefixes exist.
    """
    revoked = await _keyed_account("mcp-revoked@example.test", revoked=True)
    closed = await _keyed_account("mcp-closed@example.test", active=False)
    with TestClient(_protected_test_app()) as client:
        for label, header in [
            ("yok", {}),
            ("bicimsiz", {"Authorization": "Bearer not-a-key"}),
            ("sema disi", {"Authorization": "Basic rp_abc.def"}),
            ("bilinmeyen", {"Authorization": "Bearer rp_zzzzzzzz.nosuchsecret"}),
            ("iptal", {"Authorization": f"Bearer {revoked}"}),
            ("kapali hesap", {"Authorization": f"Bearer {closed}"}),
        ]:
            assert client.get("/mcp", headers=header).status_code == 401, label


@pytest.mark.asyncio
async def test_two_keys_in_a_row_do_not_bleed_into_each_other():
    """The credential travels through a ContextVar; a leak would let one user act as another.

    This is the failure the whole design turns on, so it is asserted directly rather than
    inferred from the transport's documentation.
    """
    first = await _keyed_account("mcp-first@example.test")
    second = await _keyed_account("mcp-second@example.test")
    async with SessionLocal() as session:
        first_id = (await get_user_by_email(session, "mcp-first@example.test")).id
        second_id = (await get_user_by_email(session, "mcp-second@example.test")).id

    with TestClient(_protected_test_app()) as client:
        seen_first = client.get("/mcp", headers={"Authorization": f"Bearer {first}"}).json()
        seen_second = client.get("/mcp", headers={"Authorization": f"Bearer {second}"}).json()
    assert seen_first["actor"] == first_id
    assert seen_second["actor"] == second_id
    assert first_id != second_id


@pytest.mark.asyncio
async def test_health_needs_no_credential_but_still_respects_the_network_perimeter():
    async def endpoint(request):
        return JSONResponse({"ok": True})

    inner = Starlette(routes=[Route("/mcp", endpoint)])
    allowed = BearerProtectedMCP(
        inner,
        allowed_origins=set(),
        allowed_networks={"127.0.0.0/8"},
    )
    with TestClient(allowed, client=("127.0.0.1", 50000)) as client:
        # No Authorization header at all: the office start/status scripts poll this to
        # decide whether the gateway came up.
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["service"] == "research-platform-mcp"
        # The tool surface behind it is still closed.
        assert client.get("/mcp").status_code == 401

    blocked = BearerProtectedMCP(
        inner,
        allowed_origins=set(),
        allowed_networks={"10.0.10.0/24"},
    )
    with TestClient(blocked, client=("127.0.0.1", 50000)) as client:
        assert client.get("/health").status_code == 403


@pytest.mark.asyncio
async def test_gateway_client_acts_for_the_key_owner():
    """The API is called with the service credential naming the caller, not with the key."""
    key = await _keyed_account("mcp-actor@example.test")
    async with SessionLocal() as session:
        user_id = (await get_user_by_email(session, "mcp-actor@example.test")).id

    captured: dict[str, str] = {}

    async def endpoint(request):
        captured.update(mcp_module._client().headers)
        return JSONResponse({"ok": True})

    protected = BearerProtectedMCP(
        Starlette(routes=[Route("/mcp", endpoint)]),
        allowed_origins=set(),
    )
    with TestClient(protected) as client:
        assert client.get("/mcp", headers={"Authorization": f"Bearer {key}"}).status_code == 200

    assert captured["X-Actor-User"] == user_id
    # The caller's own key must not be forwarded upstream.
    assert key not in captured["Authorization"]


@pytest.mark.asyncio
async def test_direct_chats_are_open_because_linking_is_the_real_gate():
    """The env allow-list no longer decides who may use the bot privately.

    It stood in for an identity the platform did not have. Now that accounts exist, a
    user who links their own Telegram account is authorized by that link; keeping the
    list as a second gate would block exactly the people who linked themselves. Whose
    research a message belongs to is decided by _resolve_actor, not here.
    """
    bot = object.__new__(TelegramResearchBot)
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = False
    assert await bot._chat_allowed({"from": {"id": 10}, "chat": {"id": 20, "type": "private"}})


@pytest.mark.asyncio
async def test_group_chats_stay_behind_the_allowlist():
    """A group has many senders, so the sender is not reliably who the bot acts for."""
    bot = object.__new__(TelegramResearchBot)
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = False
    group = {"from": {"id": 999}, "chat": {"id": -100123, "type": "supergroup"}}
    assert not await bot._chat_allowed(group)

    bot.allow_group_chats = True
    # Enabled but with nothing allow-listed is still a refusal.
    assert not await bot._chat_allowed(group)

    bot.allowed_chats = {-100123}
    assert await bot._chat_allowed(group)

    bot.allowed_chats = set()
    bot.allow_all_users = True
    assert await bot._chat_allowed(group)


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


def test_telegram_accepts_positional_minutes_after_delivery_mode():
    mode, question, budget = parse_research_request(
        ["both", "2", "lung", "cancer", "CT"],
        default_minutes=20,
        maximum_minutes=180,
        default_sources=None,
        default_rounds=3,
    )
    assert mode.value == "both"
    assert question == "lung cancer CT"
    assert budget.max_wall_minutes == 2
    assert has_explicit_duration(["both", "2", "lung", "cancer", "CT"])
    assert has_explicit_duration(["raw", "--minutes", "4", "question"])
    assert not has_explicit_duration(["both", "lung", "cancer", "CT"])


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
            self.actors = []

        def for_actor(self, actor_user_id):
            # The bot binds every call to the platform user behind the Telegram
            # account, so record which one it resolved.
            self.actors.append(actor_user_id)
            return self

        async def start(self, protocol):
            self.protocols.append(protocol)
            return {"id": "RUN1"}

    # The bot now needs to know whose research a message creates, so the Telegram
    # account has to be linked to a platform account first.
    telegram_owner = await _linked_telegram_user(7)

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
    bot.watched_runs = {}
    bot.pending_answers = {}
    client = FakeClient()
    message = {
        "from": {"id": 7},
        "chat": {"id": 11, "type": "private"},
        "text": "/research raw kaynak sınırı olmayan araştırma",
    }

    # Language first, then duration: neither is guessed, and nothing starts until both
    # are answered.
    await bot._handle(client, message)
    assert bot.gateway.protocols == []
    picker = client.posts[-1][1]["json"]["reply_markup"]["inline_keyboard"]
    assert picker[0][0]["callback_data"].startswith("research_lang:")

    await bot._handle_callback(client, {
        "id": "CALLBACK0",
        "from": {"id": 7},
        "data": picker[0][0]["callback_data"],
        "message": {"message_id": 98, "chat": {"id": 11, "type": "private"}},
    })
    assert bot.gateway.protocols == []
    picker = client.posts[-1][1]["json"]["reply_markup"]["inline_keyboard"]
    callback_data = picker[1][0]["callback_data"]
    assert callback_data.startswith("research_time:")

    await bot._handle_callback(client, {
        "id": "CALLBACK1",
        "from": {"id": 7},
        "data": callback_data,
        "message": {"message_id": 99, "chat": {"id": 11, "type": "private"}},
    })

    assert len(bot.gateway.protocols) == 1
    assert bot.gateway.protocols[0].budget.max_wall_minutes == 30
    assert bot.gateway.protocols[0].budget.max_sources is None
    assert bot.gateway.protocols[0].interaction_language == "tr"

    # --lang answers the language question up front, so an explicit duration is enough to
    # start straight away.
    bot.gateway.protocols.clear()
    await bot._handle(client, {
        "from": {"id": 7},
        "chat": {"id": 11, "type": "private"},
        "text": "/research both 2 --lang en lung cancer detection by CT",
    })
    assert len(bot.gateway.protocols) == 1
    assert bot.gateway.protocols[0].budget.max_wall_minutes == 2
    assert bot.gateway.protocols[0].primary_question == "lung cancer detection by CT"
    assert bot.gateway.protocols[0].interaction_language == "en"
    assert bot.gateway.protocols[0].report_language == "en"
    # Every run it started was attributed to the linked account.
    assert set(bot.gateway.actors) == {telegram_owner}


@pytest.mark.asyncio
async def test_unlinked_telegram_user_is_told_how_to_get_linked():
    """Allowed to use the bot is not the same as having an account to own runs."""

    class FakeClient:
        def __init__(self):
            self.posts = []

        async def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return SimpleNamespace()

    class RefusingGateway:
        def for_actor(self, actor_user_id):
            raise AssertionError("unlinked user must not reach the API")

        async def start(self, protocol):
            raise AssertionError("unlinked user must not start a run")

    await create_schema()
    bot = object.__new__(TelegramResearchBot)
    bot.settings = SimpleNamespace(
        telegram_default_max_wall_minutes=20,
        telegram_max_wall_minutes=180,
        telegram_default_max_sources=None,
        telegram_default_max_rounds=3,
    )
    bot.bot_url = "https://telegram.test/botTOKEN"
    bot.gateway = RefusingGateway()
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = True
    bot.pending_research = {}
    bot.watched_runs = {}
    bot.pending_answers = {}

    client = FakeClient()
    await bot._handle(client, {
        "from": {"id": 999_777},
        "chat": {"id": 12, "type": "private"},
        "text": "/research raw bir soru sordum ama hesabim bagli degil",
    })
    sent = client.posts[-1][1]["json"]["text"]
    # Self-service now: the user is pointed at the panel rather than at an administrator.
    assert "/baglan" in sent
    assert "panel" in sent.lower()


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


@pytest.mark.asyncio
async def test_authenticated_client_api_lists_status_and_downloads(tmp_path, monkeypatch):
    """The download API the backup script uses runs on the same per-user credential."""
    archive = tmp_path / "RUN1_both.zip"
    archive.write_bytes(b"PK\x03\x04test")

    class FakeGateway:
        async def runs(self, *, limit=50):
            return [{"id": "RUN1", "limit": limit}]

        async def status(self, run_id):
            return {"id": run_id, "status": "completed"}

        async def download(self, run_id, mode, destination):
            return archive

    key = await _keyed_account("mcp-downloader@example.test")
    monkeypatch.setattr(mcp_module, "_client", lambda: FakeGateway())
    protected = BearerProtectedMCP(Starlette(routes=[]), allowed_origins=set())
    headers = {"Authorization": f"Bearer {key}"}
    with TestClient(protected) as client:
        assert client.get("/client/v1/research-runs").status_code == 401
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


# --------------------------------------------------- self-service Telegram linking


class _LinkFakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return SimpleNamespace()

    @property
    def last_text(self) -> str:
        return self.posts[-1][1]["json"]["text"]


def _link_bot() -> TelegramResearchBot:
    bot = object.__new__(TelegramResearchBot)
    bot.settings = SimpleNamespace(
        telegram_default_max_wall_minutes=20,
        telegram_max_wall_minutes=180,
        telegram_default_max_sources=None,
        telegram_default_max_rounds=3,
    )
    bot.bot_url = "https://telegram.test/botTOKEN"
    bot.gateway = SimpleNamespace()
    bot.allowed_users = set()
    bot.allowed_chats = set()
    bot.allow_group_chats = False
    bot.allow_all_users = False
    bot.pending_research = {}
    bot.watched_runs = {}
    bot.pending_answers = {}
    return bot


async def _account_with_code(email: str, ttl_seconds: int = 300) -> tuple[str, str]:
    await create_schema()
    async with SessionLocal() as session:
        user = await get_user_by_email(session, email)
        if user is None:
            user = await create_user(
                session, email=email, display_name=email, password="link-test-password"
            )
        code = await issue_telegram_link_code(
            session, user_id=user.id, ttl_seconds=ttl_seconds
        )
        return user.id, code


@pytest.mark.asyncio
async def test_link_code_binds_the_telegram_account_that_redeems_it():
    user_id, code = await _account_with_code("link-ok@example.test")
    bot, client = _link_bot(), _LinkFakeClient()

    await bot._handle(client, {
        "from": {"id": 555_001},
        "chat": {"id": 555_001, "type": "private"},
        "text": f"/baglan {code}",
    })
    assert "Bağlandı" in client.last_text
    assert await bot._resolve_actor(555_001) == user_id


@pytest.mark.asyncio
async def test_link_code_works_as_a_deep_link_start_payload():
    """The panel's t.me link arrives as "/start <code>", not as /baglan."""
    user_id, code = await _account_with_code("link-deep@example.test")
    bot, client = _link_bot(), _LinkFakeClient()

    await bot._handle(client, {
        "from": {"id": 555_002},
        "chat": {"id": 555_002, "type": "private"},
        "text": f"/start {code}",
    })
    assert "Bağlandı" in client.last_text
    assert await bot._resolve_actor(555_002) == user_id


@pytest.mark.asyncio
async def test_link_code_is_single_use():
    """A leaked code must not let a second Telegram account claim the same user."""
    user_id, code = await _account_with_code("link-once@example.test")
    bot, client = _link_bot(), _LinkFakeClient()

    await bot._handle(client, {
        "from": {"id": 555_010},
        "chat": {"id": 555_010, "type": "private"},
        "text": f"/baglan {code}",
    })
    assert await bot._resolve_actor(555_010) == user_id

    await bot._handle(client, {
        "from": {"id": 555_011},
        "chat": {"id": 555_011, "type": "private"},
        "text": f"/baglan {code}",
    })
    assert "geçersiz" in client.last_text.lower()
    assert await bot._resolve_actor(555_011) is None


@pytest.mark.asyncio
async def test_expired_link_code_is_refused():
    user_id, code = await _account_with_code("link-expired@example.test", ttl_seconds=60)
    async with SessionLocal() as session:
        user = await get_user(session, user_id)
        user.telegram_link_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    bot, client = _link_bot(), _LinkFakeClient()
    await bot._handle(client, {
        "from": {"id": 555_020},
        "chat": {"id": 555_020, "type": "private"},
        "text": f"/baglan {code}",
    })
    assert "geçersiz" in client.last_text.lower()
    assert await bot._resolve_actor(555_020) is None


@pytest.mark.asyncio
async def test_wrong_code_reveals_nothing_and_links_nobody():
    await _account_with_code("link-guess@example.test")
    bot, client = _link_bot(), _LinkFakeClient()

    await bot._handle(client, {
        "from": {"id": 555_030},
        "chat": {"id": 555_030, "type": "private"},
        "text": "/baglan ZZZZZZ",
    })
    assert "geçersiz" in client.last_text.lower()
    assert await bot._resolve_actor(555_030) is None


@pytest.mark.asyncio
async def test_link_code_accepts_the_formatting_shown_in_the_panel():
    """The panel renders A3F9K2 as A3F-9K2; typing it back must work."""
    user_id, code = await _account_with_code("link-format@example.test")
    bot, client = _link_bot(), _LinkFakeClient()

    await bot._handle(client, {
        "from": {"id": 555_040},
        "chat": {"id": 555_040, "type": "private"},
        "text": f"/baglan {format_link_code(code).lower()}",
    })
    assert "Bağlandı" in client.last_text
    assert await bot._resolve_actor(555_040) == user_id
