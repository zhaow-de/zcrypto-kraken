---
status: open
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

## Suggested next steps

- Decide the shape of recurrence detection and whether it replaces or supplements the latch. Two candidates, neither yet evaluated against the rule's stated properties: a second rule on `increase(zcrypto_capture_venue_status_total{system!="online"}[15m]) > 0` as a *recurrence* signal beside the latch (the rule comment explains why `increase()` cannot be the primary form — a series is born at 1 and Prometheus inserts no implicit zero, so a first transition would sit green — but that argument does not apply to a series that already exists at a non-zero value, which is exactly the post-latch state); or an annotation/`__value__` surface that makes the counter's current value visible in the notification so a responder can see it move.
- Whichever is chosen, land it with the rule-replacing deploy order from `capture-deploys.md`: converge → push → verify the first sample **by value** → prune → confirm the old uid 404s. Never prune the superseded rule before its replacement has a verified first sample.
- Prefer landing it **before** the next primary capture converge. That converge restarts the daemon and clears the latch, which makes the alert green again and removes the evidence that motivated the change — easy to then forget until the next outage re-latches it.
- Record the 2026-08-06 outage and its 10,711.7 gap-seconds (~15 min/stream) in `docs/reference/capture-era-data-hygiene-map.md`'s "Structural windows" table, which does not yet carry that date, so a future continuity run over a window containing 2026-08-06 is not re-investigated from scratch as a new defect.
