# B2 family opening — the funding-extreme de-risk overlay, its subject and trial 1

**Spec:** `docs/specs/00128-b2-family-opening-design.md` — binding; every constant, window and matrix row below is the spec's, repeated here only where a task needs the value in front of it. **Iteration:** iter-175. **Topic:** T0023 under T0016. **Branch:** `research/00128-b2-family-opening`, worktree `.claude/worktrees/b2-opening`.

**Goal:** the emission and overlay module `cli/alpha/b2.py`, the committed research subject `b2-funding-derisk`, and trial 1 registered through `zcrypto research eval` on the owner's word, with its verdict in the registry and the decisions log and T0023 and T0016 updated.

**Architecture:** one module mirrors `cli/alpha/b1.py`'s shape (a frozen config, pure functions over lists, engagement helpers); the subject in `cli/research/subjects.py` composes the existing readers (`_capturing_union` for the 4h closes, `ObservedReader.read_series` for the funding parquet), the three adopted A2 arms, the overlay, the frozen benchmark constructor `benchmark_4h_net_of_cost`, `a1_kill_bar` and `net_of_cost_verdict`, and returns the metrics block the command registers; its inputs half (`_b2_inputs`) computes positions, the feature and the scales and no return, and is all of the subject the trial's data meets before Task 4. No change to `cli/alpha/a2.py`, `cli/portfolio/*`, `cli/features/derivatives.py` or any adopted artifact.

