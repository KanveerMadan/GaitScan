"""F41: structured logs with redaction and request IDs; Sentry only with a DSN and without PII."""

import json
import logging

from conftest import PASSWORD, register


def test_redaction_removes_secrets_and_emails():
    from app.core.logging import redact

    event = {
        "event": "login failed for alice@example.com",
        "password": "hunter2-long",
        "Authorization": "Bearer abc",
        "new_password": "x",
        "email": "a@b.com",
        "path": "/auth/login",
    }
    out = redact(None, "info", dict(event))
    text = json.dumps(out)
    for secret in ("hunter2-long", "Bearer abc", "alice@example.com", "a@b.com"):
        assert secret not in text
    assert out["path"] == "/auth/login"


def test_requests_get_an_id_and_one_json_access_line(client, capfd):
    r = client.get("/status", headers={"X-Request-ID": "req-123"})
    assert r.headers["X-Request-ID"] == "req-123"
    r2 = client.get("/status")
    assert len(r2.headers["X-Request-ID"]) >= 16
    lines = [json.loads(line) for line in capfd.readouterr().err.splitlines() if line.startswith("{")]
    access = [e for e in lines if e.get("event") == "request" and e.get("request_id") == "req-123"]
    assert access and access[0]["status"] == 200 and access[0]["path"] == "/status"


def test_login_logs_contain_no_password_or_email(client, capfd):
    email, _ = register(client)
    client.post("/auth/login", json={"email": email, "password": "wrong-password-xyz"})
    logging.getLogger("gaitscan").warning("probe %s", email)  # stdlib calls go through redaction too
    err = capfd.readouterr().err
    assert "wrong-password-xyz" not in err and PASSWORD not in err
    assert email not in err


def test_sentry_not_initialised_without_dsn(monkeypatch):
    import app.core.observability as obs

    calls = []
    monkeypatch.setattr(obs.sentry_sdk, "init", lambda **kw: calls.append(kw))
    obs.init_sentry(dsn="", environment="production")
    assert calls == []


def test_sentry_initialised_without_pii_or_bodies(monkeypatch):
    import app.core.observability as obs

    calls = []
    monkeypatch.setattr(obs.sentry_sdk, "init", lambda **kw: calls.append(kw))
    obs.init_sentry(dsn="https://key@o0.ingest.example.com/1", environment="production")
    assert calls and calls[0]["send_default_pii"] is False
    assert calls[0]["max_request_body_size"] == "never"
    assert calls[0]["environment"] == "production"


def test_exception_tracebacks_are_redacted(client, capfd, monkeypatch):
    import app.api.analysis as analysis

    def boom(path):
        raise RuntimeError("failure while processing bob@example.com")

    from conftest import fake_video

    fake_video(monkeypatch)
    monkeypatch.setattr(analysis, "extract_clip", boom)
    _, t = register(client)
    client.post(
        "/analyze", headers={"Authorization": f"Bearer {t}"}, files={"video": ("v.mp4", b"x", "video/mp4")}
    )
    err = capfd.readouterr().err
    assert "Traceback" in err  # the traceback is logged server-side...
    assert "bob@example.com" not in err  # ...but redacted


def test_database_errors_do_not_carry_bound_parameters():
    """SQLAlchemy puts bound values (e.g. password hashes) in exception text, which reaches logs/Sentry."""
    import pytest
    import sqlalchemy as sa

    from app.db.database import engine

    with pytest.raises(sa.exc.DBAPIError) as e, engine.connect() as conn:
        conn.execute(sa.text("INSERT INTO no_such_table (x) VALUES (:x)"), {"x": "$2b$12$hash-like-value"})
    assert "hash-like-value" not in str(e.value)
