"""Verification for integer-valued predictive distributions and bucket probabilities.

Inputs are the `pmf` rows saved by scripts/06_fit_models.py: probability over
center + OFFSETS. Bucket metrics use a 2°F grid with an even lower bound
(the current market grid: ..., 82-83, 84-85, ...).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .models.common import OFFSETS


def stack_pmf(pmf_col: pd.Series) -> np.ndarray:
    return np.vstack(pmf_col.to_numpy())


def pit_randomized(pmf: np.ndarray, center: np.ndarray, y: np.ndarray, seed: int = 0) -> np.ndarray:
    """Randomized PIT for discrete forecasts: U ~ Uniform(F(y-1), F(y)).
    Uniform on [0,1] iff the forecast is calibrated (Czado et al. 2009)."""
    F = np.cumsum(pmf, axis=1)
    idx = np.clip(np.asarray(y) - center - OFFSETS[0], 0, pmf.shape[1] - 1)
    rows = np.arange(len(idx))
    hi = F[rows, idx]
    lo = np.where(idx > 0, F[rows, np.maximum(idx - 1, 0)], 0.0)
    u = np.random.default_rng(seed).uniform(size=len(idx))
    return np.clip(lo + u * (hi - lo), 0, 1)


def pit_dispersion(u: np.ndarray) -> float:
    """12 * Var(PIT): 1 = calibrated spread, >1 = too narrow (U-shape), <1 = too wide (hump)."""
    return float(12 * np.var(u))


def bucket_matrix(pmf: np.ndarray, center: np.ndarray, width: int = 2):
    """Collapse integer pmfs into 2°F buckets. Returns (bucket_ids (n, B), probs (n, B))."""
    support = center[:, None] + OFFSETS[None, :]
    b = np.floor(support / width).astype(int)
    b0 = b[:, :1]
    rel = b - b0                                  # 0..B-1 within each row
    B = rel.max() + 1
    probs = np.zeros((len(pmf), B))
    np.add.at(probs, (np.repeat(np.arange(len(pmf)), pmf.shape[1]), rel.ravel()), pmf.ravel())
    ids = b0 + np.arange(B)[None, :]
    return ids, probs


def bucket_scores(pmf: np.ndarray, center: np.ndarray, y: np.ndarray, width: int = 2) -> pd.DataFrame:
    """Per-row multi-category Brier score and log loss on the bucket grid."""
    ids, probs = bucket_matrix(pmf, center, width)
    obs = (ids == np.floor(np.asarray(y) / width).astype(int)[:, None]).astype(float)
    p_obs = (probs * obs).sum(axis=1)
    return pd.DataFrame({"brier": ((probs - obs) ** 2).sum(axis=1),
                         "bucket_logloss": -np.log(np.maximum(p_obs, 1e-6)),
                         "p_obs_bucket": p_obs})


def reliability(pmf: np.ndarray, center: np.ndarray, y: np.ndarray, width: int = 2,
                bins: np.ndarray = np.linspace(0, 1, 11)) -> pd.DataFrame:
    """Pool every (bucket probability, bucket happened?) pair; bin by forecast probability.
    Pairs with p < 0.005 are dropped (far-tail buckets that would swamp the lowest bin)."""
    ids, probs = bucket_matrix(pmf, center, width)
    obs = (ids == np.floor(np.asarray(y) / width).astype(int)[:, None])
    p, o = probs.ravel(), obs.ravel().astype(float)
    keep = p >= 0.005
    p, o = p[keep], o[keep]
    k = np.clip(np.digitize(p, bins) - 1, 0, len(bins) - 2)
    df = pd.DataFrame({"bin": k, "p": p, "o": o}).groupby("bin").agg(
        p_mean=("p", "mean"), obs_freq=("o", "mean"), n=("o", "size")).reset_index()
    return df


def expected_calibration_error(rel: pd.DataFrame) -> float:
    w = rel["n"] / rel["n"].sum()
    return float((w * (rel["p_mean"] - rel["obs_freq"]).abs()).sum())


def block_bootstrap_skill(score: np.ndarray, ref: np.ndarray, block: int = 30, n_boot: int = 2000,
                          seed: int = 0) -> tuple[float, float, float]:
    """Skill = 1 - mean(score)/mean(ref) with a moving-block bootstrap CI.

    Rows must be in time order and paired (same days). Blocks of `block` days
    keep the serial correlation of daily errors.
    """
    score, ref = np.asarray(score, float), np.asarray(ref, float)
    n = len(score)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    skills = 1 - score[idx].mean(axis=1) / ref[idx].mean(axis=1)
    lo, hi = np.percentile(skills, [2.5, 97.5])
    return float(1 - score.mean() / ref.mean()), float(lo), float(hi)
