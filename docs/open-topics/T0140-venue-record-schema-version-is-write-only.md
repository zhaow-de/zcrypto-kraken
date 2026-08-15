---
status: open
ripe_when: a third writer or any reader of the venue record's payload appears — grep `cli/` for `VENUE_SCHEMA_VERSION` and for reads of a `venue-<HH>.json` payload beyond `_seed_venue_state`'s five keys; today the constant has exactly two occurrences, both writes
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

## Suggested next steps

- Decide the cheaper of two shapes, and record which and why: (a) give the venue record a `validate_venue_record` mirroring the journal's, refusing a payload whose key shape disagrees with its declared version; or (b) accept the stamp as provenance-only and say so **at the constant**, so the next reader does not mistake it for an enforced invariant. Option (b) is legitimate and may be right — the point is that the file currently says neither.
- If (a): give the two existing tests something non-self-referential to assert — a stored record with a mismatched shape must be refused. Prove it by constructing the defect, per `agent-ops.md`; a guard is unproven until the defect it names is seen to trip it.
- Re-check this when `00090` lands: if its reconciliation reads the venue payload structurally, option (b) stops being available.
