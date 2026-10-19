# B1 trial 5 — hourly channel exits on the A2-4h ensemble's own channel (design)

**Ruling:** the owner, attended, 2026-10-19: "directly run C for B1, then B2‘s data work, then B2 baseline ruling", and four answers — "B1, as trial 5 (Recommended)", "As trials 3 and 4 (Recommended)", "Mean difference (Recommended)", "Registry fact only (Recommended)"; the pick, and the four answers each with its question and the option it read, verbatim in `docs/research/10.phase4-decisions.md`'s two `[iter-179]` entries; the DSR leg binds by the owner's ruling recorded as the first `[iter-176]` entry there. The rest of this spec is the author's: every call past those words is marked **Author's call** where it is made. **Iteration:** iter-179. **Topic:** T0022 under the T0016 umbrella. **Goal:** pre-register B1's fifth trial — candidate C of the survey `docs/research/10.phase4-b1-candidate-hypotheses.md` (its `### C`, lines 76–96, with the shortlist's common items, lines 29–38, and the common decisions, lines 98–102) — on trials 3 and 4's conventions (`docs/specs/00132-b1-hourly-rv-weights-design.md`, `docs/specs/00134-b1-volume-confirmation-design.md`), as numbered decisions with code-level definitions: a module computing the hourly exit check, arm B's positions in each hour of the interval and its net of cost, a committed research subject that builds both arms and registers the trial through `zcrypto research eval --register` and spec 00133's trial-attempts log, its evaluate-only pre-flight twin, and trial 5's one register run (D12). This spec spends one trial of Bucket B's shared budget when trial 5 runs: 21 remain today (`docs/open-topics/T0016-bucket-b-c-alpha-families.md:20`), 20 after.

## The measured basis

Every command below ran on 2026-10-19 from 02:51:42Z in this branch's worktree at develop's `82cfedcab`, with `data/ohlc-full` linked from the main checkout's `data/`. The one script is scratch under `.tmp/spec-00135/`, never committed: it reads the union and the ten 60 files through one `ObservedReader` as the subject reads them (D5), then compares stamps and closes — which hourly bars exist, inside which 240 bar, and whether a close equals another; it computes no return of any series, no channel position, no state and no direction. The plan's basis test commits what it measures about the reads (D5). Every `path:line` citation in this file reads the tree at `82cfedcab`; in a later tree the cited code is found by what the citation names. **Author's call** — neither arm A nor the engagement count is run here: the survey reads the engagement pre-flight's count "after the spec's sha256 is taken" (`docs/research/10.phase4-b1-candidate-hypotheses.md:36`) and arm A's figures are the arm-A pre-flight's (D9), the order trials 3 and 4 kept and the owner's "As trials 3 and 4" carries, so this basis holds no return of either arm, no state of either state machine and no count of the knob's engagement; the anchor's standing is read off the registry and the code instead.

- **The reads, the hourly coverage, the interval's interior hourly closes and the seam with the 240 files** — the 4h union through `_b1_hourly_rv_reads(reader, "ohlc-full", None, None, False, subject=...)` (`cli/research/subjects.py:775-802`), which this trial reuses (D5), and the reader's block; per asset over the 60 file, its rows, first and last hour, the hours on the grid between them and the missing ones, the missing hours that fall inside a 240 bar the asset has, the stamps' order and grid, bad closes and `count == 0` rows, and the hourly bars outside every 240 bar; per interval — each of the asset's 240 bars after its first, judged on the hourly bars opening 0, 1 and 2 hours into it — how many of the three interior hourly closes are present, overall, on the intervals whose two bars are consecutive union stamps (`union-adjacent`, the ones a return index maps), on those spanning more than 4h, and in the asset's lowest calendar year; per 240 bar whether it holds an hourly bar, whether the hourly bar opening 3h in is present and its close equals the 240 close, and whether the last present hourly close equals it; and the hourly bars in the span of each stamp `_ffill_btc` fills:

```
$ uv run python .tmp/spec-00135/measure_hourly.py data
union: 27338 stamps, 27337 return indices, 2013-09-10 20:00:00+00:00 -> 2026-03-31 20:00:00+00:00; steps other than 4h: 63
block over the 240 and 60 reads: 8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1 files 20 rows 855305 span ['2013-09-10 20:00:00+00:00', '2026-03-31 23:00:00+00:00']
ADA 60: rows 65623, first 2018-09-28 13:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 65795, missing hours 172, hours missing inside a present 240 bar's span 161, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
ADA intervals: 16445, interior hourly closes present {0..3}: {0: 3, 1: 10, 2: 92, 3: 16340}, all three 16340 (0.9936); union-adjacent 16444, all three 16340 (0.9937); spanning more than 4h 3 {2: 3}; lowest year 2019 2124/2190 (0.9699)
ADA seam: 240 bars 16446, with no hourly bar 0; T+3h hourly bar present 16407, its close != the 240 close 0; the last present hourly close != the 240 close 0
AVAX 60: rows 37157, first 2021-12-21 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 37473, missing hours 316, hours missing inside a present 240 bar's span 303, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
AVAX intervals: 9364, interior hourly closes present {0..3}: {0: 2, 1: 10, 2: 183, 3: 9169}, all three 9169 (0.9792); union-adjacent 9362, all three 9169 (0.9794); spanning more than 4h 4 {2: 4}; lowest year 2023 2103/2189 (0.9607)
AVAX seam: 240 bars 9365, with no hourly bar 0; T+3h hourly bar present 9274, its close != the 240 close 0; the last present hourly close != the 240 close 0
BTC 60: rows 108786, first 2013-09-10 23:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 110041, missing hours 1255, hours missing inside a present 240 bar's span 542, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
BTC intervals: 27331, interior hourly closes present {0..3}: {0: 28, 1: 111, 2: 98, 3: 27094}, all three 27094 (0.9913); union-adjacent 27326, all three 27093 (0.9915); spanning more than 4h 62 {0: 9, 1: 39, 2: 9, 3: 5}; lowest year 2013 315/505 (0.6238)
BTC seam: 240 bars 27332, with no hourly bar 0; T+3h hourly bar present 27197, its close != the 240 close 0; the last present hourly close != the 240 close 0
DOGE 60: rows 53237, first 2019-12-19 14:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 55066, missing hours 1829, hours missing inside a present 240 bar's span 1603, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
DOGE intervals: 13709, interior hourly closes present {0..3}: {0: 42, 1: 266, 2: 512, 3: 12889}, all three 12889 (0.9402); union-adjacent 13660, all three 12881 (0.9430); spanning more than 4h 51 {0: 4, 1: 19, 2: 20, 3: 8}; lowest year 2019 6/63 (0.0952)
DOGE seam: 240 bars 13710, with no hourly bar 0; T+3h hourly bar present 13279, its close != the 240 close 0; the last present hourly close != the 240 close 0
DOT 60: rows 49181, first 2020-08-18 17:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 49231, missing hours 50, hours missing inside a present 240 bar's span 43, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
DOT intervals: 12305, interior hourly closes present {0..3}: {0: 1, 1: 5, 2: 18, 3: 12281}, all three 12281 (0.9980); union-adjacent 12305, all three 12281 (0.9980); spanning more than 4h 2 {2: 2}; lowest year 2020 806/811 (0.9938)
DOT seam: 240 bars 12306, with no hourly bar 0; T+3h hourly bar present 12295, its close != the 240 close 0; the last present hourly close != the 240 close 0
ETH 60: rows 92294, first 2015-08-07 11:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 93349, missing hours 1055, hours missing inside a present 240 bar's span 874, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
ETH intervals: 23291, interior hourly closes present {0..3}: {0: 25, 1: 139, 2: 305, 3: 22822}, all three 22822 (0.9799); union-adjacent 23260, all three 22817 (0.9810); spanning more than 4h 37 {0: 3, 1: 9, 2: 19, 3: 6}; lowest year 2015 454/844 (0.5379)
ETH seam: 240 bars 23292, with no hourly bar 0; T+3h hourly bar present 23079, its close != the 240 close 0; the last present hourly close != the 240 close 0
LINK 60: rows 56518, first 2019-09-25 13:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 57107, missing hours 589, hours missing inside a present 240 bar's span 550, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
LINK intervals: 14266, interior hourly closes present {0..3}: {0: 8, 1: 53, 2: 263, 3: 13942}, all three 13942 (0.9773); union-adjacent 14259, all three 13939 (0.9776); spanning more than 4h 9 {0: 2, 2: 4, 3: 3}; lowest year 2019 432/580 (0.7448)
LINK seam: 240 bars 14267, with no hourly bar 0; T+3h hourly bar present 14111, its close != the 240 close 0; the last present hourly close != the 240 close 0
LTC 60: rows 99565, first 2013-09-14 08:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 109960, missing hours 10395, hours missing inside a present 240 bar's span 7419, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
LTC intervals: 26745, interior hourly closes present {0..3}: {0: 269, 1: 1353, 2: 2019, 3: 23104}, all three 23104 (0.8639); union-adjacent 26383, all three 23057 (0.8739); spanning more than 4h 365 {0: 50, 1: 142, 2: 126, 3: 47}; lowest year 2015 726/1962 (0.3700)
LTC seam: 240 bars 26746, with no hourly bar 0; T+3h hourly bar present 24861, its close != the 240 close 0; the last present hourly close != the 240 close 0
SOL 60: rows 41918, first 2021-06-17 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 41961, missing hours 43, hours missing inside a present 240 bar's span 26, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
SOL intervals: 10485, interior hourly closes present {0..3}: {1: 4, 2: 9, 3: 10472}, all three 10472 (0.9988); union-adjacent 10483, all three 10472 (0.9990); spanning more than 4h 4 {2: 4}; lowest year 2021 1177/1182 (0.9958)
SOL seam: 240 bars 10486, with no hourly bar 0; T+3h hourly bar present 10480, its close != the 240 close 0; the last present hourly close != the 240 close 0
XRP 60: rows 77653, first 2017-05-18 15:00:00+00:00, last 2026-03-31 23:00:00+00:00, hours on the grid 77745, missing hours 92, hours missing inside a present 240 bar's span 39, strictly increasing True, off-grid stamps 0, bad closes 0, count==0 rows 0, hourly bars outside every 240 bar 0
XRP intervals: 19422, interior hourly closes present {0..3}: {0: 4, 1: 3, 2: 12, 3: 19403}, all three 19403 (0.9990); union-adjacent 19420, all three 19403 (0.9991); spanning more than 4h 5 {0: 2, 2: 3}; lowest year 2018 2175/2179 (0.9982)
XRP seam: 240 bars 19423, with no hourly bar 0; T+3h hourly bar present 19417, its close != the 240 close 0; the last present hourly close != the 240 close 0
TOTAL {'rows': 681932, 'missing': 15796, 'missing_inside': 11560, 'outside': 0, 'intervals': 173363, 'all3': 167516, 'adjacent': 172902, 'adjacent_all3': 167452, 'bars': 173373, 'fourth': 170400, 'fourth_disagree': 0, 'last_disagree': 0, 'no_hour': 0, 'interior0': 382, 'interior1': 1954, 'interior2': 3511, 'interior3': 167516}; all three present 0.9663, union-adjacent 0.9685; intervals not union-adjacent 461
BTC filled at union index 6 (2013-09-14 08:00:00+00:00), hourly bars in its span 0
BTC filled at union index 26 (2013-09-29 04:00:00+00:00), hourly bars in its span 0
BTC filled at union index 160 (2013-11-03 08:00:00+00:00), hourly bars in its span 0
BTC filled at union index 235 (2013-11-16 04:00:00+00:00), hourly bars in its span 0
BTC filled at union index 9340 (2018-01-12 00:00:00+00:00), hourly bars in its span 0
BTC filled at union index 9341 (2018-01-12 16:00:00+00:00), hourly bars in its span 0
```

