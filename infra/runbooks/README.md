# Runbooks — what to do when something demands action

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

## Scope — what belongs here, and what does not

- **Procedures** for a signal that fires at an operator, and **accepted limitations** an operator may run into while debugging. Nothing else.
- **This is not a backlog.** If acting on a section produces work, put it where work lives: something needing a *decision* opens a `T<NNNN>` per `.claude/rules/open-topics.md`; something needing *doing* goes in the memo queue. Deferrals must not accumulate here — a runbook nobody can finish reading is a runbook nobody reads.
- Every section carries a **Retire when** naming something checkable — a metric that stops existing, a rule absent from `infra/grafana/alerts.yaml`, a line no longer in the code. A retirement condition you have to *judge* is one nobody will act on.

**Split when** this file exceeds ~12 sections, or gains a second subsystem's worth of material: move to `infra/runbooks/<subsystem>.md` and keep the explicit `<a name=…>` anchors byte-identical, because alert summaries and code comments cite them. They are explicit rather than heading-derived precisely because the `— ALERT` / `— KNOWN LIMITATION` marker would otherwise become part of the slug.

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

1. **Read the state and its ladder.** The `system` value is on the page; the full transition sequence is in the capture log: `sudo docker logs zcrypto-capture 2>&1 | grep "venue status"` on either host (or the same line via Loki). Kraken's observed exit ladder is `maintenance` → `cancel_only` → `post_only` → `online`. `effective_time` has been observed only as `None` (the 2026-08-06 event, all five transitions, both hosts) — expect no advance notice.
2. **A venue-side halt DOES book permanent loss. Expect the loss page, hours later.** The 2026-08-06 halt booked **10588.382751 s** — ~15 min across all 12 pairs — as `both_streams_silent`, and `Reconciler · residual gap increased` paged for it at 09:24Z. The data is genuinely gone: the venue emitted nothing, so no host missed anything that existed, but "no component failed" is not "no loss". Do not tell yourself otherwise, and do not close the incident before the reconciler has spoken.
3. **Do NOT read `zcrypto_reconcile_residual_gap_seconds_total` during or just after the halt — it cannot answer yet, and it will answer reassuringly.** Booking waits on `SETTLE_HOURS = 2` measured from the hour's **START** (`settled_hours` takes `floor(now) − 2 h`), and the reconcile timer runs at `*:12,42` — so **hour H is eligible at H+2 h and booked at the next `:12`/`:42` tick**. Hour 07 became eligible at 09:00 and was booked at 09:12, which is exactly when the ledger records it. A read taken at 07:20 for hour 07 is not a lagging counter; it is a question the system cannot answer for another **1 h 52 m**. `zcrypto_reconcile_last_success_timestamp_seconds` does NOT protect you here: it is run liveness, not coverage — at 07:20Z it read 06:42Z (fresh), and at 08:42Z it read 08:42Z (maximally fresh) while hour 07 was still unbooked. The only sound check is the clock: **hour H is bookable no earlier than H+2 h, at the next `:12`/`:42` tick.** This exact mistake produced a false "nothing was lost" record on 2026-08-06.
4. **Check whether CAPTURE degraded** — that is a different question from whether data was lost, and it is the one you can answer now: `zcrypto_capture_seconds_since_last_book_message` per pair, `RestartCount` on both daemons. The two capture silence rules fire and auto-resolve around the window on their own; that is them working, not something to respond to separately.
5. **Do not converge or restart anything on this signal alone.** Nothing in the capture path reacts to venue status; a restart costs a resubscribe and buys nothing. The 2026-08-06 event's FEED resolved itself in 17 minutes with zero human action — but it still cost ~15 min of unbackfillable L2 on every pair, which the loss page reported 2 h later.
6. **Silence `zcrypto-capture-venue-not-online` once triaged, time-boxed — and NEVER `zcrypto-capture-venue-state-recurrence`.** The latch is a counter-presence check, so it stays firing for the daemon's whole lifetime — the counter only resets when the capture daemon restarts, which is days-to-weeks away and gated on a bake. Silence in Grafana on **that uid only**, for a bounded window; delete the silence early if the daemons restart sooner; do not delete the rule. The recurrence rule is the one signal that still reports a repeat while the latch is stuck, and it self-resolves on its own — silencing it re-opens exactly the blind spot it was added to close.

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

<a name="zaccess-bridgehead-dark"></a>

## zaccess-bridgehead-dark — ALERT

### What you are seeing

A critical-severity Grafana alert (`zcrypto-alloy-dark-zaccess`): the internet bridgehead's `up` series has been absent from Grafana Cloud for more than 10 minutes.

### What it means

The bridgehead runs Alloy **natively** (an apt package, no docker) — the only host in the fleet where that's true. When it stops shipping, every other rule scoped to `host="zaccess"` goes blind at the same time: the WireGuard tunnel handshake-age gauge, the edge TLS cert-expiry gauge, and this host's own disk-high content rule all read no data, which renders identically to healthy. Nothing on this host reacts to its own Alloy dying — there is no container to restart, no compose stack to recreate, just the one systemd unit.

### What to do

1. `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`.
2. `systemctl status alloy` — is the unit running at all?
3. `journalctl -u alloy --no-pager -n 100` — a config parse failure (a hand edit that didn't survive the next converge, or a credentials rotation that didn't reach `/etc/default/alloy`) is the usual cause on this host, since the config copy here is deliberately ungated (every converge ships it, so there is no separate drift-assert task to catch a bad render before it lands).
4. `systemctl restart alloy` is the usual fix. If it will not stay up, check `/etc/default/alloy` for the six `GRAFANA_*` values and re-converge (`--limit zaccess --tags access`) to re-render them.
5. Confirm recovery from the workstation: `uv run python infra/scripts/grafana-query.py 'up{host="zaccess"}'` → `1`.

### Retire when

`zcrypto-alloy-dark-zaccess` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-disk-high"></a>

## zaccess-disk-high — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-disk-high`): the bridgehead's root filesystem has been below 15% free for at least 30 minutes.

### What it means

The whole host is one small root filesystem (a 25 GB Linode) — Alloy, Caddy's ACME state, and the WireGuard config all live under `mountpoint="/"`, so there is no separate spool to watch the way the capture hosts' unbackfillable L2 spool needs one. This host holds no capture data and nothing on it is unbackfillable — the risk here is running the box out of room for logs or a stuck ACME renewal artifact, not data loss.

### What to do

1. `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`; `df -h /`.
2. `du -sh /var/log/* /var/lib/alloy* 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small.
3. Check for a stuck ACME renewal loop (Caddy re-requesting a cert repeatedly leaves debug artifacts) once the Caddy role (spec 00075, later phase) is live.
4. Reclaim space (`journalctl --vacuum-size=200M` is the usual first move) rather than resizing the disk — everything on this host is re-issuable, so growing the volume is a last resort, not a routine response.

### Retire when

`zaccess-disk-high` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-tunnel-stale"></a>

## zaccess-tunnel-stale — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-tunnel-stale`): the `zaccess0` WireGuard tunnel's handshake age has been over 300s on at least one end for 10+ minutes.

### What it means

