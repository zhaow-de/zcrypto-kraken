# Capture runbooks — the venue feed and the archive's hour boundaries

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-capture-venue-not-online"></a>

## zcrypto-capture-venue-not-online — ALERT

### What you are seeing

A warning-severity Grafana alert. Kraken's WebSocket `status` channel reported a `system` value other than `online` on at least one capture host. The page carries that value — one alert instance per `(host, system)` — so you already know *which* state was reported before opening anything.

### What it means

The capture daemon counts every `status` frame it receives, labelled by the `system` value, into `zcrypto_capture_venue_status_total`. Kraken pushes `status` on every connect, so the counter advances routinely — **only the non-`online` label is unusual.**

No record-keeping is owed here beyond normal triage.

This does **not** by itself mean data is being lost. A venue in `maintenance` or `cancel_only` may still stream book updates, and the capture path is unaffected by order-entry state. Loss shows up on the reconciler's counters, not here.

### What to do

1. **Read the state and its ladder.** The `system` value is on the page; the full transition sequence is in the capture log: `sudo docker logs zcrypto-capture 2>&1 | grep "venue status"` on either host (or the same line via Loki). Kraken's observed exit ladder is `maintenance` → `cancel_only` → `post_only` → `online`. `effective_time` has been observed only as `None`, so expect no advance notice **in the frame** — the advance notice is on Kraken's published calendar instead.
2. **A venue-side halt DOES book permanent loss. Expect the loss page, hours later.** The reconciler books it as `both_streams_silent` against the halt's hour. `zcrypto-reconcile-residual-gap` carries `for: 0s`, so it TRANSITIONS within a scrape of the booking while the notification lands later. Read the booking's own log line rather than waiting on the page: `archive reconcile: both_streams_silent hour=… windows=… residual_s=… verdict=…`, in the reconciler's journal on `zcrypto-ops` (needs `sudo`) or via Loki — `residual_s` is the booked seconds per stream. The data is genuinely gone: the venue emitted nothing, so no host missed anything that existed, but "no component failed" is not "no loss". Do not tell yourself otherwise, and do not close the incident before the reconciler has spoken.
3. **Do NOT read `zcrypto_reconcile_residual_gap_seconds_total` during or just after the halt — it cannot answer yet, and it will answer reassuringly.** Booking waits on `SETTLE_HOURS = 2` measured from the hour's **START** (`settled_hours` takes `floor(now) − 2 h`), and the reconcile timer runs at `*:12,42`. `zcrypto_reconcile_last_success_timestamp_seconds` does NOT protect you here: it is run liveness, not coverage, and can read maximally fresh while a lost hour is still unbooked. The only sound check is the clock: **hour H is bookable no earlier than H+2 h, at the next `:12`/`:42` tick.**
4. **Check whether CAPTURE degraded** — that is a different question from whether data was lost, and it is the one you can answer now: `zcrypto_capture_seconds_since_last_book_message` per pair, `RestartCount` on both daemons. **Which of the two capture silence rules fired measures the halt's LENGTH, not its severity**: the fleet-wide critical rule crosses at 120 s — guaranteed only by ~180 s of silence once a 60 s scrape is allowed for — while the per-pair rule needs over 300 s on a pair. So a halt of a few minutes fires the critical rule alone, a very short one can fire neither, and the per-pair rule sitting Normal BOUNDS the halt rather than exposing a blind spot: its own notice period is 300 s plus a scrape and an evaluation, so ~5–7 min of silence on a pair before it speaks. Whichever fired and auto-resolved around the window is that rule working, and each has its own section below if you need to triage one on its own. They report the same halt in a different vocabulary; they are not a second incident.
5. **Do not converge or restart anything on this signal alone.** Nothing in the capture path reacts to venue status; a restart costs a resubscribe and buys nothing. A feed that heals itself has still cost unbackfillable L2 on every pair, which the loss page reports about two hours later.
6. **Silence `zcrypto-capture-venue-not-online` once triaged, time-boxed — and NEVER `zcrypto-capture-venue-state-recurrence`.** The latch is a counter-presence check, so it stays firing for the daemon's whole lifetime — the counter resets only when the capture daemon restarts, which is gated on a bake. Silence in Grafana on **that uid only**, for a bounded window, **with `system` matched to the states you have actually read** — matchers are conjunctive, so a silence naming no `system` also suppresses the states you have not triaged, including a value new to this fleet; widen it as the ladder climbs, never ahead of it — and **delete it at each host's own next capture restart — per host, never fleet-wide**: the canary rule restarts the secondary days ahead of the primary, so one silence outlives the other host's reset. That deletion is not tidiness, it is the blind spot closing — a restart zeroes the counter, which makes the next event's states first sightings again, and on a first sighting the recurrence rule's `increase()` reads only what arrives after the first scrape, so a brand-new outage under a stale silence pages on a coin flip at best. Do not delete the rule. The recurrence rule is the one signal that still reports a repeat while the latch is stuck, and it self-resolves on its own — silencing it re-opens exactly the blind spot it was added to close.

