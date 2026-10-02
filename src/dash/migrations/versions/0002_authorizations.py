"""authorizations

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the authorizations table."""
    op.create_table(
        "authorizations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("authorizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("secrets", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "kind", "external_id"),
    )
    op.create_index("ix_authorizations_parent_id", "authorizations", ["parent_id"])


def downgrade() -> None:
    """Drop the authorizations table."""
    op.drop_table("authorizations")
