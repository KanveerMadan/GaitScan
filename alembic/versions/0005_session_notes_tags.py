"""sessions.notes and sessions.tags: the owner's own labels (Plan V3 Phase 4)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-26

Two nullable columns; existing rows keep NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("tags")
        batch.drop_column("notes")
