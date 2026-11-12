"""Email addresses are compared in lower case everywhere (2026-11-12): sign-up kept the capitals as
typed, sign-in matched them exactly, and recovery lowercased first, so an account made as
Name@example.com could never be recovered with a code. Migration 0014 lowercases stored addresses
and stops, changing nothing, if two accounts differ only by capitals."""

import sqlalchemy as sa
from conftest import PASSWORD, auth, migrate


def sign_up(client, email):
    return client.post("/auth/register", json={"email": email, "password": PASSWORD})


def test_an_address_is_stored_in_lower_case_and_signs_in_however_it_is_typed(client):
    r = sign_up(client, "Ana.Caps@Example.com")
    assert r.status_code == 201, r.text
    assert (
        client.get("/auth/me", headers=auth(r.json()["access_token"])).json()["email"]
        == "ana.caps@example.com"
    )
    for typed in ("ana.caps@example.com", "ANA.CAPS@EXAMPLE.COM", "Ana.Caps@Example.com"):
        assert client.post("/auth/login", json={"email": typed, "password": PASSWORD}).status_code == 200, (
            typed
        )


def test_the_same_address_in_other_capitals_is_the_same_account(client):
    assert sign_up(client, "twice@example.com").status_code == 201
    assert sign_up(client, "Twice@Example.com").status_code == 409


def test_an_account_made_with_capitals_can_be_recovered_with_a_code(client):
    codes = sign_up(client, "Rec.Caps@Example.com").json()["recovery_codes"]
    for code, typed in ((codes[0], "rec.caps@example.com"), (codes[1], "REC.CAPS@EXAMPLE.COM")):
        r = client.post(
            "/auth/recover", json={"email": typed, "code": code, "new_password": PASSWORD + "-new"}
        )
        assert r.status_code == 200, (typed, r.text)


def test_a_token_issued_with_capitals_still_works_after_addresses_are_lowercased(client):
    """Tokens from before the migration carry the address as it was typed; nobody is signed out."""
    from app.core.security import create_access_token

    sign_up(client, "token.caps@example.com")
    old = create_access_token({"sub": "Token.Caps@Example.com", "role": "patient"})
    r = client.get("/auth/me", headers=auth(old))
    assert r.status_code == 200 and r.json()["email"] == "token.caps@example.com"


def _users(url, emails):
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for e in emails:
            conn.execute(
                sa.text("INSERT INTO users (email, hashed_password, role) VALUES (:e, 'x', 'patient')"),
                {"e": e},
            )
    engine.dispose()


def _emails(url):
    engine = sa.create_engine(url)
    with engine.connect() as conn:
        out = sorted(r[0] for r in conn.execute(sa.text("SELECT email FROM users")))
    engine.dispose()
    return out


def test_the_migration_lowercases_stored_addresses(tmp_path):
    url = f"sqlite:///{tmp_path}/case.db"
    migrate(url, "0013")
    _users(url, ["Mixed.Case@Example.com", "already@lower.com"])
    migrate(url)
    assert _emails(url) == ["already@lower.com", "mixed.case@example.com"]


def test_the_migration_stops_and_changes_nothing_when_two_accounts_differ_only_by_capitals(tmp_path):
    import pytest

    url = f"sqlite:///{tmp_path}/clash.db"
    migrate(url, "0013")
    _users(url, ["Same@Example.com", "same@example.com", "Other@Example.com"])
    with pytest.raises(RuntimeError) as e:
        migrate(url)
    message = str(e.value)
    assert "differ only by capitals" in message and "user ids" in message
    assert "same@example.com" not in message.lower()  # ids only: no addresses in deploy logs
    assert _emails(url) == ["Other@Example.com", "Same@Example.com", "same@example.com"]
