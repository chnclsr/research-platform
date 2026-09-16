from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from .config import get_settings
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
        timeout_s: float | None = None,
        artifact_max_chars: int | None = None,
        actor_user_id: str | None = None,
        invocation_source: str = "api",
    ) -> None:
        settings = get_settings()
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_token}"}
        if actor_user_id:
            self.headers["X-Actor-User"] = actor_user_id
        self.timeout_s = timeout_s if timeout_s is not None else settings.gateway_client_timeout_s
        self.artifact_max_chars = (
            artifact_max_chars
            if artifact_max_chars is not None
            else settings.gateway_artifact_max_chars
        )
        self.invocation_source = invocation_source

    def for_actor(self, actor_user_id: str) -> ResearchGatewayClient:
        """A copy of this client bound to one user, leaving the original untouched."""
        clone = ResearchGatewayClient(
            self.base_url,
            "",
            timeout_s=self.timeout_s,
            artifact_max_chars=self.artifact_max_chars,
            invocation_source=self.invocation_source,
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
                    "invocation_source": self.invocation_source,
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

    async def access_issues(self, run_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/access-issues"
            )
            response.raise_for_status()
            return response.json()

    async def revisions(self, run_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/revisions"
            )
            response.raise_for_status()
            return response.json()

    async def revision(self, revision_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/document-revisions/{revision_id}"
            )
            response.raise_for_status()
            return response.json()

    async def active_revision(
        self, *, channel: str, conversation_id: str
    ) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/document-revisions/active",
                params={"channel": channel, "conversation_id": conversation_id},
            )
            response.raise_for_status()
            return response.json()

    async def artifact_versions(self, run_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/artifact-versions"
            )
            response.raise_for_status()
            return response.json()

    async def create_revision(
        self,
        run_id: str,
        artifact_name: str,
        *,
        feedback: str = "",
        base_revision_id: str | None = None,
        parent_revision_id: str | None = None,
        channel: str = "api",
        conversation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "feedback": feedback,
            "base_revision_id": base_revision_id,
            "parent_revision_id": parent_revision_id,
            "channel": channel,
            "conversation_id": conversation_id,
        }
        headers = dict(self.headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs/{run_id}/artifacts/{artifact_name}/revisions",
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def add_revision_feedback(
        self, run_id: str, revision_id: str, feedback: str
    ) -> dict[str, Any]:
        return await self._revision_action(
            run_id, revision_id, "feedback", body={"feedback": feedback}
        )

    async def approve_revision_plan(self, run_id: str, revision_id: str) -> dict[str, Any]:
        return await self._revision_action(run_id, revision_id, "approve-plan")

    async def accept_revision(self, run_id: str, revision_id: str) -> dict[str, Any]:
        return await self._revision_action(run_id, revision_id, "accept")

    async def cancel_revision(self, run_id: str, revision_id: str) -> dict[str, Any]:
        return await self._revision_action(run_id, revision_id, "cancel")

    async def _revision_action(
        self,
        run_id: str,
        revision_id: str,
        action: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.post(
                f"{self.base_url}/v1/research-runs/{run_id}/revisions/{revision_id}/{action}",
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def read_artifact(
        self,
        run_id: str,
        name: str,
        *,
        offset: int = 0,
        max_chars: int | None = None,
    ) -> str:
        limit = max_chars if max_chars is not None else self.artifact_max_chars
        async with httpx.AsyncClient(timeout=self.timeout_s, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/artifacts/{name}"
            )
            response.raise_for_status()
            text = response.content.decode("utf-8", errors="replace")
            selected = text[offset : offset + limit]
            if offset + limit < len(text):
                selected += f"\n\n[TRUNCATED next_offset={offset + limit}]"
            return selected

    async def download(
        self,
        run_id: str,
        mode: DeliveryMode,
        destination: Path,
    ) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        revisions = await self.revisions(run_id)
        accepted = next((item for item in revisions if item.get("status") == "accepted"), None)
        revision_id = str((accepted or {}).get("id") or "unversioned")
        target = destination / f"{run_id}_{mode.value}_{revision_id}.zip"
        if target.exists() and target.stat().st_size > 0:
            return target.resolve()
        async with httpx.AsyncClient(timeout=None, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/research-runs/{run_id}/delivery/{mode.value}"
            )
            response.raise_for_status()
            target.write_bytes(response.content)
        return target.resolve()

    async def download_artifact_version(
        self, version_id: str, destination: Path
    ) -> tuple[Path, str, dict[str, str]]:
        destination.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=None, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/v1/artifact-versions/{version_id}"
            )
            response.raise_for_status()
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename="([^"]+)"', disposition)
        filename = Path(match.group(1)).name if match else f"{version_id}.bin"
        target = destination / f"{version_id}_{filename}"
        if not target.exists() or target.stat().st_size == 0:
            target.write_bytes(response.content)
        media_type = response.headers.get("Content-Type", "application/octet-stream")
        metadata = {
            "run_id": response.headers.get("X-Run-Id", ""),
            "revision_id": response.headers.get("X-Revision-Id", ""),
            "revision_number": response.headers.get("X-Revision-Number", ""),
            "version_id": response.headers.get("X-Artifact-Version-Id", version_id),
            "logical_name": filename,
        }
        return target.resolve(), media_type, metadata
