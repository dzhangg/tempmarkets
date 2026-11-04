"""M3: rolling-origin (monthly refit, expanding window) out-of-sample predictive distributions.

For each station x checkpoint x test month m, every model is trained only on
target dates <= (first day of m) - 2 days, so even the earliest day-ahead
forecast in m never trains on an observation that was not final yet.

Outputs:
  data/processed/predictions.parquet  one row per station x date x checkpoint x model
  reports/m3_models.md                quick out-of-sample skill check (full verification is M4)
Usage: python scripts/06_fit_models.py [--first-test-month 2022-01]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from tempmarkets.models.baseline import EmpiricalResidual, RawNBM
from tempmarkets.models.common import OFFSETS, Forecast, log_score, rps_integer
from tempmarkets.models.emos import EMOS
from tempmarkets.models.qreg import QuantileRegression

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
MODELS = (RawNBM, EmpiricalResidual, EMOS, QuantileRegression)


def even_bucket_logloss(fc: Forecast, y: np.ndarray) -> np.ndarray:
    """Log loss on the current market grid (2°F buckets with even lower bound)."""
    same = np.floor(fc.support() / 2) == np.floor(np.asarray(y)[:, None] / 2)
    return -np.log(np.maximum((fc.pmf * same).sum(axis=1), 1e-6))


def central_coverage(fc: Forecast, y: np.ndarray, level: float = 0.8) -> np.ndarray:
    F = np.cumsum(fc.pmf, axis=1)
    a = (1 - level) / 2
    sup = fc.support()
    lo = sup[np.arange(len(y)), np.argmax(F >= a, axis=1)]
    hi = sup[np.arange(len(y)), np.argmax(F >= 1 - a, axis=1)]
    return ((y >= lo) & (y <= hi)).astype(float)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-test-month", default="2022-01")
    args = ap.parse_args()

    f = pd.read_parquet(PROC / "features.parquet")
    f = f.dropna(subset=["nbm_txn", "max_metar"]).copy()
    f["y"] = f["max_metar"].astype(int)
    f["date"] = pd.to_datetime(f["date"])
    months = pd.period_range(args.first_test_month, f["date"].max().to_period("M"), freq="M")

    out, t0 = [], time.time()
    for (st, cp), g in f.groupby(["station", "checkpoint"]):
        g = g.sort_values("date")
        for m in months:
            start = m.start_time
            test = g[(g["date"] >= start) & (g["date"] <= m.end_time)]
            train = g[g["date"] <= start - pd.Timedelta(days=2)]
            if test.empty:
                continue
            assert train["date"].max() < test["date"].min() - pd.Timedelta(days=1)
            for M in MODELS:
                fc = M().fit(train).predict(test)
                out.append(pd.DataFrame({
                    "station": st, "date": test["date"].dt.date.to_numpy(), "checkpoint": cp,
                    "model": M.name, "test_month": str(m), "train_end": train["date"].max().date(),
                    "n_train": len(train), "y": test["y"].to_numpy(),
                    "y_all": test["max_all"].to_numpy(), "nbm_txn": test["nbm_txn"].to_numpy(),
                    "center": fc.center, "pmf": list(fc.pmf),
                    "rps": rps_integer(fc, test["y"].to_numpy()),
                    "log_score": log_score(fc, test["y"].to_numpy()),
                    "bucket_logloss": even_bucket_logloss(fc, test["y"].to_numpy()),
                    "cover80": central_coverage(fc, test["y"].to_numpy()),
                    "mean": fc.mean(),
                }))
        print(f"{st} {cp}: done ({time.time() - t0:.0f}s)", flush=True)

    p = pd.concat(out, ignore_index=True)
    p.to_parquet(PROC / "predictions.parquet", index=False)

    lines = ["# M3: out-of-sample predictive distributions — quick skill check", "",
             f"Monthly refit, expanding window; test months {months[0]} → {months[-1]}. "
             "Target = current METAR-rule max. Lower is better except coverage (target 80%). "
             "Full verification (reliability, PIT, CIs) is M4.", "",
             "Discrete CRPS (RPS over 1°F bins) is in °F, log score is in nats, and bucket loss uses "
             "today's 2°F grid. Skill = 1 − CRPS / CRPS(raw NBM).", ""]
    for cp, gc in p.groupby("checkpoint"):
        lines += [f"## Checkpoint `{cp}`", "",
                  "| station | model | n | CRPS | skill vs raw NBM | log score | 2°F bucket log loss | 80% coverage | bias of mean |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for st, gs in gc.groupby("station"):
            ref = gs[gs["model"] == "nbm_raw"]["rps"].mean()
            for mname in [M.name for M in MODELS]:
                g = gs[gs["model"] == mname]
                lines.append(f"| {st} | {mname} | {len(g)} | {g['rps'].mean():.3f} | {1 - g['rps'].mean() / ref:+.1%} | "
                             f"{g['log_score'].mean():.3f} | {g['bucket_logloss'].mean():.3f} | "
                             f"{g['cover80'].mean():.1%} | {(g['mean'] - g['y']).mean():+.2f} |")
        lines.append("")
    (ROOT / "reports" / "m3_models.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
