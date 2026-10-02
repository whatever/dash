"""conversations, messages, memories (pgvector)

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On RDS the app role can't create extensions. Run this once as the master user;
    # IF NOT EXISTS makes it a no-op here after that.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "memories",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_memories_created_at", "memories", ["created_at"])
    op.execute(
        "CREATE INDEX ix_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("memories")
    op.drop_table("messages")
    op.drop_table("conversations")
