from __future__ import annotations

import pytest

from research_platform.schemas import HitlConfig, ResearchProtocol
from research_platform.telegram_bot import (
    TelegramResearchBot, has_explicit_duration, plan_summary,
)


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)

    async def start(self, protocol):
        return {"id": "RUN1", "status": "queued"}

    async def status(self, run_id):
        return self.responses.pop(0) if self.responses else {"status": "running"}


class RecordingBot(TelegramResearchBot):
    """The real bot with its network edges replaced, so the logic stays under test."""

    def __init__(self):
        self.sent = []
        self.pending_research = {}
        self.watched_runs = {}
        self.bot_url = "https://telegram.invalid/botX"

    async def _send_message(self, client, chat_id, text):
        self.sent.append((chat_id, text))


def protocol(plan_review: bool) -> ResearchProtocol:
    return ResearchProtocol(
        title="Telegram run",
        primary_question="Which methods detect pulmonary nodules on CT?",
        budget={"max_wall_minutes": 30},
        hitl=HitlConfig(plan_review=plan_review),
    )


def test_flag_parsing_keeps_the_plan_gate_out_of_the_hitl_switch():
    # --plansiz must not be mistaken for the duration, the way --hitl already is not.
    assert has_explicit_duration(["--plansiz", "lung", "CT"]) is False
    assert has_explicit_duration(["--plansiz", "45", "lung", "CT"]) is True
    assert has_explicit_duration(["--hitl", "--plansiz", "--minutes", "20", "x"]) is True


@pytest.mark.asyncio
async def test_a_started_run_is_watched_and_announced_as_waiting_for_a_plan():
    bot = RecordingBot()
    await bot._start_research(None, 55, protocol(plan_review=True), FakeGateway([]))
    assert "RUN1" in bot.watched_runs
    assert "planı onayınıza sunacağım" in bot.sent[0][1]

    bot.watched_runs["RUN1"]["gateway"] = FakeGateway([
        {
            "status": "awaiting_input",
            "interaction": {
                "interaction_id": "INT1",
                "type": "plan_review",
                "data": {"plan": {
                    "questions": {"primary": "Which methods detect nodules?",
                                  "sub_questions": ["Which datasets?"]},
                    "query_plan": [{"query": "nodule detection CT"}],
                    "budget": {"max_wall_minutes": 30, "max_rounds": 4},
                    "effective_limits": [{"limit": "max_rounds", "binding": False}],
                }},
            },
        },
        {"status": "awaiting_input", "interaction": {
            "interaction_id": "INT1", "type": "plan_review", "data": {"plan": {}},
        }},
    ])
    await bot._notify_waiting_runs(None)
    announcement = bot.sent[-1][1]
    assert "Plan onayı bekleniyor: RUN1" in announcement
    assert "/respond RUN1 approve" in announcement
    assert "max_rounds" in announcement

    # The same interaction must not be announced twice on the next poll.
    before = len(bot.sent)
    await bot._notify_waiting_runs(None)
    assert len(bot.sent) == before


@pytest.mark.asyncio
async def test_an_opted_out_run_is_not_watched_and_says_so():
    bot = RecordingBot()
    await bot._start_research(None, 55, protocol(plan_review=False), FakeGateway([]))
    assert bot.watched_runs == {}
    assert "--plansiz" in bot.sent[0][1]


@pytest.mark.asyncio
async def test_a_finished_run_stops_being_watched():
    bot = RecordingBot()
    bot.watched_runs["RUN1"] = {
        "chat_id": 55,
        "gateway": FakeGateway([{"status": "completed_incomplete"}]),
        "notified": None,
    }
    await bot._notify_waiting_runs(None)
    assert bot.watched_runs == {}
    assert bot.sent == []


def test_plan_summary_stays_inside_a_telegram_message():
    plan = {
        "questions": {
            "primary": "P" * 500,
            "sub_questions": [f"sub {i} " + "x" * 200 for i in range(8)],
        },
        "query_plan": [{"query": f"query {i} " + "y" * 200} for i in range(12)],
        "budget": {"max_wall_minutes": 30, "max_sources": 8, "max_rounds": 4},
        "effective_limits": [{"limit": "max_rounds", "binding": False}],
        "date_scope": {
            "start_date": "2024-08-19T00:00:00+00:00",
            "end_date": "2026-08-19T00:00:00+00:00",
            "inferred_from_question": True,
        },
        "strategy_note": "S" * 2000,
    }
    text = plan_summary("RUN1", plan)
    assert len(text) < 4096
    assert "6 dal daha" in text
    assert "(sorudan çıkarıldı)" in text
