---
status: open
---

# Stage 6b sub-phasing — the ratified ladder lands as a §12 amendment

## Context — what

§12's Stage 6b as written (€500–1,000 sleeve, quarter size, weekly tracking error against a 10 bps-of-NAV band) was measured against the real 6a journal on 2026-07-30 and cannot execute: **0 of 801** intended orders clear Kraken's minimums at the tiny-live size as specified. The owner and the session reshaped 6b into a three-rung ladder, and the **shape was ratified 2026-08-02**: rung 1 = the §11 T2 tax probe as the plumbing proof (≥1 margin long + ≥1 margin short across ≥2 rollovers, one closed one settled, ~€10–30); rung 2 = fewer assets at lower budget, time-boxed, operational confidence only — its tracking error is explicitly not the go/no-go number; rung 3 = full weights at €1,000 under the accumulation delta formula ([[T0119]]), gated on a re-derived tracking band ([[T0118]]). This topic is the amendment's carrier: the ladder text, the re-anchored go/no-go band, the §12 edit, and the decision-register entry.

## Why this matters

Without the amendment the ratification exists only in a memo bullet and a conversation — the exact informal drift §12's governance exists to prevent. And the go/no-go gate as pre-registered would measure Kraken's minimums, not our execution: per-asset live-vs-sim mismatch under accumulation is bounded by ~`ordermin` (€30–80 across the active book) while the deployed book at €1,000 is ~€54 — mismatch can exceed deployed exposure, so the written band (≤ €1/week at €1,000) is structurally unmeetable and would force either a false NO-GO or a quiet waiver at the gate.

## Findings so far

- The placeability measurement (2026-07-30, 801 intended orders / 120 cycles / 20 days): €1,000 full weights 4.0 % placeable, €500 full 1.5 %, €1,000 quarter 0.25 %, €500 quarter 0 %; median intended order €0.0116 against 20-day total turnover of ~€275; blocked by `ordermin` (the quantity floor, €3–25/pair in EUR terms — e.g. 20 ADA, 50 DOGE, 3.9 DOT), not `costmin` (€0.45); median miss ~3 orders of magnitude. Scaling: 50 % placeability needs ~€228k, 80 % ~€1.36 M, 95 % ~€9.4 M. The design never produces mostly-placeable orders at any sanctioned size — the ladder is the response, not a workaround.
- Shape ratified 2026-08-02 (owner): parameters wait on two feeder measurements — [[T0117]] (gross decomposition) and [[T0118]] (accumulation replay → the honest band). Both can only move parameters (band width, expected gross, rung-2 scope), not the shape.
- Rung 1 doubles as §11's T2 probe and gives [[T0090]] its first measured fills; [[T0005]]'s T1 check rides alongside; the go/no-go still inherits [[T0064]] and [[T0090]] regardless of staging.
- Caveats on all numbers: journal read from the NAS replica; venue minimums from the snapshot register stamped 2026-07-07 ([[T0113]]); figures describe intent, not fills.

## Suggested next steps

- **(autonomous)** After [[T0117]] and [[T0118]] land: draft the §12 amendment — the three rungs with their entry/exit criteria, the re-derived band as the rung-3 gate, rung 2's skip-or-carry policy, and the explicit statement that rung 2's tracking error is not a gate input.
- **(decision)** Owner ratifies the amendment text; it lands as a `00.master-plan.md` edit plus a decision-register entry in the phase-6 decisions log, in one change.
- **(autonomous)** Update the 6b session brief's decision queue to point at the ratified ladder (its items 1–6 currently describe the un-sub-phased 6b).
