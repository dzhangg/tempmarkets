"""Reference models: raw NBM, and NBM + empirical seasonal residual distribution."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .common import OFFSETS, Forecast, centers, from_cdf


class RawNBM:
    """NBM's own Gaussian: N(txn, xnd). Uncalibrated; the thing to beat."""
    name = "nbm_raw"

    def fit(self, train: pd.DataFrame) -> "RawNBM":
        return self

    def predict(self, df: pd.DataFrame) -> Forecast:
        mu = df["nbm_txn"].to_numpy(float)
        sd = np.maximum(df["nbm_xnd"].fillna(2.0).to_numpy(float), 0.7)
        return from_cdf(centers(df), lambda x: norm.cdf(x, mu[:, None], sd[:, None]))


class EmpiricalResidual:
    """NBM txn + empirical distribution of (obs - round(txn)) from training days
    within ±`window` days of year. Mixed with a little Gaussian (fit to the same
    residuals) so no integer gets zero probability."""
    name = "baseline"

    def __init__(self, window: int = 15, gauss_weight: float = 0.05, min_n: int = 60):
        self.window, self.w, self.min_n = window, gauss_weight, min_n

    def fit(self, train: pd.DataFrame) -> "EmpiricalResidual":
        self.doy = pd.to_datetime(train["date"]).dt.dayofyear.to_numpy()
        self.res = (train["y"].to_numpy() - centers(train)).astype(int)
        return self

    def predict(self, df: pd.DataFrame) -> Forecast:
        c = centers(df)
        doy = pd.to_datetime(df["date"]).dt.dayofyear.to_numpy()
        pmf = np.empty((len(df), len(OFFSETS)))
        lo = OFFSETS[0]
        for i, d in enumerate(doy):
            dist = np.abs(self.doy - d)
            dist = np.minimum(dist, 366 - dist)
            w = self.window
            r = self.res[dist <= w]
            while len(r) < self.min_n and w < 183:  # widen thin windows
                w += 10
                r = self.res[dist <= w]
            hist = np.bincount(np.clip(r - lo, 0, len(OFFSETS) - 1), minlength=len(OFFSETS)) / len(r)
            mu, sd = r.mean(), max(r.std(), 0.7)
            g = np.diff(norm.cdf(np.append(OFFSETS - 0.5, OFFSETS[-1] + 0.5), mu, sd))
            pmf[i] = (1 - self.w) * hist + self.w * g / g.sum()
        return Forecast(c, pmf / pmf.sum(axis=1, keepdims=True))
