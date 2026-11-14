"""Every verdict threshold in one place (Plan V3 Phase 11, owner decisions D1 and D3; docs/verdicts.md).

Bands (D1): a same-method reference (healthy LJMU walkers measured by this app) already carries the
method's errors: typical within mean +- TYPICAL_SD SDs, slightly outside up to CLEAR_SD SDs, clearly
outside beyond. A literature reference was measured another way, so GaitScan's own error (e95) is added
to both bands: a difference the app can't resolve never counts. 2.5 SDs hold ~99% of healthy adults when
values are roughly normal. The release gate on healthy LJMU walkers (<= 5% "outside",
<= 25% "keep an eye on it", leave-one-participant-out) is checked in docs/validation/verdicts.md.

Overall verdict (D3, D4): from the KEY_METRICS only, at medium or high confidence; "outside" when at
least RED_MIN_CLEAR of them are clearly outside, "keep_an_eye" when any is outside, else "typical".
Symmetry isn't used (leg identity can't be checked: docs/validation/leg-identity.md).
"""

import math
from typing import Any

# 2.0 / 3.0 SDs (as proposed in D1) failed the release gate: 34.5% of healthy LJMU walkers got "keep an
# eye on it" (with six key metrics at 2 SDs, ~26% is expected by chance alone). D1 says widen: 2.25 gave
# 27.6% (fail), 2.5 / 3.5 gives 13.8% and 0% "outside" (29 participants judged; 2026-11-14).
TYPICAL_SD = 2.5
CLEAR_SD = 3.5
RED_MIN_CLEAR = 2
KEY_METRICS = ("cadence", "step_time_cv", "knee_peak_swing", "knee_rom", "hip_rom", "hip_peak_ext")
# Shown with their values and references but no level (D3: information).
INFO_METRICS = (
    "knee_ic",
    "hip_peak_flex",
    "ankle_ic",
    "ankle_rom",
    "trunk_lean_deg",
    "arm_swing_deg",
    "stance_pct",
    "swing_pct",
    "double_support_pct",
)
ONE_SIDED = {"step_time_cv": "above"}  # steadier steps are never a concern

# Recording quality for any verdict (brief section 3.6; configurable here only).
MIN_VERDICT_STEPS = 10
MIN_USABLE_FRACTION = 0.4
MIN_STRIDES = 3
# Per-metric confidence: high with >= HIGH_N strides (steps for timing) and leg landmarks seen well;
# low below MIN_STRIDES or with poorly seen legs (not counted in the overall verdict).
HIGH_N = 6
HIGH_VISIBILITY = 0.8
LOW_VISIBILITY = 0.6


def bands(ref: Any) -> tuple[float, float]:
    extra = ref.error_95 if ref.kind == "literature" else 0.0
    return TYPICAL_SD * ref.sd + extra, CLEAR_SD * ref.sd + extra


def level(x: float, ref: Any, one_sided: str | None = None) -> tuple[str, str | None]:
    """(level, direction): "typical" | "slightly_outside" | "clearly_outside", and "above" | "below"."""
    d = x - ref.mean
    direction = "above" if d > 0 else "below" if d < 0 else None
    if one_sided == "above" and d <= 0:
        return "typical", direction
    typical, clear = bands(ref)
    if abs(d) <= typical + 1e-9:
        return "typical", direction
    if abs(d) <= clear + 1e-9:
        return "slightly_outside", direction
    return "clearly_outside", direction


def confidence(n: int | None, visibility: float | None) -> str:
    vis = visibility if visibility is not None and math.isfinite(visibility) else 0.0
    if n is None or n < MIN_STRIDES or vis < LOW_VISIBILITY:
        return "low"
    return "high" if n >= HIGH_N and vis >= HIGH_VISIBILITY else "medium"
