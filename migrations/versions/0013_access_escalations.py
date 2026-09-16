"""blocked searches and source pages kept for the user after a run

Revision ID: 0013_access_escalations
Revises: 0012_document_revisions
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_access_escalations"
down_revision = "0012_document_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_issues",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("owner_id", sa.String(length=26), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("connector_id", sa.String(length=100), nullable=True),
        sa.Column("mission_id", sa.String(length=26), nullable=True),
        sa.Column("branch_id", sa.String(length=120), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("strategies_tried", sa.JSON(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "kind", "dedupe_key", name="uq_access_issue_identity"),
    )
    op.create_index("ix_access_issues_run_id", "access_issues", ["run_id"])
    op.create_index("ix_access_issues_owner_id", "access_issues", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_access_issues_owner_id", table_name="access_issues")
    op.drop_index("ix_access_issues_run_id", table_name="access_issues")
    op.drop_table("access_issues")
