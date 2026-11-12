"""M4: verification of the out-of-sample predictive distributions from 06_fit_models.py.

Metrics: CRPS (discrete), log score, 2°F-bucket Brier and log loss, randomized PIT
(+ 12·Var dispersion ratio), bucket reliability (+ ECE). Skill CIs use a 30-day
moving-block bootstrap on paired daily scores.
Outputs: reports/m4_verification.md, reports/figures/m4_*.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from tempmarkets.verify import (block_bootstrap_skill, bucket_scores, expected_calibration_error,  # noqa: E402
                                pit_dispersion, pit_randomized, reliability, stack_pmf)

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "reports" / "figures"
MODELS = ["nbm_raw", "baseline", "emos", "qreg"]
LABEL = {"nbm_raw": "Raw NBM", "baseline": "Baseline", "emos": "EMOS", "qreg": "Quantile reg."}
CP_LABEL = {"d1_1800": "Day-ahead (D-1 18:00)", "d0_0800": "Morning-of (D 08:00)"}
# Reference palette, light mode: raw NBM as neutral reference, then slots 1-3 in fixed order.
COLOR = {"nbm_raw": "#8f8e88", "baseline": "#2a78d6", "emos": "#eb6834", "qreg": "#1baf7a"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
    "axes.titlesize": 11, "axes.titleweight": "semibold", "legend.frameon": False,
})


def add_scores(p: pd.DataFrame) -> pd.DataFrame:
    out = []
    for m, g in p.groupby("model"):
        pmf, c, y = stack_pmf(g["pmf"]), g["center"].to_numpy(), g["y"].to_numpy()
        s = bucket_scores(pmf, c, y)
        g = g.assign(pit=pit_randomized(pmf, c, y), brier=s["brier"].to_numpy(),
                     bucket_logloss=s["bucket_logloss"].to_numpy())
        out.append(g)
    return pd.concat(out, ignore_index=True)


def paired(p: pd.DataFrame, model: str, ref: str, col: str = "rps"):
    a = p[p["model"] == model].sort_values(["date", "station"])
    b = p[p["model"] == ref].sort_values(["date", "station"])
    assert (a["date"].to_numpy() == b["date"].to_numpy()).all()
    return a[col].to_numpy(), b[col].to_numpy()


def fmt_skill(t):
    s, lo, hi = t
    return f"{s:+.1%} [{lo:+.1%}, {hi:+.1%}]"


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    p = pd.read_parquet(ROOT / "data" / "processed" / "predictions.parquet")
    p = add_scores(p)
    n_st = p["station"].nunique()
    L = ["# M4: verification of out-of-sample predictive distributions", "",
         f"Test period {p['test_month'].min()} → {p['test_month'].max()} (monthly refit, expanding window, "
         "training cut off 2 days before each test month). Target = current METAR-rule settlement max.",
         "Skill = 1 − score / reference score, with 95% CIs from a 30-day moving-block bootstrap on "
         "paired daily scores. Bucket metrics use today's 2°F market grid.", "",
         "**PIT 12·Var**: 1.00 = calibrated spread; > 1 = too narrow (U-shaped PIT); < 1 = too wide (humped).", ""]

    # --- headline table, per checkpoint x station x model
    for cp in ["d1_1800", "d0_0800"]:
        L += [f"## {CP_LABEL[cp]}", "",
              "| station | model | CRPS °F | CRPS skill vs raw NBM | vs baseline | log score | bucket Brier | "
              "bucket log loss | PIT 12·Var | ECE |", "|---|---|---|---|---|---|---|---|---|---|"]
        for st in sorted(p["station"].unique()):
            g = p[(p["checkpoint"] == cp) & (p["station"] == st)]
            for m in MODELS:
                gm = g[g["model"] == m]
                vs_raw = fmt_skill(block_bootstrap_skill(*paired(g, m, "nbm_raw"))) if m != "nbm_raw" else "—"
                vs_base = (fmt_skill(block_bootstrap_skill(*paired(g, m, "baseline")))
                           if m in ("emos", "qreg") else "—")
                rel = reliability(stack_pmf(gm["pmf"]), gm["center"].to_numpy(), gm["y"].to_numpy())
                L.append(f"| {st} | {LABEL[m]} | {gm['rps'].mean():.3f} | {vs_raw} | {vs_base} | "
                         f"{gm['log_score'].mean():.3f} | {gm['brier'].mean():.3f} | "
                         f"{gm['bucket_logloss'].mean():.3f} | {pit_dispersion(gm['pit'].to_numpy()):.2f} | "
                         f"{expected_calibration_error(rel):.3f} |")
        L.append("")

    # --- pooled comparisons
    L += ["## Pooled over stations", "", "| checkpoint | comparison | CRPS skill | log-score diff (nats) |",
          "|---|---|---|---|"]
    for cp in ["d1_1800", "d0_0800"]:
        g = p[p["checkpoint"] == cp]
        for m, ref in [("emos", "nbm_raw"), ("qreg", "nbm_raw"), ("emos", "baseline"),
                       ("qreg", "baseline"), ("qreg", "emos")]:
            a, b = paired(g, m, ref, "log_score")
            L.append(f"| {cp} | {LABEL[m]} vs {LABEL[ref]} | "
                     f"{fmt_skill(block_bootstrap_skill(*paired(g, m, ref), block=30 * n_st))} | "
                     f"{(a - b).mean():+.3f} |")
    L.append("")

    # --- season breakdown (day-ahead)
    d1 = p[p["checkpoint"] == "d1_1800"].copy()
    d1["season"] = pd.to_datetime(d1["date"]).dt.month.map(
        {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
         6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"})
    L += ["## Day-ahead EMOS CRPS skill vs raw NBM, by season", "",
          "| station | DJF | MAM | JJA | SON |", "|---|---|---|---|---|"]
    for st in sorted(d1["station"].unique()):
        cells = []
        for s in ["DJF", "MAM", "JJA", "SON"]:
            g = d1[(d1["station"] == st) & (d1["season"] == s)]
            a, b = paired(g, "emos", "nbm_raw")
            cells.append(f"{1 - a.mean() / b.mean():+.1%}")
        L.append(f"| {st} | " + " | ".join(cells) + " |")
    L.append("")

    # --- figures
    fig, axes = plt.subplots(2, 4, figsize=(12, 5.4), sharey=True, sharex=True)
    for i, cp in enumerate(["d1_1800", "d0_0800"]):
        for j, m in enumerate(MODELS):
            ax = axes[i, j]
            u = p[(p["checkpoint"] == cp) & (p["model"] == m)]["pit"].to_numpy()
            h, e = np.histogram(u, bins=10, range=(0, 1), density=True)
            ax.bar(e[:-1], h, width=0.1, align="edge", color=COLOR[m], edgecolor=SURF, linewidth=2)
            ax.axhline(1, color=INK2, lw=1, ls="--")
            ax.set_ylim(0, 2.5)
            ax.text(0.5, 2.32, f"12·Var = {pit_dispersion(u):.2f}", ha="center", fontsize=9, color=INK2)
            if i == 0:
                ax.set_title(LABEL[m])
            if j == 0:
                ax.set_ylabel(f"{CP_LABEL[cp].split(' (')[0]}\ndensity")
            if i == 1:
                ax.set_xlabel("PIT")
    fig.suptitle("Randomized PIT histograms (all stations, out-of-sample). Flat = calibrated.",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(FIG / "m4_pit.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
    for ax, cp in zip(axes, ["d1_1800", "d0_0800"]):
        ax.plot([0, 1], [0, 1], color=INK2, lw=1, ls="--", label="Perfect reliability")
        for m in MODELS:
            g = p[(p["checkpoint"] == cp) & (p["model"] == m)]
            rel = reliability(stack_pmf(g["pmf"]), g["center"].to_numpy(), g["y"].to_numpy())
            rel = rel[rel["n"] >= 50]
            ax.plot(rel["p_mean"], rel["obs_freq"], color=COLOR[m], lw=2, marker="o", ms=5,
                    markeredgecolor=SURF, markeredgewidth=1.5, label=LABEL[m])
        ax.set_title(CP_LABEL[cp])
        ax.set_xlabel("Forecast probability of a 2°F bucket")
        ax.set_xlim(0, 0.8); ax.set_ylim(0, 0.8)
    axes[0].set_ylabel("Observed frequency")
    axes[1].legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "m4_reliability.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, sharex=True)
    stations = sorted(p["station"].unique())
    for ax, cp in zip(axes, ["d1_1800", "d0_0800"]):
        for k, m in enumerate(["baseline", "emos", "qreg"]):
            for i, st in enumerate(stations):
                g = p[(p["checkpoint"] == cp) & (p["station"] == st)]
                s, lo, hi = block_bootstrap_skill(*paired(g, m, "nbm_raw"))
                yv = i + (k - 1) * 0.22
                ax.plot([lo * 100, hi * 100], [yv, yv], color=COLOR[m], lw=2, solid_capstyle="round")
                ax.plot(s * 100, yv, "o", color=COLOR[m], ms=7, markeredgecolor=SURF, markeredgewidth=1.5,
                        label=LABEL[m] if i == 0 else None)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_yticks(range(len(stations))); ax.set_yticklabels(stations)
        ax.set_title(CP_LABEL[cp]); ax.set_xlabel("CRPS skill vs raw NBM (%), 95% CI")
        ax.grid(axis="y", visible=False)
    axes[1].legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "m4_skill.png", dpi=150)
    plt.close(fig)

    L += ["## Figures", "", "![PIT histograms](figures/m4_pit.png)", "",
          "![Reliability](figures/m4_reliability.png)", "", "![Skill](figures/m4_skill.png)", ""]
    (ROOT / "reports" / "m4_verification.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
