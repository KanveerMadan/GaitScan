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


# Migration 0003 (Plan V3): these values move from their columns/tables into session_archive.
ARCHIVED_SESSION_COLUMNS = (
    "activity",
    "confidence",
    "risk_score",
    "risk_label",
    "risk_color",
    "risk_meaning",
    "cadence",
    "knee_si",
    "hip_si",
    "knee_flex_L",
    "knee_flex_R",
)
ARCHIVED_TABLES = ("findings", "exercises")


def _archive(conn, session_id):
    import json

    raw = conn.execute(
        sa.text("SELECT data FROM session_archive WHERE session_id = :s"), {"s": session_id}
    ).scalar()
    return raw if isinstance(raw, dict) else json.loads(raw)


def _same(table, col, got, val):
    if isinstance(val, datetime) and isinstance(got, str):  # SQLite stores text
        got = datetime.fromisoformat(got)
    if isinstance(val, datetime) and got.tzinfo is None:
        val = val.replace(tzinfo=None)
    assert got == val, (table, col, got, val)


@pytest.mark.parametrize("backend", DB_BACKENDS)
@pytest.mark.parametrize("variant", ["phase0", "early"])
def test_upgrade_keeps_every_value_of_a_create_all_database(tmp_path, backend, variant):
    """Production was built by create_all (no alembic_version). Upgrading must lose nothing: every
    legacy value is either still in its column or in session_archive (migration 0003)."""
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
    insp = sa.inspect(engine)
    with engine.connect() as conn:
        for table, expected in rows.items():
            if table in ARCHIVED_TABLES:
                assert table not in insp.get_table_names()
                continue
            got = [dict(r._mapping) for r in conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id"))]  # noqa: S608
            assert len(got) == len(expected), table
            for g, e in zip(got, expected, strict=True):
                for col, val in e.items():
                    if table == "sessions" and col in ARCHIVED_SESSION_COLUMNS:
                        assert col not in g, col
                        continue
                    _same(table, col, g[col], val)
        for e in rows["sessions"]:
            arch = _archive(conn, e["id"])
            for col in ARCHIVED_SESSION_COLUMNS:
                assert arch["session"][col] == e[col], col
            assert arch["session"]["mode"] is None  # 0002: never recorded
            for table in ARCHIVED_TABLES:
                want = [
                    {k: v for k, v in r.items() if k != "session_id"}
                    for r in rows[table]
                    if r["session_id"] == e["id"]
                ]
                assert arch[table] == want, table
            label = conn.execute(
                sa.text("SELECT pipeline_version, result FROM sessions WHERE id = :s"), {"s": e["id"]}
            ).one()
            assert label.pipeline_version == "legacy" and label.result is None
    engine.dispose()
    # The upgraded database still accepts new rows (ids, defaults, FKs intact).
    from sqlalchemy.orm import Session as OrmSession

    from app.db.models import Session, User

    engine = sa.create_engine(url)
    with OrmSession(engine) as db:
        user = User(email="new@example.com", hashed_password="h", role="patient")
        db.add(user)
        db.flush()
        db.add(
            Session(id="ef56ab78", user_id=user.id, pipeline_version="2.0.0", result={"status": "accepted"})
        )
        db.commit()
    engine.dispose()
    if backend == "postgres":
        _reset_postgres(url)


def _downgrade(url, rev):
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.downgrade(cfg, rev)


@pytest.mark.parametrize("backend", DB_BACKENDS)
def test_0003_downgrade_restores_the_archived_values(tmp_path, backend):
    from legacy_schema import build_legacy_db

    if backend == "postgres":
        url = os.environ["TEST_POSTGRES_URL"]
        _reset_postgres(url)
    else:
        url = f"sqlite:///{tmp_path}/legacy.db"
    rows = build_legacy_db(url, "phase0")
    migrate(url, "0002")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE sessions SET mode = 'Runner'"))
    engine.dispose()
    migrate(url)
    _downgrade(url, "0002")
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        s = dict(conn.execute(sa.text("SELECT * FROM sessions")).one()._mapping)
        for col in ARCHIVED_SESSION_COLUMNS:
            assert s[col] == rows["sessions"][0][col], col
        assert s["mode"] == "Runner"
        for table in ARCHIVED_TABLES:
            got = [dict(r._mapping) for r in conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id"))]  # noqa: S608
            assert got == rows[table], table
        assert "session_archive" not in sa.inspect(engine).get_table_names()
    engine.dispose()
    if backend == "postgres":
        _reset_postgres(url)


def test_0003_downgrade_refuses_to_drop_v2_results(tmp_path):
    url = f"sqlite:///{tmp_path}/v2.db"
    migrate(url)
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO sessions (id, pipeline_version, result) VALUES ('s1', '2.0.0', '{}')")
        )
    engine.dispose()
    with pytest.raises(RuntimeError, match="pipeline 2"):
        _downgrade(url, "0002")