Both ends of the tunnel run a probe timer that writes `zaccess_wireguard_handshake_age_seconds` from `wg show zaccess0 latest-handshakes` — the bridgehead's copy under `host="zaccess"`, the ops node's under `host="ops"`. The rule takes `max by (host)`, so each end is evaluated on its own and the notification names the end that reported stale — a genuine outage is visible from both sides and therefore raises **one instance per end**, so expect two. A healthy tunnel handshakes every couple of minutes given `PersistentKeepalive = 25` on the ops-side client conf, so 300s is already several missed keepalives, not noise. This does not mean the whole bridgehead is unreachable: that is `zaccess-bridgehead-dark`'s job (this host's Alloy itself going dark) and `zcrypto-alloy-dark-ops`'s job (the ops node's).

### What to do

1. `wg show zaccess0` on **both** ends — `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` for the bridgehead, the usual ops access for `zcrypto-ops` — and compare `latest handshake` on each.
2. Check the `Endpoint` the ops-side client conf resolves to (`/etc/wireguard/zaccess0.conf` on `zcrypto-ops`) against the bridgehead's actual public address — a home-ISP IP change on the ops side is the routine cause of a stuck endpoint, not a config error.
3. Confirm UDP `51820` is still open on the Linode Cloud Firewall and the bridgehead's own nftables rules (`firewall_extra_udp_ports` in `group_vars/access_host/vars.yml`) — a firewall change elsewhere in the fleet is the other routine cause.
4. `systemctl restart wg-quick@zaccess0` on the ops node is the usual fix — it re-initiates the handshake against the configured endpoint without touching the bridgehead's own service.
5. Confirm recovery: `wg show zaccess0` on both ends shows a handshake under a few minutes old, and `uv run python infra/scripts/grafana-query.py 'zaccess_wireguard_handshake_age_seconds'` returns a low value for both hosts.

### Retire when

`zaccess-tunnel-stale` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-cert-expiring"></a>

## zaccess-cert-expiring — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-cert-expiring`): a tracked zaccess endpoint's TLS certificate has been under 14 days from expiry for at least an hour. Each certificate is its own alert instance and the notification names it in the `target` label, so more than one can be in flight at once.

### What it means

Two probe timers write `zaccess_tls_not_after_seconds{target=...}`: the bridgehead's own probe handshakes against each Caddy vhost on `127.0.0.1:443` and writes `target="tmux"`/`target="nas"`; the ops node's probe handshakes against the NAS admin port and writes `target="nas-dsm"`. The rule takes `min by (host, target)`, so each tracked certificate is evaluated on its own and the page names the one that tripped. `tmux` and `nas` are Caddy-managed: Caddy's ACME client renews them automatically, well before 14 days out under normal operation, so either arriving at this threshold usually means renewal has been failing silently rather than an unavoidable expiry. `nas-dsm` is the Synology DSM's own certificate, outside Caddy's control — its renewal (or lack of it) is a DSM-side concern.

### What to do

1. **Read the `target` from the notification** — it names the certificate that tripped. To see every target's expiry at once, `uv run python infra/scripts/grafana-query.py 'zaccess_tls_not_after_seconds'` — one value per `target` label; `date -d @<value>` turns it into a calendar date.
2. **`tmux` or `nas`**: `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`; `journalctl -u caddy --no-pager -n 200 | grep -i acme` for renewal failures (a failed HTTP-01 challenge, rate limiting, or a stale ACME account are the usual causes — port 80 must stay reachable for the challenge). `systemctl status caddy` — confirm the unit is up and serving both vhosts.
3. **`nas-dsm`**: log into the DSM admin console directly and check its own certificate manager — this is DSM's certificate lifecycle, not something either bridgehead role touches.
4. Confirm recovery: re-run the query in step 1 — the tripped target's value should read comfortably above `time() + 14*86400`.

### Retire when

`zaccess-cert-expiring` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-ops-verify-replay-new-breakage"></a>
<a name="zcrypto-ops-verify-replay-run-broken"></a>

## zcrypto-ops-verify-replay — ALERT

### What you are seeing

Two critical-severity Grafana alerts, both scoped to the ops node's nightly canonical-archive replay:

- **`Ops · verify-replay NEW hours stopped replaying`** (uid `zcrypto-ops-verify-replay-new-breakage`) — a replay hour failed today that did NOT fail in the prior sweep.
- **`Ops · verify-replay run broken`** (uid `zcrypto-ops-verify-replay-run-broken`) — the sweep itself did not run to completion, so today's per-hour findings are unknown, not clean.

### What it means

The nightly sweep publishes three counters every run: how many hours failed, how many hours it checked in total, and whether it produced a parseable summary at all. The first alert watches the change in the failed-hour count over the last 25 hours — an hour that failed yesterday and still fails today contributes nothing to that change and stays quiet; only an hour that newly starts failing moves it. The second alert watches whether the run produced a summary at all — it goes critical on a crash, an I/O error against the read-only archive mount, a run that never started, or a run that silently found no hours to check (which used to read as healthy and no longer does). A failed hour is logged as a warning, not an error, specifically so it does not also trip the separate ops error-log alert — only a genuinely broken run does that. A companion dead-man ping for this same timer is withheld whenever the run fails to produce a summary, independently of both Grafana rules above.

### What to do

1. **For a new-breakage page**: read the per-hour findings in the run's own log output for today — pair, hour, and which check failed (anchoring, ordering, checksum, or replay itself) — then triage and record the finding somewhere durable. This alert clears itself after 25 hours and is not itself a record of what was found.
2. **For a run-broken page, read `ops_verify_replay_audit_mismatches` first — it is a discriminator, not a detail.** A nonzero value means the sweep **ran** and its own sampled audit caught cached verdicts disagreeing with a fresh replay of the very same hours: the archive was being certified partly against a cache that was wrong about N of the hours audited. That is a different and more serious situation than a crash, and the run-broken message on its own would send you hunting for one. Capture the value and the hours named in the run's log **before it clears** — the audit repairs the rows it caught, so the next healthy run publishes `0` and the evidence is gone. Read it as *the cache is unreliable*, not *N hours are bad*: re-verify the archive ignoring the cache entirely and compare the result against what the cache had been claiming.
3. **Zero mismatches: tell the deliberately-withheld summary apart from a crash** in the timer's own log output. The sweep withholds its summary — so the run reads broken rather than green — when the state directory could not be written, or when the enumeration lost more than a tenth of the hours it had already checkpointed; both say so in the log, and a crash leaves a traceback and neither. Also confirm the archive mount is populated rather than silently empty: an empty enumeration prints no census and no summary on purpose, because "zero hours checked, zero failed" would otherwise read as a clean sweep of an unmounted mirror. A read error on a *single* hour is none of these — it is isolated into that hour's own failure, the run completes, and it heals on the next run once the read succeeds.
4. **A refused eviction is usually right — the one case where it is not is a shrink you meant.** The refusal exists for a mirror that resolved empty or partial, where dropping those hours from the cache would discard verified history on a green-looking night and force an unplanned multi-night rebuild. After a **deliberate** mass shrink of the archive there is nothing to repair and the answer is to stop resisting it: delete the state directory and let the next run rebuild the cache. The rebuild announces itself in the census (everything replayed, nothing reused) and takes as many nights as the archive needs — budget them.
5. **A state-write failure part-way through a long run costs replay work, not verdicts.** The state file is written whole and swapped into place, so a failed write leaves the previous one intact and readable, and the run is killed deliberately rather than allowed to keep reporting green against state it can no longer record. Progress is saved every 250 replayed hours, so the next run resumes from the last save and loses at most ~250 hours of replaying — minutes to an hour of work, no more. What survives in the state file is only what was actually verified, so a killed run can never leave behind a verdict it did not compute. Fix the mount or the permissions and re-run; do not delete the state directory for this one.
6. **The net-zero caveat, worth internalizing before trusting silence**: if an hour is repaired and a different hour breaks within the same 25-hour window, the two changes cancel on the new-breakage count and neither alert fires. The day after healing a known-bad hour, a quiet new-breakage alert is not evidence that nothing new broke — check the run's own hour counts directly rather than reading silence as a clean bill of health.

