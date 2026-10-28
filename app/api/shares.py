"""Read-only share links for one session (Plan V3 Phase 5).

The token is random (32 bytes), stored only as its SHA-256, travels in the link's fragment
(.../shared#token=...) and is posted to POST /shared, so it never appears in a URL path, a server
log or a Referer header. Links last 7 days by default (1-30), can be revoked, and die with the
session. The shared view holds the measurements only: no name, email, notes or tags.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.core import ratelimit
from app.core.config import settings
from app.core.copy import DISCLAIMER
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Session as SessionModel
from app.db.models import ShareLink, User
from app.schemas import Result

router = APIRouter(tags=["sharing"])
NOT_FOUND = "This link is invalid, has expired or was withdrawn."


class ShareCreate(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


class ShareOut(BaseModel):
    id: int
    created_at: str | None
    expires_at: str
    revoked: bool


class ShareCreated(ShareOut):
    url: str  # shown once: only the hash is kept


class SharedToken(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class SharedSession(BaseModel):
    created_at: str | None
    result: Result
    disclaimer: str


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)  # SQLite: naive, stored in UTC


def _out(s: ShareLink) -> ShareOut:
    return ShareOut(
        id=s.id,
        created_at=s.created_at.isoformat() if s.created_at else None,
        expires_at=_aware(s.expires_at).isoformat(),
        revoked=s.revoked_at is not None,
    )


def _owned_session(db: DBSession, user: User, session_id: str) -> SessionModel:
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is None or s.user_id != user.id or s.result is None:
        raise HTTPException(404, "Session not found")
    return s


@router.post("/sessions/{session_id}/shares", response_model=ShareCreated, status_code=201)
def create_share(
    session_id: str,
    body: ShareCreate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    _owned_session(db, current_user, session_id)
    raw = secrets.token_urlsafe(32)
    link = ShareLink(
        session_id=session_id,
        user_id=current_user.id,
        token_hash=_hash(raw),
        expires_at=datetime.now(UTC) + timedelta(days=body.days),
    )
    db.add(link)
    db.commit()
    return ShareCreated(**_out(link).model_dump(), url=f"{settings.frontend_url}/shared#token={raw}")


@router.get("/sessions/{session_id}/shares", response_model=list[ShareOut])
def list_shares(
    session_id: str, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
):
    _owned_session(db, current_user, session_id)
    rows = db.query(ShareLink).filter(ShareLink.session_id == session_id).order_by(ShareLink.id.desc())
    return [_out(s) for s in rows]


@router.delete("/shares/{share_id}", status_code=204)
def revoke_share(
    share_id: int, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
):
    s = db.get(ShareLink, share_id)
    if s is None or s.user_id != current_user.id:
        raise HTTPException(404, "Link not found")
    s.revoked_at = s.revoked_at or datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


@router.post("/shared", response_model=SharedSession)
def open_shared(body: SharedToken, request: Request, db: DBSession = Depends(get_db)):
    ip = ratelimit.client_ip(request)
    ratelimit.enforce((ratelimit.shared_link_opens_per_ip, ip))
    ratelimit.shared_link_opens_per_ip.hit(ip)
    link = db.query(ShareLink).filter(ShareLink.token_hash == _hash(body.token)).first()
    if link is None or link.revoked_at is not None or _aware(link.expires_at) < datetime.now(UTC):
        raise HTTPException(404, NOT_FOUND)
    s = db.get(SessionModel, link.session_id)
    if s is None or s.result is None:
        raise HTTPException(404, NOT_FOUND)
    return SharedSession(
        created_at=s.created_at.isoformat() if s.created_at else None,
        result=Result.model_validate(s.result),
        disclaimer=DISCLAIMER,
    )
