# Runbooks — what to do when something demands action

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. This page is the index: find the alert `uid`, or the anchor in the comment that sent you, in the list below and follow it into that subsystem's file.

## Scope — what belongs here, and what does not

- **Procedures** for a signal that fires at an operator, and **accepted limitations** an operator may run into while debugging. Nothing else.
- **This is not a backlog.** If acting on a section produces work, put it where work lives: something needing a *decision* opens a `T<NNNN>` per `.claude/rules/open-topics.md`; something needing *doing* goes in the memo queue. Deferrals must not accumulate here — a runbook nobody can finish reading is a runbook nobody reads.
- **Four parts, in this order**: *What you are seeing* · *What it means* · *What to do* · *Retire when* — for ALERT, KNOWN LIMITATION and SCHEDULED REMINDER sections. A PROCEDURE carries those four or, for a drill, the seven spec `00105` names. Same order every time, so a cold reader can skim.
- **Four kinds, marked in the heading**: `— ALERT` (something fires), `— KNOWN LIMITATION` (something an operator meets while debugging, where the right action may be "nothing"), `— PROCEDURE` (nothing fires it; you open it deliberately), `— SCHEDULED REMINDER` (a reminder came due; nothing is wrong).
- **A step names the sanctioned program that executes it.** A step with no such program is a credential-handling improvisation waiting for an operator — write the program's invocation, or do not write the step.
- **A drill's output is a runbook section, never a report.**
- Every section carries a **Retire when** naming something checkable — a metric that stops existing, a rule absent from `infra/grafana/alerts.yaml`, a line no longer in the code. A retirement condition you have to *judge* is one nobody will act on.

**This file holds no procedures — the index and this scope, nothing else.** A new section joins the subsystem file that already covers its signal, or mints a new `infra/runbooks/<subsystem>.md`; either way it gets a row below. An index that also holds a few leftover sections has no rule against gaining one more.

**Split a subsystem file when** it exceeds ~12 sections, or gains a second subsystem's worth of material. Keep the explicit `<a name=…>` anchors byte-identical through any move, and update every citation in the same change: alert summaries, dashboard panel descriptions and code comments cite a section by **file and anchor**, so a section that moves without them leaves a paged responder holding a fragment and no next step. `tests/test_infra_alert_rules.py` is what fails when a citation and its anchor fall out of step. The anchors are explicit rather than heading-derived precisely because the `— ALERT` / `— KNOWN LIMITATION` marker would otherwise become part of the slug.

## Index

### [`capture.md`](capture.md) — the venue feed and the archive's hour boundaries