### Retire when

`zcrypto-ops-verify-replay-new-breakage` and `zcrypto-ops-verify-replay-run-broken` are both absent from `infra/grafana/alerts.yaml` — i.e. the rules were deliberately removed.

______________________________________________________________________

<a name="zcrypto-ops-verify-replay-backlog-stuck"></a>

## zcrypto-ops-verify-replay-backlog-stuck — ALERT

### What you are seeing

A warning-severity Grafana alert (`Ops · verify-replay backlog stuck`): the nightly canonical-archive sweep has hours queued for re-verification, and that queue has not gone down across two consecutive nightly runs.

### What it means

The sweep certifies the **whole** archive every night but only *replays* what changed. Hours it has never seen before are replayed unconditionally; hours whose bytes changed since they were last verified are re-replayed oldest-first until a wall-clock budget runs out, and whatever the budget did not reach is reported as `pending` and picked up by the next run.

A backlog is therefore normal and self-clearing — a deliberate re-verification of the whole archive creates one by design, and it can legitimately take many nights. **This alert is not about the backlog existing; it is about it not shrinking.** The rule compares the backlog against its value 26 hours earlier, which spans exactly the last two runs, and pages only once "no smaller than 26 hours ago" has held continuously for 27 hours. The count published each night is held between runs, so even a *healthy* drain satisfies that comparison for a full 26 hours after the night that created its backlog — the 27-hour hold is what outlasts that, and it is why a healthy drain never reaches this page while a backlog that survived a second run does.

Warning, not critical: nothing here says the archive is wrong. It says the instrument that proves the archive is right has stopped making progress, and every night it stays stuck is another night of changed hours certified from a cache nobody re-checked.

### What to do

1. **Check `ops_verify_replay_run_ok` first — the summary's "the sweep still runs" is an assumption, not a measurement.** A run that keeps failing carries the previous `pending` forward unchanged, which is "not shrinking" by this rule's arithmetic, so a persistently broken sweep trips this page too, a day after the critical one. If `run_ok` is 0 the backlog is a symptom: follow the run-broken section above and ignore the rest of this one.
2. **Read the sweep's own census line** from the last few runs' log output — `pending=`, `replayed=`, `reused=`, `duration_s=`. `pending` falling night over night means the drain works and the alert is about to clear itself; flat or rising is the real thing.
3. **`duration_s` well under the run's budget while `pending` stays high** means the drain is not spending the time it was given: the budget is set too low, or to zero, or the drain never reached those hours. Check the budget the nightly runner passes.
4. **`reused` near zero every night** means nothing is being served from the cache at all, so the state directory is being lost between runs. Confirm the runner's writable state mount is present and that the file inside it survives a run.
5. **`pending` rising while `replayed` merely keeps pace with the archive's daily growth** means hours are going stale faster than the drain clears them — a re-verification larger than one night's budget. Confirm it was deliberate; if it was, either wait it out (the count must still fall every night) or raise the budget for a few nights.
6. **Do not delete the state directory to clear this.** A rebuild replays the entire archive, which is the same work the backlog already represents, and at current growth that no longer fits in one night. Deleting it is the right move only for a refused eviction after a deliberate archive shrink — the run-broken section above.

### Retire when

`zcrypto-ops-verify-replay-backlog-stuck` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-engine-sleeve-count-changed"></a>

## zcrypto-engine-sleeve-count-changed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · sleeve composition changed`): the number of the shadow engine's sleeves carrying non-zero exposure stepped up or down within the last 26 hours. Nothing is broken. This alert announces a change in **what the book is**, not a fault.

### What it means

The engine's book is three sleeves — `B`, `A1`, `A2` — combined at fixed one-third weights, and the combination is deliberately fixed: the weights do not react to which sleeves are currently earning. A sleeve that is sitting flat contributes zero and costs nothing to carry; it re-arms on its own signal, with no deploy and no config change.

For a long stretch only `A2` has carried exposure, so the live book has been structurally a **one-sleeve book at roughly a sixth of that sleeve's own gross** — one third from the fixed weights, halved again by the exposure governor. Two consequences follow, and both are why this alert exists rather than a dashboard panel:

- **Gross moves roughly in proportion to the count.** A second sleeve arming is not a marginal change in exposure; it is close to a doubling of the combined book's gross, and a third is close to a tripling. Everything sized against the one-sleeve state — the drift band, the expected order notionals — was derived under a gross that no longer holds.
- **Order placeability flips with it.** At one-sleeve gross the intended orders sit under the venue's minimum order sizes, which is why so few of them would clear at small live size. More gross moves orders back above those minimums, which changes turnover, fee drag and slippage all at once.

The alert reads `changes(zcrypto_engine_active_sleeves[26h])`, so it fires on a step in **either** direction: a dormant sleeve arming, or an active one going flat. The window is wider than a day, so the page persists long enough to be seen and then ages out on its own.

Two things this alert deliberately does **not** do. It does not fire when the engine goes dark — the series simply stops, and `noDataState` is `OK`, because engine liveness is the healthchecks.io dead-man's job and the cycle-completed staleness rule's, not this one's. And it does not fire on a failed cycle: a cycle that never reached the build reports no composition at all, so both gauges hold their previous values rather than reading as "everything went flat".

### What to do

1. **Identify which sleeve moved, and in which direction.** `uv run python infra/scripts/grafana-query.py 'zcrypto_engine_sleeve_gross'` — one value per `sleeve` label. Compare against `zcrypto_engine_active_sleeves` over the last few days to see when the step landed. A single 4h cycle's blip and a sustained re-arming are different events; do not act on one cycle.
2. **Do not restart, converge, or "fix" anything.** The engine is behaving exactly as designed — the sleeve's own signal turned on or off. There is no failure here to recover from, and a restart changes nothing about the composition.
3. **Re-derive the numbers that were sized against the old composition** before the next go-live decision reads them: the model-consistency band the gate compares realized performance against, and the expected order notionals versus the venue minimums. Both were derived under the previous sleeve count and neither updates itself.
4. **Record the transition durably** — date, which sleeve, the gross before and after. This alert ages out within a day and is not a record. The book's composition history is what a later gate reading depends on, and the last such transition went unrecorded for months precisely because nothing announced it.
5. **If the count went DOWN to one or zero**, treat it as information, not an emergency: a long-only sleeve going flat in a downtrend is the risk control working. Zero active sleeves means a flat book — no exposure, no turnover — which is a legitimate state and not a reason to intervene.

### Retire when

