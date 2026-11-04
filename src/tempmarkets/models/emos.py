"""EMOS / NGR: Y ~ N(mu, sigma^2), fitted by minimum CRPS (Gneiting et al. 2005).

    mu       = b0 + b1*txn + b2*d_tmp + b3*d_gfs + b4*sin + b5*cos + b6*sky + b7*p12 + b8*dpt_dep
    log sig  = g0 + g1*lxnd + g2*p12 + g3*sky + g4*sin + g5*cos

Target is jittered (y + U(-.5,.5)) so the continuous Gaussian describes the
quantity that gets discretised into P(Y=k) = F(k+.5) - F(k-.5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

from .common import Forecast, centers, design, from_cdf, jitter

MU_COLS = ["txn", "d_tmp", "d_gfs", "sin", "cos", "sky", "p12", "dpt_dep"]
SIG_COLS = ["lxnd", "p12", "sky", "sin", "cos"]


def crps_gaussian(y, mu, sig):
    z = (y - mu) / sig
    return sig * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def _crps_grad(theta, Xm, Xs, y):
    k = Xm.shape[1]
    mu, sig = Xm @ theta[:k], np.exp(Xs @ theta[k:])
    z = (y - mu) / sig
    Phi, phi = norm.cdf(z), norm.pdf(z)
    crps = sig * (z * (2 * Phi - 1) + 2 * phi - 1 / np.sqrt(np.pi))
    d_mu = -(2 * Phi - 1)                      # dCRPS/dmu
    d_logsig = crps - sig * z * (2 * Phi - 1)  # dCRPS/dlog(sig) = sig*(2phi - 1/sqrt(pi))
    n = len(y)
    return crps.mean(), np.concatenate([Xm.T @ d_mu / n, Xs.T @ d_logsig / n])


class EMOS:
    name = "emos"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def _mats(self, X: pd.DataFrame):
        Xm = np.column_stack([np.ones(len(X)), X[MU_COLS].to_numpy()])
        Xs = np.column_stack([np.ones(len(X)), X[SIG_COLS].to_numpy()])
        return (Xm - self.m_shift) / self.m_scale, (Xs - self.s_shift) / self.s_scale

    def fit(self, train: pd.DataFrame) -> "EMOS":
        X, self.fill = design(train)
        Xm = np.column_stack([np.ones(len(X)), X[MU_COLS].to_numpy()])
        Xs = np.column_stack([np.ones(len(X)), X[SIG_COLS].to_numpy()])
        # Standardise non-intercept columns for a well-conditioned optimisation.
        self.m_shift = np.r_[0, Xm[:, 1:].mean(0)]; self.m_scale = np.r_[1, Xm[:, 1:].std(0) + 1e-9]
        self.s_shift = np.r_[0, Xs[:, 1:].mean(0)]; self.s_scale = np.r_[1, Xs[:, 1:].std(0) + 1e-9]
        Xm, Xs = (Xm - self.m_shift) / self.m_scale, (Xs - self.s_shift) / self.s_scale
        y = jitter(train["y"].to_numpy(float), self.seed)
        beta0 = np.linalg.lstsq(Xm, y, rcond=None)[0]
        resid_sd = np.std(y - Xm @ beta0)
        theta0 = np.concatenate([beta0, [np.log(resid_sd)], np.zeros(Xs.shape[1] - 1)])
        res = minimize(_crps_grad, theta0, args=(Xm, Xs, y), jac=True, method="L-BFGS-B")
        self.theta, self.k, self.converged = res.x, Xm.shape[1], res.success
        return self

    def params(self, df: pd.DataFrame):
        X, _ = design(df, self.fill)
        Xm, Xs = self._mats(X)
        return Xm @ self.theta[:self.k], np.exp(Xs @ self.theta[self.k:])

    def predict(self, df: pd.DataFrame) -> Forecast:
        mu, sig = self.params(df)
        return from_cdf(centers(df), lambda x: norm.cdf(x, mu[:, None], sig[:, None]))
