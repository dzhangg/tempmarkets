# tempmarkets

Probabilistic daily max-temperature forecasts vs. Polymarket prices.
Read-only analysis plus a paper-trading log. **No order placement code exists in this repo.**

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python scripts/00_probe_sources.py   # M0: verifies every data source
```

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
- **M2** day-ahead NBM/MOS forecasts with issuance-time guards
- **M3** baseline / EMOS / quantile regression → bucket probabilities
- **M4** verification (CRPS, RPS, Brier, log loss, PIT, reliability), time-based splits
- **M5** model vs. market calibration + forward paper-trading log
