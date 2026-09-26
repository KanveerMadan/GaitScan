# GaitScan — Technical Audit

Audit date: 2026-09-27 · Backend `gaitscan` @ `5f34703` (53 commits) · Frontend `../gaitscan-frontend` @ `49759fe` (25 commits)
Everything under `_audit/` is new. No existing source file was modified.

**Artifacts produced by this audit**

| Path | What |
|---|---|
| `_audit/.venv/` | Python 3.11 venv built from `requirements.txt` (installs cleanly on macOS arm64) |
| `_audit/sandbox/` | Copy of `src/` used as the working dir for all runs, so the app's cwd-relative writes (`data/`, `outputs/`, `gaitscan.db`) never touch the repo |
| `_audit/probes/*.py` + `out_*.txt` | Probe scripts and their captured output |
| `_audit/tests/test_angles_audit.py` + `out_pytest.txt` | 18 synthetic unit tests (11 pass, 7 fail by design) |
| `_audit/fe_build/` | Production build of the frontend |
| `_audit/probes/contact_sheet.jpg` | Frame strip of the only sample clip (`data/raw/walk01.mp4`) |

**Assumptions** (stated, not verified)
- A1. Render plan is Free or Starter. Both are 512 MB RAM (Free about 0.1 CPU, Starter 0.5 CPU) per Render's published plans as I know them. `render.com/docs/free` confirmed the 15-minute spin-down and the ephemeral filesystem but gave no RAM/CPU numbers. **Verify in your dashboard.**
- A2. Production uses Postgres via `DATABASE_URL`. `psycopg2-binary` is in requirements, and commit `7d99464` "regenerate PDF from DB when file not on disk" only makes sense with a persistent DB and an ephemeral disk.
- A3. The frontend in `../gaitscan-frontend` is the Vercel app. It hardcodes `https://gaitscan.onrender.com` (`App.js:8`).
- A4. Timing numbers are from an Apple M3. Render vCPUs are slower. I estimate 4–8× wall-time on Starter (0.5 CPU); that is an estimate, not a measurement.

---

## 1. Executive Summary

**Verdict:** GaitScan is a working **demo-grade student prototype** with a **live security and privacy exposure**. The plumbing is real: upload → MediaPipe → angles → heuristics → PDF → React dashboard, deployed and reachable. But:

- The analysis numbers are not trustworthy. Cadence counts one leg plus jitter: a synthetic 110 steps/min walk reads 54 and is classified "Unknown". Angles are distorted by up to 30° on portrait video.
- The 0–100 "risk score" is an invented additive heuristic. It returned **0 "No issues detected"** for every probe I ran, including two people in frame (reported knee flexion 179.8°) and a sideways video.
- Anyone on the internet can forge a login for any user with the JWT secret committed in `src/core/auth.py:14`. They can also read any patient's results and PDF **without logging in**.

This is not SaaS-ready and should not be shown to a clinic as a "risk" tool today. The good news: the codebase is small (~2,000 LOC backend) and the fixes are well understood.

**Top 5 things to fix, in order**
1. **Stop the data exposure (hours, not days):** rotate the JWT secret into an env var, add auth + ownership checks to `/sessions/{id}` and `/report/{id}`, stop self-assigning the `clinician` role, delete `/debug/links`, stop printing passwords (`auth.py:22-23`), and stop storing plaintext passwords in `localStorage` (`App.js:56,107`).
2. **Reframe the output:** remove the "risk score", "abnormality", "injury risk" and "prescribed" language until validated. Show measured values with units, a quality/confidence indicator, and "screening, not diagnosis" framing.
3. **Fix the measurement core:** pixel-space angles, visibility gating + smoothing, real gait-event detection (both legs, hysteresis), robust percentiles instead of `min()`, and quality gates that refuse bad video.
4. **Move analysis off the request thread:** job queue + worker, object storage with TTL deletion, status polling. One upload currently freezes the entire server (measured: 28.7 s health-check stall).
5. **Build a validation harness** against a public gait dataset or goniometer measurements, and publish the error bars. Until then, no clinical claims.

---

## 2. What it's genuinely good at

- **End-to-end flow exists and is deployed.** The live `/status` returned 200 (after a 42 s cold start), `/openapi.json` lists 14 routes, and the Vercel build compiles (`_audit/fe_build`, 186 kB gz JS).
- **Local reproducibility of the pipeline is fine.** A clean Python 3.11 venv installs from `requirements.txt` with no errors. Two extractions of the same file gave identical landmarks (`max_abs_coord_diff = 0.0`, `out_stability.txt`).
- **The basic angle math is correct.** `angle_3pts` returns correct values for 45/90/120/180°, clips the `arccos` domain, works in degrees, and uses the correct MediaPipe left/right indices (tests `test_angle_known_values`, `test_arccos_domain_is_clipped`, `test_left_knee_uses_mediapipe_left_indices` pass).
- **Password hashing uses bcrypt** via passlib (`auth.py:18`), and SQLAlchemy ORM queries are parameterised: no SQL injection surface found.
- **Clinician→patient link endpoint checks ownership** (`clinician_router.py:156-162`). This is the one place authz was done right.
- **Graceful LLM fallback:** when Groq fails, exercises still render with a template sentence (`exercise_prescription.py:311-322`).
- **The PDF is visually structured** (tables, colour-coded status, thresholds shown). The information design instinct is there, even though the content is wrong (§6 A5).

---

## 3. What it's bad at (ranked)

1. 🔴 **Security:** committed JWT secret, verified forgery; unauthenticated IDOR on health data and PDFs; self-service clinician role; plaintext passwords in server logs and browser storage (F01–F05).
2. 🔴 **Privacy / DPDP:** no consent, no retention policy, no deletion, and biometric skeleton CSVs and PDFs kept indefinitely. Health findings are sent to a US LLM provider with no disclosure. Videos are left on disk whenever analysis fails (F06).
3. 🔴 **Scientific validity:** zero ground truth; invented risk score; wrong cadence; aspect-ratio distortion; no quality gates; view-dependent 2D angles sold as "any angle / CCTV" (F22–F30).
4. 🔴 **Architecture:** CPU-bound pipeline inside `async def` blocks the event loop; everything is stored on an ephemeral local disk; peak memory is at the instance limit (F13–F15).
5. 🟠 **Engineering hygiene:** zero tests, no CI, no migrations, no Docker, unpinned and duplicated deps, 40 known Python advisories, 48 npm advisories, and 24 of 53 backend commits named `feat: c` or similar (F11, F16–F18, F38, F41).
6. 🟠 **Product:** a clinician cannot upload for a patient; patient name is never sent; thresholds shown in UI, PDF and scoring contradict each other; no responsive layout or accessibility (F35, F39, F40).

---

## 4. Things that make no sense

1. **Commit `5f34703` "chore: remove database file from tracking"** deleted two stray curl artifacts named `-H` and `-d` (the latter contains a FastAPI 422 body). `gaitscan.db` **is still tracked** (`git ls-files` lists it).
2. **The PDF regeneration path silently changes the report.** A session analysed in Runner mode regenerates as "Clinical Mode" (no `mode` column in `models.py:6-24`) and loses all charts. Probe: `regenerated PDF reports wrong mode … 'Runner' in pdf=False; charts in pdf=False` (`out_api_security.txt`). Because Render's disk is ephemeral, this is the **normal** path after any deploy.
3. **Three threshold tables that disagree** for the same metric:
   - Clinical-mode knee flexion flags at <45° in scoring (`risk_scoring.py:7`) but is "normal >50°" in the PDF (`report_generator.py:21,64`). The frontend colours it red at ≤50° regardless of mode (`App.js:307-308`).
   - Elderly SI flags at 25% (`risk_scoring.py:51`); the frontend paints ≥20% red (`App.js:302-303`).
   - The PDF's own status column uses `good*2` (`report_generator.py:234-237`), which does not match the flag thresholds (Runner: 16 vs 15).
