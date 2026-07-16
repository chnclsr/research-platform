"""academic source identities, relations, and connector sync cursors

Revision ID: 0004_academic_sources
Revises: 0003_collection_pipeline
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_academic_sources"
down_revision = "0003_collection_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_relations",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("source_id", sa.String(length=26), nullable=False),
        sa.Column("target_source_id", sa.String(length=26), nullable=True),
        sa.Column("target_persistent_id", sa.String(length=512), nullable=True),
        sa.Column("relation_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_id", "target_persistent_id", "relation_type", "provider",
            name="uq_source_relation_identity",
        ),
    )
    op.create_index("ix_source_relations_run_id", "source_relations", ["run_id"])
    op.create_index("ix_source_relations_source_id", "source_relations", ["source_id"])
    op.create_index(
        "ix_source_relations_target_persistent_id",
        "source_relations",
        ["target_persistent_id"],
    )
    op.create_table(
        "connector_sync_cursors",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("connector_id", sa.String(length=100), nullable=False),
        sa.Column("scope_key", sa.String(length=512), nullable=False),
        sa.Column("cursor_value", sa.String(length=512), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("connector_id", "scope_key", name="uq_connector_sync_scope"),
    )
    op.create_index(
        "ix_connector_sync_cursors_connector_id",
        "connector_sync_cursors",
        ["connector_id"],
    )


def downgrade() -> None:
    op.drop_table("connector_sync_cursors")
    op.drop_table("source_relations")
