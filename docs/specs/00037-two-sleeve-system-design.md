# Two-sleeve system + ratified kill bar (design)

**Iteration:** iter-072 (attended decisions → autonomous build). **Goal:** execute the T0009 decision set (2026-07-09, attended, decisions log `[iter-072]`): fold the ratified kill bar into `a1_kill_bar`; register **trial 34** (A1-long/flat weekly v0.12, the admitted second sleeve) under that bar; build and validate the **two-sleeve combination as P1 trial 35**; prepare the holdout-look script for the ratified out-of-time window.

## The ratified bar (T0009, all six legs decided)

1. **Worst-slice leg**: benchmark-relative (`benchmark_relative_worst_slice`'s `beats_benchmark_worst` vs the frozen benchmark) with **partial-year stubs (2013, 2026) excluded**; per-slice P&L/DD reported as part of the reading.
2. **Evaluation window**: **k≥230 decisive** for SPA/head-to-head legs; both windows always reported.
3. **SPA leg**: **net-of-cost** — both sides charged their own turnover + carry (`net_of_cost_verdict` machinery).
4. **DSR threshold**: **> 0.95**.
5. A1-lf weekly v0.12 **admitted** as a second sleeve (trial 34, spends 1 of 8 reserved A-family trials).
6. A-family spending **resumes** in future loops (T0011 goes live when T0009 resolves at this iteration's close).

## Committed code: `a1_kill_bar` fold-in (TDD)

`cli/alpha/killbar.py::a1_kill_bar` updated in place to the ratified protocol (ratification date in the docstring):

- **SPA leg**: unchanged machinery, but the docstring + contract state the caller passes **net-of-cost** series for both book and benchmark, and the leg is evaluated on the **post-warm-up window** — new keyword `decisive_start: int = 0`; the caller passes the benchmark's warm-up cut (230 for B3+vt-dynamic). Full-window figures remain in the result dict for reporting.
- **Worst-slice leg**: replaced. New signature parameter `benchmark_slices` (same shape as the iter-054 diagnostic); the leg passes iff `benchmark_relative_worst_slice(book_slices, benchmark_slices)["beats_benchmark_worst"]` is true, where the caller excludes stub slices. The old absolute computation is removed from the pass/fail path but the per-slice Sharpe values stay in the result for the record.
- **DSR leg**: threshold 0.5 → **0.95**.
- Result dict keeps its shape (`passes`, per-leg booleans + values) so registry metrics stay comparable; new fields added, none removed.
- Tests updated/added: planted cases for each leg at the new thresholds; a regression test asserting the ratified configuration (net-of-cost inputs + relative worst-slice + 0.95) reproduces the trial-34 verdict computed by the driver.

## Trial 34 — A1-lf weekly v0.12 (family `A1`, `variant="A1lf-weekly-v012"`, `n_trials_in_family=33`)

Verdict under the ratified bar via the driver (QA first: offset-mean Sharpe reproduces 1.3798; bench 1.2455):

- DSR at the family's true trial count (n=33; `var_trials` from the 32 recorded per-period Sharpes) — expect ≫ 0.95.
- SPA net-of-cost, k≥230 decisive (recorded: p = 0.0070) + full window (0.0080).
- Benchmark-relative worst-slice, stubs excluded (iter-066: PASS, DD 5/11).
- Cost stress ×1.5 (iter-070: 1.2865 vs 1.1581, p = 0.0115) and ×2 reported.
- Expected verdict **adopt**; recorded as computed, not as expected.

## Trial 35 — the two-sleeve P1 combination (`family="P1"`, `variant="B3vtdyn+A1lf-w012+gov+cap"`, `n_trials_in_family=2`)

**Construction (weight-level, full costing — decisions log `[iter-072]` item 2):**

1. Sleeve position sets on the union calendar: `pos_B_a[k]` = the benchmark sleeve's per-asset positions (`w·l3`); `pos_A_a[k]` = the A1-lf weekly **offset-mean** held positions (mean over the 7 offsets' position-hold books).
2. Sleeve weights `w_B[k], w_A[k]`: rolling 30-bar inverse-vol on each sleeve's net-of-cost returns through k−1, normalized; 0.5/0.5 for k < 30. *\[Precision added during execution: inverse-vol applies only when BOTH windows have positive vol; ANY degenerate window (a sleeve flat over its trailing 30 bars) falls back to 0.5/0.5 — the spec originally left this branch unstated, the driver and its diagnostic implemented it differently, and the divergence was caught by bisection before any verdict was recorded (decisions log \[iter-072\]).\]*
3. Combined per-asset positions `c_a[k] = w_B[k]·pos_B_a[k] + w_A[k]·pos_A_a[k]` → `apply_position_caps` (20 %/10 %).
4. **Per-asset net-of-cost on the final capped book** (turnover of `c` × 0.006/side; no shorts → no carry). Internal crossings between sleeves net out — full costing, not the overlay approximation.
5. `drawdown_governor` (D1 defaults) on the capped book's own net-of-cost series; final positions = multiplier × capped.

**Pre-registered adopt criteria (fixed before any number):** (a) QA — each sleeve reproduces its frozen figures through this driver; cap + governor engagement evidenced; (b) combined maxDD ≤ 15 %; (c) combined net-of-cost Sharpe ≥ record 33's **1.3263** (point) — failing this, verdict **reject** and the holdout look runs on record 33; (d) the ratified-bar legs vs the frozen benchmark reported in full (net-of-cost SPA k≥230 decisive + full window; benchmark-relative worst-slice, stubs excluded; ×1.5/×2 cost stress; DSR at n=2 with the deflation noted; PSR).

## Docs & lifecycle at close

- Master-plan **§9/§12 wording** updated to the ratified bar (per T0009's own instruction), marked with the decision date.
- **T0009 → resolved** (archived; all six legs decided, the code fold-in landing in this same iteration). **T0011's `ripe_when` fires** (stays open, now live for the next unattended loop). **T0017 stays partial** (the look + ledger remain).
- Runbook (`12.phase5-system-spec-runbook.md`): holdout section updated — window ratified (2026-04-01 → fresh freeze); the look's subject = the trial-35 system if adopted, else record 33; the look script `holdout_look.py` prepared (parameters frozen, fresh-pull + QA + two systems + paired-index CIs + ledger), **not run**.
- Iterations-history entry; PR into develop.

## Out of scope

Running the holdout look (human present, next session); any Phase-6 work; T0011's 4h A2 (next unattended loop).
