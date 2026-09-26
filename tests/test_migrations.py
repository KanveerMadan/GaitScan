"""Alembic migrations build the same schema as the models, and adopt a pre-Alembic database."""

import os

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
