# M1: CLI daily max vs. market settlement max

Complete station-days 2020→2026-11: 9995. Market max = current rule (routine METAR T-group, °C→°F half-up, local calendar day).

## CLI − market max (KMIA, KLGA, KATL; KDAL has no CLI)

| station | n | mean °F | CLI higher | CLI lower | different 2°F bucket |
|---|---|---|---|---|---|
| KATL | 2496 | +0.75 | 62.2% | 0.2% | 36.6% |
| KLGA | 2496 | +0.64 | 54.9% | 0.7% | 32.9% |
| KMIA | 2489 | +0.85 | 68.7% | 0.1% | 41.9% |

Distribution of CLI − market max, all three stations:

| ≤-2 | -1 | +0 | +1 | +2 | +3 | ≥+4 |
|---|---|---|---|---|---|---|
| 0.1% | 0.2% | 37.7% | 50.1% | 10.4% | 1.2% | 0.2% |

### By season

| station | DJF | MAM | JJA | SON |
|---|---|---|---|---|
| KATL | +0.61 | +0.74 | +0.92 | +0.72 |
| KLGA | +0.51 | +0.67 | +0.80 | +0.58 |
| KMIA | +0.77 | +0.90 | +0.83 | +0.89 |

### Decomposition: CLI − market = window + SPECI + sensor

| station | DST? | window | SPECI | sensor | total |
|---|---|---|---|---|---|
| KATL | std | +0.00 | +0.04 | +0.59 | +0.63 |
| KATL | DST | -0.01 | +0.03 | +0.79 | +0.81 |
| KLGA | std | +0.00 | +0.03 | +0.49 | +0.53 |
| KLGA | DST | -0.06 | +0.03 | +0.74 | +0.70 |
| KMIA | std | +0.00 | +0.01 | +0.78 | +0.79 |
| KMIA | DST | -0.00 | +0.06 | +0.82 | +0.88 |

- **window**: max over the standard-time day minus max over the clock day. It is zero outside DST by construction, and during DST it measures the 00–01 vs. next-day 00–01 swap.
- **SPECI**: what special reports add on top of routine ones (the market ignores them now; WU-era markets included them).
- **sensor**: what the continuous record catches between reports (peaks between hourly obs, and whole-°F vs. tenths-°C rounding paths).

## SPECI effect on the settlement bucket (all four stations)

| station | days SPECI raises max | days it changes the 2°F bucket |
|---|---|---|
| KATL | 2.6% | 1.5% |
| KDAL | 2.3% | 1.6% |
| KLGA | 2.8% | 1.2% |
| KMIA | 3.9% | 2.3% |

## CLI proxy for KDAL (no CLI issued for Love Field)

Proxy = max of 6-hr max groups fully inside the standard-time day and every tenths-°C T-group.
Where CLI exists it matches exactly on 96.6% of days, within 1°F on 99.1% (mean CLI − proxy +0.04°F).

| ≤-2 | -1 | +0 | +1 | ≥+2 |
|---|---|---|---|---|
| 0.1% | 0.1% | 96.6% | 2.5% | 0.8% |

KDAL proxy − market max: mean +0.72°F, different 2°F bucket on 35.1% of days.
