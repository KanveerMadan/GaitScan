import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class UserRole(enum.StrEnum):
    patient = "patient"
    clinician = "clinician"


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="patient")
    full_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    patient_name = Column(String, default="Anonymous")
    mode = Column(String, nullable=True)  # NULL for sessions stored before migration 0002
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
    findings = relationship("Finding", back_populates="session", cascade="all, delete")
    exercises = relationship("Exercise", back_populates="session", cascade="all, delete")


class Finding(Base):
    __tablename__ = "findings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    metric = Column(String)
    value = Column(String)
    status = Column(String)
    plain_english = Column(Text)
    session = relationship("Session", back_populates="findings")


class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    name = Column(String)
    muscle = Column(String)
    difficulty = Column(String)
    instructions = Column(Text)
    why = Column(Text)
    session = relationship("Session", back_populates="exercises")


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