4. **Two different labels for the same score.** The API says "No issues detected"/"Minor findings" (`risk_scoring.py:272-279`); the PDF says "Low Risk" for the same 0–25 (`report_generator.py:115-117`).
5. **Unreachable score band.** The maximum achievable score is 80 (30+20+20+10). "Limping", the most severe detection, **caps at 75** because the cadence term is skipped for it (`risk_scoring.py:199-213, 249`). So a limp can never be "Serious abnormality", but a stiff walker with slow cadence can.
6. **Runner-mode "Brisk Walking" is always under target.** The classifier only emits Brisk Walking for cadence in roughly 120–150 (`activity_classifier.py:57-67`), while Runner mode's healthy range is 150–170 (`risk_scoring.py:27`). Every Runner-mode brisk walk is by construction "lower than ideal".
7. **The limp rule's second condition is always true.** `cadence_irregularity > 25` (`activity_classifier.py:46`), but the healthy sample clip scores 50.4 (`out_profile_walk01.txt`). So "Limping" hinges on asymmetry alone.
8. **`patient_name`** is accepted by `/analyze` (`main.py:55`), stored, and listed in the UI, but the frontend never sends it (`App.js:277-279`). Every session shows "Anonymous — Walking" (`App.js:685`), and the name never appears on the PDF.
9. **`shoulder_tilt`** is computed for every frame (`calculate_angles.py:30-31,40`), never used, and is direction-dependent (level shoulders = 0° or 180° depending on walking direction; test fails).
10. **`/debug/links`** ships in production (`clinician_router.py:190-196`) and returns every clinician–patient link in the database.
11. **Duplicated logic:** the cadence counter exists twice (`activity_classifier.py:12-15`, `risk_scoring.py:238-244`); knee-SI twice (`activity_classifier.py:24-26`, `risk_scoring.py:93-95`); `require_clinician` twice (`auth.py:62-65`, `auth_router.py:70-76`); session serialisation three times (`main.py:233-247, 255-283`, `clinician_router.py:175-188`).
12. **Empty files:** `main.py` (root, 0 bytes), `tests/test_angles.py` (0 bytes), `notebooks/` (empty).
13. **Dead dependencies:** `scikit-learn`, `sounddevice`, `joblib` (never imported), and **three** OpenCV distributions at two versions (`opencv-python 4.13`, `opencv-contrib-python 4.13`, `opencv-python-headless 4.9`) all writing the same `cv2` package.
14. **`runtime.txt`** is a Heroku convention. Render selects Python via `PYTHON_VERSION` or `.python-version` [verify], so this file probably does nothing. The actual start command is not in the repo at all.
15. **The "RAG pipeline"** in the README is a tag lookup over a hardcoded 19-item list (`exercise_prescription.py:4-195, 198-246`). The LLM only writes one "why" sentence per exercise. Nothing is retrieved by embedding or search.
16. **The frontend "Download report" is a plain `<a href>`** (`App.js:484,705,917`). It cannot carry a bearer token, which is almost certainly why `/report/{id}` has no auth.
17. **The frontend saves `gaitscan_creds` (email + plaintext password)** on every login/register (`App.js:56,107`) and **never reads it**. It exists only to leak.
18. **The upload UI promises "Phone, CCTV, sports footage · Any angle"** (`App.js:418`). The math is 2D sagittal-only (§7 B2).

---

## 5. Findings table

Severity: 🔴 Critical / 🟠 High / 🟡 Medium / ⚪ Low. Effort: S <2h, M <1 day, L multi-day.

