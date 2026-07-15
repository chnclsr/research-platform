"""Add structure-aware document passages.

Revision ID: 0002_passages
Revises: 0001_initial
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_passages"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passages",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("source_version_id", sa.String(length=26), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False, server_default="Document"),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source_version_id", "chunk_index", name="uq_passage_version_chunk"),
    )
    op.create_index("ix_passages_source_version_id", "passages", ["source_version_id"])
    op.create_index("ix_passages_content_hash", "passages", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_passages_content_hash", table_name="passages")
    op.drop_index("ix_passages_source_version_id", table_name="passages")
    op.drop_table("passages")
