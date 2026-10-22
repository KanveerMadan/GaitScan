"""Sliding-window rate limits for authentication endpoints (F10, F12).

Client address and its trust assumption
---------------------------------------
Per-IP limits key on `client_ip()`. With TRUSTED_PROXY_HOPS=0 (default) that is the
TCP peer and all forwarding headers are ignored. With N > 0 we assume exactly N
proxies sit in front of the app and each *appends* the address it received from to
X-Forwarded-For. The entry N places from the right was written by the outermost
trusted proxy and is the real client; anything left of it was written by the client
and is never read, so a spoofed header cannot choose the bucket.

Render (assumed, not in Render's docs): client -> Cloudflare -> Render proxy -> app,
both appending, so XFF = "<client-written...>, <client>, <Cloudflare edge>" and
render.yaml sets TRUSTED_PROXY_HOPS=2. If the real chain has fewer appending proxies,
the chosen entry could be client-written (spoofable); with more, users share an
edge address. Verify after deploying (PHASE_1.md, human actions). uvicorn's own
--proxy-headers is disabled in the Dockerfile because it trusts the leftmost entry.

ponytail: in-process memory. Correct for one uvicorn worker on one instance (the
current deployment). With several workers or instances each has its own counts, so
move this to Postgres or Redis when scaling out.
"""

import threading
import time
from collections import defaultdict, deque

import structlog
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

ALL = (login_failures_per_email, login_attempts_per_ip, registrations_per_ip)


def client_ip(request: Request) -> str:
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


# shortcut: temporary diagnostic, remove after the client-IP fix (shows Render's real header chain).
PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "true-client-ip", "cf-connecting-ip", "forwarded")


def log_proxy_headers(request: Request) -> None:
    if settings.log_proxy_headers:
        structlog.get_logger("gaitscan").info(
            "login proxy_headers",
            peer=request.client.host if request.client else None,
            **{h.replace("-", "_"): request.headers.get(h) for h in PROXY_HEADERS},
        )


def enforce(*checks: tuple[SlidingWindowLimiter, str]) -> None:
    wait = max(limiter.retry_after(key) for limiter, key in checks)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {max(1, round(wait / 60))} minute(s).",
            headers={"Retry-After": str(wait)},
        )
