# M2: raw guidance vs. market settlement max (current METAR rule)

Target = `max_metar`. Error = forecast − observed. Complete days only.

| station | checkpoint | n | NBM bias | NBM MAE | NBM RMSE | GFS MOS MAE | corr(xnd, abs err) | NBM rounded in right 2°F bucket |
|---|---|---|---|---|---|---|---|---|
| KATL | d0_0800 | 2226 | +0.52 | 1.80 | 2.67 | 2.05 | 0.35 | 38.2% |
| KATL | d1_1800 | 2226 | +0.47 | 1.89 | 2.74 | 2.19 | 0.30 | 37.0% |
| KDAL | d0_0800 | 2226 | +0.41 | 1.95 | 2.74 | 2.76 | 0.29 | 34.6% |
| KDAL | d1_1800 | 2226 | +0.36 | 2.09 | 2.90 | 2.77 | 0.33 | 31.8% |
| KLGA | d0_0800 | 2226 | +0.26 | 1.86 | 2.54 | 2.32 | 0.28 | 35.2% |
| KLGA | d1_1800 | 2226 | +0.27 | 1.96 | 2.64 | 2.43 | 0.27 | 33.0% |
| KMIA | d0_0800 | 2226 | +0.79 | 1.23 | 1.68 | 1.40 | 0.20 | 46.6% |
| KMIA | d1_1800 | 2226 | +0.79 | 1.26 | 1.76 | 1.42 | 0.21 | 46.8% |

## Day-ahead NBM bias by season (°F)

| station | DJF | MAM | JJA | SON |
|---|---|---|---|---|
| KATL | -0.18 | +0.91 | +0.89 | +0.24 |
| KDAL | -0.31 | +0.81 | +0.86 | +0.08 |
| KLGA | -0.38 | +0.52 | +1.02 | -0.08 |
| KMIA | +0.68 | +0.83 | +0.87 | +0.80 |

## Day-ahead NBM error by forecast spread (xnd)

| xnd (°F) | n | MAE | error SD |
|---|---|---|---|
| ≤1 | 3575 | 1.33 | 1.71 |
| 2 | 3646 | 1.80 | 2.39 |
| 3 | 1228 | 2.51 | 3.36 |
| 4 | 318 | 3.31 | 4.30 |
| ≥5 | 123 | 4.75 | 6.29 |

## Run selection (which NBM run each checkpoint used)

- `d0_0800`: 01Z 0%, 06Z 8%, 07Z 92%, 10Z 0%, 11Z 0%, 12Z 0%; median lead to 15:00 local on D = 13 h
- `d1_1800`: 13Z 0%, 18Z 8%, 19Z 92%; median lead to 15:00 local on D = 25 h
