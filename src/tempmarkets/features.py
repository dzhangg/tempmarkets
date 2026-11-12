"""Leak-free forecast features for a target local date at a market checkpoint.

For each target date D and checkpoint (e.g. D-1 18:00 local), we pick the latest run
of each model whose *publication* time (runtime + delay) is at or before the
checkpoint. Every row records runtime, available_at, and checkpoint so leakage
can be asserted downstream.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Conservative publication delays after nominal runtime.
PUBLISH_DELAY = {"NBS": pd.Timedelta(minutes=90), "GFS": pd.Timedelta(hours=4)}


@dataclass(frozen=True)
class Checkpoint:
    name: str
    day_offset: int  # relative to target date D
    hour_local: int

    def utc(self, target: dt.date, tz: str) -> pd.Timestamp:
        d = target + dt.timedelta(days=self.day_offset)
        return pd.Timestamp(dt.datetime(d.year, d.month, d.day, self.hour_local)).tz_localize(tz).tz_convert("UTC")


CHECKPOINTS = (Checkpoint("d1_1800", -1, 18), Checkpoint("d0_0800", 0, 8))


@dataclass(frozen=True)
class FixedCheckpoint:
    """A checkpoint at a fixed instant (live use: 'now')."""
    name: str
    at_utc: pd.Timestamp

    def utc(self, target: dt.date, tz: str) -> pd.Timestamp:
        return self.at_utc


def latest_available_run(runtimes: np.ndarray, delay: pd.Timedelta, cutoff: pd.Timestamp):
    """Latest runtime with runtime + delay <= cutoff (runtimes sorted ascending), or None."""
    i = np.searchsorted(runtimes, (cutoff - delay).to_datetime64(), side="right") - 1
    return pd.Timestamp(runtimes[i], tz="UTC") if i >= 0 else None


def _utc_values(runs: dict) -> np.ndarray:
    """Sorted tz-aware UTC runtimes -> naive UTC datetime64 array for searchsorted."""
    if not runs:
        return np.array([], dtype="datetime64[ns]")
    return pd.DatetimeIndex(sorted(runs)).tz_convert("UTC").tz_localize(None).values


def _max_row_ftime(target: dt.date) -> pd.Timestamp:
    """NBM/MOS daytime max (7am-7pm LST) for US stations is labelled 00Z on D+1."""
    d1 = target + dt.timedelta(days=1)
    return pd.Timestamp(dt.datetime(d1.year, d1.month, d1.day), tz="UTC")


def build_features(nbs: pd.DataFrame, gfs: pd.DataFrame, dates: list[dt.date], tz: str,
                   checkpoint: Checkpoint) -> pd.DataFrame:
    nbs_runs = {k: g.set_index("ftime") for k, g in nbs.groupby("runtime")}
    gfs_runs = {k: g.set_index("ftime") for k, g in gfs.groupby("runtime")} if len(gfs) else {}
    nbs_rt = _utc_values(nbs_runs)
    gfs_rt = _utc_values(gfs_runs)
    rows = []
    for d in dates:
        cp = checkpoint.utc(d, tz)
        fmax = _max_row_ftime(d)
        row = {"date": d, "checkpoint": checkpoint.name, "checkpoint_utc": cp}
        rt = latest_available_run(nbs_rt, PUBLISH_DELAY["NBS"], cp)
        run = nbs_runs.get(rt) if rt is not None else None
        if run is not None and fmax in run.index and pd.notna(run.at[fmax, "txn"]):
            local = run.index.tz_convert(tz)
            day = run[local.date == d]
            daytime = day[(local[local.date == d].hour >= 9) & (local[local.date == d].hour <= 18)]
            row.update({
                "nbs_runtime": rt, "nbs_available_at": rt + PUBLISH_DELAY["NBS"],
                "lead_h": (pd.Timestamp(dt.datetime(d.year, d.month, d.day, 15)).tz_localize(tz)
                           .tz_convert("UTC") - rt) / pd.Timedelta(hours=1),
                "nbm_txn": float(run.at[fmax, "txn"]),
                "nbm_xnd": float(run.at[fmax, "xnd"]) if pd.notna(run.at[fmax, "xnd"]) else np.nan,
                "nbm_p12": float(run.at[fmax, "p12"]) if pd.notna(run.at[fmax, "p12"]) else np.nan,
                "nbm_tmp_max": float(day["tmp"].max()) if len(day) else np.nan,
                "nbm_n_tmp": int(day["tmp"].notna().sum()),
                "nbm_sky_day": float(daytime["sky"].mean()) if len(daytime) else np.nan,
                "nbm_dpt_day": float(daytime["dpt"].mean()) if len(daytime) else np.nan,
                "nbm_wsp_day": float(daytime["wsp"].mean()) if len(daytime) else np.nan,
            })
        grt = latest_available_run(gfs_rt, PUBLISH_DELAY["GFS"], cp) if len(gfs_rt) else None
        grun = gfs_runs.get(grt) if grt is not None else None
        if grun is not None and fmax in grun.index and pd.notna(grun.at[fmax, "n_x"]):
            row.update({"gfs_runtime": grt, "gfs_available_at": grt + PUBLISH_DELAY["GFS"],
                        "gfs_nx": float(grun.at[fmax, "n_x"])})
        rows.append(row)
    return pd.DataFrame(rows)


def assert_no_leakage(df: pd.DataFrame, tz_by_station: dict[str, str]) -> None:
    """Every forecast was published at/before its checkpoint; day-ahead checkpoints
    are before the target day starts locally."""
    for col in ("nbs_available_at", "gfs_available_at"):
        if col in df:
            ok = df[col].isna() | (df[col] <= df["checkpoint_utc"])
            assert ok.all(), f"{col} after checkpoint in {(~ok).sum()} rows"
    d1 = df[df["checkpoint"] == "d1_1800"]
    for st, g in d1.groupby("station"):
        start = pd.to_datetime(g["date"]).dt.tz_localize(tz_by_station[st]).dt.tz_convert("UTC")
        assert (g["checkpoint_utc"].values < start.values).all(), f"{st}: day-ahead checkpoint not before D"
