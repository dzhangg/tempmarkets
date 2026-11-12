"""Forward paper log: snapshot live books + live EMOS forecast; record hypothetical trades.

READ-ONLY. Fetches public data (IEM NBM/GFS MOS, Polymarket Gamma + CLOB /book) and
appends to paper_log/*.jsonl. It places no orders and has no wallet or signing code.

For each study station and each open event whose observation date is today or
tomorrow (local), it:
  1. builds features from the latest NBM/GFS runs already published (same delays as M2)
  2. fits EMOS on all history for the matching lead (tomorrow -> d1, today -> d0)
  3. converts the forecast to the event's buckets and reads each bucket's best bid/ask
  4. logs the snapshot, and logs one paper trade per event and lead if edge > threshold
Settle later with: python scripts/paper_settle.py
Usage: python scripts/paper_snapshot.py [--threshold 0.05] [--stake 1]
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tempmarkets.buckets import bucket_probs, parse_bucket
from tempmarkets.features import FixedCheckpoint, build_features
from tempmarkets.io import iem, polymarket as pm
from tempmarkets.models.common import OFFSETS
from tempmarkets.models.emos import EMOS
from tempmarkets.paper import log

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.05)
    ap.add_argument("--stake", type=float, default=1.0)
    args = ap.parse_args()

    now = pd.Timestamp.now(tz="UTC").floor("min")
    feats = pd.read_parquet(ROOT / "data" / "processed" / "features.parquet")
    feats = feats.dropna(subset=["nbm_txn", "max_metar"]).assign(y=lambda d: d["max_metar"].astype(int))
    existing = {(t["slug"], t["lead"]) for t in log.read(log.TRADES)}
    snaps, trades = [], []

    for icao, st in CFG["stations"].items():
        if st.get("candidate"):
            continue
        tz = st["tz"]
        today = now.tz_convert(tz).date()
        nbs = iem.mos_range(icao, "NBS", now - pd.Timedelta(days=2), now)
        time.sleep(3)  # IEM rate limit
        gfs = iem.mos_range(icao, "GFS", now - pd.Timedelta(days=2), now)
        time.sleep(3)
        events = {pm.observation_date(e): e for e in pm.series_events(st["series_slug"], closed=False)
                  if not pm.is_superseded(e)}
        for target, lead, train_cp in ((today + dt.timedelta(days=1), "d1", "d1_1800"),
                                       (today, "d0", "d0_0800")):
            ev = events.get(target)
            if ev is None:
                continue
            f = build_features(nbs, gfs, [target], tz, FixedCheckpoint("live", now))
            if f["nbm_txn"].isna().all() if "nbm_txn" in f else True:
                print(f"{icao} {target} ({lead}): no NBM daytime max in the latest published run (window already passed or run not out yet); skipping")
                continue
            f["station"] = icao
            hist = feats[(feats["station"] == icao) & (feats["checkpoint"] == train_cp)]
            model = EMOS().fit(hist)
            fc = model.predict(f)
            bms = pm.bucket_markets(ev)
            buckets = [parse_bucket(b.label) for b in bms]
            probs = bucket_probs(fc.center[0] + OFFSETS, fc.pmf[0], buckets)
            fee = pm.fee_schedule(ev)
            quotes = [log.best_quotes(pm.order_book(b.yes_token)) for b in bms]
            for b, q in zip(bms, quotes):
                snaps.append({"ts": now.isoformat(), "station": icao, "date": str(target), "lead": lead,
                              "slug": ev["slug"], "bucket": b.label, "model_p": round(probs[b.label], 5),
                              **q, "nbs_runtime": str(f.loc[0, "nbs_runtime"]), "nbm_txn": f.loc[0, "nbm_txn"],
                              "nbm_xnd": f.loc[0, "nbm_xnd"], "fee_rate": fee["rate"]})
            if (ev["slug"], lead) in existing:
                continue
            d = log.paper_decision([b.label for b in bms], [probs[b.label] for b in bms],
                                   [q["ask"] for q in quotes], [q["ask_size"] for q in quotes],
                                   fee["rate"], args.threshold, args.stake)
            if d:
                trades.append({"ts": now.isoformat(), "station": icao, "date": str(target), "lead": lead,
                               "slug": ev["slug"], "threshold": args.threshold, "fee_rate": fee["rate"], **d})
            mu, sig = model.params(f)
            print(f"{icao} {target} ({lead}): NBM {f.loc[0, 'nbm_txn']:.0f}±{f.loc[0, 'nbm_xnd']:.0f} → "
                  f"EMOS N({mu[0]:.1f}, {sig[0]:.1f}); top bucket {max(probs, key=probs.get)} "
                  f"{max(probs.values()):.0%}; " + (f"PAPER BUY {d['bucket']} @ {d['ask']:.3f} (edge {d['edge']:+.3f})"
                                                     if d else "no trade"))

    print(f"logged {log.append(log.SNAPSHOTS, snaps)} bucket snapshots, {log.append(log.TRADES, trades)} paper trades")


if __name__ == "__main__":
    main()
