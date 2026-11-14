"""Progress across sessions (Plan V3 Phase 11, BE-B): GET /me/trends. Per session, oldest first: the
overall verdict (worked out on read, like every result) and the key numbers the progress view plots:
cadence, step-time variability, knee and hip range of motion (both legs pooled) and the GPS. Results
stored before the gait profile give None for the profile's numbers (app/services/trends.py)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.api.profiles import owned_profile
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.services.trends import trend_points

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


@router.get("/me/trends", response_model=Trends)
def trends(
    profile_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> Trends:
    if profile_id is not None:
        owned_profile(db, current_user, profile_id)
    return Trends(sessions=[TrendPoint(**p) for p in trend_points(db, current_user.id, profile_id)])