- **Records 45, 46, 48 and 49, the four B1 trials the dispersion reads** — their registered arm-B per-period Sharpe, the arm-A and benchmark figures the arm-A pre-flight reproduces (D9), the commit each of the last two ran at, their dataset hashes and record 49's attempt:

```
$ sed -n '45,46p;48,49p' docs/reference/trial-registry.jsonl | python3 -c 'import json, sys
for line in sys.stdin:
    r = json.loads(line); m = r["metrics"]
    print(r["trial_id"], r["family"], r["n_trials_in_family"], r["verdict"], m["per_period_sharpe_4h"], m["arm_a_ann_sharpe_noc"], m["arm_a_ann_sharpe_noc_decisive"], m["arm_a_max_drawdown"], m["turnover_a"], m["arm_a_spot_drag_pct_yr"], m["benchmark_ann_sharpe_noc"], m["benchmark_ann_sharpe_noc_decisive"], (r.get("invocation") or {}).get("commit"), r["dataset_hash"], json.dumps(r.get("attempt")))'
45 B1 1 reject 0.02374 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 None cccb8d175d2038c462de57b295e9eb53ee2d51278e4110accfa350d93ced68b9 null
46 B1 2 reject 0.02959 1.405 1.3716 0.2154 146.19 0.0703 1.2128 1.2447 None cccb8d175d2038c462de57b295e9eb53ee2d51278e4110accfa350d93ced68b9 null
48 B1 3 park 0.030191886721210086 1.404998307684581 1.3716011675660076 0.2154323695072342 146.18534602048504 0.07026650498259404 1.2128451567638199 1.2446890489958136 838adb43291183a5bc320fba804be4d4eb777ed0 8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1 null
49 B1 4 reject 0.03028127927651177 1.404998307684581 1.3716011675660076 0.2154323695072342 146.18534602048504 0.07026650498259404 1.2128451567638199 1.2446890489958136 bf515702a748ecba29d7405e31fa2d5fa9438fb3 ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69 {"absorbs": [], "begin": "b1bb22d3622b08e64cd510d0f2f6d4caf11cad3e02c33642b3914a8ddbd410fc", "counted": [], "id": 1, "log": "60c9f39c37ec81b4a53396218b690304"}
```

- **Arm A's code path since record 49's run** — the packages and files an arm-A build reads:

```
$ git merge-base --is-ancestor bf515702a748ecba29d7405e31fa2d5fa9438fb3 HEAD && echo "bf515702a is an ancestor of $(git rev-parse --short HEAD)"; git log --oneline bf515702a748ecba29d7405e31fa2d5fa9438fb3..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry/observed.py cli/ohlc | wc -l
bf515702a is an ancestor of 82cfedcab
0
```

- **The DSR code at this trial's count**:

```
$ uv run python -c 'from cli.validation.dsr import expected_max_sharpe; print(f"expected_max_sharpe(5, 1.0) = {expected_max_sharpe(5, 1.0)!r}"); print(f"expected_max_sharpe(4, 1.0) = {expected_max_sharpe(4, 1.0)!r}")'
expected_max_sharpe(5, 1.0) = 1.192594001014789
expected_max_sharpe(4, 1.0) = 1.0521228241893004
```

- **T0123's trigger and the trial-attempts allowlist**:

```
$ sed -n '3p' docs/open-topics/T0123-sleeve-promotion-path.md; git grep -n 'combination' -- 'docs/open-topics/T0123-*.md'; echo "git grep exit $?"; cat docs/reference/trial-attempt-logs.txt
ripe_when: "a post-deploy family reaches an ADOPT verdict in `docs/reference/trial-registry.jsonl` — the first candidate that needs the ruled path. The shadow-alongside capability (running the candidate's contract beside the live record; no `builder_contract`/`contract_version` symbol in `cli/` today) is built then, against a real promotion."
git grep exit 1
60c9f39c37ec81b4a53396218b690304 zcrypto-ops
```

- **Where the code the design rests on lives**:

```
$ git grep -n -E '^def (_donchian_signal|_asset_directions_a2|a2_book_returns|channel_position|_map_to_union_index|_inverse_vol_weights|_asset_returns|_ffill_btc|book_turnover|net_of_cost|_capturing_union|_b1_refuse_window|_b1_hourly_rv_reads|_b1_volume_inputs|_b1_volume_build|_b1_volume_confirmation_verdict|_b2_verdict|a2_positions_on_directions|directions_differ_per_year|a1_kill_bar|net_of_cost_verdict|calendar_year_slices|benchmark_4h_net_of_cost|expected_max_sharpe|deflated_sharpe_ratio|sharpe|max_drawdown)\(' -- cli/
cli/alpha/a1.py:83:def _map_to_union_index(own_ts: list, own_values: list[float], union_ts: list) -> list[float | None]:
cli/alpha/a1.py:157:def _asset_returns(prices: list[float | None]) -> list[float | None]:
cli/alpha/a1.py:164:def _inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]:
cli/alpha/a2.py:68:def _donchian_signal(prices: list[float], *, window: int, band: float) -> list[float]:
cli/alpha/a2.py:81:def _asset_directions_a2(
cli/alpha/a2.py:114:def a2_book_returns(prices_by_asset: dict[str, list[float | None]], *, config: A2Config) -> dict:
cli/alpha/b1.py:210:def book_turnover(asset_positions: dict[str, list[float]]) -> float:
cli/alpha/b1_volume.py:142:def a2_positions_on_directions(
cli/alpha/b1_volume.py:174:def directions_differ_per_year(
cli/alpha/b2.py:252:def net_of_cost(
cli/alpha/killbar.py:14:def a1_kill_bar(
cli/alpha/killbar.py:151:def net_of_cost_verdict(
cli/features/channel.py:6:def channel_position(prices: list[float], *, window: int) -> list[float]:
cli/portfolio/crossfreq_system.py:199:def _ffill_btc(prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
cli/portfolio/record43_book.py:199:def net_of_cost(positions: dict[str, list[float]], returns: dict[str, list[float]], n: int) -> tuple[list[float], list[float]]:
cli/portfolio/record44_legs.py:64:def benchmark_4h_net_of_cost(h4_prices: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]:
cli/portfolio/record44_legs.py:108:def calendar_year_slices(returns: list[float], h4_ts: list[datetime]) -> dict[str, list[float]]:
cli/research/subjects.py:110:def _capturing_union(
cli/research/subjects.py:523:def _b2_verdict(m: dict) -> str | None:
cli/research/subjects.py:545:def _b1_refuse_window(subject: str, h4_ts: list[datetime], window: tuple[str, str] | None) -> None:
cli/research/subjects.py:775:def _b1_hourly_rv_reads(
cli/research/subjects.py:1153:def _b1_volume_inputs(reads: _B1VolumeReads) -> _B1VolumeInputs:
cli/research/subjects.py:1336:def _b1_volume_build(
cli/research/subjects.py:1377:def _b1_volume_confirmation_verdict(m: dict) -> str | None:
cli/validation/dsr.py:12:def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
cli/validation/dsr.py:53:def deflated_sharpe_ratio(
cli/validation/metrics.py:26:def sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float:
cli/validation/metrics.py:66:def max_drawdown(returns: list[float]) -> float:
$ git grep -n -E '^GRID_INTERVALS|^_SUBMISSION_WINDOW|^_B1_[A-Z0-9_]+ =|^_B2_ARM_A_BAR_KEYS|^DSR_PASS_THRESHOLD|^STUB_YEARS' -- cli/
cli/alpha/killbar.py:11:DSR_PASS_THRESHOLD = 0.95
cli/engine/executor.py:115:_SUBMISSION_WINDOW = timedelta(hours=3, minutes=30)
cli/engine/store.py:42:GRID_INTERVALS = (1440, 240)
cli/portfolio/record44_legs.py:31:STUB_YEARS = (2013, 2026)  # partial-year slices, excluded from the worst-slice leg
cli/research/subjects.py:377:_B2_ARM_A_BAR_KEYS = _B2_ARM_A_BAR_FLAGS | {"dsr", "spa_p_value", "spa_p_value_full", "cost_stress_sharpe", "worst_slice_sharpe"}
cli/research/subjects.py:535:_B1_COST_PER_SIDE = 0.006
cli/research/subjects.py:536:_B1_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
cli/research/subjects.py:537:_B1_LOOKBACK = 180
cli/research/subjects.py:538:_B1_DECISIVE_START = 1380
cli/research/subjects.py:539:_B1_N_RESAMPLES = 2000
cli/research/subjects.py:540:_B1_FROM_2016 = datetime(2016, 1, 1, tzinfo=UTC)
cli/research/subjects.py:542:_B1_GRID = ((30, 7), (30, 1234), (102, 42))
cli/research/subjects.py:719:_B1_METRIC_KEYS = frozenset(
cli/research/subjects.py:762:_B1_RECORDED_PER_PERIOD_SHARPES = (0.02374, 0.02959)
cli/research/subjects.py:764:_B1_HOURLY_RV_N_TRIALS = 3
cli/research/subjects.py:766:_B1_HOURLY_RV_GRID = ((30, 42), (30, 7), (30, 1234), (102, 42), (102, 7), (102, 1234))
cli/research/subjects.py:1032:_B1_HOURLY_RV_METRIC_KEYS = frozenset(
cli/research/subjects.py:1078:_B1_HOURLY_RV_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
cli/research/subjects.py:1094:_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES = (*_B1_RECORDED_PER_PERIOD_SHARPES, 0.030191886721210086)
cli/research/subjects.py:1096:_B1_VOLUME_N_TRIALS = 4
cli/research/subjects.py:1098:_B1_VOLUME_MIN_CELL_OBS = 100
cli/research/subjects.py:1390:_B1_VOLUME_METRIC_KEYS = frozenset(
cli/research/subjects.py:1437:_B1_VOLUME_PREFLIGHT_KEYS = _B2_ARM_A_BAR_KEYS | {
```

