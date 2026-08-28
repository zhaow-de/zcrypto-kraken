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
4. **Check whether CAPTURE degraded** — that is a different question from whether data was lost, and it is the one you can answer now: `zcrypto_capture_seconds_since_last_book_message` per pair, `RestartCount` on both daemons. The two capture silence rules will have fired and auto-resolved around the window — that is them working, and both have their own sections below if you need to triage one on its own. They report the same halt in a different vocabulary; they are not a second incident.
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

______________________________________________________________________

<a name="zcrypto-capture-all-streams-silent"></a>

## zcrypto-capture-all-streams-silent — ALERT

### What you are seeing

A **critical** Grafana alert, one instance per capture host. The *minimum* of `zcrypto_capture_seconds_since_last_book_message` across all 12 pairs on that host crossed 120 s — so not one thin leg went quiet, the whole feed did.

### What it means

**Check the venue's published maintenance calendar before anything else.** Every firing in this rule's life has been one: 2026-08-06 and 2026-08-20, both hosts each time, both inside a "Kraken Website and API Maintenance" window announced 48–145 h ahead. That is 2 for 2 — no unexplained crossing has ever been observed.

It is nonetheless a **true positive, not noise**. The venue emitted nothing, so no host missed anything that existed, but L2 is unbackfillable and the hours are genuinely short: 2026-08-06 cost ~893 s per stream, 2026-08-20 ~551 s. Expect the reconciler's loss page about two hours later.

Nothing natural comes near this bar. Over 13 clean retained days the fleet-wide minimum peaked at **6.13 s**; the bar is ~20× that. A restart cannot raise it either — `_run` seeds `last_seen` for every pair before the collector registers, so a fresh process reads ~0.

### What to do

1. **Read the venue calendar first.** `curl -s https://status.kraken.com/api/v2/scheduled-maintenances.json` and look for an entry whose `components` carry `WebSocket` or `REST` covering now. The recurring one is "Kraken Website and API Maintenance", roughly biweekly at 07:01–07:16 UTC. A match explains the page completely — go to step 4.
2. **No published window? Now it is a real incident.** Check both daemons: `docker inspect --format '{{.RestartCount}}' zcrypto-capture` and whether parquet is advancing (`find <data-dir> -name '*.parquet' -mmin -3`). A silent-but-synced stream never self-heals, so this will not clear on its own if the daemon is wedged.
3. **Check the sibling host.** Both hosts firing together is venue-side; one host alone is fleet-side and the peer's copy is the recovery path.
4. **Expect the loss page, and do not pre-empt it.** Hour H is bookable no earlier than H+2 h, at the next `*:12`/`*:42` tick — reading the residual counter before then answers reassuringly and wrongly (step 3 of the venue-status section above has the full arithmetic).
5. **Do not converge or restart on this signal alone.** Nothing in the capture path reacts to venue status, and a restart costs a resubscribe.

A Grafana query-execution failure does **not** raise this page: `execErrState: OK`, deliberately — see the note at the end of this file.

### Retire when

`zcrypto-capture-all-streams-silent` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-capture-stream-silent"></a>

## zcrypto-capture-stream-silent — ALERT

### What you are seeing

A **warning** Grafana alert, one instance per `(host, pair)` — the `pair` label names the stuck stream. That pair delivered nothing for over 300 s while its siblings kept flowing.

### What it means

The single-stuck-stream shape, which nothing else catches: the dead-man still pings, the desync rule sees no checksum failure, and the fleet-wide rule above reads its minimum off a healthy pair. Nor does the daemon heal it — recovery is desync-driven only, so a stream that is silent while still *in sync* is never resubscribed and never reconnected, at any age.

**If all 12 pairs on both hosts fire at once, this is not 24 stuck streams** — it is the fleet-wide event, and the critical rule above is the one to read. That is what both known firings were.

The bar is ~20× the measured natural maximum. The thinnest pairs really do go quiet: full-resolution archive measurement puts single-host natural quiescence at **14.78 s** (AVAX, 7.8 M messages), and the live gauge independently peaks at **14.16 s** on SOL/BTC with no restart within 26 h. Both instruments agree, so a per-pair silence in the tens of seconds is normal and this bar is not close to it.

### What to do

1. **Count the instances.** Many pairs at once ⇒ read `zcrypto-capture-all-streams-silent` instead and follow that section. One or two pairs ⇒ continue here.
2. **Check whether that pair's resubscribe went through** — `sudo docker logs zcrypto-capture 2>&1 | grep <PAIR>` on the named host.
3. **Restarting the capture daemon re-establishes every stream**, and is the remedy here precisely because the daemon will not self-heal a synced-but-silent stream. Weigh it against the resubscribe cost and the canary rule if a converge is in flight.
4. **Check the peer host for the same pair.** One host stuck is healable from the sibling's copy; both hosts stuck on the same pair is the unbackfillable case and the reconciler will book it.

### Retire when

`zcrypto-capture-stream-silent` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="capture-silence-rules-and-datasource-errors"></a>

## capture-silence-rules-and-datasource-errors — KNOWN LIMITATION

### What you are seeing

Nothing — that is the point. The two capture silence rules above carry `execErrState: OK`, so when Grafana Cloud cannot execute their query they stay silent instead of paging.

### What it means

Grafana Cloud intermittently fails to reach its own Prometheus (`dial tcp …: i/o timeout`). Measured over 2026-08-05 → 08-28, those failures produced **264** alert instances from these two rules against **52** genuine ones — 83.5 % of everything they had ever raised. Because both rules carry `for: 0s` — load-bearing for their detection arithmetic — a one-minute platform hiccup fired instantly.

The page was not merely noisy, it was **false**: its summary asserts that every book stream on a named host has been silent for minutes, which the system had not observed and could not have observed, since the query never ran. A wrong critical page on the fleet's highest-severity capture signal costs more than a missed one about Grafana's own health.

**Nothing goes unwatched.** Every other rule in `infra/grafana/alerts.yaml` still carries `execErrState: Alerting`, so a datasource outage is still reported — loudly, by many rules at once. What changed is only that these two no longer contribute a false blackout claim to that storm.

### What to do

If you suspect the alerting pipeline itself is blind rather than the fleet quiet, check the datasource directly — `uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}'` — and the healthchecks.io dead-man switches, which are an independent failure domain and unaffected by Grafana.

### Retire when

Either rule's `execErrState` is no longer `OK`, or a dedicated rule is introduced that owns "the alerting datasource is unreadable" — at which point the other rules' `Alerting` becomes redundant rather than merely loud.
