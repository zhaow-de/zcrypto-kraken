---
status: open
ripe_when: spec `00092`, whose serial is reserved for rung 3 and not yet written, is created, or an executor path sizes an open order as `target − held`
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
- The formula does not survive a restart on the rung-2 pin, measured live on 2026-10-01 (`docs/reference/drill-log.md`, entry `spot-proof`). `held` is the engine Cache's net position, not a figure re-read from the venue, and on nautilus-trader `2.0.0rc6.dev20260921` under `spot_account_type=MARGIN` a restart restores every held spot lot beside an equal `EXTERNAL` short: the venue record's position and the cycle's `held` read 0 on a lot Kraken holds, then only the trades since that restart. `target − held` would then buy the whole book again. The defect is the adapter's and is fixed upstream (`docs/research/14.phase6-decisions.md`, `[iter-173]`); rung 3's precondition in master plan §12 is a pinned build that carries the fix, shown by two reads on it: `tests/test_cache_restart.py::test_a_restored_spot_lot_is_offset_by_an_external_short_until_sold_and_restarted_and_the_account_keeps_its_coin` fails at its restore assertion, the one whose message reads `no longer books an EXTERNAL short equal to the lot beside the strategy's long`, and one spot lot held across an engine restart is restored live at Kraken's quantity with no `EXTERNAL` line beside it. The case red at another assertion does not meet it — its last three pin the stored account, which other changes turn red while the offset stands.

## Suggested next steps

- **(autonomous)** Implement `delta = target − held` in the executor's order computation, with the accumulation gap journaled per asset per cycle (the gap series is [[T0118]]'s live counterpart and the rung-3 tracking-error input).
- **(autonomous)** Tests: sub-`ordermin` deltas accumulate and place on crossing; a partial fill leaves the remainder in the gap; restart re-derives the gap from venue state bit-identically — with a spot lot held across it, on a pin that carries the restore's fix: `held` after the restart equals Kraken's holding.
- **(autonomous)** Wire the gap series into the order/position/PnL metrics families ([[T0018]] / [[T0095]] inheritance) so drift is observable from Grafana, not only from the journal.
