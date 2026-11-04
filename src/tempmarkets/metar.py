"""METAR parsing for settlement-relevant temperature fields.

Only what the market rules and the analysis need: the hourly T-group (tenths C),
the body temperature (whole C), the 6-hr max group, and report type.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

# "T" followed by exactly eight digits: sign(0/1) + 3 digits temp, sign + 3 digits dew point.
_TGROUP = re.compile(r"(?<!\S)T([01])(\d{3})([01])(\d{3})(?!\S)")
# Body temp/dew point, e.g. 26/21, M11/M17, 18/ (missing dew point).
_BODY_TEMP = re.compile(r"(?<!\S)(M?)(\d{2})/(M?\d{2})?(?!\S)")
# 6-hr max group in remarks: 1sTTT.
_SIX_HR_MAX = re.compile(r"(?<!\S)1([01])(\d{3})(?!\S)")


def _split_remarks(metar: str) -> tuple[str, str]:
    body, sep, rmk = metar.partition(" RMK ")
    return body, rmk if sep else ""


def is_speci(raw: str) -> bool:
    """True when the report line begins with SPECI (the rule's definition)."""
    return raw.lstrip().upper().startswith("SPECI")


def tgroup_tenths_c(metar: str) -> Optional[int]:
    """Temperature from the hourly T-group, in tenths of a degree C, or None."""
    _, rmk = _split_remarks(metar)
    m = _TGROUP.search(rmk)
    if not m:
        return None
    val = int(m.group(2))
    return -val if m.group(1) == "1" else val


def body_temp_c(metar: str) -> Optional[int]:
    """Whole-degree C temperature from the report body, or None."""
    body, _ = _split_remarks(metar)
    m = _BODY_TEMP.search(body)
    if not m:
        return None
    val = int(m.group(2))
    return -val if m.group(1) == "M" else val


def six_hr_max_tenths_c(metar: str) -> Optional[int]:
    """6-hr maximum temperature group (1sTTT) in tenths C, or None."""
    _, rmk = _split_remarks(metar)
    m = _SIX_HR_MAX.search(rmk)
    if not m:
        return None
    val = int(m.group(2))
    return -val if m.group(1) == "1" else val


def c_to_f_half_up(c: Decimal) -> int:
    """F = C*9/5+32, rounded to nearest whole F with exact halves rounded up.

    Uses Decimal so 18.3 C -> 64.94 F stays exact (no float drift at .5 boundaries).
    """
    f = c * Decimal(9) / Decimal(5) + Decimal(32)
    return math.floor(f + Decimal("0.5"))


@dataclass(frozen=True)
class RuleTemp:
    temp_f: Optional[int]
    source: Optional[str]  # "tgroup" | "body" | None


def metar_rule_temp_f(metar: str) -> RuleTemp:
    """Per-observation temperature under the current (METAR-era) rule.

    The T-group governs; if absent, the body's whole-degree C; else no temperature.
    """
    t = tgroup_tenths_c(metar)
    if t is not None:
        return RuleTemp(c_to_f_half_up(Decimal(t) / Decimal(10)), "tgroup")
    b = body_temp_c(metar)
    if b is not None:
        return RuleTemp(c_to_f_half_up(Decimal(b)), "body")
    return RuleTemp(None, None)