- **The channel, the state machine, the clip, the positions, the union mapping, the costing loop and the engine's cycle bound the design rests on** (`cli/features/channel.py:16-18`; `cli/alpha/a2.py:68-78`, `:94-98`, `:105-107`, `:147-150`; `cli/alpha/a1.py:89-94`; `cli/alpha/b2.py:263-273`; `cli/engine/executor.py:112-115`; `cli/engine/store.py:42`):

```
$ sed -n '16,18p' cli/features/channel.py; echo ---; sed -n '68,78p;94,98p;105,107p' cli/alpha/a2.py; echo ---; sed -n '147,150p' cli/alpha/a2.py; echo ---; sed -n '89,94p' cli/alpha/a1.py; echo ---; sed -n '263,273p' cli/alpha/b2.py; echo ---; sed -n '112,115p' cli/engine/executor.py; echo ---; sed -n '42p' cli/engine/store.py
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
        j0 = own_pos.get(union_ts[k])
        j1 = own_pos.get(union_ts[k + 1])
        if j0 is not None and j1 is not None and j1 == j0 + 1:
            mapped.append(own_values[j0])
        else:
            mapped.append(None)
---
    net: list[float] = []
    for k in range(n):
        gross, turnover = 0.0, 0.0
        for i, (positions, returns) in enumerate(legs):
            p = positions[k]
            r = returns[k]
            gross += p * (0.0 if r is None else r)
            turnover += abs(p - previous[i])
            previous[i] = p
        net.append(gross - turnover * cost_per_side)
    return net
---
# How long after its boundary an intent of the cycle plan may still start (`_start_intent`); one that has not started by
# then carries to the next boundary. The latest start, its `_TIME_BOX` and three IOC attempts each bounded by `_ACK_WAIT`
# end every order by about B+3h47, before the next boundary's cycle can hold the event loop.
_SUBMISSION_WINDOW = timedelta(hours=3, minutes=30)
---
GRID_INTERVALS = (1440, 240)
```

What the reads establish, each figure from the blocks above:

- **The reads are record 48's.** The union is 27,338 stamps, 27,337 return indices, 2013-09-10 20:00 → 2026-03-31 20:00, 63 steps other than 4h; the ten 240 files and the ten 60 files read whole through one reader give the block `8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1` over 20 files and 855,305 rows, span to 2026-03-31 23:00 — record 48's `dataset_hash`, produced by the reads half this trial reuses. This trial reads no other file.
- **Every hourly bar is clean and lies inside a 240 bar.** All 681,932 rows of the ten 60 files are strictly increasing, on the hour, with no null, non-finite or non-positive close and no `count == 0` row; none lies outside a 240 bar of its asset (0 of 681,932), and none in the span of any of the six stamps `_ffill_btc` fills. So an interval's hourly closes are exactly those of the 240 bar that ends it, and an interval ending at a fill has none.
- **The hourly coverage per asset** — first hour, then the missing hours of the grid from it to the last hour, every file's last hour being 2026-03-31 23:00: ADA 2018-09-28 13:00, 172 of 65,795; AVAX 2021-12-21 15:00, 316 of 37,473; BTC 2013-09-10 23:00, 1,255 of 110,041; DOGE 2019-12-19 14:00, 1,829 of 55,066; DOT 2020-08-18 17:00, 50 of 49,231; ETH 2015-08-07 11:00, 1,055 of 93,349; LINK 2019-09-25 13:00, 589 of 57,107; LTC 2013-09-14 08:00, 10,395 of 109,960; SOL 2021-06-17 15:00, 43 of 41,961; XRP 2017-05-18 15:00, 92 of 77,745 — 15,796 in all, 11,560 of them inside the span of a 240 bar the asset has: no-trade hours, the interior ones among them the hours the check skips (D4).
- **The interval's three interior hourly closes.** Of 173,363 intervals, 167,516 (0.9663) hold all three, 3,511 two, 1,954 one and 382 none; on the 172,902 union-adjacent intervals, the ones a return index maps, 167,452 (0.9685). Per asset all three are present in ADA 0.9936, AVAX 0.9792, BTC 0.9913, DOGE 0.9402, DOT 0.9980, ETH 0.9799, LINK 0.9773, LTC 0.8639, SOL 0.9988 and XRP 0.9990 of its intervals; the thinnest asset-years are DOGE 2019 (6 of 63), LTC 2015 (726 of 1,962), ETH 2015 (454 of 844) and BTC 2013 (315 of 505). The check is thinner wherever an hour is missing — disclosed here, not repaired, since the survey fixes "a missing hour is skipped". 461 intervals map to no return index: the asset lacked a union stamp between its two bars. The count is over the 240 files' own bars; BTC's six fills split five of its intervals in the state machine's series, the parts ending at a fill holding no hourly close.
- **The hourly path ends at the 4h close arm A reads.** All 173,373 240 bars hold at least one hourly bar; 170,400 hold the bar opening 3h in, whose close equals the 240 close in every one, and in every bar the last present hourly close equals the 240 close. The fourth hourly close, where present, is therefore the 4h close itself, and the first three are what the 4h rule cannot see; in the 2,973 bars without it, the last present interior close is the 4h close (D4).
- **Arm A's anchor stands.** Records 45, 46, 48 and 49 hold the same arm A at the registry's precision — annualised Sharpe 1.405 (records 48 and 49: 1.404998307684581), decisive 1.3716, maximum drawdown 0.2154, turnover 146.19 (146.18534602048504), drag 0.0703, benchmark 1.2128 and 1.2447 — record 49 run at `bf515702a`, an ancestor of this branch's cut, and no commit since touches a package or file an arm-A build reads. The arm-A pre-flight re-checks the anchor after the hash (D9).
- **The DSR leg in numbers of the code.** `expected_max_sharpe(5, V)` is `1.192594001014789 · √V`, against trial 4's `1.0521228241893004 · √V` at four trials.
- **The dispersion's four registered Sharpes** are 0.02374 and 0.02959 — five decimals, the precision records 45 and 46's lost writer stored — and 0.030191886721210086 and 0.03028127927651177, records 48 and 49's, stored unrounded.
- **The count stands at four records and no orphan.** Record 49 is B1's fourth record and its `attempt.counted` is empty, written to the log `60c9f39c37ec81b4a53396218b690304`, the one row of `docs/reference/trial-attempt-logs.txt`, the workstation `zcrypto-ops`'s.
- **T0123 ripens on any ADOPT.** Its `ripe_when` names no combination trial — `git grep 'combination'` over the topic finds nothing — so a B1 adopt would ripen it directly; D13 qualifies it.
- **The engine has no hourly path.** Every cycle order ends by about B+3h47 after its boundary (`cli/engine/executor.py:112-115`) and the store holds the 1440 and 240 grids alone (`cli/engine/store.py:42`): an hourly exit has neither an intra-cycle order path nor a 60 grid to read, which D13's adoption path names.

## Operating model

