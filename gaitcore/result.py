"""The analysis result: measurements with units, a quality block, and versions (ADR-001, ADR-005).

Only the V3 KEEP/CONDITIONAL metrics exist here (_audit/REBUILD_PLAN_V3.md section 2). A metric
that can't be measured is absent (null), never estimated. No error ranges yet (Phase 3).
"""

import math
from dataclasses import dataclass, field
from importlib.metadata import version
from typing import Any

import numpy as np

from gaitcore import __version__, model
from gaitcore.accuracy import accuracy_for
from gaitcore.gait import Walk
from gaitcore.quality import Rejection

WALK = "walk"  # the test types (pipeline.TESTS): overground walking, validated on LJMU
TREADMILL = "treadmill"  # walking on a treadmill at an entered belt speed: not yet validated
MIN_STRIDES_PER_LEG = 3  # a median of >= 3 strides can't be set by one bad stride
LEG = {"L": "left", "R": "right"}

# Per-leg values (peak knee flexion) need the left/right labels; cadence and step time
# don't (gait.py). When the steps between labelled heel strikes of alternate feet vary by more than
# MAX_LABELLED_STEP_CV (SD / mean), the labels are taken to be swapping and per-leg values are
# withheld with a note. Data: on 20 LJMU clips with AI-annotated + cross-checked heel strikes
# (Topham et al. 2023, CC BY 4.0), cadence from the labelled strikes was off by at most 3.9 / 5.8 /
# 13.7 steps/min in clips with CV <= 0.10 / 0.15 / 0.20 (7 / 10 / 13 clips), and by up to 57.9 above;
# 0.20 was chosen on 2026-10-24. Known limit: brief flips (1-2 frames, 5-10% of frames) on the
# synthetic walker keep the CV at 0.06-0.11 while per-leg stride times read up to 26% short, so this
# check doesn't catch every label problem.
MAX_LABELLED_STEP_CV = 0.20
# A leg's median stride time must also be within MAX_STRIDE_MISMATCH of twice the label-free mean
# step time. On LJMU the labels often follow the legs' position in the image rather than the leg, and
# one label's "stride" is then a single step. Data (2026-10-26, 77 accepted LJMU clips, 110 legs
# with >= 3 strides, vs twice the reference step time): stride / reference was 0.91-1.05 for 56
# legs and <= 0.88 for the rest (37 at 0.48-0.62: one step), so +-10% keeps every correct leg.
MAX_STRIDE_MISMATCH = 0.10
LEGS_NOT_TOLD_APART = (
    "Left and right legs couldn't be told apart reliably in this video, so there's no outline of the "
    "walk to replay. Cadence and step time don't depend on telling the legs apart."
)


def _summary(values: list[float], unit: str, digits: int, centre: str = "median") -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    value = float(np.median(arr) if centre == "median" else np.mean(arr))
    sd = float(np.std(arr, ddof=1)) if len(arr) >= 2 else None
    return {
        "value": round(value, digits),
        "sd": None if sd is None else round(sd, digits),
        "n": len(arr),
        "unit": unit,
    }


def legs_told_apart(walk: Walk) -> bool:
    t = np.asarray(walk.step_times, dtype=float)
    if len(t) >= 2 and float(np.std(t, ddof=1) / np.mean(t)) > MAX_LABELLED_STEP_CV:
        return False
    stride = 2 * walk.mean_step_time
    return all(
        abs(float(np.median(walk.stride_times[s])) / stride - 1) <= MAX_STRIDE_MISMATCH
        for s in ("L", "R")
        if len(walk.stride_times[s]) >= MIN_STRIDES_PER_LEG and math.isfinite(stride)
    )


def notes_from_walk(walk: Walk) -> list[str]:
    return [] if legs_told_apart(walk) else [LEGS_NOT_TOLD_APART]


def metrics_from_walk(walk: Walk) -> dict[str, Any]:
    # walk.hip_excursion is computed but not returned: CONDITIONAL until it passes Phase 3.
    # walk.stride_times likewise: brief left/right label flips (5-10% of frames) make it read up to
    # 26% short on the synthetic walker without tripping legs_told_apart. Phase 3.
    # Peak knee flexion was removed on 2026-11-12 (owner decision: Phase 8, the only way to validate a
    # knee angle, is cancelled), so no analysis reports a knee angle.
    steps = walk.contact_step_times
    m: dict[str, Any] = {
        "cadence": {"value": round(walk.cadence, 1), "n": walk.step_count, "unit": "steps/min"},
        "step_time": {**_summary(steps, "s", 3, "mean"), "value": round(walk.mean_step_time, 3)},
    }
    if walk.step_lengths_m is not None:
        if walk.step_lengths_m:
            m["step_length"] = _summary(walk.step_lengths_m, "m", 3, "mean")
            speed = walk.speed_m_s
            m["walking_speed"] = {
                "value": None if speed is None else round(speed, 2),
                "n": len(walk.step_lengths_m),
                "unit": "m/s",
            }
        else:
            m["step_length"] = None
            m["walking_speed"] = None
    return m


