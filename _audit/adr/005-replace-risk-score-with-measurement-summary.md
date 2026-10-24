# ADR-005: Replace the composite "risk score" with a measurement summary + quality gates

**Status:** Accepted, amended by REBUILD_PLAN_V3.md (2026-10-03): metrics per the V3 metric policy; no angle reference ranges · **Date:** 2026-09-27

## Context
The 0–100 "risk score" is four additive heuristics with invented weights and thresholds, a max of 80, and no validation (B5). It returned 0 "No issues" for invalid input (two people, occluded feet, rotated) and 20 "Minor" for a simulated 60% knee ROM loss. The user-facing copy makes diagnostic and injury claims (A3), which is a regulatory and liability risk in India, where software making diagnostic claims may fall under medical-device rules.

## Decision
- Remove `overall_risk_score`, `risk_label`, `risk_color`, the four "modes", and the activity classifier from the product surface.
- Report per side, with units: peak swing knee flexion (median ± SD across strides), knee ROM, cadence (steps/min), stride time, stance %, and step-time asymmetry (%).
- Each metric shows a **cited** typical range (source in `gaitcore/reference_ranges.yaml`) and **our measured uncertainty** from ADR-006/validation.
- A **recording-quality gate** runs before any metric is shown: side-view check, single person, lower-limb visibility ≥ threshold in ≥ X% of frames, ≥ 4 clean strides detected, fps ≥ 25. Failing clips return actionable guidance instead of numbers.
- Copy is screening/measurement framing only: "outside typical range", never "abnormal", "risk" or "injury". A persistent "not a diagnostic device" notice appears in the UI and the PDF.

## Consequences
- It looks less impressive in a demo but can be defended in an interview and to a clinic.
- A composite index can return later only with an outcome, a dataset and published validation.
- Historic sessions keep their old numbers flagged `legacy_unvalidated=true`.
