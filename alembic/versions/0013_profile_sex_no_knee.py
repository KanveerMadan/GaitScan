"""profiles.sex; knee angle deleted from stored results (owner decisions 2026-11-12)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-12

- profiles.sex: optional ("female" / "male"), only for the published cadence reference by age and
  sex. The account holder's own sex and birth year are in users.settings (JSON), so they need no column.
- Knee angle is no longer reported (Phase 8 cancelled: it can never be validated), so it is deleted
  from every stored result rather than kept unseen: peak_knee_flexion (metrics, accuracy) and the
  knee_flexion curve. The data export then holds what the account holds. Not restorable: the
  downgrade drops the column but can't bring the knee values back.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_NOTE = (
    "Left and right legs couldn't be told apart reliably in this video, so peak knee flexion isn't "
    "shown for each leg. Cadence and step time don't depend on telling the legs apart."
)
NEW_NOTE = (
    "Left and right legs couldn't be told apart reliably in this video, so there's no outline of the "
    "walk to replay. Cadence and step time don't depend on telling the legs apart."
)
sessions = sa.table("sessions", sa.column("id", sa.String), sa.column("result", sa.JSON))


def without_knee(result: dict[str, Any]) -> dict[str, Any] | None:
    """The result without knee values, or None when it held none."""
    out = dict(result)
    changed = False
    for key, name in (("metrics", "peak_knee_flexion"), ("accuracy", "peak_knee_flexion"), ("curves", "knee_flexion")):
        part = out.get(key)
        if isinstance(part, dict) and name in part:
            out[key] = {k: v for k, v in part.items() if k != name}
            changed = True
    notes = out.get("notes")
    if isinstance(notes, list) and OLD_NOTE in notes:
        out["notes"] = [NEW_NOTE if n == OLD_NOTE else n for n in notes]
        changed = True
    return out if changed else None


def upgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.add_column(sa.Column("sex", sa.String(), nullable=True))
    conn = op.get_bind()
    for sid, result in conn.execute(sa.select(sessions.c.id, sessions.c.result)).all():
        if isinstance(result, dict) and (new := without_knee(result)) is not None:
            conn.execute(sessions.update().where(sessions.c.id == sid).values(result=new))


def downgrade() -> None:
    with op.batch_alter_table("profiles") as batch:
        batch.drop_column("sex")
