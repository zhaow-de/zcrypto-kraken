# Sleeve composition ledger

Every observed change in which of the deployable's sleeves carry exposure, with the gross on each side of it.

The deployable (registry record 47, superseding 44) combines three sleeves — **B**, **A1**, **A2** — at fixed one-third weights, and the exposure governor halves the result. A sleeve sitting flat contributes zero and costs nothing to carry; it re-arms on its own signal, with no deploy and no config change. So the book's *structure* changes without anything in this repo changing, and nothing but this file records that it did.

**Why the file exists.** [T0124](../open-topics/archive/T0124-deployable-runs-as-a-one-sleeve-book.md) found the book had been running as a one-sleeve book for months and that no document said so — discovered ~9 months after the fact by a measurement iteration that happened to decompose it. The `zcrypto-engine-sleeve-count-changed` alert now announces each transition, but it ages out within a day by design and is not a record; its runbook's step 4 says to write the transition down, and this is where. A later go-live gate reads the composition history, not the alert.

**How to add a row.** Read the transition off the series rather than reconstructing it: `zcrypto_engine_active_sleeves` for the count and `zcrypto_engine_sleeve_gross` for the per-sleeve figures, bracketing the 4-hourly cycle that published the step (cycles publish a few minutes past the boundary). Record the last pre-transition cycle and the first post-transition one, at full precision. `zcrypto_engine_sleeve_gross` is each sleeve's **own** gross — the sum of its absolute target weights, before the ⅓ combination weight and before the governor — so the book figures below are derived, not published.

## Transitions

### 2026-08-22 — B and A1 re-arm; the one-sleeve era ends

| | last pre-transition cycle<br>2026-08-21 20:03Z | first post-transition cycle<br>2026-08-22 00:03Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 1 | **3** |
| `sleeve_gross{sleeve="B"}` | 0 | 0.1801192405996337 |
| `sleeve_gross{sleeve="A1"}` | 0 | 0.05523539758932526 |
| `sleeve_gross{sleeve="A2"}` | 0.6368186292538144 | 0.4995580728531716 |
| book gross (Σ ÷ 3) | 0.21227287641793813 | 0.24497090368071017 |
| governed (× 0.5) | 0.10613643820896906 | 0.12248545184035509 |

B had held exactly zero since ~2025-10-30 and A1 since ~2025-11-09 (T0124's measurement over 136 journaled cycles). This is the first re-arming of either, and the first cycle since then in which the book is genuinely the three-sleeve combination whose figures were registered.

**The gross did not move the way the alert and its runbook predicted, and that is the row's most useful fact.** Both said gross moves roughly in proportion to the count — a third sleeve arming "close to a tripling". Measured: book gross rose **×1.154** at the step (+0.0327), and by 2026-08-22 14:56Z it had fallen to **0.20893989064867470**, *below* the pre-transition level, because A2's own gross fell from 0.6368 to 0.3915 across the same window. Per-sleeve grosses are independent; they can and did move in compensating directions. The composition changed materially while the exposure barely did.

Context worth carrying: book gross had already risen ~5× over 2026-08-19 → 08-20 (0.0483 → 0.2177) on A2 alone, before any composition change — so the book was re-risking for three days before this transition, and the transition is not what put it where it is.

Owed as a consequence, tracked in [T0149](../open-topics/T0149-sleeve-reversal-invalidates-the-one-sleeve-derivations.md): the drift band and the order-placeability arithmetic were both derived under the one-sleeve state and neither updates itself.
