# B2 — the funding-extreme de-risk overlay on the adopted A2-4h ensemble (family opening design)

**Iteration:** iter-175 (attended; decisions log `[iter-175]`; family topic T0023 under the T0016 umbrella, picked on the owner's word of 2026-10-12: "pick the most relevant item from milestone Research substrate and start working on it"). **Goal:** open the B2 family — derivatives-positioning features at intraday horizons as de-risking triggers for the spot book (master plan §5's brief, binding: a conditioning family on an adopted signal, never a standalone high-turnover system, every read net of cost) — with the substrate→feature emission spec `00110` deferred here, a leak-free overlay module mirroring `cli/alpha/b1.py`, a committed research subject so the trial registers through `zcrypto research eval`, and the pre-registered trial 1, run on the owner's word after the plan review. This spec spends one trial of the shared B budget when trial 1 runs: 23 remain today, 22 after.

## The measured basis

Every number below is the printed output of a command run on 2026-10-12 against the workstation's data root, the hub's mirror after `zcrypto data fetch` (the rolling set at its 2026-10-10 head, the two derivatives substrates as catalogued); the scripts are `.tmp/b2/measure_substrates.py` and `.tmp/b2/measure_engagement.py`, their outputs `.tmp/b2/substrates.json` and `.tmp/b2/engagement.json`.

- **The funding substrate on its own cadence** (`read_funding_series` per perp, `funding_zscore(window=90)` over the 8h prints, spec `00110` D7): BTCUSDT 7,119 prints 2020-01-01 → 2026-06-30T16:00Z, 3,190 of them stamped 1–47 ms past the hour (max offset 0.047 s), 7,030 z-scores defined, 457 with |z| > 2, 255 with |z| > 2.5, 165 with |z| > 3; the other nine perps between 6,322 (AVAX, from 2020-09-22) and 7,103 prints, each with 396–504 prints at |z| > 2; SOL carries the 101 off-cadence prints (`interval_hours` ≠ 8), the only perp with any. The substrate ends 2026-06-30, the last complete month at its build.
- **The OI substrate on the 4h grid** (`read_oi_series`, `group_by_dynamic` 4h left-closed, `oi_levels_from_raw`, `oi_zscore(window=180)`): BTCUSDT 618,850 five-minute rows 2020-09-01 → 2026-07-22, 12,904 4h bars, 11 placeholder levels; the other nine 488,000 rows each from 2021-12-01, 10,168 bars, 4–5 placeholders; |z| > 2 on 12–14 % of bars (the level's z-score is trend-dominated, not a spike measure); the absolute 4h log-delta's 99th percentile between 0.0515 (DOT) and 0.0978 (DOGE). OI is not in trial 1; these figures bound trial 2.
- **The engagement of a funding-extreme de-risk on the adopted ensemble** (the three adopted A2 arms of `cli/portfolio/crossfreq_system.py` — lookbacks (20, 50, 100) at target vol 0.12, (60, 120, 240) at 0.10 and at 0.12, short off, vol and basket lookback 180, 2,190 periods a year — on the rolling set's 4h closes for the ten EUR assets through `cli.research.subjects._capturing_union`, window 2020-09-22 → 2026-06-30, as of 2026-10-10, holes accepted; the funding z-score as-of aligned to each boundary's close stamp `ts[k] + 4h` with the print stamps normalised to the hour): 12,646 union stamps, 12,645 return indices; z defined at every stamp for eight assets, at 12,464 for AVAX and 12,287 for SOL; the book is long on 67,093 of 126,450 asset-stamps; of those, 3,005 (4.5 %) have z > 2 — between 164 (AVAX) and 350 (BTC) per asset — 1,942 have z > 2.5, and 1,379 have z < −2. No conditional return was read.

## Hypothesis (trial 1, pre-registered `[iter-175]`)

A two-sigma-high trailing funding print marks crowded long positioning in the perpetual, and the spot book's long in that asset at that boundary carries more downside than the ensemble's trend signal prices: **halving the asset's position while its 30-day funding z-score exceeds +2 improves the ensemble's net-of-cost performance, through a lower drawdown at the engaged stamps, against the unconditioned ensemble.** Arms: **A** = the adopted equal-weight three-arm A2-4h ensemble exactly as `crossfreq_system.py` builds it; **B** = the same ensemble passed through the overlay. One treatment (the de-risk), judged by the pre-registered decision matrix below.

## D1 — the grid is the ensemble's own 4h boundary

The overlay acts where the ensemble decides, at the 4h close-time boundary `ts[k] + 4h` the pinned contract keys every position on (spec `00045` F3 and `expand_daily_positions`); the master plan's §6 puts funding and OI features in the 4h signal layer. The 1h grid spec `00110` D3 built stays unused by this family's trial 1: a same-hour de-risk between boundaries is an execution-layer knob, not a conditioning of the signal, and a trial on it is its own pre-registration. (Closed world: the grids spec `00110` D3 names are 1h and 4h; trial 1 takes 4h.)

## D2 — the feature is the 30-day funding z-score, as-of at the boundary close, on normalised stamps

- The asset's own 8h funding prints from `derivatives-funding` (`PERP_SYMBOLS` maps the ten EUR bases; the two /BTC legs have no perp and are outside the family, as they are outside the ensemble). Prints whose `interval_hours` ≠ 8 arrive as `None` (spec `00110` D7; SOL's 101).
- **Stamp normalisation (the first ruling T0023 records)**: a print stamped within the hour's first minute is the settlement at that hour — the stamp is truncated to the hour before alignment. The look-ahead this admits is the print's own offset, at most 0.047 s measured; a print more than 60 s past the hour is not normalised and is refused by the emission (none exists; the enumeration is the substrate, 68,281 prints, max offset 0.047 s).
- `funding_zscore(window=90)`: 90 prints = 30 days at 8h, inclusive, sample stdev, `None` while short or null-bearing (spec `00110` D7's pinned semantics, unchanged).
- **The grid handed to `align_asof` is the close stamp (the second ruling)**: `ts[k] + 4h` for return index `k`, never the bar-open `ts[k]`; a print at the boundary's own hour is included (`source_ts <= grid_ts`), since the settlement is known at that instant. The emission is leak-free by `align_asof`'s contract and its truncating-prefix property test.
- Emitted as `binperp_funding_z30d` per asset on the union's return index (spec `00110` D8's prefix).