- **One session, one machine, one look.** The session holding this branch's worktree builds, pre-flights and registers trial 5 on the workstation `zcrypto-ops`, whose clone holds the one listed trial-attempts log (`60c9f39c37ec81b4a53396218b690304 zcrypto-ops`, `docs/reference/trial-attempt-logs.txt`). D12's step 4 is a single `--register` run. The model has no other session running a family-B1 subject while this branch is open, no second machine and no restored or copied log; each of those is spec 00133's to count and refuse (its D3–D6 and "What stays prose"), not this spec's to design for.
- **The processes.** Every run is one blocking `uv run zcrypto research eval` process in this branch's worktree: the pre-flight's plain eval, a `--reading` re-run of it only on a stop, and the one `--register` run — no daemon, timer, background job or concurrent run. A run reads `data/ohlc-full`, a symlink to the main checkout's canonical set, and writes nothing under it; it makes no network call — the count reads `origin/develop` through local git alone (spec 00133 D3) — and touches none of the fleet roles the workstation also runs.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, one per clone, shared by every worktree and session of it and appended under its flock (spec 00133 D1). Its unit is an attempt, identified across copies by the triple (log id, attempt id, the `line_hash` of its `begin` line) (spec 00133 D3); an attempt is open from its `begin` line, written before the fit, to its `end` line, written before the print (spec 00133 D2), and an open one is alive while its recorded `pid` runs under its recorded `boot` on this host (spec 00133 D3's liveness test).
- **The registry and the reading ledger** — `docs/reference/trial-registry.jsonl` and `docs/reference/reading-ledger.jsonl`, tracked, append-only and hash-chained; this branch's worktree is their one writer while the branch is open, and they reach develop through its pull request. A record's unit is its `trial_id` with its `record_hash`, a reading's its `reading_id`; D12's step 2 checks that both files equal develop's before the append, so the append chains onto develop's last line.
- **The data** — the frozen set, read-only, its unit the block `8216f4db…49a1` the reader records (D5).

## Hypothesis (trial 5, pre-registered by this spec's sha256)

Arm A sets a lookback to −1 at a new `w`-bar low of 4h closes and is blind for the four hours between boundaries; the plan gives stop distances to the hourly risk layer (`docs/research/00.master-plan.md:182`). Checking the arm's own channel at each hourly close exits a trend earlier when the breach holds to the 4h close, and adds a false exit — and a re-entry at the next new 4h high — when it does not (`docs/research/10.phase4-b1-candidate-hypotheses.md:79`). **Arm B — each adopted arm with a lookback's +1 state also set to −1 at the first hourly close inside the interval that breaches the level at which the 4h close would be a new `w`-bar low — has a higher mean net-of-cost return than arm A at 0.006 per side (SPA p < 0.05, full window) and a lower maximum drawdown** (`:78`, verbatim). Arms: **A** = the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46, 48 and 49 built it; **B** = the same ensemble with its directions from the state machine plus the hourly exit check, on arm A's weights and vol scalar. One knob, the exit's sampling, judged by the pre-registered decision matrix (D10). Stop-loss rules always lower expected return under a random walk and can add value under momentum, so the knob's sign is a test of hourly momentum in these pairs (`:79`). The survey's expectations stand: turnover up, since a false exit can add a round trip A never pays and an early exit adds none; maximum drawdown down; the knob's own failure mode is whipsaw, which the false-exit count bounds (`:85`). Its honest prior stands: about 0.05 that it is adopted, about 0.25 that the point estimate favours B, about 0.7 that the drawdown falls — hourly closes breach a 4h-close channel at least as often as 4h closes do, a false breach can cost a round trip plus the gap to the next new high, and the mean-difference head-to-head penalizes the exposure B gives up (`:95`).

## D1 — the arms: arm A is records 45, 46, 48 and 49's, arm B changes its directions alone