| ID | Area | Sev | Eff | Finding | Evidence | Recommended fix |
|---|---|---|---|---|---|---|
| F01 | Security | 🔴 | S | JWT secret hardcoded and committed; 4 historical values in git | `src/core/auth.py:14`; `git log -p src/core/auth.py` shows 4 distinct committed values (redacted here; treat all as public). Probe: forged token → `/auth/me` returned victim, `/sessions` returned victim data (`out_api_security.txt`) | `JWT_SECRET` from env, fail startup if missing; rotate; treat all old values as public |
| F02 | Security | 🔴 | M | No auth / ownership on `GET /sessions/{id}` and `GET /report/{id}`; IDs are 8 hex chars (32 bits) | `main.py:166-167, 250-252, 67`. Probe: unauthenticated GET returned patient name + 4 findings; PDF 617 kB | Require auth + ownership/clinician-link check; UUID4 full IDs; frontend fetches PDF as blob or via short-lived signed URL |
| F03 | Security | 🔴 | S | Any registrant can choose `role: clinician` | `auth_router.py:16, 34-41`; frontend role picker `App.js:139-150`. Probe: `201 role=clinician` with password `a` | Role not client-settable; clinicians created by invite/admin within an org |
| F04 | Security | 🔴 | S | Plaintext password printed on every registration | `auth.py:22-23`; found in `_audit/sandbox/uvicorn.log`: `PASSWORD RECEIVED: pw12345678` | Delete lines; purge Render logs; structured logger with redaction |
| F05 | Security | 🔴 | S | Frontend stores email + plaintext password in `localStorage`; never used | `App.js:56, 107` (removed only on logout `App.js:26`) | Delete; also move token out of `localStorage` long-term (httpOnly cookie) |
| F06 | Privacy | 🔴 | L | No consent, retention, deletion or data-processing disclosure; biometric data kept indefinitely; video kept on failure; findings sent to Groq | `main.py:81` (full 33-landmark CSV per job), `main.py:99-101` (PDF + plots), `main.py:102` (video deleted only on success; `data/raw/ba2be09e.mp4`, `c9d7ccd1.mp4` are leftovers of failed runs, `outputs/ba2be09e` has plots but no PDF), `exercise_prescription.py:297-303`; no "consent/delete/retention" string anywhere in either repo | Consent capture, `DELETE` endpoints, TTL on raw video, `finally:` cleanup, DPA/notice for LLM or strip it (ADR-007) |
| F07 | Security | 🟠 | M | Upload validation is a case-sensitive extension check; no size/duration/resolution/content check | `main.py:60-61, 72-73`. Probe: shell-script bytes named `evil.mp4` written to disk, 500 returned. `IMG_0001.MOV` is rejected though the frontend allows it (`App.js:270` uses `/i`) | Stream to storage with max size; probe with `ffprobe`/`cv2` for codec, duration ≤ N s, resolution cap; lowercase compare |
| F08 | Security | 🟠 | S | `allow_origins=["*"]`; bearer token logged to browser console; 365-day tokens with no revocation | `main.py:29-34`; `App.js:282`; `auth.py:16`. Live: `access-control-allow-origin: *` | Allow-list the Vercel origin; remove log; 15–60 min access + refresh token |
| F09 | Security | 🟠 | S | Internal exception text returned to client; OpenAPI/Swagger public in prod | `main.py:162-163` → `{"detail":"Analysis failed: Cannot open video: data/raw/f06d39d0.mp4"}`; live `/docs` 200 | Generic message + error ID; log detail server-side; `docs_url=None` in prod or behind auth |
| F10 | Security | 🟠 | S | No rate limiting (login, register, invite join, analyze); invite codes use `random`, never expire | Probe: 30 bad logins → all 401, no 429; `clinician_router.py:17-18` | `slowapi` or edge rate limits; `secrets.choice`; invite TTL |
| F11 | Deps | 🟠 | M | 40 unique advisories in 9 Python packages; 48 npm (2 critical, 23 high) | `uvx pip-audit` on `_audit/.venv`: python-jose 3.3.0 (PYSEC-2024-232/233, CVE-2024-33663/33664), python-multipart 0.0.20 (6), starlette 0.46.2 (7), pillow 10.3.0 (17), protobuf 3.20.3 (2), anyio, click, ecdsa, idna. `npm audit`: axios 1.14.0 (28 advisories, runtime), rest CRA build chain | Replace python-jose with PyJWT; bump FastAPI/Starlette/multipart/pillow; migrate CRA → Vite; Dependabot |
| F12 | Security | 🟡 | S | Account enumeration and no password policy | `auth_router.py:31-32` returns 409 "Email already registered"; 1-char password accepted | Generic response; min length 10 + breach check optional |
| F13 | Arch | 🔴 | L | CPU-bound pipeline runs synchronously inside `async def` → blocks the event loop for every user | `main.py:52-163`. Probe (`out_concurrency.txt`): `/status` latency **28.72 s** during one 60 s-clip analysis | Job queue + separate worker (ADR-002); API returns `202 {job_id}` |
| F14 | Infra | 🟠 | M | Peak RSS 339 MB (16 s 480p), 485–516 MB (60 s 1080p) vs 512 MB instance | `out_profile_walk01.txt`, `out_variants.txt`, `ps` RSS 484.8 MB for uvicorn | Downscale frames before inference, cap duration, worker process with its own memory budget, `--workers 1` on API |
| F15 | Arch | 🟠 | M | Artifacts on ephemeral local disk; PDF regeneration loses mode and charts | `main.py:36-38, 68-70, 166-221`; probe shows wrong mode in regenerated PDF | Object storage (R2/S3) for video (TTL) and PDFs; persist `mode`, `pipeline_version`, raw metrics JSON in Postgres |
| F16 | Build | 🟡 | S | Unpinned deps, duplicates, dead deps, 3 OpenCV builds, no lockfile, no Dockerfile/render.yaml | `requirements.txt:56-65` (`sqlalchemy`, `psycopg2-binary`, `python-multipart`, `email-validator` unpinned; `passlib`, `python-multipart` listed twice); `scikit-learn`, `sounddevice` never imported | `pyproject.toml` + `uv.lock`; only `opencv-python-headless`; Dockerfile; `render.yaml` |
| F17 | Data | 🟡 | M | No migrations; `create_all` at startup; silent SQLite fallback | `database.py:6, 26-29`; `main.py:40-42` | Alembic; fail fast if `DATABASE_URL` missing outside dev |
| F18 | Repo | 🟡 | S | `gaitscan.db` still tracked; stray empty files; `.gitignore` typo `*.gifoutputs/` | `git ls-files`; `.gitignore` line `*.gifoutputs/`; `main.py`, `tests/test_angles.py` 0 bytes | `git rm --cached gaitscan.db`, fix ignore, delete stubs |
| F19 | Code | 🟡 | S | matplotlib backend never set; pyplot global state; crashes off main thread on macOS | `visualise.py:1`; probe crashed with `NSException` under TestClient until `MPLBACKEND=Agg` | `matplotlib.use("Agg")` / object-oriented `Figure` API, or drop server-side PNGs (render charts in PDF natively) |
| F20 | Code | 🟡 | S | Unescaped text in ReportLab markup; LLM output containing `<` crashes PDF build → whole `/analyze` 500s, and the video is left on disk | `report_generator.py:338-343, 395-400`; probe: `CRASH 'Keeps your L<R imbalance in check' ValueError` | `xml.sax.saxutils.escape()` all interpolated text |
| F21 | Infra | 🟠 | S | Cold start 42 s on live service (first request timed out at 90 s); frontend has no timeout, warm-up or retry UX | `curl` timings in Phase 0; `App.js:283-287` | Paid instance or keep-warm ping; async job UX makes it tolerable |
| F22 | ML | 🔴 | L | No ground truth, validation set, or accuracy numbers for any metric | No dataset, notebook or eval code in repo (`notebooks/` empty); only one clip, 3 identical copies (`cmp` IDENTICAL) | Validation harness (REBUILD_PLAN D5) |
| F23 | ML | 🔴 | L | "Risk score" is an invented additive heuristic; insensitive and uncalibrated | `risk_scoring.py:91-291`. All 6 degraded variants → 0; 75 noisy runs → 0; simulated 60% right-knee ROM loss → 20 "Minor findings" (`out_stability.txt`) | Remove the composite score; report metrics with reference ranges and quality flags (ADR-005) |
| F24 | ML | 🔴 | M | "Cadence" counts upward crossings of the **left** knee through 155° (one leg, no hysteresis, no smoothing) | `risk_scoring.py:238-244`, duplicate `activity_classifier.py:12-15`. Synthetic 110 steps/min → **54.1**; +6° noise → 75.1; real clip: 30 crossings, 10 of them <0.4 s apart | Gait-event detection per leg (heel-strike from ankle/heel trajectory), hysteresis, band-pass, steps = both legs |
| F25 | ML | 🟠 | S | Angles computed on normalised coords (x/W, y/H) → aspect distortion | `calculate_angles.py:14-16`. Test: true 121.9° → app 91.1°. Sample clip: mean 7.4–8.3°, max 27.6° error vs pixel space (`out_signal_analysis.txt`) | Multiply by frame W,H before angles (or use world landmarks where valid) |
| F26 | ML | 🟠 | M | No visibility gating, no smoothing, no quality gates, no multi-person handling | `extract_landmarks.py:18-35` (visibility stored, never read). L-knee visibility <0.5 in 25.6% of frames; frame-to-frame knee jumps p95 24°, max 77.5°; two-people clip → knee flexion 179.8° accepted; feet-occluded → "Running 95%" | Gate on visibility, interpolate short gaps, One-Euro/Savitzky–Golay, reject clips failing quality thresholds |
| F27 | ML | 🟠 | S | Knee flexion = 180 − **min** over the whole clip (single-frame outlier sets it) | `risk_scoring.py:168-171`, `activity_classifier.py:18-21`. Sample: min-based 66.5–105.2° vs 2nd-percentile 55.1–55.4° (pixel space) | Per-stride peak flexion, median across strides |
| F28 | ML | 🟠 | S | Symmetry index computed on the **mean absolute angle** (~160°), compressing real asymmetry | `risk_scoring.py:93-99`. Test: right-knee ROM halved → SI 7.3% → "good" | SI on per-stride ROM / step time / step length |
| F29 | ML | 🟠 | M | 2D angles are view-dependent; no view detection; UI claims "Any angle", README "CCTV" | Probe `out_view_dependency.txt`: true 60° reads 45.1° at 45° yaw, 0° frontal; `App.js:418`; README L7 | Restrict to side view, detect view from shoulder/hip width ratio, reject otherwise |
| F30 | ML | 🟠 | M | Activity classifier = 4 hand thresholds; "confidence" is a formula of cadence, not a probability | `activity_classifier.py:46-95`. Clean 110 spm walk → "Unknown"; mirror of same clip → "Brisk Walking"; noise σ=0.004 → 5/25 flip to Brisk Walking | Drop classifier for v1 (clinician states the task), or train + evaluate a real one later |
| F31 | ML | 🟡 | S | Duration = `time_s.max()` not span; fps derived from detected frames; dropped frames leave silent gaps | `activity_classifier.py:8-9`, `risk_scoring.py:238`; 17 dropped frames on sample | Use container fps + frame indices; resample onto uniform timeline |
| F32 | Perf | 🟡 | M | Every frame processed at full resolution with the legacy `mp.solutions.pose` API | `extract_landmarks.py:18-26`; MediaPipe = 57% of 12 s on 16 s clip, 94% (27.8 of 29.6 s) on 60 s 1080p | Downscale to ~640 px long side; MediaPipe Tasks `PoseLandmarker` (VIDEO mode) pinned model file |
| F33 | Code | 🟡 | S | Dead, direction-dependent `shoulder_tilt` | `calculate_angles.py:30-31, 40`; test fails (179.9° for level shoulders) | Delete |
| F34 | ML | 🟡 | S | "Hip flexion" plotted is the trunk–thigh angle (180° when upright) | `calculate_angles.py:24-28`, `visualise.py:27-33` | Define hip flexion vs vertical/pelvis; label clearly |
| F35 | Product | 🟠 | S | Threshold tables contradict across scoring, PDF and UI; different labels for same score | See §4 items 3–4 | Single source of truth served by API |
| F36 | Regulatory | 🔴 | S | Diagnostic/injury language throughout user-facing output | §6 A3 table | Screening framing (§6 A3) |
| F37 | Code | 🟡 | S | "RAG" overclaim; blocking Groq call inside request; no explicit timeout; model name hardcoded | `exercise_prescription.py:297-303`; README "RAG pipeline" | Rename to "template + LLM phrasing" or remove LLM; timeout; move to worker |
| F38 | Tests | 🟠 | M | Zero tests; frontend's only test is the failing CRA boilerplate | `tests/test_angles.py` 0 bytes → "no tests ran"; `App.test.js` fails "Unable to find an element with the text: /learn react/i" | See D4 |
| F39 | Frontend | 🟡 | M | 1,102-line `App.js`, inline styles, hardcoded API URL, no router, no responsive CSS, no a11y, errors swallowed as empty state, CRA (deprecated) | `App.js:8`; `grep @media` = 0 in App.js; no `htmlFor`/`aria-*`; clickable `<span>/<div>` at `App.js:89,157,980`; `fetchHistory` catch → `[]` (`App.js:262-264`) shows "No sessions yet" on failure; `<title>React App</title>` | Vite + React Router + TanStack Query + typed client; split components |
| F40 | Product | 🟡 | S | Patient identity missing: name never sent, not on PDF; clinicians cannot upload | `App.js:277-279`; `main.py:55`; clinician UI has no upload (`App.js:316-323`) | Patient records owned by clinic; practitioner uploads for patient |
| F41 | Ops | 🟡 | S | `print` logging; no error tracking; 24/53 backend + 14/25 frontend commits titled `feat: c`, `fix: P` etc. | 13 `print(` calls in `src/`; `git log` | `structlog`/JSON logs, Sentry, Conventional Commits |
| F42 | Math | ⚪ | S | `+1e-8` in denominator biases 0°/180° by ~0.01–0.05°; coincident points return 90° instead of NaN | `calculate_angles.py:11`; tests | Guard zero-length vectors → NaN |
| F43 | Code | ⚪ | S | Unused imports and duplicates | `main.py:6, 21`; `visualise.py:2`; `clinician_router.py:7` (`Optional, List`, `defaultdict`) | ruff will flag them |
| F44 | Code | ⚪ | S | All uploads saved as `.mp4` regardless of container | `main.py:68` | Keep real extension / detect container |

---

## 6. Part A — Broad audit

### Phase 0 recon

