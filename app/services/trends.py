"""Per-session key numbers for progress (Plan V3 Phase 11): GET /me/trends and the report's progress
page. Oldest first; the overall verdict is worked out on read, like every result. Results stored before
the gait profile give None for the profile's numbers; legacy sessions are left out."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.db.models import Session as SessionModel
from app.services.gait_profile import person_for_session, present


def _v(part: dict[str, Any] | None, name: str) -> float | None:
    row = (part or {}).get(name)
    return row.get("value") if isinstance(row, dict) else None


def point(s: SessionModel) -> dict[str, Any]:
    r = present(s.result, person_for_session(s)) or {}
    gp = r.get("gait_profile") or {}
    v = gp.get("verdict") or {}
    return {
        "id": s.id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "overall": v.get("overall"),
        "cadence": (r.get("metrics") or {}).get("cadence", {}).get("value"),
        "step_time_cv": _v(gp.get("timing"), "step_time_cv"),
        "knee_rom": _v(gp.get("kinematics"), "knee_rom"),
        "hip_rom": _v(gp.get("kinematics"), "hip_rom"),
        "gps": (v.get("gps") or {}).get("value"),
    }


def sessions_of(db: DBSession, user_id: int | None, profile_id: int | None) -> list[SessionModel]:
    """Every session of one person (the account holder, or one profile), oldest first."""
    return (
        db.query(SessionModel)
        .filter(SessionModel.user_id == user_id, SessionModel.profile_id == profile_id)
        .order_by(SessionModel.created_at, SessionModel.id)
        .all()
    )


def trend_points(
    db: DBSession, user_id: int | None, profile_id: int | None, before: datetime | None = None
) -> list[dict[str, Any]]:
    rows = sessions_of(db, user_id, profile_id)
    if before is not None:
        rows = [s for s in rows if s.created_at is not None and s.created_at < before]
    return [point(s) for s in rows if not s.legacy and s.result is not None]