- **Arm A** is built as `_b1_volume_inputs` builds it (`cli/research/subjects.py:1153-1188`): `fed = _ffill_btc(h4_prices)`; for each `(lookbacks, target_vol)` in `_B1_A2_ARMS` (`:536`), `a2_book_returns(fed, config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_B1_LOOKBACK, basket_lookback=_B1_LOOKBACK, periods_per_year=PPY_4H))`; arm A is the per-asset `statistics.mean` of the three `asset_positions` at every return index.
- **Arm B** is the same three configs, each arm's position on asset `a` in slot `i` of return index `k` (D3) `weights_a[k].get(a, 0.0) * d_b[a][k][i] * vt_a[k]` — `0.0` in place of `d_b[a][k][i]` where `d_b[a][k]` is `None` — with `weights_a = _inverse_vol_weights(fed, lookback=_B1_LOOKBACK)`, arm A's weights, one path for the three arms since each arm's `basket_lookback` is 180; `d_b` that arm's slot directions (D2); and `vt_a` that arm's `a2_book_returns(...)["vol_target_positions"]`, arm A's vol scalar on arm A's own base returns; averaged per asset per slot over the three arms as arm A is. This is the survey's arm B: "the three arms with arm A's weights and vol scalar and B's directions from the state machine plus the hourly exit check" (`docs/research/10.phase4-b1-candidate-hypotheses.md:81`).
- Everything else is arm A's: the asset returns, the costing (D6), the B1 literals `_B1_COST_PER_SIDE`, `_B1_A2_ARMS`, `_B1_LOOKBACK`, `_B1_DECISIVE_START`, `_B1_N_RESAMPLES`, `_B1_FROM_2016` (`cli/research/subjects.py:535-540`) and the SPA grid `_B1_HOURLY_RV_GRID` (`:766`), reused and not restated — trial 5 runs B1's protocol, so a change to one of them is a change to every B1 trial's instrument (spec 00130 D2).
- **The files the build touches, a closed list**: one new module, `cli/alpha/b1_exit.py` (D2's state machine and directions, D3's slot positions, price paths and costing, D8's engagement helpers); in `cli/research/subjects.py`, new constants, the two subjects' build halves, rule and key sets, and their two `SUBJECTS` entries (D11), with no existing function of it changed; `README.md`'s `research eval` `--subject` row; and the tests the plan names. No change to `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/alpha/b1.py`, `cli/alpha/b1_rv.py`, `cli/alpha/b1_volume.py`, `cli/alpha/b2.py`, `cli/features/*`, `cli/portfolio/*`, `cli/engine/*` or any adopted artifact. **Author's call**: the module's name, beside trial 3's `cli/alpha/b1_rv.py` and trial 4's `cli/alpha/b1_volume.py`.
- **Identity, held by tests**: with every interior hourly close absent, every lookback's four slot states equal `_donchian_signal`'s state at every own bar, each arm's four slot directions equal `_asset_directions_a2`'s direction, arm B's four slot positions equal arm A's position, and arm B's net (D3) equals `net_of_cost(arm_a, returns, cost_per_side=_B1_COST_PER_SIDE)` exactly — so the knob is the hourly check and nothing else; and on the fixture, B's slot direction is at or below A's direction at every arm, asset, return index and slot where both are present.

## D2 — the exit check: A2's state machine, a +1 state also set to −1 at an interior hourly close

- **The survey fixes every value** (`docs/research/10.phase4-b1-candidate-hypotheses.md:82`, verbatim): "Hourly sampling, §6's risk-layer cadence (`docs/research/00.master-plan.md:182`); the breach level for lookback `w` in the interval after boundary `k` is the minimum of the last `w − 1` four-hour closes, the level at which `close[k+1]` would be a new `w`-bar low under the channel's definition at band 1.0 (`cli/features/channel.py:6-19`); the exited state is −1, A2's own new-low state (`cli/alpha/a2.py:75-76`); the check applies to a lookback at +1, one still at its initial 0 being left to the 4h rule; it runs on the interval's first three hourly closes, the fourth being the 4h close arm A already reads; a missing hour is skipped; exits only — entries stay on the 4h signal layer (`docs/research/00.master-plan.md:181`)." Nothing below re-chooses one of them.
- **The 4h rule is A2's, on the asset's own series**: `own_prices` the non-`None` prices of `fed[a]` (`cli/alpha/a2.py:94`), `cp = channel_position(own_prices, window=w)`, `band` 1.0 (`A2Config`, `:32`); at own bar `j`, `cp[j] >= band` sets +1, `cp[j] <= -band` sets −1, otherwise the state is held (`:68-78`).
- **The interval after own bar `j`** runs from `close[j]` to `close[j+1]`. Its interior hourly closes are the closes of the hourly bars opening at `own_ts[j+1]`, `own_ts[j+1] + 1h` and `own_ts[j+1] + 2h`, in that order — offsets 1, 2 and 3, closing 1, 2 and 3 hours into the 240 bar `j+1`; that bar's fourth hourly bar closes at its 4h close. The interval holds no other hourly close: no hourly bar lies outside a 240 bar, and none in a fill's span (measured, 0 of 681,932 and 0 at each of the six fills).
- **The breach.** **Author's call** — the breach test is `channel_position`'s own expression (`cli/features/channel.py:16-18`) on the window of the last `w − 1` four-hour closes, `own_prices[j+2−w .. j]`, `close[j]` included, with the hourly close `h` in `close[j+1]`'s place, at or below `-band`: with `lo` and `hi` the window's minimum and maximum, `h` breaches when `hi > lo` and `2 * (h - lo) / (hi - lo) - 1 <= -band`. At band 1.0 that is `h` at or below the survey's breach level, `min(own_prices[j+2−w .. j])`, with the window not flat — a close equal to the level breaches, as `channel_position` reads a close equal to the window's low as −1, and a flat window breaches nothing, as it reads 0 there. One expression for the hourly and the 4h test, so the two agree on every tie and every rounding; a test holds that `new_low(own_prices[j+2−w : j+1], own_prices[j+1], band=band)` equals `cp[j+1] <= -band` at every own bar `j+1` where `cp` is defined and the window is whole.
- **The exit.** At the first interior close, in time order, that breaches while the lookback is at +1, its state becomes −1 for the rest of the interval; the check applies only at +1, so a lookback exits at most once per interval, and a lookback at −1 or at its initial 0 is not checked. A missing interior hour is skipped: no check at it.
- **The next boundary continues from B's state**: at `close[j+1]` the 4h rule runs from it — a new high re-enters at +1, "re-entry only on A2's own rule"; a new low sets −1; otherwise the exit's −1 is held until A2's next new high.
- **An exit event** is `(j, offset)` of one lookback; it is **early** when arm A's same lookback exits at that interval's 4h close and **false** when it does not (`:84`). B at +1 implies A at +1 (below), so A's state over the interval is +1 and A exits at `close[j+1]` exactly when `close[j+1]` is a new `w`-bar low: early is `new_low(prior, own_prices[j+1], band=band)`, false its negation.
- In `cli/alpha/b1_exit.py`, `interior` holding one triple per own bar — the interior closes of that bar, `None` where the hour is missing; entry 0 is read by no interval — and returning one four-slot tuple per own bar `j` for the move `j → j+1`, slot 0 the state from `close[j]`, slots 1–3 the state from each interior close, and the events `(j, offset, early)`:

```python
def new_low(prior: list[float], close: float, *, band: float) -> bool:
    lo, hi = min(min(prior), close), max(max(prior), close)
    return hi > lo and 2 * (close - lo) / (hi - lo) - 1 <= -band


def donchian_signal_hourly_exit(
    prices: list[float],
    interior: list[tuple[float | None, float | None, float | None]],
    *,
    window: int,
    band: float,
) -> tuple[list[tuple[float, float, float, float]], list[tuple[int, int, bool]]]:
    cp = channel_position(prices, window=window)
    held, out, exits = 0.0, [], []
    for j in range(len(cp)):
        if cp[j] >= band:
            held = 1.0
        elif cp[j] <= -band:
            held = -1.0
        slots = [held]
        for offset, h in enumerate(interior[j + 1], start=1):
            if held == 1.0 and h is not None:
                # held reached +1 at some j' <= j with j' >= window - 1, so the window is whole.
                prior = prices[j + 2 - window : j + 1]
                if new_low(prior, h, band=band):
                    held = -1.0
                    exits.append((j, offset, new_low(prior, prices[j + 1], band=band)))
            slots.append(held)
        out.append((slots[0], slots[1], slots[2], slots[3]))
    return out, exits
```

- **Arm B's slot directions per arm**: `_asset_directions_a2`'s body (`cli/alpha/a2.py:92-111`) with each lookback's four-slot states mapped onto the union by `_map_to_union_index` (`cli/alpha/a1.py:83-95`) in place of `_donchian_signal`'s states — at return index `k`, per slot `i`, the mean over the arm's lookbacks clipped at 0; `None` wherever any lookback's mapping is `None`. The interior closes are one list per asset, shared by every lookback and every arm. A config with `short="on"` is refused (`AlphaError`): **Author's call** — the argument that B's direction never exceeds A's rests on the clip at 0.
- **B never carries exposure A has shed.** B's state is at or below A's on every lookback at every bar and slot: both start at 0; at a 4h close a new high sets both to +1, which nothing exceeds, a new low sets both to −1, and otherwise both hold; inside an interval B's one move is +1 → −1 and A's state does not move. The mean over lookbacks and the clip at 0 are monotone, and A's weight and A's scalar are at or above 0, so B's position in every slot is at or below A's on every asset at every return index (`docs/research/10.phase4-b1-candidate-hypotheses.md:80`).

## D3 — the interval's return split at each exit hour, and the hourly trade at 0.006 per side

- **The survey's split** (`docs/research/10.phase4-b1-candidate-hypotheses.md:81`): "the interval's return is split at the exit hour — the pre-exit position earns `close[k]` → the exit close, the post-exit position the exit close → `close[k+1]` — and the hourly trade is charged 0.006 per side; the next boundary continues from B's state."
- **The slots.** Return index `k` has four slots: slot 0 from `close[k]` to the interval's first interior close, slots 1–3 from the interior close at offsets 1–3 to the next, slot 3 ending at `close[k+1]`. Arm B's position on an asset in slot `i` is D1's with that slot's direction; arm A's is one position for all four. **Author's call** — several position changes in one interval, from another lookback or another arm's lookback exiting at a later interior close, split the interval at each of them: the survey's split at the exit hour, applied to every interior close at which arm B's position changes.
- **The price path** of asset `a` at return index `k`: `P0 = fed[a][k]`; for offsets 1–3, `P_i` the close of the hourly bar opening at `h4_ts[k+1] + (i − 1)h`, the interior close of union bar `k+1`, or `P_{i−1}` where that hour is missing; `P4 = fed[a][k+1]`; no path where `fed[a][k]` or `fed[a][k+1]` is `None`, where arm A's return is `None` and is read as 0.0. Where both are present the asset's own bars at `k` and `k+1` are adjacent, so the union bar `k+1` is its own bar and its interior closes are the ones its state machine read (D2).
- **The gross.** The asset's gross at `k` is `Σ_i p_i · (P_{i+1} − P_i) / P0`, each leg's move read in units of the boundary close. **Author's call**: a position is a fraction of the boundary's equity held through the interval with no rebalancing — the convention by which `net_of_cost` prices it at `p · r` (`cli/alpha/b2.py:263-273`) — so a cut at an interior close sells that fraction of the holding and the post-exit holding earns `p_post · (close[k+1] − h) / close[k]`; with no change the legs telescope to `p · r`, which a leg read as `(close[k+1] − h) / h` would not. An interval whose four slot positions are equal is computed as `p0 * (P4 / P0 - 1)`, arm A's own expression, so B with no exit equals A bit for bit.
- **The cost.** Every change of an asset's position — at a boundary, and at an interior close — is charged `cost_per_side · |Δp|`, 0.006 copied from the survey, the change measured as `net_of_cost` measures every boundary trade, in units of the boundary's equity with no drift adjustment. **Author's call**: the hourly trade's notional is not rescaled by `h / close[k]`, since no trade the records costed was rescaled by its own drift.
- In `cli/alpha/b1_exit.py`:

```python
def net_of_cost_hourly(
    slot_positions: dict[str, list[tuple[float, float, float, float]]],
    paths: dict[str, list[tuple[float, float, float, float, float] | None]],
    *,
    cost_per_side: float,
) -> list[float]:
    assets = list(slot_positions)
    previous = [0.0] * len(assets)
    net: list[float] = []
    for k in range(len(slot_positions[assets[0]])):
        gross, traded = 0.0, 0.0
        for i, asset in enumerate(assets):
            ps, path = slot_positions[asset][k], paths[asset][k]
            if path is not None:
                if ps[0] == ps[1] == ps[2] == ps[3]:
                    gross += ps[0] * (path[4] / path[0] - 1)
                else:
                    gross += sum(ps[s] * (path[s + 1] - path[s]) / path[0] for s in range(4))
            for p in ps:
                traded += abs(p - previous[i])
                previous[i] = p
        net.append(gross - traded * cost_per_side)
    return net
```

- **Turnover.** `turnover_b` is `book_turnover` (`cli/alpha/b1.py:210-222`) over each asset's slot positions flattened in time order, four per return index, from flat — the boundary and the intra-interval trades together, the survey's "turnover including the intra-interval trades" (`:84`) — which equals `book_turnover(arm_a)` when every slot equals arm A's position, as with no exit event; `turnover_b_intra` is the part traded at interior closes, `Σ_a Σ_k Σ_{i=1..3} |p_i − p_{i−1}|`.
- The ×1.5 series is the same function at `1.5 * _B1_COST_PER_SIDE`.

## D4 — eligibility and edge cases

- **The state machine's series, fills included.** **Author's call** — the check runs on the series arm A's state machine runs on, the non-`None` prices of `fed[a]`, so BTC's six forward-filled stamps are bars of it and the breach level reads their closes as arm A's channel does; an interval ending at a fill has no interior close (measured), so no check runs in it.
- **An interval a return index does not map** — 461 of the 240 files' intervals, the asset lacking a union stamp between its two bars (measured) — still runs the check, and its state carries forward as A2's does; no position exists there, its weight being 0 and its return `None` (`cli/alpha/a1.py:157-189`). **Author's call**: the state machine is the asset's own, as A2's is, whatever the union holds.
- **An interval spanning more than 4h** checks the interior closes of the bar that ends it alone; no hourly bar lies in the gap (measured).
- **Missing hours.** A missing interior hour is skipped — 3,511 of the 240 files' intervals lack one interior close, 1,954 two and 382 all three (measured) — and in the price path it carries the previous close, so its slot earns nothing and the next present close carries the move (D3). Where all three are missing no check runs in the interval and arm B's position holds through it. Where the hour opening 3h in is missing — 2,973 of the 173,373 240 bars (measured) — the last present interior close is the 4h close itself, so a breach there is an early exit at arm A's own exit price, which D8's counts carry as any other exit, its trade charged in the return index before arm A's.
- **Warm-up.** A lookback reaches +1 only once `cp[j] >= band`, which needs `j >= w − 1`, so whenever the check runs the window of `w − 1` closes before `close[j+1]` is whole.
- **Refusals, never drops** (`AlphaError`, naming the asset and the stamp): an hourly close that is not a finite number above 0; hourly stamps not strictly increasing, tz-naive or off the hour; an hourly bar whose 240 bar the asset's own series lacks, where the 60 and 240 files disagree about which 4h bars traded; hourly stamps and closes of unequal length; an `interior` list whose length is not the price series'. Dropping one would move a check or a split. None can fire on the frozen set: every hourly row is clean and inside a 240 bar of its asset (measured).
- **A windowed evaluation** reads both grids under the same bounds (`cli/research/subjects.py:775-802`), so the state machine warms up from the window's first bar, as arm A's does. The bounds are bar-open stamps, read inclusively (`ObservedReader.read_series` keeps `ts <= end`): a window ending on the 4h grid keeps the 240 bar opening at its end and, of that bar's hourly bars, the first alone, so the last interval's closes at offsets 2 and 3 read as missing hours. The trial reads no window.

## D5 — the data and the window: the frozen `ohlc-full` set's 240 and 60 files, whole

- `--dataset ohlc-full`, no `--window`, no `--as-of`: the owner's "As trials 3 and 4 (Recommended)", whose option read "Frozen ohlc-full with its 60 files, 2013-09-10 → 2026-03-31 (arm A reproduces record 45's arm A)" (the second `[iter-179]` entry). The set ends 2026-03-31, before the spent holdout's window, 2026-04-01 → 2026-07-09 (`docs/research/13.phase5-holdout-ledger.md:9`): no holdout question arises. The survey's Data line names this set first (`docs/research/10.phase4-b1-candidate-hypotheses.md:83`).
- **The reads** are `_b1_hourly_rv_reads(reader, dataset, window, as_of, accept_holes, subject=subject)` (`cli/research/subjects.py:775-802`), trial 3's reads half, called and unchanged: its as-of refusal; the 4h union through `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)` — measured 27,338 stamps, 27,337 return indices; the window refusal `_b1_refuse_window` (`:545`); and per asset `reader.read_series(dataset, f"{asset}/EUR/60.parquet", window=window)`, its `ts` and `close`, a file polars cannot read a `SubjectError` naming it. **Author's call**: reused rather than copied — a copy would be a second path to the same block, and the reuse lets trial 3's basis test, which already pins this half, stand for this trial's reads too. The subject's intervals are `(240, 60)`, so the command refuses an incomplete set before any read (`required_relpaths`, `cli/research/subjects.py:106-107`).
- **The inputs' identity** is the block the measured basis names: `8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1` over the ten 240 and ten 60 files, 855,305 rows, span 2013-09-10 20:00 → 2026-03-31 23:00 — record 48's `dataset_hash`. The plan's data-gated basis test reproduces it, the union's shape, the hourly coverage, the interior counts, the seam and the fills from the reads half, computing no state.
- The decisive window starts at return index 1380 (`_B1_DECISIVE_START`), the from-2016 cut at the first `k` with `h4_ts[k] ≥ 2016-01-01T00:00Z`, the bar-start convention records 45, 46, 48 and 49 read; a per-year figure keys a return index by its bar-start year `h4_ts[k].year` and an exit event by the bar-start year of the own bar `j` that opens its interval, which is `h4_ts[k].year` wherever a return index maps the interval.

