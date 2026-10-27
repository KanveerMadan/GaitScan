import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base

# Column arguments mirror the migrated schema exactly; test_migrations diffs them.

LEGACY = "legacy"


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
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Logins issued before this are refused (a password change or reset ends other sessions).
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthToken(Base):
    """A single-use link token for password reset or email verification. Only its SHA-256 is stored."""

    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String, nullable=False)  # reset | verify
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    """One accepted analysis. pipeline_version 'legacy' = analysed before Plan V3: its values were
    unreliable and live only in SessionArchive (migration 0003); `result` is NULL."""

    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    patient_name: Mapped[str | None] = mapped_column(String, default="Anonymous")
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    pipeline_version: Mapped[str] = mapped_column(String, nullable=False, server_default="legacy")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # the owner's own note
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    archive: Mapped["SessionArchive | None"] = relationship(back_populates="session", cascade="all, delete")

    @property
    def legacy(self) -> bool:
        return self.pipeline_version == LEGACY


class AnalysisJob(Base):
    """One uploaded video being analysed in the background (Plan V3 Phase 4). status: queued |
    running | done (session_id set) | rejected (error_code/message: the quality gate's reason) |
    failed (error_message: user-facing, with a log reference). Holds no measurements itself."""

    __tablename__ = "analysis_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    test: Mapped[str] = mapped_column(String, nullable=False, server_default="walk")
    patient_name: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, ForeignKey("sessions.id"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Consent(Base):
    """One acceptance of the consent text (ADR-007). Withdrawal sets withdrawn_at; rows are kept as
    the record. Active = the latest row for the user, current version, not withdrawn."""

    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionArchive(Base):
    """Pre-V3 values that Plan V3 removed from the product (the full list is in migration 0003),
    kept verbatim for export and deletion; never shown as measurements."""

    __tablename__ = "session_archive"
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"), primary_key=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    session: Mapped[Session] = relationship(back_populates="archive")


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
