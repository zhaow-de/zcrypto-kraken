---
status: open
ripe_when: before the pre-live universe refresh ([[T0025]]) or any decision that leans on the spread cap covering the whole universe — whichever comes first. Adding subscriptions to a live unbackfillable pipeline is a capture-config change with its own cost, so it wants a deliberate slot, not a drive-by
---

# Two universe legs have no L2 capture, so the spread cap cannot screen them

## Context — what

The capture daemon subscribes to **EUR-quoted pairs only**. Verified against the archive: every base under `/mnt/zhao-crypto/capture-reconciled/<BASE>/` has exactly one quote directory, `EUR`, and nothing else.

The point-in-time universe, however, selects **twelve** symbols — ten EUR-quoted plus **`ETH/BTC` and `SOL/BTC`**, the BTC-quoted relative-value legs. Those two have no L2 capture at all, and therefore no spread.

[[T0024]]'s spread cap (spec `00067`) consequently screens 10 of 12. The two uncaptured legs are recorded `spread_bps: null` on their universe entries and are **not** rejected — absence of evidence is not evidence of a wide spread — but they are equally not *checked*.

## Why this matters

The cap exists because "a thin-book pair could clear the €150k/day volume floor yet be untradeable at our sizing". `SOL/BTC` sits at **233,594 EUR/day** median quote volume — barely above the €150k floor, and one of the two symbols the cap cannot see. The gap sits precisely where the criterion was most wanted.

It is not urgent: nothing today suggests those legs are untradeable, they are relative-value legs rather than core exposure, and the cap binds on nothing anywhere in the universe right now. But a criterion that silently covers 10/12 while reading as a universe-wide filter is the "green because we stopped looking" shape, which is why the nulls are surfaced in the artifact rather than hidden.

## Findings so far

- Capture coverage measured 2026-07-22: 10 bases × `EUR` only. Both BTC-quoted legs absent.
- Both legs are genuinely selected members, not candidates: `ETH/BTC` (579,964 EUR/day, max leverage 5) and `SOL/BTC` (233,595 EUR/day, max leverage 4).
- The cost model has the same blind spot for the same reason — `cli/costs/spread.py`'s table is keyed by base and calibrated from EUR pairs, so a BTC-quoted notional has no entry either. Any future cost accounting on those legs inherits this gap.
- Adding two subscriptions is not free: it touches a **live, unbackfillable** capture pipeline (the canary rule in `capture-deploys.md` applies), adds two more streams to the reconciler and the panel, and grows the archive. The cost is operational, not analytical.

## Suggested next steps

- **(Decide first — the whole question)** Whether the BTC-quoted legs should be captured at all. Three shapes: (a) add `ETH/BTC` + `SOL/BTC` to the capture set and let the panel/calibration pick them up on the next window; (b) leave them uncaptured and make the exemption explicit policy — the spread cap is a EUR-leg criterion by design; (c) drop the BTC-quoted legs from the universe at the pre-live refresh, which removes the gap by removing the members. Option (b) is the status quo and is defensible; it just needs to be a decision rather than an accident.
- **(If (a))** Sequence it through the capture-rollout discipline — a subscription change is a capture-image/config rollout, and the pipeline is unbackfillable.
- **(Cheap, whichever way)** A derived cross-spread sanity check: `ETH/BTC`'s spread is bounded below by the combination of `ETH/EUR` and `BTC/EUR` spreads. That gives an order-of-magnitude floor without new capture — enough to confirm the legs are nowhere near the cap, though not enough to screen them properly.
