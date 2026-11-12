"""Polymarket read-only access (Gamma metadata + CLOB price history / order book).

GET requests only. There is deliberately no order, signing, or wallet code here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Optional

from .http import get

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def series_events(series_slug: str, closed: bool) -> list[dict]:
    """All events in a series. Gamma caps pages at 100, so paginate by offset."""
    out, offset = [], 0
    while True:
        page = get(f"{GAMMA}/events", {"series_slug": series_slug, "closed": str(closed).lower(),
                                        "limit": 100, "offset": offset}).json()
        out += page
        if len(page) < 100:
            break
        offset += 100
    out = [e for e in out if e.get("endDate")]
    out.sort(key=lambda e: e["endDate"])
    return out


def event(slug: str) -> dict:
    return get(f"{GAMMA}/events/slug/{slug}").json()


@dataclass(frozen=True)
class BucketMarket:
    label: str
    yes_token: str
    no_token: str
    outcome_prices: tuple[float, float]  # (yes, no); ~1/0 once settled
    volume: float


def bucket_markets(ev: dict) -> list[BucketMarket]:
    out = []
    for m in ev.get("markets", []):
        toks = json.loads(m.get("clobTokenIds") or "[]")
        px = json.loads(m.get("outcomePrices") or "[]")
        if len(toks) != 2:
            continue
        out.append(BucketMarket(
            label=m.get("groupItemTitle", ""),
            yes_token=toks[0], no_token=toks[1],
            outcome_prices=(float(px[0]), float(px[1])) if len(px) == 2 else (float("nan"),) * 2,
            volume=float(m.get("volume") or 0),
        ))
    return out


_DATE_PATTERNS = [
    (re.compile(r"\bon (\d{1,2} [A-Z][a-z]{2} '\d{2})"), "%d %b '%y"),        # 22 Jan '26
    (re.compile(r"\bon ([A-Z][a-z]+ \d{1,2}, \d{4})"), "%B %d, %Y"),           # January 22, 2025
    (re.compile(r"\bon (\d{1,2} [A-Z][a-z]{2} \d{4})"), "%d %b %Y"),          # 6 Dec 2025
]


def observation_date(ev: dict) -> dt.date:
    """Observation date from the rule text; `endDate` is not always that day
    (e.g. NYC 'may-12' 2025 has endDate 2025-05-13)."""
    if ev.get("eventDate"):
        return dt.date.fromisoformat(ev["eventDate"][:10])
    desc = ev.get("description", "")
    for rx, fmt in _DATE_PATTERNS:
        if m := rx.search(desc):
            return dt.datetime.strptime(m.group(1), fmt).date()
    raise ValueError(f"No observation date found for {ev.get('slug')}")


def is_superseded(ev: dict) -> bool:
    """`arch-` events are archived duplicates (May 2026) that settled on the lowest bucket."""
    return ev.get("slug", "").startswith("arch-")


def winning_label(ev: dict) -> Optional[str]:
    """Label of the bucket whose YES settled at ~1, if the event is settled."""
    wins = [b.label for b in bucket_markets(ev) if b.outcome_prices[0] > 0.99]
    return wins[0] if len(wins) == 1 else None


def price_history(token: str, start_ts: int, end_ts: int, fidelity_min: int = 60) -> list[dict]:
    """Hourly price series. Closed markets need explicit startTs/endTs;
    `interval=max` returns an empty list for them (verified 2026-11-03)."""
    r = get(f"{CLOB}/prices-history",
            {"market": token, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity_min})
    return r.json().get("history", [])


def price_history_cached(token: str, start_ts: int, end_ts: int, cache_dir, fidelity_min: int = 60) -> list[dict]:
    """price_history with a per-token JSON cache (settled markets never change)."""
    from pathlib import Path
    path = Path(cache_dir) / f"{token}.json"
    if path.exists():
        return json.loads(path.read_text())
    hist = price_history(token, start_ts, end_ts, fidelity_min)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist))
    return hist


def fee_schedule(ev: dict) -> dict:
    """Taker fee schedule recorded on the event's markets (rate 0 if fees disabled).
    Fee per trade = shares * rate * p * (1 - p) (docs.polymarket.com/trading/fees)."""
    m = (ev.get("markets") or [{}])[0]
    sch = m.get("feeSchedule") or {}
    rate = float(sch.get("rate", 0) or 0) if m.get("feesEnabled") else 0.0
    return {"rate": rate, "type": m.get("feeType")}


def taker_fee_per_share(price: float, rate: float) -> float:
    return rate * price * (1 - price)


def order_book(token: str) -> dict:
    return get(f"{CLOB}/book", {"token_id": token}).json()