### Retire when

Both `zcrypto-capture-venue-not-online` and `zcrypto-capture-venue-state-recurrence` are absent from `infra/grafana/alerts.yaml` — i.e. the rules were deliberately removed.

______________________________________________________________________

<a name="zcrypto-capture-venue-state-recurrence"></a>

## zcrypto-capture-venue-state-recurrence — ALERT

### What you are seeing

A warning-severity Grafana alert, and the one that means **it is happening now**, not "it happened once". Kraken reported a non-`online` `system` value within the last 15 minutes on at least one capture host. One instance per `(host, system)` pair, same as its sibling.

### What it means

The sibling latch above fires on the mere presence of a non-online count and cannot fall until the daemon restarts, so once a state has been seen it can never report that state again. This rule reads `increase()` over the same counter instead, so it sees a repeat as a step and says so. The two are deliberately opposite forms and neither is redundant: a non-online series is born at whatever its first scrape catches, with no implicit zero before it, so `increase()` sees a first sighting only where a scrape lands inside the burst — which is precisely what the latch catches unconditionally.

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

**Measured, not estimated**: **0.045%** of the 2026-07-13 event's fleet-dark seconds. **Not** structurally bounded by `min_gap_seconds`: H−1 books a stream's tail only when the *fleet*-dark window there exceeds the threshold, and the fleet tail is bounded above by the stream's own — so a stream quiet from 11:45 while the fleet ticks to 11:59:50 leaves a 10 s fleet tail that is booked nowhere and a straddle far wider than the threshold. What bounds it in practice is the measured silence distribution, which `infra/scripts/gap_distribution.py` re-measures — an argument that degrades correctly when a thin pair joins the universe, where the structural one simply fails.

**This is accepted, not outstanding.** Closing it means reading each pair's H−1 segment on every hour carrying a fleet-dark window — real I/O on every cycle, for a fraction of a percent. The decision and its measurement are recorded in \[[T0103]\].

### What to do

Nothing. Do not "fix" this incidentally while working nearby without re-measuring the share first — the 0.045% figure is what makes it acceptable, and it is the number that would have to change to justify the I/O.

### Retire when

`containing_dark_window` no longer clamps to `hour_start` — i.e. the limitation is closed and this section describes nothing.

______________________________________________________________________

<a name="bogus-timestamp-hour-rotation"></a>

## bogus-timestamp-hour-rotation — KNOWN LIMITATION

### What you are seeing

`zcrypto-capture-hour-finalized-early` or `zcrypto-capture-ts-past-dated-hour` fired, or you are reading `HourOracle` / `_count_if_early` / `_enter_hour` in `cli/capture/segment_writer.py`, or an archive hour is short and you are asking whether the writer closed it before its time.

### What it means

The writer rotates the archive hour from **the event's own exchange timestamp**, a field the venue sends and we parse straight through. An hour is opened, and the previous one finalized, only once **two witnesses** agree time has reached it — each stream's newest plausible stamp (clamped at our clock plus five minutes) plus the wall clock itself, handicapped by five minutes so a leading clock cannot second a bogus stamp on its own. A row for an unconfirmed hour is **held**, never dropped.

**Three residuals survive that, and all three are accepted design limits.** Each closing knob starves a legitimate case; the judgement is unchanged and is the reason this is a limitation section rather than a defect.

| residual | what it takes | what would close it | what that starves | what SEES it |
| -- | -- | -- | -- | -- |
| **(a) two bogus stamps in one closing window** | two streams both taking a guard-passing stamp in the hour's last five minutes, meeting the quorum early; each stamped hour publishes truncated by at most that window | raise the witness quorum above two | a small `--pairs` run, too few streams to reach it | `zcrypto-capture-hour-finalized-early`, with the clock offset |
| **(b) a clock leading over five minutes, plus one bogus stamp** | the handicapped clock witness seconds the stamp; truncation is the lead minus five minutes, unbounded above | require two DISTINCT stream stamps before the clock may second an hour | a lone sparse stream, which would never rotate its hour | **`zcrypto-capture-clock-skew` alone** — see below |
| **past-dated first stamp** | a stamp into a past, unpublished hour arriving as a process's FIRST event; the hour opens and can commit a complete-looking final for a period nothing was captured | refuse a first stamp whose hour is behind our clock's hour | live data whenever our clock is the wrong one — the clock gets **no veto over live data** | `zcrypto-capture-ts-past-dated-hour` |

