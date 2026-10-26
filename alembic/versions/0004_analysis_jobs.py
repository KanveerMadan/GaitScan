"""analysis_jobs: videos analysed in the background (Plan V3 Phase 4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26

A new table only; existing tables are untouched. Downgrade drops it (jobs are transient: the
measurements live in sessions).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("test", sa.String(), nullable=False, server_default="walk"),
        sa.Column("patient_name", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analysis_jobs")
