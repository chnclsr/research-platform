"""
What the poll loop does when Telegram misbehaves.

`serve()` used to run its `getUpdates` call unguarded, so any failure escaped to `run()`
and ended the process; `restart: unless-stopped` then brought the bot back. On 2026-09-17
that happened seven times in two minutes -- five 502s and two read timeouts from Telegram
itself, no conflict involved.

The restart is what makes this more than noise. `offset` lives in `serve()`'s frame and
returns as 0, while Telegram treats an update as delivered only once a later poll asks for
a higher offset. Anything taken from a batch but not yet confirmed therefore came back and
was handled twice -- a repeated /research is a second run against a six-slot capacity.

So two properties are pinned here: a transient failure is retried instead of ending the
loop, and the offset moves past an update whose handling raised. The third test keeps the
409 diagnosis alive now that the container no longer crash-loops to announce it, and the
fourth keeps the bot token out of the log it is most likely to reach.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from research_platform.telegram_bot import (
    POLL_BACKOFF_MAX_S,
    POLL_BACKOFF_START_S,
    TelegramResearchBot,
    TokenRedactingFilter,
)

BOT_URL = "https://telegram.invalid/bot4242:SECRET-TOKEN"


class LoopStop(BaseException):
    """Ends serve()'s `while True` from inside the fake transport.

    Deliberately a BaseException: the loop now catches `Exception` around update handling,
    and a test sentinel that those guards could swallow would hang the suite instead of
    failing it.
    """


def _ok(updates: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"ok": True, "result": updates},
        request=httpx.Request("GET", BOT_URL + "/getUpdates"),
    )


def _status(code: int) -> httpx.Response:
    return httpx.Response(code, request=httpx.Request("GET", BOT_URL + "/getUpdates"))


class ScriptedTelegram:
    """Answers getUpdates from a script and records the offset each poll asked for."""

    def __init__(self, steps: list) -> None:
        self._steps = list(steps)
        self.offsets: list[int] = []

    async def __aenter__(self) -> ScriptedTelegram:
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def get(self, url: str, params: dict | None = None) -> httpx.Response:
        self.offsets.append((params or {})["offset"])
        if not self._steps:
            raise LoopStop()
        step = self._steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class LoopBot(TelegramResearchBot):
    """The real loop with its network edge and its database edge removed."""

    def __init__(self) -> None:
        self.bot_url = BOT_URL
        self.handled: list[int] = []
        self.explode_on: set[int] = set()

    async def _handle(self, client, message) -> None:
        update_id = message["_update_id"]
        if update_id in self.explode_on:
            raise RuntimeError("bu mesaj islenemiyor")
        self.handled.append(update_id)

    async def _handle_callback(self, client, callback) -> None:  # pragma: no cover
        raise AssertionError("bu testlerde callback yok")

    # The notices keep their own guards in serve(); they are stubbed only so the loop does
    # not reach for a database it has no business touching here.
    async def _notify_waiting_runs(self, client) -> None: ...
    async def _notify_failed_runs(self, client) -> None: ...
    async def _notify_completed_runs(self, client) -> None: ...
    async def _notify_document_revisions(self, client) -> None: ...
    async def _notify_plan_cancelled_runs(self, client) -> None: ...


@pytest.fixture
def scripted(monkeypatch):
    """Drives serve() from a script and swallows the backoff sleeps."""
    slept: list[float] = []

    async def no_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("research_platform.telegram_bot.asyncio.sleep", no_sleep)

    def build(steps: list) -> tuple[LoopBot, ScriptedTelegram, list[float]]:
        telegram = ScriptedTelegram(steps)
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: telegram)
        return LoopBot(), telegram, slept

    return build


async def _serve_until_stop(bot: LoopBot) -> None:
    with pytest.raises(LoopStop):
        await bot.serve()


async def test_transient_failure_is_retried_not_fatal(scripted):
    """A 502 and a read timeout cost a backoff, not the process."""
    bot, telegram, slept = scripted(
        [
            _status(502),
            httpx.ReadTimeout("timed out"),
            _ok([{"update_id": 7, "message": {"_update_id": 7}}]),
        ]
    )

    await _serve_until_stop(bot)

    # The update behind the two failures still arrived, which is the whole point.
    assert bot.handled == [7]
    assert slept == [POLL_BACKOFF_START_S, POLL_BACKOFF_START_S * 2]
    # A success resets the backoff, so the next outage starts patient again rather than
    # carrying yesterday's penalty.
    assert slept[-1] <= POLL_BACKOFF_MAX_S


async def test_offset_moves_past_an_update_that_could_not_be_handled(scripted):
    """The redelivery bug: a failed update must not come back on the next poll."""
    bot, telegram, _ = scripted(
        [
            _ok([{"update_id": 10, "message": {"_update_id": 10}}]),
            _ok([{"update_id": 11, "message": {"_update_id": 11}}]),
        ]
    )
    bot.explode_on = {10}

    await _serve_until_stop(bot)

    # 10 raised and 11 did not, and the loop stayed up for both.
    assert bot.handled == [11]
    # First poll starts at 0; every later poll asks past what it has already taken. If the
    # loop had died on 10, or had left the offset where it was, this would read [0, 0, ...].
    assert telegram.offsets == [0, 11, 12]


async def test_conflict_is_reported_in_the_log(scripted, caplog):
    """RestartCount no longer announces a second consumer, so the log has to."""
    bot, _, _ = scripted([_status(409)])

    with caplog.at_level(logging.ERROR, logger="research_platform.telegram_bot"):
        await _serve_until_stop(bot)

    assert any(
        record.levelno == logging.ERROR and "409" in record.getMessage()
        for record in caplog.records
    )


def test_token_is_redacted_from_exception_text():
    """httpx prints the failing URL, and for this bot the URL carries the credential."""
    token = "4242:SECRET-TOKEN"
    record = logging.LogRecord(
        name="research_platform.telegram_bot",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="getUpdates basarisiz: %s",
        args=(f"{BOT_URL}/getUpdates?offset=0",),
        exc_info=None,
    )

    assert TokenRedactingFilter(token).filter(record) is True
    assert token not in record.getMessage()
    assert "<token>" in record.getMessage()


def test_token_is_redacted_from_a_traceback():
    """The likelier leak: the credential inside a rendered traceback, not the message."""
    token = "4242:SECRET-TOKEN"
    try:
        raise httpx.ConnectError(f"connection refused for {BOT_URL}/sendMessage")
    except httpx.ConnectError:
        import sys

        record = logging.LogRecord(
            name="research_platform.telegram_bot",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="bildirim basarisiz",
            args=(),
            exc_info=sys.exc_info(),
        )

    assert TokenRedactingFilter(token).filter(record) is True
    text = record.getMessage()
    assert token not in text
    assert "<token>" in text
    # Dropped from the record so the handler cannot print an unredacted copy underneath.
    assert record.exc_info is None
