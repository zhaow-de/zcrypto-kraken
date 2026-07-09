---
status: open
ripe_when: the next attended Phase-4/5 protocol review — all decision inputs are merged and ready as of 2026-07-09
---

# Phase-4/5 validation-protocol decisions (human decision sheet)

## Context — what

The A1/A2 arcs (iters 044–054) surfaced changes to the **pre-registered validation protocol** (master-plan §9/§12 kill bar and evaluation methodology) that only the human may decide. Until they are decided, the loop holds the A-family's 8 reserved trials (see the "broken instrument suspends spending" rule) and records worst-slice outcomes as uninformative.

## Why this matters

The kill bar's current worst-slice leg cannot discriminate a challenger from the benchmark (it fails gated-B1 itself), and its SPA leg runs zero-fee (it over-credited high-turnover A1). Every future family verdict — and the disposition of the already-parked A1/A2 arms — depends on these calls.

## Findings so far

Reports `docs/research/07` (cost-asymmetry gap, A1-long/flat tradeoff), `09` (worst-slice exposure-blindness, warm-up handicap); decisions log iters 045–053. The candidate instruments are merged and tested: `net_of_cost_verdict` (iter-050) and `benchmark_relative_worst_slice` (iter-054), both in `cli/alpha/killbar.py`; `a1_kill_bar` itself is unchanged.

## Suggested next steps

Each item = read the named evidence, decide, record the decision in the decisions log + master-plan §12 wording, and (where it changes code) have `a1_kill_bar` updated in a reviewed iteration:

- **Worst-slice leg**: replace the absolute Sharpe>0-per-year leg with (a) benchmark-relative (`benchmark_relative_worst_slice`'s `beats_benchmark_worst`), (b) drawdown/P&L-based, and/or (c) exclusion of partial-year stubs (2013 = 109 periods, 2026 = 89). Evidence: `09` finding 1 — gated-B1 fails the current leg on 2014 (Sharpe −2.07) despite being ~87 % flat and losing only −5.5 % (6.0 % DD); the leg is exposure-blind and skips zero-variance slices (rewards non-participation).
- **Evaluation window**: ratify comparing challenger vs benchmark on the **post-benchmark-warm-up window** (k ≥ 200) or an alternative. Evidence: `09` finding 2 — A2's K=8 net-of-cost family SPA moves 0.034 (full) → 0.057 (post-warm-up). Related: the tick-report's early-2013/2014 data-quality caveat (sparse 2-asset early history).
- **Net-of-cost SPA leg**: fold `net_of_cost_verdict` into the pre-registered bar (both sides charged their own realistic cost) so a zero-fee edge erased by turnover cannot clear it. Evidence: `07`.
- **DSR pass threshold**: ratify `dsr > 0.5` (the faithful "DSR > 0" reading, current) or tighten to the 0.95 significance bar. Evidence: iter-045 decisions entry + the flag in `cli/alpha/killbar.py`'s docstring.
- **A1-long/flat disposition**: net-of-cost superior at weekly/biweekly cadence (~1.30 vs gated-B1's 1.047, family-corrected p ≈ 0.022) yet worst-slice-rejected on 2014 (−1.8) — decide under the revised bar, including whether 2014 is a genuine tail or an early-data artifact. Evidence: `07` §long-flat-capstone (with the iter-053 re-scoping).
- **Resumption**: after the above, decide whether the A-family's 8 reserved trials re-run under the revised bar (this also un-blocks T0011).
