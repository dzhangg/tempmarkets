from decimal import Decimal
import math

import pandas as pd
import pytest

from tempmarkets.buckets import bucket_for, check_partition, parse_bucket
from tempmarkets.metar import (body_temp_c, c_to_f_half_up, is_speci, metar_rule_temp_f,
                               six_hr_max_tenths_c, tgroup_tenths_c)
from tempmarkets.truth import daily_max_all_reports, daily_max_metar_rule, era_for

# Real reports seen on aviationweather.gov / IEM for KMIA, 2025-07-01 and 2026-11-03.
M1 = ("KMIA 032353Z 06006KT 10SM TS FEW025CB SCT048 BKN250 26/23 A2997 RMK AO2 RAE41 TSB38 "
      "SLP148 FRQ LTGICCC NW-NE TS NW-NE MOV W P0000 60000 T02560228 10306 20250 53007 $")
SPECI_LINE = "SPECI KMIA 040010Z 08008KT 10SM SCT025 26/23 A2997 RMK AO2 T02560233 $"


@pytest.mark.parametrize("c,f", [
    (Decimal("18.3"), 65),   # 64.94 -> 65 (from rule text)
    (Decimal("17.8"), 64),   # 64.04 -> 64
    (Decimal("19"), 66),     # 66.2  -> 66
    (Decimal("-22.5"), -8),  # exactly -8.5 -> rounds up to -8
    (Decimal("25.0"), 77),   # exactly 77.0
    (Decimal("30.6"), 87),   # 87.08
])
def test_half_up_conversion(c, f):
    assert c_to_f_half_up(c) == f


def test_tgroup_and_body_and_6hr():
    assert tgroup_tenths_c(M1) == 256
    assert body_temp_c(M1) == 26
    assert six_hr_max_tenths_c(M1) == 306
    assert tgroup_tenths_c("KXXX 010000Z 00000KT M11/M17 A3000 RMK AO2 T11071172") == -107
    assert body_temp_c("KXXX 010000Z 00000KT M11/M17 A3000") == -11
    assert body_temp_c("KXXX 010000Z 00000KT 18/ A3000") == 18


def test_tgroup_requires_exactly_eight_digits():
    assert tgroup_tenths_c("KXXX 010000Z 18/12 A3000 RMK T0139013") is None
    assert tgroup_tenths_c("KXXX 010000Z 18/12 A3000 RMK T013901331") is None


def test_rule_temp_fallback():
    assert metar_rule_temp_f(M1).temp_f == 78 and metar_rule_temp_f(M1).source == "tgroup"
    no_t = "KXXX 010000Z 00000KT 18/12 A3000 RMK AO2"
    r = metar_rule_temp_f(no_t)
    assert (r.temp_f, r.source) == (64, "body")  # 18 C = 64.4 F
    assert metar_rule_temp_f("KXXX 010000Z 00000KT A3000 RMK AO2").temp_f is None


def test_is_speci():
    assert is_speci(SPECI_LINE) and not is_speci("METAR " + M1) and not is_speci(M1)


def _obs(rows):
    df = pd.DataFrame(rows, columns=["valid_utc", "metar", "is_speci", "tmpf"])
    df["valid_utc"] = pd.to_datetime(df["valid_utc"], utc=True)
    return df


def test_daily_max_excludes_speci_and_uses_local_day():
    obs = _obs([
        # 2025-07-01 18:53Z = 14:53 EDT on Jul 1: routine, 31.1 C -> 88 F
        ("2025-07-01 18:53", "KMIA 011853Z 18/12 A3000 RMK T03110200", False, 88.0),
        # SPECI hotter, same day: excluded under METAR rule, included in all-reports max
        ("2025-07-01 19:10", "KMIA 011910Z 18/12 A3000 RMK T03220200", True, 90.0),
        # 2025-07-02 03:53Z = 23:53 EDT Jul 1 -> still Jul 1 locally
        ("2025-07-02 03:53", "KMIA 020353Z 18/12 A3000 RMK T03330200", False, 92.0),
        # 2025-07-02 04:53Z = 00:53 EDT Jul 2
        ("2025-07-02 04:53", "KMIA 020453Z 18/12 A3000 RMK T02000200", False, 68.0),
    ])
    m = daily_max_metar_rule(obs, "America/New_York")
    import datetime as dt
    assert m.loc[dt.date(2025, 7, 1), "max_metar"] == 92  # 33.3 C = 91.94 -> 92
    assert m.loc[dt.date(2025, 7, 2), "max_metar"] == 68
    a = daily_max_all_reports(obs, "America/New_York")
    assert a.loc[dt.date(2025, 7, 1), "max_all"] == 92


def test_buckets():
    labels = ["73°F or below", "74-75°F", "76-77°F", "78-79°F", "80°F or higher"]
    bs = [parse_bucket(x) for x in labels]
    check_partition(bs)
    assert bucket_for(73, bs).label == "73°F or below"
    assert bucket_for(-40, bs).label == "73°F or below"
    assert bucket_for(77, bs).label == "76-77°F"
    assert bucket_for(200, bs).label == "80°F or higher"
    assert parse_bucket("12°C").lo == 12 and parse_bucket("12°C").unit == "C"
    assert math.isinf(parse_bucket("5°C or below").lo)


def test_era_for():
    eras = [{"name": "wu", "start": "2025-01-01", "end": "2026-08-22"},
            {"name": "nws_ts", "start": "2026-08-23", "end": "2026-10-22"},
            {"name": "metar", "start": "2026-10-23", "end": None}]
    import datetime as dt
    assert era_for(dt.date(2026, 8, 22), eras) == "wu"
    assert era_for(dt.date(2026, 8, 23), eras) == "nws_ts"
    assert era_for(dt.date(2026, 11, 3), eras) == "metar"


def test_bucket_label_variants():
    assert parse_bucket("81–82°F").lo == 81           # en dash
    assert parse_bucket("54 °F or below").hi == 54     # stray space
    b = [parse_bucket(x) for x in ["<29°F", "30-31°F", "32°F or higher"]]
    check_partition(b)
    assert bucket_for(29, b).label == "<29°F"


def test_observation_date_parsing():
    import datetime as dt
    from tempmarkets.io.polymarket import is_superseded, observation_date
    assert observation_date({"eventDate": "2026-11-02"}) == dt.date(2026, 11, 2)
    assert observation_date({"description": "in degrees Fahrenheit on 22 Jan '26."}) == dt.date(2026, 1, 22)
    assert observation_date({"description": "Fahrenheit on January 22, 2025."}) == dt.date(2025, 1, 22)
    assert observation_date({"description": "Fahrenheit on 6 Dec 2025."}) == dt.date(2025, 12, 6)
    assert is_superseded({"slug": "arch-highest-temperature-in-miami-on-may-19-2026"})
