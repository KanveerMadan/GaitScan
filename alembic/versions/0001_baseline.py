"""baseline: the schema as created by the pre-Alembic `Base.metadata.create_all`

Revision ID: 0001
Revises:
Create Date: 2026-09-27

Idempotent on purpose: the production database already has these tables
(created by create_all, with no alembic_version). Each table is created only if
it is missing, so `alembic upgrade head` adopts an existing database and builds
a fresh one with the same code path.

create_all never altered existing tables, so an adopted database can hold an older
shape. `_reconcile_legacy_drift` fixes the two the model history allows (see
tests/legacy_schema.py); tests/test_migrations.py checks the result matches.
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


    _reconcile_legacy_drift()


def _reconcile_legacy_drift() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # sessions created before 2026-04-15 (5c18025) have no user_id.
    if "user_id" not in {c["name"] for c in insp.get_columns("sessions")}:
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key("fk_sessions_user_id_users", "users", ["user_id"], ["id"])
    # users created 2026-04-15..20 (a93b308..a5d0a91) on Postgres have a native enum role.
    if bind.dialect.name == "postgresql":
        role = next(c for c in insp.get_columns("users") if c["name"] == "role")
        if isinstance(role["type"], sa.Enum):
            op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR USING role::text")
            op.execute(f"DROP TYPE IF EXISTS {role['type'].name}")


def downgrade() -> None:
    for table in ("findings", "exercises", "sessions", "clinician_patients", "clinician_invites", "users"):
        op.drop_table(table)
