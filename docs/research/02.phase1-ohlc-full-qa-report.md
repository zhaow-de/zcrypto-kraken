# OHLC Dataset QA Report

As of: 2026-07-07T21:33:30.315688+00:00

| Series | Rows | Coverage % | Gaps | Missing candles | Wick outliers | Monotonic ts | Nonneg volume |
| --- | ---: | ---: | ---: | ---: | ---: | :---: | :---: |
| ADA/EUR/1440 | 2742 | 100.00 | 0 | 0 | 88 | True | True |
| ADA/EUR/240 | 16446 | 99.98 | 3 | 3 | 34 | True | True |
| ADA/EUR/60 | 65623 | 99.74 | 131 | 172 | 25 | True | True |
| AVAX/EUR/1440 | 1562 | 100.00 | 0 | 0 | 34 | True | True |
| AVAX/EUR/240 | 9365 | 99.96 | 4 | 4 | 13 | True | True |
| AVAX/EUR/60 | 37157 | 99.16 | 264 | 316 | 8 | True | True |
| BTC/EUR/1440 | 4581 | 99.89 | 4 | 5 | 66 | True | True |
| BTC/EUR/240 | 27332 | 99.35 | 62 | 179 | 39 | True | True |
| BTC/EUR/60 | 108786 | 98.86 | 273 | 1255 | 27 | True | True |
| DOGE/EUR/1440 | 2295 | 100.00 | 0 | 0 | 134 | True | True |
| DOGE/EUR/240 | 13710 | 99.59 | 51 | 57 | 117 | True | True |
| DOGE/EUR/60 | 53237 | 96.68 | 1019 | 1829 | 94 | True | True |
| DOT/EUR/1440 | 2052 | 100.00 | 0 | 0 | 67 | True | True |
| DOT/EUR/240 | 12306 | 99.98 | 2 | 2 | 25 | True | True |
| DOT/EUR/60 | 49181 | 99.90 | 28 | 50 | 22 | True | True |
| ETH/BTC/1440 | 3679 | 99.95 | 1 | 2 | 68 | True | True |
| ETH/BTC/240 | 22057 | 99.87 | 7 | 28 | 31 | True | True |
| ETH/BTC/60 | 88174 | 99.82 | 31 | 163 | 27 | True | True |
| ETH/EUR/1440 | 3890 | 100.00 | 0 | 0 | 152 | True | True |
| ETH/EUR/240 | 23292 | 99.80 | 37 | 46 | 78 | True | True |
| ETH/EUR/60 | 92294 | 98.87 | 572 | 1055 | 41 | True | True |
| LINK/EUR/1440 | 2380 | 100.00 | 0 | 0 | 71 | True | True |
| LINK/EUR/240 | 14267 | 99.93 | 9 | 10 | 32 | True | True |
| LINK/EUR/60 | 56518 | 98.97 | 426 | 589 | 21 | True | True |
| LTC/EUR/1440 | 4542 | 99.13 | 10 | 40 | 193 | True | True |
| LTC/EUR/240 | 26746 | 97.29 | 365 | 744 | 110 | True | True |
| LTC/EUR/60 | 99565 | 90.55 | 4378 | 10395 | 84 | True | True |
| SOL/BTC/1440 | 1749 | 100.00 | 0 | 0 | 27 | True | True |
| SOL/BTC/240 | 10487 | 99.96 | 4 | 4 | 15 | True | True |
| SOL/BTC/60 | 41839 | 99.71 | 86 | 122 | 11 | True | True |
| SOL/EUR/1440 | 1749 | 100.00 | 0 | 0 | 55 | True | True |
| SOL/EUR/240 | 10486 | 99.95 | 4 | 5 | 27 | True | True |
| SOL/EUR/60 | 41918 | 99.90 | 13 | 43 | 16 | True | True |
| XRP/EUR/1440 | 3239 | 99.97 | 1 | 1 | 170 | True | True |
| XRP/EUR/240 | 19423 | 99.93 | 5 | 14 | 105 | True | True |
| XRP/EUR/60 | 77653 | 99.88 | 17 | 92 | 70 | True | True |

## Summary

- Series count: 36
- Total gaps: 7807
- Min coverage %: 90.55

## Gap characterization

Summary: {'series_count': 36, 'total_gaps': 7807, 'min_coverage_pct': 90.5465623863223}

**Lowest-coverage series (no-trade intervals — thin markets / early history):**

| Series | Coverage % | Gaps | Missing candles |
| --- | ---: | ---: | ---: |
| LTC/EUR/60 | 90.55 | 4378 | 10395 |
| DOGE/EUR/60 | 96.68 | 1019 | 1829 |
| LTC/EUR/240 | 97.29 | 365 | 744 |
| BTC/EUR/60 | 98.86 | 273 | 1255 |
| ETH/EUR/60 | 98.87 | 572 | 1055 |
| LINK/EUR/60 | 98.97 | 426 | 589 |
| LTC/EUR/1440 | 99.13 | 10 | 40 |
| AVAX/EUR/60 | 99.16 | 264 | 316 |

**Per-year bar density (data density across §9 regimes):**

- **BTC/EUR 1h** (theoretical ~8760/yr): 2013:18%, 2014:100%, 2015:100%, 2016:100%, 2017:100%, 2018:99%, 2019:100%, 2020:100%, 2021:100%, 2022:100%, 2023:100%, 2024:100%, 2025:100%, 2026:25%
- **DOT/EUR 1d** (theoretical ~365/yr): 2020:37%, 2021:100%, 2022:100%, 2023:100%, 2024:100%, 2025:100%, 2026:25%

_No-trade intervals are genuinely absent (Kraken omits them); they are reported, not filled. 1h/4h coverage is lowest in early/thin periods — relevant to which §9 walk-forward regimes carry reliable intraday density._
