from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

import httpx

from .config import get_settings
from .gateway_client import ResearchGatewayClient
from .schemas import DeliveryMode, ResearchBudget, ResearchProtocol


HELP = """Research Platform komutları:
/whoami
/research [raw|result|both] [--minutes N] [--sources N] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
"""


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
    return mode, question, ResearchBudget(
        max_wall_minutes=minutes,
        max_sources=sources,
        max_rounds=default_rounds,
    )


class TelegramResearchBot:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        self.bot_url = (
            f"{self.settings.telegram_api_url.rstrip('/')}/bot"
            f"{self.settings.telegram_bot_token}"
        )
        self.gateway = ResearchGatewayClient(
            self.settings.research_api_url,
            self.settings.api_token,
        )
        self.allowed_users = set(self.settings.telegram_allowed_user_ids)
        self.allowed_chats = set(self.settings.telegram_allowed_chat_ids)
        self.allow_group_chats = self.settings.telegram_allow_group_chats
        self.allow_all_users = self.settings.telegram_allow_all_users

    def _authorized(self, message: dict) -> bool:
        user_id = int((message.get("from") or {}).get("id", 0))
        chat = message.get("chat") or {}
        chat_id = int(chat.get("id", 0))
        if self.allow_all_users:
            return True
        if self.allow_group_chats and chat.get("type") in {"group", "supergroup"}:
            return True
        return (
            bool(self.allowed_users or self.allowed_chats)
            and (user_id in self.allowed_users or chat_id in self.allowed_chats)
        )

    async def _send_message(self, client: httpx.AsyncClient, chat_id: int, text: str) -> None:
        await client.post(
            f"{self.bot_url}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4096]},
        )

    async def _send_document(
        self, client: httpx.AsyncClient, chat_id: int, path: Path,
    ) -> None:
        with path.open("rb") as handle:
            await client.post(
                f"{self.bot_url}/sendDocument",
                data={"chat_id": str(chat_id)},
                files={"document": (path.name, handle, "application/zip")},
                timeout=None,
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
                mode, question, budget = parse_research_request(
                    parts[1:],
                    default_minutes=self.settings.telegram_default_max_wall_minutes,
                    maximum_minutes=self.settings.telegram_max_wall_minutes,
                    default_sources=self.settings.telegram_default_max_sources,
                    default_rounds=self.settings.telegram_default_max_rounds,
                )
                run = await self.gateway.start(ResearchProtocol(
                    title=question[:120],
                    primary_question=question,
                    output_mode=mode.value,
                    budget=budget,
                ))
                await self._send_message(
                    client,
                    chat_id,
                    f"Run başlatıldı: {run['id']}\nTeslim modu: {mode.value}\n"
                    f"Bütçe: {budget.max_wall_minutes} dk, "
                    f"{budget.max_sources or 'süreye bağlı sınırsız'} kaynak, "
                    f"{budget.max_rounds} tur\n"
                    f"Durum için: /status {run['id']}",
                )
            elif command == "/status" and len(parts) == 2:
                run = await self.gateway.status(parts[1])
                await self._send_message(
                    client,
                    chat_id,
                    f"{run['id']}\nDurum: {run['status']}\nAşama: {run['current_stage']}\n"
                    f"Kaynak: {run['sources_count']} | İddia: {run['claims_count']}",
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
                        "allowed_updates": '["message"]',
                    },
                )
                response.raise_for_status()
                for update in response.json().get("result", []):
                    offset = max(offset, int(update["update_id"]) + 1)
                    message = update.get("message")
                    if message:
                        await self._handle(client, message)


def run() -> None:
    asyncio.run(TelegramResearchBot().serve())
