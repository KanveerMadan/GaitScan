# GaitScan — Rebuild Plan V2 (proposal)

**Status:** proposal, not adopted. `REBUILD_PLAN.md` is unchanged and remains the plan of record until you accept this.
**Basis:** [`FUNDAMENTALS_REVIEW.md`](FUNDAMENTALS_REVIEW.md), recommended option **D** (research-first, narrow product).
**Effort figures** are estimates [I], assuming 10–15 h/week as in V1.

## Goal in one sentence

An open-source, privacy-first browser tool reports a small set of gait metrics from a side-view phone video. Pose estimation runs on the device and the video is never uploaded. Every number has a published error bar and minimal detectable change, and the tool is backed by a validation and repeatability study submitted for publication.

## Product scope (v1)

| In | Out |
|---|---|
| Cadence (steps/min) | Risk / deviation score, "findings", modes |
| Stride time and step time per leg (s); step-time asymmetry (%) | Activity classifier |
| Peak swing knee flexion per stride (median ± SD, °) | Ankle angles; angle-based L/R symmetry |
| Gait speed and step length **only** with the floor-scale protocol | Uncalibrated speed or length in metres |
| Recording-quality gate with actionable messages | Frontal-plane metrics (valgus, pelvic drop, lateral trunk) |
| Per-stride CSV/JSON export; local session history | Exercise suggestions, LLM text |
| Session comparison against the person's own baseline, with an MDC indicator | Clinician dashboard, invites, orgs, multi-tenancy, billing |
| Intended-use statement + claims policy (ADR-010) | Accounts (unless a real need appears) |

The stance % and hip angle stay **out** unless the Phase V3 validation meets pre-specified limits; then they can be added.

## ADR changes

| ADR | Action |
|---|---|
| 001 modular monolith + `gaitcore` | **Keep.** `gaitcore` stays the single source of analysis logic; its input becomes landmark arrays (from browser JSON or the Python CLI). |
| 002 Postgres job queue + worker | **Superseded** by ADR-009: no server-side video processing. |
| 003 object storage + TTL | **Superseded** by ADR-009: no video storage. |
| 004 tenancy + auth | **Superseded**: no orgs or patients. Revisit only if a real multi-user need is validated. |
| 005 no risk score; measurement summary | **Keep; strengthen.** No angle "typical ranges" until method-matched norms exist (review §3.2). Spatiotemporal ranges (speed, cadence) only with citations. |
| 006 pipeline v2 | **Amend.** Pose comes from MediaPipe Tasks Web in the browser [S39], with model version pinned and recorded. The Python CLI uses the same model for batch evaluation, and a golden test checks equivalence. Ankle and angle-symmetry outputs are removed. Step length/speed only with calibration. |
| 007 consent/retention | **Rewrite.** App: nothing leaves the device by default; local data deletable in one click; a plain privacy notice. Study: written informed consent, IEC approval, pseudonymised landmark data only, video deleted after annotation (study-protocol specific). |
| 008 frontend | **Amend.** Vite + TS stays. No job polling or TanStack-for-jobs. Local-first SPA (IndexedDB history), one optional typed call to the analysis endpoint (or none if analysis is ported). |
| **009 (new)** on-device pose extraction | **Decision.** Use the browser MediaPipe Pose Landmarker (VIDEO mode). Send only landmarks, if anything, to a stateless `/v1/analyze-landmarks` endpoint that stores nothing (or run the analysis in-browser later). **Consequences:** no queue, no storage, no video DPDP exposure. Device variability must be benchmarked and validated per device class. |
| **010 (new)** intended use and claims | **Decision.** Intended use: "education, research and personal tracking; not for diagnosis, screening, monitoring or treatment of any disease or condition" (CDSCO general-wellness boundary [S33]). Wording rules as in review §4.3, enforced by `tests/test_language.py` (backend) and the frontend banned-words test. |

## Revised phases

