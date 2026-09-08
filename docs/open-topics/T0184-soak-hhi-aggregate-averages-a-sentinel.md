---
status: open
---

# The soak report averages a specified HHI sentinel as though it were a measurement

## Context — what

`structural_metrics` (`cli/engine/soak.py:65`) computes a per-bar concentration `hhi = Σ_a (|w_a|/gross)^2` and returns `0.0` for a bar whose gross is at or below `1e-12` — a branch recorded as the design at `docs/plans/00058-soak-check-oos-report.md:52`. That `0.0` is a sentinel, not a measurement: `docs/specs/00059-soak-check-realized-governor-cap-design.md:49` states HHI's lower bound is `1/n > 0`, so no measured bar can produce it, and a reader of one bar can always tell unmeasurable from measured. The site is sound.

`analyze_soak` is not. Its gating loop (`cli/engine/soak.py:998-1010`) takes `_mean(live_series)` over the realized per-bar `hhi` list and hands the null's list to `windowed_null` and `block_bootstrap_null` (`:950-956`), none of which knows the value is out of range. A flat bar inside an otherwise active window contributes `0.0` to the mean and pulls the concentration figure toward *better diversified than anything measured*. `hhi` is one of the seven gating verdicts under spec `00059` D6 (`_METRIC_ROWS`, `soak.py:1201`), so the figure is one the go-live decision reads.

The all-flat case is already detected — `test_analyze_soak_degenerate_zero_exposure` (`tests/test_engine_soak.py:878`) drives six all-zero-weight bars through the branch and asserts `is_degenerate`. The defect is the mixed window: some flat bars among active ones, which nothing flags.

Split out of `T0183` because it is not a member of that family. `T0183`'s members return a value the metric can genuinely take, so nothing downstream can tell the empty case from a measured one; here the site returns a value the metric excludes, and the consumer is what fails to honour that.

## Why this matters

`soak_report` is the instrument the go-live decision reads. A fabricated number there cannot place a trade — `soak_report` is reached only by the offline `soak-check` command and the file places no order — but it can steer whether trades are placed at all. A concentration figure biased toward *well diversified* is the one that says the book is more diversified than it is at exactly the moment someone decides to go live. That makes this worse than `T0183`'s members rather than milder, and it is why it takes its own decision instead of a quiet fix.

Fixing it moves a gating verdict: excluding unmeasurable bars from the aggregate changes that metric's window and its `effective_n`. No HHI figure has been published in any research report or decisions log — the only occurrences under `docs/` are the spec and plan that define it — so nothing recorded is invalidated, but the number a future soak reports will differ from what the current code would have said.

## Findings so far

- The per-bar site is correct and specified; the defect is entirely in aggregation. `bar_hhi` stays `0.0` on empty gross: three consumers need floats, and `windowed_null` slices contiguous windows, so the per-bar lists must stay parallel — `None` is not a drop-in there.
- The meaning-preserving fix is to exclude out-of-range bars from the aggregate rather than average them, which leaves the specified sentinel untouched and changes only what the consumer does with it.
- This is `T0183`'s general form applied to a consumer: a sentinel still produces that family's failure the moment something aggregates it without knowing it is one. The question at this site is not what the empty branch returns but whether every consumer knows the value is out of range.

## Suggested next steps

Decomposed by what feeds the decision and what waits on it.

- **Measure whether the mixed window occurs, and how much it moves the figure** (autonomous — feeds the decision). Over a soak journal that `soak-check` actually reads — a pulled VPS journal via `--journal-dir` is the read-only input — count the bars with `gross <= 1e-12` inside windows that also carry active bars, and compute the `hhi` mean with and without them. A decision about a gating metric needs the size of the bias, not the existence of the branch. Paste the counts and both means into this file.
- **Rule on the aggregation** (the owner's — it changes a number a go-live decision reads). The recommendation on record: exclude unmeasurable bars from the mean and from the null series passed to `windowed_null` and `block_bootstrap_null`, with the metric's `effective_n` recomputed over the bars that remain, so the sentinel is honoured everywhere the per-bar list is consumed. The alternative is a conscious keep with the measured bias recorded beside it.
- **Implement with a test that constructs the mixed window** (waits on the ruling): a fixture with active bars and one flat bar, asserting the `hhi` mean equals the mean over the active bars alone and that `effective_n` counts only those — constructed so it fails against today's code — with the all-active and all-flat cases beside it.
