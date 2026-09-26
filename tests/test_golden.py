"""Golden test: the Phase 1 refactor must not change any analysis output.

tests/golden/legacy_pipeline.json was generated from the pre-refactor code
(commit b7e9408) with `python tests/test_golden.py --regenerate`. Inputs are
synthetic landmarks only. Regenerate ONLY for an intentional output change, and
say so in the commit.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden", "legacy_pipeline.json")
sys.path.insert(0, HERE)

from synthetic import synthetic_landmarks  # noqa: E402

CASES = [(spm, ks) for spm in (60, 110, 170) for ks in (1.0, 0.3)]
MODES = ["Clinical", "Runner", "Athlete", "Elderly"]
ACTIVITIES = ["Walking", "Brisk Walking", "Running", "Asymmetric Walking"]


def _pipeline():
    try:  # post-refactor layout
        from gaitcore.angles import add_all_angles
        from gaitcore.activity import classify_activity
        from gaitcore.legacy import calculate_risk_scores
        from app.services.exercises import _match_exercises
    except ImportError:  # pre-refactor layout (used once, to generate the file)
        from src.core.calculate_angles import add_all_angles
        from src.core.activity_classifier import classify_activity
        from src.core.risk_scoring import calculate_risk_scores
        from src.core.exercise_prescription import _match_exercises
    return add_all_angles, classify_activity, calculate_risk_scores, _match_exercises


def _round(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar
        return _round(obj.item())
    return obj


def compute():
    add_all_angles, classify_activity, calculate_risk_scores, match = _pipeline()
    out = {}
    for spm, ks in CASES:
        df = add_all_angles(synthetic_landmarks(steps_per_min=spm, knee_scale_R=ks))
        key = f"spm={spm},knee_scale_R={ks}"
        out[key] = {
            "angle_means": {c: float(df[c].mean()) for c in ("knee_L", "knee_R", "hip_L", "hip_R", "shoulder_tilt")},
            "activity": classify_activity(df),
            "scoring": {
                f"{mode}/{act}": calculate_risk_scores(df, activity=act, mode=mode)
                for mode in MODES for act in ACTIVITIES
            },
        }
        out[key]["exercise_ids"] = {
            k: [e["id"] for e in match(v["findings"], k.split("/")[1], k.split("/")[0])]
            for k, v in out[key]["scoring"].items()
        }
    return _round(out)


def test_analysis_output_matches_golden():
    with open(GOLDEN) as f:
        expected = json.load(f)
    assert compute() == expected


if __name__ == "__main__" and "--regenerate" in sys.argv:
    sys.path.insert(0, os.path.dirname(HERE))
    os.environ.setdefault("ENV", "dev")
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, "w") as f:
        json.dump(compute(), f, indent=1, sort_keys=True, ensure_ascii=False)
    print("wrote", GOLDEN)
