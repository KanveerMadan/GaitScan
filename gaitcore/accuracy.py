"""What is known about each metric's accuracy, shown next to its value (Plan V3 Phase 3).

A metric is either validated, with the 95% error found by `make evaluate` on LJMU (Topham et al. 2023,
CC BY 4.0), or marked not yet validated, with the reason. Every metric the result can contain must
be listed here (tests/test_measurement.py).
"""

from typing import Any

NOT_YET_VALIDATED = "not_yet_validated"
VALIDATED_STATUS = "validated"

# From evaluation/results/ljmu_summary.json (`make evaluate`, 2026-10-27): the larger 95th-percentile
# absolute error of all 97 accepted clips (57 participants) and of the 21 test clips alone, rounded up
# to the displayed precision (tests/test_accuracy.py checks they match). Reference: heel strikes
# AI-annotated + cross-checked, or from an independent pose model (RTMPose), settled visually where
# they disagreed with the pipeline by > 5 steps/min. Cadence: all p95 4.48, test p95 2.75 steps/min;
# step time: all p95 23.5 ms, test p95 18.9 ms.
# mdc_95, the minimal detectable change: 1.96 x the SD of the difference between two walks of the same
# person in the same session (25 pairs, 16 participants): cadence 4.60 steps/min, step time 24.7 ms.
# Same-session only; day-to-day variation is likely larger and isn't in it.
VALIDATED: dict[str, dict[str, Any]] = {
    "cadence": {"error_95": 4.5, "mdc_95": 4.6, "unit": "steps/min", "clips": 97, "test_clips": 21},
    "step_time": {"error_95": 0.024, "mdc_95": 0.025, "unit": "s", "clips": 97, "test_clips": 21},
}

_KNEE = (
    "Not yet validated: there is no knee-angle reference to check it against yet. Use it to compare "
    "your own recordings, not as an exact angle."
)
_CALIBRATED = (
    "Not yet validated on real recordings: checked only on simulated walking, and its accuracy "
    "depends on where the two floor points were marked."
)

UNVALIDATED: dict[str, str] = {
    "peak_knee_flexion": _KNEE,
    "step_length": _CALIBRATED,
    "walking_speed": _CALIBRATED,
}

# Treadmill mode (Plan V3 Phase 9): the accuracy check above used walks over the ground, so nothing
# measured on a treadmill is validated yet, cadence and step time included.
_TREADMILL = (
    "Not yet validated on treadmill walking: the accuracy check used walks over the ground. Use it to "
    "compare your own treadmill recordings."
)
TREADMILL_UNVALIDATED: dict[str, str] = {
    "cadence": _TREADMILL,
    "step_time": _TREADMILL,
    "peak_knee_flexion": _KNEE,
    "step_length": (
        "Not yet validated: worked out from the belt speed you entered and the measured step time, so it "
        "is only as right as the treadmill's speed display."
    ),
    "belt_speed": "The speed you entered: it isn't measured from the video.",
}


def _validated(name: str) -> dict[str, Any]:
    v = VALIDATED[name]
    return {
        "status": VALIDATED_STATUS,
        "error_95": v["error_95"],
        "mdc_95": v["mdc_95"],
        "unit": v["unit"],
        "note": (
            f"In an accuracy check on {v['clips']} side-view walks from a public dataset (LJMU), 95% of "
            f"values were within ±{v['error_95']} {v['unit']} of the reference."
        ),
    }


def accuracy_for(metrics: dict[str, Any], test: str = "walk") -> dict[str, dict[str, Any]]:
    """One entry per metric in `metrics`, for the test they come from (result.WALK / TREADMILL)."""
    if test != "walk":
        return {name: {"status": NOT_YET_VALIDATED, "note": TREADMILL_UNVALIDATED[name]} for name in metrics}
    return {
        name: _validated(name)
        if name in VALIDATED
        else {"status": NOT_YET_VALIDATED, "note": UNVALIDATED[name]}
        for name in metrics
    }
