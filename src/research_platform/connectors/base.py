from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..config import Settings
from ..schemas import ConnectorCandidate, ConnectorHealth, SourceFamily


class SourceConnector(ABC):
    id: str
    family: SourceFamily
    requires_credentials: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("search", "metadata")

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    def missing_credentials(self) -> list[str]:
        return [name for name in self.requires_credentials if not getattr(self.settings, name, None)]

    async def health(self) -> ConnectorHealth:
        missing = self.missing_credentials()
        return ConnectorHealth(
            id=self.id,
            family=self.family,
            enabled=not missing,
            healthy=not missing,
            requires_credentials=bool(self.requires_credentials),
            missing_credentials=missing,
            capabilities=list(self.capabilities),
            detail="credentials missing" if missing else "configured",
        )

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]: ...

    async def fetch_metadata(self, candidate: ConnectorCandidate) -> dict[str, Any]:
        return candidate.metadata

    async def fetch_content(self, candidate: ConnectorCandidate) -> str | None:
        return None

    async def fetch_citations(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        return []

    async def fetch_versions(self, candidate: ConnectorCandidate) -> list[dict[str, Any]]:
        return []

    def candidate(
        self,
        *,
        title: str,
        url: str,
        snippet: str = "",
        persistent_id: str | None = None,
        authors: list[str] | None = None,
        publisher: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorCandidate | None:
        try:
            return ConnectorCandidate(
                connector_id=self.id,
                family=self.family,
                title=title.strip() or url,
                url=url,
                snippet=snippet.strip(),
                persistent_id=persistent_id,
                authors=authors or [],
                publisher=publisher,
                metadata=metadata or {},
            )
        except Exception:
            return None


class CredentialOnlyConnector(SourceConnector):
    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        if self.missing_credentials():
            return []
        return []

