"""Progress across sessions (Plan V3 Phase 11, BE-B): GET /me/trends. Per session, oldest first: the
overall verdict (worked out on read, like every result) and the key numbers the progress view plots:
cadence, step-time variability, knee and hip range of motion (both legs pooled) and the GPS. Results
stored before the gait profile give None for the profile's numbers."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.profiles import owned_profile
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import Session as SessionModel
from app.db.models import User
from app.services.gait_profile import person_for_session, present

router = APIRouter(tags=["sessions"])


class TrendPoint(BaseModel):
    id: str
    created_at: str | None
    overall: str | None
    cadence: float | None
    step_time_cv: float | None
    knee_rom: float | None
    hip_rom: float | None
    gps: float | None


class Trends(BaseModel):
    sessions: list[TrendPoint]


def _v(part: dict[str, Any] | None, name: str) -> float | None:
    row = (part or {}).get(name)
    return row.get("value") if isinstance(row, dict) else None


@router.get("/me/trends", response_model=Trends)
def trends(
    profile_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> Trends:
    if profile_id is not None:
        owned_profile(db, current_user, profile_id)
    rows = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id, SessionModel.profile_id == profile_id)
        .order_by(SessionModel.created_at)
        .all()
    )
    out = []
    for s in rows:
        if s.legacy or s.result is None:
            continue
        r = present(s.result, person_for_session(s)) or {}
        gp = r.get("gait_profile") or {}
        v = gp.get("verdict") or {}
        out.append(
            TrendPoint(
                id=s.id,
                created_at=s.created_at.isoformat() if s.created_at else None,
                overall=v.get("overall"),
                cadence=(r.get("metrics") or {}).get("cadence", {}).get("value"),
                step_time_cv=_v(gp.get("timing"), "step_time_cv"),
                knee_rom=_v(gp.get("kinematics"), "knee_rom"),
                hip_rom=_v(gp.get("kinematics"), "hip_rom"),
                gps=(v.get("gps") or {}).get("value"),
            )
        )
    return Trends(sessions=out)
