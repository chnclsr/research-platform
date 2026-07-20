from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .schemas import DeliveryMode, ResearchProtocol


class ResearchGatewayClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        *,
        timeout_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_token}"}
        self.timeout_s = timeout_s

    async def start(self, protocol: ResearchProtocol) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs",
                json={"protocol": protocol.model_dump(mode="json")},
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
