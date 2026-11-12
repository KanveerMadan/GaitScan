"""Smoke check of the built image (CI `docker` job): the baked-in pose model is the pinned file, MediaPipe
loads it, and one synthetic analysis is accepted. Not collected by pytest. Run:
    docker run --rm -e PYTHONPATH=/app -v "$PWD/tests:/t:ro" gaitscan-api:ci python /t/docker_smoke.py
"""

from mediapipe.tasks.python.vision import PoseLandmarker
from synthetic import synthetic_clip

from gaitcore import landmarks, model
from gaitcore.pipeline import analyse

path = model.model_path()  # ModelError unless the file's SHA-256 is the pinned one
assert model.sha256(path) == model.SHA256
with PoseLandmarker.create_from_options(landmarks._options()):
    pass

r = analyse(synthetic_clip(steps_per_min=110)[0]).to_dict()
assert r["status"] == "accepted", r["rejection"]
assert set(r["metrics"]) == {"cadence", "step_time"}, set(r["metrics"])
assert abs(r["metrics"]["cadence"]["value"] - 110) <= 2, r["metrics"]["cadence"]
assert r["model"]["sha256"] == model.SHA256
print(f"ok: {path} sha256 {model.SHA256[:12]}..., cadence {r['metrics']['cadence']['value']} steps/min")
