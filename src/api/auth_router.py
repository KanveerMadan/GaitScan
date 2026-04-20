from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from src.core.auth import hash_password, verify_password, create_access_token, get_current_user
from src.models.user import User, UserRole
from src.core.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Schemas ────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.patient

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None

# ── Routes ─────────────────────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    role_str = payload.role.value if hasattr(payload.role, "value") else payload.role

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role_str,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    role_str = user.role if isinstance(user.role, str) else user.role.value
    token = create_access_token({"sub": user.id, "role": role_str})
    return TokenResponse(access_token=token, role=role_str, full_name=user.full_name)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    role_str = user.role if isinstance(user.role, str) else user.role.value
    token = create_access_token({"sub": user.id, "role": role_str})
    return TokenResponse(access_token=token, role=role_str, full_name=user.full_name)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "full_name": current_user.full_name,
    }