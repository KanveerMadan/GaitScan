"""Render's free instance has 512 MB: one analysis of a phone-sized clip must fit with room to spare."""

import os
import subprocess
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEAK_RSS_LIMIT_MB = 350
# MediaPipe 1.0.1's pose graph doesn't run on macOS; CI (Linux) and the Docker image do.
needs_mediapipe = pytest.mark.skipif(sys.platform == "darwin", reason="MediaPipe 1.0.1 runs on Linux only")


def _write_video(path: str, w: int = 1920, h: int = 1080, fps: int = 60, secs: int = 10) -> None:
    """A figure walking across a moving textured background (the pose model finds it in most frames)."""
    bg = np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for i in range(fps * secs):
        f = np.roll(bg, i * 4, axis=1)
        x = int(200 + (w - 400) * (i % (fps * 3)) / (fps * 3))
        cv2.ellipse(f, (x, 360), (40, 55), 0, 0, 360, (150, 180, 220), -1)
        cv2.rectangle(f, (x - 55, 420), (x + 55, 700), (60, 60, 160), -1)
        sw = int(60 * np.sin(i / fps * 2 * np.pi))
        cv2.line(f, (x, 700), (x + sw, 980), (40, 40, 40), 30)
        cv2.line(f, (x, 700), (x - sw, 980), (40, 40, 40), 30)
        out.write(f)
    out.release()


# A fresh process, so the number is the server's imports plus one analysis, nothing from pytest.
CHILD = """
import resource, sys
import app.main
from app.api.analysis import run_pipeline
run_pipeline(sys.argv[1], None)
print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)
"""


@needs_mediapipe
def test_analysis_of_1080p_60fps_10s_peaks_under_350_mb(tmp_path):
    video = str(tmp_path / "synthetic_1080p60.mp4")
    _write_video(video)
    out = subprocess.run(
        [sys.executable, "-c", CHILD, video],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": ROOT},
    )
    peak_mb = int(out.stdout.split()[-1])  # ru_maxrss is in KiB on Linux
    assert peak_mb <= PEAK_RSS_LIMIT_MB, f"peak RSS {peak_mb} MB"


def test_pose_model_sees_at_most_640px_but_landmarks_stay_full_frame(tmp_path, monkeypatch):
    from gaitcore import landmarks

    video = str(tmp_path / "small.mp4")
    _write_video(video, w=1920, h=1080, fps=30, secs=1)
    seen = []

    class FakeLandmarker:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def detect_for_video(self, image, ts):
            seen.append((image.width, image.height))
            return type("R", (), {"pose_landmarks": []})()

    monkeypatch.setattr(landmarks.PoseLandmarker, "create_from_options", lambda o: FakeLandmarker())
    monkeypatch.setattr(landmarks, "_options", lambda: type("O", (), {})())
    clip = landmarks.extract_clip(video)
    assert set(seen) == {(640, 360)}  # long side 640, aspect ratio kept
    assert (clip.width, clip.height) == (1920, 1080)  # calibration and gates use the original frame
    assert clip.n_frames == 30