**Residual (b) is invisible to the early-close counter, and that is arithmetic rather than an oversight.** Earliness is measured against the same clock that is wrong, so a leading clock subtracts its own lead back out of the measurement and a truncated hour can compute as *negative* earliness, counting nothing. No arrangement of that counter can see it. `zcrypto-capture-clock-skew` is therefore not a disambiguator for (b) — it is (b)'s **only** detector, which is why a 10-second offset pages critical on a fleet where nothing has yet been lost. **A silent early-close counter is never a clean bill for the hour boundaries.**

### What to do

**The truncation is permanent by design — do not attempt to repair the hour.** A committed final is never reopened, and the writer cannot know a final was premature. The finals are hash-certified, so hand-writing rows into one breaks the certification and the nightly replay verification will report that hour broken from then on. The rows themselves are unrecoverable in any case: L2 is unbackfillable and the venue serves no history.

**The sanctioned repair is the peer machine, and it is automatic.** A bogus stamp poisons one stream on one machine. If the other capture machine's copy of that hour is whole, the reconciler covers the hour from it and nothing is lost — that path already has its own alerts. Only when **both** machines truncated the same hour on the same pair is the loss real, and then the reconciler books it and `zcrypto-reconcile-residual-gap` pages, about two hours after the hour in question.

**Naming which residual fired** — read the early-close signal against the clock offset, never either alone:

1. **Early closes firing, clock offset healthy** ⇒ residual (a). A bogus stamp truncated one or more streams' hours. Real loss on those streams; go to the peer-machine paragraph above.
2. **Early closes firing, clock BEHIND** ⇒ benign. A clock lagging by less than five minutes closes every genuine boundary that early, on every writer, 24 times a day. Fix the clock; nothing was lost. **The count itself is the tell**: order-100 over six hours means every boundary and every writer, which is the clock; a handful means specific streams, which is a stamp.
3. **Clock skew firing with the clock AHEAD, early closes silent** ⇒ residual (b) may be live and structurally invisible. This is the one case where silence proves nothing. Compare the suspect hours' row counts against the peer machine directly rather than trusting the counter.
4. **Past-dated firing** ⇒ the third residual, independent of the other two. There is no baseline to lean on: a count is not by itself a bad stamp, because a benign restart can also open a past hour that holds no captured parts. Separating the two is its own section below.

**On reading the offset's direction**: `zcrypto_clock_offset_seconds` carries the clock's own error, positive when it is **fast** — running AHEAD of the reference. That is the dangerous direction here: a leading clock is what truncates an hour, and it is invisible to every other signal. Note the sign is the opposite of the kernel's `node_timex` convention, so do not carry an instinct over from it. If you are about to act on the direction, confirm it on the machine (`chronyc tracking`, or `date -u` against a clock you trust).

### Retire when

All three of these hold in `cli/capture/segment_writer.py`, at which point this section describes nothing: the witness quorum is above two, the wall clock can no longer second an hour on its own, and `_enter_hour`'s first-event branch refuses an hour behind our own. Closing one residual does not retire the other two, nor the alert sections below that cover them — retire each with the mechanism it describes. The decision to accept all three, and what each closing knob would starve, is recorded in \[[T0037]\].

______________________________________________________________________

<a name="zcrypto-capture-hour-finalized-early"></a>

## zcrypto-capture-hour-finalized-early — ALERT

### What you are seeing

A **warning** Grafana alert, one instance per capture machine. That machine finalized at least one archive hour before its own clock said the hour was over, at some point in the last six hours.

### What it means

**Two causes, and this signal cannot tell them apart.** Either a bogus exchange timestamp closed an hour early and that stream's remaining rows for it were then refused as late — permanent, unbackfillable loss — or the machine's clock is running behind, which closes every genuine boundary early and costs nothing at all. That ambiguity is deliberate: the clock is not trustworthy enough to be given a veto over live data, so a lagging clock legitimately fires this and cannot be engineered out of it.

