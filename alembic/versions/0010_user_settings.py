"""users.settings: per-user settings (Plan V3 Phase 9)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01

One nullable JSON column; NULL means the defaults.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("settings", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("settings")
