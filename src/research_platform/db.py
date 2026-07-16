from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from .config import get_settings


def json_type():
    return JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class ResearchRunRow(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    current_stage: Mapped[str] = mapped_column(String(80), default="INIT")
    protocol: Mapped[dict] = mapped_column(json_type())
    state: Mapped[dict] = mapped_column(json_type(), default=dict)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    claims_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[dict] = mapped_column(json_type(), default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CheckpointRow(Base):
    __tablename__ = "run_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "stage", name="uq_checkpoint_run_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    stage: Mapped[str] = mapped_column(String(80))
    state: Mapped[dict] = mapped_column(json_type())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventRow(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRow(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("run_id", "dedupe_key", name="uq_source_run_dedupe"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(512))
    family: Mapped[str] = mapped_column(String(80), index=True)
    connector_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    persistent_id: Mapped[str | None] = mapped_column(String(512), index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceVersionRow(Base):
    __tablename__ = "source_versions"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(26), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    acquisition_method: Mapped[str] = mapped_column(String(100))
    access_status: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text, default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict] = mapped_column(json_type(), default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRelationRow(Base):
    __tablename__ = "source_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "target_persistent_id", "relation_type", "provider",
            name="uq_source_relation_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    source_id: Mapped[str] = mapped_column(String(26), index=True)
    target_source_id: Mapped[str | None] = mapped_column(String(26), index=True)
    target_persistent_id: Mapped[str | None] = mapped_column(String(512), index=True)
    relation_type: Mapped[str] = mapped_column(String(40), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConnectorSyncCursorRow(Base):
    __tablename__ = "connector_sync_cursors"
    __table_args__ = (
        UniqueConstraint("connector_id", "scope_key", name="uq_connector_sync_scope"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    connector_id: Mapped[str] = mapped_column(String(100), index=True)
    scope_key: Mapped[str] = mapped_column(String(512))
    cursor_value: Mapped[str] = mapped_column(String(512))
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PassageRow(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("source_version_id", "chunk_index", name="uq_passage_version_chunk"),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_version_id: Mapped[str] = mapped_column(String(26), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str] = mapped_column(Text, default="Document")
    page_number: Mapped[int | None] = mapped_column(Integer)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list] = mapped_column(json_type(), default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)


class FrontierRow(Base):
    __tablename__ = "crawl_frontier"
    __table_args__ = (UniqueConstraint("run_id", "canonical_url", name="uq_frontier_run_url"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    discovered_from: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimRow(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    text: Mapped[str] = mapped_column(Text)
    importance: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="unresolved")
    confidence: Mapped[float] = mapped_column(default=0.0)
    audit: Mapped[dict] = mapped_column(json_type(), default=dict)


class EvidenceRow(Base):
    __tablename__ = "evidence_links"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(26), index=True)
    source_version_id: Mapped[str] = mapped_column(String(26), index=True)
    direction: Mapped[str] = mapped_column(String(20))
    quote: Mapped[str] = mapped_column(Text)
    location: Mapped[dict] = mapped_column(json_type(), default=dict)
    entailment_score: Mapped[float] = mapped_column(default=0.0)
    independence_score: Mapped[float] = mapped_column(default=1.0)


class ArtifactRow(Base):
    __tablename__ = "export_artifacts"
    __table_args__ = (UniqueConstraint("run_id", "name", name="uq_artifact_run_name"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
