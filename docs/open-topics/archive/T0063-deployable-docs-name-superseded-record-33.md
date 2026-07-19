---
status: resolved
---

# The deployable-system docs name the superseded record 33, not the actual deployable (trial 44)

## Context — what

The Phase-6 execution engine is built against **registry record 44** — the P1 cross-frequency system (`build_crossfreq_system_fast`, `cli/portfolio/crossfreq_system.py`), three sleeves (daily basket + daily-derived weekly + native-4h Donchian ensemble) at fixed 1/3 weights on the 4h union calendar, `dataset_hash 45275ebe…` over the daily||4h manifests. But several committed docs still name the **superseded record 33** (daily-only, `build_combined_system`, `dataset_hash ba47e37e…`) as the deployable:

- `docs/research/13.phase5-closeout.md` — "The deployable system is registry record 33".
- `docs/research/12.phase5-system-spec-runbook.md` — the Final-system-spec **body** (line ~39) pins record 33's dataset (`ba47e37e`, daily, 2013-09-10 → 2026-03-31); only the top record-44 **update** section reflects the supersession.
- `docs/specs/00039-phase6-kickoff-design.md` — decision-5 prose still says the engine "runs the pure function `cli.portfolio.build_combined_system`"; the switch to `build_crossfreq_system` is only in the line-31 amendment ([iter-082], 2026-07-10).

The supersession chain: record 33 (Phase-5 exit deployable) → trial 43 (iter-080, adaptive weights) → trial 44 (iter-081, fixed 1/3). Records 43/44 are Phase-6 iterations, after the Phase-5 closeout was written — so the closeout never saw them.

## Why this matters

The deployable's **true identity and dataset_hash (`45275ebe`) appear only in the registry** and the runbook's record-44 update section — never restated in the closeout or the runbook/spec bodies. A reader (human or a future session) consulting the natural sources — the phase closeout, the runbook body, the kickoff spec — is told the wrong system (record 33), the wrong builder (`build_combined_system`), and the wrong dataset (`ba47e37e` daily-only vs the real `45275ebe` daily+4h). Provenance drift on the one artifact that must be unambiguous: what actually deploys. The live code (`cli/engine/cycle.py:353` calls `build_crossfreq_system_fast`) is the only unambiguous witness.

## Findings so far

- Live code is correct and runs trial 44 (`cli/engine/cycle.py:353`, `cli/portfolio/crossfreq_system.py`). Spec 00040 correctly describes the record-44 builder. So this is a **doc-consistency** defect, not a code defect.
- The stale pins: `13.phase5-closeout.md`, `12.phase5-system-spec-runbook.md` body (~line 39), `docs/specs/00039-phase6-kickoff-design.md` decision-5 prose.
- Trial 44 spec_hash `a25d7102…` (pins spec 00038 + its iter-080 execution-precision amendments); dataset_hash `45275ebe…` = `sha256(daily-manifest ba47e37e ‖ 4h-manifest 81dc9b44)`, span 2013-09-10 → 2026-03-31, 10 EUR pairs.
- Related lesson already logged ([iter-085]): hash the spec after any execution-time amendment (records 34/35 carry the pre-amendment spec_hash). This topic is the deployable-identity analogue of that drift.

## Resolution (2026-07-19)

All three prescriptions delivered in one docs pass: dated inline supersession pointers at every stale site — `13.phase5-closeout.md` (the exit-deployable sentence + the `build_combined_system` build-target line), `00039-phase6-kickoff-design.md` (decision-5 prose + the non-goals record-33 line) — plus a **one-lookup "Current deployable" line** atop `12.phase5-system-spec-runbook.md` (record 44 · `build_crossfreq_system_fast` · `dataset_hash 45275ebe…` = daily `ba47e37e` ‖ 4h `81dc9b44`) and a historical-pin note on the runbook body's `ba47e37e` dataset line. Historical narratives marked in place, never rewritten; the registry stays the source of truth.

## Suggested next steps

- Reconcile the deployable's identity across the three stale docs: add a dated supersession pointer at each (matching the T0003/T0032 inline-correction style) naming **trial 44 / `build_crossfreq_system` / `dataset_hash 45275ebe` / daily+4h** as the current deployable, so a reader landing on the closeout or runbook body is not misled. Keep the registry (record 44) as the single source of truth and point the prose at it.
- Do NOT rewrite the historical closeout narrative — mark the superseded claim in place (the Phase-5 closeout was correct as of Phase-5 exit; the supersession is a Phase-6 event).
- Consider a one-line "current deployable" pointer in a durable, re-read location (e.g. the runbook's top) so the answer to "what deploys?" is one lookup, not a registry archaeology.
