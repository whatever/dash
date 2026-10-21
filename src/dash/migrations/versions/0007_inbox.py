"""inbox

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the inbox_items and tool_rules tables."""
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        ),
        sa.Column("job_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"])
    op.create_index("ix_inbox_items_conversation_id", "inbox_items", ["conversation_id"])
    op.create_index("ix_inbox_items_job_id", "inbox_items", ["job_id"])
    op.create_index("ix_inbox_items_created_at", "inbox_items", ["created_at"])
    op.create_table(
        "tool_rules",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tool", "args"),
    )


def downgrade() -> None:
    """Drop the inbox_items and tool_rules tables."""
    op.drop_table("tool_rules")
    op.drop_table("inbox_items")
