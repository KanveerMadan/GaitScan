from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.database import get_db
from app.db.models import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 10
# Verified against when the email is unknown, so every login costs one bcrypt check (F12).
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def require_new_password(password: str) -> None:
    """Only new passwords (registration, change) must meet the minimum; login never checks length,
    so accounts created before the rule keep working."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    # No role field: roles are never client-supplied. Clinicians are promoted by an admin.


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None


def _token_response(user: User) -> TokenResponse:
    role_str = user.role if isinstance(user.role, str) else user.role.value
    token = create_access_token({"sub": user.email, "role": role_str})
    return TokenResponse(access_token=token, role=role_str, full_name=user.full_name)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip = ratelimit.client_ip(request)
    ratelimit.enforce((ratelimit.registrations_per_ip, ip))
    ratelimit.registrations_per_ip.hit(ip)
    require_new_password(payload.password)

    if db.query(User).filter(User.email == payload.email).first():
        # ponytail: open sign-up still reveals that an address is taken (any failure differs from
        # success). The rate limit above slows enumeration; invite-only / email-verified sign-up
        # (ADR-004, Phase 4) removes it.
        raise HTTPException(status_code=409, detail="Could not create an account with these details.")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.patient.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email_key = payload.email.lower()
    ip = ratelimit.client_ip(request)
    ratelimit.enforce((ratelimit.login_failures_per_email, email_key), (ratelimit.login_attempts_per_ip, ip))
    ratelimit.login_attempts_per_ip.hit(ip)

    user = db.query(User).filter(User.email == payload.email).first()
    ok = verify_password(payload.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not ok:
        ratelimit.login_failures_per_email.hit(email_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _token_response(user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email_key = current_user.email.lower()
    ratelimit.enforce((ratelimit.login_failures_per_email, email_key))
    if not verify_password(payload.current_password, current_user.hashed_password):
        ratelimit.login_failures_per_email.hit(email_key)
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    require_new_password(payload.new_password)
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password changed."}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
    }
