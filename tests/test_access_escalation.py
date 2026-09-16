from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from conftest import acting_principal, api_headers, ensure_test_user
from fastapi.testclient import TestClient

from research_platform.access_escalation import (
    classify_blocked_response,
    classify_search_block,
)
from research_platform.acquisition import AcquisitionService
from research_platform.api import app
from research_platform.auth import Principal
from research_platform.config import get_settings
from research_platform.db import SessionLocal, create_schema
from research_platform.identity import link_telegram
from research_platform.pipeline import ResearchPipeline
from research_platform.repository import Repository
from research_platform.schemas import (
    AcquiredDocument,
    ConnectorCandidate,
    ResearchProtocol,
    RunStatus,
    SourceFamily,
)
from research_platform.telegram_bot import TelegramResearchBot, access_issue_list_text

FILLER = " The system was deployed in several organisations and evaluated for six months." * 15
CHALLENGE_HTML = "<html><title>Just a moment...</title>Checking your browser</html>"


def protocol(**overrides) -> ResearchProtocol:
    return ResearchProtocol(
        **{
            "title": "Blocked source listing",
            "primary_question": "Which accessible evidence answers this blocked source question?",
            "connectors": {"profile": "custom", "included_families": ["web"]},
            "budget": {"max_sources": 8, "max_wall_minutes": 10},
            **overrides,
        }
    )


def candidate(url: str = "https://publisher.example/article") -> ConnectorCandidate:
    return ConnectorCandidate(
        connector_id="fixture",
        family=SourceFamily.WEB,
        title="Blocked fixture source",
        url=url,
        metadata={"query_branch": "query:blocked"},
    )


