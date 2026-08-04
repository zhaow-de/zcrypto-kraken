---
status: open
ripe_when: the next iteration that touches `cli/engine/command.py`'s `_CycleGauges` — both fixes are inside that one class, so they ride along at near-zero marginal cost; neither is worth its own converge of the live trade host
---

# Two engine gauge-lifecycle defects: a stale target weight and a false-zero cycle duration

## Context — what

Spec `00084`'s dashboard design read `_CycleGauges` closely enough to find two lifecycle defects in the engine's `/metrics` families. Both are invisible today because nothing charts those families; the `engine` board makes both visible, and its panel descriptions carry the caveats. **A description is a workaround, not a fix.**

- **A target weight persists at its last value until the process restarts.** The cycle gauges call `.labels(asset=…).set(…)` on every cycle and never `.clear()` or `.remove()`. An asset that drops out of the target set therefore keeps publishing its last weight indefinitely: the series neither falls to zero nor goes absent. `zcrypto_engine_target_weight{asset}` and, through it, any book-level gross or net computed from the weight set, over-report for the life of the process.
- **`zcrypto_engine_cycle_duration_seconds` reads a false zero after every restart.** Unlike `cycle_completed_at` (seeded at startup from the newest journal artifact) and `cycle_success` (deliberately left unregistered until an outcome is known), `cycle_duration` is registered eagerly in `_CycleGauges.__init__` and never seeded. It sits at the `prometheus_client` gauge default until the first cycle completes — a literal false value rather than an absence — and renders as a healthy green data point meaning "the last cycle took 0 seconds", for up to a full 4-hourly cycle gap.

## Why this matters

The two defects sit on opposite sides of the same line, and the engine already gets that line right elsewhere — which is what makes these bugs rather than choices.

`cycle_success` is the house pattern done correctly: the code refuses to publish a `0` it cannot justify, leaving the series unregistered so absence reads as absence. `cycle_duration` publishes a `0` it cannot justify. A monitoring system whose healthy-looking value is indistinguishable from "no information yet" is the exact failure class the surrounding work exists to remove — and it is worse than a missing panel, because a missing panel is obvious and a green false zero is not.

The stale weight is the more consequential of the two once the executor lands. A target-weight series that never retires means the intended book, as read from `/metrics`, drifts permanently away from the intended book as journalled — and the journal is the source of truth. Any future reconciliation, tracking-error report, or drift band computed from the metric rather than the journal inherits that drift silently.

## Findings so far

- Verified in source (2026-08-04, spec `00084` design): `cli/engine/command.py`, `_CycleGauges.__init__` registers `cycle_duration` eagerly alongside `cycle_completed_at`; the only write is a `.set(duration_seconds)` after a cycle completes. No startup seeding path exists for it, though one exists and is used for `cycle_completed_at`.
- Verified in source: no `.clear()` or `.remove()` call exists anywhere on the labelled cycle gauges.
- Neither defect can false-fire an existing alert today: no rule reads either family. Spec `00084` D11 adds `Engine · cycles have stopped` and `Engine · the last cycle failed`, both of which read other families, so the defects stay presentation-only until fixed.
- The workaround shipped with spec `00084`: both caveats are written into the `engine` board's panel descriptions.

## Suggested next steps

- **(autonomous)** Seed `cycle_duration` at startup the way `cycle_completed_at` is seeded — the newest journal artifact carries the duration of the cycle it recorded — **or** make it lazily registered like `cycle_success`, so absence stays absence. Prefer whichever matches what the journal artifact actually stores; check before choosing, since seeding is only possible if the duration is persisted there.
- **(autonomous)** Retire target-weight series for assets absent from the current cycle: track the label set written last cycle and `.remove()` the difference, so a dropped asset's series goes absent rather than freezing. Removing rather than zeroing is the right call — a zero weight and a not-in-the-book asset are different states, and the executor will need to tell them apart.
- **(autonomous, same change)** Whichever lands, drop the corresponding caveat sentence from the `engine` board's panel description in the same commit — a stale caveat is its own drift.
- **(test)** Both are straightforwardly TDD-able against a fake registry with no live engine: assert a dropped asset's series is gone after the next cycle, and assert `cycle_duration` is either absent or journal-seeded before the first cycle of a fresh process.
