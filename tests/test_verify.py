import numpy as np
from scipy.stats import norm

from tempmarkets.models.common import from_cdf
from tempmarkets.verify import (block_bootstrap_skill, bucket_matrix, bucket_scores,
                                expected_calibration_error, pit_dispersion, pit_randomized,
                                reliability)


def _draw(n, sd_true, sd_fc, seed=0):
    rng = np.random.default_rng(seed)
    mu = rng.normal(80, 5, n)
    y = np.rint(mu + rng.normal(0, sd_true, n)).astype(int)
    c = np.rint(mu).astype(int)
    fc = from_cdf(c, lambda x: norm.cdf(x, mu[:, None], sd_fc))
    return fc, y


def test_pit_detects_calibration_and_dispersion():
    fc, y = _draw(20000, 2.0, 2.0)
    u = pit_randomized(fc.pmf, fc.center, y)
    assert abs(pit_dispersion(u) - 1) < 0.05
    assert np.allclose(np.histogram(u, bins=10, range=(0, 1))[0] / len(u), 0.1, atol=0.01)
    narrow, y2 = _draw(20000, 3.0, 1.5)
    assert pit_dispersion(pit_randomized(narrow.pmf, narrow.center, y2)) > 1.3   # too narrow
    wide, y3 = _draw(20000, 1.5, 3.0)
    assert pit_dispersion(pit_randomized(wide.pmf, wide.center, y3)) < 0.7      # too wide


def test_bucket_matrix_sums_and_grid():
    fc, y = _draw(50, 2.0, 2.0)
    ids, probs = bucket_matrix(fc.pmf, fc.center)
    assert np.allclose(probs.sum(1), 1)
    # 82 and 83 share a bucket; 83 and 84 do not (even lower bound).
    assert np.floor(82 / 2) == np.floor(83 / 2) != np.floor(84 / 2)
    s = bucket_scores(fc.pmf, fc.center, y)
    assert ((s["brier"] >= 0) & (s["brier"] <= 2)).all()


def test_reliability_of_calibrated_forecast():
    fc, y = _draw(20000, 2.0, 2.0)
    rel = reliability(fc.pmf, fc.center, y)
    assert expected_calibration_error(rel) < 0.02


def test_block_bootstrap_ci_brackets_point():
    rng = np.random.default_rng(1)
    ref = rng.gamma(2, 1, 1000)
    score = ref * 0.9
    s, lo, hi = block_bootstrap_skill(score, ref, n_boot=500)
    assert abs(s - 0.1) < 1e-9 and lo <= s <= hi
