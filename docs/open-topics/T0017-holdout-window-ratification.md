---
status: open
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

## Suggested next steps

- **[human, at the holdout event]** Ratify the holdout window. On the runbook's §Holdout-look protocol, pick one: **(1) recommended** — out-of-time window 2026-04-01 → the fresh pre-deployment freeze date (genuinely clean; shorter than 12 months — the power tradeoff is stated there); (2) delay the event until 12 clean out-of-time months exist (~2027-04); (3) any other window you define. Record the choice in the decisions log and the runbook.
- **[human + loop, at the event]** Execute the pre-registered mechanical procedure in the runbook §Holdout-look protocol verbatim: fresh OHLC pull for the 10 assets through the freeze date → dataset QA (gap/duplicate checks, hash the new manifest) → compute combined system and frozen benchmark net-of-cost on the ratified window only → stationary-bootstrap CI (mean_block 17, n_resamples 2000, seeds 42/7/1234) on the Sharpe difference → read *beats-or-equals* per the exit bar. One look. No parameter may change after seeing any number.
- **[loop, at the event]** Create the §9 budgeted-holdout ledger (`docs/research/holdout-ledger.md`: date, window, dataset hash, who was present, figures, verdict; one row per look, budget 1) and record the look in it in the same change.
