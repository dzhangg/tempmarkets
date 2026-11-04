# tempmarkets

Probabilistic daily max-temperature forecasts vs. Polymarket prices.
Read-only analysis plus a paper-trading log. **No order placement code exists in this repo.**

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python scripts/00_probe_sources.py   # M0: verifies every data source
```

## Pipeline (run in order)
| Script | Does | First run |
|---|---|---|
| `01_fetch_obs.py` | IEM METAR/SPECI + NWS CLI + settled Polymarket events → `data/raw/` | ~5 min |
| `02_truth_table.py` | daily settlement max per era, validated vs. settled markets → `reports/m1_validation.md` | <1 min |
| `03_gap_analysis.py` | CLI vs. market max → `reports/m1_gaps.md` | seconds |
| `04_fetch_forecasts.py` | NBM (NBS) + GFS MOS archives → `data/raw/mos/` (paced for IEM's rate limit) | ~12 min |
| `05_build_features.py` | leak-free feature table + raw skill → `reports/m2_forecasts.md` | ~2 min |

Downloads are cached. Re-runs only re-fetch the current year.

## Settlement rules change over time
Polymarket's rule text for these markets has three eras (confirmed for KMIA, KLGA, KORD, KDAL, KATL, KAUS):

| Era | Observation dates | Settles on |
|---|---|---|
| `wu` | through 2026-08-22 | Weather Underground Daily Observations max, whole °F (METAR+SPECI) |
| `nws_ts` | 2026-08-23 → 2026-10-22 | weather.gov/wrh/timeseries "Temp" max, whole °F |
| `metar` | 2026-10-23 → | Routine METARs only (no SPECI), T-group tenths °C (else body °C) → °F, half-up, local day |

`src/tempmarkets/truth.py` rebuilds each era's daily max from IEM METAR data. Models target the
`metar` rule, and market comparisons score each day with the rule in force on that day.

## Milestones
- **M0** source probe + station selection ✅
- **M1** ground truth + CLI gap analysis + validation against settled outcomes ✅ (`reports/m1_validation.md`, `reports/m1_gaps.md`)
- **M2** day-ahead NBM/MOS forecasts with issuance-time guards ✅ (`reports/m2_forecasts.md`)
  - Checkpoints: D-1 18:00 local (day-ahead) and D 08:00 local (morning-of). Each uses the latest
    run published by then, assuming NBM is out 90 min and GFS MOS 4 h after the run time.
  - NBM daily max/spread (`txn`/`xnd`) exist from 2020-09-30 (the NBM v4.0 upgrade). GFS MOS covers 2020→.
- **M3** baseline / EMOS / quantile regression → bucket probabilities
- **M4** verification (CRPS, RPS, Brier, log loss, PIT, reliability), time-based splits
- **M5** model vs. market calibration + forward paper-trading log
