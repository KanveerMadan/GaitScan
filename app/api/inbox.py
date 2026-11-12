"""Professional inbox (Plan V3 Phase 9): comments on a session between its owner and a linked
clinician, and a clinician's inbox of their linked patients' sessions, marking what's new since they
last looked. Access follows the session: owner or linked clinician; anyone else gets a 404."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.api.sessions import get_visible_session
from app.core.security import get_current_user, require_clinician
from app.db.database import get_db
from app.db.models import ClinicianPatient, SessionComment, User
from app.db.models import Session as SessionModel

router = APIRouter(tags=["inbox"])

INBOX_DAYS = 90
INBOX_LIMIT = 50


def _utc(dt: datetime | None) -> datetime | None:
    """Stored times may come back naive (SQLite, and sessions are stored in naive UTC)."""
    return None if dt is None else dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    body: str
    author_role: str
    author_name: str | None
    mine: bool
    created_at: str | None


def _out(c: SessionComment, author: User, me: User) -> CommentOut:
    created = _utc(c.created_at)
    return CommentOut(
        id=c.id,
        body=c.body,
        author_role=author.role,
        author_name=author.full_name,
        mine=author.id == me.id,
        created_at=created.isoformat() if created else None,
    )


@router.get("/sessions/{session_id}/comments", response_model=list[CommentOut])
def list_comments(
    session_id: str, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> list[CommentOut]:
    get_visible_session(db, current_user, session_id)
    rows = (
        db.query(SessionComment, User)
        .join(User, User.id == SessionComment.author_id)
        .filter(SessionComment.session_id == session_id)
        .order_by(SessionComment.id)
        .all()
    )
    return [_out(c, author, current_user) for c, author in rows]


@router.post("/sessions/{session_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    session_id: str,
    body: CommentIn,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> CommentOut:
    get_visible_session(db, current_user, session_id)
    # Stamped here, to the microsecond: the database default has whole seconds, which can't be compared
    # with when the inbox was last looked at.
    c = SessionComment(
        session_id=session_id,
        author_id=current_user.id,
        body=body.body.strip() or body.body,
        created_at=datetime.now(UTC),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c, current_user, current_user)


class InboxItem(BaseModel):
    session_id: str
    patient_id: int
    patient_name: str | None
    created_at: str | None
    cadence: float | None
    comments: int
    last_comment_at: str | None
    new: bool


class Inbox(BaseModel):
    items: list[InboxItem]
    seen_at: str | None


@router.get("/clinician/inbox", response_model=Inbox)
def inbox(clinician: User = Depends(require_clinician), db: DBSession = Depends(get_db)) -> Inbox:
    seen = _utc(clinician.inbox_seen_at)
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=INBOX_DAYS)
    rows = (
        db.query(SessionModel, User)
        .join(User, User.id == SessionModel.user_id)
        .join(ClinicianPatient, ClinicianPatient.patient_id == SessionModel.user_id)
        .filter(
            ClinicianPatient.clinician_id == clinician.id,
            SessionModel.profile_id.is_(None),  # the patient's own sessions, not other people on the account
            SessionModel.created_at >= since,
        )
        .order_by(SessionModel.created_at.desc())
        .limit(INBOX_LIMIT)
        .all()
    )
    ids = [s.id for s, _ in rows]
    counts = dict(
        db.query(SessionComment.session_id, func.count(SessionComment.id))
        .filter(SessionComment.session_id.in_(ids))
        .group_by(SessionComment.session_id)
        .all()
    )
    latest_from_patient: dict[str, datetime] = {}
    latest_any: dict[str, datetime] = {}
    for c, author in (
        db.query(SessionComment, User)
        .join(User, User.id == SessionComment.author_id)
        .filter(SessionComment.session_id.in_(ids))
        .all()
    ):
        t = _utc(c.created_at)
        if t is None:
            continue
        latest_any[c.session_id] = max(t, latest_any.get(c.session_id, t))
        if author.id != clinician.id:
            latest_from_patient[c.session_id] = max(t, latest_from_patient.get(c.session_id, t))
    items = []
    for s, patient in rows:
        created = _utc(s.created_at)
        reply = latest_from_patient.get(s.id)
        new = seen is None or (created is not None and created > seen) or (reply is not None and reply > seen)
        cadence = ((s.result or {}).get("metrics") or {}).get("cadence") or {}
        items.append(
            InboxItem(
                session_id=s.id,
                patient_id=patient.id,
                patient_name=patient.full_name or s.patient_name,
                created_at=created.isoformat() if created else None,
                cadence=cadence.get("value"),
                comments=int(counts.get(s.id, 0)),
                last_comment_at=latest_any[s.id].isoformat() if s.id in latest_any else None,
                new=new,
            )
        )
    return Inbox(items=items, seen_at=seen.isoformat() if seen else None)


@router.post("/clinician/inbox/seen", status_code=204)
def mark_seen(clinician: User = Depends(require_clinician), db: DBSession = Depends(get_db)) -> Response:
    clinician.inbox_seen_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
