---
status: open
ripe_when: 2026-08-05 — one week after `zcrypto_capture_seconds_since_last_book_message` began reaching Cloud (2026-07-29, with the capture roll), which covers the weekend trough the threshold must be fitted to. The VENUE-STATUS half is no longer parked here: it is armed as the `zcrypto-capture-venue-not-online` alert with its procedure in `infra/runbooks/README.md`, so the event now pages instead of waiting to be noticed
---

# Upstream silence: the paging half, and reacting to the venue's own status

## Context — what

The deliberately deferred second half of spec `00073` ([[T0101]]). That spec made a connected-but-silent book stream **observable** — booked as gap, exported as a gauge — and stopped there. Two things it consciously did not do:

1. **Nothing pages.** `gap_monitor.is_healthy()` does not consult the silence window, so the healthchecks.io dead-man still reports green through a total blackout. A repeat of 2026-07-27 is now correctly *counted* and still wakes nobody.
2. **Nothing reacts to Kraken's `status` channel.** It is classified, logged with its `effectiveTime`, and counted by `system` value; no behaviour and no alert rule keys on any of it.

Both omissions are recorded in the spec as decisions (D1, D3), not oversights.

## Why this matters

**Half a fix that is mistaken for a whole one is worse than no fix**, because the metric now looks healthy-and-instrumented while the paging gap is unchanged. Anyone reading `zcrypto_capture_gap_seconds_total` after spec `00073` will see it move for the first time and could reasonably conclude the blind spot is closed. It is closed for *measurement*; it is open for *alerting*.

The reason for deferring is real and should not be discarded on a later reading: `is_healthy()` gates the dead-man ping for **all 12 pairs at once**, on both hosts. A threshold fitted to ~4 days of thin-leg data could let one twitchy pair darken the fleet's last-resort liveness signal — trading a metric gap for a liveness outage, which is strictly the worse failure. That is the same reasoning spec `00072` D4 applied to the recovery ladder's wall-clock budget.

## Findings so far

- **The threshold's current basis is thin by construction.** 30 s was derived from the worst measured *natural* intra-hour book spacing: **12.196 s** (ETH/BTC, Fri 2026-07-24), **11.439 s** (ETH/BTC, Sun 07-26), with a largest natural hourly max of **12.299 s** across 104 segments. The `/BTC` legs bind because they are the newest and least liquid, and they had only ~4 days of history at measurement time. That is enough to set a conservative *booking* threshold and not enough to set a *paging* one.
- **The gauge is the instrument to fit against.** `zcrypto_capture_seconds_since_last_book_message{pair}` is fed by the same `last_seen` map the watchdog reads, so `max_over_time(...[24h])` on a healthy host gives the real natural-quiet distribution per pair, without injecting a fault into an unbackfillable pipeline.
- **Kraken's `status` channel is pushed automatically on connect and on every trading-engine state change**, carrying `system` ∈ {`online`, `cancel_only`, `maintenance`, `post_only`}. Its documented planned-downtime notification carries `type=maintenance`, `priority=high`, and an `effectiveTime` epoch.
- **Whether the 2026-07-27 outage was announced is unknown and unknowable retroactively** — `classify()` returned `"other"` for `status` and `_consume` dropped it unlogged, so nothing was ever recorded. Spec `00073` D1 fixes the recording; it deliberately builds no reaction, because a handler for a message this fleet has never once observed is the mechanism-nobody-proves-runs pattern.
- **An announcement cannot prevent loss** and should not be sold as if it could: if the venue publishes nothing, the data does not exist, and the secondary is fed by the same source. What it buys is *attribution* — separating "announced venue maintenance" from "our fleet broke", which is exactly what [[T0101]] got wrong for a day.
- **The counter this work will alert on is an UPPER BOUND, not a coverage fraction.** `GapMonitor` sums three window kinds independently — desync, disk watermark, upstream silence — so a pair desynced *through* a blackout books those seconds twice and `gap_ratio` can exceed 1.0. That is deliberate (each window answers a different question, and collapsing them would make two simultaneous faults look like one), but it means a rule reading `increase(zcrypto_capture_gap_seconds_total[...])` must be phrased as "how bad, roughly", never as "what fraction of the window was lost". Pinned by `test_gap_seconds_can_double_count_and_the_ratio_can_exceed_one`.
- **The booked duration over-reports by up to one 5 s check interval**, and always in that direction. The silence window closes at the pair's `last_seen` as of the closing tick rather than at the first message after the silence, so it absorbs a tick's worth of live traffic (≤ 2.4 % of a 209 s outage). Any threshold fitted from `gap_seconds_total` inherits that bias; fitting from the gauge does not.
- **The `1012` close frame is not an announcement.** Measured 2026-07-27: silence began 07:01:04.07, the `1012` arrived 07:04:49.35 — **225.28 s later**, at the end of the outage. Anything keyed on it recovers nothing.

## Suggested next steps

- *(autonomous, ripe 2026-08-05)* Fit the paging threshold for `zcrypto_capture_seconds_since_last_book_message` from a full week of both hosts' history, weekend trough included, and add the rule.
- *(decision, ripe only when the alert first fires)* Whether a pre-drain is worth building. The lead time in the status frame's `effective_time` is the deciding number, and the runbook's procedure says to record it here. Until an actual non-`online` value is observed, there is nothing to decide on.
