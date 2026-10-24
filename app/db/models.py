import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
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
    archive: Mapped["SessionArchive | None"] = relationship(back_populates="session", cascade="all, delete")

    @property
    def legacy(self) -> bool:
        return self.pipeline_version == LEGACY


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
