# Phase 2 — Measurement correctness: report

Plan: [REBUILD_PLAN_V3.md](../REBUILD_PLAN_V3.md) (adopted this phase). Branches: backend and frontend
`rebuild/phase-2-measurement`, **stacked on `rebuild/phase-1-foundations`**. On 2026-10-03 `git fetch`
showed Phase 0 merged into `origin/main` (PR #1, both repos) but Phase 1 **not** merged, so Phase 2
could not branch from main. Merge order: Phase 1, then Phase 2.

## Summary

GaitScan now measures only what one side-view phone video can honestly measure, and refuses clips it
can't measure.
- **Measurement core (`gaitcore` v2, pipeline 2.0.0):**
  - MediaPipe 1.0.1 Tasks with a SHA-256-pinned model (the same release and model file as
    `@mediapipe/tasks-vision` 1.0.1);
  - pixel-space angles;
  - low-visibility masking with no interpolation;
  - a 6 Hz zero-phase filter;
  - steady-state segmentation;
  - bilateral heel-strike detection (Zeni 2008);
  - per-stride knee and hip values;
  - optional floor calibration;
  - a quality gate with eight specific, user-facing rejection reasons.
- **Removed everywhere:** the risk score, activity classifier, modes, symmetry indices, findings,
  exercises, Groq/LLM, plots and the legacy wording filter. They're gone from the pipeline, API, DB,
  PDF and frontend.
- **Old values archived:** migration `0003` copies them verbatim into `session_archive` before
  dropping the columns. That's proven on SQLite and Postgres, and downgrade restores them.
- **Legacy sessions** are labelled, show no numbers, and never enter trends.

**One acceptance criterion is not met: walk01 is rejected.** No pass in that portrait clip contains a
complete step, so the gate answers `too_little_walking`. I kept the rule rather than loosen it for
the only real clip (hard rule 6). Real-footage accuracy is Phase 3's OpenCap check.

The audit spec needed an owner-approved amendment: four tests encoded removed features, and one broke
on the required upgrade. With the amendment it passes **18/18**, and it is ported into `tests/`.

## Acceptance criteria

| # | Criterion (Step 2) | Result | Evidence |
|---|---|---|---|
| 1 | MediaPipe upgrade first, own commit; same model as Tasks for Web; deltas; golden; CI ignores removed | **PASS** (synthetic part: see note) | `21ec11f`: 1.0.1, `pose_landmarker_full` float16/1, SHA-256 `5134a3aa…11b1`. Linux arm64 deltas, walk01: lower-limb median 6.0 px (p95 32.8), knee median 2.2° (p95 11.6°). For scale, the platform switch alone (macOS → Linux on 0.10.9) gives 0.8°. Golden unchanged, not regenerated. Both protobuf ignores removed; pip-audit clean without ignores. Note: a rendered synthetic figure is detected in only 5/120 frames on 1.0.1 (55/120 on 0.10.9), so synthetic checks are at the landmark level. `phase2_mediapipe_upgrade.txt` |
| 2 | Pixel-space angles; portrait 121.9° test passes | **PASS** | `test_aspect_ratio_preserves_angle_on_portrait_video` passes (amended call, same numbers) |
| 3 | Low-visibility landmarks masked, never used | **PASS** | `signals.masked_xy`; no interpolation; strides touching a masked frame give no knee value (`test_measurement.py`) |
| 4 | Smoothing justified | **PASS** | 2nd-order Butterworth, filtfilt, 6 Hz, Gustafsson initial conditions. Basis: Winter 2009 (textbook convention; not re-read this session) plus synthetic tests: signal kept within 2% of range, noise RMS −30%+ |
| 5 | Bilateral heel strikes; synthetic 110 → 110 ± 2; step/stride from events | **PASS** | Overground walker 109.1, treadmill-style audit walker 109.95 (6° jitter: 109.64); 90/125 spm within ±2; strikes within 2 frames of truth |
| 6 | Segmentation excludes turns, out-of-frame, ramps | **PASS** (synthetic) | `test_measurement.py` segmentation tests. Out-of-frame is excluded per landmark (deviation 3) |
| 7 | Quality gate with specific reasons; variants table; **walk01's usable segments accepted** | **PASS / FAIL** | All bad variants and synthetic cases are rejected with the right code (table below). **walk01 is rejected (`too_little_walking`): FAIL.** See `phase2_walk01_diagnosis.txt` and deviation 2 |
| 8 | Optional floor calibration | **PASS** (API) | `calib_x1/y1/x2/y2` + `calib_distance_m`; step length and speed within 2% of synthetic truth; absent without calibration; bad input gets 422 `bad_calibration`. No frontend picker (Phase 4) |
| 9 | Remove the REMOVE list incl. risk score, classifier, modes, exercises, Groq, `legacy_display.py` | **PASS** | `82df61b`. `app/services/display.py` (the legacy wording filter; there is no `legacy_display.py`) deleted; `groq` removed from the lock; OpenAPI and responses free of removed keys (`test_api_v3`, audit spec) |
| 10 | Migration archives values (tested); `pipeline_version`; legacy labelled, never in trends | **PASS** | `0003`; `test_upgrade_keeps_every_value…` and `test_0003_downgrade_restores…` (SQLite + Postgres 16); `legacy: true` in responses; trend uses current-version sessions only |
| 11 | Units on every metric; quality indicator on every result | **PASS** | `test_result_has_units_quality_and_versions`; no error ranges (Phase 3) |
| 12 | Audit tests pass unchanged, then ported | **PASS after an approved amendment** | 18/18. `a7efac2` (amendment), `437a0f1` (byte-identical port + identity test). Deviation 1 |
| 13 | Re-run every probe; simulated 60% knee loss visible | **PASS** (synthetic) / **N/A on walk01** | walk01 is rejected, so the user would see the rejection reason. On the synthetic walker, right peak knee flexion goes 56.3° → 22.5° (left 56.7° unchanged) |
| 14 | Frontend: no removed metrics, rejection reasons clear | **PASS** | `03286dd`; frontend tests 20/20 |
| V3 | mypy strict, ruff, suites, pip-audit without ignores | **PASS** | below. CI on a PR not run (human action 2) |

## Tests

| Suite | Start of phase | End of phase |
|---|---|---|
| Backend `tests/` (SQLite) | 116 passed, 1 skipped | **158 passed, 1 skipped** |
| Backend `tests/` (Postgres 16, Docker) | — (CI only) | **161 passed** (run before the final F14 test was added) |
| Audit spec `_audit/tests` | 7 failed / 11 passed | **18 passed** (amended spec) |
| Frontend vitest | 18 passed | **20 passed** |
| ruff / format / mypy | clean | clean (mypy strict on `gaitcore`) |
| pip-audit | 2 ignored (protobuf) | **no known vulnerabilities, no ignores** |
| npm audit `--omit=dev` | 0 | 0 |

Files: `phase2_tests_after.txt`, `phase2_fe_tests_after.txt`, `phase2_audit_spec_vs_old_code.txt`.

## Probes, before → after

"Before" means the audit's outputs (`_audit/probes/out_*.txt`). "After" means `out_*_phase2.txt`.
All probes were ported to the new API, with a version note in each file.

| Probe | Before (audit) | After (Phase 2) |
|---|---|---|
| signal_analysis | Angles in normalised coordinates: 7.4/8.3° mean error; knee jumps p95 24.1°, max 77.5°; "cadence" = left-knee crossings, 10 of 30 jitter; 17 frames silently dropped | Pixel space (normalised error on these landmarks: 7.4/8.7°); knee jumps p95 17.6° raw → **9.3°** masked and filtered; 15 no-pose frames kept as gaps; 9 passes, 7 single strikes, **0 steps → rejected** |
| stability | Deterministic; σ = 0.004 → 5/25 flip to Brisk Walking, cadence 100–136; 15 fps 107 → 82; **60% right-knee loss → score 20, knee SI 7.7% "good"** | Deterministic (diff 0.0). walk01: every noise run and 15 fps are rejected (`too_little_walking` / `low_frame_rate`). Synthetic: σ = 0.004 → all accepted, cadence 108.0–111.9; **60% loss → right peak knee flexion 56.3° → 22.5°**, cadence 110.8 |
| view_dependency | 60° reads 45.1° at 45° yaw; no view check | Same geometry; the gate accepts the synthetic walker ≤ 25° yaw (ratio 0.31) and rejects ≥ 30° (0.37) |
| make_variants (+ v2 pipeline) | Every variant scored 0, "No issues"; two people → 179.8° flexion | Every variant rejected with its reason (table below) |
| api_security_probe | Phase 1: 14/16 PASS | **15/16 PASS** (F40 now passes: name on the PDF; F12 enumeration still FAIL, accepted until Phase 5) |
| concurrency_probe | /status max **28.72 s** during an analysis | /status max **0.02 s** during an 18.6 s analysis |

`profile_pipeline.py` was not re-run. It isn't in the Step 2 probe list, and its timing columns are
covered by the gate table.

## Quality-gate table

Real clips are walk01 (local only, never committed) and its `make_variants.py` variants, run through
the full v2 pipeline in the Linux image (`out_quality_gate_phase2.txt`). Synthetic cases come from
`tests/synthetic.py`; their results are synthetic ground truth.

| Input | Expected | Result | Key quality values | Pass? |
|---|---|---|---|---|
| walk01 (portrait 480×848, ~1 s passes) | **accept** its usable segments | rejected `too_little_walking` | feet 0.59, view 0.16, 9 passes, 0 steps | **FAIL** (deviation 2) |
| mirror | accept (same walk) | rejected `too_little_walking` | 0 steps | FAIL (same cause) |
| dark (18% brightness + noise) | reject or warn | rejected `feet_not_visible` | feet 0.486 (threshold 0.5) | PASS, but close to the threshold |
| occluded_feet | reject: feet | rejected `feet_not_visible` | feet 0.00 | PASS |
| two_people | reject: multiple people | rejected `multiple_people` | — | PASS |
| rotated90 | reject: orientation | rejected `wrong_orientation` | — | PASS |
| long_1080p_60s (walk01 looped) | same as walk01 | rejected `too_little_walking` | 3 steps | consistent with walk01 |
| synthetic, side view (90/110/125 spm) | accept | accepted, cadence ±2 | view 0.0 | PASS |
| synthetic, 15° yaw | accept | accepted | view 0.19 | PASS |
| synthetic, 40° yaw / frontal | reject: view | `not_side_view` | 0.48 / 0.74 | PASS |
| synthetic, 2 people | reject | `multiple_people` | | PASS |
| synthetic, rotated 90° | reject | `wrong_orientation` | | PASS |
| synthetic, feet visibility 0.2 | reject | `feet_not_visible` | | PASS |
| synthetic, 1 short pass (3.4 s) | reject | `too_little_walking` | 2 steps | PASS |
| synthetic, 15 fps | reject | `low_frame_rate` | | PASS |
| synthetic, 2.5 s | reject | `too_short` | | PASS |

Every threshold and its basis is documented in `gaitcore/quality.py`, `gaitcore/segments.py`,
`gaitcore/gait.py` and `gaitcore/signals.py`. The design thresholds that are not literature-based are
labelled as such: multi-person 10%, feet 50%, steady band ±20%. The 0.8 frontal shoulder ratio
behind the view threshold is an **assumption**, to be checked in Phase 3.

## Diffstat

- **Backend:** 81 files, +4,289 / −7,350 (`rebuild/phase-1-foundations..rebuild/phase-2-measurement`,
  before the F14 commits).
  - Removed: `gaitcore/legacy.py`, `activity.py`, `app/services/exercises.py`, `display.py`,
    `plots.py`, and the 4,858-line legacy golden.
  - New:
    - `gaitcore/`: `clip`, `signals`, `segments`, `gait`, `quality`, `calibration`, `result`,
      `pipeline`, `model`;
    - app and DB: `alembic/versions/0003_v3_measurements.py`, `app/schemas.py`, `app/core/copy.py`;
    - tests: `test_measurement.py`, `test_api_v3.py`, `test_audit_spec.py`.
  - Of the total, `_audit/`: 28 files, +932 / −195.
- **Backend F14 commits** `596f82e`, `56347cf`: 2 files.
- **Frontend:** 4 files, +283 / −808 (`App.jsx` 2,050 → 1,323 lines; new `src/measurements.jsx`).

## Migration and data-archive evidence

`0003_v3_measurements.py` does the following:
1. Creates `session_archive(session_id PK/FK, archived_at, source, data JSON)`.
2. For every session, copies these values into `data.session`: `activity`, `confidence`,
   `risk_score/label/color/meaning`, `cadence`, `knee_si`, `hip_si`, `knee_flex_L/R` and `mode`.
3. Copies the session's `findings` and `exercises` rows into `data.findings` / `data.exercises`.
4. Only then drops those columns and both tables.
5. Adds `pipeline_version` (existing rows: `'legacy'`) and `result` JSON.

Downgrade restores every value and both tables. It refuses while any v2 session exists, because the
old schema has nowhere to keep its result.

Tests, each run on SQLite and Postgres 16:
- `test_upgrade_keeps_every_value_of_a_create_all_database[phase0|early]`: kept columns are
  unchanged, and every archived field equals the original, including the findings and exercises rows;
- `test_0003_downgrade_restores_the_archived_values` (includes a stored mode);
- `test_0003_downgrade_refuses_to_drop_v2_results`.

The Postgres run caught an unquoted mixed-case column (`knee_flex_L`). It was fixed before commit.

The Docker image (final tree) runs 0001 → 0002 → 0003 at startup and serves `/healthz` 200.

## What changed for users

- GaitScan now gives **measurements, not judgements**:
  - steps per minute;
  - step and stride time;
  - how far each knee bends at its peak in each stride;
  - how far each thigh swings.
  
  Each comes with units and the number of strides it's based on.
- **Step length and walking speed** appear only if you mark two points on the floor a known distance
  apart. Without that, they're left out rather than guessed.
- **Videos that can't be measured are turned away, with the reason and what to change**: more than
  one person, feet hidden, video rotated, not filmed from the side, not enough steady walking, under
  24 frames per second, or under 3 seconds.
- **Removed:**
  - the overall score and its colour;
  - the walking/running label and its "confidence";
  - the Clinical/Runner/Athlete/Elderly modes;
  - left/right "symmetry" percentages;
  - findings, exercise suggestions and AI-written text.
- **Older results** are marked "earlier version: measurements not shown", because they weren't
  reliable. Their numbers are kept in storage but not displayed or mixed into charts. Record again to
  get current measurements.
- **The PDF** shows the same measurements and a recording-quality summary, with your name.
- **Not yet:** error ranges for these numbers are still to be measured (next phase).

## Human actions required

1. **Decide on the walk01 criterion** (deviation 2). Recording one new local test clip that follows
   the protocol would show an accepted real result:
   - landscape;
   - 3–4 m from a walkway of at least 5 m;
   - whole body including feet in view;
   - phone still;
   - a few passes.
   
   Don't commit it.
2. **Open PRs and get CI green:** Phase 1 first, then Phase 2 (stacked; retarget after Phase 1
   merges). CI was not triggered from here; every CI step was run locally.
3. **Phase 1 deploy dependencies still open** (PHASE_1.md human actions). Render: `JWT_SECRET`,
   `CORS_ORIGINS`, `DATABASE_URL`, Docker service from `render.yaml`, and the
   `TRUSTED_PROXY_HOPS=2` verification. Vercel: `VITE_API_BASE_URL`.
4. **New for Phase 2 deploy:**
   - **Back up the production database before `alembic upgrade head`.** `0003` drops columns after
     archiving them; it's tested, but production data is irreplaceable.
   - Remove `ENABLE_LLM_EXPLANATIONS` and `GROQ_API_KEY` from Render. Revoke the Groq key if one was
     ever set.
   - The Docker build now downloads the model from `storage.googleapis.com` (verified by SHA-256),
     so the Render build needs that network access.
   - **Deploy backend and frontend together:** each expects the other's new response shapes.
5. **Developer machines:**
   - run `uv sync --reinstall-package opencv-python-headless` once (removing the contrib wheel
     deleted the shared `cv2` files);
   - run `python gaitcore/model.py fetch`;
   - on macOS arm64, MediaPipe 1.0.1 cannot extract poses, even with the CPU delegate; use the Docker
     image.
6. **git ≥ 2.35** is still needed for the pre-commit hooks (Phase 1 action 10). With git 2.15:
   - `git stash push -- <path>` deleted untracked files during this phase (recreated, nothing lost);
   - `git worktree remove` doesn't exist.

## Deviations

### 1. Audit spec amended (approved by Kanveer on 2026-10-03; commit `a7efac2`)

Four tests encoded V1 expectations that V3 removes, and one broke with the required MediaPipe 1.0.1
upgrade (`mediapipe.solutions` no longer exists). The owner approved an amendment with conditions:
- the original inputs, numbers and tolerances are kept;
- unamended tests stay byte-identical, which was checked with `ast`;
- the substantive tests must fail on the pre-Phase-2 code: 9 failed / 9 passed through an adapter,
  with numeric failures (`phase2_audit_spec_vs_old_code.txt`).

| Test | Original assertion | Amended assertion | Why the intent is preserved |
|---|---|---|---|
| test_left_knee_uses_mediapipe_left_indices | mp.solutions.pose.PoseLandmark LEFT_HIP/KNEE/ANKLE == (23,25,27), LEFT_SHOULDER == 11; straight leg knee_angle_L == 180 ±0.1 | Same values from mediapipe.tasks.python.vision.PoseLandmark; rest unchanged | Same indices from MediaPipe's own enum in the version we ship; mp.solutions was removed in 1.0 |
| test_aspect_ratio_preserves_angle_on_portrait_video | knee_angle_L(r) == 90 ±1 and == 121.9 ±1 for x/W, y/H inputs on 480x848 | knee_angle_L(r, frame_size=(480, 848)), same inputs, same expected values and tolerance | The row has no frame size, so it is passed in; normalised MediaPipe coordinates in, pixel-space angle out |
| test_cadence_reports_steps_per_minute | calculate_risk_scores(synthetic_walk(110)).cadence == 110 rel 0.1 | measure_walk(Clip(synthetic_walk_landmarks(110))).cadence == 110 rel 0.1 | Same walker (110 spm, 20 s, 30 fps, same knee-angle trace, verified to 1e-12 deg) delivered as landmarks because V3 counts heel strikes; same bound |
| test_cadence_robust_to_jitter[3, 6] | noisy == clean ±10%, N(0, sigma) added to the knee angle | Same, with the noise applied as a shank rotation so the knee angle gets the identical draw (seed 0, left then right) | Same sigma, seed and bound |
| test_healthy_walker_classified_walking → test_healthy_walker_measured_without_activity_label | classify_activity(...).activity == "Walking" | (a) gaitcore.activity gone; no removed key in analyse() output or in the OpenAPI schema. (b) cadence 110 rel 0.1 and per-leg median peak knee flexion 62 ±3 deg | Intent: a healthy 110 spm / 60 deg walk is handled correctly. V3 measures it instead of labelling it |
| test_symmetry_index_detects_halved_knee_rom → test_halved_knee_rom_shows_in_per_leg_peak_flexion | knee symmetry finding status != "good" when the right knee ROM is halved | (a) no symmetry/findings/risk keys anywhere. (b) left 62 ±3 deg, right 32 ±3 deg, left − right ≥ 25 deg (expected 30) | Intent: a 50% knee ROM loss must be detectable; it now shows in the right leg's own peak flexion |

### 2. walk01 is rejected (acceptance criterion 7, partly 13)

The person crosses the 480 px portrait frame in about 1 s with the feet at the bottom edge. In every
pass, the second heel strike falls where that heel is masked: out of frame, or visibility below 0.5.

So no pass holds a complete step (two consecutive strikes of alternate feet), even with a diagnostic
0.5 s widening. The detections are 7 single strikes in 9 passes (`phase2_walk01_diagnosis.txt`).

The rule is kept. The ways to accept walk01 would be:
- counting unconfirmed peaks at gap edges;
- interpolating masked heels;
- deriving cadence from single strikes across turns.

Each of those breaks a Phase 2 requirement or the overfitting rule. Consequence: no accepted
real-video result exists yet. Accuracy on real footage is Phase 3's job (OpenCap lab data).

### 3. Design corrections found on real data (`3d99bc8`)

These came from walk01's geometry. They are not tuned to its numbers; each has a physical basis:
- **Speed averaging:** pelvis speed averaged over one step period (0.5 s) instead of 1 s.
- **Minimum segment:** one step at 130 spm.
- **Out-of-frame exclusion:** applied per landmark rather than per frame.
- **Short runs:** Gustafsson filtfilt, so short valid runs aren't discarded.
- **Feet visibility:** counted only while the hips are in view.

I also changed one test I'd written earlier in this phase (out-of-frame), as explained in that
commit. None of these changes made walk01 pass.

### 4. Cadence uses the balanced mean (`d201767`)

The stability probe showed a constant per-leg timing offset biasing cadence: 117.4 for a truth of
110. Cadence and step time now average the L→R and R→L step means. The golden was regenerated for
this intentional change.

### 5. `/analyze` runs in the thread pool, one at a time (`82df61b`, `56347cf`)

Making the handler a plain `def` ended the event-loop stall (28.7 s → 0.02 s). A process lock then
keeps two pose runs from overlapping (F14). Both are small slices of Phase 4 tasks 1–2; the
background task and status endpoint are still Phase 4.

### 6. Other changes

- **Dependencies:** no new runtime dependency.
  - Removed: `groq`, the direct `matplotlib` (MediaPipe still requires it), `protobuf`.
  - Excluded by uv override: `opencv-contrib-python` and `sounddevice`, which MediaPipe declares but
    the pose API doesn't use.
  - Docker installs `libegl1`/`libgles2`, which the 1.0.1 native library links.
- **Model file:** not committed (9.4 MB). It's fetched and hash-checked by `gaitcore/model.py`.
- **External calls:** the only ones were package registries, the Google model URL and Docker Hub.
  No live app URL was called and nothing was deployed.
- **Security baseline:** `.secrets.baseline` gained one entry, the public model hash inside the
  golden JSON. Elsewhere it uses an inline allowlist pragma.
- **Frontend `dist/`:** the untracked build folder was regenerated by `vite build` during the checks.

## Review guide (riskiest spots)

1. **Heel strikes, steps and strides:** `gaitcore/gait.py:66` (`heel_strikes`), `:151` (step
   pairing), `:166` (stride rule), `:92` (balanced mean).
   - Check that a missed event can never create a double-length step or stride.
   - Check that prominence 0.1 L and the 0.5 s minimum are safe for slow or impaired walkers. Not
     tested on real impaired gait.
   - Zeni's method leads true heel strike by about 1 frame on the synthetic walker.
2. **Segmentation:** `gaitcore/segments.py:67` (`steady_segments`), `:58` (speed smoothing),
   `:52` (pelvis in view).
   - The ±20% steady band and the 0.25 leg-lengths/s floor decide what counts as steady walking.
   - A panning camera or a treadmill yields no passes, by design.
3. **Quality gate:**
   - order of checks: `gaitcore/pipeline.py:21`;
   - thresholds: `gaitcore/quality.py:27-34`;
   - API mapping to 422: `app/api/analysis.py:101`.
   
   Points to check:
   - the feet threshold sits close to the dark variant's value (0.486 vs 0.5);
   - the view ratio relies on an assumed 0.8 frontal shoulder ratio;
   - `multiple_people` relies on MediaPipe finding the second person with `num_poses=2`.
4. **Migration 0003:** `alembic/versions/0003_v3_measurements.py:51` (upgrade), `:60` (quoted
   columns), `:95` (downgrade guard).
   - It drops columns in production. Read it next to `tests/test_migrations.py`, and back up first.
5. **Masking and filtering:** `gaitcore/signals.py:60` (`masked_xy`), `:76` (`lowpass`).
   - Every downstream "never used" guarantee rests here.
   - The run-length minimum and Gustafsson padding affect values near gaps.
