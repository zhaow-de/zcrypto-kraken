# The deployable's first revalidation — record 47's book on the data after the spent holdout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ruled research subject `p1-revalidation` that rebuilds record 47's book over `ohlc-rolling`, scores it on the returns after 2026-07-10 against its own in-sample band, and lands its first run as a P1 trial on `docs/reference/trial-registry.jsonl`, its rule fixed by spec 00152's sha256 before any return after 2026-03-31 is computed.

**Architecture:** The scoring is pure code in a new `cli/portfolio/revalidation.py` — the slice's and the reference's bounds on the union's bar-open stamps, the band of same-length windows, the metrics and the rule — over three return series the subject hands it. The subject in `cli/research/subjects.py` builds those series with the existing `_crossfreq_book` (record 47's book at `_RECORD44_CONFIG`) and `benchmark_4h_net_of_cost`, and declares the rule, family P1 and `n_trials` 6. The run is `zcrypto research eval --register`, unchanged.

**Tech Stack:** Python 3.14, numpy (`numpy.percentile`), `cli.validation.metrics` (`sharpe`, `max_drawdown`), `cli.validation.dsr.deflated_sharpe_ratio`, `cli.portfolio.record44_legs.benchmark_4h_net_of_cost`, `cli.research.subjects`, pytest.

**Spec:** `docs/specs/00152-deployable-revalidation-design.md`

## Global Constraints

- The hash rule (spec D9): before the spec's sha256 is taken nobody computes a return after 2026-03-31 over the real data; the module and the subject are proven on synthetic series alone. A dispatch never links or reads `data/ohlc-rolling`.
- The constants, verbatim (spec D3–D7): the slice's first bar stamp `2026-07-10 00:00Z`; the reference's last bar stamp `2026-03-31 20:00Z`; the reference's first return index `1380`; the band's window step `6`; the minimum slice `180` returns; the instrument check's count `27337`, Sharpe `1.5609`, tolerance `0.00005`; the benchmark's cost `0.006` a side; annualization `2190` four-hour periods a year; `n_trials` `6`; the percentiles `5` and `95` by `numpy.percentile`'s default linear interpolation.
- Return `i` runs from bar `i`'s close to bar `i + 1`'s; the union's stamps are bar opens. The slice is the returns `i` with `h4_ts[i] >= 2026-07-10 00:00Z`; the reference the returns `i >= 1380` with `h4_ts[i + 1] <= 2026-03-31 20:00Z`; the in-sample prefix the returns `i` with `h4_ts[i + 1] <= 2026-03-31 20:00Z`.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, pasted; one state-changing git command per Bash call, nothing beside it; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names — `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and the session line.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section.
- Probes: on this `full`-tier plan, each guard a task's Probe step lists, through its own case, with `infra/scripts/mutate-probe.sh` on a committed tree, the verdict lines into `.local/iter198/probes-task-<N>.txt` (one `mkdir -p .local/iter198` first; the file started empty by `: > <file>`), carried whole into the next commit's message; `--basetemp=.tmp/implementer/pt` after each probe's `--`.
- The worktree is `.claude/worktrees/iter198`; the main checkout at `/home/zhaow/Projects/zcrypto-kraken` is live, and its `data/` is never written.

## Review Focus

1. The boundary bars — a return whose first bar is stamped 2026-07-09 20:00 is not in the slice, the one whose first bar is 2026-07-10 00:00 is; a return whose second bar is stamped 2026-03-31 20:00 is in the reference, the next is not. Pinned in Task 1's `test_the_slice_starts_at_the_first_return_whose_first_bar_is_on_or_after_its_start` and `test_the_reference_ends_at_the_last_return_whose_second_bar_is_on_or_before_its_end`.
2. A return inside the spent holdout window enters neither the slice, the band nor the in-sample prefix. Pinned in Task 1's `test_no_return_inside_the_holdout_window_enters_a_metric`.
3. The band's last window — a window ending exactly at the reference's end is counted, none past it. Pinned in Task 1's `test_the_band_counts_every_window_that_fits_and_none_past_the_end`.
4. The legs' equality edges — a slice Sharpe equal to the 5th percentile passes leg 1, a drawdown equal to the 95th percentile passes leg 2. Pinned in Task 1's `test_a_leg_at_its_band_edge_passes`.
5. The instrument check's edges — a prefix one return short, or a Sharpe 0.00005 off, gives no verdict. Pinned in Task 1's `test_the_instrument_check_gives_no_verdict_off_record_47`.

---

### Task 1: the scoring in `cli/portfolio/revalidation.py`

**Files:**
- Create: `cli/portfolio/revalidation.py`
- Test: `tests/test_portfolio_revalidation.py`

