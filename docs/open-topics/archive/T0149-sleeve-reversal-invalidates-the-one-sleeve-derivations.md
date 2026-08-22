---
status: resolved
---

# The sleeve reversal invalidates the numbers derived under the one-sleeve book

## Context — what

On 2026-08-22 at the 00:00 UTC cycle the deployable's sleeve composition stepped from **1 active sleeve to 3**: B armed to 0.1801 gross and A1 to 0.05524, both from exactly zero, where they had sat since ~2025-10-30 and ~2025-11-09 respectively. The transition is recorded at full precision in [`docs/reference/sleeve-composition-ledger.md`](../../reference/sleeve-composition-ledger.md); the `Engine · sleeve composition changed` alert announced it at 00:08:30Z, which is what [T0124](T0124-deployable-runs-as-a-one-sleeve-book.md) built that alert for.

Two numbers were derived while the book was structurally a one-sleeve book, and neither updates itself:

- **The drift band** — the model-consistency band the go-live gate compares realized performance against.
- **Order placeability** — [T0116](T0116-stage6b-subphasing-amendment.md)'s chain, measured as A2 alone at 32.2 % median gross → ÷3 by the fixed weights → 10.7 % combined → ×0.5 governor → **5.37 %** final, which is why 0 of 801 intended orders cleared Kraken's minimums at tiny-live size.

## Why this matters

The go-live gate reads both. Neither is wrong *because* the composition changed — the point is that nobody has checked, and the arithmetic that produced them has a term in it (which sleeves are live) that has now moved for the first time in ten months.

**And the obvious shortcut is already ruled out by measurement.** The alert's rule comment and its runbook both say gross moves roughly in proportion to the sleeve count — a third sleeve arming is "close to a tripling" — which would make the re-derivation a scaling exercise. It is not: book gross rose **×1.154** at the step and had fallen *below* the pre-transition level within fifteen hours, because A2's own gross fell from 0.6368 to 0.3915 while B and A1 armed. Per-sleeve grosses are independent and moved in compensating directions. So the composition changed materially while the exposure barely did, and any re-derivation has to be measured rather than scaled.

The placeability consequence looked, when this topic was opened, as though it could surprise in either direction: more *sleeves* at roughly unchanged *gross* might spread the same exposure across more instruments and push individual notionals down. **That speculation is refuted below** — the leg count did not change — and it is left here only so the Resolution's correction of it reads against something.

## Findings so far

- The transition, measured off `zcrypto_engine_active_sleeves` and `zcrypto_engine_sleeve_gross` bracketing the 00:00 cycle, is in the composition ledger with the derived book figures (0.21227 → 0.24497 book gross, 0.10614 → 0.12249 governed).
- Book gross had already risen ~5× over 2026-08-19 → 08-20 (0.0483 → 0.2177) on A2 alone, so the book was re-risking for three days *before* this transition. Whatever re-derivation happens should treat the composition step and the exposure rise as two separate events.
- The engine was and remains **disarmed** throughout (`zcrypto_exec_armed` 0, `zcrypto_exec_kill_tripped` 0), and the Stage-6a gate was unaffected — `zcrypto_gate_status` 1 with the streak advancing 39 → 42 across the window. Nothing is live on these numbers today, which is why this is registered rather than urgent.
- The falsified "proportional to the count" claim has been corrected in place on the runbook and in the alert rule's comment (this branch). Spec `00084`'s line carrying the same prediction is a point-in-time design record and is deliberately left.

## Resolution

**Resolved 2026-08-22, the same day the transition landed, by measuring all three items rather than scaling them.** The instrument was validated before any new figure was trusted: `zcrypto engine accum-replay` over the registered window (2026-07-11 → 2026-08-02, the 2026-07-07 minimums snapshot the figures rest on) reproduces [T0116](T0116-stage6b-subphasing-amendment.md)'s registered band at €1,000 — **51.1 / 115.7 bps** against its recorded 51.2 / 115.7, with three of its four weekly means identical to the decimal (94.5 / 50.3 / 68.0; W31 reads 31.1 against 32.4 on two extra cycles this window catches).

