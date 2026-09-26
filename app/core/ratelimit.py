"""Sliding-window rate limits for authentication endpoints (F10, F12).

ponytail: in-process memory. Correct for one uvicorn worker on one instance (the
current deployment). With several workers or instances each has its own counts, so
move this to Postgres or Redis when scaling out.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


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
    # Behind Render's proxy this is only the real client when uvicorn runs with
    # --proxy-headers (see Dockerfile); X-Forwarded-For can be spoofed, so the
    # per-email limit is the control that protects an individual account.
    return request.client.host if request.client else "unknown"


def enforce(*checks: tuple[SlidingWindowLimiter, str]) -> None:
    wait = max(limiter.retry_after(key) for limiter, key in checks)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {max(1, round(wait / 60))} minute(s).",
            headers={"Retry-After": str(wait)},
        )
