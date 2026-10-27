import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import settings
from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.database import get_db
from app.db.models import AuthToken, User, UserRole
from app.services import mailer

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LENGTH = 10
# Verified against when the email is unknown, so every login costs one bcrypt check (F12).
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


def require_new_password(password: str) -> None:
    """Only new passwords (registration, change) must meet the minimum; login never checks length,
    so accounts created before the rule keep working."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    # No role field: roles are never client-supplied. Clinicians are promoted by an admin.


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth2 token type, not a secret)
    role: str
    full_name: str | None = None


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
    current_user.password_changed_at = datetime.now(UTC)  # ends every other login
    db.commit()
    # A fresh token for this session, issued after the change, so it stays signed in.
    return {"message": "Password changed.", **_token_response(current_user).model_dump()}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
        "email_verified": current_user.email_verified_at is not None,
    }


# ---- Password reset and email verification (Plan V3 Phase 5) -----------------------------------
RESET_TTL = timedelta(minutes=30)
VERIFY_TTL = timedelta(hours=24)
NO_MAIL = (
    "Sending email isn't available yet, so this can't be done by email. "
    "Please contact the GaitScan team for help with your account."
)
RESET_SENT = "If an account uses this email address, we've sent it a link to choose a new password."


class EmailRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str


class LinkToken(BaseModel):
    token: str = Field(min_length=20, max_length=200)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthToken(user_id=user.id, purpose=purpose, token_hash=_hash(raw), expires_at=datetime.now(UTC) + ttl)
    )
    return raw


def _redeem(db: Session, raw: str, purpose: str) -> AuthToken:
    row = db.query(AuthToken).filter(AuthToken.token_hash == _hash(raw), AuthToken.purpose == purpose).first()
    expires = None if row is None else row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)  # SQLite: naive, stored in UTC
    if row is None or row.used_at is not None or expires is None or expires < datetime.now(UTC):
        raise HTTPException(400, "This link is invalid or has expired. Please ask for a new one.")
    row.used_at = datetime.now(UTC)
    return row


def _link(path: str, raw: str) -> str:
    # The token goes in the URL fragment: browsers never send it to a server or in a Referer header.
    return f"{settings.frontend_url}/{path}#token={raw}"


@router.post("/password-reset", status_code=202)
def request_password_reset(payload: EmailRequest, request: Request, db: Session = Depends(get_db)):
    if not mailer.available():
        raise HTTPException(503, NO_MAIL)
    email_key = str(payload.email).lower()
    ip = ratelimit.client_ip(request)
    ratelimit.enforce((ratelimit.reset_requests_per_email, email_key), (ratelimit.reset_requests_per_ip, ip))
    ratelimit.reset_requests_per_email.hit(email_key)
    ratelimit.reset_requests_per_ip.hit(ip)
    user = db.query(User).filter(User.email == email_key).first()
    if user is not None:
        raw = _issue(db, user, "reset", RESET_TTL)
        db.commit()
        mailer.send(
            user.email,
            "Choose a new GaitScan password",
            "Someone asked to reset the password for this GaitScan account.\n\n"
            f"Choose a new password here (the link works once, for 30 minutes):\n{_link('reset-password', raw)}\n\n"
            "If it wasn't you, ignore this email: your password stays the same.",
        )
    return {"message": RESET_SENT}


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: ResetConfirm, db: Session = Depends(get_db)):
    require_new_password(payload.new_password)
    row = _redeem(db, payload.token, "reset")
    user = db.get(User, row.user_id)
    if user is None:
        raise HTTPException(400, "This link is invalid or has expired. Please ask for a new one.")
    now = datetime.now(UTC)
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = now  # ends every earlier login
    user.email_verified_at = user.email_verified_at or now  # the link reached this inbox
    db.query(AuthToken).filter(
        AuthToken.user_id == user.id, AuthToken.purpose == "reset", AuthToken.used_at.is_(None)
    ).update({AuthToken.used_at: now})
    db.commit()
    return {"message": "Password changed. You can now sign in with your new password."}


@router.post("/verify-email/request", status_code=202)
def request_email_verification(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not mailer.available():
        raise HTTPException(503, NO_MAIL)
    raw = _issue(db, current_user, "verify", VERIFY_TTL)
    db.commit()
    mailer.send(
        current_user.email,
        "Confirm your email address for GaitScan",
        f"Confirm this is your email address (the link works once, for 24 hours):\n{_link('verify-email', raw)}",
    )
    return {"message": "We've sent a confirmation link to your email address."}


@router.post("/verify-email")
def verify_email(payload: LinkToken, db: Session = Depends(get_db)):
    row = _redeem(db, payload.token, "verify")
    user = db.get(User, row.user_id)
    if user is not None:
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    db.commit()
    return {"message": "Email address confirmed."}
