# ADR-001: Modular monolith with a framework-independent analysis package

**Status:** Accepted, amended by REBUILD_PLAN_V3.md (2026-10-03): no worker process; results record pipeline_version + model SHA-256 · **Date:** 2026-09-27

## Context
Pipeline code (`src/core/*`) is mixed with auth, ORM models and user-facing copy. `risk_scoring.py` holds thresholds, scoring and English text together. `main.py` does orchestration, persistence and serialisation (audit A1). Nothing is typed or versioned, so a stored result can't be traced to the code that produced it (B6). One solo developer maintains everything.

## Decision
Keep **one repo and one deployable backend**, split into two Python packages:
- `gaitcore/` is pure analysis: `analyse(video_path | landmarks, config) -> AnalysisResult` (Pydantic/dataclass). It has no FastAPI, no DB and no filesystem layout assumptions, and exposes `__version__` plus the model asset hash.
- `app/` is the web layer: `api/` (routers), `services/` (use cases), `schemas/` (Pydantic I/O), `db/` (SQLAlchemy models + Alembic), `worker/`, `core/config.py` (pydantic-settings).
Every stored result records `pipeline_version` and `model_sha256`.

## Consequences
- The pipeline can be unit-tested, golden-file-tested and run from a CLI/notebook for validation without the web stack.
- The worker imports `gaitcore` directly, so no HTTP hop is needed.
- No microservices: one image, two process types (web, worker).
- This costs a one-time move of files (~1 day) with import churn.
