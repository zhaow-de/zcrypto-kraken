# The daemon cannot see a connected-but-silent stream (spec 00073, T0101)

**Goal.** Make a subscribed, connected, silent book stream observable — and record the venue messages that would explain why it went silent.

**Scope.** `cli/capture/` only: `command.py`'s message path and loops, `gap_monitor.py`'s window bookkeeping, `ws_client.py`'s `classify()` and backoff. No change to the writers, the reconciler, the panel, or any alert threshold. The reconciler's own accounting defects and the panel's frozen-row behaviour are **different producers** and are registered separately — see *Out of scope*.

## The defect

On 2026-07-27 both capture hosts lost every one of 12 book streams for ~209 s. The daemon booked **nothing**: `zcrypto_capture_gap_seconds_total` read `0.0` on all 12 pairs across 97.57 h of uptime containing 33 reconnects, and both hosts' entire container logs contain **zero** `gap start` / `gap end` lines.

`start_gap` has exactly one production call site — `command.py`, `monitor.start_gap(pair, "checksum_resync", at=now)` — plus the global disk-watermark window in `gap_monitor.py`. `ws_client.py` holds no reference to the monitor at all. **Nothing in `cli/capture/` reads a last-message timestamp**, so "subscribed, connected, and receiving nothing" is not a state the daemon can represent.

Every liveness signal the daemon has was answered correctly while the data was absent:

- `client.connected` was `True` — the socket stayed open; a `1012` close frame cannot arrive on a dead one.
- The `websockets` library keepalive **passed**: defaults `ping_interval=20 / ping_timeout=20`, no overrides, so ≥11 ping/pong round trips completed across the silence.
- `monitor.is_healthy()` was `True` — nothing had opened a window.
- The healthchecks.io dead-man therefore **pinged green throughout**.

The venue announced the restart only at the *end*: the `1012 (service restart)` frame arrived at 07:04:49.35, **225.28 s after** the silence began at 07:01:04.07. It is a post-hoc notification, not a warning.

## D1 — Record the message classes we currently discard, before designing any reaction to them

`classify()` returns `"other"` for anything that is not `book` / `trade` / `heartbeat` / a subscribe-unsubscribe ack, and `_consume` does nothing with it. Kraken's WS v2 pushes a **`status` channel** automatically on connect and whenever the trading-engine state changes (`online` / `cancel_only` / `maintenance` / `post_only`), and its documented planned-downtime notification carries `type=maintenance`, `priority=high`, and an `effectiveTime` epoch.

So the daemon silently drops the one message class that could say whether an outage was announced — which is why **"did Kraken announce it?" is unanswerable today, not answered "no"**. An empty log is not an absent event when nothing logs the event.

Therefore: classify `status`, log every one at INFO with its `system`, `version` and **`effectiveTime`**, and count them by `system` value into `zcrypto_capture_venue_status_total`. `effectiveTime` is the field a planned-downtime notice carries, and its lead time is the single number that decides whether a pre-drain is worth building -- capturing `system` and dropping it would answer only the easy half. **Do not act on them yet** — building a handler for a message this fleet has never once recorded is the "mechanism nobody proves runs" pattern this work exists to end. Acting on an announcement is a follow-up whose ripeness is *a recorded announcement*.

This also cannot prevent loss and should not be sold as if it could: if the venue publishes nothing, the data does not exist, and the secondary is fed by the same source. What it buys is **attribution** — telling "announced venue maintenance" from "our fleet broke", which is exactly what this topic got wrong for a day.

## D2 — A per-pair book staleness watchdog, stamped at `last_seen`, not at `now`

Record `last_seen[pair]` on every book message at receipt, **before any early return** (the disk-watermark breach path returns early, and a breach must not also blind the watchdog). A 5 s loop opens a gap for any pair whose staleness exceeds the threshold, and the window is stamped **`at=last_seen[pair]`** — not `at=now`, or the first 30 s of every outage is silently uncounted and the metric under-reports by exactly the threshold.

**Book only.** Trade streams are legitimately sparse — a quiet pair can go minutes without a trade — so a trade-staleness watchdog would need a per-pair fitted threshold and would fire on ordinary quiet. Book updates at depth-100 are continuous by construction; that is what makes their absence meaningful.

## D3 — The watchdog books the gap; it does NOT gate the dead-man in this iteration

This is the load-bearing safety decision, and it is deliberately conservative.

`is_healthy()` gates the healthchecks.io ping for **all** pairs. Wiring an unfitted threshold into it means one twitchy pair darkens the dead-man fleet-wide on both capture hosts — trading a metric gap for a liveness outage, which is strictly the worse failure. That is the same reasoning D4 of spec `00072` applied to the recovery ladder's wall-clock budget.

So this iteration ships the **measurement**: the gap is booked, `gap_seconds_total` becomes truthful, and the companion gauge exposes the live distribution. Gating `is_healthy()` — and any paging rule — waits until that distribution is measured in production over a full week including a weekend trough. Registered as a follow-up with `ripe_when` on accumulated observation, never a date.

Consequence, stated plainly rather than glossed: **after this change a repeat of 2026-07-27 still pages nobody.** It becomes visible and correctly counted, which is the defect this topic is about. Paging is the next step, and it is sequenced second on purpose.

## D4 — The proof-it-runs mechanism is a gauge, not a drill

