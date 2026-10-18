# B1 trial 4 — seasonally normalized volume confirmation of the A2-4h ensemble's breakout entries (design)

**Ruling:** the owner, attended, 2026-10-17: "don't close B1, run candidate B instead", and four answers — "B1, as trial 4 (Recommended)", "As trial 3 (Recommended)", "Any reduction (Recommended)", "Registry fact, combination trial next (Recommended)" — and, after a walk-through of the adoption path, "Keep: combination trial next (Recommended)"; the pick, and the five answers each with its question and the option it read, verbatim in `docs/research/10.phase4-decisions.md`'s two `[iter-178]` entries; the DSR leg binds by the owner's ruling recorded as the first `[iter-176]` entry there. The rest of this spec was written in an unattended run: every call past those words is the author's, marked **Author's call** where it is made. **Iteration:** iter-178. **Topic:** T0022 under the T0016 umbrella. **Goal:** pre-register B1's fourth trial — candidate B of the survey `docs/research/10.phase4-b1-candidate-hypotheses.md` (its `### B`, lines 62–74, with the shortlist's common items, lines 29–38, candidate A's matrix, lines 50–57, which candidate B's takes, and the common decisions, lines 98–102) — on trial 3's conventions (`docs/specs/00132-b1-hourly-rv-weights-design.md`), as numbered decisions with code-level definitions: a module computing the volume norm, the confirmed state machine and arm B's book, a committed research subject that builds both arms and registers the trial through `zcrypto research eval`, its evaluate-only pre-flight twin, and trial 4, run once spec 00133's trial-attempts log has merged (D12). This spec spends one trial of Bucket B's shared budget when trial 4 runs: 22 remain today (`docs/open-topics/T0016-bucket-b-c-alpha-families.md:20`), 21 after.

## The measured basis

Every command below ran on 2026-10-17 from 21:29:44Z in this branch's worktree at develop's `86175dfe5`, with `data/ohlc-full` linked from the main checkout's `data/`. The two scripts are scratch under `.tmp/spec-00134/`, never committed: the first reads the ten 240 files' stamps, volumes and trade counts, the union through one `ObservedReader` as the subject reads it, and the volumes mapped onto the union's stamps, then counts each asset's bars per hour-of-week cell; the second reads the union's BTC closes for presence alone. Neither computes a return of any series, a channel position, an entry event or a direction. The plan's basis test commits what they measure about the reads (D5). Every `path:line` citation in this file reads the tree at `86175dfe5`; in a later tree the cited code is found by what the citation names. **Author's call** — arm A is not run here: its figures are the arm-A pre-flight's, read after this file's sha256 (D9), the order trial 3 kept, so this basis holds no return of either arm; the anchor's standing is read off the registry and the code instead (the third and fourth blocks).

- **The ten 240 files' volume column, the reads as the subject makes them, and the norm's warm-up and 42 cells** — per file the rows, first and last stamp, stamps off the 4h grid, null, NaN and non-positive volumes, the smallest volume, `count == 0` rows and the smallest count; the union through `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, then each 240 file read again through the same reader for its `volume`, and the block; per asset whether a volume is present exactly where a close is, and the stamps `_ffill_btc` gives a price and no volume; per asset over its own bars (the file's rows), the first bar with 180 prior bars, the smallest 180-bar median volume, the cells `(hour, weekday)` of `ts + 4h` seen, each cell's count of bars with 180 prior bars, and the first bar at which a cell has 100 earlier such bars — the first cell's and the last of the 42:

```
$ uv run python .tmp/spec-00134/measure_volume.py data
ADA 240: rows 16446, first 2018-09-28 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 360.6, count==0 rows 0, min count 1
AVAX 240: rows 9365, first 2021-12-21 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 0.47305301, count==0 rows 0, min count 1
BTC 240: rows 27332, first 2013-09-10 20:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 0.00026834, count==0 rows 0, min count 1
DOGE 240: rows 13710, first 2019-12-19 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 3000.0, count==0 rows 0, min count 1
DOT 240: rows 12306, first 2020-08-18 16:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 1.66950889, count==0 rows 0, min count 1
ETH 240: rows 23292, first 2015-08-07 08:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 0.02, count==0 rows 0, min count 1
LINK 240: rows 14267, first 2019-09-25 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 5.68292658, count==0 rows 0, min count 1
LTC 240: rows 26746, first 2013-09-14 08:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 0.00051999, count==0 rows 0, min count 1
SOL 240: rows 10486, first 2021-06-17 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 115.2871867, count==0 rows 0, min count 13
XRP 240: rows 19423, first 2017-05-18 12:00:00+00:00, last 2026-03-31 20:00:00+00:00, off-grid stamps 0, null volume 0, NaN volume 0, volume <= 0 0, min volume 3000.0, count==0 rows 0, min count 4
union: 27338 stamps, 27337 return indices, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00
block over the 240 reads, each read twice: ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 rows 173373
union ADA: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union AVAX: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union BTC: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 6
union DOGE: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union DOT: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union ETH: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union LINK: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union LTC: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union SOL: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
union XRP: price present == volume present at every stamp: True; stamps the BTC fill gives a price and no volume: 0
ADA norm: bars 16446, first bar with 180 prior bars 2018-10-28 12:00:00+00:00, min L 145253.043832995, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 385 max 388, total 16266; cells reaching 100 earlier observations 42; first 2020-09-27 12:00:00+00:00, all 42 by 2020-10-04 08:00:00+00:00; from the first bar: first 730 days, all 736 days
AVAX norm: bars 9365, first bar with 180 prior bars 2022-01-20 12:00:00+00:00, min L 574.973046415, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 217 max 219, total 9185; cells reaching 100 earlier observations 42; first 2023-12-21 12:00:00+00:00, all 42 by 2023-12-30 00:00:00+00:00; from the first bar: first 730 days, all 738 days
BTC norm: bars 27332, first bar with 180 prior bars 2013-11-07 08:00:00+00:00, min L 2.0, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 645 max 647, total 27152; cells reaching 100 earlier observations 42; first 2015-10-08 08:00:00+00:00, all 42 by 2015-10-19 00:00:00+00:00; from the first bar: first 757 days, all 768 days
DOGE norm: bars 13710, first bar with 180 prior bars 2020-01-21 12:00:00+00:00, min L 174459.3690752, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 317 max 324, total 13530; cells reaching 100 earlier observations 42; first 2021-12-21 12:00:00+00:00, all 42 by 2022-02-05 00:00:00+00:00; from the first bar: first 733 days, all 778 days
DOT norm: bars 12306, first bar with 180 prior bars 2020-09-17 16:00:00+00:00, min L 7220.07636406, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 288 max 289, total 12126; cells reaching 100 earlier observations 42; first 2022-08-18 16:00:00+00:00, all 42 by 2022-08-25 12:00:00+00:00; from the first bar: first 730 days, all 736 days
ETH norm: bars 23292, first bar with 180 prior bars 2015-09-07 04:00:00+00:00, min L 297.74406141500003, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 545 max 552, total 23112; cells reaching 100 earlier observations 42; first 2017-08-07 04:00:00+00:00, all 42 by 2017-09-16 00:00:00+00:00; from the first bar: first 730 days, all 770 days
LINK norm: bars 14267, first bar with 180 prior bars 2019-10-25 12:00:00+00:00, min L 2420.1512037700004, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 333 max 336, total 14087; cells reaching 100 earlier observations 42; first 2021-09-24 12:00:00+00:00, all 42 by 2021-10-10 04:00:00+00:00; from the first bar: first 730 days, all 745 days
LTC norm: bars 26746, first bar with 180 prior bars 2013-12-04 08:00:00+00:00, min L 51.778360160000005, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 608 max 642, total 26566; cells reaching 100 earlier observations 42; first 2015-11-11 08:00:00+00:00, all 42 by 2016-06-01 00:00:00+00:00; from the first bar: first 788 days, all 990 days
SOL norm: bars 10486, first bar with 180 prior bars 2021-07-17 20:00:00+00:00, min L 2022.8965592499999, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 243 max 246, total 10306; cells reaching 100 earlier observations 42; first 2023-06-17 20:00:00+00:00, all 42 by 2023-06-24 16:00:00+00:00; from the first bar: first 730 days, all 737 days
XRP norm: bars 19423, first bar with 180 prior bars 2017-06-17 12:00:00+00:00, min L 316059.421934235, cells seen 42 (hours [0, 4, 8, 12, 16, 20]), observations per cell min 457 max 459, total 19243; cells reaching 100 earlier observations 42; first 2019-05-18 12:00:00+00:00, all 42 by 2019-06-01 04:00:00+00:00; from the first bar: first 730 days, all 743 days
```

- **The six stamps `_ffill_btc` fills, and BTC's own bars before each** (`cli/portfolio/crossfreq_system.py:199-211`):

```
$ uv run python .tmp/spec-00134/measure_fills.py data
BTC filled at union index 6 (2013-09-14 08:00:00+00:00), BTC bars before it 6
BTC filled at union index 26 (2013-09-29 04:00:00+00:00), BTC bars before it 25
BTC filled at union index 160 (2013-11-03 08:00:00+00:00), BTC bars before it 158
BTC filled at union index 235 (2013-11-16 04:00:00+00:00), BTC bars before it 232
BTC filled at union index 9340 (2018-01-12 00:00:00+00:00), BTC bars before it 9336
BTC filled at union index 9341 (2018-01-12 16:00:00+00:00), BTC bars before it 9336
```

- **Records 45, 46 and 48, the three B1 trials the dispersion reads** — their registered arm-B per-period Sharpe, the arm-A and benchmark figures the arm-A pre-flight reproduces (D9), and the commit record 48 ran at:

```
$ sed -n '45,46p;48p' docs/reference/trial-registry.jsonl | python3 -c 'import json, sys
for line in sys.stdin:
    r = json.loads(line); m = r["metrics"]
    print(r["trial_id"], r["family"], r["n_trials_in_family"], r["verdict"], m["per_period_sharpe_4h"], m["arm_a_ann_sharpe_noc"], m["arm_a_ann_sharpe_noc_decisive"], m["arm_a_max_drawdown"], m["turnover_a"], m["arm_a_spot_drag_pct_yr"], m["benchmark_ann_sharpe_noc"], m["benchmark_ann_sharpe_noc_decisive"], (r.get("invocation") or {}).get("commit"))'
