from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx

from ..config import Settings
from ..schemas import ConnectorCandidate, ConnectorHealth, ResearchScope, SourceFamily
from ..temporal import publication_datetime


class ConnectorQueryError(RuntimeError):
    """A provider answered, and the answer says the query was wrong.

    Distinct from a transport failure in two ways that matter. It must not be retried --
    several providers penalise a repeated malformed request harder than a valid one -- and
    it must reach `connector_errors` rather than being flattened into an empty result list,
    because a rejected query and a genuine no-match are indistinguishable to the caller
    once both have become `[]`.
    """

    def __init__(self, connector_id: str, detail: str, *, query: str = "") -> None:
        self.connector_id = connector_id
        self.detail = detail
        self.query = query
        super().__init__(f"{connector_id}: {detail}")


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

    async def search_scoped(
        self,
        query: str,
        limit: int = 20,
        scope: ResearchScope | None = None,
    ) -> list[ConnectorCandidate]:
        """Search with optional provider-side scope pushdown when implemented."""
        return await self.search(query, limit)

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
        published_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorCandidate | None:
        try:
            normalized_metadata = dict(metadata or {})
            inferred_date, date_basis = publication_datetime(normalized_metadata)
            normalized_date = published_at or inferred_date
            if normalized_date is not None:
                normalized_metadata["published_at"] = normalized_date.isoformat()
                normalized_metadata["publication_date_basis"] = (
                    "connector" if published_at is not None else date_basis
                )
            return ConnectorCandidate(
                connector_id=self.id,
                family=self.family,
                title=title.strip() or url,
                url=url,
                snippet=snippet.strip(),
                persistent_id=persistent_id,
                authors=authors or [],
                publisher=publisher,
                published_at=normalized_date,
                metadata=normalized_metadata,
            )
        except Exception:
            return None


class CredentialOnlyConnector(SourceConnector):
    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        if self.missing_credentials():
            return []
        return []
