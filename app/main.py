import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.analysis import recover_unfinished_jobs
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.clinician import router as clinician_router
from app.api.consent import router as consent_router
from app.api.google_auth import router as google_router
from app.api.inbox import router as inbox_router
from app.api.privacy import router as privacy_router
from app.api.profiles import router as profiles_router
from app.api.sessions import router as sessions_router
from app.api.settings import router as settings_router
from app.api.shares import router as shares_router
from app.core.config import settings
from app.core.logging import RequestLogMiddleware, configure_logging
from app.core.observability import init_sentry
from app.db import database

configure_logging()
init_sentry(settings.sentry_dsn, settings.env)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    recover_unfinished_jobs()
    yield


# Interactive docs and the OpenAPI schema are only exposed in dev.
_docs = settings.docs_enabled
app = FastAPI(
    lifespan=lifespan,
    title="GaitScan API",
    version="2.1.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)
app.include_router(auth_router)
app.include_router(clinician_router)
app.include_router(analysis_router)
app.include_router(sessions_router)
app.include_router(consent_router)
app.include_router(privacy_router)
app.include_router(shares_router)
app.include_router(settings_router)
app.include_router(google_router)
app.include_router(inbox_router)
app.include_router(profiles_router)

app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

os.makedirs("data/raw", exist_ok=True)


@app.get("/")
def root():
    return {"message": "GaitScan API is running", "version": "2.1.0"}


@app.get("/status")
def status():
    return {"status": "healthy", "message": "GaitScan is running"}


@app.get("/healthz")
def healthz() -> JSONResponse:
    """Render health check: the process is up and the database answers."""
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logging.getLogger("gaitscan").exception("health check: database unreachable")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})
