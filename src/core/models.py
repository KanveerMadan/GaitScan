from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from src.core.database import Base

class Session(Base):
    __tablename__ = "sessions"

    id           = Column(String, primary_key=True)   # job_id
    patient_name = Column(String, default="Anonymous")
    activity     = Column(String)
    confidence   = Column(Integer)
    risk_score   = Column(Integer)
    risk_label   = Column(String)
    risk_color   = Column(String)
    risk_meaning = Column(Text)
    cadence      = Column(Float)
    knee_si      = Column(Float)   # knee symmetry index
    hip_si       = Column(Float)   # hip symmetry index
    knee_flex_L  = Column(Float)
    knee_flex_R  = Column(Float)
    created_at   = Column(DateTime, default=datetime.utcnow)

    findings  = relationship("Finding",  back_populates="session", cascade="all, delete")
    exercises = relationship("Exercise", back_populates="session", cascade="all, delete")


class Finding(Base):
    __tablename__ = "findings"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    session_id  = Column(String, ForeignKey("sessions.id"))
    metric      = Column(String)
    value       = Column(String)
    status      = Column(String)
    plain_english = Column(Text)

    session = relationship("Session", back_populates="findings")


class Exercise(Base):
    __tablename__ = "exercises"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    session_id   = Column(String, ForeignKey("sessions.id"))
    name         = Column(String)
    muscle       = Column(String)
    difficulty   = Column(String)
    instructions = Column(Text)
    why          = Column(Text)

    session = relationship("Session", back_populates="exercises")