**Repo map**

```
gaitscan/                       (FastAPI backend, Render)
  src/api/main.py               app, CORS, /analyze, /report, /sessions — 282 LOC, god-file
  src/api/auth_router.py        /auth/register|login|me
  src/api/clinician_router.py   invites, patient list, /debug/links
  src/core/                     mixed bag: auth, DB, ORM models AND the ML pipeline
    extract_landmarks.py        MediaPipe loop
    calculate_angles.py         2D angles
    activity_classifier.py      threshold rules
    risk_scoring.py             mode configs + scoring + all user-facing text
    exercise_prescription.py    19-item exercise list + Groq call
    report_generator.py         ReportLab PDF — 454 LOC
  src/models/                   User, ClinicianInvite, ClinicianPatient (other models live in src/core/models.py)
  src/utils/visualise.py        matplotlib PNGs
  gaitscan.db (tracked!), main.py (empty), tests/test_angles.py (empty), notebooks/ (empty)
  data/raw, data/processed, outputs/  (gitignored runtime artifacts — local copies contain a real person's video)
gaitscan-frontend/              (CRA React 19, Vercel)
  src/App.js                    everything: auth context, login, register, upload, results, history, clinician dashboard
```

**Frontend ↔ backend contract**
- Base URL hardcoded: `const API = "https://gaitscan.onrender.com"` (`App.js:8`). No env vars in either repo. No `.env.example`.
- Auth is a bearer JWT set as a global axios default in a `useEffect` (`App.js:30-36`). Child effects run before parent effects, so the clinician dashboard hand-adds headers (`App.js:800-803`, commit `7fb8317` "add auth headers to clinician dashboard calls" is the workaround for this ordering bug).
- The PDF is fetched by plain link, with no auth (`App.js:484`).
- Endpoints used by the frontend: `/auth/login`, `/auth/register`, `/analyze`, `/sessions`, `/patient/join`, `/clinician/patients`, `/clinician/invite`, `/clinician/patients/{id}/sessions`, `/report/{id}`.
- Unused by the frontend: `/auth/me`, `/sessions/{id}`, `/debug/links`, `/`, `/status`.
- Response shapes are untyped dicts; there are no Pydantic response models on any analysis endpoint.

**Dependencies** — `requirements.txt` has 65 lines and is a `pip freeze` of a dev venv plus hand-appended lines.

| Issue | Packages |
|---|---|
| Unpinned | `sqlalchemy` (also pinned as `SQLAlchemy==2.0.49` → duplicate), `psycopg2-binary`, `python-multipart` (dup of `==0.0.20`), `email-validator` |
| Duplicated | `passlib`, `passlib[bcrypt]==1.7.4`; `python-multipart` ×2; `sqlalchemy` ×2 |
| Unused | `scikit-learn`, `joblib`, `threadpoolctl`, `sounddevice`, `cffi`/`pycparser` (only for sounddevice), `opencv-python`, `opencv-contrib-python` |
| Conflicting | 3 OpenCV wheels at 2 versions share the `cv2` namespace; installed `cv2.__version__` resolved to 4.13.0 — whichever wins is install-order dependent |
| Outdated / fragile | `mediapipe==0.10.9` (Jan 2024; PyPI now serves 0.10.30–1.0.1 for py3.13, and pip-audit could not even resolve 0.10.9 on 3.13); `protobuf==3.20.3` pinned for it; `bcrypt==3.2.2` pinned to dodge passlib's bcrypt-4 incompatibility; `python-jose` (unmaintained) |
| Bloat | `matplotlib` + `pandas` + `scipy` for 4 PNGs, 1 `find_peaks` and row-wise `df.apply` |
| Frontend | `react-scripts 5.0.1` (CRA, deprecated); testing libs in `dependencies`; `web-vitals` 2.x unused beyond template; axios 1.14.0 has 28 advisories |

Vulnerabilities: see F11. The npm counts are mostly the CRA dev/build chain (`webpack-dev-server`, `svgo`, `jest`). The runtime-relevant one is axios.

**Git history**
- Backend: 53 commits from 2026-04-08 to 2026-05-15, bursty (7 on 04-12, 6 on 04-14 and 04-21), then a 3-week gap. 24/53 are content-free titles. One branch (`main`); no tags; no PRs.
- Largest commit: `e147cbc` (+441/−139 in `report_generator.py`).
- Nine consecutive commits (04-11 → 04-21) churn `requirements.txt`, i.e. deploy-by-trial-and-error.
- Auth secret churn: 5 commits on `auth.py` in 2 days (04-24 → 04-25), ending with "fix: hardcode fallback secret". This most likely fixed "tokens invalid after restart" (the env var was not set on Render) by hardcoding, which is the wrong fix.
- Committed secrets: the JWT secrets above. The historical `gaitscan.db` blobs (`0e74967`, `1243be6`) contain **0 users, 0 sessions**, so no PII leaked via git. The Groq key is read from env; not found in history.
- Large binaries: initial commit `e21f4ab` committed 3 PDFs (later removed; still in history, ~480 lines each).
- Frontend: 25 commits; `App.js` grew from the CRA template to 1,102 lines in 23 commits; 14/25 content-free titles.

**What this project actually is (from code):**
A single FastAPI process accepts an uploaded video from a logged-in user and runs MediaPipe Pose (legacy API, default settings) on every frame, synchronously, inside the request. It computes four 2D joint angles in normalised image coordinates. It then applies hand-picked thresholds to whole-clip means and minima to produce:
- an activity label,
- a "cadence" (actually left-knee extension crossings per minute),
- two symmetry percentages,
- a 0–80 additive "risk" number with templated English sentences.

It picks 2–5 exercises from a hardcoded list, asks Groq/Llama-3.1-8B to phrase one sentence per exercise, renders matplotlib PNGs and a ReportLab PDF to local disk, and stores summary numbers in a SQL database. A React single-file app provides login, upload, results, history charts, and a clinician view of patients who joined via a 6-character invite code.

**README vs reality**

| README claim | Reality |
|---|---|
| "walking/running/CCTV video uploads" | 2D sagittal angles; CCTV (elevated, oblique, low-res) is exactly the case that fails (F29) |
| "Extracts 33 body landmarks per frame" | True, but visibility is ignored and frames without a person are silently dropped |
| "Classifies activity (Walking / Brisk Walking / Running / Limping)" | Four `if` statements; healthy synthetic walk → "Unknown" (F30) |
| "Calculates knee/hip symmetry, flexion range, cadence" | Computed, but cadence is wrong by construction (F24) and flexion is outlier-driven (F27) |
| "Scores gait risk 0–100" | Max reachable is 80; not a risk model (F23) |
| "Groq/Llama RAG pipeline" | No retrieval; tag lookup + one LLM sentence (F37) |
| "Multi-user auth (JWT), clinician dashboard, progress tracking" | Exists, but insecure (F01–F05); "progress tracking" = list of past scores |
| "PostgreSQL" | Supported, with silent SQLite fallback; no migrations |
| "GET /report/{job_id} — download PDF report" | Also downloadable by anyone with the ID |
| (not mentioned) | Frontend lives in a separate repo with the CRA default README |

### A1. Architecture & design

- **Separation of concerns:** `src/core/` holds auth, database, ORM models and the ML pipeline side by side. `src/models/` holds only some models. `risk_scoring.py` mixes thresholds, scoring, and all user-facing copy. `main.py` contains orchestration, persistence mapping, serialisation and PDF regeneration. There is no service layer, no schemas for responses, and no pipeline object.
- **Data flow:** upload → write `data/raw/{id}.mp4` → landmarks DataFrame (in memory) → CSV to `data/processed` → classify → score → Groq (network, blocking) → PNGs → PDF to `outputs/{id}` → delete video (success only) → DB insert → JSON response.
  - There is no persisted link between the stored summary and the pipeline version or config that produced it.
  - The DB stores only 10 summary numbers; the rest of the response (activity metrics, mode, recommendations) is lost.
- **Synchronous processing:** yes, and worse than sync. `async def analyze` runs blocking CPU work directly on the event loop, so FastAPI does **not** offload it to the threadpool. Measured: 28.7 s of total server unresponsiveness for one 60 s clip.
  - **60 s 1080p on Render:** locally it takes 29.6 s and peaks at 516 MB RSS. On Starter (0.5 CPU, 512 MB), expect roughly 2–4 minutes of wall time [estimate, A4] and likely an OOM kill.
  - During that time health checks stall, every other user's request queues, and the browser shows a spinner with no progress.
  - Cold start adds 40–90 s on top (measured on the live service).
