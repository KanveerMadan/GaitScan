# GaitScan — Rebuild Plan V3 ("correct and usable")

**Status:** plan of record, adopted 2026-10-03 (owner decision).
**Supersedes:** [`REBUILD_PLAN.md`](REBUILD_PLAN.md) (V1) and [`REBUILD_PLAN_V2_PROPOSAL.md`](REBUILD_PLAN_V2_PROPOSAL.md) (V2, never adopted). Both are kept for history.
**Inputs:** [`GAITSCAN_AUDIT.md`](GAITSCAN_AUDIT.md) (findings F01–F44), [`FUNDAMENTALS_REVIEW.md`](FUNDAMENTALS_REVIEW.md) (sources `S#`), `adr/`, the dataset scan on branch `research/novelty-scan` (`_audit/research/DATASETS.md`, `FEASIBILITY.md`; sources `N#`), [`phase-reports/`](phase-reports/).
**Effort figures** are estimates, at 10–15 h/week as before.

---

## 1. Goal

GaitScan becomes a clean, usable, fundamentally correct gait-measurement web app. It may coexist with similar tools (OpenCap, Sports2D, Kinovea). It does not need to be novel. The research/paper direction and the broad "mobility toolkit" are **not** being pursued.

The bar for every number the app shows:
1. A single **side-view phone video** can honestly measure it (literature support, review §2.2).
2. It is **computed correctly** (tested against synthetic ground truth, then checked against lab data in Phase 3).
3. It is shown with an **honest error range**, measured on our own pipeline (Phase 3).

Anything that can't meet that bar is removed.

Intended use stays as in the review (§4.3): measurement for education, research and personal tracking; not for diagnosing, screening, monitoring or treating any disease or condition. Wording rules from review §4.3 apply to the app, README and PDF and are enforced by `tests/test_language.py` and the frontend banned-words test.

---

## 2. Metric policy

Status meanings:
- **KEEP:** shown whenever the quality gate passes.
- **CONDITIONAL:** shown only when its condition holds; otherwise it is absent (not estimated, not zero).
- **REMOVE:** deleted from the pipeline, API, database (values archived, not dropped), PDF and frontend in Phase 2.

Review status (R/C/U) is the column of the same name in FUNDAMENTALS_REVIEW §2.2.

