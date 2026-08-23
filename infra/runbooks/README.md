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
- [`cross-hour-straddle`](capture.md#cross-hour-straddle) — KNOWN LIMITATION: silence that began before an hour boundary is measured from the boundary, not from its true start.

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
- [`zcrypto-reconcile-cycle-duration`](ops.md#zcrypto-reconcile-cycle-duration) — ALERT: the overlay-writer cycle is approaching the interval between its own ticks, past which the next trigger is dropped and the booking cadence halves.

### [`engine.md`](engine.md) — the trading engine and its order path

- [`zcrypto-engine-sleeve-count-changed`](engine.md#zcrypto-engine-sleeve-count-changed) — ALERT: the number of sleeves carrying exposure stepped, so the book's gross moved roughly in proportion.
- [`zcrypto-engine-exec-armed-too-long`](engine.md#zcrypto-engine-exec-armed-too-long) — ALERT: order submission has been armed for six unbroken hours.
- [`zcrypto-engine-exec-kill-tripped`](engine.md#zcrypto-engine-exec-kill-tripped) — ALERT: the execution kill switch is engaged, so nothing may be submitted.
- [`zcrypto-engine-exec-not-evaluated`](engine.md#zcrypto-engine-exec-not-evaluated) — ALERT: the execution safety gate has stopped being evaluated, so every gauge describing it is frozen.
- [`zcrypto-venue-concordance-failed`](engine.md#zcrypto-venue-concordance-failed) — ALERT: a ratified instrument is missing from the venue's set, or its constraints came back absent or unparseable.
- [`zcrypto-venue-snapshot-stale`](engine.md#zcrypto-venue-snapshot-stale) — ALERT: no successful venue-truth snapshot has landed in over five hours.
- [`engine-probe-window`](engine.md#engine-probe-window) — PROCEDURE: the attended live-order probe window, and the only sanctioned way to run one. Nothing fires this; you open it deliberately, and real money moves.
- [`engine-tracking-band`](engine.md#engine-tracking-band) — PROCEDURE: the weekly tracking-error trip — what its verdict tile is saying, and what has to be true before a band is set. Nothing fires this; a breach pages through the kill-switch alert above.

### [`order-semantics-verification.md`](order-semantics-verification.md) — the adapter's order semantics on a new nautilus version

- [`order-semantics-verification`](order-semantics-verification.md#order-semantics-verification) — PROCEDURE: the attended ~EUR 0.20 six-probe pass a nautilus bump owes before the engine may be armed on it. Nothing fires this; you run it deliberately, and real money moves.

### [`reference-data.md`](reference-data.md) — facts a third party owns

- [`refdata-sweep-due`](reference-data.md#refdata-sweep-due) — SCHEDULED REMINDER: the Kraken reference-data re-confirmation sweep is due. Nothing is wrong.
