---
status: resolved
---

# The delta formula: `target − actually held`, not `target − previously journaled intent`

## Context — what

The engine's intended order today is the change against *previously journaled intent*; the executor must compute it against the *actually held position* read from venue account state. The distinction is invisible in shadow (nothing fills, held ≡ 0) and load-bearing the moment orders flow: with real fills, intent-based deltas compound every unfilled or partially-filled order into permanent drift between the journal's book and the venue's. Under `target − held`, an unplaceable delta persists as a growing gap that places itself once it crosses `ordermin` — which is exactly the accumulation mechanism Stage 6b's rung 3 runs on ([[T0116]]), so this fix is the rung's mechanism, not an optimization.

## Why this matters

This is the intent-vs-holdings drift defect: without it, the tiny-live sleeve's sub-`ordermin` deltas (median intended order €0.0116 against €3–25 floors) are silently dropped forever and the live book never converges to the target book at all. It also defines what the reconciliation loop reconciles — journal intent vs venue holdings stops being an error class and becomes the tracked accumulation gap.

## Findings so far

- **Why `00092` is the trigger.** It is the first spec whose executor computes a rebalance order at all, so it is the first moment this formula has a caller; [[T0018]]'s decomposition assigns it there from the sequence's construction, and `00090`'s rung-1 executor sizes from plan-supplied intent quantities instead. Two nearby computations are deliberately NOT the trigger: a reduce-only close is sized from `held` by construction, and `feeders.py`'s `target − held` is a measurement replay whose own docstring names the executor as the intended reader.

- Measured 2026-07-30: 0 of 801 journaled intended orders clear `ordermin` at §12's tiny-live size — under the current formula the sleeve would emit nothing, indefinitely.
- The held-position source is consumed: spec `00089` landed the `held` read (iter-138), and the executor sizes a closer from the Cache's live position; startup reconciliation fail-closes the node. This topic owns the open-order formula and its tests.
- The formula does not survive a restart on the rung-2 pin (`docs/reference/drill-log.md`, entry `spot-proof`): `held` is the engine Cache's net position, not a figure re-read from the venue, and on nautilus-trader `2.0.0rc6.dev20260921` under `spot_account_type=MARGIN` a restart restores every held spot lot beside an equal `EXTERNAL` short, so `held` reads 0 on a lot Kraken holds and `target − held` would buy the whole book again. The fix is upstream's; rung 3's precondition in master plan §12 is a pinned build that carries it, and says how it is read.

## Resolution

- **The formula is spec `00092` D2's, built by its plan's Task 11 (iter-174, PR #666)**: `_draft_cycle_plan` in `cli/engine/executor.py` drafts each boundary's one plan from `target_eur − held_qty × close` — `held` the venue's own read (`read_venue_book`, Task 2), the close the cycle record's journaled `closes` — through the helper's table at the record's NAV, D4's carry with its two rules from the executor's records, the plan cap and the 3h30 submission window; the engine's Cache net is the record's cross-check column, never the input.
- **The gap series per asset per cycle is `accum-<HH>.json`** (`cli/engine/accumledger.py`, Task 3): one row per model leg per boundary — `target_eur`, `held_qty`, `cache_net`, `delta_eur`, `outcome`, `reason` — outside the Stage-6a gate's globs. **Its gauge is `zcrypto_exec_gap_eur{symbol}`**, ten series admitted end to end (Task 4): each leg's whole delta at the draft, `delta_eur − filled × close` at its intent's terminal, on the Engine board's accumulation row.
- **The tests are Task 11's**, in `tests/test_engine_executor.py`: rung 2's entry-day fixtures (synthesized, every figure invented) drafting the ten legs at NAV 1,000, the loop's rows at EUR 720 equal to the helper's decision rows, the cross-check drafting from the venue's figure, the open-row carry, the window's close, the dedup wall refusing a re-drafted boundary after a restart, the sleeve's cash and the plan cap, and the gap gauge at the draft and at the terminal — each guard proven by `infra/scripts/mutate-probe.sh` (commit `24ddd4c45`).
- **Left with their owners, not here**: the restart with a lot held on a pin carrying upstream #5181's fix is `00092`'s rollout gate R0 (1), a live read (master plan §12); slots S2 and S3 — the counts and intent times that confirm D3's window and box and D4's carry, or move them — are rung 2's exit report, [[T0018]]'s row, read at R0 (2).
