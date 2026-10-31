"""profiles, sessions.profile_id, analysis_jobs.profile_id: other adults on one account (Plan V3 Phase 9)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-01

A new table and two nullable columns. NULL profile_id means the account holder.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_profiles_owner_id", "profiles", ["owner_id"])
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_sessions_profile_id", "profiles", ["profile_id"], ["id"])
    with op.batch_alter_table("analysis_jobs") as batch:
        batch.add_column(sa.Column("profile_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_analysis_jobs_profile_id", "profiles", ["profile_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch:
        batch.drop_constraint("fk_analysis_jobs_profile_id", type_="foreignkey")
        batch.drop_column("profile_id")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("fk_sessions_profile_id", type_="foreignkey")
        batch.drop_column("profile_id")
    op.drop_index("ix_profiles_owner_id", table_name="profiles")
    op.drop_table("profiles")