def metrics_from_treadmill(walk: Walk, belt_speed_m_s: float) -> dict[str, Any]:
    """The walk's timing, plus the belt speed as entered and the step length it gives:
    on a treadmill each step carries the foot back by the belt's travel in one step time."""
    m = metrics_from_walk(walk)
    m["belt_speed"] = {"value": round(belt_speed_m_s, 2), "unit": "m/s", "source": "entered"}
    step = walk.mean_step_time
    m["step_length"] = (
        {"value": round(belt_speed_m_s * step, 3), "n": walk.step_count, "unit": "m"}
        if math.isfinite(step)
        else None
    )
    return m


def pass_results(walks: list[tuple[int, float, Walk]], min_steps: int) -> list[dict[str, Any]]:
    """Cadence and step time of each walk across the frame (pass_index, direction, walk) that holds
    at least `min_steps` steps (quality.MIN_STEPS, the same resolution bound as the whole clip)."""
    return [
        {
            "pass": k + 1,
            "direction": "left_to_right" if direction > 0 else "right_to_left",
            "steps": w.step_count,
            "cadence": {"value": round(w.cadence, 1), "unit": "steps/min"},
            "step_time": {
                **_summary(w.contact_step_times, "s", 3, "mean"),
                "value": round(w.mean_step_time, 3),
            },
        }
        for k, direction, w in walks
        if w.step_count >= min_steps
    ]


def pass_variability(passes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """SD of the per-pass values between passes; None with fewer than two timed passes."""
    if len(passes) < 2:
        return None
    sd = {m: float(np.std([p[m]["value"] for p in passes], ddof=1)) for m in ("cadence", "step_time")}
    return {
        "passes": len(passes),
        "cadence_sd": {"value": round(sd["cadence"], 1), "unit": "steps/min"},
        "step_time_sd": {"value": round(sd["step_time"], 3), "unit": "s"},
    }


def curves_from_walk(walk: Walk) -> dict[str, Any]:
    """The stride outline for the ghost replay. (The knee-flexion curve was removed with peak knee
    flexion on 2026-11-12.)"""
    return {"stride_outline": stride_outline_from_walk(walk, legs_told_apart(walk))}


def stride_outline_from_walk(walk: Walk, shown: bool) -> dict[str, Any] | None:
    """The mean stride outline (gait.stride_outline) for ghost replay: hidden when the legs can't be
    told apart (legs_told_apart); no absolute position, head, arms or hands. Each point is the mean over the strides
    in which it was visible throughout; a point visible in fewer than MIN_STRIDES_PER_LEG is null."""
    if not shown or len(walk.stride_outlines) < MIN_STRIDES_PER_LEG:
        return None
    points: dict[str, list[list[float]] | None] = {}
    for key in walk.stride_outlines[0]:
        tracks = [t for o in walk.stride_outlines if (t := o[key]) is not None]
        points[key] = (
            [[round(float(x), 3), round(float(y), 3)] for x, y in np.mean(np.stack(tracks), axis=0)]
            if len(tracks) >= MIN_STRIDES_PER_LEG
            else None
        )
    return {
        "points": points,
        "strides": len(walk.stride_outlines),
        "trail_strike": round(float(np.mean(walk.trail_strikes)), 3),
        "units": "leg lengths; x from the pelvis in the walking direction, y above the floor",
    }


def model_info() -> dict[str, str]:
    return {
        "name": model.NAME,
        "version": model.VERSION,
        "sha256": model.SHA256,
        "mediapipe": version("mediapipe"),
    }


@dataclass
class AnalysisResult:
    status: str  # "accepted" | "rejected"
    rejection: Rejection | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # user-facing caveats about an accepted result
    test: str = WALK
    passes: list[dict[str, Any]] = field(default_factory=list)  # per walk across the frame
    pass_variability: dict[str, Any] | None = None
    curves: dict[str, Any] = field(default_factory=dict)  # gait-cycle curves (not yet validated)
    pipeline_version: str = __version__

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "model": model_info(),
            "test": self.test,
            "status": self.status,
            "rejection": None
            if self.rejection is None
            else {"code": self.rejection.code, "message": self.rejection.message},
            "metrics": self.metrics,
            "accuracy": accuracy_for(self.metrics, self.test),
            "quality": _clean(self.quality),
            "notes": list(self.notes),
            "passes": self.passes,
            "pass_variability": self.pass_variability,
            "curves": self.curves,
        }


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _clean(v)
        elif isinstance(v, (float, np.floating)):
            out[k] = None if not math.isfinite(float(v)) else float(v)
        elif isinstance(v, np.integer):
            out[k] = int(v)
        else:
            out[k] = v
    return out
