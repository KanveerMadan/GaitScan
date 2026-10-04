"""Golden test: pins the v2 pipeline's complete output on synthetic inputs.

tests/golden/v2_pipeline.json replaces legacy_pipeline.json (the legacy pipeline was removed in
Plan V3 Phase 2). Regenerate ONLY for an intentional output change, and say so in the commit:
    ENV=dev python tests/test_golden.py --regenerate
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "golden", "v2_pipeline.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from synthetic import synthetic_clip  # noqa: E402

CASES = {
    "spm90": {"steps_per_min": 90, "passes": 4},
    "spm110": {"steps_per_min": 110},
    "spm125": {"steps_per_min": 125, "passes": 4},
    "noise2px": {"noise_px": 2.0, "seed": 3},
    "yaw15": {"yaw_deg": 15},
    "two_people": {"people": 2},
    "rotated90": {"rotate90": True},
    "feet_hidden": {"feet_visibility": 0.2},
    "frontal": {"yaw_deg": 90},
    "few_steps": {"passes": 1, "pass_secs": 3.4},
    "low_fps": {"fps": 15},
    "short": {"passes": 1, "pass_secs": 2.5},
}


def compute():
    from gaitcore.calibration import Calibration
    from gaitcore.pipeline import analyse

    out = {name: analyse(synthetic_clip(**kw)[0]).to_dict() for name, kw in CASES.items()}
    clip, truth = synthetic_clip()
    px = 4.0 / 0.9 * 200
    out["calibrated"] = analyse(clip, Calibration(100, truth.floor_y, 100 + px, truth.floor_y, 4.0)).to_dict()
    return json.loads(json.dumps(out))


def test_analysis_output_matches_golden():
    with open(GOLDEN) as f:
        expected = json.load(f)
    assert compute() == expected


if __name__ == "__main__" and "--regenerate" in sys.argv:
    os.environ.setdefault("ENV", "dev")
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, "w") as f:
        json.dump(compute(), f, indent=1, sort_keys=True)
    print("wrote", GOLDEN)
