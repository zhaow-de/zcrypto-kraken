# B1 trial 3 — hourly realized-volatility inverse weights on the adopted A2-4h ensemble (design)

**Ruling:** the owner, attended, 2026-10-15: "back to T0022, go with candidate A, keyed to B1", and four answers — "Frozen ohlc-full (Recommended)", "B1's family dispersion (Recommended)", "Hourly (Recommended)", "Any reduction (Recommended)" — and two more on the author's points, "Arm A stands in (Recommended)" and "Both blocks, as A did (Recommended)" — the pick and the six answers verbatim, each answer with its question, in `docs/research/10.phase4-decisions.md`'s three `[iter-177]` entries; the DSR leg binds by the owner's ruling recorded as the first `[iter-176]` entry there. **Iteration:** iter-177. **Topic:** T0022 under the T0016 umbrella. **Goal:** pre-register B1's third trial — candidate A of the survey `docs/research/10.phase4-b1-candidate-hypotheses.md` (its `### A`, lines 40–60, with the shortlist's common items, lines 29–38, and the common decisions, lines 98–102) — as numbered decisions with code-level definitions: a module computing the hourly realized-volatility inverse weights and arm B's book, a committed research subject that builds both arms and registers the trial through `zcrypto research eval`, its evaluate-only pre-flight twin, and trial 3, run on the owner's word after the plan review. This spec spends one trial of Bucket B's shared budget when trial 3 runs: 23 remain today, 22 after.

## The measured basis

Every command below ran on 2026-10-15 between 13:40 and 13:50Z in this branch's worktree at `8c65e4777`, with `data/ohlc-full` linked from the main checkout's `data/`. The two scripts are scratch under `.tmp/b1-trial3/`, never committed; they read stamps and closes, compare closes for equality, and compute no return of any series. The plan's basis test commits what they measure about the reads (D4).

- **The ten EUR assets' 60 and 240 files, and the seam between them** — for each asset, the rows, first and last stamp, density over the asset's own span, stamps off the interval's grid, the largest gap, synthetic (`count == 0`) rows and null closes per file; the lowest calendar-year hourly density; and, joining every 4h bar `T` with the hourly bars whose open lies in `[T, T + 4h)`, whether the 4h close equals the close of the last present hourly bar there:

```
$ uv run python .tmp/b1-trial3/measure_files.py data
ADA 60: rows 65623, first 2018-09-28 13:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 65795, density 0.9974, off-grid stamps 0, largest gap 7:00:00 ending 2024-04-14 09:00:00+00:00, gaps>step 131, count==0 rows 0, null closes 0, min close 0.018853
ADA 240: rows 16446, first 2018-09-28 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 16449, density 0.9998, off-grid stamps 0, largest gap 8:00:00 ending 2024-01-20 20:00:00+00:00, gaps>step 3, count==0 rows 0, null closes 0, min close 0.0202
ADA 60: lowest calendar-year density 0.9882 in 2019 (8657 of 8760 hours)
ADA seam: 4h bars 16446; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 16446 agree, 0 disagree; of them with the T+3h bar present: 16407, 16407 agree, 0 disagree; hourly bars per 4h bar {1: 3, 2: 15, 3: 122, 4: 16306}
AVAX 60: rows 37157, first 2021-12-21 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 37473, density 0.9916, off-grid stamps 0, largest gap 6:00:00 ending 2023-06-03 05:00:00+00:00, gaps>step 264, count==0 rows 0, null closes 0, min close 6.97
AVAX 240: rows 9365, first 2021-12-21 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 9369, density 0.9996, off-grid stamps 0, largest gap 8:00:00 ending 2023-06-03 04:00:00+00:00, gaps>step 4, count==0 rows 0, null closes 0, min close 6.97
AVAX 60: lowest calendar-year density 0.9842 in 2023 (8622 of 8760 hours)
AVAX seam: 4h bars 9365; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 9365 agree, 0 disagree; of them with the T+3h bar present: 9274, 9274 agree, 0 disagree; hourly bars per 4h bar {1: 8, 2: 18, 3: 243, 4: 9096}
BTC 60: rows 108786, first 2013-09-10 23:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 110041, density 0.9886, off-grid stamps 0, largest gap 3 days, 2:00:00 ending 2013-09-28 18:00:00+00:00, gaps>step 273, count==0 rows 0, null closes 0, min close 81.0
BTC 240: rows 27332, first 2013-09-10 20:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 27511, density 0.9935, off-grid stamps 0, largest gap 3 days, 0:00:00 ending 2013-09-28 16:00:00+00:00, gaps>step 62, count==0 rows 0, null closes 0, min close 82.0
BTC 60: lowest calendar-year density 0.5827 in 2013 (1567 of 2689 hours)
BTC seam: 4h bars 27332; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 27332 agree, 0 disagree; of them with the T+3h bar present: 27197, 27197 agree, 0 disagree; hourly bars per 4h bar {1: 104, 2: 69, 3: 92, 4: 27067}
DOGE 60: rows 53237, first 2019-12-19 14:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 55066, density 0.9668, off-grid stamps 0, largest gap 14:00:00 ending 2020-04-12 08:00:00+00:00, gaps>step 1019, count==0 rows 0, null closes 0, min close 0.00105
DOGE 240: rows 13710, first 2019-12-19 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 13767, density 0.9959, off-grid stamps 0, largest gap 16:00:00 ending 2020-04-12 08:00:00+00:00, gaps>step 51, count==0 rows 0, null closes 0, min close 0.0013139
DOGE 60: lowest calendar-year density 0.4362 in 2019 (130 of 298 hours)
DOGE seam: 4h bars 13710; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 13710 agree, 0 disagree; of them with the T+3h bar present: 13279, 13279 agree, 0 disagree; hourly bars per 4h bar {1: 157, 2: 315, 3: 502, 4: 12736}
DOT 60: rows 49181, first 2020-08-18 17:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 49231, density 0.9990, off-grid stamps 0, largest gap 7:00:00 ending 2024-04-14 09:00:00+00:00, gaps>step 28, count==0 rows 0, null closes 0, min close 1.0336
DOT 240: rows 12306, first 2020-08-18 16:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 12308, density 0.9998, off-grid stamps 0, largest gap 8:00:00 ending 2024-04-14 08:00:00+00:00, gaps>step 2, count==0 rows 0, null closes 0, min close 1.0404
DOT 60: lowest calendar-year density 0.9972 in 2020 (3238 of 3247 hours)
DOT seam: 4h bars 12306; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 12306 agree, 0 disagree; of them with the T+3h bar present: 12295, 12295 agree, 0 disagree; hourly bars per 4h bar {1: 2, 2: 5, 3: 27, 4: 12272}
ETH 60: rows 92294, first 2015-08-07 11:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 93349, density 0.9887, off-grid stamps 0, largest gap 17:00:00 ending 2018-01-13 11:00:00+00:00, gaps>step 572, count==0 rows 0, null closes 0, min close 0.364
ETH 240: rows 23292, first 2015-08-07 08:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 23338, density 0.9980, off-grid stamps 0, largest gap 16:00:00 ending 2015-10-04 08:00:00+00:00, gaps>step 37, count==0 rows 0, null closes 0, min close 0.36965
ETH 60: lowest calendar-year density 0.7541 in 2015 (2652 of 3517 hours)
ETH seam: 4h bars 23292; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 23292 agree, 0 disagree; of them with the T+3h bar present: 23079, 23079 agree, 0 disagree; hourly bars per 4h bar {1: 76, 2: 169, 3: 308, 4: 22739}
LINK 60: rows 56518, first 2019-09-25 13:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 57107, density 0.9897, off-grid stamps 0, largest gap 9:00:00 ending 2019-12-22 08:00:00+00:00, gaps>step 426, count==0 rows 0, null closes 0, min close 1.41194
LINK 240: rows 14267, first 2019-09-25 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 14277, density 0.9993, off-grid stamps 0, largest gap 12:00:00 ending 2019-12-22 08:00:00+00:00, gaps>step 9, count==0 rows 0, null closes 0, min close 1.44403
LINK 60: lowest calendar-year density 0.8794 in 2019 (2057 of 2339 hours)
LINK seam: 4h bars 14267; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 14267 agree, 0 disagree; of them with the T+3h bar present: 14111, 14111 agree, 0 disagree; hourly bars per 4h bar {1: 21, 2: 84, 3: 319, 4: 13843}
LTC 60: rows 99565, first 2013-09-14 08:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 109960, density 0.9055, off-grid stamps 0, largest gap 15 days, 9:00:00 ending 2013-10-26 20:00:00+00:00, gaps>step 4378, count==0 rows 0, null closes 0, min close 1.0
LTC 240: rows 26746, first 2013-09-14 08:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 27490, density 0.9729, off-grid stamps 0, largest gap 15 days, 12:00:00 ending 2013-10-26 20:00:00+00:00, gaps>step 365, count==0 rows 0, null closes 0, min close 1.0
LTC 60: lowest calendar-year density 0.4367 in 2013 (1139 of 2608 hours)
LTC seam: 4h bars 26746; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 26746 agree, 0 disagree; of them with the T+3h bar present: 24861, 24861 agree, 0 disagree; hourly bars per 4h bar {1: 940, 2: 1382, 3: 1835, 4: 22589}
SOL 60: rows 41918, first 2021-06-17 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 41961, density 0.9990, off-grid stamps 0, largest gap 13:00:00 ending 2021-06-25 21:00:00+00:00, gaps>step 13, count==0 rows 0, null closes 0, min close 7.75
SOL 240: rows 10486, first 2021-06-17 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 10491, density 0.9995, off-grid stamps 0, largest gap 12:00:00 ending 2021-06-25 20:00:00+00:00, gaps>step 4, count==0 rows 0, null closes 0, min close 8.22
SOL 60: lowest calendar-year density 0.9964 in 2021 (4720 of 4737 hours)
SOL seam: 4h bars 10486; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 10486 agree, 0 disagree; of them with the T+3h bar present: 10480, 10480 agree, 0 disagree; hourly bars per 4h bar {1: 2, 2: 4, 3: 12, 4: 10468}
XRP 60: rows 77653, first 2017-05-18 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, grid 77745, density 0.9988, off-grid stamps 0, largest gap 1 day, 20:00:00 ending 2018-01-13 11:00:00+00:00, gaps>step 17, count==0 rows 0, null closes 0, min close 0.11076
XRP 240: rows 19423, first 2017-05-18 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, grid 19437, density 0.9993, off-grid stamps 0, largest gap 1 day, 20:00:00 ending 2018-01-13 08:00:00+00:00, gaps>step 5, count==0 rows 0, null closes 0, min close 0.114999
XRP 60: lowest calendar-year density 0.9937 in 2018 (8705 of 8760 hours)
XRP seam: 4h bars 19423; with no hourly bar 0; hourly buckets with no 4h bar 0; 4h close == close of the last present hourly bar: 19423 agree, 0 disagree; of them with the T+3h bar present: 19417, 19417 agree, 0 disagree; hourly bars per 4h bar {1: 5, 2: 6, 3: 12, 4: 19400}
TOTAL {'h4': 173373, 'h1': 681932, 'agree': 173373, 'disagree': 0, 'no_hourly': 0, 'no_4h': 0, 'third': 170400, 'third_agree': 170400}
```

- **The trial's reads through one `ObservedReader`, the union, the blocks, and the hourly density by year** — the 4h union exactly as records 45 and 46's subjects read it (`_capturing_union(reader, "ohlc-full", 240, None, None, False)`), its block, then the ten 60 files read whole through the same reader, its block; per-year hourly density over each asset's own span; two facts of the DSR code:

```
$ uv run python .tmp/b1-trial3/measure_block.py data
union: 27338 stamps, 27337 return indices, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00; steps other than 4h: 63, largest (datetime.timedelta(days=3), datetime.datetime(2013, 9, 28, 16, 0, tzinfo=zoneinfo.ZoneInfo(key='UTC')))
union ADA: first present index 10891 (2018-09-28 12:00:00+00:00), None after it 1
union AVAX: first present index 17971 (2021-12-21 12:00:00+00:00), None after it 2
union BTC: first present index 0 (2013-09-10 20:00:00+00:00), None after it 6
union DOGE: first present index 13573 (2019-12-19 12:00:00+00:00), None after it 55
union DOT: first present index 15032 (2020-08-18 16:00:00+00:00), None after it 0
union ETH: first present index 4010 (2015-08-07 08:00:00+00:00), None after it 36
union LINK: first present index 13063 (2019-09-25 12:00:00+00:00), None after it 8
union LTC: first present index 6 (2013-09-14 08:00:00+00:00), None after it 586
union SOL: first present index 16849 (2021-06-17 12:00:00+00:00), None after it 3
union XRP: first present index 7910 (2017-05-18 12:00:00+00:00), None after it 5
block over the 240 reads: ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 173373 ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'] 10
block over the 240 and 60 reads: 8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1 855305 ['2013-09-10 20:00:00+00:00', '2026-03-31 23:00:00+00:00'] 20
  ADA/EUR/240.parquet 0646c3579ae296300943cecc472962e642416dd874db486d84546303f398bdd9
  ADA/EUR/60.parquet 7f874067a371b3b9505e17c1d066d190b7306cf8c0efcfec7feea25a9934e9c7
  AVAX/EUR/240.parquet 3b06646600836928ab5ce54525ae7b48691e2f65859796e35e531317879f22bd
  AVAX/EUR/60.parquet 2396d2bd5cd6ccf34c98e3d110c81f8f1b9f9235492fdd11ee269ca1112e4a48
  BTC/EUR/240.parquet 1cdfcb3cab6379349c56dce38043cf6a83a34adb5c754eaa303536141c9df0d9
  BTC/EUR/60.parquet 569e794674d97aee9d04de3706b3b447d5f88612daa3723ec8826ae6e7c6d25a
  DOGE/EUR/240.parquet 1567307d3b3464f704d1da348b48faf532cee844489562b112eb7df9c2c9cd7b
  DOGE/EUR/60.parquet 367d8a32572a3df740cdadbcfed8f0bc0807724d164ed5b88bc1fe8960f1f5ea
  DOT/EUR/240.parquet 35f4373ec470d56626253ba2427d825dab8862766ad5b7b08e54ca1a12405a89
  DOT/EUR/60.parquet c66689bd1b3ad9627ad06d63e57c63ad160688d7dee598cffe1a9b3cdba53a65
  ETH/EUR/240.parquet daf47dd3a323aa4e0ef72e61b8b18293b71cc4be774d4af430833d3d275278f3
  ETH/EUR/60.parquet 21d3d1d82500f03b60ad00e07e2536b26f798c4ea135a644b47d5f19c314ab0b
  LINK/EUR/240.parquet 596ffa28ca7f8435061dbd97ae501d3d6915caba32cb1f4f88198bf180100e8f
  LINK/EUR/60.parquet 47069eaec298e6d6ddcf172bbe12f011d32a50a46723a42c56534dc783bb5f85
  LTC/EUR/240.parquet c228951dec83ee20159594ca8a2293d2cf70c078e0335458700dc9d369fd5886
  LTC/EUR/60.parquet df5c9b3277f406557a8c29af47ea057a23584d5b563df64eed4afee00daec25d
  SOL/EUR/240.parquet 8f6bccc064a117ccf1c278a226be289f99227acdf71744a8cf732d7f8897ec25
  SOL/EUR/60.parquet 3b57529f65cac7f3005173be41403b1ae06794c3e131d1014560fcfd5f6ba24a
  XRP/EUR/240.parquet c80e235477a82b9bf513440893d14668b2c6ca962027dc5b4e30f35d4d44abaa
  XRP/EUR/60.parquet 28d8aac39d8ee1f45419760bf186622cd2eb315f0a075aef610c64ea7b99a0f4
density % ADA: 2018 99.29, 2019 98.82, 2020 99.76, 2021 99.92, 2022 100.00, 2023 99.97, 2024 99.85, 2025 99.90, 2026 100.00
density % AVAX: 2021 100.00, 2022 98.76, 2023 98.42, 2024 99.68, 2025 99.66, 2026 99.49
density % BTC: 2013 58.27, 2014 99.59, 2015 99.98, 2016 99.90, 2017 99.98, 2018 99.41, 2019 99.97, 2020 99.98, 2021 99.93, 2022 100.00, 2023 99.99, 2024 99.87, 2025 99.90, 2026 100.00
density % DOGE: 2019 43.62, 2020 81.47, 2021 99.93, 2022 99.99, 2023 99.99, 2024 99.84, 2025 99.87, 2026 100.00
density % DOT: 2020 99.72, 2021 99.93, 2022 99.99, 2023 99.94, 2024 99.81, 2025 99.86, 2026 100.00
density % ETH: 2015 75.41, 2016 98.83, 2017 99.92, 2018 99.46, 2019 99.97, 2020 99.99, 2021 99.93, 2022 99.99, 2023 99.99, 2024 99.86, 2025 99.90, 2026 100.00
density % LINK: 2019 87.94, 2020 98.19, 2021 99.93, 2022 99.83, 2023 99.17, 2024 99.57, 2025 99.82, 2026 100.00
density % LTC: 2013 43.67, 2014 73.61, 2015 60.10, 2016 69.74, 2017 95.91, 2018 99.36, 2019 99.89, 2020 99.91, 2021 99.93, 2022 100.00, 2023 99.99, 2024 99.85, 2025 99.90, 2026 100.00
density % SOL: 2021 99.64, 2022 99.99, 2023 99.97, 2024 99.85, 2025 99.90, 2026 100.00
density % XRP: 2017 99.96, 2018 99.37, 2019 99.97, 2020 99.98, 2021 99.93, 2022 100.00, 2023 99.99, 2024 99.84, 2025 99.90, 2026 100.00
expected_max_sharpe(3, 1.0) = 0.8528044961506948
dsr_pass at var_trials 0.0 over 27337 returns needs a per-period Sharpe above 0.009949 (annualised 0.4656)
```

- **Records 45 and 46, the two B1 trials the dispersion reads** — their registered arm-B per-period Sharpe and the arm-A and benchmark figures the arm-A pre-flight reproduces (D7):

```
$ sed -n '45,46p' docs/reference/trial-registry.jsonl | python3 -c 'import json, sys
for line in sys.stdin:
    r = json.loads(line); m = r["metrics"]
    print(r["trial_id"], r["family"], r["n_trials_in_family"], r["verdict"], m["per_period_sharpe_4h"], m["arm_a_ann_sharpe_noc"], m["arm_a_ann_sharpe_noc_decisive"], m["arm_a_max_drawdown"], m["turnover_a"], m["arm_a_spot_drag_pct_yr"], m["benchmark_ann_sharpe_noc"], m["benchmark_ann_sharpe_noc_decisive"], m["dsr_pass"])'
45 B1 1 reject 0.02374 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 1
46 B1 2 reject 0.02959 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 1
```

- **Where the code the design rests on lives**:

```
$ git grep -n -E '^def (_inverse_vol_weights|a2_book_returns|vol_target|a1_kill_bar|net_of_cost_verdict|calendar_year_slices|benchmark_4h_net_of_cost|_ffill_btc|book_turnover|net_of_cost|_capturing_union|_b1_refuse_window|_b1_metrics|aggregate_minutes|expected_max_sharpe|deflated_sharpe_ratio|sharpe)\(' -- cli/
cli/alpha/a1.py:164:def _inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]:
cli/alpha/a2.py:114:def a2_book_returns(prices_by_asset: dict[str, list[float | None]], *, config: A2Config) -> dict:
cli/alpha/b1.py:210:def book_turnover(asset_positions: dict[str, list[float]]) -> float:
cli/alpha/b2.py:252:def net_of_cost(
cli/alpha/killbar.py:14:def a1_kill_bar(
cli/alpha/killbar.py:151:def net_of_cost_verdict(
cli/backfill/aggregate.py:4:def aggregate_minutes(minute_rows: list[list], interval_secs: int) -> list[list]:
cli/benchmark/strategies.py:16:def vol_target(returns: list[float], *, target_vol: float, lookback: int, max_leverage: float = 1.0) -> list[float]:
cli/portfolio/crossfreq_system.py:199:def _ffill_btc(prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
cli/portfolio/record43_book.py:199:def net_of_cost(positions: dict[str, list[float]], returns: dict[str, list[float]], n: int) -> tuple[list[float], list[float]]:
cli/portfolio/record44_legs.py:64:def benchmark_4h_net_of_cost(h4_prices: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]:
cli/portfolio/record44_legs.py:108:def calendar_year_slices(returns: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
cli/research/subjects.py:93:def _capturing_union(
cli/research/subjects.py:526:def _b1_refuse_window(subject: str, h4_ts: list[datetime], window: tuple[str, str] | None) -> None:
cli/research/subjects.py:560:def _b1_metrics(
cli/validation/dsr.py:12:def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
cli/validation/dsr.py:53:def deflated_sharpe_ratio(
cli/validation/metrics.py:26:def sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float:
$ git grep -n -E '^GRID_INTERVALS|^_B1_[A-Z0-9_]+ =|^STUB_YEARS|^DSR_PASS_THRESHOLD|k16 = ' -- cli/
cli/alpha/killbar.py:11:DSR_PASS_THRESHOLD = 0.95
cli/engine/store.py:42:GRID_INTERVALS = (1440, 240)
cli/portfolio/record44_legs.py:31:STUB_YEARS = (2013, 2026)  # partial-year slices, excluded from the worst-slice leg
cli/research/subjects.py:516:_B1_COST_PER_SIDE = 0.006
cli/research/subjects.py:517:_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
cli/research/subjects.py:518:_B1_LOOKBACK = 180
cli/research/subjects.py:519:_B1_DECISIVE_START = 1380
cli/research/subjects.py:520:_B1_N_RESAMPLES = 2000
cli/research/subjects.py:521:_B1_FROM_2016 = datetime(2016, 1, 1, tzinfo=UTC)
cli/research/subjects.py:523:_B1_GRID = ((30, 7), (30, 1234), (102, 42))
cli/research/subjects.py:613:    k16 = next(k for k in range(n) if h4_ts[k] >= _B1_FROM_2016)
```

- **Arm A's weight estimator, its window and its eligibility** (`cli/alpha/a1.py:172-183`, `:187-188`):

```
$ sed -n '172,183p;187,188p' cli/alpha/a1.py
    for t in range(length - 1):
        inv_weights: dict[str, float] = {}
        if t >= lookback:
            for asset, rets in returns_by_asset.items():
                if rets[t] is None:
                    continue
                window = rets[t - lookback : t]
                if any(r is None for r in window):
                    continue
                vol = statistics.stdev(window)
                if vol > 0:
                    inv_weights[asset] = 1.0 / vol
        total = sum(inv_weights.values())
        weights.append({asset: inv / total for asset, inv in inv_weights.items()})
```

- **Where the weights enter A2's book, the vol target, the bar stamps, the kill bar's DSR leg, the slices** (`cli/alpha/a2.py:128`, `:141-150`; `cli/benchmark/strategies.py:34-39`; `cli/backfill/aggregate.py:9-11`, `:16-19`; `cli/alpha/killbar.py:69-72`, `:110`; `cli/validation/dsr.py:20-21`, `:27`, `:46-50`; `cli/portfolio/record44_legs.py:115`, `:31`):

```
$ sed -n '128p;141,150p' cli/alpha/a2.py; echo ---; sed -n '34,39p' cli/benchmark/strategies.py; echo ---; sed -n '9,11p;16,19p' cli/backfill/aggregate.py; echo ---; sed -n '69,72p;110p' cli/alpha/killbar.py; echo ---; sed -n '20,21p;27p;46,50p' cli/validation/dsr.py; echo ---; sed -n '115p' cli/portfolio/record44_legs.py; sed -n '31p' cli/portfolio/record44_legs.py
    weights = _inverse_vol_weights(prices_by_asset, lookback=config.basket_lookback)
    positions = vol_target(
        book_base_returns,
        target_vol=config.target_vol / math.sqrt(config.periods_per_year),
        lookback=config.vol_lookback,
        max_leverage=config.max_leverage,
    )
    asset_positions: dict[str, list[float]] = {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * positions[k] for k in range(length - 1)]
        for asset in prices_by_asset
    }
---
    for t in range(len(returns)):
        if t < lookback:
            positions.append(0.0)
            continue
        rv = statistics.stdev(returns[t - lookback : t])
        positions.append(min(target_vol / rv, max_leverage) if rv > 0 else 0.0)
---
    buckets: dict[int, list[list]] = {}
    for ts, o, h, l, c, v, n in minute_rows:
        bucket_ts = ts // interval_secs * interval_secs
        rows = sorted(buckets[bucket_ts], key=lambda r: r[0])
        open_ = float(rows[0][1])
        close = float(rows[-1][4])
        high = max(float(r[2]) for r in rows)
---
        sr = sharpe(book_net_returns)
        dsr = deflated_sharpe_ratio(sr, n_obs, n_trials, var_trials)
        # dsr is a probability P(true SR > deflated benchmark); ratified bar is dsr > DSR_PASS_THRESHOLD (0.95).
        dsr_pass = dsr > DSR_PASS_THRESHOLD
    passes = dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass
---
    if n_trials == 1 or var_trials == 0:
        return 0.0
    return math.sqrt(var_trials) * ((1 - g) * _NORM.inv_cdf(p1) + g * _NORM.inv_cdf(p2))
    denom = 1 - skew * sr + (kurtosis - 1) / 4 * sr**2
    if denom <= 0:
        raise ValidationError(f"non-positive Sharpe-SE denominator ({denom}); degenerate skew/kurtosis")
    z = (sr - benchmark_sr) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return _NORM.cdf(z)
---
        year = h4_ts[k + 1].year
STUB_YEARS = (2013, 2026)  # partial-year slices, excluded from the worst-slice leg
```

What the reads establish, each figure from the blocks above:

- **The seam holds on every bar.** All 173,373 4h bars' closes equal the close of the last present hourly bar whose open lies in `[T, T + 4h)`; no 4h bar lacks an hourly bar and no hourly bar lies outside a 4h bar. In 173,373 − 170,400 = 2,973 bars the `T + 3h` hourly bar is absent and the 4h close is an earlier hour's — so "the last hourly bar" is the last present one, never the `T + 3h` stamp. The reconstruction explains it: both grids bucket the same 1-minute rows by `ts // interval_secs * interval_secs` and take the last minute's close, and an empty bucket writes no row (`cli/backfill/aggregate.py:11`, `:18`); no file holds a synthetic `count == 0` row or an off-grid stamp.
- **Hourly density on the 60 files.** Over each asset's own span: from 90.55 % (LTC) to 99.90 % (DOT, SOL). The survey's 88–97 % for AVAX, LINK and DOT came from the 15m set; on the 60 files AVAX reads 98.42–100 % by year, LINK 87.94 % in its partial first year 2019 and 98.19–100 % after, DOT 99.72–100 %. The thin hourly years are early: BTC 2013 58.27 %, LTC 2013–2016 43.67–73.61 %, ETH 2015 75.41 %, DOGE 2019 43.62 % and 2020 81.47 %. Missing hours are frequent enough that the gap rule matters: from 13 (SOL) to 4,378 (LTC) hourly gaps per file; the largest are LTC's 15 days 9 hours ending 2013-10-26 20:00 and BTC's 3 days 2 hours ending 2013-09-28 18:00.
- **The union is records 45 and 46's.** 27,338 stamps, 27,337 return indices, 2013-09-10 20:00 → 2026-03-31 20:00 (spec 00130's measured basis names the same), with 63 steps longer than 4h, the longest 3 days ending 2013-09-28 16:00; BTC is absent at 6 union stamps after its first, the stamps `_ffill_btc` fills (`cli/portfolio/crossfreq_system.py:199-211`). The 240 reads' block is `ff2e5700…`, the block `tests/test_b1_records_reproduce.py` pins for record 46 — this reader reads the bytes those records read.
- **The trial's inputs.** The 240 and 60 reads together form the block whose `compute_hash` is `8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1`: 20 files, 855,305 rows, span 2013-09-10 20:00 → 2026-03-31 23:00.
- **The DSR leg in numbers of the code.** `expected_max_sharpe(3, V)` is `0.8528044961506948 · √V`; at `var_trials` 0.0 a book of 27,337 returns passes the leg above a per-period Sharpe of 0.009949, annualised 0.4656 (spec 00128 D6 gives 0.466 for the same count).

