"""Password reset and email verification (Plan V3 Phase 5): single-use, expiring links whose tokens
are stored only as hashes; a reset or a password change ends every earlier login."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from conftest import PASSWORD, auth, register

NEW = "a-brand-new-passphrase"


def link_token(message, path):
    m = re.search(rf"http://app\.test/{path}#token=([A-Za-z0-9_-]+)", message["text"])
    assert m, message["text"]
    return m.group(1)


def test_a_reset_link_goes_only_to_existing_accounts_with_the_same_answer_either_way(client, outbox):
    email, _ = register(client)
    a = client.post("/auth/password-reset", json={"email": email})
    b = client.post("/auth/password-reset", json={"email": "nobody-" + email})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert [m["to"] for m in outbox] == [email]
    assert "30 minutes" in outbox[0]["text"]


def test_a_reset_link_sets_a_new_password_once_and_ends_earlier_logins(client, outbox):
    email, old_token = register(client)
    client.post("/auth/password-reset", json={"email": email})
    token = link_token(outbox[0], "reset-password")
    r = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": NEW})
    assert r.status_code == 200
    assert client.get("/sessions", headers=auth(old_token)).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": NEW}).status_code == 200
    again = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": NEW + "x"})
    assert again.status_code == 400


def test_an_expired_or_unknown_reset_link_is_refused(client, outbox):
    from app.db.database import SessionLocal
    from app.db.models import AuthToken

    email, _ = register(client)
    client.post("/auth/password-reset", json={"email": email})
    token = link_token(outbox[0], "reset-password")
    db = SessionLocal()
    for row in db.query(AuthToken).all():
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    db.close()
    assert (
        client.post("/auth/password-reset/confirm", json={"token": token, "new_password": NEW}).status_code
        == 400
    )
    assert (
        client.post("/auth/password-reset/confirm", json={"token": "x" * 43, "new_password": NEW}).status_code
        == 400
    )


def test_the_raw_token_is_never_stored(client, outbox):
    from app.db.database import SessionLocal
    from app.db.models import AuthToken

    email, _ = register(client)
    client.post("/auth/password-reset", json={"email": email})
    token = link_token(outbox[0], "reset-password")
    db = SessionLocal()
    try:
        assert all(token not in (r.token_hash or "") for r in db.query(AuthToken).all())
    finally:
        db.close()


def test_a_short_new_password_is_refused(client, outbox):
    email, _ = register(client)
    client.post("/auth/password-reset", json={"email": email})
    token = link_token(outbox[0], "reset-password")
    assert (
        client.post(
            "/auth/password-reset/confirm",
            json={
                "token": token,
                "new_password": NEW[:5],
            },
        ).status_code
        == 422
    )


def test_reset_requests_are_rate_limited_per_email(client, outbox):
    email, _ = register(client)
    codes = [client.post("/auth/password-reset", json={"email": email}).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]


def test_without_an_email_provider_the_reset_says_so(client, monkeypatch, outbox):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mail_backend", "none")
    email, _ = register(client)
    r = client.post("/auth/password-reset", json={"email": email})
    assert r.status_code == 503 and "isn't available" in r.json()["detail"] and outbox == []


def test_email_verification(client, outbox):
    email, t = register(client)
    assert client.get("/auth/me", headers=auth(t)).json()["email_verified"] is False
    assert client.post("/auth/verify-email/request", headers=auth(t)).status_code == 202
    token = link_token(outbox[0], "verify-email")
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 200
    assert client.get("/auth/me", headers=auth(t)).json()["email_verified"] is True
    assert client.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_changing_the_password_ends_other_logins_but_keeps_this_one(client):
    email, t = register(client)
    other = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    r = client.post(
        "/auth/change-password", headers=auth(t), json={"current_password": PASSWORD, "new_password": NEW}
    )
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.get("/sessions", headers=auth(other)).status_code == 401
    assert client.get("/sessions", headers=auth(r.json()["access_token"])).status_code == 200


@pytest.mark.parametrize(
    "path", ["/auth/password-reset", "/auth/password-reset/confirm", "/auth/verify-email"]
)
def test_link_endpoints_need_no_login_but_validate_input(client, path):
    assert client.post(path, json={}).status_code == 422
