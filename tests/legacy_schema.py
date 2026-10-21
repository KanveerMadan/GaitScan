"""Pre-Alembic schemas, as `Base.metadata.create_all` built them from the old src/ models.

create_all never alters existing tables, so production may hold an older shape:
- "phase0": the models as of origin/main 38c8db3 (what a fresh create_all built last).
- "early": sessions created before user_id was added (5c18025, 2026-04-14) and users
  created while role was a native Enum (a93b308..a5d0a91, 2026-04-15..20).
"""

import enum
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func


class UserRole(str, enum.Enum):  # noqa: UP042 - verbatim legacy definition
    patient = "patient"
    clinician = "clinician"


def legacy_metadata(variant: str) -> sa.MetaData:
    Base = declarative_base()
    early = variant == "early"

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True, index=True)
        email = Column(String, unique=True, index=True, nullable=False)
        hashed_password = Column(String, nullable=False)
        role = (
            Column(Enum(UserRole), nullable=False, default=UserRole.patient)
            if early
            else Column(String, nullable=False, default="patient")
        )
        full_name = Column(String, nullable=True)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    class Session(Base):
        __tablename__ = "sessions"
        id = Column(String, primary_key=True)
        patient_name = Column(String, default="Anonymous")
        if not early:
            user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        activity = Column(String)
        confidence = Column(Integer)
        risk_score = Column(Integer)
        risk_label = Column(String)
        risk_color = Column(String)
        risk_meaning = Column(Text)
        cadence = Column(Float)
        knee_si = Column(Float)
        hip_si = Column(Float)
        knee_flex_L = Column(Float)
        knee_flex_R = Column(Float)
        created_at = Column(DateTime, default=datetime.utcnow)

    class Finding(Base):
        __tablename__ = "findings"
        id = Column(Integer, primary_key=True, autoincrement=True)
        session_id = Column(String, ForeignKey("sessions.id"))
        metric = Column(String)
        value = Column(String)
        status = Column(String)
        plain_english = Column(Text)

    class Exercise(Base):
        __tablename__ = "exercises"
        id = Column(Integer, primary_key=True, autoincrement=True)
        session_id = Column(String, ForeignKey("sessions.id"))
        name = Column(String)
        muscle = Column(String)
        difficulty = Column(String)
        instructions = Column(Text)
        why = Column(Text)

    class ClinicianInvite(Base):
        __tablename__ = "clinician_invites"
        id = Column(Integer, primary_key=True, index=True)
        clinician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        code = Column(String(6), unique=True, nullable=False, index=True)
        used = Column(Boolean, default=False)
        patient_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    class ClinicianPatient(Base):
        __tablename__ = "clinician_patients"
        id = Column(Integer, primary_key=True, index=True)
        clinician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        patient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    return Base.metadata


T0 = datetime(2026, 4, 20, 12, 0, 0)
T0Z = T0.replace(tzinfo=UTC)


def sample_rows(variant: str) -> dict[str, list[dict[str, object]]]:
    """Synthetic rows for every table (no real people)."""
    session = {
        "id": "ab12cd34",
        "patient_name": "Test Patient",
        "activity": "Walking",
        "confidence": 71,
        "risk_score": 20,
        "risk_label": "Minor deviations",
        "risk_color": "green",
        "risk_meaning": "text <with> markup & symbols",
        "cadence": 104.5,
        "knee_si": 6.2,
        "hip_si": 3.1,
        "knee_flex_L": 58.0,
        "knee_flex_R": 61.5,
        "created_at": T0,
    }
    if variant != "early":
        session["user_id"] = 2
    return {
        "users": [
            {
                "id": 1,
                "email": "clin@example.com",
                "hashed_password": "h1",
                "role": "clinician",
                "full_name": "Dr Test",
                "created_at": T0Z,
            },
            {
                "id": 2,
                "email": "pat@example.com",
                "hashed_password": "h2",
                "role": "patient",
                "full_name": None,
                "created_at": T0Z,
            },
        ],
        "sessions": [session],
        "findings": [
            {
                "id": 1,
                "session_id": "ab12cd34",
                "metric": "Cadence",
                "value": "104.5 steps/min",
                "status": "good",
                "plain_english": "Step rate was 104.5 steps/min.",
            }
        ],
        "exercises": [
            {
                "id": 1,
                "session_id": "ab12cd34",
                "name": "Glute bridge",
                "muscle": "Glutes",
                "difficulty": "Easy",
                "instructions": "Lie on your back.",
                "why": "Hip extension.",
            }
        ],
        "clinician_invites": [
            {"id": 1, "clinician_id": 1, "code": "AB12CD", "used": True, "patient_id": 2, "created_at": T0Z}
        ],
        "clinician_patients": [{"id": 1, "clinician_id": 1, "patient_id": 2, "created_at": T0Z}],
    }


def build_legacy_db(url: str, variant: str) -> dict[str, list[dict[str, object]]]:
    md = legacy_metadata(variant)
    rows = sample_rows(variant)
    engine = sa.create_engine(url)
    md.create_all(engine)
    with engine.begin() as conn:
        for table in md.sorted_tables:
            payload = rows[table.name]
            if table.name == "users" and variant == "early":
                payload = [{**r, "role": UserRole(r["role"])} for r in payload]
            conn.execute(table.insert(), payload)
        if engine.dialect.name == "postgresql":  # explicit ids: advance sequences as app inserts did
            for table in md.sorted_tables:
                if table.name != "sessions":
                    conn.execute(
                        sa.text(
                            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                            f"(SELECT max(id) FROM {table.name}))"
                        )
                    )
    engine.dispose()
    return rows