### V2: Measurement core on landmarks (≈ 25 h, 2–3 weeks)
Largely the old Phase 2, re-targeted.
1. `gaitcore` takes landmark arrays (+ fps, frame size) as input; video decoding moves out of the core. (3 h)
2. Pixel-space angles, NaN on degenerate vectors, signed knee flexion (F25, F42). (2 h)
3. Visibility gating, short-gap interpolation, 6 Hz zero-phase low-pass (F26). (3 h)
4. Steady-state walking-segment detection (exclude turns and out-of-frame spans). (4 h)
5. Per-leg heel-strike / toe-off; cadence, stride/step time, step-time asymmetry, per-stride peak swing knee flexion (F24, F27). (6 h)
6. Quality gate: side-view check, single person, visibility, ≥ 4 clean strides, fps ≥ 25; plus a **setup fingerprint** (body height in pixels, walking-line angle) for longitudinal comparability. (4 h)
7. Delete `legacy.py` scoring, modes, classifier, exercises, the LLM path and their DB columns. Port the audit tests; the aspect-ratio and 110 spm tests must pass. (3 h)

**Acceptance:**
- the audit tests that ADR-006 targets are green;
- synthetic 110 spm reads 110 ± 3;
- the bad variants are rejected with reasons;
- `mypy --strict` stays clean on `gaitcore`.

### V3: On-device capture and the thin app (≈ 22 h, 2–3 weeks)
Replaces the old Phases 3 and 4.
1. Browser capture/upload-from-gallery → MediaPipe Tasks Web pose loop (VIDEO mode) → landmark JSON, with progress UI. (6 h)
2. Analysis path:
   - the stateless `/v1/analyze-landmarks` endpoint (existing FastAPI app, no DB writes), **or**
   - a TS port of the small signal-processing layer.

   Decide by the benchmark in step 3. (4 h)
3. Device benchmark: 3–4 phones (one budget Android) × 30/60 fps. Record processing speed and landmark agreement against the Python pipeline on the same clips. (4 h)
4. Capture-guidance screen with live quality-gate feedback; results page with per-metric units and placeholders for error bars (filled in V5). (5 h)
5. Local history (IndexedDB), CSV/JSON export, "delete all my data". (3 h)

**Acceptance:**
- a full walk-through on a budget Android phone with the network disconnected after page load (if analysis is in-browser), or with only landmark JSON visible in DevTools (if server-side);
- no video bytes leave the device (asserted in an e2e test via request inspection).

### V4: Validation study protocol and tooling (≈ 20 h + 4–8 weeks calendar time for ethics)
New phase, run in parallel with V3.
1. Write the protocol:
   - claims: cadence, stride time, peak knee flexion, calibrated speed;
   - references: 2-annotator frame labels at 60 fps, timed distance, plus electrogoniometer or IMU, or a public mocap dataset [S7, S11, S45];
   - n ≥ 20–30 justified by Lu 2016 / Bonett [S41, S43];
   - 2 sessions;
   - pre-specified acceptable limits of agreement.

   Pre-register it (e.g. OSF). (6 h)
2. Submit to the IEC; prepare consent forms and the data-management plan (pseudonymised landmarks kept; raw video deleted after annotation). (4 h + waiting)
3. Annotation tool (frame-stepper for heel strike / toe-off) and inter-annotator agreement script. (5 h)
4. `gaitcore.eval` CLI: Bland–Altman (repeated measures), MAE/RMSE, ICC(2,1) reported per Koo & Li, SEM, MDC95, event timing error [S40]. Unit-tested on synthetic data. (5 h)

**Acceptance:** IEC approval letter (or a written exemption); a pre-registration link; the eval CLI reproduces a known Bland–Altman example.

