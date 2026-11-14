"""The gait profile an accepted walk stores (Plan V3 Phase 11, result schema 3): measurements only. The
verdict is added when the result is read (gaitcore.verdict), so a stored result never goes stale.

Values are both legs pooled (label-free, owner decision B): no left/right, no symmetry (decision A).
Pelvis oscillation is stored under "hidden" and not shown (owner, 2026-11-14: about twice published
values on LJMU; docs/validation/kinematics.md)."""

from typing import Any

from gaitcore.kinematics import Kinematics

SCHEMA = 3
KINEMATICS = (
    "knee_ic",
    "knee_peak_swing",
    "knee_rom",
    "hip_peak_ext",
    "hip_peak_flex",
    "hip_rom",
    "ankle_ic",
    "ankle_rom",
    "trunk_lean_deg",
    "arm_swing_deg",
)
UNITS = {"stance_pct": "%", "swing_pct": "%", "double_support_pct": "%"}


def _stat(s: dict[str, Any] | None, unit: str, digits: int = 1) -> dict[str, Any]:
    if s is None:
        return {"value": None, "sd": None, "n": 0, "unit": unit}
    return {"value": round(s["value"], digits), "sd": round(s["sd"], digits), "n": s["n"], "unit": unit}


def gait_profile(
    metrics: dict[str, Any], quality: dict[str, Any], kin: Kinematics | None
) -> dict[str, Any] | None:
    if kin is None:
        return None
    s = kin.summary()
    steps = quality.get("steps_detected") or 0
    cv = quality.get("step_time_cv")
    timing: dict[str, Any] = {
        "cadence": {**metrics["cadence"], "n": steps},
        "step_time": metrics["step_time"],
        "step_time_cv": {"value": None if cv is None else round(100 * cv, 1), "unit": "%", "n": steps},
    }
    for m in ("stance_pct", "swing_pct", "double_support_pct"):
        timing[m] = _stat(s[m], UNITS[m])
    kinematics: dict[str, Any] = {m: _stat(s[m], "deg") for m in KINEMATICS}
    kinematics["curves"] = {
        j: (
            None
            if c is None
            else {"mean": [round(v, 1) for v in c["mean"]], "sd": [round(v, 1) for v in c["sd"]], "n": c["n"]}
        )
        for j, c in kin.curves().items()
    }
    return {
        "schema": SCHEMA,
        "timing": timing,
        "kinematics": kinematics,
        "poses": kin.poses,
        "quality": {
            "steps": steps,
            "strides": len(kin.strides),
            "usable_frame_fraction": quality.get("usable_frame_fraction"),
            "leg_visibility": None
            if kin.leg_visibility != kin.leg_visibility
            else round(kin.leg_visibility, 3),
        },
        "hidden": {"pelvis_oscillation": _stat(s["pelvis_oscillation"], "leg lengths", 3)},
    }