- **Abstractions:**
  - Missing: a pipeline interface (`analyse(video) -> AnalysisResult` with a version), typed result objects, a storage abstraction, and a job model.
  - Premature or pointless: four "modes" of invented thresholds, which triple the surface area to validate; the `icon` emoji field in API responses.
  - Not premature (good call): the clinician invite model.
- **Makes no sense:** see §4.

### A2. Code quality

- **Naming:** mostly readable. Misleading names: `cadence` (is one-leg crossings), `knee_flexion_range` (is 180 − min, not a range), `hip_angle` (trunk–thigh), `risk_score`, `confidence`, `EXERCISE_KNOWLEDGE_BASE`/"RAG".
- **Typing:** there are no type hints on any pipeline function. Pydantic is used only for auth request bodies (`auth_router.py:12-26`, `clinician_router.py:35-36`). Every analysis response is an untyped dict. The frontend is plain JS with no PropTypes.
- **Error handling:**
  - A bare `except Exception` → 500 with the message (`main.py:162-163`).
  - A bare `except Exception` swallows Groq errors via `print` (`exercise_prescription.py:311-313`).
  - Frontend catches swallow everything (`App.js:262, 805, 816, 829`).
- **Logging:** 13 `print` calls, one of which prints passwords. No request IDs, no levels.
- **Magic numbers:** everywhere, and uncommented.
  - Thresholds: 155° (crossing), 15/25 (limp), 150/70, 120/55, 60/35 (classifier), and the 30/20/15/10/25 risk weights.
  - Confidence formulas: `50 + asymmetry + irregularity/2`, and so on.
  - Plot limits: 60–200°, 80–200°.
  - PDF column widths.
- **Duplication:** see §4 item 11. The frontend repeats the session-card JSX and trend charts twice (`App.js:637-712` vs `866-925`), plus colour maps and inline threshold logic.
- **Tests:** none in the backend. The frontend's one test fails. There is nothing asserting anything.
- **Frontend specifics:**
  - One component tree in one file; `MainApp` holds 11 `useState`s.
  - There is no router: results are unreachable by URL, and refresh loses them.
  - `symmetryData`/`flexionData`/`trendData` are recomputed every render (cheap; not a real problem).
  - `ResponsiveContainer` is fine, but the chart y-domains are fixed (`[0,25]` for SI, `App.js:528`), so an SI of 40% is clipped.
  - Loading state: a spinner with a fake progress string ("Extracting body landmarks…" is set before the upload even starts, `App.js:281`).
  - Error state: a raw backend string is shown.
  - Empty state: shown on error too (F39).
  - Responsiveness: a fixed 200 px sidebar, `gridTemplateColumns: "1fr 1fr"` and zero media queries mean it breaks on phones, which is the likely capture device.
  - Accessibility: no labels bound to inputs, clickable `span`/`div`, colour-only status in charts, emoji as content.

### A3. Security & privacy

- **Upload handling:** extension-only and case-sensitive (F07).
  - No size limit: Starlette spools the whole multipart body to a temp file, then `shutil.copyfileobj` copies it again.
  - No duration/resolution limit: a 4K 10-minute video would run for tens of minutes and OOM.
  - Content sniffing: none.
  - Path traversal: not exploitable. The filename is not used in the path (`main.py:68`), and `job_id` in `/report/{job_id}` is only used after a DB hit or for `os.path.exists` (a `..` value just 404s).
  - Decompression-bomb-style risk: a small, highly compressible high-resolution/long video decodes to huge frame counts. That is CPU exhaustion rather than memory, since frames are streamed, but there is no cap.
- **Storage:**
  - Raw video: `data/raw/`; deleted only on success. Failure leaves it forever, as the local leftovers show.
  - Landmarks: a full 33-point skeleton time series, `data/processed/{id}_angles.csv`, **never deleted**.
  - PNGs and PDF: `outputs/{id}/`, **never deleted**.
  - DB rows: never deleted, and there is no delete endpoint.
  - On Render, the ephemeral disk wipes files on redeploy. That is accidental, unverifiable deletion, not a policy.
- **Auth/authz:**
  - JWT exists, but the secret is public (F01).
  - The role is client-chosen (F03).
  - `/sessions/{id}` and `/report/{id}` are unauthenticated (F02).
  - `/debug/links` is available to any clinician (F03 probe).
  - IDs are 8 hex chars ≈ 4.3 billion possibilities. That is not guessable by random scan quickly, but IDs are shared in URLs, logs and PDF links, and the forged-JWT path makes enumeration unnecessary anyway.
- **Configuration and leakage:**
  - CORS `*` (live-verified).
  - Secrets in code: F01.
  - `.env` is gitignored, but there is no `.env.example`.
  - Debug mode: uvicorn debug not detectable. Swagger `/docs` is public.
  - Stack traces: the exception message leaks to the client (F09).
  - PII in logs: passwords (F04), bearer token in the browser console (F08).
- **Language and framing.** Every user-facing string that implies diagnosis, injury prediction or treatment:

| Location | String | Problem | Screening-tool alternative |
|---|---|---|---|
| `risk_scoring.py:270, App.js:464, report_generator.py:178` | "Risk Score", "Risk Assessment" | Implies a validated risk prediction | "Movement summary" (no composite) |
| `risk_scoring.py:289-290`, PDF `report_generator.py:126` | "Serious abnormality… Please consult a doctor" | Diagnostic claim | "Several measurements fall outside typical ranges for this recording. A clinician can interpret these." |
| `risk_scoring.py:285-286` | "Clear gait abnormalities detected. Physiotherapy is recommended." | Diagnosis + treatment recommendation | "Measurements outside typical range: [list]" |
| `risk_scoring.py:111-114` | "…can cause long-term joint damage and pain" | Injury causation claim | "Left/right knee motion differed by X% in this recording (typical: <Y%)." |
| `risk_scoring.py:146-148` | "can indicate hip weakness or tightness… contributes to lower back pain" | Etiology claim | Remove etiology; state the measurement |
| `risk_scoring.py:185-187` | "increases injury risk — especially shin splints and knee pain" | Injury prediction | Remove |
| `risk_scoring.py:224-226` | "'stiff-legged' pattern… increases fall risk" | Fall-risk prediction (a regulated claim category) | "Peak knee bend X° (typical walking: ~60°)" |
| `risk_scoring.py:203-209`, `activity_classifier.py:47-53` | "Limping", "Affected Side… suggesting it is the affected leg" | Clinical sign detection | "Asymmetric pattern detected; left/right step timing differed by X%" |
| `risk_scoring.py:212-213` | "Avoid high-impact activities until assessed" | Medical advice | Remove |
| `report_generator.py:229, 215, 381` | "Clinical Measurements", "Clinical focus", "Prescribed Exercises" | "Prescribed" implies a prescriber | "Measurements", "Suggested exercises for discussion with your physiotherapist" |
| `App.js:570` | "Personalised to your specific findings — generated by AI" | LLM-generated health advice to patients | Clinician-reviewed exercise list; LLM off by default |
| `risk_scoring.py:274` | "Your gait looks healthy. No concerns found." | False reassurance (returned for the two-person clip) | "No measurements outside typical range. This is not a health assessment." |
| `App.js:418`, README | "Phone, CCTV, sports footage · Any angle" | Unsupported capability claim | "Side-on phone video, full body visible, 10–20 s straight walk" |
| `risk_scoring.py:63`, App mode buttons | "Elderly — fall-risk focused" | Fall-risk screening claim | Drop modes or describe as "reference-range set" |

  Disclaimer: only a 7.5 pt footer in the PDF (`report_generator.py:449-451`). No disclaimer in the web UI.

- **Indian legal context (DPDP Act 2023, as operationalised by the DPDP Rules):**

| DPDP basic | Status | Evidence |
|---|---|---|
| Notice + informed consent before processing | ❌ | No consent screen or text in either repo; register form collects role, name, email only (`App.js:96-161`) |
| Purpose limitation | ❌ | No stated purpose; landmarks retained with no use; data sent to Groq for text generation |
| Data minimisation | ❌ | Full skeleton CSV persisted (`main.py:81`) though only summaries are used |
| Retention limits / erasure when purpose served | ❌ | No TTL; no delete; failure path leaves raw video |
| Right to access / correction / erasure | ❌ | No export, no delete endpoint, no account deletion |
| Security safeguards | ❌ | F01–F05 |
| Breach notification readiness | ❌ | No logging/audit trail to even detect access |
| Cross-border transfer | ⚠️ | Render region and Groq are presumably US; transfer is generally permitted unless restricted by notification, but must be disclosed in the notice |
| Children's data (verifiable parental consent) | ❌ | Sports academies = minors; no age gate |
| Grievance officer contact | ❌ | None |

  Physio clinics are the data fiduciary and GaitScan is their data processor. A clinic will need a DPA from you. Nothing here supports that yet.

### A4. Performance & infrastructure

