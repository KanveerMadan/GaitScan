"""Structured JSON logging with PII/secret redaction and per-request IDs (F41).

Both structlog loggers and stdlib `logging` calls (uvicorn, our 'gaitscan' logger)
are rendered through the same processor chain, so redaction applies everywhere.
Request bodies are never logged.
"""
import logging
import re
import sys
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

REDACT_KEYS = {"password", "current_password", "new_password", "token", "access_token",
               "authorization", "jwt_secret", "email", "cookie"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def redact(_logger, _method, event_dict):
    for key in list(event_dict):
        if key.lower() in REDACT_KEYS:
            event_dict[key] = "[redacted]"
        elif isinstance(event_dict[key], str):
            event_dict[key] = EMAIL.sub("[email]", event_dict[key])
    return event_dict


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever sys.stderr is at emit time (not the object captured at import)."""

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value):
        pass


def configure_logging() -> None:
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.format_exc_info,  # before redact, so tracebacks are redacted too
        redact,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    handler = _StderrHandler()
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer()],
    ))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = name != "uvicorn.access"  # we log requests ourselves


class RequestLogMiddleware(BaseHTTPMiddleware):
    """One access line per request, tagged with an X-Request-ID (accepted from the proxy or generated)."""

    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.get_logger("gaitscan.access").info(
                "request", method=request.method, path=request.url.path, status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 1))
            structlog.contextvars.clear_contextvars()
