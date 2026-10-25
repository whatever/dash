"""router

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add routing decisions to the timeline and a fixed route to sources."""
    op.add_column("timeline", sa.Column("action", sa.Text(), nullable=True))
    op.add_column("timeline", sa.Column("routed_by", sa.Text(), nullable=True))
    op.add_column("timeline", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("timeline", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("route", sa.Text(), nullable=True))


def downgrade() -> None:
    """Drop the routing columns."""
    op.drop_column("sources", "route")
    op.drop_column("timeline", "reason")
    op.drop_column("timeline", "confidence")
    op.drop_column("timeline", "routed_by")
    op.drop_column("timeline", "action")
