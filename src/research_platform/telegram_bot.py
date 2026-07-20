from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

import httpx

from .config import get_settings
from .gateway_client import ResearchGatewayClient
from .schemas import DeliveryMode, ResearchProtocol


HELP = """Research Platform komutları:
/whoami
/research [raw|result|both] <soru>
/status <run_id>
/get <run_id> [raw|result|both]
/pause <run_id>
/resume <run_id>
/cancel <run_id>
"""


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
                mode = DeliveryMode.BOTH
                question_parts = parts[1:]
                if question_parts and question_parts[0] in {mode.value for mode in DeliveryMode}:
                    mode = DeliveryMode(question_parts.pop(0))
                question = " ".join(question_parts).strip()
                if not question:
                    raise ValueError("Araştırma sorusu eksik.")
                run = await self.gateway.start(ResearchProtocol(
                    title=question[:120],
                    primary_question=question,
                    output_mode=mode.value,
                ))
                await self._send_message(
                    client,
                    chat_id,
                    f"Run başlatıldı: {run['id']}\nTeslim modu: {mode.value}\n"
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
