---
status: open
ripe_when: live now — the dead-man fix is a ~2-line change and should land at the next capture-daemon deploy; the disk-fill deadline itself is ≈2026-11-23 at the measured fill rate
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

## Suggested next steps

- **(autonomous, ~2 lines + TDD test)** Make the dead-man actually fire. Withhold the healthcheck ping
  while the watermark is breached, so healthchecks.io alerts instead of reporting green:
  ```python
  if client.connected and monitor.is_healthy(pairs) and not watermark.breached:
      ping_healthcheck(url)
  ```
  Test: breach the watermark (injectable `usage_fn` already exists on `DiskWatermark`) → assert no ping.
  This closes the *silent* half of the bug and is the highest value-per-line change available.
- **(autonomous)** Correct the **0.48 GB/day** figure in [[T0003]] (and the derived "7-day buffer" /
  "online every few days" framing) and in `00048`'s eviction non-goal rationale — several design
  constraints are calibrated against a 20×-wrong number.
- **(autonomous)** Decide and implement **retention** for the capture segments (prune-after-verified-pull,
  the same shape as [[T0021]]'s journal retention), or accept the disk growth and add a **VPS disk-free
  alert** — but note an alert alone still needs the VPS `obs` role ([[T0020]]) to exist. The dead-man fix
  above is the only mitigation that works with today's infrastructure.
- **(verification)** Re-measure the fill rate once the **second capture host** exists (it pulls to the same
  archive, roughly doubling archive growth — though not the *VPS's* own disk, which stays ~0.48 GB/day).
