# Capture runbooks — the venue feed and the archive's hour boundaries

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-capture-venue-not-online"></a>

## zcrypto-capture-venue-not-online — ALERT

### What you are seeing

A warning-severity Grafana alert. Kraken's WebSocket `status` channel reported a `system` value other than `online` on at least one capture host. The page carries that value — one alert instance per `(host, system)` — so you already know *which* state was reported before opening anything.

### What it means

The capture daemon counts every `status` frame it receives, labelled by the `system` value, into `zcrypto_capture_venue_status_total`. Until this fired, every observed value fleet-wide was `online`. Kraken pushes `status` on every connect, so the counter advances routinely — **only the non-`online` label is unusual.**

The frame also carries `effectiveTime`, logged but not counted. It was the number the pre-drain decision waited on, and the first real event answered it: `None` on every transition — zero advance notice, so the pre-drain was dropped (decision recorded in the phase-6 decisions log; the executor checks venue state at cycle entry instead). No record-keeping is owed here beyond normal triage.

This does **not** by itself mean data is being lost. A venue in `maintenance` or `cancel_only` may still stream book updates, and the capture path is unaffected by order-entry state. Loss shows up on the reconciler's counters, not here.

### What to do

1. **Read the state and its ladder.** The `system` value is on the page; the full transition sequence is in the capture log: `sudo docker logs zcrypto-capture 2>&1 | grep "venue status"` on either host (or the same line via Loki). Kraken's observed exit ladder — identical on both known events — is `maintenance` → `cancel_only` → `post_only` → `online`. `effective_time` has been observed only as `None` (the 2026-08-06 event, all five transitions, both hosts) — expect no advance notice.
2. **A venue-side halt DOES book permanent loss. Expect the loss page, hours later.** Both known halts booked: **10588.382751 s** on 2026-08-06 (~15 min × 12 pairs) and **6251.349974 s** on 2026-08-20 (~9 min × 12 pairs), each as `both_streams_silent` against hour 07, each written at the **09:12Z** tick, each paged minutes later — 09:24Z and 09:27Z. The data is genuinely gone: the venue emitted nothing, so no host missed anything that existed, but "no component failed" is not "no loss". Do not tell yourself otherwise, and do not close the incident before the reconciler has spoken.
3. **Do NOT read `zcrypto_reconcile_residual_gap_seconds_total` during or just after the halt — it cannot answer yet, and it will answer reassuringly.** Booking waits on `SETTLE_HOURS = 2` measured from the hour's **START** (`settled_hours` takes `floor(now) − 2 h`), and the reconcile timer runs at `*:12,42` — so **hour H is eligible at H+2 h and booked at the next `:12`/`:42` tick**. Hour 07 became eligible at 09:00 and was booked at 09:12, which is exactly when the ledger records it. A read taken at 07:20 for hour 07 is not a lagging counter; it is a question the system cannot answer for another **1 h 52 m**. `zcrypto_reconcile_last_success_timestamp_seconds` does NOT protect you here: it is run liveness, not coverage — at 07:20Z it read 06:42Z (fresh), and at 08:42Z it read 08:42Z (maximally fresh) while hour 07 was still unbooked. The only sound check is the clock: **hour H is bookable no earlier than H+2 h, at the next `:12`/`:42` tick.** This exact mistake produced a false "nothing was lost" record on 2026-08-06.
4. **Check whether CAPTURE degraded** — that is a different question from whether data was lost, and it is the one you can answer now: `zcrypto_capture_seconds_since_last_book_message` per pair, `RestartCount` on both daemons. The two capture silence rules fire and auto-resolve around the window on their own; that is them working, not something to respond to separately.
5. **Do not converge or restart anything on this signal alone.** Nothing in the capture path reacts to venue status; a restart costs a resubscribe and buys nothing. The 2026-08-06 event's FEED resolved itself in 17 minutes with zero human action — but it still cost ~15 min of unbackfillable L2 on every pair, which the loss page reported 2 h later.
6. **Silence `zcrypto-capture-venue-not-online` once triaged, time-boxed — and NEVER `zcrypto-capture-venue-state-recurrence`.** The latch is a counter-presence check, so it stays firing for the daemon's whole lifetime — the counter only resets when the capture daemon restarts, which is days-to-weeks away and gated on a bake. Silence in Grafana on **that uid only**, for a bounded window, and **delete it at each host's own next capture restart — per host, never fleet-wide**: the canary rule restarts the secondary days ahead of the primary, so one silence outlives the other host's reset. That deletion is not tidiness, it is the blind spot closing — a restart zeroes the counter, which makes the next event's states first sightings again, and the recurrence rule's `increase()` cannot see a first sighting, so a brand-new outage under a stale silence pages nothing at all. Do not delete the rule. The recurrence rule is the one signal that still reports a repeat while the latch is stuck, and it self-resolves on its own — silencing it re-opens exactly the blind spot it was added to close.

