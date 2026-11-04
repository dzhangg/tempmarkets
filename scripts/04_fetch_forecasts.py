"""M2 data pull: archived NBM (NBS) and GFS MOS runs from IEM, one CSV per station-year.

Paced to respect IEM's rate limit. Past years are cached; the current year is re-fetched.
Usage: python scripts/04_fetch_forecasts.py [--start-year 2020] [--models NBS GFS]
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
from pathlib import Path

import yaml

from tempmarkets.io import iem

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2020)
    ap.add_argument("--models", nargs="+", default=["NBS", "GFS"])
    args = ap.parse_args()
    this_year = dt.date.today().year
    for icao, st in CFG["stations"].items():
        if st.get("candidate"):
            continue
        for model in args.models:
            for year in range(args.start_year, this_year + 1):
                t0 = time.time()
                df = iem.mos_year(icao, model, year, refresh=(year == this_year))
                runs = df["runtime"].dt.hour.value_counts().sort_index().to_dict()
                print(f"{icao} {model} {year}: {len(df):6d} rows, {df['runtime'].nunique()} runs "
                      f"{runs} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
