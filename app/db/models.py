import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base

# Column arguments mirror the pre-Alembic create_all schema exactly; test_migrations diffs them.


class UserRole(enum.StrEnum):
    patient = "patient"
    clinician = "clinician"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="patient")
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_name: Mapped[str | None] = mapped_column(String, default="Anonymous")
    # NULL for sessions stored before migration 0002
    mode: Mapped[str | None] = mapped_column(String, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    activity: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[int | None] = mapped_column(Integer)
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_label: Mapped[str | None] = mapped_column(String)
    risk_color: Mapped[str | None] = mapped_column(String)
    risk_meaning: Mapped[str | None] = mapped_column(Text)
    cadence: Mapped[float | None] = mapped_column(Float)
    knee_si: Mapped[float | None] = mapped_column(Float)
    hip_si: Mapped[float | None] = mapped_column(Float)
    knee_flex_L: Mapped[float | None] = mapped_column(Float)
    knee_flex_R: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    findings: Mapped[list["Finding"]] = relationship(back_populates="session", cascade="all, delete")
    exercises: Mapped[list["Exercise"]] = relationship(back_populates="session", cascade="all, delete")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, ForeignKey("sessions.id"))
    metric: Mapped[str | None] = mapped_column(String)
    value: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    plain_english: Mapped[str | None] = mapped_column(Text)
    session: Mapped[Session | None] = relationship(back_populates="findings")


class Exercise(Base):
    __tablename__ = "exercises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String, ForeignKey("sessions.id"))
    name: Mapped[str | None] = mapped_column(String)
    muscle: Mapped[str | None] = mapped_column(String)
    difficulty: Mapped[str | None] = mapped_column(String)
    instructions: Mapped[str | None] = mapped_column(Text)
    why: Mapped[str | None] = mapped_column(Text)
    session: Mapped[Session | None] = relationship(back_populates="exercises")


class ClinicianInvite(Base):
    __tablename__ = "clinician_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clinician_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    used: Mapped[bool | None] = mapped_column(Boolean, default=False)
    patient_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicianPatient(Base):
    __tablename__ = "clinician_patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clinician_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    patient_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