`zcrypto_capture_seconds_since_last_book_message{pair}` is updated on the same code path that feeds the watchdog. A gauge that is always fresh proves the watchdog's **input** is live on every message, in production, without injecting a fault into an unbackfillable pipeline.

That matters because the alternative — waiting for a real outage to prove the watchdog works — is precisely how [[T0035]] stayed open for weeks while landed and deployed, and how this topic's own defect survived 97 h of uptime and 33 reconnects unnoticed.

Acceptance once deployed: `max_over_time(zcrypto_capture_seconds_since_last_book_message[24h])` on a healthy host should land near the measured natural worst (~12 s), and the counter should book ~the observed reconnect cost per reconnect (0.8–6.2 s measured).

## D5 — Threshold 30 s, derived from measurement rather than intuition

Measured worst intra-hour book spacing per pair, primary mirror, excluding the two known incidents (2026-07-17's drill and 2026-07-27's outage):

| window | fleet-worst natural spacing |
| --- | --- |
| Sun 2026-07-26 (weekend trough) | **11.439 s** — ETH/BTC |
| Fri 2026-07-24 (weekday) | **12.196 s** — ETH/BTC |
| ETH/BTC, 104 hourly segments, largest **natural** hourly max | **12.299 s** (2026-07-25 h07) |
| ETH/BTC, same sample, p99 of hourly maxima excluding the two incidents | 12.186 s |
| XRP/EUR, 464 hours, p99 of hourly maxima | 9.245 s |

The thin BTC-quoted legs bind, as expected — they are the newest and least liquid. **30 s is ~2.4× the binding pair's worst natural gap** (2.44× against 12.299, 2.46× against the 12.186 p99 — the choice does not turn on which), and it deliberately matches the reconciler's `--min-gap-seconds`, so the two producers finally measure the same thing and their numbers become comparable instead of merely adjacent.

The sample is ~4 days for the `/BTC` legs. That is enough to set a conservative booking threshold; it is **not** enough to set a paging threshold, which is D3's other reason for deferring the gate.

## D6 — Reconnect no faster than 5 s after a venue-announced restart

Kraken's documented guidance: reconnect instantly a handful of times on a random drop, but **no more often than once every 5 s** after maintenance or extended downtime. Our backoff starts at 1.0 s.

Measured on 2026-07-27: the primary's attempt 1 fired 1.0 s after the `1012` and was answered `HTTP 503`; attempt 2 succeeded. The secondary, whose first attempt landed later, connected first try. Reconnecting too eagerly into a restarting venue cost the primary ~3.9 s of extra silence.

So: when the close carried code `1012`, floor the first delay at 5 s. Ordinary drops — the common case at ~8.2 reconnects/day — keep the existing fast path untouched. This is a small, bounded change to a load-bearing loop and it is the one place a bug would be expensive, so it is guarded by tests on both branches.

## D7 — Validation

- **Unit, injected clock**: no messages past the threshold ⇒ a window opens stamped at `last_seen`; the next message closes it; the booked duration equals the true silence, not silence-minus-threshold.
- **The early-return trap**: a watermark breach must not stop `last_seen` being recorded.
- **Offline replay of the real hour**: feed the archived 2026-07-27 hour-07 stream through the message path with a fake clock and assert ~209 s booked per pair. This is the only test that reproduces the shape that actually happened, and the data is on disk.
- **Backoff**: `1012` ⇒ first delay ≥ 5 s; any other close ⇒ unchanged.
- **Mutation-check the seam** in-repo on a committed tree, never in a `git archive` sandbox — the editable install's `.pth` puts the repo on `sys.path`, so pytest inside a sandbox measures unmutated code (`agent-ops.md`).

## Out of scope — registered, not built here

- **The reconciler's accounting** — `healed_seconds` books the full width of a gap on one secondary `update` row; `residual_seconds` is a hardcoded `0.0` on minted records; a pair with no update witness produces no record at all; `trade_deficit` books zero residual. Measured: of 2,311.54 s claimed healed for this event, **82.96 s** is real, and 2,187.03 s is double-booked into both the "covered" and the "nobody covered" counter. A different producer (`cli/archive`), therefore a different component and its own topic.
- **The panel materializes frozen rows across a canonical hole** — measured on `BTC/EUR` hour 07: 212 rows inside the blackout carrying **2 distinct `mid` values**, against 8 across the hour's 11 other zero-update seconds. The hour has its full 3600 rows and reads as complete. Its own topic.
- **Alerting on the reconcile counters** — the healable-gap-rate threshold is in pair-seconds while its summary claims minutes, and the critical permanent-loss rule self-resolves after 60 minutes. **Registered in [[T0103]]**, with that topic, because both are defects in the surfacing of the counters it fixes. (This bullet first said "registered" while no topic named them — prose is not registration, and a spec sentence claiming otherwise is worse than silence because it reads as done.)
- **Acting on a venue announcement** — ripe when D1 has actually recorded one.
- **Whether the outage was venue-side or a shared edge** — both hosts resolve `ws.kraken.com` to the *identical* Cloudflare anycast set (`104.17.185.205`–`104.17.189.205`), so host independence is established but **network-path independence is not**, and `HTTP 503` is what a CDN edge returns when it cannot reach origin. This does not change any decision here — the watchdog fires either way — but it does bear on whether a second mirror on a different provider would have covered the loss.

## Deployment note

Capture-daemon code on the unbackfillable path: image build → ≥24 h secondary canary bake → primary re-pin (`capture-deploys.md`). Merged and unrolled is the correct end state for this PR.
