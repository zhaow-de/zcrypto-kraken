---
status: resolved
---

# T0210 — soak-check's gating verdicts have no scheduled reader, so an inconsistent one reaches nobody

## Context — what

`zcrypto engine soak-check` renders a structural fingerprint of the live book against a backtest null and files a verdict per metric in `gating_verdicts` — `gross`, `net`, `active_frac`, `turnover`, `hhi`, `governor_engagement`, `cap_breach`. Nothing runs that command on a schedule: there is no timer, no systemd unit, no CI job and no ops-role invocation anywhere under `infra/` or `.github/`, and `infra/scripts/ops_daily.py` does not read it. Nothing outside `cli/engine/soak.py` consumes a verdict either. The command is hand-run, so a verdict is seen only when a person chooses to look, and an `inconsistent` verdict between two hand-runs reaches no one at all.

## Why this matters

The metric is called *gating* and gates nothing. Today that is cheap: the engine is disarmed, has submitted zero orders, and the "live book" the fingerprint scores is a shadow. Once the engine is armed the same unread verdict is a statement about a book holding real money, and the gap stops being free at exactly the moment nobody is watching for it.

It also disables two other topics' triggers. [[T0184]] is ripe when a soak-check run reports a non-zero realized no-book bar count or an hhi verdict other than `consistent`, and [[T0201]] when a run renders `window_bound : store` with an off-boundary store last bar. Both are evaluation statements over a command no schedule runs, so `zcrypto-daily-ops` can only ever name them unevaluated. A trigger whose evaluation nobody performs is a deferral with no reader, which is the failure the topic register exists to prevent.

## Findings so far

- **The readership gap was measured, not inferred.** At registration `grep -rn "soak-check\|soak_check"` over `infra/` and `.github/` returned exactly one hit, and it was not an invocation: `infra/scripts/ops_daily.py` listed `soak-check` among the `zcrypto engine <sub>` shapes the daily pass will CLASSIFY as a read. `grep -rn "gating_verdicts" cli/` outside tests returned only `cli/engine/soak.py` itself, where the dict is built and rendered. The metric is thoroughly unit-tested in `tests/test_engine_soak.py` — its computation is not in question, only who reads the answer.
- **The gap was surfaced by a live `inconsistent`, and that reading is NOT itself evidence of a defect.** A run on 2026-09-18 against the NAS journal and a store pulled from the engine host returned `governor_engagement` `inconsistent`: live `1.0000` against a median `0.8571` and a band `[0.0000,1.0000]` at the 100th percentile. The report's own line reads `1 of 7 outside band (~0.7 expected by chance at 90%)`, so one exceedance is the expected count, and its disclosure adds that only one null construction discriminated at all (`primary='n/a'`, `secondary='inconsistent'`). **What is registered here is that no reader exists, never that this particular verdict is wrong.** Two further disclosures bound it: governor engagement is judged at day granularity over 70 realized days, and that granularity is exact rather than approximate because the multiplier is constant within a day by construction.
- **The same run reported every other metric `consistent`**, the self-tests `ok`, `realized no-book bars : 0 of 419`, and `window_bound` as `journal` with the store's last bar on a 4h boundary, so neither [[T0184]]'s nor [[T0201]]'s trigger fires today. That is the evaluation those two triggers ask for, performed by hand — which is the point of this topic.

## Resolution

Resolved by PR #572 under spec `00115` and its plan. `ops-daily.py report` now prints a `soak verdict` row: `read_soak_verdict` in `infra/scripts/ops_daily.py` runs `soak-check` over a store derived from the newest journaled 240 snapshots and reduces the payload to `PASS`, `FAIL` or `unreadable`, reading `void_reasons` before any verdict and failing on the panel's outside count at a PROVISIONAL three, on a panel that left fewer than three metrics decided, or on a scored window that is not current, never on one metric's `inconsistent`. The daily pass is therefore the scheduled reader, sited on the workstation, with no timer, no host change and no store replica. The three shapes this topic listed are costed in the spec's Alternatives tables; the metric with an alert rule is what paging between passes would cost, and the spec leaves it out of scope.

The last next step — re-read `governor_engagement` once the null has power — is dropped as a separate action: the row names every outside metric, and how many null constructions called it, on every pass, so the re-read happens daily and needs no trigger of its own. [[T0184]]'s two operands are printed by the same row; [[T0201]]'s trigger cannot be evaluated from a journal-derived store; both topics record that. The reading `zcrypto-daily-ops` owes the row landed with it, as the paragraph on the `soak verdict` row under that skill's `## 4. Read the dashboards numerically`.
