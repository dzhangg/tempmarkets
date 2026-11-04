"""M0: verify every data source still works, and summarise market history per station.

Exits non-zero if any required check fails. Read-only (GET requests only).
Usage: python scripts/00_probe_sources.py [--skip-markets]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

from tempmarkets.buckets import check_partition, parse_bucket
from tempmarkets.io import iem, polymarket as pm
from tempmarkets.io.http import get

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())

results: list[tuple[str, bool, bool, str]] = []  # name, required, ok, detail


def check(name: str, required: bool = True):
    def deco(fn):
        try:
            detail = fn()
            results.append((name, required, True, detail or ""))
        except Exception as e:  # noqa: BLE001 - we want to report any failure
            results.append((name, required, False, f"{type(e).__name__}: {e}"[:200]))
        return fn
    return deco


@check("IEM ASOS routine+SPECI with T-group")
def _():
    df = iem.asos_year("MIA", 2025, iem.REPORT_ROUTINE, cache=False).head(500)
    sp = iem.asos_year("MIA", 2025, iem.REPORT_SPECI, cache=False)
    has_t = df["metar"].str.contains(r" T[01]\d{7}", regex=True).mean()
    assert has_t > 0.9, f"only {has_t:.0%} routine reports carry a T-group"
    return f"routine T-group share {has_t:.0%}; {len(sp)} SPECI in 2025"


@check("IEM CLI daily high")
def _():
    df = iem.cli_year("KMIA", 2025)
    assert {"valid", "high"} <= set(df.columns) and len(df) > 300
    return f"{len(df)} days in 2025"


@check("IEM NBM (NBS) txn + xnd")
def _():
    df = iem.mos_run("KMIA", "NBS", "2025-07-01T13:00Z")
    assert df["txn"].notna().any() and df["xnd"].notna().any()
    return f"{len(df)} rows; txn/xnd present"


@check("IEM NBS archive depth (2020)")
def _():
    assert len(iem.mos_run("KLGA", "NBS", "2020-06-01T13:00Z")) > 0
    return "2020 runs available"


@check("IEM GFS MOS n_x")
def _():
    df = iem.mos_run("KLGA", "GFS", "2023-01-10T12:00Z")
    assert df["n_x"].notna().any()
    return f"{df['n_x'].notna().sum()} max/min rows"


@check("IEM NBE (extended)", required=False)
def _():
    df = iem.mos_run("KMIA", "NBE", "2025-07-01T01:00Z")
    assert len(df) > 0
    return "01Z run present (00/12Z absent in earlier probe)"


@check("Open-Meteo previous-runs day1", required=False)
def _():
    js = get("https://previous-runs-api.open-meteo.com/v1/forecast", {
        "latitude": 25.788, "longitude": -80.317, "start_date": "2025-07-01", "end_date": "2025-07-01",
        "hourly": "temperature_2m_previous_day1", "temperature_unit": "fahrenheit",
        "timezone": "America/New_York"}).json()
    vals = [v for v in js["hourly"]["temperature_2m_previous_day1"] if v is not None]
    assert len(vals) >= 20
    return f"{len(vals)} hourly values"


@check("AviationWeather.gov METAR (current settlement source)")
def _():
    txt = get("https://aviationweather.gov/api/data/metar",
              {"ids": "KMIA", "format": "raw", "hours": 3}).text
    lines = [l for l in txt.splitlines() if l.strip()]
    assert lines and all(l.startswith(("METAR", "SPECI")) for l in lines)
    return f"{len(lines)} reports, METAR/SPECI labelled"


@check("Polymarket CLOB order book (live)")
def _():
    evs = pm.series_events("miami-daily-weather", closed=False)
    assert evs, "no open Miami events"
    b = pm.bucket_markets(evs[0])
    book = pm.order_book(b[len(b) // 2].yes_token)
    assert "bids" in book and "asks" in book
    return f"{evs[0]['slug']}: {len(book['bids'])} bids / {len(book['asks'])} asks"


def era_of(ev: dict) -> str:
    text = (ev.get("resolutionSource") or "") + " " + (ev.get("description") or "")
    if "aviationweather.gov" in text:
        return "metar"
    if "wrh/timeseries" in text:
        return "nws_ts"
    if "wunderground" in text.lower():
        return "wu"
    return "?"


def market_summary(icao: str, st: dict) -> str:
    evs = pm.series_events(st["series_slug"], closed=True)
    if not evs:
        raise RuntimeError(f"series {st['series_slug']!r} returned no settled events")
    stations = Counter(m.group(1) for e in evs
                       if (m := re.search(r"\(([A-Z]{4})\)", e.get("description", ""))))
    eras = Counter(era_of(e) for e in evs)
    # Spot-check the newest event's buckets tile the integers and it has a winner.
    last = evs[-1]
    bs = [parse_bucket(b.label) for b in pm.bucket_markets(last)]
    check_partition(bs)
    winner = pm.winning_label(last)
    # Price history for one bucket of the newest settled event.
    end = int(dt.datetime.fromisoformat(last["endDate"].replace("Z", "+00:00")).timestamp())
    hist = pm.price_history(pm.bucket_markets(last)[0].yes_token, end - 4 * 86400, end + 86400)
    other = {k: v for k, v in stations.items() if k != icao}
    warn = f" ⚠ other stations named: {dict(other)}" if other else ""
    return (f"{len(evs)} settled, {evs[0]['endDate'][:10]} → {evs[-1]['endDate'][:10]}; "
            f"eras {dict(eras)}; last winner {winner!r}; {len(hist)} hourly prices{warn}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-markets", action="store_true")
    args = ap.parse_args()
    if not args.skip_markets:
        for icao, st in CFG["stations"].items():
            check(f"Polymarket history {icao}", required=not st.get("candidate"))(
                lambda icao=icao, st=st: market_summary(icao, st))
            time.sleep(0.5)

    width = max(len(r[0]) for r in results)
    failed_required = False
    for name, required, ok, detail in results:
        tag = "PASS" if ok else ("FAIL" if required else "WARN")
        failed_required |= required and not ok
        print(f"[{tag}] {name.ljust(width)}  {detail}")
    return 1 if failed_required else 0


if __name__ == "__main__":
    sys.exit(main())
