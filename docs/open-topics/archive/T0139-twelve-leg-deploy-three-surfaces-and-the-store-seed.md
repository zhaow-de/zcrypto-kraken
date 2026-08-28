---
status: resolved
---

# The twelve-leg deploy: three surfaces, one order, and the store seed

## Context — what

The twelve-leg pipeline (spec `00094`, registry record 47, iter-139) was **DEPLOYED 2026-08-15/16** across all four surfaces and verified by value at the first schema-2 cycle (`## Resolution`). This topic exists because the deploy was not one converge but three surfaces in a load-bearing order, and because it turned out to owe two steps no converge performs; the ordering and those steps are recorded below so the next basket-widening does not rediscover them.

## Why this matters

**The order is the whole risk.** The ratified gate is *scored* on the NAS (`gate-export` under the NAS image pin, after every journal pull) and re-verified on ops (`verified-replay` under the ops pin). Old code on either scoring surface meets the first schema-2 record with `unsupported schema_version 2`, classifies the day unclean, and **zeroes the ratified streak with the engine deploy fully correct** — the failure lands on a surface nobody is watching during an engine converge. Converging NAS and ops *ahead* is safe in the other direction, because every existing record is v1 and the widened code loads `{1, 2}`.

The preparation steps fail in the other direction. The engine host mounts no data root, so the two `/BTC` canonical parquets exist nowhere on it until they are staged; and a soak window that straddles the flip reads `store`-bound on every pre-boundary cycle unless the widened legs' history is seeded **back** before the flip, not merely forward from it.

## Findings so far

- **Surface order (spec `00094` D8).** (1) NAS and ops images converge **first**; (2) the engine **last**, under standard discipline — canary via the secondary's capture bake, the inter-cycle window, `fleet-pins.md` recorded before the converge, attended. (3) Stacking with spec `00089`'s still-owed engine payload is an operational call at deploy time under `fleet-deploys.md`: one converge may carry both, or two may run.
- **The store seed is not optional, and it is now fail-fast rather than fail-late.** `refresh_store` iterates every `BASKET` leg on both grids, so a store missing `ETH/BTC` or `SOL/BTC` kills the first post-converge cycle. `engine run`'s store-presence guard used to glob `*/EUR/*.parquet` and passed on exactly that store — the node started, looked healthy, and died at the first boundary, where a `failed-cycle-<HH>.json` sidecar makes the boundary unretryable at any time. The guard now tests `BASKET` membership on both grids and names the absent legs, so an unseeded store aborts the start instead. **That converts a lost boundary into a refused start; it does not remove the staging step.**
- **The soak back-seeding has no other home.** A mixed-schema soak window needs the widened legs' store history seeded back before the schema flip, or every pre-boundary cycle in that window reads `store`-bound.
- **Two post-deploy readings are cosmetic but will be triaged as faults** (measured during iter-139, not predicted): at engine start the startup seed reads the last **pre**-deploy v1 venue record and publishes `zcrypto_venue_instruments_loaded 10` against `_expected 12` until the first post-deploy cycle, up to 4 h — no page, since spec `00089` D6 excludes both from alerting. And the `target_weight` gauge's `asset` label re-keys from `"BTC"` to `"BTC/EUR"`, so every series legend on the Engine board changes at the deploy; no Grafana query breaks, `engine-dashboard.json` filtering only on host.

## Done so far