### Retire when

Both `zcrypto-capture-venue-not-online` and `zcrypto-capture-venue-state-recurrence` are absent from `infra/grafana/alerts.yaml` — i.e. the rules were deliberately removed. (The pre-drain decision landed 2026-08-06 and this procedure was rewritten then, per this clause's own instruction; the alerts stay.)

______________________________________________________________________

<a name="zcrypto-capture-venue-state-recurrence"></a>

## zcrypto-capture-venue-state-recurrence — ALERT

### What you are seeing

A warning-severity Grafana alert, and the one that means **it is happening now**, not "it happened once". Kraken reported a non-`online` `system` value within the last 15 minutes on at least one capture host. One instance per `(host, system)` pair, same as its sibling.

### What it means

The sibling latch above fires on the mere presence of a non-online count and cannot fall until the daemon restarts, so once a state has been seen it can never report that state again. This rule reads `increase()` over the same counter instead, so it sees a repeat as a step and says so. The two are deliberately opposite forms and neither is redundant: a non-online series is born at 1 with no implicit zero before it, so `increase()` is blind to a first sighting, which is precisely what the latch catches.

### What to do

1. **Steps 1–5 of the sibling procedure above apply unchanged** — read the state and its ladder, expect the loss page hours later, do not read the residual-gap counter yet, check whether capture itself degraded, and do not converge or restart on this signal alone.
2. **Treat it as current.** Unlike the latch, this one answers "is it recurring right now?", so a firing instance means a sighting inside the last 15 minutes rather than any time since the daemon started.
3. **Do NOT silence it.** It self-resolves roughly 15 minutes after the last sighting. Silencing it removes the only signal that still reports a repeat while the sibling latch sits stuck.
4. **Repeats inside one window coalesce.** It reports *that* a degradation is recurring, not *how many times* — read the capture log's `venue status` lines for the full ladder.

### Retire when

Covered by the sibling's Retire-when clause above: both rules go together, since each covers the venue failure the other structurally cannot.

______________________________________________________________________

<a name="cross-hour-straddle"></a>

## cross-hour-straddle — KNOWN LIMITATION

### What you are seeing

You are reading `containing_dark_window` in `cli/archive/settle.py`, or reconciling a small discrepancy between a stream's true silence and what the ledger booked for it at an hour boundary.

### What it means

`containing_dark_window` clamps to `hour_start`, exactly as `fleet_dark_windows` does. A stream whose silence began in the previous hour is therefore measured from the boundary, not from its true start, so a few seconds before the boundary are attributed to that previous hour's own tail window rather than to this one.

**Measured, not estimated**: 1.203668 s fleet-wide on the 2026-07-13 event (0.002794 s DOT … 0.308901 s ETH) — **0.045%** of that event's 2,696.031909 s. **Not** structurally bounded by `min_gap_seconds`, despite an earlier claim here to that effect: H−1 books a stream's tail only when the *fleet*-dark window there exceeds the threshold, and the fleet tail is bounded above by the stream's own — so a stream quiet from 11:45 while the fleet ticks to 11:59:50 leaves a 10 s fleet tail that is booked nowhere and a straddle far wider than the threshold. What bounds it in practice is the measured silence distribution (max 11.44 s across all 12 pairs, both mirrors, 2026-07-26) — an argument that degrades correctly when a thin pair joins the universe, where the structural one simply fails.

**This is accepted, not outstanding.** Closing it means reading each pair's H−1 segment on every hour carrying a fleet-dark window — real I/O on every cycle, for a fraction of a percent. The decision and its measurement are recorded in \[[T0103]\].

### What to do

Nothing. Do not "fix" this incidentally while working nearby without re-measuring the share first — the 0.045% figure is what makes it acceptable, and it is the number that would have to change to justify the I/O.

### Retire when

`containing_dark_window` no longer clamps to `hour_start` — i.e. the limitation is closed and this section describes nothing.
