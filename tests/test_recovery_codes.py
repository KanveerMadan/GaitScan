"""Recovery codes (Plan V3 Phase 9): password recovery without email. Eight single-use codes are shown
once (at sign-up, or when the user makes a new set); a code plus the account's email sets a new
password and ends every earlier login. Only their SHA-256 is stored."""

import re
import uuid

from conftest import PASSWORD, auth, register

NEW = "another-long-passphrase"
CODE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}$")  # Crockford base32, 80 bits


def signup(client):
    r = client.post(
        "/auth/register", json={"email": f"rc-{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_sign_up_shows_eight_codes_once(client):
    body = signup(client)
    codes = body["recovery_codes"]
    assert len(codes) == 8 and len(set(codes)) == 8 and all(CODE.match(c) for c in codes)
    me = client.get("/auth/me", headers=auth(body["access_token"])).json()
    assert me["recovery_codes_left"] == 8
    assert (
        "recovery_codes"
        not in client.post("/auth/login", json={"email": me["email"], "password": PASSWORD}).json()
    )


def test_a_code_sets_a_new_password_once_and_ends_earlier_logins(client):
    body = signup(client)
    email = client.get("/auth/me", headers=auth(body["access_token"])).json()["email"]
    code = body["recovery_codes"][3]
    r = client.post("/auth/recover", json={"email": email, "code": code.lower(), "new_password": NEW})
    assert r.status_code == 200, r.text
    assert client.get("/auth/me", headers=auth(body["access_token"])).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    token = client.post("/auth/login", json={"email": email, "password": NEW}).json()["access_token"]
    assert client.get("/auth/me", headers=auth(token)).json()["recovery_codes_left"] == 7
    again = client.post("/auth/recover", json={"email": email, "code": code, "new_password": NEW + "x"})
    assert again.status_code == 400


def test_a_wrong_code_or_unknown_email_gets_the_same_answer(client):
    body = signup(client)
    email = client.get("/auth/me", headers=auth(body["access_token"])).json()["email"]
    other = signup(client)["recovery_codes"][0]  # a real code, but another account's
    a = client.post("/auth/recover", json={"email": email, "code": other, "new_password": NEW})
    b = client.post("/auth/recover", json={"email": "nobody-" + email, "code": other, "new_password": NEW})
    assert a.status_code == b.status_code == 400 and a.json() == b.json()


def test_codes_are_stored_only_as_hashes(client):
    from app.db.database import SessionLocal
    from app.db.models import RecoveryCode

    codes = signup(client)["recovery_codes"]
    db = SessionLocal()
    try:
        stored = [r.code_hash for r in db.query(RecoveryCode).all()]
    finally:
        db.close()
    assert stored and not any(c.replace("-", "") in h or c in h for c in codes for h in stored)


def test_a_new_set_needs_the_password_and_replaces_the_old_one(client):
    body = signup(client)
    token, old = body["access_token"], body["recovery_codes"]
    me = client.get("/auth/me", headers=auth(token)).json()
    assert (
        client.post(
            "/auth/recovery-codes", headers=auth(token), json={"password": "wrong-password-1"}
        ).status_code
        == 401
    )
    r = client.post("/auth/recovery-codes", headers=auth(token), json={"password": PASSWORD})
    assert r.status_code == 201 and len(r.json()["recovery_codes"]) == 8
    stale = client.post("/auth/recover", json={"email": me["email"], "code": old[0], "new_password": NEW})
    assert stale.status_code == 400
    fresh = client.post(
        "/auth/recover",
        json={"email": me["email"], "code": r.json()["recovery_codes"][0], "new_password": NEW},
    )
    assert fresh.status_code == 200


def test_accounts_from_before_recovery_codes_have_none_until_they_make_a_set(client):
    _, token = register(client)  # the helper's account, as an existing user's would be
    from app.db.database import SessionLocal
    from app.db.models import RecoveryCode

    db = SessionLocal()
    try:
        db.query(RecoveryCode).delete()
        db.commit()
    finally:
        db.close()
    assert client.get("/auth/me", headers=auth(token)).json()["recovery_codes_left"] == 0


def test_guessing_codes_is_rate_limited_per_email(client):
    body = signup(client)
    email = client.get("/auth/me", headers=auth(body["access_token"])).json()["email"]
    codes = [
        client.post(
            "/auth/recover", json={"email": email, "code": "AAAA-AAAA-AAAA-AAAA", "new_password": NEW}
        ).status_code
        for _ in range(6)
    ]
    assert codes == [400] * 5 + [429]


def test_a_short_new_password_is_refused(client):
    body = signup(client)
    email = client.get("/auth/me", headers=auth(body["access_token"])).json()["email"]
    r = client.post(
        "/auth/recover", json={"email": email, "code": body["recovery_codes"][0], "new_password": NEW[:5]}
    )
    assert r.status_code == 422


def test_recovery_works_with_no_email_provider(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mail_backend", "none")
    body = signup(client)
    email = client.get("/auth/me", headers=auth(body["access_token"])).json()["email"]
    r = client.post(
        "/auth/recover", json={"email": email, "code": body["recovery_codes"][0], "new_password": NEW}
    )
    assert r.status_code == 200
