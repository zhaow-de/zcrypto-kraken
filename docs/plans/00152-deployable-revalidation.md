# The deployable's first revalidation — record 47's book on the data after the spent holdout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A ruled research subject `p1-revalidation` that rebuilds record 47's book over `ohlc-rolling`, scores it on the returns after 2026-07-10 against its own in-sample band, and lands its first run as a P1 trial on `docs/reference/trial-registry.jsonl`, its rule fixed by spec 00152's sha256 before any return after 2026-03-31 is computed.

**Architecture:** The scoring is pure code in a new `cli/portfolio/revalidation.py` — the slice's and the reference's bounds on the union's bar-open stamps, the band of same-length windows, the metrics and the rule — over three return series the subject hands it. The subject in `cli/research/subjects.py` builds those series with the existing `_crossfreq_book` (record 47's book at `_RECORD44_CONFIG`) and `benchmark_4h_net_of_cost`, and declares the rule, family P1 and `n_trials` 6. The run is `zcrypto research eval --register`, unchanged.

**Tech Stack:** Python 3.14, numpy (`numpy.percentile`), `cli.validation.metrics` (`sharpe`, `max_drawdown`), `cli.validation.dsr.deflated_sharpe_ratio`, `cli.portfolio.record44_legs.benchmark_4h_net_of_cost`, `cli.research.subjects`, pytest.

**Spec:** `docs/specs/00152-deployable-revalidation-design.md`

## Global Constraints

