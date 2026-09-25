---
status: open
ripe_when: 'an evaluation statement: `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day of rung 2> --until <today>` reports a realized maker share on at least 30 euro-denominated fills across rung 2''s first complete ISO weeks — the report''s `fills N` line is the count'
---

# The deployable record's cost basis is re-priced from rung 2's measured blend, as a new registry record

## Context — what

T0090 measured the realized blend at Rung 1's first fills (2026-09-25: two fills, maker 100 %, fee per side 40.0 bps against the assumed 40.0 bps) and the owner ruled the point RECORDED BESIDE the registered basis, not applied to it: the builder default `fee_per_side = 0.0040` + `spread_per_side = 0.0020` stays the ×1.0 headroom basis every registered figure reproduces under, and the go/no-go quote reads both that basis (conditional 0.751) and the measured maker basis (the table's 42.1 bps row, conditional 0.907). This topic is the deferred half of that ruling: the re-pricing of the record's cost basis from a blend measured over a real sample, done as a new registry record.

## Why this matters

Applying the tracking report's proposed rate to the builder default invalidates every registered figure's reproduction, so it is a new trial record with its own validation, never a side effect of reading the proposal. Two maker fills of 20 EUR in one session cannot settle the blend: the deployable at rung 3 sizes through accumulation deltas with a time-boxed taker fallback, and each 10 bps of blended cost moves the conditional baseline by about 0.1, the band's whole width over the maker-to-taker range. Rung 2's daily loop is the first sample that carries a taker share worth pricing.

## Findings so far

- The instrument exists: `zcrypto engine tracking-report` reports the realized maker share with `n`, the per-fill realized cost's min/median/max and the rate it proposes against `CrossfreqSystemConfig.fee_per_side` alone (iter-145, spec `00091`).
- T0090's table already carries the maker-basis row (42.1 bps per side, ×0.7017, conditional 0.907) and the taker-basis row (82.1 bps, conditional 0.520); the measured blend lands between them.
- The venue's fee on a margin open is the spot fee plus a 2 bps margin-opening fee that the fee term does not carry; a re-pricing states which fees the term covers.

## Suggested next steps

- **(autonomous, at the trigger)** Run the tracking report over rung 2's first complete ISO weeks from a pulled copy of the engine journal, read the maker share, the per-fill spread and the proposed rate, and record them in this file beside T0090's measured point.
- **(decision)** Put the proposed rate to the owner as a new registry record: the spec that re-prices `fee_per_side` and `spread_per_side`, its `spec_hash` stored on a new `docs/reference/trial-registry.jsonl` record, the registered figures re-validated at the new basis; T0090's rows are re-quoted against that record, never edited in place.
