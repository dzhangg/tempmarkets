"""M5: model vs. Polymarket on settled events, at the same checkpoints the forecasts use.

For every settled event with an out-of-sample model forecast:
  * market probabilities = hourly CLOB price at the checkpoint, normalised across buckets
  * outcome = the market's own settled winner (so each era is scored by its own rule)
  * scores: log loss, Brier for market, EMOS, QR, and a 50/50 log-pool of EMOS + market
  * edge calibration: does (model - market) predict (outcome - market)?
  * hypothetical rule: buy the best-edge bucket when edge > threshold after half-spread + fees
Outputs: data/processed/market_compare.parquet, reports/m5_market.md, reports/figures/m5_*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from tempmarkets.features import CHECKPOINTS  # noqa: E402
from tempmarkets.io import polymarket as pm  # noqa: E402
from tempmarkets.market import blend, hypothetical_trade, model_probs, scores, snapshot  # noqa: E402
from tempmarkets.models.common import OFFSETS  # noqa: E402
from tempmarkets.truth import era_for  # noqa: E402
from tempmarkets.verify import block_bootstrap_skill  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "stations.yaml").read_text())
PRICES = ROOT / "data" / "raw" / "prices"
FIG = ROOT / "reports" / "figures"
THRESHOLDS = (0.03, 0.05, 0.10)
CP_LABEL = {"d1_1800": "Day-ahead (D-1 18:00)", "d0_0800": "Morning-of (D 08:00)"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "legend.frameon": False,
})


def load_hist(token: str) -> list:
    p = PRICES / f"{token}.json"
    return json.loads(p.read_text()) if p.exists() else []


def block_mean_ci(x: np.ndarray, block: int = 30, n_boot: int = 2000, seed: int = 0):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return float(np.mean(x)) if n else np.nan, np.nan, np.nan
    block = min(block, n)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    m = x[idx].mean(axis=1)
    return float(x.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    pred = pd.read_parquet(ROOT / "data" / "processed" / "predictions.parquet",
                           columns=["station", "date", "checkpoint", "model", "center", "pmf"])
    pred = pred[pred["model"].isin(["emos", "qreg"])]
    pred_idx = {(r.station, r.date, r.checkpoint, r.model): (r.center, r.pmf) for r in pred.itertuples()}

    ev_rows, bucket_rows, trade_rows, skipped = [], [], [], {"no_pred": 0, "no_price": 0, "no_winner": 0}
    for icao, st in CFG["stations"].items():
        if st.get("candidate"):
            continue
        evs = json.loads((ROOT / "data" / "raw" / "polymarket" / f"{st['series_slug']}.json").read_text())
        for ev in evs:
            if pm.is_superseded(ev):
                continue
            d = pm.observation_date(ev)
            hists = {b.yes_token: load_hist(b.yes_token) for b in pm.bucket_markets(ev)}
            for cp in CHECKPOINTS:
                ts = int(cp.utc(d, st["tz"]).timestamp())
                key_e, key_q = (icao, d, cp.name, "emos"), (icao, d, cp.name, "qreg")
                if key_e not in pred_idx:
                    skipped["no_pred"] += 1
                    continue
                snap = snapshot(ev, ts, hists)
                if snap is None:
                    skipped["no_price"] += 1
                    continue
                if snap.winner is None:
                    skipped["no_winner"] += 1
                    continue
                probs = {}
                for name, key in (("emos", key_e), ("qreg", key_q)):
                    c, pmf = pred_idx[key]
                    probs[name] = model_probs(c + OFFSETS, np.asarray(pmf), snap)
                probs["market"] = snap.implied
                probs["blend"] = blend(probs["emos"], snap.implied, 0.5, "log")
                row = {"station": icao, "date": d, "checkpoint": cp.name, "slug": ev["slug"],
                       "era": era_for(d, CFG["eras"]), "fee_rate": snap.fee_rate,
                       "overround": snap.overround, "n_buckets": len(snap.labels), "winner": snap.winner,
                       "market_fav_won": snap.labels[int(np.argmax(snap.implied))] == snap.winner,
                       "emos_fav_won": snap.labels[int(np.argmax(probs["emos"]))] == snap.winner}
                for name, p in probs.items():
                    s = scores(p, snap)
                    row.update({f"{name}_logloss": s["logloss"], f"{name}_brier": s["brier"],
                                f"{name}_pwin": s["p_winner"]})
                ev_rows.append(row)
                for lab, pm_, pk, raw in zip(snap.labels, probs["emos"], snap.implied, snap.raw):
                    bucket_rows.append({"station": icao, "date": d, "checkpoint": cp.name, "label": lab,
                                        "model": pm_, "market": pk, "raw": raw, "won": lab == snap.winner})
                for th in THRESHOLDS:
                    for hs in ((0.0, 0.01, 0.02) if th == 0.05 else (0.01,)):
                        t = hypothetical_trade(probs["emos"], snap, th, half_spread=hs)
                        if t:
                            trade_rows.append({"station": icao, "date": d, "checkpoint": cp.name,
                                               "threshold": th, "half_spread": hs, "era": row["era"],
                                               "fee_rate": snap.fee_rate, **t})

    E = pd.DataFrame(ev_rows).sort_values(["date", "station"])
    B = pd.DataFrame(bucket_rows)
    T = pd.DataFrame(trade_rows).sort_values("date") if trade_rows else pd.DataFrame()
    E.to_parquet(ROOT / "data" / "processed" / "market_compare.parquet", index=False)
    print(f"events scored: {len(E)}; skipped: {skipped}", flush=True)

    L = ["# M5: model vs. Polymarket on settled events", "",
         f"{E['slug'].nunique()} settled events ({E['date'].min()} → {E['date'].max()}), scored at both checkpoints "
         f"where an out-of-sample forecast and fresh (≤6 h old) prices for every bucket exist. "
         f"Skipped event-checkpoints: {skipped}.", "",
         "- **Market** = hourly CLOB price at the checkpoint, normalised to sum to 1 "
         f"(median overround {E['overround'].median():+.1%}). Not executable quotes.",
         "- **Outcome** = the market's own settled winner, so each era is scored by the rule it used. "
         "The model targets the current routine-METAR rule; for pre-2026-08-23 events (which counted "
         "SPECI) this costs it a little on the ~3% of days where SPECI moves the max.",
         "- **Blend** = 50/50 logarithmic pool of EMOS and market.",
         "- Log loss floors probabilities at 0.001 (the CLOB tick) for every forecaster alike.", ""]

    L += ["## Who forecasts better?", "",
          "Log-loss skill vs. market = 1 − LL / LL(market), 95% CI from a 30-day block bootstrap. "
          "Positive = better than the market.", "",
          "| checkpoint | station | events | market LL | EMOS LL | EMOS skill | QR skill | blend skill | "
          "market fav. wins | EMOS fav. wins |", "|---|---|---|---|---|---|---|---|---|---|"]
    for cp in ["d1_1800", "d0_0800"]:
        Ec = E[E["checkpoint"] == cp]
        for st in sorted(Ec["station"].unique()) + ["ALL"]:
            g = Ec if st == "ALL" else Ec[Ec["station"] == st]
            blk = 30 * (g["station"].nunique())
            sk = lambda m: block_bootstrap_skill(g[f"{m}_logloss"], g["market_logloss"], block=blk)  # noqa: E731
            f = lambda t: f"{t[0]:+.1%} [{t[1]:+.1%}, {t[2]:+.1%}]"  # noqa: E731
            L.append(f"| {cp} | **{st}** | {len(g)} | {g['market_logloss'].mean():.3f} | "
                     f"{g['emos_logloss'].mean():.3f} | {f(sk('emos'))} | {f(sk('qreg'))} | {f(sk('blend'))} | "
                     f"{g['market_fav_won'].mean():.1%} | {g['emos_fav_won'].mean():.1%} |"
                     if st == "ALL" else
                     f"| {cp} | {st} | {len(g)} | {g['market_logloss'].mean():.3f} | "
                     f"{g['emos_logloss'].mean():.3f} | {f(sk('emos'))} | {f(sk('qreg'))} | {f(sk('blend'))} | "
                     f"{g['market_fav_won'].mean():.1%} | {g['emos_fav_won'].mean():.1%} |")
    L.append("")

    L += ["## By settlement era (all stations)", "", "| checkpoint | era | events | market LL | EMOS LL | blend LL |",
          "|---|---|---|---|---|---|"]
    for (cp, era), g in E.groupby(["checkpoint", "era"]):
        L.append(f"| {cp} | {era} | {len(g)} | {g['market_logloss'].mean():.3f} | "
                 f"{g['emos_logloss'].mean():.3f} | {g['blend_logloss'].mean():.3f} |")
    L.append("")

    # Edge calibration
    bins = [-1, -0.15, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 0.15, 1]
    B["edge"] = B["model"] - B["market"]
    B["excess"] = B["won"].astype(float) - B["market"]
    B["bin"] = pd.cut(B["edge"], bins)
    L += ["## Edge calibration (EMOS − market, per bucket)", "",
          "If the model's disagreements carry information, realised excess (outcome − market prob) should "
          "have the same sign as the edge and grow with it.", "",
          "| checkpoint | edge bin | buckets | mean edge | realised excess | 95% CI |", "|---|---|---|---|---|---|"]
    edge_plot = {}
    for cp, gc in B.groupby("checkpoint"):
        rows = []
        for b, g in gc.groupby("bin", observed=True):
            g = g.sort_values("date")
            m, lo, hi = block_mean_ci(g["excess"].to_numpy())
            L.append(f"| {cp} | {b} | {len(g)} | {g['edge'].mean():+.3f} | {m:+.3f} | [{lo:+.3f}, {hi:+.3f}] |")
            rows.append((g["edge"].mean(), m, lo, hi, len(g)))
        edge_plot[cp] = rows
    L.append("")

    # Hypothetical trades
    L += ["## Hypothetical rule: buy best-edge bucket when edge > threshold (PAPER ONLY)", "",
          "$1 per trade at the quoted price + half-spread, minus the event's taker fee "
          "(`shares × rate × p × (1 − p)`; 0 before 2026-03-30 and 2026-10-20→10-30, 5% otherwise). "
          "Quoted history prices are not fills, and size at those prices was often small, so treat "
          "these as an upper bound.", "",
          "| checkpoint | threshold | half-spread | trades | hit rate | avg price | avg model p | "
          "total P&L ($) | ROI per $ | 95% CI |", "|---|---|---|---|---|---|---|---|---|---|"]
    if len(T):
        for (cp, th, hs), g in T.groupby(["checkpoint", "threshold", "half_spread"]):
            g = g.sort_values("date")
            m, lo, hi = block_mean_ci(g["pnl"].to_numpy())
            L.append(f"| {cp} | {th:.2f} | {hs:.2f} | {len(g)} | {g['won'].mean():.1%} | {g['price'].mean():.3f} | "
                     f"{g['model_p'].mean():.3f} | {g['pnl'].sum():+.1f} | {m:+.1%} | [{lo:+.1%}, {hi:+.1%}] |")
        L += ["", "By era (threshold 0.05, half-spread 0.01):", "",
              "| checkpoint | era | trades | hit rate | ROI per $ | fees paid ($) |", "|---|---|---|---|---|---|"]
        base = T[(T["threshold"] == 0.05) & (T["half_spread"] == 0.01)]
        for (cp, era), g in base.groupby(["checkpoint", "era"]):
            L.append(f"| {cp} | {era} | {len(g)} | {g['won'].mean():.1%} | {g['pnl'].mean():+.1%} | {g['fee'].sum():.2f} |")
    L.append("")

    # Figures
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True, sharey=True)
    stations = sorted(E["station"].unique()) + ["ALL"]
    for ax, cp in zip(axes, ["d1_1800", "d0_0800"]):
        Ec = E[E["checkpoint"] == cp]
        for k, (m, col, lab) in enumerate([("emos", C1, "EMOS"), ("qreg", C3, "Quantile reg."),
                                           ("blend", C2, "50/50 blend")]):
            for i, st in enumerate(stations):
                g = Ec if st == "ALL" else Ec[Ec["station"] == st]
                s, lo, hi = block_bootstrap_skill(g[f"{m}_logloss"], g["market_logloss"],
                                                  block=30 * g["station"].nunique())
                yv = i + (k - 1) * 0.22
                ax.plot([lo * 100, hi * 100], [yv, yv], color=col, lw=2, solid_capstyle="round")
                ax.plot(s * 100, yv, "o", color=col, ms=7, markeredgecolor=SURF, markeredgewidth=1.5,
                        label=lab if i == 0 else None)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_yticks(range(len(stations))); ax.set_yticklabels(stations)
        ax.set_title(CP_LABEL[cp]); ax.set_xlabel("Log-loss skill vs market (%), 95% CI")
        ax.grid(axis="y", visible=False)
    axes[1].legend(loc="lower right", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "m5_skill_vs_market.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4.6))
    ax.plot([-0.25, 0.25], [-0.25, 0.25], color=INK2, lw=1, ls="--", label="Edge fully realised")
    ax.axhline(0, color=GRID, lw=1); ax.axvline(0, color=GRID, lw=1)
    for cp, col in (("d1_1800", C1), ("d0_0800", C2)):
        r = np.array(edge_plot.get(cp, []))
        if len(r):
            ax.errorbar(r[:, 0], r[:, 1], yerr=[r[:, 1] - r[:, 2], r[:, 3] - r[:, 1]], color=col, lw=2,
                        marker="o", ms=6, mec=SURF, mew=1.5, capsize=0, label=CP_LABEL[cp])
    ax.set_xlabel("EMOS − market probability (bucket)"); ax.set_ylabel("Outcome − market probability")
    ax.set_title("Do model–market disagreements pay off?")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout(); fig.savefig(FIG / "m5_edge.png", dpi=150); plt.close(fig)

    if len(T):
        fig, ax = plt.subplots(figsize=(9, 3.8))
        base = T[(T["threshold"] == 0.05) & (T["half_spread"] == 0.01)]
        for cp, col in (("d1_1800", C1), ("d0_0800", C2)):
            g = base[base["checkpoint"] == cp].groupby("date")["pnl"].sum().cumsum()
            ax.plot(pd.to_datetime(g.index), g.values, color=col, lw=2, label=CP_LABEL[cp])
        ax.axhline(0, color=INK2, lw=1)
        ax.set_ylabel("Cumulative P&L ($1 per trade)")
        ax.set_title("Hypothetical rule (edge > 0.05, 1¢ half-spread, fees) — paper only")
        ax.legend(loc="upper left", fontsize=9)
        fig.tight_layout(); fig.savefig(FIG / "m5_pnl.png", dpi=150); plt.close(fig)

    L += ["## Figures", "", "![Skill vs market](figures/m5_skill_vs_market.png)", "",
          "![Edge calibration](figures/m5_edge.png)", "", "![Hypothetical P&L](figures/m5_pnl.png)", ""]
    (ROOT / "reports" / "m5_market.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
