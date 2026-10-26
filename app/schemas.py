"""Response models (typed OpenAPI for the frontend client, ADR-008)."""

from typing import Any

from pydantic import BaseModel


class Result(BaseModel):
    """gaitcore.result.AnalysisResult.to_dict() of an accepted analysis."""

    pipeline_version: str
    model: dict[str, str]
    test: str = "walk"  # absent in results stored before Phase 3 (all walks)
    status: str
    metrics: dict[str, Any]
    accuracy: dict[str, Any] = {}  # per metric; absent in results stored before Phase 3
    quality: dict[str, Any]
    notes: list[str] = []  # user-facing caveats; absent in results stored before 2026-10-24
    passes: list[dict[str, Any]] = []  # per walk across the frame; absent before Phase 3
    pass_variability: dict[str, Any] | None = None


class AnalyzeResponse(BaseModel):
    job_id: str
    result: Result
    report_url: str
    disclaimer: str


class JobQueued(BaseModel):
    job_id: str
    status: str
    status_url: str


class Rejection(BaseModel):
    code: str
    message: str


class JobStatus(BaseModel):
    """status: queued | running | done | rejected | failed."""

    job_id: str
    status: str
    rejection: Rejection | None
    error: str | None
    analysis: AnalyzeResponse | None


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
