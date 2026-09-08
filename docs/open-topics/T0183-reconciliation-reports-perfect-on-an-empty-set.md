---
status: open
---

# A reconciliation reports a perfect score when it compared nothing

## Context — what

Two reconcile functions return their best possible value on an empty comparison set rather than refusing to report one. `cli/tick/reconcile.py:46-54` returns `pct_within_tol: 100.0` and `pct_within_tol_loose: 100.0` when `n_intervals == 0`; `cli/backfill/reconcile.py:19-26` returns `ohlc_match_rate: 1.0`, `volume_rel_diff_max: 0.0` and `vwap_mean_abs_rel_diff: 0.0` when `overlap_rows == 0`. In both, the value a reader acts on says *everything agreed* when the truthful answer is *nothing was compared*.

The family is defined by shape, not by a literal: a summary statistic whose empty-input branch returns the value that also means success. A `1.0`, a `100.0` and a `0.0` are all members when the metric's good direction points that way, so the sweep is by shape and never by `grep 'return 1.0'` — that grep finds a sign function in `cli/features/trend_agreement.py:19` which is not a member, and misses `volume_rel_diff_max: 0.0` which is.

## Why this matters

A reconciliation exists to answer whether two sources agree, and its empty case is the one where a caller most needs to know it got no answer. `agent-ops.md` already names the class for queries — *an empty filtered query is not an absent event; require a positive trace and print the input's line count before trusting any zero* — and these are the same failure inside the code that computes the number rather than in a shell reading it. A pipeline whose upstream join silently produced no overlap reports a clean reconciliation, and every downstream reader, dashboard and operator sees agreement.

Both members sit on data QA rather than on the live trade path, which is why this is registered rather than escalated.

## Findings so far

- Both members were opened and read, not grepped, during the batch-B prose pass (`docs/prose-batch-b`); bravo flagged rather than folded them, correctly, since a code fix on a prose branch is the omnibus failure `branch-workflow.md` bans.
- `cli/tick/reconcile.py`'s instance was found independently earlier by a QC read of the tick package, so the shape has now surfaced twice from different directions.
- `cli/features/trend_agreement.py:19` was checked and excluded: `_sign` returning `1.0` for a positive input is not a summary statistic.
- No sweep of the whole tree by shape has been run yet, so the member list is a floor and not a census.

## Suggested next steps

- Sweep `cli/` by shape for the family: every function returning a rate, ratio, percentage, count-based score or max-deviation whose zero-input branch returns the success-direction value. Enumerate each candidate with its file, line and empty-branch return, and adjudicate each one — member or not — rather than reporting a count.
- For each confirmed member, decide between refusing (raising, or returning `None`) and reporting the emptiness in a field a caller must read, and apply one choice consistently across the family rather than per site.
- Add a test per member that pins the empty case, constructed so it fails against today's code and passes after the fix, with a populated-input case beside it that must keep passing.
- `cli/backfill/reconcile.py` is touched by the open `docs/prose-batch-b` branch; its fix waits until that merges, so the two do not collide on the same file.
