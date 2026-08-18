from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .acquisition import AcquisitionService
from .auth import Principal
from .config import Settings
from .connectors import build_registry
from .embeddings import EmbeddingClient
from .passages import chunk_document
from .repository import Repository
from .schemas import (
    ResearchProtocol, RunStatus, SourceFamily, ZoteroSyncRequest, ZoteroSyncResult,
)


class ZoteroSyncService:
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
        client: httpx.AsyncClient,
        *,
        actor: Principal,
    ):
        self.settings = settings
        # A sync creates a run, so it needs a real user to own it. This service is only
        # ever reached through the API, which always has a request principal -- there
        # is no scheduled Zotero job that would arrive without one.
        self.repo = Repository(session, actor=actor)
        self.registry = build_registry(settings, client)
        self.acquisition = AcquisitionService(settings, client)
        self.embeddings = EmbeddingClient(settings, client)

    async def sync(self, request: ZoteroSyncRequest) -> ZoteroSyncResult:
        connector_id = f"zotero_{request.mode}"
        connector = self.registry.get(connector_id)
        if connector is None:
            raise ValueError(f"Connector not found: {connector_id}")
        health = await connector.health()
        if not health.enabled or not health.healthy:
            raise RuntimeError(health.detail or f"{connector_id} unavailable")
        protocol = ResearchProtocol(
            title=f"Zotero {request.mode} corpus sync",
            primary_question="Import the selected Zotero library items into the local corpus.",
            connectors={
                "profile": "custom",
                "included_families": [SourceFamily.ACADEMIC],
                "included_connectors": [connector_id],
                "zotero_collections": request.collections,
                "zotero_tags": request.tags,
            },
        )
        run = await self.repo.create_run(protocol)
        await self.repo.update_run(
            run.id, status=RunStatus.RUNNING.value, current_stage="ZOTERO_SYNC"
        )
        scope_key = request.mode
        if request.mode == "web":
            scope_key = self.settings.zotero_user_id or self.settings.zotero_group_id or "web"
        cursor = await self.repo.get_sync_cursor(connector_id, scope_key)
        since = int(cursor.cursor_value) if cursor and cursor.cursor_value.isdigit() else None
        candidates = await connector.search_since(request.query, request.limit, since)
        candidates = [
            candidate for candidate in candidates
            if self._selected(candidate.metadata, request.collections, request.tags)
        ]
        imported = 0
        skipped = 0
        library_version = 0
        for candidate in candidates:
            library_version = max(
                library_version, int(candidate.metadata.get("zotero_library_version", 0))
            )
            document = await self.acquisition.acquire(candidate)
            if not document.success:
                skipped += 1
                continue
            _, version = await self.repo.save_document(run.id, document)
            passages = chunk_document(
                document.content, version.id,
                target_tokens=self.settings.passage_target_tokens,
                overlap_tokens=self.settings.passage_overlap_tokens,
            )
            try:
                vectors = await self.embeddings.embed([
                    f"{passage.section_path}\n{passage.text}" for passage in passages
                ])
                for passage, vector in zip(passages, vectors, strict=True):
                    passage.embedding = vector
            except Exception:
                pass
            for passage in passages:
                passage.language = document.language
                passage.document_type = document.document_type
            await self.repo.save_passages(passages)
            imported += 1
        if library_version:
            await self.repo.set_sync_cursor(
                connector_id, scope_key, str(library_version),
                {"collections": request.collections, "tags": request.tags},
            )
        await self.repo.update_run(
            run.id, status=RunStatus.COMPLETED.value, current_stage="COMPLETE",
            sources_count=imported,
        )
        await self.repo.event(run.id, "zotero_sync_complete", {
            "discovered": len(candidates), "imported": imported, "skipped": skipped,
            "library_version": library_version or None,
        })
        return ZoteroSyncResult(
            run_id=run.id, connector_id=connector_id, discovered=len(candidates),
            imported=imported, skipped=skipped, library_version=library_version or None,
        )

    @staticmethod
    def _selected(
        metadata: dict[str, Any], collections: list[str], tags: list[str],
    ) -> bool:
        if collections and not set(collections).intersection(metadata.get("collections", [])):
            return False
        if tags and not set(tags).intersection(metadata.get("tags", [])):
            return False
        return True
