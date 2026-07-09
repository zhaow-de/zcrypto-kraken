---
status: partial
ripe_when: the next attended Phase-4/5 protocol review — all decision inputs are merged and ready as of 2026-07-09
---

# Phase-4/5 validation-protocol decisions (human decision sheet)

## Context — what

The A1/A2 arcs (iters 044–054) surfaced changes to the **pre-registered validation protocol** (master-plan §9/§12 kill bar and evaluation methodology) that only the human may decide. Until they are decided, the loop holds the A-family's 8 reserved trials (see the "broken instrument suspends spending" rule) and records worst-slice outcomes as uninformative.

## Why this matters

The kill bar's current worst-slice leg cannot discriminate a challenger from the benchmark (it fails gated-B1 itself), and its SPA leg runs zero-fee (it over-credited high-turnover A1). Every future family verdict — and the disposition of the already-parked A1/A2 arms — depends on these calls.

## Findings so far

Reports `docs/research/07` (cost-asymmetry gap, A1-long/flat tradeoff), `09` (worst-slice exposure-blindness, warm-up handicap); decisions log iters 045–053. The candidate instruments are merged and tested: `net_of_cost_verdict` (iter-050) and `benchmark_relative_worst_slice` (iter-054), both in `cli/alpha/killbar.py`; `a1_kill_bar` itself is unchanged.

## Consequence tables (iter-066 — decision-support; adjudication stays yours)

Each candidate worst-slice redesign applied to the contested books (calendar years, end-of-move stamping; A1-lf weekly = the offset-mean series, QA'd to the recorded 1.380 at vol=0.12; full table in the iter-066 history entry):

- **(a) absolute (current leg): FAILS every real book — including the adopted bar itself** (B3+vt-dynamic: 2018/2022/2023/2025) **and the adopted combined system**. The leg cannot pass anything that trades.
- **(c) absolute excluding 2013/2026 stubs: barely moves** — it clears only A2's 2026 rows; every book still fails on full-year slices. The stub question is secondary to exposure-blindness.
- **(b) benchmark-relative (iter-054 diagnostic, vs the adopted bar): discriminates in both directions** — combined PASS (smaller DD 8/11 years), A1-lf weekly PASS (5/11), gated-B1 FAIL, A2 slow arms (20–100) FAIL (DD 5/11 and 2/11), A2 fast arms narrow PASS (5/11, 4/11). Design caveat, stated without an empirical case here: a DD-count criterion can in principle favor low-exposure books, so weigh a P&L/exposure dimension alongside it.
- **DSR threshold: the 0.5 → 0.95 choice flips zero recorded verdicts** (min recorded DSR 0.9978 across all 32; record 33's post-hoc DSR 0.999999). Tightening is free today; it binds only future marginal families.

## Done so far

- **Deployable bar / frozen benchmark — DECIDED (human, 2026-07-09, on PR #74 review): adopt B3+vt-dynamic** as the frozen benchmark, superseding gated-B1. Recorded in master-plan §9 benchmark-family paragraph (with the exact construction spec + reference figures: net-of-cost 1.245 full / 1.278 post-warm-up; zero-fee 1.419 / maxDD 21.9 %), the decisions log, and `docs/benchmark-b2-dynamic-report.md` §"B3 and B4". Consequences: future kill-bar SPA legs compare against B3+vt-dynamic; the iter-055 re-reads vs this bar already exist (A1-long/flat weekly beats it, p = 0.0070; A2's long/flat arms fall below it post-warm-up); the remaining protocol legs below are unchanged and still gate the A-family resumption.

## Suggested next steps

Each item = read the named evidence, decide, record the decision in the decisions log + master-plan §12 wording, and (where it changes code) have `a1_kill_bar` updated in a reviewed iteration:

- **Worst-slice leg**: replace the absolute Sharpe>0-per-year leg with (a) benchmark-relative (`benchmark_relative_worst_slice`'s `beats_benchmark_worst` — now vs **B3+vt-dynamic**, the adopted bar), (b) drawdown/P&L-based, and/or (c) exclusion of partial-year stubs (2013 = 109 periods, 2026 = 89). Evidence: `09` finding 1 — gated-B1 fails the current leg on 2014 (Sharpe −2.07) despite being ~87 % flat and losing only −5.5 % (6.0 % DD); the leg is exposure-blind and skips zero-variance slices (rewards non-participation). **Plus the iter-065 stub probe (T0011 Done-so-far; A2 rows corrected in iter-066)**: in 2026 every benchmark + the combined system sat at literal zero exposure (skipped as degenerate) while A2's fast arms genuinely lost −10.6 %/−12.7 % at ~19 % exposure and its slow arms −2.5 % at 1.6 %; base rate — a 1.33-Sharpe book shows negative 89-bar windows ~41 % of the time (27 % for 365-bar), so a negative stub is near-uninformative in general even where a specific book's loss is real.
- **Evaluation window**: ratify comparing challenger vs benchmark on the **post-benchmark-warm-up window** (k ≥ 200 under gated-B1; **k ≥ 230 under the adopted B3+vt-dynamic**, whose basket-lookback + equity-gate warm-up is ~229 — see master-plan §9) or an alternative. Evidence: `09` finding 2 — A2's K=8 net-of-cost family SPA moves 0.034 (full) → 0.057 (post-warm-up). Related: the tick-report's early-2013/2014 data-quality caveat (sparse 2-asset early history).
- **Net-of-cost SPA leg**: fold `net_of_cost_verdict` into the pre-registered bar (both sides charged their own realistic cost) so a zero-fee edge erased by turnover cannot clear it. Evidence: `07`.
- **DSR pass threshold**: ratify `dsr > 0.5` (the faithful "DSR > 0" reading, current) or tighten to the 0.95 significance bar. Evidence: iter-045 decisions entry + the flag in `cli/alpha/killbar.py`'s docstring.
- **A1-long/flat disposition**: net-of-cost superior at weekly cadence and — updated iter-055 — **significantly beats even the new candidate bar B3+vt-dynamic** (net-of-cost 1.380 full / 1.416 post-warm-up — the Sharpe of the offset-*averaged* series, iter-049's own SPA construction; the per-offset-mean statistic is ≈ 1.30, and 3 of 7 individual weekly phases sit below the candidate bar — vs B3+vt's 1.245 / 1.278; head-to-head p = 0.0070, +1.7 bps/day), yet worst-slice-rejected on 2014 (−1.8) under the mis-calibrated leg — decide under the revised bar, including whether 2014 is a genuine tail or an early-data artifact. Evidence: `07` §long-flat-capstone (iter-053 re-scoping) + `docs/benchmark-b2-dynamic-report.md` §B3/B4 re-reads. **Plus the iter-069 start-date table (the 2014 question answered directly)**: rebuilding book AND benchmark from each Jan-1 truncation 2014–2023, A1-lf weekly beats the bar at *every* start, significantly (v0.12 p ≤ 0.0195) at all starts except the short 2023 window (p = 0.0625, 1185 bars) — and **dropping 2014 strengthens the edge** (2015 start: 1.549 vs 1.269, p = 0.0015). Its maxDD is 15.78 % vs the bar's 25.53 % (worst episode 2024-03 → 2024-11, inside every window). Honest margins: v0.10's full-window p sits exactly at 0.0500; the recorded p = 0.0070 is the k≥230 window (full-window 0.0080).
- **Resumption**: after the above, decide whether the A-family's 8 reserved trials re-run under the revised bar (this also un-blocks T0011).
