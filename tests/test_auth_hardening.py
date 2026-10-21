"""Amendment 2026-09-27: password minimum (register/change only), F10 rate limiting, F12 enumeration."""

import uuid

import pytest
from conftest import PASSWORD, auth, register


def new_email():
    return f"{uuid.uuid4().hex[:10]}@example.com"


# ---- password minimum length --------------------------------------------------------------
def test_register_rejects_password_shorter_than_10(client):
    r = client.post("/auth/register", json={"email": new_email(), "password": "123456789"})
    assert r.status_code == 422
    assert "at least 10 characters" in r.json()["detail"]  # plain string the UI can show


def test_register_accepts_exactly_10(client):
    r = client.post("/auth/register", json={"email": new_email(), "password": "1234567890"})
    assert r.status_code == 201


def test_legacy_user_with_short_password_can_still_log_in(client):
    from app.core.security import hash_password
    from app.db.database import SessionLocal
    from app.db.models import User

    email = new_email()
    db = SessionLocal()
    db.add(User(email=email, hashed_password=hash_password("short"), role="patient"))
    db.commit()
    db.close()
    r = client.post("/auth/login", json={"email": email, "password": "short"})
    assert r.status_code == 200, r.text


def test_change_password_requires_auth(client):
    r = client.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "x" * 12})
    assert r.status_code == 401


def test_change_password_enforces_minimum_and_current_password(client):
    email, t = register(client)
    short = client.post(
        "/auth/change-password", headers=auth(t), json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422 and "at least 10 characters" in short.json()["detail"]
    wrong = client.post(
        "/auth/change-password",
        headers=auth(t),
        json={"current_password": "not-my-password", "new_password": "a-new-password-1"},
    )
    assert wrong.status_code == 400


def test_change_password_works_and_old_password_stops_working(client):
    email, t = register(client)
    r = client.post(
        "/auth/change-password",
        headers=auth(t),
        json={"current_password": PASSWORD, "new_password": "a-brand-new-passphrase"},
    )
    assert r.status_code == 200
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert (
        client.post("/auth/login", json={"email": email, "password": "a-brand-new-passphrase"}).status_code
        == 200
    )


def test_legacy_short_password_user_can_change_to_a_long_one(client):
    from app.core.security import hash_password
    from app.db.database import SessionLocal
    from app.db.models import User

    email = new_email()
    db = SessionLocal()
    db.add(User(email=email, hashed_password=hash_password("short"), role="patient"))
    db.commit()
    db.close()
    t = client.post("/auth/login", json={"email": email, "password": "short"}).json()["access_token"]
    r = client.post(
        "/auth/change-password",
        headers=auth(t),
        json={"current_password": "short", "new_password": "now-long-enough-1"},
    )
    assert r.status_code == 200


# ---- F10 rate limiting -----------------------------------------------------------------------
def test_failed_logins_for_one_email_are_limited(client):
    email, _ = register(client)
    codes = [
        client.post("/auth/login", json={"email": email, "password": f"wrong-{i}"}).status_code
        for i in range(8)
    ]
    assert codes[:5] == [401] * 5
    assert 429 in codes[5:]
    blocked = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert blocked.status_code == 429  # locked for the window, even with the right password
    assert int(blocked.headers["Retry-After"]) > 0


def test_limit_applies_to_unknown_emails_too(client):
    """The 429 must not reveal whether the account exists."""
    email = new_email()
    codes = [client.post("/auth/login", json={"email": email, "password": "x"}).status_code for _ in range(7)]
    assert 429 in codes


def test_login_attempts_per_client_ip_are_limited(client):
    codes = [
        client.post("/auth/login", json={"email": new_email(), "password": "x"}).status_code
        for _ in range(25)
    ]
    assert 429 in codes


def test_registrations_per_client_ip_are_limited(client):
    codes = [
        client.post("/auth/register", json={"email": new_email(), "password": "long-enough-pw"}).status_code
        for _ in range(15)
    ]
    assert codes[0] == 201 and 429 in codes


# ---- F12 enumeration -------------------------------------------------------------------------
def test_unknown_email_login_costs_a_bcrypt_verification(client, monkeypatch):
    import app.api.auth as auth_api

    calls = []
    real = auth_api.verify_password
    monkeypatch.setattr(auth_api, "verify_password", lambda p, h: calls.append(1) or real(p, h))
    r = client.post("/auth/login", json={"email": new_email(), "password": "whatever-password"})
    assert r.status_code == 401
    assert calls == [1]


@pytest.mark.parametrize("path", ["/auth/login"])
def test_login_error_does_not_say_which_part_was_wrong(client, path):
    email, _ = register(client)
    unknown = client.post(path, json={"email": new_email(), "password": "wrong-password"}).json()
    wrong_pw = client.post(path, json={"email": email, "password": "wrong-password"}).json()
    assert unknown == wrong_pw
