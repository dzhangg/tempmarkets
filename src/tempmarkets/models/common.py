"""Shared pieces: feature prep, discretisation, scoring helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

OFFSETS = np.arange(-25, 26)  # support relative to round(NBM txn)


@dataclass
class Forecast:
    center: np.ndarray  # (n,) int
    pmf: np.ndarray     # (n, len(OFFSETS)), rows sum to 1

    def support(self) -> np.ndarray:
        return self.center[:, None] + OFFSETS[None, :]

    def cdf_at(self, k: np.ndarray) -> np.ndarray:
        """P(Y <= k) per row."""
        return (self.pmf * (self.support() <= np.asarray(k)[:, None])).sum(axis=1)

    def mean(self) -> np.ndarray:
        return (self.pmf * self.support()).sum(axis=1)


def centers(df: pd.DataFrame) -> np.ndarray:
    return np.rint(df["nbm_txn"].to_numpy()).astype(int)


def from_cdf(center: np.ndarray, cdf: Callable[[np.ndarray], np.ndarray]) -> Forecast:
    """Discretise continuous CDFs: P(Y=k) = F(k+0.5) - F(k-0.5), tails folded in.

    `cdf` maps an (n, m) array of absolute temperatures to probabilities row-wise.
    """
    edges = center[:, None] + np.append(OFFSETS - 0.5, OFFSETS[-1] + 0.5)[None, :]
    F = np.clip(cdf(edges), 0.0, 1.0)
    F = np.maximum.accumulate(F, axis=1)
    F[:, 0], F[:, -1] = 0.0, 1.0  # fold tails into end bins
    pmf = np.diff(F, axis=1)
    return Forecast(center, pmf / pmf.sum(axis=1, keepdims=True))


def jitter(y: np.ndarray, seed: int = 0) -> np.ndarray:
    """Integer target -> continuous (y + U(-0.5, 0.5)), so continuous models fit
    the discretised quantity consistently (Machado & Santos Silva 2005)."""
    return y + np.random.default_rng(seed).uniform(-0.5, 0.5, size=len(y))


FEATURE_FILL = ("d_tmp", "d_gfs", "lxnd", "p12", "sky", "dpt_dep")


def design(df: pd.DataFrame, fill: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Model features (all relative to NBM txn where it makes sense).

    Missing values are filled with training medians; pass the returned `fill`
    dict back in at predict time so test rows never see test statistics.
    """
    doy = pd.to_datetime(df["date"]).dt.dayofyear.to_numpy()
    X = pd.DataFrame(index=df.index)
    X["txn"] = df["nbm_txn"]
    X["d_tmp"] = df["nbm_tmp_max"] - df["nbm_txn"]           # hourly-path max vs NBM max
    X["d_gfs"] = df.get("gfs_nx", np.nan) - df["nbm_txn"]     # model disagreement
    X["lxnd"] = np.log1p(df["nbm_xnd"])                      # NBM spread
    X["p12"] = df["nbm_p12"] / 100
    X["sky"] = df["nbm_sky_day"] / 100
    X["dpt_dep"] = (df["nbm_txn"] - df["nbm_dpt_day"]) / 10  # dryness proxy
    X["sin"] = np.sin(2 * np.pi * doy / 365.25)
    X["cos"] = np.cos(2 * np.pi * doy / 365.25)
    if fill is None:
        fill = {c: float(X[c].median()) for c in FEATURE_FILL}
        fill["d_gfs"] = 0.0 if np.isnan(fill["d_gfs"]) else fill["d_gfs"]
    X = X.fillna(fill)
    return X, fill


# --- scores (used for quick checks here; full verification lives in verify.py / M4) ---

def rps_integer(fc: Forecast, y: np.ndarray) -> np.ndarray:
    """Discrete CRPS over unit bins: sum_k (F(k) - 1{y<=k})^2."""
    F = np.cumsum(fc.pmf, axis=1)
    obs = (fc.support() >= np.asarray(y)[:, None]).astype(float)
    return ((F - obs) ** 2).sum(axis=1)


def log_score(fc: Forecast, y: np.ndarray, floor: float = 1e-6) -> np.ndarray:
    idx = np.asarray(y) - fc.center - OFFSETS[0]
    idx = np.clip(idx, 0, len(OFFSETS) - 1)
    p = fc.pmf[np.arange(len(idx)), idx]
    return -np.log(np.maximum(p, floor))