### V5: Data collection and analysis (≈ 20 h + 3–6 weeks calendar time)
1. Collect: ≥ 20 adults × 2 sessions × ≥ 3 trials, 2 phones, 30/60 fps, one oblique trial per subject for the quality gate. (calendar)
2. Annotate (2 annotators), run the eval, produce `reports/eval-<version>.md` including failures and negative results. (12 h)
3. Feed the measured LoA and MDC into the app's error bars and the session-comparison indicator. Drop any metric that misses its pre-specified limit. (4 h)
4. CI regression gate on a small eval subset (MAE must not worsen by more than 1°, event error by more than 1 frame). (4 h)

**Acceptance:**
- the eval report is committed;
- every displayed metric has an error bar and an MDC from this study;
- metrics that failed their limits are removed from the UI.

### V6: Paper and release (≈ 25 h, 3–4 weeks)
1. Manuscript following COSMIN-style reporting [S44]:
   - methods, agreement and reliability, limitations (healthy adults only, side view, devices tested);
   - a comparison with Stenum 2021/2024 and OpenCap Monocular [S1, S2, S8].

   (15 h)
2. Preprint (medRxiv/arXiv) + journal submission (e.g. *Sensors*, *JMIR Formative Research*) or IEEE EMBC; supervisor co-authorship [Q]. (4 h)
3. Open-source release: licence, README with the validation table and intended use, anonymised landmark dataset with a data statement. (4 h)
4. Portfolio write-up: the audit → fixes → validation story. (2 h)

**Acceptance:** a preprint DOI and a submission confirmation; a tagged release whose README numbers match the paper.

### Optional V7: Longitudinal UX (≈ 10 h)
Trend view of your own baseline with MDC bands; a setup-consistency checklist. Only after V5 shows the MDC is small enough to be useful.

**Total:** ≈ 112 h core (+ 10 h optional), against ≈ 135 h remaining in V1 for Phases 2–6. The calendar is dominated by ethics and recruitment (≈ 3–4 months end to end [I]).

**Gate (hard):** if by the end of V4 there is no IEC path or no realistic route to ≥ 20 participants, stop after V3. Publish V2+V3 as an open-source tool with a technical report and treat the project as option E-plus.

## Mapping from V1

| V1 phase | V2 fate |
|---|---|
| 2: Measurement core v2 | → **V2** (kept, narrowed; landmark input) |
| 3: Async jobs + object storage | **Deleted** (ADR-009) |
| 4: Tenancy, auth, consent, deletion | **Deleted**; study consent moves to V4, local deletion to V3 |
| 5: Validation harness | → **V4 + V5** (expanded, becomes the core) |
| 6: Product & report | → **V3** (capture + results) and **V7** (longitudinal); billing, clinic PDF and dashboard deleted |
| (new) | **V6** paper + release |

## What from Phases 0–1 becomes unnecessary

Kept in git history as portfolio evidence; remove from the running product when V3 lands:
- Clinician role, invite codes, `/clinician/*`, `/patient/join`, clinician dashboard (frontend).
- `/analyze` video upload path, upload validation, plots, server-side PDF generation and regeneration (F15 work).
- Exercises module and the Groq/LLM integration.
- JWT auth, registration/login rate limits, change-password, the `users`/`sessions`/`findings`/`exercises` tables, Postgres + Alembic, but **only if** no accounts are kept. If a stateless landmark endpoint is the only server piece, it needs neither a DB nor auth (keep CORS, size limits and rate limiting by IP).
- `render.yaml` web service may shrink to the stateless API; the frontend becomes the main deployable.

Stays as-is: CI in both repos, pre-commit, Docker for the API, structured logging with redaction, `.env.example` discipline, the testing culture (failing test first), the audit tests, and the security probe pattern (rewritten for the smaller surface).

## Decisions needed from Kanveer before adopting

See `FUNDAMENTALS_REVIEW.md` §8. The blocking ones:
- goal priority;
- hours per week;
- an IEC path;
- access to participants and a dynamic reference (IMU, electrogoniometer, or a lab);
- a supervisor or co-author.
