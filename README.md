# GaitScan — Backend

Video-based gait **measurement** API (FastAPI + MediaPipe Pose).

> **Not a medical device.** GaitScan is experimental. It does not diagnose conditions or predict
> injury, and its measurements have **not been clinically validated** (see Known limitations).
> A qualified clinician should interpret any output.

## What it does today
- Accepts a video upload (`.mp4`, `.mov`, `.avi`; size-capped), runs MediaPipe Pose on every frame
  and deletes the raw video afterwards.
- Computes 2D joint angles (knee, hip) and whole-clip summary measurements: knee/hip left–right
  symmetry index, knee flexion range, cadence.
- Compares them with mode-specific reference ranges (Clinical, Runner, Athlete, Elderly) and returns
  per-metric findings worded as measurements, plus a PDF report.
- Optional exercise suggestions from a fixed template list; LLM phrasing via Groq is **off** unless
  `ENABLE_LLM_EXPLANATIONS=true` (it sends the measurement summary to Groq).
- Accounts with JWT auth, patient/clinician roles (clinicians are promoted by an admin, never
  self-assigned), invite codes linking patients to a clinician.

## Video capture protocol
The current pipeline measures 2D angles in the image plane, so results are only meaningful for
recordings that follow this protocol. Other views produce wrong numbers without warning until the
Phase 2 quality gate lands.

1. **Side view.** The camera points at a right angle to the walking direction. Frontal or diagonal
   views distort knee and hip angles (a true 60° reads as 45° at 45° yaw in our probe).
2. **Landscape** orientation.
3. **Full body in frame** for the whole clip, head to feet, including the feet at the start and end
   of each pass. Only **one person** in view.
4. **Distance:** about **3–4 m** from the walking line, camera fixed (tripod or steady surface) at
   roughly hip height. Mark a straight **walkway of at least 5 m**, so the steps measured in the
   middle are at a steady pace. This distance is a guideline for a typical phone camera; it has not
   been validated yet (Phase 5).
5. Plain background, good even light, fitted clothing; walk at a self-selected pace, at least
   **10 seconds** of walking, no turns in the clip.

## Known limitations
- No accuracy figures exist for any metric yet: there is no ground truth or validation set (audit
  F22, plan Phase 5).
- Cadence counts threshold crossings of one knee and under-reads (synthetic 110 steps/min reads ~54);
  angles are aspect-distorted on non-square frames; no visibility gating, smoothing or input quality
  gate. All are fixed in **Phase 2** (ADR-006). The audit tests in `_audit/tests/` pin the expected
  behaviour and fail until then.
- Analysis runs synchronously inside the request (blocks the API for the clip's duration) and
  artifacts live on local disk; both move to a worker + object storage in **Phase 3**.

## Architecture
See [docs/architecture.md](docs/architecture.md). In short: one deployable, two packages:
`gaitcore/` (pure analysis, no web/DB imports) and `app/` (FastAPI routers, services, DB).

## Local setup
Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # creates .venv from uv.lock
cp .env.example .env             # ENV=dev works without further edits
uv run alembic upgrade head      # creates/updates the database (SQLite in dev)
uv run uvicorn app.main:app --reload --env-file .env
```

Open http://localhost:8000/docs (interactive docs are only served when `ENV=dev`).

### Tests and checks
```bash
uv run pytest                    # app tests (SQLite)
TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/gaitscan_test uv run pytest  # + Postgres
uv run pytest _audit/tests       # audit spec: expected failures until Phase 2
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pre-commit install        # run the same checks on every commit (needs git >= 2.35)
```

### Docker
```bash
docker build -t gaitscan-api .
docker run -p 8000:8000 --env-file .env gaitscan-api   # runs migrations, then uvicorn
```

## Configuration
Every variable is documented in [.env.example](.env.example). Outside `ENV=dev` the app refuses to
start without a strong `JWT_SECRET`, an explicit `CORS_ORIGINS` list and `DATABASE_URL`.

## Deployment
Render, from [render.yaml](render.yaml) (Docker web service, health check `/healthz`). The container
runs `alembic upgrade head` before starting uvicorn.

## Endpoints
| Method | Path | Auth |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | — (rate-limited) |
| GET | `/auth/me` | user |
| POST | `/auth/change-password` | user |
| POST | `/analyze` | user |
| GET | `/sessions`, `/sessions/{id}`, `/report/{id}` | owner or linked clinician |
| POST | `/clinician/invite` · GET `/clinician/patients`, `/clinician/patients/{id}/sessions` | clinician |
| POST | `/patient/join` | patient |
| GET | `/healthz` | — (checks the database) |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.
