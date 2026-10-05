---
status: partial
ripe_when: 'plan `00092`''s Task 11 is merged into `develop` — the boundary drafts `target − held` from the venue''s own read; check: `git grep -c _draft_cycle_plan develop -- cli/engine/executor.py` prints a line'
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

## Done so far

- **The formula is settled by spec `00092` D2** (commit `f5e818e97`, the owner's ruling of 2026-10-05 folded in `247f641c8`): `held` is the venue's own read at the boundary — `read_venue_book`, `read_venue_holdings` extended by the EUR balance's `total` and `free`, three private calls on the executor's bare client — and the engine's Cache net is the cross-check, logged as a WARNING per leg where it differs by more than a lot step, never the input; the delta is `target_eur − held_qty × close` at the cycle record's journaled `closes`, a buy a `notional_eur` opening intent and a sell a `qty` closing intent; a hand act on a basket coin moves `held` by construction and is a finding for the weekly reconciliation, not a stop. The three rejected forms are named there: `target − previously journaled intent`, `target − Cache net` (0 on a lot held through a restart on the rung-2 pin), `target − the venue record's balances` (the stored account a restart never drops a coin from).
- **The accumulation and the gap series are D4 and D14**: the carry is rung 2's `[iter-173]` policy verbatim with the box's measured floors, plus two rules from the executor's records (no re-placement inside a cycle; a leg with an open ledger row carried until the venue has answered it); the gap per asset per cycle is `accum-<HH>.json`'s leg row (`target_eur`, `held_qty`, `cache_net`, `delta_eur`, `outcome`, `reason`) and its gauge `zcrypto_exec_gap_eur{symbol}`, ten series, on the Engine board's accumulation row.
- **Rung 2 runs the formula by hand since 2026-10-05**: `zcrypto engine draft-plan` drafts each plan as the target minus Kraken's own exported holdings (`engine-rung-2-box`), and day 1 placed nine legs with nine rows `carried` under the venue's floors — the policy is rung 3's accumulation done by hand (spec `00092`'s Problem).
- **The restart finding above stands**: rung 3's precondition (master plan §12) is the pin carrying upstream #5181's fix, read by `00092`'s rollout gate R0 (1) — the restore assertion red and one live restart with a lot held — and not by a test of this topic's.

## Suggested next steps

- **(autonomous — plan `00092`)** The code: Task 2 (`read_venue_book`, the executor keeping the newest book it read), Task 11 (`_draft_cycle_plan` — the boundary's draft from the book, the table, the carry, the record, the gap gauge's value), Task 3 (`accum-<HH>.json`, invisible to the Stage-6a gate) and Task 4 (`zcrypto_exec_gap_eur` admitted end to end). Its tests are Task 11's — rung 2's entry-day fixtures drafting the ten legs at NAV 1,000, the dedup wall refusing a re-drafted boundary after a restart, the window-closed carry — and the restart with a lot held on the fixed pin is rollout R0's live read, never a test here.
- **(measurement — rung 2's box)** Slots S2 and S3 of spec `00092`, read in the exit report: per cycle the placed, carried and queued counts and each intent's time from start to terminal; the time-box crossings and the `unfilled`, `partial`, `ambiguous` and `revoked` counts — they confirm D3's window and box and D4's carry, or move them.
