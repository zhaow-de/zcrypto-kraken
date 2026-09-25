---
status: open
ripe_when: '`uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day of rung 2> --until <the last Sunday>` reports a realized maker share on at least 30 euro-denominated fills — the count the `basis:` line names'
---

# The deployable record's cost basis is re-priced from rung 2's measured blend, as a new registry record

## Context — what

T0090 measured the fee term at Rung 1's first fills (2026-09-25: two maker fills, 40.0 bps per side against the assumed 40.0) and the owner ruled the point RECORDED BESIDE the registered basis, not applied to it. This topic is the deferred half of that ruling: the re-pricing of the record's cost basis from a blend measured over a real sample, done as a new registry record.

## Why this matters

Applying the tracking report's proposed rate to the builder default invalidates every registered figure's reproduction, so it is a new trial record with its own validation. Two maker fills of 20 EUR in one session cannot settle the blend: the deployable at rung 3 sizes through accumulation deltas with a time-boxed taker fallback, and each 10 bps of blended cost moves the conditional baseline by about 0.1 (T0090's table: 0.907 maker, 0.520 taker). Rung 2's daily loop is the first sample that carries a taker share worth pricing.

## Findings so far

- The venue's fee on a margin open is the spot fee plus a 2 bps margin-opening fee that the fee term does not carry; a re-pricing states which fees the term covers.

## Suggested next steps

- **(autonomous, at the trigger)** Run the tracking report over rung 2's first complete ISO weeks from a pulled copy of the engine journal, read the maker share, the per-fill spread and the proposed rate, and record them in this file beside T0090's measured point.
- **(decision)** Put the proposed rate to the owner as a new registry record: the spec that re-prices `fee_per_side` and `spread_per_side`, its `spec_hash` stored on a new `docs/reference/trial-registry.jsonl` record, the registered figures re-validated at the new basis; T0090's rows are re-quoted against that record, never edited in place.
