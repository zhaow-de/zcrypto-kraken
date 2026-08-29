# Runbooks — what to do when something demands action

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. This page is the index: find the alert `uid`, or the anchor in the comment that sent you, in the list below and follow it into that subsystem's file. Each section there is written to be actioned without opening any other document.

## Scope — what belongs here, and what does not

- **Procedures** for a signal that fires at an operator, and **accepted limitations** an operator may run into while debugging. Nothing else.
- **This is not a backlog.** If acting on a section produces work, put it where work lives: something needing a *decision* opens a `T<NNNN>` per `.claude/rules/open-topics.md`; something needing *doing* goes in the memo queue. Deferrals must not accumulate here — a runbook nobody can finish reading is a runbook nobody reads.
- Every section carries a **Retire when** naming something checkable — a metric that stops existing, a rule absent from `infra/grafana/alerts.yaml`, a line no longer in the code. A retirement condition you have to *judge* is one nobody will act on.

**This file holds no procedures — the index and this scope, nothing else.** A new section joins the subsystem file that already covers its signal, or mints a new `infra/runbooks/<subsystem>.md` and a row below. An index that also holds a few leftover sections has no rule against gaining one more, and that is how a single file reached nineteen of them.

**Split a subsystem file when** it exceeds ~12 sections, or gains a second subsystem's worth of material. Keep the explicit `<a name=…>` anchors byte-identical through any move, and update every citation in the same change: alert summaries, dashboard panel descriptions and code comments cite a section by **file and anchor**, so a section that moves without them leaves a paged responder holding a fragment and no next step. `tests/test_infra_alert_rules.py` fails on an alert summary whose named file does not define the anchor, and on any anchor defined in two files at once. The anchors are explicit rather than heading-derived precisely because the `— ALERT` / `— KNOWN LIMITATION` marker would otherwise become part of the slug.

## Index

### [`capture.md`](capture.md) — the venue feed and the archive's hour boundaries

