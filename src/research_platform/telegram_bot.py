from __future__ import annotations

import asyncio
import html
import logging
import re
import secrets
import shlex
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .auth import Principal
from .config import get_settings
from .db import SessionLocal
from .gateway_client import ResearchGatewayClient
from .identity import consume_telegram_link_code, principal_from_telegram, telegram_ids_for
from .normalization import detect_language
from .queueing import NORMAL, PRIORITIES, URGENT, normalize_priority
from .repository import Repository
from .schemas import DeliveryMode, HitlConfig, ResearchBudget, ResearchProtocol
from .scoping import slugify

logger = logging.getLogger(__name__)

# Marks a run whose failure has been announced. A run event rather than a column: no
# migration, and it survives a bot restart so nobody is told twice.
FAILURE_NOTICE_EVENT = "telegram_failure_notified"

# Every word the bot says, in both languages. One table rather than several: a new string
# has exactly one place to go, and the key-parity test catches the half that gets
# forgotten. The research itself still runs in English -- this is only what the chat reads.
MESSAGES = {
    "tr": {
        "help": """Research Platform komutları:
/baglan <kod>   — Telegram hesabınızı platform hesabınıza bağlar
/whoami
/research [raw|result|both] [dakika|--minutes N] [--dil tr|en] [--acil] [--hitl] [--plansiz] [--sources N] <soru>
                  önce dil, süre ve aciliyet sorulur, sonra araştırmayı daraltan sorular gelir;
                  plan onayınıza sunulmadan arama başlamaz (--plansiz bunu atlar)
/kosular          son koşularınızı adlarıyla listeler
/oncelik <ad|run_id> acil|normal
                  bekleyen bir koşuyu acile alır ya da geri çeker
Aşağıdaki komutlarda <run_id> yerine koşunun adını da yazabilirsiniz.
/status <run_id>
/respond <run_id> approve|reject|answer|include ...
                  plan onayı normalde düğmeyle verilir; bu komut bot yeniden
                  başladıktan sonra düğmeler geçersiz kaldığında gerekir
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
""",
        "durations": {"fast": "⚡ Hızlı", "standard": "⚖ Standart", "deep": "🧠 Derin",
                      "max": "🔥 Maksimum"},
        "minutes": "dk",
        "choose_language": "Hangi dilde ilerleyelim? Araştırma her hâlükârda İngilizce "
                           "kaynaklarda yürür; bu seçim sohbeti, planlama sorularını ve "
                           "raporun dilini belirler.",
        "choose_duration": "Araştırma süresini seçin:\nKaynak sayısı süre boyunca "
                           "sınırsızdır; coverage yeterli olursa araştırma daha erken "
                           "tamamlanabilir.",
        "choose_priority": "Aciliyet seviyesi:\nAcil koşular sırada öne geçer ve o anda "
                           "çalışan normal bir koşuyu duraklatır; duraklatılan koşu, acil "
                           "olan bitince son checkpoint'inden devam eder.",
        "priorities": {"normal": "● Normal", "urgent": "⚡ Acil"},
        "priority_label": "Öncelik",
        "priority_usage": "Kullanım: /oncelik <ad|run_id> acil|normal",
        "priority_invalid": "Öncelik yalnız acil ya da normal olabilir.",
        "priority_set": "{run_id}: öncelik {priority}.",
        "priority_flag_invalid": "--oncelik yalnız acil veya normal olabilir.",
        "starting": "Araştırma başlatılıyor…",
        "no_permission": "Araştırma yetkiniz yok.",
        "invalid_choice": "Geçersiz seçim.",
        "expired_choice": "Bu seçim geçersiz veya süresi dolmuş.",
        "failed": "İşlem başarısız: {error}",
        "chat_not_allowed": "Bu sohbette araştırma başlatılamıyor. Botla birebir konuşun.",
        "id_unreadable": "Telegram kimliğiniz okunamadı.",
        "code_invalid": "Kod geçersiz, süresi dolmuş ya da zaten kullanılmış.\n\n"
                        "Panelden yeni bir kod alın: Ayarlar → Telegram bağlantısı.",
        "linked": "Bağlandı: {email}\n\nBundan sonra başlattığınız araştırmalar bu hesaba "
                  "ait olacak ve panelde yalnız siz göreceksiniz.\n\nBaşlamak için "
                  "/research yazın.",
        "link_usage": "Kullanım: /baglan <kod>",
        "link_hint": "Telegram hesabınız bir platform hesabına bağlı değil, bu yüzden "
                     "araştırmanızın sahibi belirlenemiyor.\n\nBağlamak için:\n"
                     "1. Kontrol paneline girin\n"
                     "2. Ayarlar → Telegram bağlantısı → Kod al\n"
                     "3. Buraya /baglan <kod> yazın (ya da paneldeki bağlantıya tıklayın)\n\n"
                     "Panel hesabınız yoksa yöneticinizden hesap açmasını isteyin.",
        "whoami": "Telegram user_id: {user_id}\nTelegram chat_id: {chat_id}",
        "started": "Run başlatıldı: {run_id}\nTeslim modu: {mode} · Öncelik: {priority}\n"
                   "Toplama bütçesi: "
                   "{minutes} dk; süre dolunca eldeki kaynakların analizi ve rapor "
                   "üretimi tamamlanır.\n{sources} kaynak, {rounds} tur{gate}\n"
                   "Durum için: /status {run_id}",
        "sources_unlimited": "süreye bağlı sınırsız",
        "gate_wait": "\nBirazdan araştırmayı daraltmak için birkaç soru soracağım, sonra "
                     "planı onayınıza sunacağım.",
        "gate_skipped": "\nPlan onayı atlandı (--plansiz); arama hemen başlıyor.",
        "status_line": "🧭 {run_id}\nID: {id}\nDurum: {status}\nAşama: {stage}\n"
                       "Kaynak: {sources} | İddia: {claims}",
        "status_waiting": "\nKullanıcı girdisi bekleniyor: {type}\n"
                          "Yanıt: /respond {run_id} ...",
        "resolve_unknown": "Böyle bir koşu yok: {token}\n\nSon koşularınızı görmek için "
                           "/kosular yazın.",
        "resolve_many": "Bu ada uyan {count} koşu var; hangisi olduğunu tahmin etmiyorum. "
                        "Kimliğiyle tekrar yazın:",
        "resolve_row": "<code>{id}</code> · {status} · {date}",
        "runs_header": "Son koşularınız:",
        "runs_empty": "Henüz bir araştırmanız yok. /research ile başlayabilirsiniz.",
        "runs_row": "🧭 <b>{label}</b>\n{status} · {stage} · {date}\n<code>{command}</code>",
        "run_failed": (
            "❌ <b>Araştırma başarısız</b>\n\n"
            "🧭 <b>{label}</b>\n<code>{run_id}</code>\n\n"
            "{error}\n\n"
            "<code>/status {run_id}</code> ile ayrıntıya bakabilirsiniz."
        ),
        "run_failed_no_reason": "Hata nedeni kaydedilmemiş.",
        "respond_ok": "{run_id}: yanıt alındı, durum {status}",
        "respond_none": "Bekleyen kullanıcı girdisi yok.",
        "respond_plan_usage": "approve veya reject <değişiklik> kullanın.",
        "respond_answer_usage": "answer <yanıt> kullanın.",
        "respond_source_usage": "include <alan,adları> [exclude <alan,adları>] kullanın.",
        "respond_unknown": "Bilinmeyen checkpoint türü.",
        "action_result": "{run_id}: {status}",
        "duration_range": "Süre 1-{maximum} dakika arasında olmalıdır.",
        "option_invalid": "Geçersiz veya eksik seçenek: {option}",
        "option_integer": "{option} tam sayı olmalıdır.",
        "minutes_range": "--minutes 1-{maximum} arasında olmalıdır.",
        "sources_positive": "--sources pozitif olmalıdır.",
        "question_missing": "Araştırma sorusu eksik.",
        "language_invalid": "--dil yalnız tr veya en olabilir.",
        "scoping_intro": "Araştırmayı daraltmak için {count} sorum var. Şıklardan birine "
                         "basabilir ya da kendi yanıtınızı yazabilirsiniz.",
        "scoping_question": "Soru {index}/{total}\n{question}",
        "scoping_free": "Yanıtınızı yazabilirsiniz.",
        "scoping_extra": "Son olarak: eklemek istediğiniz bir şey var mı? Yazabilir ya da "
                         "atlayabilirsiniz.",
        "scoping_extra_label": "Eklemek istediğiniz bir şey var mı?",
        "scoping_skip": "Eklemek istemiyorum",
        "scoping_done": "Teşekkürler, yanıtlarınız alındı. Planı hazırlayıp onayınıza "
                        "sunacağım.",
        # Values, not sentences. The strings around them were translated a version ago and
        # the enum tokens inside were not, which is what produced "durum queued".
        "status": {
            "queued": "sırada", "running": "çalışıyor", "awaiting_input": "girdi bekliyor",
            "paused": "duraklatıldı", "cancel_requested": "iptal bekliyor",
            "cancelled": "iptal edildi", "completed": "tamamlandı",
            "completed_incomplete": "eksik tamamlandı", "failed": "hata",
        },
        "stage": {
            "INIT": "Başlangıç", "VALIDATE_PROTOCOL": "Protokol", "DECOMPOSE": "Ayrıştırma",
            "BUILD_QUERY_BRANCHES": "Sorgu planı", "SEARCH": "Arama", "ACQUIRE": "Edinim",
            "NORMALIZE": "Normalizasyon", "CHUNK_INDEX": "Parçalama ve indeks",
            "RETRIEVE_PASSAGES": "Pasaj retrieval", "EXTRACT_EVIDENCE": "Kanıt çıkarımı",
            "ANALYZE_CLAIMS": "İddia analizi", "AUDIT": "Audit",
            "CHECK_COVERAGE": "Coverage kontrolü", "PLAN_RECOVERY": "Recovery planı",
            "ADVERSARIAL_REVIEW": "Karşı inceleme", "SYNTHESIZE_EXPORT": "Sentez ve çıktı",
            "COMPLETE": "Tamamlandı", "FAILED": "Hata",
        },
        "interaction": {
            "planning_questions": "kapsam soruları", "plan_review": "plan onayı",
            "source_review": "kaynak onayı", "outline_review": "taslak onayı",
        },
        "mode": {"raw": "ham arşiv", "result": "rapor", "both": "rapor ve ham arşiv"},
        "plan": {
            "waiting": "Plan onayı bekleniyor",
            "question": "Soru",
            "research_wording": "Araştırma dili (İngilizce)",
            "sub_questions": "Alt sorular",
            "branches": "Sorgu dalları",
            "more": "{count} dal daha",
            "duration": "Süre",
            "minutes": "dk",
            "sources": "Kaynak",
            "unlimited": "sınırsız",
            "rounds": "Tur",
            "inert": "Bağlayıcı olmayan sınır",
            "dates": "Tarih",
            "inferred": "sorudan çıkarıldı",
            "answers": "Verdiğiniz yanıtlar",
            "feedback": "Önceki geri bildiriminiz",
            "strategy": "Strateji",
            "applied": "Uyguladığım ayarlar",
            "approve_button": "✅ Onayla",
            "reject_button": "✏️ Değişiklik iste",
            "reject_prompt": "Planda neyi değiştirelim? Yazın, planı ona göre yeniden "
                             "kuracağım.",
            "approved": "Plan onaylandı, araştırma başlıyor.",
            "rejected": "Geri bildiriminiz alındı; planı yeniden kuruyorum.",
            "expired": "Bu plan düğmesi artık geçerli değil. /respond {run_id} approve ya "
                       "da /respond {run_id} reject <gerekçe> kullanın.",
            "fallback": "Onay:       /respond {run_id} approve\n"
                        "Değişiklik: /respond {run_id} reject <gerekçe>",
        },
    },
    "en": {
        "help": """Research Platform commands:
/baglan <code>  — links your Telegram account to your platform account
/whoami
/research [raw|result|both] [minutes|--minutes N] [--lang tr|en] [--urgent] [--hitl] [--plansiz] [--sources N] <question>
                  language, duration and urgency are asked first, then a few questions that narrow
                  the research; no search starts before you approve the plan (--plansiz
                  skips that)
/runs             lists your recent runs by name
/priority <name|run_id> urgent|normal
                  moves a waiting run into the other queue band
In the commands below you can use the run's name instead of <run_id>.
/status <run_id>
/respond <run_id> approve|reject|answer|include ...
                  the plan is normally approved with a button; this command is what
                  you need after a bot restart, when the buttons no longer work
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
""",
        "durations": {"fast": "⚡ Quick", "standard": "⚖ Standard", "deep": "🧠 Deep",
                      "max": "🔥 Maximum"},
        "minutes": "min",
        "choose_language": "Which language should we continue in? The research itself runs "
                           "against English sources either way; this choice sets the chat, "
                           "the scoping questions and the report language.",
        "choose_duration": "Choose the research duration:\nThe source count is unlimited "
                           "within that time; the run can finish earlier if coverage is "
                           "sufficient.",
        "choose_priority": "Urgency:\nAn urgent run goes ahead of everything waiting and "
                           "pauses a running normal one; the paused run continues from its "
                           "last checkpoint once the urgent one is done.",
        "priorities": {"normal": "● Normal", "urgent": "⚡ Urgent"},
        "priority_label": "Priority",
        "priority_usage": "Usage: /priority <name|run_id> urgent|normal",
        "priority_invalid": "Priority accepts only urgent or normal.",
        "priority_set": "{run_id}: priority {priority}.",
        "priority_flag_invalid": "--priority accepts only urgent or normal.",
        "starting": "Starting the research…",
        "no_permission": "You are not allowed to start research here.",
        "invalid_choice": "Invalid choice.",
        "expired_choice": "That choice is invalid or has expired.",
        "failed": "Request failed: {error}",
        "chat_not_allowed": "Research cannot be started in this chat. Message the bot "
                            "directly.",
        "id_unreadable": "Your Telegram identity could not be read.",
        "code_invalid": "The code is invalid, expired or already used.\n\nGet a new one "
                        "from the panel: Settings → Telegram link.",
        "linked": "Linked: {email}\n\nResearch you start from now on belongs to this "
                  "account and only you see it in the panel.\n\nType /research to begin.",
        "link_usage": "Usage: /baglan <code>",
        "link_hint": "Your Telegram account is not linked to a platform account, so a run "
                     "started here would have no owner.\n\nTo link it:\n"
                     "1. Sign in to the control panel\n"
                     "2. Settings → Telegram link → Get code\n"
                     "3. Send /baglan <code> here (or use the link in the panel)\n\n"
                     "If you have no panel account, ask your administrator for one.",
        "whoami": "Telegram user_id: {user_id}\nTelegram chat_id: {chat_id}",
        "started": "Run started: {run_id}\nDelivery mode: {mode} · Priority: {priority}\n"
                   "Collection budget: "
                   "{minutes} min; when it runs out, what was collected is analysed and "
                   "reported.\n{sources} sources, {rounds} rounds{gate}\n"
                   "Status: /status {run_id}",
        "sources_unlimited": "time-bounded, no cap",
        "gate_wait": "\nI will ask a few questions to narrow the research, then put the "
                     "plan up for your approval.",
        "gate_skipped": "\nPlan approval skipped (--plansiz); the search starts now.",
        "status_line": "🧭 {run_id}\nID: {id}\nStatus: {status}\nStage: {stage}\n"
                       "Sources: {sources} | Claims: {claims}",
        "status_waiting": "\nWaiting for your input: {type}\n"
                          "Reply: /respond {run_id} ...",
        "resolve_unknown": "There is no run called that: {token}\n\nSend /runs to see your "
                           "recent runs.",
        "resolve_many": "{count} runs share that name, and I will not guess which one you "
                        "mean. Send the command again with the id:",
        "resolve_row": "<code>{id}</code> · {status} · {date}",
        "runs_header": "Your recent runs:",
        "runs_empty": "You have no research yet. Start one with /research.",
        "runs_row": "🧭 <b>{label}</b>\n{status} · {stage} · {date}\n<code>{command}</code>",
        "run_failed": (
            "❌ <b>Research failed</b>\n\n"
            "🧭 <b>{label}</b>\n<code>{run_id}</code>\n\n"
            "{error}\n\n"
            "Use <code>/status {run_id}</code> for the details."
        ),
        "run_failed_no_reason": "No failure reason was recorded.",
        "respond_ok": "{run_id}: answer received, status {status}",
        "respond_none": "There is no pending checkpoint.",
        "respond_plan_usage": "Use approve, or reject <what to change>.",
        "respond_answer_usage": "Use answer <your answer>.",
        "respond_source_usage": "Use include <domains> [exclude <domains>].",
        "respond_unknown": "Unknown checkpoint type.",
        "action_result": "{run_id}: {status}",
        "duration_range": "Duration must be between 1 and {maximum} minutes.",
        "option_invalid": "Invalid or incomplete option: {option}",
        "option_integer": "{option} must be an integer.",
        "minutes_range": "--minutes must be between 1 and {maximum}.",
        "sources_positive": "--sources must be positive.",
        "question_missing": "The research question is missing.",
        "language_invalid": "--lang accepts only tr or en.",
        "scoping_intro": "I have {count} questions to narrow the research. Tap an option "
                         "or type your own answer.",
        "scoping_question": "Question {index}/{total}\n{question}",
        "scoping_free": "Type your answer.",
        "scoping_extra": "Last one: is there anything you would like to add? Type it, or "
                         "skip.",
        "scoping_extra_label": "Anything you would like to add?",
        "scoping_skip": "Nothing to add",
        "scoping_done": "Thank you, your answers are in. I will prepare the plan and put "
                        "it up for approval.",
        "status": {
            "queued": "queued", "running": "running", "awaiting_input": "awaiting input",
            "paused": "paused", "cancel_requested": "cancelling",
            "cancelled": "cancelled", "completed": "completed",
            "completed_incomplete": "completed with gaps", "failed": "failed",
        },
        "stage": {
            "INIT": "Start", "VALIDATE_PROTOCOL": "Protocol", "DECOMPOSE": "Decomposition",
            "BUILD_QUERY_BRANCHES": "Query plan", "SEARCH": "Search",
            "ACQUIRE": "Acquisition", "NORMALIZE": "Normalisation",
            "CHUNK_INDEX": "Chunking and index", "RETRIEVE_PASSAGES": "Passage retrieval",
            "EXTRACT_EVIDENCE": "Evidence extraction", "ANALYZE_CLAIMS": "Claim analysis",
            "AUDIT": "Audit", "CHECK_COVERAGE": "Coverage check",
            "PLAN_RECOVERY": "Recovery plan", "ADVERSARIAL_REVIEW": "Adversarial review",
            "SYNTHESIZE_EXPORT": "Synthesis and export", "COMPLETE": "Completed",
            "FAILED": "Failed",
        },
        "interaction": {
            "planning_questions": "scoping questions", "plan_review": "plan approval",
            "source_review": "source approval", "outline_review": "outline approval",
        },
        "mode": {"raw": "raw archive", "result": "report", "both": "report and raw archive"},
        "plan": {
            "waiting": "Plan awaiting approval",
            "question": "Question",
            "research_wording": "Research wording (English)",
            "sub_questions": "Sub-questions",
            "branches": "Query branches",
            "more": "{count} more branches",
            "duration": "Duration",
            "minutes": "min",
            "sources": "Sources",
            "unlimited": "unlimited",
            "rounds": "Rounds",
            "inert": "Non-binding limit",
            "dates": "Dates",
            "inferred": "inferred from the question",
            "answers": "Your answers",
            "feedback": "Your earlier feedback",
            "strategy": "Strategy",
            "applied": "Settings I applied",
            "approve_button": "✅ Approve",
            "reject_button": "✏️ Request changes",
            "reject_prompt": "What should change in the plan? Type it and I will rebuild "
                             "the plan around it.",
            "approved": "Plan approved, the research is starting.",
            "rejected": "Your feedback is in; I am rebuilding the plan.",
            "expired": "This plan button is no longer valid. Use /respond {run_id} approve "
                       "or /respond {run_id} reject <reason>.",
            "fallback": "Approve: /respond {run_id} approve\n"
                        "Changes: /respond {run_id} reject <reason>",
        },
    },
}

