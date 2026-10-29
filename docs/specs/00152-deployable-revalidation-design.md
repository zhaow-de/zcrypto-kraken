# The deployable's first revalidation — record 47's book scored on the data after the spent holdout, against its own in-sample band

Iteration `iter-198`, family P1 (master plan §12, "Ongoing — Operate, Monitor, Revalidate"), topic [T0122](../open-topics/T0122-ongoing-register-kill-criteria.md). The master plan's monthly revalidation on rolling data, registered as a trial, run for the first time: the deployable record's book rebuilt over `ohlc-rolling` and scored on the returns its adoption never saw, against the band of returns of the same length it earned in-sample. The rule is pre-registered by this spec's sha256 before any return after the holdout is computed.

## The measured basis

Measured 2026-10-29 on `zcrypto-ops`, the workstation, in the branch's worktree over a symlink to the main checkout's `data/ohlc-rolling`, read-only.

- **The deployable** is registry record 47 (`P1-crossfreq-fixedthird-twelve-leg-basket-btczero`, iter-139, adopted 2026-08-15T00:30:58Z, family P1, `n_trials_in_family` 5), read over `ohlc-full` through 2026-03-31: `ann_sharpe_noc` 1.5609, `n_bars_compared_4h` 27337, `cap_breach_bars` 1318, `maxdd` 0.1357, `decisive_start` 1380 — the decisive window's first return index, `k ≥ 230` daily bars under B3 + vt-dynamic (master plan §12, Phase 4's kill bar). `cli/research/subjects.py`'s `LEGACY_INCUMBENTS` maps 47 to the subject `record44-crossfreq`, whose builder `_crossfreq_book` rebuilds that book at its own cost literal, `_RECORD44_CONFIG` (fee 0.0040 and spread 0.0020 a side).
- **The rolling set as of 2026-10-27**, the hub's head, brought to the main checkout on the owner's second word (D1) by `uv run zcrypto data fetch` there (new=221, rc 0), the lines 2026-10-11 → 2026-10-27 each 12 files and no hole: `uv run zcrypto data rolling verify --as-of 2026-10-27 --root data/ohlc-rolling` → `2026-10-27 89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4 files=336`, rc 0. Its frame is Kraken's quarterly dump through 2026-09-30, then the captured tape's daily bars from 2026-10-01 (README, `zcrypto data rolling`).
- **The known answer**: `uv run zcrypto research eval --subject record44-crossfreq --dataset ohlc-rolling --as-of 2026-10-27 --window '2010-01-01 00:00:00+00:00' '2026-03-31 23:59:59+00:00'` → `ann_sharpe_noc` 1.560907676587497, `n_periods` 27337, `cap_breach_bars` 1318, `governor_engaged_bars` 7302, span 2013-09-10 00:00 → 2026-03-31 20:00. The rolling set reproduces record 47's in-sample book: the same Sharpe to four places, the same period count, the same cap breaches.
- **The union's stamps** are bar opens and the net series has one value fewer than the bars: return `i` runs from bar `i`'s close to bar `i + 1`'s (`cli/alpha/b2.py`'s `funding_grid_feature` docstring: "the union's bar-open stamps in, `len(union_ts) - 1` values out").
- **The slice's bars**, read through the subject's own loader `_capturing_union` over `ohlc-rolling` as of 2026-10-27 with the window 2026-07-10 00:00 → 2026-10-27 23:59:59, no return computed: 660 four-hour bars, stamped 2026-07-10 00:00 → 2026-10-27 20:00, so 659 returns, and 110 daily bars, 2026-07-10 → 2026-10-27, for each of the ten assets (ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP), no null close in either grid.
- **The in-sample band at the slice's length**, from the known answer's build alone (no return after 2026-03-31 computed), the decisive window's 25957 returns cut into every run of 659 consecutive returns starting every 6 returns, one day: 4217 windows; their annualized Sharpe (`cli/validation/metrics.py`'s `sharpe`, 2190 periods a year) has 5th percentile −2.8851, median 0.8707, and 40.08 % of them are below zero; their max drawdown (`max_drawdown`) has median 0.0402 and 95th percentile 0.0736. Over 110 days the deployable's own history spans a wide range: the book earns in a few strong stretches and gives a little back between them.