**Magnitude is the cheapest discriminator you have.** The counter sums across 24 writers (12 pairs × book and trade), each closing 24 boundaries a day, so a lagging clock produces up to ~576 counts a day per machine — roughly 144 inside this rule's six-hour window. An order-100 reading is the clock. A handful is a stamp.

**It does NOT see the opposite fault.** A clock running *ahead* truncates hours and hides the truncation from this measurement, because the earliness is computed with that same wrong clock and the lead cancels out exactly. `zcrypto-capture-clock-skew` is the only detector for that case. **Reading this rule's silence as coverage of the hour-rotation residuals is being misled** — the limitation section above has the full map.

### What to do

1. **Read `zcrypto-capture-clock-skew` first.** Firing, with the clock behind ⇒ this is benign; fix the time discipline and expect this to clear six hours after the last early close.
2. **Read the count** on the integrity board's hour-rotation panel, and apply the magnitude test above.
3. **Name the streams.** Every early close is logged with its pair, kind, hour and how early it was: `sudo docker logs zcrypto-capture 2>&1 | grep "hour finalized early"` on the machine the page names, or the same line via Loki.
4. **Check the peer machine for the same hour and pair.** One machine truncated ⇒ the fleet still holds the rows and the reconciler covers the hour. Both ⇒ the loss is real and the reconciler will book it; expect `zcrypto-reconcile-residual-gap` about two hours after the hour.
5. **Do not repair the hour by hand** — see the limitation section above for why, and for what the sanctioned path is.
6. **Silencing is rarely warranted.** It self-resolves six hours after the last early close. If you silence it while fixing a clock, time-box it, or a genuine stamp event during the fix reports nothing.

### Retire when

`zcrypto-capture-hour-finalized-early` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-capture-ts-past-dated-hour"></a>

## zcrypto-capture-ts-past-dated-hour — ALERT

### What you are seeing

A **critical** Grafana alert, one instance per capture machine. A stream's **first event after a capture process started** carried a timestamp dated into an hour that had already passed **and that held no captured `.part` files on disk**, and the writer opened that hour. Both halves are the trigger: an hour already holding parts is re-opened without counting anything.

### What it means

The plausibility guard bounds the *future* direction only, so a stamp dated backwards is anomalous but still trusted. It can only act at a process's first event: from then on the open hour is the floor and the late-event guard refuses anything behind it. Acting on a genuinely bogus stamp means opening a past hour and eventually committing a manifest-certified, complete-looking final for a period during which **nothing was actually captured** — and redeeming any quarantined `.held` spill for that hour into it on the way.

**There is no hard-zero baseline, and a step is not by itself a bad stamp.** The venue's own timestamps have been non-decreasing across every production row measured, so a *fabricated* stamp has never been observed — but that is not what the counter counts. It counts a first event that opened a past hour holding no captured parts, and a plain restart can leave exactly that shape behind. The counter steps **at most once per stream per capture process**, so it is a step detector rather than a rate and there is no threshold to tune; what a step tells you is only that the hour that opened held no captured data. The four shapes below are what separate a real event from a benign restart.

**The harm is a fabricated hour, not a missing one.** The bad hour reads as complete and certified, so nothing downstream will question it.

**What a non-zero value means, exactly.** The hour that opened held no **confirmed** capture **on disk at the moment it opened** — no `.part` files. It does not mean nothing was ever captured for that hour, and it is not a claim about the timestamp. A re-open of an hour that already holds `.part` files does not count at all, so the commonest restart shape never reaches you.

**Four shapes do reach you, and this host's disk does not separate them.** Shapes 1, 2 and 4 all leave the hour with no `.part` files — which is exactly why the predicate counts them.