RESEARCH_TIME_OPTIONS = (("fast", 10), ("standard", 30), ("deep", 120), ("max", 180))
PENDING_REQUEST_TTL_SECONDS = 15 * 60


def text_for(language: str) -> dict:
    return MESSAGES["en" if language == "en" else "tr"]


def label_of(strings: dict, kind: str, value: Any) -> str:
    """Translate one enum value, or print it as it came.

    A status or stage the table has not heard of shows its raw token rather than an empty
    string: a new RunStatus member should read oddly for one release, not silently blank
    out the sentence it sits in.
    """
    token = str(value or "")
    return str((strings.get(kind) or {}).get(token) or token)


def looks_like_run_id(token: str) -> bool:
    """Whether this argument is already a run id rather than a label.

    A ULID is 26 characters of upper-case base32. Labels come out of slugify(), so they
    carry underscores or lower-case letters; a 26-character all-upper-case label with no
    underscore is not something the naming prompt produces. Getting it wrong costs one
    listing call and a "no such run" message, and the real id still works.
    """
    return len(token) == 26 and token.isalnum() and token.upper() == token


def run_moment(run: Mapping[str, Any]) -> str:
    """When the run was created, in the reader's own timezone."""
    raw = str(run.get("created_at") or "")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%d.%m %H:%M")