## Hypothesis (trial 3, pre-registered by this spec's sha256)

A held asset's position in each adopted A2 arm is weight × direction × book vol scalar, the weight being 1/σ renormalised over the eligible assets and re-estimated at every boundary from the asset's last 180 four-hour returns (`cli/alpha/a2.py:128`, `:147-150`; `cli/alpha/a1.py:164-189`); one large 4h move shifts σ, and every held asset's position, twice — when it enters the window and 30 days later when it leaves. Hourly realized variance over the same 180 intervals estimates the same quantity from four times the observations, so the weights move less from boundary to boundary and the book trades less to follow them. **Arm B — each adopted arm with its per-asset inverse-volatility weight estimated from the realized variance of hourly log returns over the same 180 four-hour intervals instead of from the standard deviation of the 180 four-hour returns — has a higher mean net-of-cost return than arm A at 0.006 per side (SPA p < 0.05, full window) and lower turnover.** Arms: **A** = the adopted equal-weight three-arm A2-4h ensemble exactly as records 45 and 46 built it; **B** = the same ensemble with the weight estimator alone replaced. One knob, judged by the pre-registered decision matrix (D7). The survey's honest prior stands: about 0.12 that it is adopted, about 0.55 that the point estimate favours B (`docs/research/10.phase4-b1-candidate-hypotheses.md:59`); the known confound is the estimator's per-asset bias against 4h variance, which tilts as well as smooths (`:49`), and engagement items (3) and (4) of D7 say which a result came from.

