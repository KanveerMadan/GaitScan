"""gaitcore.dsp replaces scipy.signal in the analysis (importing scipy.signal costs ~60 MB of resident
memory, against Render's 512 MB). Each function must give scipy's output: identical peak indices,
and filtered values / peak positions equal to floating-point rounding. scipy stays a test-only
oracle here."""

import os
import subprocess
import sys

import numpy as np
import pytest
from scipy import signal
from synthetic import synthetic_clip

from gaitcore import dsp
from gaitcore.signals import CUTOFF_HZ, ORDER, masked_xy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 1e-9  # well below anything the pipeline rounds to (0.01 px, 1 ms, 0.1 step/min)


@pytest.mark.parametrize("fps", [15.0, 24.0, 25.0, 29.97, 30.0, 50.0, 60.0, 120.0])
def test_butterworth_coefficients_match_scipy(fps):
    b, a = dsp.butter2_lowpass(CUTOFF_HZ / (fps / 2))
    sb, sa = signal.butter(ORDER, CUTOFF_HZ / (fps / 2))
    np.testing.assert_allclose(b, sb, rtol=1e-13, atol=0)
    np.testing.assert_allclose(a, sa, rtol=1e-13, atol=0)


def _signals():
    rng = np.random.default_rng(0)
    t = np.arange(400) / 30
    yield np.c_[np.sin(2 * np.pi * 0.9 * t) * 80 + 600, np.cos(2 * np.pi * 1.8 * t) * 20 + 300]
    yield rng.normal(0, 5, (250, 2)).cumsum(axis=0) + 500
    yield rng.normal(0, 1, (5, 2))  # the shortest run the pipeline filters at 30 fps
    yield np.full((40, 2), 123.0)
    for i in (23, 29, 30):  # real pipeline input: masked landmark tracks of the synthetic walker
        xy = masked_xy(synthetic_clip(noise_px=2.0)[0], i)
        yield xy[np.isfinite(xy).all(axis=1)][:300]


@pytest.mark.parametrize("fps", [24.0, 30.0, 60.0])
def test_zero_phase_filter_matches_scipy_filtfilt_gust(fps):
    b, a = signal.butter(ORDER, CUTOFF_HZ / (fps / 2))
    for x in _signals():
        expected = signal.filtfilt(b, a, x, axis=0, method="gust")
        np.testing.assert_allclose(dsp.filtfilt_gust(b, a, x), expected, rtol=0, atol=TOL * np.abs(x).max())


def _peaky():
    rng = np.random.default_rng(1)
    t = np.arange(600) / 30
    sep = np.abs(np.sin(np.pi * 1.8 * t)) * 0.8 + rng.normal(0, 0.03, len(t))  # heel separation-like
    yield sep
    yield rng.normal(0, 1, 500)
    yield np.array([0, 1, 1, 1, 0, 2, 2, 0, 3, 3, 3, 3, 1, 0], dtype=float)  # plateaus
    yield np.array([0, 2, 0, 2, 0, 2, 0, 2, 0], dtype=float)  # equal heights
    yield np.array([1, 0, 1], dtype=float)
    yield np.array([0, 1], dtype=float)
    yield np.array([5.0])
    yield np.zeros(0)
    yield np.round(rng.normal(0, 1, 300), 1)  # many ties


@pytest.mark.parametrize("distance", [1, 3, 8, 15])
@pytest.mark.parametrize("prominence", [0.0, 0.1, 0.5])
def test_peaks_match_scipy_find_peaks(distance, prominence):
    for x in _peaky():
        expected, _ = signal.find_peaks(x, distance=distance, prominence=prominence)
        np.testing.assert_array_equal(dsp.find_peaks(x, distance=distance, prominence=prominence), expected)


def test_peak_widths_match_scipy():
    for x in _peaky():
        peaks, _ = signal.find_peaks(x, distance=8, prominence=0.1)
        if not len(peaks):
            continue
        _, _, left, right = signal.peak_widths(x, peaks, rel_height=0.5)
        my_left, my_right = dsp.peak_half_width_edges(x, peaks)
        np.testing.assert_allclose(my_left, left, rtol=0, atol=TOL)
        np.testing.assert_allclose(my_right, right, rtol=0, atol=TOL)


def test_the_analysis_never_imports_scipy():
    """The API process imports the analysis; scipy must not come with it."""
    code = (
        "import sys, app.main, gaitcore.pipeline, gaitcore.gait, gaitcore.quality; "
        "print(sorted(m for m in sys.modules if m == 'scipy' or m.startswith('scipy.')))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ROOT, "ENV": "dev"},
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "[]"
