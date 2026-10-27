"""Consent before analysis (ADR-007): GET the current text and status, POST to accept, DELETE to
withdraw. The analysis endpoints call require_consent()."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.core.copy import CONSENT_TEXT, CONSENT_VERSION
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Consent, User

router = APIRouter(tags=["consent"])


class ConsentAccept(BaseModel):
    version: str


class ConsentRecord(BaseModel):
    version: str
    accepted_at: str | None
    withdrawn_at: str | None


class ConsentStatus(BaseModel):
    active: bool
    version: str  # the current text's version
    text: str
    accepted_at: str | None
    history: list[ConsentRecord]  # newest first


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _latest(db: DBSession, user: User) -> Consent | None:
    return db.query(Consent).filter(Consent.user_id == user.id).order_by(Consent.id.desc()).first()


def has_consent(db: DBSession, user: User) -> bool:
    c = _latest(db, user)
    return c is not None and c.version == CONSENT_VERSION and c.withdrawn_at is None


def require_consent(db: DBSession, user: User) -> None:
    if not has_consent(db, user):
        raise HTTPException(
            403,
            {
                "code": "consent_required",
                "message": "Please read and accept the consent before analysing a video.",
            },
        )


def _status(db: DBSession, user: User) -> ConsentStatus:
    rows = db.query(Consent).filter(Consent.user_id == user.id).order_by(Consent.id.desc()).all()
    active = has_consent(db, user)
    return ConsentStatus(
        active=active,
        version=CONSENT_VERSION,
        text=CONSENT_TEXT,
        accepted_at=_iso(rows[0].accepted_at) if active else None,
        history=[
            ConsentRecord(
                version=r.version, accepted_at=_iso(r.accepted_at), withdrawn_at=_iso(r.withdrawn_at)
            )
            for r in rows
        ],
    )


@router.get("/consent", response_model=ConsentStatus)
def get_consent(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    return _status(db, current_user)


@router.post("/consent", response_model=ConsentStatus, status_code=201)
def accept_consent(
    body: ConsentAccept, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
):
    if body.version != CONSENT_VERSION:
        raise HTTPException(409, "The consent text has changed. Please read the current version.")
    if not has_consent(db, current_user):
        db.add(Consent(user_id=current_user.id, version=CONSENT_VERSION))
        db.commit()
    return _status(db, current_user)


@router.delete("/consent", response_model=ConsentStatus)
def withdraw_consent(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    c = _latest(db, current_user)
    if c is not None and c.withdrawn_at is None:
        c.withdrawn_at = datetime.now(UTC)
        db.commit()
    return _status(db, current_user)