- The hash rule (spec D9): before the spec's sha256 is taken nobody computes a return after 2026-03-31 over the real data; the module and the subject are proven on synthetic series alone. A dispatch never links or reads `data/ohlc-rolling`.
- The constants, verbatim (spec D3–D7): the slice's first bar stamp `2026-07-10 00:00Z`; the reference's last bar stamp `2026-03-31 20:00Z`; the reference's first return index `1380`; the band's window step `6`; the minimum slice `180` returns; the instrument check's count `27337`, Sharpe `1.5609`, tolerance `0.00005`; the benchmark's cost `0.006` a side; annualization `2190` four-hour periods a year; `n_trials` `6`; P1's cross-trial variance of per-period Sharpes `1.3058096692086857e-05`; the percentiles `5` and `95` by `numpy.percentile`'s default linear interpolation.
- Return `i` runs from bar `i`'s close to bar `i + 1`'s; the union's stamps are bar opens. The slice is the returns `i` with `h4_ts[i] >= 2026-07-10 00:00Z`; the reference the returns `i >= 1380` with `h4_ts[i + 1] <= 2026-03-31 20:00Z`; the in-sample prefix the returns `i` with `h4_ts[i + 1] <= 2026-03-31 20:00Z`.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, pasted; one state-changing git command per Bash call, nothing beside it; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names — `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and the session line.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section.
- Probes: on this `full`-tier plan, each guard a task's Probe step lists, through its own case, with `infra/scripts/mutate-probe.sh` on a committed tree, the verdict lines into `.local/iter198/probes-task-<N>.txt` (one `mkdir -p .local/iter198` first; the file started empty by `: > <file>`), carried whole into the next commit's message — Task 2's into the record's commit, Task 3 Step 4; `--basetemp=.tmp/implementer/pt` after each probe's `--`.
- The worktree is `.claude/worktrees/iter198`; the main checkout at `/home/zhaow/Projects/zcrypto-kraken` is live, and its `data/` is never written. `mkdir -p .tmp/implementer` before the first pytest run: `--basetemp` creates no parent.

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
  - Constants: `SLICE_START = datetime(2026, 7, 10, tzinfo=UTC)`; `REFERENCE_LAST_BAR = datetime(2026, 3, 31, 20, tzinfo=UTC)`; `DECISIVE_START = 1380`; `BAND_STEP = 6`; `MIN_SLICE = 180`; `RECORD_47_RETURNS = 27337`; `RECORD_47_SHARPE = 1.5609`; `SHARPE_TOLERANCE = 0.00005`; `BENCH_COST_PER_SIDE = 0.006`; `PPY_4H = 2190`; `P1_VAR_TRIALS = 1.3058096692086857e-05`. The trial count is no constant here: `revalidation_metrics` takes the subject's.
  - `class RevalidationError(Exception)`; `deflated_sharpe_ratio` imported by name (`from cli.validation import deflated_sharpe_ratio`), the name Task 2's count tie patches.
  - `slice_bounds(h4_ts: list[datetime], start: datetime) -> tuple[int, int]` — the half-open return range `[lo, hi)`: `lo` the first `i` with `h4_ts[i] >= start`, `hi = len(h4_ts) - 1`; `lo = hi` when no bar is at or after `start`.
  - `prefix_end(h4_ts: list[datetime], last_bar: datetime) -> int` — the count of returns `i` with `h4_ts[i + 1] <= last_bar`.
  - `@dataclass(frozen=True) class Band`: `sharpe_q05: float`, `maxdd_q95: float`, `sharpes: tuple[float, ...]`; each percentile filled as `float(numpy.percentile(...))`, since `validate_metrics` (`cli/registry/record.py`) refuses a `numpy.float64` leaf.
  - `band(reference: list[float], length: int, *, step: int) -> Band` — the windows `reference[s : s + length]` for `s = 0, step, 2·step, …` while `s + length <= len(reference)`; per window `sharpe(w, periods_per_year=PPY_4H)` and `max_drawdown(w)`; `RevalidationError` when no window fits.
  - `legs(slice_sharpe: float, slice_maxdd: float, band: Band) -> tuple[int, int]` — `(int(slice_sharpe >= band.sharpe_q05), int(slice_maxdd <= band.maxdd_q95))`, leg 1 then leg 2.
  - `METRIC_KEYS: frozenset[str]` = `{"in_sample_returns", "in_sample_sharpe", "reference_returns", "slice_returns", "band_windows", "band_sharpe_q05", "band_maxdd_q95", "slice_sharpe", "slice_maxdd", "slice_sharpe_rank", "slice_sharpe_ungoverned", "slice_bench4h_sharpe", "slice_mean_diff_vs_bench4h", "slice_dsr", "leg_sharpe_pass", "leg_maxdd_pass"}`.
  - `revalidation_metrics(governed: list[float], ungoverned: list[float], bench: list[float], h4_ts: list[datetime], *, n_trials: int) -> dict` — first the slice `[lo, hi)` from `slice_bounds(h4_ts, SLICE_START)` and `slice_returns = hi - lo`, a `RevalidationError` naming the count when `slice_returns < MIN_SLICE`, before any band or Sharpe is computed; then exactly `METRIC_KEYS`, every value a builtin `int` or `float`: `in_sample_returns` = `prefix_end(h4_ts, REFERENCE_LAST_BAR)`, `in_sample_sharpe` of `governed[:in_sample_returns]`; the reference `governed[DECISIVE_START:in_sample_returns]`, its length `reference_returns`; the band at `length = slice_returns`, `step = BAND_STEP`; `band_windows = len(band.sharpes)`; `slice_sharpe`, `slice_maxdd` of `governed[lo:hi]`; `slice_sharpe_rank` the share of `band.sharpes` at or below `slice_sharpe`; `slice_sharpe_ungoverned` of `ungoverned[lo:hi]`; `slice_bench4h_sharpe` of `bench[lo:hi]`; `slice_mean_diff_vs_bench4h` = mean of `governed[lo:hi]` less mean of `bench[lo:hi]`; `slice_dsr` = `deflated_sharpe_ratio(sharpe(governed[lo:hi]), slice_returns, n_trials=n_trials, var_trials=P1_VAR_TRIALS)`, its counts by keyword; `leg_sharpe_pass`, `leg_maxdd_pass` = `legs(slice_sharpe, slice_maxdd, band)`. `in_sample_sharpe`, `slice_sharpe`, `slice_sharpe_ungoverned`, `slice_bench4h_sharpe` and the band's Sharpes are annualized, `sharpe(..., periods_per_year=PPY_4H)`; `slice_dsr` alone reads the per-period Sharpe. The three series are taken as `len(h4_ts) - 1` returns each, the shape `_crossfreq_book` and `benchmark_4h_net_of_cost` return, and no length is checked.
  - `revalidation_verdict(metrics: dict) -> str | None` — `None` unless `metrics["in_sample_returns"] == RECORD_47_RETURNS` and `abs(metrics["in_sample_sharpe"] - RECORD_47_SHARPE) < SHARPE_TOLERANCE`; then `"adopt"` when both legs are 1, else `"park"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_portfolio_revalidation.py`, each over synthetic stamps on the 4h grid built by a helper `_grid(first: datetime, n: int) -> list[datetime]` and series made in the test:
  - `test_the_slice_starts_at_the_first_return_whose_first_bar_is_on_or_after_its_start` — a grid from 2026-07-09 12:00 with 10 bars: `slice_bounds(grid, SLICE_START) == (3, 9)`; a grid wholly before the start gives `lo == hi`.
  - `test_the_reference_ends_at_the_last_return_whose_second_bar_is_on_or_before_its_end` — a grid from 2026-03-31 08:00 with 6 bars: `prefix_end(grid, REFERENCE_LAST_BAR) == 3`.
  - `test_no_return_inside_the_holdout_window_enters_a_metric` — a grid from 2025-01-01 through 2026-10-10 20:00 and a varied series (a sine of the index, scaled to 0.001) passed as governed, ungoverned and bench; the same three, each with every return whose first bar is stamped 2026-03-31 20:00 through 2026-07-09 20:00 replaced by 0.5: every metric of the two calls is equal.
  - `test_the_band_counts_every_window_that_fits_and_none_past_the_end` — over 20 returns of a varied series, `band(returns, 8, step=6)` has 3 windows, starting at 0, 6 and 12, the last ending at the 20th return (a start at 18 does not fit), each Sharpe that window's own; `band(returns, 20, step=6)` has 1 window; `band(returns, 21, step=6)` raises `RevalidationError`.
  - A helper `_planted()`: the holdout test's grid; `governed` a varied series whose first 1380 returns are drawn at three times the scale of the rest, its slice `[lo, hi)` a copy of `governed[1380:1380 + (hi - lo)]`, the reference's window at offset 0; `ungoverned` and `bench` varied series of their own phases and scales, `bench` shifted down by 0.0003, so the three differ and the slice's mean difference is positive.
  - `test_a_slice_equal_to_a_band_window_reads_that_windows_sharpe_and_drawdown` — over `_planted()`: `slice_sharpe` and `slice_maxdd` are the annualized Sharpe and the drawdown of `governed[1380:1380 + slice_returns]`, both legs 1.
  - `test_each_reported_read_is_computed_over_its_own_returns` — over `_planted()` with `n_trials=7`, each read against the test's own computation: `in_sample_returns == prefix_end(grid, REFERENCE_LAST_BAR)`; `in_sample_sharpe` the annualized Sharpe of `governed[:in_sample_returns]`; `reference_returns == in_sample_returns - 1380`; `band_windows == (reference_returns - slice_returns) // 6 + 1`; `band_sharpe_q05` and `band_maxdd_q95` the 5th and 95th `numpy.percentile` of the Sharpes and drawdowns of the windows the test cuts from `governed[1380:in_sample_returns]`; `slice_sharpe_rank == sum(s <= slice_sharpe for s in those Sharpes) / band_windows`, the window at offset 0 equal to the slice; `slice_sharpe_ungoverned` and `slice_bench4h_sharpe` the annualized Sharpes of `ungoverned[lo:hi]` and `bench[lo:hi]`; `slice_mean_diff_vs_bench4h` `pytest.approx` the mean of `governed[lo:hi]` less the mean of `bench[lo:hi]`, a positive number; `slice_dsr == deflated_sharpe_ratio(sharpe(governed[lo:hi]), slice_returns, n_trials=7, var_trials=P1_VAR_TRIALS)`.
  - `test_a_slice_planted_below_the_bands_5th_percentile_fails_leg_1` and `test_a_slice_planted_past_the_bands_95th_percentile_drawdown_fails_leg_2` — each leg 0 and the other 1, `revalidation_verdict` `"park"` with the instrument fields set to record 47's.
  - `test_a_leg_at_its_band_edge_passes` — a `Band` built in the test: `legs(band.sharpe_q05, band.maxdd_q95, band) == (1, 1)`.
  - `test_the_instrument_check_gives_no_verdict_off_record_47` — each case holds the other field at record 47's value: `in_sample_returns` 27336 with `in_sample_sharpe` 1.5609 → `None`; `in_sample_sharpe` 1.5609 ± 0.00005 with `in_sample_returns` 27337 → `None`; 1.5609 ± 0.00004 with 27337 and both legs 1 → `"adopt"`.
  - `test_a_short_slice_is_refused_before_any_metric` — slices of 0, 1 and 179 returns each raise `RevalidationError` naming the count; at 0, a band of length 0 computed first would raise `sharpe`'s `ValidationError` instead.
  - `test_the_metrics_carry_exactly_the_declared_keys` — `set(revalidation_metrics(...)) == METRIC_KEYS`, and `type(value) in (int, float)` for every value.
- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_portfolio_revalidation.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected: the file errors at collection, `ModuleNotFoundError` on `cli.portfolio.revalidation`, no case run.
- [ ] **Step 3: Implement** `cli/portfolio/revalidation.py` to the interfaces above.
- [ ] **Step 4: Run them to see them pass** — the same command; expected: every case passes.
- [ ] **Step 5: Commit** `feat(portfolio): the deployable's revalidation scoring — slice, band and rule (spec 00152 D3–D6)`, the message carrying the result line.
- [ ] **Probe** (each through its own case): the slice's `>=` made `>` (`-k slice_starts`); the prefix's `<=` made `<` (`-k reference_ends`); the band's fit test `s + length <= len` made `<` (`-k band_counts`); leg 1's `>=` made `>`, and leg 2's `<=` made `<`, each its own probe (`-k band_edge`); the instrument check's `and` made `or` (`-k instrument_check`); `DECISIVE_START` dropped from the reference's slice, the rank's `<=` made `<`, and `n_trials=n_trials` at the `deflated_sharpe_ratio` call made `n_trials=6`, each its own probe (`-k each_reported_read`). The tolerance's `<` is not probed: no float lies exactly 0.00005 from 1.5609, so `<` and `<=` read alike at these constants.

### Task 2: the subject `p1-revalidation`

