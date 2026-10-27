"""Sliding-window rate limits for authentication endpoints (F10, F12).

Client address and its trust assumption
---------------------------------------
Per-IP limits key on `client_ip()`:
1. CLIENT_IP_HEADER set (Render: true-client-ip): that header, if it holds one valid IP.
   Only safe when the edge proxy always overwrites it, so a client can't choose it.
2. Otherwise TRUSTED_PROXY_HOPS=N > 0: we assume exactly N proxies sit in front of the
   app and each *appends* the address it received from to X-Forwarded-For. The entry N
   places from the right is the real client; anything left of it was written by the
   client and is never read, so a spoofed header cannot choose the bucket.
3. Otherwise (0, the default) the TCP peer; forwarding headers are ignored.

Render, observed with a temporary header log: the peer is 127.0.0.1, XFF arrives as
"<client-written...>, <client>, <Cloudflare edge>, <10.x Render internal>" with the last
two varying per request (so hops=1 or 2 gave every request its own bucket; hops=3 is
the client), and True-Client-IP / CF-Connecting-IP hold the client even when XFF is
spoofed. uvicorn's own --proxy-headers is disabled in the Dockerfile because it trusts
the leftmost entry.

ponytail: in-process memory. Correct for one uvicorn worker on one instance (the
current deployment). With several workers or instances each has its own counts, so
move this to Postgres or Redis when scaling out.
"""

import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: int):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits[key]
        while q and q[0] <= now - self.window_s:
            q.popleft()
        return q

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again (0 = allowed now). Does not record a hit."""
        now = time.monotonic()
        with self._lock:
            q = self._prune(key, now)
            return int(q[0] + self.window_s - now) + 1 if len(q) >= self.limit else 0

    def hit(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Failed logins per email (counts unknown emails too, so a 429 reveals nothing).
login_failures_per_email = SlidingWindowLimiter(limit=5, window_s=15 * 60)
# All login attempts per client address.
login_attempts_per_ip = SlidingWindowLimiter(limit=20, window_s=5 * 60)
# Registrations per client address (slows email enumeration via sign-up).
registrations_per_ip = SlidingWindowLimiter(limit=10, window_s=60 * 60)
# Password-reset emails: a few per address and per client an hour (no inbox flooding, no probing).
reset_requests_per_email = SlidingWindowLimiter(limit=3, window_s=60 * 60)
reset_requests_per_ip = SlidingWindowLimiter(limit=10, window_s=60 * 60)
# Invite codes (6 characters): a person mistypes a few times; guessing needs millions of tries (F10).
invite_joins_per_ip = SlidingWindowLimiter(limit=10, window_s=15 * 60)
# Opening shared links: generous for a person, a wall for token guessing.
shared_link_opens_per_ip = SlidingWindowLimiter(limit=60, window_s=60 * 60)

ALL = (
    login_failures_per_email,
    login_attempts_per_ip,
    registrations_per_ip,
    reset_requests_per_email,
    reset_requests_per_ip,
    shared_link_opens_per_ip,
    invite_joins_per_ip,
)


def client_ip(request: Request) -> str:
    if settings.client_ip_header:
        try:
            return str(ipaddress.ip_address(request.headers.get(settings.client_ip_header, "").strip()))
        except ValueError:
            pass  # missing or not a single IP: fall back to the X-Forwarded-For chain
    peer = request.client.host if request.client else "unknown"
    hops = settings.trusted_proxy_hops
    if hops <= 0:
        return peer
    chain = [a.strip() for a in request.headers.get("x-forwarded-for", "").split(",")]
    chain = [a for a in chain if a]
    if not chain:
        return peer
    # Shorter than `hops`: no client-written entries can be present, so the leftmost is trusted.
    return chain[-hops] if len(chain) >= hops else chain[0]


def enforce(*checks: tuple[SlidingWindowLimiter, str]) -> None:
    wait = max(limiter.retry_after(key) for limiter, key in checks)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {max(1, round(wait / 60))} minute(s).",
            headers={"Retry-After": str(wait)},
        )
