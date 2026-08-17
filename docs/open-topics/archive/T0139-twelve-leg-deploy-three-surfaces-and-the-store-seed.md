---
status: resolved
---

# The twelve-leg deploy: three surfaces, one order, and the store seed

## Context — what

The twelve-leg pipeline (spec `00094`, registry record 47, iter-139) is **DEPLOYED** — all four surfaces converged 2026-08-15/16; the fleet no longer runs the ten-leg build. What remains is reading the first schema-2 cycle by value (`## Resolution

**The first schema-2 cycle verified clean 2026-08-16 20:01:43Z, and the deploy is complete.** Every by-value check this topic named was read rather than assumed:

- `cycle-20.json` — `schema_version: 2`, completed inside `[20:00, 20:30]`, **twelve symbol-keyed targets**, `ETH/BTC` and `SOL/BTC` at **exactly `0.0`**. Zero `failed-cycle-*.json` since the converge.
- **No phantom rebalance — the check this topic called its rollback trigger.** The v1 predecessor (`cycle-16.json`) held base-keyed `{ADA: 0.002101, AVAX: 0.003461, LINK: 0.01263}`; the v2 record holds the same three positions symbol-keyed with sub-threshold drift, and `orders.jsonl` carries **one row for 20:00 which is a note, not an order**, recording the predecessor it read. Zero order rows. A failed `_previous_success` normalization would have read those three as new-from-flat and emitted three full-size buys.
- `venue-20.json` — the FIRST venue record ever written, 00089 having never deployed: schema 2, `status: ok`, **12 instruments, 12 positions, 0 concordance failures**. `zcrypto_venue_instruments_loaded` moved **0 → 12** to match `expected`; the 0 at converge was the startup seed finding no prior record, not a fault.
- **The gate advanced THROUGH the schema boundary**: `status 1`, `mismatch_total 0`, `streak_days` **35 → 37**. 2026-08-16 was a genuinely mixed-schema day — cycles 00/04/08/12/16 at schema 1, cycle 20 at schema 2 — and it scored clean. That is the straddle case spec `00094` D3 exists for, and the reason each schema must replay and compare in its NATIVE key space: normalizing v1 replay output would have made all five of that day's earlier records a structural mismatch and zeroed the ratified streak.
- Steady state confirmed at the next boundary — `cycle-00.json` 2026-08-17 00:01:54Z, same twelve-leg shape.

The three instructions this topic got wrong, and the fourth thing the deploy surfaced, are recorded under `## Done so far`; the two durable imperatives they produced now live in `.claude/rules/capture-deploys.md` § Engine converges, which is the surface consulted at converge time.