## D1 — the arms: arm A is records 45 and 46's, arm B swaps the weight estimator alone

- **Arm A** is built as `_b1_metrics` builds it (`cli/research/subjects.py:568-583`): `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B1_A2_ARMS` (`:517`), `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_B1_LOOKBACK, basket_lookback=_B1_LOOKBACK, periods_per_year=PPY_4H))["asset_positions"]` (`:518`, `:62`); arm A is the per-asset `statistics.mean` of the three at every return index (`:583`).
- **Arm B** is the same three configs, each arm's positions from `a2_positions_with_weights(fed, weights_b, config=<that arm's A2Config>)` (D3), with one weight path for the three, `weights_b = hourly_rv_inverse_vol_weights(fed, h4_ts, hourly, lookback=_B1_LOOKBACK)` (D2) — one path because every adopted arm's `basket_lookback` is 180 (`:518`, `:576-577`), so arm A's three arms share one weight path too; averaged per asset per stamp as arm A is.
- Everything else is arm A's: the directions (`_asset_directions_a2`, `cli/alpha/a2.py:81-111`, called at `:126`), the asset returns, the vol target's parameters, the costing (D5). The B1 literals are reused, not restated: `_B1_COST_PER_SIDE`, `_B1_A2_ARMS`, `_B1_LOOKBACK`, `_B1_DECISIVE_START`, `_B1_N_RESAMPLES`, `_B1_FROM_2016` (`cli/research/subjects.py:516-521`) — trial 3 runs B1's protocol, so a change to one of them is a change to all three B1 trials' instrument (spec 00130 D2).
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b2.py`, `cli/portfolio/*`, the engine or any adopted artifact: the new code is one module, `cli/alpha/b1_rv.py` (D2, D3, D7's engagement helpers), and the two subjects (D8). Adoption is a verdict on the A2 ensemble alone; deploying it needs a combination trial over record 47's book (`docs/research/10.phase4-b1-candidate-hypotheses.md:38`; D9).

## D2 — the hourly realized-variance inverse weights

- **Stamps.** Every 4h and 1h stamp in `ohlc-full` is the bar's open: both grids bucket the same 1-minute rows at `ts // interval_secs * interval_secs`, the close being the bucket's last minute's close (`cli/backfill/aggregate.py:11`, `:18`); measured, no stamp lies off its grid. Return index `k` of the 4h union is the move `close[k] → close[k + 1]`, decided at `ts[k] + 4h` (spec 00045 F3; `cli/alpha/b1.py:54-55`, `seasonality_gates`' contract).
- **Arm A's window at return index `t`** is `rets[t − 180 : t]` (`cli/alpha/a1.py:178`): the 180 moves ending at `close[t − 179]`, …, `close[t]`, whose closes fall in `(ts[t − 180] + 4h, ts[t] + 4h]`.
- **Arm B's window at `t`, pinned to arm A's**: the asset's hourly bars whose close stamp `h + 1h` lies in `(ts[t − 180] + 4h, ts[t] + 4h]`, `h` the bar's open stamp — equivalently `ts[t − 180] + 3h < h ≤ ts[t] + 3h`. In code: the close stamps `c[i] = h[i] + timedelta(hours=1)`, `i0 = bisect_right(c, ts[t − lookback] + timedelta(hours=4))`, `i1 = bisect_right(c, ts[t] + timedelta(hours=4))`, the bars `i0 … i1 − 1`. Over 181 union stamps 4h apart these are the hourly bars of the 4h bars `t − 179 … t`, 720 when none is missing; across a union step longer than 4h (63 measured) the window still spans exactly arm A's wall-clock interval, which a count of 720 bars would not. The last close read is at `ts[t] + 4h`, the decision instant and `close[t]`'s own stamp: no look-ahead.
- **The gap-return rule.** Each bar `i` in the window contributes `math.log(close[i] / close[i − 1]) ** 2`, `i − 1` the previous row of the asset's 60 series — the previous present bar, however many hours back and whether or not it lies inside the window or inside the same 4h bar — not demeaned. Under the measured seam the first windowed bar's predecessor is the last present hourly bar whose close stamp is at or before `ts[t − 180] + 4h`, whose close is `close[t − 180]` (for BTC at a stamp `_ffill_btc` fills, the close the fill carries), so the window's hourly log returns telescope to `ln(close[t] / close[t − 180])`, arm A's own span; dropping gap returns instead would discard the moves of every missing hour — up to 4,378 gaps a file (LTC).
- **The estimate and the weight.** `rv = math.fsum(<the window's squared log returns>)` — exactly rounded, so the value does not depend on summation order; `sigma = math.sqrt(rv / lookback)` (realized variance per 4h interval, the survey's divisor 180); `inv = 1.0 / sigma`; the stamp's weights `{asset: inv / total}`, `total = sum(<the stamp's inv values>)`, in `prices_by_asset` order — `cli/alpha/a1.py:187-188`'s form. The divisor cancels in the renormalisation and is kept so `sigma` is the estimator the survey names.
- **Eligibility, read off arm A's weights, never restated.** `weights_a = _inverse_vol_weights(prices_by_asset, lookback=lookback)` is computed inside the function, and arm B weights asset `a` at `t` exactly when `a in weights_a[t]` — the predicate `cli/alpha/a1.py:174-182` applies (`t ≥ 180`, a return at `t`, no missing return in the window, `statistics.stdev` of the window `> 0`), on the same `_ffill_btc` prices; the asset set per stamp is identical across arms by construction. It carries `:176`'s test that the asset has a return at `t`, a read of `close[t + 1]`'s presence that arm A already makes; both arms share it and this trial does not change it.
- **Refusals, never drops.** An asset arm A weights at `t` whose window holds no hourly bar, whose first windowed bar has no predecessor row, or whose `rv` is 0, is refused — `AlphaError` naming the asset and `ts[t]` — since dropping it would break the identical asset set. Under the measured seam none can fire on the frozen set: for every asset but BTC, eligibility needs `close[t − 180]` and `close[t]` present (`cli/alpha/a1.py:176-180`), so the 4h bars `t − 180` and `t` each hold an hourly bar, which gives the predecessor and a windowed bar; BTC reaches the weights through `_ffill_btc`, its first hourly bar closes at `ts[0] + 4h`, at or before every window's lower bound, and its longest hourly gap is 3 days 2 hours, inside any 180-bar window; and `rv = 0` makes every hourly close from the predecessor on equal, hence every 4h close in the window equal and arm A's stdev 0, which arm A does not weight. Input refusals: first the prices, as `_validate_prices_by_asset` refuses them (`cli/alpha/a1.py:192-208`: a price neither `None` nor a finite number above 0, lists of unequal length, BTC absent or holding a `None`) — the validation `a2_book_returns` makes of the same prices (`cli/alpha/a2.py:118`) — since `_inverse_vol_weights` trusts validated prices (`cli/alpha/a1.py:165-167`) and divides by them (`:157-161`); `union_ts` not strictly increasing or tz-naive, or of a length other than the price lists'; an hourly series whose stamps are not strictly increasing or tz-naive, or whose closes are not finite numbers above 0; hourly assets other than the price assets.
- **The function**, in `cli/alpha/b1_rv.py`: `hourly_rv_inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], union_ts: list[datetime], hourly_by_asset: dict[str, tuple[list[datetime], list[float]]], *, lookback: int) -> list[dict[str, float]]` — one dict per return index, `len(union_ts) − 1` of them, `{}` where arm A weights nothing.
- Rejected: 15m sampling (the owner's answer; the survey's reason, `docs/research/10.phase4-b1-candidate-hypotheses.md:46`); a window of the last 720 hourly bars by count (it drifts off arm A's span at every union gap); demeaning (the survey's estimator is the uncentred realized variance of Andersen, Bollerslev, Diebold & Labys).

## D3 — arm B's book: arm A's directions, B's weights, the vol target on B's own book

- `a2_positions_with_weights(prices_by_asset: dict[str, list[float | None]], weights: list[dict[str, float]], *, config: A2Config) -> dict[str, list[float]]` in `cli/alpha/b1_rv.py` is `a2_book_returns`' body (`cli/alpha/a2.py:116-150`) with `weights` in place of `:128`'s call: the config and price validation (`:116-119`); `union_ts` and `asset_ts` (`:121-124`); `directions = _asset_directions_a2(...)` (`:126`); `returns = {a: _asset_returns(p)}` (`:127`); the base return at `k`, `Σ_a weights[k].get(a, 0.0) · d · r` over the assets whose return and direction are both present (`:130-139`); `positions = vol_target(base, target_vol=config.target_vol / math.sqrt(config.periods_per_year), lookback=config.vol_lookback, max_leverage=config.max_leverage)` (`:141-146`, `max_leverage` defaulting to 1.0 at `:36`); and the asset positions `weights[k].get(a, 0.0) · (directions[a][k] or 0.0) · positions[k]` (`:147-150`). It returns the asset positions alone.
- So arm B's book level is A2's own 4h vol target applied to B's own base returns — the 4h estimator over the 180 returns before `t`, `t` excluded (`cli/benchmark/strategies.py:34-39`), capped at 1.0 — the survey's arm B (`docs/research/10.phase4-b1-candidate-hypotheses.md:45`). Applying the hourly estimator to the book vol target too is a park variant (D7), not this trial.
- Identity, held by a test: given `_inverse_vol_weights(prices, lookback=config.basket_lookback)`, it returns `a2_book_returns(prices, config=config)["asset_positions"]` exactly, so the knob is the weights and nothing else. It refuses a `weights` list whose length is not `len(prices) − 1` or a weight keyed by an asset the prices lack (`AlphaError`).

## D4 — the data and the window: the frozen `ohlc-full` set, whole

- `--dataset ohlc-full`, no `--window`, no `--as-of` — the instrument records 45 and 46 fixed, so trial 3 differs from them in its knob alone; the owner's answer to the dataset question (the second `[iter-177]` entry). The set ends 2026-03-31, before the spent holdout's window, 2026-04-01 → 2026-07-09 (`docs/research/13.phase5-holdout-ledger.md:9`): no holdout question arises.
- The reads, in order: the 4h union through `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)` (`cli/research/subjects.py:93-120`) — measured 27,338 stamps, 27,337 return indices; the window refusal `_b1_refuse_window` (`:526-543`); then per asset `reader.read_series(dataset, f"{asset}/EUR/60.parquet", window=window)` (`cli/registry/observed.py:119-155`), its `ts` and `close` columns as the asset's hourly series — whole for the trial, since its window is none; a `--window` evaluation reads both grids under the same bounds, which keeps every bar the weights read (the earliest needed, the predecessor of the first eligible window, lies in the 4h bar at the window's first union stamp). A file it cannot parse, or one with no `close` column, is a `SubjectError` naming `<dataset>/<A>/EUR/60.parquet`, as `_b1_m15` names the 15m set's (`:546-557`).
- An `--as-of` read is refused with a `SubjectError` before any read: the subject reads a frozen set's two grids, and an `ohlc-rolling` instrument for this estimator is a later pre-registration's.
- The inputs' identity is the block the measured basis names: `8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1` over the 20 files, its ten 240 files the block `ff2e5700…` records 45 and 46 read. The plan's data-gated basis test reproduces it, the union's shape, the hourly rows and the seam from the subject's reads half, computing no weight.
- The decisive window starts at return index 1380 (`_B1_DECISIVE_START`), the from-2016 cut at the first `k` with `h4_ts[k] ≥ 2016-01-01T00:00Z` (`cli/research/subjects.py:612-613`, the bar-start convention of `[iter-086]`'s fold assignment that records 45 and 46 read); the per-year engagement figure (D7) keys a return index by the same bar-start year (`cli/alpha/b1.py:187-197`).

## D5 — the costing, the benchmark and the slices: records 45 and 46's

- `returns = {a: _asset_returns(fed[a])}` (`cli/research/subjects.py:584`); each arm's net through `net_of_cost(arm, returns, cost_per_side=_B1_COST_PER_SIDE)` (`cli/alpha/b2.py:252-273`: per-asset turnover from flat, a missing return read as 0.0), arm B's stressed series through the same at `1.5 * _B1_COST_PER_SIDE` (`cli/research/subjects.py:586`, `:591-592`) — never `a2_book_returns`' `net_returns`, which is uncosted.
- The benchmark: `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B1_COST_PER_SIDE)` on the raw union prices (`cli/portfolio/record44_legs.py:64`; `cli/research/subjects.py:593`).
- The slices: `calendar_year_slices(series, h4_ts)`, each return keyed by its close year `h4_ts[k + 1].year`, 2013 and 2026 dropped (`cli/portfolio/record44_legs.py:108-119`, `:31`).

## D6 — `var_trials`: B1's family dispersion, two-pass, from the registered Sharpes

- **The source** of records 45 and 46's arm-B per-period Sharpes is the registry: their `per_period_sharpe_4h`, 0.02374 and 0.02959 (`docs/reference/trial-registry.jsonl:45`, `:46`, measured above), held in the subject as the literal `_B1_RECORDED_PER_PERIOD_SHARPES = (0.02374, 0.02959)` and pinned by an ungated test against the committed records. This is the A family's convention — trial 34's DSR took "var_trials from the 32 recorded per-period Sharpes" (`docs/research/13.phase5-decisions.md:84`), trial 43's "variance(the 33 recorded A1 daily per-period Sharpes)/6" (`:122`) — and `tests/test_b1_records_reproduce.py` already proves the committed subjects `b1-conditioning` and `b1-window-only` reproduce both values at the five decimals the registry stores.
- **The arithmetic.** `per_period_sharpe_4h = sharpe(net_b)` — unannualised (`cli/validation/metrics.py:26-40`), the per-period Sharpe `a1_kill_bar` deflates (`cli/alpha/killbar.py:69-70`) — then `var_trials = statistics.variance([0.02374, 0.02959, per_period_sharpe_4h])`, the sample variance over three (denominator 2), the `statistics.variance` of the A family's two-pass (`docs/research/10.phase4-decisions.md:50`). All three Sharpes are 4h per-period over the same 27,337 returns, so no periodicity conversion applies (`[iter-074]`'s ÷6 converts a daily family's dispersion to 4h, `:158`).
- **The two passes.** The first builds arm B and its per-period Sharpe; the second calls arm B's bar of D7 with `n_trials=3` and that `var_trials`; arm A's bar takes `arm_a_var_trials` (below). Records 45 and 46 keep their registered bars at `var_trials` 0.0: the registry is append-only and nothing re-verdicts them.
- **What it does to the leg**, from the code: `dsr_pass` holds exactly when `Φ((sr − 0.8528044961506948 · √var_trials) · √27,336 / √(1 + sr² / 2)) > 0.95`, `sr` arm B's per-period Sharpe — `expected_max_sharpe` at `n_trials` 3 (`cli/validation/dsr.py:20-27`) and the PSR at the kill bar's default moments, skew 0 and kurtosis 3 (`:46-50`; `cli/alpha/killbar.py:70` passes none). At `var_trials` 0.0 the leg asks a per-period Sharpe above 0.009949; a positive dispersion raises the bar by about `0.8528 · √var_trials`. Neither the variance nor the bar's figure is computed here.
- **Arm A's pre-flight bar** (D7) takes `arm_a_var_trials = statistics.variance([0.02374, 0.02959, sharpe(net_a)])` — arm A standing in arm B's place as the family's third — because arm B's Sharpe does not exist before the run and the pre-flight computes none of arm B's returns.
- Rejected: re-deriving the two Sharpes in the run through `b1-conditioning` and `b1-window-only` — the trial's block would then cite the `ohlc-15m` set's ten files, which `b1-conditioning` reads (spec 00130 D1), its build would run two past trials' full bars, and the values would equal the registered ones at the registry's precision, which a test already proves; and, for arm A's pre-flight, `var_trials` 0.0 (a lower bar than arm B meets) or arm B's value (it needs arm B's returns before the pre-flight).

## D7 — the bar, the pre-flights, the engagement proof and the decision matrix, fixed before the run

- **Arm B's bar, the headline cell**: `a1_kill_bar(net_b, bench, n_trials=3, var_trials=var_trials, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`. The kill-bar column is its `passes`, `dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass` (`cli/alpha/killbar.py:110`): the DSR leg binds (`[iter-176]`).
- **The SPA grid, recorded**: for blocks {30, 102} × seeds {42, 7, 1234}, the decisive-window SPA p — at (30, 42) the headline's `spa_p_value`; at the other five cells `reality_check_pvalue([[net_b[k] - bench[k]] for k in range(1380, n)], mean_block=block, n_resamples=2000, seed=seed)["p_value"]`, `_b1_metrics`' form (`cli/research/subjects.py:607-611`) and the same computation `a1_kill_bar` makes for its decisive SPA (`cli/alpha/killbar.py:79-84`). The matrix's first column is the headline cell's `passes`, as specs 00045 and 00128 read it, and its adopt row also requires the time-matched block: `spa_p_decisive_b102_s42` < 0.05, the A family's 4h rule that adopted an arm only if its decisive SPA held at both block 30 and block 102 (`docs/research/10.phase4-decisions.md:159`, `[iter-074]` item 2), on the owner's answer (the third `[iter-177]` entry). A cell that meets every other adopt condition with `spa_p_decisive_b102_s42` ≥ 0.05 parks with the block-sensitivity finding, as that rule parks it. The other four cells of the grid are recorded for the reader.
- **The head-to-head**: `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` over the full window — the primary read, since no arm has a burn-in that leaves early years inert — and over `[k16:]` recorded beside it for comparison with records 45 and 46 (`cli/research/subjects.py:613-615`).
- **Pre-flight 1, arm A** — after this file's sha256 is taken as the spec hash and by no one before, since arm A's figures largely predict arm B's column and a read before the hash would be a look while the decisions could still move: (a) the reads' block is `8216f4db…`; (b) arm A reproduces record 45's arm A at the precision the registry stores (spec 00130's measured basis): `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703 and the benchmark's 1.2128 and 1.2447, each at 4 decimals, and `turnover_a` 146.19 at 2; (c) arm A's bar — the headline call with `net_a`, arm A's ×1.5 series and arm A's slices, `n_trials` 3 and `arm_a_var_trials` (D6), every other argument the headline's — reads `passes` 1. (b) is checked before (c) is read.
- **Pre-flight 2, engagement**: `stamps_weights_differ`, the return indices at which arm B's weight dict differs from arm A's (`!=` on the two dicts, whose key sets D2 makes equal), computed from prices alone — no position or return of arm B — is above 0.
- A failed pre-flight is an instrument finding: no run, no verdict, the trial unspent; the pre-flight subject's run is kept as a reading under iter-177 (spec 00129 D7) and T0022 records what failed.
- **The engagement proof recorded with the run**, every item in the record: (1) `stamps_weights_differ`; (2) `stamps_positions_differ`, the return indices where any asset's arm-B position `!=` arm A's (`cli/research/subjects.py:650`'s definition); (3) the weight path's total variation per arm, `math.fsum` over `t` from 0 and over the union of `weights[t]`'s and `weights[t − 1]`'s keys of `|weights[t].get(a, 0.0) − weights[t − 1].get(a, 0.0)|`, `weights[−1]` taken as `{}` — `weight_tv_a`, `weight_tv_b` and `weight_tv_ratio` = B over A; the mechanism predicts a ratio below 1, and a ratio at or above 1 is recorded as the trial's mechanism finding, the mechanism inverted, whatever the verdict; (4) `mean_weight_per_year`: per asset and per bar-start year of the window, `[mean_b, mean_a]`, each the `statistics.fmean` over that year's return indices of `weights[k].get(asset, 0.0)` — both means rather than their ratio, since an asset carries no weight in its years before listing and the registry refuses a non-finite value; (5) `turnover_a`, `turnover_b` (`book_turnover`, `cli/alpha/b1.py:210-222`) and `turnover_reduction_pct` = `100 * (turnover_a - turnover_b) / turnover_a`, as records 45 and 46 hold them.
- **The matrix** (every outcome in exactly one row; the head-to-head read on the full window):

| Kill bar (B vs frozen benchmark, the headline cell) | Head-to-head (B vs A, full window) and turnover | Verdict |
| --- | --- | --- |
| pass, and `spa_p_decisive_b102_s42` < 0.05 | mean outperformance > 0 and SPA p < 0.05, and `turnover_b` < `turnover_a` | **adopt** the estimator |
| pass, and `spa_p_decisive_b102_s42` ≥ 0.05 | mean outperformance > 0 and SPA p < 0.05, and `turnover_b` < `turnover_a` | **park** (the block-sensitivity finding: the bar's significance does not hold at the time-matched block) |
| pass | mean outperformance > 0, SPA p ≥ 0.05, and `turnover_b` < `turnover_a` | **park** (variants: 15m sampling; the hourly estimator also in the book vol target) |
| pass | mean outperformance ≤ 0, or `turnover_b` ≥ `turnover_a` | **reject** |
| fail | any — arm A having passed the same bar at the pre-flight | **reject** (an estimator that breaks the adopted arm's bar is harmful) |

Every quantity the matrix reads is a stored key read unrounded: the kill bar's `passes`, `spa_p_decisive_b102_s42`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `turnover_a` and `turnover_b`. The third row's turnover condition — the park row's, SPA p ≥ 0.05, which the second `[iter-177]` entry calls the second row, numbered before the block-sensitivity row existed — is any reduction, `turnover_b < turnover_a`, the owner's answer there, which closes the cell the trial-1 design left open (`docs/specs/00045-b1-seasonality-conditioning-design.md:51`); the first two rows carry the same condition from the survey's adopt row (`docs/research/10.phase4-b1-candidate-hypotheses.md:54`). The comparison is exact, with no floor: an exact tie of the two turnovers reads as "not below" and rejects. The rule, as the subject declares it (spec 00129 D4), with the two instrument findings its metrics show:

```python
def _b1_hourly_rv_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["stamps_weights_differ"] == 0:
        return None  # instrument finding: no verdict, the trial unspent
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_full"] > 0 and m["turnover_b"] < m["turnover_a"]:
        if m["head_to_head_spa_p_full"] < 0.05 and m["spa_p_decisive_b102_s42"] < 0.05:
            return "adopt"
        return "park"
    return "reject"
```

The third instrument finding, the inputs' block against the measured basis, is not a metric and stays a pre-flight step of the plan.

## D8 — the registry record and the two subjects

- **The record** (spec 00129 D1, D2, D4): family `B1`, `n_trials_in_family` 3, `variant` `B1-hourly-rv-weights-a2eq-v1`, `iteration` `iter-177`; the command computes `spec_hash` — the sha256 of this file, the subject's declared spec — and the verdict by the subject's rule, and the plan passes both as `--spec-hash` and `--verdict` assertions; `seeds` are the subject's declared (42, 7, 1234); `invocation` names `b1-hourly-rv`, `ohlc-full`, window null, as-of null, holes false, comparator null and the commit; `datasets` is the reader's block (D4), `dataset_hash` its `compute_hash`; `notes` is caller text naming the matrix row that fired, `var_trials` and its three inputs, the DSR leg binding, and arm A's pre-flight.
- **The subject `b1-hourly-rv`**: `Subject("b1-hourly-rv", (240, 60), _ASSETS, _build_b1_hourly_rv, spec="docs/specs/00132-b1-hourly-rv-weights-design.md", metric_keys=_B1_HOURLY_RV_METRIC_KEYS, seeds=(42, 7, 1234), verdict=_b1_hourly_rv_verdict, no_verdict="instrument finding: arm A fails the bar, or arm B's weights equal arm A's at every stamp; no verdict, the trial unspent")` — no incumbent, since arm A is built in the run (spec 00129 D3). Its intervals declare both grids of `--dataset`, so the command refuses an incomplete set before any read (`required_relpaths`, `cli/research/subjects.py:89-90`).
- **The metric keys, exactly these 42** (bools as 0/1, keys str): arm B's `ann_sharpe_noc`, `ann_sharpe_noc_decisive`, `per_period_sharpe_4h`; `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`; `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (Sharpes at 2,190 periods a year, the decisive ones from index 1380, the per-period one unannualised); `var_trials`; from the headline cell `dsr_corrected` (its `dsr`), `dsr_pass`, `spa_pass`, `spa_p_full` (its `spa_p_value_full`), `cost_stress_pass`, `worst_slice_relative_pass` (its `worst_slice_pass`), `passes`; `decisive_start` 1380 and `n_resamples` 2000; `arm_a_var_trials` and `arm_a_passes` (arm A's pre-flight bar, recomputed in the run); `spa_p_decisive_b30_s42`, `spa_p_decisive_b30_s7`, `spa_p_decisive_b30_s1234`, `spa_p_decisive_b102_s42`, `spa_p_decisive_b102_s7`, `spa_p_decisive_b102_s1234`; `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `head_to_head_mean_outperf_2016`, `head_to_head_spa_p_2016`; `max_drawdown` and `arm_a_max_drawdown` over the full series; `spot_drag_pct_yr` and `arm_a_spot_drag_pct_yr` (`turnover / n × 0.006 × 2190`, `cli/research/subjects.py:643-644`); `turnover_a`, `turnover_b`, `turnover_reduction_pct`; `stamps_weights_differ`, `stamps_positions_differ`; `weight_tv_a`, `weight_tv_b`, `weight_tv_ratio`; `mean_weight_per_year` (`{asset: {year: [mean_b, mean_a]}}`). A build in which `weight_tv_a` or `turnover_a` is 0 refuses (`ValidationError`), since a ratio divides by it.
- **The pre-flight subject `b1-hourly-rv-preflight`**, evaluate-only: `Subject("b1-hourly-rv-preflight", (240, 60), _ASSETS, _build_b1_hourly_rv_preflight, spec=<this file>, metric_keys=<its 19 keys>, seeds=(42,))`, no rule — so `--register` refuses it and a `--reading` keeps a stop. It computes no position and no return of arm B. Its 19 keys: `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (the anchors); `arm_a_var_trials`; arm A's bar's `dsr`, `dsr_pass`, `spa_p_value`, `spa_p_value_full`, `spa_pass`, `cost_stress_sharpe`, `cost_stress_pass`, `worst_slice_sharpe`, `worst_slice_pass`, `passes` (the keys `b2-arm-a-bar` declares, `cli/research/subjects.py:358-359`); `stamps_weights_differ`.
- **The build in three halves**, so each consumer reads no more than it needs: `_b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, *, subject)` — the as-of refusal, the union, the window refusal and the hourly reads (D4), no compute — is all the basis test calls; `_b1_hourly_rv_inputs(reads)` adds `weights_a`, `weights_b` and arm A's positions, no position or return of arm B; the trial subject's metrics and the pre-flight subject's metrics each start from it. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `ValidationError` — is a `SubjectError` naming the subject and its window, as `_b1_build` names B1's (`:668-676`).
- `README.md`'s `research eval` `--subject` row names both subjects without an internal term: the A2 4h ensemble against the same ensemble with its per-asset weights estimated from hourly realized volatility, reading the 4h and hourly series of `--dataset`; and its evaluate-only pre-flight, arm A's bar and the count of stamps whose weights differ, no return of arm B, kept with `--reading`.

## D9 — what a verdict changes

- **Adopt** is a research-registry fact on the A2 ensemble alone and does not touch the live book: deploying it needs a combination trial over record 47's book (`docs/research/10.phase4-b1-candidate-hypotheses.md:38`) and an hourly grid in the engine's store, which holds the 1440 and 240 grids only (`cli/engine/store.py:42`). T0123's `ripe_when` reads any ADOPT in the registry, so on adopt it is qualified so that this record ripens it only once its combination trial adopts.
- **Park** names its variants in the record — 15m sampling, and the hourly estimator also in the book vol target — each a new trial of the shared budget.
- **Reject** archives the hypothesis in the record and the decisions log; T0022 goes back to the owner's pick between the survey's candidates B and C, or closing the family as attributed out.

## Out of scope

The park variants (15m sampling; the estimator in the book vol target) — each its own trial, which a park puts to the owner through T0022. A demeaned estimator — rejected in D2. A HAR-type weight estimator — dropped: none of the survey's candidates is one (its one HAR-type item, `docs/research/10.phase4-b1-candidate-hypotheses.md:20`, is a book vol target, attributed out). An `ohlc-rolling` read of this estimator — on adopt the combination trial D9 calls for settles its instrument, and on any other verdict nothing serves the estimator — and any window but the frozen set's full history. Re-verdicting records 45 or 46 at the new `var_trials`. The combination trial over record 47's book, an hourly grid in the engine store, and live serving. Any change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b2.py`, `cli/portfolio/*`, the engine or an adopted artifact. The survey's candidates B and C.
