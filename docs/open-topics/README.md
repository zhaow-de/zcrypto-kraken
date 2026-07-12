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

- [T0014 — captured-spread cost calibration](T0014-captured-spread-cost-calibration.md) — the cost model's missing spread term from T0003's L2 capture (ripe when: ≥2 weeks captured + synced copy, ≈2026-07-22).
- [T0022 — B1 intraday seasonality family](T0022-b1-intraday-seasonality-family.md) — split from T0016 when its prerequisites fired; conditioning-overlay trials on the adopted A2-4h ensemble against the 15m substrate, net-of-cost per T0009 (ripe when: live now — trials ride research iterations).
- [T0024 — universe spread-cap criterion](T0024-universe-spread-cap-criterion.md) — add the pending `spread_cap` filter to universe selection once captured L2 exists; shares T0014/T0003's L2 dependency (ripe when: synced L2 copy, ≈2026-07-22).
- [T0025 — full symbol & corporate-action ledger](T0025-full-corporate-action-ledger.md) — extend iter-002's alias ledger to a full point-in-time record (redenominations, migrations, delistings) for survivorship (ripe when: a universe pair has a corporate action, or before a live-trading universe refresh).

### Partially done<a name="partially-done"></a>

- [T0023 — B2 derivatives-positioning data sourcing](T0023-b2-derivatives-data-sourcing.md) — funding substrate delivered (iter-090); liquidations-source decided (option a, free live-only); the OI backfill + harness are autonomous when B2 is picked.

- [T0016 — Bucket-B/C alpha families](T0016-bucket-b-c-alpha-families.md) — the §5 queue umbrella, now partial: B1 split out to T0022 (iter-086); remainder = B2/B3/B4, C1–C3 (budgets B=25 shared/C=10) with per-family prerequisites in the frontmatter.

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
- [T0012 — 15m bars + tick storage for Bucket-B](archive/T0012-15m-tick-storage-bucket-b.md) — resolved in iter-085: `data/ohlc-15m/` built from the 1m dumps via `cli/backfill` (basket 0fed24a6…), tick-reconciled bit-exact + count-proven seam; tick catalog explicitly dropped (re-opens under C2/C1).

## Live trading preparation<a name="live-trading-preparation"></a>

### Open<a name="open-1"></a>

- [T0005 — Blockpit T1 tax check](T0005-blockpit-t1-tax-check.md) — connect the Kraken depot read-only, verify import scope + historical labeling, write the T1 memo; human-gated on the Blockpit/depot authorize step (ripe when: Stage 6b starts — the T1 connection rides alongside the §11 T2 probe window, per spec 00039).
- [T0008 — robust book-desync recovery](T0008-desync-recovery-robustness.md) — the iter-039 resubscribe fix heals on the common path but its single fire-and-forget attempt can still leave a pair stuck; add retry / ack-correlation / reconnect-escalation (ripe when: next attended capture-maintenance window, or on a recurrence).
- [T0021 — VPS journal retention](T0021-vps-journal-retention.md) — prune-after-verified-pull design for the append-only engine journal (~0.35 GiB/month measured) (ripe when: the 80% disk watermark — T0020's disk alert is the trigger mechanism — or an earlier attended ops window).
- [T0026 — reconnect trade-snapshot overwrite](T0026-reconnect-trade-snapshot-overwrite.md) — on a full WS reconnect the trade snapshot silently overwrites already-finalized past-hour trade segments (manifest regenerated, so hash-invisible); books unaffected, trades REST-backfillable (ripe when: next attended capture-maintenance window; loss-quantification is autonomous now).
- [T0028 — NAS pull re-hashes the whole archive](T0028-nas-pull-incremental-verify.md) — Role A's `verify_tree` sha256-re-verifies the entire (unbounded) archive every hourly cycle → O(archive) per cycle, stalls the loop in ~2 months; verify only rsync-transferred files instead (ripe when: the verify sweep approaches the pull interval, ~250–600 GB in).

### Partially done<a name="partially-done-1"></a>

- [T0003 — D2 forward-capture pipeline (VPS daemon → NAS archive)](T0003-d2-capture-pipeline.md) — capture daemon built + deployed LIVE on the hardened Debian 13 VPS (depth-100, CRC32-validated, healthchecks liveness; ≥7-day clock started iter-038); the NAS pull/archive (Role A of the three-tier model) landed iter-093 (spec/plan 00048); remainder = the alerting drill + the ≥7-day clean-run verification + Roles B/C (gate-verify + redundant capture) (ripe when: the ≥7-day verification ≈2026-07-15 and the alerting drill).

- [T0018 — Phase-6 build sequence](T0018-phase6-build-sequence.md) — the kickoff roadmap with its cross-iteration constraints; builder + concordance core (iter-082), the shadow node + workstation soak (iter-083), and the VPS deployment (iter-084, gate clock ticking since 2026-07-11 00:00 UTC) all landed; remainder = the 6b executor (ripe when: the Stage-6a gate is met — ≥ 14 consecutive clean complete-UTC days — and the human convenes the 6b session).

- [T0020 — Grafana Cloud observability](T0020-grafana-cloud-observability.md) — Alloy + socket proxy ship both containers' logs + OS/container/app metrics to the provisioned Grafana Cloud instance, one committed dashboard, API-provisioned email alerts; the human credential fetch + vault is DONE (2026-07-11), remaining = the autonomous Tasks 1–3 build + the attended Task 4 deploy (ripe when: an observability build+deploy session; capture exporter flip additionally after the ≥7-day clock ≈ 2026-07-15).

- [T0027 — unattended auto-reboot policy](T0027-unattended-reboot-policy.md) — unattended-upgrades auto-reboots the VPS at 04:00 UTC on kernel updates (2026-07-11: both containers recovered clean, ~83 s capture gap, engine day-1 gate cycle verified intact — the 04:00 cycle re-ran and replays bit-identical); remaining = the human ops-policy decision + confirming order-state reconciliation survives a mid-order-submission reboot before live 6b (ripe when: before the Stage-6b executor session, or on the next disruptive auto-reboot).

- [T0029 — NAS CPU has no AVX; polars crashes](T0029-nas-cpu-no-avx-polars.md) — the Atom Goldmont NAS can't run the AVX-compiled polars; resolved via two image variants (VPS keeps AVX `polars-runtime-32` untouched; NAS gets an amd64 `-compat` build with `polars-runtime-compat`, same polars 1.42.1 — `polars-lts-cpu` is deprecated, `rtcompat` is the replacement); remaining = Role B's cross-runtime replay determinism (ripe when: before Role B / Increment 2).

### Resolved<a name="resolved-1"></a>

- [T0000 — Phase 0 human account actions & live-account confirmations](archive/T0000-phase0-account-actions.md) — resolved in iter-023 (Phase-2 close-out): account actions + live confirmations done 2026-07-07; the deferred July-9 fee-schedule fold-in landed in iter-017 (`cli/costs/`).
