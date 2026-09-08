---
status: partial
---

# A reconciliation reports a perfect score when it compared nothing

## Context — what

Two reconcile functions return their best possible value on an empty comparison set rather than refusing to report one. `cli/tick/reconcile.py:46-54` returns `pct_within_tol: 100.0` and `pct_within_tol_loose: 100.0` when `n_intervals == 0`; `cli/backfill/reconcile.py:19-26` returns `ohlc_match_rate: 1.0`, `volume_rel_diff_max: 0.0` and `vwap_mean_abs_rel_diff: 0.0` when `overlap_rows == 0`. In both, the value a reader acts on says *everything agreed* when the truthful answer is *nothing was compared*.

The family is defined by shape, not by a literal: a summary statistic whose empty-input branch returns the value that also means success. A `1.0`, a `100.0` and a `0.0` are all members when the metric's good direction points that way, so the sweep is by shape and never by `grep 'return 1.0'` — that grep finds a sign function in `cli/features/trend_agreement.py:19` which is not a member, and misses `volume_rel_diff_max: 0.0` which is.

## Why this matters

A reconciliation exists to answer whether two sources agree, and its empty case is the one where a caller most needs to know it got no answer. `agent-ops.md` already names the class for queries — *an empty filtered query is not an absent event; require a positive trace and print the input's line count before trusting any zero* — and these are the same failure inside the code that computes the number rather than in a shell reading it. A pipeline whose upstream join silently produced no overlap reports a clean reconciliation, and every downstream reader, dashboard and operator sees agreement.

Both members sit on data QA rather than on the live trade path, which is why this is registered rather than escalated.

## Findings so far

**The family is an empty DENOMINATOR, not an empty input, and an exclusion is what establishes that.** `cli/engine/concordance.py:138`'s `compare_targets` returns `passed=True, worst_abs_diff=0.0` on empty and is CORRECT: its `set(a) != set(b)` guard has already returned, so reaching `not a` means both sides are empty and their key sets agree — two environments each reporting no positions genuinely concur. It is on the live trade path, so a fix refusing every empty input would have turned a legitimate both-flat agreement into an error there.

**The sweep** ran over `cli/` in two AST passes: every emptiness-guarded early return (99 candidates), and every conditional expression containing a division, `max(`, `mean` or `sum(` (69). The second found most members — a guarded division on one line has no `if` statement for the first to see. Every row below was opened.

| site | computes | was | now |
|---|---|---|---|
| `cli/tick/reconcile.py:35` | `_match_stats` pct | `100.0` | `None` |
| `cli/tick/reconcile.py:46` | `pct_within_tol`, `_loose` | `100.0` | `None` |
| `cli/backfill/substrate15m.py:85` | `coverage_pct` | `100.0` | `None` |
| `cli/backfill/substrate15m.py:142,143` | `max_{price,volume}_rel_diff` | `0.0` | `None` |
| `cli/backfill/substrate15m.py:144` | `all_match` | `True` | requires a non-empty join |
| `cli/xcheck/binance.py:113` | `max_abs_rel_diff_overall` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py:19` | `ohlc_match_rate` + two maxima | `1.0` / `0.0` | **open** — fenced behind `docs/prose-batch-b` |
| `cli/engine/soak.py:46` | `bar_hhi` | `0.0` | **open** — engine, review floor undetermined |
| `cli/engine/soak.py:1134` | `null_cap_rate` | `0.0` | **open** — engine, review floor undetermined |

Excluded, with the reason:

- `cli/trades/gaps.py:46` — counts, not ratios: zero gaps in zero rows is a true count, and `rows` sits in the same struct and is read by `backfill.py`.
- `cli/ohlc/qa.py:76`, `cli/alpha/killbar.py:143` — same shape, opposite polarity; 0 % coverage and a 0.0 hit rate are the failure direction.
- `cli/engine/soak.py:1003,1048,1060,1141` — the `eff_n` family, where 0 is the degenerate direction `degenerate()` also reports.
- `cli/engine/feeders.py:60,232,235` (`math.nan`), `cli/engine/tracking.py:297,308,309` and `cli/xcheck/binance.py:112` (`None`) — already refuse to invent a value; `:112` set the convention this fix adopted.
- `cli/validation/dsr.py:20` — success direction, but `0.0` is the formula's limit at `n_trials == 1` or zero dispersion, not a guard over an unmade comparison.
- `cli/risk/limits.py:118` — `math.inf` headroom on zero use is correct.
- `cli/alpha/b1.py:156,160`, `cli/features/{channel,derivatives,momentum}.py` — neutral defaults for a feature, not summaries of a comparison.

Flagged, NOT adjudicated: `cli/engine/soak.py:892` (a generic mean helper) and `:1046` (`gov_live`). Their polarity turns on callers the sweep did not read, and a guess would put a wrong row in a census.

**The tick instance was documented and pinned, not overlooked.** Its docstring said zero overlap reports the percentage "vacuously" and shipped it, and a test named `test_reconcile_zero_overlap_reports_vacuous_full_match` held it in place. The prose was correct and the code was wrong; only reading them against each other surfaced it, and the test made the defect harder to remove by making its removal look like a regression.

**Why `None` rather than a field, a sentinel or a raise.** Both original members already returned their denominator — `n_intervals: 0`, `overlap_rows: 0` — beside the value that lied, so reporting the emptiness in a field is the fix that had already lost here, twice, because the headline is what gets read. `math.nan` survives arithmetic silently and is truthy under `bool()`. Raising is wrong for a report function called per-pair in a sweep, where one empty window must not abort the run.

## Suggested next steps

- `cli/backfill/reconcile.py:19` takes the same `None` treatment once `docs/prose-batch-b` merges.
- `cli/engine/soak.py:46` and `:1134` need that file's review floor established first: a return-value change is behavioural, so the prose-only exemption does not reach it.
- Adjudicate `cli/engine/soak.py:892` and `:1046` by reading what their callers do with the value.
