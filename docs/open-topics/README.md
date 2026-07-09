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

- [T0011 — A2 refinements: 4h band, breakout-hold, 2026 probe](T0011-a2-refinements.md) — the parked A2 follow-ups; they spend reserved A-family trials (ripe when: T0009 resolved).
- [T0012 — 15m bars + tick storage for Bucket-B](T0012-15m-tick-storage-bucket-b.md) — split out of archived T0004's buried deferral (ripe when: first B1 intraday iteration).
- [T0014 — captured-spread cost calibration](T0014-captured-spread-cost-calibration.md) — the cost model's missing spread term from T0003's L2 capture (ripe when: ≥2 weeks captured + synced copy, ≈2026-07-22).
- [T0015 — registry per-schema-version key-set validation](T0015-registry-key-set-validation.md) — close the unknown-key acceptance class found by the v3 review; hardening, not a live hole (ripe when: next registry-hardening iteration).
- [T0016 — Bucket-B/C alpha families](T0016-bucket-b-c-alpha-families.md) — the un-started remainder of the §5 queue (B1/B2/B3/B4, C1–C3; budgets B=25/C=10), registered at the Phase-4 close (ripe when: per-family prerequisites — T0009 protocol legs, T0012 substrate, captured L2 for C1).
- [T0017 — holdout window ratification](T0017-holdout-window-ratification.md) — the pre-registered "final 12 months at data freeze" holdout was never carved out and is in-sample everywhere; the human ratifies the clean out-of-time window at the Phase-5 holdout event (ripe when: that event, D3(v)).

### Partially done<a name="partially-done"></a>

- [T0009 — Phase-4/5 validation-protocol decisions](T0009-validation-protocol-decisions.md) — the human decision sheet from the A1/A2/benchmark arcs: the deployable bar is **decided** (2026-07-09: **B3+vt-dynamic adopted** as the frozen benchmark); remaining: worst-slice leg, evaluation window, net-of-cost SPA, DSR threshold, A1-long/flat disposition, trial resumption (ripe when: next attended protocol review).

### Resolved<a name="resolved"></a>

- [T0002 — universe liquidity-floor calibration & quote-currency volume](archive/T0002-universe-liquidity-floor-calibration.md) — resolved in iter-007: EUR floor lowered €1M→€150k (footprint-based) + `quote_volume_in_eur` FX-normalizes the BTC-quoted legs → the full 12-name basket, `escalate=False`; findings recorded in master-plan §3.
- [T0001 — full-history OHLCVT backfill](archive/T0001-ohlcvt-full-history-backfill.md) — resolved in iter-008: built `cli/backfill/` (1-minute dumps → canonical 1h/4h/1d, base-authoritative merge); the full-history dataset (12 pairs, BTC 2013→2026) reconstructs OHLC bit-identical to the v0 REST (100% match).
- [T0006 — harness numeric-param type guards](archive/T0006-validation-numeric-param-type-guards.md) — resolved in iter-021: `isinstance(int|float)` guards on `cli/validation/` float params → `ValidationError` (not `TypeError`) on a non-numeric type; closed per defined scope (dsr `n_trials`/`n_obs` deliberately isfinite-only).
- [T0004 — full tick history + tick-derived bar reconciliation](archive/T0004-tick-history-reconciliation.md) — resolved in iter-044 (human-confirmed exit-bar): `cli/tick/` reconciles the full universe + full history at 100% coverage, 99.4–100% within 1% (the early-illiquid residual accepted), plus the true tick-weighted VWAP; 15m/tick-storage folded into the Bucket-B queue.
- [T0007 — dynamic-composition inverse-vol basket (full-history B2 variant)](archive/T0007-dynamic-composition-basket.md) — resolved in iter-044: built the look-ahead-free `dynamic_inverse_vol_basket` (2→10 majors over the full 2013→2026 union calendar) and answered finding-1 — the full-history basket is statistically indistinguishable from single-asset BTC (Sharpe ~1.1 both), so the fixed-window "basket loses" was a window artifact; a co-equal viable base for A1.
- [T0010 — full-history dynamic benchmark B3/B4](archive/T0010-dynamic-benchmark-b3-b4.md) — resolved in iter-055: self-gated dynamic B3/B4 built with full QA; B3+vt point-beats gated-B1 net-of-cost (1.245/1.278 vs 1.047/1.074, n.s., higher drawdown) → the deployable-bar choice escalated to T0009; the Phase-3 basket-cost carry-forward reconciled.
- [T0013 — trial-registry variant field](archive/T0013-registry-variant-field.md) — resolved in iter-056: schema_version 3 adds an optional first-class `variant` (hash-covered, omit-when-None); v2+v3 files co-load with the chain intact; budget counter untouched; adversarial review APPROVED (forge/torn-tail/concurrency probes).

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0005 — Blockpit T1 tax check](T0005-blockpit-t1-tax-check.md) — connect the Kraken depot read-only, verify import scope + historical labeling, write the T1 memo; human-gated on the Blockpit/depot authorize step (ripe when: an attended session authorizes the read-only depot connection).
- [T0008 — robust book-desync recovery](T0008-desync-recovery-robustness.md) — the iter-039 resubscribe fix heals on the common path but its single fire-and-forget attempt can still leave a pair stuck; add retry / ack-correlation / reconnect-escalation (ripe when: next attended capture-maintenance window, or on a recurrence).

### Partially done<a name="partially-done-1"></a>

- [T0003 — D2 forward-capture pipeline (VPS daemon → workstation sync → NAS)](T0003-d2-capture-pipeline.md) — capture daemon built + deployed LIVE on the hardened Debian 13 VPS (depth-100, CRC32-validated, healthchecks liveness; ≥7-day clock started iter-038); remainder = the workstation pull/NAS sync + alerting drill + the 7-day clean run (ripe when: the ≥7-day clock completes ≈2026-07-15 + an attended workstation/NAS session).

### Resolved<a name="resolved-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](archive/T0000-phase0-account-actions.md) — resolved in iter-023 (Phase-2 close-out): account actions + live confirmations done 2026-07-07; the deferred July-9 fee-schedule fold-in landed in iter-017 (`cli/costs/`).
