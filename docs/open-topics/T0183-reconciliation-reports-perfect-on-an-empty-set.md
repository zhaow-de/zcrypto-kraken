---
status: partial
---

# A reconciliation reports a perfect score when it compared nothing

## Context — what

A summary statistic whose empty-input branch returns the value that also means success. `cli/tick/reconcile.py`'s `reconcile` returned `pct_within_tol: 100.0` with no intervals, and `cli/backfill/reconcile.py`'s `reconcile_series` returned `ohlc_match_rate: 1.0`, `volume_rel_diff_max: 0.0` and `vwap_mean_abs_rel_diff: 0.0` with no overlap: the two members the topic was opened for. In each, the value a reader acts on says *everything agreed* when the truthful answer is *nothing was compared*.

The family is defined by that shape, not by a literal. A `1.0`, a `100.0` and a `0.0` are all members when the metric's good direction points that way, so `grep 'return 1.0'` is the wrong instrument twice over — it finds a sign function in `cli/features/trend_agreement.py` that is not a member, and it misses `volume_rel_diff_max: 0.0` that is.

**The tell that finds them fastest is a file that applies a polarity decision to some of its fields and not others.** `cli/xcheck/binance.py`'s `crosscheck_dataset` returned `None` for `min_close_corr` and `0.0` for `max_abs_rel_diff_overall`, one line apart; `cli/backfill/reconcile.py`'s `reconcile_dataset` has the same pair and made the same split. A member beside a non-member in the same dict is the readable signature of the defect, and it is what a sweep by shape alone reads past.

## Why this matters

A reconciliation exists to answer whether two sources agree, and its empty case is the one where a caller most needs to know it got no answer. `agent-ops.md` already names the class for queries — *an empty filtered query is not an absent event; require a positive trace and print the input's line count before trusting any zero* — and these are the same failure inside the code that computes the number rather than in a shell reading it. A pipeline whose upstream join silently produced no overlap reports a clean reconciliation, and every downstream reader, dashboard and operator sees agreement.

Every member sits on data QA rather than on the live trade path, which is why this was registered rather than escalated.

## Findings so far

**The family is an empty DENOMINATOR, not an empty input, and an exclusion is what establishes that.** `cli/engine/concordance.py`'s `compare_targets` returns `passed=True, worst_abs_diff=0.0` on empty and is CORRECT: its `set(a) != set(b)` guard has already returned, so reaching `not a` means both sides are empty and their key sets agree — two environments each reporting no positions genuinely concur. It is on the live trade path, so a fix refusing every empty input would have turned a legitimate both-flat agreement into an error there.

**The sweep** ran over `cli/` in two AST passes: every early return guarded by an emptiness test, and every conditional expression whose true arm contains a division, `max(`, `mean` or `sum(`. The second pass is where the members concentrate — a guarded division on one line has no `if` statement for the first pass to see. Every row below was opened and read.

**One member the sweep missed, and why.** `crosscheck_series`'s guard reads `if overlap_rows < 2`, and the first pass's emptiness predicate enumerated the spellings already seen — `not `, `== 0`, `is_empty`, `height`, `len(`, `< 1`, `<= 0`. A predicate built from the members already found finds the members that look like them. It was caught by a reviewer, in the same file and seven lines above a member already fixed, and it defeated that fix for the case that actually happens: with one symbol whose Binance window does not reach Kraken's, the dataset maximum was still taken over a `0.0`.

**The tick instance was documented and pinned, not overlooked.** Its docstring said zero overlap reports the percentage "vacuously" and shipped it, and a test named `test_reconcile_zero_overlap_reports_vacuous_full_match` held it in place. The prose was correct and the code was wrong; only reading them against each other surfaced it, and the test made the defect harder to remove by making its removal look like a regression.

**Why `None` rather than a field, a sentinel or a raise.** Both original members already returned their denominator — `n_intervals: 0`, `overlap_rows: 0` — beside the value that lied, so reporting the emptiness in a field is the fix that had already lost here, twice, because the headline is what gets read. `math.nan` survives arithmetic silently and is truthy under `bool()`. Raising is wrong for a report function called per-pair in a sweep, where one empty window must not abort the run.