Sample: `walk01.mp4`, 480×848, 30 fps, 505 frames (16.8 s). M3, Python 3.11 (`out_profile_walk01.txt`).

| Stage | 16.8 s 480p | 60 s 1080p |
|---|---|---|
| imports (mediapipe, cv2, pandas, matplotlib…) | 0.93 s | — |
| decode + MediaPipe | 6.84 s | 27.81 s |
| angles (`df.apply` row-wise ×5) | 0.03 s | — |
| classify | 2.94 s (almost all lazy `import scipy` inside the function) | — |
| scoring | <0.01 s | — |
| exercises (no Groq key) | <0.01 s (a real Groq call adds ~0.5–3 s network, unmeasured) | — |
| plots | 1.01 s | — |
| PDF | 0.24 s | — |
| **Total** | **11.98 s** | **29.61 s** |
| **Peak RSS** | **339 MB** | **516 MB** (server process 485 MB) |

- **Frame sampling:** every frame at native resolution. MediaPipe resizes internally to 256×256, so decoding and colour-converting 1080p frames is wasted work. Gait at 30 fps is adequate. Processing at 15 fps would halve cost but changes current results (cadence 107 → 82, `out_stability.txt`) because the current metrics are jitter-dependent. Once smoothing and event detection are correct, 30 fps is recommended for heel-strike timing, with a downscale to ~640 px.
- **Concurrency estimate:** effectively **1**.
  - The event loop is blocked for the whole analysis (measured), so a second upload cannot even be received until the first finishes.
  - Adding uvicorn workers doubles memory (~2 × 350–500 MB) past the 512 MB instance.
  - With a Starter-class CPU at 4–8× slower [A4], the third user in a queue of 16 s clips waits roughly 2–4 minutes. Any proxy or browser timeout, or a user closing the tab, wastes the work because there is no job persistence.
- **Render/Vercel config:**
  - Cold start 42 s (`/status`); the first request timed out at 90 s.
  - The health check path is unknown (not in repo).
  - No env separation (one hardcoded API URL; no staging).
  - Build reproducibility: no lockfile, unpinned lines, 3 OpenCV wheels, `runtime.txt` likely ignored.
  - No Dockerfile, `render.yaml`, `Procfile` or `vercel.json`.
  - Render's maximum HTTP request duration could not be verified from official docs [not audited].

### A5. Product & UX sense

Walking the flow as a physiotherapist:
1. **Registers** and picks "Clinician". Any patient could also pick that.
2. **The clinician lands on a patient list with no upload button.** A physio's job is to record the patient in the clinic; the product assumes patients record themselves at home.
3. The clinician generates a 6-char code and tells the patient to "enter this in History tab → Join Clinician", which is buried under the history heading.
4. **The patient uploads** from a phone. The layout is not responsive, and an iPhone `.MOV` is rejected (F07). There is no capture guidance beyond "Any angle".
5. **Waits** 15 s to several minutes behind a spinner with a fake progress string. On a cold start, 40–90 s more. No resume if the tab closes.
6. **Result:** an activity emoji plus "Confidence 76%" (not a probability), then "0/100 No issues detected", "Your gait looks healthy".
   - It shows no measurement quality, no indication of which frames were used, and no warning that the subject walked out of frame in ~30% of the clip.
   - Two bar charts coloured by thresholds that don't match the backend.
   - AI-written "Why for you" exercise reasons.
7. **The clinician sees** a list of patients with a "latest risk" and a sparkline, and a "⚠ Needs attention" flag if risk > 50 or three consecutive increases (`clinician_router.py:122-128`).
   - No patient demographics, no notes, no video playback, no per-stride data, no comparison of two sessions.
   - The patient is named by `full_name or email`.
8. **The PDF:**
   - No patient name, no date of birth, no clinician, no clinic, no video metadata.
   - A "Risk Score 0/100 — Low Risk" headline that differs from the web label.
   - A thresholds table from a different config than the scoring used.
   - "Prescribed Exercises".
   - Plots with fixed y-limits: the knee plot cuts at 60°, so knee angles below 60° vanish.
   - It looks professional and is **developer output dressed up**.

**Units, ranges, confidence, caveats:** units are present on most values (°, %, steps/min). Reference ranges are invented, mode-specific and uncited. Confidence exists only for activity, and it isn't one. Caveats: one small footer line.

**Features that exist because they were fun to build `[opinion]`:**
- the four "modes" with bespoke thresholds;
- the LLM "Why for you" sentences;
- activity classification with emojis (a clinician already knows whether the patient walked or ran — they asked them to);
- the 0–100 composite score and "Needs attention" rule;
- the ankle trajectory scatter plot ("proves the cyclic walking pattern", `visualise.py:39`);
- the Athlete mode's "peak biomechanical efficiency" framing.

**What a clinic actually needs:** reliable per-side joint angle curves with a clear capture protocol, per-stride spatiotemporal parameters, side-by-side session comparison, the video with a skeleton overlay for trust, and an editable report with clinician notes.

---

## 7. Part B — ML / gait pipeline deep audit

### B1. Landmark extraction (`extract_landmarks.py`)