1. **Capture was not running for that hour** — an attended reboot, a host outage. The hour holds no parts, so the first replayed stamp after the restart counts, correctly by the predicate and yet with nothing bogus about the timestamp. On disk: hour 14 finalized, no parts for hour 15, a new writer at 16:15 whose first event is stamped 15:40 → the hour opens, counter **1**.
2. **A non-graceful stop lost the unflushed buffer** — the likeliest first page this rule produces. There is no timed flush (`DEFAULT_FLUSH_ROWS = 5_000`), so a thin stream's whole hour can sit in RAM; SIGTERM reaches `close()`, which writes that buffer out as an ordinary `.part`, but an OOM kill, SIGKILL, kernel panic or power loss does not. The replay then re-opens an hour that has no parts *because the stop lost them*, and that replay is restoring exactly those rows. On disk: hour 14 finalized, two hour-15 rows buffered below `flush_rows`, the writer dropped without `close()`, a new writer at 16:15 replaying the 15:47 print → no parts for 15, counter **1**. The identical case with `close()` reached first leaves `15.part0000.parquet` on disk and counts **0**.
3. **The hour held only a quarantined `.held` spill** — counted on purpose. Those rows were never corroborated, and the hour is about to be certified from rows nothing confirmed. **Its evidence destroys itself**: opening the hour calls `_redeem_held`, which renames the spill into an ordinary `.part`, and the next rotation merges it into a certified `<HH>.parquet`. On disk: `['14.parquet', '15.held0000.parquet']` before the append, `['14.parquet', '15.part0000.parquet']` after it, counter **1**. An operator arriving minutes later finds a full, certified hour and will file a genuine fabrication as a detector fault unless they know this. **The redemption is silent** — `_redeem_held`'s only log line is its `could not redeem` failure path — so afterwards neither the disk nor the log distinguishes a redeemed hour. Two checks survive it: the writer's `first stamp opened a past hour` line (step 2 below), which carries the pair, kind and hour, and the peer machine's copy of that hour (step 3), taken **before anything else touches the tree**. `zcrypto_capture_rows_quarantined_total` on that host corroborates only when the spill happened to be scraped before the stop, which a `close()` spill usually is not.
4. **A genuinely bogus past-dated stamp — the fabrication this alert exists for.** A first event carries a stamp naming an hour this host never captured; the plausibility guard bounds the future direction only and cannot refuse it, and the writer opens that hour. **On this host's disk it is indistinguishable from shapes 1 and 2** — no parts for the hour, no `.held` file, a restart on this machine — so nothing local separates it, and the two shapes it hides behind are the two this entry calls benign. The peer's copy does not finish the job alone either: an hour this host is short while the peer holds it whole is either a single-host outage (shape 1, where the stop, reboot or OOM is on the record) or this one, where **nothing accounts for the gap**. An unaccounted-for gap is filed as this shape, and the whole cost of a wrong call sits on the side that files it benign.

**Discriminating them, because 1, 2 and 4 look identical here.** The peer comparison — step 3 below — is mandatory for **every** page where the hour held no `.held` file, not a tie-breaker between 1 and 2. Read `RestartCount` and `StartedAt` (step 1) and compare the hour against the peer:

- A gap on **both** machines spanning the hour ⇒ an outage backfill, shape 1. Nothing was fabricated, and neither machine holds the hour, so there is nothing to cover it from — the loss is the outage's, and the limitation section above has what happens to a gap both machines share.
- This host short against a whole peer copy, **with** a stop, reboot or crash on this host's record accounting for the gap ⇒ still not a fabrication: shape 1 where capture was simply down for the hour, shape 2 where the stop lost rows the replay has not restored. Which of the two it is does not change what you do — cover the hour from the peer.
- This host's copy of the hour **matching** the peer's, with a restart on this host only ⇒ a crash replay, shape 2; the replay restored what the stop lost. A single-host crash leaves no gap on the peer, so "a gap on both" used as the sole test misfiles this one as a bad stamp.
- This host still short against a peer copy that is whole, with **no** stop, reboot or crash on this host accounting for the gap ⇒ shape 4. The rows never existed here and no replay is bringing them; the presence or absence of that accounting is the whole of what separates this from the two bullets above it.

For shape 3 that comparison is the whole of the disk evidence, since the redemption renamed the rest away.

**The rule is a latch: it reads the value, not a window.** The counter is cumulative over the capture process's life and never falls, so once it is above zero the rule stays firing. Waiting for a six-hour window to roll past clears nothing — that window belongs to `zcrypto-capture-hour-finalized-early`, not to this rule. What clears this one is the capture process restarting, which is a supervised act on the capture pair and never something done to quiet a board; in practice it clears at the next capture re-pin, which replaces the container and restarts the process anyway. A converge that changes neither the image nor the config does not restart it and does not clear it. It also clears if the host stops reporting at all — but that silence pages on its own.

**A second open while the page stands raises no second page.** The rule reads `max by (host)`, so there is one alert instance per host and a counter stepping 1 → 2 moves the measured value without changing a single label: Grafana sees no state transition and sends nothing new. The step surfaces only as the numeral in the `measured …` line of a repeat notification, on a page already filed — and a standing latch is the expected condition rather than a corner. **Record the counter's standing value in the ops-journal entry this page produces, and treat any later value above the recorded one as a NEW event**, worked from step 1 below as if it had paged on its own.

### What to do

