"""Sign in with Google (Plan V3 Phase 9): off until GOOGLE_CLIENT_ID is set. The app sends Google's ID
token; the API checks it (signature against Google's keys, issuer, audience = our client ID, expiry)
and links to an existing account only when Google says the email address is verified."""

import pytest
from conftest import PASSWORD, auth, register

from app.api import google_auth

CLIENT_ID = "123-test.apps.googleusercontent.com"


@pytest.fixture
def google(monkeypatch):
    """Google configured, with the token check replaced: a token 'good:<email>' is valid."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_client_id", CLIENT_ID)

    def check(token: str, client_id: str) -> dict[str, object]:
        assert client_id == CLIENT_ID
        kind, _, email = token.partition(":")
        if kind == "good":
            return {"email": email, "email_verified": True, "name": "Ana Google", "sub": "g-1"}
        if kind == "unverified":
            return {"email": email, "email_verified": False, "sub": "g-2"}
        raise google_auth.InvalidGoogleToken("bad token")

    monkeypatch.setattr(google_auth, "check_id_token", check)


def test_without_a_client_id_google_sign_in_is_off(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "google_client_id", "")
    r = client.post("/auth/google", json={"credential": "x" * 40})
    assert r.status_code == 503 and "isn't set up" in r.json()["detail"]


def test_a_new_google_user_gets_an_account_and_recovery_codes(client, google):
    r = client.post("/auth/google", json={"credential": "good:new-google@example.com"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "patient" and body["full_name"] == "Ana Google"
    assert len(body["recovery_codes"]) == 8
    me = client.get("/auth/me", headers=auth(body["access_token"])).json()
    assert me["email"] == "new-google@example.com" and me["email_verified"] is True


def test_an_existing_account_is_linked_when_google_verified_the_email(client, google):
    email, _ = register(client)
    r = client.post("/auth/google", json={"credential": f"good:{email}"})
    assert r.status_code == 200 and "recovery_codes" not in r.json()
    assert client.get("/auth/me", headers=auth(r.json()["access_token"])).json()["email"] == email
    # The password still works.
    assert client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200


def test_an_unverified_google_email_is_refused(client, google):
    email, _ = register(client)
    r = client.post("/auth/google", json={"credential": f"unverified:{email}"})
    assert r.status_code == 400 and "verified" in r.json()["detail"]


def test_an_invalid_token_is_refused(client, google):
    assert client.post("/auth/google", json={"credential": "forged:" + "x" * 30}).status_code == 401


def test_google_sign_in_is_rate_limited_per_client(client, google):
    codes = [
        client.post("/auth/google", json={"credential": "forged:" + "x" * 30}).status_code for _ in range(21)
    ]
    assert codes[:20] == [401] * 20 and codes[20] == 429


def test_the_real_check_refuses_a_token_not_signed_by_google():
    """No network: a token that isn't a JWT fails before any key is fetched."""
    with pytest.raises(google_auth.InvalidGoogleToken):
        google_auth.check_id_token("not-a-jwt", CLIENT_ID)
