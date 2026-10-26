"""Phase 3.2 degradation and reliability helpers (evaluation/degrade.py, evaluation/reliability.py)."""

import math

import numpy as np
import pytest

from evaluation.degrade import alter

FRAME = np.full((120, 160, 3), 128, dtype=np.uint8)


@pytest.mark.parametrize(
    "kind,level,shape",
    [("resolution", 80, (60, 80, 3)), ("compression", 10, (120, 160, 3)), ("roll", 15, (120, 160, 3))],
)
def test_alterations_keep_a_valid_bgr_frame(kind, level, shape):
    out = alter(kind, level, seed=0)(FRAME)
    assert out.shape == shape and out.dtype == np.uint8


def test_low_light_darkens_and_adds_noise():
    out = alter("low_light", 0.2, seed=0)(FRAME)
    assert abs(float(out.mean()) - 128 * 0.2) < 2 and float(out.std()) > 3


def test_conformal_quantile_covers_at_least_one_minus_alpha():
    sk = pytest.importorskip("sklearn")  # the 'evaluate' dependency group
    assert sk
    from evaluation.reliability import ALPHA, conformal_q

    scores = np.arange(1, 101, dtype=float)
    q = conformal_q(scores)
    assert q == scores[math.ceil(101 * (1 - ALPHA)) - 1]
    assert (scores <= q).mean() >= 1 - ALPHA