def status_error(status: int, text: str = "", headers=None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://search.example/query?q=captcha+solving")
    response = httpx.Response(status, request=request, headers=headers or {}, text=text)
    return httpx.HTTPStatusError("failed", request=request, response=response)


# --- classification -------------------------------------------------------------------


def test_search_block_classifier_keeps_rate_limits_out_of_the_list() -> None:
    challenge = status_error(403, CHALLENGE_HTML, {"cf-mitigated": "challenge"})
    captcha = status_error(403, "<p>Please complete the CAPTCHA</p>")

    assert classify_search_block(challenge, {}) == "bot_block"
    assert classify_search_block(captcha, {}) == "captcha"
    assert classify_search_block(status_error(429, "too many requests"), {}) is None
    assert classify_search_block(status_error(401, "login required"), {}) is None


def test_cloudflare_proxying_alone_is_not_a_challenge() -> None:
    """cf-ray is on every Cloudflare response, including an API's plain 403 for a bad key."""
    api_error = status_error(
        403,
        '{"error": "access denied: invalid api key"}',
        {"cf-ray": "abc", "content-type": "application/json"},
    )
    plain_forbidden = status_error(403, "<h1>Forbidden</h1>", {"cf-ray": "abc"})

    assert classify_search_block(api_error, {}) is None
    assert classify_search_block(plain_forbidden, {}) is None


def test_the_query_itself_never_classifies_a_failure() -> None:
    """A run researching CAPTCHAs must not turn every failed search into a CAPTCHA."""
    echoed = status_error(503, "<p>No results for captcha solving right now</p>")

    # Without the query the echo is indistinguishable from a real page, which is why the
    # pipeline always passes what it sent.
    assert classify_search_block(echoed, {}) == "captcha"
    assert classify_search_block(echoed, {}, queries=["captcha solving"]) is None
    assert classify_search_block(
        status_error(500, "<p>Search for captcha solving failed</p>"),
        {},
        queries=["captcha solving"],
    ) is None
    # The same body without the echo is a real CAPTCHA page.
    assert classify_blocked_response(503, "<p>Solve the captcha</p>", {}) == "captcha"


def test_the_error_message_does_not_speak_when_a_response_exists() -> None:
    """httpx puts the request URL -- and so the query -- into the exception message."""
    request = httpx.Request("GET", "https://search.example/?q=captcha")
    response = httpx.Response(500, request=request, text="<p>Internal error</p>")
    error = httpx.HTTPStatusError(
        "Server error '500' for url 'https://search.example/?q=captcha'",
        request=request,
        response=response,
    )
    assert classify_search_block(error, {}) is None


def document_for(url: str, text: str, final_url: str | None = None) -> AcquiredDocument:
    service = AcquisitionService(get_settings(), httpx.AsyncClient())
    return service._document(
        candidate(url), text, "direct", ["direct"], "text/html",
        document_type="html", final_url=final_url,
    )


@pytest.mark.parametrize(
    ("url", "text", "final_url"),
    [
        (
            "https://en.wikipedia.org/wiki/CAPTCHA",
            "CAPTCHA\n\nA CAPTCHA is a challenge-response test used to tell humans from bots."
            + FILLER,
            None,
        ),
        (
            "https://docs.example.com/api",
            "API overview\n\nEndpoints return 401 Authentication required without a token."
            + FILLER,
            None,
        ),
        (
            "https://blog.example.com/p/12345",
            "How we cut inference latency in half." + FILLER,
            "https://blog.example.com/authors/jane/post-12345",
        ),
    ],
    ids=["captcha-article", "api-docs", "redirect-to-authors"],
)
def test_pages_that_merely_mention_a_wall_are_still_sources(url, text, final_url) -> None:
    document = document_for(url, text, final_url)

    assert document.success is True
    assert document.failure_reason is None


def test_a_redirect_onto_a_login_page_is_a_login_wall() -> None:
    document = document_for(
        "https://publisher.example/article/42",
        "Sign in to your account. Email. Password. Forgot your password?" + FILLER,
        "https://publisher.example/login?next=/article/42",
    )

    assert document.success is False
    assert document.access_status == "unavailable"
    assert document.failure_reason == "login_wall"
    assert document.error == "Redirected to a login page"


def test_an_interstitial_naming_a_captcha_is_labelled_as_one() -> None:
    document = document_for(
        "https://publisher.example/article",
        "Just a moment... Complete the hCaptcha below to continue.",
    )

    assert document.success is False
    assert document.error == "Bot check interstitial"
    assert document.failure_reason == "captcha"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "headers", "reason"),
    [
        (403, CHALLENGE_HTML, {"cf-mitigated": "challenge"}, "bot_block"),
        (401, "Unauthorized", {}, "login_wall"),
        (503, "<p>Service temporarily unavailable</p>", {}, None),
    ],
)
async def test_direct_fetch_names_the_wall_it_hit(status, body, headers, reason) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers=headers, text=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = AcquisitionService(get_settings(), client)
        document = await service._direct(
            "https://publisher.example/article", candidate(), []
        )

    if reason is None:
        assert document is None
    else:
        assert document.success is False
        assert document.failure_reason == reason
        assert document.error.startswith(f"HTTP {status}:")


@pytest.mark.asyncio
async def test_later_fallback_failure_does_not_erase_the_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def public_url(*args, **kwargs):
        return 0

    async def no_result(*args, **kwargs):
        return None

    blocked = AcquiredDocument(
        candidate=candidate(), success=False, error="CAPTCHA challenge", failure_reason="captcha",
    )
    ordinary_failure = AcquiredDocument(candidate=candidate(), success=False, error="reader timeout")

    async def direct(*args, **kwargs):
        return blocked

    async def final_reader(*args, **kwargs):
        return ordinary_failure

    async with httpx.AsyncClient() as client:
        service = AcquisitionService(get_settings(), client)
        monkeypatch.setattr("research_platform.acquisition.validate_public_url", public_url)
        for name in ("_github_repository", "_open_access_fulltext", "_agentsearch",
                     "_crawl4ai", "_jina_reader"):
            monkeypatch.setattr(service, name, no_result)
        monkeypatch.setattr(service, "_scholarly_metadata_document", lambda *args: None)
        monkeypatch.setattr(service, "_direct", direct)
        monkeypatch.setattr(service, "_scrapling", final_reader)
        result = await service.acquire(candidate())

    assert result.failure_reason == "captcha"
    assert result.error == "CAPTCHA challenge"


