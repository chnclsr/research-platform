"""per-source record of how each source ended up in the Word report

Revision ID: 0010_report_citations
Revises: 0009_run_priority
Create Date: 2026-09-01

The chain from a raw source to a reference in the .docx was queryable up to the claim and
no further. Source labels (``S03``) are assigned by list position while the document is
rendered, and the synthesis sections that cite them are in-memory dataclasses, so the last
hop existed only for the duration of ``build_exports``.

The consequence was not a missing statistic. A source could carry audited quotes and still
be absent from the report for four different reasons -- no evidence at all, evidence that
never cleared the reportable threshold, a section draft discarded by the citation guard, or
a model that simply never cited what it was offered -- and from outside all four looked the
same: a source in the catalogue and nowhere else.

``drop_reason`` is nullable and NULL is the success case: the source is cited in the report.
Writing it the other way round would need a sentinel string for the outcome that matters.

No backfill. Reproducing these rows for an existing run means re-running the LLM synthesis,
which would produce a different report than the one that was delivered -- a citation record
that does not describe the shipped document is worse than an empty one. Older runs read as
"no export record" in the panel.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_report_citations"
down_revision = "0009_run_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_citations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("source_id", sa.String(length=26), nullable=False),
        sa.Column("label", sa.String(length=8), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("cited_sections", sa.JSON(), nullable=False),
        sa.Column("offered_sections", sa.JSON(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_bibliography", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("drop_reason", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        # Export can run twice for one run: the writer deletes and re-inserts, and this
        # keeps a half-finished second pass from leaving two rows for one source.
        sa.UniqueConstraint("run_id", "source_id", name="uq_report_citation_run_source"),
    )
    op.create_index("ix_report_citations_run_id", "report_citations", ["run_id"])
    op.create_index("ix_report_citations_source_id", "report_citations", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_report_citations_source_id", table_name="report_citations")
    op.drop_index("ix_report_citations_run_id", table_name="report_citations")
    op.drop_table("report_citations")
