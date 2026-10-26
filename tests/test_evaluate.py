"""The LJMU accuracy check's arithmetic (evaluation/evaluate.py), on the synthetic walker."""

import math

import pytest
from synthetic import synthetic_clip

from evaluation.evaluate import (
    Reference,
    error_stats,
    evaluate_clip,
    load_reference,
    merge_close,
    reference_step_time,
    summarise,
)


def test_reference_step_time_uses_only_strikes_in_the_window():
    ref = Reference("P1_E1T1_90", 1, "test", "visual", [10, 25, 40, 55, 70, 200])
    assert reference_step_time(ref, 0, 100, 30.0) == pytest.approx(15 / 30)
    assert math.isnan(reference_step_time(ref, 50, 100, 30.0))  # two strikes: one step


def test_rtmpose_footprints_closer_than_half_a_step_are_merged():
    assert merge_close([10, 25, 27, 40, 55]) == [10, 25, 40, 55]
    ref = Reference("P1_E1T1_90", 1, "test", "rtmpose", [10, 25, 27, 40, 55])
    assert reference_step_time(ref, 0, 100, 30.0) == pytest.approx(15 / 30)


def test_error_stats():
    s = error_stats([1.0, -1.0, 2.0, -2.0])
    assert s["n"] == 4 and s["mae"] == 1.5 and s["bias"] == 0.0 and s["max_abs"] == 2.0
    lo, hi = s["limits_of_agreement"]
    assert lo == -hi and hi == pytest.approx(1.96 * s["sd"], abs=0.01)
    assert error_stats([]) == {"n": 0}


def test_a_clip_scored_against_its_true_heel_strikes_has_no_cadence_error():
    clip, truth = synthetic_clip(steps_per_min=110, passes=1, pass_secs=8.0)
    strikes = sorted(round(t * clip.fps) for side in "LR" for t in truth.heel_strikes[side])
    row = evaluate_clip(Reference("P1_E1T1_90", 1, "test", "visual", strikes), clip)
    assert row["status"] == "accepted"
    assert abs(row["cadence_error"]) <= 2 and abs(row["step_time_error_ms"]) <= 15
    s = summarise([row])
    assert s["test"]["accepted"] == 1 and s["tuning"]["clips"] == 0
    assert s["all"]["cadence_steps_per_min"]["n"] == 1


def test_reference_file_is_well_formed():
    refs = load_reference()
    assert len({r.clip for r in refs}) == len(refs) > 0
    for r in refs:
        assert r.role in ("tuning", "test") and r.source in ("visual", "visual_coarse", "rtmpose")
        assert r.clip.endswith("_90") and r.strikes == sorted(r.strikes)


def test_repeatability_pairs_walks_of_one_person_in_one_session():
    from evaluation.evaluate import repeatability

    rows = [
        {"clip": "P1_E1T1_90", "participant": 1, "status": "accepted", "cadence": 110.0, "step_time": 0.545},
        {"clip": "P1_E1T2_90", "participant": 1, "status": "accepted", "cadence": 112.0, "step_time": 0.536},
        {"clip": "P1_E2T1_90", "participant": 1, "status": "accepted", "cadence": 130.0, "step_time": 0.46},
        {"clip": "P2_E1T1_90", "participant": 2, "status": "accepted", "cadence": 100.0, "step_time": 0.6},
        {"clip": "P2_E1T2_90", "participant": 2, "status": "rejected"},
    ]
    r = repeatability(rows)
    assert r["pairs"] == 1 and r["participants"] == 1  # P1 E1T1-E1T2 only: other sessions/rejected excluded
    assert r["cadence_steps_per_min"]["mean_abs_diff"] == pytest.approx(2.0)
