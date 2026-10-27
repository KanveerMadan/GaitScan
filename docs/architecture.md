# Architecture

This page describes the system as it is now. The decisions behind it are recorded as ADRs in
[`_audit/adr/`](../_audit/adr/); the table at the end says how each one was carried out.

```
 browser                                   Render web service (Docker, 1 uvicorn worker)
 ─────────────────────────  HTTPS  ┌───────────────────────────────────────────────────┐
  gaitscan-frontend (Vercel) ─────▶│ app/   FastAPI                                     │
  React 19, Vite, Router 7,        │  api/       auth, analysis (jobs), sessions,       │
  Tailwind v4 + shadcn/ui,         │             consent, privacy, shares, clinician    │
  client generated from            │  services/  PDF report (from the stored result),   │
  contracts/openapi.json           │             mailer (console / none)                │
  MediaPipe Tasks for Web:         │  core/      config, JWT, rate limits, JSON logs,   │
  live framing check only          │             Sentry                                 │
                                   │  db/        SQLAlchemy models ── Alembic 0001-0008 │
                                   │      │ imports                                     │
                                   │      ▼                                             │
                                   │ gaitcore/   pure analysis: no web, DB or file-     │
                                   │             layout imports (mypy strict)           │
                                   └───────────────┬───────────────────────────────────┘
                                                   │
                                   Postgres (Render)        local disk: the uploaded video,
                                                            only during its analysis
```

## An analysis, end to end
1. `POST /analyses` (JWT, current consent).
   - The upload is checked (extension, size cap), streamed to `data/raw/` and probed for frame rate
     and length.
   - Too-short or low-frame-rate files are turned down before the pose model runs.
   - Otherwise a row is added to `analysis_jobs` and the API answers **202** with a status URL.
2. A FastAPI background task runs the pipeline under a process-wide lock, so only one pose model runs
   at a time (Render's 512 MB) and the event loop stays free.
3. `gaitcore.pipeline`:
   1. `landmarks.extract_clip`: MediaPipe Tasks `PoseLandmarker`, pinned model, frames downscaled
      to 640 px. One row per frame, plus how many people were seen.
   2. `analyse`, the checks every test needs: length, frame rate, a person, upright.
   3. The walk: `signals` (visibility masking without filling, 6 Hz zero-phase low-pass) →
      `segments` (steady passes, averaged over the walker's own step time, minus stretches with a
      second person or no visible heel) → side-on checks → `gait` (label-free step events from
      heel separation; per-foot strikes for strides and knee angles) → step-count and regularity
      checks → `result` (units, the accuracy block, a quality block, versions, the model's SHA-256).
4. The video is deleted in a `finally:` block. An accepted result is stored as JSON in
   `sessions.result` with `pipeline_version`. A rejected one is stored on the job with its code and
   message.
5. The client polls `GET /analyses/{id}` until the job is `done` or `rejected`. PDFs are built on
   request from the stored result, never from files.

## Packages
| Package | Rule | Checks |
|---|---|---|
| `gaitcore/` | No FastAPI, DB or filesystem-layout imports; `__version__` and the model hash go into every result | mypy strict; synthetic-ground-truth tests; golden file |
| `app/` | Web layer; may import `gaitcore` | mypy; API, access-control and migration tests (SQLite + Postgres) |
| `evaluation/` | Offline: `make evaluate`, degradation curves, reliability model | its results are checked against `gaitcore/accuracy.py` |

## Data
Alembic owns the schema (`alembic/versions/`):

| Migration | Change |
|---|---|
| 0001 | Idempotent baseline of the pre-Alembic database |
| 0002 | Session mode |
| 0003 | Old values archived to `session_archive`; `pipeline_version` and `result` added |
| 0004 | `analysis_jobs` |
| 0005 | Session notes and tags |
| 0006 | `consents` |
| 0007 | `auth_tokens` (reset and verification) |
| 0008 | `share_links` |

Every migration is additive and runs before uvicorn starts. Nothing about a video is kept except
the measurements derived from it.

## Contract between the repos
`tests/test_contract.py` writes the OpenAPI schema to `contracts/openapi.json`. The frontend keeps a
byte-identical copy and generates `src/api/schema.d.ts` from it (`npm run gen:api`). CI in both
repos fails when either copy drifts.

## Decisions (ADRs), as built
| ADR | Decision | As built |
|---|---|---|
| 001 | Modular monolith with a framework-free analysis package | As decided: `gaitcore/`; no separate worker process |
| 002 | Postgres-backed job queue + worker | Superseded: a FastAPI background task plus status polling (`analysis_jobs` holds status, not a queue) |
| 003 | Object storage with lifecycle deletion | Superseded: the video is a temp file deleted after its analysis; nothing else is stored as a file |
| 004 | Clinic-scoped multi-tenancy | Superseded: user accounts; clinicians link to patients through expiring invite codes |
| 005 | Measurement summary + quality gates instead of a risk score | As decided, with the V3 metric policy: no reference ranges for angles; error ranges from LJMU |
| 006 | Measurement pipeline v2 | As decided, plus label-free cadence (heel separation), the LJMU-chosen side-on and step-regularity checks, and the step-sized steadiness window |
| 007 | Consent, retention, deletion; no LLM on health data | Consent, export and deletion built; LLM removed; no scheduled purge (data kept until the user deletes it) |
| 008 | Vite, React Router, generated client | As decided, with polling instead of TanStack Query; Tailwind v4 + shadcn/ui |

## Limits of this design
- **One worker, in-process rate limits, a process-wide pose lock.** These are right for a single
  free-tier instance. Scaling out needs the limits in Postgres or Redis, and a real job queue.
- **Analysis time.** About 1 s per second of video, measured locally
  (`loadtest/analysis_time.py`). Uploads are capped by size, not duration.
