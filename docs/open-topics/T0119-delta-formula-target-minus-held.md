---
status: open
ripe_when: spec `00092` (rung-3 accumulation) is picked up — `docs/specs/00092-*.md` exists; or earlier if any executor path computes a rebalance delta as `target − held`.
---

# The delta formula: `target − actually held`, not `target − previously journaled intent`

## Context — what

The engine's intended order today is the change against *previously journaled intent*; the executor must compute it against the *actually held position* read from venue account state. The distinction is invisible in shadow (nothing fills, held ≡ 0) and load-bearing the moment orders flow: with real fills, intent-based deltas compound every unfilled or partially-filled order into permanent drift between the journal's book and the venue's. Under `target − held`, an unplaceable delta persists as a growing gap that places itself once it crosses `ordermin` — which is exactly the accumulation mechanism Stage 6b's rung 3 runs on ([[T0116]]), so this fix is the rung's mechanism, not an optimization.

## Why this matters

This is the intent-vs-holdings drift defect: without it, the tiny-live sleeve's sub-`ordermin` deltas (median intended order €0.0116 against €3–25 floors) are silently dropped forever and the live book never converges to the target book at all. It also defines what the reconciliation loop reconciles — journal intent vs venue holdings stops being an error class and becomes the tracked accumulation gap.

## Findings so far

- **Why `00092` is the trigger.** It is the first spec whose executor computes a rebalance order at all, so it is the first moment this formula has a caller; [[T0018]]'s decomposition assigns it there from the sequence's construction, and `00090`'s rung-1 executor sizes from plan-supplied intent quantities instead. Two nearby computations are deliberately NOT the trigger: a reduce-only close is sized from `held` by construction, and `feeders.py`'s `target − held` is a measurement replay whose own docstring names the executor as the intended reader.

- Measured 2026-07-30: 0 of 801 journaled intended orders clear `ordermin` at §12's tiny-live size — under the current formula the sleeve would emit nothing, indefinitely.
- The held-position source exists: Nautilus `Portfolio`/`Cache` carry live account state over the authenticated executions WS already held; startup reconciliation fail-closes the node. Consuming it is [[T0018]]'s fill-ingestion build item; this topic owns the formula and its tests.
- The formula interacts with the restart→reduce-only policy ([[T0018]]): after a restart, held is re-read from the venue, so the accumulation gap survives restarts by construction — a property worth a test, not an assumption.

## Suggested next steps

- **(autonomous)** Implement `delta = target − held` in the executor's order computation, with the accumulation gap journaled per asset per cycle (the gap series is [[T0118]]'s live counterpart and the rung-3 tracking-error input).
- **(autonomous)** Tests: sub-`ordermin` deltas accumulate and place on crossing; a partial fill leaves the remainder in the gap; restart re-derives the gap from venue state bit-identically.
- **(autonomous)** Wire the gap series into the order/position/PnL metrics families ([[T0018]] / [[T0095]] inheritance) so drift is observable from Grafana, not only from the journal.
