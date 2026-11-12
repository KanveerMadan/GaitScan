# Audit findings: final status

The technical audit (`_audit/GAITSCAN_AUDIT.md`, 2026-09-27) listed 44 findings. Each one is now
**closed** (fixed, with a test or probe) or **accepted** (deliberately left open, with the reason).
Commits are in this repository unless marked *(frontend)*. Probe outputs are in `_audit/probes/`; the
Phase 5 re-run is the `*_phase5.txt` files (API security probe: 15/16 PASS, the one FAIL is F12).

| # | Finding | Status | How | Evidence |
|---|---|---|---|---|
| F01 | JWT secret hardcoded and committed | Closed | Secret only from the environment; startup fails without a strong one; old values treated as public | `679164a`; `tests/test_config.py`; probe F01 ×2 PASS |
| F02 | No auth or ownership on sessions and reports | Closed | Auth + owner-or-linked-clinician check on every session, report and share route | `315a654`; `tests/test_access_control.py`; probe F02 ×2 PASS |
| F03 | Anyone can register as a clinician | Closed | Client-supplied role ignored; `/debug/links` removed | `58831bb`; probe F03 PASS |
| F04 | Plaintext password printed on registration | Closed | Print removed; JSON logging with redaction; `print` banned by lint | `679164a`, `d792c67`; probe F04 PASS |
| F05 | Frontend stores email + password in `localStorage` | Closed, part accepted | Password never stored; token not logged. The access token is still in `localStorage` (see SECURITY.md); accepted by the owner 2026-11-12 | `f7956ee` *(frontend)* |
| F06 | No consent, retention or deletion; video kept on failure; data sent to Groq | Closed, part accepted | Consent before the first analysis; export and deletion; video deleted in `finally:`; LLM removed. No scheduled purge: data is kept until the user deletes it, as the Privacy page now states (owner decision 2026-11-12) | `8048daf`, `c021909`, `82df61b`; probe F06/F07 PASS |
| F07 | Upload validation is a case-sensitive extension check | Closed | Case-insensitive allow-list, streamed size cap, decoded before analysis, generic 422 | `a1e511f`; probe F06/F07 PASS |
| F08 | CORS `*`, token logged, 365-day tokens | Closed | CORS allow-list; 12-hour tokens; password change ends other logins | `78ff1e1`, `47c11db`; probe F08 ×2 PASS |
| F09 | Internal errors returned; Swagger public | Closed | Generic errors with a reference; `/docs` only in dev | `78ff1e1`, `a1e511f`; probe F09 PASS |
| F10 | No rate limiting; guessable, non-expiring invites | Closed | Sliding-window limits keyed on a spoof-resistant client IP; `secrets` invite codes, 7-day expiry, join limit | `236777b`, `89f08e8`, `5a326af`; probe F10 PASS |
| F11 | 40 Python + 48 npm advisories | Closed | PyJWT, upgraded stack, Vite, MediaPipe 1.0.1; `pip-audit` / `npm audit` in CI; Dependabot | `f2c646c`, `21ec11f`, `a5e598a`; `96ebe3c` *(frontend)* |
| F12 | Account enumeration; no password policy | Part accepted | 10-character minimum and equal-cost login done. Sign-up still says when an email is taken: closing it needs verified sign-up by email, and GaitScan sends no email (no domain; owner decision 2026-10-31) | `236777b`; probe F12 FAIL (accepted) |
| F13 | Analysis blocks the event loop | Closed | Background task + status polling; `/status` max 0.03 s during an analysis (was 28.7 s) | `83dcd5e`; `out_concurrency_phase5.txt` |
| F14 | Peak memory near the 512 MB instance | Closed | Frames downscaled to 640 px before the pose model; one pose run per process; peak RSS test (≤ 420 MB for 10 s of 1080p60) | `21ec11f`, `56347cf`; `tests/test_memory.py` |
| F15 | Artifacts on ephemeral disk; regenerated PDF loses data | Closed | Results stored as JSON with `pipeline_version`; PDF built from the stored result | `82df61b`, `00f81d4` |
| F16 | Unpinned deps, no lockfile, no Dockerfile | Closed | `pyproject.toml` + `uv.lock`; Dockerfile; `render.yaml` | `f2c646c`, `b90ffdf` |
| F17 | No migrations; silent SQLite fallback | Closed | Alembic (idempotent baseline); `DATABASE_URL` required outside dev | `d9f6f1c`; `tests/test_migrations.py` |
| F18 | Tracked database file, stray files, `.gitignore` typo | Closed | Database untracked, stubs deleted, ignore fixed | `38c8db3`, `e47fd9b`, `ee86286` |
| F19 | matplotlib backend never set | Closed | `Agg` selected; server-side plots later removed with the old PDF | `6b28629`, `82df61b` |
| F20 | Unescaped text crashes the PDF build | Closed | All interpolated text escaped | `2cd1474` |
| F21 | 42 s cold start on Render | Accepted | Free-tier instance. Polling with timeouts tolerates it. Owner decision 2026-11-12: an external uptime check calls `GET /healthz` every 10 minutes to keep it awake; `/healthz` is one `SELECT 1` (tests/test_healthz.py) | — |
| F22 | No ground truth or accuracy numbers | Closed | `make evaluate` on LJMU (Topham et al. 2023): cadence ±4.5 steps/min, step time ±0.024 s (95%); knee, step length, speed labelled not yet validated | `7dd653e`, `4f06451`; [model card](model-card.md) |
| F23 | Invented "risk score" | Closed | Removed; measurements only | `82df61b`; `03286dd` *(frontend)* |
| F24 | Cadence from one knee crossing 155° | Closed | Label-free step events from heel separation, both feet | `3f9eae5`, `d201767` |
| F25 | Angles on normalised coordinates | Closed | Angles in pixel space | `3f9eae5` |
| F26 | No visibility gating, smoothing, quality or multi-person handling | Closed | Visibility masking without filling; 6 Hz zero-phase filter; recording checks; frames with two people masked | `3f9eae5`, `d8aec1e` |
| F27 | Knee flexion = 180 − min over the clip | Closed | Per-stride peak, median across strides; knee angle then removed entirely on 2026-11-12 (Phase 8 cancelled) | `3f9eae5` |
| F28 | Symmetry index on mean angles | Closed | Symmetry indices removed | `82df61b`; `03286dd` *(frontend)* |
| F29 | View-dependent angles; "any angle" claims | Closed | Side-on view required: shoulder-width and path-convergence checks | `3f9eae5`; `out_view_dependency_phase5.txt` |
| F30 | Activity classifier of hand thresholds | Closed | Removed | `82df61b`; `03286dd` *(frontend)* |
| F31 | Duration and fps from detected frames | Closed | Container fps and frame indices | `3f9eae5` |
| F32 | Full-resolution legacy MediaPipe API | Closed | MediaPipe Tasks 1.0.1, pinned model (SHA-256), 640 px long side | `21ec11f` |
| F33 | Dead `shoulder_tilt` | Closed | Deleted | `3f9eae5` |
| F34 | "Hip flexion" is the trunk–thigh angle | Closed | Hip measure redefined, then withheld until it can be validated | `3f9eae5`, `62f7e1e` |
| F35 | Contradictory threshold tables | Closed | Removed with the scores; one source (the API) for everything shown | `82df61b`; `03286dd` *(frontend)* |
| F36 | Diagnostic and injury language | Closed | Measurement wording; banned-phrase tests in the frontend | `cb1a1ef`, `265aabe`, `69ebd67` |
| F37 | "RAG" overclaim; blocking LLM call | Closed | LLM made opt-in, then removed | `2367d0f`, `82df61b` |
| F38 | Zero tests | Closed | ~300 backend tests (synthetic ground truth, golden file, API, migrations); ~60 frontend unit + Playwright e2e | `437a0f1`; CI in both repos |
| F39 | 1,100-line `App.js`, CRA, no router or a11y | Closed | Vite, React Router, typed client from the OpenAPI contract, design system, axe checks | `96ebe3c`, `8105c82` *(frontend)* |
| F40 | Patient name missing; clinicians can't upload | Closed, part accepted | The name (or the account holder's) is on sessions and PDFs. Clinicians uploading for a patient is not built; accepted by the owner 2026-11-12 | `62cf428`; probe F40 PASS |
| F41 | `print` logging; no error tracking; poor commit messages | Closed | JSON logging, Sentry (opt-in), Conventional Commits | `3908373`, `d792c67` |
| F42 | Epsilon in angle denominators | Closed | Zero-length vectors give NaN | `3f9eae5` |
| F43 | Unused imports | Closed | ruff in pre-commit and CI | `f385e5c`, `99a88f8` |
| F44 | Every upload saved as `.mp4` | Closed | The real (allow-listed) extension is kept | `a1e511f` |
