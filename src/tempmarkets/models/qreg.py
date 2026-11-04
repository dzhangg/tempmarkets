"""Linear quantile regression on the NBM residual -> full CDF.

Fits Q_tau(y_jit - txn | X) for a grid of taus, sorts the predicted quantiles
(rearrangement, Chernozhukov et al. 2010), interpolates the CDF linearly between
them, and adds exponential tails beyond the outermost taus.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from statsmodels.regression.quantile_regression import QuantReg

from .common import Forecast, centers, design, from_cdf, jitter

TAUS = np.array([0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.975, 0.99])
COLS = ["d_tmp", "d_gfs", "lxnd", "sin", "cos", "sky", "p12", "dpt_dep"]


def _cdf_from_quantiles(q: np.ndarray, taus: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Row-wise CDF at points x (n, m) given sorted quantiles q (n, T)."""
    n, m = x.shape
    out = np.empty((n, m))
    # Exponential tails matched to the gap between the two outermost quantiles.
    s_lo = np.maximum((q[:, 2] - q[:, 0]) / np.log(taus[2] / taus[0]), 0.2)
    s_hi = np.maximum((q[:, -1] - q[:, -3]) / np.log((1 - taus[-3]) / (1 - taus[-1])), 0.2)
    for i in range(n):
        qi = q[i] + np.arange(len(taus)) * 1e-9  # strictly increasing for interp
        F = np.interp(x[i], qi, taus)
        lo, hi = x[i] < qi[0], x[i] > qi[-1]
        F[lo] = taus[0] * np.exp((x[i][lo] - qi[0]) / s_lo[i])
        F[hi] = 1 - (1 - taus[-1]) * np.exp(-(x[i][hi] - qi[-1]) / s_hi[i])
        out[i] = F
    return out


class QuantileRegression:
    name = "qreg"

    def __init__(self, taus: np.ndarray = TAUS, seed: int = 0):
        self.taus, self.seed = taus, seed

    def fit(self, train: pd.DataFrame) -> "QuantileRegression":
        X, self.fill = design(train)
        A = np.column_stack([np.ones(len(X)), X[COLS].to_numpy()])
        self.shift = np.r_[0, A[:, 1:].mean(0)]; self.scale = np.r_[1, A[:, 1:].std(0) + 1e-9]
        A = (A - self.shift) / self.scale
        r = jitter(train["y"].to_numpy(float), self.seed) - train["nbm_txn"].to_numpy(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # IterationLimitWarning on extreme taus is harmless here
            self.coef = np.column_stack([QuantReg(r, A).fit(q=t, max_iter=5000).params for t in self.taus])
        return self

    def quantiles(self, df: pd.DataFrame) -> np.ndarray:
        X, _ = design(df, self.fill)
        A = (np.column_stack([np.ones(len(X)), X[COLS].to_numpy()]) - self.shift) / self.scale
        q = A @ self.coef + df["nbm_txn"].to_numpy(float)[:, None]
        return np.sort(q, axis=1)  # rearrangement fixes any quantile crossing

    def predict(self, df: pd.DataFrame) -> Forecast:
        q = self.quantiles(df)
        return from_cdf(centers(df), lambda x: _cdf_from_quantiles(q, self.taus, x))