| Metric | Policy | Reason | Source |
|---|---|---|---|
| **Cadence** (steps/min, from heel strikes of **both** legs) | **KEEP** | Rated R. Temporal errors are ~20 ms with sagittal video, so cadence error is well under 1 step/min over steady walking. Current code counts one leg's knee crossings and reads 110 spm as 54 (F24). | S1, S2, S54; audit F24 |
| **Step time / stride time** (s, per leg, from heel strikes) | **KEEP** | Rated C: depends on event detection; sagittal step-time errors are 0–0.02 s. One app study found step-time ICC ≈ 0, so Phase 3 must measure our own event error before an error range is shown. | S1, S2, S54 |
| **Sagittal knee angle during walking** (per-stride peak knee flexion, per leg, median ± SD) | **KEEP** | Rated C. MAE 5.6° (OpenPose), 2.4–2.8° (MediaPipe, best camera position), 3.5–4.0° in clinical groups. MediaPipe can confuse left/right in older adults, so each leg's value carries its own valid-stride count. Replaces the outlier-driven 180 − min (F27) and the aspect-distorted angles (F25). | S1, S2, S4, S5; audit F25, F27 |
| **Step length** (m) | **CONDITIONAL**: only with a user-provided floor calibration (two marked points a known distance apart in the walking plane) | Rated C with a floor scale (0.049 m per step; < 0.02 m participant mean) and U without (monocular scale is ambiguous; no validation found). | S1, S2; review §2.2; audit B3 |
| **Walking speed** (m/s) | **CONDITIONAL**: only with floor calibration | Rated C with calibration (≤ 0.04 m/s, side view) and U without. | S1, S2 |
| **Hip sagittal angle** (per-stride thigh excursion, per leg) | **CONDITIONAL**: kept, redefined; must pass the Phase 3 accuracy check or it is removed | The review's evidence supports it at the same tier as the knee (rated C: MAE 4.0° OpenPose, 1.9–2.35° MediaPipe, 2.7–3.3° clinical). The condition is the redefinition the review asks for: the current "hip" is a trunk–thigh angle, 180° when upright (F34). V3 measures the thigh's angle to the image vertical. A side view has no pelvis landmark that tracks tilt, so this is not lab hip flexion; reporting the per-stride **excursion** (max − min) cancels the constant pelvic-tilt offset. The remaining difference is pelvic-tilt motion within the stride; Phase 3 measures it against the lab data. | S1, S2, S5; review §2.2–2.3; audit F34 |
| Risk / deviation score | **REMOVE** | No outcome it predicts and no validation; insensitive (0 for invalid input, 20 for a simulated 60% knee loss); max reachable 80. A risk claim is medical-device software under CDSCO. | Review §2.4; S17, S18, S19, S33; audit F23, B5; ADR-005 |
| Frontal-plane metrics (knee valgus, pelvic drop, lateral trunk lean, shoulder tilt) | **REMOVE** | 2D frontal-plane validity is low to moderate; MediaPipe valgus bias ≈ −19°. GaitScan's `shoulder_tilt` was also direction-dependent and unused. | S9, S10, S51; audit F33 |
| Ankle angles (and the ankle trajectory plot) | **REMOVE** | MediaPipe ankle "completely misidentified" in one study; 7.4° MAE even for OpenPose. | S1, S4, S5 |
| Single-view left/right angle symmetry (knee/hip symmetry index) | **REMOVE** | The far leg is occluded in a side view, and MediaPipe confuses L/R; the existing index was also computed on mean absolute angles, which hides asymmetry (F28). Each leg's own value stays visible. | S4, S50; audit F28 |
| Uncalibrated distances and speeds | **REMOVE** | No validation; monocular scale is ambiguous. Replaced by the calibrated CONDITIONAL rows above. | Review §2.2; audit B3 |
| Activity classification (+ "confidence") | **REMOVE** | Four hand thresholds; a clean 110 spm walk read "Unknown"; the "confidence" is a formula, not a probability. The person recording knows the task. | Review §3.1; audit F30, B4 |
| Mode-specific thresholds (Clinical/Runner/Athlete/Elderly) | **REMOVE** | Invented, labelled "not clinically validated" in the code, contradictory across scoring/PDF/UI. | Review §3.2; audit F35 |
| Exercise suggestions | **REMOVE** | Mapping a measurement to an exercise implies a condition and a treatment, which nothing supports and which CDSCO treats as the top significance tier. | Review §3.3; S33 |
| LLM explanations (Groq) and the `groq` dependency | **REMOVE** | Fluent text about invalid findings; hallucination and automation-bias risks; sending health data to a third party needs notice and a contract. | Review §3.4; S35, S49; audit F37 |

**Not added** (not in the KEEP/CONDITIONAL lists, so out of scope until evidence changes):
- stance/swing % (review: C → treat as U in v1, S54);
- step-time asymmetry (review: C, no direct validation found);
- trunk lean (review: low evidence);
- reference ranges for angles. Normative angle data comes from marker-based models, and comparing our pipeline's values to it mixes method bias with real deviation (review §3.2).

---

## 3. Phases

