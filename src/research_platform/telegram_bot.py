from __future__ import annotations

import asyncio
import secrets
import shlex
import time
from pathlib import Path

import httpx

from .config import get_settings
from .gateway_client import ResearchGatewayClient
from .schemas import DeliveryMode, HitlConfig, ResearchBudget, ResearchProtocol


HELP = """Research Platform komutları:
/whoami
/research [raw|result|both] [dakika|--minutes N] [--hitl] [--sources N] <soru>
/status <run_id>
/respond <run_id> approve|reject|answer|include ...
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
"""

RESEARCH_TIME_OPTIONS = (
    ("⚡ Hızlı", 10),
    ("⚖ Standart", 30),
    ("🧠 Derin", 120),
    ("🔥 Maksimum", 180),
)
PENDING_REQUEST_TTL_SECONDS = 15 * 60


def duration_keyboard(request_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": f"{label} · {minutes} dk",
                    "callback_data": f"research_time:{request_id}:{minutes}",
                }
            ]
            for label, minutes in RESEARCH_TIME_OPTIONS
        ]
    }


def parse_research_request(
    parts: list[str],
    *,
    default_minutes: int,
    maximum_minutes: int,
    default_sources: int | None,
    default_rounds: int,
) -> tuple[DeliveryMode, str, ResearchBudget]:
    mode = DeliveryMode.BOTH
    tokens = list(parts)
    if tokens and tokens[0] in {item.value for item in DeliveryMode}:
        mode = DeliveryMode(tokens.pop(0))
    minutes = default_minutes
    sources = default_sources
    if tokens and tokens[0].lstrip("+-").isdigit():
        minutes = int(tokens.pop(0))
        if not 1 <= minutes <= maximum_minutes:
            raise ValueError(f"Süre 1-{maximum_minutes} dakika arasında olmalıdır.")
    while tokens and tokens[0].startswith("--"):
        option = tokens.pop(0)
        if option not in {"--minutes", "--sources"} or not tokens:
            raise ValueError(f"Geçersiz veya eksik seçenek: {option}")
        try:
            value = int(tokens.pop(0))
        except ValueError as exc:
            raise ValueError(f"{option} tam sayı olmalıdır.") from exc
        if option == "--minutes":
            if not 1 <= value <= maximum_minutes:
                raise ValueError(f"--minutes 1-{maximum_minutes} arasında olmalıdır.")
            minutes = value
        else:
            if value < 1:
                raise ValueError("--sources pozitif olmalıdır.")
            sources = value
    question = " ".join(tokens).strip()
    if not question:
        raise ValueError("Araştırma sorusu eksik.")
    return (
        mode,
        question,
        ResearchBudget(
            max_wall_minutes=minutes,
            max_sources=sources,
            max_rounds=default_rounds,
        ),
    )


