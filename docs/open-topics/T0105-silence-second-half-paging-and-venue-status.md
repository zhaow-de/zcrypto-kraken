---
status: open
ripe_when: TWO independent triggers, each covering one half. (a) PAGING — ripe once `zcrypto_capture_seconds_since_last_book_message` has a full week of production history including a weekend trough on both hosts, which is what the threshold must be fitted to; the gauge ships with spec `00073` so the clock starts at that image's primary re-pin, not at merge. (b) VENUE STATUS — ripe the first time a `venue status system=` line is actually observed in the logs, and immediately if one ever reads anything other than `online`
---

# Upstream silence: the paging half, and reacting to the venue's own status

## Context — what

The deliberately deferred second half of spec `00073` ([[T0101]]). That spec made a connected-but-silent book stream **observable** — booked as gap, exported as a gauge — and stopped there. Two things it consciously did not do:

1. **Nothing pages.** `gap_monitor.is_healthy()` does not consult the silence window, so the healthchecks.io dead-man still reports green through a total blackout. A repeat of 2026-07-27 is now correctly *counted* and still wakes nobody.
2. **Nothing reacts to Kraken's `status` channel.** It is classified and logged; no behaviour keys on it.

Both omissions are recorded in the spec as decisions (D1, D3), not oversights.

## Why this matters

**Half a fix that is mistaken for a whole one is worse than no fix**, because the metric now looks healthy-and-instrumented while the paging gap is unchanged. Anyone reading `zcrypto_capture_gap_seconds_total` after spec `00073` will see it move for the first time and could reasonably conclude the blind spot is closed. It is closed for *measurement*; it is open for *alerting*.

The reason for deferring is real and should not be discarded on a later reading: `is_healthy()` gates the dead-man ping for **all 12 pairs at once**, on both hosts. A threshold fitted to ~4 days of thin-leg data could let one twitchy pair darken the fleet's last-resort liveness signal — trading a metric gap for a liveness outage, which is strictly the worse failure. That is the same reasoning spec `00072` D4 applied to the recovery ladder's wall-clock budget.

## Findings so far

- **The threshold's current basis is thin by construction.** 30 s was derived from the worst measured *natural* intra-hour book spacing: **12.196 s** (ETH/BTC, Fri 2026-07-24), **11.439 s** (ETH/BTC, Sun 07-26), with a 101-hour p99 of **12.299 s**. The `/BTC` legs bind because they are the newest and least liquid, and they had only ~4 days of history at measurement time. That is enough to set a conservative *booking* threshold and not enough to set a *paging* one.
- **The gauge is the instrument to fit against.** `zcrypto_capture_seconds_since_last_book_message{pair}` is fed by the same `last_seen` map the watchdog reads, so `max_over_time(...[24h])` on a healthy host gives the real natural-quiet distribution per pair, without injecting a fault into an unbackfillable pipeline.
- **Kraken's `status` channel is pushed automatically on connect and on every trading-engine state change**, carrying `system` ∈ {`online`, `cancel_only`, `maintenance`, `post_only`}. Its documented planned-downtime notification carries `type=maintenance`, `priority=high`, and an `effectiveTime` epoch.
- **Whether the 2026-07-27 outage was announced is unknown and unknowable retroactively** — `classify()` returned `"other"` for `status` and `_consume` dropped it unlogged, so nothing was ever recorded. Spec `00073` D1 fixes the recording; it deliberately builds no reaction, because a handler for a message this fleet has never once observed is the mechanism-nobody-proves-runs pattern.
- **An announcement cannot prevent loss** and should not be sold as if it could: if the venue publishes nothing, the data does not exist, and the secondary is fed by the same source. What it buys is *attribution* — separating "announced venue maintenance" from "our fleet broke", which is exactly what [[T0101]] got wrong for a day.
- **The `1012` close frame is not an announcement.** Measured 2026-07-27: silence began 07:01:04.07, the `1012` arrived 07:04:49.35 — **225.28 s later**, at the end of the outage. Anything keyed on it recovers nothing.

## Suggested next steps

- **(a, on trigger) Fit the paging threshold from the gauge, then wire it.** Read `max_over_time(zcrypto_capture_seconds_since_last_book_message[7d])` per pair on both hosts; set the threshold from the measured tail of the *thinnest* leg, not the fleet mean. Then choose the surface deliberately: gating `is_healthy()` (dead-man, fleet-wide, blunt) versus a dedicated Grafana rule on the gauge or on `increase(zcrypto_capture_gap_seconds_total[...])` (per-pair, tunable, does not risk the dead-man). **The rule is the safer first move**; gating the dead-man can follow once the rule has run quietly for a while.
- **(a) When the gate is wired, rewrite the test that forbids it.** `tests/test_capture_upstream_silence.py::test_silence_does_not_gate_the_dead_man_in_this_iteration` asserts the current behaviour deliberately, so the change cannot happen by accident — and spec `00073` D3 must be revised in the same change rather than left contradicting the code.
- **(b, on trigger) Once a `venue status` line is observed, decide whether to act on it.** Cheapest useful step is a counter labelled by `system` value plus a rule on anything ≠ `online`; only then consider behaviour (suppressing a silence alert during an announced window, or pre-emptively marking the gap's reason so [[T0104]]'s panel marker can distinguish announced maintenance from an unexplained hole).
- **(b) Record the observed lead time.** If a `maintenance` status or an `effectiveTime` ever arrives *before* the data stops, that number is what decides whether a pre-drain is worth building. If it consistently arrives after, close that idea explicitly rather than leaving it implied.
