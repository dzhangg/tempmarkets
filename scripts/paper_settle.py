"""Settle paper trades whose events have resolved, and print a running summary. READ-ONLY.
Usage: python scripts/paper_settle.py
"""
from __future__ import annotations

import pandas as pd

from tempmarkets.io import polymarket as pm
from tempmarkets.paper import log


def main() -> None:
    trades = log.read(log.TRADES)
    done = {(s["slug"], s["lead"]) for s in log.read(log.SETTLED)}
    new = []
    for t in trades:
        if (t["slug"], t["lead"]) in done:
            continue
        ev = pm.event(t["slug"])
        win = pm.winning_label(ev) if ev.get("closed") else None
        if win is None:
            continue
        won = t["bucket"] == win
        pnl = t["shares"] * (1.0 if won else 0.0) - t["stake"] - t["fee"]
        new.append({**t, "winner": win, "won": won, "pnl": pnl})
    log.append(log.SETTLED, new)
    s = pd.DataFrame(log.read(log.SETTLED))
    open_n = len(trades) - len(s)
    if s.empty:
        print(f"no settled paper trades yet ({open_n} open)")
        return
    print(f"settled {len(new)} new; total settled {len(s)}, open {open_n}")
    print(s.groupby("lead").agg(trades=("pnl", "size"), hit_rate=("won", "mean"),
                                total_pnl=("pnl", "sum"), roi=("pnl", "mean")).round(3).to_string())


if __name__ == "__main__":
    main()
