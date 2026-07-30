"""source-linked figure observations

Revision ID: 0006_figure_observations
Revises: 0005_hitl
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_figure_observations"
down_revision = "0005_hitl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "figure_observations",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("run_id", sa.String(length=26), nullable=False),
        sa.Column("source_id", sa.String(length=26), nullable=False),
        sa.Column("source_version_id", sa.String(length=26), nullable=False),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("vision_model", sa.String(length=160), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "source_version_id",
            "image_hash",
            "vision_model",
            name="uq_figure_observation_identity",
        ),
    )
    op.create_index("ix_figure_observations_run_id", "figure_observations", ["run_id"])
    op.create_index("ix_figure_observations_source_id", "figure_observations", ["source_id"])
    op.create_index(
        "ix_figure_observations_source_version_id",
        "figure_observations",
        ["source_version_id"],
    )
    op.create_index(
        "ix_figure_observations_image_hash",
        "figure_observations",
        ["image_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_figure_observations_image_hash", table_name="figure_observations")
    op.drop_index(
        "ix_figure_observations_source_version_id",
        table_name="figure_observations",
    )
    op.drop_index("ix_figure_observations_source_id", table_name="figure_observations")
    op.drop_index("ix_figure_observations_run_id", table_name="figure_observations")
    op.drop_table("figure_observations")
