"""Append-only JSONL paper log + live order-book helpers. No order placement exists here."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

LOG_DIR = Path(__file__).resolve().parents[3] / "paper_log"
SNAPSHOTS = LOG_DIR / "snapshots.jsonl"
TRADES = LOG_DIR / "trades.jsonl"
SETTLED = LOG_DIR / "settled.jsonl"


def append(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
            n += 1
    return n


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def best_quotes(book: dict) -> dict:
    """Best bid/ask and their sizes from a CLOB /book response."""
    bids = [(float(b["price"]), float(b["size"])) for b in book.get("bids", [])]
    asks = [(float(a["price"]), float(a["size"])) for a in book.get("asks", [])]
    bb = max(bids, default=(None, 0.0))
    ba = min(asks, default=(None, 0.0))
    return {"bid": bb[0], "bid_size": bb[1], "ask": ba[0], "ask_size": ba[1]}


def paper_decision(labels: list[str], model_p: list[float], asks: list[Optional[float]],
                   ask_sizes: list[float], fee_rate: float, threshold: float = 0.05,
                   stake: float = 1.0, min_price: float = 0.02, max_price: float = 0.95) -> Optional[dict]:
    """Same rule as the backtest, but against the live best ask (an executable price).
    Fee per share = rate * p * (1 - p). Requires the ask to have size for the whole stake."""
    best = None
    for lab, p, a, sz in zip(labels, model_p, asks, ask_sizes):
        if a is None or not (min_price <= a <= max_price):
            continue
        edge = p - (a + fee_rate * a * (1 - a))
        shares = stake / a
        if edge > threshold and sz >= shares and (best is None or edge > best["edge"]):
            best = {"bucket": lab, "ask": a, "model_p": p, "edge": edge, "shares": shares,
                    "fee": shares * fee_rate * a * (1 - a), "stake": stake}
    return best