`zcrypto-engine-sleeve-count-changed` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_engine_active_sleeves` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-engine-exec-armed-too-long"></a>

## zcrypto-engine-exec-armed-too-long — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · order submission has been armed for over six hours`): `zcrypto_exec_armed` has read 1 continuously for the whole of the last six hours.

### What it means

The engine may submit orders only when BOTH arming keys are present: the `armed` flag baked into its deployed config, and an arm file the operator places on the engine host. `zcrypto_exec_armed` deliberately conflates the two into one 0/1 gauge — remote telemetry can say THAT the engine is armed, never WHICH of the two keys is set. The alert reads `min_over_time(zcrypto_exec_armed[6h]) == 1`: the MINIMUM over the window, not an average, so a single dip to 0 — a disarm at any point — clears the condition; only a gauge that has read 1 at every sample for the whole six hours trips it.

Arming is expected only inside an attended probe window, and is normally removed by the operator when that window ends. This alert exists because the failure mode is forgetting to remove it, not the arming itself — firing does not by itself mean anything went wrong, or that an order was actually submitted: the gate-level reading still needs the kill switch clear, the restart hold cleared, and the venue online before anything could move. But an engine left armed for six unattended hours has quietly removed one of the two keys that are supposed to stand between a mistake and real money, which is worth resolving even when nothing downstream has gone wrong yet.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. This is the only place `reasons` and the two arming keys are visible separately — the dashboard and this page can show only that the engine is armed, never which key put it there.
2. **If the probe window is over, remove the arm file.** Deleting it disarms the engine immediately — no deploy, no restart, no engine downtime. `zcrypto_exec_armed` reads 0 on the engine's next evaluation (at most one cycle, roughly four hours), and because the rule reads `min_over_time` over the window, a single 0 sample is enough to drop it — the alert clears at the very next rule evaluation after that disarmed reading lands, not after six more hours have to pass.
3. **If the probe window is still legitimately open, leave it and let the alert ride.** It re-fires on the same condition every time `for: 15m` re-qualifies, so expect it to keep paging for the length of a long window; that repetition is intentional, not a bug.
4. **If you did not expect the engine to be armed at all**, treat this as a live safety-envelope breach: read the engine log and the `exec-status` output together, remove the arm file, and confirm nothing was submitted through the same window — there is no order-submission telemetry on this board yet, so check the engine journal and process log directly.

### Retire when

The engine begins arming continuously as its normal operating mode (order submission goes live and stays live). At that point a duration-based "armed too long" rule fires forever, and this rule must be **REPLACED** by one shaped for continuous arming — never silenced in place. Until then, `zcrypto-engine-exec-armed-too-long` retires only if it is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-engine-exec-kill-tripped"></a>

## zcrypto-engine-exec-kill-tripped — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution kill switch is engaged`): `zcrypto_exec_kill_tripped` has read 1 for the last five minutes.

### What it means

The kill file is present on the engine host, which forces the gate level to 0 (nothing may be submitted) regardless of arming, restart hold, or venue state — it is the one input that overrides every other reading. This is a deliberate control, not a fault: the switch exists so a human can refuse all submission immediately, and the alert exists because the failure mode is forgetting the switch is engaged, not the engagement itself. Firing does not mean anything is broken.

### What to do

1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. `reasons` will list `kill_switch` alongside whatever else the gate is currently refusing on — remote telemetry alone cannot show this.
2. **If the switch was engaged deliberately and the reason still holds**, silence this alert in Grafana for the expected duration rather than letting it keep paging — it re-fires every time `for: 5m` re-qualifies for as long as the file exists.
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears immediately: no deploy, no restart, no engine downtime.
4. **If you did not expect the kill switch to be engaged**, that is itself the finding — read the engine log for whatever wrote the file before removing it.

### Retire when

`zcrypto-engine-exec-kill-tripped` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-engine-exec-not-evaluated"></a>

## zcrypto-engine-exec-not-evaluated — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · the execution safety gate has stopped being evaluated`): `time() - zcrypto_exec_last_evaluation_timestamp_seconds` has read above 17100 s (4h45m) for 10 minutes, or the series is missing entirely.

### What it means

This is the heartbeat for the whole execution envelope, not a reading of any one input. The gate is evaluated at engine start and again after every cycle, roughly four-hourly, and every one of the six `zcrypto_exec_*` families is only ever updated as a side effect of that evaluation. If the evaluation call is dropped by a regression — anywhere in the cycle path, however unrelated it looks — every one of those six gauges FREEZES at its last published value. Cycle telemetry (`zcrypto_engine_cycle_success`, `zcrypto_engine_cycle_completed_at_seconds`) can keep reading perfectly healthy through this, because nothing about the cycle itself needs to fail for the gate call inside it to be skipped. A stale `disarmed` reading is indistinguishable on this dashboard from a live one — this alert is the only signal that can tell the difference.

`noDataState` is `Alerting` here, deliberately unlike the two rules above: a gate that has NEVER published at all — a fresh converge that never ran, or an exporter that never started — is this rule's worst case, not a state it should stay quiet through. Every other exec gauge already reads a safe default (0 / disarmed) before the first evaluation, so their own absence is comparatively low-stakes; this heartbeat is the one thing that must page on total silence too.

### What to do

1. **Check whether cycles are still completing** (the cycle-staleness alert, the cycle-age panel above this one on the Engine board). If cycles are also stopped, this is a symptom of the engine being down entirely — follow that alert instead, and expect this one to clear once the engine restarts and evaluates once at startup.
2. **If cycles ARE completing but this still fires**, the gate evaluation call has been dropped from the cycle path specifically — a code regression, not an infrastructure problem. Do not trust any of the other five `zcrypto_exec_*` readings on the board until it is fixed: every one of them is frozen at whatever it last read, and a frozen `disarmed` looks identical to a live one.
3. **Read the current state directly on the engine host**, never from the dashboard, while this is firing: `zcrypto engine exec-status`. It re-evaluates the gate on the spot rather than reading a possibly-stale published value, and it is the only place `reasons` is visible at all — that field never reaches Grafana, so there is no dashboard reading it could otherwise be checked against.
4. **Restore evaluation** (a code fix and a redeploy, or a restart if the process itself has wedged without crashing) and confirm the heartbeat panel starts advancing again before considering this resolved — the alert clears itself once a fresh sample lands.

### Retire when

`zcrypto-engine-exec-not-evaluated` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_exec_last_evaluation_timestamp_seconds` is no longer in the capture role's keep-list (`infra/ansible/roles/capture/files/config.alloy`) — either way the rule can no longer fire and this section describes nothing.

______________________________________________________________________

<a name="zcrypto-venue-concordance-failed"></a>

## zcrypto-venue-concordance-failed — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · venue concordance failed`): `zcrypto_venue_concordance_failures` read above zero on the most recent cycle — a ratified instrument is missing from the venue's loaded instrument set, or its constraints came back absent or unparseable.

### What it means

The executor's basket and what the venue actually reports have diverged for at least one leg: a delisting, a halted instrument, or a change to the constraint schema the parser does not yet handle are the usual causes. This is read-only observability — venue truth is journaled, never consulted for targets or orders, so a concordance failure changes nothing about what the engine does and no order path is affected by it on its own.

### What to do

