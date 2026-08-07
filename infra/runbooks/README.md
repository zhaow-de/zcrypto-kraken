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
6. **Silence this rule once triaged, time-boxed.** It is a counter-presence check, so it stays firing for the daemon's whole lifetime — the counter only resets when the capture daemon restarts, which is days-to-weeks away and gated on a bake. Silence in Grafana on the rule uid for a bounded window; delete the silence early if the daemons restart sooner; do not delete the rule.

### Retire when

`zcrypto-capture-venue-not-online` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed. (The pre-drain decision landed 2026-08-06 and this procedure was rewritten then, per this clause's own instruction; the alert stays.)

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
