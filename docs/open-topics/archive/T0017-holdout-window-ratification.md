---
status: resolved
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

## Resolution

- **Window RATIFIED (human, attended session 2026-07-09 ~23:50 Berlin)**: the holdout is the **out-of-time window 2026-04-01 → a fresh freeze at the look date** (decisions log `[iter-072]`). The burned in-sample window is formally retired; the delay-to-2027 option was declined. The look will run on the **two-sleeve system** (A1-lf weekly v0.12 admitted as a second sleeve in the same session — T0009 decisions 5/6), after its P1 trial validates.

- **Correction (2026-09-12), on the sweep's read of the archive:** "The look will run on the **two-sleeve system** … after its P1 trial validates" is contradicted by what the look ran on: the two-sleeve P1 (trial 35) was **rejected** under its pre-registered criteria, so the subject stayed the one-sleeve record 33. Shown by `sed -n '7p' docs/research/13.phase5-holdout-ledger.md` → the ledger's only row names `**Record 33** (one-sleeve combined system) vs the frozen benchmark B3+vt-dynamic`, and `grep -n "holdout look's subject" docs/research/13.phase5-decisions.md` → `84:[iter-072] … Trial 35 (P1, two-sleeve, n=2): REJECT per the pre-registered criteria — Sharpe 1.3135 < record 33's 1.3263 … The deployable system and the holdout look's subject remain record 33 (one sleeve).` This sentence was written at the 2026-07-09 ratification, before that verdict existed; the bullet below and the blockquote above both already read on record 33.

- **Both next steps were executed the same night and neither outlived the look** (2026-07-10 ~01:35 UTC, human present — decisions log `[iter-073]`). The runbook's §Holdout-look protocol ran verbatim: a fresh pull to `data/ohlc-holdout-2026-07-10` (100 bars/pair over 2026-04-01 → 2026-07-09, manifest `4e251df2…`, 621 overlap bars/pair verified exact against the canonical, which stayed untouched), record 33 against the frozen B3+vt-dynamic benchmark, no parameter changed after any number was seen. The §9 budgeted-holdout ledger was created in the same change — `docs/research/13.phase5-holdout-ledger.md`, one row, look budget 1 → 0, verdict **EQUALS** on a window whose exposure was zero on both sides every bar.

**The steps this topic carried at its close, kept verbatim with what answered each:**

- **[human + loop, at the event]** Execute the pre-registered mechanical procedure in the runbook §Holdout-look protocol verbatim: fresh OHLC pull for the 10 assets through the freeze date → dataset QA (gap/duplicate checks, hash the new manifest) → compute combined system and frozen benchmark net-of-cost on the ratified window only → stationary-bootstrap CI (mean_block 17, n_resamples 2000, seeds 42/7/1234) on the Sharpe difference → read *beats-or-equals* per the exit bar. One look. No parameter may change after seeing any number. — **ANSWERED:** executed 2026-07-10 ~01:35 UTC with the human present (decisions log `[iter-073]`) — fresh pull to `data/ohlc-holdout-2026-07-10` (100 bars/pair, 2026-04-01 → 2026-07-09; manifest `4e251df2…`; 621 overlap bars/pair verified exact against the canonical, which stayed untouched), record 33 against the frozen B3+vt-dynamic benchmark, CI trivially [0, 0] on a window at literal zero exposure both sides, exit-bar reading **EQUALS**; no parameter changed after any number was seen.
- **[loop, at the event]** Create the §9 budgeted-holdout ledger (`docs/research/13.phase5-holdout-ledger.md`: date, window, dataset hash, who was present, figures, verdict; one row per look, budget 1) and record the look in it in the same change. — **ANSWERED:** created in that same change — `docs/research/13.phase5-holdout-ledger.md` carries the prescribed columns in one row (look budget 1, remaining 0; subject record 33; verdict **EQUALS**) and a procedure note recording `12.phase5-system-spec-runbook.md` §Holdout-look protocol as executed verbatim.
