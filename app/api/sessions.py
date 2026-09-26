"""Session history, session detail and PDF report endpoints (owner or linked clinician only)."""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DBSession

from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import ClinicianPatient, User
from app.db.models import Session as SessionModel
from app.services import display
from app.services.report_pdf import generate_pdf_report
from gaitcore.legacy import DISCLAIMER

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


@router.get("/report/{job_id}")
def get_report(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, job_id)
    pdf_path = f"outputs/{s.id}/gaitscan_report.pdf"
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename="gaitscan_report.pdf")

    results = {
        "scores": {
            "overall_risk_score": s.risk_score,
            "knee_symmetry_index": s.knee_si,
            "hip_symmetry_index": s.hip_si,
            "knee_flexion_range_L": s.knee_flex_L,
            "knee_flexion_range_R": s.knee_flex_R,
            "cadence": s.cadence,
        },
        "findings": [display.finding(f) for f in s.findings],
        "recommendations": [],
        "mode": s.mode,
        **display.summary(s.risk_score),
        "activity": {
            "activity": display.activity(s.activity),
            "confidence": s.confidence,
            "icon": "🚶",
            "description": f"Detected activity: {display.activity(s.activity)}",
        },
        "exercises": [display.exercise(ex) for ex in s.exercises],
    }

    output_dir = f"outputs/{s.id}"
    os.makedirs(output_dir, exist_ok=True)
    generate_pdf_report(results, output_path=pdf_path, plots_dir=output_dir)

    return FileResponse(pdf_path, media_type="application/pdf", filename="gaitscan_report.pdf")


@router.get("/sessions")
def list_sessions(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id)
        .order_by(SessionModel.created_at.desc())
        .all()
    )
    return [session_summary(s) for s in sessions]


def session_summary(s: SessionModel) -> dict:
    return {
        "id": s.id,
        "patient_name": s.patient_name,
        "mode": s.mode,
        "activity": display.activity(s.activity),
        "confidence": s.confidence,
        "risk_score": s.risk_score,
        **display.summary(s.risk_score),
        "cadence": s.cadence,
        "knee_si": s.knee_si,
        "hip_si": s.hip_si,
        "knee_flex_L": s.knee_flex_L,
        "knee_flex_R": s.knee_flex_R,
        "created_at": s.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    s = get_visible_session(db, current_user, session_id)
    return {
        **session_summary(s),
        "findings": [display.finding(f) for f in s.findings],
        "exercises": [display.exercise(ex) for ex in s.exercises],
        "disclaimer": DISCLAIMER,
    }
