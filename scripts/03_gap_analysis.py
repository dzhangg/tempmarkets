"""M1: quantify the gap between the NWS CLI daily max and the market's settlement max.

Decomposes CLI - market_max (current METAR rule) into:
  window : CLI uses the local-standard-time day (1am-1am clock time during DST)
  speci  : market excludes SPECI reports
  sensor : CLI uses the continuous record; hourly reports can miss the peak
Output: reports/m1_gaps.md
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def dist_table(s: pd.Series, lo: int = -2, hi: int = 4) -> str:
    c = s.clip(lo, hi).value_counts(normalize=True).reindex(range(lo, hi + 1), fill_value=0)
    head = "| " + " | ".join(f"{'≤' if k == lo else '≥' if k == hi else ''}{k:+d}" for k in c.index) + " |"
    return head + "\n|" + "---|" * len(c) + "\n| " + " | ".join(f"{v:.1%}" for v in c.values) + " |"


def main() -> None:
    t = pd.read_parquet(ROOT / "data" / "processed" / "truth_daily.parquet")
    t = t[t["complete"]].copy()
    t["date"] = pd.to_datetime(t["date"])
    t["dst"] = t["date"].dt.tz_localize("America/New_York", nonexistent="shift_forward",
                                        ambiguous=False).map(lambda d: bool(d.dst()))
    # Same 2°F bucket grid as current markets (even lower bound: 82-83, 84-85, ...).
    bucket = lambda x: np.floor(x / 2)  # noqa: E731

    out = ["# M1: CLI daily max vs. market settlement max", "",
           f"Complete station-days 2020→2026-11: {len(t)}. Market max = current rule "
           "(routine METAR T-group, °C→°F half-up, local calendar day).", ""]

    c = t.dropna(subset=["cli_high"]).copy()
    c["gap"] = c["cli_high"] - c["max_metar"]
    c["bucket_diff"] = bucket(c["cli_high"]) != bucket(c["max_metar"])
    out += ["## CLI − market max (KMIA, KLGA, KATL; KDAL has no CLI)", "",
            "| station | n | mean °F | CLI higher | CLI lower | different 2°F bucket |", "|---|---|---|---|---|---|"]
    for s, g in c.groupby("station"):
        out.append(f"| {s} | {len(g)} | {g['gap'].mean():+.2f} | {(g['gap'] > 0).mean():.1%} | "
                   f"{(g['gap'] < 0).mean():.1%} | {g['bucket_diff'].mean():.1%} |")
    out += ["", "Distribution of CLI − market max, all three stations:", "", dist_table(c["gap"]), "",
            "### By season", "", "| station | DJF | MAM | JJA | SON |", "|---|---|---|---|---|"]
    for s, g in c.groupby("station"):
        m = g.groupby("season")["gap"].mean()
        out.append(f"| {s} | " + " | ".join(f"{m.get(k, np.nan):+.2f}" for k in ["DJF", "MAM", "JJA", "SON"]) + " |")

    # Decomposition (each step changes one thing).
    c["window"] = c["max_all_lstday"] - c["max_all"]          # LST day vs local day (all reports)
    c["speci"] = c["max_all"] - c["max_metar"]                # SPECI included vs excluded (+rounding path)
    c["sensor"] = c["cli_high"] - c["max_all_lstday"]         # continuous record vs reports
    out += ["", "### Decomposition: CLI − market = window + SPECI + sensor", "",
            "| station | DST? | window | SPECI | sensor | total |", "|---|---|---|---|---|---|"]
    for (s, d), g in c.groupby(["station", "dst"]):
        out.append(f"| {s} | {'DST' if d else 'std'} | {g['window'].mean():+.2f} | {g['speci'].mean():+.2f} | "
                   f"{g['sensor'].mean():+.2f} | {g['gap'].mean():+.2f} |")
    out += ["", "- **window**: max over the standard-time day minus max over the clock day. It is zero "
            "outside DST by construction, and during DST it measures the 00–01 vs. next-day 00–01 swap.",
            "- **SPECI**: what special reports add on top of routine ones (the market ignores them now; "
            "WU-era markets included them).",
            "- **sensor**: what the continuous record catches between reports (peaks between hourly obs, "
            "and whole-°F vs. tenths-°C rounding paths).", ""]

    # How often SPECI alone moves the settlement bucket (relevant to era changes).
    a = t.copy()
    a["speci_bucket"] = bucket(a["max_all"]) != bucket(a["max_metar"])
    out += ["## SPECI effect on the settlement bucket (all four stations)", "",
            "| station | days SPECI raises max | days it changes the 2°F bucket |", "|---|---|---|"]
    for s, g in a.groupby("station"):
        out.append(f"| {s} | {(g['max_all'] > g['max_metar']).mean():.1%} | {g['speci_bucket'].mean():.1%} |")

    # Continuous proxy (for KDAL) validated where CLI exists.
    p = c.dropna(subset=["max_cont_proxy"])
    d = p["cli_high"] - p["max_cont_proxy"]
    kd = t[t["station"] == "KDAL"]
    out += ["", "## CLI proxy for KDAL (no CLI issued for Love Field)", "",
            "Proxy = max of 6-hr max groups fully inside the standard-time day and every tenths-°C T-group.",
            f"Where CLI exists it matches exactly on {(d == 0).mean():.1%} of days, within 1°F on "
            f"{(d.abs() <= 1).mean():.1%} (mean CLI − proxy {d.mean():+.2f}°F).", "",
            dist_table(d, -2, 2), "",
            f"KDAL proxy − market max: mean {(kd['max_cont_proxy'] - kd['max_metar']).mean():+.2f}°F, "
            f"different 2°F bucket on {(bucket(kd['max_cont_proxy']) != bucket(kd['max_metar'])).mean():.1%} of days.", ""]

    (ROOT / "reports" / "m1_gaps.md").write_text("\n".join(out))
    print("\n".join(out))


if __name__ == "__main__":
    main()
