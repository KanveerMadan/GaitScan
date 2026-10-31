"""Export the landing page's walking figure and its measurement trace (frontend src/landing/walker.json),
and the onboarding example result (frontend src/onboarding/example-result.json), from one simulated walk.

The figure is GaitScan's own simulated walker (tests/synthetic.py), the ground truth its tests
measure, so the page shows real geometry, not an illustration:
- `stride`: one steady stride of the 12 landmarks the pipeline uses, sampled at PHASES points from
  a left heel strike to the next. x is relative to the pelvis, y is height above the floor, both in
  leg lengths. `strikes`: the stride phase of each heel strike.
- `trace`: what gaitcore computes for the same walker filmed at 30 fps (EXAMPLE_CLIP: three 6 s passes):
  the heel-separation signal over one steady pass, the step events found in it, and the measured
  cadence and step time, next to the true cadence.

The example result is the full API result for EXAMPLE_CLIP, so the demo page and the landing page quote
the same walk and the same pipeline version.

Run: ENV=dev uv run python tools/export_walker.py ../gaitscan-frontend/src
"""

import json
import math
import sys

import numpy as np

sys.path.insert(0, "tests")
from synthetic import LEG, synthetic_clip  # noqa: E402

from gaitcore.gait import contact_runs, heel_separation, leg_length  # noqa: E402
from gaitcore.pipeline import analyse, walking  # noqa: E402
from gaitcore.signals import SIDES, build_tracks, raw_xy  # noqa: E402

SPM = 110.0
PHASES = 120
EXAMPLE_CLIP = {"steps_per_min": SPM, "pass_secs": 6.0}
NAMES = ("shoulder", "hip", "knee", "ankle", "heel", "toe")


def stride() -> dict[str, object]:
    clip, truth = synthetic_clip(steps_per_min=SPM, passes=1, pass_secs=8.0, fps=240.0, width=4000)
    t = np.arange(clip.n_frames) / clip.fps
    pts = {(s, n): raw_xy(clip, SIDES[s][n]) for s in ("L", "R") for n in NAMES}
    pelvis_x = (pts[("L", "hip")][:, 0] + pts[("R", "hip")][:, 0]) / 2
    period = 120.0 / SPM
    t0 = next(h for h in truth.heel_strikes["L"] if h > 2.5)  # a left heel strike in steady walking
    phase_t = t0 + np.arange(PHASES) / PHASES * period
    out: dict[str, list[list[float]]] = {}
    for (side, name), xy in pts.items():
        x = (np.interp(phase_t, t, xy[:, 0]) - np.interp(phase_t, t, pelvis_x)) / LEG
        y = (truth.floor_y - np.interp(phase_t, t, xy[:, 1])) / LEG
        out[f"{side}_{name}"] = [[round(float(a), 4), round(float(b), 4)] for a, b in zip(x, y, strict=True)]
    strikes = {
        side: sorted(round(((h - t0) / period) % 1.0, 4) for h in hs if t0 <= h < t0 + period)
        for side, hs in truth.heel_strikes.items()
    }
    return {"spm": SPM, "phases": PHASES, "near": "L", "points": out, "strikes": strikes}


def trace() -> dict[str, object]:
    clip, truth = synthetic_clip(**EXAMPLE_CLIP)
    result = analyse(clip)
    tracks = build_tracks(clip)
    leg = leg_length(tracks)
    seg = walking(clip, tracks, leg).segments[0]
    sep = heel_separation(clip, leg)
    events = [e for run in contact_runs(sep, seg, clip.fps) for e in run]
    s = sep[seg.start : seg.end]
    return {
        "fps": clip.fps,
        "start_s": round(seg.start / clip.fps, 3),
        "separation": [None if not math.isfinite(v) else round(float(v), 4) for v in s],
        "events_s": [round(e, 4) for e in events],
        "true_cadence": truth.cadence,
        "cadence": result.metrics["cadence"]["value"],
        "step_time": result.metrics["step_time"]["value"],
        "steps": result.quality["steps_detected"],
    }


if __name__ == "__main__":
    src = sys.argv[1]
    data = {
        "source": "GaitScan's simulated walker (tests/synthetic.py) and gaitcore's output for it; tools/export_walker.py",
        "stride": stride(),
        "trace": trace(),
    }
    with open(f"{src}/landing/walker.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    example = analyse(synthetic_clip(**EXAMPLE_CLIP)[0]).to_dict()
    with open(f"{src}/onboarding/example-result.json", "w") as f:
        json.dump(example, f, indent=2)
        f.write("\n")
    sys.stdout.write(
        f"walker {data['trace']['cadence']} steps/min; example {example['metrics']['cadence']}\n"
    )