### Phase 0 — Stop the bleeding: **done**
Report: [phase-reports/PHASE_0.md](phase-reports/PHASE_0.md). Merged to `main` in both repos (PR #1), not yet deployed.

### Phase 1 — Foundations: **done**
Report: [phase-reports/PHASE_1.md](phase-reports/PHASE_1.md). Pushed, not merged and not deployed; Render auto-deploy is off. Human actions are listed in the report.

### Phase 2 — Measurement correctness (≈ 34 h)
**Goal:** every number the pipeline produces is in the KEEP/CONDITIONAL rows of §2, is correct on synthetic ground truth, and comes only from video that passed a quality gate.

| # | Task | Findings | Est. |
|---|---|---|---|
| 1 | Amend the audit spec for the V3 API, keeping its intent, numbers and tolerances (owner-approved 2026-10-03; one separate commit). | F38 | 2 h |
| 2 | Upgrade MediaPipe to the Tasks API at **1.0.1**, the same release as `@mediapipe/tasks-vision` 1.0.1. Pin the same model (`pose_landmarker_full`, `float16/1`) by SHA-256 in its own commit, before any algorithm change. Report landmark deltas. Remove the CI ignores for the protobuf advisories. | F11, F32 | 4 h |
| 3 | Pixel/aspect-corrected angles; NaN for degenerate vectors; signed knee flexion; hip redefined as thigh vs vertical; `shoulder_tilt` direction-independent and not reported. | F25, F33, F34, F42 | 2 h |
| 4 | Visibility masking (never used, never interpolated) and a zero-phase low-pass filter, with parameters justified and tested. | F26 | 3 h |
| 5 | Steady-state segmentation: in frame, constant direction, no turns, no acceleration/deceleration. | F26, F31 | 4 h |
| 6 | Bilateral heel-strike detection (Zeni et al. 2008, adapted to 2D); cadence, step and stride time; per-stride knee and hip values. | F24, F27 | 5 h |
| 7 | Input quality gate with user-facing reasons: multiple people, feet not visible, wrong orientation, non-side view, too little steady walking, too low a frame rate, too short a clip. | F26, F29 | 4 h |
| 8 | Optional floor calibration in the API; step length and speed only when it's given. | B3 | 2 h |
| 9 | Remove every REMOVE row from the pipeline, API, DB, PDF and frontend, including `display.py` (legacy wording filter), the `groq` dependency and the clinician "needs attention" flag. | F23, F28, F30, F35, F37 | 4 h |
| 10 | Alembic migration that archives the removed columns' and tables' values, plus `pipeline_version` and a stored result on every session. Legacy results are labelled and never mixed into trends. | F15 (rest), B6 | 3 h |
| 11 | Units on every metric; a quality block on every result. | — | 1 h |
| 12 | Port the amended audit spec into `tests/`; re-run every probe; minimal frontend changes (no removed metrics, clear rejection reasons). | F38 | 3 h |

**Acceptance:**
- The amended audit spec passes. It also passes once ported into `tests/`, and the substantive tests fail on the pre-Phase-2 code.
- The aspect test passes: true 121.9° reads 121.9° ± 1°.
- Synthetic 110 steps/min reads 110 ± 2.
- The quality gate rejects the bad `make_variants.py` variants and the synthetic bad cases, each with its specific reason; walk01's usable segments are still accepted.
- Step length and speed appear only with calibration.
- The simulated 60% loss of right-knee motion is visible in the right knee's peak flexion.
- No removed metric remains in the pipeline, API, DB, PDF or frontend, and the archived values survive the migration (tested).
- `mypy` strict on `gaitcore`, ruff, the full suites and pip-audit with no ignores all pass.

### Phase 3 — Honest results (≈ 30 h)
**Goal:** every number shown has an error range measured on *our* pipeline, and the results page and PDF say what that range means.

| # | Task | Est. |
|---|---|---|
| 1 | Download and inspect the **OpenCap lab validation data** (SimTK; 10 healthy adults; walking; 5 RGB cameras; marker mocap + force plates; "Apache 2.0 Use Agreement" per the project page, which must be re-checked in the README). Confirm: which camera is nearest sagittal, video fps and resolution, mocap rate, and video↔mocap synchronisation. The research scan could not verify these (DATASETS.md, N27, N69). If the data can't support a sagittal comparison, stop and report; no substitute dataset is chosen without the owner. | 4 h |
| 2 | `gaitcore.eval` CLI: run our pipeline on the chosen camera's walking trials. References: heel strikes from force plates; knee and hip sagittal angles from mocap (definition-matched as far as possible, with the remaining mismatch stated); step length and speed from markers. | 8 h |
| 3 | Agreement statistics per metric: bias, 95% limits of agreement, MAE, n trials/subjects, with leave-one-subject-out where anything is tuned. Committed as `reports/eval-<pipeline_version>.md`. Each metric gets a **pre-specified** acceptable limit before the run (cadence ±2 steps/min, step/stride time ±0.03 s, knee peak ±5°, hip excursion ±5°, step length ±0.05 m, speed ±0.05 m/s; these come from S1/S2 ranges and are written down before the data is processed). A metric that misses its limit is removed from the UI. | 6 h |
| 4 | Error ranges in the app and API: each metric shows "± X (95% LoA, OpenCap lab data, n = 10 healthy adults, side view)". The conditions are always stated with the number. | 3 h |
| 5 | Published reference norms only where they exist and are method-independent enough: gait speed by age/sex (Bohannon & Williams Andrews 2011, S20); cadence intensity context (CADENCE-Adults, S21, labelled as an intensity heuristic, not a normal range). **No angle norms** (review §3.2). Each with its citation in `gaitcore/reference_norms.yaml`. | 3 h |
| 6 | Results page and PDF redesign: measurements with units and error ranges, the quality block, the conditions of validity, the disclaimer; the PDF built from the stored result, so it is deterministic (closes the rest of F15). | 6 h |

**Acceptance:**
- `reports/eval-<version>.md` is committed with n, conditions, the pre-specified limits and every metric's result, including failures.
- Every displayed metric has an error range from that report.
- Failed metrics are gone from the UI.
- No norm appears without a citation.

**Honesty note:** n = 10 healthy adults in a lab is a small, best-case reference. The app must say so next to the number. Test–retest/MDC is not measured, so Phase 4's history notes use the agreement range, not an MDC.

### Phase 4 — Usability (≈ 28 h)
**Goal:** a person can record, upload, wait without the server freezing, and understand their result on a phone.

| # | Task | Findings | Est. |
|---|---|---|---|
| 1 | Non-blocking analysis: `POST /analyze` stores the upload in a temp file, returns `202 {job_id}`, and runs the pipeline in a FastAPI background task (in a thread so the event loop stays free). An `analysis_jobs` table holds status (queued/running/succeeded/rejected/failed) and the result id; `GET /analyze/{job_id}` serves status for polling. Video deleted in `finally:` as now. **No Redis, Celery, worker service or object storage.** Jobs interrupted by a restart are marked failed at startup. | F13, F21 | 6 h |
| 2 | Memory/duration guard: downscale frames to 640 px long side before inference (only after the Phase 3 eval confirms the error range is unchanged at that size), cap clip duration, one analysis at a time per process (a semaphore). | F14 | 3 h |
| 3 | Capture guidance UI: a checklist (side view, phone still at hip height, 3–4 m away, whole body in frame, walk across and back, ≥ 30 fps), an example frame, rejection reasons mapped to fixes, and a floor-calibration point picker on the first frame. | F29 | 5 h |
| 4 | Split `App.jsx` per ADR-008 (amended): React Router routes, a typed API client generated from OpenAPI, and TanStack Query for the status polling. | F39 | 8 h |
| 5 | Mobile-friendly layout and accessibility basics (labels, focus, no colour-only status). | F39 | 4 h |
| 6 | History: v2 sessions only in trends, legacy sessions listed separately, and a "within measurement error" note when the change between two sessions is smaller than the Phase 3 error range. | — | 2 h |

**Acceptance:**
- `/healthz` p95 < 200 ms while an analysis runs (`concurrency_probe.py` adapted).
- A full walk-through on a phone-width viewport.
- No frontend file > 400 lines.
- The typed client compiles against the live OpenAPI schema in CI.

### Phase 5 — Privacy & close-out (≈ 16 h)
| # | Task | Findings | Est. |
|---|---|---|---|
| 1 | Consent screen before first analysis: what is processed, that the video is deleted immediately after analysis, what is stored (measurements only), where it is hosted, and how to delete it. A consent record (version + timestamp) per user. | F06 | 3 h |
| 2 | Account and data deletion: `DELETE /me` removes the user, sessions, results and archive rows; tested. | F06 | 3 h |
| 3 | Data export: `GET /me/export` returns JSON of every stored session and result (including archived legacy values). | F06 | 2 h |
| 4 | F40: the analysed person's name is entered, sent and shown on the result and PDF (or the field is removed if the owner prefers anonymity); clinicians can see linked users' results only. | F40 | 2 h |
| 5 | Final README with what is measured, the error table from Phase 3, the capture protocol, and **known limitations** (side view only, one person, healthy-adult lab validation, phone variability not measured). | F22 | 2 h |
| 6 | Re-run every audit probe; final findings table showing each of F01–F44 as **closed** or **explicitly accepted with a reason**. | all | 4 h |

**Acceptance:**
- Deletion and export are proven by tests.
- Every audit probe is re-run and its output committed.
- The findings table has no F-ID without a status.

**Total remaining:** ≈ 108 h (Phase 2 34 + Phase 3 30 + Phase 4 28 + Phase 5 16).

---

## 4. Explicitly dropped

- **Clinic multi-tenancy** (orgs, memberships, patient records, audit log) from ADR-004. The existing user accounts and clinician links stay as they are.
- **Object storage** (ADR-003). Videos stay server-side only as a temporary file and are **deleted immediately after analysis**, success or failure (already true since Phase 0).
- **A job queue** (Postgres jobs + worker, Celery, Redis; ADR-002). Phase 4 uses a FastAPI background task + status table instead.
- **On-device processing** (V2's ADR-009).
- **The participant study and the paper** (V2's V4–V6). Accuracy is checked against public lab data in Phase 3 instead; no human-subject data is collected.
- Billing, the clinic PDF with clinician notes, the clinician "needs attention" rule, and session-comparison MDC (no test–retest data).

---

## 5. ADR changes

Each ADR file keeps its text; only its status header changes.

| ADR | Status | Why (one line) |
|---|---|---|
| 001 Modular monolith + `gaitcore` | **Kept, amended** | The split stays; there is no worker process (the Phase 4 background task runs in the web process), and results record `pipeline_version` plus the model SHA-256. |
| 002 Postgres job queue + worker | **Superseded by V3** | No job queue (§4); Phase 4 uses a FastAPI background task with a status table and polling. |
| 003 Object storage + TTL | **Superseded by V3** | No object storage; video is a temp file deleted right after analysis. |
| 004 Tenancy + auth | **Superseded by V3** | No clinic multi-tenancy; existing accounts, PyJWT and rate limits from Phases 0–1 stay. |
| 005 No risk score; measurement summary | **Kept, amended** | Risk score, modes and classifier removed as decided; metrics follow V3 §2; reference ranges only from cited norms (no angle norms); legacy results labelled via `pipeline_version`. |
| 006 Pipeline v2 | **Kept, amended** | MediaPipe Tasks 1.0.1 with `pose_landmarker_full float16/1` pinned by hash; low-visibility points masked, never interpolated; ankle angles and stance % not reported; hip redefined; floor calibration for distances. 640 px downscale moves to Phase 4, after the Phase 3 eval. |
| 007 Privacy, consent, retention | **Kept, amended** | No R2/TTL/org consent records; a user-level consent screen, deletion and export in Phase 5; LLM removed entirely, not just off by default. |
| 008 Frontend | **Kept, amended** | Vite + TS, router, typed OpenAPI client and TanStack Query stay; routes are user/session based (no `/patients` tenancy); polling is for the Phase 4 analysis status. |

V2's proposed ADR-009 (on-device pose) and ADR-010 (claims policy) are **not adopted**. The claims wording rules live in review §4.3 and the language tests.

---

## 6. Open findings → phase

| Phase | Findings |
|---|---|
| 2 | F11 (protobuf), F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34, F35, F37, F42, F15 (remaining: report built from the stored result) |
| 3 | F22 |
| 4 | F13, F14, F21, F39 (rest) |
| 5 | F06 (rest), F07 (rest: content/duration checks, if not done in 4), F12 (accept or close), F18 (history rewrite: human), F40, F43/F44 re-check, final table for all F01–F44 |
