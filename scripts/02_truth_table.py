"""M1: build the daily truth table and validate it against settled Polymarket events.

Outputs:
  data/processed/truth_daily.parquet   one row per station x local date
  data/processed/market_validation.parquet   one row per settled event
  reports/m1_validation.md              match rates + mismatch list
Usage: python scripts/02_truth_table.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import yaml

from tempmarkets.buckets import bucket_for, parse_bucket
from tempmarkets.io import iem, polymarket as pm
from tempmarkets.truth import (daily_max_all_reports, daily_max_continuous_proxy,
                               daily_max_metar_rule, era_for)

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())
PROC = ROOT / "data" / "processed"
LST = {"America/New_York": "Etc/GMT+5", "America/Chicago": "Etc/GMT+6"}  # fixed standard time


def load_obs(iem_id: str) -> pd.DataFrame:
    parts = []
    for p in sorted((ROOT / "data" / "raw" / "asos").glob(f"{iem_id}_*_rt*.csv")):
        year, rt = int(p.stem.split("_")[1]), int(p.stem.split("_rt")[1])
        parts.append(iem.asos_year(iem_id, year, rt))
    obs = pd.concat(parts, ignore_index=True)
    # IEM year files overlap at Jan 1 00:00; drop exact duplicates.
    return obs.drop_duplicates(subset=["valid_utc", "metar"]).sort_values("valid_utc")


def load_cli(icao: str) -> pd.DataFrame:
    parts = [pd.DataFrame(json.loads(p.read_text()).get("results", []))
             for p in sorted((ROOT / "data" / "raw" / "cli").glob(f"{icao}_*.json"))]
    cli = pd.concat(parts, ignore_index=True)
    if cli.empty:  # e.g. KDAL: NWS issues no CLI for Love Field
        return pd.DataFrame({"cli_high": pd.Series(dtype=float)}, index=pd.Index([], name="date"))
    cli["date"] = pd.to_datetime(cli["valid"]).dt.date
    cli = cli.drop_duplicates("date", keep="last").set_index("date")
    return cli[["high"]].rename(columns={"high": "cli_high"}).apply(pd.to_numeric, errors="coerce")


def truth_for_station(icao: str, st: dict) -> pd.DataFrame:
    obs = load_obs(st["iem_id"])
    tz = st["tz"]
    metar = daily_max_metar_rule(obs, tz)
    allr = daily_max_all_reports(obs, tz)
    routine_whole = daily_max_all_reports(obs.loc[~obs["is_speci"]], tz).rename(
        columns={"max_all": "max_routine_wholeF", "n_all": "n_routine_all"})
    lst = daily_max_all_reports(obs, LST[tz]).rename(columns={"max_all": "max_all_lstday", "n_all": "n_lst"})
    cont = daily_max_continuous_proxy(obs, LST[tz])
    df = (metar.join(allr, how="outer").join(routine_whole, how="outer")
          .join(lst, how="outer").join(cont, how="outer"))
    df = df.join(load_cli(icao), how="left")
    df.index.name = "date"
    df = df.reset_index()
    df.insert(0, "station", icao)
    df["season"] = pd.to_datetime(df["date"]).dt.month.map(
        {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
         6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"})
    # Partial days (first/last day of the archive, outages) get flagged, not dropped.
    df["complete"] = df["n_routine"].fillna(0) >= 20
    return df


def validate(icao: str, st: dict, truth: pd.DataFrame) -> pd.DataFrame:
    evs = json.loads((ROOT / "data" / "raw" / "polymarket" / f"{st['series_slug']}.json").read_text())
    t = truth.set_index("date")
    rows = []
    for ev in evs:
        if pm.is_superseded(ev):
            continue
        date = pm.observation_date(ev)
        end = dt.date.fromisoformat(ev["endDate"][:10])
        assert abs((end - date).days) <= 1, (ev["slug"], date, end)
        win = pm.winning_label(ev)
        labels = [b.label for b in pm.bucket_markets(ev)]
        try:
            buckets = [parse_bucket(x) for x in labels]
        except ValueError:
            buckets = []
        era = era_for(date, CFG["eras"])
        row = {"station": icao, "date": date, "slug": ev["slug"], "era": era, "winner": win,
               "unit": buckets[0].unit if buckets else None}
        for col in ("max_metar", "max_all", "max_routine_wholeF"):
            v = t[col].get(date) if date in t.index else None
            b = bucket_for(int(v), buckets) if (v is not None and pd.notna(v) and buckets) else None
            row[col] = v
            row[f"{col}_bucket"] = b.label if b else None
            row[f"{col}_match"] = (b is not None and win is not None and b.label == win)
        rows.append(row)
    return pd.DataFrame(rows)


def report(val: pd.DataFrame) -> str:
    # The rule we expect to match in each era.
    expected = {"wu": "max_all", "nws_ts": "max_all", "metar": "max_metar"}
    v = val.dropna(subset=["winner"]).copy()
    lines = ["# M1 validation: rebuilt daily max vs. settled Polymarket winners", "",
             f"Generated {dt.date.today()}. Settled events with a single winner: {len(v)}.", "",
             "| station | era | n | all-reports °F | routine-only °F | METAR rule |",
             "|---|---|---|---|---|---|"]
    for (s, e), g in v.groupby(["station", "era"]):
        lines.append(f"| {s} | {e} | {len(g)} | {g['max_all_match'].mean():.1%} | "
                     f"{g['max_routine_wholeF_match'].mean():.1%} | {g['max_metar_match'].mean():.1%} |")
    lines += ["", "Expected rule per era: wu and nws_ts → all-reports; metar → METAR rule.", "",
              "## Mismatches under the expected rule", "",
              "| station | date | era | winner | rebuilt | value |", "|---|---|---|---|---|---|"]
    for _, r in v.iterrows():
        col = expected.get(r["era"])
        if col and not r[f"{col}_match"]:
            lines.append(f"| {r['station']} | {r['date']} | {r['era']} | {r['winner']} | "
                         f"{r[f'{col}_bucket']} | {r[col]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    study = {k: v for k, v in CFG["stations"].items() if not v.get("candidate")}
    truths, vals = [], []
    for icao, st in study.items():
        t = truth_for_station(icao, st)
        truths.append(t)
        vals.append(validate(icao, st, t))
        print(f"{icao}: {len(t)} days, {t['complete'].sum()} complete", flush=True)
    truth = pd.concat(truths, ignore_index=True)
    val = pd.concat(vals, ignore_index=True)
    truth.to_parquet(PROC / "truth_daily.parquet", index=False)
    val.to_parquet(PROC / "market_validation.parquet", index=False)
    (ROOT / "reports").mkdir(exist_ok=True)
    md = report(val)
    (ROOT / "reports" / "m1_validation.md").write_text(md)
    print(md[:3000])


if __name__ == "__main__":
    main()
