"""Response models (typed OpenAPI for the frontend client, ADR-008)."""

from typing import Any

from pydantic import BaseModel


class Result(BaseModel):
    """gaitcore.result.AnalysisResult.to_dict() of an accepted analysis."""

    pipeline_version: str
    model: dict[str, str]
    status: str
    metrics: dict[str, Any]
    quality: dict[str, Any]
    notes: list[str] = []  # user-facing caveats; absent in results stored before 2026-10-24


class AnalyzeResponse(BaseModel):
    job_id: str
    result: Result
    report_url: str
    disclaimer: str


class SessionOut(BaseModel):
    id: str
    patient_name: str | None
    created_at: str | None
    pipeline_version: str
    legacy: bool  # analysed before Plan V3: no measurements shown, never part of trends
    result: Result | None
    note: str | None


class SessionDetail(SessionOut):
    disclaimer: str


class PatientSummary(BaseModel):
    patient_id: int
    name: str
    email: str
    session_count: int
    latest_session_at: str | None
    linked_since: str | None


class PatientRef(BaseModel):
    id: int
    name: str
    email: str


class PatientSessions(BaseModel):
    patient: PatientRef
    sessions: list[SessionOut]
