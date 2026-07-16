"""Initial research platform schema.

Revision ID: 0001_initial
Revises:
"""

import sqlalchemy as sa
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("current_stage", sa.String(length=80), nullable=False),
        sa.Column("protocol", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("sources_count", sa.Integer(), nullable=False),
        sa.Column("claims_count", sa.Integer(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_research_runs_status", "research_runs", ["status"])
    op.create_table(
        "run_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "stage", name="uq_checkpoint_run_stage"),
    )
    op.create_index("ix_run_checkpoints_run_id", "run_checkpoints", ["run_id"])
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_table(
        "sources",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False),
        sa.Column("family", sa.String(length=80), nullable=False),
        sa.Column("connector_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("persistent_id", sa.String(length=512), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "dedupe_key", name="uq_source_run_dedupe"),
    )
    op.create_index("ix_sources_run_id", "sources", ["run_id"])
    op.create_index("ix_sources_family", "sources", ["family"])
    op.create_index("ix_sources_persistent_id", "sources", ["persistent_id"])
    op.create_table(
        "source_versions",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("source_id", sa.String(length=26), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("acquisition_method", sa.String(length=100), nullable=False),
        sa.Column("access_status", sa.String(length=30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])
    op.create_index("ix_source_versions_content_hash", "source_versions", ["content_hash"])
    op.create_table(
        "claims",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("importance", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("audit", sa.JSON(), nullable=False),
    )
    op.create_index("ix_claims_run_id", "claims", ["run_id"])
    op.create_table(
        "evidence_links",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("claim_id", sa.String(length=26), nullable=False),
        sa.Column("source_version_id", sa.String(length=26), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("location", sa.JSON(), nullable=False),
        sa.Column("entailment_score", sa.Float(), nullable=False),
        sa.Column("independence_score", sa.Float(), nullable=False),
    )
    op.create_index("ix_evidence_links_claim_id", "evidence_links", ["claim_id"])
    op.create_index(
        "ix_evidence_links_source_version_id", "evidence_links", ["source_version_id"]
    )
    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "name", name="uq_artifact_run_name"),
    )
    op.create_index("ix_export_artifacts_run_id", "export_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_table("export_artifacts")
    op.drop_table("evidence_links")
    op.drop_table("claims")
    op.drop_table("source_versions")
    op.drop_table("sources")
    op.drop_table("run_events")
    op.drop_table("run_checkpoints")
    op.drop_table("research_runs")
