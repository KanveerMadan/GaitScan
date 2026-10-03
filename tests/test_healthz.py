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