**Tech stack:** Python 3.14, polars for the parquet reads, `cli.alpha.a1` (`_asset_returns`), `cli.alpha.a2` (`A2Config`, `a2_book_returns`), `cli.alpha.b1` (`book_turnover`), `cli.alpha.killbar` (`a1_kill_bar`, `net_of_cost_verdict`), `cli.features.derivatives` (`align_asof`, `funding_zscore`, `coverage_by_year`), `cli.derivatives.funding` (`PERP_SYMBOLS`, the parquet's schema), `cli.portfolio.crossfreq_system` (`CrossfreqSystemConfig`, `_ffill_btc`, `_A2_LOOKBACK`, `_PPY_4H`, `build_crossfreq_system_fast`), `cli.portfolio.record44_legs` (`benchmark_4h_net_of_cost`, `calendar_year_slices`), `cli.validation` (`sharpe`, `max_drawdown`), `cli.registry.observed` (`ObservedReader`), `cli.registry` (`TrialRegistry`), `cli.research.subjects` (`Subject`, `_capturing_union`), `cli.research.command` (the `eval` command).

## Global constraints

- TDD per task: the failing test first, the implementation second, the test green third; every mutation probe through `infra/scripts/mutate-probe.sh`, its verdict line in the commit message or the PR body naming the script.
- A probe's target test holds a fixture on which the defect and the correct code differ: an exactly-at-threshold z (`>` → `>=`); a z below −threshold (`>` → `abs(...) >`); a defined z distinct from the value carried before it (the normalisation, the close grid — a `z_window` of 2 scores every print ±1/√2, so these fixtures take 3 or more); prints between consecutive closes (the forward grid); a prefix cutoff the test computes as `union_ts[n - 1] + timedelta(hours=4)`, never through `close_grid` (a cutoff taken from the code under test moves with it); a flat stamp at z > 2 (the engaged count's position test); a hand-computed net list (the cost term).
- No return of arm B is computed over the trial's data before Task 4's owner's word: Tasks 1–3 run the full subject on synthetic series only, and meet the real sets only through the subject's inputs half (`_b2_inputs`: arm A's positions, the feature, the scales), which computes no arm-B return.
- The two stamp rulings (spec D2) live in `cli/alpha/b2.py` and nowhere else — `close_grid` is the one line that builds `ts[k] + 4h`, and the subject calls it rather than shifting a stamp itself; `cli/features/derivatives.py` is not edited.
- Every data-gated test gates on `substrate_root` / `nothing_found_under` (the six forms `tests/test_live_venue_opt_in.py` admits); the data-gated family runs locally before the first push (`uv run pytest -m data` over the files this branch touches), the skip count read.
- Commits by kind: `feat(alpha)` for the module, `feat(research)` for the subject, `test` where a task is tests alone, `docs` for the records; each task its own commit; no amend.
- Reads, in this order: the trio over Tasks 1–3's range (`pre-review`, `review`, `re-review` as CLAUDE.md orders them) closes with no open Critical or Important before Task 4's step 1, and the spec is not edited from that read to the registration (its sha256 is the `--spec-hash`); the trial's registration commit (the registry append, the decisions-log entry, the topics) is a records commit and takes a `pre-review` over itself, and the push that carries it a read of the delta over Task 4's range (open-pr's read line: a commit pushed after the read takes a read of the delta); the PR's read line on Opus with the Fable line unless the owner names a difficulty.

## Task 1 — the emission: `close_grid` and `funding_grid_feature`

**Files:** `cli/alpha/b2.py` (new), `tests/test_alpha_b2.py` (new).

1. `B2Config` frozen dataclass, spec D8's three fields: `z_threshold: float = 2.0`, `derisk_scale: float = 0.5`, `z_window: int = 90`; construction refuses a bool for any of them, a threshold that is not a finite number > 0, a scale that is not a finite number in (0, 1], a window that is not an int ≥ 2. The 60 s stamp tolerance is spec D2's ruling, not a knob: the module constant `_STAMP_TOLERANCE = timedelta(seconds=60)`, beside `_BOUNDARY = timedelta(hours=4)`.
2. `close_grid(union_ts: list[datetime]) -> list[datetime]`: the close stamp of every return index, its body the one line `return [t + _BOUNDARY for t in union_ts[:-1]]`.
3. `funding_grid_feature(prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], union_ts: list[datetime], *, config: B2Config) -> list[float | None]` — the union's bar-open stamps in, one value per return index out (`len(union_ts) - 1`):
   - refuses unsorted or tz-naive stamps, and any print more than `_STAMP_TOLERANCE` past its hour (`AlphaError` naming the print);
   - normalises each stamp to its hour (`replace(minute=0, second=0, microsecond=0)`);
   - maps a print whose `interval_hours` ≠ 8 to `None` before the z-score;
   - `funding_zscore(rates, window=config.z_window)` then `align_asof(normalised_ts, z, close_grid(union_ts))`.
4. Tests (known answers, synthetic series):
   - a print 30 ms past the hour and one on the hour align identically, the fixture's z at that print defined and distinct from the value carried before it, the assertion naming that value at that return index;
   - a print 61 s past the hour is refused by name;
   - an off-cadence print maps to `None` before the z-score, so the z-score is `None` at that print and at the next `z_window − 1` prints — every window that holds it, `funding_zscore`'s rule; mapped, never dropped (spec `00110` D7) — and the feature is `None` at every return index whose latest print is one of them;
   - the close grid, two-sided: bar-opens 00:00, 04:00, 08:00 and a print settled at 08:00 — return index 0 (close 04:00) carries the earlier print's value, index 1 (close 08:00) the 08:00 print's;
   - the truncating-prefix property over the inputs: for every `n`, the feature over `union_ts[:n + 1]` and only the prints whose normalised stamp is at or before `union_ts[n - 1] + timedelta(hours=4)` equals the first `n` values of the full run, the prints starting before the union's first close so every prefix sees one — the form of `tests/test_features_derivatives.py::test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit`, since truncating the grid alone holds under a look-ahead too;
   - a planted two-sigma print lifts the feature from its settlement hour's close until the next print's;
   - `B2Config` refusals, parametrised: threshold `0`, `-1.0`, `nan`, `True`; scale `0`, `1.5`, `nan`; window `1`, `2.5`, `True`; and scale `1.0` accepted.
5. Probes, each expect KILLED: the normalisation removed, against the 30 ms test; the tolerance check removed, against the 61 s test; `close_grid`'s `union_ts[:-1]` → `union_ts[1:]` (a 4h look-ahead), against the close-grid test and, as its own run, the prefix test; `close_grid`'s `t + _BOUNDARY` → `t` (one bar stale), against the close-grid test.

**Commit:** `feat(alpha): the B2 emission — funding prints to the 4h close grid, stamps normalised, leak-free`.

## Task 2 — the overlay: `derisk_scales`, `scale_positions`, `net_of_cost`, the engagement helpers

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

1. `derisk_scales(z_by_asset: dict[str, list[float | None]], *, config: B2Config) -> dict[str, list[float]]`: each value `config.derisk_scale if z is not None and z > config.z_threshold else 1.0`, the comparison one-sided as written; every list the same length or refused.
2. `scale_positions(asset_positions: dict[str, list[float]], scales: dict[str, list[float]]) -> dict[str, list[float]]`: elementwise product; the key sets must match; lengths must match.
3. `net_of_cost(asset_positions: dict[str, list[float]], asset_returns: dict[str, list[float | None]], *, cost_per_side: float) -> list[float]`: per return index `k`, `Σ_a p_a[k] · r_a[k]` (a `None` return read as 0.0) less `cost_per_side · Σ_a |p_a[k] − p_a[k−1]|`, every asset starting flat — `build_crossfreq_system`'s net-of-cost loop, and the one costing arm A, arm B and B's stressed series go through; key sets and lengths must match.
4. Engagement helpers, each keyed by `str(close_ts[k].year)` with every year present, zero included, `close_ts` being `close_grid`'s output:
   - `per_year_engaged_counts(asset_positions, scales, close_ts) -> dict[str, int]`: asset-stamps with position > 0 and scale < 1 — spec D6's "long and z > 2";
   - `per_year_positions_differ(a, b, close_ts) -> dict[str, int]`: return indices where any asset's position differs (B1's book-wide sense);
   - `per_year_turnover(asset_positions, close_ts) -> dict[str, float]`: per-asset |Δp| from flat, each change in the year of its index — `book_turnover`'s convention, which the window totals import from `cli.alpha.b1`;
   - `per_year_max_drawdown(returns, close_ts) -> dict[str, float]`: `cli.validation.max_drawdown` over each year's slice.
5. Tests:
   - a planted crossing scales exactly those stamps, a z of exactly 2.0 and a z of −3.0 both left at 1.0; `None` leaves 1.0; mismatched keys refused;
   - `net_of_cost` on a hand-computed two-asset case, the whole net list asserted: halving one asset's position `p` for one stamp takes `0.5·p·r` off that stamp's gross and adds `0.006 × |p|` of cost across the de-risk and the re-risk, and a `None` return contributes nothing;
   - the four engagement helpers on a two-year synthetic case with known per-year values, including a flat stamp at z > 2 that `per_year_engaged_counts` does not count.
6. Probes, each expect KILLED: `derisk_scales`'s `else 1.0` → `else 0.0`, against the `None` test; `z > config.z_threshold` → `z >= config.z_threshold`, against the planted-crossing test; `z > config.z_threshold` → `abs(z) > config.z_threshold`, against the same test; `net_of_cost`'s cost term dropped, against its hand-computed test; `per_year_engaged_counts`'s position test dropped, against the flat-stamp case.

**Commit:** `feat(alpha): the B2 overlay — a fixed half-scale while the funding z-score exceeds its threshold`.

## Task 3 — the research subject `b2-funding-derisk`

**Files:** `cli/research/subjects.py`, `tests/test_research_command.py` (the subject tests' home), `tests/test_research_b2_basis.py` (new; the data-gated basis, module-marked `data`).

1. `Subject("b2-funding-derisk", (240,), _ASSETS, _build_b2_funding_derisk)` registered beside the two existing subjects; `required_relpaths` is untouched — the funding files reach the datasets block through `read_series` itself, the block being `reader.block()`.
2. `_b2_inputs(reader, dataset, window, as_of, accept_holes) -> _B2Inputs`, a `NamedTuple` of `h4_ts`, `h4_prices`, `close`, `arm_a`, `z_by_asset`, `scales` — positions, the feature and the scales, never a return:
   - the 4h union through `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)`; `close = close_grid(h4_ts)`;
   - per asset, the funding prints through `reader.read_series("derivatives-funding", f"{PERP_SYMBOLS[asset]}/funding.parquet")`, no `window` — the z-score warms on the prints before the trial's start (spec D4) — then `funding_grid_feature(<its ts, funding_rate, interval_hours>, h4_ts, config=B2Config())`;
   - arm A as `build_crossfreq_system` builds its A2 sleeve, its constants imported, never restated: for each `(lookbacks, target_vol)` in `CrossfreqSystemConfig().a2_arms`, `a2_book_returns(_ffill_btc(h4_prices), config=A2Config(lookbacks=lookbacks, short="off", target_vol=target_vol, vol_lookback=_A2_LOOKBACK, basket_lookback=_A2_LOOKBACK, periods_per_year=_PPY_4H))["asset_positions"]`, then the per-asset `statistics.mean` over the three;
   - `scales = derisk_scales(z_by_asset, config=B2Config())`.
3. `_build_b2_funding_derisk(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — `_b2_inputs`, then:
   - arm B `= scale_positions(arm_a, scales)`; the returns `{a: _asset_returns(_ffill_btc(h4_prices)[a])}`; `net_a`, `net_b` through `net_of_cost` at `CrossfreqSystemConfig().cost_per_side`, and `net_b_x15` at 1.5 × it — never `a2_book_returns`'s `net_returns`, which is uncosted;
   - the benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=CrossfreqSystemConfig().cost_per_side)`, imported from `cli.portfolio.record44_legs`, on the raw union prices;
   - the slices: `record44_legs.calendar_year_slices(series, h4_ts)` (each bar keyed by its close year) with `"2020"` dropped as well — the window's partial years are 2020 and 2026, and that function drops 2026 itself;
   - the kill bar, spec D6's call: `a1_kill_bar(net_b, bench, n_trials=1, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=<net_b's slices>, benchmark_slices=<bench's slices>, decisive_start=1380, n_resamples=2000)`; each grid cell is the same call's `spa_p_value` (the decisive window) at its block and seed, blocks {30, 102} × seeds {42, 7, 1234};
   - the head-to-head, spec D6's call: `net_of_cost_verdict(net_b, net_a, mean_block=30, seed=42, n_resamples=2000)` on the full window and from `k21`, the first return index whose `close` is at or after 2021-01-01T00:00Z;
   - the drawdowns on the from-`k21` read; the engagement helpers over `close`; `coverage_by_year(close, z)` per asset as `[non_null, total]` per str year;
   - the metrics dict: spec D7's key list copied verbatim into the module constant `_B2_METRIC_KEYS`, bools as 0/1, keys str.
4. Tests. What refuses a run before a record exists, each met by the fixtures below: a window of at most `decisive_start` = 1380 return indices (`a1_kill_bar` refuses it) or one inside the arms' 181-index warm-up (`a2_book_returns` reads zero variance); a union of fewer than the ten assets (`load_union` reads all ten); stub-excluded slices that leave no year (`a1_kill_bar` refuses an empty `regime_slices`); a metric leaf other than a builtin int or float, or a key other than a str (the registry refuses a `YearCoverage`, a datetime, a str, a bool, an int key).
   - `tests/test_research_command.py`: the subject is registered and names its intervals and assets; on a synthetic frozen set of ten assets × at least 1,600 4h bars, every bar inside 2021, trending as the module's `_rows` writes them, and a synthetic `derivatives-funding` set (ten `<PERP>/funding.parquet` of `ts`, `funding_rate`, `interval_hours`; 8h prints on the hour from at least 30 days before the union's first bar, with planted spikes so the overlay engages on long stamps), `eval --register` into a `tmp_path` registry exits 0, the appended record's metric keys equal `_B2_METRIC_KEYS` and its `datasets` names the ten funding files. No test runs the full subject over the real sets.
   - `tests/test_research_b2_basis.py`, the pre-flight Task 4 runs: gated through `substrate_root` on `ohlc-rolling` and `derivatives-funding` (one `ObservedReader` over their common parent, the test asserting the parents agree), `_b2_inputs` over spec D4's window as of 2026-10-10 with holes accepted reproduces the spec's measured basis exactly — 12,645 return indices; 67,093 long asset-stamps of 126,450; the engaged asset-stamps per asset (ADA 311, AVAX 164, BTC 350, DOGE 318, DOT 347, ETH 344, LINK 304, LTC 334, SOL 210, XRP 323) and per close-stamp year (283 / 1,189 / 8 / 572 / 908 / 27 / 18 for 2020–2026), 3,005 in all; the feature defined at 12,645 return indices for eight assets, 12,464 for AVAX, 12,287 for SOL — and arm A lies within 1e-12 of `build_crossfreq_system_fast(...).sleeve_positions["A2"]`'s first 12,645 rows over the same window's daily and 4h unions. No arm-B return is computed.
5. Probes, each expect KILLED: the funding read handed the trial window (`, window=window` in the `read_series` call), against the basis test — the z-score then warms inside the window; arm A's mean replaced by the first arm's positions, against the basis test; one key left out of the metrics dict, against the synthetic register test.

**Commit:** `feat(research): the b2-funding-derisk subject — arms, benchmark, bar and verdicts through the reader`.

## Task 4 — trial 1, on the owner's word

**Files:** `docs/reference/trial-registry.jsonl`, `docs/research/10.phase4-decisions.md` (the alpha families' log, beside B1's `[iter-086]` and `[iter-087]`), `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`.

1. Gate: the reads over Tasks 1–3 (Global constraints) have closed with no open Critical or Important, and the spec is unchanged since — `sha256sum docs/specs/00128-b2-family-opening-design.md` is the `--spec-hash`.
2. Pre-flight, no arm-B return: `uv run pytest tests/test_research_b2_basis.py` reads `1 passed`. A skip is no pre-flight; a failure is spec D6's instrument finding — stop, no run, no verdict.
3. On the owner's word, the run, read-only: `uv run zcrypto research eval --subject b2-funding-derisk --dataset ohlc-rolling --as-of 2026-10-10 --window "2020-09-22 00:00:00+00:00" "2026-06-30 23:59:59+00:00" --accept-holes`. From here the trial is spent: its row is registered whatever it reads, with no stop and no re-run with anything changed. The row is read off the printed metrics by spec D6's matrix: the kill bar's `passes`, then the from-2021 read's `head_to_head_mean_outperf_2021`, `head_to_head_spa_p_2021`, and `max_drawdown` against `arm_a_max_drawdown`.
4. The registration — step 3's line plus `--register --iteration iter-175 --family B2 --spec-hash <step 1's sha256> --n-trials 1 --variant B2-funding-derisk-a2eq-v1 --seed 42 --seed 7 --seed 1234 --verdict <step 3's row: adopt, park or reject> --notes "<subject b2-funding-derisk, the window, as of 2026-10-10, --accept-holes; the matrix row that fired, quoted; the DSR leg non-binding at n_trials 1 (spec D6)>"` — which the owner runs, or says to. The record read back: its metrics equal step 3's printed ones, `cli.registry.record.compute_hash(record["datasets"])` equals its `dataset_hash`, and its `datasets` names the as-of line and the ten funding files.
5. The decisions-log entry `[iter-175] B2 trial 1 — the funding-extreme de-risk on the adopted A2-4h ensemble (Decision: <row>)` in `docs/research/10.phase4-decisions.md`, its numbered options spec D6's matrix rows.
6. The topics, per `topic-ops`: T0023's `## Done so far` takes the emission, the subject, trial 1's record and both stamp rulings with their look-ahead bounds (a print's own offset, 47 ms at most measured, under the 60 s refusal; the close grid `ts[k] + 4h`); its `ripe_when` is rewritten for the remainder — B2's next trial picked for an iteration, or the owner expands or closes the shared B budget — and its next steps carry the OI leg and the z < −2 re-risk as later trials' candidates, the liquidations leg, the Bybit cross-check, and by the verdict the park row's variants or, on adopt, the live funding feed a promotion needs first (spec D9); T0016's `ripe_when` drops B2's arm, and its two B2 lines (`## Done so far`'s re-deferral, the next steps' "Next family to split out") record the opening and the budget, 22 remaining; `uv run python infra/scripts/topics-index.py` re-renders the index.
7. The records commit takes its own `pre-review`.

**Commit:** `docs(research): B2 trial 1 registered — <verdict>`.

## Task 5 — closeout

1. The change-index row at PR-open (`iter-175` in the title); the PR `feat(alpha): iter-175 — B2 family opening, the funding-extreme de-risk overlay` with the trial's verdict in the body and the read line naming the tip the delta read covered (Global constraints); merge on the owner's word.
2. Before the worktree is removed: `unlink` the three dataset links under the worktree's `data/` (`derivatives-funding`, `derivatives-oi`, `ohlc-rolling`), then `ls -la /home/zhaow/Projects/zcrypto-kraken/data` reads the three canonical sets still there.
3. The memo's T0023 item condensed to the family's state and its next trial; the handoff line.
