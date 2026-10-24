"""V3 metric policy: archive the removed measurements; store pipeline_version + result

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04

Plan V3 removes the risk score, activity classification, symmetry indices, modes, findings and
exercise suggestions. Nothing is silently dropped: for every existing session, those values (and
its findings and exercises rows) are copied into session_archive.data as JSON before the columns
and tables go. Existing sessions are labelled pipeline_version = 'legacy' with no result; new
sessions store the v2 result JSON.

Downgrade restores every archived value. It refuses while v2 sessions exist, because the old
schema has nowhere to keep their results.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SESSION_COLUMNS = {
    "activity": sa.String(),
    "confidence": sa.Integer(),
    "risk_score": sa.Integer(),
    "risk_label": sa.String(),
    "risk_color": sa.String(),
    "risk_meaning": sa.Text(),
    "cadence": sa.Float(),
    "knee_si": sa.Float(),
    "hip_si": sa.Float(),
    "knee_flex_L": sa.Float(),
    "knee_flex_R": sa.Float(),
    "mode": sa.String(),
}
FINDING_COLUMNS = ("id", "metric", "value", "status", "plain_english")
EXERCISE_COLUMNS = ("id", "name", "muscle", "difficulty", "instructions", "why")
SOURCE = "migration 0003: values from the pre-V3 pipeline, removed from the product"


def _rows(conn: sa.Connection, sql: str, **params: object) -> list[dict[str, object]]:
    return [dict(r._mapping) for r in conn.execute(sa.text(sql), params)]


def upgrade() -> None:
    conn = op.get_bind()
    archive = op.create_table(
        "session_archive",
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    cols = ", ".join(f'"{c}"' for c in ["id", *SESSION_COLUMNS])  # quoted: knee_flex_L is mixed case
    payload = []
    for s in _rows(conn, f"SELECT {cols} FROM sessions"):  # noqa: S608 (fixed column names)
        sid = s.pop("id")
        payload.append(
            {
                "session_id": sid,
                "source": SOURCE,
                "data": {
                    "session": s,
                    "findings": _rows(
                        conn,
                        f"SELECT {', '.join(FINDING_COLUMNS)} FROM findings WHERE session_id = :s ORDER BY id",  # noqa: S608
                        s=sid,
                    ),
                    "exercises": _rows(
                        conn,
                        f"SELECT {', '.join(EXERCISE_COLUMNS)} FROM exercises WHERE session_id = :s ORDER BY id",  # noqa: S608
                        s=sid,
                    ),
                },
            }
        )
    if payload:
        op.bulk_insert(archive, payload)

    op.drop_table("findings")
    op.drop_table("exercises")
    with op.batch_alter_table("sessions") as batch:
        for name in SESSION_COLUMNS:
            batch.drop_column(name)
        batch.add_column(sa.Column("pipeline_version", sa.String(), nullable=False, server_default="legacy"))
        batch.add_column(sa.Column("result", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    v2 = conn.execute(sa.text("SELECT count(*) FROM sessions WHERE pipeline_version <> 'legacy'")).scalar()
    if v2:
        raise RuntimeError(
            f"{v2} session(s) hold pipeline 2 results, which the pre-0003 schema cannot store. "
            "Export or delete them before downgrading."
        )
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("result")
        batch.drop_column("pipeline_version")
        for name, type_ in SESSION_COLUMNS.items():
            batch.add_column(sa.Column(name, type_, nullable=True))
    findings = op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("metric", sa.String(), nullable=True),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("plain_english", sa.Text(), nullable=True),
    )
    exercises = op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("muscle", sa.String(), nullable=True),
        sa.Column("difficulty", sa.String(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("why", sa.Text(), nullable=True),
    )
    sessions = sa.table("sessions", sa.column("id"), *(sa.column(c) for c in SESSION_COLUMNS))
    for row in _rows(conn, "SELECT session_id, data FROM session_archive"):
        data = row["data"] if isinstance(row["data"], dict) else json.loads(str(row["data"]))
        sid = row["session_id"]
        conn.execute(sessions.update().where(sessions.c.id == sid).values(**data["session"]))
        if data["findings"]:
            op.bulk_insert(findings, [{**f, "session_id": sid} for f in data["findings"]])
        if data["exercises"]:
            op.bulk_insert(exercises, [{**e, "session_id": sid} for e in data["exercises"]])
    op.drop_table("session_archive")
    if conn.dialect.name == "postgresql":  # restored explicit ids: move the sequences past them
        for table in ("findings", "exercises"):
            conn.execute(
                sa.text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)"
                )
            )