def run_label(run: Mapping[str, Any]) -> str:
    """The run's topic handle, for saying which research a message is about.

    Never a substitute for the id -- two runs on one topic share a label -- so every caller
    prints the id alongside it. Falls back to the question for the short window before
    VALIDATE_PROTOCOL has named the run.
    """
    protocol = run.get("protocol") or {}
    label = str(protocol.get("label") or "")
    if label:
        return label
    # original_question is set only when the question was translated, and never changes
    # afterwards; primary_question is the original text until then. Either way the fallback
    # stays the same string for the whole run rather than switching language mid-way.
    source = protocol.get("original_question") or protocol.get("primary_question") or ""
    return slugify(source) or str(run.get("id") or "")


def reply_language(
    *,
    run: dict | None = None,
    question: str = "",
    message: dict | None = None,
) -> str:
    """Which language to answer in, from the most reliable signal available.

    An outright choice beats the language the question happened to be written in, which in
    turn beats the language of the user's Telegram client. detect_language() only gets a
    vote when it is sure: it answers "und" for anything short, and treating that as English
    would mistranslate half the Turkish one-liners people actually send.
    """
    protocol = (run or {}).get("protocol") or {}
    chosen = protocol.get("interaction_language")
    if chosen in {"tr", "en"}:
        return chosen
    original = protocol.get("original_language")
    if original in {"tr", "en"}:
        return original
    if question:
        detected = detect_language(question)
        if detected in {"tr", "en"}:
            return detected
    client_language = str(((message or {}).get("from") or {}).get("language_code") or "")
    if client_language.lower().startswith("en"):
        return "en"
    if client_language.lower().startswith("tr"):
        return "tr"
    return "tr"


def language_keyboard(request_id: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "🇹🇷 Türkçe", "callback_data": f"research_lang:{request_id}:tr"}],
            [{"text": "🇬🇧 English", "callback_data": f"research_lang:{request_id}:en"}],
        ]
    }


def priority_keyboard(request_id: str, language: str = "tr") -> dict:
    text = text_for(language)
    return {
        "inline_keyboard": [
            [
                {
                    "text": text["priorities"][value],
                    "callback_data": f"research_prio:{request_id}:{value}",
                }
                for value in (NORMAL, URGENT)
            ]
        ]
    }


def duration_keyboard(request_id: str, language: str = "tr") -> dict:
    text = text_for(language)
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"{text['durations'][key]} · {minutes} {text['minutes']}",
                    "callback_data": f"research_time:{request_id}:{minutes}",
                }
            ]
            for key, minutes in RESEARCH_TIME_OPTIONS
        ]
    }


def take_language_flag(parts: list[str]) -> tuple[list[str], str | None]:
    """Pull `--dil en` / `--lang en` out of the command, leaving the rest untouched.

    Stripped before anything else parses the line so neither the duration detector nor the
    request parser has to know about a flag that carries a value.
    """
    tokens = list(parts)
    language = None
    index = 0
    while index < len(tokens):
        if tokens[index] in {"--dil", "--lang"}:
            value = tokens[index + 1].lower() if index + 1 < len(tokens) else ""
            if value not in {"tr", "en"}:
                raise ValueError("language_invalid")
            language = value
            del tokens[index : index + 2]
            continue
        index += 1
    return tokens, language


_PRIORITY_WORDS = {
    "acil": URGENT, "urgent": URGENT, "yuksek": URGENT, "high": URGENT,
    "normal": NORMAL, "standart": NORMAL, "low": NORMAL, "dusuk": NORMAL,
}


def read_priority(word: str) -> str | None:
    """The urgency a person typed, in either language, or None if it is not one."""
    return _PRIORITY_WORDS.get(str(word).strip().casefold().replace("ı", "i").replace("ü", "u"))


def take_priority_flag(parts: list[str]) -> tuple[list[str], str | None]:
    """Pull `--acil` / `--urgent` out of the command, leaving the rest untouched.

    A bare switch rather than a flag with a value: nobody types `--oncelik normal`, and
    the button asks anyone who does not use the switch.
    """
    tokens = [item for item in parts if item not in {"--acil", "--urgent"}]
    chosen = URGENT if len(tokens) != len(parts) else None
    return tokens, chosen


