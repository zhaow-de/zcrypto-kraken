# Sleeve composition ledger

Every observed change in which of the deployable's sleeves carry exposure, with the gross on each side of it.

The deployable (registry record 47, superseding 44) combines three sleeves — **B**, **A1**, **A2** — at fixed one-third weights, which the exposure governor scales down two independent ways — five bars at half after a bar losing the daily limit or more, and a drawdown ladder — and leaves at 1.0 otherwise. A sleeve sitting flat contributes zero and costs nothing to carry; it re-arms on its own signal, with no deploy and no config change. So the book's *structure* changes without anything in this repo changing, and nothing but this file records that it did.

**Why the file exists.** [T0124](../open-topics/archive/T0124-deployable-runs-as-a-one-sleeve-book.md) found the book had been running as a one-sleeve book for months and that no document said so. The `zcrypto-engine-sleeve-count-changed` alert now announces each transition, but it ages out within a day by design and is not a record; its runbook's step 4 says to write the transition down, and this is where. A later go-live gate reads the composition history, not the alert.

**How to add a row.** Read the transition off the series rather than reconstructing it: `zcrypto_engine_active_sleeves` for the count and `zcrypto_engine_sleeve_gross` for the per-sleeve figures, bracketing the 4-hourly cycle that published the step (cycles publish a few minutes past the boundary). Record the last pre-transition cycle and the first post-transition one, at full precision. `zcrypto_engine_sleeve_gross` is each sleeve's **own** gross, before the ⅓ combination weight and before the governor. Do **not** derive the book from it: the ⅓ combination nets opposing sleeve positions away asset by asset, so the combined gross is not in general the summed sleeve gross ÷ 3 (`cli/engine/feeders.py::cancellation_ratio` exists to name how much survives). Read the book directly instead — `sum(abs(zcrypto_engine_target_weight))`, which is the final governed book after combination, caps and limits, and equals the journal record's `sum|final_targets|`.

## Transitions

### 2026-08-22 — B and A1 re-arm; the one-sleeve era ends

| | last pre-transition cycle<br>2026-08-21 20:03Z | first post-transition cycle<br>2026-08-22 00:03Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 1 | **3** |
| `sleeve_gross{sleeve="B"}` | 0 | 0.1801192405996337 |
| `sleeve_gross{sleeve="A1"}` | 0 | 0.05523539758932526 |
| `sleeve_gross{sleeve="A2"}` | 0.6368186292538144 | 0.4995580728531716 |
| **final book gross** (Σ\|target weight\|, governed) | **0.10613643820896906** | **0.12248545184035509** |

B had held exactly zero since ~2025-10-30 and A1 since ~2025-11-09 — dates T0124 sources from its 28,079-row backtest, not from the 136 journaled cycles (those begin 2026-07-11 and establish only that both were flat throughout them). This is the first re-arming of either, and the first cycle since then in which the book is genuinely the three-sleeve combination whose figures were registered.

**The gross did not scale with the count, and that is the row's most useful fact.** Measured: the final book rose **×1.154** at the step, and by the 12:00 cycle had fallen to **0.10446994532433734**, *below* the pre-transition level, because A2's own gross fell from 0.6368186292538144 to 0.3914650337570651 across the same window. Per-sleeve grosses are independent and moved in compensating directions. The composition changed materially while the exposure barely did.

**Nothing cancelled between the sleeves, and that is measured rather than assumed**: the final book equals the summed sleeve gross ÷ 6 to within one ulp on both sides of the step (0.10613643820896906 and 0.12248545184035509), i.e. a cancellation ratio of 1.0 — the three sleeves agreed in sign on every asset they both held. That will not always be true, which is why the recipe above says to read the book directly.

Context worth carrying: the book had already risen ~5× over 2026-08-19 → 08-20 on A2 alone (0.0483 → 0.2177 **before** the governor, i.e. 0.0241 → 0.1090 on the governed basis the table above uses), before any composition change — so the book was re-risking for three days before this transition, and the transition is not what put it where it is.

The consequences were measured at the transition rather than assumed — see [T0149](../open-topics/archive/T0149-sleeve-reversal-invalidates-the-one-sleeve-derivations.md), which carries the re-derived drift band, the re-measured placeability (placement is rare and tracks target-move size — 63 of 1,572 intended orders journal-wide — with `ordermin`, not `costmin`, the binding floor), and the re-measured expected-gross parameter.

### 2026-10-25 — A2 goes flat; the book runs on B and A1

| | last pre-transition cycle<br>2026-10-25 04Z (published by 04:02Z) | first post-transition cycle<br>2026-10-25 08Z (published by 08:02Z) |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 3 | **2** |
| `sleeve_gross{sleeve="B"}` | 0.2736749476376006 | 0.2736749476376006 |
| `sleeve_gross{sleeve="A1"}` | 0.23225123803907569 | 0.23225123803907569 |
| `sleeve_gross{sleeve="A2"}` | 0.004541113427651558 | 0 |
| **final book gross** (Σ\|target weight\|, governed) | **0.08507788318405463** | **0.08432103094611271** |

A2's gross had wound down over three days (about 0.037 on 10-22, 0.0295 and 0.0156 on the next two, 0.0045 from the 10-24 17Z cycle) and read 0 from the 08Z cycle. The book moved ×0.991 at the step, the size of A2's own last contribution: B and A1 stood exactly where they were. The book equals the summed sleeve gross ÷ 6 on both sides (0.08507788318405463 and 0.08432103094611271 against the read figures, ratios 1.000000 and 1.000000), so nothing cancelled between the sleeves at this step either. `zcrypto-engine-sleeve-count-changed` fired at 08:07:30Z (Pending 08:02:30Z); the flat was read as sustained through 2026-10-26 15:00Z, seven cycles, and held ten cycles in all, 2026-10-25 08Z through 2026-10-26 20Z.

### 2026-10-27 — A2 re-arms; the three sleeves again

| | last pre-transition cycle<br>2026-10-26 20Z | first post-transition cycle<br>2026-10-27 00Z (published by 00:02Z) |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 2 | **3** |
| `sleeve_gross{sleeve="B"}` | 0.28306223023886007 | 0.28186353398379443 |
| `sleeve_gross{sleeve="A1"}` | 0.2285482066433322 | 0.21765246874127114 |
| `sleeve_gross{sleeve="A2"}` | 0 | 0.007155053701170019 |
| **final book gross** (Σ\|target weight\|, governed) | **0.08526840614703204** | **0.08444517607103927** |

The book fell ×0.990 as A2 re-armed: B and A1 stepped down at their own daily 00Z update by more than A2's new gross added. The book again equals the summed sleeve gross ÷ 6 on both sides (0.08526840614703206 and 0.08444517607103925, ratios 1.000000 and 1.000000). `zcrypto-engine-sleeve-count-changed` fired from 00:07:30Z. The composition is back to the three sleeves the drift band was derived on after under two days, so the band re-derivation the runbook's step 3 asks for after three complete weeks in a changed composition is not owed by this pair of transitions.