def has_explicit_duration(parts: list[str]) -> bool:
    tokens = [item for item in parts if item != "--hitl"]
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
            self.settings.api_token,
        )
        self.allowed_users = set(self.settings.telegram_allowed_user_ids)
        self.allowed_chats = set(self.settings.telegram_allowed_chat_ids)
        self.allow_group_chats = self.settings.telegram_allow_group_chats
        self.allow_all_users = self.settings.telegram_allow_all_users
        self.pending_research: dict[str, dict] = {}

    def _authorized(self, message: dict) -> bool:
        user_id = int((message.get("from") or {}).get("id", 0))
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id", 0))
        if self.allow_all_users:
            return True
        if self.allow_group_chats and chat.get("type") in {"group", "supergroup"}:
            return True
        return bool(self.allowed_users or self.allowed_chats) and (
            user_id in self.allowed_users or chat_id in self.allowed_chats
        )

    async def _send_message(self, client: httpx.AsyncClient, chat_id: int, text: str) -> None:
        await client.post(
            f"{self.bot_url}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4096]},
        )

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
        protocol: ResearchProtocol,
    ) -> None:
        run = await self.gateway.start(protocol)
        budget = protocol.budget
        await self._send_message(
            client,
            chat_id,
            f"Run başlatıldı: {run['id']}\nTeslim modu: {protocol.output_mode}\n"
            f"Toplama bütçesi: {budget.max_wall_minutes} dk; süre dolunca eldeki "
            f"kaynakların analizi ve rapor üretimi tamamlanır.\n"
            f"{budget.max_sources or 'süreye bağlı sınırsız'} kaynak, "
            f"{budget.max_rounds} tur\n"
            f"Durum için: /status {run['id']}",
        )

    async def _offer_duration(
        self,
        client: httpx.AsyncClient,
        message: dict,
        protocol: ResearchProtocol,
    ) -> None:
        now = time.monotonic()
        self.pending_research = {
            key: value
            for key, value in self.pending_research.items()
            if now - float(value["created_at"]) < PENDING_REQUEST_TTL_SECONDS
        }
        request_id = secrets.token_urlsafe(6)
        chat_id = int((message.get("chat") or {}).get("id", 0))
        user_id = int((message.get("from") or {}).get("id", 0))
        self.pending_research[request_id] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "created_at": now,
            "protocol": protocol.model_dump(mode="json"),
        }
        await client.post(
            f"{self.bot_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": (
                    "Araştırma süresini seçin:\n"
                    "Kaynak sayısı süre boyunca sınırsızdır; coverage yeterli olursa "
                    "araştırma daha erken tamamlanabilir."
                ),
                "reply_markup": duration_keyboard(request_id),
            },
        )

    async def _handle_callback(self, client: httpx.AsyncClient, callback: dict) -> None:
        callback_id = str(callback.get("id") or "")
        message = callback.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id", 0))
        user = callback.get("from") or {}
        auth_message = {"from": user, "chat": chat}
        if not self._authorized(auth_message):
            await client.post(
                f"{self.bot_url}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Araştırma yetkiniz yok.",
                    "show_alert": True,
                },
            )
            return
        data = str(callback.get("data") or "")
        parts = data.split(":")
        if len(parts) != 3 or parts[0] != "research_time":
            await client.post(
                f"{self.bot_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": "Geçersiz seçim."},
            )
            return
        request_id = parts[1]
        pending = self.pending_research.pop(request_id, None)
        try:
            minutes = int(parts[2])
        except ValueError:
            minutes = 0
        valid_minutes = {value for _, value in RESEARCH_TIME_OPTIONS}
        expired = pending and (
            time.monotonic() - float(pending["created_at"]) >= PENDING_REQUEST_TTL_SECONDS
        )
        if (
            pending is None
            or expired
            or int(pending["chat_id"]) != chat_id
            or int(pending["user_id"]) != int(user.get("id", 0))
            or minutes not in valid_minutes
            or minutes > self.settings.telegram_max_wall_minutes
        ):
            await client.post(
                f"{self.bot_url}/answerCallbackQuery",
                json={
                    "callback_query_id": callback_id,
                    "text": "Bu seçim geçersiz veya süresi dolmuş.",
                    "show_alert": True,
                },
            )
            return
        await client.post(
            f"{self.bot_url}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": "Araştırma başlatılıyor…"},
        )
        protocol = ResearchProtocol.model_validate(pending["protocol"])
        protocol.budget = protocol.budget.model_copy(
            update={"max_wall_minutes": minutes},
        )
        await client.post(
            f"{self.bot_url}/editMessageReplyMarkup",
            json={
                "chat_id": chat_id,
                "message_id": int(message.get("message_id", 0)),
                "reply_markup": {"inline_keyboard": []},
            },
        )
        try:
            await self._start_research(client, chat_id, protocol)
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(
                client,
                chat_id,
                f"İşlem başarısız: {str(exc)[:1000]}",
            )

    async def _handle(self, client: httpx.AsyncClient, message: dict) -> None:
        chat_id = int((message.get("chat") or {}).get("id", 0))
        text = str(message.get("text") or "").strip()
        try:
            parts = shlex.split(text)
        except ValueError:
            await self._send_message(client, chat_id, HELP)
            return
        if not parts or parts[0] in {"/start", "/help"}:
            await self._send_message(client, chat_id, HELP)
            return
        command = parts[0].split("@", 1)[0].lower()
        if command == "/whoami":
            user_id = int((message.get("from") or {}).get("id", 0))
            await self._send_message(
                client,
                chat_id,
                f"Telegram user_id: {user_id}\nTelegram chat_id: {chat_id}",
            )
            return
        if not self._authorized(message):
            await self._send_message(
                client,
                chat_id,
                "Bu bot için araştırma yetkiniz yok. Kimliklerinizi görmek için /whoami yazın.",
            )
            return
        try:
            if command == "/research":
                explicit_minutes = has_explicit_duration(parts[1:])
                hitl_enabled = "--hitl" in parts[1:]
                research_parts = [item for item in parts[1:] if item != "--hitl"]
                mode, question, budget = parse_research_request(
                    research_parts,
                    default_minutes=self.settings.telegram_default_max_wall_minutes,
                    maximum_minutes=self.settings.telegram_max_wall_minutes,
                    default_sources=self.settings.telegram_default_max_sources,
                    default_rounds=self.settings.telegram_default_max_rounds,
                )
                protocol = ResearchProtocol(
                    title=question[:120],
                    primary_question=question,
                    output_mode=mode.value,
                    budget=budget,
                    hitl=HitlConfig(
                        planning_questions=hitl_enabled,
                        plan_review=hitl_enabled,
                        source_review=hitl_enabled,
                        outline_review=hitl_enabled,
                    ),
                )
                if explicit_minutes:
                    await self._start_research(client, chat_id, protocol)
                else:
                    await self._offer_duration(client, message, protocol)
            elif command == "/status" and len(parts) == 2:
                run = await self.gateway.status(parts[1])
                interaction = run.get("interaction") or {}
                hitl_note = ""
                if interaction:
                    hitl_note = (
                        f"\nKullanıcı girdisi bekleniyor: {interaction.get('type')}"
                        f"\nInteraction: {interaction.get('interaction_id')}"
                        f"\nYanıt: /respond {run['id']} ..."
                    )
                await self._send_message(
                    client,
                    chat_id,
                    f"{run['id']}\nDurum: {run['status']}\nAşama: {run['current_stage']}\n"
                    f"Kaynak: {run['sources_count']} | İddia: {run['claims_count']}"
                    f"{hitl_note}",
                )
            elif command == "/respond" and len(parts) >= 3:
                run = await self.gateway.status(parts[1])
                interaction = run.get("interaction") or {}
                interaction_id = interaction.get("interaction_id")
                interaction_type = interaction.get("type")
                if not interaction_id:
                    raise ValueError("Bekleyen kullanıcı girdisi yok.")
                verb = parts[2].lower()
                tail = " ".join(parts[3:]).strip()
                if interaction_type in {"plan_review", "outline_review"}:
                    if verb not in {"approve", "reject"}:
                        raise ValueError("approve veya reject <değişiklik> kullanın.")
                    payload = {"approved": verb == "approve"}
                    if tail:
                        payload["modifications"] = tail
                elif interaction_type == "planning_questions":
                    if verb != "answer" or not tail:
                        raise ValueError("answer <yanıt> kullanın.")
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
                        raise ValueError("include <alan,adları> [exclude <alan,adları>] kullanın.")
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
                    raise ValueError("Bilinmeyen checkpoint türü.")
                updated = await self.gateway.respond(parts[1], interaction_id, payload)
                await self._send_message(
                    client,
                    chat_id,
                    f"{updated['id']}: yanıt alındı, durum {updated['status']}",
                )
            elif command == "/get" and len(parts) in {2, 3}:
                mode = DeliveryMode(parts[2] if len(parts) == 3 else "both")
                path = await self.gateway.download(
                    parts[1], mode, Path(self.settings.gateway_download_dir)
                )
                await self._send_document(client, chat_id, path)
            elif command in {"/pause", "/resume", "/cancel"} and len(parts) == 2:
                run = await self.gateway.action(parts[1], command[1:])
                await self._send_message(client, chat_id, f"{run['id']}: {run['status']}")
            else:
                await self._send_message(client, chat_id, HELP)
        except (httpx.HTTPError, ValueError) as exc:
            await self._send_message(client, chat_id, f"İşlem başarısız: {str(exc)[:1000]}")

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


def run() -> None:
    asyncio.run(TelegramResearchBot().serve())
