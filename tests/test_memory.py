"""Render's free instance has 512 MB: one analysis of a phone-sized clip must fit with room to spare."""

import importlib.util
import os
import subprocess
import sys
import warnings

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# shortcut: measured ~400 MB on arm64 Docker; 512 MB Render free tier; revisit (numpy filtering or bigger instance) if production OOMs
PEAK_RSS_LIMIT_MB = 420
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
# peak_mb(): this process' peak resident memory, in MB. Linux: VmHWM, which exec resets; ru_maxrss
# would carry over the peak of the process that started it (pytest, hundreds of MB in a full run).
PEAK = """
import resource
def peak_mb():
    try:
        with open("/proc/self/status") as f:
            return next(int(line.split()[1]) for line in f if line.startswith("VmHWM:")) // 1024
    except OSError:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
"""
CHILD = (
    PEAK
    + """
import sys
{preload}
import app.main
idle = peak_mb()
from app.api.analysis import run_pipeline
run_pipeline(sys.argv[1], None)
print(idle, peak_mb())
"""
)


def _child(code: str, *args: str) -> list[int]:
    out = subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ROOT},
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return [int(v) for v in out.stdout.split()]


def _rss_mb(video: str, preload: str = "") -> tuple[int, int]:
    """(idle after importing the app, peak after one analysis), in MB."""
    idle, peak = _child(CHILD.format(preload=preload), video)[-2:]
    return idle, peak


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux exec semantics (CI, Docker)")
def test_a_child_reports_its_own_memory_not_its_parents():
    """On Linux ru_maxrss survives exec: a child started by pytest reported pytest's own size
    (442 MB on CI, the same with or without an analysis)."""
    ballast = b"x" * (300 * 1024 * 1024)  # the parent holds 300 MB, as a full test run does
    (peak,) = _child(PEAK + "print(peak_mb())")
    assert len(ballast) and peak < 100, f"child reported {peak} MB"


@needs_mediapipe
def test_analysis_of_1080p_60fps_10s_peaks_under_420_mb(tmp_path):
    video = str(tmp_path / "synthetic_1080p60.mp4")
    _write_video(video)
    idle, peak = _rss_mb(video)
    # Reported on every run (pytest's warnings summary): CI's x86 runners are the reference for
    # Render (x86, 512 MB). For the scipy decision (perf/numpy-signal), the same analysis with
    # scipy.signal imported first, as the app did before gaitcore.dsp, is measured on the same runner.
    msg = f"RSS idle {idle} MB, peak {peak} MB (limit {PEAK_RSS_LIMIT_MB} MB)"
    if importlib.util.find_spec("scipy") is not None:
        old_idle, old_peak = _rss_mb(video, preload="import scipy.signal")
        msg += f"; with scipy.signal imported: idle {old_idle} MB, peak {old_peak} MB"
    warnings.warn(msg, UserWarning, stacklevel=1)
    assert peak <= PEAK_RSS_LIMIT_MB, f"peak RSS {peak} MB"


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
