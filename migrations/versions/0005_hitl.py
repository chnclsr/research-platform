"""human-in-the-loop research checkpoints

Revision ID: 0005_hitl
Revises: 0004_academic_sources
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_hitl"
down_revision = "0004_academic_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_runs", sa.Column("interaction", sa.JSON(), nullable=True))
    op.add_column(
        "research_runs",
        sa.Column("hitl_history", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("research_runs", "hitl_history")
    op.drop_column("research_runs", "interaction")
