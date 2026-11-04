# M1 validation: rebuilt daily max vs. settled Polymarket winners

Generated 2026-11-03. Settled events with a single winner: 1582.

| station | era | n | all-reports °F | routine-only °F | METAR rule |
|---|---|---|---|---|---|
| KATL | metar | 11 | 100.0% | 100.0% | 100.0% |
| KATL | nws_ts | 61 | 100.0% | 100.0% | 100.0% |
| KATL | wu | 255 | 100.0% | 98.0% | 98.0% |
| KDAL | metar | 11 | 100.0% | 100.0% | 100.0% |
| KDAL | nws_ts | 61 | 100.0% | 100.0% | 100.0% |
| KDAL | wu | 258 | 100.0% | 99.6% | 99.6% |
| KLGA | metar | 11 | 100.0% | 100.0% | 100.0% |
| KLGA | nws_ts | 61 | 100.0% | 98.4% | 98.4% |
| KLGA | wu | 570 | 99.8% | 98.2% | 98.2% |
| KMIA | metar | 11 | 100.0% | 100.0% | 100.0% |
| KMIA | nws_ts | 61 | 98.4% | 98.4% | 98.4% |
| KMIA | wu | 211 | 100.0% | 98.6% | 98.6% |

Expected rule per era: wu and nws_ts → all-reports; metar → METAR rule.

## Mismatches under the expected rule

| station | date | era | winner | rebuilt | value |
|---|---|---|---|---|---|
| KMIA | 2026-09-02 | nws_ts | 90-91°F | 88-89°F | 89 |
| KLGA | 2025-03-07 | wu | 45-46°F | 49°F or higher | 50 |
