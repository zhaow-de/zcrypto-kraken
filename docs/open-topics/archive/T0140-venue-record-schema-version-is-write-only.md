---
status: resolved
---

# The venue record's schema_version is write-only

## Context — what

`cli/engine/venueledger.py` stamps `VENUE_SCHEMA_VERSION` onto every `venue-<HH>.json` the engine writes each cycle, and **nothing anywhere reads it back**. The constant occurs exactly twice in `cli/` — its definition and the write — and the only two consumers of a venue record (`cycle.py`'s `read_venue_record(...).get("status")` and `command.py`'s `_seed_venue_state`, which reads `status`, `cycle_ts`, `state.instruments`, `state.snapshot_at` and `concordance.failures`) never look at it. Its two tests compare the written record against the constant itself, so they pass at any value.

Contrast the *cycle* journal, where `cli/engine/journal.py::validate_record` is schema-aware in both directions and refuses a record whose key shape disagrees with its declared version.

## Why this matters

Spec `00094` bumped this constant 1 → 2 because `VenueState.to_payload()` changed shape four ways at once (instrument keys base → symbol, position keys base → symbol, a new `costmin_quote` field, and `base` values becoming full symbols). The bump was correct and safe *precisely because* nothing validates it — but that is also the problem: a version stamp nothing checks records an intention rather than enforcing an invariant, so the two shapes are indistinguishable to any future reader that starts caring.

The gap is not hypothetical, and it has already cost something. A fixture in `tests/test_engine_metrics.py` described itself as matching `write_venue_record`'s schema while writing `schema_version: 1`; it drifted the moment the constant moved to 2, and **no test objected** — there was nothing to object with. It was corrected by hand during `00094`'s closeout, which is the point: the only thing that caught it was a reviewer reading the file. That is the same failure shape the cycle journal's validator exists to prevent.

Today the blast radius is small: both live readers are key-agnostic, so a shape mismatch degrades a dashboard rather than breaking a cycle. It grows the moment anything reads the payload structurally — which `00090`'s reconciliation work plausibly does, since the venue record is where the `held` read and the realized-state evidence land.

## Findings so far

- Measured during spec `00094`'s Task 4 review and re-confirmed in its whole-branch review: the constant is write-only, and its two tests are self-referential (`tests/test_engine_venueledger.py` asserts `doc["schema_version"] == VENUE_SCHEMA_VERSION`, which holds for any value).
- The startup seed publishes a real, visible consequence of a shape change even without a validator: reading a pre-deploy base-keyed record yields `zcrypto_venue_instruments_loaded 10 / _expected 12` until the first post-deploy cycle. Measured, not predicted. It does not page (spec `00089` D6 excludes both gauges from alerting) but it reads as a fault to whoever looks.
- `cli/engine/journal.py` is the worked example of the alternative — schema-aware validation that refuses wrong keying rather than silently normalizing it — including the `_LOADABLE_SCHEMA_VERSIONS` pattern for keeping older records readable.

## Resolution

**Resolved 2026-08-18 (iter-140, spec/plan `00090` D9) — ruled option (a), and the third suggested step is what forced it.** `00090`'s executor seeds `zcrypto_exec_position{symbol}` at startup from the newest `venue-<HH>.json`'s `state.positions`, and its `reduce_only` classification reads `state.balances_free` to refute a spot-disposal quantity — both structural reads of the payload. That is exactly the condition this topic named as the one that removes option (b), so provenance-only labelling stopped being available and the ruling was forced by the consumer rather than chosen on cost.

`cli/engine/venueledger.py::validate_venue_record` mirrors `cli/engine/journal.py::validate_record`: schema-aware in both directions, refusing a record whose key shape disagrees with its declared `schema_version`, with `_LOADABLE_VENUE_SCHEMA_VERSIONS = {1, 2}` keeping older records readable on the journal's own pattern. v1 loadability is deliberate and narrow — no v1 `venue-<HH>.json` ever existed on the engine host (`00089` first deployed 2026-08-16 with the schema already at 2), so it covers workstation-side journals only.

The two self-referential tests are gone, replaced with refusal tests that can actually fail: a stored schema-2 record carrying base keys is **refused, not normalized**; a v1 record validates in its own shape (and is refused the moment a v2-only field is added to it); an unknown schema is refused. The *wiring* is proven separately and deliberately: every other venue-record fixture in `tests/test_engine_metrics.py` now writes schema-valid records, so a single v1-shaped body stamped `schema_version: 2` is what makes deleting either `validate_venue_record(doc)` call — in `_seed_venue_state` or in `_seed_exec_positions`, both of which validate **before** reading `status` — turn the suite red instead of leaving it green.

**The exec ledger got the identical treatment in the same branch, for the identical reason** (`00090` D5): `validate_exec_record` with `_LOADABLE_EXEC_SCHEMA_VERSIONS = {1, 2}`, `EXEC_SCHEMA_VERSION` bumped 1 → 2 for the write-ahead `submitted` rows, routed through `_store` so every mutator refuses a bad record — including a typo'd row state (`"acepted"`), which previously persisted cleanly and then dropped silently out of the re-attach set with nothing raising. An unvalidated stamp on a forensic record beside real money is this same trap one artifact over.

Commits: `d1099f98` + `479c49d1` (the exec ledger's schema 2 and its validator), `4004c764` + `f5237be3` (the venue validator, the startup position seed, and the erasable-proof pin). **The code has landed and is green; nothing is deployed** — the first record either validator will read on the fleet arrives at the deploy converge's next boundary.
