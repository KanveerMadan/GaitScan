# ADR-006: Measurement pipeline v2 — pixel-space angles, gating, smoothing, gait events

**Status:** Accepted, amended by REBUILD_PLAN_V3.md (2026-10-03): MediaPipe Tasks 1.0.1, masking without interpolation, no ankle/stance %, hip redefined, floor calibration · **Date:** 2026-09-27

## Context
The audit found:
- angles in normalised coords (up to 30° error, F25);
- visibility ignored (F26);
- no smoothing (p95 frame-to-frame jump 24°);
- `min()`-based flexion (F27);
- a one-leg, hysteresis-free cadence counter that halves true cadence (F24);
- SI on mean absolute angles (F28);
- legacy `mp.solutions` API, and every frame processed at full resolution (F32).

## Decision
1. **Pose:** MediaPipe Tasks `PoseLandmarker` in VIDEO mode, a pinned `.task` model file (full) with SHA-256 recorded, frames downscaled to 640 px long side, and container fps/timestamps used.
2. **Coordinates:** convert to pixels (x·W, y·H) before any geometry. World landmarks are recorded but not used for angles until validated.
3. **Gating:** a joint is valid when visibility ≥ 0.6. Interpolate gaps ≤ 5 frames; otherwise NaN. Reject the clip if the valid fraction of lower-limb joints is < 70% in the analysed segment.
4. **Smoothing:** zero-phase Butterworth low-pass at 6 Hz on pixel trajectories (standard for gait kinematics). One-Euro only if real-time preview is ever needed.
5. **Segmentation:** detect steady-state walking segments (subject fully in frame, horizontal velocity sign constant, excluding turns); analyse only those.
6. **Gait events:** heel strike / toe-off per leg from heel/foot-index horizontal position relative to the pelvis (Zeni et al. 2008 coordinate-based method, adapted to 2D side view). Cadence = heel strikes (both legs)/min. Stride time, stance % and step-time asymmetry come from the events.
7. **Kinematics per stride:** knee flexion = 180 − angle (signed via cross product to flag hyperextension). Peak swing flexion per stride; report median ± SD.
8. **Versioning:** `gaitcore.__version__` (semver) + model hash + config hash stored with each result. Golden-file tests pin outputs for fixture clips.

## Consequences
- Metrics become defensible and testable; audit tests F24/F25/F27/F28 turn green.
- Side view is required: it becomes an explicit protocol, not a hidden assumption.
- Output changes for existing sessions (new pipeline_version).
