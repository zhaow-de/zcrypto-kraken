---
status: resolved
---

# The sleeve reversal invalidates the numbers derived under the one-sleeve book

## Context — what

On 2026-08-22 at the 00:00 UTC cycle the deployable's sleeve composition stepped from **1 active sleeve to 3**: B armed to 0.1801 gross and A1 to 0.05524, both from exactly zero, where they had sat since ~2025-10-30 and ~2025-11-09 respectively. The transition is recorded at full precision in [`docs/reference/sleeve-composition-ledger.md`](../reference/sleeve-composition-ledger.md); the `Engine · sleeve composition changed` alert announced it at 00:08:30Z, which is what [T0124](archive/T0124-deployable-runs-as-a-one-sleeve-book.md) built that alert for.

Two numbers were derived while the book was structurally a one-sleeve book, and neither updates itself:

- **The drift band** — the model-consistency band the go-live gate compares realized performance against.
- **Order placeability** — [T0116](archive/T0116-stage6b-subphasing-amendment.md)'s chain, measured as A2 alone at 32.2 % median gross → ÷3 by the fixed weights → 10.7 % combined → ×0.5 governor → **5.37 %** final, which is why 0 of 801 intended orders cleared Kraken's minimums at tiny-live size.

## Why this matters

The go-live gate reads both. Neither is wrong *because* the composition changed — the point is that nobody has checked, and the arithmetic that produced them has a term in it (which sleeves are live) that has now moved for the first time in ten months.

**And the obvious shortcut is already ruled out by measurement.** The alert's rule comment and its runbook both say gross moves roughly in proportion to the sleeve count — a third sleeve arming is "close to a tripling" — which would make the re-derivation a scaling exercise. It is not: book gross rose **×1.154** at the step and had fallen *below* the pre-transition level within fifteen hours, because A2's own gross fell from 0.6368 to 0.3915 while B and A1 armed. Per-sleeve grosses are independent and moved in compensating directions. So the composition changed materially while the exposure barely did, and any re-derivation has to be measured rather than scaled.

The placeability consequence is the one that could surprise in either direction: more *sleeves* at roughly unchanged *gross* means the same total exposure spread across more instruments, so individual order notionals could fall rather than rise — the opposite of what the runbook's reasoning predicts, and the direction that makes placeability worse, not better.

## Findings so far

- The transition, measured off `zcrypto_engine_active_sleeves` and `zcrypto_engine_sleeve_gross` bracketing the 00:00 cycle, is in the composition ledger with the derived book figures (0.21227 → 0.24497 book gross, 0.10614 → 0.12249 governed).
- Book gross had already risen ~5× over 2026-08-19 → 08-20 (0.0483 → 0.2177) on A2 alone, so the book was re-risking for three days *before* this transition. Whatever re-derivation happens should treat the composition step and the exposure rise as two separate events.
- The engine was and remains **disarmed** throughout (`zcrypto_exec_armed` 0, `zcrypto_exec_kill_tripped` 0), and the Stage-6a gate was unaffected — `zcrypto_gate_status` 1 with the streak advancing 39 → 42 across the window. Nothing is live on these numbers today, which is why this is registered rather than urgent.
- The falsified "proportional to the count" claim has been corrected in place on the runbook and in the alert rule's comment (this branch). Spec `00084`'s line carrying the same prediction is a point-in-time design record and is deliberately left.

## Resolution

**Resolved 2026-08-22, the same day the transition landed, by measuring all three items rather than scaling them.** The instrument was validated before any new figure was trusted: `zcrypto engine accum-replay` over the registered window (2026-07-11 → 2026-08-02, the 2026-07-07 minimums snapshot the figures rest on) reproduces [T0116](T0116-stage6b-subphasing-amendment.md)'s registered band at €1,000 — **51.1 / 115.7 bps** against its recorded 51.2 / 115.7, with three of its four weekly means identical to the decimal (94.5 / 50.3 / 68.0; W31 reads 31.1 against 32.4 on two extra cycles this window catches).

### The drift band, re-derived — and the initialisation sensitivity that nearly fooled it

Three runs at €1,000, and the difference between the first two is itself the finding:

| basis | n | median bps | p95 bps | placed |
| --- | --- | --- | --- | --- |
| standalone replay starting 2026-08-15 | 46 | 95.0 | 168.1 | 12/46 |
| **the same 46 cycles, state carried from 07-11** | 46 | **53.9** | **146.3** | 11/46 |
| registered window, same continuous run | 138 | 51.1 | 114.0 | — |
| T0116's registered figures | 136 | 51.2 | 115.7 | — |

`accumulation_payload` carries `held_qty` across cycles and **initialises it to zero at the window's first cycle**. Starting at 08-15 — the lowest-gross stretch in the journal — leaves legs that cannot be established from flat never closing their gap, so a standalone run carries a persistent additive offset that never decays. A live book is never flat; it is in the carried state. **The carried figures are therefore the ones a gate reading today would face, and the standalone pair overstates the floor.**

**What survives the correction: the p95 widened ×1.28 (114.0 → 146.3). The median did not meaningfully move (51.1 → 53.9, ×1.05).** T0116 pinned **p95** as the gate's statistic — the edge is "the p95 of the per-cycle drift floor against that week's mean drift" — so the contradiction lands exactly where it matters, and only there.

