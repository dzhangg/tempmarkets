# M3: out-of-sample predictive distributions — quick skill check

Monthly refit, expanding window; test months 2022-01 → 2026-11. Target = current METAR-rule max. Lower is better except coverage (target 80%). Full verification (reliability, PIT, CIs) is M4.

Discrete CRPS (RPS over 1°F bins) is in °F, log score is in nats, and bucket loss uses today's 2°F grid. Skill = 1 − CRPS / CRPS(raw NBM).

## Checkpoint `d0_0800`

| station | model | n | CRPS | skill vs raw NBM | log score | 2°F bucket log loss | 80% coverage | bias of mean |
|---|---|---|---|---|---|---|---|---|
| KATL | nbm_raw | 1768 | 1.369 | +0.0% | 2.421 | 1.748 | 78.3% | +0.55 |
| KATL | baseline | 1768 | 1.324 | +3.3% | 2.419 | 1.703 | 83.9% | +0.06 |
| KATL | emos | 1768 | 1.193 | +12.8% | 2.138 | 1.487 | 85.5% | -0.02 |
| KATL | qreg | 1768 | 1.201 | +12.3% | 2.156 | 1.485 | 85.5% | -0.03 |
| KDAL | nbm_raw | 1768 | 1.437 | +0.0% | 2.510 | 1.802 | 76.7% | +0.42 |
| KDAL | baseline | 1768 | 1.395 | +2.9% | 2.478 | 1.735 | 85.1% | +0.00 |
| KDAL | emos | 1768 | 1.261 | +12.3% | 2.219 | 1.551 | 86.7% | -0.06 |
| KDAL | qreg | 1768 | 1.254 | +12.7% | 2.226 | 1.536 | 87.6% | +0.05 |
| KLGA | nbm_raw | 1768 | 1.389 | +0.0% | 2.538 | 1.843 | 74.8% | +0.28 |
| KLGA | baseline | 1768 | 1.325 | +4.6% | 2.388 | 1.682 | 85.3% | -0.02 |
| KLGA | emos | 1768 | 1.177 | +15.3% | 2.173 | 1.521 | 87.0% | -0.09 |
| KLGA | qreg | 1768 | 1.185 | +14.6% | 2.177 | 1.504 | 87.0% | +0.05 |
| KMIA | nbm_raw | 1768 | 0.905 | +0.0% | 1.999 | 1.336 | 78.5% | +0.79 |
| KMIA | baseline | 1768 | 0.793 | +12.4% | 1.887 | 1.210 | 86.8% | +0.00 |
| KMIA | emos | 1768 | 0.742 | +18.0% | 1.706 | 1.086 | 91.2% | +0.05 |
| KMIA | qreg | 1768 | 0.746 | +17.7% | 1.721 | 1.090 | 90.3% | +0.03 |

## Checkpoint `d1_1800`

| station | model | n | CRPS | skill vs raw NBM | log score | 2°F bucket log loss | 80% coverage | bias of mean |
|---|---|---|---|---|---|---|---|---|
| KATL | nbm_raw | 1768 | 1.424 | +0.0% | 2.485 | 1.797 | 80.0% | +0.50 |
| KATL | baseline | 1768 | 1.372 | +3.6% | 2.446 | 1.726 | 84.6% | +0.05 |
| KATL | emos | 1768 | 1.257 | +11.7% | 2.190 | 1.528 | 86.5% | +0.06 |
| KATL | qreg | 1768 | 1.259 | +11.5% | 2.222 | 1.540 | 85.4% | -0.02 |
| KDAL | nbm_raw | 1768 | 1.493 | +0.0% | 2.497 | 1.795 | 78.6% | +0.37 |
| KDAL | baseline | 1768 | 1.458 | +2.3% | 2.520 | 1.773 | 85.7% | -0.02 |
| KDAL | emos | 1768 | 1.350 | +9.5% | 2.262 | 1.591 | 86.1% | +0.09 |
| KDAL | qreg | 1768 | 1.345 | +9.9% | 2.290 | 1.596 | 86.3% | +0.09 |
| KLGA | nbm_raw | 1768 | 1.445 | +0.0% | 2.581 | 1.877 | 73.8% | +0.29 |
| KLGA | baseline | 1768 | 1.375 | +4.9% | 2.410 | 1.708 | 86.3% | -0.02 |
| KLGA | emos | 1768 | 1.236 | +14.5% | 2.200 | 1.532 | 86.1% | -0.08 |
| KLGA | qreg | 1768 | 1.254 | +13.2% | 2.248 | 1.562 | 86.3% | -0.01 |
| KMIA | nbm_raw | 1768 | 0.944 | +0.0% | 2.058 | 1.395 | 77.9% | +0.79 |
| KMIA | baseline | 1768 | 0.842 | +10.8% | 1.948 | 1.266 | 85.7% | -0.01 |
| KMIA | emos | 1768 | 0.792 | +16.1% | 1.773 | 1.144 | 89.9% | +0.05 |
| KMIA | qreg | 1768 | 0.794 | +15.9% | 1.788 | 1.145 | 89.6% | +0.01 |
