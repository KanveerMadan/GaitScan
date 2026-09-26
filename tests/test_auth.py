"""F01, F03, F04, F08: token signing, roles, password handling."""

import os
import time

import jwt

from conftest import PASSWORD, auth, register


def test_tokens_are_signed_with_the_env_secret(client):
    email, token = register(client)
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["sub"] == email


def test_token_signed_with_other_secret_is_rejected(client):
    email, _ = register(client)
    forged = jwt.encode({"sub": email, "exp": int(time.time()) + 600}, "x" * 48, algorithm="HS256")
    assert client.get("/auth/me", headers=auth(forged)).status_code == 401


def test_register_cannot_self_assign_clinician(client):
    r = client.post(
        "/auth/register", json={"email": "wannabe@example.com", "password": PASSWORD, "role": "clinician"}
    )
    assert r.status_code == 201
    assert r.json()["role"] == "patient"
    me = client.get("/auth/me", headers=auth(r.json()["access_token"])).json()
    assert me["role"] == "patient"


def test_password_is_never_printed(client, capsys):
    register(client, password="very-distinctive-password-123")
    out = capsys.readouterr()
    assert "very-distinctive-password-123" not in out.out + out.err


def test_access_token_lifetime_at_most_one_day(client):
    _, token = register(client)
    claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert claims["exp"] - time.time() <= 24 * 3600
