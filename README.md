# GaitScan — Backend

Measures how you walk from a phone video: cadence and step time, with error ranges from a published
accuracy check. FastAPI + MediaPipe Pose. The web app is in
[gaitscan-frontend](https://github.com/KanveerMadan/gaitscan-frontend).

> **Not a medical device.** GaitScan is an experimental measurement tool. It does not diagnose
> conditions or predict outcomes, and its measurements have not been clinically validated.

## What it measures
| Measurement | Status | Error range (95% of LJMU clips within) |
|---|---|---|
| Cadence (steps/min) | Validated on LJMU | ±4.5 steps/min |
| Step time (s) | Validated on LJMU | ±0.024 s |
| Peak knee flexion per stride, per leg (°) | **Not yet validated** (no knee-angle reference) | — |
| Step length (m), walking speed (m/s) | **Not yet validated**; only with a floor calibration | — |

Cadence and step time come from heel-separation peaks, which don't depend on left/right leg labels.
Every value is from the steady part of each walk across the frame; turns, speeding up and slowing
down are left out. How the numbers were checked, and where they fail, is in the
[model card](docs/model-card.md).

Before measuring, the **recording checks** turn down videos that can't be measured, with a reason the
user can act on. Reasons include too short, a low frame rate, nobody in view, a rotated picture,
not side-on, too few or irregular steps, or the legs not followed. A second person, or heels out of
view, for a step or more removes only that stretch.

Not measured, by design: risk or composite scores, symmetry indices, activity labels, ankle or
frontal-plane angles, uncalibrated distances, exercise advice.

## How to film
Side-on, landscape, phone still at waist height 3–4 m from the walking line, 30 fps; walk across the
frame and back for 10–20 s. Details and the reasons behind them:
[docs/capture-protocol.md](docs/capture-protocol.md).

## Run it locally
Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                  # .venv from uv.lock
uv run python gaitcore/model.py fetch    # pinned pose model (SHA-256 checked) -> gaitcore/models/
cp .env.example .env                     # ENV=dev works as is
uv run alembic upgrade head              # SQLite in dev
uv run uvicorn app.main:app --reload --env-file .env
```

API docs: http://localhost:8000/docs (only with `ENV=dev`).

**macOS (Apple silicon):** MediaPipe 1.0.1 aborts during pose extraction ("Service is unavailable").
Anything that decodes video runs in the Docker image (Linux), which is also what production runs:

```bash
docker build -t gaitscan-api .
docker run -p 8000:8000 --env-file .env gaitscan-api   # migrations, then uvicorn
```

Tests use synthetic landmarks and run anywhere.

## Checks
```bash
ENV=dev uv run pytest                               # ~300 tests (SQLite)
TEST_POSTGRES_URL=postgresql://... uv run pytest     # + migrations on Postgres (CI does this)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pre-commit install                            # the same on every commit
```

What the suites rely on:
- **Synthetic ground truth.** `tests/synthetic.py` simulates a walker whose heel strikes, cadence,
  step length and knee angles are known exactly.
- **Golden file.** `tests/golden/v2_pipeline.json` pins the whole output. After an intended change,
  regenerate it with `ENV=dev uv run python tests/test_golden.py --regenerate` and say so in the
  commit.

## Accuracy check (`make evaluate`)
Uses the LJMU gait dataset (Topham et al. 2023, *Scientific Data*, CC BY 4.0). Videos and landmarks
stay outside git.

```bash
make fetch-ljmu                       # side-view videos -> data/ljmu/videos
make evaluate                         # -> evaluation/results/ljmu_clips.csv, ljmu_summary.json
```

`tests/test_accuracy.py` fails if the error ranges the API shows (`gaitcore/accuracy.py`) drift from
the latest summary. `evaluation/degrade.py` runs the degradation curves, and
`evaluation/reliability.py` runs the reliability-model evaluation
([write-up](docs/reliability-engine.md)).

## Configuration and deployment
- **Configuration.** Every variable is described in [.env.example](.env.example). Outside `ENV=dev`
  the app refuses to start without a strong `JWT_SECRET`, `CORS_ORIGINS` and `DATABASE_URL`.
- **Deployment.** Render, from [render.yaml](render.yaml): a Docker web service with one uvicorn
  worker and the health check `/healthz`. The container runs `alembic upgrade head` before
  starting.

## API
| Method | Path | Who |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | anyone (rate-limited) |
| GET · POST | `/auth/me` · `/auth/change-password` | signed in |
| POST | `/auth/recover` (email + recovery code + new password) | anyone (rate-limited) |
| POST | `/auth/recovery-codes` (a new set; needs the password) | signed in |
| POST | `/auth/password-reset`, `/auth/password-reset/confirm`, `/auth/verify-email`, `/auth/verify-email/request` | unused: answer 503 while no email is sent (`MAIL_BACKEND=none`) |
| GET · POST · DELETE | `/consent` | signed in |
| POST · GET | `/analyses` (202) · `/analyses/{job_id}` (poll) | signed in, with consent |
| POST | `/analyze` (synchronous; for scripts, the app uses `/analyses`) | signed in, with consent |
| GET · PATCH · DELETE | `/sessions`, `/sessions/{id}` (PATCH: notes, tags) | owner; a linked clinician can read |
| GET | `/report/{id}` (PDF) | owner or linked clinician |
| GET · POST · DELETE | `/sessions/{id}/shares`, `/shares/{share_id}` | owner |
| POST | `/shared` (open a share link) | anyone with the token (rate-limited) |
| GET · DELETE | `/me/export`, `/me` | signed in |
| POST · GET | `/clinician/invite`, `/clinician/patients`, `/clinician/patients/{id}/sessions` | clinician |
| POST | `/patient/join` | patient (rate-limited) |
| GET | `/healthz` | anyone |

The OpenAPI contract is committed at `contracts/openapi.json`. The frontend generates its client from
it, and CI in both repos fails on drift.

## More
- [Architecture](docs/architecture.md)
- [Model card](docs/model-card.md)
- [Security and threat model](SECURITY.md)
- [Audit findings](docs/findings.md)
- [Changelog](CHANGELOG.md)
- [Case study](docs/case-study.md)
- [Contributing](CONTRIBUTING.md)