## Operating model

- **One machine, one session.** The run is the controller's, on `zcrypto-ops`, in the branch's worktree; `data/ohlc-rolling` is a symlink to the main checkout's set, read-only, unlinked before the worktree goes.
- **One writer of each shared file.** `zcrypto research eval --register` appends one record to `docs/reference/trial-registry.jsonl` in the branch and two lines to the clone's trial-attempts log in the main checkout's `.local/trial-attempts.jsonl` (`cli/registry/attempts.py`), its first before the build and its last before the print; no other process writes either during the run. No daemon, timer, host or live engine is touched.

## The question and its rule

Does record 47's book, scored on the 659 returns after the spent holdout window that its adoption never saw, stay inside the band its own in-sample history draws for a run of that length? At 110 days the band is wide (the measured basis): the reading can show a book that broke, never confirm an edge. Each later monthly run scores the whole span from 2026-07-10 to its as-of day, so the slice grows and the band narrows with it.

## D1 — the pick: the owner's word

- The owner's word of 2026-10-29, verbatim: "go ahead with 1 and 2, the window from 2026-07-10 is fine" — item 1 being "Revalidate the deployable on data it never saw", put to the owner beside three other items, its window choice the owner's to confirm because the read is of the adopted system. Item 2, the engine's execution cost from the kept fill model, is its own iteration.
- The owner's second word of 2026-10-29, told that the local rolling set ended at 2026-10-10, verbatim: "extend the rolling set first, then rerun the revalidation" — the read is as of 2026-10-27, the hub's head (the measured basis). Both words stand in the phase-6 decisions log's `[iter-198]` pick entry.

## D2 — the instrument

- **The book**: record 47's, built by `_crossfreq_book` over `ohlc-rolling` as of 2026-10-27, full history from 2013-09-10, no window, at `_RECORD44_CONFIG`; the governed net-of-cost series is the scored series.
- **No hole is crossed**: the run takes no `--accept-holes`; the as-of line records none.

## D3 — the slice

- **The 659 returns between the closes of consecutive bars both stamped at or after 2026-07-10 00:00Z**, through the as-of day's last bar: the first runs from the close of the 2026-07-10 00:00 bar to the close of the 04:00 bar, the last from the close of the 2026-10-27 16:00 bar to the close of the 20:00 bar. No return has an end at a bar stamped inside the spent holdout window.
- **The spent holdout window, 2026-04-01 → 2026-07-09, is read as history and never scored**, as `[iter-176]` rules ("the adopted system is never re-evaluated on it"): its bars feed the signals the slice's first positions are formed from, and no metric, band window or reported read covers a return inside it.

## D4 — the band

- **The reference**: the same build's governed net returns with index at or above record 47's `decisive_start` (1380) whose bars are stamped at or before 2026-03-31 20:00 — the decisive window record 47 was adopted on, 25957 returns.
- **The windows**: every run of `L` consecutive reference returns starting at reference offset 0, 6, 12, …, `L` the slice's length (659 as of 2026-10-27); per window, the annualized Sharpe and the max drawdown as the measured basis computes them.
- **The band**: the 5th percentile of the windows' Sharpes and the 95th percentile of their max drawdowns, `numpy.percentile` with its default linear interpolation.

## D5 — the rule, pre-registered

- **The instrument check first**: the build's in-sample prefix — its returns whose bars are stamped at or before 2026-03-31 20:00 — reproduces record 47: 27337 returns and an annualized governed Sharpe within 0.00005 of 1.5609, the measured basis's known answer. Otherwise the rule gives no verdict: the rolling set no longer rebuilds the record's book, an instrument finding, and the run is kept as a reading with no trial spent.
- **Leg 1**: the slice's annualized Sharpe is at or above the band's 5th-percentile Sharpe.
- **Leg 2**: the slice's max drawdown is at or below the band's 95th-percentile drawdown.
- **Verdict**: both legs pass → `adopt`, record 47 re-confirmed on data it never saw, its book inside its own band; either fails → `park`, the book outside its band, to the owner. Never `reject`: retiring the deployable is the owner's, under T0122's ratified kill criteria (the 20 % governed drawdown floor and the paired live-minus-simulation difference), which this reading neither replaces nor moves.

