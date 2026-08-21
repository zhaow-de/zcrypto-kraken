---
status: open
---

# Reconcile cycle duration scales with window byte volume and can outgrow its own tick

## Context — what

The ops overlay-writer cycle (`zcrypto-archive-pull`, `:12`/`:42` ticks) re-reads every hour's parquet in its `--window-hours 48` window on **both** capture trees each cycle, so its wall-clock duration is proportional to the window's byte volume — which is market volume, not anything the fleet controls. Measured 2026-08-21 during the residual-gap alert investigation: cycle duration fell to a **315 s** floor on 2026-08-16 ~22:00 (the window covering the two ~20 MB/day weekend days), then grew continuously to **1,371 s** at the 2026-08-21 08:12Z cycle (window covering the 92 and 129 MB/day midweek vol-spike days, BTC/EUR book bytes as the proxy; both capture trees are byte-identical per day). The growth is smooth at roughly +12 s/cycle while daily volume rises: one new ~5 MB hour slides into the window every tick.

## Why this matters

- **The tick interval is 1,800 s and the 08:12Z cycle took 1,371 s.** A sustained ~150 MB/day (16 % above 2026-08-20's 129) puts the cycle over its own tick. When a systemd timer fires while the unit is still `activating`, the trigger is dropped, not queued — cadence silently halves to hourly, booking latency for permanent-loss records grows by 30 min, and the runbooks' "books hour H at the next `:12`/`:42` tick after H+2 h" arithmetic bends without anything saying so.
- **No alert sees the degradation below 3 h.** `zcrypto_reconcile_last_success_timestamp_seconds` is stamped near cycle *start* (measured: stamp `08:12:16` for a cycle that ended `08:35:06`), and `zcrypto-reconcile-exporter-stale` pages at 3 h — at hourly cadence with ~25 min cycles, staleness peaks well under that. The failure mode is silent until it is severe.
- **No duration telemetry exists at all.** Cycle duration is currently only recoverable by subtracting journal `Starting`/`Finished` lines on the ops host — which is how this was found, incidentally, during an unrelated alert investigation.

## Findings so far

- Duration series (journal-measured, 351 cycles 2026-08-14 → 2026-08-21): ~600 s on 08-14, falling to the 315 s floor 08-16 ~22:00, ~520 s through 08-19 afternoon, then accelerating with the vol spike — 770 s (08-20 00:12), 1,043 s (08-20 18:12), 1,371 s (08-21 08:12).
- BTC/EUR book bytes per day (identical on both trees): 60, 57, 20, 21, 58, 54, 92, 129 MB for 08-13 → 08-20. The duration curve is this series pushed through a sliding 48 h sum — including the V-shape and the weekend floor.
- Ruled out: the minted output tree (1,328 files, one touched since 08-10 — static), the converges (no step at the 2026-08-20 18:33Z ops converge; growth predates it), the daily trade-backfill (its 00:12 cycles are not outliers).
- The 23-minute 08-21 08:12Z cycle completed cleanly (`failures=0`, exit 0) — this is scaling, not a hang.

## Suggested next steps

- **Export a cycle-duration metric** (start-to-export wall clock) from the reconcile textfile write, and stamp `last_success` at cycle *end* or export both ends — today the stamp mis-states a long cycle's completion by its whole duration.
- **Alert on duration approaching the tick interval** (e.g. warn at 1,500 s) — push after the metric's first record exists, per the alert-rule lifecycle in `capture-deploys.md`.
- **Decide whether the cycle should be incremental**: finalized hours already reconciled cleanly do not need re-reading every 30 min; the ledger already records what was booked. Profile first — the 48 h re-read may be load-bearing for late-arriving segments (the NAS pull is hourly, so an hour can gain data after first sight), and any trim must respect that.
- Until then, treat a slow cycle as expected during high-volume weeks: the liveness check is `zcrypto_reconcile_last_success_timestamp_seconds` age against one tick interval plus the current cycle length, not against the 16 s a quiet week suggests.
