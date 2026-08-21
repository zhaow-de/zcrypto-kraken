# Ops runbooks — the nightly archive sweep and the tape-bars dataset

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

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

<a name="zcrypto-reconcile-residual-gap"></a>

## zcrypto-reconcile-residual-gap — ALERT

### What you are seeing

A critical-severity Grafana alert (`Reconciler · residual gap increased (permanent loss)`): `zcrypto_reconcile_residual_gap_seconds_total` increased with no counter reset in the last 24 hours. This is the highest-severity rule in the system.

### What it means

**The counter books the ABSENCE of data, never fault attribution.** It is derived by summing an append-only ledger and is monotonic, so whatever it books is permanent — there is no later correction path short of a deliberate, approved ledger edit. A venue outage lands here exactly the same way a capture failure does: both leave no book data on either host for the window, and the counter cannot on its own tell the two apart. Reading this page as "we lost data" is correct; reading it as "our capture broke" is not, and the discriminator below exists precisely to stop that leap.

The three record shapes that drive it are `both_streams_silent`, `total_loss`, and a minted/would_mint hour whose splice left seconds unfilled — of these, only `both_streams_silent` carries the discriminator, because it is the one case where both hosts were reachable and simply recorded nothing.

### What to do

1. **Read the `verdict` on the hour's `both_streams_silent` ledger record** — TRIAGE FIRST, before chasing the fleet. **A record carrying no `verdict` key at all reads `undetermined`, not a failed read**: every record booked before the discriminator shipped carries no field, and the exporter folds those into `undetermined` deliberately. The reconciler also logs the whole answer as it books — `archive reconcile: both_streams_silent hour=… verdict=… updates=… snapshots=… divergent=…` — which is the fastest read and the only one carrying the evidence counts. `zcrypto_reconcile_dark_episode_seconds_total` answers from Prometheus, but it is cumulative over the whole ledger: read the **step** across the `:12`/`:42` tick that booked your hour, never its level.
2. **`venue_silent`**: both capture hosts recorded the same venue message timestamps inside the window, so the silence was upstream of both hosts. Weigh it as a venue event, not a capture fault — and treat it sceptically if a fleet-wide image change just landed, since both hosts run the same digest by the canary rule and a shared-digest bug can masquerade as venue agreement.
3. **`capture_divergent`**: one host missed what the other received. This is a real capture-side discrepancy — investigate the fleet.
4. **`undetermined`** — including a record with no `verdict` key: no evidence either way from the cross-host comparison, which is where a hard halt lands, since a venue emitting *nothing* leaves no interior messages for the two hosts to agree on. Treat it as loss, then ask whether the venue **announced** it. Fastest: look **back** in the alert list for `Capture · Kraken reports the venue is not online` — it reads the venue's own WebSocket `status` frames, typically fires ~2 h before this page, and its `activeAt` is the announcement time. Otherwise read the frames directly: `sudo docker logs zcrypto-capture 2>&1 | grep "venue status"` on either capture host, or the same line via Loki — each line carries its own UTC timestamp, so scope by reading the line, never by `--since`. **Reading `zcrypto_capture_venue_status_total` instead needs care, and neither obvious form works**: it *latches* until the capture daemon restarts, so bare presence at H+2 h can be a different day's event; and `increase()` is blind to a first sighting, so a clean one-frame transition reads 0 — which is exactly the shape of a host that restarted shortly before the event. Take a series **born** inside hour H, or one that **steps** inside it, and nothing else; a series flat across H is not evidence either way, because Kraken pushes `status` on connect and on change only. **If the venue announced it, write the event's row in `docs/reference/capture-era-data-hygiene-map.md`** — that map, not this counter, is the durable answer to "was this hour ours?", because the counter and the log both age out with retention.

### Retire when

Never, while `zcrypto_reconcile_residual_gap_seconds_total` exists — this is the triage path for the system's highest-severity rule.
