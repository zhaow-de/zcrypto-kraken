---
status: partial
ripe_when: the retention/eviction remainder is ripe now (design work is autonomous); the disk-fill deadline itself is ≈2026-11-23 at the measured fill rate — but the breach is no longer silent, so it now pages instead of losing data unnoticed
---

# Capture stops silently when the disk watermark breaches — and the dead-man still reports healthy

## Context — what

When `DiskWatermark` breaches (free space below `min_free_bytes`, default **1 GiB**), the capture daemon
**stops writing every row** but keeps looking perfectly healthy:

- `_handle_book_message` / `_handle_trade_message` (`cli/capture/command.py`) return early on
  `watermark.breached` — no book rows, no trade rows are appended.
- The breach does **not** disconnect the WS, so `client.connected` stays `True`.
- The breach does **not** open a gap, so `monitor.is_healthy(pairs)` stays `True`.
- Therefore `_healthcheck_loop`'s condition still holds and **the healthchecks.io dead-man keeps
  pinging green**:

```python
if client.connected and monitor.is_healthy(pairs):
    ping_healthcheck(url)
```

The only signal is a single `logger.error("disk watermark breached …")` on the **transition** — and the
VPS's logs currently ship **nowhere** (the VPS `obs` role is exactly the unbuilt remainder of [[T0020]]).

Net effect: **the disk fills → capture silently produces nothing → every monitor stays green → the
unbackfillable L2 stream is lost until a human happens to look.**

## Why this matters

L2 is the one artifact in this project that **cannot be backfilled**. This is a total-capture-loss
failure mode with **no alerting whatsoever**, and it is **dated**, not hypothetical:

- Measured on the live primary (2026-07-13, read-only): root fs **79 G total / 10 G used / 65 G avail**;
  capture data **2.4 G spanning 2026-07-08 → 2026-07-13** ⇒ **≈0.48 GB/day**.
- 64 GB of headroom before the 1 GiB watermark ⇒ **≈133 days ⇒ the breach lands ≈2026-11-23.**
- **No eviction/retention exists.** Confirmed on the host: no zcrypto prune timer or cron
  (`systemctl list-timers` shows only `systemd-tmpfiles-clean`). Spec `00048` explicitly made
  delete-after-verified a **non-goal** — but it did so reasoning from a **wrong** disk figure (below).
- Any unexpected disk consumer (log growth, the engine journal, a stray file) brings the date forward.

## Findings so far

- **`T0003`'s "~10 GB/day" figure is wrong by ~20×.** Measured: **0.48 GB/day** (both on the VPS and
  independently on the pulled NAS archive: 2.57 GB over ~5.2 days). This single bad number is load-bearing
  in the current design: it produced the "~7-day VPS ring buffer" and the "bring the workstation online
  every few days or the VPS evicts un-pulled segments and that L2 is **permanently lost**" constraint in
  T0003. **At the true rate the safe-offline window is ~4 months, not ~7 days**, and 00048's "the 7-day
  buffer's 12× margin makes eviction unnecessary" reasoning rests on the same bad figure.
- The same 20× error makes **[[T0028]]** far less urgent than believed: its stall cliff (~250–600 GB)
  is ~1–2 years out at the real rate, not ~2 months.
- The daemon is otherwise very lean (measured live): capture uses **102 MiB RAM** and ~24% of one core
  (max 53%) at ~58% of the peak hour's message rate.

## Done so far

- **The silent half is fixed.** `_healthcheck_loop` now withholds the dead-man ping while the watermark is
  breached, so a breach **pages** instead of reporting green:
  ```python
  if client.connected and monitor.is_healthy(pairs) and not watermark.breached:
      ping_healthcheck(url)
  ```
  Two TDD tests cover it (`tests/test_capture_command.py`): the dead-man pings with disk headroom, and
  **stops** on a breach. This converts a silent, total, unbackfillable-data loss into a loud, actionable
  alert — the highest value-per-line change available. *(Deliberately NOT implemented via
  `GapMonitor.start_gap`, which looked more elegant but interacts badly: `start_gap` is idempotent, so a
  concurrent `checksum_resync` gap would swallow the watermark gap, and its `end_gap` would then resume
  pinging **while still breached** — reintroducing the very bug.)*
- **The 20×-wrong disk figure is corrected** in [[T0003]] (measured **0.48 GB/day**, not ~10 GB/day),
  along with the "~7-day ring buffer / bring the workstation online every few days" framing it produced.
- **The breach window is now booked into the exit-bar gap accounting.** `GapMonitor` gained a dedicated
  global watermark window (`start_watermark_gap` / `end_watermark_gap`) that rolls into every pair's
  `gap_seconds` / `gap_ratio`, driven from `_disk_watermark_loop`. It is tracked **independently** of the
  per-pair `_open` gaps and of the ping-withholding — deliberately **not** via `GapMonitor.start_gap`
  (idempotent per pair: a concurrent `checksum_resync` gap would swallow it and resume the ping while
  still breached). So a breach inside a ≥7-day clean run now both **pages** *and* shows in the
  automated `<0.1 %` gap-time bar. Six executed tests (`tests/test_capture_gap_monitor.py`,
  `tests/test_capture_command.py`).
- **The watermark loop itself can no longer die silently.** Adversarial verification executed a
  backward wall-clock step (chrony makestep) across an open breach window: `end_watermark_gap`
  raised `CaptureError` inside `_disk_watermark_loop` — a task nothing awaits until shutdown — so
  polling stopped for the life of the process (`breached` froze, later real breaches never withheld
  the ping: the same silent death, reintroduced), and the corpse's exception re-raised in `_run`'s
  shutdown ahead of the writer-close loop. Fixed three ways, each with an executed regression test:
  `end_watermark_gap` clamps a negative window to zero instead of raising; the loop survives any
  exception from its body (a flaky mount's `OSError` out of `disk_usage` included) and keeps
  polling; and `_run`'s shutdown awaits log-and-continue on a task's non-`CancelledError` corpse so
  every writer still flushes on the way out.

**Not yet deployed:** the fix ships with the next capture-image rollout (there is ~135 days of runway on
the disk, and the rollout is needed for Role C anyway).

- **(b) 00048's eviction rationale corrected** — the body §Non-goals now carries an inline `[Superseded — …]` marker flagging that the "~12× margin makes delete-after-verified unnecessary" claim rests on the 20×-wrong fill figure, and that eviction is in fact *not* implemented (disk fills ≈2026-11-23).
- **(c) probe-outage blind spot closed** — `DiskWatermark` now tracks `measurable`; a probe that raises sets it False, and the dead-man ping is gated on `not breached AND measurable`, so "cannot measure" no longer pings green on a frozen `breached` (the healthcheck grace absorbs a transient blip; a sustained failure pages).

## Suggested next steps

- **(autonomous)** Decide and implement **retention** for the capture segments — prune-after-verified-pull,
  the same shape as [[T0021]]'s journal retention. **There is no ring buffer anywhere**: nothing prunes
  capture segments on any host, so the disk simply fills. With the dead-man fix this now *pages* rather
  than silently losing data, but the underlying growth is unbounded. (Spec `00050`'s D9 adds a retention
  timer to the *secondary* capture host; the **primary** still has none.)
- **(verification)** Confirm the deployed daemon actually withholds the ping, at the next image rollout.
