"""Privacy center (ADR-007, Plan V3 Phase 5): export everything the account holds, delete one session,
delete the account. Deletion removes every row that refers to the user; nothing is kept back."""

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.settings import settings_of
from app.core.security import get_current_user, verify_password
from app.db.database import get_db
from app.db.models import (
    AnalysisJob,
    AuthToken,
    ClinicianInvite,
    ClinicianPatient,
    Consent,
    Profile,
    RecoveryCode,
    SessionArchive,
    SessionComment,
    ShareLink,
    User,
)
from app.db.models import Session as SessionModel
from app.schemas import public_result

log = logging.getLogger("gaitscan")
router = APIRouter(tags=["privacy"])


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def delete_session_rows(db: DBSession, session_id: str) -> None:
    db.query(SessionComment).filter(SessionComment.session_id == session_id).delete()
    db.query(ShareLink).filter(ShareLink.session_id == session_id).delete()
    db.query(AnalysisJob).filter(AnalysisJob.session_id == session_id).delete()
    db.query(SessionArchive).filter(SessionArchive.session_id == session_id).delete()
    db.query(SessionModel).filter(SessionModel.id == session_id).delete()


@router.get("/me/export")
def export_my_data(
    current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> Response:
    uid = current_user.id
    sessions = (
        db.query(SessionModel).filter(SessionModel.user_id == uid).order_by(SessionModel.created_at).all()
    )
    clinicians = (
        db.query(ClinicianPatient, User)
        .join(User, User.id == ClinicianPatient.clinician_id)
        .filter(ClinicianPatient.patient_id == uid)
        .all()
    )
    data: dict[str, Any] = {
        "exported_at": datetime.now().astimezone().isoformat(),
        "account": {
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "created_at": _iso(current_user.created_at),
        },
        "sessions": [
            {
                "id": s.id,
                "created_at": _iso(s.created_at),
                "patient_name": s.patient_name,
                "profile_id": s.profile_id,
                "pipeline_version": s.pipeline_version,
                "result": public_result(s.result) if s.result else None,
                "notes": s.notes,
                "tags": s.tags or [],
                "archived_values": s.archive.data if s.archive else None,
                "comments": [
                    {
                        "by": "you" if c.author_id == uid else "clinician",
                        "body": c.body,
                        "at": _iso(c.created_at),
                    }
                    for c in db.query(SessionComment)
                    .filter(SessionComment.session_id == s.id)
                    .order_by(SessionComment.id)
                ],
            }
            for s in sessions
        ],
        "profiles": [
            {"id": p.id, "name": p.name, "birth_year": p.birth_year, "sex": p.sex}
            for p in db.query(Profile).filter(Profile.owner_id == uid).order_by(Profile.id)
        ],
        "consents": [
            {"version": c.version, "accepted_at": _iso(c.accepted_at), "withdrawn_at": _iso(c.withdrawn_at)}
            for c in db.query(Consent).filter(Consent.user_id == uid).order_by(Consent.id)
        ],
        "analysis_jobs": [
            {
                "id": j.id,
                "status": j.status,
                "created_at": _iso(j.created_at),
                "finished_at": _iso(j.finished_at),
            }
            for j in db.query(AnalysisJob).filter(AnalysisJob.user_id == uid)
        ],
        "linked_clinicians": [{"name": u.full_name, "since": _iso(cp.created_at)} for cp, u in clinicians],
        "settings": settings_of(current_user).model_dump(),
    }
    return Response(
        json.dumps(data, indent=1, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="gaitscan-export.json"'},
    )


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> Response:
    s = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if s is None or s.user_id != current_user.id:  # linked clinicians can't delete
        raise HTTPException(404, "Session not found")
    delete_session_rows(db, session_id)
    db.commit()
    return Response(status_code=204)


class DeleteAccount(BaseModel):
    password: str


@router.delete("/me", status_code=204)
def delete_account(
    body: DeleteAccount, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> Response:
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(400, "The password is incorrect.")
    uid = current_user.id
    for (sid,) in db.query(SessionModel.id).filter(SessionModel.user_id == uid).all():
        delete_session_rows(db, sid)
    db.query(AnalysisJob).filter(AnalysisJob.user_id == uid).delete()
    db.query(Profile).filter(Profile.owner_id == uid).delete()
    db.query(Consent).filter(Consent.user_id == uid).delete()
    db.query(AuthToken).filter(AuthToken.user_id == uid).delete()
    db.query(RecoveryCode).filter(RecoveryCode.user_id == uid).delete()
    db.query(SessionComment).filter(SessionComment.author_id == uid).delete()  # theirs on others' sessions
    db.query(ClinicianPatient).filter(
        (ClinicianPatient.patient_id == uid) | (ClinicianPatient.clinician_id == uid)
    ).delete(synchronize_session=False)
    db.query(ClinicianInvite).filter(
        (ClinicianInvite.clinician_id == uid) | (ClinicianInvite.patient_id == uid)
    ).delete(synchronize_session=False)
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    log.info("account deleted user_id=%d", uid)  # the id only: no email or name in logs
    return Response(status_code=204)