1. **Anchor it to a process start**, because that is the only place it can happen: `sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-capture` and `--format '{{.RestartCount}}'` on the machine the page names. A restart you did not expect is itself a finding.
2. **Name the hour and the stream.** The writer logs it: `sudo docker logs zcrypto-capture 2>&1 | grep "first stamp opened a past hour"` — the line carries pair, kind and the hour that was opened. **Read it as narrower than its wording**: the text says only "a past hour", but the writer emits it on exactly the counter's condition — a past hour that held no `.part` files when it opened. A restart re-opening an hour that already held parts logs nothing here, so every line you find is one of the four shapes above, never the wider condition the sentence reads like.
3. **Compare that hour against the peer machine's copy** — row counts and time coverage. This is not optional and it is not a tie-breaker: it is the only thing separating a fabrication from a benign restart, because shapes 1, 2 and 4 leave the same trace on this host. Take it before anything else touches the tree.
4. **Do not hand-edit the final.** Same reasoning as the limitation section above: the tree is hash-certified and a hand edit reports as permanent breakage thereafter.
5. **Record what the hour actually contained before anything else touches it** — the `.held` shape above erases its own evidence within one rotation. Then record the counter's standing value in the ops-journal entry this page produces; a later value above it is a new event, worked from step 1 again. **Treat the response as unrehearsed rather than routine**: the benign shapes are the likelier ones, and a benign step rehearses none of this procedure.

### Retire when

`zcrypto-capture-ts-past-dated-hour` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-capture-clock-skew"></a>

## zcrypto-capture-clock-skew — ALERT

### What you are seeing

A **critical** Grafana alert, one instance per capture machine. That machine's clock is more than 10 seconds from true time, or the machine reports its clock unsynchronised.

### What it means

**Nothing has been lost. This is a precondition, and it is the reason it pages critical.** A clock running ahead lets a bogus exchange timestamp close an archive hour early *and* hides that earliness from every counter measured against the same clock, so `zcrypto-capture-hour-finalized-early` sits silent while the archive is being truncated. When the fault is the clock, only the precondition is observable — and, unusually, it is observable **before** the damage rather than after.

10 seconds is a structural bar, not a fitted one: orders of magnitude above a disciplined clock's steady state, and 30× below the five-minute margin at which the clock witness can start seconding a bogus stamp. So there is room, and the correct posture is prompt rather than frantic.

**chrony is MANAGED, and re-converging it is the repair.** `infra/ansible/roles/chrony` owns the config, and `site.yml` applies it to the capture hosts under `tags: [chrony]`, so a chrony that has stopped, died or been hand-edited is fixed by re-converging that role — **`--tags chrony`** — which re-asserts the config and reports its sources. Check `systemctl is-active chrony` and `chronyc -N sources` first; a stopped daemon, not an unmanaged one, is what lets the clock drift. **The role's `makestep 1.0 3` also means chrony itself MAY STEP — whenever the offset exceeds 1.0 s — on the first three updates after a restart**, which is exactly the precondition residual (b) below warns about.

### What to do

1. **Confirm it on the machine**, not from the metric alone: `timedatectl` on the machine the page names, and `date -u` against a clock you trust.
2. **Establish the direction.** `zcrypto_clock_offset_seconds` is positive when the clock is **fast**, i.e. ahead of the reference — the direction that truncates hours. Direction decides everything below, so confirm it in step 1 rather than reading it off the sign.
3. **Restore the time discipline.** Prefer a slew. A correction that **steps the clock forward** briefly hands the clock witness a lead it did not earn, which is exactly residual (b)'s precondition — so make that correction while you are watching, and read the early-close counter afterwards.
4. **Then look backwards.** Did `zcrypto-capture-hour-finalized-early` fire while the clock was off? If the clock was **ahead**, its silence proves nothing — compare the suspect hours' row counts against the peer machine instead.
5. **Both machines skewed at once** points at something shared — a hypervisor, a network time source, a converge — rather than at one machine.

### Retire when

`zcrypto-capture-clock-skew` is absent from `infra/grafana/alerts.yaml`, or the capture writer no longer takes the wall clock as a witness for opening an hour — at which point a skewed clock stops being able to truncate the archive and this becomes ordinary machine hygiene rather than a data-integrity signal.

**One blind spot is deliberate and lives elsewhere.** A healthy clock produces an empty query, so the rule reads no-data as healthy — which means the two series *vanishing* also reads as healthy. The exporter publishes on EVERY run including the healthy case, and publishes the offset as NaN with the synchronised flag at 0 when chrony cannot be read, which pages. A dead TIMER produces no such silence, and `zcrypto-capture-clock-exporter-stale` is what says so — **while that alert is firing, treat the clock-skew alert as blind**, not as a clean bill.

