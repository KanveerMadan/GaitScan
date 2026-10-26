"""What is known about each metric's accuracy, shown next to its value (Plan V3 Phase 3).

A metric is either validated, with the error found by `make evaluate` on LJMU (Topham et al. 2023,
CC BY 4.0), or marked not yet validated, with the reason. Every metric the result can contain must
be listed here (tests/test_measurement.py).
"""

from typing import Any

NOT_YET_VALIDATED = "not_yet_validated"

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


def accuracy_for(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """One entry per metric in `metrics`."""
    return {
        name: {"status": NOT_YET_VALIDATED, "note": UNVALIDATED[name]}
        for name in metrics
        if name in UNVALIDATED
    }
