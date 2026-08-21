---
status: partial
---

# Reconcile cycle duration scales with window byte volume and can outgrow its own tick

## Context — what

The ops overlay-writer cycle (`zcrypto-archive-pull`, `:12`/`:42` ticks) re-reads every hour's parquet in its `--window-hours 48` window on **both** capture trees each cycle, so its wall-clock duration is proportional to the window's byte volume — which is market volume, not anything the fleet controls. Measured 2026-08-21 during the residual-gap alert investigation: cycle duration fell to a **315 s** floor on 2026-08-16 ~22:00 (the window covering the two ~20 MB/day weekend days), then grew continuously to **1,371 s** at the 2026-08-21 08:12Z cycle (window covering the 92 and 129 MB/day midweek vol-spike days, BTC/EUR book bytes as the proxy; both capture trees are byte-identical per day). The growth is smooth at roughly +12 s/cycle while daily volume rises: one new ~5 MB hour slides into the window every tick.

## Why this matters

- **The tick interval is 1,800 s and the 08:12Z cycle took 1,371 s.** A sustained ~150 MB/day (16 % above 2026-08-20's 129) puts the cycle over its own tick. When a systemd timer fires while the unit is still `activating`, the trigger is dropped, not queued — cadence silently halves to hourly, booking latency for permanent-loss records grows by 30 min, and the runbooks' "books hour H at the next `:12`/`:42` tick after H+2 h" arithmetic bends without anything saying so.
- **No alert sees the degradation below 3 h.** `zcrypto_reconcile_last_success_timestamp_seconds` **was** stamped near cycle *start* (measured: stamp `08:12:16` for a cycle that ended `08:35:06`; spec `00097` moved it to cycle completion), and `zcrypto-reconcile-exporter-stale` pages at 3 h — at hourly cadence with ~25 min cycles, staleness peaks well under that. The failure mode is silent until it is severe.
- **No duration telemetry existed at all** before spec `00097` (published, though not yet deployed — see the remaining sub-item). Cycle duration was recoverable only by subtracting journal `Starting`/`Finished` lines on the ops host — which is how this was found, incidentally, during an unrelated alert investigation.

## Findings so far

- Duration series (journal-measured, 351 cycles 2026-08-14 → 2026-08-21): ~600 s on 08-14, falling to the 315 s floor 08-16 ~22:00, ~520 s through 08-19 afternoon, then accelerating with the vol spike — 770 s (08-20 00:12), 1,043 s (08-20 18:12), 1,371 s (08-21 08:12).
- BTC/EUR book bytes per day (identical on both trees): 60, 57, 20, 21, 58, 54, 92, 129 MB for 08-13 → 08-20. The duration curve is this series pushed through a sliding 48 h sum — including the V-shape and the weekend floor.
- Ruled out: the minted output tree (1,328 files, one touched since 08-10 — static), the converges (no step at the 2026-08-20 18:33Z ops converge; growth predates it), the daily trade-backfill (its 00:12 cycles are not outliers).
- The 23-minute 08-21 08:12Z cycle completed cleanly (`failures=0`, exit 0) — this is scaling, not a hang.

## Done so far

**Spec `00097`, delivered in full and proven against the real mirrors.** Three layers compose: cycle-duration telemetry with `last_success` moved to cycle completion; the gap arithmetic vectorized onto int64-microsecond arrays; and a fingerprint skip-cache that lets a settled hour be skipped only when re-examining it provably cannot decide anything new.

- **Measured on the live mirrors, same 72 h window, all three runs started inside one UTC hour**: develop (the exact merge-base) **1428.79 s** → branch cold **120.23 s** (11.9×) → branch warm **15.90 s** — **89.9×**. develop ran last with a warm page cache, so the ratios are conservative.
- **Nothing an examined hour decides, books, or mints changed.** The golden replay's ledgers are byte-identical (same sha256, `at` popped), including microsecond spans (`372.488552 s`, `48.036112 s`, `408.501293 s`) and the 2026-08-20 dark hour's verdict line verbatim. Textfiles match once the three expected movers are normalized. The mint path — which that window happened not to exercise — is covered against develop by a constructed A/B of 7 scenarios × detect/mint with 24 minted parquet sha256s and zero differences, and by a cache-on vs cache-off run in which every minted parquet was byte-identical.
- **The profile that motivated all of it**: ~97 % of the cycle was Python-object timestamp arithmetic (60 % `PySeries.to_list`, 20 % `fleet_dark_windows`); actual parquet decode was **2 %**.
- **The cache fails open, never wrong.** An hour is skipped only if the cache entry matches on a fingerprint whose *presence* is derived from the same `scan_hours` result the examination uses (never a fresh `stat`), the examination was late and clean, no expected file is absent, and this cycle changed nothing about that hour. Anything unreadable, corrupt, mode-mismatched or stale reads as no cache at all. Two hours are re-examined every cycle as a rotating audit; any divergence logs at ERROR — which pages — and deletes the whole cache. Measured reach: a poisoned hour is caught within ~11 h, well inside the 48 h window.
- **Operator surface**: `zcrypto_reconcile_cycle_duration_seconds` and `zcrypto_reconcile_hours_skipped` (incremented inside the skip branch, so it reports what happened rather than what was planned), both charted; the `zcrypto-reconcile-cycle-duration` warning rule staged in `alerts.yaml`; a new runbook section whose `skipped=0` triage names the real causes, including a pair add and a thin pair's zero-print hour; and `infra/nas/README.md` updated for the overlay's one new sidecar and the correction that must delete it.

## Suggested next steps

- **The attended rollout, and the measurement that resolves this topic.** The image builds from `develop` after the feature PR merges; then the ops host pulls the digest, `fleet-pins.md` records it with the converge evidence in that commit's message, the Kraken maintenance feed and the open-topics/memo blockers are swept, and `converge.sh --limit zcrypto-ops -e ops_image_digest=… -e liquidations_decision=roll-after` runs between `:12`/`:42` ticks — followed by the owed liquidations roll (`docker compose up -d` in `/etc/zcrypto-ops`, digest read back from the container, never the compose file). Then **read two consecutive cycles by value**: the first builds the cache and should land near the cold figure, the second should land at the warm one. Push `zcrypto-reconcile-cycle-duration` only after that first live sample exists, and verify the rule against it by value rather than presence. This topic resolves on those two measured cycles and the live alert — not on either merge.
