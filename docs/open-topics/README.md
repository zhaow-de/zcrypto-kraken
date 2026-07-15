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

- [T0043 — a genuinely lost trades file is invisible when its book sibling survives](T0043-lost-trades-file-with-surviving-book-is-invisible.md) — the `total_loss` fix judges an absent trades hour against its pair's book hour (a quiet pair really does go an hour without a print), which trades a demonstrated false **positive** for a theoretical false **negative**: a trades segment lost on BOTH mirrors while its book survives is now silent, and no other signal in the stack would catch it — continuity.py is book-only by design, and the manifests only verify files that exist (ripe when: any such absence is ever observed, or before the overlay feeds a production consumer).

### Partially done<a name="partially-done"></a>

- [T0023 — B2 derivatives-positioning data sourcing](T0023-b2-derivatives-data-sourcing.md) — funding substrate delivered (iter-090); liquidations-source decided (option a, free live-only); the OI backfill + harness are autonomous when B2 is picked.

- [T0016 — Bucket-B/C alpha families](T0016-bucket-b-c-alpha-families.md) — the §5 queue umbrella, now partial: B1 split out to T0022 (iter-086); remainder = B2/B3/B4, C1–C3 (budgets B=25 shared/C=10) with per-family prerequisites in the frontmatter.

- [T0044 — correcting the reconcile ledger resets the counters](T0044-reconcile-ledger-correction-resets-counters.md) — the reconcile counters are summed from an append-only ledger, so a correction/rebuild reads as a reset; the two `increase()` rules are guarded with `resets()==0` so it can't false-page, and the correction **runbook is now written** (`infra/nas/README.md`); still open: a correction marker + the O(ledger) rotation design (ripe when: the ledger needs another correction, or the ~17-min Atom cycle slows).

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

- [T0021 — VPS journal retention](T0021-vps-journal-retention.md) — prune-after-verified-pull design for the append-only engine journal (~0.35 GiB/month measured) (ripe when: the 80% disk watermark — the NAS Alloy `/volume1` disk-free alert (T0020) is the trigger mechanism, now live (provisioned) — or an earlier attended ops window).

- [T0026 — reconnect trade-snapshot overwrite](T0026-reconnect-trade-snapshot-overwrite.md) — on a full WS reconnect the trade snapshot silently overwrites already-finalized past-hour trade segments (manifest regenerated, so hash-invisible); books unaffected, trades REST-backfillable (ripe when: next attended capture-maintenance window; loss-quantification is autonomous now).

- [T0028 — NAS pull re-hashes the whole archive](T0028-nas-pull-incremental-verify.md) — Role A's `verify_tree` sha256-re-verifies the entire (unbounded) archive every hourly cycle → O(archive) per cycle; verify only rsync-transferred files instead (ripe when: the verify sweep approaches the pull interval, ~250–600 GB in — now ~1–2 years out, since the real growth is 0.48 GB/day, not the 10 GB/day the estimate assumed; see T0032).

