"""Other adults on one account (Plan V3 Phase 9): someone can measure a partner or a parent without
a second account. A profile is a name and a self-declared birth year; under-18s are refused, because
GaitScan is for adults. Deleting a profile deletes its sessions."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session as DBSession

from app.api.privacy import delete_session_rows
from app.core.security import get_current_user
from app.db.database import get_db
from app.db.models import AnalysisJob, Profile, User
from app.db.models import Session as SessionModel

router = APIRouter(tags=["profiles"])

ADULT_AGE = 18
OLDEST_BIRTH_YEAR = 1900
MAX_PROFILES = 10


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    birth_year: int
    is_adult: bool  # the account holder confirms the person is 18 or over

    @model_validator(mode="after")
    def adults_only(self) -> "ProfileIn":
        latest = date.today().year - ADULT_AGE
        if not self.is_adult or not OLDEST_BIRTH_YEAR <= self.birth_year <= latest:
            raise ValueError(
                f"Profiles are for adults (18 or over): a birth year from {OLDEST_BIRTH_YEAR} to {latest}."
            )
        return self


class ProfileRename(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProfileOut(BaseModel):
    id: int
    name: str
    birth_year: int


def owned_profile(db: DBSession, user: User, profile_id: int) -> Profile:
    """The profile if `user` owns it; anything else is a 404, so IDs can't be probed."""
    p = db.get(Profile, profile_id)
    if p is None or p.owner_id != user.id:
        raise HTTPException(404, "Profile not found")
    return p


def _out(p: Profile) -> ProfileOut:
    return ProfileOut(id=p.id, name=p.name, birth_year=p.birth_year)


@router.get("/profiles", response_model=list[ProfileOut])
def list_profiles(current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)):
    return [
        _out(p) for p in db.query(Profile).filter(Profile.owner_id == current_user.id).order_by(Profile.id)
    ]


@router.post("/profiles", response_model=ProfileOut, status_code=201)
def create_profile(
    body: ProfileIn, current_user: User = Depends(get_current_user), db: DBSession = Depends(get_db)
) -> ProfileOut:
    if db.query(Profile).filter(Profile.owner_id == current_user.id).count() >= MAX_PROFILES:
        raise HTTPException(409, f"An account can hold up to {MAX_PROFILES} other people.")
    p = Profile(owner_id=current_user.id, name=body.name.strip(), birth_year=body.birth_year)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _out(p)


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
def rename_profile(
    profile_id: int,
    body: ProfileRename,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> ProfileOut:
    p = owned_profile(db, current_user, profile_id)
    p.name = body.name.strip()
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
