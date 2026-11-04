import datetime as dt

import numpy as np
import pandas as pd
from scipy.optimize import check_grad
from scipy.stats import norm

from tempmarkets.buckets import bucket_probs, parse_bucket
from tempmarkets.models.baseline import EmpiricalResidual, RawNBM
from tempmarkets.models.common import OFFSETS, from_cdf, log_score, rps_integer
from tempmarkets.models.emos import EMOS, _crps_grad, crps_gaussian
from tempmarkets.models.qreg import QuantileRegression


def synthetic(n=1500, seed=1):
    """y = round(txn + 0.7 + N(0, 1 + 0.6*xnd)): a warm bias and spread-dependent noise."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    txn = np.rint(70 + 15 * np.sin(2 * np.pi * dates.dayofyear / 365) + rng.normal(0, 3, n))
    xnd = rng.integers(1, 5, n).astype(float)
    y = np.rint(txn + 0.7 + rng.normal(0, 1 + 0.6 * xnd)).astype(int)
    return pd.DataFrame({"date": dates, "nbm_txn": txn, "nbm_xnd": xnd, "nbm_p12": 20.0,
                         "nbm_sky_day": 50.0, "nbm_tmp_max": txn, "nbm_dpt_day": txn - 15,
                         "gfs_nx": txn, "y": y})


def test_from_cdf_is_a_proper_pmf():
    c = np.array([70, 90])
    fc = from_cdf(c, lambda x: norm.cdf(x, c[:, None] + 1.0, 2.0))
    assert np.allclose(fc.pmf.sum(1), 1) and (fc.pmf >= 0).all()
    assert np.allclose(fc.mean(), c + 1.0, atol=0.01)


def test_scores_reward_sharp_correct_forecasts():
    c = np.array([70])
    sharp = from_cdf(c, lambda x: norm.cdf(x, 70, 0.6))
    wide = from_cdf(c, lambda x: norm.cdf(x, 70, 4.0))
    y = np.array([70])
    assert rps_integer(sharp, y) < rps_integer(wide, y)
    assert log_score(sharp, y) < log_score(wide, y)


def test_emos_gradient_and_crps():
    rng = np.random.default_rng(0)
    Xm, Xs, y = rng.normal(size=(50, 3)), rng.normal(size=(50, 2)), rng.normal(size=50)
    th = rng.normal(size=5) * 0.3
    assert check_grad(lambda t: _crps_grad(t, Xm, Xs, y)[0], lambda t: _crps_grad(t, Xm, Xs, y)[1], th) < 1e-5
    assert abs(crps_gaussian(0.0, 0.0, 1.0) - 0.2337) < 1e-3  # known value


def test_models_learn_bias_and_spread():
    d = synthetic()
    train, test = d.iloc[:1200], d.iloc[1200:]
    y = test["y"].to_numpy()
    score = lambda fc: rps_integer(fc, y).mean()  # noqa: E731
    raw = score(RawNBM().fit(train).predict(test))
    base_fc = EmpiricalResidual().fit(train).predict(test)
    base = score(base_fc)
    assert abs((base_fc.mean() - y).mean()) < 0.35                           # removes the +0.7 bias
    for M in (EMOS, QuantileRegression):
        fc = M().fit(train).predict(test)
        assert np.allclose(fc.pmf.sum(1), 1)
        assert abs((fc.mean() - y).mean()) < 0.35, M.name
        # Spread-aware models beat both the biased raw NBM and the spread-blind baseline.
        assert score(fc) < raw and score(fc) < base, M.name
    emos = EMOS().fit(train)
    _, sig = emos.params(test)
    assert np.corrcoef(sig, test["nbm_xnd"])[0, 1] > 0.9                    # spread tracks xnd


def test_bucket_probs_sum_to_one():
    bs = [parse_bucket(x) for x in ["73°F or below", "74-75°F", "76-77°F", "78°F or higher"]]
    c = np.array([75])
    fc = from_cdf(c, lambda x: norm.cdf(x, 75.3, 1.5))
    p = bucket_probs(fc.support()[0], fc.pmf[0], bs)
    assert abs(sum(p.values()) - 1) < 1e-9 and max(p, key=p.get) == "74-75°F"