1. Read the newest `venue-<HH>.json` on the engine host for the per-leg failure strings — it names which instrument and why.
2. This is read-only observability, so nothing here is auto-remediated. Do not converge on this alone.
3. Confirm recovery: the next cycle's `venue-<HH>.json` reads `status: "ok"` with an empty failures list, and `zcrypto_venue_concordance_failures` reads back to 0.

### Retire when

`zcrypto-venue-concordance-failed` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-venue-snapshot-stale"></a>

## zcrypto-venue-snapshot-stale — ALERT

### What you are seeing

A warning-severity Grafana alert (`Engine · venue snapshot is stale`): no successful venue-truth snapshot has landed in over five hours — one 4h cycle plus slack.

### What it means

The boundary snapshot hook has stopped producing a fresh reading. The cycle itself may still be running and journaling targets fine — venue truth can never block a boundary by design, so a stuck or failing snapshot hook does not by itself mean the engine is down; check cycle liveness separately before assuming otherwise. Note that the gauge is seeded from the newest on-disk venue record at startup, so a routine engine restart alone does not trigger this — something has to actually stop producing.

### What to do

1. Check the engine container is up and cycles are landing — the newest `cycle-<HH>.json` on the engine host.
2. Read the newest `venue-<HH>.json` for a `status: "error"` and its reason.
3. Confirm recovery: the snapshot-age gauge reads within the last cycle interval and the newest `venue-<HH>.json` reads `status: "ok"`.

### Retire when

`zcrypto-venue-snapshot-stale` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-ops-tapebars-permanent-gap"></a>

## zcrypto-ops-tapebars-permanent-gap — ALERT

### What you are seeing

A warning-severity Grafana alert (`Ops · tape-bars permanent gap`): `zcrypto_tapebars_days_gap` is above zero. One or more settled days were never published into `tape-bars` and have now fallen outside the sweep's re-scan window.

### What it means

**This is the only signal that will ever report this event, which is why it pages rather than sitting on a dashboard.** While a day is inside the re-scan window the sweep keeps retrying it and counts it as `days_unhealed`. Once the watermark carries the window past it, the day leaves every other counter — `days_unhealed` stops counting it, the exit code stays 0, and the dataset simply reads short. `days_gap` is computed from the archive calendar and the set of published files, so it keeps reporting after the fact.

The usual cause is a trade-tape hole the healer could not close: the sweep refuses a day whose `trade_id` sequence is not contiguous, because publishing it would write a silently short day into a dataset with no rewrite path. A day the reconciler booked `trades_unrecoverable` will never become publishable, and that is the honest outcome — a permanent, *named* hole rather than a quiet wrong number.

It is **not** an urgent outage. Nothing is degrading; a day that was already missing has become permanently missing.

### What to do

1. **Find which pair and day.** Read the runner's log on `zcrypto-ops` for the `days_gap` line, or list what is absent: compare the archive's day calendar against the published finals under the dataset root.
2. **Ask whether the tape can still be healed for it.** `uv run zcrypto archive backfill-trades <primary> <reconciled> --detect-only --pair <PAIR>` reports the loss without minting. If REST can still serve the missing ids, a heal followed by a widened `--rescan-days` on one manual run will let the day publish.
3. **If the ids are unrecoverable, record the gap and stop.** Note the pair, the day and the reason where the dataset's consumers will read it. Do not widen the settle gate or relax the heal check to make the day publish — a short day is indistinguishable from a quiet market once written, which is precisely what this design refuses to do.
4. **Do not re-run with a fresh output root to "fix" it.** Re-materialising rebuilds every day the archive still holds, which hides the gap rather than closing it, and costs the full history.

### Retire when

`zcrypto-ops-tapebars-permanent-gap` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_tapebars_days_gap` is no longer in the ops role's keep-list (`infra/ansible/roles/ops/files/config.alloy`).

______________________________________________________________________

<a name="zcrypto-ops-tapebars-not-advancing"></a>

## zcrypto-ops-tapebars-not-advancing — ALERT

### What you are seeing

A warning-severity Grafana alert (`Ops · tape-bars not advancing`): no new `tape-bars` day has been published for more than 48 hours.

### What it means

**The materializer is probably reporting success.** A day whose trade tape is not yet heal-complete is deferred, not failed — the sweep counts it in `days_unhealed` and exits 0 by design, so the exit-code alert stays quiet and a naive "last success" stamp would keep advancing hourly while the dataset froze. That is why this rule reads `zcrypto_tapebars_last_publish_timestamp_seconds`, which moves only when a day is actually written.

A day becomes eligible roughly 26 hours after it ends, so publishing is about daily; 48 hours means two consecutive days produced nothing. The cause is almost always **upstream of the materializer**: the daily REST trade backfill has stopped healing the tape, the archive pull has stalled, or capture itself is down. The materializer refusing to publish an unhealed day is the design working, not the fault.

### What to do

1. **Check the healer before the materializer.** On `zcrypto-ops`, confirm the archive pull is running and that the daily `backfill-trades` leg ran: its stamp is `.trade-backfill-last-utc-day` in the ops data dir, and it fires on the first pull cycle after 00:00 UTC.
2. **Check capture is still writing.** If the trade tape has no new hours, nothing downstream can advance — that is a capture incident, and the capture dead-men own it.
3. **Read `days_unhealed` and `errors` from the same runner log.** A high `days_unhealed` with zero `errors` confirms the deferral path (upstream); non-zero `errors` points at the materializer or a corrupt segment instead.
4. **Do not lower the settle gate or bypass the heal check to make days publish.** The gate is what keeps un-healed bars out of a dataset that has no rewrite path.

### Retire when

`zcrypto-ops-tapebars-not-advancing` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_tapebars_last_publish_timestamp_seconds` is no longer exported by the ops runner.

______________________________________________________________________

<a name="refdata-sweep-due"></a>

## refdata-sweep-due — SCHEDULED REMINDER

### What you are seeing

A message in Slack `#zcrypto` saying the Kraken reference-data sweep is due. It is not an alert — nothing is wrong. It is a **calendar trigger with no metric behind it**, armed as a scheduled Slack message because the facts it re-confirms are owned by a third party and move without emitting any signal we could alert on.

### What it means

The master plan marks fees, fee tiers, borrow-rollover rates, pair lists, MiCA status, tax rules and market-data pricing as **externally owned**. A stale one is silent: nothing breaks, nothing fires, and a decision quietly gets taken against last month's numbers. The sweep exists so that "re-confirmed, identical" is distinguishable from "never re-run" — the register's re-confirmation log is that distinction, one row per sweep.

Two facts about the sources decide how to read the result, and both were learned the hard way:

- **Kraken's public endpoint churns constantly and lags reality.** Sweep #1 saw 93 pairs removed and 13 added while all twelve candidates held — so `raw_sha256` changes almost every sweep for reasons touching nothing we depend on. It also still served the **pre-2026-07-09** fee schedule a month after that schedule was superseded.
- **The account's own fee tier is behind a login**, so no automation can reach it. That half is yours.

### What to do

Run `/zcrypto-refdata-sweep` — the skill carries the procedure and the exact code. In short:

