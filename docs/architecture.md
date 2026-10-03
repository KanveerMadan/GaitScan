# Architecture

Decisions are recorded as ADRs in [`_audit/adr/`](../_audit/adr/) (kept beside the audit and
rebuild plan they reference). This page describes the system **as it is now** (Phase 1).

```
 browser (Vercel, React)                Render web service (Docker, 1 uvicorn worker)
 ───────────────────────   HTTPS    ┌──────────────────────────────────────────────┐
  gaitscan-frontend  ─────────────▶ │ app/  FastAPI                                 │
                                    │  api/       routers: auth, analysis,          │
                                    │             sessions, clinician               │
                                    │  services/  PDF report, plots, exercises,     │
                                    │             display wording                   │
                                    │  core/      config, security (JWT), rate      │
                                    │             limits, JSON logging, Sentry      │
                                    │  db/        SQLAlchemy models ── Alembic      │
                                    │      │                                        │
                                    │      ▼ imports                                │
                                    │ gaitcore/  pure analysis (no web/DB imports)  │
                                    │  landmarks (MediaPipe) → angles → activity →  │
                                    │  legacy scoring                               │
                                    └──────────────┬───────────────────────────────┘
                                                   │
                                   Postgres (Render)   local disk: data/raw (deleted
                                                       after each run), outputs/ (PDFs)
```

## Request flow: `POST /analyze`
1. Auth (JWT) → upload validated (extension, size cap) and streamed to `data/raw/`.
2. `gaitcore.landmarks.extract_landmarks` → `angles.add_all_angles` → `activity.classify_activity`
   → `legacy.calculate_risk_scores` (reference-range comparison).
3. `app.services` builds plots and the PDF; rows are written to `sessions`, `findings`, `exercises`.
4. The raw video is deleted in a `finally:` block.

This runs inside the request (blocking the event loop; audit F13). Phase 3 moves it to a
Postgres-backed job queue and a worker process (ADR-002) and artifacts to object storage (ADR-003).

## Packages
| Package | Rule | Type checking |
|---|---|---|
| `gaitcore/` | No FastAPI, DB or filesystem-layout imports; `__version__` for traceability (ADR-001) | mypy strict |
| `app/` | Web layer; may import `gaitcore` | mypy default |

## Data
Schema is owned by Alembic (`alembic/versions/`). `0001` is an idempotent baseline that adopts the
pre-Alembic `create_all` database and reconciles its known historical drift; `0002` adds
`sessions.mode`. The container runs `alembic upgrade head` before serving.

## Security controls (current)
JWT secret from env (startup fails without a strong one) · roles never client-assigned · ownership
checks on session/report endpoints · CORS allow-list · docs off outside dev · generic 500s ·
rate limits on login/registration keyed by a proxy-aware client IP (`app/core/ratelimit.py`) ·
JSON logs with redaction and SQL parameters hidden · bcrypt password hashes.

## Planned (see `_audit/REBUILD_PLAN.md`)
Phase 2 measurement core v2 (ADR-006) · Phase 3 jobs + object storage (ADR-002/003) · Phase 4
tenancy, refresh tokens, consent and deletion (ADR-004/007) · Phase 5 validation harness ·
Phase 6 measurement-summary report (ADR-005).
