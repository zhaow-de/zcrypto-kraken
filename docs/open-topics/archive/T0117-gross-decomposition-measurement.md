---
status: resolved
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

## Resolution

**Resolved 2026-08-02 by spec `00081`** (`docs/specs/00081-6b-feeder-measurements-design.md`), commits `6ef95da9` (per-cycle stage extraction), `892ec8f4` (`decompose_payload` + the attribution report), `5dbb0974` (`zcrypto engine decompose`). Measured over **136 journaled cycles, 2026-07-11 → 2026-08-02**, on the NAS journal replica. All three sub-items close.

**The framing was a false binary, and neither branch is the answer.** The governor *is* derating (branch 2 — a constant ×0.5 on every one of the 136 cycles), but that is only a factor of 2 of a factor of ~6. The missing factor is structural and was in neither branch: the deployable combines three sleeves at **fixed ⅓ weights** and two of them hold nothing.

**The chain, medians of per-cycle values** (every consecutive-stage ratio is the median of per-cycle ratios, never a ratio of stage medians):

| stage | median | note |
| --- | --- | --- |
| A2 sleeve gross | **32.224 %** of NAV | min 7.423, max 54.853 |
| B sleeve gross | **0** | exactly zero in all 136 cycles |
| A1 sleeve gross | **0** | exactly zero in all 136 cycles |
| mean sleeve gross | **10.741 %** | = combined gross; the ⅓ weights on one live sleeve |
| capped gross | 10.741 % | position caps bound **0 of 136** cycles |
| governor multiplier | **×0.5** | constant across the window |
| final gross | **5.371 %** | what the engine journals and would trade |

Ratios: sleeve → combined **1.000**, combined → capped **1.000**, capped → final **0.500**. In one line: **32.2 % → ÷3 (fixed ⅓ weights, one live sleeve) → 10.7 % → caps no-op → ×0.5 → 5.37 %.**

**No residual is left over, and the "naive 15–20 %" was never the book's number.** The spec's Risks anticipated an unexplained remainder; there is none. A2 alone runs at 32.2 % gross — *above* the naive per-sleeve expectation, not below it — and the whole ~6× gap to the observed ~5 % is the ⅓ combination times the ×0.5 governor, both exactly accounted. The naive arithmetic's error was treating a per-sleeve vol target as a book gross target. So this is the **first branch** in substance — the pipeline's intended output — arriving through a mechanism the topic never listed.

**The spec's own D3 hypothesis is refuted.** D3 made the cancellation term first-class on the reasoning that ⅓-weighting nets opposing sleeve positions away asset by asset, and called it "the likeliest answer". The measured cancellation ratio is **exactly 1.000** on every cycle: nothing cancels, because there is nothing to cancel against. A prediction the iteration itself made, and which shaped the report's design, was wrong — recorded here rather than quietly dropped, because the report still carries the term and a later reader would otherwise read 1.000 as a finding about sleeve agreement instead of about sleeve dormancy.

**The dormancy is not a defect, and it opened [[T0124]].** Both sleeves were live for much of the backtest — B non-zero on **51.4 %** of 28,079 rows (last non-zero ≈ **2025-10-30**), A1 on **57.0 %** (last non-zero ≈ **2025-11-09**) — and each went flat and stayed flat: long-only sleeves correctly sitting out a sustained downtrend, with B behind the 200-day SMA gate `docs/research/13.phase5-holdout-ledger.md` already records as off. What no document recorded is the compound consequence for the live book's composition, so it is registered as [[T0124]] (commit `4de6b0eb`) — a go/no-go input for the owner, not a measurement residual.

**Both identity guards were proven to bite on real data, with distinct messages** (`stage identity broken` vs `replay disagrees with the journal`), so a self-consistent rebuild of a book the engine never traded cannot pass as agreement; the clean 136-cycle run exits 0 with no cycle skipped — a record that fails to replay is named and counted, never dropped, so no aggregate is ever computed over a quietly smaller window.

**Handed to [[T0116]]** in this same change: **5.371 %** median final gross is the expected-gross parameter for rungs 2–3, with the chain that produces it, so the ladder's placeability arithmetic rests on a measured number instead of the naive one.
