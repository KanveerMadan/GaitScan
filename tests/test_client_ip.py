"""Client address used for per-IP rate limits (F10).

Observed on Render (LOG_PROXY_HEADERS diagnostic): the TCP peer is 127.0.0.1 and
X-Forwarded-For arrives as "<anything the client wrote>, <client>, <Cloudflare edge>, <10.x
Render internal>", the last two varying per request; True-Client-IP and CF-Connecting-IP are
the client even when X-Forwarded-For is spoofed. R below is 203.0.113.7.
"""

import pytest
from starlette.requests import Request


def req(xff=None, peer="10.0.0.5", **extra):
    """`extra` header names use underscores: true_client_ip="..." -> True-Client-IP."""
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    headers += [(k.replace("_", "-").encode(), v.encode()) for k, v in extra.items()]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


R = "203.0.113.7"
# The exact shapes seen on Render; edge and internal addresses differ per request.
PLAIN = f"{R}, 172.70.1.10, 10.201.3.4"
SPOOFED = f"10.9.1.1,{R}, 172.70.2.20, 10.201.5.6"
PLAIN_LATER = f"{R}, 162.158.9.9, 10.201.7.8"


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


@pytest.fixture
def ip_header(monkeypatch):
    from app.core.config import settings

    def set_header(name):
        monkeypatch.setattr(settings, "client_ip_header", name, raising=False)

    return set_header


def test_client_ip_header_gives_the_real_client_for_render_chains(hops, ip_header):
    from app.core.ratelimit import client_ip

    hops(2)
    ip_header("true-client-ip")
    for xff in (PLAIN, SPOOFED, PLAIN_LATER):
        assert client_ip(req(xff, peer="127.0.0.1", true_client_ip=R)) == R


@pytest.mark.parametrize("value", [None, "", "not-an-ip", "203.0.113.7, 10.9.1.1"])
def test_missing_or_invalid_client_ip_header_falls_back_to_hops(hops, ip_header, value):
    from app.core.ratelimit import client_ip

    hops(3)
    ip_header("true-client-ip")
    extra = {} if value is None else {"true_client_ip": value}
    assert client_ip(req(SPOOFED, peer="127.0.0.1", **extra)) == R


def test_three_hops_picks_the_client_from_render_chains(hops):
    from app.core.ratelimit import client_ip

    hops(3)
    assert client_ip(req(PLAIN, peer="127.0.0.1")) == R
    assert client_ip(req(SPOOFED, peer="127.0.0.1")) == R  # not 10.9.1.1
    assert client_ip(req(PLAIN, peer="127.0.0.1")) == client_ip(req(PLAIN_LATER, peer="127.0.0.1"))


def test_render_spoofing_does_not_bypass_login_limit_and_users_stay_separate(client, hops, ip_header):
    """End to end with the production setting: rotating X-Forwarded-For and varying edges, one bucket."""
    hops(2)
    ip_header("true-client-ip")
    codes = [
        client.post(
            "/auth/login",
            json={"email": f"nobody{i}@example.com", "password": "wrong-password-xyz"},
            headers={"X-Forwarded-For": f"10.9.{i}.1,{R}, 172.70.{i}.20, 10.201.{i}.6", "True-Client-IP": R},
        ).status_code
        for i in range(22)
    ]
    assert codes[:20] == [401] * 20 and codes[20:] == [429, 429]
    other = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password-xyz"},
        headers={
            "X-Forwarded-For": "198.51.100.7, 172.70.1.10, 10.201.3.4",
            "True-Client-IP": "198.51.100.7",
        },
    )
    assert other.status_code == 401  # a different real client is unaffected
