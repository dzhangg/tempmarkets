"""Market bucket labels <-> integer temperature ranges."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Sequence

_RANGE = re.compile(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*°?\s*([FC])\s*$")
_BELOW = re.compile(r"^\s*(-?\d+)\s*°?\s*([FC])\s+or\s+(below|lower)\s*$", re.I)
_ABOVE = re.compile(r"^\s*(-?\d+)\s*°?\s*([FC])\s+or\s+(higher|above)\s*$", re.I)
_SINGLE = re.compile(r"^\s*(-?\d+)\s*°?\s*([FC])\s*$")


@dataclass(frozen=True)
class Bucket:
    label: str
    lo: float  # inclusive integer bound, -inf for open lower tail
    hi: float  # inclusive integer bound, +inf for open upper tail
    unit: str  # "F" or "C"

    def contains(self, value: int) -> bool:
        return self.lo <= value <= self.hi


def parse_bucket(label: str) -> Bucket:
    # Older markets use en/em dashes and stray spaces ("81–82°F", "54 °F or below").
    s = label.replace("º", "°").replace("–", "-").replace("—", "-").replace("−", "-")
    if m := _RANGE.match(s):
        return Bucket(label, int(m.group(1)), int(m.group(2)), m.group(3).upper())
    if m := _BELOW.match(s):
        return Bucket(label, -math.inf, int(m.group(1)), m.group(2).upper())
    if m := _ABOVE.match(s):
        return Bucket(label, int(m.group(1)), math.inf, m.group(2).upper())
    # Early NYC labels: "<29°F" next to "30-31°F". Read as "29 or below" so the
    # buckets tile the integers (strict "<29" would leave 29 in no bucket).
    if m := re.match(r"^\s*<\s*(-?\d+)\s*°?\s*([FC])\s*$", s):
        return Bucket(label, -math.inf, int(m.group(1)), m.group(2).upper())
    if m := re.match(r"^\s*>\s*(-?\d+)\s*°?\s*([FC])\s*$", s):
        return Bucket(label, int(m.group(1)), math.inf, m.group(2).upper())
    if m := _SINGLE.match(s):
        v = int(m.group(1))
        return Bucket(label, v, v, m.group(2).upper())
    raise ValueError(f"Unrecognized bucket label: {label!r}")


def bucket_for(value: int, buckets: Sequence[Bucket]) -> Optional[Bucket]:
    hits = [b for b in buckets if b.contains(value)]
    if len(hits) > 1:
        raise ValueError(f"Overlapping buckets for {value}: {[b.label for b in hits]}")
    return hits[0] if hits else None


def bucket_probs(support: Sequence[int], pmf: Sequence[float], buckets: Sequence[Bucket]) -> dict[str, float]:
    """Sum an integer pmf (one row) into market buckets. Buckets must tile the integers."""
    out = {b.label: 0.0 for b in buckets}
    for k, p in zip(support, pmf):
        b = bucket_for(int(k), buckets)
        if b is not None:
            out[b.label] += float(p)
    return out


def check_partition(buckets: Sequence[Bucket]) -> None:
    """Assert buckets tile the integers with no gaps or overlaps."""
    bs = sorted(buckets, key=lambda b: b.lo)
    if not (math.isinf(bs[0].lo) and math.isinf(bs[-1].hi)):
        raise ValueError("Buckets must have open tails at both ends")
    for a, b in zip(bs, bs[1:]):
        if b.lo != a.hi + 1:
            raise ValueError(f"Gap/overlap between {a.label!r} and {b.label!r}")
