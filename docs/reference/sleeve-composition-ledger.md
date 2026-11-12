# Sleeve composition ledger

Every observed change in which of the deployable's sleeves carry exposure, with the gross on each side of it.

The deployable (registry record 47, superseding 44) combines three sleeves — **B**, **A1**, **A2** — at fixed one-third weights, which the exposure governor scales down. A sleeve sitting flat contributes zero and costs nothing to carry; it re-arms on its own signal, with no deploy and no config change. So the book's *structure* changes without anything in this repo changing, and nothing but this file records that it did.

**Why the file exists.** The `zcrypto-engine-sleeve-count-changed` alert is not a record: its runbook's step 4 writes each transition here, and a later go-live gate reads this history.

**How to add a row.** Read the transition off the series rather than reconstructing it: `zcrypto_engine_active_sleeves` for the count and `zcrypto_engine_sleeve_gross` for the per-sleeve figures, bracketing the 4-hourly cycle that published the step (cycles publish a few minutes past the boundary). Record the last pre-transition cycle and the first post-transition one, at full precision. `zcrypto_engine_sleeve_gross` is each sleeve's **own** gross, before the ⅓ combination weight and before the governor. Do **not** derive the book from it: the ⅓ combination nets opposing sleeve positions away asset by asset, so the combined gross is not in general the summed sleeve gross ÷ 3 (`cli/engine/feeders.py::cancellation_ratio` exists to name how much survives). Read the book directly instead — `sum(abs(zcrypto_engine_target_weight))`, the final governed book after combination, caps and limits, within one ulp of the journal record's `sum|final_targets|`.

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

| | last pre-transition cycle<br>2026-10-25 04Z | first post-transition cycle<br>2026-10-25 08Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 3 | **2** |
| `sleeve_gross{sleeve="B"}` | 0.2736749476376006 | 0.2736749476376006 |
| `sleeve_gross{sleeve="A1"}` | 0.23225123803907569 | 0.23225123803907569 |
| `sleeve_gross{sleeve="A2"}` | 0.004541113427651558 | 0 |
| **final book gross** (Σ\|target weight\|, governed) | **0.08507788318405463** | **0.08432103094611271** |

The book equals the summed sleeve gross ÷ 6 on both sides, to within one ulp, so nothing cancelled between the sleeves at this step either.

### 2026-10-27 — A2 re-arms; the three sleeves again

| | last pre-transition cycle<br>2026-10-26 20Z | first post-transition cycle<br>2026-10-27 00Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 2 | **3** |
| `sleeve_gross{sleeve="B"}` | 0.28306223023886007 | 0.28186353398379443 |
| `sleeve_gross{sleeve="A1"}` | 0.2285482066433322 | 0.21765246874127114 |
| `sleeve_gross{sleeve="A2"}` | 0 | 0.007155053701170019 |
| **final book gross** (Σ\|target weight\|, governed) | **0.08526840614703204** | **0.08444517607103927** |

The book again equals the summed sleeve gross ÷ 6 on both sides, to within one ulp. The band the next go-live decision reads is derived over the whole box window (plan 00092's R0 item 6, `--since 2026-10-05`), which carries the two-sleeve stretch, so no separate re-derivation follows this pair.

### 2026-10-29 — A2 goes flat again; the book runs on B and A1

| | last pre-transition cycle<br>2026-10-29 16Z | first post-transition cycle<br>2026-10-29 20Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 3 | **2** |
| `sleeve_gross{sleeve="B"}` | 0.27680137117579956 | 0.27680137117579956 |
| `sleeve_gross{sleeve="A1"}` | 0.23175786405427282 | 0.23175786405427282 |
| `sleeve_gross{sleeve="A2"}` | 0.009001193899437303 | 0 |
| **final book gross** (Σ\|target weight\|, governed) | **0.08626007152158495** | **0.0847598725383454** |

The book equals the summed sleeve gross ÷ 6 on both sides, exactly.

### 2026-11-04 — A2 re-arms; the three sleeves again

| | last pre-transition cycle<br>2026-11-04 12Z | first post-transition cycle<br>2026-11-04 16Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 2 | **3** |
| `sleeve_gross{sleeve="B"}` | 0.2331803027478531 | 0.2331803027478531 |
| `sleeve_gross{sleeve="A1"}` | 0.1529826832310278 | 0.1529826832310278 |
| `sleeve_gross{sleeve="A2"}` | 0 | 0.012834323780066924 |
| **final book gross** (Σ\|target weight\|, governed) | **0.0643604976631468** | **0.0664995516264913** |

The book equals the summed sleeve gross ÷ 6 on both sides, to within one ulp.

### 2026-11-06 — A2 goes flat again; the book runs on B and A1

| | last pre-transition cycle<br>2026-11-05 20Z | first post-transition cycle<br>2026-11-06 00Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 3 | **2** |
| `sleeve_gross{sleeve="B"}` | 0.22201612480558255 | 0.1988646935144358 |
| `sleeve_gross{sleeve="A1"}` | 0.14337346393053554 | 0.12618508297147388 |
| `sleeve_gross{sleeve="A2"}` | 0.012509402400102607 | 0 |
| **final book gross** (Σ\|target weight\|, governed) | **0.06298316518937011** | **0.054174962747651614** |

The book equals the summed sleeve gross ÷ 6 on both sides, to within one ulp. A2's step is about a quarter of the book's fall at this cycle: B and A1 fell with it.

### 2026-11-09 — A2 re-arms; the three sleeves again

| | last pre-transition cycle<br>2026-11-09 12Z | first post-transition cycle<br>2026-11-09 16Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 2 | **3** |
| `sleeve_gross{sleeve="B"}` | 0.21115017275314488 | 0.21115017275314488 |
| `sleeve_gross{sleeve="A1"}` | 0.0813969207123157 | 0.0813969207123157 |
| `sleeve_gross{sleeve="A2"}` | 0 | 0.00805303780452022 |
| **final book gross** (Σ\|target weight\|, governed) | **0.048757848910910104** | **0.05010002187833014** |

The book equals the summed sleeve gross ÷ 6 on both sides, to within one ulp. This is the first change of composition inside rung 3's tracking series, whose birth, 2026-11-09 00Z, fell on two sleeves. The band in force (`docs/research/14.phase6-decisions.md`, rung 3's gate read 6) is read over the box's whole window, which carries both compositions, so as at 2026-10-27 no separate re-derivation follows.

### 2026-11-11 — B goes flat; the book runs on A1 and A2

| | last pre-transition cycle<br>2026-11-10 20Z | first post-transition cycle<br>2026-11-11 00Z |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | 3 | **2** |
| `sleeve_gross{sleeve="B"}` | 0.21129528130350228 | 0 |
| `sleeve_gross{sleeve="A1"}` | 0.088225435982652 | 0.0743129249240008 |
| `sleeve_gross{sleeve="A2"}` | 0.008058035667649899 | 0.008054022895045664 |
| **final book gross** (Σ\|target weight\|, governed) | **0.0512631254923007** | **0.013727824636507742** |

The book equals the summed sleeve gross ÷ 6 on both sides, to within one ulp. The band in force (`docs/research/14.phase6-decisions.md`, rung 3's gate read 6) was derived over the box's window, which carries no stretch with B flat, so it does not carry this composition: `infra/runbooks/engine.md`'s `zcrypto-engine-sleeve-count-changed` step 3 re-derives it, and the expected order notionals, before the next go-live decision reads them.
