---
status: resolved
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

## Resolution — 2026-07-20 (iter-108, spec 00059)

Both metrics are now real realized-vs-backtest **gating** comparisons; the fingerprint is 7 metrics. The unlock was that the journal is its own evidence: each cycle record's 240 snapshot carries the full hash-verified price history, so ONE `build_crossfreq_system_fast` rebuild on the latest record yields per-bar multipliers and sleeve positions for every scored cycle — no live-store dependency. Alignment (`h4_ts[k] == T - 4h`, timestamp-keyed) is proven window-wide by a `final_targets` identity that VOIDs on any shift; measured on the real 55-cycle journal at **worst |diff| = 0.0** across 54 cycles x 10 assets, with per-bar cap-breach agreeing with the builder's own diagnostic (**1318 == 1318**).

Two findings came out of running it for real, both recorded as spec `00059` decisions rather than code comments:

- **D8** — a band spanning a metric's whole attainable domain is `n/a`, not "consistent". The first live run gave `governor_engagement` band `[0.0, 1.0]`: nothing could ever fall outside it, so the verdict was vacuous *and* it inflated the multiplicity denominator. `metric_verdict` already escaped a zero-width band; a full-width band is the same failure inverted.
- **D9** — judge a window statistic against the distribution of same-length window statistics, never the null's global mean. Reading the realized governor rate (1.0) against the global 0.266 suggested a divergence; the correct windowed comparison shows the backtest reaches 100% engagement often enough that p95 = 1.0, so it is unremarkable. **Not a divergence.**

Consequently `governor_engagement` currently renders `n/a` (no discriminating power at a 9-day window) with the reason disclosed — an honest outcome, not a gap in this work. Remaining soak-check scope lives in [[T0073]] (secondary block-bootstrap null + `--null`/`--path` + regime context).
