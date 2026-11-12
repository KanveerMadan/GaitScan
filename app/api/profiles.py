"""Other adults on one account (Plan V3 Phase 9): someone can measure a partner or a parent without
a second account. A profile is a name and a self-declared birth year, and optionally a sex (only for
the published cadence reference by age and sex, 2026-11-12); under-18s are refused, because GaitScan is
for adults. Deleting a profile deletes its sessions."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session as DBSession

from app.api.privacy import delete_session_rows
from app.core.people import Sex, adult_birth_years
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import AnalysisJob, Profile, User
from app.db.models import Session as SessionModel

router = APIRouter(tags=["profiles"])

MAX_PROFILES = 10


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    birth_year: int
    is_adult: bool  # the account holder confirms the person is 18 or over
    sex: Sex | None = None

    @model_validator(mode="after")
    def adults_only(self) -> "ProfileIn":
        oldest, latest = adult_birth_years()
        if not self.is_adult or not oldest <= self.birth_year <= latest:
            raise ValueError(f"Profiles are for adults (18 or over): a birth year from {oldest} to {latest}.")
        return self


class ProfileUpdate(BaseModel):
    """Only the fields sent change; "sex": null removes it."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=80)
    sex: Sex | None = None


class ProfileOut(BaseModel):
    id: int
    name: str
    birth_year: int
    sex: Sex | None = None


def owned_profile(db: DBSession, user: User, profile_id: int) -> Profile:
    """The profile if `user` owns it; anything else is a 404, so IDs can't be probed."""
    p = db.get(Profile, profile_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Profile not found")
    return p


def _out(p: Profile) -> ProfileOut:
    return ProfileOut.model_validate({"id": p.id, "name": p.name, "birth_year": p.birth_year, "sex": p.sex})


def profiles_of(db: DBSession, user: User) -> list[ProfileOut]:
    return [_out(p) for p in db.query(Profile).filter(Profile.owner_id == user.id).order_by(Profile.id)]


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    return profiles_of(db, current_user)


@router.post("/profiles", response_model=ProfileOut, status_code=201)
def create_profile(
    body: ProfileIn, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> ProfileOut:
    if db.query(Profile).filter(Profile.owner_id == current_user.id).count() >= MAX_PROFILES:
        raise HTTPException(409, f"An account can hold up to {MAX_PROFILES} other people.")
    p = Profile(owner_id=current_user.id, name=body.name.strip(), birth_year=body.birth_year, sex=body.sex)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p)


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> ProfileOut:
    p = owned_profile(db, current_user, profile_id)
    if body.name is not None:
        p.name = body.name.strip()
    if "sex" in body.model_fields_set:
        p.sex = body.sex
    db.commit()
    return _out(p)


@router.delete("/profiles/{profile_id}", status_code=204)
def delete_profile(
    profile_id: int, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> Response:
    delete_profile_rows(db, owned_profile(db, current_user, profile_id).id)
    db.commit()
    return Response(status_code=204)


def delete_profile_rows(db: DBSession, profile_id: int) -> None:
    for (sid,) in db.query(SessionModel.id).filter(SessionModel.profile_id == profile_id).all():
        delete_session_rows(db, sid)
    db.query(AnalysisJob).filter(AnalysisJob.profile_id == profile_id).delete()
    db.query(Profile).filter(Profile.id == profile_id).delete()
