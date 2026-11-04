"""Iowa Environmental Mesonet: ASOS/METAR archive, CLI reports, MOS/NBM archive."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from .http import get

IEM = "https://mesonet.agron.iastate.edu"
RAW = Path(__file__).resolve().parents[3] / "data" / "raw"

# IEM report_type codes: 3 = routine (METAR), 4 = special (SPECI).
REPORT_ROUTINE, REPORT_SPECI = 3, 4


def asos_year(iem_id: str, year: int, report_type: int, cache: bool = True,
              refresh: bool = False) -> pd.DataFrame:
    """One station-year of reports of one type, timestamps in UTC.
    `refresh` re-downloads even if cached (use for the current, incomplete year)."""
    path = RAW / "asos" / f"{iem_id}_{year}_rt{report_type}.csv"
    if cache and path.exists() and not refresh:
        text = path.read_text()
    else:
        params = {
            "station": iem_id, "data": ["tmpf", "metar"], "tz": "Etc/UTC",
            "year1": year, "month1": 1, "day1": 1, "year2": year + 1, "month2": 1, "day2": 1,
            "format": "onlycomma", "latlon": "no", "missing": "M", "trace": "T",
            "report_type": report_type,
        }
        text = get(f"{IEM}/cgi-bin/request/asos.py", params, timeout=300).text
        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    df = pd.read_csv(io.StringIO(text), na_values=["M"])
    df["valid_utc"] = pd.to_datetime(df["valid"], utc=True)
    df["is_speci"] = report_type == REPORT_SPECI
    return df[["station", "valid_utc", "tmpf", "metar", "is_speci"]]


def cli_year(icao: str, year: int, refresh: bool = False) -> pd.DataFrame:
    path = RAW / "cli" / f"{icao}_{year}.json"
    if path.exists() and not refresh:
        text = path.read_text()
    else:
        text = get(f"{IEM}/json/cli.py", {"station": icao, "year": year}).text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return pd.DataFrame(json.loads(text).get("results", []))


def mos_year(icao: str, model: str, year: int, refresh: bool = False,
             pause_s: float = 8.0, max_tries: int = 6) -> pd.DataFrame:
    """All archived runs of one MOS/NBM model for one station-year (bulk CSV).

    IEM rate-limits this endpoint ("Too many requests ... slow down"), returned
    as a 200 with a text body, so we detect that and back off. Times are UTC.
    """
    import time

    path = RAW / "mos" / f"{icao}_{model}_{year}.csv"
    if path.exists() and not refresh:
        text = path.read_text()
    else:
        params = {"station": icao, "model": model, "format": "csv",
                  "sts": f"{year}-01-01T00:00Z", "ets": f"{year + 1}-01-01T00:00Z"}
        for attempt in range(max_tries):
            text = get(f"{IEM}/cgi-bin/request/mos.py", params, timeout=600).text
            if text.startswith("runtime"):
                break
            time.sleep(pause_s * 2 ** attempt)
        else:
            raise RuntimeError(f"IEM MOS {icao} {model} {year}: {text[:120]!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        time.sleep(pause_s)
    df = pd.read_csv(io.StringIO(text), low_memory=False)
    df["runtime"] = pd.to_datetime(df["runtime"], utc=True)
    df["ftime"] = pd.to_datetime(df["ftime"], utc=True)
    return df


def mos_run(icao: str, model: str, runtime_utc: str) -> pd.DataFrame:
    """One MOS/NBM run, e.g. model='NBS', runtime_utc='2025-07-01T13:00Z'."""
    js = get(f"{IEM}/api/1/mos.json", {"station": icao, "model": model, "runtime": runtime_utc}).json()
    return pd.DataFrame(js.get("data", []))
