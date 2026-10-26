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
from gaitcore.gait import Walk
from gaitcore.quality import Rejection

WALK = "walk"  # the test type: the only one so far (pipeline.TESTS)
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
LEGS_NOT_TOLD_APART = (
    "Left and right legs couldn't be told apart reliably in this video, so peak knee flexion isn't "
    "shown for each leg. Cadence and step time don't depend on telling the legs apart."
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


def _per_leg(values: dict[str, list[float]], unit: str, digits: int, centre: str) -> dict[str, Any]:
    return {
        LEG[s]: _summary(values[s], unit, digits, centre) if len(values[s]) >= MIN_STRIDES_PER_LEG else None
        for s in ("L", "R")
    }


def legs_told_apart(walk: Walk) -> bool:
    t = np.asarray(walk.step_times, dtype=float)
    return len(t) < 2 or float(np.std(t, ddof=1) / np.mean(t)) <= MAX_LABELLED_STEP_CV


def notes_from_walk(walk: Walk) -> list[str]:
    return [] if legs_told_apart(walk) else [LEGS_NOT_TOLD_APART]


def metrics_from_walk(walk: Walk) -> dict[str, Any]:
    # walk.hip_excursion is computed but not returned: CONDITIONAL until it passes Phase 3.
    # walk.stride_times likewise: brief left/right label flips (5-10% of frames) make it read up to
    # 26% short on the synthetic walker without tripping legs_told_apart. Phase 3.
    steps = walk.contact_step_times
    per_leg = legs_told_apart(walk)
    no_legs = {"left": None, "right": None}
    m: dict[str, Any] = {
        "cadence": {"value": round(walk.cadence, 1), "n": walk.step_count, "unit": "steps/min"},
        "step_time": {**_summary(steps, "s", 3, "mean"), "value": round(walk.mean_step_time, 3)},
        "peak_knee_flexion": _per_leg(walk.knee_peak_flexion, "deg", 1, "median") if per_leg else no_legs,
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
            "quality": _clean(self.quality),
            "notes": list(self.notes),
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
