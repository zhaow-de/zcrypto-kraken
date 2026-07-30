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
