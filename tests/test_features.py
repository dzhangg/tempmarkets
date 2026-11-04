import datetime as dt

import numpy as np
import pandas as pd
import pytest

from tempmarkets.features import (CHECKPOINTS, Checkpoint, PUBLISH_DELAY, assert_no_leakage,
                                  build_features, latest_available_run)

TZ = "America/New_York"


def _nbs(runtimes, target=dt.date(2025, 7, 2), txn_by_run=None):
    """Synthetic NBS: each run has 3-hourly rows over two days and a txn at D+1 00Z."""
    rows = []
    for rt in runtimes:
        rt = pd.Timestamp(rt, tz="UTC")
        for h in range(0, 72, 3):
            f = rt.floor("D") + pd.Timedelta(hours=h)
            rows.append({"runtime": rt, "ftime": f, "tmp": 80 + (h % 24) / 3, "sky": 50, "dpt": 70, "wsp": 8,
                         "txn": np.nan, "xnd": np.nan, "p12": np.nan})
        fmax = pd.Timestamp(target + dt.timedelta(days=1), tz="UTC")
        rows.append({"runtime": rt, "ftime": fmax, "tmp": 82, "sky": 50, "dpt": 70, "wsp": 8,
                     "txn": (txn_by_run or {}).get(rt.hour, 90.0), "xnd": 2.0, "p12": 10.0})
    df = pd.DataFrame(rows).drop_duplicates(["runtime", "ftime"], keep="last")
    return df


def test_latest_available_run_respects_publish_delay():
    rts = np.array(pd.to_datetime(["2025-07-01 13:00", "2025-07-01 19:00"]).values)
    cutoff = pd.Timestamp("2025-07-01 20:29", tz="UTC")
    assert latest_available_run(rts, PUBLISH_DELAY["NBS"], cutoff).hour == 13  # 19Z not out until 20:30
    cutoff = pd.Timestamp("2025-07-01 20:30", tz="UTC")
    assert latest_available_run(rts, PUBLISH_DELAY["NBS"], cutoff).hour == 19
    assert latest_available_run(rts, PUBLISH_DELAY["NBS"], pd.Timestamp("2025-07-01 00:00", tz="UTC")) is None


def test_checkpoint_utc_handles_dst():
    cp = Checkpoint("d1_1800", -1, 18)
    assert cp.utc(dt.date(2025, 7, 2), TZ) == pd.Timestamp("2025-07-01 22:00", tz="UTC")   # EDT
    assert cp.utc(dt.date(2025, 1, 2), TZ) == pd.Timestamp("2025-01-01 23:00", tz="UTC")   # EST


def test_day_ahead_uses_only_published_run():
    target = dt.date(2025, 7, 2)
    # A 19Z D-1 run (published 20:30Z < 22:00Z checkpoint) and a later 01Z D run that must be ignored.
    nbs = _nbs(["2025-07-01 13:00", "2025-07-01 19:00", "2025-07-02 01:00"], target,
               txn_by_run={13: 88.0, 19: 91.0, 1: 99.0})
    f = build_features(nbs, pd.DataFrame(), [target], TZ, CHECKPOINTS[0])
    assert f.loc[0, "nbm_txn"] == 91.0
    assert f.loc[0, "nbs_runtime"] == pd.Timestamp("2025-07-01 19:00", tz="UTC")
    f["station"] = "KMIA"
    assert_no_leakage(f, {"KMIA": TZ})


def test_leakage_guard_trips():
    bad = pd.DataFrame({"station": ["KMIA"], "date": [dt.date(2025, 7, 2)], "checkpoint": ["d1_1800"],
                        "checkpoint_utc": [pd.Timestamp("2025-07-01 22:00", tz="UTC")],
                        "nbs_available_at": [pd.Timestamp("2025-07-01 23:00", tz="UTC")]})
    with pytest.raises(AssertionError):
        assert_no_leakage(bad, {"KMIA": TZ})
