# Open topics

Topics worth follow-up are parked here, one file per topic. See `.claude/rules/open-topics.md` for the convention.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Research and development](#research-and-development)
  - [Open](#open)
  - [Partially done](#partially-done)
  - [Resolved](#resolved)
- [Live trading preparation](#live-trading-preparation)
  - [Open](#open-1)
  - [Partially done](#partially-done-1)
  - [Resolved](#resolved-1)

<!-- mdformat-toc end -->

## Research and development<a name="research-and-development"></a>

### Open<a name="open"></a>

- [T0004 — full tick history + tick-derived bar reconciliation](T0004-tick-history-reconciliation.md) — the tick-vs-OHLCVT tolerance test + true vwap; blocked on tick-data acquisition (not on NAS), deferred to Phase-4 microstructure / true-vwap need.
- [T0007 — dynamic-composition inverse-vol basket (full-history B2 variant)](T0007-dynamic-composition-basket.md) — the richer B2 that grows the basket 2→10 assets over BTC's full 2013→2026 calendar; parked in iter-030 to isolate the look-ahead-critical weighting from composition churn.

### Partially done<a name="partially-done"></a>

_(none)_

### Resolved<a name="resolved"></a>

- [T0002 — universe liquidity-floor calibration & quote-currency volume](archive/T0002-universe-liquidity-floor-calibration.md) — resolved in iter-007: EUR floor lowered €1M→€150k (footprint-based) + `quote_volume_in_eur` FX-normalizes the BTC-quoted legs → the full 12-name basket, `escalate=False`; findings recorded in master-plan §3.
- [T0001 — full-history OHLCVT backfill](archive/T0001-ohlcvt-full-history-backfill.md) — resolved in iter-008: built `cli/backfill/` (1-minute dumps → canonical 1h/4h/1d, base-authoritative merge); the full-history dataset (12 pairs, BTC 2013→2026) reconstructs OHLC bit-identical to the v0 REST (100% match).
- [T0006 — harness numeric-param type guards](archive/T0006-validation-numeric-param-type-guards.md) — resolved in iter-021: `isinstance(int|float)` guards on `cli/validation/` float params → `ValidationError` (not `TypeError`) on a non-numeric type; closed per defined scope (dsr `n_trials`/`n_obs` deliberately isfinite-only).

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0003 — D2 forward-capture pipeline (VPS daemon → workstation sync → NAS)](T0003-d2-capture-pipeline.md) — the hard Phase-1 exit-bar gate (≥7-day clean capture + verified sync); human-gated on VPS provisioning, then autonomous.
- [T0005 — Blockpit T1 tax check](T0005-blockpit-t1-tax-check.md) — connect the Kraken depot read-only, verify import scope + historical labeling, write the T1 memo; human-gated on the Blockpit/depot authorize step.

### Partially done<a name="partially-done-1"></a>

_(none)_

### Resolved<a name="resolved-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](archive/T0000-phase0-account-actions.md) — resolved in iter-023 (Phase-2 close-out): account actions + live confirmations done 2026-07-07; the deferred July-9 fee-schedule fold-in landed in iter-017 (`cli/costs/`).
