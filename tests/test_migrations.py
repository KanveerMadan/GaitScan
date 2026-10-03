"""Alembic migrations build the same schema as the models, and adopt a pre-Alembic database."""

import os
from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from conftest import ROOT, migrate


def schema_diff(url):
    from app.db import models  # noqa: F401
    from app.db.database import Base

    engine = sa.create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    return diff


def head_revision():
    from alembic.script import ScriptDirectory

    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def current_revision(url):
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        rev = MigrationContext.configure(conn).get_current_revision()
    engine.dispose()
    return rev


def test_fresh_database_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path}/fresh.db"
    migrate(url)
    assert schema_diff(url) == []
    assert current_revision(url) == head_revision()


def test_adopts_pre_alembic_database(tmp_path):
    """Production was built by create_all: tables exist, no alembic_version."""
    url = f"sqlite:///{tmp_path}/legacy.db"
    migrate(url, "0001")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE alembic_version"))
        conn.execute(
            sa.text("INSERT INTO users (email, hashed_password, role) VALUES ('a@b.com', 'x', 'patient')")
        )
    engine.dispose()
    migrate(url)  # must not fail on existing tables
    assert current_revision(url) == head_revision()
    assert schema_diff(url) == []
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM users")).scalar() == 1  # data kept
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL (CI does)")
def test_postgres_fresh_database_matches_models():
    url = os.environ["TEST_POSTGRES_URL"]
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()
    migrate(url)
    assert schema_diff(url) == []


def _reset_postgres(url):
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()


DB_BACKENDS = ["sqlite"] + (["postgres"] if os.getenv("TEST_POSTGRES_URL") else [])


@pytest.mark.parametrize("backend", DB_BACKENDS)
@pytest.mark.parametrize("variant", ["phase0", "early"])
def test_upgrade_keeps_every_row_and_column_of_a_create_all_database(tmp_path, backend, variant):
    """Production was built by create_all (no alembic_version). Upgrading must lose nothing."""
    from legacy_schema import build_legacy_db

    if backend == "postgres":
        url = os.environ["TEST_POSTGRES_URL"]
        _reset_postgres(url)
    else:
        url = f"sqlite:///{tmp_path}/legacy.db"
    rows = build_legacy_db(url, variant)

    migrate(url)

    assert current_revision(url) == head_revision()
    assert schema_diff(url) == []
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        for table, expected in rows.items():
            got = [dict(r._mapping) for r in conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id"))]  # noqa: S608
            assert len(got) == len(expected), table
            for g, e in zip(got, expected, strict=True):
                for col, val in e.items():
                    if isinstance(val, datetime) and isinstance(g[col], str):  # SQLite stores text
                        g[col] = datetime.fromisoformat(g[col])
                    if isinstance(val, datetime) and g[col].tzinfo is None:
                        val = val.replace(tzinfo=None)
                    assert g[col] == val, (table, col)
                assert set(e) <= set(g), table  # no legacy column dropped
        assert conn.execute(sa.text("SELECT mode FROM sessions")).scalar() is None  # 0002: not recorded
    engine.dispose()
    # The upgraded database still accepts new rows (ids, defaults, FKs intact).
    from sqlalchemy.orm import Session as OrmSession

    from app.db.models import Session, User

    engine = sa.create_engine(url)
    with OrmSession(engine) as db:
        user = User(email="new@example.com", hashed_password="h", role="patient")
        db.add(user)
        db.flush()
        db.add(Session(id="ef56ab78", user_id=user.id, mode="Clinical"))
        db.commit()
    engine.dispose()
    if backend == "postgres":
        _reset_postgres(url)