______________________________________________________________________

<a name="zcrypto-capture-clock-exporter-stale"></a>

## zcrypto-capture-clock-exporter-stale — ALERT

### What you are seeing

The clock reading on a capture host has not refreshed in over 30 minutes. The timer writes every 5 minutes, so this is roughly six missed runs.

### What it means

`zcrypto_clock_offset_seconds` and `zcrypto_clock_synchronised` are frozen at whatever they last held. The textfile collector re-serves the last file forever, so those gauges still look healthy — they are not. **While this is firing, `zcrypto-capture-clock-skew` is blind**, and that alert is the only detector for a leading clock, which silently truncates archive hours.

### What to do

1. `systemctl list-timers zcrypto-clock-offset` on the host — is the timer active and when did it last run?
2. `systemctl status zcrypto-clock-offset.service` for the last run's exit status; the script writes one line to stderr when `chronyc` fails.
3. `chronyc tracking` by hand. If chrony itself is down, the clock is unmanaged and the skew risk is live, not hypothetical.
4. Until the exporter is back, treat any hour-rotation question on that host as unresolvable from metrics alone.

### Retire when

The clock offset is published by something whose liveness is visible without a separate staleness rule.

______________________________________________________________________

<a name="zcrypto-capture-rows-quarantined"></a>

## zcrypto-capture-rows-quarantined — ALERT

### What you are seeing

A **warning** Grafana alert, one instance per capture machine. That machine spilled rows to a `.held` quarantine file in the last six hours. Baseline is zero on both machines, so any nonzero value is a real event.

### What it means

**Rows parked for an archive hour that nothing ever corroborated**, written to a `<HH>.held####.parquet` sidecar instead of into the canonical tree. **It is not the late-arrival path** — a row that genuinely arrives after its hour was finalized is refused by the late-event guard and counted nowhere.

**Holding is normal; spilling is not.** Every genuine boundary holds a few rows while the first stream across waits for a second to corroborate, which is why the held counter beside it discriminates nothing. The spill only happens when the hour is *still* unconfirmed at a flush cap or at shutdown.

**Two real causes**, and they are what to look for: an hour carrying only one live stream, so nothing ever seconds it; or a capture process stopping within five minutes of an hour boundary, before corroboration could arrive.

**Nothing is lost.** Spilled rows are kept and never deleted — the prune's globs exclude them deliberately — and the sweep, the merge, the recovery floor and the archive's tree verification all skip them. They are redeemed into ordinary parts automatically when a live, corroborated stream next opens their hour.

### What to do

1. **Find them**: `sudo find /var/lib/zcrypto-capture -name '*.held*.parquet'` on the machine the page names. The path carries the pair, kind and hour.
2. **Correlate with a restart** — `sudo docker inspect --format '{{.RestartCount}}' zcrypto-capture` and `--format '{{.State.StartedAt}}'`. A stop within five minutes of an hour boundary explains the event completely and needs nothing further.
3. **No restart? Look for a sparse hour on one pair** — a stream that printed once and had no second live stream in its hour.
4. **Do not delete the files and do not fold them in by hand.** Redemption is automatic and hand-merging puts uncorroborated rows into a certified tree, which is the exact thing quarantining them prevents.
5. **Spills that persist across many hours are the design working**, not a stuck queue: that hour genuinely never had a second witness, and keeping its rows out of a certified final is the safe side of an unanswerable question.

### Retire when

`zcrypto-capture-rows-quarantined` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-capture-all-streams-silent"></a>

## zcrypto-capture-all-streams-silent — ALERT

### What you are seeing

A **critical** Grafana alert, one instance per capture host. The *minimum* of `zcrypto_capture_seconds_since_last_book_message` across all 12 pairs on that host crossed 120 s — so not one thin leg went quiet, the whole feed did.

### What it means

**Check the venue's published maintenance calendar before anything else.** Every firing of this rule so far has been a published "Kraken Website and API Maintenance" window, on both hosts at once.

It is nonetheless a **true positive, not noise**. The venue emitted nothing, so no host missed anything that existed, but L2 is unbackfillable and the hours are genuinely short. Expect the reconciler's loss page about two hours later.

Nothing natural comes near this bar: it sits roughly twenty times the fleet-wide natural quiescence this gauge measures outside venue windows, and `infra/scripts/gap_distribution.py` re-derives that envelope from the archive. A restart cannot raise it either — `_run` seeds `last_seen` for every pair before the collector registers, so a fresh process reads ~0.

