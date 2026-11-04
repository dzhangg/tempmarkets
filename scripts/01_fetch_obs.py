"""M1 data pull: IEM METAR (routine + SPECI), IEM CLI, and settled Polymarket events.

Everything is cached under data/raw/. Past years are fetched once; the current
year is re-fetched every run. Sequential with a pause, to be gentle on IEM.
Usage: python scripts/01_fetch_obs.py [--start-year 2020]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import yaml

from tempmarkets.io import iem, polymarket as pm

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2020)
    args = ap.parse_args()
    this_year = dt.date.today().year
    study = {k: v for k, v in CFG["stations"].items() if not v.get("candidate")}

    for icao, st in study.items():
        for year in range(args.start_year, this_year + 1):
            refresh = year == this_year
            for rt in (iem.REPORT_ROUTINE, iem.REPORT_SPECI):
                t0 = time.time()
                df = iem.asos_year(st["iem_id"], year, rt, refresh=refresh)
                print(f"{icao} {year} rt{rt}: {len(df):6d} reports ({time.time() - t0:.1f}s)", flush=True)
                if time.time() - t0 > 0.5:  # only pause after a real download
                    time.sleep(2)
            cli = iem.cli_year(icao, year, refresh=refresh)
            print(f"{icao} {year} CLI: {len(cli)} days", flush=True)

        evs = pm.series_events(st["series_slug"], closed=True)
        out = ROOT / "data" / "raw" / "polymarket" / f"{st['series_slug']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evs))
        print(f"{icao} Polymarket: {len(evs)} settled events", flush=True)


if __name__ == "__main__":
    main()
