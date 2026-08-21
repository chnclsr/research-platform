"""priority band and preemption marker for research runs

Revision ID: 0009_run_priority
Revises: 0008_telegram_link_codes
Create Date: 2026-08-21

The queue was strictly first-in-first-out, so an urgent question could sit behind a
three-hour run with no way past it. These two columns are what the scheduler reads.

``priority`` is a column rather than a protocol field because the protocol says what to
research -- it is the document the user approves at the plan gate -- while this says when
to run it, and because "is an urgent run waiting?" is asked on every scheduler tick and
belongs in an index rather than inside jsonb.

``preempted_at`` records that *the scheduler* paused a run. A run paused by its owner and
a run paused to let an urgent one through are the same status, and auto-resume must only
ever pick up the second kind.
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_run_priority"
down_revision = "0008_telegram_link_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "priority",
            sa.String(length=10),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "research_runs",
        sa.Column("preempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Both scheduler questions -- "is an urgent run queued?" and "which normal run is
    # running?" -- filter on status and priority together.
    op.create_index(
        "ix_research_runs_status_priority",
        "research_runs",
        ["status", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_runs_status_priority", table_name="research_runs")
    op.drop_column("research_runs", "preempted_at")
    op.drop_column("research_runs", "priority")
