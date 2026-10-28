"""The few scipy.signal routines the analysis uses, in numpy and plain Python.

Importing scipy.signal loads most of scipy (stats, optimize, sparse, spatial, ...): ~60 MB of resident
memory in the API process, against Render's 512 MB. These are ports of scipy 1.17's algorithms, step for
step, so the outputs are the same; tests/test_dsp.py checks them against scipy on synthetic and real
pipeline signals:
- butter2_lowpass: scipy.signal.butter(2, wn) (analog prototype -> prewarp -> bilinear -> polynomial);
- filtfilt_gust: scipy.signal.filtfilt(b, a, x, axis=0, method="gust") (Gustafsson's initial conditions,
  F. Gustafsson, IEEE Trans. Signal Processing 44(4):988-992, 1996), on columns along axis 0;
- find_peaks: scipy.signal.find_peaks(x, distance=..., prominence=...) (plateaus -> middle sample;
  distance keeps the higher peak; prominence over the whole signal, no window);
- peak_half_width_edges: the left/right interpolated positions of scipy.signal.peak_widths(x, peaks,
  rel_height=0.5).
The loops run over a few hundred samples per call, so plain Python is fast enough.
"""

import math

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]


def butter2_lowpass(wn: float) -> tuple[Array, Array]:
    """Coefficients (b, a) of a 2nd-order Butterworth low-pass; wn = cut-off / Nyquist, in (0, 1)."""
    if not 0 < wn < 1:
        raise ValueError("wn must be between 0 and 1")
    fs = 2.0
    poles = -np.exp(1j * np.pi * np.arange(-1, 2, 2) / 4)  # buttap(2)
    warped = 2 * fs * math.tan(math.pi * wn / fs)
    p = warped * poles  # lp2lp_zpk
    k = warped**2
    fs2 = 2.0 * fs  # bilinear_zpk
    p_z = (fs2 + p) / (fs2 - p)
    k_z = k * np.real(1.0 / np.prod(fs2 - p))
    b = k_z * np.real(np.poly([-1.0, -1.0]))
    a = np.real(np.poly(p_z))
    return np.asarray(b, dtype=float), np.asarray(a, dtype=float)


def _lfilter(b: Array, a: Array, x: Array, zi: tuple[float, float] = (0.0, 0.0)) -> Array:
    """scipy.signal.lfilter for a 2nd-order filter with a[0] == 1 (transposed direct form II), along
    axis 0 of a 1-D or 2-D array."""
    b0, b1, b2 = (float(v) for v in b)
    _, a1, a2 = (float(v) for v in a)
    cols = np.asarray(x, dtype=float).reshape(len(x), -1)
    out = np.empty_like(cols)
    for c in range(cols.shape[1]):
        z0, z1 = zi
        ys = []
        for xi in cols[:, c].tolist():
            y = z0 + b0 * xi
            z0 = z1 + xi * b1 - y * a1
            z1 = xi * b2 - y * a2
            ys.append(y)
        out[:, c] = ys
    return out.reshape(np.shape(x))


def filtfilt_gust(b: Array, a: Array, x: Array) -> Array:
    """Zero-phase forward-backward filter of each column of x (axis 0), Gustafsson's initial
    conditions, for the 2nd-order (b, a) of butter2_lowpass."""
    if len(a) != 3 or len(b) != 3 or a[0] != 1.0:
        raise ValueError("2nd-order filter with a[0] == 1 expected")
    x2 = np.asarray(x, dtype=float).reshape(len(x), -1)
    n, order = x2.shape[0], 2
    obs = np.zeros((n, order))
    obs[:, 0] = _lfilter(b, a, np.zeros(n), zi=(1.0, 0.0))
    obs[1:, 1] = obs[:-1, 0]
    obsr = obs[::-1]
    s = _lfilter(b, a, obs[::-1])
    sr = s[::-1]
    m = np.hstack((sr - obs, obsr - s))
    y_f = _lfilter(b, a, x2)
    y_fb = _lfilter(b, a, y_f[::-1])[::-1]
    y_b = _lfilter(b, a, x2[::-1])[::-1]
    y_bf = _lfilter(b, a, y_b)
    ic_opt = np.linalg.lstsq(m, y_bf - y_fb, rcond=None)[0]  # (2 * order, columns)
    w = np.hstack((sr, obsr))
    y = y_fb + ic_opt.T.dot(w.T).T
    return np.asarray(y.reshape(np.shape(x)), dtype=float)


