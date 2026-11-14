"""Session history, session detail and PDF report endpoints (owner or linked clinician only).

Legacy sessions (analysed before Plan V3) are listed with `legacy: true` and no measurements; their
old values stay in session_archive and are never served as measurements or mixed into trends.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session as DBSession

from app.api.profiles import owned_profile
from app.api.settings import settings_of
from app.core.copy import DISCLAIMER, LEGACY_NOTE
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import ClinicianPatient, User
from app.db.models import Session as SessionModel
from app.schemas import Result, SessionDetail, SessionLabels, SessionOut
from app.services.gait_profile import person_for_session, present
from app.services.report_pdf import build_pdf, build_report
from app.services.trends import sessions_of, trend_points

router = APIRouter(tags=["sessions"])


def get_visible_session(db: DBSession, user: User, session_id: str) -> SessionModel:
    """Return the session if `user` owns it or is a clinician linked to its owner.
    Anything else is a 404, so callers can't probe which IDs exist."""
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is not None and s.user_id is not None:
        if s.user_id == user.id:
            return s
        if (
            user.role == "clinician"
            and s.profile_id is None  # another adult on the account is not the clinician's patient
            and db.query(ClinicianPatient)
            .filter(
                ClinicianPatient.clinician_id == user.id,
                ClinicianPatient.patient_id == s.user_id,
            )
            .first()
        ):
            return s
    raise HTTPException(404, "Session not found")


def session_out(s: SessionModel) -> SessionOut:
    legacy = s.legacy or s.result is None
    return SessionOut(
        id=s.id,
        patient_name=s.patient_name,
        created_at=s.created_at.isoformat() if s.created_at else None,
        pipeline_version=s.pipeline_version,
        legacy=legacy,
        result=None if legacy else Result.model_validate(present(s.result, person_for_session(s))),
        note=LEGACY_NOTE if legacy else None,
        notes=s.notes,
        tags=list(s.tags or []),
        profile_id=s.profile_id,
    )


@router.get("/report/{job_id}")
def get_report(
    job_id: str,
    lang: Literal["en", "hi"] | None = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> Response:
    s = get_visible_session(db, current_user, job_id)
    if s.legacy or s.result is None:
        raise HTTPException(410, LEGACY_NOTE)
    # Built from the stored result every time: deterministic, nothing kept on disk (F15).
    if s.result.get("gait_profile"):
        # The full report (Phase 11): in the language asked for, else the reader's own setting.
        # Age, sex, session number, progress and the goal are the measured person's, as on their
        # result page; a linked clinician sees what the patient sees.
        owner = db.get(User, s.user_id)
        everyone = [x.id for x in sessions_of(db, s.user_id, s.profile_id)]
        goal = settings_of(owner).goal_cadence if owner is not None and s.profile_id is None else None
        pdf = build_report(
            s.result,
            patient_name=s.patient_name,
            created_at=s.created_at,
            lang=lang or settings_of(current_user).language,
            person=person_for_session(s),
            report_id=s.id,
            session_number=everyone.index(s.id) + 1 if s.id in everyone else None,
            history=trend_points(db, s.user_id, s.profile_id, before=s.created_at),
            goal_cadence=goal,
        )
    else:  # results stored before the gait profile, and the treadmill test: the v2 report
        pdf = build_pdf(s.result, patient_name=s.patient_name, created_at=s.created_at)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="gaitscan_report.pdf"'},
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    profile_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """All the account's sessions; `profile_id` narrows to one profile ('self' = the account holder)."""
    q = db.query(SessionModel).filter(SessionModel.user_id == current_user.id)
    if profile_id == "self":
        q = q.filter(SessionModel.profile_id.is_(None))
    elif profile_id is not None:
        if not profile_id.isdigit():
            raise HTTPException(422, "profile_id is a profile's id or 'self'.")
        q = q.filter(SessionModel.profile_id == owned_profile(db, current_user, int(profile_id)).id)
    return [session_out(s) for s in q.order_by(SessionModel.created_at.desc()).all()]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, session_id)
    return SessionDetail(**session_out(s).model_dump(), disclaimer=DISCLAIMER)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def label_session(
    session_id: str,
    labels: SessionLabels,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """The owner's notes and tags. Only the owner may edit (a linked clinician sees them)."""
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is None or s.user_id != current_user.id:
        raise HTTPException(404, "Session not found")
    sent = labels.model_fields_set
    if "notes" in sent:
        s.notes = (labels.notes or "").strip() or None
    if "tags" in sent:
        s.tags = labels.tags or []
    db.commit()
    return session_out(s)
