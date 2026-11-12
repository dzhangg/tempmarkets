"""Model vs. market: align prices to checkpoints, score both, and evaluate edges.

Prices come from CLOB /prices-history (hourly). These are *not* executable quotes:
hypothetical trades add an assumed half-spread and the event's taker fee.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .buckets import Bucket, bucket_probs, parse_bucket
from .io import polymarket as pm

P_FLOOR = 1e-3  # = CLOB min tick; applied to model and market alike in log loss


def price_at(history: Sequence[dict], ts: int, max_stale_h: float = 6.0) -> Optional[float]:
    """Last price at or before `ts` (unix s), or None if none within `max_stale_h` hours."""
    if not history:
        return None
    times = [h["t"] for h in history]
    i = bisect.bisect_right(times, ts) - 1
    if i < 0 or ts - times[i] > max_stale_h * 3600:
        return None
    return float(history[i]["p"])


@dataclass
class EventSnapshot:
    labels: list[str]
    buckets: list[Bucket]
    raw: np.ndarray        # YES prices as quoted (sum = 1 + overround)
    winner: Optional[str]
    fee_rate: float

    @property
    def overround(self) -> float:
        return float(self.raw.sum() - 1)

    @property
    def implied(self) -> np.ndarray:
        """Normalised market probabilities."""
        return self.raw / self.raw.sum()


def snapshot(ev: dict, ts: int, histories: dict[str, list], max_stale_h: float = 6.0) -> Optional[EventSnapshot]:
    """Market state at `ts`. None if any bucket lacks a fresh price or labels don't parse."""
    bms = pm.bucket_markets(ev)
    try:
        buckets = [parse_bucket(b.label) for b in bms]
    except ValueError:
        return None
    prices = [price_at(histories.get(b.yes_token, []), ts, max_stale_h) for b in bms]
    if any(p is None for p in prices) or sum(prices) <= 0:
        return None
    return EventSnapshot([b.label for b in bms], buckets, np.array(prices, float),
                         pm.winning_label(ev), pm.fee_schedule(ev)["rate"])


def model_probs(support: np.ndarray, pmf: np.ndarray, snap: EventSnapshot) -> np.ndarray:
    p = bucket_probs(support, pmf, snap.buckets)
    return np.array([p[label] for label in snap.labels])


def scores(p: np.ndarray, snap: EventSnapshot) -> dict:
    o = np.array([label == snap.winner for label in snap.labels], float)
    pw = float(np.clip(p, P_FLOOR, 1)[o.astype(bool)][0])
    return {"logloss": -np.log(pw), "brier": float(((p - o) ** 2).sum()), "p_winner": pw}


def blend(model: np.ndarray, market: np.ndarray, w: float = 0.5, kind: str = "log") -> np.ndarray:
    """Linear or logarithmic opinion pool of two bucket distributions."""
    if kind == "linear":
        out = w * model + (1 - w) * market
    else:
        out = np.exp(w * np.log(np.clip(model, P_FLOOR, 1)) + (1 - w) * np.log(np.clip(market, P_FLOOR, 1)))
    return out / out.sum()


def hypothetical_trade(model: np.ndarray, snap: EventSnapshot, threshold: float, half_spread: float = 0.01,
                       min_price: float = 0.02, max_price: float = 0.95, stake: float = 1.0) -> Optional[dict]:
    """Buy YES on the single bucket with the largest edge after costs, if edge > threshold.

    cost per share = quoted price + half_spread; fee per share = rate * p * (1 - p).
    Edge = model prob - (cost + fee) per share. PAPER ONLY: quoted history prices are
    not executable, so this is an upper bound on what a real taker could have done.
    """
    px = snap.raw
    cost = px + half_spread
    fee = snap.fee_rate * cost * (1 - cost)
    edge = model - (cost + fee)
    ok = (px >= min_price) & (px <= max_price)
    if not ok.any():
        return None
    edge = np.where(ok, edge, -np.inf)
    j = int(np.argmax(edge))
    if edge[j] <= threshold:
        return None
    shares = stake / cost[j]
    won = snap.labels[j] == snap.winner
    pnl = shares * (1.0 if won else 0.0) - stake - shares * fee[j]
    return {"bucket": snap.labels[j], "price": float(px[j]), "cost": float(cost[j]),
            "fee": float(shares * fee[j]), "model_p": float(model[j]), "edge": float(edge[j]),
            "won": won, "pnl": float(pnl)}