1. **Automated half**: re-fetch, re-render, diff the rendered tables (never the hash), append a log row in `docs/reference/kraken-snapshot-register.md`. The stamp moves even on an unchanged sweep.
2. **Attended half**: open **Kraken Pro → Fee tab**, report **tier** and **30-day USD spot volume**. Unchanged → logged; changed → `docs/reference/kraken-fee-schedule.md` is corrected *and* the re-pricing named (`cli/costs/fees.py` encodes that ladder verbatim); unavailable → recorded as **not re-read**, never inherited from the previous row.
3. **Never cost anything off the register's fee columns.** `kraken-fee-schedule.md` owns the level; those columns are a drift detector on the endpoint. If they finally move, reconcile *back* to the fee doc rather than adopting the newer-looking API numbers.
4. **Re-arm the next reminder** — a scheduled Slack message fires once. Scheduling the following month's is part of closing this one out, or the routine silently stops after a single run.

Out of scope here: MiCA status, tax rules and market-data pricing have no endpoint and are human re-reads belonging to the pre-go/no-go sweep, which lives in `T0085`, not in this cadence.

### Retire when

`docs/reference/kraken-snapshot-register.md` is absent from the repo — the artifact this routine maintains. Until then the cadence outlives any individual reminder, which is why step 4 exists.

______________________________________________________________________

<a name="engine-probe-window"></a>

## engine-probe-window — PROCEDURE

### What you are seeing

You are about to run — or are in the middle of — an attended live-order probe window on the engine. **Nothing has fired**: no alert sent you here and no guard tripped. You opened this because a probe window is being planned or is under way, and this is the only sanctioned way to run one.

Real money moves — roughly €10–30 per leg — on the host that holds the live trade key.

### What it means

The engine's order path submits **only operator-authored probe plans**, and only inside an attended window bounded by two arming keys: the `exec_armed` value baked into the deployed config, and an `armed` file placed on the engine host. Both must be present for anything to be submitted; removing either one disarms it. Every step below exists because its omission has a named failure, and where a step's *position* in the sequence matters, the step says what happens if you take it early — that ordering is load-bearing, not ceremonial.

Where everything lives — never guess these:

- **Engine host** `zcrypto` (`ssh zcrypto`); the container is `zcrypto-engine`; the CLI and the rendered config live inside it.
- **Control files**: `/var/lib/zcrypto-engine/exec/` — `armed`, `kill`, `restart-hold`, and the plan file `probe-plan.json`. Presence is the whole protocol; contents are informational.
- **Journal**: `/var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/` — `cycle-<HH>.json`, `exec-<HH>.json`, `venue-<HH>.json`.
- **`<HH>` is the 4-hourly cycle boundary** (00/04/08/12/16/20 UTC), never the wall-clock hour. A record written at 09:14 UTC is `…-08.json`.
- **Rendered config**: `/opt/zcrypto-engine/zcrypto.toml`, rendered by the deploy from `infra/ansible/roles/engine/templates/zcrypto.toml.j2`. Never hand-edit it on the host; the next converge overwrites it.

Three reads you will use repeatedly. **Scope every `docker inspect` to one field with `--format`** — this container carries the live trade key in its environment, and an unscoped inspect prints it.

**The gate read** — run it in the container, which is where the CLI and the config are:

```
sudo docker exec zcrypto-engine zcrypto engine exec-status
```

It prints `level=<none|reduce_only|full>`, then a `reasons=` line carrying every condition that restricted the level, comma-separated — a single `-` means none — then every gate input on its own line. It re-evaluates the gate on the spot, and it is the **only** place the reasons exist at all — they never reach Grafana, and `zcrypto_exec_armed` conflates the two arming keys into one gauge.

**The ledger read** — always by value, never by presence:

```
sudo python3 - <<'PY'
import json, pathlib
root = pathlib.Path("/var/lib/zcrypto-engine/journal")
p = max(root.glob("*/exec-*.json"), key=lambda q: q.stat().st_mtime)
d = json.loads(p.read_text())
print(p, "level=", d["level"], "reasons=", d["reasons"])
for e in d.get("plans", []):
    print(" plan", e["plan_id"], e["disposition"], e["reasons"])
    for i in e["intents"]:
        print("   intent", i["index"], i["outcome"], i["reasons"], "filled_qty", i["filled_qty"])
for r in d["submitted"]:
    print(" order", r["client_order_id"], r["state"], "filled_qty", r["filled_qty"])
    for ev in r["events"]:
        if ev.get("event") == "fill":
            print("     fill", ev["qty"], "@", ev["px"], "fee", ev["fee"], ev["fee_currency"], ev["liquidity"], ev["trade_id"])
PY
```

**The venue-truth read** — positions, balances and the instrument constraints the engine last saw:

```
sudo python3 - <<'PY'
import json, pathlib
root = pathlib.Path("/var/lib/zcrypto-engine/journal")
p = max(root.glob("*/venue-*.json"), key=lambda q: q.stat().st_mtime)
d = json.loads(p.read_text())
print(p, "status", d["status"])
if d["status"] != "ok":
    print("  error:", d.get("error"))
else:
    print("  snapshot_at:", d["state"]["snapshot_at"])
    print("  positions:", d["state"]["positions"])
    print("  balances:", d["state"]["balances"])
PY
```

### What to do

#### 1. Pre-probe — before anything touches the host

1. **Sweep for blockers, and present the result together with the arming request.** Read `### Open` and `### Partially done` in `docs/open-topics/README.md`, and grep `docs/memo.local.md` for anything in flight against the engine. "Ready" without the sweep is not ready.
2. **Confirm the deployed code is the code you tested.** The engine row in `docs/reference/fleet-pins.md` records the digest running on `zcrypto` and the revision it was built from. Confirm the running digest matches — `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine` — and that your working tree is at that revision. Then run the two guards that catch a drift between the committed cost floors / ratified basket and what the venue reports: `uv run pytest tests/test_costmin_drift.py tests/test_basket_concordance.py` → expect `2 passed`. A failure means the floors or the basket have moved since that image was built; stop, do not arm.
3. **Confirm funding covers the plan, by hand, before the tooling does it for you.** Take the free EUR balance from the venue-truth read (the live balances spell the currency `ZEUR`). The plan's total `notional_eur` must be at or under `exec_max_plan_notional_eur` in `/opt/zcrypto-engine/zcrypto.toml` (rendered `100.0`), and `sum(notional ÷ leverage) × 2.5` over the margin intents must fit under that free balance. `probe-plan --check` recomputes both below and refuses on either — this step is so you learn it before the window, not during it.
4. **Only the account owner authors and places a plan.** A plan file the owner did not place does not exist to this process.

#### 2. Arm — two keys, in this order

