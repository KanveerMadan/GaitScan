"""Per-user settings (Plan V3 Phase 9): how often to re-test (reminders and "next test due"), display
units, language, theme and a cadence goal. Only what a feature uses is stored. The goal is the user's own
number: GaitScan suggests none (no norms by age or sex are verified, and it isn't advice)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import User

router = APIRouter(tags=["settings"])

RetestWeeks = Literal[1, 2, 4, 8, 12]
GoalCadence = Annotated[int, Field(ge=60, le=180)]  # steps/min: the range a walk can sensibly have


class Settings(BaseModel):
    retest_weeks: RetestWeeks | None = None
    units: Literal["metric", "imperial"] = "metric"
    language: Literal["en", "hi"] = "en"
    theme: Literal["system", "light", "dark"] = "system"
    goal_cadence: GoalCadence | None = None


class SettingsUpdate(BaseModel):
    """Only the fields sent change; retest_weeks / goal_cadence: null turns them off."""

    model_config = ConfigDict(extra="forbid")
    retest_weeks: RetestWeeks | None = None
    units: Literal["metric", "imperial"] | None = None
    language: Literal["en", "hi"] | None = None
    theme: Literal["system", "light", "dark"] | None = None
    goal_cadence: GoalCadence | None = None


def settings_of(user: User) -> Settings:
    return Settings(**(user.settings or {}))


@router.get("/me/settings", response_model=Settings)
def get_settings(current_user: User = Depends(get_current_user)) -> Settings:
    return settings_of(current_user)


@router.patch("/me/settings", response_model=Settings)
def update_settings(
    body: SettingsUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Settings:
    # Only the re-test interval and the goal can be cleared; a null for anything else leaves it as it is.
    clearable = ("retest_weeks", "goal_cadence")
    changes = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in clearable
    }
    merged = Settings(**{**settings_of(current_user).model_dump(), **changes})
    current_user.settings = merged.model_dump()  # a new dict, so SQLAlchemy sees the change
    db.commit()
    return merged
