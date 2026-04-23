from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func
from src.core.database import Base

class ClinicianInvite(Base):
    __tablename__ = "clinician_invites"

    id          = Column(Integer, primary_key=True, index=True)
    clinician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code        = Column(String(6), unique=True, nullable=False, index=True)
    used        = Column(Boolean, default=False)
    patient_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

class ClinicianPatient(Base):
    __tablename__ = "clinician_patients"

    id           = Column(Integer, primary_key=True, index=True)
    clinician_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    patient_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())