## D6 — the costing, the benchmark and the slices: the records', with D3 for arm B

- `returns = {a: _asset_returns(fed[a])}`; arm A's net through `net_of_cost(arm_a, returns, cost_per_side=_B1_COST_PER_SIDE)` (`cli/alpha/b2.py:252-273`: per-asset turnover from flat, a missing return read as 0.0), the ×1.5 series through the same at `1.5 * _B1_COST_PER_SIDE`, as trials 3 and 4 compute them — never `a2_book_returns`' `net_returns`, which is uncosted. Arm B's net and ×1.5 series through D3's `net_of_cost_hourly` at the same two costs.
- The benchmark: `benchmark_4h_net_of_cost(h4_prices, cost_per_side=_B1_COST_PER_SIDE)` on the raw union prices (`cli/portfolio/record44_legs.py:64`).
- The slices: `calendar_year_slices(series, h4_ts)`, each return keyed by its close year `h4_ts[k + 1].year`, 2013 and 2026 dropped (`cli/portfolio/record44_legs.py:108-119`, `:31`).

## D7 — `var_trials`: B1's family dispersion over records 45, 46, 48 and 49 and arm B, two-pass, from the registered Sharpes

- **The source**: the registered `per_period_sharpe_4h` of records 45, 46, 48 and 49 — 0.02374, 0.02959, 0.030191886721210086 and 0.03028127927651177 (`docs/reference/trial-registry.jsonl:45`, `:46`, `:48`, `:49`, measured above) — the owner's "var_trials = B1's family dispersion over records 45, 46, 48, 49 and this arm B" (the second `[iter-179]` entry), held in the subject as `_B1_EXIT_RECORDED_PER_PERIOD_SHARPES = (*_B1_VOLUME_RECORDED_PER_PERIOD_SHARPES, 0.03028127927651177)` and pinned by an ungated test against the four committed records. **Author's call**: each value at the precision its record stores — records 45 and 46 at their five decimals, records 48 and 49 unrounded — since the dispersion reads the registry's values and never a re-derivation (trial 3's D6).
- **The arithmetic.** `per_period_sharpe_4h = sharpe(net_b)` — unannualised (`cli/validation/metrics.py:26-40`), the per-period Sharpe `a1_kill_bar` deflates — then `var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, per_period_sharpe_4h])`, the sample variance over five (denominator 4). All five are 4h per-period Sharpes over the same 27,337 returns, so no periodicity conversion applies.
- **The two passes.** The first builds arm B and its per-period Sharpe; the second calls arm B's bar (D10) with `n_trials=5` and that `var_trials`.
- **Arm A's pre-flight bar** takes `arm_a_var_trials = statistics.variance([0.02374, 0.02959, 0.030191886721210086, 0.03028127927651177, sharpe(net_a)])`, arm A's own Sharpe in arm B's place, since arm B's does not exist before the run and the pre-flight computes none of arm B's returns — one of the conventions the owner's "As trials 3 and 4" carries: trial 3's answer "Arm A stands in (Recommended)" (the third `[iter-177]` entry), and trial 4's option text "with arm A standing in for the pre-flight" (the second `[iter-178]` entry).
- **What it does to the leg**, from the code: `dsr_pass` holds exactly when `Φ((sr − 1.192594001014789 · √var_trials) · √27,336 / √(1 + sr² / 2)) > 0.95`, `sr` the bar's per-period Sharpe — `expected_max_sharpe` at `n_trials` 5 (measured) and the PSR at the kill bar's default moments, skew 0 and kurtosis 3 (`cli/validation/dsr.py:46-49`; `cli/alpha/killbar.py:70` passes none). Neither the variance nor the bar's figure is computed here.
- Records 45, 46, 48 and 49 keep their registered bars: the registry is append-only and nothing re-verdicts them.
- **Author's call** — an orphan: should spec 00133's count find an attempt in family B1 that never landed, the register run is refused (D12), and no orphan's Sharpe enters this dispersion; the next subject's count and dispersion go to the owner, the question spec 00133 leaves to the plan review of each trial ("What stays prose").

## D8 — the engagement pre-flight, its dead-knob stop, and the diagnostics recorded with the run

- The pre-flight count is read from closes alone — both state machines read closes only, and no position and no return of arm B is computed — after this file's sha256 is taken and before any verdict (`docs/research/10.phase4-b1-candidate-hypotheses.md:36`, `:84`). Every item is a metric of the pre-flight subject and of the trial:
- `exit_events_per_year`: `{arm: {asset: {lookback: {year: [events, early, false]}}}}`, the arm `"1"`–`"3"` in `_B1_A2_ARMS` order, the lookback and the year as strings, the year D5's for an event; every year in which the asset has a state value appears, zeros included — the survey's "hourly exit events per year per arm × asset × lookback". **Author's call**: the early and false split, which the survey records with the run, is carried in the pre-flight too, since it reads closes alone (D2); and the grain is kept although arms 2 and 3 carry equal counts by construction — both run lookbacks (60, 120, 240), and the state machine reads no target vol.
- `exit_events`, `exit_events_early`, `exit_events_false`, the totals over every arm, asset, lookback and year, and `share_false` = `exit_events_false / exit_events`; **Author's call**: a build with no exit event refuses (`ValidationError`), since the share divides by the count — the dead knob's commonest form, since with no exit B's states are A's, kept as D9 keeps a refusal.
- `hourly_closes_directions_differ`: the hourly closes `(k, i)` — return index `k`, offset `i` in 0–3, offset 0 its 4h close `close[k]` and offsets 1–3 its interior closes — at which, for any arm and any asset, arm B's clipped direction in force from that close `!=` arm A's direction at `k`, `None` equal to `None`, since both arms map the same `None`s; and `hourly_closes_directions_differ_per_year`, `{year: count}` over every bar-start year of the union's return indices, zeros included — the survey's "the hourly closes where B's clipped direction differs from A's". **Author's call**: offset 0 counts — a false exit held past the 4h close makes B's direction differ there and at every hourly close after it until A2's own rule re-enters — and the offsets are the union's hourly grid, so an asset whose hour is missing keeps its direction from the previous offset.
- **The dead-knob stop**: `hourly_closes_directions_differ == 0` — zero such closes — is a dead knob, an instrument finding: no run, no verdict, the trial unspent, as both precedents and the committed B2 rule hold (`docs/specs/00045-b1-seasonality-conditioning-design.md:44`; `docs/specs/00128-b2-family-opening-design.md:56`; `cli/research/subjects.py:523-530`). The rule carries the stop too (D10), so a register run on a dead knob that has an exit event is a stop, never a verdict; one with no exit event refuses before the rule (D9).
- **Recorded with the run** (`:84`): the early and false split above; `stamps_positions_differ`, the return indices at which any asset's arm-B position in any slot `!=` arm A's position; `turnover_a` (`book_turnover(arm_a)`, as the records hold it), `turnover_b` and `turnover_b_intra` (D3), and `turnover_reduction_pct` = `100 * (turnover_a - turnover_b) / turnover_a`. **Author's call**: the records' key and sign kept, so the expected increase reads negative.

## D9 — the arm-A pre-flight

