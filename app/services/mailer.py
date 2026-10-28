"""Sending email (Plan V3 Phase 5). No provider is integrated yet: choosing one needs an account and
an API key (a decision for the owner). Until then:
- "console" (dev and tests): messages are kept in OUTBOX and their subject logged;
- "none" (production default): send() raises MailUnavailable, and callers answer 503 with a reason.
A provider backend implements the same send(to, subject, text)."""

import logging

from app.core.config import settings

log = logging.getLogger("gaitscan")
OUTBOX: list[dict[str, str]] = []  # console backend only


class MailUnavailable(RuntimeError):
    """No email provider is configured."""


def available() -> bool:
    return settings.mail_backend == "console"


def send(to: str, subject: str, text: str) -> None:
    if settings.mail_backend != "console":
        raise MailUnavailable(settings.mail_backend)
    OUTBOX.append({"to": to, "subject": subject, "text": text})
    log.info("email (console) subject=%r", subject)  # never the address or the body (links hold tokens)
