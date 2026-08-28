from __future__ import annotations

import pytest

from research_platform.schemas import HitlConfig, ResearchProtocol
from research_platform.telegram_bot import (
    TelegramResearchBot, has_explicit_duration, plan_summary,
)


class FakeGateway:
    def __init__(self, responses):
        self.responses = list(responses)

    async def start(self, protocol, *, priority="normal"):
        self.started_priority = priority
        return {"id": "RUN1", "status": "queued"}

    async def status(self, run_id):
        return self.responses.pop(0) if self.responses else {"status": "running"}


class RecordingBot(TelegramResearchBot):
    """The real bot with its network edges replaced, so the logic stays under test."""

    def __init__(self):
        self.sent = []
        self.pending_research = {}
        self.watched_runs = {}
        self.pending_answers = {}
        self.bot_url = "https://telegram.invalid/botX"

    async def _send_message(self, client, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append((chat_id, text, reply_markup))

    async def _clear_markup(self, client, chat_id, message_id):
        return None

    async def _answer_callback(self, client, callback_id, text, alert=False):
        return None


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
    await bot._start_research(None, 55, 7, protocol(plan_review=True), FakeGateway([]))
    assert "RUN1" in bot.watched_runs
    assert "planı onayınıza sunacağım" in bot.sent[0][1]

    bot.watched_runs["RUN1"]["gateway"] = FakeGateway([
        {
            "id": "RUN1",
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
        {"id": "RUN1", "status": "awaiting_input", "interaction": {
            "interaction_id": "INT1", "type": "plan_review", "data": {"plan": {}},
        }},
    ])
    await bot._notify_waiting_runs(None)
    chat_id, announcement, markup = bot.sent[-1]
    assert "Plan onayı bekleniyor" in announcement
    assert "max_rounds" in announcement
    # The decision is two taps now; the command wording is gone from the message and lives
    # only in /help, where it belongs as the after-a-restart fallback.
    assert "/respond" not in announcement
    buttons = markup["inline_keyboard"][0]
    assert [item["callback_data"] for item in buttons] == [
        "plan_review:RUN1:approve", "plan_review:RUN1:reject",
    ]

    # The same interaction must not be announced twice on the next poll.
    before = len(bot.sent)
    await bot._notify_waiting_runs(None)
    assert len(bot.sent) == before


@pytest.mark.asyncio
async def test_an_opted_out_run_is_not_watched_and_says_so():
    bot = RecordingBot()
    await bot._start_research(None, 55, 7, protocol(plan_review=False), FakeGateway([]))
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


def test_plan_summary_speaks_the_language_the_request_arrived_in():
    base = {
        "questions": {
            "primary": "Which methods detect pulmonary nodules?",
            "sub_questions": ["Which datasets are used?"],
        },
        "query_plan": [{"query": "pulmonary nodule detection CT"}],
        "budget": {"max_wall_minutes": 30, "max_rounds": 4},
        "effective_limits": [{"limit": "max_rounds", "binding": False}],
    }
    run = {"id": "RUN1", "protocol": {"label": "nodule_detection_ct"}}
    english = plan_summary(run, {**base, "display_language": "en"})
    assert "Plan awaiting approval" in english
    assert "Query branches" in english
    assert "Non-binding limit" in english
    # The topic reads at a glance; the id stays as tap-to-copy code beside it.
    assert "nodule_detection_ct" in english
    assert "<code>RUN1</code>" in english

    turkish = plan_summary(run, {
        **base,
        "display_language": "tr",
        "questions": {
            **base["questions"],
            "translated": True,
            "original": "Hangi yöntemler nodül tespit ediyor?",
            "sub_questions_display": ["Hangi veri setleri kullanılıyor?"],
        },
    })
    assert "Plan onayı bekleniyor" in turkish
    # The reader's own wording leads, the operational English stays underneath.
    assert turkish.index("Hangi yöntemler nodül") < turkish.index("Which methods detect")
    assert "Hangi veri setleri kullanılıyor?" in turkish
    # Query branches are the strings that actually go out, so they are never translated.
    assert "pulmonary nodule detection CT" in turkish


@pytest.mark.asyncio
async def test_the_scoping_interview_asks_one_question_at_a_time_and_submits_once():
    bot = RecordingBot()
    sent_payloads = []

    class Gateway:
        async def status(self, run_id):
            return {
                "id": run_id,
                "status": "awaiting_input",
                "protocol": {"interaction_language": "en"},
                "interaction": {
                    "interaction_id": "INT1",
                    "type": "planning_questions",
                    "data": {"questions": [
                        {"question": "Which angle matters?", "options": ["Clinical", "Cost"]},
                        {"question": "Which sources count?", "options": ["Trials", "Registries"]},
                    ]},
                },
            }

        async def respond(self, run_id, interaction_id, payload):
            sent_payloads.append((run_id, interaction_id, payload))
            return {"id": run_id, "status": "queued"}

    bot.watched_runs["RUN1"] = {
        "chat_id": 11, "user_id": 7, "gateway": Gateway(), "notified": None,
        "language": "en",
    }
    await bot._notify_waiting_runs(None)
    # Intro plus the first question only: the interview does not dump everything at once.
    assert "2 questions" in bot.sent[0][1]
    assert "Question 1/2" in bot.sent[1][1]
    assert bot.sent[1][2]["inline_keyboard"][0][0]["callback_data"] == "plan_answer:RUN1:0:0"
    assert sent_payloads == []

    await bot._handle_answer_callback(
        None, "CB1", ["plan_answer", "RUN1", "0", "0"], 11, {"message_id": 1}
    )
    assert "Question 2/2" in bot.sent[-1][1]
    # A typed answer is accepted in place of tapping an option.
    await bot._handle(None, {
        "from": {"id": 7}, "chat": {"id": 11, "type": "private"}, "text": "Registries only",
    })
    assert "anything you would like to add" in bot.sent[-1][1]
    assert sent_payloads == []

    await bot._handle(None, {
        "from": {"id": 7}, "chat": {"id": 11, "type": "private"}, "text": "Focus on Europe",
    })
    # One submission carrying every answer, including the closing note.
    assert len(sent_payloads) == 1
    run_id, interaction_id, payload = sent_payloads[0]
    assert (run_id, interaction_id) == ("RUN1", "INT1")
    assert [item["answer"] for item in payload["answers"]] == [
        "Clinical", "Registries only", "Focus on Europe",
    ]
    assert "RUN1" not in bot.pending_answers


def test_every_message_exists_in_both_languages():
    """The way this class of bug comes back is adding a string to one table only."""
    from research_platform.telegram_bot import MESSAGES

    def keys(table, prefix=""):
        found = set()
        for key, value in table.items():
            found.add(prefix + key)
            if isinstance(value, dict):
                found |= keys(value, f"{prefix}{key}.")
        return found

    assert keys(MESSAGES["tr"]) == keys(MESSAGES["en"])


def test_reply_language_prefers_the_clearest_signal():
    from research_platform.telegram_bot import reply_language

    chosen = {"protocol": {"interaction_language": "en", "original_language": "tr"}}
    assert reply_language(run=chosen) == "en"

    written = {"protocol": {"original_language": "tr"}}
    assert reply_language(run=written, message={"from": {"language_code": "en"}}) == "tr"

    assert reply_language(question="Akciğer BT'sinde yapay zeka ne yapar?") == "tr"
    # detect_language() answers "und" for short text; the client language decides then,
    # because guessing English there would mistranslate half the Turkish one-liners.
    assert reply_language(question="AI in CT?", message={"from": {"language_code": "en-GB"}}) == "en"
    assert reply_language() == "tr"


@pytest.mark.asyncio
async def test_an_english_run_is_answered_entirely_in_english():
    """The reported bug: `RUN1: yanıt alındı, durum queued` — two languages in one line."""
    bot = RecordingBot()
    bot.settings = None
    run = {
        "id": "01M0FGKAVQA2J90FYRWHWDPPKD",
        "status": "awaiting_input",
        "current_stage": "DECOMPOSE",
        "sources_count": 0,
        "claims_count": 0,
        "protocol": {"interaction_language": "en", "label": "ai_in_lung_ct"},
        "interaction": {"interaction_id": "INT1", "type": "plan_review"},
    }

    class Gateway:
        async def status(self, run_id):
            return run

        async def runs(self, limit=50):
            return [run]

        async def respond(self, run_id, interaction_id, payload):
            return {"id": run_id, "status": "queued", "protocol": run["protocol"]}

        def for_actor(self, actor):
            return self

    bot.gateway = Gateway()
    bot.allowed_users, bot.allowed_chats = set(), set()
    bot.allow_group_chats, bot.allow_all_users = False, True
    bot._resolve_actor = lambda telegram_user_id: _immediate("USER1")

    await bot._handle(None, {
        "from": {"id": 7, "language_code": "tr"},
        "chat": {"id": 11, "type": "private"},
        "text": "/respond ai_in_lung_ct approve",
    })
    reply = bot.sent[-1][1]
    assert "answer received" in reply
    assert not any(ch in reply for ch in "çğıöşüÇĞİÖŞÜ")


async def _immediate(value):
    return value


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
    text = plan_summary({"id": "RUN1", "protocol": {"label": "nodules"}}, plan)
    # Telegram rejects an over-long message rather than trimming it, so the caps inside
    # plan_summary have to hold on their own.
    assert len(text) < 4096
    assert "2 dal daha" in text
    assert "(sorudan çıkarıldı)" in text


def test_plan_summary_shows_the_answers_and_the_feedback_behind_the_plan():
    """The questions were already in the chat; what the reader gave back was not.

    Without them the approval screen asks someone to judge a plan against choices they
    can no longer see, and a revision shows only that one happened.
    """
    plan = {
        "questions": {"primary": "open source alternatives"},
        "budget": {"max_wall_minutes": 120, "max_sources": None, "max_rounds": 3},
        "planning_answers": ["Hangi dönem? -> Son 3 yıl", "Kaynak türü? -> web, academic"],
        "feedback": ["Tarihi son 1 yıl yap"],
    }
    text = plan_summary({"id": "RUN1", "protocol": {}}, plan)
    assert "Verdiğiniz yanıtlar (2)" in text
    assert "Son 3 yıl" in text
    assert "Kaynak türü? → web, academic" in text
    assert "Önceki geri bildiriminiz (1)" in text
    assert "Tarihi son 1 yıl yap" in text


def test_plan_summary_ends_the_strategy_note_on_a_boundary():
    """A fixed slice used to stop mid-word with nothing to show that anything was cut."""
    note = "Cümle bir burada biter. " * 200
    plan = {
        "questions": {"primary": "q"},
        "budget": {"max_wall_minutes": 30, "max_sources": 8, "max_rounds": 4},
        "strategy_note": note,
    }
    text = plan_summary({"id": "RUN1", "protocol": {}}, plan)
    assert len(text) < 4096
    assert "…" in text
    # The note gets the room the rest of the plan left, well past the old fixed 500.
    assert text.count("Cümle bir burada biter.") > 500 // len("Cümle bir burada biter.")
    body = text.rsplit("<blockquote expandable>", 1)[1]
    assert body.replace("</blockquote>", "").rstrip().endswith("biter. …")


def test_plan_summary_shrinks_the_strategy_note_when_the_plan_is_long():
    """The budget is shared: a plan with long lists must not push the message over."""
    plan = {
        "questions": {
            "primary": "P" * 500,
            "sub_questions": [f"sub {i} " + "x" * 200 for i in range(8)],
        },
        "query_plan": [{"query": f"query {i} " + "y" * 200} for i in range(12)],
        "budget": {"max_wall_minutes": 30, "max_sources": 8, "max_rounds": 4},
        "planning_answers": [f"soru {i} -> " + "a" * 200 for i in range(8)],
        "feedback": ["f" * 400, "g" * 400, "h" * 400],
        "strategy_note": "S" * 4000,
    }
    text = plan_summary({"id": "RUN1", "protocol": {"label": "nodules"}}, plan)
    assert len(text) < 4096


class PlanGateway:
    """Records what the plan buttons actually send."""

    def __init__(self):
        self.sent = []

    async def respond(self, run_id, interaction_id, payload):
        self.sent.append((run_id, interaction_id, payload))
        return {"id": run_id, "status": "queued",
                "protocol": {"label": "ai_in_lung_ct", "interaction_language": "tr"}}


def _watched(bot, gateway, language="tr"):
    bot.watched_runs["RUN1"] = {
        "chat_id": 11, "user_id": 7, "gateway": gateway, "notified": "INT1",
        "language": language,
    }


@pytest.mark.asyncio
async def test_the_approve_button_decides_the_plan_without_typing_an_id():
    bot = RecordingBot()
    gateway = PlanGateway()
    _watched(bot, gateway)
    await bot._handle_plan_callback(
        None, "CB1", ["plan_review", "RUN1", "approve"], 11, 7, {"message_id": 3}
    )
    assert gateway.sent == [("RUN1", "INT1", {"approved": True})]
    # The confirmation names the topic and speaks one language throughout.
    assert "ai_in_lung_ct" in bot.sent[-1][1]
    assert "queued" not in bot.sent[-1][1]
    assert "sırada" in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_the_reject_button_waits_for_a_reason_before_sending_anything():
    """A rejection with no note rebuilds the identical plan and loops to the limit."""
    bot = RecordingBot()
    gateway = PlanGateway()
    _watched(bot, gateway)
    await bot._handle_plan_callback(
        None, "CB1", ["plan_review", "RUN1", "reject"], 11, 7, {"message_id": 3}
    )
    assert gateway.sent == []
    assert "neyi değiştirelim" in bot.sent[-1][1]

    consumed = await bot._consume_interview_text(
        None, {"chat": {"id": 11}, "text": "Sadece resmî kaynaklara bak"}
    )
    assert consumed is True
    assert gateway.sent == [
        ("RUN1", "INT1", {"approved": False, "modifications": "Sadece resmî kaynaklara bak"})
    ]
    assert "RUN1" not in bot.pending_answers


@pytest.mark.asyncio
async def test_someone_elses_button_press_is_refused():
    bot = RecordingBot()
    gateway = PlanGateway()
    _watched(bot, gateway)
    await bot._handle_plan_callback(
        None, "CB1", ["plan_review", "RUN1", "approve"], 11, 999, {"message_id": 3}
    )
    assert gateway.sent == []


@pytest.mark.asyncio
async def test_a_button_from_before_a_restart_points_at_the_command_that_still_works():
    bot = RecordingBot()
    await bot._handle_plan_callback(
        None, "CB1", ["plan_review", "RUN1", "approve"], 11, 7, {"message_id": 3}
    )
    # watched_runs is process memory; the command path is the only thing that survives.
    assert "/respond RUN1 approve" in bot.sent[-1][1]


def test_run_label_names_the_topic_and_never_replaces_the_id():
    from research_platform.telegram_bot import run_label

    assert run_label({"id": "RUN1", "protocol": {"label": "ai_in_lung_ct"}}) == "ai_in_lung_ct"
    # Before VALIDATE_PROTOCOL names the run, the question stands in -- and it is the
    # original wording, so the label does not change language halfway through the run.
    early = {"id": "RUN1", "protocol": {
        "primary_question": "AI in lung CT",
        "original_question": "Akciğer BT'sinde yapay zeka",
    }}
    assert run_label(early) == "Akciger_BT_sinde_yapay_zeka"
    assert run_label({"id": "RUN1"}) == "RUN1"


def test_every_enum_value_the_bot_prints_has_a_translation():
    """The other half of the reported bug: the sentence was translated, the value was not."""
    from research_platform.control_panel_metrics import PIPELINE_STAGES
    from research_platform.schemas import DeliveryMode, RunStatus
    from research_platform.telegram_bot import MESSAGES, label_of

    for language in ("tr", "en"):
        table = MESSAGES[language]
        assert set(table["status"]) == {item.value for item in RunStatus}
        assert set(table["mode"]) == {item.value for item in DeliveryMode}
        assert {name for name, _ in PIPELINE_STAGES} <= set(table["stage"])
        # A value nobody has translated yet prints as itself rather than blanking out.
        assert label_of(table, "status", "brand_new") == "brand_new"
        assert label_of(table, "nosuchkind", "x") == "x"


def test_a_rejected_html_message_is_sent_again_as_plain_text():
    """A single unsupported entity makes Telegram drop the whole message."""
    import asyncio

    from research_platform.telegram_bot import strip_tags

    assert strip_tags("<b>A &amp; B</b>\n<blockquote expandable>x</blockquote>") == "A & B\nx"

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = "can't parse entities"

        def json(self):
            return {"ok": self.status_code < 400}

    class Client:
        def __init__(self):
            self.calls = []

        async def post(self, url, json=None, **kwargs):
            self.calls.append(json)
            return Response(400 if len(self.calls) == 1 else 200)

    bot = TelegramResearchBot.__new__(TelegramResearchBot)
    bot.bot_url = "https://telegram.invalid/botX"
    client = Client()
    asyncio.run(
        TelegramResearchBot._send_message(
            bot, client, 11, "<b>Plan</b> &amp; more", parse_mode="HTML"
        )
    )
    assert len(client.calls) == 2
    assert "parse_mode" not in client.calls[1]
    assert client.calls[1]["text"] == "Plan & more"


@pytest.mark.asyncio
async def test_the_language_question_is_asked_in_the_language_of_the_request():
    """Asking "Which language should we continue in?" in English about a Turkish
    request answers itself wrongly before the user has chosen anything."""
    bot = RecordingBot()
    bot.settings = type("S", (), {
        "telegram_default_max_wall_minutes": 30, "telegram_max_wall_minutes": 180,
        "telegram_default_max_sources": None, "telegram_default_max_rounds": 4,
    })()
    bot.allowed_users, bot.allowed_chats = set(), set()
    bot.allow_group_chats, bot.allow_all_users = False, True
    bot._resolve_actor = lambda telegram_user_id: _immediate("USER1")
    bot.gateway = FakeGateway([])
    bot.gateway.for_actor = lambda actor: bot.gateway

    # A Turkish request from a client set to English still gets a Turkish prompt.
    await bot._handle(None, {
        "from": {"id": 7, "language_code": "en"},
        "chat": {"id": 11, "type": "private"},
        "text": "/research Son 3 ay içinde akciğer BT görüntülerinden radyoloji raporu "
                "yazan yapay zeka çalışmalarını araştır",
    })
    assert "Hangi dilde ilerleyelim" in bot.sent[-1][1]

    await bot._handle(None, {
        "from": {"id": 7, "language_code": "tr"},
        "chat": {"id": 11, "type": "private"},
        "text": "/research Find the open weight models that write radiology reports "
                "from CT scans and compare them with the closed ones",
    })
    assert "Which language should we continue in" in bot.sent[-1][1]

    # detect_language() answers "und" for anything short, and the client setting decides
    # there. That fallback stays: Turkish typed without its diacritics carries no Turkish
    # signal either, and calling it English would be the same bug pointed the other way.
    await bot._handle(None, {
        "from": {"id": 7, "language_code": "tr"},
        "chat": {"id": 11, "type": "private"},
        "text": "/research AI in lung CT",
    })
    assert "Hangi dilde ilerleyelim" in bot.sent[-1][1]


class RunsGateway:
    """A gateway that records every call, so a lookup that should not happen is visible."""

    def __init__(self, runs):
        self._runs = list(runs)
        self.listed = 0
        self.actions = []
        self.downloads = []

    async def runs(self, limit=50):
        self.listed += 1
        return self._runs[:limit]

    async def action(self, run_id, action):
        self.actions.append((run_id, action))
        return {"id": run_id, "status": "cancelled",
                "protocol": {"label": "ai_in_lung_ct"}}

    async def download(self, run_id, mode, destination):
        self.downloads.append((run_id, mode))
        return destination

    def for_actor(self, actor):
        return self


def _run(run_id, label, status="running", stage="ACQUIRE", created="2026-08-20T14:19:00+00:00"):
    return {
        "id": run_id, "status": status, "current_stage": stage,
        "sources_count": 0, "claims_count": 0, "created_at": created,
        "protocol": {"label": label, "interaction_language": "tr"},
    }


def _bot_with(gateway):
    bot = RecordingBot()
    bot.settings = type("S", (), {"gateway_download_dir": "."})()
    bot.gateway = gateway
    bot.allowed_users, bot.allowed_chats = set(), set()
    bot.allow_group_chats, bot.allow_all_users = False, True
    bot._resolve_actor = lambda telegram_user_id: _immediate("USER1")
    return bot


def _message(text):
    return {"from": {"id": 7, "language_code": "tr"}, "chat": {"id": 11, "type": "private"},
            "text": text}


@pytest.mark.asyncio
async def test_cancel_accepts_the_label_the_bot_itself_printed():
    """The reported bug: the bot names a run, then does not answer to that name."""
    gateway = RunsGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/cancel ai_in_lung_ct"))
    assert gateway.actions == [("01M0FGKAVQA2J90FYRWHWDPPKD", "cancel")]

    # Case is not part of the name: the label is printed capitalised in some messages.
    await bot._handle(None, _message("/cancel AI_IN_LUNG_CT"))
    assert gateway.actions[-1][0] == "01M0FGKAVQA2J90FYRWHWDPPKD"


@pytest.mark.asyncio
async def test_a_run_id_argument_costs_no_extra_lookup():
    gateway = RunsGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/cancel 01M0FGKAVQA2J90FYRWHWDPPKD"))
    assert gateway.actions == [("01M0FGKAVQA2J90FYRWHWDPPKD", "cancel")]
    assert gateway.listed == 0


@pytest.mark.asyncio
async def test_an_unknown_name_cancels_nothing_and_points_at_the_listing():
    gateway = RunsGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/cancel yok_boyle_bir_sey"))
    assert gateway.actions == []
    assert "/kosular" in bot.sent[-1][1]


@pytest.mark.asyncio
async def test_two_runs_sharing_a_name_are_listed_rather_than_guessed_between():
    """/cancel cannot be undone, so an ambiguous name must not pick one."""
    gateway = RunsGateway([
        _run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct"),
        _run("01M0E2ZZZZA2J90FYRWHWDQW7", "ai_in_lung_ct", status="completed"),
    ])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/cancel ai_in_lung_ct"))
    assert gateway.actions == []
    reply = bot.sent[-1][1]
    assert "01M0FGKAVQA2J90FYRWHWDPPKD" in reply
    assert "01M0E2ZZZZA2J90FYRWHWDQW7" in reply


@pytest.mark.asyncio
async def test_a_run_from_before_labels_is_found_by_its_derived_name():
    gateway = RunsGateway([{
        "id": "01M0FGKAVQA2J90FYRWHWDPPKD", "status": "running",
        "current_stage": "ACQUIRE", "created_at": "2026-08-20T14:19:00+00:00",
        "protocol": {"primary_question": "AI in lung CT"},
    }])
    bot = _bot_with(gateway)
    # run_label() derives a name for runs whose protocol has no label field yet, and the
    # lookup goes through the same helper, so the two can never disagree.
    await bot._handle(None, _message("/cancel AI_lung_CT"))
    assert gateway.actions == [("01M0FGKAVQA2J90FYRWHWDPPKD", "cancel")]


@pytest.mark.asyncio
async def test_get_downloads_the_resolved_id_not_the_label():
    gateway = RunsGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    bot._send_document = lambda client, chat_id, path: _immediate(None)
    await bot._handle(None, _message("/get ai_in_lung_ct raw"))
    assert gateway.downloads[0][0] == "01M0FGKAVQA2J90FYRWHWDPPKD"


@pytest.mark.asyncio
async def test_the_listing_names_every_run_and_offers_a_copyable_command():
    gateway = RunsGateway([
        _run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct"),
        _run("01M0E2ZZZZA2J90FYRWHWDQW7", "nodule_detection", status="completed",
             stage="COMPLETE"),
    ])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/kosular"))
    listing = bot.sent[-1][1]
    # Telegram links a bare /command but drops its argument, so the whole line is a code
    # span the reader can copy in one tap.
    assert "<code>/status ai_in_lung_ct</code>" in listing
    assert "<code>/get nodule_detection</code>" in listing
    assert "çalışıyor" in listing and "tamamlandı" in listing

    empty = _bot_with(RunsGateway([]))
    await empty._handle(None, _message("/runs"))
    assert "Henüz bir araştırmanız yok" in empty.sent[-1][1]


def test_only_a_ulid_shaped_argument_skips_the_lookup():
    from research_platform.telegram_bot import looks_like_run_id

    assert looks_like_run_id("01M0FGKAVQA2J90FYRWHWDPPKD") is True
    assert looks_like_run_id("ai_in_lung_ct") is False
    assert looks_like_run_id("artificial_intelligence_last_3m") is False
    assert looks_like_run_id("01M0FGKAVQA2J90FYRWHWDPPK") is False


class PriorityGateway(RunsGateway):
    def __init__(self, runs):
        super().__init__(runs)
        self.priorities = []

    async def set_priority(self, run_id, priority):
        self.priorities.append((run_id, priority))
        return {"id": run_id, "status": "queued",
                "protocol": {"label": "ai_in_lung_ct", "interaction_language": "tr"}}


@pytest.mark.asyncio
async def test_a_waiting_run_can_be_moved_between_bands_by_name():
    gateway = PriorityGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/oncelik ai_in_lung_ct acil"))
    assert gateway.priorities == [("01M0FGKAVQA2J90FYRWHWDPPKD", "urgent")]
    assert "acil" in bot.sent[-1][1].casefold()

    # Both languages of the word, and the English command name.
    await bot._handle(None, _message("/priority ai_in_lung_ct normal"))
    assert gateway.priorities[-1] == ("01M0FGKAVQA2J90FYRWHWDPPKD", "normal")


@pytest.mark.asyncio
async def test_an_unusable_urgency_word_changes_nothing():
    gateway = PriorityGateway([_run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")])
    bot = _bot_with(gateway)
    await bot._handle(None, _message("/oncelik ai_in_lung_ct cok_acil"))
    assert gateway.priorities == []
    # And an unknown run is refused before the priority call is made at all.
    await bot._handle(None, _message("/oncelik yok_boyle_bir_sey acil"))
    assert gateway.priorities == []


@pytest.mark.asyncio
async def test_the_listing_marks_urgent_runs_without_breaking_their_command():
    urgent = _run("01M0FGKAVQA2J90FYRWHWDPPKD", "ai_in_lung_ct")
    urgent["priority"] = "urgent"
    bot = _bot_with(RunsGateway([urgent]))
    await bot._handle(None, _message("/kosular"))
    listing = bot.sent[-1][1]
    assert "⚡" in listing
    # The badge is display only: the command has to stay resolvable as typed.
    assert "<code>/status ai_in_lung_ct</code>" in listing
