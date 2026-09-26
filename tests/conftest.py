"""Test harness: isolated cwd + throwaway SQLite DB, configured before the app is imported."""
import os
import secrets
import sys
import tempfile
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# The app writes data/ and outputs/ relative to cwd; keep that out of the repo.
TMP = tempfile.mkdtemp(prefix="gaitscan-test-")
os.chdir(TMP)
os.environ.update({
    "ENV": "dev",
    "DATABASE_URL": f"sqlite:///{TMP}/test.db",
    "JWT_SECRET": secrets.token_urlsafe(48),
    "CORS_ORIGINS": "http://localhost:3000",
})
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("ENABLE_LLM_EXPLANATIONS", None)

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def register(client, email=None, password=PASSWORD, **extra):
    email = email or f"{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": password, **extra})
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def db_user(email):
    from app.db.database import SessionLocal
    from app.db.models import User
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == email).first().id
    finally:
        db.close()


def promote_to_clinician(email):
    """Stands in for the admin step that replaces self-assigned roles."""
    from app.db.database import SessionLocal
    from app.db.models import User
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.role = "clinician"
        db.commit()
    finally:
        db.close()


def link(clinician_email, patient_email):
    from app.db.database import SessionLocal
    from app.db.models import ClinicianPatient
    db = SessionLocal()
    try:
        db.add(ClinicianPatient(clinician_id=db_user(clinician_email), patient_id=db_user(patient_email)))
        db.commit()
    finally:
        db.close()


def seed_session(owner_email, legacy_text=False):
    """Insert a finished analysis directly (no video needed). legacy_text mimics rows
    written before Phase 0, which carry diagnostic wording."""
    from app.db.database import SessionLocal
    from app.db.models import Session, Finding, Exercise
    sid = str(uuid.uuid4())
    db = SessionLocal()
    try:
        db.add(Session(
            id=sid, patient_name="Test Patient", user_id=db_user(owner_email),
            activity="Limping" if legacy_text else "Walking", confidence=70,
            risk_score=80 if legacy_text else 15,
            risk_label="Serious abnormality" if legacy_text else "x",
            risk_color="red",
            risk_meaning=("Serious gait issues detected. Please consult a doctor or physiotherapist soon."
                          if legacy_text else "x"),
            cadence=100.0, knee_si=12.0, hip_si=4.0, knee_flex_L=55.0, knee_flex_R=50.0,
        ))
        db.add(Finding(session_id=sid, metric="Knee Symmetry", value="12.0%", status="mild",
                       plain_english=("which can cause long-term joint damage and pain."
                                      if legacy_text else "Left and right knee motion differed by 12%.")))
        db.add(Exercise(session_id=sid, name="Glute bridge", muscle="Glutes", difficulty="Easy",
                        instructions="Lie on back.",
                        why="Reduces your injury risk & keeps L<R balance" if legacy_text else "Builds hip strength."))
        db.commit()
    finally:
        db.close()
    return sid
