from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.clinician import router as clinician_router
from app.api.sessions import router as sessions_router
from app.core.config import settings

# Interactive docs and the OpenAPI schema are only exposed in dev.
_docs = settings.docs_enabled
app = FastAPI(
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

os.makedirs("data/raw", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

@app.get("/")
def root():
    return {"message": "GaitScan API is running", "version": "2.1.0"}

@app.get("/status")
def status():
    return {"status": "healthy", "message": "GaitScan is running"}