### What to do

1. **Read the venue calendar first.** `curl -s https://status.kraken.com/api/v2/scheduled-maintenances.json` and look for an entry whose `components` — **or whose `name` (an API, not a ticker)** — carries `WebSocket` or `REST` covering the firing time; an empty `components` array is not an absent impact. The recurring one is "Kraken Website and API Maintenance", roughly biweekly at 07:01–07:16 UTC. A match explains the page completely — go to step 4. **Use that endpoint, not `/scheduled-maintenances/upcoming.json`**, and match on the window rather than on the status: this feed keeps entries after they finish (`status: completed`), so it answers for a page you are triaging an hour or a day late — the upcoming-only variant would return nothing and read as "no window", which is the one way to get this step backwards.
2. **No published window? Now it is a real incident.** Check both daemons: `sudo docker inspect --format '{{.RestartCount}}' zcrypto-capture` and whether parquet is advancing (`sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | head`). A silent-but-synced stream never self-heals, so this will not clear on its own if the daemon is wedged.
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

**If all 12 pairs on both hosts fire at once, this is not 24 stuck streams** — it is the fleet-wide event, and the critical rule above is the one to read. A fleet-wide halt shorter than this rule's 300 s bar never raises it at all, which is the length bound the venue-status section's step 4 describes.

The bar is ~20× the measured natural maximum, and the thinnest pairs really do go quiet. Two instruments bracket that envelope rather than pinning it — this 60 s-sampled gauge, which censors short silences, and the full-resolution archive (`infra/scripts/gap_distribution.py`), which is the binding one — so read a per-pair silence in the tens of seconds as normal, and this bar as nowhere near it.

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

Grafana Cloud intermittently fails to reach its own Prometheus (`dial tcp …: i/o timeout`). Measured over 2026-08-05 → 08-28, those failures produced **264** alert instances from these two rules against **52** genuine ones. Because both rules carry `for: 0s` — load-bearing for their detection arithmetic — a one-minute platform hiccup fired instantly.

The page was not merely noisy, it was **false**: its summary asserts that every book stream on a named host has been silent for minutes, which the system had not observed and could not have observed, since the query never ran. A wrong critical page on the fleet's highest-severity capture signal costs more than a missed one about Grafana's own health.

**A CORRELATED datasource outage does not go unwatched** — that is the case this trades on, and the qualification matters, because a rule-scoped failure is a different story told under *What is NOT covered* below. Siblings in this group still carry `execErrState: Alerting`, so an outage that reaches the datasource is still reported — loudly, by several rules at once. What changed is only that these two no longer contribute a false blackout claim to that storm.

### How to recognise it

**Several `zcrypto-capture-*` rules firing and auto-resolving within about a minute, with no host-side symptom, is a datasource error rather than a fleet event** — and these two rules are deliberately absent from that storm. Only six rules in the `zcrypto-capture` group carry `for: 0s` and can fire on a hiccup that short; the rest absorb it in their pending period. Four of those six still carry `execErrState: Alerting`, so the storm still happens — it just no longer contains a claim that capture went dark.

### What to do

If you suspect the alerting pipeline itself is blind rather than the fleet quiet, check the datasource directly — `uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}'`, which needs the repo checked out and the vaulted token, so it is a workstation step rather than a phone one — and the healthchecks.io dead-man switches, which are an independent failure domain and unaffected by Grafana.

### What is NOT covered, deliberately

A **rule-scoped** evaluation error on these two — an expression broken by a later edit, a permission or cardinality failure on this query alone — now pages nothing, because the four siblings above are correlated cover only. That residual is accepted rather than watched: nothing in the repo detects it today.

### Where the numbers came from

The 264-against-52 measurement is read from Grafana's **alert state history**, not from metrics — `GET /api/v1/rules/history?ruleUID=<uid>&from=<epoch seconds>&to=<epoch seconds>` (milliseconds return an empty page that reads as no data), with the same service-account token `infra/scripts/grafana-query.py` resolves. It is a different store from metric retention, so it answers for windows the metrics cannot. Read it in chunks and compare each chunk's row count against the `limit`: a chunk that returns exactly its limit is truncated, which understates both columns.

### Retire when

Either rule's `execErrState` is no longer `OK`, or a dedicated rule is introduced that owns "the alerting datasource is unreadable" — at which point the other rules' `Alerting` becomes redundant rather than merely loud.
