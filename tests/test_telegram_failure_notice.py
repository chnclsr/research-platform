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

import inspect

from datetime import UTC, datetime, timedelta

import pytest
from conftest import acting_principal

from research_platform.auth import Principal
from research_platform.db import SessionLocal, create_schema
from research_platform.identity import create_user, get_user_by_email, link_telegram
from research_platform.repository import Repository
from research_platform.schemas import ResearchProtocol, RunStatus
from research_platform.telegram_bot import (
    FAILURE_NOTICE_EVENT,
    PLAN_CANCEL_NOTICE_EVENT,
    PLAN_LIMIT_EVENT,
    TelegramResearchBot,
    plan_summary,
)


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


async def _cancelled_by_the_plan_gate(owner_id: str, *, mark: bool = True) -> str:
    """A run the gate closed after the revision limit, not one its owner cancelled."""
    run_id = await _run(owner_id, status=RunStatus.CANCELLED, error=None)
    if mark:
        async with SessionLocal() as session:
            repo = Repository(session, actor=acting_principal())
            await repo.event(run_id, PLAN_LIMIT_EVENT, {"revisions": 3})
    return run_id


@pytest.mark.asyncio
async def test_the_gate_cancelling_a_run_reaches_its_owner_once():
    """The complaint this closes: three revisions and then nothing at all."""
    owner = await _user("plancancel-owner@example.test", 5151)
    run_id = await _cancelled_by_the_plan_gate(owner)
    bot = RecordingBot()

    await bot._notify_plan_cancelled_runs(None)

    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 5151
    assert run_id in text
    assert "iptal edildi" in text
    # The limit is named, so the number is not a mystery the reader has to infer.
    assert "3" in text

    await bot._notify_plan_cancelled_runs(None)
    assert len(bot.sent) == 1
    async with SessionLocal() as session:
        marks = await Repository(session, actor=acting_principal()).events_by_types(
            run_id, {PLAN_CANCEL_NOTICE_EVENT}
        )
    assert len(marks) == 1


@pytest.mark.asyncio
async def test_a_run_the_user_cancelled_stays_silent():
    """Announcing someone's own cancellation back to them is noise, and always was."""
    owner = await _user("selfcancel-owner@example.test", 5252)
    await _cancelled_by_the_plan_gate(owner, mark=False)
    bot = RecordingBot()

    await bot._notify_plan_cancelled_runs(None)

    assert bot.sent == []


@pytest.mark.asyncio
async def test_the_two_notices_do_not_consume_each_others_marker():
    """A run can carry both markers; neither may suppress the other."""
    owner = await _user("bothnotice-owner@example.test", 5353)
    run_id = await _cancelled_by_the_plan_gate(owner)
    bot = RecordingBot()
    await bot._notify_plan_cancelled_runs(None)
    async with SessionLocal() as session:
        repo = Repository(session, actor=acting_principal())
        assert not await repo.events_by_types(run_id, {FAILURE_NOTICE_EVENT})
    # The failure notifier still ignores it: the run is cancelled, not failed.
    await bot._notify_failed_runs(None)
    assert len(bot.sent) == 1


def test_the_plan_warns_before_the_last_revision_is_spent():
    """The limit was being reached without the person rejecting having been told."""
    base = {
        "questions": {"primary": "q"},
        "budget": {"max_wall_minutes": 30, "max_sources": 8, "max_rounds": 4},
    }
    warned = plan_summary({"id": "R1", "protocol": {}}, {**base, "revisions_left": 1})
    assert "Bir değişiklik hakkınız kaldı" in warned
    for left in (3, 2, 0):
        text = plan_summary({"id": "R1", "protocol": {}}, {**base, "revisions_left": left})
        assert "hakkınız kaldı" not in text


def test_the_cancelled_run_query_does_not_distinct_over_json_columns():
    """A regression the suite cannot reach through SQLite, pinned structurally instead.

    `research_runs` carries `protocol` and `state`. The model derives JSONB but the
    migration created them as plain `json`, and PostgreSQL has no equality operator for
    that type -- so a join with DISTINCT raised UndefinedFunctionError against production
    while passing here, where SQLite does not care. The membership test avoids the whole
    question, and this asserts it stays that way.
    """
    from sqlalchemy import select as sa_select

    from research_platform.db import EventRow, ResearchRunRow

    statement = (
        sa_select(ResearchRunRow)
        .where(
            ResearchRunRow.id.in_(
                sa_select(EventRow.run_id).where(EventRow.event_type == "x")
            )
        )
    )
    assert "DISTINCT" not in str(statement).upper()
    source = inspect.getsource(Repository.list_runs_cancelled_by_event_since)
    assert ".distinct()" not in source
    assert ".in_(" in source
