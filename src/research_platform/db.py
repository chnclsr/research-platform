from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from .capacity import startup_ceiling
from .config import get_settings


def json_type():
    return JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class ResearchRunRow(Base):
    __tablename__ = "research_runs"
    # Both scheduler questions -- "is an urgent run queued?" and "which normal run is
    # running?" -- filter on status and priority together.
    __table_args__ = (Index("ix_research_runs_status_priority", "status", "priority"),)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    # Who may see this run. Every creation path must supply one; reads are filtered by
    # it in the repository layer, not at the route, because the control panel reaches
    # this table both through the API and directly.
    owner_id: Mapped[str | None] = mapped_column(String(26), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    # Scheduling, not research: which band this run waits in. Deliberately a column and
    # not a protocol field -- the protocol describes what to research and is what the user
    # approves at the plan gate, while "is an urgent run waiting?" is a query the
    # scheduler runs on every tick.
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="normal", default="normal"
    )
    # Set only when the scheduler paused this run to let an urgent one through. What
    # separates it from a pause the user asked for: without the distinction, auto-resume
    # would restart runs somebody deliberately stopped.
    preempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_stage: Mapped[str] = mapped_column(String(80), default="INIT")
    protocol: Mapped[dict] = mapped_column(json_type())
    state: Mapped[dict] = mapped_column(json_type(), default=dict)
    round_number: Mapped[int] = mapped_column(Integer, default=0)
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    claims_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[dict] = mapped_column(json_type(), default=dict)
    interaction: Mapped[dict | None] = mapped_column(json_type(), nullable=True)
    hitl_history: Mapped[list] = mapped_column(json_type(), default=list)
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


class FigureObservationRow(Base):
    __tablename__ = "figure_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "image_hash",
            "vision_model",
            name="uq_figure_observation_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(26), index=True)
    source_id: Mapped[str] = mapped_column(String(26), index=True)
    source_version_id: Mapped[str] = mapped_column(String(26), index=True)
    image_hash: Mapped[str] = mapped_column(String(64), index=True)
    image_key: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    caption: Mapped[str] = mapped_column(Text, default="")
    vision_model: Mapped[str] = mapped_column(String(160))
    analysis: Mapped[dict] = mapped_column(json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceRelationRow(Base):
    __tablename__ = "source_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "target_persistent_id",
            "relation_type",
            "provider",
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


class UserRow(Base):
    """A person who can sign in to the panel and own research runs.

    Accounts are deactivated (``is_active=False``), never deleted -- a deleted row would
    leave its runs owned by an id nobody holds. Following the rest of this schema, the
    identity tables carry no ForeignKey constraints; ownership is enforced in the
    repository layer, and a dangling ``owner_id`` fails closed (invisible to everyone
    but an admin) rather than opening access.
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumping this invalidates every session cookie the user holds, which is the
    # revocation path for a lost device without keeping a server-side session table.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A pending Telegram link code, hashed. One per user by construction: issuing a new
    # code overwrites the old one and consuming it clears both columns, so single use
    # does not depend on the consuming code remembering to enforce it.
    telegram_link_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_link_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApiKeyRow(Base):
    """A per-user credential for the surfaces that cannot hold a session cookie."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(26), index=True)
    name: Mapped[str] = mapped_column(String(80))
    # Stored in the clear and indexed so verification is one indexed lookup rather
    # than a scan that hashes every row.
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramIdentityRow(Base):
    """Maps a Telegram account to a platform user so bot-started runs get an owner."""

    __tablename__ = "telegram_identities"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(26), index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


settings = get_settings()
# Sized from the parallel-run ceiling: each run holds its pipeline session and opens
# short-lived control and checkpoint sessions beside it, so the default 5+10 pool is the
# next thing to run out once more than one run executes at a time.
_POOL_KWARGS: dict = {} if settings.database_url.startswith("sqlite") else {
    "pool_size": max(settings.db_pool_min_size, startup_ceiling(settings) * settings.db_pool_per_run),
    "max_overflow": max(
        settings.db_overflow_min_size,
        startup_ceiling(settings) * settings.db_overflow_per_run,
    ),
}
engine = create_async_engine(settings.database_url, pool_pre_ping=True, **_POOL_KWARGS)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
