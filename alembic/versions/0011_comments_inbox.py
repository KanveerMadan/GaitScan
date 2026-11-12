"""session_comments and users.inbox_seen_at: comments and the clinician inbox (Plan V3 Phase 9)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-01

A new table and one nullable column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_session_comments_session_id", "session_comments", ["session_id"])
    op.add_column("users", sa.Column("inbox_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("inbox_seen_at")
    op.drop_index("ix_session_comments_session_id", table_name="session_comments")
    op.drop_table("session_comments")
