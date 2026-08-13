---
status: resolved
---

# The venue-not-online latch masks a recurrence on the primary

## Context — what

`zcrypto-capture-venue-not-online` fires on `sum by (host, system) (zcrypto_capture_venue_status_total{system!="online"}) > 0` (abridged — the rule also carries a `host=~` matcher and an `or on() vector(0)` fallback, both discussed below), and the rule's own comment states the latch is deliberate: the counter never decreases until the daemon restarts, so the first observation of an unseen payload shape cannot self-resolve before anyone reads it.

The latch works as designed. What it cannot do is distinguish an old latch from a fresh recurrence of an **already-seen** `system` value on the same host: a second `maintenance` on `zcrypto` increments that series from 1 to 2, and the `{host=zcrypto, system=maintenance}` alert instance is already `Alerting`, so no new notification is produced. A genuinely novel state (say `limit_only`) still creates a new series and does notify — the masking is specific to repeats, not total.

## Why this matters

The primary's counter has carried `maintenance=1, cancel_only=2, post_only=1` since the real Kraken outage of 2026-08-06 07:01:02–07:18:18 UTC, and the rule has been firing continuously ever since. The latch clears only on a capture-daemon restart, and capture on the primary is **deliberately parked** on `99faf16514e3` (its code has moved by one comments-only commit, so re-pinning would restart live capture on the unbackfillable path for no gain). There is therefore no scheduled event that would clear it.

Two consequences, both live today. A repeat venue degradation on the primary is invisible to this rule until that restart happens. And a rule that has been red for days trains its responder to ignore it, which is the failure the latch design was itself trying to prevent — the deliberate choice bought "somebody reads the value once" at the cost of "nobody reads it again".

The live trading gate does **not** depend on this signal: spec `00088`'s engine reads venue status fresh from the public REST `SystemStatus` — evaluated once at startup, again per cycle, and (by `ExecutionGate`'s design) immediately before any future submission — surfaced as `zcrypto_exec_venue_ok` and independent of capture's counter, so execution safety is unaffected either way. This topic is about the forensic/notification surface only.

## Findings so far

- The 2026-08-06 event was real and self-resolved in 17 minutes: the primary's log shows `maintenance` 07:01:02 → `cancel_only` 07:14:58, 07:16:08 → `post_only` 07:16:15 → `online` 07:18:18. Every `venue status` line since (42 of them, through 2026-08-12) reads `system=online`.
- The event cost book data. **The durable number is 10,711.7 gap-seconds over 12 streams — 893 s ≈ 14.9 min each.** The percentages are point-in-time and dilute as clean hours accumulate, because `--since` is open-ended and the numerator is frozen: measured 2026-08-12 ~08:00Z the run failed the exit bar for `--since 2026-08-06` at 0.1631% gap time (worst stream 0.1669%), and by mid-afternoon the same command already read 0.1559%, so it will cross back under the 0.1% bar and read PASS within days without anything having changed. `--since 2026-08-07` measures 0.0000%, so the whole gap sits on the outage day. **0 truncated and 0 missing hours throughout** — capture wrote every hour. 893 s is 86% of the 17.3-minute window, which is consistent with the venue having stopped sending while capture kept running (sub-threshold gaps are not booked, so ≤ window is expected); the gap's confinement to 08-06 is measured, its alignment to 07:01–07:18 within that day is inferred from the log timestamps. Unbackfillable either way, and not a capture defect.
- The secondary corroborates independently: its re-pin restarted the daemon 2026-08-11 14:13:17Z, which reset its counter, and it now carries `online=10` with **no** non-online series — so nothing non-online has occurred fleet-wide since. It also demonstrates that a restart is what clears the latch.
- The masking is structural, not a misconfiguration: `by (host, system)` grouping is load-bearing for the responder (planned `maintenance` versus degraded `cancel_only`/`post_only` demand opposite responses), and the `on()` on the `vector(0)` fallback is load-bearing against a permanent extra series. Any fix must preserve both.

## Done so far

- **The recurrence shape was decided and built: a second rule that SUPPLEMENTS the latch, never replaces it.** `zcrypto-capture-venue-state-recurrence` reads `increase(...[15m])` over the same counter, grouped `by (host, system)` with the same `on()`-guarded fallback. The annotation/`__value__` candidate was rejected on analysis rather than taste: Grafana notifies on state transitions, so a richer annotation on an instance that is already `Alerting` produces no new notification and closes nothing. Replacing the latch was rejected too — it would lose first-observation detection entirely, since `increase()` is blind to a series born at 1. The two forms partition the space: presence catches the first sighting (including the first after any restart, the counter being in-memory), `increase()` catches every sighting thereafter, and the new rule self-resolves ~15 min after the last sighting so it can answer "is it happening again?" with a no.
- **Four tests pin what a future edit would silently break** — the uid fits Grafana's 40-char column, the `[15m]` window agrees with `relativeTimeRange.from`, the two rules keep OPPOSITE forms, and both keep `by (host, system)` plus the `on()` fallback. All proven load-bearing by mutation probe, including a vacuity probe that deletes the whole rule.
- **The deploy is purely additive**, so no uid is superseded, no prune is owed, and the rule-replacing order collapses to push → verify by value. No converge either: the metric already reaches Grafana Cloud through the capture keep-regex.
- **The runbook carries the new uid**, with its own anchor and the explicit instruction never to silence it — the sibling's "silence this rule once triaged" step is scoped to the latch, since silencing the recurrence rule would re-open the exact blind spot it closes.
- **The 2026-08-06 outage is recorded** in `docs/reference/capture-era-data-hygiene-map.md`'s "Structural windows" table, with the gap-seconds as the durable figure and the reconciler's `both_streams_silent` number reconciled against it.

## Resolution

Resolved 2026-08-13. The recurrence rule `zcrypto-capture-venue-state-recurrence` is live in Grafana Cloud and **verified by value, not presence**: its A arm reads three labeled zeros — `{zcrypto, maintenance}`, `{zcrypto, cancel_only}`, `{zcrypto, post_only}` — where the standing latch holds 1/2/1, so the rule arrived green rather than inheriting the latch's red. A `(no series)` there would have been a FAIL and a `>0` would have been a real page; neither occurred. The rule is **evaluating**, not merely stored: `state=inactive health=ok lastError=(none)`, `lastEvaluation` fresh, 3 alert instances tracking the three latched pairs.

The push was upsert-only with `GRAFANA_PRUNE` deliberately unset, and the push's own orphan check reported none — the change is purely additive, so no uid was superseded and the dangerous prune step of a rule-replacing deploy never arose.

The gap this topic named is closed: a repeat of an already-seen `system` value now steps the counter, `increase()` sees the step, and a notification fires — where before it landed on an instance already `Alerting` and produced nothing. The two rules keep deliberately opposite forms, each covering the venue failure the other structurally cannot, with four tests and a runbook section pinning that so a future edit cannot quietly collapse them into one.
