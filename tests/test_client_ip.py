"""Client address used for per-IP rate limits (F10).

Assumed chain on Render (TRUSTED_PROXY_HOPS=2): client -> Cloudflare (appends client)
-> Render proxy (appends Cloudflare edge) -> app, so X-Forwarded-For arrives as
"<anything the client wrote>, <client>, <edge>".
"""

import pytest
from starlette.requests import Request


def req(xff=None, peer="10.0.0.5"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.fixture
def hops(monkeypatch):
    from app.core.config import settings

    def set_hops(n):
        monkeypatch.setattr(settings, "trusted_proxy_hops", n)

    return set_hops


def test_default_ignores_forwarded_headers(hops):
    from app.core.ratelimit import client_ip

    hops(0)
    assert client_ip(req("1.2.3.4", peer="9.9.9.9")) == "9.9.9.9"


def test_users_behind_the_proxy_get_separate_buckets(hops):
    from app.core.ratelimit import client_ip

    hops(2)
    a = client_ip(req("203.0.113.1, 172.70.0.1"))
    b = client_ip(req("198.51.100.7, 172.70.0.1"))
    assert (a, b) == ("203.0.113.1", "198.51.100.7")


def test_client_supplied_forwarded_for_cannot_choose_the_bucket(hops):
    from app.core.ratelimit import client_ip

    hops(2)
    for spoof in ("1.1.1.1", "1.1.1.1, 2.2.2.2", "garbage, , 3.3.3.3"):
        assert client_ip(req(f"{spoof}, 203.0.113.1, 172.70.0.1")) == "203.0.113.1"


def test_short_or_missing_header_falls_back_without_trusting_client_input(hops):
    from app.core.ratelimit import client_ip

    hops(2)
    # Fewer entries than trusted hops: every entry was written by a trusted proxy.
    assert client_ip(req("203.0.113.1")) == "203.0.113.1"
    assert client_ip(req(None, peer="10.0.0.5")) == "10.0.0.5"
    assert client_ip(req("", peer="10.0.0.5")) == "10.0.0.5"


def test_spoofed_header_does_not_bypass_login_limit(client, hops):
    """End to end: rotating the leftmost X-Forwarded-For still hits the per-IP limit."""
    hops(2)
    codes = [
        client.post(
            "/auth/login",
            json={"email": f"nobody{i}@example.com", "password": "wrong-password-xyz"},
            headers={"X-Forwarded-For": f"10.9.{i}.1, 203.0.113.9, 172.70.0.1"},
        ).status_code
        for i in range(25)
    ]
    assert codes[:20] == [401] * 20 and 429 in codes[20:]
    other = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-xyz"},
        headers={"X-Forwarded-For": "198.51.100.7, 172.70.0.1"},
    )
    assert other.status_code == 401  # a different real client is unaffected


@pytest.mark.parametrize("enabled", [False, True])
def test_login_logs_proxy_headers_only_when_enabled(client, capfd, monkeypatch, enabled):
    from app.core.config import settings

    monkeypatch.setattr(settings, "log_proxy_headers", enabled, raising=False)
    capfd.readouterr()
    client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-xyz"},
        headers={
            "X-Forwarded-For": "10.9.1.1, 203.0.113.9",
            "X-Real-IP": "203.0.113.8",
            "True-Client-IP": "203.0.113.7",
            "CF-Connecting-IP": "203.0.113.6",
            "Forwarded": "for=203.0.113.5",
        },
    )
    err = capfd.readouterr().err
    logged = [
        v in err
        for v in ("10.9.1.1, 203.0.113.9", "203.0.113.8", "203.0.113.7", "203.0.113.6", "for=203.0.113.5")
    ]
    assert logged == [enabled] * 5
    assert ("proxy_headers" in err) is enabled
