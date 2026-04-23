import random
import string
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from collections import defaultdict

from src.core.auth import get_current_user, require_clinician
from src.core.database import get_db
from src.models.user import User
from src.models.clinician_patient import ClinicianInvite, ClinicianPatient

router = APIRouter(tags=["clinician"])

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# ── Clinician generates invite code ───────────────────────────────────────
@router.post("/clinician/invite")
def create_invite(
    clinician: User = Depends(require_clinician),
    db: Session = Depends(get_db)
):
    code = generate_code()
    # ensure unique
    while db.query(ClinicianInvite).filter(ClinicianInvite.code == code).first():
        code = generate_code()

    invite = ClinicianInvite(clinician_id=clinician.id, code=code)
    db.add(invite)
    db.commit()
    return {"code": code, "message": "Share this code with your patient"}

# ── Patient joins using invite code ───────────────────────────────────────
class JoinRequest(BaseModel):
    code: str

@router.post("/patient/join")
def join_clinician(
    payload: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can join a clinician")

    invite = db.query(ClinicianInvite).filter(
        ClinicianInvite.code == payload.code.upper(),
        ClinicianInvite.used == False
    ).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or already used invite code")

    # check not already linked
    existing = db.query(ClinicianPatient).filter(
        ClinicianPatient.clinician_id == invite.clinician_id,
        ClinicianPatient.patient_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already linked to this clinician")

    # mark invite used
    invite.used = True
    invite.patient_id = current_user.id

    # create link
    link = ClinicianPatient(
        clinician_id=invite.clinician_id,
        patient_id=current_user.id
    )
    db.add(link)
    db.commit()

    return {"message": "Successfully linked to your clinician"}

# ── Clinician gets all their patients ─────────────────────────────────────
@router.get("/clinician/patients")
def get_patients(
    clinician: User = Depends(require_clinician),
    db: Session = Depends(get_db)
):
    from src.core.models import Session as GaitSession

    links = db.query(ClinicianPatient).filter(
        ClinicianPatient.clinician_id == clinician.id
    ).all()

    result = []
    for link in links:
        patient = db.query(User).filter(User.id == link.patient_id).first()
        if not patient:
            continue

        # get all sessions for this patient
        sessions = db.query(GaitSession).filter(
            GaitSession.user_id == link.patient_id
        ).order_by(desc(GaitSession.created_at)).all()

        if not sessions:
            result.append({
                "patient_id": patient.id,
                "name": patient.full_name or patient.email,
                "email": patient.email,
                "session_count": 0,
                "latest_risk": None,
                "latest_activity": None,
                "trend": [],
                "flag": False,
                "linked_since": link.created_at.isoformat()
            })
            continue

        latest = sessions[0]

        # trend — last 5 sessions oldest first
        trend = [
            {"date": s.created_at.strftime("%d %b"), "risk": s.risk_score}
            for s in reversed(sessions[:5])
        ]

        # flag logic — risk > 50 OR rising across last 3
        flag = False
        if latest.risk_score and latest.risk_score > 50:
            flag = True
        if len(sessions) >= 3:
            last3 = [s.risk_score for s in sessions[:3] if s.risk_score is not None]
            if len(last3) == 3 and last3[0] > last3[1] > last3[2]:
                flag = True

        result.append({
            "patient_id": patient.id,
            "name": patient.full_name or patient.email,
            "email": patient.email,
            "session_count": len(sessions),
            "latest_risk": latest.risk_score,
            "latest_risk_color": latest.risk_color,
            "latest_activity": latest.activity,
            "latest_knee_si": latest.knee_si,
            "trend": trend,
            "flag": flag,
            "linked_since": link.created_at.isoformat()
        })

    # flagged patients first
    result.sort(key=lambda x: (not x["flag"], x["name"]))
    return result

# ── Clinician gets one patient's full session history ─────────────────────
@router.get("/clinician/patients/{patient_id}/sessions")
def get_patient_sessions(
    patient_id: int,
    clinician: User = Depends(require_clinician),
    db: Session = Depends(get_db)
):
    from src.core.models import Session as GaitSession

    # verify this patient belongs to this clinician
    link = db.query(ClinicianPatient).filter(
        ClinicianPatient.clinician_id == clinician.id,
        ClinicianPatient.patient_id == patient_id
    ).first()
    if not link:
        raise HTTPException(status_code=403, detail="Patient not in your list")

    patient = db.query(User).filter(User.id == patient_id).first()
    sessions = db.query(GaitSession).filter(
        GaitSession.user_id == patient_id
    ).order_by(desc(GaitSession.created_at)).all()

    return {
        "patient": {
            "id": patient.id,
            "name": patient.full_name or patient.email,
            "email": patient.email
        },
        "sessions": [
            {
                "id": s.id,
                "activity": s.activity,
                "risk_score": s.risk_score,
                "risk_label": s.risk_label,
                "risk_color": s.risk_color,
                "knee_si": s.knee_si,
                "hip_si": s.hip_si,
                "cadence": s.cadence,
                "created_at": s.created_at.isoformat()
            }
            for s in sessions
        ]
    }