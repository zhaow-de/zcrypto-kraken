---
status: resolved
---

# The reconciler saw primary silence the capture daemon did not book as a gap

## Context — what

On 2026-07-27 the *Reconciler · primary gap rate high (degrading host)* rule fired (activeAt 09:48:00Z): the primary showed 2,318 s of healable gap in the preceding 6 h while the daemon's own `zcrypto_capture_gap_seconds_total` read **zero**.

**The cause was a Kraken WebSocket service restart, and the daemon was structurally unable to see it.** Both capture hosts lost every one of 12 book streams from **07:01:04 to ~07:04:35 UTC** — one simultaneous outage, every pair's last message falling within **0.454658 s** of every other. Kraken then sent an application-layer `1012 (service restart)` close frame to both hosts **19.65 ms apart** (`07:04:49.352183069Z` primary, `07:04:49.332529441Z` secondary), and answered the primary's next connect with `HTTP 503`.

Throughout the silence the socket was **open** and healthy: a `1012` cannot arrive on a dead socket, and the `websockets` keepalive (defaults `ping_interval=20 / ping_timeout=20`, no overrides) completed **≥11 ping/pong round trips**. The connection was alive at transport and protocol level and silent only at the data layer.

## Why this mattered

**Every liveness signal the daemon had answered correctly while the data was absent.** `client.connected` was True, no gap window existed, and so the healthchecks.io dead-man **pinged green through a total 12-pair blackout on both hosts** — roughly 3–4 pings per host. The fleet's last-resort liveness signal was blind to exactly the failure it exists to catch.

The blindness was structural, not a tuning error. `start_gap` had one production call site — `checksum_resync` — plus the global disk-watermark window, and **nothing in `cli/capture/` read a last-message timestamp**. There was no threshold to lower because there was no signal to threshold. `zcrypto_capture_gap_seconds_total` read `0.0` on all 12 pairs across 97.57 h of uptime containing 33 reconnects, and neither host's container log held a single `gap start` line in its entire 4-day life.

**This topic's original diagnosis was wrong, and the correction is the useful part.** It read the event as unbooked *reconnect* silence and factored 2,318 s as "12 pairs × 5 reconnects × ~39 s per pair per reconnect". Measured reconnect cost is **single-digit seconds** (0.002–2.82 s close-frame-to-first-book-event; 2.276–6.204 s close-to-first-processed-message, which counts the replay burst — the two methods disagree on the interval, not on the order of magnitude); 2,318/12 ≈ 193 s is **one** silence window per pair, not five reconnects' worth. The reconnect is a seconds-long footnote on a ~225 s outage. The defect was never *reconnect* silence — it was **connected-but-silent upstream** silence, which no amount of reconnect accounting would have found.

**It also claimed "Not data loss — and that is verified". That was false.** The verification was circular: it checked the healed counter against the healable counter, both summed from the same ledger. Measured against the parquet instead, **2,437.147792 s of L2 book across 12 pairs is permanently absent from the canonical archive**, and the reconciler physically healed **82.955463 s** of the 2,311.536587 s it books as healed. A CRITICAL-severity page — *Reconciler · residual gap increased (permanent loss)* — had already fired to Slack at **09:18:35Z**, thirty minutes *before* the warning this topic was written from, and the topic simply omitted it.

## Findings so far

