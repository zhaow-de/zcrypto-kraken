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

- [T0012 — 15m bars + tick storage for Bucket-B](T0012-15m-tick-storage-bucket-b.md) — split out of archived T0004's buried deferral (ripe when: first B1 intraday iteration).
- [T0014 — captured-spread cost calibration](T0014-captured-spread-cost-calibration.md) — the cost model's missing spread term from T0003's L2 capture (ripe when: ≥2 weeks captured + synced copy, ≈2026-07-22).
- [T0016 — Bucket-B/C alpha families](T0016-bucket-b-c-alpha-families.md) — the un-started remainder of the §5 queue (B1/B2/B3/B4, C1–C3; budgets B=25/C=10), registered at the Phase-4 close (ripe when: per-family prerequisites — T0009 protocol legs, T0012 substrate, captured L2 for C1).

### Partially done<a name="partially-done"></a>

### Resolved<a name="resolved"></a>

- [T0002 — universe liquidity-floor calibration & quote-currency volume](archive/T0002-universe-liquidity-floor-calibration.md) — resolved in iter-007: EUR floor lowered €1M→€150k (footprint-based) + `quote_volume_in_eur` FX-normalizes the BTC-quoted legs → the full 12-name basket, `escalate=False`; findings recorded in master-plan §3.
- [T0001 — full-history OHLCVT backfill](archive/T0001-ohlcvt-full-history-backfill.md) — resolved in iter-008: built `cli/backfill/` (1-minute dumps → canonical 1h/4h/1d, base-authoritative merge); the full-history dataset (12 pairs, BTC 2013→2026) reconstructs OHLC bit-identical to the v0 REST (100% match).
- [T0006 — harness numeric-param type guards](archive/T0006-validation-numeric-param-type-guards.md) — resolved in iter-021: `isinstance(int|float)` guards on `cli/validation/` float params → `ValidationError` (not `TypeError`) on a non-numeric type; closed per defined scope (dsr `n_trials`/`n_obs` deliberately isfinite-only).
- [T0004 — full tick history + tick-derived bar reconciliation](archive/T0004-tick-history-reconciliation.md) — resolved in iter-044 (human-confirmed exit-bar): `cli/tick/` reconciles the full universe + full history at 100% coverage, 99.4–100% within 1% (the early-illiquid residual accepted), plus the true tick-weighted VWAP; 15m/tick-storage folded into the Bucket-B queue.
- [T0007 — dynamic-composition inverse-vol basket (full-history B2 variant)](archive/T0007-dynamic-composition-basket.md) — resolved in iter-044: built the look-ahead-free `dynamic_inverse_vol_basket` (2→10 majors over the full 2013→2026 union calendar) and answered finding-1 — the full-history basket is statistically indistinguishable from single-asset BTC (Sharpe ~1.1 both), so the fixed-window "basket loses" was a window artifact; a co-equal viable base for A1.
- [T0010 — full-history dynamic benchmark B3/B4](archive/T0010-dynamic-benchmark-b3-b4.md) — resolved in iter-055: self-gated dynamic B3/B4 built with full QA; B3+vt point-beats gated-B1 net-of-cost (1.245/1.278 vs 1.047/1.074, n.s., higher drawdown) → the deployable-bar choice escalated to T0009; the Phase-3 basket-cost carry-forward reconciled.
- [T0013 — trial-registry variant field](archive/T0013-registry-variant-field.md) — resolved in iter-056: schema_version 3 adds an optional first-class `variant` (hash-covered, omit-when-None); v2+v3 files co-load with the chain intact; budget counter untouched; adversarial review APPROVED (forge/torn-tail/concurrency probes).
- [T0015 — registry per-schema-version key-set validation](archive/T0015-registry-key-set-validation.md) — resolved in iter-062: exact key-set per schema version (15 base keys, v3 ± `variant`); surplus or missing key = corruption; the chain-consistent "variannt" forge now fails on this check alone; adversarial review PASS.
- [T0009 — Phase-4/5 validation-protocol decisions](archive/T0009-validation-protocol-decisions.md) — resolved in iter-072 (attended review, 2026-07-09): all six legs decided — benchmark-relative + stub-excluded worst-slice, k≥230 decisive window, net-of-cost SPA, DSR 0.95, A1-lf weekly v0.12 admitted (trial 34), A-family resumption; folded into `a1_kill_bar`.
- [T0017 — holdout window ratification](archive/T0017-holdout-window-ratification.md) — resolved in iter-073 (attended): window ratified (out-of-time 2026-04-01 → freeze), the look executed same night (degenerate gate-off window, reading **EQUALS**), ledger created, budget → 0.
- [T0011 — A2 refinements](archive/T0011-a2-refinements.md) — resolved in iter-080: the 2026 probe, the 4h arms (three adopts), the cadence sweep (family closed 40/40), and finally the cross-frequency P1 trial — **trial 43 ADOPT** (governed 1.5366, all ratified legs) — the combination supersedes record 33 as the deployable candidate (Phase-6 scope → T0018).
- [T0019 — P1 fixed-weight combination variant](archive/T0019-p1-fixed-weight-variant.md) — resolved in iter-081 (same session): the pre-registered fixed-⅓ trial — **trial 44 ADOPT** (1.5609, SPA grid max p 0.0060, all legs) — supersedes trial 43 as the deployable candidate and deletes the adaptive-weight mechanism from the Phase-6 engine's scope.

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0005 — Blockpit T1 tax check](T0005-blockpit-t1-tax-check.md) — connect the Kraken depot read-only, verify import scope + historical labeling, write the T1 memo; human-gated on the Blockpit/depot authorize step (ripe when: Stage 6b starts — the T1 connection rides alongside the §11 T2 probe window, per spec 00039).
- [T0008 — robust book-desync recovery](T0008-desync-recovery-robustness.md) — the iter-039 resubscribe fix heals on the common path but its single fire-and-forget attempt can still leave a pair stuck; add retry / ack-correlation / reconnect-escalation (ripe when: next attended capture-maintenance window, or on a recurrence).
- [T0018 — Phase-6 build sequence](T0018-phase6-build-sequence.md) — the kickoff roadmap (shadow engine → deployment → 6b executor) with its cross-iteration constraints: the 00038 verdict LANDED (trials 43+44 adopted → the engine builds against the fixed-weight 4h cross-frequency combination, record 44), §8 hardening verified before the trade key lands, and the full 6b-executor scope incl. the D3(iii) T2 tax-probe set (ripe when: the shadow-engine iteration — next attended session — is brainstormed).

### Partially done<a name="partially-done-1"></a>

- [T0003 — D2 forward-capture pipeline (VPS daemon → workstation sync → NAS)](T0003-d2-capture-pipeline.md) — capture daemon built + deployed LIVE on the hardened Debian 13 VPS (depth-100, CRC32-validated, healthchecks liveness; ≥7-day clock started iter-038); remainder = the workstation pull/NAS sync + alerting drill + the 7-day clean run (ripe when: the ≥7-day clock completes ≈2026-07-15 + an attended workstation/NAS session).

### Resolved<a name="resolved-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](archive/T0000-phase0-account-actions.md) — resolved in iter-023 (Phase-2 close-out): account actions + live confirmations done 2026-07-07; the deferred July-9 fee-schedule fold-in landed in iter-017 (`cli/costs/`).
