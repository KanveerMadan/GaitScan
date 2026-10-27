"""The error ranges shown next to each metric come from `make evaluate` (evaluation/results)."""

import json
import math
import os

import pytest
from synthetic import synthetic_clip
from test_measurement import floor_calibration

from gaitcore.accuracy import VALIDATED
from gaitcore.pipeline import analyse

SUMMARY = os.path.join(os.path.dirname(__file__), "..", "evaluation", "results", "ljmu_summary.json")


def test_every_metric_has_an_accuracy_entry():
    clip, truth = synthetic_clip()
    d = analyse(clip, floor_calibration(truth)).to_dict()
    assert set(d["accuracy"]) == set(d["metrics"])
    for name in ("cadence", "step_time"):
        a = d["accuracy"][name]
        assert a["status"] == "validated" and a["error_95"] > 0 and a["unit"] == d["metrics"][name]["unit"]
        assert "LJMU" in a["note"]


@pytest.mark.parametrize(
    "metric,key,scale,digits",
    [("cadence", "cadence_steps_per_min", 1.0, 1), ("step_time", "step_time_ms", 0.001, 3)],
)
def test_error_ranges_are_the_evaluation_results(metric, key, scale, digits):
    """The larger 95th-percentile absolute error of all clips and of the test clips alone (the tuning
    clips are optimistic: thresholds were chosen on them), rounded up to the displayed precision."""
    with open(SUMMARY) as f:
        s = json.load(f)
    p95 = max(s["all"][key]["p95_abs"], s["test"][key]["p95_abs"]) * scale
    assert VALIDATED[metric]["error_95"] == pytest.approx(math.ceil(p95 * 10**digits - 1e-9) / 10**digits)
    assert VALIDATED[metric]["test_clips"] == s["test"][key]["n"]