- After this file's sha256 is taken as the spec hash and by no one before — arm A's figures largely predict arm B's column, so a read before the hash would be a look while the decisions could still move (trial 3's D7): (a) the reads' block is `8216f4db…`; (b) arm A reproduces record 45's arm A at the precision the registry stores: `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703 and the benchmark's 1.2128 and 1.2447, each at 4 decimals, and `turnover_a` 146.19 at 2; (c) arm A's bar — the headline call (D10) with `net_a`, arm A's ×1.5 series and arm A's slices, `n_trials` 5 and `arm_a_var_trials` (D7), every other argument the headline's — reads `passes` 1. (b) is checked before (c) is read.
- A failed pre-flight, this one or D8's, is an instrument finding: no run, no verdict, the trial unspent; the pre-flight subject's run is kept as a reading under iter-179 (D12, spec 00129 D7), and T0022 records what failed. A run whose build refuses — D8's no-exit refusal, a D4 refusal or any other compute refusal of either subject — prints no metrics, so no reading can keep it, a `--reading` re-run refusing alike before any append, and under `--register` its attempt ends failed, which counts 0 (spec 00133 D3, class "failed"): the same instrument finding, T0022 recording the refusal line.

## D10 — the bar, the SPA grid, the head-to-head, the drawdown pair and the decision matrix, fixed before the run

- **Arm B's bar, the headline cell**: `a1_kill_bar(net_b, bench, n_trials=5, var_trials=var_trials, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)` (`docs/research/10.phase4-b1-candidate-hypotheses.md:34`, at this trial's count). The kill-bar column is its `passes`, `dsr_pass and spa_pass and cost_stress_pass and worst_slice_pass` (`cli/alpha/killbar.py:110`): the DSR leg binds (`[iter-176]`).
- **The SPA grid, recorded**: for blocks {30, 102} × seeds {42, 7, 1234}, the decisive-window SPA p — at (30, 42) the headline's `spa_p_value`; at the other five cells `reality_check_pvalue([[net_b[k] - bench[k]] for k in range(1380, n)], mean_block=block, n_resamples=2000, seed=seed)["p_value"]`, trials 3 and 4's form (`cli/research/subjects.py:1268-1272`). The adopt row also requires the time-matched block, `spa_p_decisive_b102_s42` < 0.05: the owner's "the adopt row needs SPA significant at both blocks 30 and 102" (the second `[iter-179]` entry), the A family's 4h rule (`docs/research/10.phase4-decisions.md:159`, `[iter-074]` item 2). A cell that meets every other adopt condition with `spa_p_decisive_b102_s42` ≥ 0.05 parks with the block-sensitivity finding. The other four cells are recorded for the reader.
- **The head-to-head is the mean difference**: `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` over the full window, the primary read, and over `[k16:]` recorded beside it for comparison with records 45 and 46 (`cli/research/subjects.py:1274-1276`) — the owner's "Mean difference (Recommended)", whose option read "The matrix as the survey wrote it: adopt needs mean outperformance > 0, SPA p < 0.05 and a drawdown reduction; park on the point estimate plus drawdown; protocol unchanged, as the B2 opening design kept it" (the second `[iter-179]` entry). The full window is primary because no part of it is inert: the check acts from each lookback's first +1 state.
- **The drawdown pair**, read on the full window (`docs/research/10.phase4-b1-candidate-hypotheses.md:86`): `max_drawdown(net_b)` and `max_drawdown(net_a)` over the full series (`cli/validation/metrics.py:66-79`), and `max_drawdown_reduction_pct = 100 * (drawdown_a - drawdown_b) / drawdown_a`. B's maximum drawdown is *below* A's when `max_drawdown_reduction_pct` exceeds 1e-6, and *not below* otherwise — the B2 opening design's tolerance (`docs/specs/00128-b2-family-opening-design.md:66`), copied, which reads two drawdowns equal but for rounding as not below. A build in which arm A never draws down refuses (`ValidationError`), since the ratio divides by its drawdown.
- **The matrix** — the survey's drawdown-conditioned table (`docs/research/10.phase4-b1-candidate-hypotheses.md:88-93`) with trials 3 and 4's block-sensitivity row; every outcome in exactly one row — a failed bar is the last row, and on a passed bar the fourth row takes every outcome with mean outperformance ≤ 0 or a reduction ≤ 1e-6, the third every other with head-to-head SPA p ≥ 0.05, and the first two the rest, split on `spa_p_decisive_b102_s42`:

| Kill bar (B vs frozen benchmark, the headline cell) | Head-to-head (B vs A, full window) and maximum drawdown (full window) | Verdict |
| --- | --- | --- |
| pass, and `spa_p_decisive_b102_s42` < 0.05 | mean outperformance > 0 and SPA p < 0.05, and `max_drawdown_reduction_pct` > 1e-6 | **adopt** the hourly exits |
| pass, and `spa_p_decisive_b102_s42` ≥ 0.05 | mean outperformance > 0 and SPA p < 0.05, and `max_drawdown_reduction_pct` > 1e-6 | **park** (the block-sensitivity finding: the bar's significance does not hold at the time-matched block) |
| pass | mean outperformance > 0, SPA p ≥ 0.05, and `max_drawdown_reduction_pct` > 1e-6 | **park** (variant: the check at 15m) |
| pass | mean outperformance ≤ 0, or `max_drawdown_reduction_pct` ≤ 1e-6 | **reject** |
| fail | any — arm A having passed the same bar at the pre-flight | **reject** (an exit check that breaks the adopted arm's bar is harmful) |

Every quantity the matrix reads is a stored key read unrounded: the kill bar's `passes`, `spa_p_decisive_b102_s42`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full` and `max_drawdown_reduction_pct`. No risk-matched read: comparing B and A at matched volatility or exposure would be a protocol change, which the owner declined (the second `[iter-179]` entry). The rule, as the subject declares it (spec 00129 D4), with the two instrument findings its metrics show:

```python
def _b1_hourly_exit_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or m["hourly_closes_directions_differ"] == 0:
        return None  # instrument finding: no verdict, the trial unspent
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_full"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        if m["head_to_head_spa_p_full"] < 0.05 and m["spa_p_decisive_b102_s42"] < 0.05:
            return "adopt"
        return "park"
    return "reject"
```

The third instrument finding, the inputs' block against the measured basis, is not a metric and stays a pre-flight step of the plan.

## D11 — the registry record and the two subjects

- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B1`, `n_trials_in_family` 5, `variant` `B1-hourly-exit-a2eq-v1`, `iteration` `iter-179`; the command computes `spec_hash` — the sha256 of this file, the subject's declared spec — and the verdict by the subject's rule; `seeds` are the subject's declared (42, 7, 1234); `invocation` names `b1-hourly-channel-exits`, `ohlc-full`, window null, as-of null, holes false, comparator null and the commit; `datasets` is the reader's block (D5), `dataset_hash` its `compute_hash`, `8216f4db…` (measured); `attempt` carries the trial-attempts log's id, this run's attempt, its `begin`, its `absorbs` and its `counted`, expected empty (spec 00133 D8); `notes` is caller text written before the run (D12).
- **The subject `b1-hourly-channel-exits`**: `Subject("b1-hourly-channel-exits", (240, 60), _ASSETS, _build_b1_hourly_exit, spec="docs/specs/00135-b1-hourly-channel-exits-design.md", metric_keys=_B1_EXIT_METRIC_KEYS, seeds=(42, 7, 1234), verdict=_b1_hourly_exit_verdict, no_verdict="instrument finding: arm A fails the bar, or arm B's directions equal arm A's at every hourly close; no verdict, the trial unspent", family="B1", n_trials=_B1_EXIT_N_TRIALS)`, `_B1_EXIT_N_TRIALS = 5` — the two fields spec 00133 D4 adds, declared as it prescribes for the trial after record 49: four records, no orphan, and itself; every `a1_kill_bar` call its build makes, arm A's pre-flight bar included, passes that count. No incumbent, since arm A is built in the run (spec 00129 D3).
- **The metric keys, exactly these 46** (bools as 0/1, keys str): arm B's `ann_sharpe_noc`, `ann_sharpe_noc_decisive`, `per_period_sharpe_4h`; `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`; `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (Sharpes at 2,190 periods a year, the decisive ones from index 1380, the per-period one unannualised); `var_trials`; from the headline cell `dsr_corrected` (its `dsr`), `dsr_pass`, `spa_pass`, `spa_p_full` (its `spa_p_value_full`), `cost_stress_pass`, `worst_slice_relative_pass` (its `worst_slice_pass`), `passes`; `decisive_start` 1380 and `n_resamples` 2000; `arm_a_var_trials` and `arm_a_passes` (arm A's pre-flight bar, recomputed in the run); `spa_p_decisive_b30_s42`, `spa_p_decisive_b30_s7`, `spa_p_decisive_b30_s1234`, `spa_p_decisive_b102_s42`, `spa_p_decisive_b102_s7`, `spa_p_decisive_b102_s1234`; `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `head_to_head_mean_outperf_2016`, `head_to_head_spa_p_2016`; `max_drawdown`, `arm_a_max_drawdown` and `max_drawdown_reduction_pct` over the full series (D10); `spot_drag_pct_yr` and `arm_a_spot_drag_pct_yr` (`turnover / n × 0.006 × 2190`, `cli/research/subjects.py:1305-1306`, arm B's on `turnover_b`, the intra-interval trades included); `turnover_a`, `turnover_b`, `turnover_b_intra`, `turnover_reduction_pct`; `exit_events`, `exit_events_early`, `exit_events_false`, `share_false`, `exit_events_per_year`, `hourly_closes_directions_differ`, `hourly_closes_directions_differ_per_year`, `stamps_positions_differ` (D8). A build in which `turnover_a` is 0 refuses (`ValidationError`), since a ratio divides by it.
- **The pre-flight subject `b1-hourly-channel-exits-preflight`**, evaluate-only: `Subject("b1-hourly-channel-exits-preflight", (240, 60), _ASSETS, _build_b1_hourly_exit_preflight, spec="docs/specs/00135-b1-hourly-channel-exits-design.md", metric_keys=_B1_EXIT_PREFLIGHT_KEYS, seeds=(42,))` — no rule, no family, no trial count, so `--register` refuses it, its plain eval is admitted (spec 00133 D7) and a `--reading` keeps a stop. It computes no position and no return of arm B. Its 25 keys: `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown`, `turnover_a`, `arm_a_spot_drag_pct_yr`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive` (the anchors); `arm_a_var_trials`; arm A's bar's `dsr`, `dsr_pass`, `spa_p_value`, `spa_p_value_full`, `spa_pass`, `cost_stress_sharpe`, `cost_stress_pass`, `worst_slice_sharpe`, `worst_slice_pass`, `passes` (the keys `b2-arm-a-bar` declares, `_B2_ARM_A_BAR_KEYS`, `cli/research/subjects.py:377`); `exit_events`, `exit_events_early`, `exit_events_false`, `share_false`, `exit_events_per_year`, `hourly_closes_directions_differ`, `hourly_closes_directions_differ_per_year`.
- **The build in three halves**, so each consumer reads no more than it needs: the reads, `_b1_hourly_rv_reads` (D5), no compute, all the basis test calls; `_b1_hourly_exit_inputs(reads)` adds `fed`, the returns, `weights_a`, each arm's positions, vol scalar and directions, the interior closes per own bar, each arm's slot directions and exit events, the price paths and arm A's positions — no position or return of arm B — the hourly closes validated (D4) before `_asset_returns` divides by a close; the trial subject's metrics and the pre-flight subject's metrics each start from it. A compute error — `AlphaError`, `BacktestError`, `BenchmarkError`, `FeatureError`, `ValidationError` — is a `SubjectError` naming the subject and its window, as `_b1_volume_build` names trial 4's (`cli/research/subjects.py:1336-1350`).
- `README.md`'s `research eval` `--subject` row names both subjects without an internal term: the A2 4h ensemble against the same ensemble with each breakout's long state also ended at the first hourly close inside a 4h interval that breaches the level at which that interval's close would be a new channel low, reading the 4h and hourly series of `--dataset`, a frozen set only; and its evaluate-only pre-flight, the unconditioned ensemble's figures and bar and the hourly exits and closes whose directions differ, with no return of the hourly-exit book, kept with `--reading`.

## D12 — the run, through spec 00133's trial-attempts log

- **The gate stands.** Spec 00133 — `docs/specs/00133-t0222-trial-attempts-design.md`, merged into develop as pull request #730 (`64d416754`) — is on this branch's first-parent line through develop's `82cfedcab`: `Subject` carries `family` and `n_trials` (its D4), every `--register` run writes its `begin` line to the trial-attempts log before the fit and its `end` line before the print (its D2), the count refuses a subject declaring fewer trials than its family needs (its D3, D4) and a bucket past its budget (its D5), and a plain eval of a subject with a rule is refused (its D7). The module, the subjects, the run's record and its verdict land in this branch's one pull request; no separate build pull request.
- **The steps**, in order, after the plan review has closed and nothing this spec pins has changed since:
  1. The spec hash: `sha256sum docs/specs/00135-b1-hourly-channel-exits-design.md`, whose value the record's `spec_hash` must equal; this file is never edited after it.
  2. The develop check: `git fetch origin develop` and `git diff --quiet origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exit 0, so an append chains onto develop's last line.
  3. The pre-flights (D8, D9): `uv run zcrypto research eval --subject b1-hourly-channel-exits-preflight --dataset ohlc-full` — a plain eval of a subject with no rule, which spec 00133 D7 admits — read in order: the printed block against `8216f4db…`, the seven anchors, `passes`, then `hourly_closes_directions_differ` above 0 with `exit_events_per_year` and `hourly_closes_directions_differ_per_year`. On a stop, the run is kept as a reading: `uv run zcrypto research eval --subject b1-hourly-channel-exits-preflight --dataset ohlc-full --reading --iteration iter-179 --spec-hash <step 1's sha256> --notes "<what failed, quoted from step 3's output; no verdict, the trial unspent>"`, and T0022 records what failed. A pre-flight that refuses is kept as D9 keeps a refusal.
  4. The trial, one run, by the owner or on their word: `uv run zcrypto research eval --subject b1-hourly-channel-exits --dataset ohlc-full --register --iteration iter-179 --family B1 --n-trials 5 --variant B1-hourly-exit-a2eq-v1 --spec-hash <step 1's sha256> --notes "<below>"`.
