"""Per-user settings (Plan V3 Phase 9): how often to re-test (reminders and "next test due"), display
units, language, theme and a cadence goal. Only what a feature uses is stored. The goal is the user's own
number: GaitScan suggests none (it isn't advice).

Sex and birth year (owner decision 2026-11-12) are optional and used only to show the published
cadence reference for the person's age and sex next to their result (the app's src/lib/norms.js).
Leaving either empty shows no reference."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.people import Sex, adult_birth_year_error, adult_birth_years
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
    sex: Sex | None = None
    birth_year: int | None = None


def _adult(year: int | None) -> int | None:
    lo, hi = adult_birth_years()
    if year is not None and not lo <= year <= hi:
        raise ValueError(adult_birth_year_error())
    return year


class SettingsUpdate(BaseModel):
    """Only the fields sent change; retest_weeks / goal_cadence: null turns them off."""

    model_config = ConfigDict(extra="forbid")
    retest_weeks: RetestWeeks | None = None
    units: Literal["metric", "imperial"] | None = None
    language: Literal["en", "hi"] | None = None
    theme: Literal["system", "light", "dark"] | None = None
    goal_cadence: GoalCadence | None = None
    sex: Sex | None = None
    birth_year: int | None = None

    _birth_year = field_validator("birth_year")(_adult)


def settings_of(user: User) -> Settings:
    return Settings(**(user.settings or {}))


@router.get("/me/settings", response_model=Settings)
def get_settings(current_user: User = Depends(get_current_user)) -> Settings:
    return settings_of(current_user)


@router.patch("/me/settings", response_model=Settings)
def update_settings(
    body: SettingsUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Settings:
    # The re-test interval, the goal, sex and birth year can be cleared; a null for anything else
    # leaves it as it is.
    clearable = ("retest_weeks", "goal_cadence", "sex", "birth_year")
    changes = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in clearable
    }
    merged = Settings(**{**settings_of(current_user).model_dump(), **changes})
    current_user.settings = merged.model_dump()  # a new dict, so SQLAlchemy sees the change
    db.commit()
    return merged