Excluded, with the reason:

- `cli/trades/gaps.py` — counts, not ratios: zero gaps in zero rows is a true count, and `rows` sits in the same struct and is read by `backfill.py`.
- `cli/ohlc/qa.py`, `cli/alpha/killbar.py` — same shape, opposite polarity; 0 % coverage and a 0.0 hit rate are the failure direction.
- `cli/engine/soak.py`'s `eff_n` family — 0 is the degenerate direction `degenerate()` also reports.
- `cli/engine/feeders.py` and `cli/engine/tracking.py` (`math.nan`), and `crosscheck_dataset`'s `min_close_corr` (`None`) — already refuse to invent a value; `min_close_corr` set the convention this fix adopted.
- `cli/validation/dsr.py` — success direction, but `0.0` is the formula's limit at `n_trials == 1` or zero dispersion, not a guard over an unmade comparison.
- `cli/risk/limits.py` — `math.inf` headroom on zero use is correct.
- `cli/alpha/b1.py`, `cli/features/{channel,derivatives,momentum}.py` — neutral defaults for a feature, not summaries of a comparison.

Flagged, NOT adjudicated: `cli/engine/soak.py`'s `_mean` (a generic helper) and `analyze_soak`'s `gov_live`. Their polarity turns on callers the sweep did not read, and a guess would put a wrong row in a census.

**Two things recorded rather than fixed.** `_match_stats`'s `else None` arm is unreachable — `reconcile`'s own empty-intervals return fires first, proven by a `12345.0` mutation of that arm surviving the suite — so its census row below is the family's shape stated where the shape belongs, not a live defect removed. And `all_match: False` on an empty join still conflates *nothing was compared* with *compared and disagreed*; it is the fail-safe direction and the only other one a boolean has, so a caller that needs to tell them apart reads `n_joined` beside it.

## Done so far

| site | computes | was | now |
|---|---|---|---|
| `cli/tick/reconcile.py` · `_match_stats` | the within-tolerance pct | `100.0` | `None` |
| `cli/tick/reconcile.py` · `reconcile` | `pct_within_tol`, `pct_within_tol_loose` | `100.0` | `None` |
| `cli/backfill/substrate15m.py` · `reconcile_15m_vs_ticks` | `coverage_pct` | `100.0` | `None` |
| `cli/backfill/substrate15m.py` · `seam_15m_to_1h` | `max_price_rel_diff`, `max_volume_rel_diff` | `0.0` | `None` |
| `cli/backfill/substrate15m.py` · `seam_15m_to_1h` | `all_match` | `True` | requires a non-empty join |
| `cli/xcheck/binance.py` · `crosscheck_series` | `max_abs_rel_diff` | `0.0` | `None`, rendered `n/a` |
| `cli/xcheck/binance.py` · `crosscheck_dataset` | `max_abs_rel_diff_overall` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `ohlc_match_rate` | `1.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `volume_rel_diff_max` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `vwap_mean_abs_rel_diff` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_dataset` | `min_ohlc_match_rate` | `1.0` | `None`, rendered `n/a` |

`reconcile_series`'s three fields are one branch but three decisions: a rate whose success value is `1.0` beside two deviation measures whose success value is `0.0`. Listing them as one row is how a reader stops seeing a `0.0` as a member at all.

Each fix carries a test whose empty case fails against the pre-fix literal, and beside it a populated-input control asserting the measured value, so a guard that answered `None` or `n/a` unconditionally cannot pass either. Three such controls were added only after `infra/scripts/mutate-probe.sh` reported the corresponding mutation SURVIVED.

## Suggested next steps

- `cli/engine/soak.py`'s `structural_metrics` (`bar_hhi`, `0.0`) and `analyze_soak` (`null_cap_rate`, `0.0`) still return their success value on an empty denominator. A return-value change is behavioural, so the prose-only exemption does not reach them; they need the coordinator's word on that file's review floor before the fix, which is why no `ripe_when:` is declared — the remainder is a question to ask, not a repo state to wait on.
- Adjudicate `cli/engine/soak.py`'s `_mean` and `analyze_soak`'s `gov_live` by reading what their callers do with the value.
