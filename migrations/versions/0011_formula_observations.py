"""formulas read off the page image, kept beside the text rather than in it

Revision ID: 0011_formula_observations
Revises: 0010_report_citations
Create Date: 2026-09-11

Docling finds a formula's box even with formula enrichment off; the text carries a
numbered placeholder ("[formül 3]") and parse_provenance carries the box. When a run
extracts evidence from such a passage, the vision model reads the crop and the result
lands here.

Why a table and not the passage text: the passage text is hashed (content_hash) and
quoted verbatim by evidence verification. A model reading is neither deterministic
across model updates nor something a quote can be checked against, so it is stored the
way figure observations are -- a cache keyed by the crop's hash and the model that read
it, reused by every later run and by the report.

``latex`` is empty when the reading was rejected; ``status`` says why.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_formula_observations"
down_revision = "0010_report_citations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "formula_observations",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("source_version_id", sa.String(length=26), nullable=False),
        sa.Column("formula_no", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("vision_model", sa.String(length=160), nullable=False),
        sa.Column("latex", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_version_id", "image_hash", "vision_model",
            name="uq_formula_observation_identity",
        ),
    )
    op.create_index("ix_formula_observations_run_id", "formula_observations", ["run_id"])
    op.create_index(
        "ix_formula_observations_source_version_id",
        "formula_observations", ["source_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_formula_observations_source_version_id",
                  table_name="formula_observations")
    op.drop_index("ix_formula_observations_run_id", table_name="formula_observations")
    op.drop_table("formula_observations")
