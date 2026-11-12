"""Render health check: /healthz is 200 only when the database answers."""


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_healthz_503_when_database_is_down(client, monkeypatch):
    from app.db import database

    def broken():
        raise RuntimeError("db unreachable: secret-host:5432")

    monkeypatch.setattr(database.engine, "connect", broken)
    r = client.get("/healthz")
    assert r.status_code == 503
    assert "secret-host" not in r.text  # no internals leaked


def test_healthz_is_one_trivial_query(client):
    """F21 (owner decision 2026-11-12): an external uptime check calls GET /healthz every 10 minutes to
    keep Render's instance awake, so it must stay cheap: one SELECT 1, no table reads."""
    import sqlalchemy as sa

    from app.db import database

    seen = []

    def record(conn, cursor, statement, *args):
        seen.append(statement)

    sa.event.listen(database.engine, "before_cursor_execute", record)
    try:
        assert client.get("/healthz").status_code == 200
    finally:
        sa.event.remove(database.engine, "before_cursor_execute", record)
    assert seen == ["SELECT 1"]
