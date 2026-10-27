"""Learned reliability model (Plan V3 Phase 3.2): each clip's expected cadence / step-time error.

Trained on evaluation/results/degradation_runs.csv (degrade.py: LJMU clips, original and degraded,
scored against reference heel strikes). Features are quality measures the app computes without a
reference (FEATURES). For each metric:
- a scale model s(x) predicts log(|error| + eps): gradient boosting (sklearn) or a ridge regression;
- normalised split-conformal: on calibration participants, score = |error| / s(x); the interval is
  +- q * s(x) with q the ceil((n + 1)(1 - alpha)) / n quantile of the scores, so that at least
  1 - alpha of new clips fall inside if they look like the calibration ones.
Evaluation is leave-participant-out (GroupKFold by participant): each fold's participants are never
seen in training or calibration. Reported per model: coverage, mean interval width, and the same for
a constant interval (the calibration quantile of |error|), which is what the app shows today.

Run: uv run --group evaluate python -m evaluation.reliability  (writes results/reliability.json)

Result (2026-10-27, 527 accepted runs, 54 participants): not shipped. The intervals reach their
coverage, but the predicted error barely ranks clips by real error (Spearman ~0.1), and rejecting the
worst-predicted 10-20% leaves the share of large errors where random rejection would. Within what the
gate accepts, the remaining error is close to the reference's own noise and not predictable from these
quality measures.
"""

import argparse
import csv
import json
import math
import os
from typing import Any

import numpy as np
import numpy.typing as npt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evaluation.evaluate import HERE

ALPHA = 0.10  # 90% intervals
EPS = {"cadence_error": 0.2, "step_time_error_ms": 2.0}  # ~ the reference's own resolution
FEATURES = (
    "q_fps",
    "pose_fraction",
    "q_feet_visible_fraction",
    "q_view_ratio",
    "q_path_convergence_deg",
    "q_steady_walking_s",
    "q_steps_detected",
    "q_step_time_cv",
    "q_usable_frame_fraction",
    "q_height_px",
    "q_mean_leg_visibility",
    "q_heel_jitter_px",
)
METRICS = ("cadence_error", "step_time_error_ms")


def load(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["status"] != "accepted" or r.get("cadence_error") in (None, ""):
                continue
            r["pose_fraction"] = float(r["q_frames_with_pose"]) / float(r["q_frames_total"])
            rows.append(r)
    return rows


def matrix(rows: list[dict[str, Any]]) -> npt.NDArray[np.float64]:
    def num(v: Any) -> float:
        return math.nan if v in (None, "") else float(v)

    x = np.array([[num(r[f]) for f in FEATURES] for r in rows], dtype=float)
    med = np.nanmedian(x, axis=0)
    return np.where(np.isfinite(x), x, med)  # a missing measure (rare) -> the median


def scale_model(kind: str) -> Any:
    if kind == "gbm":
        return GradientBoostingRegressor(
            n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0
        )
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0))


def conformal_q(scores: npt.NDArray[np.float64]) -> float:
    n = len(scores)
    k = min(n, math.ceil((n + 1) * (1 - ALPHA)))
    return float(np.sort(scores)[k - 1])


def evaluate_model(
    x: npt.NDArray[np.float64], err: npt.NDArray[np.float64], groups: npt.NDArray[Any], kind: str, eps: float
) -> dict[str, Any]:
    y = np.log(np.abs(err) + eps)
    cover, width, c_cover, c_width = [], [], [], []
    for train, test in GroupKFold(n_splits=5).split(x, y, groups):
        # Split the training participants again: 75% fit the scale model, 25% calibrate.
        tg = np.unique(groups[train])
        rng = np.random.default_rng(0)
        cal_g = set(rng.choice(tg, size=max(1, len(tg) // 4), replace=False))
        cal = np.array([i for i in train if groups[i] in cal_g])
        fit = np.array([i for i in train if groups[i] not in cal_g])
        m = scale_model(kind).fit(x[fit], y[fit])
        s_cal, s_test = np.exp(m.predict(x[cal])), np.exp(m.predict(x[test]))
        q = conformal_q(np.abs(err[cal]) / s_cal)
        half = q * s_test
        cover += list(np.abs(err[test]) <= half)
        width += list(2 * half)
        qc = conformal_q(np.abs(err[cal]))
        c_cover += list(np.abs(err[test]) <= qc)
        c_width += [2 * qc] * len(test)
    return {
        "coverage": round(float(np.mean(cover)), 3),
        "mean_width": round(float(np.mean(width)), 2),
        "median_width": round(float(np.median(width)), 2),
        "constant_coverage": round(float(np.mean(c_cover)), 3),
        "constant_width": round(float(np.mean(c_width)), 2),
    }


def discrimination(
    x: npt.NDArray[np.float64], err: npt.NDArray[np.float64], groups: npt.NDArray[Any], eps: float
) -> dict[str, Any]:
    """Does the predicted error rank clips by their real error? Leave-participant-out predictions:
    Spearman correlation with |error|, and what rejecting the worst-predicted share does to the share
    of errors beyond `limit` compared with rejecting the same share at random."""
    from scipy.stats import spearmanr

    pred = np.zeros(len(err))
    for train, test in GroupKFold(n_splits=5).split(x, err, groups):
        m = scale_model("gbm").fit(x[train], np.log(np.abs(err[train]) + eps))
        pred[test] = np.exp(m.predict(x[test]))
    a = np.abs(err)
    limit = float(np.quantile(a, 0.95))
    order = np.argsort(-pred)
    curve = []
    for frac in (0.0, 0.1, 0.2):
        keep = order[int(frac * len(a)) :]
        curve.append({"rejected": frac, "share_beyond_limit": round(float((a[keep] > limit).mean()), 3)})
    return {
        "spearman": round(float(spearmanr(pred, a).statistic), 3),
        "limit_p95_abs": round(limit, 2),
        "share_beyond_limit_if_random": round(float((a > limit).mean()), 3),
        "rejecting_worst_predicted": curve,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", default=os.path.join(HERE, "results", "degradation_runs.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "results", "reliability.json"))
    args = ap.parse_args()
    rows = load(args.runs)
    x = matrix(rows)
    groups = np.array([r["participant"] for r in rows])
    out: dict[str, Any] = {
        "runs": len(rows),
        "participants": len(set(groups)),
        "alpha": ALPHA,
        "features": list(FEATURES),
        "evaluation": "leave-participant-out, 5 folds (GroupKFold)",
    }
    for metric in METRICS:
        err = np.array([float(r[metric]) for r in rows])
        out[metric] = {kind: evaluate_model(x, err, groups, kind, EPS[metric]) for kind in ("gbm", "ridge")}
        out[metric]["discrimination"] = discrimination(x, err, groups, EPS[metric])
        print(metric, out[metric])
    with open(args.out, "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
