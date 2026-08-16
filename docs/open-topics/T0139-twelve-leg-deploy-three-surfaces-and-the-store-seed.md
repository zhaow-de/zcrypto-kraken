---
status: partial
ripe_when: the engine's first schema-2 record exists — `cycle-<HH>.json` on the engine host reading `"schema_version": 2` — and its by-value checks are unread
---

# The twelve-leg deploy: three surfaces, one order, and the store seed

## Context — what

The twelve-leg pipeline (spec `00094`, registry record 47, iter-139) is **DEPLOYED** — all four surfaces converged 2026-08-15/16; the fleet no longer runs the ten-leg build. What remains is reading the first schema-2 cycle by value (`## Suggested next steps`). This topic exists because the deploy was not one converge but three surfaces in a load-bearing order, and because it turned out to owe two steps no converge performs; the ordering and those steps are recorded below so the next basket-widening does not rediscover them.

## Why this matters

**The order is the whole risk.** The ratified gate is *scored* on the NAS (`gate-export` under the NAS image pin, after every journal pull) and re-verified on ops (`verified-replay` under the ops pin). Old code on either scoring surface meets the first schema-2 record with `unsupported schema_version 2`, classifies the day unclean, and **zeroes the ratified streak with the engine deploy fully correct** — the failure lands on a surface nobody is watching during an engine converge. Converging NAS and ops *ahead* is safe in the other direction, because every existing record is v1 and the widened code loads `{1, 2}`.

The preparation steps fail in the other direction. The engine host mounts no data root, so the two `/BTC` canonical parquets exist nowhere on it until they are staged; and a soak window that straddles the flip reads `store`-bound on every pre-boundary cycle unless the widened legs' history is seeded **back** before the flip, not merely forward from it.

## Findings so far

- **Surface order (spec `00094` D8).** (1) NAS and ops images converge **first**; (2) the engine **last**, under standard discipline — canary via the secondary's capture bake, the inter-cycle window, `fleet-pins.md` recorded before the converge, attended. (3) Stacking with spec `00089`'s still-owed engine payload is an operational call at deploy time under `capture-deploys.md`: one converge may carry both, or two may run.
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

## Suggested next steps

- Read the first schema-2 cycle **by value**, not by presence: `schema_version` 2; `final_targets` twelve symbol-keyed entries with `ETH/BTC` and `SOL/BTC` at **exactly** `0.0`; `venue-<HH>.json` twelve instruments and `zcrypto_venue_instruments_loaded` moving 0 → 12; `completed_at` inside `[B, B+30]`; no `failed-cycle-<HH>.json` (a sidecar makes that boundary unretryable at any time).
- **`orders.jsonl` must show no phantom rebalance — this is the rollback trigger.** The predecessor record is v1/base-keyed; if `_previous_success`'s normalization failed, every `.get(symbol, 0.0)` misses, the engine reads the whole book as flat and writes a from-flat rebalance, silently, because the gate never reads orders. Order rows only for genuine deltas. A full-book set rolls back to `6c5151d9f3af`.
- On the **NAS and ops replay surfaces**, `validation_failures` and `mismatches` must be UNCHANGED while `replayed_ok` advances — the engine writing v2 is only half the story; the two surfaces that SCORE the gate have to keep accepting records across the schema boundary, which is the whole reason they converged first.
- Read the gate streak at the deploy day's **20:30 UTC** evaluation, not after the first cycle — it counts COMPLETE days, so expecting +1 immediately is wrong arithmetic. Pre-deploy baseline: status 1, streak 35, mismatch 0.
