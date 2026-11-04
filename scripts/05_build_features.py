"""M2: build the leak-free forecast feature table and summarise raw guidance skill.

Outputs:
  data/processed/features.parquet  station x date x checkpoint, with targets joined
  reports/m2_forecasts.md          bias / MAE / spread-skill of raw NBM and GFS MOS
Usage: python scripts/05_build_features.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from tempmarkets.features import CHECKPOINTS, assert_no_leakage, build_features
from tempmarkets.io import iem

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())
PROC = ROOT / "data" / "processed"


def load_model(icao: str, model: str) -> pd.DataFrame:
    parts = [iem.mos_year(icao, model, int(p.stem.split("_")[-1]))
             for p in sorted((ROOT / "data" / "raw" / "mos").glob(f"{icao}_{model}_*.csv"))]
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    return df.drop_duplicates(["runtime", "ftime"], keep="last")


def summarise(f: pd.DataFrame) -> str:
    out = ["# M2: raw guidance vs. market settlement max (current METAR rule)", "",
           "Target = `max_metar`. Error = forecast − observed. Complete days only.", "",
           "| station | checkpoint | n | NBM bias | NBM MAE | NBM RMSE | GFS MOS MAE | "
           "corr(xnd, abs err) | NBM rounded in right 2°F bucket |",
           "|---|---|---|---|---|---|---|---|---|"]
    for (s, c), g in f.groupby(["station", "checkpoint"]):
        e = g["nbm_txn"] - g["max_metar"]
        eg = (g["gfs_nx"] - g["max_metar"]).dropna()
        hit = (np.floor(g["nbm_txn"].round() / 2) == np.floor(g["max_metar"] / 2)).mean()
        out.append(f"| {s} | {c} | {len(g)} | {e.mean():+.2f} | {e.abs().mean():.2f} | "
                   f"{np.sqrt((e ** 2).mean()):.2f} | {eg.abs().mean():.2f} | "
                   f"{np.corrcoef(g['nbm_xnd'].fillna(g['nbm_xnd'].median()), e.abs())[0, 1]:.2f} | {hit:.1%} |")
    d1 = f[f["checkpoint"] == "d1_1800"].copy()
    d1["err"] = d1["nbm_txn"] - d1["max_metar"]
    out += ["", "## Day-ahead NBM bias by season (°F)", "", "| station | DJF | MAM | JJA | SON |", "|---|---|---|---|---|"]
    for s, g in d1.groupby("station"):
        m = g.groupby("season")["err"].mean()
        out.append(f"| {s} | " + " | ".join(f"{m.get(k, np.nan):+.2f}" for k in ["DJF", "MAM", "JJA", "SON"]) + " |")
    out += ["", "## Day-ahead NBM error by forecast spread (xnd)", "",
            "| xnd (°F) | n | MAE | error SD |", "|---|---|---|---|"]
    d1["xnd_bin"] = pd.cut(d1["nbm_xnd"], [0, 1, 2, 3, 4, 99], labels=["≤1", "2", "3", "4", "≥5"], right=True)
    for b, g in d1.groupby("xnd_bin", observed=True):
        out.append(f"| {b} | {len(g)} | {g['err'].abs().mean():.2f} | {g['err'].std():.2f} |")
    out += ["", "## Run selection (which NBM run each checkpoint used)", ""]
    for c, g in f.groupby("checkpoint"):
        hrs = g["nbs_runtime"].dt.hour.value_counts(normalize=True).sort_index()
        out.append(f"- `{c}`: " + ", ".join(f"{h:02d}Z {v:.0%}" for h, v in hrs.items())
                   + f"; median lead to 15:00 local on D = {g['lead_h'].median():.0f} h")
    return "\n".join(out) + "\n"


def main() -> None:
    truth = pd.read_parquet(PROC / "truth_daily.parquet")
    feats = []
    for icao, st in CFG["stations"].items():
        if st.get("candidate"):
            continue
        nbs, gfs = load_model(icao, "NBS"), load_model(icao, "GFS")
        t = truth[(truth["station"] == icao) & truth["complete"]]
        dates = sorted(t["date"])
        for cp in CHECKPOINTS:
            f = build_features(nbs, gfs, dates, st["tz"], cp)
            f.insert(0, "station", icao)
            feats.append(f)
            print(f"{icao} {cp.name}: {f['nbm_txn'].notna().sum()}/{len(f)} days with NBM, "
                  f"{f.get('gfs_nx', pd.Series(dtype=float)).notna().sum()} with GFS MOS", flush=True)
    f = pd.concat(feats, ignore_index=True)
    assert_no_leakage(f, {k: v["tz"] for k, v in CFG["stations"].items()})
    f = f.merge(truth[["station", "date", "max_metar", "max_all", "cli_high", "max_cont_proxy", "season"]],
                on=["station", "date"], how="left")
    f.to_parquet(PROC / "features.parquet", index=False)
    md = summarise(f.dropna(subset=["nbm_txn", "max_metar"]))
    (ROOT / "reports" / "m2_forecasts.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