- [`zcrypto-capture-venue-not-online`](capture.md#zcrypto-capture-venue-not-online) — ALERT: Kraken reported a `system` state other than `online` at some point since the capture daemon started.
- [`zcrypto-capture-venue-state-recurrence`](capture.md#zcrypto-capture-venue-state-recurrence) — ALERT: the same, but inside the last 15 minutes — the one that means it is happening now.
- [`zcrypto-capture-all-streams-silent`](capture.md#zcrypto-capture-all-streams-silent) — ALERT: every book stream on one host went quiet at once.
- [`zcrypto-capture-stream-silent`](capture.md#zcrypto-capture-stream-silent) — ALERT: one book stream stopped delivering while its siblings kept flowing.
- [`cross-hour-straddle`](capture.md#cross-hour-straddle) — KNOWN LIMITATION: silence that began before an hour boundary is measured from the boundary, not from its true start.
- [`bogus-timestamp-hour-rotation`](capture.md#bogus-timestamp-hour-rotation) — KNOWN LIMITATION: the three accepted ways a bogus exchange timestamp can still close an archive hour early or open a past one — start here before acting on `zcrypto-capture-hour-finalized-early`, `zcrypto-capture-ts-past-dated-hour` or `zcrypto-capture-clock-skew`.
- [`zcrypto-capture-hour-finalized-early`](capture.md#zcrypto-capture-hour-finalized-early) — ALERT: an archive hour was closed before the clock said it was over.
- [`zcrypto-capture-ts-past-dated-hour`](capture.md#zcrypto-capture-ts-past-dated-hour) — ALERT: a stream's first event after a process start was dated into an hour already gone **that held no captured parts on disk**, which can publish a complete-looking final for a period nothing was captured.
- [`zcrypto-capture-clock-exporter-stale`](capture.md#zcrypto-capture-clock-exporter-stale) — ALERT: the host clock reading has stopped refreshing, so the offset gauges are frozen and look healthy.
- [`zcrypto-capture-clock-skew`](capture.md#zcrypto-capture-clock-skew) — ALERT: a capture machine's clock is over 10 s out or unsynchronised.
- [`zcrypto-capture-rows-quarantined`](capture.md#zcrypto-capture-rows-quarantined) — ALERT: rows were spilled to a `.held` sidecar because their hour was never corroborated.
- [`capture-silence-rules-and-datasource-errors`](capture.md#capture-silence-rules-and-datasource-errors) — KNOWN LIMITATION: the two silence rules stay silent on a Grafana query failure rather than raising a blackout page the system never observed.

### [`fleet.md`](fleet.md) — every long-lived daemon's memory and restarts

- [`zcrypto-fleet-memory-headroom`](fleet.md#zcrypto-fleet-memory-headroom) — ALERT: a daemon is above 70 % of its container memory limit — the slow-leak alarm.
- [`zcrypto-fleet-alloy-memory-headroom`](fleet.md#zcrypto-fleet-alloy-memory-headroom) — ALERT: Alloy is above 90 % of its container limit.
- [`zcrypto-fleet-memory-leak`](fleet.md#zcrypto-fleet-memory-leak) — ALERT: a daemon's hourly memory floor rose 64 MiB over a day.
- [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) — ALERT: a daemon restarted.

### [`zaccess.md`](zaccess.md) — the internet access host

- [`zaccess-converge`](zaccess.md#zaccess-converge) — PROCEDURE: converging the bridgehead needs an agent holding only its own key, and the command that builds one.
- [`zaccess-revoke-client-cert`](zaccess.md#zaccess-revoke-client-cert) — PROCEDURE: dropping a client cert's pin, and the host copy the converge does not delete.
- [`zaccess-alloy-converge`](zaccess.md#zaccess-alloy-converge) — PROCEDURE: the bridgehead's Alloy is the fleet's one native-deb Alloy — no digest operand, no bake, an ungated config copy.
- [`zaccess-bridgehead-dark`](zaccess.md#zaccess-bridgehead-dark) — ALERT: the bridgehead's Alloy stopped shipping.
- [`zaccess-disk-high`](zaccess.md#zaccess-disk-high) — ALERT: the bridgehead's root filesystem is under 15% free.
- [`zaccess-tunnel-stale`](zaccess.md#zaccess-tunnel-stale) — ALERT: the WireGuard tunnel's handshake age is over 300 s at one end or both.
- [`zaccess-cert-expiring`](zaccess.md#zaccess-cert-expiring) — ALERT: a tracked TLS certificate is under 14 days from expiry.

### [`ops.md`](ops.md) — the nightly archive sweep and the tape-bars dataset

- [`zcrypto-ops-verify-replay-new-breakage`](ops.md#zcrypto-ops-verify-replay-new-breakage) and [`zcrypto-ops-verify-replay-run-broken`](ops.md#zcrypto-ops-verify-replay-run-broken) — ALERT, one section serving both uids: an archive hour newly failed replay, or the sweep did not run to completion.
- [`zcrypto-ops-verify-replay-backlog-stuck`](ops.md#zcrypto-ops-verify-replay-backlog-stuck) — ALERT: the re-verification queue has not shrunk across two consecutive nightly runs.
- [`zcrypto-ops-verify-replay-stale`](ops.md#zcrypto-ops-verify-replay-stale) — ALERT: the nightly canonical-archive sweep has not run for over 48 hours.
- [`zcrypto-ops-tapebars-permanent-gap`](ops.md#zcrypto-ops-tapebars-permanent-gap) — ALERT: a settled day was never published and has now fallen outside the re-scan window.
- [`zcrypto-ops-tapebars-not-advancing`](ops.md#zcrypto-ops-tapebars-not-advancing) — ALERT: no new day has been published for more than 48 hours.
- [`zcrypto-reconcile-residual-gap`](ops.md#zcrypto-reconcile-residual-gap) — ALERT: permanent, unrecoverable L2 loss booked to the reconcile ledger — the highest-severity rule in the system.
- [`zcrypto-reconcile-healable-gap-rate`](ops.md#zcrypto-reconcile-healable-gap-rate) — ALERT: the primary needed heavy covering by the secondary. The counter is the silence the secondary could cover, not what a splice filled — whether anything was lost is the ledger's `residual_seconds`.
- [`healable-threshold-rederivation-due`](ops.md#healable-threshold-rederivation-due) — SCHEDULED REMINDER: the healable-gap-rate threshold is provisional and its fit is still owed.
- [`zcrypto-reconcile-cycle-duration`](ops.md#zcrypto-reconcile-cycle-duration) — ALERT: the overlay-writer cycle is approaching the interval between its own ticks.
- [`reconcile-ledger-scan-cost`](ops.md#reconcile-ledger-scan-cost) — ALERT: the append-only reconcile ledger has grown into the cost driver of every cycle.
- [`zcrypto-reconcile-exporter-stale`](ops.md#zcrypto-reconcile-exporter-stale) — ALERT: no reconciler run has succeeded in over 3 h, or its series is gone entirely.
- [`zcrypto-reconcile-source-lag`](ops.md#zcrypto-reconcile-source-lag) — ALERT: one capture mirror is over 3 h behind.

### [`engine.md`](engine.md) — the trading engine and its order path

- [`zcrypto-engine-sleeve-count-changed`](engine.md#zcrypto-engine-sleeve-count-changed) — ALERT: the number of sleeves carrying exposure stepped up or down. Nothing is broken.
- [`zcrypto-engine-exec-armed-too-long`](engine.md#zcrypto-engine-exec-armed-too-long) — ALERT: order submission has been armed for six unbroken hours.
- [`zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) — ALERT: the execution kill switch is engaged, so nothing may be submitted.
- [`zcrypto-engine-exec-not-evaluated`](engine.md#zcrypto-engine-exec-not-evaluated) — ALERT: the execution safety gate has stopped being evaluated, so every gauge describing it is frozen.
- [`zcrypto-venue-concordance-failed`](engine.md#zcrypto-venue-concordance-failed) — ALERT: a ratified instrument is missing from the venue's set, or its constraints came back absent or unparseable.
- [`zcrypto-venue-snapshot-stale`](engine.md#zcrypto-venue-snapshot-stale) — ALERT: no successful venue-truth snapshot has landed in over five hours.
- [`engine-data-socket-idle`](engine.md#engine-data-socket-idle) — KNOWN LIMITATION: the engine's data socket is idle by design while disarmed, and its reconnect lines exist only in `docker logs`.
- [`zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale) — ALERT: the engine has completed no cycle in over 4h35m, or its series is gone entirely.
- [`zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) — ALERT: a non-zero position at last sight with the engine's scrape gone — exposure with nothing watching it.
- [`zcrypto-engine-cycle-failed`](engine.md#zcrypto-engine-cycle-failed) — ALERT: the engine's last cycle failed.
- [`zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs) — ALERT: at least one ERROR or CRITICAL line from the engine in the last 15 minutes.
- [`zcrypto-engine-log-dead`](engine.md#zcrypto-engine-log-dead) — ALERT: Loki holds no engine log line of any level in the last 6 hours.

### [`engine-procedures.md`](engine-procedures.md) — the engine's attended procedures

- [`engine-probe-window`](engine-procedures.md#engine-probe-window) — PROCEDURE: the attended live-order probe window, and the only sanctioned way to run one. Real money moves.
  - [`adopt-pass-blind-legs`](engine-procedures.md#adopt-pass-blind-legs) — inside the arm step: the five legs the venue's open-order read is blind on, in every state an order can be in.
- [`engine-tracking-band`](engine-procedures.md#engine-tracking-band) — PROCEDURE: the weekly tracking-error trip — what its verdict tile is saying, and what has to be true before a band is set.
- [`engine-flatten`](engine-procedures.md#engine-flatten) — PROCEDURE: the emergency halt — one command that stops the engine and closes the whole account at market, at whatever price the market gives.
  - [`flat-verdict-blind-legs`](engine-procedures.md#flat-verdict-blind-legs) — the third limit: the five legs the flat verdict cannot see, so exit 0 can be a false all-clear.
  - [`flatten-read-only-dry-run`](engine-procedures.md#flatten-read-only-dry-run) — beside the press: who runs the read-only dry run that proves the five account reads, and the adapter-verification row it discharges into.
- [`engine-adhoc-key-read`](engine-procedures.md#engine-adhoc-key-read) — PROCEDURE: the one-off read that needs the live trade key — inside the engine image, driven from the workstation, inside the engine play's own window.

### [`order-semantics-verification.md`](order-semantics-verification.md) — the adapter's order semantics on a new nautilus version

- [`order-semantics-verification`](order-semantics-verification.md#order-semantics-verification) — PROCEDURE: the attended ~EUR 0.20 six-probe pass a nautilus bump owes before the engine may be armed on it. Real money moves.

### [`reference-data.md`](reference-data.md) — facts a third party owns

- [`refdata-sweep-due`](reference-data.md#refdata-sweep-due) — SCHEDULED REMINDER: the Kraken reference-data re-confirmation sweep is due.

### [`capture-daemon.md`](capture-daemon.md) — the capture daemon's own guards

- [`zcrypto-capture-book-desync-stuck`](capture-daemon.md#zcrypto-capture-book-desync-stuck) — ALERT: a pair's book has been stuck in desync; the `pair` label names it.
- [`zcrypto-capture-resubscribe-rate`](capture-daemon.md#zcrypto-capture-resubscribe-rate) and [`zcrypto-capture-resubscribe-failing`](capture-daemon.md#zcrypto-capture-resubscribe-failing) — ALERT, one section serving both uids: a host resubscribed a book more than once in a day, or the resubscribe leg itself was refused or timed out.
- [`zcrypto-capture-watermark-breached`](capture-daemon.md#zcrypto-capture-watermark-breached) — ALERT: a capture host crossed its disk watermark and is DISCARDING data.
- [`zcrypto-capture-error-logs`](capture-daemon.md#zcrypto-capture-error-logs) — ALERT: at least one ERROR or CRITICAL line from a capture daemon in the last 15 minutes.

### [`hosts.md`](hosts.md) — disk, load, reboots and the textfile transport

- [`zcrypto-capture-disk-low`](hosts.md#zcrypto-capture-disk-low) — ALERT: a capture host's root filesystem is below 10 % free.
- [`zcrypto-capture-load-high`](hosts.md#zcrypto-capture-load-high) — ALERT: a capture host's 1-minute load average is above 1.5 per core.
- [`zcrypto-capture-reboot-pending`](hosts.md#zcrypto-capture-reboot-pending) — ALERT: `/run/reboot-required` has existed on a capture host for 15 minutes.
- [`zcrypto-capture-textfile-missing`](hosts.md#zcrypto-capture-textfile-missing) and [`zcrypto-capture-textfile-unreadable`](hosts.md#zcrypto-capture-textfile-unreadable) and [`zcrypto-reboot-probe-stale`](hosts.md#zcrypto-reboot-probe-stale) and [`zcrypto-oneoff-textfile-stale`](hosts.md#zcrypto-oneoff-textfile-stale) — ALERT: Four warning-severity rules over **one transport**.
- [`zcrypto-engine-journal-prune-dead`](hosts.md#zcrypto-engine-journal-prune-dead) — ALERT: the primary's daily engine-journal prune has not completed in over 26 hours, or its completion gauge has vanished.

### [`observability.md`](observability.md) — the telemetry planes themselves

- [`zcrypto-alloy-dark-nas`](observability.md#zcrypto-alloy-dark-nas) and [`zcrypto-alloy-dark-ops`](observability.md#zcrypto-alloy-dark-ops) and [`zcrypto-alloy-dark-capture-primary`](observability.md#zcrypto-alloy-dark-capture-primary) and [`zcrypto-alloy-dark-capture-secondary`](observability.md#zcrypto-alloy-dark-capture-secondary) — ALERT, one section serving four uids: the named host's `up` series has been absent from Grafana Cloud for over 10 minutes.
- [`zcrypto-node-collector-failed`](observability.md#zcrypto-node-collector-failed) — ALERT: a node-exporter collector is failing on some host.
- [`zcrypto-logship-lines-dropped`](observability.md#zcrypto-logship-lines-dropped) and [`zcrypto-logship-worker-stalled`](observability.md#zcrypto-logship-worker-stalled) — ALERT, one section serving both uids: the direct-ship log path dropped lines before reaching Loki, or its worker stalled.
- [`zcrypto-capture-log-dead-primary`](observability.md#zcrypto-capture-log-dead-primary) and [`zcrypto-capture-log-dead-secondary`](observability.md#zcrypto-capture-log-dead-secondary) — ALERT, one rule per capture host: no parsed capture-daemon log line of any level has reached Loki from that host in 6 hours.
- [`zcrypto-ops-log-pipeline-dead`](observability.md#zcrypto-ops-log-pipeline-dead) and [`zcrypto-ops-poller-log-dead`](observability.md#zcrypto-ops-poller-log-dead) and [`zcrypto-ops-unit-parse-dead`](observability.md#zcrypto-ops-unit-parse-dead) and [`zcrypto-ops-journal-transport-dead`](observability.md#zcrypto-ops-journal-transport-dead) — ALERT, one section serving four uids: one of the ops node's log-plane dead-men fired.
- [`zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) — ALERT: a healthchecks.io check is down, or healthchecks.io itself is unreadable.
- [`grafana-cloud-dark`](observability.md#grafana-cloud-dark) — PROCEDURE: Grafana Cloud itself is unreadable — no Grafana rule can page for this.

### [`ops-node.md`](ops-node.md) — the ops node's timers and units

- [`zcrypto-ops-archive-pull-stalled`](ops-node.md#zcrypto-ops-archive-pull-stalled) and [`zcrypto-ops-archive-pull-exit-nonzero`](ops-node.md#zcrypto-ops-archive-pull-exit-nonzero) — ALERT, one section serving both uids: the overlay-writer cycle stalled, or exited non-zero.
- [`zcrypto-trade-backfill-stale`](ops-node.md#zcrypto-trade-backfill-stale) and [`zcrypto-trade-backfill-exit-nonzero`](ops-node.md#zcrypto-trade-backfill-exit-nonzero) — ALERT, one section serving both uids: the daily trade-tape healing step went stale, or exited non-zero.
- [`zcrypto-ops-verified-replay-stale`](ops-node.md#zcrypto-ops-verified-replay-stale) and [`zcrypto-ops-verified-replay-exit-nonzero`](ops-node.md#zcrypto-ops-verified-replay-exit-nonzero) — ALERT, one section serving both uids: the daily verified-path replay of the engine journal went stale, or exited non-zero.
- [`zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) — ALERT: the last hourly L2 panel materialize errored.
- [`zcrypto-ops-load-high`](ops-node.md#zcrypto-ops-load-high) — ALERT: the ops node's 1-minute load average is above 20.
- [`zcrypto-ops-error-logs`](ops-node.md#zcrypto-ops-error-logs) — ALERT: an ERROR or CRITICAL line from the ops node.
- [`agentboard-node-upgrade`](ops-node.md#agentboard-node-upgrade) — PROCEDURE: moving the ops node's web terminal onto a new node or `@gbasin/agentboard` pin, and why that restart is only safe with `KillMode=process`.

### [`nas.md`](nas.md) — the durable archive and its pull loop

- [`zcrypto-nas-disk-low`](nas.md#zcrypto-nas-disk-low) — ALERT: the NAS's `/volume1` is below 10 % free.
- [`zcrypto-nas-load-high`](nas.md#zcrypto-nas-load-high) — ALERT: the NAS's 1-minute load average is above 4.
- [`zcrypto-nas-archive-pull-errors`](nas.md#zcrypto-nas-archive-pull-errors) — ALERT: at least one ERROR or CRITICAL line from the NAS's archive-pull container in the last 15 minutes.
- [`zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled) — ALERT: the NAS's archive-pull has logged no successful completion in the last 3 hours.
- [`nas-file-transfer`](nas.md#nas-file-transfer) — PROCEDURE: the `/volume1` sftp chroot, and the `nas-hot:` rrsync endpoint whose overwrites are skipped in silence.

### [`gate.md`](gate.md) — the shadow-concordance export on the NAS

- [`zcrypto-gate-streak-reset`](gate.md#zcrypto-gate-streak-reset) — ALERT: the gate's streak of consecutive clean days dropped.
- [`zcrypto-gate-mismatch`](gate.md#zcrypto-gate-mismatch) — ALERT: the gate found a mismatch in the last day.
- [`zcrypto-gate-pull-lag`](gate.md#zcrypto-gate-pull-lag) — ALERT: the gate's journal pull is over 6 h behind.
- [`zcrypto-gate-exporter-stale`](gate.md#zcrypto-gate-exporter-stale) — ALERT: the gate exporter has not published for over 2 h.
- [`zcrypto-gate-cache-reverify-stalled`](gate.md#zcrypto-gate-cache-reverify-stalled) — ALERT: the gate's cache re-verification has been stalled for over 3 days.

### [`drills-telemetry.md`](drills-telemetry.md) — induce a telemetry fault on purpose, measure what fires

No money moves here. A row's link lands below that file's standing rules — read them first.

- [`drill-c`](drills-telemetry.md#drill-c) — PROCEDURE: the ingest plane goes dark, held long enough to measure what a restarted shipper recovers per plane.
- [`drill-c-prime`](drills-telemetry.md#drill-c-prime) — PROCEDURE: C′, Grafana Cloud dark — the page time on each of the two routes the ops-side watchdog can fail by.
- [`drill-i`](drills-telemetry.md#drill-i) — PROCEDURE: a disk watermark breach through a withheld ping to a page, end to end, on the ops node and on no capture host.
- [`drill-j-prime`](drills-telemetry.md#drill-j-prime) — PROCEDURE: J′, the `/fail` route on a dead-man — that an explicit fail ping leaves a process, moves the check and reaches Slack on both routes.
- [`drill-k`](drills-telemetry.md#drill-k) — PROCEDURE: Alloy killed and timed — the Alloy-dark bound measured rather than computed, and the restart recipe verified by value.
- [`drill-o`](drills-telemetry.md#drill-o) — PROCEDURE: timer death — whether the one ops timer with no Grafana staleness rule is caught by its dead-man alone.
- [`drill-p-plus-r`](drills-telemetry.md#drill-p-plus-r) — PROCEDURE: P+R, the secondary goes away — the one log class no Alloy pipeline sees, whose liveness rests entirely on a dead-man, and that the **primary stays whole** across the window.
- [`drill-q`](drills-telemetry.md#drill-q) — PROCEDURE: does the phone actually buzz — a page reaching a **phone**, on each of the three receivers independently.
- [`proven-tier-reverification`](drills-telemetry.md#proven-tier-reverification) — PROCEDURE: whether a scenario already proven — by a drill or by a real incident — needs another run.

### [`drills-order-path.md`](drills-order-path.md) — induce the fault where money is at stake

Every section below runs inside an attended probe window ([`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window)) and exposes real money. A row's link lands below that file's standing rules and its warning about the drill letters — read from the top.

- [`drill-a1`](drills-order-path.md#drill-a1) — PROCEDURE: the primary reboots with an order resting and no fill — the capture gap healed from the secondary, the reduce-only hold latched, the resting opener cancelled by the startup adopt pass.
- [`drill-a2`](drills-order-path.md#drill-a2) — PROCEDURE: the primary reboots and a fill lands while it is down — a fill the engine was not present to hear, reconciled at startup into a **real position** the operator is left holding.
- [`drill-b`](drills-order-path.md#drill-b) — PROCEDURE: the red button — decision-to-flat in wall-clock minutes.
- [`drill-d`](drills-order-path.md#drill-d) — PROCEDURE: the engine goes dark with a position open — that the page nothing else covers reaches a phone, and how long an operator stays unaware of an unwatched position.
- [`drill-e`](drills-order-path.md#drill-e) — PROCEDURE: the kill switch — a hand-placed kill file revoking a resting order inside the executor's tick, and the alert half reaching Slack inside its bound.
- [`drill-e-prime`](drills-order-path.md#drill-e-prime) — PROCEDURE: E′, the phone-reachable halt — the same placement made from a phone over the fleet's access path, timed from the decision. Run inside E.
- [`drill-f2`](drills-order-path.md#drill-f2) — PROCEDURE: the engine loses its socket with an order resting — one cancel attempt, then an `ambiguous` intent, and an order that may still be resting at Kraken with nothing in the process able to reach it.
- [`drill-g`](drills-order-path.md#drill-g) — PROCEDURE: restart with an order resting — what the venue does with a GTC opener across an engine stop, the reduce-only hold latching, and the adopt pass attaching every matched row before it cancels. Runs on a one-way-spelled leg.