45 B1 1 reject 0.02374 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 None
46 B1 2 reject 0.02959 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 None
48 B1 3 park 0.030191886721210086 1.404998307684581 1.3716011675660076 0.2154323695072342 146.18534602048504 0.07026650498259404 1.2128451567638199 1.2446890489958136 838adb43291183a5bc320fba804be4d4eb777ed0
```

- **Arm A's code path since record 48's run** — the packages and files an arm-A build reads:

```
$ git merge-base --is-ancestor 838adb43291183a5bc320fba804be4d4eb777ed0 HEAD && echo "838adb432 is an ancestor of $(git rev-parse --short HEAD)"; git log --oneline 838adb43291183a5bc320fba804be4d4eb777ed0..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry/observed.py cli/ohlc | wc -l
838adb432 is an ancestor of 86175dfe5
0
```

- **The DSR code at this trial's count**:

```
$ uv run python -c 'from cli.validation.dsr import expected_max_sharpe; print(f"expected_max_sharpe(4, 1.0) = {expected_max_sharpe(4, 1.0)!r}"); print(f"expected_max_sharpe(3, 1.0) = {expected_max_sharpe(3, 1.0)!r}")'
expected_max_sharpe(4, 1.0) = 1.0521228241893004
expected_max_sharpe(3, 1.0) = 0.8528044961506948
```

- **Where the code the design rests on lives**:

```
$ git grep -n -E '^def (_donchian_signal|_asset_directions_a2|a2_book_returns|channel_position|_map_to_union_index|_inverse_vol_weights|_asset_returns|_validate_prices_by_asset|vol_target|a1_kill_bar|net_of_cost_verdict|calendar_year_slices|benchmark_4h_net_of_cost|_ffill_btc|book_turnover|net_of_cost|_capturing_union|load_union|_b1_refuse_window|_b1_hourly_rv_reads|_b1_hourly_rv_inputs|_b1_hourly_rv_arm_a|_b1_hourly_rv_verdict|weights_differ_count|expected_max_sharpe|deflated_sharpe_ratio|sharpe|max_drawdown)\(' -- cli/
cli/alpha/a1.py:83:def _map_to_union_index(own_ts: list, own_values: list[float], union_ts: list) -> list[float | None]:
cli/alpha/a1.py:157:def _asset_returns(prices: list[float | None]) -> list[float | None]:
cli/alpha/a1.py:164:def _inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]:
cli/alpha/a1.py:192:def _validate_prices_by_asset(prices_by_asset: dict[str, list[float | None]]) -> None:
cli/alpha/a2.py:68:def _donchian_signal(prices: list[float], *, window: int, band: float) -> list[float]:
cli/alpha/a2.py:81:def _asset_directions_a2(
cli/alpha/a2.py:114:def a2_book_returns(prices_by_asset: dict[str, list[float | None]], *, config: A2Config) -> dict:
cli/alpha/b1.py:210:def book_turnover(asset_positions: dict[str, list[float]]) -> float:
cli/alpha/b1_rv.py:128:def weights_differ_count(weights_a: list[dict[str, float]], weights_b: list[dict[str, float]]) -> int:
cli/alpha/b2.py:252:def net_of_cost(
cli/alpha/killbar.py:14:def a1_kill_bar(
cli/alpha/killbar.py:151:def net_of_cost_verdict(
cli/benchmark/strategies.py:16:def vol_target(returns: list[float], *, target_vol: float, lookback: int, max_leverage: float = 1.0) -> list[float]:
cli/features/channel.py:6:def channel_position(prices: list[float], *, window: int) -> list[float]:
cli/portfolio/crossfreq_system.py:199:def _ffill_btc(prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
cli/portfolio/record43_book.py:199:def net_of_cost(positions: dict[str, list[float]], returns: dict[str, list[float]], n: int) -> tuple[list[float], list[float]]:
cli/portfolio/record44_legs.py:48:def load_union(interval: int, *, root: Path = DATA_ROOT, read=read_parquet) -> tuple[list[datetime], dict[str, list[float | None]]]:
cli/portfolio/record44_legs.py:64:def benchmark_4h_net_of_cost(h4_prices: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]:
cli/portfolio/record44_legs.py:108:def calendar_year_slices(returns: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
cli/research/subjects.py:100:def _capturing_union(
cli/research/subjects.py:533:def _b1_refuse_window(subject: str, h4_ts: list[datetime], window: tuple[str, str] | None) -> None:
cli/research/subjects.py:763:def _b1_hourly_rv_reads(
cli/research/subjects.py:804:def _b1_hourly_rv_inputs(reads: _B1HourlyRVReads) -> _B1HourlyRVInputs:
cli/research/subjects.py:831:def _b1_hourly_rv_arm_a(inputs: _B1HourlyRVInputs) -> tuple[dict, float, list[float], list[float]]:
cli/research/subjects.py:1007:def _b1_hourly_rv_verdict(m: dict) -> str | None:
cli/validation/dsr.py:12:def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
cli/validation/dsr.py:53:def deflated_sharpe_ratio(
cli/validation/metrics.py:26:def sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float:
cli/validation/metrics.py:66:def max_drawdown(returns: list[float]) -> float:
$ git grep -n -E '^GRID_INTERVALS|^_B1_[A-Z0-9_]+ =|^_RAW_COLUMNS|^_FLOAT_COLUMNS|^STUB_YEARS|^DSR_PASS_THRESHOLD' -- cli/
cli/alpha/killbar.py:11:DSR_PASS_THRESHOLD = 0.95
cli/derivatives/oi.py:47:_FLOAT_COLUMNS = (
cli/engine/store.py:42:GRID_INTERVALS = (1440, 240)
cli/ohlc/dataset.py:10:_RAW_COLUMNS = ["ts", "open", "high", "low", "close", "vwap", "volume", "count"]
cli/ohlc/dataset.py:11:_FLOAT_COLUMNS = ["open", "high", "low", "close", "vwap", "volume"]
cli/portfolio/record44_legs.py:31:STUB_YEARS = (2013, 2026)  # partial-year slices, excluded from the worst-slice leg
cli/research/subjects.py:523:_B1_COST_PER_SIDE = 0.006
cli/research/subjects.py:524:_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
cli/research/subjects.py:525:_B1_LOOKBACK = 180
cli/research/subjects.py:526:_B1_DECISIVE_START = 1380
cli/research/subjects.py:527:_B1_N_RESAMPLES = 2000
cli/research/subjects.py:528:_B1_FROM_2016 = datetime(2016, 1, 1, tzinfo=UTC)
cli/research/subjects.py:530:_B1_GRID = ((30, 7), (30, 1234), (102, 42))
cli/research/subjects.py:707:_B1_METRIC_KEYS = frozenset(
cli/research/subjects.py:750:_B1_RECORDED_PER_PERIOD_SHARPES = (0.02374, 0.02959)
cli/research/subjects.py:752:_B1_HOURLY_RV_N_TRIALS = 3
cli/research/subjects.py:754:_B1_HOURLY_RV_GRID = ((30, 42), (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))
cli/research/subjects.py:1020:_B1_HOURLY_RV_METRIC_KEYS = frozenset(
cli/research/subjects.py:1066:_B1_HOURLY_RV_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
```

- **The channel, the state machine, the clip, the positions and the cell key the gate and the norm rest on** (`cli/features/channel.py:16-18`; `cli/alpha/a2.py:68-78`, `:94-98`, `:105-107`, `:147-150`; `cli/alpha/b1.py:73-74`; `cli/ohlc/dataset.py:10-11`; `cli/engine/store.py:42`):

```
$ sed -n '16,18p' cli/features/channel.py; echo ---; sed -n '68,78p;94,98p;105,107p' cli/alpha/a2.py; echo ---; sed -n '147,150p' cli/alpha/a2.py; echo ---; sed -n '73,74p' cli/alpha/b1.py; echo ---; sed -n '10,11p' cli/ohlc/dataset.py; echo ---; sed -n '42p' cli/engine/store.py
        w = prices[k - window + 1 : k + 1]
        hi, lo = max(w), min(w)
        out.append(2 * (prices[k] - lo) / (hi - lo) - 1 if hi > lo else 0.0)
---
def _donchian_signal(prices: list[float], *, window: int, band: float) -> list[float]:
    cp = channel_position(prices, window=window)
    out: list[float] = []
    held = 0.0
    for k in range(len(cp)):
        if cp[k] >= band:
            held = 1.0
        elif cp[k] <= -band:
            held = -1.0
        out.append(held)
    return out
        own_prices = [p for p in prices if p is not None]
        mapped = [
            _map_to_union_index(asset_ts[asset], _donchian_signal(own_prices, window=w, band=config.band), union_ts)
            for w in config.lookbacks
        ]
            ensemble = statistics.mean(values)
            if config.short == "off":
                d.append(max(ensemble, 0.0))
---
    asset_positions: dict[str, list[float]] = {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * positions[k] for k in range(length - 1)]
        for asset in prices_by_asset
    }
---
    boundaries = [ts + _BOUNDARY for ts in union_ts[:-1]]
    cells = [(b.hour, b.weekday()) for b in boundaries]
---
_RAW_COLUMNS = ["ts", "open", "high", "low", "close", "vwap", "volume", "count"]
_FLOAT_COLUMNS = ["open", "high", "low", "close", "vwap", "volume"]
---
GRID_INTERVALS = (1440, 240)
```

What the reads establish, each figure from the blocks above:

- **Every bar carries a usable volume.** All 173,373 rows of the ten 240 files hold a volume that is finite and above 0 — no null, no NaN, none at or below 0 — and no file holds a `count == 0` row or a stamp off the 4h grid; the smallest volumes run from 0.00026834 (BTC) to 3000.0 (DOGE, XRP), in each base asset's units, which the norm's ratio cancels. So `volume[j] / L[j]` is defined at every bar, and D4's refusals cannot fire on the frozen set.
- **The reads are records 45, 46 and 48's 4h reads.** The union is 27,338 stamps, 27,337 return indices, 2013-09-10 20:00 → 2026-03-31 20:00, the shape trial 3's basis names; reading each 240 file a second time under the same window adds nothing to the block, which stays `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69` over 173,373 rows — the block `tests/test_b1_records_reproduce.py` pins for record 46 and trial 3's basis names for its ten 240 files. This trial reads no other file.
- **Volume is present exactly where a close is**, on every asset at every union stamp. `_ffill_btc` gives BTC a price and no volume at six stamps — 2013-09-14 08:00, 2013-09-29 04:00, 2013-11-03 08:00, 2013-11-16 04:00, 2018-01-12 00:00 and 2018-01-12 16:00 — and three of them (BTC bars before each: 6, 25, 158) fall before BTC's 180th bar, where the norm does not yet exist: D4 orders the warm-up rule before the fill rule for that reason.
- **The norm's level exists from each asset's 181st bar** — from 2013-11-07 08:00 (BTC) to 2022-01-20 12:00 (AVAX) — and the smallest 180-bar median volume over each asset's history is above 0 (from 2.0, BTC).
- **All 42 cells occur on every asset** — hours 0, 4, 8, 12, 16, 20 of `ts + 4h`, each on all seven weekdays — and over the full history each cell holds, of bars with a level: ADA 385–388, AVAX 217–219, BTC 645–647, DOGE 317–324, DOT 288–289, ETH 545–552, LINK 333–336, LTC 608–642, SOL 243–246, XRP 457–459.
- **The 100-observation rule starts binding** — the first cell to reach 100 earlier observations, then the last of the 42: ADA 2020-09-27 12:00 → 2020-10-04 08:00; AVAX 2023-12-21 12:00 → 2023-12-30 00:00; BTC 2015-10-08 08:00 → 2015-10-19 00:00; DOGE 2021-12-21 12:00 → 2022-02-05 00:00; DOT 2022-08-18 16:00 → 2022-08-25 12:00; ETH 2017-08-07 04:00 → 2017-09-16 00:00; LINK 2021-09-24 12:00 → 2021-10-10 04:00; LTC 2015-11-11 08:00 → 2016-06-01 00:00; SOL 2023-06-17 20:00 → 2023-06-24 16:00; XRP 2019-05-18 12:00 → 2019-06-01 04:00. That is 730–788 days after each asset's first bar for the first cell — 180 bars, then 100 weeks — and 736–990 days for the last, LTC's 990 the effect of its 2013–2016 gaps. The survey's "about two years into each asset's history" holds; before it, `S` is 1 and the gate compares a bar's volume with `L` alone — the burn-in disclosed here as the trial-1 design disclosed its own.
- **Arm A's anchor stands.** Records 45, 46 and 48 hold the same arm A at the registry's precision — annualised Sharpe 1.405 (record 48: 1.404998307684581), decisive 1.3716, maximum drawdown 0.2154, turnover 146.19 (146.18534602048504), drag 0.0703, benchmark 1.2128 and 1.2447 — record 48 run at `838adb432`, an ancestor of this branch's cut, and no commit since touches a package or file an arm-A build reads. The arm-A pre-flight re-checks the anchor after the hash (D9).
- **The DSR leg in numbers of the code.** `expected_max_sharpe(4, V)` is `1.0521228241893004 · √V`, against trial 3's `0.8528044961506948 · √V` at three trials.
- **The dispersion's three registered Sharpes** are 0.02374 and 0.02959 — five decimals, the precision records 45 and 46's lost writer stored — and 0.030191886721210086, record 48's, stored unrounded.
- **The operating model this spec is read under.** One session registers this trial, on one machine, once: D12's step 4 is a single `--register` run, and the trial-attempts log it writes to is one per machine and carried by no transport (spec 00133's D1 and D6, from that spec's merge). Concurrent registrations, a second machine and a restored log are spec 00133's to count and refuse, not this spec's to design for: a finding that needs one of them reaches no decision here unless it changes what step 4 records. **Author's call**, added after the plan review of spec 00133 spent most of its floor on out-of-model edges.

## Hypothesis (trial 4, pre-registered by this spec's sha256)

Each adopted A2 lookback's state is +1 from a bar whose 4h close is the highest of the last `w` closes and −1 from one whose close is the lowest, held in between, 0 only before its first touch (`cli/features/channel.py:6-19`, `cli/alpha/a2.py:68-78`); with short off the arm's direction is the mean over its three lookbacks clipped at 0 (`cli/alpha/a2.py:105-107`). A false breakout flips one lookback −1 → +1 and back and costs arm A a round trip on the direction change it causes. Volume separates a breakout many participants act on from a print in a thin hour, and crypto volume carries a robust intraday and weekly seasonality, so the knob compares the breakout bar's volume with what is normal for that hour of the week (`docs/research/10.phase4-b1-candidate-hypotheses.md:65`). **Arm B — each adopted arm with a Donchian entry accepted only when the breakout bar's volume is at or above its hour-of-week norm, exits always accepted — has a higher mean net-of-cost return than arm A at 0.006 per side (SPA p < 0.05, full window) and lower turnover** (`:64`, verbatim). Arms: **A** = the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48 built it; **B** = the same ensemble with only the state machine's entry transition gated. One knob, entry confirmation, judged by the pre-registered decision matrix (D10). The survey's expectations stand: turnover down, since a rejected breakout that fails saves A's round trip and one confirmed later still trades once; maximum drawdown at or below A's, not guaranteed, since B can hold the subset that falls (`:71`). Its honest prior stands: about 0.08 that it is adopted, about 0.35 that the point estimate favours B — B's exposure is a subset of A's, which carries the edge that clears the bar, so B wins only if the opening bars of low-volume breakouts, up to confirmation, lose money net of the round trips they cost (`:73`).

## D1 — the arms: arm A is records 45, 46 and 48's, arm B gates the entry transition alone

- **Arm A** is built as `_b1_hourly_rv_inputs` builds it (`cli/research/subjects.py:804-829`): `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B1_A2_ARMS` (`:524`), `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_B1_LOOKBACK, basket_lookback=_B1_LOOKBACK, periods_per_year=PPY_4H))`; arm A is the per-asset `statistics.mean` of the three `asset_positions` at every return index.
- **Arm B** is the same three configs, each arm's asset positions `weights_a[k].get(a, 0.0) * (directions_b[a][k] or 0.0) * vt_a[k]`, with `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)` — arm A's weights, one path for the three arms since each arm's `basket_lookback` is 180 — `directions_b` that arm's confirmed directions (D2), and `vt_a` that arm's `a2_book_returns(...)["vol_target_positions"]`, arm A's vol scalar on arm A's own base returns; averaged per asset per stamp as arm A is. This is the survey's arm B: "B's position is arm A's weight × B's direction × arm A's vol scalar, so the knob moves directions only" (`docs/research/10.phase4-b1-candidate-hypotheses.md:67`) — unlike trial 3, whose arm B re-ran the vol target on its own book.
- Everything else is arm A's: the asset returns, the costing (D6), the B1 literals `_B1_COST_PER_SIDE`, `_B1_A2_ARMS`, `_B1_LOOKBACK`, `_B1_DECISIVE_START`, `_B1_N_RESAMPLES`, `_B1_FROM_2016` (`cli/research/subjects.py:523-528`), reused and not restated — trial 4 runs B1's protocol, so a change to one of them is a change to every B1 trial's instrument (spec 00130 D2).
- No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b1_rv.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, the engine or any adopted artifact: the new code is one module, `cli/alpha/b1_volume.py` (D2, D3, D4, D8's helpers), and the two subjects (D11). **Author's call**: the module's name, beside trial 3's `cli/alpha/b1_rv.py`.
- **Identity, held by a test**: with every entry confirmed, each arm's confirmed directions equal `_asset_directions_a2`'s and its positions equal `a2_book_returns(fed, config=config)["asset_positions"]` exactly, so the knob is the gate and nothing else; and on the fixture, B's direction is at or below A's at every arm, asset and stamp where both are present.

## D2 — the entry gate: A2's state machine with its +1 transition confirmed

- A2's state machine for lookback `w` runs on the asset's own contiguous series, `own_prices` the non-`None` prices of `fed[a]` (`cli/alpha/a2.py:94`): `cp = channel_position(own_prices, window=w)`, `held` from 0.0, `cp[j] >= band` setting +1 and `cp[j] <= -band` setting −1, `band` 1.0 (`A2Config`, `:32`); the state at own bar `j` is the position over the move `own j → j + 1`, mapped onto the union by `_map_to_union_index` (`cli/alpha/a1.py:83-95`).
- **An entry event** at own bar `j` of lookback `w` is a bar where the channel position reaches the band (1.0) while the lookback's state is not already +1 — A2's own transition, the survey's definition (`docs/research/10.phase4-b1-candidate-hypotheses.md:68`) — read on arm B's own state machine. It is **accepted** when `confirm[j]` (D3, D4) is true, setting B's state to +1, and **rejected** otherwise, leaving B's state where it was: −1, or its initial 0. A band touch while B's state is already +1 is no event. Exits are always accepted: `cp[j] <= -band` sets −1 whatever `confirm[j]` says.
- In `cli/alpha/b1_volume.py`, returning the states and the events `(j, accepted)`:

```python
def donchian_signal_confirmed(
    prices: list[float], confirm: list[bool], *, window: int, band: float
) -> tuple[list[float], list[tuple[int, bool]]]:
    cp = channel_position(prices, window=window)
    held, out, events = 0.0, [], []
    for j in range(len(cp)):
        if cp[j] >= band:
            if held != 1.0:
                events.append((j, confirm[j]))
                if confirm[j]:
                    held = 1.0
        elif cp[j] <= -band:
            held = -1.0
        out.append(held)
    return out, events
```

- **Arm B's directions per arm**: `_asset_directions_a2`'s body (`cli/alpha/a2.py:92-111`) with `donchian_signal_confirmed(own_prices, confirm_by_asset[asset], window=w, band=config.band)[0]` in place of `_donchian_signal(...)` — the mean over the arm's lookbacks, `None` wherever any lookback's mapping is `None`, clipped at 0. `confirm_by_asset[asset]` is one list per asset, one flag per own bar, shared by every lookback and every arm: the gate reads the bar's volume and its norm, which no lookback changes. A config with `short="on"` is refused (`AlphaError`): **Author's call** — the survey's argument that B's direction never exceeds A's rests on the clip at 0, and under "on" a state held lower is a deeper short.
- **B never carries exposure A has shed.** B's state is at or below A's on every lookback at every bar: both start at 0; at a band touch A's goes to +1, which nothing exceeds; at a new low both go to −1; otherwise both hold. The mean over lookbacks and the clip at 0 are monotone, so B's direction is at or below A's, and with A's weight and A's scalar both at or above 0, B's position is at or below A's on every asset at every stamp (`docs/research/10.phase4-b1-candidate-hypotheses.md:66-67`).
- A confirmed function with every flag true returns `_donchian_signal(prices, window=window, band=band)` exactly — the identity D1's test reads.

## D3 — the norm `E[k] = L[k] × S[c(k)]`, as the survey fixes it

- Accept when `volume[k] ≥ E[k]`, "at or above typical", with `E[k] = L[k] × S[c(k)]` (`docs/research/10.phase4-b1-candidate-hypotheses.md:68`, every value below copied from it).
- **`L[k]`** is the median volume of the asset's prior 180 bars, A2's own 30-day horizon: the median of the volumes of the asset's 180 bars before bar `k`, bar `k` excluded.
- **`c(k)`** is the hour and weekday of the decision boundary `ts[k] + 4h`, `ts[k]` the bar's open stamp: `b = ts[k] + timedelta(hours=4)` and `c = (b.hour, b.weekday())`, the trial-1 design's 42-cell key (`docs/specs/00045-b1-seasonality-conditioning-design.md:11`) as `cli/alpha/b1.py:73-74` computes it — hours 0, 4, 8, 12, 16, 20 × weekdays 0–6, Monday 0; all 42 occur on every asset (measured).
- **`S[c]`** is the median over the asset's earlier bars in cell `c` of `volume[j] / L[j]`, held at 1 while the cell has fewer than 100 earlier observations, the trial-1 design's thin-cell rule (`:13`).
- Medians throughout, so one spike does not set the norm. Both `L` and `S` read volume only, never a return, and bar `k` reads only bars before it, plus its own volume, which is known at `ts[k] + 4h` together with `close[k]`: walk-forward and leak-free by construction.
- **Author's call** — an observation of `S` is an earlier bar with its own level, one with 180 prior bars, its ratio read against its own `L[j]`; a bar of the warm-up adds its volume to later levels' windows and no ratio. The measured cell counts and binding dates use exactly this.
- **Author's call** — `statistics.median` for both: the mean of the two middle values at an even count, so `L`, over 180 values, is always that mean. The product `L * S` is computed in float and compared with `>=` exactly, with no tolerance.
- In `cli/alpha/b1_volume.py`, called with `lookback=_B1_LOOKBACK` (180) and `min_cell_obs=100`, `stamps` and `volumes` the asset's own bars (D4):

```python
def volume_confirmations(
    stamps: list[datetime], volumes: list[float | None], *, lookback: int, min_cell_obs: int
) -> list[bool]:
    rows: list[float] = []
    ratios: dict[tuple[int, int], list[float]] = {}
    out: list[bool] = []
    for t, v in zip(stamps, volumes, strict=True):
        if len(rows) < lookback:
            out.append(True)  # fewer than 180 prior bars: accepted, a fill among them (D4)
            if v is not None:
                rows.append(v)
            continue
        if v is None:
            out.append(False)  # a forward-filled BTC stamp: no volume, never confirms, no bar
            continue
        level = statistics.median(rows[-lookback:])
        b = t + timedelta(hours=4)
        cell = ratios.setdefault((b.hour, b.weekday()), [])
        shape = statistics.median(cell) if len(cell) >= min_cell_obs else 1.0
        out.append(v >= level * shape)
        cell.append(v / level)
        rows.append(v)
    return out
```

- Rejected: a raw-volume comparison, which would reject a breakout for the hour it happens in (`docs/research/10.phase4-b1-candidate-hypotheses.md:65`); means in place of the medians, and the hour-of-day key of 6 cells, both kept as park variants (D10).

## D4 — eligibility and edge cases

- **Own bars and the file's rows.** The gate runs on each asset's own series as A2's state machine does: `stamps` are the union stamps where `fed[a]` holds a price, `volumes` the bar's volume there, `None` at a stamp `_ffill_btc` filled. **Author's call** — the survey's "the asset's prior 180 bars" and "earlier bars" are the asset's 240-file rows: a BTC fill carries no volume, so it adds nothing to a level's window or a cell's observations and does not advance the prior-bar count, while the state machine's lookback, arm A's, counts it, the fill being a price of `fed`.
- **The warm-up.** An asset with fewer than 180 prior bars has its entries accepted, so B's states equal A's on the bar the norm first exists.
- **The forward-filled BTC stamp** carries no volume and never confirms: an entry event there is rejected. **Author's call** — the warm-up rule comes first: three of the six fills (2013-09-14 08:00, 2013-09-29 04:00, 2013-11-03 08:00) fall before BTC's 180th bar (measured), where there is no norm to confirm against and every entry is accepted, so an entry there is accepted too; the fill rule binds the other three (2013-11-16 04:00, 2018-01-12 00:00 and 2018-01-12 16:00). Rejecting a warm-up entry at a fill would make B differ from A by an artifact of the forward fill before the knob exists.
- **Thin cells.** `S` is 1 while a cell has fewer than 100 earlier observations; the weekly shape binds about two years into each asset's history, from the dates the measured basis lists, and the gate compares a bar's volume with its level alone before that.
- **Refusals, never drops** (`AlphaError`, naming the asset and the stamp): a volume at a bar with a price that is not a finite number above 0; a volume present where the price is absent, or absent where the price is present at a stamp other than a BTC fill; stamps not strictly increasing or tz-naive; `stamps` and `volumes` of unequal length; `lookback` or `min_cell_obs` not an int of at least 1. Dropping a bar would shift every later level window and cell count. None can fire on the frozen set: every row's volume is finite and above 0, and presence matches at every stamp but BTC's six fills (measured).
- **A windowed evaluation** reads the union and the volumes under the same bounds (D5), so the norm warms up from the window's first bar and its gate differs from the full run's over the window's first 180 bars and each cell's first 100 observations. The trial reads no window.

## D5 — the data and the window: the frozen `ohlc-full` set's 240 files, whole

- `--dataset ohlc-full`, no `--window`, no `--as-of`: the owner's "As trial 3 (Recommended)", whose option read "Frozen ohlc-full, 2013-09-10 → 2026-03-31 (arm A reproduces record 45's arm A)" (the second `[iter-178]` entry). The set ends 2026-03-31, before the spent holdout's window, 2026-04-01 → 2026-07-09 (`docs/research/13.phase5-holdout-ledger.md:9`): no holdout question arises.
- **The reads**, in order: the 4h union through `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)` (`cli/research/subjects.py:100-127`) — measured 27,338 stamps, 27,337 return indices; the window refusal `_b1_refuse_window` (`:533-550`); then per asset `reader.read_series(dataset, f"{asset}/EUR/240.parquet", window=window)` (`cli/registry/observed.py:119-155`), its `ts` and `volume` columns mapped onto the union's stamps by `ts`, `None` where the asset has no bar. The second read of a file under the same window is the same read: the reader hashes and records a `(dataset, relpath)` once (`:128`, `:151-154`), so the block is the 240 reads' alone. A file polars cannot read, or one with no `volume` column, is a `SubjectError` naming `<dataset>/<A>/EUR/240.parquet`, as `_b1_hourly_rv_reads` names its 60 files (`:782-789`). The subject's intervals are `(240,)`: no 60, 15m or L2 file is read (the survey's Data line, `docs/research/10.phase4-b1-candidate-hypotheses.md:69`).
- An `--as-of` read is refused with a `SubjectError` before any read, as `_b1_hourly_rv_reads` refuses one (`cli/research/subjects.py:774-778`). **Author's call**: no `ohlc-rolling` instrument for this gate — the trial reads the frozen set alone, the owner's "As trial 3", and an adopt's road to live serving is D13's, through the combination trial and T0123.
- **The inputs' identity** is the block the measured basis names: `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69` over the ten 240 files, 173,373 rows, span 2013-09-10 20:00 → 2026-03-31 20:00. The plan's data-gated basis test reproduces it, the union's shape, the volume presence, the six fills, the 42 cells' counts and the binding dates from the subject's reads half, computing no direction.
- The decisive window starts at return index 1380 (`_B1_DECISIVE_START`), the from-2016 cut at the first `k` with `h4_ts[k] ≥ 2016-01-01T00:00Z` (`cli/research/subjects.py:620`), the bar-start convention records 45, 46 and 48 read; the per-year engagement figures (D8) key a return index, or an event bar, by the same bar-start year `h4_ts[k].year`.

## D6 — the costing, the benchmark and the slices: records 45, 46 and 48's

- `returns = {a: _asset_returns(fed[a])}`; each arm's net through `net_of_cost(arm, returns, cost_per_side=_B1_COST_PER_SIDE)` (`cli/alpha/b2.py:252-273`: per-asset turnover from flat, a missing return read as 0.0), the ×1.5 series through the same at `1.5 * _B1_COST_PER_SIDE`, as trial 3's subject computes them (`cli/research/subjects.py:834-835`, `:878-879`) — never `a2_book_returns`' `net_returns`, which is uncosted.
- The benchmark: `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B1_COST_PER_SIDE)` on the raw union prices (`cli/portfolio/record44_legs.py:64`; `cli/research/subjects.py:836`).
- The slices: `calendar_year_slices(series, h4_ts)`, each return keyed by its close year `h4_ts[k + 1].year`, 2013 and 2026 dropped (`cli/portfolio/record44_legs.py:108-119`, `:31`).

## D7 — `var_trials`: B1's family dispersion over records 45, 46 and 48 and arm B, two-pass, from the registered Sharpes

- **The source**: the registered `per_period_sharpe_4h` of records 45, 46 and 48 — 0.02374, 0.02959 and 0.030191886721210086 (`docs/reference/trial-registry.jsonl:45`, `:46`, `:48`, measured above) — the owner's "var_trials B1's family dispersion over records 45, 46, 48 and this trial's arm B" (the second `[iter-178]` entry), held in the subject as `_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES = (*_B1_RECORDED_PER_PERIOD_SHARPES, 0.030191886721210086)` and pinned by an ungated test against the three committed records. **Author's call**: each value at the precision its record stores — records 45 and 46 at their five decimals, record 48 unrounded, every digit its writer stored — since the dispersion reads the registry's values and never a re-derivation (trial 3's D6).
- **The arithmetic.** `per_period_sharpe_4h = sharpe(net_b)` — unannualised (`cli/validation/metrics.py:26-40`), the per-period Sharpe `a1_kill_bar` deflates — then `var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, per_period_sharpe_4h])`, the sample variance over four (denominator 3). All four are 4h per-period Sharpes over the same 27,337 returns, so no periodicity conversion applies.
- **The two passes.** The first builds arm B and its per-period Sharpe; the second calls arm B's bar (D10) with `n_trials=4` and that `var_trials`.
- **Arm A's pre-flight bar** takes `arm_a_var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, sharpe(net_a)])` — "with arm A standing in for the pre-flight", the owner's answer — since arm B's Sharpe does not exist before the run and the pre-flight computes none of arm B's returns.
- **What it does to the leg**, from the code: `dsr_pass` holds exactly when `Φ((sr − 1.0521228241893004 · √var_trials) · √27,336 / √(1 + sr² / 2)) > 0.95`, `sr` the bar's per-period Sharpe — `expected_max_sharpe` at `n_trials` 4 (measured) and the PSR at the kill bar's default moments, skew 0 and kurtosis 3 (`cli/validation/dsr.py:46-50`; `cli/alpha/killbar.py:70` passes none). Neither the variance nor the bar's figure is computed here.
- Records 45, 46 and 48 keep their registered bars: the registry is append-only and nothing re-verdicts them.
- **Author's call** — an orphan: should spec 00133's count find an attempt in family B1 that never landed, the register run is refused (D12), and no orphan's Sharpe enters this dispersion; the next subject's count and dispersion go to the owner, the question spec 00133 leaves to the plan review of each trial ("What stays prose").

## D8 — the engagement pre-flight and its dead-knob stop

- The pre-flight count is read from prices and volumes alone — no position and no return of arm B computed — after this file's sha256 is taken and before any verdict (`docs/research/10.phase4-b1-candidate-hypotheses.md:36`, `:70`). Every item is a metric of the pre-flight subject and of the trial:
- `entry_events_per_year`: `{arm: {asset: {lookback: {year: [events, rejected]}}}}`, the arm `"1"`–`"3"` in `_B1_A2_ARMS` order, the lookback and the event bar's bar-start year as strings; every year in which the asset has a state value appears, zeros included — the survey's "entry events and rejected entry events per year, per arm × asset × lookback". **Author's call**: kept at that grain although arms 2 and 3 carry equal counts by construction — both run lookbacks (60, 120, 240), and the state machine reads no target vol.
- `entry_events` and `entry_events_rejected`, the totals over every arm, asset, lookback and year, and `share_rejected` = `entry_events_rejected / entry_events`, the survey's "the share rejected"; **Author's call**: a build with no entry event refuses (`ValidationError`), since the share divides by the count.
- `stamps_directions_differ`: the return indices `k` at which, for any arm and any asset, arm B's clipped direction `!=` arm A's — `None` equal to `None`, since both arms map the same `None`s — and `stamps_directions_differ_per_year`, `{year: count}` over every bar-start year of the union's return indices, zeros included: the survey's "the stamps where B's clipped direction differs from A's".
- **The dead-knob stop**: `stamps_directions_differ == 0` — zero such stamps in every year — is a dead knob, an instrument finding: no run, no verdict, the trial unspent, as both precedents and the committed B2 rule hold (`docs/specs/00045-b1-seasonality-conditioning-design.md:44`; `docs/specs/00128-b2-family-opening-design.md:56`; `cli/research/subjects.py:511-518`). The rule carries the stop too (D10), so a register run on a dead knob is a stop, never a verdict.
- A year with events and none accepted — `events > 0` and `rejected == events` summed over a year's arms, assets and lookbacks — is reported as such, read off `entry_events_per_year` in the pre-flight step (D12) and in the decisions-log entry; it stops nothing.
- **Recorded with the run**: `stamps_positions_differ`, the return indices where any asset's arm-B position `!=` arm A's (`cli/research/subjects.py:938`'s definition); `turnover_a`, `turnover_b` (`book_turnover`, `cli/alpha/b1.py:210-222`) and `turnover_reduction_pct` = `100 * (turnover_a - turnover_b) / turnover_a`, as records 45, 46 and 48 hold them.

## D9 — the arm-A pre-flight

- After this file's sha256 is taken as the spec hash and by no one before — arm A's figures largely predict arm B's column, so a read before the hash would be a look while the decisions could still move (trial 3's D7): (a) the reads' block is `ff2e5700…`; (b) arm A reproduces record 45's arm A at the precision the registry stores: `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703 and the benchmark's 1.2128 and 1.2447, each at 4 decimals, and `turnover_a` 146.19 at 2; (c) arm A's bar — the headline call (D10) with `net_a`, arm A's ×1.5 series and arm A's slices, `n_trials` 4 and `arm_a_var_trials` (D7), every other argument the headline's — reads `passes` 1. (b) is checked before (c) is read.
- A failed pre-flight, this one or D8's, is an instrument finding: no run, no verdict, the trial unspent; the pre-flight subject's run is kept as a reading under iter-178 (D12, spec 00129 D7), and T0022 records what failed.

## D10 — the bar, the SPA grid, the head-to-head and the decision matrix, fixed before the run

- **Arm B's bar, the headline cell**: `a1_kill_bar(net_b, bench, n_trials=4, var_trials=var_trials, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`. The kill-bar column is its `passes`, `dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass` (`cli/alpha/killbar.py:110`): the DSR leg binds (`[iter-176]`).
- **The SPA grid, recorded**: for blocks {30, 102} × seeds {42, 7, 1234}, the decisive-window SPA p — at (30, 42) the headline's `spa_p_value`; at the other five cells `reality_check_pvalue([[net_b[k] - bench[k]] for k in range(1380, n)], mean_block=block, n_resamples=2000, seed=seed)["p_value"]`, trial 3's form (`cli/research/subjects.py:895-899`). The adopt row also requires the time-matched block, `spa_p_decisive_b102_s42` < 0.05: the owner's "the adopt row needs SPA significant at both blocks 30 and 102, as A did" (the second `[iter-178]` entry), the A family's 4h rule (`docs/research/10.phase4-decisions.md:159`, `[iter-074]` item 2). A cell that meets every other adopt condition with `spa_p_decisive_b102_s42` ≥ 0.05 parks with the block-sensitivity finding. The other four cells are recorded for the reader.
- **The head-to-head**: `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` over the full window, the primary read, and over `[k16:]` recorded beside it for comparison with records 45 and 46 (`cli/research/subjects.py:901-903`). The full window is primary because no part of it is inert: the gate acts from each asset's 181st bar, with `S` at 1 until its weekly shape binds about two years in (measured).
- **The matrix** — candidate A's table with the park row's variants "hour-of-day cells only (6); the mean in place of the median" (`docs/research/10.phase4-b1-candidate-hypotheses.md:72`), and trial 3's block-sensitivity row; every outcome in exactly one row, the head-to-head read on the full window:

| Kill bar (B vs frozen benchmark, the headline cell) | Head-to-head (B vs A, full window) and turnover | Verdict |
| --- | --- | --- |
| pass, and `spa_p_decisive_b102_s42` < 0.05 | mean outperformance > 0 and SPA p < 0.05, and `turnover_b` < `turnover_a` | **adopt** the entry confirmation |
| pass, and `spa_p_decisive_b102_s42` ≥ 0.05 | mean outperformance > 0 and SPA p < 0.05, and `turnover_b` < `turnover_a` | **park** (the block-sensitivity finding: the bar's significance does not hold at the time-matched block) |
| pass | mean outperformance > 0, SPA p ≥ 0.05, and `turnover_b` < `turnover_a` | **park** (variants: hour-of-day cells only (6); the mean in place of the median) |
| pass | mean outperformance ≤ 0, or `turnover_b` ≥ `turnover_a` | **reject** |
| fail | any — arm A having passed the same bar at the pre-flight | **reject** (a confirmation that breaks the adopted arm's bar is harmful) |

Every quantity the matrix reads is a stored key read unrounded: the kill bar's `passes`, `spa_p_decisive_b102_s42`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `turnover_a` and `turnover_b`. The third row — the survey's second, the park row the owner's question names, "B above A on the point estimate, SPA not significant" — takes any reduction, `turnover_b < turnover_a`, the owner's "Any reduction (Recommended)", whose option read "turnover_b < turnover_a, as you answered for trial 3"; the first two rows carry the same condition from the survey's adopt row (`docs/research/10.phase4-b1-candidate-hypotheses.md:54`). The comparison is exact, with no floor: an exact tie of the two turnovers reads as "not below" and rejects. The rule, as the subject declares it (spec 00129 D4), with the two instrument findings its metrics show:

```python
def _b1_volume_confirmation_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["stamps_directions_differ"] == 0:
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

## D11 — the registry record and the two subjects

- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B1`, `n_trials_in_family` 4, `variant` `B1-volume-confirm-a2eq-v1`, `iteration` `iter-178`; the command computes `spec_hash` — the sha256 of this file, the subject's declared spec — and the verdict by the subject's rule; `seeds` are the subject's declared (42, 7, 1234); `invocation` names `b1-volume-confirmation`, `ohlc-full`, window null, as-of null, holes false, comparator null and the commit; `datasets` is the reader's block (D5), `dataset_hash` its `compute_hash`, `ff2e5700…` (measured); `attempt` carries the trial-attempts log's id, this run's attempt, its `absorbs` and its `counted`, expected empty (spec 00133 D8); `notes` is caller text written before the run (D12).
- **The subject `b1-volume-confirmation`**: `Subject("b1-volume-confirmation", (240,), _ASSETS, _build_b1_volume_confirmation, spec="docs/specs/00134-b1-volume-confirmation-design.md", metric_keys=_B1_VOLUME_METRIC_KEYS, seeds=(42, 7, 1234), verdict=_b1_volume_confirmation_verdict, no_verdict="instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every stamp; no verdict, the trial unspent", family="B1", n_trials=_B1_VOLUME_N_TRIALS)`, `_B1_VOLUME_N_TRIALS = 4` — the two fields spec 00133 D4 adds, declared as it prescribes for the trial after record 48: three records, no orphan, and itself; every `a1_kill_bar` call its build makes, arm A's pre-flight bar included, passes that count. No incumbent, since arm A is built in the run (spec 00129 D3). Its intervals declare the 240 grid of `--dataset`, so the command refuses an incomplete set before any read (`required_relpaths`, `cli/research/subjects.py:96-97`).
- **The metric keys, exactly these 43** (bools as 0/1, keys str): arm B's `ann_sharpe_noc`, `ann_sharpe_noc_decisive`, `per_period_sharpe_4h`; `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`; `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (Sharpes at 2,190 periods a year, the decisive ones from index 1380, the per-period one unannualised); `var_trials`; from the headline cell `dsr_corrected` (its `dsr`), `dsr_pass`, `spa_pass`, `spa_p_full` (its `spa_p_value_full`), `cost_stress_pass`, `worst_slice_relative_pass` (its `worst_slice_pass`), `passes`; `decisive_start` 1380 and `n_resamples` 2000; `arm_a_var_trials` and `arm_a_passes` (arm A's pre-flight bar, recomputed in the run); `spa_p_decisive_b30_s42`, `spa_p_decisive_b30_s7`, `spa_p_decisive_b30_s1234`, `spa_p_decisive_b102_s42`, `spa_p_decisive_b102_s7`, `spa_p_decisive_b102_s1234`; `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `head_to_head_mean_outperf_2016`, `head_to_head_spa_p_2016`; `max_drawdown` and `arm_a_max_drawdown` over the full series; `spot_drag_pct_yr` and `arm_a_spot_drag_pct_yr` (`turnover / n × 0.006 × 2190`, `cli/research/subjects.py:932-933`); `turnover_a`, `turnover_b`, `turnover_reduction_pct`; `entry_events`, `entry_events_rejected`, `share_rejected`, `entry_events_per_year`, `stamps_directions_differ`, `stamps_directions_differ_per_year`, `stamps_positions_differ` (D8). A build in which `turnover_a` is 0 refuses (`ValidationError`), since a ratio divides by it.
- **The pre-flight subject `b1-volume-confirmation-preflight`**, evaluate-only: `Subject("b1-volume-confirmation-preflight", (240,), _ASSETS, _build_b1_volume_confirmation_preflight, spec="docs/specs/00134-b1-volume-confirmation-design.md", metric_keys=_B1_VOLUME_PREFLIGHT_KEYS, seeds=(42,))` — no rule, no family, no trial count, so `--register` refuses it and a `--reading` keeps a stop. It computes no position and no return of arm B. Its 24 keys: `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (the anchors); `arm_a_var_trials`; arm A's bar's `dsr`, `dsr_pass`, `spa_p_value`, `spa_p_value_full`, `spa_pass`, `cost_stress_sharpe`, `cost_stress_pass`, `worst_slice_sharpe`, `worst_slice_pass`, `passes` (the keys `b2-arm-a-bar` declares, `cli/research/subjects.py:365-366`); `entry_events`, `entry_events_rejected`, `share_rejected`, `entry_events_per_year`, `stamps_directions_differ`, `stamps_directions_differ_per_year`.
- **The build in three halves**, so each consumer reads no more than it needs: `_b1_volume_reads(reader, dataset, window, as_of, accept_holes, *, subject)` — the as-of refusal, the union, the window refusal and the volume reads (D5), no compute — is all the basis test calls; `_b1_volume_inputs(reads)` adds `fed`, the returns, `weights_a`, each arm's positions, vol scalar and directions, the confirmations, each arm's confirmed directions and events, and arm A's positions — no position or return of arm B; the trial subject's metrics and the pre-flight subject's metrics each start from it. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `ValidationError` — is a `SubjectError` naming the subject and its window, as `_b1_hourly_rv_build` names trial 3's (`cli/research/subjects.py:966-980`).
- `README.md`'s `research eval` `--subject` row names both subjects without an internal term: the A2 4h ensemble against the same ensemble with each breakout entry accepted only on a bar whose volume is at or above its hour-of-week norm, reading the 4h series and its volumes of `--dataset`, a frozen set only; and its evaluate-only pre-flight, arm A's bar and the entry events and stamps whose directions differ, no return of arm B, kept with `--reading`.

## D12 — the run, gated on spec 00133's merge

- **The gate.** Trial 4 runs only once spec 00133 — `docs/specs/00133-t0222-trial-attempts-design.md`, merged into develop as pull request #730 on 2026-10-18 — is in this branch through develop: then `Subject` carries `family` and `n_trials` (its D4), every `--register` run writes its `begin` line to the trial-attempts log before the fit and its `end` line before the print (its D2), the count refuses a subject declaring fewer trials than its family needs (its D3, D4) and a bucket past its budget (its D5), and a plain eval of a subject with a rule is refused (its D7). Before that merge neither subject runs over the trial's data.
- **Where the build sits.** **Author's call**: this branch was rebased onto spec 00133's branch once its `Subject` carried `family` and `n_trials` (plan 00133's Task 6), and onto develop after spec 00133 merged, before any of this spec's code was written; no part of this spec's code reaches develop before spec 00133's did, so `b1-volume-confirmation` never exists where a plain eval of it would run uncounted. There is no separate build pull request: the module, the subjects, the run's record and its verdict land in this branch's one pull request.
- **The steps**, in order, after the plan review has closed and nothing this spec pins has changed since:
  1. The spec hash: `sha256sum docs/specs/00134-b1-volume-confirmation-design.md`, whose value the record's `spec_hash` must equal; this file is never edited after it.
  2. The develop check: `git fetch origin develop` and `git diff --quiet origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exit 0, so an append chains onto develop's last line.
  3. The pre-flights (D8, D9): `uv run zcrypto research eval --subject b1-volume-confirmation-preflight --dataset ohlc-full` — a plain eval of a subject with no rule, which spec 00133 D7 admits — read in order: the printed block against `ff2e5700…`, the seven anchors, `passes`, then `stamps_directions_differ` above 0 with `entry_events_per_year` and `stamps_directions_differ_per_year`, any year with events and none accepted noted. On a stop, the run is kept as a reading: `uv run zcrypto research eval --subject b1-volume-confirmation-preflight --dataset ohlc-full --reading --iteration iter-178 --spec-hash <step 1's sha256> --notes "<what failed, quoted from step 3's output; no verdict, the trial unspent>"`, and T0022 records what failed.
  4. The trial, one run, by the owner or on their word: `uv run zcrypto research eval --subject b1-volume-confirmation --dataset ohlc-full --register --iteration iter-178 --family B1 --n-trials 4 --variant B1-volume-confirm-a2eq-v1 --spec-hash <step 1's sha256> --notes "<below>"`.
- **No plain eval of `b1-volume-confirmation`**, before or after step 4: spec 00133 D7 refuses one, and step 4 is the trial's one look, which its `begin` line counts before the fit. Trial 3's separate read-only run (`docs/plans/00132-b1-hourly-rv-weights.md`, Task 4 steps 3 and 4) becomes this one register run.
- **No `--verdict` assertion.** **Author's call**: with no plain eval before it, nothing has shown the verdict, so an asserted one would be a guess the command refuses after its print; the rule's verdict is stored.
- **The notes, written before the run.** **Author's call**: they name only what is fixed before it — the subject over `ohlc-full`, full history, no as-of; the two arms, the hypothesis D13's reject archives in the record; `var_trials` the variance of records 45, 46 and 48's registered per-period Sharpes and arm B's, `n_trials` 4, the DSR leg binding; step 3's pre-flight figures, quoted; the park variants D13 names in the record; the matrix pre-registered by this spec's hash. The row that fired is read off the record's verdict and metrics, and the decisions-log verdict entry names it with its figures.
- **A refusal from the count.** If `required_n(B1)` exceeds 4 — an attempt in B1 that never landed — or bucket B has no trial left, step 4 is refused, before the fit or after its print (spec 00133 D3, D5), the count's refusal naming each orphan it counts and the bucket's its spent figure; a refusal after the print leaves a look no record carries, whose printed metrics T0022's findings name and whose orphans T0016's budget line counts; the trial goes back to the owner through T0022, whose `ripe_when` becomes the owner's ruling on what the refusal names, since this spec's hash fixes `n_trials` 4 and the dispersion's sources, and a further count is a new subject under a new spec (D7).
- **A stop by the rule** under `--register` — arm A failing its bar, or no direction differing — is kept as a reading carrying its attempt, which counts 0: the trial unspent (spec 00133 D3, class "stopped").
- **After a verdict**: the decisions-log entry `[iter-178] Verdict — B1 trial 4 <ADOPT, PARK or REJECT> (registry trial <N>, family B1 n=4)` with the row that fired, its figures and the engagement proof, written with `iteration-closeout` loaded; T0022's findings and T0016's budget line (B1 spent 4, 21 remain, less one for each orphan the record's `attempt.counted` lists) updated in the same branch.

## D13 — what a verdict changes

- **Adopt** is a research-registry fact on the A2 ensemble alone and does not touch the live book — the owner's "Keep: combination trial next (Recommended)", whose option read: "An adopt is a registry fact on the A2 ensemble alone; deploying needs a P1 combination trial over record 47's book (unbudgeted), and on its adopt T0123's promotion path (contract bump, ≥14 days parity, ≥3 ISO weeks band, class declared before evidence). The adopt ripens T0123 only once the combination trial adopts." The combination trial is P1's, outside every bucket's budget (`docs/research/13.phase5-decisions.md:29`); T0123's path is its "Always" list — a new record, a builder-contract version bump, shadow concordance re-earned on the new contract — with the change class declared and ratified before the evidence, parity at ≥ 14 consecutive clean on-time days and the tracking band at ≥ 3 consecutive complete ISO weeks (`docs/open-topics/T0123-sleeve-promotion-path.md:37-41`, `:51`, `:59`). T0123's `ripe_when` reads any ADOPT in the registry (`:3`), so it is qualified so that this record ripens it only once its combination trial adopts. **Author's call**: the qualification is written in the PR that registers an adopt, so no tree holds the adopt without it; on any other verdict T0123 is untouched. The live path is the cheapest of the survey's three: the engine store already carries volume on the 240 grid (`cli/engine/store.py:42`; `cli/ohlc/dataset.py:10-15`), so deploying needs no new grid, unlike trial 3's hourly estimator.
- **Park** names its variants in the record — on the third row, hour-of-day cells only (6), and the mean in place of the median; on the second, the block-sensitivity finding — each variant a new trial of the shared budget, which a park puts to the owner through T0022.
- **Reject** archives the hypothesis in the record and the decisions log; T0022 goes back to the owner's pick among candidate C, a park variant of trial 3, or closing the family as attributed out.
- **No verdict** — a pre-flight stop, or the rule's stop under `--register` — spends no trial; T0022 records what failed.

## Out of scope

The park variants (hour-of-day cells only; the mean in place of the median) — each its own trial, which a park puts to the owner through T0022. A raw-volume gate — rejected in D3. A volume condition on exits, volume in the sizing, and arm B's vol target on its own book — the survey fixes A's scalar and an entry-only gate (D1, D2). An `ohlc-rolling` read of this gate and any window but the frozen set's full history (D5). Re-verdicting records 45, 46 or 48 at the new `var_trials`. Spec 00133's trial-attempts log itself, which this trial consumes and does not build. The combination trial over record 47's book, T0123's promotion and live serving. T0123's `ripe_when` before an adopt is registered (D13). Any change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b1_rv.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, the engine or an adopted artifact. Trial 3's park variants and the survey's candidate C.
