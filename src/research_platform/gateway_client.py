from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .schemas import DeliveryMode, ResearchProtocol


class ResearchGatewayClient:
    """HTTP client for the research API, optionally acting for a specific user.

    ``actor_user_id`` turns the shared service credential into a per-user call: the
    API accepts the header only alongside a valid service token, so a gateway can
    authenticate its own users (a Telegram account, an MCP session) and still have
    the platform apply that user's ownership rules.
    """

    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        timeout_s: float = 60.0,
        actor_user_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_token}"}
        if actor_user_id:
            self.headers["X-Actor-User"] = actor_user_id
        self.timeout_s = timeout_s

    def for_actor(self, actor_user_id: str) -> "ResearchGatewayClient":
        """A copy of this client bound to one user, leaving the original untouched."""
        clone = ResearchGatewayClient(
            self.base_url,
            "",
            timeout_s=self.timeout_s,
        )
        clone.headers = {**self.headers, "X-Actor-User": actor_user_id}
        return clone

    async def start(
        self,
        protocol: ResearchProtocol,
        *,
        priority: str = "normal",
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs",
                json={
                    "protocol": protocol.model_dump(mode="json"),
                    # Beside the protocol, not inside it: how urgent a run is says nothing
                    # about what it researches.
                    "priority": priority,
                },
            )
            response.raise_for_status()
            return response.json()

    async def set_priority(self, run_id: str, priority: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs/{run_id}/priority",
                json={"priority": priority},
            )
            response.raise_for_status()
            return response.json()

    async def status(self, run_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(f"{self.base_url}/v1/research-runs/{run_id}")
            response.raise_for_status()
            return response.json()

    async def runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs",
                params={"limit": min(max(1, limit), 200)},
            )
            response.raise_for_status()
            return response.json()

    async def action(self, run_id: str, action: str) -> dict[str, Any]:
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError(f"Unsupported action: {action}")
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(f"{self.base_url}/v1/research-runs/{run_id}/{action}")
            response.raise_for_status()
            return response.json()

    async def respond(
        self,
        run_id: str,
        interaction_id: str,
        response_payload: dict[str, Any],
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs/{run_id}/respond",
                json={"interaction_id": interaction_id, "response": response_payload},
            )
            response.raise_for_status()
            return response.json()

    async def artifacts(self, run_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(f"{self.base_url}/v1/research-runs/{run_id}/artifacts")
            response.raise_for_status()
            return response.json()

    async def read_artifact(
        self,
        run_id: str,
        name: str,
        *,
        offset: int = 0,
        max_chars: int = 100_000,
    ) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/artifacts/{name}"
            )
            response.raise_for_status()
            text = response.content.decode("utf-8", errors="replace")
            selected = text[offset : offset + max_chars]
            if offset + max_chars < len(text):
                selected += f"\n\n[TRUNCATED next_offset={offset + max_chars}]"
            return selected

    async def download(
        self,
        run_id: str,
        mode: DeliveryMode,
        destination: Path,
    ) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"{run_id}_{mode.value}.zip"
        if target.exists() and target.stat().st_size > 0:
            return target.resolve()
        async with httpx.AsyncClient(timeout=None, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/delivery/{mode.value}"
            )
            response.raise_for_status()
            target.write_bytes(response.content)
        return target.resolve()
