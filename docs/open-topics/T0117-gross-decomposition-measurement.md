---
status: open
---

# The ~5 % gross: vol-target's intended output, or governor derating in-window?

## Context — what

The 20-day 6a journal shows the book running ~5 % gross (median 5.4 %, range 1.9–9.1 %, net = gross — long-only in the window, median 7/10 assets active; at €1,000 that deploys ~€54, roughly €8 per active position, and an intended order is a delta of that). A 10–12 % vol target against 60–80 % realized crypto vol naively suggests 15–20 % gross, so the measured figure is a factor of ~3 below the naive expectation. Two candidate explanations with different consequences: the vol-target × cap pipeline legitimately produces this (fine), or the governor was derating in-window (its ladder is `((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))` with daily-loss 0.5) and the "true" book is larger. The cycle records journal only `final_targets` + snapshot hashes — no multiplier — so the decomposition needs a builder rebuild that separates capped-book gross from the governor multiplier, replayed over the journaled snapshots.

## Why this matters

Every placeability number behind the Stage-6b ladder ([[T0116]]) scales with gross: if the un-derated book is 15–20 % rather than 5 %, order sizes triple-to-quadruple and the rung-3 parameters (and the €228k "50 % placeable" figure) move materially. It is also a sanity check on the deployable itself — a governor stuck at ×0.5 for 20 days would be a finding about the DD state, not about sizing.

## Findings so far

- Governor ladder and daily-loss factor read from config (2026-07-30); the journal's `final_targets` are post-governor, so the decomposition cannot be read off existing records.
- `build_crossfreq_system` / `build_crossfreq_system_fast` (`cli/portfolio/crossfreq_system.py`) rebuild the book from journaled snapshots; the rebuild must expose the pre-governor capped book beside the multiplier rather than only their product.
- The governor enters live at its true carried state (×0.5 — recorded in [[T0018]]), which is itself a candidate explanation for the whole gap: 5.4 % × 2 ≈ 11 % ≈ the vol target's naive output.

## Suggested next steps

- **(autonomous)** Extend the builder (or a read-only sibling of it) to emit `(capped_gross, governor_multiplier, final_gross)` per journaled cycle; replay the 20-day journal; report the decomposition series.
- **(autonomous)** Classify the answer: intended output (close [[T0116]]'s parameter question with the measured gross), or in-window derating (report which ladder rung and why — the DD input series becomes the next question).
- **(autonomous)** Feed the result into [[T0116]]'s amendment text as the expected-gross parameter for rungs 2–3.
