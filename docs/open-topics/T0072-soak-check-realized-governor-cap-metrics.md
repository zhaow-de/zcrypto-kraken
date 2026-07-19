---
status: open
ripe_when: the soak-check gate produces populated verdicts (L >= floor) and the governor/cap fingerprint is wanted as a realized-vs-backtest comparison rather than backtest-only context
---

# soak-check: realized governor-engagement + cap-breach as real comparisons (currently backtest context only)

## Context — what

`zcrypto engine soak-check` (spec `00058`) gates its verdict on **five** position-derived structural metrics computed from the journaled `final_targets` (the traded weights): gross exposure, net exposure, active fraction, per-cycle turnover, and concentration (HHI). The spec's other two metrics — **governor-engagement rate** and **cap-breach rate** — are reported only as **null-side backtest context** (from the frozen build's `multipliers` / `cap_breach_bars`), *not* as a realized-vs-backtest comparison.

The reason is a data limitation: the journal stores `final_targets = mult x capped` (the post-governor, post-cap product), not the strategy internals a realized governor/cap metric needs:

- **cap-breach** is undetectable from `final_targets`: since `mult <= 1` and `capped <= cap`, `final_targets <= cap` on every bar, so a cap-breach metric computed from the traded weights is trivially always 0.
- **governor-engagement** needs the per-bar multiplier `mult[k]`, which the journal does not store separately.

## Why this matters

The governor and the cap layer are §10 risk machinery; whether they engage OOS the way the backtest predicts is genuinely informative (e.g. the governor throttling far more OOS than in-sample is a regime signal). With only backtest-side context, the soak-check can't say whether the *realized* governor/cap behaviour is consistent with expectation — it covers 5 of the 7 spec metrics as real comparisons. Closing this makes the structural fingerprint complete.

## Findings so far

- soak-check v1 (PR #154, spec/plan `00058`): 5 gating metrics + governor/cap as backtest context; the decision and its rationale are recorded in the phase-6 decisions/ledger and the PR description.
- The realized multipliers + cap-breaches **are** recoverable: building `build_crossfreq_system_fast` on the **latest journal record's snapshots** (authoritative, hash-verified, containing the full history through that cycle) yields `multipliers` / `day_index` / `sleeve_positions` for every bar including the realized window — one build, sliced by timestamp to the scored cycles. The concordance identity self-test already confirms such a rebuild reproduces the journaled `final_targets`.
- `cli/engine/soak.py` already has `governor_engaged_daily(mult, day_index)` and the `apply_position_caps`-based capped reconstruction (`_net_live_from_result`) needed to derive per-bar cap-breach — the pieces exist; only the realized-side build + window-slice + two extra gating verdicts are missing.

## Suggested next steps

- **(Autonomous)** Add a `realized_internals(latest_record, snapshot_reader)` that builds on the latest journal snapshot and returns per-bar `multipliers` + per-bar cap-breach flags keyed by timestamp; slice to the scored realized window. Guard it with the same timestamp-keyed discipline (and an off-by-one cross-check) as the forward-return join in `realized_series`, and VOID on any window/asset-set mismatch.
- **(Autonomous)** Extend `analyze_soak` to compute realized governor-engagement (day granularity, effective-n ≈ days) and realized cap-breach rate, judge each against the null distribution, and promote them from context to gating verdicts (7 gating metrics). Update the report table + the panel multiplicity count.
- **(Autonomous)** Add tests: the realized-internals rebuild reproduces the journaled `final_targets` (identity), the governor/cap verdicts discriminate (planted-consistent / planted-inconsistent), and the window-slice is off-by-one-safe.