### The drift band, re-derived across the whole NAV curve

All figures below are **nearest-rank p95** — the estimator `accum-replay` itself uses, because it always reports an observed value. Everything is one continuous replay of 2026-07-11 → 08-22 (257 cycles, 0 failed) against the 2026-08-04 minimums, sliced; a standalone run of the later window is reported separately because the difference between them is itself a finding.

| NAV | registered 07-11 → 08-02 | current 08-15 → 08-22 | 10 bps band at p95 |
| --- | --- | --- | --- |
| €500 | 147.9 / 209.2 | 142.1 / 306.8 | unmet → unmet |
| **€1,000** | **51.1 / 115.7** | **54.3 / 148.1** | unmet → unmet |
| €2,500 | 11.5 / 30.9 | 6.9 / 58.3 | unmet → unmet |
| €5,000 | 6.1 / 14.2 | 6.6 / 23.7 | unmet → unmet |
| €10,000 | 4.3 / **8.9** | 2.0 / **12.7** | **MET → UNMET** |

The registered column reproduces T0116's recorded curve cell for cell (147.9/209.2, 51.2/115.7, 11.6/30.9, 6.2/14.2, 4.3/8.9), which is what qualifies the instrument.

**The gate-relevant result is the last row.** T0116 recorded the pre-registered 10 bps band as becoming meetable around €10,000 on p95 (8.9). It is **no longer met at any NAV measured** — €10,000 now reads 12.7. That is new, and it is the one number here a go/no-go would actually consult.

**At rung 3's own size the p95 widened ×1.28** (115.7 → 148.1) while the median did not move (51.1 → 54.3). T0116 pinned p95 as the gate's statistic — its edge is "the p95 of the per-cycle drift floor against that week's mean drift" — so the contradiction lands exactly there and only there.

**Two honesty caveats on that ×1.28, both of which cut against the headline.**

*The comparison is not fully like-for-like.* `accumulation_payload` initialises held quantity to zero at its first cycle, so a window opening in a low-gross stretch carries an additive offset that never decays. A standalone run of 08-15 → 08-22 reads **95.0 / 168.1** — the flat-start artifact — against **54.3 / 148.1** for the same cycles carried from 07-11, and the carried figures are the honest ones because a live book is never flat. But **the registered window is itself the start of the chain and carries the identical artifact**: drop its first two days and it reads 49.7 / **91.0**. De-transiented on both sides the widening is ≈**×1.63**, not ×1.28. The direction survives either way — 07-11 is the journal's first day, so no warm start exists for it, and that is exactly why the like-for-like number is a range rather than a point.

