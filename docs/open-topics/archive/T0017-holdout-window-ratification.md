---
status: resolved
ripe_when: the Phase-5 holdout event (D3(v), human present) — this decision IS the event's first agenda item
---

# Holdout window ratification — the pre-registered definition was never carved out

## Context — what

The Decision Register's autonomous-with-defaults holdout definition (master-plan §12: *"final 12 months at data freeze; look budget = 1, spent in Phase 5"*) was adopted but **never operationalized**: no carve-out exists in the Phase-1/2 artifacts, and every backtest from Phase 3 through the P1 combination adoption (record 33) ran the **full** dataset window (2013-09-10 → 2026-03-31; 2025/2026 calendar slices appear in every report). The final 12 months of the research dataset are in-sample everywhere and unusable as a clean holdout. The only genuinely untouched data is **out-of-time: after 2026-03-31** (~3.2 months as of 2026-07-09, growing until the pre-deployment freeze).

## Why this matters

The Phase-5 exit bar reads *"combined system beats or equals the frozen bar **on the holdout look** with CIs reported."* Without a ratified, honest holdout window, the exit bar cannot be met and the go/no-go-to-paper decision has no out-of-sample evidence behind it. Redefining a pre-registered protocol element is a human decision by the register's own rules.

## Findings so far

- The discovery and options analysis: decisions log `[iter-061]`; presented with a recommendation in `docs/research/12.phase5-system-spec-runbook.md` §Holdout-look protocol.
- No performance computation has touched post-2026-03-31 data (verified by the dataset span itself — the canonical dataset ends 2026-03-31 and is hash-frozen; registry record 1's `dataset_hash` binds it).
- The §9 *budgeted-holdout ledger* was never built (no look has occurred yet).

> **Resolution (2026-07-10, attended — iter-073).** Window ratified (out-of-time 2026-04-01 → freeze), the look executed in the human's presence the same night, the ledger created (`docs/research/13.phase5-holdout-ledger.md`, budget → 0). Result: a degenerate window — both systems at zero exposure throughout (gate off); exit-bar reading **EQUALS**, trivially.

## Done so far

- **Window RATIFIED (human, attended session 2026-07-09 ~23:50 Berlin)**: the holdout is the **out-of-time window 2026-04-01 → a fresh freeze at the look date** (decisions log `[iter-072]`). The burned in-sample window is formally retired; the delay-to-2027 option was declined. The look will run on the **two-sleeve system** (A1-lf weekly v0.12 admitted as a second sleeve in the same session — T0009 decisions 5/6), after its P1 trial validates.

## Suggested next steps

- **[human + loop, at the event]** Execute the pre-registered mechanical procedure in the runbook §Holdout-look protocol verbatim: fresh OHLC pull for the 10 assets through the freeze date → dataset QA (gap/duplicate checks, hash the new manifest) → compute combined system and frozen benchmark net-of-cost on the ratified window only → stationary-bootstrap CI (mean_block 17, n_resamples 2000, seeds 42/7/1234) on the Sharpe difference → read *beats-or-equals* per the exit bar. One look. No parameter may change after seeing any number.
- **[loop, at the event]** Create the §9 budgeted-holdout ledger (`docs/research/13.phase5-holdout-ledger.md`: date, window, dataset hash, who was present, figures, verdict; one row per look, budget 1) and record the look in it in the same change.