- **Model/config:** legacy `mp.solutions.pose.Pose(min_detection_confidence=0.5)` (`L18`). Defaults: `static_image_mode=False` (tracking on), `model_complexity=1` (Full, not Heavy), `smooth_landmarks=True` (MediaPipe's internal filter), `min_tracking_confidence=0.5`, `enable_segmentation=False`. `mediapipe==0.10.9`. The model file is bundled in the wheel, so it is implicitly versioned by the pip pin. The `solutions` API is legacy (superseded by MediaPipe Tasks `PoseLandmarker`).
- **Low-visibility handling:** none. `visibility` is stored (`L34`) and never read. On the sample clip the **left knee has visibility <0.5 in 25.6% of frames** (the far leg in side view), yet those frames feed every angle.
- **World landmarks** (`results.pose_world_landmarks`, metric 3D) are ignored.
- **Frames with no detection** are dropped with no gap marker; 17 on the sample (`out_signal_analysis.txt`).
- **Probe results** (full pipeline per variant, `out_variants.txt`):

| Condition | Frames w/ pose | Activity | Knee flex L/R | Cadence | Score | Correct behaviour |
|---|---|---|---|---|---|---|
| Original side view (walks in/out of frame, turns) | 488/505 | Walking 76% | 81.5 / 95.7 | 107.1 | 0 | Should segment steady walking or reject |
| Mirrored (same motion) | 489 | **Brisk Walking** 61% | 92.4 / 100.8 | **132.1** | 0 | Same cadence, L/R swapped |
| Dark (18% brightness + noise) | 412 | Walking 73% | 89.6 / 87.8 | 92.9 | 0 | Warn: low detection rate |
| Feet/ankles occluded (bottom 22% black) | 475 | **Running 95%** | **136.8 / 140.2** | 164.3 | 0 | Reject: ankles not visible |
| Two people side by side | 485 | Walking 71% | **179.8 / 178.0** | 85.7 | 0 | Reject: multiple people |
| Rotated 90° (lying sideways) | 496 | Walking 77% | 106.2 / 93.5 | 110.7 | 0 | Reject/auto-rotate |
| Same clip ×3.6 loop, upscaled to 1080p | 1749/1800 | **Brisk Walking** 56% | 80.1 / 95.1 | **122.1** | 0 | Same as original |

  Not probed with real footage: a frontal view (walking toward camera), baggy clothing, and a genuinely angled camera (no such footage available; see Not audited). The frontal/angled case is covered analytically in B2.
- **Temporal smoothing:** only MediaPipe's built-in landmark smoothing. No app-level filter. Knee-angle frame-to-frame jumps: median 4.5°, **p95 24.1°, max 77.5°** in 1/30 s. A real knee does not move 77° in 33 ms.

### B2. Joint angle calculation (`calculate_angles.py`)

- **Space:** 2D, in **normalised** image coordinates (`_p` returns `lm.x, lm.y`, `L14-16`). Not pixels, not world 3D.
- **Aspect-ratio distortion:** MediaPipe returns `x/width` and `y/height`. On a 480×848 portrait frame, one unit of x is 480 px and one unit of y is 848 px, so angles are skewed.
  - Test: a true 121.9° knee reads **91.1°** (`test_aspect_ratio_preserves_angle_on_portrait_video` FAILS).
  - On the sample clip the mean |error| is 7.4° (L) / 8.3° (R), max 27.6°. Right-knee "flexion" moves from 95.7° to 105.2° when computed correctly in pixels.
  - Fix: multiply by W, H. One line.
- **Perspective/projection:** the choice of 2D sagittal angles is defensible **only** for a camera perpendicular to the walking direction, at hip height, with the subject mid-frame. The code nowhere checks or acknowledges this. The UI and README claim the opposite.
  - Probe (`out_view_dependency.txt`, orthographic): a true 60° knee flexion reads 58.4° at 15° yaw, 53.5° at 30°, 45.1° at 45°, 33.1° at 60°, and 0° frontal.
  - At 45° yaw a normal walker is flagged "stiff-legged… increases fall risk" in Clinical mode (threshold 45°).
- **Bug checks:**

| Check | Result | Evidence |
|---|---|---|
| Degrees vs radians | ✅ degrees | `np.degrees`, test passes |
| `arccos` domain | ✅ clipped | `np.clip(cos_a, -1, 1)`, test passes |
| Epsilon bias | ⚪ 0.01–0.05° at 0°/180° | `+1e-8` in denominator; negligible |
| Degenerate (zero-length) vectors | ⚠️ returns 90.0 instead of NaN | test FAILS; occluded landmarks collapsing onto each other produce a confident 90° |
| Left/right labels | ✅ indices correct (23/25/27 = LEFT_HIP/KNEE/ANKLE) | test passes. MediaPipe labels are anatomical (subject's left) but become unreliable for the far, occluded leg, and the mirror probe shows L/R flexion values do not swap cleanly (81.5/95.7 → 92.4/100.8) |
| Image y-axis inversion | ✅ irrelevant for unsigned 3-point angles | test passes |
| Flexion vs hyperextension | ⚠️ unsigned angle, `180 − angle` cannot distinguish knee hyperextension from flexion | code inspection `L4-12` |
| Hip "flexion" definition | ⚠️ trunk–thigh angle (shoulder–hip–knee), 180° upright, trunk lean contaminates it | test documents definition; `visualise.py:31` labels it "Hip Flexion" |
| Shoulder tilt | ❌ unsigned, direction-dependent (0° or 180° for level shoulders), unused | test FAILS |

**Unit tests** (`_audit/tests/test_angles_audit.py`, run from `_audit/sandbox`): **11 passed, 7 failed** (`out_pytest.txt`)

```
PASSED test_angle_known_values[90/180/0/45/120]          (5)
PASSED test_arccos_domain_is_clipped
PASSED test_returns_degrees_not_radians
PASSED test_y_axis_inversion_does_not_change_unsigned_angle
PASSED test_left_knee_uses_mediapipe_left_indices
PASSED test_hip_angle_is_trunk_thigh_not_hip_flexion
PASSED test_cadence_robust_to_jitter[3]
FAILED test_degenerate_points_should_be_nan              got 90.0
FAILED test_aspect_ratio_preserves_angle_on_portrait_video  true 121.9 vs app 91.1
FAILED test_shoulder_tilt_level_shoulders_facing_either_way 179.94 == 0 ± 1
FAILED test_cadence_reports_steps_per_minute             54.1 == 110 ± 11
FAILED test_cadence_robust_to_jitter[6]                  75.1 == 54.1 ± 5.41
FAILED test_healthy_walker_classified_walking            'Unknown' == 'Walking'
FAILED test_symmetry_index_detects_halved_knee_rom       (7.3, 'good')
```

### B3. Gait event detection & metrics

- **Heel strike / toe-off:** **not detected at all.**
- **Stride / step length:** not computed.
- **Cadence** (`risk_scoring.py:238-244`, duplicated `activity_classifier.py:12-15`): the count of frames where the left knee angle crosses upward through 155°, divided by `time_s.max()`, × 60.
  - Standard cadence (steps/min) counts steps of **both** feet, i.e. heel strikes per minute. Left-knee extension events happen once per **stride** (two steps), so the formula reports roughly half the true cadence: synthetic 110 steps/min → 54.1.
  - There is no hysteresis or smoothing, so each noisy crossing counts: +6° Gaussian noise → 75.1; +10° → 96.2.
  - On the real clip, 10 of 30 counted events are <0.4 s apart (physically impossible for one leg at walking speed).
  - The real clip's plausible-looking "107 steps/min" is **two bugs cancelling**, not a measurement.
  - The clip also contains ~6 turns and in/out-of-frame segments that are counted as walking (`contact_sheet.jpg`).
- **"Cadence irregularity"** (`activity_classifier.py:31-37`): the coefficient of variation of intervals between peaks of left-ankle y. Healthy sample = 50.4%, far above the 25% limp threshold. This is not a recognised gait-variability measure in this form (literature uses stride-time CV from detected events, typically ~1–3% in healthy adults).
- **Symmetry:** Robinson-style SI `|L−R| / mean × 100`, but applied to the **mean joint angle over the clip**. The literature applies SI to discrete parameters (step length, step time, stance time, ROM per stride). Using absolute angles near 160–180° divides by a large number and hides asymmetry: 50% ROM loss → 7.3%.
- **Scale calibration:** none, and none is claimed. Step length is not reported in any unit. It **cannot** be computed in metres from monocular 2D without a known reference (a marker of known length in the walking plane, a known walkway distance, or subject height + a pinhole assumption). If added later, it must be labelled as relative (e.g. step length / leg length), or calibrated with a floor marker of known length.

### B4. Activity classification (`activity_classifier.py`)

- **Type:** rules only. No training data, no model, no evaluation, no confusion matrix, no held-out set. **🔴 No ground-truth validation set exists.**
- **Every threshold:**

| Rule (order matters) | Threshold | Justification in code | Brittleness (measured) |
|---|---|---|---|
| Limping | knee mean-angle SI > 15% **and** cadence irregularity > 25% | none | Irregularity is 38–59% on every healthy variant → condition is effectively SI-only |
| Running | "cadence" > 150 **and** 180−min(knee) > 70 | none | Cadence is half of true, so real running (160–180 spm) reads ~80–90 → not Running; yet the feet-occluded walk → Running 95% |
| Brisk Walking | "cadence" > 120 **and** flexion > 55 | none | Mirror or upscale of the same walk flips Walking→Brisk |
| Walking | "cadence" > 60 **and** flexion > 35 | none | Clean 110 spm synthetic walk ("cadence" 54) → Unknown |
| Confidence | `min(95, 50 + asym + irreg/2)`, `60 + (cad−150)/2 + (flex−70)/2`, `55 + (cad−120)/2`, `50 + min(cad,120)/4`, fixed 30 | none — monotone in the input magnitude, not a probability | Feet-occluded → 95% "confident" |

### B5. Risk scoring (`risk_scoring.py:68-302`) — full reverse-engineering

Inputs: the angle DataFrame, `activity` (from B4), and `mode`. All thresholds come from `MODE_CONFIGS[mode]`.

| Term | Input | Condition (Clinical / Runner / Athlete / Elderly) | Points |
|---|---|---|---|
| Knee symmetry | `SI_k = |mean(knee_L) − mean(knee_R)| / mean × 100` | > 20/15/10/25 → flagged | +30 |
| | | > 10/8/5/15 → mild | +15 |
| Hip symmetry | same on trunk–thigh angle | > 20/15/10/25 → flagged | +20 |
| | | > 10/8/5/15 → mild | +10 |
| Knee flexion (activity = Running) | `180 − min(knee)` each side | either side < 70/80/85/60 | +20 |
| Limp (activity = Limping) | — | always | +25 (and cadence term skipped) |
| Knee flexion (otherwise) | `180 − min(knee)` | either side < 45/50/55/35 | +20 |
| Cadence | one-leg crossings/min (B3) | < lower bound of mode×activity range (e.g. Clinical Walking 80) | +10 |
| **Total** | `min(risk, 100)` — **max reachable 80** | | |

- **Bands:**
  - 0 "No issues detected"
  - 1–25 "Minor findings" (green)
  - 26–50 "Moderate concern" (amber)
  - 51–75 "Significant issues" (red)
  - 76–100 "Serious abnormality" (red)
- **Grounding:** none of the weights (30/20/20/25/10/15/10) or thresholds has a citation, a comment, a normative dataset or a validation.
  - Some numbers loosely echo literature, e.g. adult walking cadence ~100–120 steps/min, and ~60° peak swing knee flexion. But they are compared against incorrectly computed quantities (half-cadence, min-over-clip flexion on distorted angles), so even the plausible numbers are misapplied.
  - Mode thresholds are invented; "Elderly: 60–100 steps/min is safe" has no source.
- **Stability** (`out_stability.txt`):
  - Identical input: identical output (deterministic).
  - Sub-pixel landmark noise σ=0.001 (≈0.5×0.85 px): cadence swings 96.4–114.3; activity stable; score 0.
  - σ=0.004: 5/25 runs flip to Brisk Walking; cadence 100–136; score 0.
  - Every-other-frame (15 fps): cadence 107 → 82.
  - The score doesn't swing because it is pinned at 0: it is **insensitive**, not stable. A simulated 60% loss of right-knee flexion scores 20 ("Minor findings"); knee SI is 7.7%, "good".
  - The score's discrete jumps (0/10/15/20/25/30…) at hard thresholds mean real patients near a boundary will flip categories between sessions from noise alone. That is exactly what the "Needs attention: three consecutive increases" rule (`clinician_router.py:125-128`) will then amplify.
- **Straight answer:** **No.** Do not present this to a clinic as a "risk score", today or after cosmetic fixes. It has no outcome it predicts, no validation, and a max of 80. It returned "healthy" for garbage input and "minor" for a simulated severe impairment.
- **Safer presentation:** a **measurement summary**.
  - Per-side values with units: peak knee flexion in swing (median of strides ± SD), stance/swing ratio, cadence (steps/min), step-time asymmetry (%).
  - Each value shown next to a **cited** typical adult range, e.g. "typical healthy adult walking ≈ 55–65° peak knee flexion (side-view marker-based studies)".
  - A **recording-quality badge**: frames usable %, view check passed, strides detected N.
  - A **measurement uncertainty** from your own validation, e.g. "±6° vs goniometer, side view".
  - No composite, no colours implying danger, and clinician interpretation required.

### B6. Reproducibility & determinism

- **Local determinism:** ✅ same process, same file → identical landmarks.
- **Local vs Render:** ❓ likely **different**.
  - Different CPU architecture (arm64 vs x86_64) → different XNNPACK kernels and float rounding.
  - Different OpenCV/FFmpeg decode path depending on which of the three `cv2` wheels wins install order.
  - Python version possibly different (`runtime.txt` likely ignored by Render).
  - Because the metrics are threshold-crossing counts on unsmoothed signals, tiny float differences change counts (σ=0.001 noise moves cadence by ±9%).
- **Versioning:** no `pipeline_version` or model hash stored with results, so a result cannot be traced to the code or model that produced it. The MediaPipe version is pinned; everything around it is not.

---

## 8. Part C — SaaS-readiness gap

| Capability | Status | Evidence | Effort |
|---|---|---|---|
| Multi-tenancy (clinic → practitioners → patients) | ❌ | Flat `users` with a free-text role; no org/clinic entity (`models/user.py:11-18`) | L |
| Auth | ⚠️ | JWT exists; secret public, 1-year tokens, no refresh, no reset, no email verify (F01, F08) | M |
| Roles / RBAC | ⚠️ | 2 roles, client-chosen (F03); no admin, no org owner | M |
| Audit logs (who viewed which patient) | ❌ | None | M |
| Patient records | ❌ | Patients are login accounts; clinician can't create a patient; `patient_name` unused (F40) | M |
| Longitudinal progress | ⚠️ | History list + risk/knee-SI line charts (`App.js:637-666`); built on invalid metrics; no session comparison | M |
| Async processing (queue, status, retries) | ❌ | Synchronous in request (F13) | L |
| Consent flow | ❌ | None (A3) | M |
| Retention & deletion policy | ❌ | None; accidental deletion via ephemeral disk (F06) | M |
| Data export (patient right of access) | ❌ | None | S |
| Billing hooks (credits / per-analysis) | ❌ | None | M |
| Monitoring / uptime / metrics | ❌ | `/status` exists but blocked during work (F13) | S |
| Error tracking | ❌ | `print` only (F41) | S |
| Backups | ❓ | Depends on Render Postgres plan; not configured in repo; not verifiable | S |
| Capture guidance (device/camera) | ❌ | UI says "Any angle" (`App.js:418`) | S |
| Recording-quality gate | ❌ | F26 | M |
| Validated measurements | ❌ | F22 | L |

---

## 9. What could be done differently

1. **Measurement tool, not diagnostic app** (recommended positioning). Sell "objective, repeatable side-view knee/hip angle curves + cadence + step-time asymmetry, with a capture protocol and published error bars". Clinicians interpret. This removes the regulatory risk of the risk score, is what physios actually lack (a goniometer only measures static angles), and is validatable by a student.
   - Trade-off: less "AI" sizzle.
2. **Browser-side pose estimation** (the alternative you probably haven't considered). Run MediaPipe `PoseLandmarker` (Tasks, WASM/WebGL) **in the browser or a phone PWA** and upload only the landmark time series (~1 MB), not the video.
   - **Privacy by design:** no raw biometric video ever leaves the device, which shrinks DPDP exposure and storage cost.
   - **Infra:** it also removes the 512 MB / CPU bottleneck on Render.
   - **Capture guidance:** it enables live guidance while recording ("step back, full body not visible", "turn sideways").
   - Trade-offs: slower on low-end Android devices; you lose the ability to re-run a newer model on old videos unless the clinic opts in to video upload; harder to guarantee identical model versions across devices (pin the model asset and send its hash with the data).
3. **Better pose model server-side.** RTMPose/RTMW via ONNX Runtime or ViTPose give better joint accuracy than BlazePose on sagittal lower limbs. Pair with a 2D→3D lifter (e.g. MotionBERT) only if you have validation data.
   - Trade-off: heavier (GPU for real-time), and hard on a student budget. Not worth it before a validation harness exists to prove the gain.
4. **Calibrated capture.** Require a floor marker (A4 sheet or tape of known length) in the walking plane. This gives px→m scale, so step length and gait speed become possible. Gait speed is the single most clinically useful gait number ("the sixth vital sign") and is cheap to get with a timed 4 m / 10 m walk.
5. **Architecture alternative:** a managed queue + serverless GPU/CPU (Modal, Replicate-style) for the worker instead of a Render background worker.
   - Trade-off: pay-per-second is good at low volume but is vendor lock-in; a Render worker is simpler to explain in interviews.
6. **Drop the LLM entirely** for v1. A clinician-curated exercise library, attached by the clinician, is safer and more useful than AI-written patient advice.

---

## 10. Resume / portfolio honesty check (current state)

**Truthful description today:**
> "Built a full-stack prototype (FastAPI, MediaPipe, React) that extracts 2D pose landmarks from walking videos, computes joint-angle time series, applies rule-based heuristics to summarise gait, and generates PDF reports; deployed on Render/Vercel with JWT auth and a basic clinician–patient linking flow. Prototype stage: metrics are unvalidated."

**Currently overselling (do not claim):**

| Claim | Why it fails in an interview |
|---|---|
| "AI-powered gait **risk** scoring" | It's four additive `if` statements, max 80, no outcome, no validation |
| "Activity **classification** model" | Four threshold rules; no training data |
| "**RAG** pipeline" | No retrieval; tag lookup + one LLM sentence |
| "Calculates cadence" | Counts one-leg crossings + jitter; reports ~half the true value on clean input |
| "Works on CCTV / any angle" | 2D sagittal only; 60° reads 45° at 45° yaw, 0° frontal |
| "Clinical-grade / clinical assessment" | No validation, no reference data |
| "Secure multi-user / HIPAA / DPDP compliant" | Public JWT secret, unauthenticated health-data endpoints, no consent/deletion |
| "Production SaaS" / "used by clinics" | Unless true, don't; the architecture handles one analysis at a time |
| "Progress tracking" (as a clinical feature) | It's a line chart of the invented score |
| Any accuracy number | None has been measured |

---

## 11. Not audited

| Item | Why |
|---|---|
| Live Render/Vercel dashboard config (instance type, start command, env vars, health-check path, Postgres plan and backups, region) | Not in repo; no dashboard access. Assumptions A1–A2 |
| Render's maximum HTTP request duration | Official page fetched didn't state it; community forum unreachable |
| Live exploitation of F01/F02 | Deliberately not done: no writes to production, no access to real users' data. All reproduced locally against a throwaway DB with the same code |
| Real frontal, angled, baggy-clothing, and poor-lighting footage | Only one real clip exists (3 identical copies). Frontal/angled covered by the geometric probe (B2); lighting by a synthetic darkened variant; clothing not probed |
| Real multi-person footage (overlapping/occluding people) | Only side-by-side synthetic composite |
| Groq call behaviour (latency, output format failures, cost) | No API key used; the fallback path was exercised; the markup-crash risk was proven with a synthetic string |
| Render x86_64 vs local arm64 numeric differences | No x86 environment run; reasoned in B6 |
| Frontend runtime in a browser (visual review, Lighthouse, screen reader) | Built and read the code; did not run a browser session |
| Postgres-specific behaviour | Probes used SQLite |
| Load test beyond one concurrent analysis | The event-loop block makes the result deterministic (serialised); a multi-client test would only restate it |
| Legal opinion on DPDP / medical-device classification (CDSCO) | Engineering audit only; the table in A3 is a checklist, not legal advice. Whether software making diagnostic claims is a medical device in India should be checked with counsel before any clinic sale |
