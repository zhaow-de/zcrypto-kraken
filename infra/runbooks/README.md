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

A warning-severity Grafana alert. Kraken's WebSocket `status` channel reported a `system` value other than `online` on at least one capture host.

### What it means

The capture daemon counts every `status` frame it receives, labelled by the `system` value, into `zcrypto_capture_venue_status_total`. Until this fired, every observed value fleet-wide was `online`. Kraken pushes `status` on every connect, so the counter advances routinely — **only the non-`online` label is unusual.**

The frame also carries `effectiveTime`, logged but not counted: on a *planned* maintenance notice that field is the lead time, and it is the single number deciding whether a pre-drain is worth building. The log line is `venue status system=… version=… effective_time=…`.

This does **not** by itself mean data is being lost. A venue in `maintenance` or `cancel_only` may still stream book updates, and the capture path is unaffected by order-entry state. Loss shows up on the reconciler's counters, not here.

### What to do

1. **Read the value and the lead time.** In Loki, `{host=~"zcrypto|zcrypto-red", container="capture"} |= "venue status"` — take `system` and `effective_time`. A non-null `effective_time` means Kraken announced it in advance.
2. **Check whether capture actually degraded**, rather than assuming: `zcrypto_capture_seconds_since_last_book_message` per pair, and the reconciler's `zcrypto_reconcile_residual_gap_seconds_total`. A venue state change with no book staleness and no residual growth is an observability event, not a data event.
3. **Do not converge or restart anything on this signal alone.** Nothing in the capture path reacts to venue status; a restart costs a resubscribe and buys nothing.
4. **Record the observation** — value, `effective_time`, whether book flow degraded, and for how long. This is the first real sample of a payload shape the fleet had never seen, and it is what \[[T0105]\]'s parked decision (whether a pre-drain is worth building) has been waiting for. Add it to that topic.
5. **Silence it once recorded, time-boxed.** This rule is a counter-presence check, so it stays firing for the daemon's whole lifetime — the counter only resets when the capture daemon restarts, which is days-to-weeks away and gated on a bake. Nothing else clears it, and step 3 rules out restarting for this alone. Silence in Grafana for a bounded window after step 4 is done; do not delete the rule.

### Retire when

`zcrypto-capture-venue-not-online` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed. If \[[T0105]\]'s pre-drain decision lands and changes the response, rewrite *What to do*; the alert itself stays.

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

Both ends of the tunnel run a probe timer that writes `zaccess_wireguard_handshake_age_seconds` from `wg show zaccess0 latest-handshakes` — the bridgehead's copy under `host="zaccess"`, the ops node's under `host="ops"`. The rule takes `max()` across both, so either side reporting stale trips it — a healthy tunnel handshakes every couple of minutes given `PersistentKeepalive = 25` on the ops-side client conf, so 300s is already several missed keepalives, not noise. This does not mean the whole bridgehead is unreachable: that is `zaccess-bridgehead-dark`'s job (this host's Alloy itself going dark) and `zcrypto-alloy-dark-ops`'s job (the ops node's).

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

A warning-severity Grafana alert (`zaccess-cert-expiring`): the soonest-expiring TLS certificate among the tracked zaccess endpoints has been under 14 days from expiry for at least an hour.

### What it means

Two probe timers write `zaccess_tls_not_after_seconds{target=...}`: the bridgehead's own probe handshakes against each Caddy vhost on `127.0.0.1:443` and writes `target="tmux"`/`target="nas"`; the ops node's probe handshakes against the NAS admin port and writes `target="nas-dsm"`. The rule takes `min()` across every target's series, so whichever certificate is closest to expiry trips it first — it does not say which one without a follow-up query. `tmux` and `nas` are Caddy-managed: Caddy's ACME client renews them automatically, well before 14 days out under normal operation, so either arriving at this threshold usually means renewal has been failing silently rather than an unavoidable expiry. `nas-dsm` is the Synology DSM's own certificate, outside Caddy's control — its renewal (or lack of it) is a DSM-side concern.

### What to do

1. Identify which target tripped it: `uv run python infra/scripts/grafana-query.py 'zaccess_tls_not_after_seconds'` — one value per `target` label; `date -d @<value>` turns it into a calendar date.
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
