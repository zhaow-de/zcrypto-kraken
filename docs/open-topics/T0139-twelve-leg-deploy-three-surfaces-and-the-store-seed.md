---
status: open
ripe_when: spec `00094`'s twelve-leg code is on `develop` (`cli/engine/store.py::BASKET` holds twelve symbols there) while the fleet's newest journaled `cycle-<HH>.json` still reads `"schema_version": 1` — both readable, no date
---

# The twelve-leg deploy: three surfaces, one order, and the store seed

## Context — what

The twelve-leg pipeline (spec `00094`, registry record 47, iter-139) has landed green and is **not deployed** — the fleet still runs the ten-leg build. Its deploy is not one converge but **three surfaces in a load-bearing order**, plus two preparation steps that no converge performs and no test can surface: staging the two `/BTC` canonical parquets to the engine host and seeding the store, and back-seeding the widened legs' store history far enough to cover a mixed-schema soak window. This topic holds those preconditions and the by-value verification, so they are checkable from repo state rather than reconstructed from a changelog paragraph at converge time.

## Why this matters

**The order is the whole risk.** The ratified gate is *scored* on the NAS (`gate-export` under the NAS image pin, after every journal pull) and re-verified on ops (`verified-replay` under the ops pin). Old code on either scoring surface meets the first schema-2 record with `unsupported schema_version 2`, classifies the day unclean, and **zeroes the ratified streak with the engine deploy fully correct** — the failure lands on a surface nobody is watching during an engine converge. Converging NAS and ops *ahead* is safe in the other direction, because every existing record is v1 and the widened code loads `{1, 2}`.

The preparation steps fail in the other direction. The engine host mounts no data root, so the two `/BTC` canonical parquets exist nowhere on it until they are staged; and a soak window that straddles the flip reads `store`-bound on every pre-boundary cycle unless the widened legs' history is seeded **back** before the flip, not merely forward from it.

## Findings so far

- **Surface order (spec `00094` D8).** (1) NAS and ops images converge **first**; (2) the engine **last**, under standard discipline — canary via the secondary's capture bake, the inter-cycle window, `fleet-pins.md` recorded before the converge, attended. (3) Stacking with spec `00089`'s still-owed engine payload is an operational call at deploy time under `capture-deploys.md`: one converge may carry both, or two may run.
- **The store seed is not optional, and it is now fail-fast rather than fail-late.** `refresh_store` iterates every `BASKET` leg on both grids, so a store missing `ETH/BTC` or `SOL/BTC` kills the first post-converge cycle. `engine run`'s store-presence guard used to glob `*/EUR/*.parquet` and passed on exactly that store — the node started, looked healthy, and died at the first boundary, where a `failed-cycle-<HH>.json` sidecar makes the boundary unretryable at any time. The guard now tests `BASKET` membership on both grids and names the absent legs, so an unseeded store aborts the start instead. **That converts a lost boundary into a refused start; it does not remove the staging step.**
- **The soak back-seeding has no other home.** A mixed-schema soak window needs the widened legs' store history seeded back before the schema flip, or every pre-boundary cycle in that window reads `store`-bound.
- **Two post-deploy readings are cosmetic but will be triaged as faults** (measured during iter-139, not predicted): at engine start the startup seed reads the last **pre**-deploy v1 venue record and publishes `zcrypto_venue_instruments_loaded 10` against `_expected 12` until the first post-deploy cycle, up to 4 h — no page, since spec `00089` D6 excludes both from alerting. And the `target_weight` gauge's `asset` label re-keys from `"BTC"` to `"BTC/EUR"`, so every series legend on the Engine board changes at the deploy; no Grafana query breaks, `engine-dashboard.json` filtering only on host.

## Suggested next steps

- **Converge the NAS and ops images first**, before any engine change, under their own rules in `capture-deploys.md` (ops needs `--limit zcrypto-ops`; record the running digest in `docs/reference/fleet-pins.md` first). Confirm both surfaces are on the widened code while every journaled record is still v1 — that combination is the safe state to sit in, for as long as needed.
- **Inside the engine converge window, before the first boundary**: stage `ETH/BTC` and `SOL/BTC`'s canonical parquets (both grids, 1440 and 240) to the engine host, then run `zcrypto engine seed`. Verify by starting the node: an incomplete store now aborts the start naming the absent `<symbol>@<interval>` series, so a clean start is itself the seed's confirmation.
- **Seed the widened legs' store history back far enough to cover the soak window that straddles the flip**, before the flip — not forward from it. Confirm no pre-boundary cycle in that window reports `store`-bound.
- **Then converge the engine last**, standard discipline: canary gate via the secondary's capture bake, the 4-hourly inter-cycle gap, `fleet-pins.md` recorded first, attended.
- **Verify by value, not by presence, at the first post-deploy cycle**: the first schema-2 `cycle-<HH>.json` carries **twelve** symbol-keyed targets with `ETH/BTC` and `SOL/BTC` at exactly `0.0`; `orders.jsonl` shows **no phantom rebalance** — a full-book order set there is the cross-schema `_previous_success` failure mode and **rolls back**; `venue-<HH>.json` reads twelve instruments; on the NAS and ops replay surfaces `validation_failures` and `mismatches` are **unchanged** with `replayed_ok` advancing.
- **Read the streak only at the deploy day's 20:30 UTC evaluation** — it counts complete days, so expecting +1 immediately after the first cycle is wrong arithmetic and would false-alarm. At 20:30 it reads pre-deploy + 1, or the deploy rolls back.
- **Close this topic only once the deploy has run and every check above has been read by value**, recording the measured values in the `## Resolution`.