## D3 — the treatment is a fixed half-scale while the z-score exceeds +2, per asset, no hold-through

- At return index `k`, for asset `a`: if `binperp_funding_z30d[a][k]` is not `None` and `> 2.0`, arm B's position is `0.5 × arm A's position`; otherwise arm A's position unchanged. The scale is applied to the ensemble's equal-weight per-asset position after the arms' own vol targeting, as B1's scaler was.
- The threshold 2.0 and the scale 0.5 are pre-registered constants, not tuned: 2.0 is the two-sigma reading the hypothesis names, measured to engage on 4.5 % of long stamps; 0.5 is the de-risk fraction B1's vol scaler fixed (spec `00045` 4), kept so the two families' knobs compare. Changing either after a result is a new trial.
- No hold-through: the de-risk is a trade and the re-risk is a trade, each charged at 0.006/side on the position change, so the treatment pays its own turnover and the matrix sees it net of cost. (B1's hold-through was its turnover-control mechanism; this family's claim is drawdown, and a forced hold would conflate the two.)
- The ensemble is long-only (`short="off"`), so the symmetric rule for shorts at z < −2 is inert on this book and is not part of trial 1; the measured 1,379 long stamps at z < −2 are a trial-2 candidate (a re-risk or the contrarian re-entry §5 names), not a treatment here.
- A `None` z-score (warm-up, SOL's dark stretch, AVAX before its first print) leaves the position unchanged: the overlay never acts on a missing feature.

## D4 — the window is the funding panel, 2020-09-22 → 2026-06-30, the rolling set as of 2026-10-10

- Start 2020-09-22T00:00Z, the balanced funding panel's first day (AVAX's first print, spec `00110`'s measured basis); end 2026-06-30T23:59:59Z, the substrate's last print month. OI's 2021-12-01 bound (spec `00110` D4) does not bind a funding-only trial.
- The 4h closes come from `ohlc-rolling` read as of 2026-10-10 (the hub's head on the measurement day; the record names the line read), holes accepted and reported, the union calendar and BTC-only forward fill of the research subject's own `_capturing_union`.
- Warm-up: the first 90 prints (30 days) carry no z-score and the ensemble's own 240-bar lookback is its warm-up; the decisive window starts at `decisive_start = 1380` return indices (230 days, the frozen benchmark's k ≥ 230 daily cut at 4h, as spec `00045` applied it) counted from the window's first index.
- The frozen benchmark B3+vt-dynamic is rebuilt at 4h over the same window with the `a2_4h_run.py:52-69` recipe spec `00045` cites, the same recipe trial 1's driver copies.

## D5 — the arms, the costing and the book

- Arm A: the three adopted A2 arms on the ten EUR assets' 4h closes, equal-weight per-asset mean of their `asset_positions`, exactly `crossfreq_system.py`'s A2 sleeve; its net-of-cost returns at 0.006/side on per-asset turnover (the inline convention of trials 37–39 and 45–46).
- Arm B: arm A's positions through the overlay (D3), costed the same way.
- The overlay consumes ensemble outputs as-is: no change to `cli/alpha/a2.py`, `cli/portfolio/*` or any adopted artifact (spec `00045`'s attribution rule: ensemble-only isolates the treatment; the full record-47 combination is out of scope).

## D6 — the kill bar and the decision matrix, fixed before the run

- Arm B against the frozen benchmark: `a1_kill_bar(book, benchmark_4h, n_trials=1, var_trials=0.0, mean_block=30, seed=42, n_resamples=2000, cost_stressed(×1.5), calendar-year slices stub-excluded, decisive_start=1380)`; the SPA robustness grid blocks {30, 102} × seeds {42, 7, 1234}; the DSR leg non-binding at n_trials = 1 (expected-max-Sharpe is 0 at n = 1, so DSR ≈ PSR against 0 — the burden sits on SPA and the worst slice; stated in the record's notes, as spec `00045` F6 did).
- Head-to-head: `net_of_cost_verdict(B, A)` on the full window and from 2021-01-01, the first full calendar year (the from-2016 read of B1 has no analogue; the second read guards the first months, where the ensemble's lookbacks and the z-score are still warming).
- Engagement proof before any verdict, per year: engaged stamps (long and z > 2), stamps where the arms' positions differ, arm B's turnover against arm A's, arm B's maximum drawdown against arm A's. Zero engaged stamps in every year is a dead knob — an instrument finding, no verdict. (The basis measures engagement in every year of the window; the proof is the run's own.)
- The matrix:

| Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, the from-2021 read primary) | Verdict |
| --- | --- | --- |
| pass | B beats A (mean outperformance > 0 and SPA p < 0.05) | **adopt** the overlay |
| pass | B > A point estimate, SPA n.s., and B's maximum drawdown below A's | **park** (variant candidates: threshold 2.5, scale 0.25, the z < −2 re-risk) |
| pass | B ≤ A, or B's drawdown not below A's | **reject** the overlay (B passing the bar inherits A's edge; the de-risk did not do what it claims) |
| fail | any | **reject** (a conditioning that breaks the adopted arm's bar is harmful) |

## D7 — the registry record and the subject that writes it

- Family key `B2` (the bucket budget B = 25 shared with B1; after trial 1, 22 remain), `n_trials_in_family = 1`, `variant = "B2-funding-derisk-a2eq-v1"`, `iteration = "iter-175"`, `spec_hash` = this file's sha256, `verdict` per the matrix, `run_ref` naming the subject and the command.
- `datasets` (schema 4) names the two sets read: `ohlc-rolling` with the as-of line's sha256 (the `ObservedReader` vouches the read), and `derivatives-funding` with its manifest's `basket_sha256`; `dataset_hash = sha256(hex_rolling_line + ":" + hex_funding)`, both hexes and the recipe verbatim in `notes`.
- Metrics: the trials-45–46 key set (`ann_sharpe_noc`, `ann_sharpe_noc_decisive`, the arm-A and benchmark counterparts, `max_drawdown`, `spa_p_*` over the grid, `dsr_corrected`, `cost_stress_pass`, `worst_slice_relative_pass`, `passes`, `head_to_head_*`, `turnover_a`, `turnover_b`) plus this family's engagement keys (`engaged_per_year`, `stamps_positions_differ`, `arm_a_max_drawdown`, `max_drawdown_reduction_pct`); bools as 0/1, keys str (the registry's type-strict check).
- **The registration path is a committed research subject** `b2-funding-derisk` in `cli/research/subjects.py` (spec `00086`: appending a record requires a committed subject): it reads the rolling set through the reader's `read_rolling` and the funding set through `read_series("derivatives-funding", "<PERP>/funding.parquet")`, builds both arms and the benchmark, runs the bar and the verdicts, and returns the metrics block; `zcrypto research eval --subject b2-funding-derisk --dataset ohlc-rolling --as-of 2026-10-10 --window … --register --family B2 …` appends the record. The trial is not a scratchpad driver: B1's `run_ref` names a script nobody can re-run, and the registry's provenance contract since spec `00086` is the reason the subject exists.

## D8 — the emission module and the overlay module

- `cli/alpha/b2.py` (mirroring `b1.py`): `B2Config(z_threshold: float = 2.0, derisk_scale: float = 0.5, z_window: int = 90)` validated at construction; `funding_grid_feature(prints_ts, prints_rate, prints_interval_hours, close_ts, *, config) -> list[float | None]` (the emission: normalise stamps, map off-cadence prints to `None`, z-score, as-of align — D2's two rulings live here and nowhere else); `derisk_scales(z_by_asset, *, config) -> dict[str, list[float]]` (1.0 or 0.5 per asset per index; `None` → 1.0); `scale_positions(asset_positions, scales) -> dict[str, list[float]]`; engagement helpers `per_year_engaged_counts`, `stamps_positions_differ`, `book_turnover` (reused from `b1.py` where the shape is identical).
- `coverage_by_year` (spec `00110` D6) is emitted beside the feature in the engagement report, so the trial cannot run blind over SOL's dark stretch or AVAX's late start.
- Known-answer tests: a planted two-sigma print scales exactly the stamps from its settlement hour to the next print's; a print 30 ms past the hour and one on the hour produce the same alignment; a print 61 s past the hour is refused; the truncating-prefix property of the emitted feature; `None` leaves the position unchanged; the scale's turnover is charged.

## D9 — what the trial does not decide, and what a verdict changes

- A verdict of **adopt** does not touch the live book: the substrate is backtest-only (spec `00110` D9), and a live funding feed is a new spec with its own API path; the adopted overlay is a research-registry fact until then, as spec `00045`'s was.
- A verdict of **park** names its variant candidates in the record; each is a new trial of the budget.
- A verdict of **reject** archives the hypothesis in the record and the decisions log; the family stays open for its OI and liquidation hypotheses.

## Out of scope

The OI leg (trial 2's candidate: a 4h OI log-delta spike as a hold-through gate, bounded above by the measured 99th percentiles) and the liquidation leg (the Coinalyze tape since 2026-07-15 is too short for a bar at 4h; T0023's own next step). The 1h grid. Shorts. Any change to `cli/alpha/a2.py`, `cli/portfolio/*`, the engine or an adopted artifact. Tuning the threshold, the scale or the window — each is a trial. The Bybit funding cross-check (T0023's optional step). Live serving.
