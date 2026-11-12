"""Lower-case every stored email address (2026-11-12)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-12

Sign-up used to keep an address as typed while recovery looked it up in lower case, so an account
made as Name@example.com could never be recovered with a code. The app now lowercases every address
on the way in (app/core/email.py); this makes the stored ones match.

If two accounts' addresses differ only by capitals, lowercasing would merge them into one address
(and break the unique index), so nothing is changed and the migration stops with their user ids.
Decide which account to keep, change or remove the other, then deploy again. The ids, not the
addresses, are in the message so no address reaches the deploy logs.

The downgrade can't restore the original capitals: it changes nothing.
"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

users = sa.table("users", sa.column("id", sa.Integer), sa.column("email", sa.String))


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.select(users.c.id, users.c.email)).all()
    by_address: dict[str, list[int]] = defaultdict(list)
    for uid, email in rows:
        by_address[email.lower()].append(uid)
    clashes = sorted(sorted(ids) for ids in by_address.values() if len(ids) > 1)
    if clashes:
        groups = "; ".join(", ".join(str(i) for i in ids) for ids in clashes)
        raise RuntimeError(
            f"Migration 0014 stopped, nothing changed: {len(clashes)} group(s) of accounts have email "
            f"addresses that differ only by capitals (user ids {groups}). Keep one account per group "
            "(change or delete the other), then deploy again."
        )
    for uid, email in rows:
        if email != email.lower():
            conn.execute(users.update().where(users.c.id == uid).values(email=email.lower()))


def downgrade() -> None:
    pass  # the original capitals are gone
