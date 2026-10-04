import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.sessions import session_out
from app.core.security import get_current_user, require_clinician
from app.db.database import get_db
from app.db.models import ClinicianInvite, ClinicianPatient, User
from app.db.models import Session as GaitSession
from app.schemas import PatientRef, PatientSessions, PatientSummary

router = APIRouter(tags=["clinician"])


def generate_code():
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


@router.post("/clinician/invite")
def create_invite(clinician: User = Depends(require_clinician), db: Session = Depends(get_db)):
    code = generate_code()

    while db.query(ClinicianInvite).filter(ClinicianInvite.code == code).first():
        code = generate_code()

    invite = ClinicianInvite(clinician_id=clinician.id, code=code)
    db.add(invite)
    db.commit()
    return {"code": code, "message": "Share this code with your patient"}


class JoinRequest(BaseModel):
    code: str


@router.post("/patient/join")
def join_clinician(
    payload: JoinRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only patients can join a clinician")

    invite = (
        db.query(ClinicianInvite)
        .filter(ClinicianInvite.code == payload.code.upper(), ClinicianInvite.used.is_(False))
        .first()
    )

    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or already used invite code")

    existing = (
        db.query(ClinicianPatient)
        .filter(
            ClinicianPatient.clinician_id == invite.clinician_id,
            ClinicianPatient.patient_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already linked to this clinician")

    invite.used = True
    invite.patient_id = current_user.id

    link = ClinicianPatient(clinician_id=invite.clinician_id, patient_id=current_user.id)
    db.add(link)
    db.commit()

    return {"message": "Successfully linked to your clinician"}


@router.get("/clinician/patients", response_model=list[PatientSummary])
def get_patients(clinician: User = Depends(require_clinician), db: Session = Depends(get_db)):
    links = db.query(ClinicianPatient).filter(ClinicianPatient.clinician_id == clinician.id).all()
    result: list[PatientSummary] = []
    for link in links:
        patient = db.query(User).filter(User.id == link.patient_id).first()
        if not patient:
            continue
        sessions = (
            db.query(GaitSession)
            .filter(GaitSession.user_id == link.patient_id)
            .order_by(GaitSession.created_at.desc())
            .all()
        )
        latest = sessions[0].created_at if sessions else None
        result.append(
            PatientSummary(
                patient_id=patient.id,
                name=patient.full_name or patient.email,
                email=patient.email,
                session_count=len(sessions),
                latest_session_at=latest.isoformat() if latest else None,
                linked_since=link.created_at.isoformat() if link.created_at else None,
            )
        )
    result.sort(key=lambda p: p.name)
    return result


@router.get("/clinician/patients/{patient_id}/sessions", response_model=PatientSessions)
def get_patient_sessions(
    patient_id: int, clinician: User = Depends(require_clinician), db: Session = Depends(get_db)
):
    # verify this patient belongs to this clinician
    link = (
        db.query(ClinicianPatient)
        .filter(ClinicianPatient.clinician_id == clinician.id, ClinicianPatient.patient_id == patient_id)
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Patient not in your list")

    patient = db.query(User).filter(User.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    sessions = (
        db.query(GaitSession)
        .filter(GaitSession.user_id == patient_id)
        .order_by(GaitSession.created_at.desc())
        .all()
    )
    return PatientSessions(
        patient=PatientRef(id=patient.id, name=patient.full_name or patient.email, email=patient.email),
        sessions=[session_out(s) for s in sessions],
    )