**Interfaces:**
- Produces, all in `cli/portfolio/revalidation.py`:
  - Constants: `SLICE_START = datetime(2026, 7, 10, tzinfo=UTC)`; `REFERENCE_LAST_BAR = datetime(2026, 3, 31, 20, tzinfo=UTC)`; `DECISIVE_START = 1380`; `BAND_STEP = 6`; `MIN_SLICE = 180`; `RECORD_47_RETURNS = 27337`; `RECORD_47_SHARPE = 1.5609`; `SHARPE_TOLERANCE = 0.00005`; `BENCH_COST_PER_SIDE = 0.006`; `PPY_4H = 2190`; `P1_TRIALS = 6`.
  - `class RevalidationError(Exception)`.
  - `slice_bounds(h4_ts: list[datetime], start: datetime) -> tuple[int, int]` — the half-open return range `[lo, hi)`: `lo` the first `i` with `h4_ts[i] >= start`, `hi = len(h4_ts) - 1`; `lo = hi` when no bar is at or after `start`.
  - `prefix_end(h4_ts: list[datetime], last_bar: datetime) -> int` — the count of returns `i` with `h4_ts[i + 1] <= last_bar`.
  - `@dataclass(frozen=True) class Band`: `sharpe_q05: float`, `maxdd_q95: float`, `sharpes: tuple[float, ...]`.
  - `band(reference: list[float], length: int, *, step: int) -> Band` — the windows `reference[s : s + length]` for `s = 0, step, 2·step, …` while `s + length <= len(reference)`; per window `sharpe(w, periods_per_year=PPY_4H)` and `max_drawdown(w)`; `RevalidationError` when no window fits.
  - `METRIC_KEYS: frozenset[str]` = `{"in_sample_returns", "in_sample_sharpe", "reference_returns", "slice_returns", "band_windows", "band_sharpe_q05", "band_maxdd_q95", "slice_sharpe", "slice_maxdd", "slice_sharpe_rank", "slice_sharpe_ungoverned", "slice_bench4h_sharpe", "slice_mean_diff_vs_bench4h", "slice_dsr", "leg_sharpe_pass", "leg_maxdd_pass"}`.
  - `revalidation_metrics(governed: list[float], ungoverned: list[float], bench: list[float], h4_ts: list[datetime]) -> dict` — exactly `METRIC_KEYS`: `in_sample_returns` = `prefix_end(h4_ts, REFERENCE_LAST_BAR)`, `in_sample_sharpe` the annualized Sharpe of `governed[:in_sample_returns]`; the reference `governed[DECISIVE_START:in_sample_returns]`, its length `reference_returns`; the slice `[lo, hi)` from `slice_bounds(h4_ts, SLICE_START)`, `slice_returns = hi - lo`; the band at `length = slice_returns`, `step = BAND_STEP`; `band_windows = len(band.sharpes)`; `slice_sharpe`, `slice_maxdd` of `governed[lo:hi]`; `slice_sharpe_rank` the share of `band.sharpes` at or below `slice_sharpe`; `slice_sharpe_ungoverned` of `ungoverned[lo:hi]`; `slice_bench4h_sharpe` of `bench[lo:hi]`; `slice_mean_diff_vs_bench4h` = mean of `governed[lo:hi]` less mean of `bench[lo:hi]`; `slice_dsr` = `deflated_sharpe_ratio(sharpe(governed[lo:hi]), slice_returns, P1_TRIALS, 0.0)`; `leg_sharpe_pass` = `int(slice_sharpe >= band.sharpe_q05)`, `leg_maxdd_pass` = `int(slice_maxdd <= band.maxdd_q95)`. `RevalidationError` naming the count when `slice_returns < MIN_SLICE`, and when `len(governed)`, `len(ungoverned)` or `len(bench)` is not `len(h4_ts) - 1`.
  - `revalidation_verdict(metrics: dict) -> str | None` — `None` unless `metrics["in_sample_returns"] == RECORD_47_RETURNS` and `abs(metrics["in_sample_sharpe"] - RECORD_47_SHARPE) < SHARPE_TOLERANCE`; then `"adopt"` when both legs are 1, else `"park"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_portfolio_revalidation.py`, each over synthetic stamps on the 4h grid built by a helper `_grid(first: datetime, n: int) -> list[datetime]` and series made in the test:
  - `test_the_slice_starts_at_the_first_return_whose_first_bar_is_on_or_after_its_start` — a grid from 2026-07-09 12:00 with 10 bars: `slice_bounds(grid, SLICE_START) == (3, 9)`; a grid wholly before the start gives `lo == hi`.
  - `test_the_reference_ends_at_the_last_return_whose_second_bar_is_on_or_before_its_end` — a grid from 2026-03-31 08:00 with 6 bars: `prefix_end(grid, REFERENCE_LAST_BAR) == 3`.
  - `test_no_return_inside_the_holdout_window_enters_a_metric` — a grid from 2025-01-01 through 2026-10-10 20:00 and a varied series (a sine of the index, scaled to 0.001); the same series with every return whose first bar is stamped 2026-03-31 20:00 through 2026-07-09 20:00 replaced by 0.5: every metric of the two calls is equal.
  - `test_the_band_counts_every_window_that_fits_and_none_past_the_end` — over 20 returns of a varied series, `band(returns, 5, step=6)` has 3 windows, starting at 0, 6 and 12 (a start at 18 does not fit), each Sharpe that window's own; `band(returns, 21, step=6)` raises `RevalidationError`.
  - `test_a_slice_equal_to_a_band_window_reads_that_windows_sharpe_and_drawdown` — a series whose slice copies the reference's window at offset 0: `slice_sharpe == band.sharpes[0]` and `slice_maxdd` that window's drawdown, both legs 1.
  - `test_a_slice_planted_below_the_bands_5th_percentile_fails_leg_1` and `test_a_slice_planted_past_the_bands_95th_percentile_drawdown_fails_leg_2` — each leg 0 and the other 1, `revalidation_verdict` `"park"` with the instrument fields set to record 47's.
  - `test_a_leg_at_its_band_edge_passes` — metrics dicts with `slice_sharpe == band_sharpe_q05` and `slice_maxdd == band_maxdd_q95`: both legs 1 when recomputed by the module's own comparison.
  - `test_the_instrument_check_gives_no_verdict_off_record_47` — `in_sample_returns` 27336 → `None`; `in_sample_sharpe` 1.5609 ± 0.00005 → `None`; 1.5609 ± 0.00004 with both legs 1 → `"adopt"`.
  - `test_a_short_slice_or_a_misaligned_series_is_refused` — a slice of 179 returns, and a `bench` one value short, each raise `RevalidationError` naming the count.
  - `test_the_metrics_carry_exactly_the_declared_keys` — `set(revalidation_metrics(...)) == METRIC_KEYS`.
- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_portfolio_revalidation.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected: every case fails on the missing module.
- [ ] **Step 3: Implement** `cli/portfolio/revalidation.py` to the interfaces above.
- [ ] **Step 4: Run them to see them pass** — the same command; expected: every case passes.
- [ ] **Step 5: Commit** `feat(portfolio): the deployable's revalidation scoring — slice, band and rule (spec 00152 D3–D6)`, the message carrying the result line.
- [ ] **Probe** (each through its own case): the slice's `>=` made `>` (`-k slice_starts`); the prefix's `<=` made `<` (`-k reference_ends`); the band's fit test `s + length <= len` made `<` (`-k band_counts`); leg 1's `>=` made `>` (`-k band_edge`); the instrument tolerance's `<` made `<=` (`-k instrument_check`).

### Task 2: the subject `p1-revalidation`

**Files:**
- Modify: `cli/research/subjects.py`, `tests/test_research_command.py` (its `_CONTRACT_DATASETS` row), `README.md` (the `--subject` row of `zcrypto research eval`)
- Test: `tests/test_research_p1_revalidation.py`

**Interfaces:**
- Consumes: Task 1's `revalidation_metrics`, `revalidation_verdict`, `METRIC_KEYS`, `RevalidationError`, `BENCH_COST_PER_SIDE`; the existing `_crossfreq_book`, `benchmark_4h_net_of_cost`, `_ASSETS`, `SubjectError`.
- Produces: `_build_p1_revalidation(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — a `window` refused with `SubjectError("p1-revalidation scores a slice of the full build, so it reads no window: drop --window")`; else `_crossfreq_book(reader, dataset, None, as_of, accept_holes)`, `benchmark_4h_net_of_cost(h4_prices, cost_per_side=BENCH_COST_PER_SIDE)`, and `revalidation_metrics(result.governed_net, result.ungoverned_net, bench, h4_ts)`, a `RevalidationError` re-raised as `SubjectError` with the dataset named. `SUBJECTS["p1-revalidation"] = Subject("p1-revalidation", (1440, 240), _ASSETS, _build_p1_revalidation, spec="docs/specs/00152-deployable-revalidation-design.md", metric_keys=METRIC_KEYS, seeds=(), verdict=revalidation_verdict, no_verdict="instrument finding: the read's in-sample prefix does not rebuild record 47's book, 27337 returns at Sharpe 1.5609; no verdict, the trial unspent", family="P1", n_trials=6)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_research_p1_revalidation.py`, over a synthetic frozen dataset `ohlc-test` of the ten `_ASSETS` at 1440 and 240 minutes from 2025-01-01 00:00 through 2026-10-10 20:00, written as the existing contract fixtures write theirs:
  - `test_the_build_returns_exactly_the_declared_keys` — `set(build) == METRIC_KEYS`, `slice_returns == 557`.
  - `test_a_synthetic_book_is_no_record_47_and_gets_no_verdict` — `revalidation_verdict(metrics) is None`.
  - `test_a_window_is_refused` — `SubjectError` with the drop-`--window` text.
  - `test_a_set_ending_before_a_month_of_slice_is_refused` — the same fixture cut at 2026-08-08 20:00 (`slice_returns` 179) raises `SubjectError` naming the dataset and 179.
  - `test_the_subject_declares_family_p1_its_count_and_spec` — `family == "P1"`, `n_trials == 6`, `seeds == ()`, the spec path.
- [ ] **Step 2: Add the `_CONTRACT_DATASETS` row** `"p1-revalidation": lambda tmp_path, subject: (<the fixture's data root>, datetime(2025, 1, 1, tzinfo=UTC))` in `tests/test_research_command.py`, the fixture writer shared with Step 1's file.
- [ ] **Step 3: Run them to see them fail** — `uv run pytest tests/test_research_p1_revalidation.py tests/test_research_command.py -k "p1_revalidation or p1-revalidation" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected: the new cases fail on the missing subject.
- [ ] **Step 4: Implement** the subject, and add `p1-revalidation` (record 47's book scored after the spent holdout against its own in-sample band; `ohlc-rolling` as of a day) to the README's `--subject` row.
- [ ] **Step 5: Run them to see them pass** — Step 3's command, then `uv run pytest tests/test_research_command.py tests/test_research_p1_revalidation.py tests/test_portfolio_revalidation.py -q -p no:cacheprovider -n 6 --basetemp=.tmp/implementer/pt`; expected: all pass.
- [ ] **Step 6: Commit** `feat(research): the p1-revalidation subject, family P1 at n_trials 6 (spec 00152 D8)`, the message carrying Task 1's probe verdicts and this task's result line.
- [ ] **Probe**: the window refusal removed (`-k window_is_refused`); the `MIN_SLICE` refusal removed (`-k before_a_month`).

### Task 3 (the controller): the hash, the run and the record

- [ ] **Step 1: The pick entry** — append `[iter-198] The deployable's first revalidation — what is scored, on which data, and where it is registered (Decision: 1)` to `docs/research/14.phase6-decisions.md` with the owner's word verbatim and three options: (1) the post-holdout slice against the record's own in-sample band, registered as a P1 trial — chosen, the owner's; (2) the same read kept as a no-slot reading — no trial counted, against §12's "registered as trials"; (3) waiting for the rolling set's extension past 2026-10-10 — a longer slice, at the cost of the run the owner asked for now. Commit `docs(research): [iter-198] the deployable's first revalidation, on the owner's word`.
- [ ] **Step 2: The hash** — on a clean tree with Tasks 1–2 merged into the branch: `sha256sum docs/specs/00152-deployable-revalidation-design.md`, pasted into the SDD ledger with `date -u`.
- [ ] **Step 3: The run** — `ln -snT /home/zhaow/Projects/zcrypto-kraken/data/ohlc-rolling .claude/worktrees/iter198/data/ohlc-rolling` (already linked by the controller for the measured basis), then `uv run zcrypto research eval --subject p1-revalidation --dataset ohlc-rolling --as-of 2026-10-10 --register --iteration iter-198 --family P1 --spec-hash <hash> --n-trials 6`; expected: `rc=0`, one record appended (trial 63) or, on the instrument finding, one reading.
- [ ] **Step 4: The record's commit** — `git add docs/reference/trial-registry.jsonl` (or the reading ledger), committed `docs(reference): trial 63 — record 47 revalidated on 2026-07-10 → 2026-10-10, <verdict>` with the run's printed metrics pasted.
- [ ] **Step 5: The replay** — in a scratch worktree at that commit with `ohlc-rolling` linked, `uv run pytest tests/test_registry_replay.py -k "trial-63" -q -p no:cacheprovider`; expected `1 passed`; its own time read off `--durations=0`, and a `tests/slow-cases.txt` line added only at 10 s or more.
- [ ] **Step 6: The verdict entry and T0122** — append `[iter-198] Record 47 revalidated on the returns after the spent holdout (trial 63) — <verdict>` to the phase-6 log with every metric of the record; T0122's monthly bullet records this run as the first and names the next run's form (spec D10). Commit each.
- [ ] **Step 7: Unlink** — `test -L data/ohlc-rolling && unlink data/ohlc-rolling` before the worktree is removed, and the main checkout's `data/` listing read after.

Decisions log: Task 3 Steps 1 and 6.
