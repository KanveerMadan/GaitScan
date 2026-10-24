# Architecture

Decisions are recorded as ADRs in [`_audit/adr/`](../_audit/adr/) (kept beside the audit and
rebuild plan they reference). This page describes the system **as it is now** (Plan V3 Phase 2).

```
 browser (Vercel, React)                Render web service (Docker, 1 uvicorn worker)
 ───────────────────────   HTTPS    ┌──────────────────────────────────────────────┐
  gaitscan-frontend  ─────────────▶ │ app/  FastAPI                                 │
                                    │  api/       routers: auth, analysis,          │
                                    │             sessions, clinician               │
                                    │  services/  PDF report (from stored result)   │
                                    │  schemas.py typed responses                   │
                                    │  core/      config, security (JWT), rate      │
                                    │             limits, JSON logging, Sentry      │
                                    │  db/        SQLAlchemy models ── Alembic      │
                                    │      │                                        │
                                    │      ▼ imports                                │
                                    │ gaitcore/  pure analysis (no web/DB imports)  │
                                    │  landmarks → signals → segments → gait →      │
                                    │  quality gate → result (pipeline 2.0.0)       │
                                    └──────────────┬───────────────────────────────┘
                                                   │
                                   Postgres (Render)   local disk: data/raw only (deleted
                                                       after each run)
```

## Request flow: `POST /analyze`
1. Auth (JWT) → upload validated (extension, size cap) and streamed to `data/raw/`.
2. `gaitcore.pipeline`: `probe` (fps, duration) → `landmarks.extract_clip` (MediaPipe Tasks, a row
   per frame, people count) → `analyse`: quality gate → `signals` (visibility masking, 6 Hz
   zero-phase filter) → `segments` (steady passes) → `gait` (bilateral heel strikes, per-step and
   per-stride values) → `result` (units, quality block, versions).
3. Rejected clips return 422 `{code, message}` and are not stored. Accepted results are stored as
   JSON in `sessions.result` with `pipeline_version`.
4. The raw video is deleted in a `finally:` block.

This still runs inside the request, in FastAPI's thread pool. Plan V3 Phase 4 makes it a background
task with a status endpoint.

## Packages
| Package | Rule | Type checking |
|---|---|---|
| `gaitcore/` | No FastAPI, DB or filesystem-layout imports; `__version__` for traceability (ADR-001) | mypy strict |
| `app/` | Web layer; may import `gaitcore` | mypy default |

## Data
Schema is owned by Alembic (`alembic/versions/`). `0001` is an idempotent baseline that adopts the
pre-Alembic `create_all` database and reconciles its known historical drift; `0002` added
`sessions.mode`; `0003` archives every removed value (mode, scores, findings, exercises) into
`session_archive`, then drops those columns/tables and adds `pipeline_version` + `result`. The
container runs `alembic upgrade head` before serving.

## Security controls (current)
JWT secret from env (startup fails without a strong one) · roles never client-assigned · ownership
checks on session/report endpoints · CORS allow-list · docs off outside dev · generic 500s ·
rate limits on login/registration keyed by a proxy-aware client IP (`app/core/ratelimit.py`) ·
JSON logs with redaction and SQL parameters hidden · bcrypt password hashes.

## Planned (see `_audit/REBUILD_PLAN_V3.md`)
Phase 3 accuracy check against public lab data, error ranges, results/PDF redesign · Phase 4
non-blocking analysis, capture guidance, frontend split · Phase 5 consent, deletion, export.