- [T0039 — the reconciler's `--min-gap-seconds` needs cross-host validation](T0039-min-gap-seconds-needs-cross-host-validation.md) — spec 00050's 5 s default sits **below the measured 14.78 s maximum natural quiescence**, so on a quiet market only an untested assumption about Kraken's per-connection coalescing prevents a phantom splice (an unaudited data swap that inflates `healed_gap_seconds` and blinds the very alert meant to spot a degrading primary); raise the default to 30 s and pin it from a detect-only soak (ripe when: the secondary is live — the measurement needs two concurrent streams, which do not exist yet).

- [T0042 — Alloy holds root-equivalent Docker access (accepted)](T0042-alloy-holds-root-equivalent-docker-access.md) — the GET-only `docker-socket-proxy` was removed on 2026-07-14 (it was severing Docker's long-lived log stream every 10 min and duplicating every line into Loki forever), so Alloy now talks to the socket directly; the Docker API is root-equivalent regardless of the `:ro` mount, and the NAS holds the rrsync keys to the capture VPS — deliberately accepted, with the two-line fix that would restore the boundary recorded (ripe when: before go-live, or before this stack ships to a capture host).

### Partially done<a name="partially-done-1"></a>

- [T0003 — D2 forward-capture pipeline (VPS daemon → NAS archive)](T0003-d2-capture-pipeline.md) — capture daemon built + deployed LIVE on the hardened Debian 13 VPS (depth-100, CRC32-validated, healthchecks liveness; ≥7-day clock started iter-038); the NAS pull/archive (Role A) landed iter-093 (spec/plan 00048), NAS gate-verify (Role B) landed iter-094 (spec/plan 00049, measured bit-identical cross-runtime); remainder = the alerting drill + the ≥7-day clean-run verification + Role C (redundant capture) (ripe when: the ≥7-day verification ≈2026-07-15 and the alerting drill).

- [T0018 — Phase-6 build sequence](T0018-phase6-build-sequence.md) — the kickoff roadmap with its cross-iteration constraints; builder + concordance core (iter-082), the shadow node + workstation soak (iter-083), and the VPS deployment (iter-084, gate clock ticking since 2026-07-11 00:00 UTC) all landed; remainder = the 6b executor (ripe when: the Stage-6a gate is met — ≥ 14 consecutive clean complete-UTC days — and the human convenes the 6b session).

- [T0020 — Grafana Cloud observability](T0020-grafana-cloud-observability.md) — the canonical dashboard, alert rules, push script, and creds path landed via iter-094's NAS build (spec 00049), and the dashboard/alerts are now provisioned live (dashboard + 7 rules + `email` contact point on `zcrypto2026.grafana.net`, verified); remaining = the VPS `obs` role + app `/metrics` exporters (spec 00043's original scope) + the capture exporter flip (ripe when: an observability build+deploy session; capture exporter flip additionally after the ≥7-day clock ≈ 2026-07-15).

- [T0027 — unattended auto-reboot policy](T0027-unattended-reboot-policy.md) — unattended-upgrades auto-reboots the VPS at 21:25 UTC on kernel updates (2026-07-11: both containers recovered clean, ~83 s capture gap, engine day-1 gate cycle verified intact — the 04:00 cycle re-ran and replays bit-identical); remaining = the human ops-policy decision + confirming order-state reconciliation survives a mid-order-submission reboot before live 6b (ripe when: before the Stage-6b executor session, or on the next disruptive auto-reboot).

- [T0032 — capture dies silently when the disk fills](T0032-capture-disk-watermark-silent-death.md) — a `DiskWatermark` breach stops all row writes but leaves the WS connected and no gap open, so the healthchecks.io dead-man kept pinging **green** while the unbackfillable L2 stream was lost; **the dead-man half is fixed** (ping withheld on breach, so it pages), the breach window is **now booked into the exit-bar gap accounting** (a dedicated `GapMonitor` watermark window, independent of the ping-withholding), and T0003's 20×-wrong ~10 GB/day figure corrected to the measured 0.48 GB/day — remainder = **retention/eviction** (nothing prunes capture segments anywhere, so the disk still fills ≈2026-11-23, now loudly) (ripe when: retention design is autonomous and ripe now).

- [T0037 — hour rotation trusts an untrusted timestamp](T0037-rotation-trusts-an-untrusted-timestamp.md) — `append()` rotated the hour from Kraken's own `timestamp` field, so one event stamped ≤`MAX_TS_AHEAD` ahead in the last minutes of an hour published the live hour as a **committed, complete** segment and dropped every genuine row after it as late (permanent, restart-surviving post-T0036); **fixed by cross-stream quorum** — a shared `HourOracle` acts on a boundary only once 2 witnesses (another stream, or the 5-min-handicapped wall clock) confirm it, holding (never dropping) rows for an unconfirmed hour, so no window size or wall-clock veto is needed and no stream is ever darkened; remainder = two accepted residuals, each ripe only **if ever observed** (two streams bogus into the same hour within one window; a clock leading >5 min plus a bogus stamp).

- [T0008 — book-desync recovery + the desync ROOT CAUSE](T0008-desync-recovery-robustness.md) — **root cause found and fixed**: `OrderBook` never pruned to the subscribed depth, so out-of-window levels went stale and resurfaced in the top-10 as phantoms (the book grew to 810 bids/468 asks vs Kraken's 100) — proven on 3 independent hosts, where replaying a real captured hour went from 482/117/398 CRC failures to **0**, so the ~200 "desyncs"/day were self-inflicted rather than network loss and **no archived data was lost**; remainder = the single-attempt resubscribe robustness, now far less pressing (ripe when: next attended capture-maintenance window, or on a recurrence).

- [T0035 — capture crashes when a WS reconnect is rejected (503)](T0035-capture-crashes-on-ws-reconnect-503.md) — Kraken's routine WS restart (close 1012) on 2026-07-13 was followed by an **HTTP 503** on the reconnect handshake; `InvalidStatus` is not `ConnectionClosed`, so it escaped `stream()`'s sole handler and **crashed the daemon** — only docker's restart policy caught it; **the code fix landed** (a failed connect attempt now backs off and retries like a drop, `CancelledError` still propagates, and an ERROR fires every 10 consecutive failed attempts); remainder = deploy the fixed image and verify the next venue-side WS restart is ridden out in-process (ripe when: the fixed capture image is deployed on the VPS).

- [T0038 — NAS mirror accumulates stale part files](T0038-nas-mirror-accumulates-stale-parts.md) — prune-after-verified landed: the pull command now deletes each verified hour's `<HH>.part*.parquet` on the NAS (strict numeric names only, hardened unlink), which drains the ~13.5k-part backlog on the first cycle after the next image rebuild + re-pin; the reader-side half was already closed by Task 7's `canonical_segments` (ripe when: verify the deploy dropped the part count — then close).

- [T0033 — home ops node (real-CPU compute tier)](T0033-home-ops-node-compute-tier.md) — the storage-topology decision is **ratified** (spec `00051`): NAS keeps custody + pulls, ops node holds the hot tier on NVMe and takes every Atom-bound compute (reconciler, verified path, CRC replay, panel, 24×7 loop) — purely additive, no Role A/B cutover; remaining work = execute OPS-1…6, with 00050 Task 13 depending on OPS-3's replayer (ripe when: now — OPS-1 touches nothing live).

### Resolved<a name="resolved-1"></a>

- [T0040 — alert on docker-socket-proxy denials and non-routine calls](archive/T0040-docker-socket-proxy-denial-alert.md) — closed unbuilt: the proxy it would have watched was removed the same day, so the denial stream it depended on no longer exists; the security residual that replaces it is [T0042](T0042-alloy-holds-root-equivalent-docker-access.md).

- [T0000 — Phase 0 human account actions & live-account confirmations](archive/T0000-phase0-account-actions.md) — resolved in iter-023 (Phase-2 close-out): account actions + live confirmations done 2026-07-07; the deferred July-9 fee-schedule fold-in landed in iter-017 (`cli/costs/`).

- [T0029 — NAS CPU has no AVX; polars crashes](archive/T0029-nas-cpu-no-avx-polars.md) — resolved — determinism measured, Role B bit-identical on the NAS (iter-094).

- [T0030 — NAS Alloy uid-key exposure](archive/T0030-nas-alloy-uid-key-exposure.md) — resolved (iter-094, same PR): Alloy runs as the dedicated non-key-owning user `zcrypto-dummy` (uid 1031, gid 1000), verified live — ships metrics + logs, `gate.prom` readable, and the `0600` pull keys denied through `/host/root`.

- [T0036 — a restart silently truncates the hour it lands in](archive/T0036-segment-writer-restart-clobber.md) — resolved 2026-07-14: committed-final invariant + atomic parts + validated recovery + cross-stream rotation quorum (T0037), deployed with a validated 1 s-downtime migration; post-deploy verified (hour-04 finals begin at :00:00, 0 desyncs, CRC-clean splice, no new truncation).

- [T0031 — re-pin NAS capture image after merge](archive/T0031-nas-image-repin-after-merge.md) — resolved 2026-07-13: the develop-built `-compat` image was published after the Role B merge and the NAS compose re-pinned to it (`sha256:ec180cde…`), replacing the branch-only digest; pull + verify green on the new image.

- [T0041 — archive-pull failures do not page](archive/T0041-archive-pull-failures-do-not-page.md) — resolved 2026-07-14: every error path now goes through `logging` so it carries the `level` label the alert selects on (`_abort` logged rather than printed — closing a regression the label-based rule itself introduced; uncaught exceptions logged via a new `run()` entry point; `pull-entrypoint.sh` emitting the Python log shape), plus a new dead-man rule that fires when no successful pull is seen for 3h — the only rule that catches silence.

- [T0034 — grafana-push safety](archive/T0034-grafana-push-safety.md) — resolved: `grafana-push.sh` now reads every pushed rule back and fails on a wrong datasourceUid (the health=ok trap), and reports/prunes orphaned rules (dry-run default, exact-membership so a renamed rule is caught); proven live (12 == 12, injected orphan flagged).
