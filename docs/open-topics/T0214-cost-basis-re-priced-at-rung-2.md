---
status: partial
ripe_when: '`uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day of rung 2> --until <the last Sunday>` reports a realized maker share on at least 30 euro-denominated fills — the count the `basis:` line names'
---

# The deployable record's cost basis is re-priced from rung 2's measured blend, as a new registry record

## Context — what

T0090 measured the fee term at Rung 1's first fills (2026-09-25: two maker fills, 40.0 bps per side against the assumed 40.0) and the owner ruled the point RECORDED BESIDE the registered basis, not applied to it. This topic is the deferred half of that ruling: the re-pricing of the record's cost basis from a blend measured over a real sample, done as a new registry record.

## Why this matters

Applying the tracking report's proposed rate to the builder default invalidates every registered figure's reproduction, so it is a new trial record with its own validation. Two maker fills of 20 EUR in one session cannot settle the blend: the deployable at rung 3 sizes through accumulation deltas with a time-boxed taker fallback, and each 10 bps of blended cost moves the conditional baseline by about 0.1 (T0090's table: 0.907 maker, 0.520 taker). Rung 2's daily loop is the first sample that carries a taker share worth pricing.

## Findings so far

- The venue's fee on a margin open is the spot fee plus a 2 bps margin-opening fee that the fee term does not carry; a re-pricing states which fees the term covers.
- The engine journal rounds a fill's fee to the cent — up to ±2.5 bps on a 20 EUR leg — so the re-pricing reads the fee from the venue's rows, or from fills large enough that the cent does not move the figure.
- A margin open's fee can be charged in EURC: the venue converts euro to EURC at par beside the row (a `collateralconversion` pair) and charges the fee in EURC, seen on the 2026-09-24 hand open and the 2026-09-25 BTC/EUR open. The tracking report's `fees on the matched rows` figure counts such a fee at par under `_EURO_FEE_ASSETS` in `cli/engine/tracking.py` (spec `00119` D8), and the journal reports that fill's fee in euro, so the re-pricing reads one euro figure; a rollover charged in EURC has not been seen, and the same set would count it.
- **Reading 9 (iter-199, spec `00153`): the engine's blend read from its own ladder replayed at the cycle boundaries over the capture**, 2026-08-01 → 2026-10-25, the ten EUR legs weighted equally: €100 0.005844 a side (95 % interval 0.005734 to 0.005945) and €1,000 0.006572 (0.006465 to 0.006672), against the registered 0.006 — beside rung 2's measured point to 2026-10-25, maker 96.3 % / taker 3.7 % of the priceable book over 25 fills, where the replay's maker share runs 0.097 to 0.907. A first leg posted at `B + 120 s` and both sides at every boundary, the IOC attempts past the first touch and a partly met order's maker part unmodelled, so the reading cannot sign its net bias (the `[iter-199]` entry in `docs/research/14.phase6-decisions.md`).

## Done so far

- The capture's reading of the blend, item 2 of the owner's word of 2026-10-29: reading 9 on `docs/reference/reading-ledger.jsonl` over `l2-ladder-20261030T020429Z` (iter-199, spec/plan `00153`).

## Suggested next steps

- **(autonomous, at the trigger)** Run the tracking report over rung 2's first complete ISO weeks from a pulled copy of the engine journal, read the maker share, the per-fill spread and the proposed rate, and record them in this file beside T0090's measured point.
- **(decision)** Put the proposed rate to the owner as a new registry record: the spec that re-prices `fee_per_side` and `spread_per_side`, its `spec_hash` stored on a new `docs/reference/trial-registry.jsonl` record, the registered figures re-validated at the new basis; T0090's rows are re-quoted against that record, never edited in place. Beside it, reading 9's blend per size — €100 0.005844 and €1,000 0.006572 a side — as a candidate re-pricing ahead of the trigger, the owner's to weigh.
