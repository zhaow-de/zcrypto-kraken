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

**One booking keeps this red for 24 hours by construction** — the expression is `increase(...[24h])`, so an hour-H gap booked at the `:12`/`:42` tick after H+2 h holds the alert firing until that tick leaves the window a day later, and every notification in between is the **same** event re-notifying, never evidence of a new one. Whether anything *new* booked is read from the counter's **level**: compare `zcrypto_reconcile_residual_gap_seconds_total` now against the total your triage recorded — flat means no new booking. (The `increase()` value itself reads slightly above the booked seconds — Prometheus extrapolates to the window edges; a ~0.07 % excess is the extrapolation, not a second increment.) Expect resolution at the first evaluation after the booking tick + 24 h; verify it actually resolves then rather than assuming.

**And a flat level is only a clean bill while the writer cycle is alive.** Check the age of `zcrypto_reconcile_last_success_timestamp_seconds`: the stamp is written at cycle **completion**, and a steady-state cycle now runs in seconds, so healthy is one tick interval (30 min) plus a seconds-scale cycle — an age past ~35 min is already worth a look, and a cycle long enough to matter has its own warning ([`zcrypto-reconcile-cycle-duration`](#zcrypto-reconcile-cycle-duration)) well below the 3 h staleness page. The 23-minute cycle measured during the 2026-08-21 vol spike (\[[T0147]\]) is the **pre-`00097`** cost model that motivated the change, not a reading to expect today; before that spec the stamp was written near cycle *start* and mis-stated a long cycle's completion by its whole duration. The cycle also **skips fail-closed** on a stale or unclean NAS `.pull-status` (rc 0, `WARNING: writer cycle SKIPPED` in the unit journal naming the reason — routine for ~2 ticks after the NAS 02:25 reboot); a persistent skip only pages via `zcrypto-reconcile-exporter-stale` at 3 h, so during a triage read the journal, not just the alert list. Unit journals on the ops host need `sudo` — unprivileged `journalctl -u` prints `-- No entries --` plus a hint, which is a permissions artifact, never evidence the unit did not run.

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

______________________________________________________________________

<a name="zcrypto-reconcile-healable-gap-rate"></a>

## zcrypto-reconcile-healable-gap-rate — ALERT

### What you are seeing

A warning-severity Grafana alert (`Reconciler · primary gap rate high (degrading host)`). Nothing was lost: every gap this counts **was covered by the secondary**. The signal is that the primary needed a lot of covering.

**Read the threshold correctly or you will mis-triage it.** The expression divides by the live pair count before comparing — `increase(zcrypto_reconcile_healable_gap_seconds_total[24h]) / scalar(count(count by (pair) (zcrypto_capture_book_desynced)))` against `gt [600]` — so it fires on **600 s of healable silence per pair**, not 600 pair-seconds in total. At twelve live pairs that is 7,200 pair-seconds. Comparing a ledger total straight to 600 overstates the reading by the pair count, and the divisor is what makes the summary's "more than 10 minutes" literally true.

### What it means

The primary was silent, and the secondary had genuine `update` rows inside that silence, so the splice repaired it. Redundancy did its job. A host that repeatedly needs this much repair is **degrading** — that is the condition worth acting on, not the individual hours.

The counter is denominated in primary silence deliberately: a correlated outage where both mirrors go dark is not the primary degrading, and those seconds belong to `zcrypto_reconcile_residual_gap_seconds_total` instead.

### What to do

1. **Read the ledger's `would_mint` / `minted` records for the window** — `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` on `zcrypto-ops`. Look for a pattern: one bad hour is weather, the same pair or the same hour-of-day repeating is the primary degrading.
2. **Check the primary's own health before blaming the feed** — capture container `RestartCount`, its `/metrics`, and whether the hours cluster around a converge or a reboot.
3. **A one-off spike after a deliberate event is not a finding.** The 2026-07-17 drill stopped the primary on purpose and booked 15,509 s; a staged event is not evidence of degradation.

### Retire when

`zcrypto_reconcile_healable_gap_seconds_total` stops existing, or the rule is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="healable-threshold-rederivation-due"></a>

## healable-threshold-rederivation-due — SCHEDULED REMINDER

### What you are seeing

A message in Slack `#zcrypto` prompting a re-read of the healable-gap-rate threshold. It is not an alert — **nothing is wrong**. Like `refdata-sweep-due`, it is a calendar trigger with no metric behind it.

### What it means

The `gt [600]` threshold above is **provisional**: it was set before enough steady-state history existed to fit it, and the fit is still owed. Two facts bound what it should become — at twelve pairs the two post-fix events measured **44.5440 s and 41.2144 s per pair**, i.e. 7.4 % and 6.9 % of the threshold, so real events have come nowhere near it.

### What to do

1. **Count the qualifying days from the LEDGER, never from Grafana Cloud.** Cloud retains ~14 days; every event so far predates its window, so a `[90d]` selector there returns zero over a series it has never seen move — the reading that once wrongly licensed dropping this work.

   ```
   ssh hp "sudo cat /var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl"
   ```

   Sum per day with the **production expression** from `cli/archive/command.py` — `float(d.get("claimed_seconds") or d.get("healed_seconds") or 0.0)` — and confirm your total equals the live gauge before trusting the per-day split. A parse that misses the `healed_seconds` fallback totals wrong and mis-attributes days.

2. **Count only days AFTER the 2026-07-28 counter fix.** Earlier values are not fittable: 2026-07-17 was a staged drill, and 2026-07-27's value is 96.4112 % fiction — that overstatement is what the fix corrected.

3. **Fewer than three qualifying days ⇒ do nothing except re-arm.** Schedule the next reminder in `#zcrypto` — the following month, matching `refdata-sweep-due`'s cadence — and stop. Fitting from one or two points is the intuition-wearing-a-table this threshold already suffered from once.

4. **Three or more ⇒ the re-derivation is due, and it is real work** — fit the threshold, push it with `infra/grafana/alerts.yaml`, verify the pushed rule by reading it back from the provisioning API rather than trusting an exit code. Open a `T<NNNN>` for it if it needs a decision; this runbook holds the trigger, not the backlog.

### Retire when

The threshold has been re-derived from steady-state history and pushed live, or `zcrypto-reconcile-healable-gap-rate` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-reconcile-cycle-duration"></a>

## zcrypto-reconcile-cycle-duration — ALERT

### What you are seeing

A warning-severity Grafana alert (`Reconciler · cycle approaching its own tick`): the last completed overlay-writer cycle took more than 1,500 s, against the 1,800 s between its `:12`/`:42` ticks.

### What it means

Cycle duration tracks two things: the data volume in the trailing 48 h window, and how many of those hours were actually examined rather than skipped. A settled hour whose inputs have not changed is skipped on a fingerprint match, which normally holds a steady-state cycle to tens of seconds — so a page here says one of two things. Either **the skip cache is being bypassed** and the cycle is re-deriving the whole window every 30 minutes, or **the volume genuinely outgrew** what the vectorized arithmetic can chew through in a tick.

Nothing is lost yet: at 1,500 s the cycle still finishes inside its tick. Past 1,800 s the timer's next trigger fires against a unit that is still running, systemd **drops** it rather than queueing it, and the booking cadence silently halves — with no other rule below `zcrypto-reconcile-exporter-stale`'s 3 h to say so. That is the outcome this warning exists to stay ahead of, which is why it is a warning and not a page about loss.

### What to do

1. **Read the skip counts first — they are the discriminator.** `zcrypto_reconcile_hours_skipped` is on the same panel as the duration series, and the cycle's own completion log carries `skipped=` and `audited=`. A healthy steady state skips every window hour except the newest few (not yet past the 6 h late deadline, so never cached) and the 2 it audits — roughly 42 of 48. `skipped=` is an **observation** — counted inside the skip branch, so it reports what the loop did rather than what it planned; a plan-derived count once read `1` with the skip disabled. `audited=` is the cycle's **selection**, and those hours are examined by construction (an audit hour is never in the skip set), so the two are not the same kind of claim.
2. **`skipped=0` on consecutive cycles means the cache is not engaging.** It degrades *silently* — there is no error for most of these — so work the list:
   - **A `scan-cache audit divergence` ERROR dropped it.** Grep the cycle log for that phrase; it names the hour and fingerprint. One divergence deletes the whole cache deliberately, so the next cycle is full and slow by design. Two in a row is a real finding about the fingerprint model, not a slow cycle.
   - **A pair was just added.** Expect `skipped=0` for a full window (48 h) *plus* the primary→secondary interval: a new pair is absent from every window hour older than its genesis, and pairs are added to the primary first, so the two hosts disagree for the length of that gap. Self-clearing — confirm the dates line up and wait it out.
   - **A thin pair published no trades final for some hour.** Legitimate and permanent for that hour: an hour with zero prints writes no file at all. Measured at ~0.16 % of pair-hours — about one hour of a 48 h window — and the count grows as thinner pairs enter the universe, so this is a rising floor rather than a fault.
   - **Hours are incomplete.** Check which finals are absent. A pair **permanently removed** from capture is the bad shape: every window hour is then missing that pair, the absence set is stable, `skipped=0` is permanent, and the whole cache is disabled with nothing logged. If the removal was intended, the fix is upstream — the pair list, not the cache.
   - **A manual ledger or overlay mutation deleted it**, which is correct — see below.
3. **A healthy skip count with a high duration means volume.** The cache is working and the cycle is still slow, so the examined hours themselves are big. Re-derive the headroom (duration against the 1,800 s tick) before the next volatility regime rather than after it, and treat a sustained climb as capacity work.
4. **A manual mutation of the reconcile ledger or the overlay must delete `<reconciled_root>/scan-cache.json` in the same act.** The cache's fingerprint covers the overlay as well as both mirrors, but a ledger edit is invisible to it — so a correction that leaves the cache in place leaves entries describing a state that no longer exists. The next cycle then skips the very hours the correction was meant to force a re-examination of, and the sampled audit only reaches a given hour after rotating through the window's ~44 cacheable hours two per cycle, twice an hour: **up to ~11 h of divergence before anything pages.** Deleting it makes the next cycle deliberately full instead. The ledger-correction procedure in `infra/nas/README.md` carries this as a step.

### Retire when

`zcrypto-reconcile-cycle-duration` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

<a name="reconcile-ledger-scan-cost"></a>

## reconcile-ledger-scan-cost — ALERT

### What you are seeing

One of two rules on `zcrypto_reconcile_ledger_scan_seconds`: the warning at 10 s, or the critical at 30 s. Both measure one thing — the wall-clock cost of reading and summing the whole append-only reconcile ledger, which every cycle does in full.

### What it means

The exporter's cumulative counters are derived by summing the entire ledger on every cycle, so both halves of that work are O(ledger). That is by design and is what keeps the counters monotone across a one-shot process with no memory; the cost is the price of it.

- **Warning (10 s)** — the ledger has become the cost driver: comparable to what an entire cycle costs today, while still well under 1% of the 30-minute tick, so nothing is at risk. What has changed is that append-only-forever stopped being free, and is now worth revisiting on evidence.
- **Critical (30 s)** — the constraint is **memory, not time**. Each record is held as a Python object at roughly six times its size on disk, so at this scan cost the ledger holds about a quarter of the memory the host had available when the bar was set, on a host it shares with the panel materialiser and the replay jobs. This is the failure `zcrypto-reconcile-cycle-duration` cannot warn you about: a cycle killed for memory publishes nothing, so that gauge goes **stale rather than high**, and the only other cover is the 3-hour exporter-stale page.

Both bars are provisional and say so in `infra/grafana/alerts.yaml`: they come from a linear fit, not from a ledger observed at that size.

### What to do

1. **Re-measure before deciding anything.** `uv run python infra/scripts/bench-ledger-scan.py` reproduces the curve at any size, so the question is a command rather than an estimate. Compare what it reports against the live `zcrypto_reconcile_ledger_records` — if the fit still holds, the remaining headroom is arithmetic; if it has bent, the fit was the wrong model and the bars need re-deriving from the new curve.
2. **Read the host's MemAvailable — never MemFree**, because that is what the critical bar encodes and it moves independently of this repo. The two differ about tenfold on a busy box, so reading the wrong one turns a healthy host into an apparent three-times over-commit. Query `node_memory_MemAvailable_bytes{host="ops"}` via `uv run python infra/scripts/grafana-query.py`, or read `MemAvailable` in `/proc/meminfo` on `ssh hp`. `docs/reference/fleet.md`'s ops row records the value the bar was set against. The reconciler runs uncapped, so its ceiling is whatever the host has available.
3. **Then renovate, not before.** The shape that preserves the counters is a compaction that folds everything older than the retention horizon into a single opening `carried_forward` record, so the sums stay exact while the scanned file stays bounded. Do NOT simply truncate — that resets every counter and pages the permanent-loss rule. One obligation comes with it: a compaction must not look like a ledger correction, since `zcrypto_reconcile_ledger_records` falling is what explains a counter reset.
4. **A one-off spike with a flat record count is not this alert's subject** — that is host contention, and the record count beside it on the panel is what tells the two apart.

### Retire when

`zcrypto_reconcile_ledger_scan_seconds` is no longer published by `cli/archive/command.py`, or the ledger stops being scanned in full each cycle — i.e. compaction has landed and the counters are derived from a bounded read.
