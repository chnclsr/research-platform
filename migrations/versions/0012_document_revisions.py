"""versioned, user-approved revisions of generated report artifacts

Revision ID: 0012_document_revisions
Revises: 0011_formula_observations
Create Date: 2026-09-14

Generated Office files used to be mutable pointers in ``export_artifacts``.  These
tables keep the report model, every rendered file and every citation snapshot under an
immutable revision id.  ``export_artifacts`` remains the compatibility pointer and is
updated only when a validated draft is accepted.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_document_revisions"
down_revision = "0011_formula_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_revisions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=26), nullable=True),
        sa.Column("base_revision_id", sa.String(length=26), nullable=True),
        sa.Column("target_artifact_name", sa.String(length=255), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False, server_default=""),
        sa.Column("edit_plan", sa.JSON(), nullable=True),
        sa.Column("report_model", sa.JSON(), nullable=False),
        sa.Column("format_overrides", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=26), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="api"),
        sa.Column("conversation_id", sa.String(length=120), nullable=True),
        sa.Column("channel_state", sa.JSON(), nullable=False),
        sa.Column("model_id", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "revision_number", name="uq_document_revision_number"),
        sa.UniqueConstraint(
            "run_id",
            "requested_by",
            "idempotency_key",
            name="uq_document_revision_idempotency",
        ),
    )
    op.create_index("ix_document_revisions_run_id", "document_revisions", ["run_id"])
    op.create_index(
        "ix_document_revisions_parent_revision_id",
        "document_revisions",
        ["parent_revision_id"],
    )
    op.create_index(
        "ix_document_revisions_base_revision_id", "document_revisions", ["base_revision_id"]
    )
    op.create_index("ix_document_revisions_status", "document_revisions", ["status"])
    op.create_index(
        "ix_document_revisions_requested_by", "document_revisions", ["requested_by"]
    )
    op.create_index("ix_document_revisions_channel", "document_revisions", ["channel"])
    op.create_index(
        "ix_document_revisions_conversation_id", "document_revisions", ["conversation_id"]
    )
    op.create_index(
        "ix_document_revisions_status_channel",
        "document_revisions",
        ["status", "channel"],
    )

    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("revision_id", sa.String(length=26), nullable=False),
        sa.Column("logical_name", sa.String(length=255), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(length=26), nullable=True),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id", "logical_name", name="uq_artifact_version_revision_name"
        ),
    )
    op.create_index("ix_artifact_versions_run_id", "artifact_versions", ["run_id"])
    op.create_index("ix_artifact_versions_revision_id", "artifact_versions", ["revision_id"])
    op.create_index(
        "ix_artifact_versions_parent_version_id", "artifact_versions", ["parent_version_id"]
    )

    op.create_table(
        "revision_citations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("revision_id", sa.String(length=26), nullable=False),
        sa.Column("source_id", sa.String(length=26), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "revision_id", "source_id", name="uq_revision_citation_revision_source"
        ),
    )
    op.create_index("ix_revision_citations_run_id", "revision_citations", ["run_id"])
    op.create_index("ix_revision_citations_revision_id", "revision_citations", ["revision_id"])
    op.create_index("ix_revision_citations_source_id", "revision_citations", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_revision_citations_source_id", table_name="revision_citations")
    op.drop_index("ix_revision_citations_revision_id", table_name="revision_citations")
    op.drop_index("ix_revision_citations_run_id", table_name="revision_citations")
    op.drop_table("revision_citations")
    op.drop_index("ix_artifact_versions_parent_version_id", table_name="artifact_versions")
    op.drop_index("ix_artifact_versions_revision_id", table_name="artifact_versions")
    op.drop_index("ix_artifact_versions_run_id", table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_index("ix_document_revisions_status_channel", table_name="document_revisions")
    op.drop_index("ix_document_revisions_conversation_id", table_name="document_revisions")
    op.drop_index("ix_document_revisions_channel", table_name="document_revisions")
    op.drop_index("ix_document_revisions_requested_by", table_name="document_revisions")
    op.drop_index("ix_document_revisions_status", table_name="document_revisions")
    op.drop_index("ix_document_revisions_base_revision_id", table_name="document_revisions")
    op.drop_index("ix_document_revisions_parent_revision_id", table_name="document_revisions")
    op.drop_index("ix_document_revisions_run_id", table_name="document_revisions")
    op.drop_table("document_revisions")