1. **Read the digest the engine is running**: `sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine`. This converge changes no image — you pass that same digest straight back, so nothing is re-pinned, no secondary bake is owed, and the pins check passes against the row already in `fleet-pins.md`.
2. **Edit one line** in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`: `exec_armed = false` → `exec_armed = true`. There is deliberately **no** `-e` override for this value — arming is a reviewed one-line diff in the repo, not a flag anyone can type on a command line.
3. **Converge, inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC — the play refuses outside it):
   ```
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine \
     -e converge_primary=true \
     -e engine_image_digest=sha256:<the digest from step 1>
   ```
   `converge.sh` runs the `--check --diff` preview first and then takes a typed confirm of the literal string `zcrypto`. **Read the preview**: exactly one line of `/opt/zcrypto-engine/zcrypto.toml` changes, `exec_armed = false` → `exec_armed = true`. Anything else in that diff means your tree does not match the fleet — abort and reconcile the tree first.
4. **The restart latches the reduce-only hold — verify reconciliation before you clear it.** The gate read prints `level=none` and `reasons=arm_file_absent,restart_hold`: exactly those two, in that order. If `config_not_armed` is still in the list the converge did not land the new value; fix that before going on. Then run the venue-truth read and confirm the positions and balances you are starting from — no open positions, EUR only.
5. **The owner clears the hold**: `sudo rm /var/lib/zcrypto-engine/exec/restart-hold`. Gate read → `level=none`, `reasons=arm_file_absent`.
6. **The owner creates the arm file**: `sudo touch /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=full`, `reasons=-`. If `venue_not_online` shows up instead, Kraken itself is not `online` — wait it out, since nothing can be submitted until it is. The engine is now armed, and the `zcrypto-engine-exec-armed-too-long` alert above will page if the window outlives six hours — that is the rule working, not a fault.

#### 3. Drill before money — both drills green before any funded plan

Three plan-file mechanics that apply to **every** plan from here on:

- **A plan expires 60 minutes after its own `created_at`**, which must be a timezone-aware ISO timestamp. Author, check and place inside that hour, or the engine refuses it and journals the refusal.
- **Place a plan by renaming it into position — never by writing it in place.** The executor stats the plan path every 5 seconds and reads whatever is there; a file still being written parses as garbage, is journaled as a refusal, and is **deleted**. A `mv` inside the same directory is atomic, so the executor sees either the whole file or no file.
- **A `plan_id` already in the execution ledger for today or yesterday is refused.** Every plan gets a fresh id.

**Drill A — the rest-cancel drill: the whole machine, zero fills, zero fees.**

1. Author the plan on the workstation. `mode: rest-cancel` prices its order well away from the touch and cancels it the moment the venue acknowledges — a resting, untouched order costs nothing.
   ```json
   {
     "plan_id": "drill-a-2026-08-18",
     "created_at": "2026-08-18T09:05:00+00:00",
     "intents": [
       {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "rest-cancel", "notional_eur": 20.0, "leverage": 2}
     ]
   }
   ```
2. Copy it to the engine host, into the state directory the container also sees, under a **staging** name:
   ```
   scp plan.json zcrypto:/tmp/probe-plan.json
   ssh zcrypto
   sudo install -o zcrypto-engine -g zcrypto-engine -m 0640 /tmp/probe-plan.json /var/lib/zcrypto-engine/exec/probe-plan.staging.json
   rm /tmp/probe-plan.json
   ```
3. Validate it offline — read-only, mutates nothing:
   ```
   sudo docker exec zcrypto-engine zcrypto engine probe-plan /var/lib/zcrypto-engine/exec/probe-plan.staging.json --check
   ```
   Expect the gate verdict, a `venue snapshot: <timestamp>` line, one line per intent (`[0] BTC/EUR buy open rest-cancel: notional 20.00 EUR, costmin <X> EUR`), and a last line `plan ok: 1 intent(s), total notional 20.00 EUR`. Any refusal exits non-zero as `plan refused: <every reason, semicolon-separated>` — fix the plan; do not place it. The check is **advisory**: the engine re-validates every plan live before any order, so a clean check is not a permission.
4. Place it atomically: `sudo mv /var/lib/zcrypto-engine/exec/probe-plan.staging.json /var/lib/zcrypto-engine/exec/probe-plan.json`.
5. Within about five seconds the executor journals the plan and **deletes the file**. Confirm: `sudo ls -l /var/lib/zcrypto-engine/exec/` shows no `probe-plan.json`.
6. Read the ledger by value. Expect the plan entry `accepted` with empty reasons; its intent `outcome rest_cancel_ok` with `filled_qty 0.0`; one order row ending `state canceled` with `filled_qty 0.0` and **no** `fill` lines at all.
7. Read the counters by value from the workstation, allowing a minute for the scrape and remote write:
   ```
   uv run python infra/scripts/grafana-query.py 'zcrypto_exec_orders_total{host="zcrypto"}' 'zcrypto_exec_fills_total{host="zcrypto"}' 'zcrypto_exec_fees_eur_total{host="zcrypto"}'
   ```
   Expect the `submitted`, `accepted` and `canceled` outcomes to have advanced, **every** `zcrypto_exec_fills_total` series still `0`, and `zcrypto_exec_fees_eur_total` still `0`. A number, never `(no series)`.

**Drill B — the disarmed refusal: prove the key actually refuses.**

1. `sudo rm /var/lib/zcrypto-engine/exec/armed`. Gate read → `level=none`, `reasons=arm_file_absent`.
2. Place a second `rest-cancel` plan with a **new** `plan_id`, exactly as in drill A steps 1–5.
3. Expect the plan entry to still read `accepted` — the plan-level checks do not read the gate — and **every intent** to read `outcome refused` with `reasons ['arm_file_absent']`. No order row is created for it, nothing reached the venue, and `zcrypto_exec_orders_total{outcome="refused"}` advances.
4. Re-create the arm file (`sudo touch /var/lib/zcrypto-engine/exec/armed`) and confirm `level=full` before going on.

#### 4. Execute — the funded plans

**Three rules hold for every funded plan below, without exception.**

- **Never drop a funded plan inside the final 60 minutes before a 4-hourly boundary** (00/04/08/12/16/20 UTC). Run `date -u` immediately before placing; if the next boundary is under 60 minutes away, wait for it to pass. The 4-hourly cycle runs synchronously on the node's single event-loop thread and can hold that thread for up to about 25 minutes when a refresh degrades. While it is held no 5-second tick fires, so **none** of the mid-flight revocations — the kill file, a disarm, quote staleness, the intent's own time-box — can act on a resting order. This rule is the only thing keeping a funded order from resting through that window.
- **Every plan is signed off on its own**: the owner reads the `--check` output and personally places the file. Drill plans included.
- **Nothing retries itself.** An intent ending `unfilled`, `refused`, `rejected`, `partial` or `ambiguous` stops there. **`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI and establish what actually reached it before placing anything else on that symbol.

**Step 1 — the open plan, both positions in one plan.** A BTC/EUR margin long and an ETH/EUR margin short, leverage 2, €10–30 each:

```json
{
  "plan_id": "open-2026-08-18",
  "created_at": "2026-08-18T09:35:00+00:00",
  "intents": [
    {"symbol": "BTC/EUR", "side": "buy",  "action": "open", "mode": "execute", "notional_eur": 20.0, "leverage": 2},
    {"symbol": "ETH/EUR", "side": "sell", "action": "open", "mode": "execute", "notional_eur": 20.0, "leverage": 2}
  ]
}
```

The short is on ETH and not on BTC on purpose: an opposing leveraged order on a pair that already holds a margin position **closes** that position instead of opening a second one, so a BTC/EUR short beside the BTC/EUR long would leave you with one position and one rollover stream instead of two.

Monitor with the ledger read (each fill carries `qty`, `px`, `fee`, `fee_currency`, `liquidity`, `trade_id`) and the Engine board's **Execution — what actually happened at the venue** row.

**Step 2 — hold at least about 9 hours.** Rollover recurs every 4 hours a position is open, so ~9 h of wall clock buys two rollover events per position. Confirm both are visible in the Kraken ledger export (Kraken → History → Export → Ledgers) before closing anything.

