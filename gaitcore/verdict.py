"""The verdict for a gait profile (Plan V3 Phase 11, BE-B): per-metric levels against references, and an
overall summary, as codes (the app words them: app/core/verdict_copy.py, owner decision D4). Worked out
when a result is read, from the person's current sex and age, so a stored result never goes stale."""

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from gaitcore.norms import ANGLE_ERRORS, cadence_reference, ljmu_references, same_method_reference
from gaitcore.norms.thresholds import (
    INFO_METRICS,
    KEY_METRICS,
    MIN_USABLE_FRACTION,
    MIN_VERDICT_STEPS,
    ONE_SIDED,
    RED_MIN_CLEAR,
    bands,
    confidence,
    level,
)

TIMING = ("cadence", "step_time_cv", "stance_pct", "swing_pct", "double_support_pct")
JOINTS = ("knee", "hip", "ankle")
RefFn = Callable[[str, str | None, float | None], Any]


def default_reference(metric: str, sex: str | None, age: float | None) -> Any:
    return cadence_reference(sex, age) if metric == "cadence" else same_method_reference(metric, sex, age)


def _value(profile: dict[str, Any], metric: str) -> dict[str, Any] | None:
    part = profile.get("timing" if metric in TIMING else "kinematics") or {}
    v = part.get(metric)
    return v if isinstance(v, dict) and v.get("value") is not None else None


def _ref_dict(ref: Any) -> dict[str, Any]:
    keys = ("mean", "sd", "n", "group", "source", "kind", "error_95", "fallback")
    return {k: getattr(ref, k, None) for k in keys}


def gps(curves: dict[str, Any] | None, ref_curves: dict[str, Any] | None) -> dict[str, Any] | None:
    """Gait Profile Score (Baker R et al. Gait Posture 2009;30(3):265-269) over the sagittal knee, hip and
    ankle (both legs pooled): each Gait Variable Score is the RMS difference over the cycle from the
    reference mean curve; the GPS is the RMS of the GVSs. Information only (D3)."""
    if not curves or not ref_curves:
        return None
    gvs = {}
    for j in JOINTS:
        c, r = (curves.get(j) or {}).get("mean"), (ref_curves.get(j) or {}).get("mean")
        if c is None or r is None:
            return None
        gvs[j] = round(float(np.sqrt(np.mean((np.asarray(c) - np.asarray(r)) ** 2))), 2)
    return {"value": round(float(np.sqrt(np.mean([v * v for v in gvs.values()]))), 2), "gvs": gvs}


def assess(
    profile: dict[str, Any], person: tuple[str | None, float | None] | None, refs: RefFn | None = None
) -> dict[str, Any]:
    refs = refs or default_reference
    sex, age = person or (None, None)
    q = profile.get("quality") or {}
    vis = q.get("leg_visibility")
    metrics: dict[str, Any] = {}
    for m in KEY_METRICS + INFO_METRICS:
        v = _value(profile, m)
        if v is None:
            continue
        ref = refs(m, sex, age)
        row: dict[str, Any] = {
            "value": v["value"],
            "level": None,
            "direction": None,
            "typical": None,
            "reference": None,
        }
        row["data_confidence"] = confidence(v.get("n"), vis if m not in TIMING[:2] else 1.0)
        joint = next((j for j in ANGLE_ERRORS if m.startswith(j)), None)
        row["error"] = ANGLE_ERRORS[joint] if joint else None
        if ref is not None:
            typical, _ = bands(ref)
            row["typical"] = [round(ref.mean - typical, 2), round(ref.mean + typical, 2)]
            row["reference"] = _ref_dict(ref)
            if m in KEY_METRICS:
                row["level"], row["direction"] = level(v["value"], ref, ONE_SIDED.get(m))
        metrics[m] = row
    out: dict[str, Any] = {"metrics": metrics, "overall": None, "drivers": [], "no_verdict": None, "tips": []}
    steps = q.get("steps") or 0
    usable = q.get("usable_frame_fraction") or 0.0
    if steps < MIN_VERDICT_STEPS:
        out.update(no_verdict="too_few_steps", tips=["walk_more_passes", "whole_body_in_view"])
    elif usable < MIN_USABLE_FRACTION:
        out.update(
            no_verdict="too_little_steady_walking", tips=["walk_more_passes", "steady_pace", "camera_still"]
        )
    else:
        counted = {m: r for m, r in metrics.items() if r["level"] and r["data_confidence"] != "low"}
        if not counted:
            out.update(
                no_verdict="low_confidence", tips=["whole_body_in_view", "landscape_waist_height", "distance"]
            )
        else:
            clear = [m for m, r in counted.items() if r["level"] == "clearly_outside"]
            outside = [m for m, r in counted.items() if r["level"] != "typical"]
            if len(clear) >= RED_MIN_CLEAR:
                out.update(overall="outside", drivers=clear)
            elif outside:
                out.update(overall="keep_an_eye", drivers=outside)
            else:
                out["overall"] = "typical"
    fallbacks = {r["reference"]["fallback"] for r in metrics.values() if r["reference"]}
    out["fallbacks"] = sorted(f for f in fallbacks if f)
    curves = (profile.get("kinematics") or {}).get("curves")
    try:
        ref_curves = ljmu_references().get("curves")
        band = ljmu_references().get("gps")
    except FileNotFoundError:
        ref_curves, band = None, None
    g = gps(curves, ref_curves)
    if g is not None and band:
        g["typical"] = [0.0, band["p95"]]
    out["gps"] = g
    return out


def age_at(birth_year: int | None, when_year: int | None) -> float | None:
    if birth_year is None or when_year is None:
        return None
    age = when_year - birth_year
    return float(age) if math.isfinite(age) else None