def _local_maxima(x: list[float]) -> list[int]:
    peaks = []
    i, i_max = 1, len(x) - 1
    while i < i_max:
        if x[i - 1] < x[i]:
            i_ahead = i + 1
            while i_ahead < i_max and x[i_ahead] == x[i]:
                i_ahead += 1
            if x[i_ahead] < x[i]:
                peaks.append((i + i_ahead - 1) // 2)  # middle of a plateau
                i = i_ahead
        i += 1
    return peaks


def _select_by_distance(peaks: list[int], priority: Array, distance: float) -> list[bool]:
    keep = [True] * len(peaks)
    d = math.ceil(distance)
    order = np.argsort(priority).tolist()  # as scipy: same sort, same tie order
    for i in range(len(peaks) - 1, -1, -1):
        j = order[i]
        if not keep[j]:
            continue
        k = j - 1
        while 0 <= k and peaks[j] - peaks[k] < d:
            keep[k] = False
            k -= 1
        k = j + 1
        while k < len(peaks) and peaks[k] - peaks[j] < d:
            keep[k] = False
            k += 1
    return keep


def _prominence(x: list[float], peak: int) -> tuple[float, int, int]:
    """(prominence, left base, right base) over the whole signal."""
    left_base = right_base = peak
    left_min = right_min = x[peak]
    i = peak
    while 0 <= i and x[i] <= x[peak]:
        if x[i] < left_min:
            left_min, left_base = x[i], i
        i -= 1
    i = peak
    while i <= len(x) - 1 and x[i] <= x[peak]:
        if x[i] < right_min:
            right_min, right_base = x[i], i
        i += 1
    return x[peak] - max(left_min, right_min), left_base, right_base


def find_peaks(x: Array, distance: float, prominence: float) -> npt.NDArray[np.intp]:
    """Indices of the local maxima at least `distance` samples apart (the higher one wins) with a
    prominence of at least `prominence`."""
    if distance < 1:
        raise ValueError("distance must be >= 1")
    xs = np.asarray(x, dtype=float).tolist()
    peaks = _local_maxima(xs)
    keep = _select_by_distance(peaks, np.asarray([xs[p] for p in peaks], dtype=float), distance)
    peaks = [p for p, k in zip(peaks, keep, strict=True) if k]
    peaks = [p for p in peaks if prominence <= _prominence(xs, p)[0]]
    return np.asarray(peaks, dtype=np.intp)


def peak_half_width_edges(x: Array, peaks: npt.NDArray[np.intp]) -> tuple[Array, Array]:
    """Interpolated left and right positions where each peak falls to half its prominence."""
    xs = np.asarray(x, dtype=float).tolist()
    left, right = [], []
    for peak in np.asarray(peaks).tolist():
        prom, i_min, i_max = _prominence(xs, peak)
        height = xs[peak] - prom * 0.5
        i = peak
        while i_min < i and height < xs[i]:
            i -= 1
        left_ip = float(i)
        if xs[i] < height:
            left_ip += (height - xs[i]) / (xs[i + 1] - xs[i])
        i = peak
        while i < i_max and height < xs[i]:
            i += 1
        right_ip = float(i)
        if xs[i] < height:
            right_ip -= (height - xs[i]) / (xs[i - 1] - xs[i])
        left.append(left_ip)
        right.append(right_ip)
    return np.asarray(left, dtype=float), np.asarray(right, dtype=float)