**Step 3 — the close plan: the ETH/EUR short only, closed by the engine.** One intent, wrapped in the same plan envelope as above (a fresh `plan_id`, a fresh `created_at`, an `intents` list):

```json
{"symbol": "ETH/EUR", "side": "buy", "action": "close", "mode": "execute", "notional_eur": 20.0, "leverage": 2}
```

`notional_eur` on a margin closer is **advisory** — the engine sizes the close from the live position and submits it reduce-only, so the same bound is enforced at both ends. This is the first live use of reduce-only anywhere in this system: a venue rejection halts the intent and surfaces to you, with no retry.

**Step 4 — the settle act: the owner settles the BTC/EUR long by hand in the Kraken web UI, and only when no intent is in flight.**

The engine cannot do this — its adapter has no settle-position order type at all — so this half is yours. Settling in kind repays the borrowed EUR from wallet balance and converts the position into a spot BTC holding; Kraken charges no trade fee on settling in kind.

**Preconditions, and their order is not optional.** Settle only after (a) two rollover events are visible in the ledger export for both positions, and (b) the close intent has reached a **terminal** state in the ledger and no intent is in flight.

**The consequence of settling early, spelled out because it is not recoverable inside the window.** One of the engine's automatic kill trips is deliberately **not** scoped to the engine's own orders: after an intent reaches a terminal state, the executor compares the venue's position in that intent's instrument against what its own fills account for, and trips on any difference larger than one lot step. A hand settle is, by construction, position movement the engine's fills do not account for. Settle while an intent is still in flight and you **will** create the kill file — it latches, resting orders are canceled, every further intent is refused, the `zcrypto-engine-exec-kill-tripped` alert pages, and the window cannot continue until a human deletes `/var/lib/zcrypto-engine/exec/kill`.

**Step 5 — read the disposal quantity out of the ledger export.** Export the ledger again after the settle and read the BTC amount the settle credited. That figure — not a balance the engine reports, not an estimate — is the disposal plan's `qty`: whether a hand-placed settle propagates live into the engine's balance view is unproven, and a plan-carried quantity removes the dependency entirely. Floor it to the leg's lot step, which `probe-plan --check` prints; the check refuses a `qty` that is not a multiple of that step, and rounding **up** would put the sell over the balance.

**Step 6 — the disposal plan: the engine sells the residual spot BTC, so the probe ends flat.** Again one intent in its own plan envelope:

```json
{"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "qty": 0.00021}
```

No `leverage` key — its absence is what makes this a spot order — and a spot close carries `qty` instead of `notional_eur`. Same sign-off and the same 60-minute boundary rule as every other funded plan. An over-quantity sell is rejected by the venue and halts attended; a remainder below the leg's `ordermin` is accepted as terminal dust.

**Step 7 — re-sync the tax depot and record the verdict.** After all three terminal acts — the close, the settle, the disposal — re-sync the Kraken depot in Blockpit and record pass/fail in `docs/research/14.phase6-decisions.md` with the evidence: bucket assignment (derivatives PnL vs spot disposal), rollover fees attached as costs, FIFO lots intact, no phantom balances, and the disposal's gain/loss computed off the basis the settle carried.

**On a FAIL, registering the fallback build item is a step of THIS checklist, executed in the same session as the verdict — never a remembered promise.** Open a topic file under `docs/open-topics/` (convention: `.claude/rules/open-topics.md`; file mechanics: the `topic-ops` skill) for the deterministic pre-transform that maps Kraken's ledger and trades exports into Blockpit's manual-import CSV with explicit margin-PnL rows, and queue it in the memo in the same pass — a topic registered but not queued is invisible when work is picked up.

#### 5. Disarm — both keys down, the second one the same day

1. **The owner deletes the arm file**: `sudo rm /var/lib/zcrypto-engine/exec/armed`. This disarms immediately — no deploy, no restart, no engine downtime. Gate read → `level=none`, `reasons=arm_file_absent`.
2. **Converge `exec_armed` back to `false` the same day — not "eventually".** Between deleting the arm file and that converge the deployed config still says armed, so arming is effectively **one** key rather than two: anything that recreates a file at `/var/lib/zcrypto-engine/exec/armed` re-arms the engine with no review and no deploy. Revert the one line in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` and converge with the same command as the arm step (same running digest, same inter-cycle gap). Read the preview: exactly one line changes back.
3. **Confirm both keys are down.** Gate read → `level=none` with `reasons=config_not_armed,arm_file_absent,restart_hold` — three reasons; the restart hold is back because the converge restarted the engine, and that is the correct resting state, so leave it. From the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed{host="zcrypto"}'` reads `0`.
4. **Treat any restore of the engine state directory as re-arming until proven otherwise.** The arm file and the plan file both live in `/var/lib/zcrypto-engine/exec/`, which sits inside the directory that is also the backup unit — a restore can bring either one back. After **any** restore of `/var/lib/zcrypto-engine`, and **before the engine starts**: `sudo ls -la /var/lib/zcrypto-engine/exec/` — expect neither `armed` nor `probe-plan.json` to be present; delete whatever you find, then start the engine. The plan's own 60-minute expiry and the ledger's plan-id dedup are the designed backstops behind this check, not a substitute for running it.

#### 6. Verify by outcome — the window is not closed until every line here reads true

1. **Every intent has a terminal outcome and every order has a terminal state**, from the ledger read: each plan entry `accepted` with empty reasons, each intent carrying an outcome, each order row a terminal `state`.
2. **Every fill carries its fee and its liquidity side**: each `fill` line shows `fee` with a `fee_currency`, and `liquidity` reading the word `maker` or `taker` — never a number.
3. **Two rollover rows per position** in the Kraken ledger export.
4. **The settle and then the disposal are visible in venue truth, read from the venue record written after the disarm converge's restart** — that restart is what forces the fresh account read, and it is the verified path. Take the restart time from `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine`, wait for the next 4-hourly boundary to write its record, then run the venue-truth read and confirm `snapshot_at` is later than that restart time. A record written before the restart is corroboration, never the gate.
5. **The probe ends flat**: that record's `positions` is empty and its `balances` are EUR only, with any BTC remainder below the leg's `ordermin` (terminal dust, not a position).
6. **The execution families are live in Grafana Cloud, read by value** from the workstation — a number in every case, never `(no series)`:
   ```
   uv run python infra/scripts/grafana-query.py \
     'zcrypto_exec_orders_total{host="zcrypto"}' \
     'zcrypto_exec_fills_total{host="zcrypto"}' \
     'zcrypto_exec_fees_eur_total{host="zcrypto"}' \
     'zcrypto_exec_position{host="zcrypto"}' \
     'zcrypto_exec_realized_pnl_eur{host="zcrypto"}'
   ```
7. **The verdict is recorded** in `docs/research/14.phase6-decisions.md`, and on a fail its fallback topic is registered and queued — step 7 above.

### Retire when

`cli/engine/executor.py` no longer picks a plan file up out of the state directory's `exec/` — check with `grep -n PLAN_FILENAME cli/engine/executor.py`, and a run that finds nothing is the signal. At that point the continuous loop that replaces attended probe windows has landed, and this procedure with it.
