"""F01/F08/F09: configuration comes from the environment and production refuses unsafe values."""

import os
import secrets
import subprocess
import sys

import pytest
from conftest import ROOT

GOOD_SECRET = secrets.token_urlsafe(48)
PROD = {
    "ENV": "production",
    "JWT_SECRET": GOOD_SECRET,
    "CORS_ORIGINS": "https://app.example.com",
    "DATABASE_URL": "sqlite:///./x.db",
}


def load(env):
    from app.core.config import load_settings

    return load_settings(env)


def test_production_requires_jwt_secret():
    env = {k: v for k, v in PROD.items() if k != "JWT_SECRET"}
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load(env)


@pytest.mark.parametrize("weak", ["", "your_jwt_secret_here", "change-me", "short-secret-under-32-chars"])
def test_production_rejects_placeholder_or_short_secret(weak):
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        load({**PROD, "JWT_SECRET": weak})


def test_error_message_never_echoes_secret_value():
    weak = "a-weak-but-distinctive-value"
    with pytest.raises(RuntimeError) as e:
        load({**PROD, "JWT_SECRET": weak})
    assert weak not in str(e.value)


def test_production_requires_database_url():
    env = {k: v for k, v in PROD.items() if k != "DATABASE_URL"}
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load(env)


def test_dev_falls_back_to_local_sqlite():
    assert load({"ENV": "dev"}).database_url.startswith("sqlite:///")


def test_postgres_scheme_is_normalised():
    s = load({**PROD, "DATABASE_URL": "postgres://u:p@h:5432/d"})
    assert s.database_url == "postgresql://u:p@h:5432/d"


def test_refusal_traceback_never_contains_the_value(tmp_path):
    weak = "distinctive-weak-value-123"
    r = _import_app(
        {
            "ENV": "production",
            "JWT_SECRET": weak,
            "CORS_ORIGINS": "https://a.example.com",
            "DATABASE_URL": f"sqlite:///{tmp_path}/x.db",
        }
    )
    assert r.returncode != 0 and "JWT_SECRET" in r.stderr
    assert weak not in r.stderr


def test_production_requires_cors_origins():
    env = {k: v for k, v in PROD.items() if k != "CORS_ORIGINS"}
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        load(env)


def test_env_defaults_to_production_fail_closed():
    with pytest.raises(RuntimeError):
        load({})


def test_dev_generates_ephemeral_secret():
    s = load({"ENV": "dev"})
    assert len(s.jwt_secret) >= 32
    assert s.cors_origins == ["http://localhost:3000", "http://localhost:5173"]  # CRA / Vite dev servers
    assert s.docs_enabled


def test_production_settings_parse():
    s = load({**PROD, "CORS_ORIGINS": "https://a.example.com, https://b.example.com"})
    assert s.jwt_secret == GOOD_SECRET
    assert s.cors_origins == ["https://a.example.com", "https://b.example.com"]
    assert not s.docs_enabled
    assert s.access_token_minutes <= 24 * 60


def _import_app(env):
    clean = {
        k: v for k, v in os.environ.items() if k not in ("ENV", "JWT_SECRET", "CORS_ORIGINS", "DATABASE_URL")
    }
    return subprocess.run(
        [sys.executable, "-c", "from app.main import app; print(app.docs_url, app.openapi_url)"],
        cwd=ROOT,
        env={**clean, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_app_refuses_to_start_in_production_without_secret(tmp_path):
    r = _import_app(
        {
            "ENV": "production",
            "CORS_ORIGINS": "https://a.example.com",
            "DATABASE_URL": f"sqlite:///{tmp_path}/x.db",
        }
    )
    assert r.returncode != 0
    assert "JWT_SECRET" in r.stderr


def test_docs_disabled_in_production(tmp_path):
    r = _import_app({**PROD, "DATABASE_URL": f"sqlite:///{tmp_path}/x.db"})
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout.strip().splitlines()[-1] == "None None"


def test_postgres_url_driver_is_installed():
    """Render's DATABASE_URL is postgresql://...; SQLAlchemy must find the driver it maps to."""
    import sqlalchemy as sa

    from app.core.config import load_settings

    url = load_settings(
        {
            "ENV": "production",
            "JWT_SECRET": "x" * 40,
            "CORS_ORIGINS": "https://a.example",
            "DATABASE_URL": "postgres://u:p@db.internal:5432/gaitscan",
        }
    ).database_url
    sa.create_engine(url).dispose()  # imports the DBAPI; does not connect
