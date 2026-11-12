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


def test_a_password_account_is_not_taken_over_by_google_sign_in(client, google):
    """2026-11-12 review: sign-up checks no email address (there is no email channel), so anyone can
    make a password account with someone else's address. Linking it when that person later signs in
    with Google would put them in an account whose password the other person knows (account
    pre-hijacking). An account whose address nobody has verified is never linked."""
    email, _ = register(client)
    r = client.post("/auth/google", json={"credential": f"good:{email}"})
    assert r.status_code == 409 and "password" in r.json()["detail"]
    assert "access_token" not in r.json()
    # Nothing changed for the account: its password works and its address is still unverified.
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    assert (
        client.get("/auth/me", headers=auth(login.json()["access_token"])).json()["email_verified"] is False
    )


def test_a_google_account_signs_in_again_to_the_same_account(client, google):
    first = client.post("/auth/google", json={"credential": "good:again@example.com"}).json()
    again = client.post("/auth/google", json={"credential": "good:again@example.com"})
    assert again.status_code == 200 and "recovery_codes" not in again.json()
    me = lambda body: client.get("/auth/me", headers=auth(body["access_token"])).json()  # noqa: E731
    assert me(first)["id"] == me(again.json())["id"]


def test_capitals_in_an_existing_address_dont_make_a_second_account(client, google):
    """Sign-up keeps the capitals in the part before the @; Google sends the address in lower case."""
    register(client, email="Ana.Caps@example.com")
    r = client.post("/auth/google", json={"credential": "good:ana.caps@example.com"})
    assert r.status_code == 409  # the existing (password) account, not a new one


def test_a_new_google_account_consents_before_its_first_analysis(client, google, monkeypatch):
    from conftest import fake_video

    fake_video(monkeypatch)
    token = client.post("/auth/google", json={"credential": "good:first-use@example.com"}).json()[
        "access_token"
    ]
    r = client.post("/analyses", headers=auth(token), files={"video": ("walk.mp4", b"x" * 64, "video/mp4")})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "consent_required"


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


@pytest.fixture
def signer(monkeypatch):
    """A local RSA key standing in for Google's: tokens are signed with it, and the check is given its
    public half as the key Google published (no network)."""
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class Keys:
        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.setattr(google_auth, "_jwks", Keys())
    now = int(time.time())
    good = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "g-123",
        "email": "real@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 600,
    }

    def sign(**changes):
        claims = {k: v for k, v in {**good, **changes}.items() if v is not None}
        return jwt.encode(claims, key, algorithm="RS256")

    return sign


def test_the_real_check_accepts_a_token_signed_for_our_client_id(signer):
    assert google_auth.check_id_token(signer(), CLIENT_ID)["email"] == "real@example.com"


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "someone-elses-client.apps.googleusercontent.com"},
        {"iss": "https://evil.example.com"},
        {"exp": 1_000_000},  # long expired
        {"exp": None},  # no expiry at all
        {"sub": None},  # no Google account id
    ],
)
def test_the_real_check_refuses_tokens_that_arent_for_us_or_are_incomplete(signer, changes):
    with pytest.raises(google_auth.InvalidGoogleToken):
        google_auth.check_id_token(signer(**changes), CLIENT_ID)