**The direction of staleness T0116 predicted is contradicted at p95, but its mechanism was right and mine was wrong.** T0116 reasoned that a bigger book shrinks the relative floor, so a stale band would be too *wide* and would pass execution it should fail. The first draft of this resolution claimed the opposite mechanism — that larger target moves "still miss `ordermin` and land in drift". That is refuted by the placement counts in the very same window: placement **rises** with gross (21 % of cycles over the registered window, 39 % over 08-19..08-21, 50 % on 08-22; on the engine's own book, 14 intended orders cleared both floors across 08-19..08-21 against zero across 08-15..08-18). T0116's mechanism visibly operates. What fails is the *inference* from it: the residual floor is not monotone in book size, because each asset's gap is bounded by a roughly fixed EUR amount (`ordermin × close`) that it saturates toward as the book grows. So the stale band is too **narrow at p95**, and its failure direction is the safe one — it fails execution that is actually fine rather than passing execution that is not.

One consequence worth stating plainly: at the carried p95 the pre-registered 10 bps band remains unmet at every NAV measured, as it was before.

**What this window cannot support**, stated rather than glossed: it spans the one-sleeve state at both low and raised gross plus only four three-sleeve cycles, and its own median book gross is **2.312 %** — *below* the registered window's 5.297 %, not double it. The doubling belongs to the last 22 cycles alone. A clean three-sleeve band needs T0116's own basis, **≥3 complete ISO weeks** in the new state.

*(Percentile note: 146.3 is linear-interpolated over the 46 sliced cycles; a nearest-rank reading of the same data gives 148.1. The median and the placed count are identical either way.)*

### Placeability, re-measured per leg — driven by target-move size, not by the composition, and the binding floor was misidentified

Read from the engine's **own intended orders** in the journal (`orders.jsonl`), not re-derived:

Swept over the **whole journal** — all 1,572 intended orders in all 256 journaled cycles, against the current snapshot: **63 orders (4.0 %) clear both floors, in 44 of 256 cycles.** Placement is not zero and it is not stable; it tracks the size of the target moves.

| cycle | state | total intended | placeable |
| --- | --- | --- | --- |
| 2026-08-19 16:00 | one sleeve | €56.9080 | 5 of 10 |
| 2026-08-20 00:00 | one sleeve | €21.3159 | 3 of 10 |
| 2026-08-21 00:00 | one sleeve | €1.7368 | 0 of 10 |
| 2026-08-21 20:00 | one sleeve | €0.2709 | 0 of 10 |
| 2026-08-22 00:00 | three sleeves (the step) | €16.3490 | **0 of 10** |
| 2026-08-22 04:00 | three sleeves | €9.1254 | 0 of 10 |
| 2026-08-22 12:00 | three sleeves | €1.7037 | 0 of 10 |

**`ordermin`, not `costmin`, is what binds** — by one to two orders of magnitude — and neither T0116's chain nor this topic's own framing said so: `costmin` is €0.45 across all ten EUR legs, while `ordermin` is a base-unit floor (BTC 5e-05, DOGE 50, ADA 20). At the transition cycle **nine** of ten legs cleared `costmin` — only DOGE at €0.1947 missed it — and **none** cleared `ordermin`.

The transition cycle placed nothing, and its nearest miss was **BTC at 4.7911331e-05 against a 5e-05 floor, 95.8 %** — striking to look at, but **not a record**: the journal-wide maximum is **ETH/EUR at 749.2 % of its floor on 2026-08-19 16:00**, three days earlier and with one sleeve live. That cycle placed five of ten. The step's €16.35 is the fifth largest of the 28 cycles from 08-18 to 08-22, not an outlier, and the two cycles after it (€9.13, €7.19) stayed well above the €0.27–1.74 the first draft of this section called "normal" — that baseline was the two smallest cycles of one day.

**The direction this topic originally speculated is refuted.** It said more sleeves at unchanged gross would spread exposure across more instruments and push individual notionals *down*. The leg count did not change: **ten legs carried non-zero weight before and after** (the two `/BTC` legs are structurally zero either way), so the new sleeves' exposure landed on the same instruments, and the step made orders larger, not smaller.

### The expected-gross parameter, re-measured

Median final book gross per cycle, the endpoint of T0116's chain (registered as **5.371 %** of NAV):

| window | n | median | state |
| --- | --- | --- | --- |
| 2026-07-11 → 08-02 | 138 | 5.297 % | one sleeve (the registered basis, reproduced) |
| 2026-08-10 → 08-18 | 54 | 3.320 % | one sleeve, before the gross rise |
| 2026-08-19 → 08-21 | 18 | 9.625 % | one sleeve, after it |
| 2026-08-22 | 4 | 10.977 % | three sleeves |

The parameter has roughly **doubled**, and the table shows why the composition step is not the cause: most of the move happened on 08-19/20 with one sleeve still live. Two events, not one.

### T0116's companion check, discharged

Its re-derivation trigger also says to re-check the minimums stamp in the same pass, since Kraken moves those without notice ([T0113](T0113-refdata-snapshot-staleness.md)). Compared `kraken-refdata-20260707T032900Z.json` against `kraken-refdata-20260804T104009Z.json` through the engine's own loader: **0 of 10 bases moved** — every `ordermin` and `costmin` identical. The band figures above are not contaminated by a minimums change.

### The fixed ⅓ weights

No change is proposed and none is owed. The weights are part of what registry record 47 ratified, so altering them is a re-ratification rather than a tuning, and nothing measured here argues for one: the sleeves agreed in sign (cancellation ratio 1.0), so the combination is behaving exactly as specified. The measurements above are what an owner would need if they ever chose to revisit it.