**All four surfaces converged 2026-08-15/16** (PR #297 payload, digest `419feafc304f`; NAS `-compat` `5f890c26237a` via PR #298). Order held: NAS → ops → secondary capture → primary Alloy → engine. `fleet-pins.md` carries each row's evidence.

**Three things this topic told the deployer that turned out to be WRONG, corrected here rather than left to mislead:**

- **`zcrypto engine seed` cannot be run on the engine host.** It is workstation-only — the image carries no canonical dataset. The engine store is *delivered by Ansible* from the workstation's `data/engine-store/`.
- **That delivery would not have happened.** The task is `only when absent`, guarded on `store/BTC` — which exists — so a normal converge SKIPS it, delivers nothing, and the new start guard then refuses to start the engine. The `/BTC` legs had to be staged by hand.
- **The canonical cannot seed the 4h grid.** `data/ohlc-full` is frozen at 2026-03-31 while Kraken's REST 4h window reaches back only to 2026-04-17 — a ~17-day hole the quarterly OHLCVT dump would fill, which [[T0065]] records as unpublished. The daily grid was fine (REST reaches 2024-08-25). The `/BTC` 4h legs were therefore seeded **REST-only, 720 bars from 2026-04-17**, on the owner's ruling. Harmless: `select_model_inputs` contracts to the ten `/EUR` legs, so no `/BTC` datum reaches the model; the legs exist so the store is complete and `00090` inherits prices. All 24 store files verified readable as uid 997:988, the engine's own identity.

**The soak back-seeding was DISCHARGED by the same staging.** Seeding the widened legs on the workstation and copying them in gave both `/BTC` legs history reaching back past the flip — daily to 2016/2020 from canonical, 4h to 2026-04-17 from REST — so a soak window straddling the boundary has store coverage on both sides and no pre-boundary cycle reads `store`-bound for want of a widened leg. Nothing further is owed on it.

**A fourth finding the deploy surfaced, unrelated to the store:** spec `00089`'s `zcrypto_venue_*` Alloy admission had never reached EITHER capture host since 2026-08-13. The keep-regex is a `keep` action, so those four gauges were being dropped at the Alloy layer while 00089's alert rules evaluated against series that never arrived. Nothing surfaced it — a drift assert refusing a converge did. Shipped config-only to both hosts; verified end to end (`zcrypto_venue_instruments_expected` = 12 in Grafana Cloud, where the same query returned `(no series)` an hour earlier).

## Resolution

**Verified by value at the first schema-2 cycle, 2026-08-16 20:01:43Z.** Every check this topic named was read:

- `cycle-20.json` — `schema_version: 2`, completed inside `[20:00, 20:30]`, **twelve symbol-keyed targets**, `ETH/BTC` and `SOL/BTC` at **exactly `0.0`**. Zero `failed-cycle-*.json` since the converge. Steady state confirmed at the next boundary (`cycle-00.json`, 2026-08-17 00:01:54Z, same shape).
- **No phantom rebalance — this topic's stated rollback trigger.** The v1 predecessor `cycle-16.json` held base-keyed `{ADA: 0.002101, AVAX: 0.003461, LINK: 0.01263}`; the v2 record holds the same three positions symbol-keyed with sub-threshold drift, and `orders.jsonl` carries **one row for 20:00 which is a note naming the predecessor it read**, not an order. Zero order rows. A failed `_previous_success` normalization would have read those three as new-from-flat and emitted three full-size buys against real money.
- `venue-20.json` — the FIRST venue record ever written, `00089` having never deployed: schema 2, `status: ok`, **12 instruments, 12 positions, 0 concordance failures**. `zcrypto_venue_instruments_loaded` moved **0 → 12** to match `expected`; the 0 read at converge was the startup seed finding no prior record, not a fault.
- **The gate advanced THROUGH the schema boundary**: `status 1`, `mismatch_total 0`, `streak_days` **35 → 37**. 2026-08-16 was a genuinely mixed-schema day — cycles 00/04/08/12/16 at schema 1, cycle 20 at schema 2 — and it scored clean. That is spec `00094` D3's straddle case, and the reason each schema must replay and compare in its NATIVE key space: normalizing v1 replay output would have made all five of that day's earlier records a structural mismatch and zeroed the ratified streak the whole deploy order exists to protect.
- **Replay surface**: `zcrypto_gate_cache_replayed` 11 with `mismatch_total` 0 — the NAS side is replaying across the boundary and accepting both schemas. The ops `verified-replay` timer was **not** separately read; the gate's own status/mismatch/streak is what was measured, and it is the surface that scores.

The three instructions this topic got wrong, and the fourth thing the deploy surfaced, stay under `## Done so far` as the record of what a basket widening actually costs. The two durable imperatives they produced live in `.claude/rules/fleet-deploys.md` § Engine converges — the surface consulted at converge time — so nothing is stranded in this archive.
