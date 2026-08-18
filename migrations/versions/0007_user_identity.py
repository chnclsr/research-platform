"""user accounts, api keys and run ownership

Revision ID: 0007_user_identity
Revises: 0006_figure_observations
Create Date: 2026-08-17

``research_runs.owner_id`` is added nullable and stays nullable. Existing runs are
assigned to the bootstrap admin by ``research-admin bootstrap``, which runs after this
migration; a NOT NULL constraint here would fail on a database that already holds runs.
Beyond the backfill, a NULL owner is treated as admin-only by the repository guard, so
the nullable column fails closed rather than open.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_user_identity"
down_revision = "0006_figure_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"], unique=True)

    op.create_table(
        "telegram_identities",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_index("ix_telegram_identities_user_id", "telegram_identities", ["user_id"])

    op.add_column("research_runs", sa.Column("owner_id", sa.String(length=26), nullable=True))
    op.create_index("ix_research_runs_owner_id", "research_runs", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_research_runs_owner_id", table_name="research_runs")
    op.drop_column("research_runs", "owner_id")
    op.drop_index("ix_telegram_identities_user_id", table_name="telegram_identities")
    op.drop_table("telegram_identities")
    op.drop_index("ix_api_keys_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
