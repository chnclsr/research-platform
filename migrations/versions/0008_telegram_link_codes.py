"""self-service telegram linking codes

Revision ID: 0008_telegram_link_codes
Revises: 0007_user_identity
Create Date: 2026-08-18

Linking used to require an administrator running ``research-admin link-telegram``. These
two columns let a signed-in user prove they hold the account themselves: the panel issues
a short-lived code, the bot consumes it.

The code lives on the user row rather than in its own table because a user can only have
one pending code at a time -- issuing a new one replaces the old, and consuming it clears
both columns. That makes single use a property of the schema instead of something the
consuming code has to remember to enforce.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_telegram_link_codes"
down_revision = "0007_user_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_link_code_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_link_expires_at")
    op.drop_column("users", "telegram_link_code_hash")