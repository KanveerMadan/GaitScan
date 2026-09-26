"""baseline: the schema as created by the pre-Alembic `Base.metadata.create_all`

Revision ID: 0001
Revises:
Create Date: 2026-09-27

Idempotent on purpose: the production database already has these tables
(created by create_all, with no alembic_version). Each table is created only if
it is missing, so `alembic upgrade head` adopts an existing database and builds
a fresh one with the same code path.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _missing(name: str) -> bool:
    return name not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _missing("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_id", "users", ["id"], unique=False)

    if _missing("clinician_invites"):
        op.create_table(
            "clinician_invites",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("clinician_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=6), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=True),
            sa.Column("patient_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["clinician_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clinician_invites_code", "clinician_invites", ["code"], unique=True)
        op.create_index("ix_clinician_invites_id", "clinician_invites", ["id"], unique=False)

    if _missing("clinician_patients"):
        op.create_table(
            "clinician_patients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("clinician_id", sa.Integer(), nullable=False),
            sa.Column("patient_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["clinician_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["patient_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_clinician_patients_id", "clinician_patients", ["id"], unique=False)

    if _missing("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("patient_name", sa.String(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("activity", sa.String(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("risk_score", sa.Integer(), nullable=True),
            sa.Column("risk_label", sa.String(), nullable=True),
            sa.Column("risk_color", sa.String(), nullable=True),
            sa.Column("risk_meaning", sa.Text(), nullable=True),
            sa.Column("cadence", sa.Float(), nullable=True),
            sa.Column("knee_si", sa.Float(), nullable=True),
            sa.Column("hip_si", sa.Float(), nullable=True),
            sa.Column("knee_flex_L", sa.Float(), nullable=True),
            sa.Column("knee_flex_R", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if _missing("exercises"):
        op.create_table(
            "exercises",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("muscle", sa.String(), nullable=True),
            sa.Column("difficulty", sa.String(), nullable=True),
            sa.Column("instructions", sa.Text(), nullable=True),
            sa.Column("why", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if _missing("findings"):
        op.create_table(
            "findings",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.String(), nullable=True),
            sa.Column("metric", sa.String(), nullable=True),
            sa.Column("value", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("plain_english", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    for table in ("findings", "exercises", "sessions", "clinician_patients", "clinician_invites", "users"):
        op.drop_table(table)