- **No plain eval of `b1-hourly-channel-exits`**, before or after step 4: spec 00133 D7 refuses one, and step 4 is the trial's one look, which its `begin` line counts before the fit.
- **No `--verdict` assertion.** **Author's call**: with no plain eval before it, nothing has shown the verdict, so an asserted one would be a guess the command refuses after its print; the rule's verdict is stored.
- **The notes, written before the run.** **Author's call**: they name only what is fixed before it — the subject over `ohlc-full`, full history, no as-of; the two arms and the hypothesis, which D13's reject archives in the record; `var_trials` the variance of records 45, 46, 48 and 49's registered per-period Sharpes and arm B's, `n_trials` 5, the DSR leg binding; step 3's pre-flight figures, quoted; the park variants D13 names in the record; the matrix pre-registered by this spec's hash. The row that fired is read off the record's verdict and metrics, and the decisions-log verdict entry names it with its figures.
- **A refusal from the count.** If `required_n(B1)` exceeds 5 — an attempt in B1 that never landed — or bucket B has no trial left, step 4 is refused, before the fit or after its print (spec 00133 D3, D5), the refusal naming each orphan it counts and the bucket's spent figure; a refusal after the print leaves a look no record carries, whose printed metrics T0022's findings name and whose orphans T0016's budget line counts; the trial goes back to the owner through T0022, since this spec's hash fixes `n_trials` 5 and the dispersion's sources, and a further count is a new subject under a new spec (D7).
- **A stop by the rule** under `--register` — arm A failing its bar, or no direction differing — is kept as a reading carrying its attempt, which counts 0: the trial unspent (spec 00133 D3, class "stopped"); a refusal of its build is D9's.
- **After a verdict**: plan 00135's verdict task — the task after the register run, as plan 00134's Task 6 was for trial 4 — writes, with `iteration-closeout` loaded, the decisions-log entry `[iter-179] Verdict — B1 trial 5 <ADOPT, PARK or REJECT> (registry trial <N>, family B1 n=5)`, naming the row that fired, its figures and the engagement proof; T0022's findings and next steps; and T0016's budget line (B1 spent 5, 20 remain, less one for each orphan the record's `attempt.counted` lists) — and on an adopt D13's two topic changes — in the same commit as the record.

## D13 — what a verdict changes

- **Adopt** is a research-registry fact on the A2 ensemble alone and does not touch the live book — the owner's "Registry fact only (Recommended)", whose option read: "An adopt is a registry fact on the A2 ensemble alone. Deploying needs a P1 combination trial over record 47's book, then an engine design for intra-cycle exits on a 60 grid (a topic registered on the adopt), then T0123's promotion path." In that order:
  - the combination trial is P1's, outside every bucket's budget (`docs/research/13.phase5-decisions.md:29`), over record 47's book (`docs/reference/trial-registry.jsonl:47`), the survey's attribution rule (`docs/research/10.phase4-b1-candidate-hypotheses.md:38`);
  - the engine design: the engine's cycle orders end by about B+3h47 after the boundary (`cli/engine/executor.py:112-115`) and its store holds the 1440 and 240 grids alone (`cli/engine/store.py:42`), so an hourly exit needs an intra-cycle exit path and a 60 grid. Plan 00135's verdict task registers it on an adopt as a topic through `topic-ops`; **Author's call**: its `ripe_when` an evaluation statement, the P1 combination trial over record 47's book that carries trial 5's arm B reaching ADOPT in the registry, since the owner's order puts the design after that trial;
  - T0123's promotion path, its "Always" list — a new record, a builder-contract version bump, shadow concordance re-earned on the new contract — with the change class declared and ratified before the evidence, parity at ≥ 14 consecutive clean on-time days and the tracking band at ≥ 3 consecutive complete ISO weeks (`docs/open-topics/T0123-sleeve-promotion-path.md:37-41`, `:51`, `:59`). T0123's `ripe_when` reads any ADOPT in the registry (`:3`) and names no combination trial (measured), so this record would ripen it directly; **this spec decides that T0123's trigger is qualified so that this record ripens it only once that combination trial adopts**. Plan 00135's verdict task writes the qualification, in the same commit as the record, so no tree holds the adopt without it; on any other verdict T0123 is untouched.
- **Park** names its variants in the record — on the third row, the check at 15m; on the second, the block-sensitivity finding — each variant a new trial of the shared budget, which a park puts to the owner through T0022, its adoption path asked of the owner rather than inherited from this spec, as T0022's next steps hold for a park variant.
- **Reject** archives the hypothesis in the record and the decisions log; with it the survey's three candidates are spent, and T0022 goes back to the owner's pick between a park variant of trial 3 and closing the family as attributed out.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, or a refused build (D9) — spends no trial; T0022 records what failed.

## Out of scope

The park variant, the check at 15m — its own trial, which a park puts to the owner through T0022. A risk-matched read of B against A — a protocol change the owner declined (the second `[iter-179]` entry). Any engine work — an intra-cycle exit path, a 60 grid in the store, the topic D13 registers on an adopt. The B2 data work and the B2 baseline ruling the owner ordered after this trial ("then B2‘s data work, then B2 baseline ruling"), which follow this branch — T0023's. Hourly entries, a check on a lookback at 0, and any short side — the survey fixes exits only, from +1, with short off (D2). Arm B's vol target on its own book — the survey fixes A's weights and scalar (D1). An `ohlc-rolling` read of this check and any window but the frozen set's full history (D5). Re-verdicting records 45, 46, 48 or 49 at the new `var_trials`. Spec 00133's trial-attempts log itself, which this trial consumes and does not build. The combination trial over record 47's book, T0123's promotion and live serving. T0123's `ripe_when` before an adopt is registered (D13). Any change to the files D1 lists as unchanged. Trial 3's park variants.