- [`zcrypto-capture-venue-not-online`](capture.md#zcrypto-capture-venue-not-online) — ALERT: Kraken reported a `system` state other than `online` at some point since the capture daemon started.
- [`zcrypto-capture-venue-state-recurrence`](capture.md#zcrypto-capture-venue-state-recurrence) — ALERT: the same, but inside the last 15 minutes — the one that means it is happening now.
- [`zcrypto-capture-all-streams-silent`](capture.md#zcrypto-capture-all-streams-silent) — ALERT: every book stream on one host went quiet at once. Check the venue's published maintenance calendar first — every firing so far has been one.
- [`zcrypto-capture-stream-silent`](capture.md#zcrypto-capture-stream-silent) — ALERT: one book stream stopped delivering while its siblings kept flowing; the daemon does not self-heal this.
- [`cross-hour-straddle`](capture.md#cross-hour-straddle) — KNOWN LIMITATION: silence that began before an hour boundary is measured from the boundary, not from its true start.
- [`bogus-timestamp-hour-rotation`](capture.md#bogus-timestamp-hour-rotation) — KNOWN LIMITATION: the three accepted ways a bogus exchange timestamp can still close an archive hour early or open a past one — which knob would close each, what it would starve, and how to name which one fired. The truncation is permanent by design; start here before acting on any of the three alerts below.
- [`zcrypto-capture-hour-finalized-early`](capture.md#zcrypto-capture-hour-finalized-early) — ALERT: an archive hour was closed before the clock said it was over. A bogus timestamp and a lagging clock look identical here — read the clock-skew signal beside it.
- [`zcrypto-capture-ts-past-dated-hour`](capture.md#zcrypto-capture-ts-past-dated-hour) — ALERT: a stream's first event after a process start was dated into an hour already gone, fabricating a complete-looking final for a period nothing was captured. Hard-zero baseline.
- [`zcrypto-capture-clock-exporter-stale`](capture.md#zcrypto-capture-clock-exporter-stale) — ALERT: the host clock reading has stopped refreshing, so the offset gauges are frozen and look healthy. The clock-skew alert is blind while this fires.
- [`zcrypto-capture-clock-skew`](capture.md#zcrypto-capture-clock-skew) — ALERT: a capture machine's clock is over 10 s out or unsynchronised. Nothing is lost yet — it is the only detector for the archive fault a clock running ahead causes.
- [`zcrypto-capture-rows-quarantined`](capture.md#zcrypto-capture-rows-quarantined) — ALERT: rows were spilled to a `.held` sidecar because their hour was never corroborated. Not the late-arrival path; nothing is lost.
- [`capture-silence-rules-and-datasource-errors`](capture.md#capture-silence-rules-and-datasource-errors) — KNOWN LIMITATION: the two silence rules stay silent on a Grafana query failure rather than raising a blackout page the system never observed.

### [`fleet.md`](fleet.md) — every long-lived daemon's memory and restarts

- [`zcrypto-fleet-memory-headroom`](fleet.md#zcrypto-fleet-memory-headroom) — ALERT: a daemon is above 70 % of its container memory limit — the slow-leak alarm, watched as a routine and never as a rollout read.
- [`zcrypto-fleet-alloy-memory-headroom`](fleet.md#zcrypto-fleet-alloy-memory-headroom) — ALERT: Alloy is above 90 % of its container limit (1 GiB on ops, 512 MiB elsewhere) — it runs nearer its ceiling than the app daemons by design, so it has its own bar.
- [`zcrypto-fleet-memory-leak`](fleet.md#zcrypto-fleet-memory-leak) — ALERT: a daemon's hourly memory floor rose 64 MiB over a day — the early notice, a week ahead of the limit page.
- [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) — ALERT: a daemon restarted — a converge's or Alloy bump's own record when one just ran, the only OOM-kill/crash signal otherwise.

### [`zaccess.md`](zaccess.md) — the internet access host

- [`zaccess-bridgehead-dark`](zaccess.md#zaccess-bridgehead-dark) — ALERT: the bridgehead's Alloy stopped shipping, and every rule scoped to that host went blind with it.
- [`zaccess-disk-high`](zaccess.md#zaccess-disk-high) — ALERT: the bridgehead's root filesystem is under 15% free.
- [`zaccess-tunnel-stale`](zaccess.md#zaccess-tunnel-stale) — ALERT: the WireGuard tunnel's handshake age is over 300 s at one end or both.
- [`zaccess-cert-expiring`](zaccess.md#zaccess-cert-expiring) — ALERT: a tracked TLS certificate is under 14 days from expiry.

### [`ops.md`](ops.md) — the nightly archive sweep and the tape-bars dataset

- [`zcrypto-ops-verify-replay-new-breakage`](ops.md#zcrypto-ops-verify-replay-new-breakage) and [`zcrypto-ops-verify-replay-run-broken`](ops.md#zcrypto-ops-verify-replay-run-broken) — ALERT, one section serving both uids: an archive hour newly failed replay, or the sweep did not run to completion.
- [`zcrypto-ops-verify-replay-backlog-stuck`](ops.md#zcrypto-ops-verify-replay-backlog-stuck) — ALERT: the re-verification queue has not shrunk across two consecutive nightly runs.
- [`zcrypto-ops-tapebars-permanent-gap`](ops.md#zcrypto-ops-tapebars-permanent-gap) — ALERT: a settled day was never published and has now fallen outside the re-scan window.
- [`zcrypto-ops-tapebars-not-advancing`](ops.md#zcrypto-ops-tapebars-not-advancing) — ALERT: no new day has been published for more than 48 hours.
- [`zcrypto-reconcile-residual-gap`](ops.md#zcrypto-reconcile-residual-gap) — ALERT: permanent, unrecoverable L2 loss booked to the reconcile ledger — the highest-severity rule in the system.
- [`zcrypto-reconcile-healable-gap-rate`](ops.md#zcrypto-reconcile-healable-gap-rate) — ALERT: the primary needed heavy covering by the secondary. Nothing was lost; a host needing this much repair is degrading. Its threshold is per-pair, not a total — read it wrong and you mis-triage.
- [`healable-threshold-rederivation-due`](ops.md#healable-threshold-rederivation-due) — SCHEDULED REMINDER: the healable-gap-rate threshold is provisional and its fit is still owed. Nothing is wrong. Count qualifying days from the ops ledger, never from Grafana Cloud.
- [`zcrypto-reconcile-cycle-duration`](ops.md#zcrypto-reconcile-cycle-duration) — ALERT: the overlay-writer cycle is approaching the interval between its own ticks, past which the next trigger is dropped and the booking cadence halves.
- [`reconcile-ledger-scan-cost`](ops.md#reconcile-ledger-scan-cost) — ALERT: the append-only reconcile ledger has grown into the cost driver of every cycle; warning at 10 s says re-measure, critical at 30 s says the constraint is memory rather than time and the cadence alert structurally cannot see it.
- [`zcrypto-reconcile-exporter-stale`](ops.md#zcrypto-reconcile-exporter-stale) — ALERT: A **critical** Grafana alert (`Reconciler · exporter stale`): `time() - zcrypto_reconcile_last_success_timestamp_seconds` has read above 10800 s (3 h) for 5 minutes, or the series is gone entirely —…
- [`zcrypto-reconcile-source-lag`](ops.md#zcrypto-reconcile-source-lag) — ALERT: A **warning** Grafana alert (`Reconciler · capture mirror lagging`): `max by (source) (zcrypto_reconcile_source_lag_seconds)` above 10800 s (3 h) for 10 minutes.

### [`engine.md`](engine.md) — the trading engine and its order path

- [`zcrypto-engine-sleeve-count-changed`](engine.md#zcrypto-engine-sleeve-count-changed) — ALERT: the number of sleeves carrying exposure stepped, so the book's gross moved roughly in proportion.
- [`zcrypto-engine-exec-armed-too-long`](engine.md#zcrypto-engine-exec-armed-too-long) — ALERT: order submission has been armed for six unbroken hours.
- [`zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) — ALERT: the execution kill switch is engaged, so nothing may be submitted.
- [`zcrypto-engine-exec-not-evaluated`](engine.md#zcrypto-engine-exec-not-evaluated) — ALERT: the execution safety gate has stopped being evaluated, so every gauge describing it is frozen.
- [`zcrypto-venue-concordance-failed`](engine.md#zcrypto-venue-concordance-failed) — ALERT: a ratified instrument is missing from the venue's set, or its constraints came back absent or unparseable.
- [`zcrypto-venue-snapshot-stale`](engine.md#zcrypto-venue-snapshot-stale) — ALERT: no successful venue-truth snapshot has landed in over five hours.
- [`engine-data-socket-idle`](engine.md#engine-data-socket-idle) — KNOWN LIMITATION: the engine's data socket is idle by design while disarmed; what its reconnect lines mean, why they exist only in `docker logs`, and how to stop the engine during a Kraken outage so its retries cannot cost the capture primary its reconnect budget.
- [`zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) — ALERT: A **critical** Grafana alert (`Engine · cycles have stopped`): `time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}` above 16500 s (4h35m) for 5 minutes, **or the series is gone entirely** —…
- [`zcrypto-engine-cycle-failed`](engine.md#zcrypto-engine-cycle-failed) — ALERT: A **warning** Grafana alert (`Engine · the last cycle failed`): `zcrypto_engine_cycle_success{host="zcrypto"}` reads 0, with `for: 0s` — the outcome is already final the instant the gauge reads 0, so there…
- [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) — ALERT: A **warning** Grafana alert (`Engine · ERROR logs`) on the `logs` receiver: at least one ERROR or CRITICAL line from the engine on the capture primary in the last 15 minutes.
- [`zcrypto-engine-log-dead`](engine.md#zcrypto-engine-log-dead) — ALERT: A **critical** Grafana alert (`Engine · log pipeline dead`) on the `logs` receiver: Loki holds **not one line of any level** from `{host="zcrypto", container="engine"}` in the last 6 hours.

### [`engine-procedures.md`](engine-procedures.md) — the engine's attended procedures

- [`engine-probe-window`](engine-procedures.md#engine-probe-window) — PROCEDURE: the attended live-order probe window, and the only sanctioned way to run one. Nothing fires this; you open it deliberately, and real money moves.
- [`engine-tracking-band`](engine-procedures.md#engine-tracking-band) — PROCEDURE: the weekly tracking-error trip — what its verdict tile is saying, and what has to be true before a band is set. Nothing fires this; a breach pages through the kill-switch alert above.

### [`order-semantics-verification.md`](order-semantics-verification.md) — the adapter's order semantics on a new nautilus version

- [`order-semantics-verification`](order-semantics-verification.md#order-semantics-verification) — PROCEDURE: the attended ~EUR 0.20 six-probe pass a nautilus bump owes before the engine may be armed on it. Nothing fires this; you run it deliberately, and real money moves.

### [`reference-data.md`](reference-data.md) — facts a third party owns

- [`refdata-sweep-due`](reference-data.md#refdata-sweep-due) — SCHEDULED REMINDER: the Kraken reference-data re-confirmation sweep is due. Nothing is wrong.

### [`capture-daemon.md`](capture-daemon.md) — the capture daemon's own guards

- [`zcrypto-capture-book-desync-stuck`](capture-daemon.md#zcrypto-capture-book-desync-stuck) — ALERT: A **warning** Grafana alert, `Capture · book desync stuck on a pair`, one instance per `(host, pair)` — the `pair` label names the stuck pair.
- [`zcrypto-capture-resubscribe-rate`](capture-daemon.md#zcrypto-capture-resubscribe-rate) — ALERT: One of two **warning** Grafana alerts, both 24-hour `increase()` reads held `for: 30m`, both on the integrity board's "Recovery ladder — 24h increase" panel: - **`zcrypto-capture-resubscribe-rate`** —…
- [`zcrypto-capture-resubscribe-failing`](capture-daemon.md#zcrypto-capture-resubscribe-failing) — ALERT: One of two **warning** Grafana alerts, both 24-hour `increase()` reads held `for: 30m`, both on the integrity board's "Recovery ladder — 24h increase" panel: - **`zcrypto-capture-resubscribe-rate`** —…
- [`zcrypto-capture-watermark-breached`](capture-daemon.md#zcrypto-capture-watermark-breached) — ALERT: A **critical** Grafana alert, `Capture · disk watermark breached -- DISCARDING data`, one instance per host: `max by (host) (zcrypto_capture_disk_watermark_breached{host=~"zcrypto|zcrypto-red"}) > 0.5`,…
- [`zcrypto-capture-error-logs`](capture-daemon.md#zcrypto-capture-error-logs) — ALERT: A **warning** Grafana alert, `Capture · daemon ERROR logs`: one or more ERROR/CRITICAL lines from the capture daemon (`container="capture"`) on a capture host in the last 15 minutes.

### [`hosts.md`](hosts.md) — disk, load, reboots and the textfile transport

- [`zcrypto-capture-disk-low`](hosts.md#zcrypto-capture-disk-low) — ALERT: A warning-severity Grafana alert (*Capture · spool disk low*), one instance per capture host: the **root** filesystem is below 10 % free and has been for 5 minutes.
- [`zcrypto-capture-load-high`](hosts.md#zcrypto-capture-load-high) — ALERT: A warning-severity Grafana alert (*Capture · node load high*), one instance per capture host: the 1-minute load average **per core** has been above 1.5 for 10 minutes.
- [`zcrypto-capture-reboot-pending`](hosts.md#zcrypto-capture-reboot-pending) — ALERT: A warning-severity Grafana alert (*Capture · reboot pending (attended)*), one instance per capture host: `/run/reboot-required` has existed for 15 minutes.
- [`zcrypto-capture-textfile-missing`](hosts.md#zcrypto-capture-textfile-missing) and [`zcrypto-capture-textfile-unreadable`](hosts.md#zcrypto-capture-textfile-unreadable) and [`zcrypto-reboot-probe-stale`](hosts.md#zcrypto-reboot-probe-stale) and [`zcrypto-oneoff-textfile-stale`](hosts.md#zcrypto-oneoff-textfile-stale) — ALERT: Four warning-severity rules over **one transport**.

### [`observability.md`](observability.md) — the telemetry planes themselves

- [`zcrypto-alloy-dark-nas`](observability.md#zcrypto-alloy-dark-nas) and [`zcrypto-alloy-dark-ops`](observability.md#zcrypto-alloy-dark-ops) and [`zcrypto-alloy-dark-capture-primary`](observability.md#zcrypto-alloy-dark-capture-primary) and [`zcrypto-alloy-dark-capture-secondary`](observability.md#zcrypto-alloy-dark-capture-secondary) — ALERT: A **critical** Grafana alert, one of four — `Fleet · Alloy dark — NAS` / `— Ops` / `— Capture primary` / `— Capture secondary`.
- [`zcrypto-node-collector-failed`](observability.md#zcrypto-node-collector-failed) — ALERT: A **warning** Grafana alert (`Node · a node-exporter collector is failing`): `min by (host) (node_scrape_collector_success) < 0.5` for 15 minutes.
- [`zcrypto-logship-lines-dropped`](observability.md#zcrypto-logship-lines-dropped) and [`zcrypto-logship-worker-stalled`](observability.md#zcrypto-logship-worker-stalled) — ALERT: One of two **warning** Grafana alerts on the direct-ship log path, and **which one fired tells you which fault it is**: - **`Logs · lines dropped before reaching Loki`** (uid…
- [`zcrypto-capture-log-dead-primary`](observability.md#zcrypto-capture-log-dead-primary) and [`zcrypto-capture-log-dead-secondary`](observability.md#zcrypto-capture-log-dead-secondary) — ALERT: A **critical** Grafana alert, one rule per capture host — `Capture · log pipeline dead — Capture primary` (uid `zcrypto-capture-log-dead-primary`, host `zcrypto`) or `— Capture secondary` (uid…
- [`zcrypto-ops-log-pipeline-dead`](observability.md#zcrypto-ops-log-pipeline-dead) and [`zcrypto-ops-poller-log-dead`](observability.md#zcrypto-ops-poller-log-dead) and [`zcrypto-ops-unit-parse-dead`](observability.md#zcrypto-ops-unit-parse-dead) and [`zcrypto-ops-journal-transport-dead`](observability.md#zcrypto-ops-journal-transport-dead) — ALERT: One of four **critical** Grafana alerts on the ops node's log plane.
- [`zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) — ALERT: A **critical** Grafana alert, `Fleet · healthchecks.io watchdog (check down, or hc.io dark)`: `max(hc_checks_down_total) or on() vector(999)` above 0, held 5 minutes.

### [`ops-node.md`](ops-node.md) — the ops node's timers and units

- [`zcrypto-ops-archive-pull-stalled`](ops-node.md#zcrypto-ops-archive-pull-stalled) and [`zcrypto-ops-archive-pull-exit-nonzero`](ops-node.md#zcrypto-ops-archive-pull-exit-nonzero) — ALERT: Two Grafana alerts on the same unit, `zcrypto-archive-pull.service` — despite the name it pulls nothing; it is the **overlay-writer cycle** (reconcile + the daily trade backfill), and the unit and metric…
- [`zcrypto-trade-backfill-stale`](ops-node.md#zcrypto-trade-backfill-stale) and [`zcrypto-trade-backfill-exit-nonzero`](ops-node.md#zcrypto-trade-backfill-exit-nonzero) — ALERT: Two **critical** Grafana alerts on the daily trade-tape healing step, which runs as the second half of the same `zcrypto-archive-pull.service` cycle.
- [`zcrypto-ops-verified-replay-stale`](ops-node.md#zcrypto-ops-verified-replay-stale) and [`zcrypto-ops-verified-replay-exit-nonzero`](ops-node.md#zcrypto-ops-verified-replay-exit-nonzero) — ALERT: Two Grafana alerts on `zcrypto-verified-replay.service`, the daily verified-path replay of the engine journal.
- [`zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) — ALERT: A **warning** Grafana alert (`Ops · panel non-zero exit`): `ops_panel_exit_code > 0`, `for: 5m`, `noDataState: OK`.
- [`zcrypto-ops-load-high`](ops-node.md#zcrypto-ops-load-high) — ALERT: A **warning** Grafana alert (`Ops · node load high`): `node_load1{host="ops"} > 20`, `for: 5m`, `noDataState: OK`, charted on the `Fleet health` board.
- [`zcrypto-ops-error-logs`](ops-node.md#zcrypto-ops-error-logs) — ALERT: A **warning** Grafana alert (`Ops · ERROR logs`) on the `logs` receiver, `for: 0s`, `noDataState: OK`.

### [`nas.md`](nas.md) — the durable archive and its pull loop

- [`zcrypto-nas-disk-low`](nas.md#zcrypto-nas-disk-low) — ALERT: A warning Grafana alert (`NAS · /volume1 free space low`, panel `zcrypto-fleet`/301): `node_filesystem_avail_bytes{mountpoint="/volume1"} / node_filesystem_size_bytes{mountpoint="/volume1"}` has been below…
- [`zcrypto-nas-load-high`](nas.md#zcrypto-nas-load-high) — ALERT: A warning Grafana alert (`NAS · load high`, panel `zcrypto-fleet`/201): `node_load1{host="nas"}` has been above `4` for 5 minutes — the box is a 4-core Atom, so the threshold is one runnable process per core.
- [`zcrypto-nas-archive-pull-errors`](nas.md#zcrypto-nas-archive-pull-errors) — ALERT: A warning Grafana alert on the **logs** receiver (`NAS · archive-pull ERROR logs`, panel `zcrypto-logs`/102): at least one line labelled `level="ERROR"` or `"CRITICAL"` from `{container="archive-pull"}` in…
- [`zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled) — ALERT: A critical Grafana alert on the **logs** receiver (`NAS · archive-pull stalled (dead-man)`, panel `zcrypto-logs`/103): Loki holds no line matching `pull complete` **and** `failed=0` from…

### [`gate.md`](gate.md) — the shadow-concordance export on the NAS

- [`zcrypto-gate-streak-reset`](gate.md#zcrypto-gate-streak-reset) — ALERT: A **warning** Grafana alert, `Gate · streak reset`: `delta(zcrypto_gate_streak_days[6h])` went negative, i.e.
- [`zcrypto-gate-mismatch`](gate.md#zcrypto-gate-mismatch) — ALERT: A **critical** Grafana alert, `Gate · mismatch in the last day`: `increase(zcrypto_gate_mismatch_total[1d]) > 0`.
- [`zcrypto-gate-pull-lag`](gate.md#zcrypto-gate-pull-lag) — ALERT: A **critical** Grafana alert, `Gate · journal pull lag high`: `zcrypto_gate_journal_pull_lag_seconds > 21600` (6 h).
- [`zcrypto-gate-exporter-stale`](gate.md#zcrypto-gate-exporter-stale) — ALERT: A **critical** Grafana alert, `Gate · exporter stale`: `time() - zcrypto_gate_export_timestamp_seconds > 7200` (2 h).
- [`zcrypto-gate-cache-reverify-stalled`](gate.md#zcrypto-gate-cache-reverify-stalled) — ALERT: A **critical** Grafana alert, `Gate · cache re-verification stalled`: `zcrypto_gate_cache_oldest_verification_age_seconds > 259200` (3 days), held for 15 m.
