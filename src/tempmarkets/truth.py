"""Reconstruct each settlement era's daily max from METAR observations.

Expected observation frame columns:
    valid_utc : tz-aware UTC timestamp
    metar     : raw report text (IEM omits the METAR/SPECI prefix)
    is_speci  : bool (from IEM report_type=4 or a SPECI prefix)
    tmpf      : float F as published by IEM (used for the whole-F eras)
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
import math
from typing import Optional

import pandas as pd

from .metar import c_to_f_half_up, metar_rule_temp_f

ERA_WU, ERA_NWS_TS, ERA_METAR = "wu", "nws_ts", "metar"


def era_for(date: dt.date, eras: list[dict]) -> Optional[str]:
    for e in eras:
        start = pd.Timestamp(e["start"]).date()
        end = pd.Timestamp(e["end"]).date() if e.get("end") else dt.date.max
        if start <= date <= end:
            return e["name"]
    return None


def _local_date(obs: pd.DataFrame, tz: str) -> pd.Series:
    return obs["valid_utc"].dt.tz_convert(tz).dt.date


def daily_max_metar_rule(obs: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Current rule: routine reports only, T-group (else body) C -> F half-up, local day."""
    o = obs.loc[~obs["is_speci"]].copy()
    rt = o["metar"].map(metar_rule_temp_f)
    o["temp_f"] = rt.map(lambda r: r.temp_f)
    o["src"] = rt.map(lambda r: r.source)
    o = o.dropna(subset=["temp_f"])
    o["date"] = _local_date(o, tz)
    g = o.groupby("date")
    out = pd.DataFrame({
        "max_metar": g["temp_f"].max().astype(int),
        "n_routine": g.size(),
        "n_body_fallback": g["src"].apply(lambda s: int((s == "body").sum())),
    })
    return out


def daily_max_continuous_proxy(obs: pd.DataFrame, lst_tz: str) -> pd.DataFrame:
    """CLI-like daily max for stations without a CLI report.

    Over the local-standard-time day: max of (a) 6-hr max groups (1sTTT) whose whole
    6-hour window lies inside the day and (b) every report's tenths-C T-group.
    Converted C -> F half-up. Validated against the real CLI where one exists.
    """
    from .metar import six_hr_max_tenths_c, tgroup_tenths_c

    o = obs.copy()
    lst = o["valid_utc"].dt.tz_convert(lst_tz)
    o["date"] = lst.dt.date
    o["t"] = o["metar"].map(tgroup_tenths_c)
    o["x6"] = o["metar"].map(six_hr_max_tenths_c)
    end = lst.dt.ceil("h")
    start = end - pd.Timedelta(hours=6)
    whole_window = start.dt.date == (end - pd.Timedelta(minutes=1)).dt.date
    o.loc[~whole_window, "x6"] = None
    o["best"] = o[["t", "x6"]].max(axis=1)
    g = o.dropna(subset=["best"]).groupby("date")
    mx = g["best"].max()
    return pd.DataFrame({
        "max_cont_proxy": mx.map(lambda v: c_to_f_half_up(Decimal(int(v)) / Decimal(10))),
        "n_6hr_groups": g["x6"].count(),
    })


def _half_up(x: float) -> int:
    return math.floor(Decimal(str(x)) + Decimal("0.5"))


def daily_max_all_reports(obs: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Approximation for the WU and NWS-timeseries eras: all reports (incl. SPECI),
    whole F. Exact source behaviour is unknown; validated against settled markets in M1."""
    o = obs.dropna(subset=["tmpf"]).copy()
    o["temp_f"] = o["tmpf"].map(_half_up)
    o["date"] = _local_date(o, tz)
    g = o.groupby("date")
    return pd.DataFrame({"max_all": g["temp_f"].max().astype(int), "n_all": g.size()})