def parse_research_request(
    parts: list[str],
    *,
    default_minutes: int,
    maximum_minutes: int,
    default_sources: int | None,
    default_rounds: int,
    language: str = "tr",
) -> tuple[DeliveryMode, str, ResearchBudget]:
    text = text_for(language)
    mode = DeliveryMode.BOTH
    tokens = list(parts)
    if tokens and tokens[0] in {item.value for item in DeliveryMode}:
        mode = DeliveryMode(tokens.pop(0))
    minutes = default_minutes
    sources = default_sources
    if tokens and tokens[0].lstrip("+-").isdigit():
        minutes = int(tokens.pop(0))
        if not 1 <= minutes <= maximum_minutes:
            raise ValueError(text["duration_range"].format(maximum=maximum_minutes))
    while tokens and tokens[0].startswith("--"):
        option = tokens.pop(0)
        if option not in {"--minutes", "--sources"} or not tokens:
            raise ValueError(text["option_invalid"].format(option=option))
        try:
            value = int(tokens.pop(0))
        except ValueError as exc:
            raise ValueError(text["option_integer"].format(option=option)) from exc
        if option == "--minutes":
            if not 1 <= value <= maximum_minutes:
                raise ValueError(text["minutes_range"].format(maximum=maximum_minutes))
            minutes = value
        else:
            if value < 1:
                raise ValueError(text["sources_positive"])
            sources = value
    question = " ".join(tokens).strip()
    if not question:
        raise ValueError(text["question_missing"])
    return (
        mode,
        question,
        ResearchBudget(
            max_wall_minutes=minutes,
            max_sources=sources,
            max_rounds=default_rounds,
        ),
    )


def _quote(items: list[str]) -> str:
    """Long lists as a collapsed quote so the message stays scannable.

    Telegram renders `blockquote expandable` closed, with a tap to open it. That is what
    keeps sub-questions and query branches from burying the budget and the buttons, which
    are the parts the reader is actually deciding on.
    """
    body = "\n".join(html.escape(item) for item in items)
    return f"<blockquote expandable>{body}</blockquote>"


def plan_summary(run: Mapping[str, Any], plan: dict) -> str:
    """The approval document compressed to something readable in a chat window.

    The full plan is a large object built for the panel; a Telegram message caps at 4096
    characters, so this keeps the parts a person actually decides on -- what will be
    asked, how long it may run, and which limit will really stop it. HTML rather than
    MarkdownV2: everything interpolated here is user text, and HTML needs three characters
    escaped instead of eighteen.
    """
    questions = plan.get("questions") or {}
    branches = plan.get("query_plan") or []
    budget = plan.get("budget") or {}
    scope = plan.get("date_scope") or {}
    text = text_for(str(plan.get("display_language") or "tr"))["plan"]
    # The reader's own wording leads; the English the run uses stays underneath so a bad
    # translation can still be rejected here.
    translated = bool(questions.get("translated") and questions.get("original"))
    lead = questions["original"] if translated else questions.get("primary", "")
    lines = [
        f"🧭 <b>{html.escape(run_label(run))}</b> — {text['waiting']}",
        f"<code>{html.escape(str(run.get('id') or ''))}</code>",
        "",
        f"<b>{text['question']}</b>",
        html.escape(str(lead)[:300]),
    ]
    if translated:
        lines.append(
            f"<i>{text['research_wording']}: "
            f"{html.escape(str(questions['primary'])[:300])}</i>"
        )
    # Collapsing the long lists buys room, but not unlimited room: every cap below is
    # chosen so the worst case still lands inside Telegram's 4096 characters, because a
    # message over the limit is not truncated by Telegram -- it is rejected.
    subs = questions.get("sub_questions_display") or questions.get("sub_questions") or []
    if subs:
        lines.append("")
        lines.append(f"<b>{text['sub_questions']} ({len(subs)})</b>")
        lines.append(_quote([f"{n}. {str(item)[:140]}" for n, item in enumerate(subs[:8], 1)]))
    if branches:
        lines.append("")
        lines.append(f"<b>{text['branches']} ({len(branches)})</b>")
        shown = [f"· {str(item.get('query', ''))[:120]}" for item in branches[:10]]
        if len(branches) > 10:
            shown.append(f"· … {text['more'].format(count=len(branches) - 10)}")
        lines.append(_quote(shown))
    lines.append("")
    lines.append(
        f"⏱ <b>{budget.get('max_wall_minutes')} {text['minutes']}</b> · "
        f"{text['sources']}: {html.escape(str(budget.get('max_sources') or text['unlimited']))} · "
        f"{text['rounds']}: {budget.get('max_rounds')}"
    )
    inert = [
        row["limit"]
        for row in plan.get("effective_limits") or []
        if not row.get("binding")
    ]
    if inert:
        lines.append(f"{text['inert']}: {html.escape(', '.join(inert))}")
    if scope.get("start_date"):
        note = f" ({text['inferred']})" if scope.get("inferred_from_question") else ""
        lines.append(
            f"📅 {str(scope['start_date'])[:10]} → {str(scope.get('end_date'))[:10]}{note}"
        )
    applied = plan.get("applied_settings") or []
    if applied:
        # The answers that became protocol fields. Named separately from the rest because
        # this is the part the run has no choice about.
        summary = " · ".join(
            f"{item.get('label', '')} → {item.get('detail', '')}" for item in applied
        )
        lines.append(f"⚙️ <b>{text['applied']}</b>: {html.escape(summary[:300])}")
    if plan.get("feedback"):
        lines.append(f"{text['feedback']}: {len(plan['feedback'])}")
    if plan.get("strategy_note"):
        lines.append("")
        lines.append(f"<b>{text['strategy']}</b>")
        lines.append(f"<i>{html.escape(str(plan['strategy_note'])[:500])}</i>")
    return "\n".join(lines)


_TAG = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    """The same message without markup, for the plain-text retry."""
    return html.unescape(_TAG.sub("", text))


def _telegram_ok(response: httpx.Response) -> bool:
    if response.status_code >= 400:
        return False
    try:
        return bool(response.json().get("ok", True))
    except ValueError:
        return True


def plan_keyboard(run_id: str, language: str) -> dict:
    text = text_for(language)["plan"]
    return {
        "inline_keyboard": [
            [
                {"text": text["approve_button"],
                 "callback_data": f"plan_review:{run_id}:approve"},
                {"text": text["reject_button"],
                 "callback_data": f"plan_review:{run_id}:reject"},
            ]
        ]
    }


def has_explicit_duration(parts: list[str]) -> bool:
    tokens = [item for item in parts if item not in {"--hitl", "--plansiz"}]
    if tokens and tokens[0] in {item.value for item in DeliveryMode}:
        tokens.pop(0)
    return "--minutes" in tokens or bool(
        tokens and tokens[0].lstrip("+-").isdigit()
    )


class TelegramResearchBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        self.bot_url = (
            f"{self.settings.telegram_api_url.rstrip('/')}/bot{self.settings.telegram_bot_token}"
        )
        self.gateway = ResearchGatewayClient(
            self.settings.research_api_url,
            self.settings.service_token or self.settings.api_token,
        )
        self.allowed_users = set(self.settings.telegram_allowed_user_ids)
        self.allowed_chats = set(self.settings.telegram_allowed_chat_ids)
        self.allow_group_chats = self.settings.telegram_allow_group_chats
        self.allow_all_users = self.settings.telegram_allow_all_users
        self.pending_research: dict[str, dict] = {}
        # Runs this process started, so the chat can be told when one stops for input.
        # In-memory like pending_research: a restarted bot forgets, and the user falls
        # back to /status -- acceptable for a notice, not for state that matters.
        self.watched_runs: dict[str, dict] = {}
        # Scoping interviews in progress, keyed by run id. Also in-memory: if the bot
        # restarts mid-interview the run still waits at awaiting_input and /respond works.
        self.pending_answers: dict[str, dict] = {}

    async def _chat_allowed(self, message: dict) -> bool:
        """Whether research commands are accepted in this conversation.

        Direct chats are open: whoever is linked acts as themselves, and someone with no
        link gets told how to get one. Group chats are the exception -- several people
        share one conversation, so the sender is not reliably the person the bot should
        act for, and they stay behind the configured allow-list.
        """
        chat = message.get("chat") or {}
        if chat.get("type") not in {"group", "supergroup"}:
            return True
        if not self.allow_group_chats:
            return False
        if self.allow_all_users:
            return True
        user_id = int((message.get("from") or {}).get("id", 0))
        chat_id = int(chat.get("id", 0))
        return bool(self.allowed_users or self.allowed_chats) and (
            user_id in self.allowed_users or chat_id in self.allowed_chats
        )

    async def _link_account(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        telegram_user_id: int,
        code: str,
        language: str,
    ) -> None:
        """Redeem a link code issued by the panel."""
        text = text_for(language)
        if not telegram_user_id:
            await self._send_message(client, chat_id, text["id_unreadable"])
            return
        async with SessionLocal() as session:
            user = await consume_telegram_link_code(
                session, code=code, telegram_user_id=telegram_user_id
            )
        if user is None:
            await self._send_message(client, chat_id, text["code_invalid"])
            return
        await self._send_message(client, chat_id, text["linked"].format(email=user.email))

    async def _resolve_actor(self, telegram_user_id: int) -> str | None:
        """The platform account this Telegram user acts as, or None if unlinked.

        This is the bot's real gate. :meth:`_chat_allowed` only decides whether the
        conversation is one where research commands make sense; this decides whose
        research a message creates and reads. An unlinked sender is told how to link
        rather than being given a run that belongs to nobody.
        """
        if not telegram_user_id:
            return None
        async with SessionLocal() as session:
            principal = await principal_from_telegram(session, telegram_user_id)
        return principal.user_id if principal else None

    @staticmethod
    def _link_hint(language: str = "tr") -> str:
        return text_for(language)["link_hint"]

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str | None = None,
    ) -> None:
        payload: dict = {"chat_id": chat_id, "text": text[:4096]}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode
        response = await client.post(f"{self.bot_url}/sendMessage", json=payload)
        if parse_mode is None or _telegram_ok(response):
            return
        # One malformed or unsupported entity makes Telegram reject the whole message, and
        # until now that failure was silent -- the user simply never saw the plan. Send it
        # again as plain text rather than losing it over formatting.
        logger.warning("HTML mesaj reddedildi, duz metin deneniyor: %s", response.text[:300])
        payload.pop("parse_mode")
        payload["text"] = strip_tags(text)[:4096]
        await client.post(f"{self.bot_url}/sendMessage", json=payload)

    async def _send_document(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        path: Path,
    ) -> None:
        with path.open("rb") as handle:
            await client.post(
                f"{self.bot_url}/sendDocument",
                data={"chat_id": str(chat_id)},
                files={"document": (path.name, handle, "application/zip")},
                timeout=None,
            )

    async def _start_research(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        user_id: int,
        protocol: ResearchProtocol,
        gateway: ResearchGatewayClient,
        priority: str = NORMAL,
    ) -> None:
        language = protocol.display_language()
        text = text_for(language)
        run = await gateway.start(protocol, priority=priority)
        budget = protocol.budget
        if protocol.hitl.plan_review or protocol.hitl.planning_questions:
            self.watched_runs[run["id"]] = {
                "chat_id": chat_id,
                # Kept so a plan button can be checked against the person who pressed it,
                # not only against the chat it was pressed in.
                "user_id": user_id,
                "gateway": gateway,
                "notified": None,
                "language": language,
            }
            gate_note = text["gate_wait"]
        else:
            gate_note = text["gate_skipped"]
        await self._send_message(
            client,
            chat_id,
            text["started"].format(
                run_id=run["id"],
                mode=label_of(text, "mode", protocol.output_mode),
                priority=text["priorities"][normalize_priority(priority)],
                minutes=budget.max_wall_minutes,
                sources=budget.max_sources or text["sources_unlimited"],
                rounds=budget.max_rounds,
                gate=gate_note,
            ),
        )

    def _remember_request(self, message: dict, protocol: ResearchProtocol, **extra) -> str:
        now = time.monotonic()
        self.pending_research = {
            key: value
            for key, value in self.pending_research.items()
            if now - float(value["created_at"]) < PENDING_REQUEST_TTL_SECONDS
        }
        request_id = secrets.token_urlsafe(6)
        self.pending_research[request_id] = {
            "chat_id": int((message.get("chat") or {}).get("id", 0)),
            "user_id": int((message.get("from") or {}).get("id", 0)),
            "created_at": now,
            "protocol": protocol.model_dump(mode="json"),
            **extra,
        }
        return request_id

    async def _offer_language(
        self,
        client: httpx.AsyncClient,
        message: dict,
        protocol: ResearchProtocol,
        *,
        explicit_minutes: bool,
        priority: str | None,
        language: str,
    ) -> None:
        request_id = self._remember_request(
            message, protocol, explicit_minutes=explicit_minutes, priority=priority
        )
        await self._send_message(
            client,
            int((message.get("chat") or {}).get("id", 0)),
            text_for(language)["choose_language"],
            reply_markup=language_keyboard(request_id),
        )

    async def _offer_duration(
        self,
        client: httpx.AsyncClient,
        message: dict,
        protocol: ResearchProtocol,
        priority: str | None = None,
    ) -> None:
        language = protocol.display_language()
        request_id = self._remember_request(message, protocol, priority=priority)
        await self._send_message(
            client,
            int((message.get("chat") or {}).get("id", 0)),
            text_for(language)["choose_duration"],
            reply_markup=duration_keyboard(request_id, language),
        )

    async def _offer_priority(
        self,
        client: httpx.AsyncClient,
        message: dict,
        protocol: ResearchProtocol,
    ) -> None:
        language = protocol.display_language()
        request_id = self._remember_request(message, protocol)
        await self._send_message(
            client,
            int((message.get("chat") or {}).get("id", 0)),
            text_for(language)["choose_priority"],
            reply_markup=priority_keyboard(request_id, language),
        )

    async def _answer_callback(
        self,
        client: httpx.AsyncClient,
        callback_id: str,
        text: str,
        alert: bool = False,
    ) -> None:
        payload = {"callback_query_id": callback_id, "text": text}
        if alert:
            payload["show_alert"] = True
        await client.post(f"{self.bot_url}/answerCallbackQuery", json=payload)

    async def _clear_markup(self, client: httpx.AsyncClient, chat_id: int, message_id: int) -> None:
        await client.post(
            f"{self.bot_url}/editMessageReplyMarkup",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": {"inline_keyboard": []},
            },
        )

    def _claim_pending(self, request_id: str, chat_id: int, user_id: int) -> dict | None:
        pending = self.pending_research.pop(request_id, None)
        if pending is None:
            return None
        expired = (
            time.monotonic() - float(pending["created_at"]) >= PENDING_REQUEST_TTL_SECONDS
        )
        if expired or int(pending["chat_id"]) != chat_id or int(pending["user_id"]) != user_id:
            return None
        return pending

    async def _handle_callback(self, client: httpx.AsyncClient, callback: dict) -> None:
        callback_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id", 0))
        user = callback.get("from") or {}
        user_id = int(user.get("id", 0))
        auth_message = {"from": user, "chat": chat}
        client_language = reply_language(message=auth_message)
        if not await self._chat_allowed(auth_message):
            await self._answer_callback(
                client, callback_id, text_for(client_language)["no_permission"], alert=True
            )
            return
        parts = str(callback.get("data") or "").split(":")
        if parts and parts[0] in {"plan_answer", "plan_extra"}:
            await self._handle_answer_callback(client, callback_id, parts, chat_id, message)
            return
        if parts and parts[0] == "plan_review":
            await self._handle_plan_callback(
                client, callback_id, parts, chat_id, user_id, message
            )
            return
        if len(parts) != 3 or parts[0] not in {
            "research_time",
            "research_lang",
            "research_prio",
        }:
            await self._answer_callback(
                client, callback_id, text_for(client_language)["invalid_choice"]
            )
            return
        pending = self._claim_pending(parts[1], chat_id, user_id)
        if pending is None:
            await self._answer_callback(
                client, callback_id, text_for(client_language)["expired_choice"], alert=True
            )
            return
        protocol = ResearchProtocol.model_validate(pending["protocol"])

        if parts[0] == "research_lang":
            if parts[2] not in {"tr", "en"}:
                await self._answer_callback(
                    client, callback_id, text_for(client_language)["invalid_choice"]
                )
                return
            # The pick drives the chat, the scoping questions, the plan screen and the
            # report; the research itself still runs in English.
            protocol = protocol.model_copy(
                update={"interaction_language": parts[2], "report_language": parts[2]}
            )
            await self._answer_callback(client, callback_id, "✓")
            await self._clear_markup(client, chat_id, int(message.get("message_id", 0)))
            follow_up = {"chat": chat, "from": user}
            if not pending.get("explicit_minutes"):
                await self._offer_duration(
                    client, follow_up, protocol, pending.get("priority")
                )
            elif pending.get("priority"):
                await self._launch(
                    client, chat_id, user_id, protocol, pending["priority"]
                )
            else:
                await self._offer_priority(client, follow_up, protocol)
            return

        if parts[0] == "research_prio":
            language = protocol.display_language()
            if parts[2] not in PRIORITIES:
                await self._answer_callback(
                    client, callback_id, text_for(language)["invalid_choice"]
                )
                return
            await self._answer_callback(client, callback_id, text_for(language)["starting"])
            await self._clear_markup(client, chat_id, int(message.get("message_id", 0)))
            await self._launch(client, chat_id, user_id, protocol, parts[2])
            return

        language = protocol.display_language()
        try:
            minutes = int(parts[2])
        except ValueError:
            minutes = 0
        valid_minutes = {value for _, value in RESEARCH_TIME_OPTIONS}
        if minutes not in valid_minutes or minutes > self.settings.telegram_max_wall_minutes:
            await self._answer_callback(
                client, callback_id, text_for(language)["expired_choice"], alert=True
            )
            return
        await self._answer_callback(client, callback_id, "✓")
        protocol.budget = protocol.budget.model_copy(update={"max_wall_minutes": minutes})
        await self._clear_markup(client, chat_id, int(message.get("message_id", 0)))
        # Urgency was given on the command line, or it is the last thing left to ask.
        if pending.get("priority"):
            await self._launch(client, chat_id, user_id, protocol, pending["priority"])
        else:
            await self._offer_priority(client, {"chat": chat, "from": user}, protocol)

    async def _launch(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        user_id: int,
        protocol: ResearchProtocol,
        priority: str = NORMAL,
    ) -> None:
        language = protocol.display_language()
        actor_id = await self._resolve_actor(user_id)
        if actor_id is None:
            await self._send_message(client, chat_id, self._link_hint(language))
            return
        try:
            await self._start_research(
                client,
                chat_id,
                user_id,
                protocol,
                self.gateway.for_actor(actor_id),
                normalize_priority(priority),
            )
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(
                client,
                chat_id,
                text_for(language)["failed"].format(error=str(exc)[:1000]),
            )

    async def _resolve_run(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        gateway: ResearchGatewayClient,
        token: str,
        strings: dict,
    ) -> str | None:
        """Turn what the user typed into a run id, or explain why it cannot be.

        The bot is the only surface where an identifier is typed by hand -- the panel is
        clicked and agents pass back ids they were given -- so the label is resolved here
        rather than in the API, where every one of the fifteen run routes would have to be
        proved to use the resolved id instead of its own path parameter.

        Returns None when it has already told the user what went wrong; callers stop.
        """
        if looks_like_run_id(token):
            return token
        try:
            # The listing is owner-scoped by the API, so a label can never reach into
            # somebody else's run: this search only sees what the caller already owns.
            runs = await gateway.runs(limit=200)
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(
                client, chat_id, strings["failed"].format(error=str(exc)[:1000])
            )
            return None
        wanted = token.casefold()
        matches = [run for run in runs if run_label(run).casefold() == wanted]
        if len(matches) == 1:
            return str(matches[0]["id"])
        if not matches:
            await self._send_message(
                client, chat_id, strings["resolve_unknown"].format(token=token[:120])
            )
            return None
        # Two runs on one topic share a label. /cancel cannot be undone, so the ambiguity
        # is handed back rather than resolved by picking the newest.
        lines = [strings["resolve_many"].format(count=len(matches))]
        lines += [
            strings["resolve_row"].format(
                id=html.escape(str(run["id"])),
                status=label_of(strings, "status", run.get("status")),
                date=run_moment(run),
            )
            for run in matches[:10]
        ]
        await self._send_message(client, chat_id, "\n".join(lines), parse_mode="HTML")
        return None

    async def _list_runs(
        self,
        client: httpx.AsyncClient,
        chat_id: int,
        gateway: ResearchGatewayClient,
        strings: dict,
    ) -> None:
        """The recent runs with their labels, for whoever cannot remember one."""
        runs = await gateway.runs(limit=10)
        if not runs:
            await self._send_message(client, chat_id, strings["runs_empty"])
            return
        finished = {"completed", "completed_incomplete"}
        lines = [strings["runs_header"], ""]
        for run in runs:
            label = run_label(run)
            # The badge is display only and must stay out of the command line below --
            # the label there has to be exactly what /status will be asked to resolve.
            badge = "⚡ " if normalize_priority(run.get("priority")) == URGENT else ""
            verb = "/get" if run.get("status") in finished else "/status"
            # The command goes inside <code>: Telegram turns a bare /command into a link
            # but drops everything after it, so tapping one would leave the label behind.
            # A code span copies the whole line instead.
            lines.append(
                strings["runs_row"].format(
                    label=badge + html.escape(label),
                    status=label_of(strings, "status", run.get("status")),
                    stage=label_of(strings, "stage", run.get("current_stage")),
                    date=run_moment(run),
                    command=html.escape(f"{verb} {label}"),
                )
            )
            lines.append("")
        await self._send_message(client, chat_id, "\n".join(lines), parse_mode="HTML")

    async def _handle_plan_callback(
        self,
        client: httpx.AsyncClient,
        callback_id: str,
        parts: list[str],
        chat_id: int,
        user_id: int,
        message: dict,
    ) -> None:
        """Approve or reject the plan from the two buttons under it.

        The watch entry is process memory, so a bot that restarted between sending the plan
        and the tap has no way to answer for the user. That is told plainly and the
        /respond wording is repeated -- the command path is the only thing that survives a
        restart, which is why it is still documented in /help.
        """
        run_id = parts[1] if len(parts) > 1 else ""
        action = parts[2] if len(parts) > 2 else ""
        watch = self.watched_runs.get(run_id)
        if (
            watch is None
            or int(watch["chat_id"]) != chat_id
            or int(watch.get("user_id", user_id)) != user_id
            or not watch.get("notified")
        ):
            language = reply_language(message={"from": {"id": user_id}})
            text = text_for(language)
            await self._answer_callback(client, callback_id, text["expired_choice"], alert=True)
            await self._send_message(
                client, chat_id, text["plan"]["expired"].format(run_id=run_id)
            )
            return
        language = watch.get("language", "tr")
        text = text_for(language)
        await self._answer_callback(client, callback_id, "✓")
        await self._clear_markup(client, chat_id, int(message.get("message_id", 0)))
        if action == "reject":
            # A rejection with no reason rebuilds the identical plan: _plan_feedback skips
            # empty notes, so the run would loop until plan_max_revisions cancels it. Ask
            # first, submit once there is something to act on.
            self.pending_answers[run_id] = {
                "kind": "plan_reject",
                "chat_id": chat_id,
                "gateway": watch["gateway"],
                "interaction_id": watch["notified"],
                "language": language,
            }
            await self._send_message(client, chat_id, text["plan"]["reject_prompt"])
            return
        await self._submit_plan_decision(client, run_id, {"approved": True})

    async def _submit_plan_decision(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        response: dict,
    ) -> None:
        watch = self.watched_runs.get(run_id)
        if watch is None:
            return
        text = text_for(watch.get("language", "tr"))
        try:
            updated = await watch["gateway"].respond(run_id, watch["notified"], response)
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(
                client, watch["chat_id"], text["failed"].format(error=str(exc)[:1000])
            )
            return
        note = text["plan"]["approved" if response.get("approved") else "rejected"]
        await self._send_message(
            client,
            watch["chat_id"],
            f"{note}\n"
            + text["respond_ok"].format(
                run_id=run_label(updated),
                status=label_of(text, "status", updated["status"]),
            ),
        )

    async def _handle_answer_callback(
        self,
        client: httpx.AsyncClient,
        callback_id: str,
        parts: list[str],
        chat_id: int,
        message: dict,
    ) -> None:
        run_id = parts[1] if len(parts) > 1 else ""
        session = self.pending_answers.get(run_id)
        if (
            session is None
            or session.get("kind") != "scoping"
            or int(session["chat_id"]) != chat_id
        ):
            await self._answer_callback(client, callback_id, text_for("tr")["expired_choice"])
            return
        text = text_for(session["language"])
        await self._clear_markup(client, chat_id, int(message.get("message_id", 0)))
        if parts[0] == "plan_extra":
            await self._answer_callback(client, callback_id, "✓")
            await self._submit_planning_answers(client, run_id)
            return
        item = session["questions"][session["index"]]
        try:
            choice = int(parts[3])
            option = item["options"][choice]
        except (IndexError, ValueError, KeyError):
            await self._answer_callback(client, callback_id, text["invalid_choice"])
            return
        # A fixed question ships the protocol value beside the wording it shows; the
        # model's questions ship none, and their answers stay guidance.
        values = item.get("values") or []
        value = str(values[choice]) if choice < len(values) else ""
        await self._answer_callback(client, callback_id, "✓")
        await self._record_answer(client, run_id, option, value=value)

    async def _record_answer(
        self,
        client: httpx.AsyncClient,
        run_id: str,
        answer: str,
        *,
        value: str = "",
    ) -> None:
        session = self.pending_answers.get(run_id)
        if session is None or session.get("kind") != "scoping":
            return
        if session.get("awaiting_extra"):
            session["answers"].append(
                {"question": text_for(session["language"])["scoping_extra_label"],
                 "answer": answer, "id": "", "value": ""}
            )
            await self._submit_planning_answers(client, run_id)
            return
        item = session["questions"][session["index"]]
        session["answers"].append(
            {
                "question": item["question"],
                "answer": answer,
                "id": str(item.get("id") or ""),
                "value": value,
            }
        )
        session["index"] += 1
        await self._ask_planning_question(client, run_id)

    async def _ask_planning_question(self, client: httpx.AsyncClient, run_id: str) -> None:
        session = self.pending_answers.get(run_id)
        if session is None:
            return
        text = text_for(session["language"])
        questions = session["questions"]
        index = session["index"]
        if index >= len(questions):
            session["awaiting_extra"] = True
            await self._send_message(
                client,
                session["chat_id"],
                text["scoping_extra"],
                reply_markup={
                    "inline_keyboard": [
                        [{"text": text["scoping_skip"],
                          "callback_data": f"plan_extra:{run_id}:skip"}]
                    ]
                },
            )
            return
        item = questions[index]
        options = item.get("options") or []
        body = text["scoping_question"].format(
            index=index + 1, total=len(questions), question=item["question"]
        )
        markup = None
        if options:
            markup = {
                "inline_keyboard": [
                    [{"text": option[:60], "callback_data": f"plan_answer:{run_id}:{index}:{n}"}]
                    for n, option in enumerate(options)
                ]
            }
        else:
            body = f"{body}\n{text['scoping_free']}"
        await self._send_message(client, session["chat_id"], body, reply_markup=markup)

    async def _submit_planning_answers(self, client: httpx.AsyncClient, run_id: str) -> None:
        session = self.pending_answers.pop(run_id, None)
        if session is None:
            return
        text = text_for(session["language"])
        answers = [item for item in session["answers"] if item["answer"].strip()]
        if not answers:
            # The checkpoint requires a non-empty list, and skipping every question is a
            # legitimate choice: say so once rather than rejecting the user's silence.
            answers = [
                {"question": session["questions"][0]["question"], "answer": "-",
                 "id": "", "value": ""}
            ]
        try:
            await session["gateway"].respond(
                run_id, session["interaction_id"], {"answers": answers}
            )
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(
                client,
                session["chat_id"],
                text["failed"].format(error=str(exc)[:1000]),
            )
            return
        await self._send_message(client, session["chat_id"], text["scoping_done"])

    async def _consume_interview_text(self, client: httpx.AsyncClient, message: dict) -> bool:
        """Route a plain message into whatever this chat is being asked, if anything.

        Both waiting states -- a scoping answer and a rejection reason -- live in one
        dictionary and are told apart by `kind`. Two dictionaries searched in sequence
        would make the answer depend on which one happened to be looked at first.
        """
        chat_id = int((message.get("chat") or {}).get("id", 0))
        body = str(message.get("text") or "").strip()
        if not body or body.startswith("/"):
            return False
        for run_id, session in list(self.pending_answers.items()):
            if int(session["chat_id"]) != chat_id:
                continue
            if session.get("kind") == "plan_reject":
                self.pending_answers.pop(run_id, None)
                await self._submit_plan_decision(
                    client, run_id, {"approved": False, "modifications": body[:5000]}
                )
            else:
                await self._record_answer(client, run_id, body)
            return True
        return False

    async def _handle(self, client: httpx.AsyncClient, message: dict) -> None:
        chat_id = int((message.get("chat") or {}).get("id", 0))
        text_body = str(message.get("text") or "").strip()
        if await self._consume_interview_text(client, message):
            return
        language = reply_language(message=message)
        strings = text_for(language)
        try:
            parts = shlex.split(text_body)
        except ValueError:
            await self._send_message(client, chat_id, strings["help"])
            return
        telegram_user_id = int((message.get("from") or {}).get("id", 0))
        command = parts[0].split("@", 1)[0].lower() if parts else ""

        # A deep link from the panel arrives as "/start <code>", so /start is only the
        # plain help screen when it carries no payload.
        if command == "/start" and len(parts) == 2:
            await self._link_account(client, chat_id, telegram_user_id, parts[1], language)
            return
        if not parts or command in {"/start", "/help", "/yardim"}:
            await self._send_message(client, chat_id, strings["help"])
            return
        if command == "/whoami":
            await self._send_message(
                client,
                chat_id,
                strings["whoami"].format(user_id=telegram_user_id, chat_id=chat_id),
            )
            return
        if command == "/baglan":
            if len(parts) != 2:
                await self._send_message(
                    client, chat_id, strings["link_usage"] + "\n\n" + strings["link_hint"]
                )
                return
            await self._link_account(client, chat_id, telegram_user_id, parts[1], language)
            return

        # Being linked to a platform account *is* the authorization. The old
        # TELEGRAM_ALLOWED_USER_IDS list stood in for an identity the system did not have;
        # now that it does, the list would only be a second gate that a self-linked user
        # could not pass. It survives for group chats, where the sender is not
        # necessarily the person the bot should act for.
        if not await self._chat_allowed(message):
            await self._send_message(client, chat_id, strings["chat_not_allowed"])
            return
        actor_id = await self._resolve_actor(telegram_user_id)
        if actor_id is None:
            await self._send_message(client, chat_id, strings["link_hint"])
            return
        gateway = self.gateway.for_actor(actor_id)
        try:
            if command == "/research":
                research_parts, flag_language = take_language_flag(parts[1:])
                research_parts, flag_priority = take_priority_flag(research_parts)
                explicit_minutes = has_explicit_duration(research_parts)
                hitl_enabled = "--hitl" in research_parts
                # The plan gate is on unless the person starting the run says otherwise.
                # It used to hang off --hitl, which meant every ordinary /research
                # explicitly sent plan_review=false and overrode the platform default.
                skip_plan = "--plansiz" in research_parts
                research_parts = [
                    item for item in research_parts if item not in {"--hitl", "--plansiz"}
                ]
                # The question about language should already be in the language it is
                # asking about. The request text is a better signal than the Telegram
                # client setting, which says what the app is set to, not what was typed.
                language = reply_language(question=" ".join(research_parts), message=message)
                strings = text_for(language)
                mode, question, budget = parse_research_request(
                    research_parts,
                    default_minutes=self.settings.telegram_default_max_wall_minutes,
                    maximum_minutes=self.settings.telegram_max_wall_minutes,
                    default_sources=self.settings.telegram_default_max_sources,
                    default_rounds=self.settings.telegram_default_max_rounds,
                    language=flag_language or language,
                )
                protocol = ResearchProtocol(
                    title=question[:120],
                    primary_question=question,
                    output_mode=mode.value,
                    budget=budget,
                    interaction_language=flag_language,
                    report_language=flag_language or "tr",
                    hitl=HitlConfig(
                        # Scoping questions are on for the bot: the chat is step by step
                        # anyway, and this is where narrowing the run actually belongs.
                        planning_questions=not skip_plan,
                        plan_review=not skip_plan,
                        source_review=hitl_enabled,
                        outline_review=hitl_enabled,
                    ),
                )
                # Each step is skipped only when the command already answered it.
                if flag_language is None:
                    await self._offer_language(
                        client,
                        message,
                        protocol,
                        explicit_minutes=explicit_minutes,
                        priority=flag_priority,
                        language=language,
                    )
                elif not explicit_minutes:
                    await self._offer_duration(client, message, protocol, flag_priority)
                elif flag_priority:
                    await self._launch(
                        client, chat_id, telegram_user_id, protocol, flag_priority
                    )
                else:
                    await self._offer_priority(client, message, protocol)
            elif command in {"/kosular", "/runs"} and len(parts) == 1:
                await self._list_runs(client, chat_id, gateway, strings)
            elif command in {"/oncelik", "/priority"}:
                if len(parts) != 3:
                    raise ValueError(strings["priority_usage"])
                priority = read_priority(parts[2])
                if priority is None:
                    raise ValueError(strings["priority_invalid"])
                run_id = await self._resolve_run(
                    client, chat_id, gateway, parts[1], strings
                )
                if run_id is None:
                    return
                run = await gateway.set_priority(run_id, priority)
                strings = text_for(reply_language(run=run, message=message))
                await self._send_message(
                    client,
                    chat_id,
                    strings["priority_set"].format(
                        run_id=run_label(run),
                        priority=strings["priorities"][normalize_priority(priority)],
                    ),
                )
            elif command == "/status" and len(parts) == 2:
                run_id = await self._resolve_run(
                    client, chat_id, gateway, parts[1], strings
                )
                if run_id is None:
                    return
                run = await gateway.status(run_id)
                strings = text_for(reply_language(run=run, message=message))
                interaction = run.get("interaction") or {}
                hitl_note = ""
                if interaction:
                    # The /respond argument has to stay the real id -- it is a command
                    # argument, not a name for a person to read.
                    hitl_note = strings["status_waiting"].format(
                        type=label_of(strings, "interaction", interaction.get("type")),
                        run_id=run["id"],
                    )
                await self._send_message(
                    client,
                    chat_id,
                    strings["status_line"].format(
                        run_id=run_label(run),
                        id=run["id"],
                        status=label_of(strings, "status", run["status"]),
                        stage=label_of(strings, "stage", run["current_stage"]),
                        sources=run["sources_count"],
                        claims=run["claims_count"],
                    )
                    + hitl_note,
                )
            elif command == "/respond" and len(parts) >= 3:
                run_id = await self._resolve_run(
                    client, chat_id, gateway, parts[1], strings
                )
                if run_id is None:
                    return
                run = await gateway.status(run_id)
                strings = text_for(reply_language(run=run, message=message))
                interaction = run.get("interaction") or {}
                interaction_id = interaction.get("interaction_id")
                interaction_type = interaction.get("type")
                if not interaction_id:
                    raise ValueError(strings["respond_none"])
                verb = parts[2].lower()
                tail = " ".join(parts[3:]).strip()
                if interaction_type in {"plan_review", "outline_review"}:
                    if verb not in {"approve", "reject"}:
                        raise ValueError(strings["respond_plan_usage"])
                    payload = {"approved": verb == "approve"}
                    if tail:
                        payload["modifications"] = tail
                elif interaction_type == "planning_questions":
                    if verb != "answer" or not tail:
                        raise ValueError(strings["respond_answer_usage"])
                    questions = (interaction.get("data") or {}).get("questions", [])
                    payload = {
                        "answers": [
                            {"question": item.get("question", ""), "answer": tail}
                            for item in questions
                        ]
                    }
                elif interaction_type == "source_review":
                    tokens = parts[2:]
                    lowered = [item.lower() for item in tokens]
                    if "include" not in lowered:
                        raise ValueError(strings["respond_source_usage"])
                    include_at = lowered.index("include")
                    exclude_at = lowered.index("exclude") if "exclude" in lowered else len(tokens)
                    include_text = " ".join(tokens[include_at + 1 : exclude_at])
                    exclude_text = (
                        " ".join(tokens[exclude_at + 1 :]) if exclude_at < len(tokens) else ""
                    )
                    payload = {
                        "included_domains": [
                            x.strip() for x in include_text.split(",") if x.strip()
                        ],
                        "excluded_domains": [
                            x.strip() for x in exclude_text.split(",") if x.strip()
                        ],
                    }
                else:
                    raise ValueError(strings["respond_unknown"])
                updated = await gateway.respond(run_id, interaction_id, payload)
                await self._send_message(
                    client,
                    chat_id,
                    strings["respond_ok"].format(
                        run_id=run_label(updated),
                        status=label_of(strings, "status", updated["status"]),
                    ),
                )
            elif command == "/get" and len(parts) in {2, 3}:
                run_id = await self._resolve_run(
                    client, chat_id, gateway, parts[1], strings
                )
                if run_id is None:
                    return
                mode = DeliveryMode(parts[2] if len(parts) == 3 else "both")
                path = await gateway.download(
                    run_id, mode, Path(self.settings.gateway_download_dir)
                )
                await self._send_document(client, chat_id, path)
            elif command in {"/pause", "/resume", "/cancel"} and len(parts) == 2:
                run_id = await self._resolve_run(
                    client, chat_id, gateway, parts[1], strings
                )
                if run_id is None:
                    return
                run = await gateway.action(run_id, command[1:])
                strings = text_for(reply_language(run=run, message=message))
                await self._send_message(
                    client,
                    chat_id,
                    strings["action_result"].format(
                        run_id=run_label(run),
                        status=label_of(strings, "status", run["status"]),
                    ),
                )
            else:
                await self._send_message(client, chat_id, strings["help"])
        except (httpx.HTTPError, ValueError) as exc:
            detail = str(exc)
            if detail == "language_invalid":
                detail = strings["language_invalid"]
            await self._send_message(
                client, chat_id, strings["failed"].format(error=detail[:1000])
            )

    async def _notify_failed_runs(self, client: httpx.AsyncClient) -> None:
        """Tell the owner when one of their runs has failed.

        Owner-driven rather than driven by `watched_runs`: that dict lives in memory and
        only holds runs started through the bot, so a run started from MCP, the API or the
        panel would fail in silence, and a bot restart would lose the rest. Every run has an
        owner, and `telegram_ids_for` turns that into chats.

        A run is announced once. The marker is an ordinary run event, so it survives a
        restart without a migration, and it is written even when there was nobody to tell --
        otherwise an owner with no linked Telegram would be retried on every poll cycle.
        """
        settings = get_settings()
        cutoff = datetime.now(UTC) - timedelta(
            hours=settings.telegram_failure_notice_window_h
        )
        async with SessionLocal() as session:
            repo = Repository(session, actor=Principal.system())
            for run in await repo.list_failed_runs_since(cutoff):
                if await repo.events_by_types(run.id, {FAILURE_NOTICE_EVENT}):
                    continue
                chat_ids = (
                    await telegram_ids_for(session, run.owner_id) if run.owner_id else []
                )
                language = reply_language(run={"protocol": run.protocol or {}})
                strings = text_for(language)
                reason = " ".join(str(run.error or "").split())
                text = strings["run_failed"].format(
                    label=html.escape(run_label({"protocol": run.protocol or {}, "id": run.id})),
                    run_id=run.id,
                    error=html.escape(reason[:600] or strings["run_failed_no_reason"]),
                )
                for chat_id in chat_ids:
                    await self._send_message(client, chat_id, text, parse_mode="HTML")
                if not chat_ids:
                    logger.warning(
                        "dusen kosu %s icin bildirilecek telegram hesabi yok (sahip=%s)",
                        run.id,
                        run.owner_id,
                    )
                await repo.event(run.id, FAILURE_NOTICE_EVENT, {"chat_count": len(chat_ids)})

    async def _notify_waiting_runs(self, client: httpx.AsyncClient) -> None:
        """Tell the chat when one of its runs has stopped for input.

        Without this the run parks at awaiting_input in silence and the person who
        started it has to guess that /status is worth running.
        """
        for run_id, watch in list(self.watched_runs.items()):
            try:
                run = await watch["gateway"].status(run_id)
            except (httpx.HTTPError, ValueError):
                continue
            status = run.get("status")
            if status in {"completed", "completed_incomplete", "failed", "cancelled"}:
                self.watched_runs.pop(run_id, None)
                self.pending_answers.pop(run_id, None)
                continue
            interaction = run.get("interaction") or {}
            interaction_id = interaction.get("interaction_id")
            if not interaction_id or interaction_id == watch["notified"]:
                continue
            kind = interaction.get("type")
            if kind not in {"plan_review", "planning_questions"}:
                continue
            watch["notified"] = interaction_id
            language = reply_language(run=run) or watch.get("language", "tr")
            watch["language"] = language
            data = interaction.get("data") or {}
            if kind == "plan_review":
                await self._send_message(
                    client,
                    watch["chat_id"],
                    plan_summary(run, data.get("plan") or {}),
                    reply_markup=plan_keyboard(run_id, language),
                    parse_mode="HTML",
                )
                continue
            questions = [item for item in data.get("questions", []) if item.get("question")]
            if not questions:
                continue
            self.pending_answers[run_id] = {
                "kind": "scoping",
                "chat_id": watch["chat_id"],
                "gateway": watch["gateway"],
                "interaction_id": interaction_id,
                "questions": questions,
                "answers": [],
                "index": 0,
                "awaiting_extra": False,
                "language": language,
            }
            await self._send_message(
                client,
                watch["chat_id"],
                text_for(language)["scoping_intro"].format(count=len(questions)),
            )
            await self._ask_planning_question(client, run_id)

    async def serve(self) -> None:
        offset = 0
        async with httpx.AsyncClient(timeout=70) as client:
            while True:
                response = await client.get(
                    f"{self.bot_url}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 60,
                        "allowed_updates": '["message","callback_query"]',
                    },
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    message = update.get("message")
                    if message:
                        await self._handle(client, message)
                    callback = update.get("callback_query")
                    if callback:
                        await self._handle_callback(client, callback)
                # Runs on the long-poll cycle: at most a minute late, and a failure here
                # must never take the command loop down with it.
                try:
                    await self._notify_waiting_runs(client)
                except Exception:
                    logger.exception("plan bildirimi basarisiz")
                # Its own guard: a failure here must not stop the plan notice, and neither
                # of them may take the command loop down.
                try:
                    await self._notify_failed_runs(client)
                except Exception:
                    logger.exception("dusen kosu bildirimi basarisiz")


def run() -> None:
    asyncio.run(TelegramResearchBot().serve())
