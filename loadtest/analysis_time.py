"""Seconds one analysis holds the pose-model slot, on this machine (Plan V3 Phase 4 capacity).

    uv run python loadtest/analysis_time.py VIDEO [VIDEO ...]

Runs the same path as a queued job (probe, precheck, pose model on every frame, measurements) and
prints the time per video and the implied analyses per minute for one process.
"""

import sys
import time

from app.api.analysis import run_pipeline

times = []
for path in sys.argv[1:]:
    t0 = time.perf_counter()
    r = run_pipeline(path, None)
    dt = time.perf_counter() - t0
    times.append(dt)
    print(f"{path}: {dt:.1f} s ({r.status}, {r.quality.get('duration_s')} s of video)")
if times:
    mean = sum(times) / len(times)
    print(f"mean {mean:.1f} s per analysis -> about {60 / mean:.0f} analyses per minute per process")
