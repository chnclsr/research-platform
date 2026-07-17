from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import (
    ArtifactRow, CheckpointRow, ClaimRow, ConnectorSyncCursorRow, EventRow, EvidenceRow,
    FrontierRow, PassageRow, ResearchRunRow, SourceRelationRow, SourceRow, SourceVersionRow,
)
from .normalization import canonicalize_url
from .schemas import (
    AcquiredDocument, ConnectorCandidate, CoverageMetrics, ExtractedClaim, Passage, ResearchProtocol,
    RunStatus, RunView, SourceFamily, new_id,
)
from .relevance import evidence_entailment
from .scholarly import candidate_dedupe_key, scholarly_identity, title_fingerprint


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, protocol: ResearchProtocol) -> ResearchRunRow:
        now = datetime.now(timezone.utc)
        row = ResearchRunRow(
            id=new_id(), status=RunStatus.QUEUED.value, current_stage="INIT",
            protocol=protocol.model_dump(mode="json"), state={}, coverage=CoverageMetrics().model_dump(),
            created_at=now, updated_at=now,
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_run(self, run_id: str, *, lock: bool = False) -> ResearchRunRow | None:
        stmt = (
            select(ResearchRunRow)
            .where(ResearchRunRow.id == run_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_runs_by_statuses(self, statuses: set[str]) -> list[ResearchRunRow]:
        if not statuses:
            return []
        rows = await self.session.scalars(
            select(ResearchRunRow)
            .where(ResearchRunRow.status.in_(statuses))
            .order_by(ResearchRunRow.created_at)
        )
        return list(rows)

    async def update_run(self, run_id: str, **values: Any) -> ResearchRunRow:
        row = await self.get_run(run_id, lock=True)
        if row is None:
            raise KeyError(run_id)
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        return row

    def run_view(self, row: ResearchRunRow) -> RunView:
        return RunView(
            id=row.id, status=RunStatus(row.status), current_stage=row.current_stage,
            protocol=ResearchProtocol.model_validate(row.protocol), round_number=row.round_number,
            sources_count=row.sources_count, claims_count=row.claims_count,
            coverage=CoverageMetrics.model_validate(row.coverage or {}),
            created_at=row.created_at, updated_at=row.updated_at, error=row.error,
        )

    async def checkpoint(self, run_id: str, stage: str, state: dict[str, Any]) -> None:
        existing = await self.session.scalar(
            select(CheckpointRow).where(CheckpointRow.run_id == run_id, CheckpointRow.stage == stage)
        )
        if existing:
            existing.state = state
            existing.created_at = datetime.now(timezone.utc)
        else:
            self.session.add(CheckpointRow(run_id=run_id, stage=stage, state=state))
        await self.update_run(run_id, current_stage=stage, state=state)

    async def latest_checkpoint(self, run_id: str) -> CheckpointRow | None:
        return await self.session.scalar(
            select(CheckpointRow).where(CheckpointRow.run_id == run_id)
            .order_by(CheckpointRow.created_at.desc()).limit(1)
        )

    async def event(self, run_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.session.add(EventRow(run_id=run_id, event_type=event_type, payload=payload or {}))
        await self.session.commit()

    async def events_after(self, run_id: str, after_id: int = 0) -> list[EventRow]:
        rows = await self.session.scalars(
            select(EventRow).where(EventRow.run_id == run_id, EventRow.id > after_id)
            .order_by(EventRow.id).limit(200)
        )
        return list(rows)

    async def save_document(self, run_id: str, document: AcquiredDocument) -> tuple[SourceRow, SourceVersionRow]:
        c = document.candidate
        persisted_metadata = dict(c.metadata)
        persisted_metadata.pop("inline_fulltext", None)
        if c.published_at is not None:
            persisted_metadata["published_at"] = c.published_at.isoformat()
            persisted_metadata.setdefault("publication_year", c.published_at.year)
        canonical = document.canonical_url or canonicalize_url(str(c.url))
        dedupe_key = candidate_dedupe_key(c)[:512]
        source = await self.session.scalar(
            select(SourceRow).where(SourceRow.run_id == run_id, SourceRow.dedupe_key == dedupe_key)
        )
        if source is None:
            candidates = list(await self.session.scalars(
                select(SourceRow).where(SourceRow.run_id == run_id).limit(500)
            ))
            normalized_title = " ".join(c.title.lower().split())
            identity = scholarly_identity(c.metadata, c.persistent_id)
            publication_year = c.metadata.get("publication_year") or c.metadata.get("year")
            fingerprint = title_fingerprint(c.title, c.authors, publication_year)
            source = next((
                row for row in candidates
                if (
                    SequenceMatcher(
                        None, normalized_title, " ".join(row.title.lower().split())
                    ).ratio() >= 0.96
                    and (
                        canonicalize_url(row.url) == canonical
                        or row.metadata_json.get("title_fingerprint") == fingerprint
                    )
                )
            ), None)
        if source is None:
            identity = scholarly_identity(c.metadata, c.persistent_id)
            publication_year = c.metadata.get("publication_year") or c.metadata.get("year")
            source = SourceRow(
                id=new_id(), run_id=run_id, dedupe_key=dedupe_key, family=c.family.value,
                connector_id=c.connector_id, title=c.title, url=canonical,
                persistent_id=identity.doi or c.persistent_id,
                metadata_json={
                    **persisted_metadata,
                    "scholarly_identity": identity.model_dump(exclude_none=True),
                    "title_fingerprint": title_fingerprint(
                        c.title, c.authors, publication_year
                    ),
                },
            )
            self.session.add(source)
            await self.session.flush()
        else:
            updated_metadata = dict(source.metadata_json or {})
            snapshots = dict(updated_metadata.get("provider_snapshots") or {})
            snapshots.update(persisted_metadata.get("provider_snapshots", {}))
            updated_metadata["provider_snapshots"] = snapshots
            alternate_locations = list(updated_metadata.get("alternate_locations") or [])
            if str(c.url) not in alternate_locations:
                alternate_locations.append(str(c.url))
            updated_metadata["alternate_locations"] = alternate_locations
            source.metadata_json = updated_metadata
        version = await self.session.scalar(
            select(SourceVersionRow).where(
                SourceVersionRow.source_id == source.id,
                SourceVersionRow.content_hash == document.content_hash,
            )
        )
        if version is None:
            version = SourceVersionRow(
                id=new_id(), source_id=source.id, content_hash=document.content_hash,
                acquisition_method=document.acquisition_method, access_status=document.access_status,
                content=document.content, raw_content=document.raw_content,
                retrieved_at=document.retrieved_at,
                provenance={
                    "url": str(c.url), "canonical_url": canonical,
                    "final_url": document.final_url, "redirect_chain": document.redirect_chain,
                    "content_type": document.content_type, "document_type": document.document_type,
                    "language": document.language, "connector": c.connector_id,
                    "raw_snapshot_key": c.metadata.get("raw_snapshot_key"),
                    "strategies_tried": document.strategies_tried, "error": document.error,
                },
            )
            self.session.add(version)
        await self.save_source_relations(run_id, source.id, c.metadata.get("citation_relations", []))
        await self.session.commit()
        return source, version

    async def save_source_relations(
        self, run_id: str, source_id: str, relations: list[dict[str, Any]],
    ) -> None:
        for relation in relations:
            target = str(relation.get("target_persistent_id") or "").strip()
            if not target:
                continue
            relation_type = str(relation.get("relation_type") or "").strip()
            provider = str(relation.get("provider") or "unknown")
            existing = await self.session.scalar(select(SourceRelationRow).where(
                SourceRelationRow.source_id == source_id,
                SourceRelationRow.target_persistent_id == target,
                SourceRelationRow.relation_type == relation_type,
                SourceRelationRow.provider == provider,
            ))
            if existing is None:
                self.session.add(SourceRelationRow(
                    id=new_id(), run_id=run_id, source_id=source_id,
                    target_persistent_id=target, relation_type=relation_type,
                    provider=provider, metadata_json=relation.get("metadata") or {},
                ))

    async def list_source_relations(self, run_id: str) -> list[SourceRelationRow]:
        return list(await self.session.scalars(
            select(SourceRelationRow).where(SourceRelationRow.run_id == run_id)
        ))

    async def get_sync_cursor(self, connector_id: str, scope_key: str) -> ConnectorSyncCursorRow | None:
        return await self.session.scalar(select(ConnectorSyncCursorRow).where(
            ConnectorSyncCursorRow.connector_id == connector_id,
            ConnectorSyncCursorRow.scope_key == scope_key,
        ))

    async def set_sync_cursor(
        self, connector_id: str, scope_key: str, cursor_value: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorSyncCursorRow:
        row = await self.get_sync_cursor(connector_id, scope_key)
        if row is None:
            row = ConnectorSyncCursorRow(
                id=new_id(), connector_id=connector_id, scope_key=scope_key,
                cursor_value=cursor_value, metadata_json=metadata or {},
            )
            self.session.add(row)
        else:
            row.cursor_value = cursor_value
            row.metadata_json = metadata or row.metadata_json
        await self.session.commit()
        return row

    async def list_sources(self, run_id: str) -> list[SourceRow]:
        return list(await self.session.scalars(select(SourceRow).where(SourceRow.run_id == run_id)))

    async def filter_novel_candidates(
        self, run_id: str, candidates: list[ConnectorCandidate],
    ) -> tuple[list[ConnectorCandidate], list[dict[str, str]]]:
        existing = await self.list_sources(run_id)
        by_dedupe_key = {source.dedupe_key: source for source in existing}
        by_url = {canonicalize_url(source.url): source for source in existing}
        by_persistent_id = {
            source.persistent_id.lower(): source
            for source in existing if source.persistent_id
        }
        novel: list[ConnectorCandidate] = []
        rejected: list[dict[str, str]] = []
        enriched = False
        for candidate in candidates:
            key = candidate_dedupe_key(candidate)[:512]
            canonical = canonicalize_url(str(candidate.url))
            persistent = (candidate.persistent_id or "").lower()
            source = (
                by_dedupe_key.get(key)
                or by_url.get(canonical)
                or (by_persistent_id.get(persistent) if persistent else None)
            )
            if source is not None:
                metadata = dict(source.metadata_json or {})
                branches = list(metadata.get("query_branches") or [])
                for branch in candidate.metadata.get("query_branches", []):
                    if branch not in branches:
                        branches.append(branch)
                        enriched = True
                metadata["query_branches"] = branches
                if (
                    candidate.metadata.get("authority") == "official"
                    and metadata.get("authority") != "official"
                ):
                    metadata["authority"] = "official"
                    enriched = True
                if enriched:
                    source.metadata_json = metadata
                rejected.append({"url": str(candidate.url), "reason": "existing_source"})
                continue
            novel.append(candidate)
        if enriched:
            await self.session.commit()
        return novel, rejected

    async def list_source_versions(self, run_id: str) -> list[tuple[SourceRow, SourceVersionRow]]:
        rows = await self.session.execute(
            select(SourceRow, SourceVersionRow).join(
                SourceVersionRow, SourceVersionRow.source_id == SourceRow.id
            ).where(SourceRow.run_id == run_id)
        )
        return list(rows.tuples())

    async def save_passages(self, passages: list[Passage]) -> None:
        for passage in passages:
            row = await self.session.scalar(
                select(PassageRow).where(
                    PassageRow.source_version_id == passage.source_version_id,
                    PassageRow.chunk_index == passage.chunk_index,
                )
            )
            values = {
                "section_path": passage.section_path, "page_number": passage.page_number,
                "start_char": passage.start_char, "end_char": passage.end_char,
                "text": passage.text, "token_count": passage.token_count,
                "content_hash": passage.content_hash, "embedding": passage.embedding,
                "metadata_json": {
                    "retrieval_score": passage.retrieval_score,
                    "matched_questions": passage.matched_questions,
                    "language": passage.language, "document_type": passage.document_type,
                },
            }
            if row is None:
                row = PassageRow(
                    id=passage.id, source_version_id=passage.source_version_id,
                    chunk_index=passage.chunk_index, **values,
                )
                self.session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
        await self.session.commit()

    async def list_passages(
        self, run_id: str, source_version_ids: list[str] | None = None,
    ) -> list[Passage]:
        stmt = (
            select(PassageRow)
            .join(SourceVersionRow, SourceVersionRow.id == PassageRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(SourceRow.run_id == run_id)
            .order_by(PassageRow.source_version_id, PassageRow.chunk_index)
        )
        if source_version_ids is not None:
            if not source_version_ids:
                return []
            stmt = stmt.where(PassageRow.source_version_id.in_(source_version_ids))
        rows = list(await self.session.scalars(stmt))
        return [Passage(
            id=row.id, source_version_id=row.source_version_id, chunk_index=row.chunk_index,
            section_path=row.section_path, page_number=row.page_number,
            start_char=row.start_char, end_char=row.end_char, text=row.text,
            token_count=row.token_count, content_hash=row.content_hash,
            embedding=row.embedding or [],
            language=(row.metadata_json or {}).get("language", "und"),
            document_type=(row.metadata_json or {}).get("document_type", "text"),
            retrieval_score=(row.metadata_json or {}).get("retrieval_score", 0.0),
            matched_questions=(row.metadata_json or {}).get("matched_questions", []),
        ) for row in rows]

    async def list_corpus_passages(self, exclude_run_id: str, limit: int = 3000) -> list[Passage]:
        rows = list(await self.session.scalars(
            select(PassageRow)
            .join(SourceVersionRow, SourceVersionRow.id == PassageRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(SourceRow.run_id != exclude_run_id)
            .order_by(SourceVersionRow.retrieved_at.desc()).limit(limit)
        ))
        return [Passage(
            id=row.id, source_version_id=row.source_version_id, chunk_index=row.chunk_index,
            section_path=row.section_path, page_number=row.page_number,
            start_char=row.start_char, end_char=row.end_char, text=row.text,
            token_count=row.token_count, content_hash=row.content_hash,
            embedding=row.embedding or [],
            language=(row.metadata_json or {}).get("language", "und"),
            document_type=(row.metadata_json or {}).get("document_type", "text"),
        ) for row in rows]

    async def corpus_documents(self, version_ids: list[str]) -> list[AcquiredDocument]:
        if not version_ids:
            return []
        rows = (await self.session.execute(
            select(SourceRow, SourceVersionRow)
            .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
            .where(SourceVersionRow.id.in_(version_ids))
        )).tuples()
        return [AcquiredDocument(
            candidate={
                "connector_id": "local_corpus", "family": SourceFamily(source.family),
                "title": source.title, "url": source.url, "persistent_id": source.persistent_id,
                "metadata": {**(source.metadata_json or {}), "local_corpus": True,
                             "source_version_id": version.id},
            },
            success=True, access_status=version.access_status, content=version.content,
            raw_content=version.raw_content or "", content_hash=version.content_hash,
            content_type=(version.provenance or {}).get("content_type", "text/plain"),
            document_type=(version.provenance or {}).get("document_type", "text"),
            language=(version.provenance or {}).get("language", "und"),
            canonical_url=source.url, final_url=(version.provenance or {}).get("final_url") or source.url,
            acquisition_method="local_corpus", strategies_tried=["local_corpus"],
        ) for source, version in rows]

    async def source_metadata_for_versions(self, version_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not version_ids:
            return {}
        rows = (await self.session.execute(
            select(SourceRow, SourceVersionRow)
            .join(SourceVersionRow, SourceVersionRow.source_id == SourceRow.id)
            .where(SourceVersionRow.id.in_(version_ids))
        )).tuples()
        return {version.id: {
            "source_id": source.id, "title": source.title, "url": source.url,
            "family": source.family, "connector_id": source.connector_id,
            "content_hash": version.content_hash, "retrieved_at": version.retrieved_at.isoformat(),
        } for source, version in rows}

    async def add_frontier_links(
        self, run_id: str, source_url: str, links: list[str], *, max_links: int,
    ) -> int:
        source_host = canonicalize_url(source_url).split("/", 3)[2]
        added = 0
        for link in list(dict.fromkeys(links))[:max_links]:
            canonical = canonicalize_url(link)
            existing = await self.session.scalar(select(FrontierRow).where(
                FrontierRow.run_id == run_id, FrontierRow.canonical_url == canonical,
            ))
            if existing:
                continue
            same_domain = canonical.split("/", 3)[2] == source_host
            self.session.add(FrontierRow(
                id=new_id(), run_id=run_id, canonical_url=canonical,
                discovered_from=source_url, depth=1, priority=1.0 if same_domain else 0.35,
                metadata_json={"same_domain": same_domain},
            ))
            added += 1
        await self.session.commit()
        return added

    async def pop_frontier_candidates(self, run_id: str, limit: int) -> list[dict[str, Any]]:
        rows = list(await self.session.scalars(
            select(FrontierRow).where(
                FrontierRow.run_id == run_id, FrontierRow.status == "pending",
            ).order_by(FrontierRow.priority.desc(), FrontierRow.created_at).limit(limit)
        ))
        for row in rows:
            row.status = "scheduled"
        await self.session.commit()
        return [{"url": row.canonical_url, "depth": row.depth,
                 "discovered_from": row.discovered_from, "priority": row.priority} for row in rows]

    async def save_claims(
        self,
        run_id: str,
        claims: list[tuple[ExtractedClaim, str]],
    ) -> None:
        existing_ids = set(await self.session.scalars(select(ClaimRow.id).where(ClaimRow.run_id == run_id)))
        existing_pairs = set((await self.session.execute(
            select(EvidenceRow.claim_id, EvidenceRow.source_version_id)
            .join(ClaimRow, ClaimRow.id == EvidenceRow.claim_id)
            .where(ClaimRow.run_id == run_id)
        )).tuples())
        for claim, version_id in claims:
            if claim.id not in existing_ids:
                self.session.add(ClaimRow(
                    id=claim.id, run_id=run_id, text=claim.text, importance=claim.importance,
                    confidence=claim.confidence, status="unresolved", audit={},
                ))
                existing_ids.add(claim.id)
            pair = (claim.id, version_id)
            if pair not in existing_pairs:
                self.session.add(EvidenceRow(
                    id=new_id(), claim_id=claim.id, source_version_id=version_id,
                    direction=claim.direction, quote=claim.quote,
                    location={
                        "start_char": claim.original_start_char
                        if claim.original_start_char is not None else claim.start_char,
                        "end_char": claim.original_end_char
                        if claim.original_end_char is not None else claim.end_char,
                        "passage_id": claim.passage_id, "section_path": claim.section_path,
                        "page_number": claim.page_number, "retrieval_score": claim.retrieval_score,
                    },
                    entailment_score=evidence_entailment(
                        claim.text, claim.quote, claim.confidence,
                    ),
                ))
                existing_pairs.add(pair)
        await self.session.commit()

    async def list_claims(self, run_id: str) -> list[ClaimRow]:
        return list(await self.session.scalars(select(ClaimRow).where(ClaimRow.run_id == run_id)))

    async def list_evidence(self, run_id: str) -> list[tuple[ClaimRow, EvidenceRow, SourceRow]]:
        result = await self.session.execute(
            select(ClaimRow, EvidenceRow, SourceRow)
            .join(EvidenceRow, EvidenceRow.claim_id == ClaimRow.id)
            .join(SourceVersionRow, SourceVersionRow.id == EvidenceRow.source_version_id)
            .join(SourceRow, SourceRow.id == SourceVersionRow.source_id)
            .where(ClaimRow.run_id == run_id)
        )
        return list(result.tuples())

    async def save_artifact(
        self, run_id: str, name: str, media_type: str, object_key: str, size_bytes: int
    ) -> ArtifactRow:
        row = await self.session.scalar(
            select(ArtifactRow).where(ArtifactRow.run_id == run_id, ArtifactRow.name == name)
        )
        if row is None:
            row = ArtifactRow(
                id=new_id(), run_id=run_id, name=name, media_type=media_type,
                object_key=object_key, size_bytes=size_bytes,
            )
            self.session.add(row)
        else:
            row.object_key, row.size_bytes, row.media_type = object_key, size_bytes, media_type
        await self.session.commit()
        return row

    async def list_artifacts(self, run_id: str) -> list[ArtifactRow]:
        return list(await self.session.scalars(select(ArtifactRow).where(ArtifactRow.run_id == run_id)))
