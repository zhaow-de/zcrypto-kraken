---
status: resolved
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
- **Reading 9 (iter-199, spec `00153`): the engine's blend read from its own ladder replayed at the cycle boundaries over the capture**, 2026-08-01 → 2026-10-25, the ten EUR legs weighted equally: €100 0.005844 a side (95 % interval 0.005734 to 0.005945) and €1,000 0.006572 (0.006465 to 0.006672), against the registered 0.006 — beside rung 2's measured point to 2026-10-25, maker 96.3 % / taker 3.7 % of the priceable book over 25 fills, where the replay's maker share on those legs runs 0.242 to 0.907. Its departures from the engine leave the sign of its net bias unread (the `[iter-199]` entry in `docs/research/14.phase6-decisions.md`).
- **The tracking report over rung 2's box, read 2026-11-02** (spec `00154` D3's candidate (a), iter-200), on `zcrypto-ops` over the NAS's copy of the box's journal and the owner's ledger export: `uv run zcrypto engine tracking-report --journal-dir /mnt/zhao-crypto/engine-journal --since 2026-10-05 --until 2026-11-01 --gate-from 2026-W45 --ledger-export <the box's export>.csv --minimums data/snapshots/kraken-refdata-20261001T101146Z.json`. Its cost block: 35 fills, all 35 priced; maker 96.9 % / taker 3.1 % of the priceable book; `fee per side: realized 41.4 bps` against the assumed 40.0, beside T0090's 40.0 bps over Rung 1's two maker fills; `basis: 35 euro-denominated fill(s) over 331.14 EUR of notional`. Its reconciliation: `ok`, 69 trade or margin rows matched a journaled fill — rows, one per asset leg of a trade, never fills — `fees on the matched rows 1.3655 EUR` and `rollover fees 0.0000 EUR`. A join of the journal's fills and the export's rows (plan `00154` Task 2 Step 2) reads 35 priced fills under 35 trade ids, none repeated, exactly the export's trade and margin `refid`s: once per trade id, 1.37 EUR of journal fees over 331.1377989928991 EUR, maker 0.9692887067185342 / taker 0.03071129328146582. The venue's fee term is 1.3655 / 331.1377989928991 = 0.004123660917457755 a side, the journal's cent-rounded 0.004137250426156811 beside it; with the registered 0.0020 spread the basis reads 0.006123660917457755, ×1.0206 of 0.006. This topic's trigger, 30 euro fills, is met on both counts: 35 priced fills once per trade id and the `basis:` line's 35.
- The report's `per fill: min 0.0 bps, median 40.1 bps, max 86.8 bps` is the fee's dispersion — each priced fill's journal fee, rounded to the cent, over its notional — and no spread: the report reads no spread, and the `plus 20.0 bps of spread, priced separately` beside its fee line is the assumed term, not a measurement.

## Resolution

- The capture's reading of the blend, item 2 of the owner's word of 2026-10-29: reading 9 on `docs/reference/reading-ledger.jsonl` over `l2-ladder-20261030T020429Z` (iter-199, spec/plan `00153`).
- The tracking report's read over rung 2's box, 2026-11-02, written into spec `00154` D3's candidate (a) (iter-200, `bfa347d96`).
- §12's cost-basis term, closed by the (a) pick: the owner's word of 2026-11-02, asked "Which rate should iter-200 re-price the deployable strategy at? (a) is what the box's 35 trades actually paid: total 0.006124, which is 1.021 × the current 0.006. The (b) rows come from the backtest replay of costs: (b1) 0.005844, (b2) 0.006572, (b3) 0.005379, (b4) 0.006047. You can also give your own fee and spread under Other." — answered, verbatim, "(a) the box's rate (Recommended)". The pick is rung 2's measured blend, the box's own fills, so it closes §12's term (b) (spec `00154` D10's first member).
- The spread's re-pricing, closed by the owner's word of 2026-11-02, asked beside the pick of spec `00154` D3's candidate (a): "Only if you pick (a): does the 0.0020 spread allowance stand? The box measured fees, not spread. Its fills were 97% maker, so 0.0020 a side is likely generous." — answered, verbatim, "0.0020 stands (Recommended)". The spread term stays at the registered 0.0020 a side (spec `00154` D10's spread member).
- **The re-pricing as a new registry record: trial 64** (iter-200, spec/plan `00154`, `ad15e7c45`), family P1 at n 7, verdict adopt: record 47's book rebuilt over `ohlc-full` at `fee_per_side` 0.004124 + `spread_per_side` 0.002 = `cost_per_side` 0.006124 a side clears the benchmark-relative bar record 47 passed, every leg passing (the `[iter-200]` verdict entry in `docs/research/14.phase6-decisions.md`); its multiple, `ann_sharpe_noc` and `conditional_live_sharpe` are the table's last row below, the record the go/no-go's cost-basis term (§12, term (b)) reads; `multipliers_moved` 486, the completed rows at which the governor's multiplier at the re-priced basis differs from the registered basis's.
- T0090's table re-quoted against trial 64 — its five rows as they stand in `docs/open-topics/archive/T0090-deployable-record-quoted-below-realistic-cost.md`, never edited, trial 64's row beside them:

| basis | multiplier | headline Sharpe | **conditional (what the gate reads)** |
| --- | --- | --- | --- |
| maker @€1k (42.1 bps/side) | ×0.7017 | 1.6304 | **0.9072** |
| maker @€10k (44.2 bps/side) | ×0.7367 | 1.6186 | — |
| **registered headline** | ×1.0 | **1.5609** | **0.7509** |
| taker @€1k (82.1 bps/side) | ×1.3683 | 1.3772 | **0.5201** |
| taker @€10k (84.2 bps/side) | ×1.4033 | **1.3641** | **0.5066** |
| trial 64, rung 2's box (0.004124 + 0.002 = 0.006124/side) | ×1.0206666666666666 | 1.5188542721112388 | 0.7506372410711731 |

- The builder default's move, closed by the owner's ruling of 2026-11-02, put after trial 64's run: "Trial 64 adopted record 47's strategy at your rate, fee 0.004124 + spread 0.002 = 0.006124 a side, 1.021 × the current 0.006. The live engine and the tracking report still build the strategy at the old default, 0.0040 + 0.0020. Moving that default is a separate engine change. It shifts the cost-throttle's multipliers on 486 bars of the history, changes the gate cache's fingerprint, and changes every figure read at the default. Should the default move?" — answered, verbatim, "Keep 0.006 for now (Recommended)". The engine's cycle and the tracking report keep `CrossfreqSystemConfig()`'s 0.0040 + 0.0020; the ruling moves nothing, so no topic is registered (spec `00154` D10's third member).
- None of spec `00154` D10's three members stays open, so the topic is resolved, 2026-11-02.