*The window cannot separate what changed.* It spans the one-sleeve state at both low and raised gross plus only the first three-sleeve cycles, and its own median book gross is **2.312 %** — *below* the registered window's 5.297 %, not double it; the doubling belongs to its last cycles alone. A band the gate can rest on needs T0116's own basis, **≥3 complete ISO weeks** in the new composition, and that instruction now lives on the operating surface (`infra/runbooks/engine.md`, this alert's step 3) rather than in this file, which is about to be archived.

**The direction of staleness T0116 predicted is contradicted at p95, but its mechanism was right and mine was wrong.** T0116 reasoned that a bigger book shrinks the relative floor, so a stale band would be too *wide* and would pass execution it should fail. The first draft of this resolution claimed the opposite mechanism — that larger target moves "still miss `ordermin` and land in drift". The placement counts in the very same window refute that: placement **rises** with gross (21 % of cycles over the registered window, 39 % over 08-19..08-21, 50 % on 08-22; on the engine's own book, 15 intended orders cleared both floors across 08-19..08-21 against 2 across 08-15..08-18). T0116's mechanism visibly operates. What fails is the *inference* from it: the per-asset unplaced gap is bounded by `max(ordermin × close, costmin)` — about €35.95, ≈359 bps at €1,000 — a fixed ceiling the floor saturates toward, so it is not monotone in book size. The stale band is therefore too **narrow at p95**, and its failure direction is the safe one: it fails execution that is actually fine rather than passing execution that is not.

### Placeability, re-measured per leg — driven by target-move size, not by the composition, and the binding floor was misidentified

Read from the engine's **own intended orders** in the journal (`orders.jsonl`), not re-derived:

Swept over the **whole journal** — all 1,572 intended orders in all 256 journaled cycles, against the current snapshot: **63 orders (4.0 %) clear both floors, in 44 of 256 cycles.** Placement is not zero and it is not stable; it tracks the size of the target moves.

| cycle | state | total intended | placeable |
| --- | --- | --- | --- |
| 2026-08-19 16:00 | one sleeve | €56.9080 | 5 of 8 |
| 2026-08-20 00:00 | one sleeve | €21.3159 | 3 of 9 |
| 2026-08-21 00:00 | one sleeve | €1.7368 | 0 of 10 |
| 2026-08-21 20:00 | one sleeve | €0.2709 | 0 of 10 |
| 2026-08-22 00:00 | three sleeves (the step) | €16.3490 | **0 of 10** |
| 2026-08-22 04:00 | three sleeves | €9.1254 | 0 of 10 |
| 2026-08-22 08:00 | three sleeves | €7.1864 | 0 of 10 |
| 2026-08-22 12:00 | three sleeves | €1.7037 | 0 of 10 |

**`ordermin`, not `costmin`, is what binds** — by one to two orders of magnitude. This is a re-confirmation, not a discovery: T0116's own findings and `14.phase6b-orientation.md` both already say *"the blocker is `ordermin` … not `costmin`"*, and T0116 already recorded **4.0 % placeable at €1,000** — the journal-wide 4.01 % below is a different and larger population landing on the same number, which is itself worth knowing. What had never drawn the distinction are the two surfaces an operator actually reads at the moment it matters, the alert and its runbook, and the chain in this topic's own framing: `costmin` is €0.45 across all ten EUR legs, while `ordermin` is a base-unit floor (BTC 5e-05, DOGE 50, ADA 20). At the transition cycle **nine** of ten legs cleared `costmin` — only DOGE at €0.1947 missed it — and **none** cleared `ordermin`.

The transition cycle placed nothing, and its nearest miss was **BTC at 4.7911331e-05 against a 5e-05 floor, 95.8 %** — striking to look at, but **not a record**: the journal-wide maximum is **ETH/EUR at 749.2 % of its floor on 2026-08-19 16:00**, three days earlier and with one sleeve live. That cycle placed five of ten. The step's €16.35 is the **fourth** largest of the 28 cycles from 08-18 to 08-22, not an outlier, and the two cycles after it (€9.13, €7.19) stayed well above the €0.27–1.74 the first draft of this section called "normal" — that baseline was the two smallest cycles of one day.

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

Its re-derivation trigger also says to re-check the minimums stamp in the same pass, since Kraken moves those without notice ([T0113](T0113-snapshot-register-reconfirmation-is-unregistered.md)). Compared `kraken-refdata-20260707T032900Z.json` against `kraken-refdata-20260804T104009Z.json` through the engine's own loader: **0 of 10 bases moved** — every `ordermin` and `costmin` identical. The band figures above are not contaminated by a minimums change.

### The fixed ⅓ weights

No change is proposed and none is owed. The weights are part of what registry record 47 ratified, so altering them is a re-ratification rather than a tuning, and nothing measured here argues for one: the sleeves agreed in sign (cancellation ratio 1.0), so the combination is behaving exactly as specified. The measurements above are what an owner would need if they ever chose to revisit it.
