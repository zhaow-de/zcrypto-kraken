---
status: open
ripe_when: a go-live decision is about to read either derived number — check `grep -n "drift band\|model-consistency band" infra/runbooks/engine.md` and the gate's own comparison basis. Ripe immediately if `zcrypto_exec_armed` renders `true` (the derivations then bind live orders), and ripe on any further step in `zcrypto_engine_active_sleeves` (each one re-invalidates whatever the previous re-derivation concluded). NOT ripe on the alert alone — the alert announces the transition, which is already recorded.
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

## Suggested next steps

- **Re-derive the drift band under the three-sleeve composition.** It is the model-consistency band the gate compares realized performance against; identify where it is defined and what inputs it takes, then recompute with the current composition rather than scaling the old figure.
- **Re-measure the placeability chain end to end** — per-sleeve gross → combined → governed → per-instrument order notionals → against each leg's `ordermin` and `costmin`. Report it per leg, not as a single percentage: the one-sleeve figure was a single number because only one sleeve was live, and that is exactly what has stopped being true. Explicitly answer whether notionals rose or fell.
- **Decide whether the fixed ⅓ weights still express the intent** now that all three sleeves are live for the first time since the deployable was ratified. This is a judgement for the owner, not an autonomous change — the weights are part of what registry record 47 ratified, and changing them is a re-ratification, not a tuning.