- **A recurrence, not a one-off.** Kraken sent exactly **two** `1012 (service restart)` frames across the primary's full journald retention (2026-07-08 → 2026-07-27, 19.3 days): 2026-07-13T07:04:47 and 2026-07-27T07:04:49. Both Mondays, 14 days apart, 2 s apart in time-of-day — but **2026-07-20 hour 07 is clean** (BTC/EUR max gap 1.108 s), so it is not weekly. n=2 with one negative control: a signature worth acting on, not an established schedule.
- **The 2026-07-13 event is the ledger's other `both_streams_silent` record** (2,661.788740 s booked; true per-pair total **2,697.235577 s**) and was a real outage, not a genesis artifact — hour 06 runs cleanly to 06:59:59.9x on every pair.
- **Local causes excluded on both hosts**: kernel ring `-- No entries --` 06:40–07:20, `RestartCount 0`, uptimes 16 d / 11 d, no OOM, no clock step, no link event. The only nearby timer (`zcrypto-reboot-check`) fires at *different* offsets per host and post-dates the primary's stall.
- **Venue-side is strongly established but network-path independence is NOT.** Four independent lines point at Kraken: the paired `1012` with its reason string, the `HTTP 503`, the keepalive passing on the same TCP connection that carried no data, and Kraken's per-pair `trade_id` being perfectly contiguous across the outage (BTC/EUR 108392444 → 108392445 spanning 329 s — the longest trade drought in 8 days and 169,957 trades, against a p99.9 of 63.0 s). **But both hosts resolve `ws.kraken.com` to the identical Cloudflare anycast set** (`104.17.185.205`–`104.17.189.205`), so a shared-edge failure is not excluded — and `HTTP 503` is what a CDN edge returns when it cannot reach origin. This bears on whether a mirror on a different provider would have covered the loss.
- **The daemon logs nothing per message**, so the 275 s of empty log during the outage is *not* independent evidence of data silence (baseline: 0–3 lines in a comparable clean stretch). What it does prove is that no close, reconnect, desync or gap occurred in that window.
- **Application-level heartbeats are unrecoverable**: `classify()` returned `"heartbeat"` and `_consume` had no branch, so nothing was ever logged at any level. The keepalive argument above is what settles the liveness question instead.

## Done so far

**Resolved 2026-07-27** by spec `00073`, on branch `feat/t0101-reconnect-silence-accounting`.

- **The daemon can now see it.** A per-pair book staleness watchdog books gap for any stream that is subscribed, connected, and silent past 30 s — stamped at `last_seen`, never at detection, so the threshold is not silently discarded from every outage. Silence gets its own window in `GapMonitor` for the same reason the disk watermark has one: `start_gap` is idempotent per pair, so routing silence through it would let a concurrent `checksum_resync` gap swallow it.
- **Threshold derived, not guessed**: worst *natural* intra-hour book spacing measured fleet-wide is **12.196 s** (ETH/BTC, the thinnest leg; largest natural hourly max **12.299 s** over 104 segments), so 30 s is ~2.4× the binding pair's p99, and it equals the reconciler's `--min-gap-seconds` so the two producers finally measure the same thing.
- **The venue's `status` channel is recorded** rather than discarded — it used to fall through to `"other"` and be dropped unlogged, which is why "was the outage announced?" is unanswerable for this event rather than answered no.
- **Reconnects no longer stampede a restarting venue**: a `1012` floors the first backoff at 5 s per Kraken's documented guidance. The primary's attempt 1 fired 1.0 s after the close and was answered `HTTP 503`, costing ~3.9 s of extra silence; the secondary connected first try.
- **Proof it runs without a drill**: `zcrypto_capture_seconds_since_last_book_message{pair}` is fed by the same `last_seen` map the watchdog reads, so a gauge that stays fresh proves the watchdog's input is live on every message — no fault injected into an unbackfillable pipeline.
- **Mutation-checked in-repo**, and it caught what review did not: a watchdog nobody starts passed all 22 tests, because every property test drives the loop body directly. Guard added.

**Split out rather than left inside this topic**, since an archived file's deferrals are lost:

- [[T0103]] — the reconciler books unfilled silence as healed and double-counts it as permanent loss (a different producer, `cli/archive`).
- [[T0104]] — the panel emits a frozen book across a canonical gap; measured 212 rows with 2 distinct `mid` values against 8 across the hour's other zero-update seconds, already materialized.
- [[T0105]] — the deliberately deferred second half: paging on silence, and reacting to the venue's status.

**Not deployed by this topic.** Capture-daemon code on the unbackfillable path reaches the fleet only via an image build → ≥24 h secondary canary bake → primary re-pin (`capture-deploys.md`); the same image carries [[T0008]]'s recovery ladder. Merged and unrolled is the intended state, and [[T0105]]'s paging trigger starts counting at that re-pin, not at merge.

**Consequence stated plainly**: after this change a repeat of 2026-07-27 is correctly counted and still pages nobody. That is [[T0105]], sequenced second on purpose — an unfitted threshold wired into `is_healthy()` would darken the dead-man fleet-wide on both hosts, which is strictly worse than the metric gap it closes.
