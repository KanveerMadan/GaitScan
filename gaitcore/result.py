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

MIN_STRIDES_PER_LEG = 3  # a median of >= 3 strides can't be set by one bad stride
LEG = {"L": "left", "R": "right"}


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


def metrics_from_walk(walk: Walk) -> dict[str, Any]:
    # walk.hip_excursion is computed but not returned: CONDITIONAL until it passes Phase 3.
    m: dict[str, Any] = {
        "cadence": {"value": round(walk.cadence, 1), "n": len(walk.step_times), "unit": "steps/min"},
        "step_time": {**_summary(walk.step_times, "s", 3, "mean"), "value": round(walk.mean_step_time, 3)},
        "stride_time": _per_leg(walk.stride_times, "s", 3, "mean"),
        "peak_knee_flexion": _per_leg(walk.knee_peak_flexion, "deg", 1, "median"),
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
    pipeline_version: str = __version__

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "model": model_info(),
            "status": self.status,
            "rejection": None
            if self.rejection is None
            else {"code": self.rejection.code, "message": self.rejection.message},
            "metrics": self.metrics,
            "quality": _clean(self.quality),
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