## D6 — the reported reads, beside the rule and never in it

- The slice's length; the band's window count; the slice's Sharpe rank, the share of band windows whose Sharpe is at or below the slice's; the slice's ungoverned Sharpe; the frozen 4h benchmark's Sharpe over the same slice (`cli/portfolio/record44_legs.py`'s `benchmark_4h_net_of_cost` at 0.006 a side, its returns indexed as the book's) and the mean per-return difference, governed book less benchmark; the slice's deflated Sharpe ratio (`cli/validation/dsr.py`'s `deflated_sharpe_ratio`, the slice's per-period Sharpe, its observation count, the slice's length, P1's true count with this record, 6, and P1's registered cross-trial variance of per-period Sharpes, 1.3058096692086857e-05 — the `var_trials_4h` records 43, 44 and 47 carry, under which the count deflates — skew and kurtosis at their defaults as `cli/alpha/killbar.py` calls it), T0122's "DSR at true trial count", read and never binding.

## D7 — the family, the count and the record

- **Family P1**, unbudgeted (`cli/registry/budget.py`'s `BUCKET_OF["P1"]` is `None`): no bucket slot is spent. `n_trials_in_family` 6, P1's five records and this one. No seeds: the build and the band are deterministic.
- **The record** names record 47 in its variant and notes, with the as-of day, the line's sha256 and the slice's span.

## D8 — the subject and its refusals

- **A new ruled subject**, `p1-revalidation`, in `cli/research/subjects.py`: the `record44-crossfreq` grids and assets, the D2 build, the D3 slice, the D4 band, the D5 rule and the D6 reads, `family="P1"`, `n_trials=6`, `spec` this file.
- **It refuses**, each with a `SubjectError` naming the cause: a `--window`, since the band and the slice are cut from the full build; a read whose slice holds fewer than 180 returns, one month — `ohlc-full`, ending 2026-03-31, holds none, so a frozen set refuses itself by this one rule and needs no rule of its own; a reference shorter than the slice, which leaves the band no window.
- **Proven on known answers before it reads the real set**: an in-sample prefix off record 47 by its count or its Sharpe gives no verdict; a synthetic series whose slice equals one band window reads that window's Sharpe and drawdown and passes both legs; a slice planted below the band's 5th percentile fails leg 1; one planted past the 95th-percentile drawdown fails leg 2; a return whose bar is stamped inside the holdout window is in no band window and not in the slice; a slice with fewer than 180 returns is refused.

## D9 — the hash rule and the order of work

- Before this spec's hash nobody computes a return after 2026-03-31 over the real data: the known answer and the band above read through 2026-03-31 alone, the module's own reads over that build — the prefix's count and Sharpe, the reference's length and the band at 659 — are checked against them, and the subject is proven on synthetic series. After the hash: the run with `--register`, the record, the entry, T0122's next steps, the replay case for the record.

## D10 — what a verdict changes

- Nothing on the live path. `adopt` adds the first out-of-time evidence beside record 47; `park` is a finding to the owner, read by value, with the production kill criteria unchanged. Either way T0122's monthly bullet records this run as its first and names the next: a new subject over the same build and this spec, its `n_trials` one higher — the command refuses a further trial of a subject whose count a landed record froze (`cli/research/command.py`) — run on the rolling set's first as-of a month or more after 2026-10-27, once an operator has extended the set.

## Out of scope

Extending `ohlc-rolling` past 2026-10-27; the live engine's long-only spot book and the paired live-versus-simulation harness (T0122's other next steps); any change to record 47, the deployable, the engine or a rung; any read of `data/ohlc-holdout-2026-07-10`; the execution-cost reading over the fill model, its own iteration.