**Files:**
- Modify: `cli/research/subjects.py`, `tests/test_research_command.py` (the fixture writer `_p1_revalidation_dataset`, its `_CONTRACT_DATASETS`, `_RULED_FIXTURES` and `_DECLARED_COUNT` rows, the families test's row and the count tie's second recorder), `README.md` (the `--subject` row of `zcrypto research eval`)
- Test: `tests/test_research_p1_revalidation.py`

**Interfaces:**
- Consumes: Task 1's `revalidation_metrics`, `revalidation_verdict`, `METRIC_KEYS`, `RevalidationError`, `BENCH_COST_PER_SIDE`; the existing `_crossfreq_book`, `benchmark_4h_net_of_cost`, `_ASSETS`, `SubjectError`, `_b2_over`.
- Produces: `_P1_REVALIDATION_N_TRIALS = 6`, the one count the subject declares and its deflated Sharpe reads. `_build_p1_revalidation(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — a `window` refused with `SubjectError(f"{_b2_over('p1-revalidation', window)}: it scores a slice of the full build, so it reads no window; drop --window")`; else `_crossfreq_book(reader, dataset, None, as_of, accept_holes)`, `benchmark_4h_net_of_cost(h4_prices, cost_per_side=BENCH_COST_PER_SIDE)`, and `revalidation_metrics(result.governed_net, result.ungoverned_net, bench, h4_ts, n_trials=_P1_REVALIDATION_N_TRIALS)`, a `RevalidationError` re-raised as `SubjectError(f"{_b2_over('p1-revalidation', None)} of {dataset}: {exc}")`. Both refusals open with `_b2_over`'s `p1-revalidation over …`, the prefix the contract's window and spoil rows read. `SUBJECTS["p1-revalidation"] = Subject("p1-revalidation", (1440, 240), _ASSETS, _build_p1_revalidation, spec="docs/specs/00152-deployable-revalidation-design.md", metric_keys=METRIC_KEYS, seeds=(), verdict=revalidation_verdict, no_verdict="instrument finding: the read's in-sample prefix does not rebuild record 47's book, 27337 returns at Sharpe 1.5609; no verdict, the trial unspent", family="P1", n_trials=_P1_REVALIDATION_N_TRIALS)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_research_p1_revalidation.py`, over Step 2's `_p1_revalidation_dataset` imported from `tests.test_research_command`, a synthetic frozen dataset `ohlc-test`, the subject read as `SUBJECTS["p1-revalidation"]` at run time:
  - `test_the_build_returns_exactly_the_declared_keys` — `set(build) == METRIC_KEYS`, `slice_returns == 557`.
  - `test_the_build_scores_the_governed_book_beside_the_ungoverned_and_the_benchmark` — `build == revalidation_metrics(result.governed_net, result.ungoverned_net, benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006), h4_ts, n_trials=6)`, from the test's own `_crossfreq_book` over a second reader of the same fixture, and `build["slice_sharpe"] != build["slice_sharpe_ungoverned"]`, the fixture's drop engaging the governor inside the slice.
  - `test_a_synthetic_book_is_no_record_47_and_gets_no_verdict` — `revalidation_verdict(metrics) is None`.
  - `test_a_window_is_refused` — `SubjectError` whose text opens `p1-revalidation over the window ` and ends `drop --window`.
  - `test_a_set_ending_before_a_month_of_slice_is_refused` — `_p1_revalidation_dataset(tmp_path, end=datetime(2026, 8, 8, 20, tzinfo=UTC))` (`slice_returns` 179) raises `SubjectError` naming the dataset and 179.
  - `test_the_subject_declares_family_p1_its_count_and_spec` — `family == "P1"`, `n_trials == 6`, `seeds == ()`, the spec path.
- [ ] **Step 2: The shared fixture and the ruled-subject rows** in `tests/test_research_command.py`: `_p1_revalidation_dataset(tmp_path: Path, *, end: datetime = datetime(2026, 10, 10, 20, tzinfo=UTC)) -> Path` — the ten `_ASSETS` at 1440 and 240 minutes from 2025-01-01 00:00 through `end`, each `_rows(n, phase=i * 0.7, start=…, step=60 * interval)` with every price from 2026-08-20 00:00 on scaled by 0.75, a drop the governor engages on inside the slice; the `_CONTRACT_DATASETS` row `"p1-revalidation": lambda tmp_path, subject: (_p1_revalidation_dataset(tmp_path), datetime(2025, 1, 1, tzinfo=UTC))`, the comment above that dict gaining "p1-revalidation brings its own, its slice reading bars from 2026-07-10 that the declared series' 600 days from 2020 never reach"; `_RULED_FIXTURES["p1-revalidation"] = _p1_revalidation_dataset`, `_DECLARED_COUNT["p1-revalidation"] = "_P1_REVALIDATION_N_TRIALS"`, and `"p1-revalidation": ("P1", 6)` in `test_the_ruled_subjects_declare_their_families_and_trial_counts`'s dict; in `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count`, a second recorder patched over `cli.portfolio.revalidation.deflated_sharpe_ratio`, appending its `n_trials` to `counts` and returning 0.5, the comment above `_DECLARED_COUNT` ending "so that a literal at a kill-bar site, or at p1-revalidation's deflated Sharpe, fails it".
- [ ] **Step 3: Run them to see them fail** — `uv run pytest tests/test_research_p1_revalidation.py tests/test_research_command.py -k "p1_revalidation or p1-revalidation" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected: every selected case fails — the new file's on `KeyError: 'p1-revalidation'`, the count tie's `[p1-revalidation]` row on the missing `_P1_REVALIDATION_N_TRIALS`.
- [ ] **Step 4: Implement** the subject, and add `p1-revalidation` (record 47's book scored after the spent holdout against its own in-sample band; `ohlc-rolling` as of a day) to the README's `--subject` row.
- [ ] **Step 5: Run them to see them pass** — Step 3's command, then `uv run pytest tests/test_research_command.py tests/test_research_p1_revalidation.py tests/test_portfolio_revalidation.py -q -p no:cacheprovider -n 6 --basetemp=.tmp/implementer/pt`; expected: all pass.
- [ ] **Step 6: Commit** `feat(research): the p1-revalidation subject, family P1 at n_trials 6 (spec 00152 D8)`, the message carrying Task 1's probe verdicts and this task's result line.
- [ ] **Probe**: the window refusal removed (`-k window_is_refused`); the `MIN_SLICE` refusal removed (`-k before_a_month`); `result.governed_net` and `result.ungoverned_net` swapped in the build's call (`-k scores_the_governed_book`); the build's `n_trials=_P1_REVALIDATION_N_TRIALS` made `n_trials=6`, through `tests/test_research_command.py` (`-k "deflates_at_its_declared_count and p1-revalidation"`).

### Task 3 (the controller): the hash, the run and the record

- [ ] **Step 1: The pick entry** — exists: `[iter-198] The deployable's first revalidation — what is scored, on which data, and where it is registered (Decision: 1)` in `docs/research/14.phase6-decisions.md`, committed at 51b5c6123 and carried to the owner's second word and the as-of 2026-10-27 at e980cd246; nothing to write.
- [ ] **Step 2: The basis check, then the hash** — on a clean tree with Tasks 1–2 merged into the branch: spec D1's quotes — the owner's two words and item 1 as put to the owner — checked character for character against the session that holds them; then, from the worktree root with `data/ohlc-rolling` linked, the module's reads over the in-sample build alone (spec D9):

```bash
uv run python - <<'EOF'
from cli.portfolio import revalidation as rv
from cli.registry.observed import ObservedReader
from cli.research import command, subjects
from cli.validation.metrics import sharpe

window = ("2010-01-01 00:00:00+00:00", "2026-03-31 23:59:59+00:00")
_, _, h4_ts, _, result = subjects._crossfreq_book(ObservedReader(command._DATA_ROOT), "ohlc-rolling", window, "2026-10-27")
governed = result.governed_net
n = rv.prefix_end(h4_ts, rv.REFERENCE_LAST_BAR)
band = rv.band(governed[rv.DECISIVE_START : n], 659, step=rv.BAND_STEP)
print(n, sharpe(governed[:n], periods_per_year=rv.PPY_4H), n - rv.DECISIVE_START, len(band.sharpes), band.sharpe_q05, band.maxdd_q95)
EOF
```

  expected: `27337 1.560907676587497 25957 4217`, then two values rounding to −2.8851 and 0.0736 — the measured basis; any other line stops the task before the hash, the module fixed first. Then `sha256sum docs/specs/00152-deployable-revalidation-design.md`, pasted into the SDD ledger with `date -u`.
- [ ] **Step 3: The run** — from the worktree root, once `sha256sum` prints Step 2's hash again; the variant and notes are D7's, fixed here before the hash:

```bash
spec_hash=$(sha256sum docs/specs/00152-deployable-revalidation-design.md | cut -d' ' -f1)
test -L data/ohlc-rolling || ln -snT /home/zhaow/Projects/zcrypto-kraken/data/ohlc-rolling data/ohlc-rolling
uv run zcrypto research eval --subject p1-revalidation --dataset ohlc-rolling --as-of 2026-10-27 --register \
  --iteration iter-198 --family P1 --spec-hash "$spec_hash" --n-trials 6 \
  --variant P1-revalidation-record47-asof-2026-10-27 \
  --notes 'Record 47 (P1-crossfreq-fixedthird-twelve-leg-basket-btczero) revalidated over ohlc-rolling as of 2026-10-27, line 89ab2d72cfffe52befa7fc767c522e945ebeb3b78bb0f379e25d72f419c812c4: its governed book scored on the 659 returns from the close of the 2026-07-10 00:00 bar to the close of the 2026-10-27 20:00 bar, the spent holdout window read as history and never scored, against the band of its own 659-return windows over the decisive in-sample returns.'
```

  expected: `rc=0`, the printed metrics' `in_sample_returns` 27337, `reference_returns` 25957, `slice_returns` 659 and `band_windows` 4217, and one record appended (trial 63) or, on the instrument finding, one reading.
- [ ] **Step 4: The record's commit** — `git add docs/reference/trial-registry.jsonl` (or the reading ledger), and on a record `tests/test_trial_registry_provenance.py` with `"p1-revalidation": 6` added to `LANDED_N_TRIALS` and to the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` holds; committed `docs(reference): trial 63 — record 47 revalidated on 2026-07-10 → 2026-10-27, <verdict>` with the run's printed metrics and `.local/iter198/probes-task-2.txt` pasted whole, the message naming `infra/scripts/mutate-probe.sh`.
- [ ] **Step 5: The replay** — in a scratch worktree at that commit with `data/ohlc-rolling` and `data/ohlc-full` both linked to the main checkout's (the case is skipped without `ohlc-full`), `uv run pytest tests/test_registry_replay.py -k "trial-63" -q -p no:cacheprovider --durations=0` (`reading-<N>` on the instrument finding); expected `1 passed` — `1 skipped` fails the step; its own time read off the durations, and a `tests/slow-cases.txt` line added only at 10 s or more; then both links unlinked, the scratch worktree removed by `git worktree remove`, and the main checkout's `data/` listing read.
- [ ] **Step 6: The verdict entry and T0122** — through the `iteration-closeout` skill, the phase-6 log takes `[iter-198] Verdict — record 47 revalidated on the returns after the spent holdout, <ADOPT|PARK> (registry trial 63, family P1 n=6)`, followed by `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` names any, then `. ` and every metric of the record — or, on the instrument finding, `[iter-198] Record 47 revalidated on the returns after the spent holdout — the instrument finding, no verdict (reading <N>). …`; through `topic-ops`, T0122's monthly bullet records this run as the first and names the next run's form (spec D10), and its `ripe_when:` becomes `any one arm: 6b produces its first weeks of paired live-vs-simulation cycles with real fills; or a date: 2026-11-27, a month past this run's as-of, for the next revalidation subject — check: date -u +%F reads 2026-11-27 or later`, the index re-rendered. Commit each.
- [ ] **Step 7: Unlink** — `test -L data/ohlc-rolling && unlink data/ohlc-rolling` before the worktree is removed, and the main checkout's `data/` listing read after.

Decisions log: Task 3 Steps 1 and 6.
