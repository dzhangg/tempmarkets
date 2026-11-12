"""M5 data pull: hourly CLOB price history for every bucket of every settled event.

Window per event: D-3 00:00 UTC -> D+1 12:00 UTC (covers both checkpoints).
Cached per token under data/raw/prices/. GET only. Light parallelism.
Usage: python scripts/08_fetch_prices.py [--workers 4]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from tempmarkets.io import polymarket as pm

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())
CACHE = ROOT / "data" / "raw" / "prices"


def jobs():
    for icao, st in CFG["stations"].items():
        if st.get("candidate"):
            continue
        evs = json.loads((ROOT / "data" / "raw" / "polymarket" / f"{st['series_slug']}.json").read_text())
        for ev in evs:
            if pm.is_superseded(ev):
                continue
            d = pm.observation_date(ev)
            start = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) - 3 * 86400
            end = start + 4 * 86400 + 12 * 3600
            for b in pm.bucket_markets(ev):
                yield b.yes_token, start, end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    todo = [j for j in jobs() if not (CACHE / f"{j[0]}.json").exists()]
    print(f"{len(todo)} token histories to fetch", flush=True)
    t0, done, empty, failed = time.time(), 0, 0, 0

    def one(job):
        time.sleep(0.05)
        return pm.price_history_cached(*job, cache_dir=CACHE)

    with ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(one, j): j for j in todo}
        for f in as_completed(futs):
            try:
                empty += len(f.result()) == 0
            except Exception as e:  # noqa: BLE001
                failed += 1
                if failed <= 5:
                    print("failed:", futs[f][0][:12], type(e).__name__, str(e)[:100], flush=True)
            done += 1
            if done % 1000 == 0:
                print(f"{done}/{len(todo)} ({time.time() - t0:.0f}s), empty={empty}, failed={failed}", flush=True)
    print(f"done: {done}, empty histories: {empty}, failed: {failed} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
