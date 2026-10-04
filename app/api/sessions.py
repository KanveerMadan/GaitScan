"""Session history, session detail and PDF report endpoints (owner or linked clinician only).

Legacy sessions (analysed before Plan V3) are listed with `legacy: true` and no measurements; their
old values stay in session_archive and are never served as measurements or mixed into trends.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session as DBSession

from app.core.copy import DISCLAIMER, LEGACY_NOTE
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import ClinicianPatient, User
from app.db.models import Session as SessionModel
from app.schemas import Result, SessionDetail, SessionOut
from app.services.report_pdf import build_pdf

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
        result=None if legacy else Result.model_validate(s.result),
        note=LEGACY_NOTE if legacy else None,
    )


@router.get("/report/{job_id}")
def get_report(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> Response:
    s = get_visible_session(db, current_user, job_id)
    if s.legacy or s.result is None:
        raise HTTPException(410, LEGACY_NOTE)
    # Built from the stored result every time: deterministic, nothing kept on disk (F15).
    pdf = build_pdf(s.result, patient_name=s.patient_name, created_at=s.created_at)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="gaitscan_report.pdf"'},
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id)
        .order_by(SessionModel.created_at.desc())
        .all()
    )
    return [session_out(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, session_id)
    return SessionDetail(**session_out(s).model_dump(), disclaimer=DISCLAIMER)
