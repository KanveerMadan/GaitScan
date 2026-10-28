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
os.environ.update(
    {
        "ENV": "dev",
        "DATABASE_URL": f"sqlite:///{TMP}/test.db",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "CORS_ORIGINS": "http://localhost:3000",
        "MAIL_BACKEND": "console",
        "FRONTEND_URL": "http://app.test",
    }
)


def migrate(url, rev="head"):
    """Run Alembic against `url` (the app no longer creates tables at startup)."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, rev)


migrate(os.environ["DATABASE_URL"])

PASSWORD = "correct-horse-battery"


@pytest.fixture
def outbox():
    """Emails 'sent' by the console mailer during the test."""
    from app.services import mailer

    mailer.OUTBOX.clear()
    return mailer.OUTBOX


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Every test starts with empty auth rate-limit windows (all requests share one test IP)."""
    from app.core import ratelimit

    for limiter in ratelimit.ALL:
        limiter.reset()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def register(client, email=None, password=PASSWORD, consent=True, **extra):
    """A new account; by default it has also accepted the current consent text (Phase 5), as every
    account must before its first analysis (tests/test_consent.py covers refusing without it)."""
    email = email or f"{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={"email": email, "password": password, **extra})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    if consent:
        from app.core.copy import CONSENT_VERSION

        c = client.post("/consent", headers=auth(token), json={"version": CONSENT_VERSION})
        assert c.status_code == 201, c.text
    return email, token


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


def seed_session(owner_email, legacy=False, legacy_text=False):
    """Insert a stored analysis directly (no video needed).

    Default: a v2 session whose result is the pipeline's output for the synthetic walker.
    legacy=True: a row as migration 0003 leaves pre-V3 sessions (pipeline_version 'legacy', old values
    only in session_archive). legacy_text adds the diagnostic wording rows written before Phase 0 had.
    """
    from synthetic import synthetic_clip

    from app.db.database import SessionLocal
    from app.db.models import Session, SessionArchive
    from gaitcore.pipeline import analyse

    legacy = legacy or legacy_text
    sid = str(uuid.uuid4())
    db = SessionLocal()
    try:
        if not legacy:
            result = analyse(synthetic_clip()[0]).to_dict()
            db.add(
                Session(
                    id=sid,
                    patient_name="Test Patient",
                    user_id=db_user(owner_email),
                    pipeline_version=result["pipeline_version"],
                    result=result,
                )
            )
        else:
            db.add(
                Session(
                    id=sid,
                    patient_name="Test Patient",
                    user_id=db_user(owner_email),
                    pipeline_version="legacy",
                )
            )
            db.flush()
            db.add(
                SessionArchive(
                    session_id=sid,
                    source="test",
                    data={
                        "session": {
                            "activity": "Limping" if legacy_text else "Walking",
                            "risk_score": 80 if legacy_text else 15,
                            "risk_label": "Serious abnormality" if legacy_text else "x",
                            "risk_meaning": "Serious gait issues detected. Please consult a doctor."
                            if legacy_text
                            else "x",
                            "cadence": 100.0,
                            "knee_si": 12.0,
                        },
                        "findings": [
                            {
                                "metric": "Knee Symmetry",
                                "plain_english": "which can cause long-term joint damage and pain.",
                            }
                        ],
                        "exercises": [{"name": "Glute bridge", "why": "Reduces your injury risk"}],
                    },
                )
            )
        db.commit()
    finally:
        db.close()
    return sid


def fake_video(monkeypatch, info=None, **clip_kwargs):
    """Skip decoding and MediaPipe: any upload 'is' a 30 fps video whose landmarks are the
    synthetic walker (tests/synthetic.py) built with `clip_kwargs`."""
    from synthetic import synthetic_clip

    import app.api.analysis as m
    from gaitcore.pipeline import VideoInfo

    clip, truth = synthetic_clip(**clip_kwargs)
    monkeypatch.setattr(
        m, "probe", lambda path: info or VideoInfo(clip.fps, clip.n_frames, clip.width, clip.height)
    )
    monkeypatch.setattr(m, "extract_clip", lambda path: clip)
    return clip, truth
