"""Sign in with Google (Plan V3 Phase 9). Off until GOOGLE_CLIENT_ID is set (503 with a reason).

The app gets an ID token from Google Identity Services and posts it here. The token is checked
against Google's published signing keys (RS256), with the issuer, the audience (our client ID) and the
expiry (all required, with the account id). A Google account whose email Google has verified signs in
to the GaitScan account it made before, or gets a new patient account (with recovery codes, like
sign-up).

It never signs in to an account made with a password (2026-11-12 review). Sign-up can't check an
address (there is no email channel), so anyone can make a password account with someone else's
address; signing that person in to it with Google would put them in an account whose password the
other person knows (account pre-hijacking). Such an account keeps its password; Google sign-in
answers 409 and says to use it. Addresses are matched without regard to capitals: sign-up keeps them,
Google doesn't.
"""

import secrets
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import SignupResponse, TokenResponse, _codes_left, _new_recovery_codes, _token_response
from app.api.profiles import profiles_of
from app.api.settings import settings_of
from app.core import ratelimit
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import get_db
from app.db.models import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]
_jwks: jwt.PyJWKClient | None = None


class InvalidGoogleToken(Exception):
    pass


def check_id_token(token: str, client_id: str) -> dict[str, Any]:
    """The verified claims of a Google ID token, or InvalidGoogleToken."""
    global _jwks
    try:
        if _jwks is None:
            _jwks = jwt.PyJWKClient(GOOGLE_CERTS, cache_keys=True)
        key = _jwks.get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=GOOGLE_ISSUERS,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        return claims
    except jwt.PyJWTError as e:
        raise InvalidGoogleToken(str(e)) from e


class GoogleCredential(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


@router.post("/google", response_model=SignupResponse | TokenResponse)
def google_sign_in(
    payload: GoogleCredential, request: Request, db: Session = Depends(get_db)
) -> SignupResponse | TokenResponse:
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in isn't set up. Sign in with your email and password.")
    ip = ratelimit.client_ip(request)
    ratelimit.enforce((ratelimit.google_signins_per_ip, ip))
    ratelimit.google_signins_per_ip.hit(ip)
    try:
        claims = check_id_token(payload.credential, settings.google_client_id)
    except InvalidGoogleToken:
        raise HTTPException(401, "Google sign-in failed. Please try again.") from None
    email = str(claims.get("email") or "").strip().lower()
    if not email or claims.get("email_verified") is not True:
        raise HTTPException(400, "Google hasn't verified this email address, so it can't be used to sign in.")
    now = datetime.now(UTC)
    matches = db.query(User).filter(func.lower(User.email) == email).all()
    if matches:
        # Only an account Google made (its address verified when it was made) signs in this way.
        user = next((u for u in matches if u.email_verified_at is not None), None)
        if user is None:
            raise HTTPException(
                409,
                "An account with this email already exists and uses a password. "
                "Sign in with your email and password.",
            )
        out = _token_response(user)
        out.recovery_codes_left = _codes_left(db, user)
        out.settings = settings_of(user)
        out.profiles = profiles_of(db, user)
        return out
    user = User(
        email=email,
        hashed_password=hash_password(secrets.token_urlsafe(32)),  # unusable until a reset or change
        full_name=str(claims.get("name") or "") or None,
        role=UserRole.patient.value,
        email_verified_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    codes = _new_recovery_codes(db, user)
    db.commit()
    return SignupResponse(**_token_response(user).model_dump(), recovery_codes=codes)
