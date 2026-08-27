"""
Who hears about a failed run, and how often.

A run that fails used to end in silence: the bot's poll loop dropped terminal runs from its
watch list without a word, and that list only ever held runs started through the bot. The
notice is therefore driven by ownership, not by the watch list, so a run started from MCP,
the API or the panel reaches its owner too.

Two properties are easy to break by accident and are pinned here: a run is announced once,
and a failure older than the notice window is never announced -- that second one is what
keeps switching the feature on from replaying every old failure at whoever is linked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import acting_principal

from research_platform.auth import Principal
from research_platform.db import SessionLocal, create_schema
from research_platform.identity import create_user, get_user_by_email, link_telegram
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.telegram_bot import FAILURE_NOTICE_EVENT, TelegramResearchBot


class RecordingBot(TelegramResearchBot):
    """The real notifier with only its network edge replaced."""

    def __init__(self):
        self.sent = []
        self.watched_runs = {}
        self.pending_answers = {}
        self.bot_url = "https://telegram.invalid/botX"

    async def _send_message(self, client, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append((chat_id, text))


async def _user(email: str, telegram_id: int | None) -> str:
    await create_schema()
    async with SessionLocal() as session:
        existing = await get_user_by_email(session, email)
        user = existing or await create_user(
            session, email=email, display_name=email.split("@")[0], password="x" * 12
        )
        if telegram_id is not None:
            await link_telegram(session, telegram_user_id=telegram_id, user_id=user.id)
        return user.id


async def _run(owner_id: str, *, status: RunStatus, error: str | None, age_hours: float = 0.0):
    async with SessionLocal() as session:
        repo = Repository(session, actor=Principal.user(owner_id))
        row = await repo.create_run(
            ResearchProtocol(
                title="Failure notice",
                primary_question="Which methods detect pulmonary nodules on CT?",
                budget={"max_wall_minutes": 30},
                label="ai_in_lung_ct",
            )
        )
        await repo.update_run(row.id, status=status.value, error=error)
        if age_hours:
            # update_run stamps updated_at with now, so an old failure has to be aged by
            # hand -- there is no other way to exercise the window.
            aged = await session.get(type(row), row.id)
            aged.updated_at = datetime.now(UTC) - timedelta(hours=age_hours)
            await session.commit()
        return row.id


@pytest.mark.asyncio
async def test_a_failed_run_reaches_its_owners_chat_once():
    owner = await _user("failnotice-owner@example.test", 4242)
    run_id = await _run(
        owner,
        status=RunStatus.FAILED,
        error="PipelineStageTimeout: ACQUIRE exceeded its 900 second safety limit",
    )
    bot = RecordingBot()

    await bot._notify_failed_runs(None)

    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 4242
    assert run_id in text
    assert "ai_in_lung_ct" in text
    assert "PipelineStageTimeout" in text

    # The marker is what makes this once-only, and it has to survive a restart -- hence a
    # run event rather than anything held in memory.
    await bot._notify_failed_runs(None)
    assert len(bot.sent) == 1
    async with SessionLocal() as session:
        marks = await Repository(session, actor=acting_principal()).events_by_types(
            run_id, {FAILURE_NOTICE_EVENT}
        )
    assert len(marks) == 1


@pytest.mark.asyncio
async def test_a_failure_older_than_the_window_is_never_announced():
    owner = await _user("failnotice-old@example.test", 4343)
    await _run(
        owner, status=RunStatus.FAILED, error="GraphRecursionError", age_hours=72
    )
    bot = RecordingBot()

    await bot._notify_failed_runs(None)

    assert bot.sent == []


@pytest.mark.asyncio
async def test_an_owner_without_telegram_is_not_retried_every_cycle():
    owner = await _user("failnotice-unlinked@example.test", None)
    run_id = await _run(owner, status=RunStatus.FAILED, error="boom")
    bot = RecordingBot()

    await bot._notify_failed_runs(None)

    assert bot.sent == []
    # Marked anyway: without this the run would be re-examined on every poll cycle forever.
    async with SessionLocal() as session:
        marks = await Repository(session, actor=acting_principal()).events_by_types(
            run_id, {FAILURE_NOTICE_EVENT}
        )
    assert len(marks) == 1


@pytest.mark.asyncio
async def test_outcomes_that_are_not_failures_stay_quiet():
    # completed_incomplete is the common ending in this platform and means the coverage
    # target was not met, not that anything broke; cancelled is the user's own doing.
    owner = await _user("failnotice-quiet@example.test", 4444)
    for status in (RunStatus.COMPLETED, RunStatus.COMPLETED_INCOMPLETE, RunStatus.CANCELLED):
        await _run(owner, status=status, error=None)
    bot = RecordingBot()

    await bot._notify_failed_runs(None)

    assert bot.sent == []


@pytest.mark.asyncio
async def test_a_failure_with_no_recorded_reason_still_says_something():
    owner = await _user("failnotice-noreason@example.test", 4545)
    await _run(owner, status=RunStatus.FAILED, error=None)
    bot = RecordingBot()

    await bot._notify_failed_runs(None)

    assert len(bot.sent) == 1
    assert "kaydedilmemiş" in bot.sent[0][1]
