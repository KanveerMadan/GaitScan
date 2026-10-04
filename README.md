# GaitScan — Backend

Video-based gait **measurement** API (FastAPI + MediaPipe Pose).

> **Not a medical device.** GaitScan is experimental. It does not diagnose conditions or predict
> injury, and its measurements have **not been clinically validated** (see Known limitations).
> A qualified clinician should interpret any output.

## What it does today
- Accepts a side-view walking video (`.mp4`, `.mov`, `.avi`; size-capped), runs the MediaPipe pose
  model (pinned `pose_landmarker_full` float16/1, MediaPipe 1.0.1) and deletes the raw video afterwards.
- Runs a **quality gate** first. A clip with more than one person, hidden feet, a rotated picture,
  a non-side view, too little steady walking, under 24 fps or under 3 s gets no numbers, only a
  specific reason and what to change.
- Measures, from the steady walking passes only (turns, standing and acceleration excluded):
  - cadence (steps/min, from heel strikes of both feet), step time and stride time per leg (s);
  - peak knee flexion per stride, per leg (deg, median ± SD);
  - hip sagittal excursion per stride (thigh angle range, deg);
  - step length (m) and walking speed (m/s) **only** when a floor calibration is given: two points
    on the floor, a known distance apart, in video pixels (`calib_x1/y1/x2/y2`, `calib_distance_m`).
- Every result carries units, a recording-quality block (frames used, steps and strides detected,
  passes, frame rate) and the pipeline/model versions. A PDF is built from the stored result.
- Not measured, by design (see `_audit/REBUILD_PLAN_V3.md` §2): any risk or composite score,
  activity labels, left/right symmetry indices, ankle angles, frontal-plane angles, uncalibrated
  distances, exercise suggestions. Sessions analysed before this version are listed as "legacy"
  without measurements; their old values are archived, not shown.
- Accounts with JWT auth, patient/clinician roles (clinicians are promoted by an admin, never
  self-assigned), invite codes linking patients to a clinician.

## Video capture protocol
The pipeline measures 2D angles in the image plane, so results are only meaningful for recordings
that follow this protocol. The quality gate rejects the clearest violations, not all of them.

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
- **No accuracy figures yet.** The pipeline is checked against synthetic ground truth only; its error
  against lab motion capture is measured in Plan V3 Phase 3 (audit F22). No error ranges are shown.
- Side view, one person, steady overground walking only. Treadmill walking is not supported (the
  pelvis must move across the frame).
- The far leg is partly hidden in a side view; its values carry their own stride count and may be
  missing.
- A short pass across a narrow (portrait) frame may contain no complete step; such clips are
  rejected as too little walking.
- Analysis still runs inside the request (one at a time); Plan V3 Phase 4 makes it non-blocking.
- On macOS arm64, MediaPipe 1.0.1 cannot run pose extraction (see Local setup); use Docker.

## Architecture
See [docs/architecture.md](docs/architecture.md). In short: one deployable, two packages:
`gaitcore/` (pure analysis, no web/DB imports) and `app/` (FastAPI routers, services, DB).

## Local setup
Requires Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                          # creates .venv from uv.lock
uv run python gaitcore/model.py fetch   # pinned pose model (9.4 MB, SHA-256 checked) -> gaitcore/models/
cp .env.example .env             # ENV=dev works without further edits
uv run alembic upgrade head      # creates/updates the database (SQLite in dev)
uv run uvicorn app.main:app --reload --env-file .env
```

Open http://localhost:8000/docs (interactive docs are only served when `ENV=dev`).

### Tests and checks
```bash
uv run pytest                    # app tests (SQLite)
TEST_POSTGRES_URL=postgresql://user:pass@localhost:5432/gaitscan_test uv run pytest  # + Postgres
uv run pytest _audit/tests       # audit spec (amended for V3; passes)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pre-commit install        # run the same checks on every commit (needs git >= 2.35)
```

Pose extraction on **macOS arm64** aborts inside mediapipe 1.0.1 (a Metal-only calculator,
"Service is unavailable", even with the CPU delegate). Run anything that decodes video in the Docker
image (Linux, CPU), which is also what production runs. Tests use synthetic landmarks and run anywhere.

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