# --- recording ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_repeated_block_is_one_item_and_the_list_is_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await create_schema()
    capped = get_settings().model_copy(update={"access_escalation_max_items_per_run": 2})
    monkeypatch.setattr("research_platform.repository.get_settings", lambda: capped)
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        first = await repo.enqueue_access_issue(
            run.id, kind="source_url", reason="bot_block",
            url="https://publisher.example/article", connector_id="fixture",
            detail="security challenge",
        )
        repeated = await repo.enqueue_access_issue(
            run.id, kind="source_url", reason="bot_block",
            url="https://publisher.example/article/", connector_id="fixture",
        )
        second = await repo.enqueue_access_issue(
            run.id, kind="search_query", reason="captcha", query="Blocked  Query",
            connector_id="fixture",
        )
        over_cap = await repo.enqueue_access_issue(
            run.id, kind="source_url", reason="login_wall",
            url="https://other.example/", connector_id="fixture",
        )
        issues = await repo.list_access_issues(run.id)

    assert repeated.id == first.id
    assert repeated.occurrences == 2
    assert second is not None
    assert over_cap is None
    assert [issue.id for issue in issues] == [first.id, second.id]


class BlockedAcquisition:
    def __init__(self) -> None:
        self.parser_overrides: dict[str, str] = {}

    async def acquire(self, item: ConnectorCandidate) -> AcquiredDocument:
        return AcquiredDocument(
            candidate=item,
            success=False,
            access_status="unavailable",
            acquisition_method="direct",
            strategies_tried=["direct", "crawl4ai", "jina_reader"],
            error="Bot check interstitial",
            failure_reason="bot_block",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_acquisition_records_a_block_only_when_enabled(enabled: bool) -> None:
    await create_schema()
    settings = get_settings().model_copy(update={"access_escalation_enabled": enabled})
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        pipeline = ResearchPipeline(settings, session, client)
        pipeline.acquisition = BlockedAcquisition()
        result = await pipeline._acquire_node(
            {
                "run_id": run.id,
                "protocol": protocol().model_dump(mode="json"),
                "candidates": [candidate().model_dump(mode="json")],
                "budget_started_at": datetime.now(UTC).isoformat(),
            }
        )
        issues = await repo.list_access_issues(run.id)
        events = await repo.events_by_types(run.id, {"access_issues_queued"})

    # Recording never changes what the round does with the document.
    assert len(result["documents"]) == 1
    assert result["documents"][0]["success"] is False
    if not enabled:
        assert issues == [] and events == []
        return
    assert len(issues) == 1
    assert issues[0].kind == "source_url"
    assert issues[0].strategies_tried == ["direct", "crawl4ai", "jina_reader"]
    assert issues[0].context["title"] == "Blocked fixture source"
    assert events[0].payload["count"] == 1


class ChallengedConnector:
    id = "challenged_web"
    family = SourceFamily.WEB

    def missing_credentials(self):
        return []

    async def search(self, query: str, limit: int = 20):
        raise status_error(403, CHALLENGE_HTML, {"cf-mitigated": "challenge"})


class ChallengedRegistry:
    def selected(self, selection):
        return [ChallengedConnector()]


@pytest.mark.asyncio
async def test_a_blocked_search_is_listed_and_the_run_still_finishes() -> None:
    await create_schema()
    settings = get_settings().model_copy(update={"access_escalation_enabled": True})
    run_protocol = protocol(
        research_mode="focused_answer",
        budget={"max_rounds": 1, "max_sources": 5, "max_wall_minutes": 5,
                "results_per_connector": 2},
        hitl={"plan_review": False},
    )
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        repo = Repository(session, actor=acting_principal())
        row = await repo.create_run(run_protocol)
        pipeline = ResearchPipeline(settings, session, client)
        pipeline.registry = ChallengedRegistry()
        await pipeline.run(row.id)
        finished = await repo.get_run(row.id)
        issues = await repo.list_access_issues(row.id)

    assert finished.status == RunStatus.COMPLETED_INCOMPLETE.value
    assert issues
    assert {issue.kind for issue in issues} == {"search_query"}
    assert {issue.reason for issue in issues} == {"bot_block"}
    assert {issue.connector_id for issue in issues} == {"challenged_web"}
    assert all(issue.query for issue in issues)


# --- presentation ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_lists_a_runs_blocked_items_to_its_owner_only() -> None:
    await ensure_test_user()
    stranger = "01ACCESSSTRANGER".ljust(26, "0")
    await ensure_test_user(stranger, role="user")
    await create_schema()
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        run = await repo.create_run(protocol())
        await repo.enqueue_access_issue(
            run.id, kind="source_url", reason="login_wall",
            url="https://publisher.example/login-wall", connector_id="fixture",
            context={"title": "A paper behind a login"},
        )

    with TestClient(app) as client:
        listed = client.get(
            f"/v1/research-runs/{run.id}/access-issues", headers=api_headers()
        )
        foreign = client.get(
            f"/v1/research-runs/{run.id}/access-issues", headers=api_headers(stranger)
        )

    assert listed.status_code == 200, listed.text
    [issue] = listed.json()
    assert issue["title"] == "A paper behind a login"
    assert issue["reason"] == "login_wall"
    assert "status" not in issue
    assert foreign.status_code == 404


def test_telegram_list_escapes_and_stays_inside_one_message() -> None:
    issues = [
        {
            "kind": "source_url", "reason": "captcha", "title": "<b>Bold</b> & co",
            "url": 'https://publisher.example/a?x=1&y="2"',
        },
        {"kind": "search_query", "reason": "bot_block", "query": "lung <ct>"},
    ]
    text = access_issue_list_text(issues, "tr")

    assert "Erişim engeline takılanlar" in text
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; co" in text
    assert 'href="https://publisher.example/a?x=1&amp;y=&quot;2&quot;"' in text
    assert "lung &lt;ct&gt;" in text
    assert "oturum" not in text and "CAPTCHA" in text

    many = [{"kind": "source_url", "reason": "bot_block", "url": f"https://x.example/{i}" * 8}
            for i in range(100)]
    long_text = access_issue_list_text(many, "en")
    assert len(long_text) < 4096
    assert "more; the control panel lists them all." in long_text
    assert access_issue_list_text([], "en") == "No search or source in this run was blocked."


class NoticeGateway:
    def __init__(self, run_id: str, *, issues_fail: bool) -> None:
        self.run_id = run_id
        self.issues_fail = issues_fail

    def for_actor(self, actor):
        return self

    async def revisions(self, run_id):
        if run_id != self.run_id:
            return []
        return [{"status": "accepted", "revision_number": 1, "artifacts": []}]

    async def access_issues(self, run_id):
        if self.issues_fail:
            raise httpx.ConnectError("api unavailable")
        return [{"id": "I1", "kind": "source_url", "reason": "captcha",
                 "url": "https://publisher.example/a"}]


class NoticeBot(TelegramResearchBot):
    def __init__(self, gateway) -> None:
        self.gateway = gateway
        self.sent: list[tuple[int, str, dict | None]] = []

    async def _send_message(self, client, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append((chat_id, text, reply_markup))


@pytest.mark.asyncio
@pytest.mark.parametrize("issues_fail", [False, True])
async def test_completion_notice_mentions_blocked_items_without_depending_on_them(
    issues_fail: bool,
) -> None:
    owner = ("01NOTICE" + ("F" if issues_fail else "O")).ljust(26, "0")
    telegram_id = 990_000_000_001 + int(issues_fail)
    await ensure_test_user(owner, role="user")
    async with SessionLocal() as session:
        await link_telegram(session, telegram_user_id=telegram_id, user_id=owner)
        await session.commit()
        repo = Repository(session, actor=Principal.user(owner, "user"))
        run = await repo.create_run(protocol())
        await repo.update_run(run.id, status=RunStatus.COMPLETED.value)

    bot = NoticeBot(NoticeGateway(run.id, issues_fail=issues_fail))
    await bot._notify_completed_runs(None)
    mine = [item for item in bot.sent if item[0] == telegram_id]

    # The report notice goes out either way.
    assert mine, "report notice was not sent"
    buttons = [
        button["callback_data"]
        for row in (mine[0][2] or {}).get("inline_keyboard", [])
        for button in row
        if "callback_data" in button
    ]
    if issues_fail:
        assert len(mine) == 1
        assert f"accesslist:{run.id}" not in buttons
    else:
        assert len(mine) == 2
        assert f"accesslist:{run.id}" in buttons
        assert "1 arama veya kaynak" in mine[1][1] or "1 searches" in mine[1][1]
