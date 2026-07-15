"""Add acquisition provenance and crawl frontier.

Revision ID: 0003_collection_pipeline
Revises: 0002_passages
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_collection_pipeline"
down_revision = "0002_passages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_versions", sa.Column("raw_content", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "crawl_frontier",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("discovered_from", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "canonical_url", name="uq_frontier_run_url"),
    )
    op.create_index("ix_crawl_frontier_run_id", "crawl_frontier", ["run_id"])
    op.create_index("ix_crawl_frontier_status", "crawl_frontier", ["status"])


def downgrade() -> None:
    op.drop_index("ix_crawl_frontier_status", table_name="crawl_frontier")
    op.drop_index("ix_crawl_frontier_run_id", table_name="crawl_frontier")
    op.drop_table("crawl_frontier")
    op.drop_column("source_versions", "raw_content")
