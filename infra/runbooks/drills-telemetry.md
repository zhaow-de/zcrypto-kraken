# Telemetry-tier drills — induce the fault, measure what fires

Nothing fires these; you open this page deliberately, in an attended window, to break a telemetry path on purpose and prove that the alert or dead-man that watches it actually pages. No money moves. The order-path drills — the ones where it does — live in `drills-order-path.md` and are fitted around [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window).

**Every section below is one drill, and every drill has the same seven parts**: *What this proves* · *Preconditions* · *Induce* · *Must fire* · *Operator action* · *Record* · *Retire when*. Read all seven before touching anything: the *Preconditions* are what keep a drill from becoming an incident, and several of them are the difference between a real reading and a fabricated one.

## Standing rules — these bind every section below

- **The primary's capture daemon and the primary's Alloy are not touched by any drill on this page.** L2 capture is unbackfillable and the primary is the host that also runs the engine. Ops, the secondary and the NAS are the subjects here.
- **Never induce inside a published Kraken maintenance window.** Read `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time **and again immediately before each induction** — the entries that matter carry `WebSocket` or `REST` in `components`, and they appear only 2–6 days ahead.
- **One induction at a time. Revert it and verify the revert BY VALUE before the next one starts.** A drill that leaves the fleet degraded is an incident, not a drill.
- **An instrument is never widened.** Each *Induce* below names exactly what to do — a container stop, a unit stop, a timer stop. Anything heavier (a reboot, a power-off, a firewall rule) is a different act with a different blast radius and is not licensed by the fact that a drill was authorized.
- **A drill that cannot be induced is `blocked`, never `fail`.** `fail` asserts a guard did not fire when nothing exercised it. The four statuses are fixed at `pass`, `fail`, `partial`, `blocked`.
- **Every run gets an entry in `docs/reference/drill-log.md` and lands its findings in the section it ran from.** A result that lives only in a report is not recorded. The entry heading is `## <YYYY-MM-DD> — <scenario id> — <status>` and the body is one paragraph of labelled clauses — `docs/reference/drill-log.md`'s own preamble is the contract and carries two optional ones this line does not repeat, *preconditions* and *collateral*: *host* · *induction* · *time-to-alert* · *channels* · *operator action* · *follow-ups*. Where a Slack path is involved the *time-to-alert* clause carries the rule's `activeAt` and the Slack message. It carries a **device** timestamp where that route's device leg is this drill's to measure; where another drill measures the same route, it names that drill and carries none — two readings of one route measure it once.

## How every bound on this page was derived

A bound is derived or it is not written. Nothing below is an estimate.

- **A Grafana rule's bound is its own `for`, quoted from `infra/grafana/alerts.yaml`, plus its group's evaluation interval.**
- **The rule-state endpoint matches a rule's TITLE, never its uid.** `GET /api/prometheus/grafana/api/v1/rules` exposed no uid field when read on 2026-08-31 — re-read the response shape rather than trusting this line, it is a third party's API and nothing here changes when it moves. The watchdog appeared only as `Fleet · healthchecks.io watchdog (check down, or hc.io dark)`, so a filter written against the uid each drill below names matches nothing and reads as *not firing* — an empty result standing in for an observation. Take the string from that rule's own `title:` in `infra/grafana/alerts.yaml`. The **history** endpoint keys the other way (`/api/v1/rules/history?ruleUID=<uid>`, [`capture.md`](capture.md)), so the two reads key on different fields and neither substitutes for the other. **It is also the only way to recover a transition after the fact** — the live endpoint carries the current state and nothing else, so a `Pending` `activeAt` not read while pending is recoverable only here. **Its `from`/`to` are epoch SECONDS**: milliseconds return HTTP 200 with a well-formed body of three empty frames, which reads as "the rule never transitioned" rather than as a bad query. Validate any empty history against a rule you know transitioned in the same window before recording it as an absence.
- **Match that title WHOLE, never as a substring** — the titles form host-prefixed families, so a substring collapses two rules into one reading. Measured on 2026-08-31 during K: `archive-pull stalled` matches both `NAS · …` and `Ops · …`, `exporter stale` both `Gate · …` and `Reconciler · …`, `Trade backfill` both `· last success stale` and `· non-zero exit code`. The failure is not noise but **misattribution**: a substring watch reports one name flipping between states when it is two rules disagreeing, and it will book **another host's** page as your induction's. Assert each filter matches exactly one rule before trusting a single reading from it, and cross-check the page set against the Slack messages, whose links carry the uid.
- **A firing rule's `activeAt` is when it started FIRING, not when its condition went true** — the same instance reported `activeAt` 07:09:40Z while `Pending` and 07:14:40Z once `Alerting`, exactly its `for: 5m` apart (measured on 2026-08-31 running J′). **Re-arm and instance-replacement are excluded by the Slack timestamp**: a re-armed instance stamped 07:14:40Z would have stayed `Pending` until 07:19:40Z and could not have paged at 07:15:13Z, and the expression is label-free (`max(hc_checks_down_total) or on() vector(999)`), so there is one instance and nothing to relabel. **This is Grafana-managed behaviour** — Prometheus's own `activeAt` is condition-onset and does not move on the transition, so the rule inverts against a native ruler. Reading it off a firing rule and calling it condition-onset understates the operator's real notice by the whole `for`, in the flattering direction. **A drill's time-to-alert is neither reading**: it is page time minus INDUCTION time, so timestamp the induction yourself — no rule carries that moment.
- **Every rule group evaluates at 60 s.** That number is in neither `infra/grafana/alerts.yaml` nor `infra/scripts/grafana-push.sh`, which sets none — it was read from Grafana's provisioning rule-group endpoint (`/api/v1/provisioning/folder/<folder uid>/rule-groups/<group>`, the `interval` field) for all eight groups on 2026-08-31. The folder uid is not in `alerts.yaml` either: every rule there carries the literal `${GRAFANA_ALERT_FOLDER_UID}` and `infra/scripts/grafana-push.sh` substitutes it, so take the value from that script's default. Re-read the interval there rather than trusting this line — it is a setting in the stack, and nothing in this repo changes when it moves.
- **Add ~5 minutes of Prometheus staleness wherever the condition cannot go true until the series goes stale** — the `count(up{…}) or on() vector(0)` silence shape every `zcrypto-alloy-dark-*` rule carries, and every instant rule that pages by `noDataState: Alerting`. Without that term the Alloy-dark bound understates the real notice by a third, which is why those rules' own comment in `alerts.yaml` puts the effective notice at ~15 min against a `for: 10m`.
- **A dead-man whose fire path is an unlabelled `or on() vector(0)` sends NO resolved notice.** Measured by drill N on `zcrypto-nas-archive-pull-stalled`: it went `Alerting` then `Normal (MissingSeries)`, and Grafana deletes such an instance rather than resolving it. The fire path is the unlabelled fallback while the healthy path is a labelled `sum by (…)`, so on recovery the firing instance does not return to normal — it ceases to exist. **Read the rule state to confirm a clear; a quiet channel does not distinguish resolved from still-firing.** `alerts.yaml` records the same self-resolution on `zcrypto-reconcile-residual-gap` after a real loss.
- **A third party's own timestamp beats a local poll for the same event.** Drill R first recorded its page from a 60 s watcher's first observation; healthchecks.io's notice was 30 s earlier, and a notification cannot precede its own detection. Take the page time and the downtime from the service that owns the check, and use the local poll as corroboration.
- **A stopped daemon is invisible to the silence rules — the dead-man is its only detector.** Measured by drill R: `zcrypto-capture-all-streams-silent` scopes both capture hosts with `for: 0s` and an evaluator of `gt 120`, and it returned nothing across 20 minutes of a stopped secondary. A stopped daemon does not publish a large value; it stops publishing, the series vanishes, and `noDataState: OK` reads that as healthy. The two detectors cover opposite failures — a running daemon gone quiet, and a daemon that is gone — so neither's silence says anything about the other's case.
- **A healthchecks.io dead-man's bound is that check's own `timeout` + `grace`**, from the management API's checks listing under the read-only key (`healthchecks_readonly_api_key`, `group_vars/all/vault.yml`). The values quoted below were read on 2026-08-31; **re-quote them immediately before a run** — they are settings on a third party's dashboard and this page does not change when one does. **The listing takes a check NAME**: `capture`, `capture-redundant`, `ops`, `nas`, `engine` are node **tags** and resolve to nothing there, and a lookup that returns nothing is never repaired by reaching for the adjacent check. [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) carries the tag-to-daemon map.
- **A `/fail` ping carries no timeout + grace term at all** — healthchecks.io moves the check down on receipt, so what is measured on that route is notification latency alone.
- **`zcrypto-hcio-watchdog` trails every dead-man on this page by ~7 min**, and it is in the *Must fire* of every drill that puts a check down: the ops Alloy scrapes healthchecks.io every 60 s (`prometheus.scrape "healthchecks"`, `infra/ansible/roles/ops/files/config.alloy`), then `for: 5m` plus the 60 s group interval. It is a **fleet-wide** aggregate — `max(hc_checks_down_total) or on() vector(999)` — so it is already firing whenever any check anywhere is down, and an `activeAt` read off it is an unrelated event's time unless it postdates your induction. **That test alone is NOT sufficient, given the firing-onset rule above**: a check that went down up to 60 s before your induction — after the last scrape your precondition read — puts the watchdog `Pending` before you induced and `Alerting` a full `for` later, so its `activeAt` postdates your induction, passes this test, and is still not your page. **The green read cannot be what closes it** — the confound lands after the scrape that read served, so that read is blind to it by construction; it narrows the window and no more. **What closes it is the `Pending` `activeAt`, read BEFORE the rule fires**: in the `Pending` state `activeAt` is condition-onset, so a value postdating your induction proves no earlier scrape saw a check already down. Read it once while the rule is still `Pending`: the live endpoint carries only the current state, so once it fires that value is gone from **that** read — recoverable afterwards only from the history endpoint above, which is how drill K recovered its own. **No before-the-fact read substitutes for it**: two green reads one scrape interval apart are each served by a scrape up to 60 s stale, so a check going down between the second read's scrape and your induction is invisible to both and still stamps a Pending `activeAt` that postdates the induction. The exposed window is not 60 s but (induction − precondition read) + one scrape interval — about 100 s on J′'s own cadence.

<a name="drill-c"></a>

## Drill C — the ingest plane goes dark — PROCEDURE

### What this proves

What a restarted shipper recovers **per plane**, and which rules misfire on the way back. Logs and metrics behave differently and the difference is the whole point: Alloy's journal reader replays the outage from its positions file under a `max_age = 48h` ceiling, while nothing scraped means the metrics window is simply **absent** — no backfill exists for it.

**A stopped shipper is not a dark destination.** Under a Grafana Cloud outage the two planes invert: `prometheus.remote_write` buffers to its WAL and replays, `loki.write` has no WAL and drops. So this drill measures one half of the permanent-loss statement [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark) needs and derives nothing about the other.

### Preconditions

- An attended window, the standing rules above satisfied, and the Kraken maintenance feed read immediately before.
- **Ops and the secondary only.** Never the primary's Alloy this round.
- The previous induction reverted and verified by value.
- **`max(hc_checks_down_total) == 0`, read by value immediately before** — `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number on the ops half and with *must stay quiet* on the secondary half, and it is a fleet-wide aggregate: a check left down by an earlier drill has it already firing, which turns the ops reading into an unrelated event's `activeAt` and the secondary assertion into one nothing can satisfy. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.
- Budget two holds of **2 h each**, one per host, sequentially. The hold is the backfill horizon this drill exists to measure; a short hold measures the bound instead, which is drill K.

### Induce

On ops (`ssh hp`), then separately on the secondary (`ssh red`):

```
sudo docker stop grafana-alloy
```

**Not `docker network disconnect`.** Both Alloy containers are `network_mode: host` (`infra/ansible/roles/ops/templates/alloy-compose.yaml.j2`, `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2`), and Docker refuses to disconnect a container from the host network. **An egress rule is not the substitute**: it is a firewall change rather than a container start–stop, and inside the shared host netns it cannot be scoped to Alloy alone.

The stop reaches nothing else. Each Alloy is its own compose project and its own container; the capture daemon and the liquidations poller are separate, bridge-networked ones. On the secondary that is the whole assurance — **the capture daemon keeps running**, its dead-man keeps pinging, and its direct-shipped logs keep flowing; what goes dark is that host's `up` and node metrics.

### Must fire

**Ops half — six pages, not two.** An entry that names only two books a six-page blackout as a two-page one, and teaches the next responder to discount the rest.

- `zcrypto-alloy-dark-ops` (critical, `metrics`) — `for: 10m` + 60 s + ~5 min staleness ≈ **16 min**.
- `zcrypto-hcio-watchdog` (critical, `metrics`) — **ahead of it, at ≈11 min**: the ops Alloy *is* the healthchecks.io scrape, so `hc_checks_down_total` goes stale with it and the rule's `or on() vector(999)` fallback trips at ~5 min staleness + `for: 5m` + 60 s. This is the one route where the watchdog leads rather than trails.
- Four instant rules page by **NoData** at ≈11 min each (~5 min staleness + `for: 5m` + 60 s), because every series only the ops Alloy carries goes stale with it and each carries `noDataState: Alerting`: [`zcrypto-ops-archive-pull-stalled`](ops-node.md#zcrypto-ops-archive-pull-stalled) (critical), [`zcrypto-reconcile-exporter-stale`](ops.md#zcrypto-reconcile-exporter-stale) (critical), [`zcrypto-trade-backfill-stale`](ops-node.md#zcrypto-trade-backfill-stale) (critical) and [`zcrypto-ops-verified-replay-stale`](ops-node.md#zcrypto-ops-verified-replay-stale) (warning). They are self-attributing: `zcrypto-alloy-dark-ops` fires in the same window and names the cause.
- **Not** the Grafana watchdog check. It `curl`s Grafana from the host, not through Alloy, and keeps pinging success throughout.
- The ops Loki rules stay quiet — their `[6h]`/`[26h]` windows still hold hours of prior lines.

**Secondary half — two pages, not one**, for the same reason the ops half spells out: an unnamed page mid-hold reads as a real fault. `zcrypto-alloy-dark-capture-secondary` (critical, `metrics`) at ≈16 min, and **`zcrypto-capture-textfile-missing` (critical, `metrics`) about 10 min behind it** — `count(node_reboot_required{host=~"zcrypto|zcrypto-red"})` with evaluator `lt 2` and `for: 20m`, so it is a **value** page rather than a NoData one and fires whenever EITHER capture host stops publishing. Read its summary carefully before reacting: it names the attended-reboot net on **both** hosts, so on a secondary-only induction it is easily misread as a primary-side fault on the unbackfillable host. `zcrypto-alloy-dark-capture-secondary` (critical, `metrics`) at the same ≈16 min. `zcrypto-hcio-watchdog` must stay **quiet** here — no check is fed by that host's Alloy.

### Operator action

None during the hold; that is the drill. At the end of each hold:

```
sudo docker start grafana-alloy
```

Then read the recovery by value — `sudo docker ps --format '{{.Names}} {{.Status}}'` and `sudo docker logs grafana-alloy --since 15m` — and confirm the pages resolve before starting the next induction.

### Record

**What the secondary half established, and it bounds the ops half:** "a stopped shipper loses metrics and recovers logs" holds only where something **writes to the journal during the outage**. Ops has timer units doing that and replayed its window in full; the secondary has none — its capture daemon direct-ships, and **nothing wrote to the SHIPPED journal** during the hold — the relabel keeps three `zcrypto-*` units besides Alloy's own container, and all three were silent across this window (the prunes run at 03:17; reboot-check emits no stdout). A hold spanning 03:17, or a unit that becomes chatty, would change that and the measurement with it — and replayed nothing. Recovery is a property of the host's workload, not of Alloy. **Count in-window lines by WHERE THEY FALL, never in bulk**: a bulk count here returns more lines than the preceding window and none of them are replay. **And `msg="Done replaying WAL"` on restart is not evidence of backfill** — the remote_write WAL buffers scraped-but-unsent samples, so a stopped Alloy has none to replay; that message attests to a dark destination, never to a stopped shipper.

**Checking for misfires on return — the window must outlive every candidate's `for`, or its zeros are guaranteed by construction.** A control proving the query saw the window is NOT a control proving the window outlived the rules: a `for: 15m` rule queried over a 10 min window after the restore cannot have fired yet, and its silence measures nothing. Enumerate the candidates from their expressions — `changes()`, `delta()`, `increase()`, `resets()` — take each one's `for` from `infra/grafana/alerts.yaml`, and end the window past the longest you intend to claim. Three candidates carry `for: 30m` and one `for: 27h`, which no drill hold can outlive: **name them as unverified rather than counting them clean.**

**What the ops half established:** the two planes recover asymmetrically — the journal replays under `max_age`, while nothing scraped leaves no buffer at all, so a metrics dashboard read across an Alloy outage shows a hole rather than a healthy flat line. **Derive expected log volume from the units' own `OnCalendar`, not by counting a neighbouring window** — a neighbour is only a control if it was undisturbed, and on a day of back-to-back drills it rarely is. `zcrypto-fleet-daemon-restarted` is tripped by a SHORT hold and not a long one: past `[15m]` its window holds only the post-restore sample, so `changes()` counts none.

Two entries, `C-ops` and `C-secondary`. Beyond the standard clauses each carries: what the restarted shipper recovered **per plane** (journal replay against the `max_age = 48h` ceiling; the metrics window absent), and which rules misfired on return — `delta()`/`increase()` reads are blind to a condition already present in a series' first sample after a gap, and a first-sample rule can page spuriously on the way back.

The measured half — what a **restarted shipper** replays — belongs in [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark), labelled *measured*, beside the Cloud-dark half derived from `config.alloy` and labelled *derived*. Land it there in the same sitting.

### Retire when

`zcrypto-alloy-dark-ops` and `zcrypto-alloy-dark-capture-secondary` are both absent from `infra/grafana/alerts.yaml`.

<a name="drill-c-prime"></a>

## Drill C′ — Grafana Cloud dark — PROCEDURE

### What this proves

The page time on each of the **two** routes by which the ops-side Grafana watchdog can fail, and the "you are here" a responder needs while the whole Grafana half of the stack is unreadable. The dead-man domain is a deliberately separate failure domain from Grafana Cloud; this drill is what proves it still answers when the other one is gone.

### Preconditions

- An attended window; standing rules above.
- **The `/fail` route restores only by a second converge.** A converge is a human step outside the routine window, so that route is written here and run when a converge window is open. The staleness route needs no converge and can run in any attended window.
- `zcrypto-grafana-watchdog` read green by value immediately before — `uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-grafana-watchdog"}' 'hc_checks_down_total'`. Green means **`hc_check_up == 1` and `max(hc_checks_down_total) == 0`**, both read as values: a check already down produces no up→down transition and therefore no notification at all, and the run would book `fail` against a route that works, while the fleet aggregate NARROWS — but does not close — the chance that the page this drill later times belongs to a check already down elsewhere. **What dates the page to this run is the watchdog's `Pending` `activeAt`** (standing rules above), read while the rule is still pending and shown to postdate the induction; that reading is destroyed when it fires. **Not green ⇒ the drill is recorded `blocked` with the reason** — never `pass`, and never `fail`, which would assert a route failed that was never exercised.

### Induce

**Route 1, staleness** — on ops (`ssh hp`), stop the pinger and let its check go stale:

```
sudo systemctl stop zcrypto-grafana-watchdog.timer
```

**Route 2, `/fail`** — a converge that overrides the probe url with an unreachable one, so the probe fails and `infra/ansible/roles/ops/templates/grafana-watchdog.sh.j2` pings `<url>/fail` instead of the success url:

```
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops \
  -e ops_grafana_watchdog_probe_url=https://grafana-watchdog-drill.invalid/api/health
```

**The revert is the same command without the `-e`** — the role default (`infra/ansible/roles/ops/defaults/main.yml`) restores the real probe url. Write that second invocation down before running the first. `converge.sh` requires `--limit`, shows a `--check --diff` preview and takes a typed confirm of the limit value; **never wrap it in `timeout`**, which kills the wrapper while its child keeps converging.

**The preview cannot show you the url you are setting.** The task that renders the runner script carries `no_log: true` and `diff: false` (`infra/ansible/roles/ops/tasks/main.yml`), because the real probe url is a credential-adjacent value — so `--check --diff` reports that task **changed** and nothing more, on the override pass and on the revert alike. Check the `-e` you typed against this page before confirming; the preview will not catch a typo in it, and a typo lands a *different* unreachable url, which still induces the drill but is not what the entry says was set.

### Must fire

- **Route 1**: the `zcrypto-grafana-watchdog` check pages natively at its own `timeout` 600 s + `grace` 600 s = **20 min from its last ping**. The timer probes every 5 min, so the page lands 15–20 min after the stop, not 20 min after it. Then `zcrypto-hcio-watchdog` at ≈7 min behind the check.
- **Route 2**: the same check pages natively **on receipt** — a `/fail` is an immediate down transition, so there is no timeout + grace term and what you are timing is notification latency. Then `zcrypto-hcio-watchdog`, again ≈7 min behind.

Both routes reach the phone through healthchecks.io's own Slack integration, which no Grafana notification template touches.

### Operator action

Route 1: `sudo systemctl start zcrypto-grafana-watchdog.timer`, then confirm the next probe pings and the check reads green by value. Route 2: the reverting converge, then the same green read.

### Record

One entry per route — `C′-staleness` and `C′` for the `/fail` route — each with its own page bound, because the two numbers are what an operator uses to tell "the pinger died" from "Grafana died" while looking at neither.

The page bound belongs in [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark), which is the procedure a responder opens for the duration of an outage: for the duration you have the dead-man domain, the daily pass's direct healthchecks read, `docker logs` on the hosts, and `exec-status` on the engine host.

### Retire when

The `zcrypto-grafana-watchdog` check is absent from the healthchecks.io checks listing, or `grafana-watchdog.timer.j2` is absent from `infra/ansible/roles/ops/templates/`.

<a name="drill-i"></a>

## Drill I — disk watermark breach to page, end to end — PROCEDURE

### What this proves

The breach → withheld ping → page path, whole, on real code — **on the ops node and on no capture host**. The gauge and the fix are deployed and unit-tested; what has never been induced is the ping actually being withheld and a check actually paging because of it.

### Preconditions

- An attended window; standing rules above. Nothing on a capture host is touched.
- **A green control runs first.** Start the throwaway container on a normally-sized data dir and see its throwaway check go **green**. Without it the drill is degenerate: a container that never reached the venue's WS (wrong pairs, missing config, no egress), or one whose disk probe raised and left `watermark.measurable` False, withholds the ping identically — and a check that only ever breached cannot tell any of them apart.
- **Then `max(hc_checks_down_total) == 0`, read by value immediately before the breaching container starts** — `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. This read comes after the control, not before it, so that "immediately before" has nothing between it and the induction. `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number, and it is a fleet-wide aggregate already firing whenever any check anywhere is down, so a page that predates the induction is booked as this drill's measurement. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

### Induce

A throwaway capture container on ops from the capture-image digest in `docs/reference/fleet-pins.md`, with a **tmpfs data dir a few hundred MiB wide**, pointed at a throwaway healthchecks.io check.

- **The tmpfs width IS the induction; nothing has to be filled.** `DEFAULT_MIN_FREE_BYTES` is 1 GiB (`cli/capture/gap_monitor.py`), so a few-hundred-MiB filesystem is under the watermark from the moment it mounts.
- **The gate is the `not watermark.breached` conjunct in `_healthcheck_loop`** (`cli/capture/command.py`), not `GapMonitor.is_healthy()`, which reads open gaps only and stays True right through a breach. Diagnosing a ping that did *not* stop by hunting for an open gap finds none and concludes the dead-man path is broken — the one wrong answer available here.
- **The throwaway check is created with its Slack integration named explicitly.** A check created through the management API inherits **no** integrations, and an unchannelled one breaches in silence — which would be recorded as a failure of the dead-man domain that never happened. Creating a check needs the full admin key (`healthchecks_api_key`, `group_vars/capture_host/vault.yml`), not the read-only one; resolve it in-process through the vault resolver and place it in a request header, never in argv where `ps` shows it. The integration's own identifier comes from the same API's channels listing under that same admin key — never guessed, and never under the read-only key, whose failure here reads as a missing integration rather than as the wrong credential.
- **`timeout` and `grace` are set explicitly at creation: 120 s each.** For a check the drill mints, the drill chooses the bound. Derived from what is being watched — the capture daemon pings every 60 s (`HEALTHCHECK_INTERVAL_SECONDS`, `cli/capture/command.py`) — so `timeout: 120` clears one jittered ping without paging during the green control, and `grace: 120` puts the page within four minutes of the withheld one. Left unset the wait is whatever the API's defaults happen to be, and the drill holds a throwaway container on the ops node for however long that is.
- **The check's `desc` carries `Runbook: infra/runbooks/drills-telemetry.md#drill-i`.** The daily pass reports every live check whose description carries no resolving citation, and this one is live across a whole sitting.
- The container's `HEALTHCHECK_URL` env var — what the capture role renders from `capture_healthcheck_url` — is what points it at the throwaway check. Left pointing anywhere else, the drill withholds a **production** dead-man.

### Must fire

- The throwaway check pages natively at **its own 120 s + 120 s ≈ 4 min** after the ping is withheld. That is this drill's chosen bound and is **not** the production capture check's notice time, which is 600 s + 600 s — say which one the entry quotes.
- `zcrypto-hcio-watchdog` (critical, `metrics`) fires with it, ≈7 min behind: the minted check going down puts `hc_checks_down_total` above 0 exactly as a production one would. Two pages, not one.

### Operator action

**The by-value read is `sudo docker logs <the throwaway container> --since 10m`** — the `disk watermark breached path=… free=… min_free_bytes=…` ERROR line from `cli/capture/gap_monitor.py`. Ops runs no `capture_app` scrape job and its Alloy keep-regex admits no `zcrypto_capture_*` series, so **no capture gauge is readable from Grafana on that host at all**.

Then delete the throwaway check through the management API and remove the container and its tmpfs. Both go in the same sitting — the only safe stopping point is the boundary between drills.

### Record

**Established here:** the watermark ERROR is logged **once**, not once per probe — the gap opens and stays open, so a single hit is not a stalled probe. And `zcrypto-hcio-watchdog` reads **1** on this induction where drill K drives it to **999**: K takes out the hc.io scrape itself, this one only puts a check down.

Entry `I`. The *time-to-alert* clause records this check's own timeout + grace and **says which check it quotes**. The *channels* clause names both pages — the native one and the watchdog — or a two-page induction is booked as one.

The healthchecks-native path of drill Q is read here; see [`drills-telemetry.md#drill-q`](drills-telemetry.md#drill-q).

### Retire when

`DEFAULT_MIN_FREE_BYTES` is absent from `cli/capture/gap_monitor.py`, or the `not watermark.breached` conjunct is absent from `_healthcheck_loop` in `cli/capture/command.py` — at which point a breach no longer withholds the ping and there is no path to exercise. The alert side of the same signal is [`capture-daemon.md#zcrypto-capture-watermark-breached`](capture-daemon.md#zcrypto-capture-watermark-breached).

<a name="drill-j-prime"></a>

## Drill J′ — the `/fail` route on a dead-man — PROCEDURE

### What this proves

That an explicit `/fail` ping leaves a process and reaches **Slack** on both routes. The device leg is drill Q's path 3, which is measured at drill I on this same route, and is not proven here. The engine's own call is unit-tested; what had never been observed end to end until 2026-08-31 is the **routing** — the ping leaving a process, healthchecks.io transitioning the check, and Slack showing it. It has now been run once (see the entry in `docs/reference/drill-log.md`); the device half of the route is still unobserved. This drill proves the route, not the caller, and the entry says so.

### Preconditions

**Both read by value immediately before the induction**, and each narrows a different confound. A third read — the watchdog's `Pending` `activeAt` — is taken *after* the induction and is what actually dates the page to this run; it is timed by the rule's own state, not by this list:

- `hc_check_up{name="zcrypto-engine-shadow"} == 1` — healthchecks.io notifies on the up→down **transition** only, so a check already down produces no message and the run would book `fail` against a routing path that works.
- `max(hc_checks_down_total) == 0` — `zcrypto-hcio-watchdog` is a fleet-wide aggregate already firing whenever any check anywhere is down, so an `activeAt` read off an instance that predates the induction is an unrelated event's time. **Postdating your induction is not sufficient on its own** (standing rules above): also read the watchdog's `activeAt` while it is still `Pending`, where the value is condition-onset, and confirm THAT postdates the induction, written into the log as a page bound a responder will later trust.

```
uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-engine-shadow"}' 'hc_checks_down_total'
```

Not green ⇒ the drill is **`blocked`** with the reason — never `pass`, never `fail`.

The engine is **disarmed** for the window.

### Induce

Read `engine_healthcheck_url` from `group_vars/engine_host/vault.yml` through the vault resolver **on the workstation**, and issue the `<url>/fail` GET **from that same Python process**.

- **Never issue that GET with `curl`.** The URL *is* the ping secret and `ps` shows argv.
- **Never from the engine host.** Its only copies sit beside the live trade key, in `engine.env` and the container environment.

### Must fire

- `zcrypto-engine-shadow` pages natively **on receipt** — a `/fail` is an immediate down transition, so no timeout + grace term applies. For contrast, the same check going *silent* would take `timeout` 14400 s + `grace` 2100 s = **4 h 35 m**; the two numbers answer different questions and the entry says which route it timed.
- `zcrypto-hcio-watchdog` (critical, `metrics`) ≈7 min behind.

### Operator action

A success ping to the same url, from the same process, to clear the check. Then read it green by value with the same query as the precondition — the induction is not reverted until the check is measured up again.

### Record

**Established here:** the `/fail` route reaches Slack on both paths, and `Engine · cycles have stopped` is untouched by it — that rule reads an engine-side gauge on a 4 h 35 m bar, which no healthchecks.io ping can move, so its silence during this drill discriminates nothing and must not be recorded as evidence of route separation.

Entry `J′`. It records the two green precondition readings taken **before** the induction — necessary, but **not** what makes the timestamps this run's: that is the watchdog's `Pending` `activeAt`, read while the rule is still pending and shown to postdate the induction (standing rules above). It records the two machine timestamps (`zcrypto-hcio-watchdog`'s rule `activeAt`, and the Slack message). It does **not** carry a device timestamp and does not mark one owed: this route's device leg is drill Q's path 3, which rides drill I's throwaway check into the same channel, so a reading here would duplicate I's rather than add one.

### Retire when

`_ping_healthcheck` in `cli/engine/cycle.py` no longer appends `/fail`, or `engine_healthcheck_url` is absent from `group_vars/engine_host/vault.yml`. The alert that reads the same check's silence is [`engine.md#zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale).

<a name="drill-k"></a>

## Drill K — Alloy kill, timed — PROCEDURE

### What this proves

The Alloy-dark bound, measured rather than computed, and the restart recipe verified by value. Same instrument as drill C, short hold: C measures what a 2 h outage costs, K measures how fast anyone finds out.

### Preconditions

An attended window; standing rules above. **Ops only.** Nothing else induced at the same time — the metrics path of drill Q is read off this induction and needs the page set to be attributable.

**`max(hc_checks_down_total) == 0`, read by value immediately before**:

```
uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'
```

This one bites in practice rather than in theory: drill I mints a throwaway check and drill O puts `zcrypto-panel` down, so running K later in the same sitting with either still down has `zcrypto-hcio-watchdog` **already firing** — and its ≈11 min here is the number K exists to measure. An `activeAt` that predates the stop is an unrelated event's time. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

### Induce

On ops (`ssh hp`):

```
sudo docker stop grafana-alloy
```

### Must fire

The same six pages drill C's ops half lists, on the same clocks — `zcrypto-hcio-watchdog` at ≈11 min, `zcrypto-alloy-dark-ops` at ≈16 min, and the four NoData rules at ≈11 min. Each trips inside K's shorter hold, which is why K is the induction that times them.

### Operator action

**Hold to `zcrypto-alloy-dark-ops`'s own ≈16 min, never to the earlier watchdog page.** Below roughly 13 minutes the restore itself trips [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) (warning, `metrics`): it reads `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, and the ops Alloy is one of its `integrations/self` targets, so a restore landing while the pre-stop sample is still inside that 15 min window counts the return as a restart. Waiting `zcrypto-alloy-dark-ops` out clears the window. A restore that lands inside it anyway is **named in the entry, never chased**.

**Read drill Q's metrics path here, while the alert is still firing.** Every induction is reverted before the next starts, so a reading deferred past the restore has nothing left to read and costs a second, unplanned Alloy stop.

Then restore with the recipe from [`observability.md#zcrypto-alloy-dark-ops`](observability.md#zcrypto-alloy-dark-ops), which works on a stopped container:

```
sudo docker restart grafana-alloy
```

Not `sudo docker start grafana-alloy`: it restores the container but exercises no recipe, and verifying the recipe by value is half of what this drill is for. Read the recovery back by value — `sudo docker ps --format '{{.Names}} {{.Status}}'`, then the four NoData rules resolving.

### Record

**Established here:** the derived bounds hold, and three of the six rules — `zcrypto-ops-archive-pull-stalled`, `zcrypto-ops-verified-replay-stale` and `zcrypto-alloy-dark-ops` — clear theirs by under one evaluation interval; treat those three as tight rather than proven roomy. **Slack delivery is not part of any of these bounds**: fold it in and those same three sit outside bounds they are comfortably inside. The margin is exactly `60 s − scrape residue`, so the whole spread is one group interval and a rule whose residue reached 60 s would fire at its bound. `zcrypto-hcio-watchdog` reads **999** here, its hc.io-dark branch, because the ops Alloy IS that scrape.

Entry `K`, with every page in the set and its measured time against the derived bound. Drill Q's metrics-path `activeAt` is quoted from `zcrypto-alloy-dark-ops` — the page this induction is for — and lands in this entry, not in one of its own.

### Retire when

`zcrypto-alloy-dark-ops` is absent from `infra/grafana/alerts.yaml`.

<a name="drill-o"></a>

## Drill O — timer death — PROCEDURE

### What this proves

Whether a systemd timer with **no Grafana staleness rule** is caught by its healthchecks.io dead-man alone — and, if it is not, that a rule is owed. The panel-materialize timer is specifically the one with no staleness rule ([`ops-node.md#zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) records the gap); any other ops timer measures a different thing.

### Preconditions

**Both read by value immediately before the stop**, for the same two reasons drill J′ reads its pair:

```
uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-panel"}' 'hc_checks_down_total'
```

`hc_check_up{name="zcrypto-panel"} == 1` with its last ping inside one timer period, **and** `max(hc_checks_down_total) == 0`. An unset or paused check has been down independently of this drill and its page predates it, and a native healthchecks.io page carries no rule `activeAt` to separate the two afterwards; the aggregate is the second half because the only rule `activeAt` this drill produces is the watchdog's.

**Not green is diagnosed, never guessed at.** Whether the url is configured at all is a repo read: ask the vault resolver for **`panel_healthcheck_url`** in `host_vars/zcrypto-ops/vault.yml`. **Do not ask it for `ops_panel_healthcheck_url`** — that is the plain, unvaulted indirection the role template reads (`host_vars/zcrypto-ops/vars.yml`, over an empty role default), the resolver is a dict lookup, and the name raises `KeyError`, which reads exactly like "the variable is not defined" when it is. Whether the live host is *pinging* it is what the green read answers.

Not green ⇒ **`blocked`** with the reason, never `pass`. A `pass` here would close a recorded gap on evidence that predates the induction, after which a panel timer that stops firing trips nothing at all.

### Induce

On ops (`ssh hp`):

```
sudo systemctl stop zcrypto-panel-materialize.timer
```

Confirm the stop landed, by value: `sudo systemctl is-active zcrypto-panel-materialize.timer` prints `inactive`. **Read the word, never `$?`.**

### Must fire

- The `zcrypto-panel` check pages natively at `timeout` 7200 s + `grace` 3600 s = **3 h from its last clean ping**, so up to 3 h after the stop.
- `zcrypto-hcio-watchdog` (critical, `metrics`) ≈7 min behind it. Here it **trails** the native page rather than leading it, unlike drill K's. An unnamed critical mid-hold reads as a real fault and stops the chain on a healthy induction, so it belongs in this list.
- **No Grafana rule reads `ops_panel_last_success_timestamp`.** That is the finding this drill is testing for, not an omission from this list.

### Operator action

**A dead-man that does NOT page is this drill's finding, not a failed induction, and is recorded `fail`.** Re-running to obtain a page destroys the answer. It is `fail` rather than `blocked` only once the stop is confirmed inactive by value above; an induction that did not land is `blocked`.

On `fail`, the entry's *follow-ups* clause names the owed staleness rule on `ops_panel_last_success_timestamp` and it is registered where work is registered — **a rule found owed is a change to `infra/grafana/alerts.yaml`, never a closure written into a runbook.**

Restore either way:

```
sudo systemctl start zcrypto-panel-materialize.timer
```

Then confirm the next ping lands and the check reads green by value.

### Record

**Established here:** the dead-man alone does catch this timer's death, so **no staleness rule is owed** — `ops-node.md`'s paragraph is re-tensed to say so, and records the cost the gap carries. **Anchor the bound on the check's `last_ping`, never the timer's `LastTriggerUSec`**: the unit pings on completion, so the trigger predicts the page early. **Restoring an `OnCalendar` timer fires a run immediately, and `Persistent=` does not predict it** — drill O's timer carries `Persistent=true` and drill C′'s carries `Persistent=no`, and both triggered on `systemctl start` with a ping seconds later. Whatever the mechanism, the operational rule is the same for either: `LastTriggerUSec` after a restore is never evidence of a healthy schedule, and the returning ping is.

Entry `O`, with the measured time-to-page against the 3 h bound, or the non-page recorded as the finding. Either outcome — `pass` or `fail`, and never `blocked` — re-tenses the no-staleness-rule paragraph in [`ops-node.md#zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) in the same change: it is written in the future tense about this run. On `blocked` the induction never landed, that future tense is still true, and re-tensing it would record an answer nobody obtained.

### Retire when

A rule in `infra/grafana/alerts.yaml` reads `ops_panel_last_success_timestamp` — at which point the dead-man is no longer the only catcher and this question is answered — or the `zcrypto-panel` check is absent from the healthchecks.io checks listing.

<a name="drill-p-plus-r"></a>

## Drill P+R — the secondary goes away — PROCEDURE

### What this proves

That the **one log class no Alloy pipeline sees** is caught, and in how long: a compose service that is never created writes nothing anywhere, so its liveness rests entirely on a dead-man. R is the unit stopped; P is the unit looping because the container cannot be created. And that **the primary stays whole** across the window.

### Preconditions

**Read all four of these immediately before the stop.** Each is a point-in-time read, the loss they guard against is permanent, and nothing in a before-and-after pair can see the primary going silent *between* them — so **the first three, which are the four primary-whole signals, are re-read on a 60 s cadence through the whole hold**. The fourth is an attribution read, taken once.

- `up{job="capture_app",host="zcrypto"}` reads **1**.
- `min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})` reads **under 120 s**, the threshold `zcrypto-capture-all-streams-silent` itself carries.
- Every primary instance of `zcrypto-capture-all-streams-silent` and of `zcrypto-capture-stream-silent` is **Normal**.
- `max(hc_checks_down_total)` reads **0** — the attribution read, and the only one here that says nothing about the primary: `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number, and as a fleet-wide aggregate it is already firing if an earlier drill left a check down. Not 0 ⇒ clear the down check first, or record **`blocked`**. It is not on the cadence and never aborts a hold under way.

**The pre-read, once, before the stop** — all three by-value queries:

```
uv run python infra/scripts/grafana-query.py 'up{job="capture_app",host="zcrypto"}' 'min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})' 'hc_checks_down_total'
```

**The cadence, every 60 s from the stop until the restore — two queries, and never the third:**

```
uv run python infra/scripts/grafana-query.py 'up{job="capture_app",host="zcrypto"}' 'min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})'
```

**`hc_checks_down_total` is absent from that second line deliberately, and adding it back breaks the drill**: `zcrypto-capture-red` going down IS this drill's *Must fire*, so the aggregate rises above 0 mid-hold by design — a cadence that read it would abort a healthy hold at the moment the induction succeeded, and an operator who learned to ignore the value would be ignoring one the abort predicate never reads.

Two instruments, because that is two kinds of read: the by-value ones through the query script, and the two **rule states** through `GET /api/prometheus/grafana/api/v1/rules` with the same bearer token, re-read on the same 60 s cadence. `ALERTS{alertstate="firing"}` is structurally empty for Grafana-managed rules and reads `(no series)` on a firing fleet, so it is never the instrument here.

**Those four primary-whole signals are four because no one of them covers another.** On 2026-07-27 all twelve pairs went silent on **both** hosts for ~209 s while the socket read connected and the process kept scraping, so `up` read 1 throughout and only the gauge moved; both silence rules carry `noDataState: OK`, so a primary whose exporter or Alloy has gone away leaves them Normal while `up` goes 0 or empty; and on a single stuck stream neither by-value read moves at all — one pair stops while its siblings keep flowing, the live pairs hold the cross-pair minimum down, and [`capture.md#zcrypto-capture-stream-silent`](capture.md#zcrypto-capture-stream-silent) is the only one of the four that fires. Drop it from the predicate and a per-pair primary silence runs the whole hold out with the secondary's daemon stopped and nothing left to heal that pair from.

**Any one of those four reading anything but the green above — an EMPTY result included — aborts the hold**: run the revert immediately instead of waiting out the cap, record the abort time, and record the run **`partial`**, never `pass`. An abort costs a re-taken window; the overlap it prevents costs L2 that nothing recovers.

Also required: **no primary converge, reboot, or published Kraken maintenance inside the window.** A converge restarts live capture, and one overlap with both hosts silent books straight to `residual_gap_seconds_total`.

**Hard cap on the hold: `zcrypto-capture-red`'s `timeout` 600 s + `grace` 600 s + one 60 s evaluation = 21 min.** Re-quote the two values from the check itself immediately before. `capture-redundant` is that check's node **tag**, not a check name — a management-API lookup by that string returns nothing, and the adjacent `zcrypto-capture` is the **primary's** check, never the substitute.

### Induce

**Arm the timed restore on the secondary itself, before the stop** — a revert that lives only in this session dies with it:

```
sudo systemd-run --on-active=26min --unit=zcrypto-capture-restore systemctl start zcrypto-capture
```

`--on-active` is the cap **plus a 5 min margin**, so the fence expires after the deliberate revert and never truncates the hold. **Read that command's exit status before issuing the stop.** `systemd-run --unit=` refuses while a transient unit of that name is still loaded, and an abort by definition leaves the timer pending — a re-taken window then re-arms into a live name, gets the refusal, and an unread exit status puts the retaken hold behind no fence at all. The other refusal, and the one a stop cannot clear, is a fence that **fired** and whose `systemctl start` then failed: that transient service stays `loaded failed` and holds the name. Recovery on a non-zero arm exit is `sudo systemctl reset-failed zcrypto-capture-restore.service`, then arm again and read the status again.

**R** — on the secondary (`ssh red`), and nothing heavier. Never a reboot, never a power-off:

```
sudo systemctl stop zcrypto-capture
```

**P** — with R's stop in place, break the compose so the container is never created (a nonexistent image reference) and let the unit's `Restart=always` loop (`infra/ansible/roles/capture/files/zcrypto-capture.service`, `RestartSec=10`). **P's restore is a secondary converge**, because the compose file is role-rendered — write that converge command down **before** breaking the compose, and note that a converge is a human step outside the routine window.

### Must fire

- The `zcrypto-capture-red` check pages natively by staleness, **inside the cap**.
- `zcrypto-alloy-dark-capture-secondary` must stay **quiet**. Alloy is up; a firing there says the induction hit the wrong thing.
- `zcrypto-hcio-watchdog` follows the check by ≈7 min — which is past the 21 min cap, so expect it during or after the restore rather than during the hold.
- **On the restore**, [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) (warning, `metrics`) fires if the hold came back short of roughly 13 min: the secondary's daemon is a `capture_app` target of its `changes(…[15m]) > 0` read with `for: 2m`. A 21 min cap is above that line. Quote the actual cap into the entry and name this page there if it fires — it is the drill's own record, arriving at the one moment where an unexplained page invites the wrong reaction.

### Operator action

Revert at the cap, or immediately on any abort:

```
sudo systemctl start zcrypto-capture
```

**Disarm the fence the moment the daemon is read back up** — `sudo systemctl stop zcrypto-capture-restore.timer` — on an abort exactly as at the cap. That stop collects both transient units and frees the name only while the timer is still **pending**; it exits 5 once the timer has already fired and collected itself, which is a disarm that was not needed rather than one that failed.

A start on an already-running unit is a no-op, so whichever revert runs second changes nothing. The entry names whichever actually issued the start.

Then two reads close the run:

- **The secondary is back**: `up{job="capture_app",host="zcrypto-red"} == 1` and `hc_check_up{name="zcrypto-capture-red"}` back to 1. The induction is not reverted until the daemon it stopped is measured running again.
- **The primary is whole a second time**: no `minted`/`would_mint` record for the window's hours, row counts and hashes intact, `residual_gap_seconds_total` unchanged before and after. The secondary's own silence should appear at most as `trade_deficit` — the reconciler heals a silent primary from a live secondary and never the reverse.

### Record

Entries `R` and, when its window comes, `P`.

**R's entry is the one not written beside its induction.** The reconciler books hour H only at the first `:12`/`:42` tick after H+2 h, so until that tick the primary-whole read is **pending, not clean** — and the four statuses contain no word for *verdict pending*, so a heading written early forces either `partial` (which asserts a half-run where the run was whole) or a fifth status. Write R's entry once, after the tick, carrying the post-restore readings and not only the pre-stop one. Nothing else waits behind it.

`partial` is also the status when the through-hold watch was lost mid-hold: the cover the entry would otherwise claim was not taken.

### Retire when

The `zcrypto-capture-red` check is absent from the healthchecks.io checks listing, or `Restart=always` is absent from `infra/ansible/roles/capture/files/zcrypto-capture.service` — at which point the unit no longer loops on a container that cannot be created and P has no behaviour to exercise.

<a name="drill-q"></a>

## Drill Q — does the phone actually buzz — PROCEDURE

### What this proves

That a page reaches a **phone**, on each of the three receivers independently. Everything else on this page proves a rule fired; this proves someone finds out. It has never been recorded.

### Preconditions

Q induces almost nothing of its own — it **rides** other drills, so its preconditions are theirs. It needs the phone in hand, and it needs the reading taken while the alert is still firing.

The one exception is its `logs` path, which has an induction of its own and runs **before** the long holds begin, so all three paths close in one sitting.

### Induce

**Path 1, `metrics` receiver** — rides drill K. No separate induction.

**Path 3, healthchecks.io native** — rides drill I's throwaway check. No separate induction.

**Path 2, `logs` receiver** — one failing invocation inside the liquidations container on ops, and the shape is load-bearing:

```
sudo docker exec -e COINALYZE_API_KEY= zcrypto-ops-liquidations zcrypto --ship-logs liquidations-poll
```

**A bare failing command in that container is not a substitute and would be recorded as a failure of a healthy receiver.** Output from an exec goes to the exec client, never to the container's log stream, and the ops Alloy's journal relabel keeps only the five `zcrypto-*.service` units plus Alloy's own container — the liquidations container is dropped deliberately, because it ships its own logs. A process that merely raises there reaches Loki by neither path. With `--ship-logs` the exec'd process installs the push handler from the container's own environment, which `docker exec` inherits, and pushes straight to Loki, landing the line as `{host="ops", container="liquidations", level="ERROR"}` — [`ops-node.md#zcrypto-ops-error-logs`](ops-node.md#zcrypto-ops-error-logs)'s own selector. The emptied `COINALYZE_API_KEY` is what makes it ERROR; `-e` scopes the override to this exec alone, and if the override somehow did not take, the data dir's `flock` refuses a second poller rather than double-polling the venue.

### Must fire

- **Path 1**: `zcrypto-alloy-dark-ops` at ≈16 min; the `activeAt` is quoted from that rule, which is the page drill K's induction is for.
- **Path 2**: `zcrypto-ops-error-logs` (warning, `logs`) — `for: 0s` over a 15 min `count_over_time` window, so it fires on the **first evaluation** after the line is in Loki: ≈60 s, the group interval. **Confirm the line is in Loki before waiting on the rule** — no line means the induction never landed, and this path is **`blocked`** with the reason, never `fail`.
- **Path 3**: the throwaway check natively at ≈4 min, through healthchecks.io's own Slack integration.

### Operator action

Per path, record: arrived or not; the three timestamps (rule `activeAt`, Slack message, device); and **the channel's mobile setting and DND state at the time**. Without the mobile setting a push that did not arrive cannot be told from a channel set to "mentions only", which is the leading hypothesis.

**With no mention anywhere, paths 1 and 2 push only under "all new messages".** Two fix candidates: an `<!channel>` in the notification template, and the mobile setting itself, recorded as an operator precondition in `docs/reference/fleet.md`. **The mention candidate is scoped by severity, not by path** — the Slack template branches on `severity`, so putting a mention on the critical branch alone reaches path 1 only: path 2 rides a `warning` rule, and path 3 is healthchecks.io's own integration, which no Grafana template touches at all. A critical-only mention leaves two of the three paths exactly where they are.

### Record

**Established here:** the healthchecks-native route carries **no rule `activeAt` at all**, because that page is healthchecks.io's own notification and not a Grafana rule — so Q's three paths are not three readings of one shape, and only two of them can be timed from a rule.

**Q has no entry of its own, by design.** Its three readings land in the `K`, `I` and `Q-logs` entries — where their inductions are — and this section is the cross-path summary. The device timestamps and the mobile/DND readings cannot be taken from an unattended run and are marked **owed** in each entry rather than omitted.

### Retire when

**Never.** Every other section here retires when its code path goes away; this one asks whether a notification reaches a human, and the answer is a property of a phone, a Slack workspace and a notification setting — all three of which change without anything in this repo changing.

<a name="proven-tier-reverification"></a>

## Re-verifying an already-proven scenario — PROCEDURE

### What you are seeing

You are deciding whether a scenario that has **already** been proven — by a drill or by a real incident — needs another run. It usually does not.

### What it means

**A proven scenario is re-verified only when the code path it proved has changed since the proof.** Not on a schedule, and not because the proof is old: a drill that re-exercises an unchanged path costs an attended window and buys nothing, and on the capture side it costs a fault induced on live, unbackfillable data.

The proofs, and what each rests on:

| id | scenario | what proved it |
| -- | -- | -- |
| F | WS loss, capture side | drilled 2026-07-27, and seen since in real incidents; runbooked at [`capture.md#zcrypto-capture-all-streams-silent`](capture.md#zcrypto-capture-all-streams-silent) |
| H | capture daemon stopped, host down | drilled 2026-07-17 on the primary, and the 2026-07-11 reboot |
| J | engine cycle failure, engine dead | the 2026-07-11 incident in shadow. **Its `/fail` route was never covered** — that is drill J′ above, and it is not this row |
| L | healthchecks.io dark, or a check down | drilled 2026-07-21; the mutual watchdog both halves of which are described at [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) |
| M | Kraken maintenance collides with a converge | four real episodes; the standing rule lives in the fleet-deploy rules, not in a drill |
| P+R | the secondary goes away | R drilled 2026-08-31 — the dead-man pages at 20 m 20 s and is the SOLE detector; the silence rules cannot see a stopped daemon. P (its restore is a converge) is unproven |
| N | NAS archive-pull stall | the 2026-07-15/16 incident — and **its path has since changed. See below.** |
| T | an alert fires for something already over | the 2026-07-27 reconstruction |
| J′ | the `/fail` route on a dead-man | drilled 2026-08-31 — the route reaches Slack; the device leg is drill Q's and rides drill I |
| K | Alloy killed and timed | drilled 2026-08-31 — six pages inside their bounds, and the `docker restart` recipe verified on a stopped container |
| O | timer death with no staleness rule | drilled 2026-08-31 — the dead-man alone catches it, so no rule is owed |
| I | disk watermark breach to page | drilled 2026-08-31 — breach, withheld ping and page proven end to end on a throwaway check |
| C | the ingest plane goes dark | drilled 2026-08-31, both halves — recovery per plane depends on the host's journal-writing workload |
| N | NAS archive-pull stall | re-drilled 2026-08-31 on the post-`T0048` path — the dead-man catches it at ~2 h 31 m; four collateral pages, not three |
| C′ | Grafana Cloud dark | drilled 2026-08-31, **staleness route only** — the `/fail` route is a converge and remains unproven |
| Q | does the page reach a phone | drilled 2026-08-31, machine half only on all three receivers; the device and mobile/DND readings remain owed |

**Two scenarios from the original matrix are in no tier at all — they were considered and deliberately dropped.**

- **A reboot-window overlap check.** Both capture hosts are attended-reboot, so no automatic reboot window exists that could overlap another host's. `docs/reference/fleet.md` § Reboots holds the procedure, and [`hosts.md#zcrypto-capture-reboot-pending`](hosts.md#zcrypto-capture-reboot-pending) is the alert that exists precisely because a pending reboot waits for a human. There is nothing here a drill could induce.
- **Drills for the reconciler's phantom-splice guard and for the lost-trades detector.** Both are code guards with tests, not fleet failure scenarios — nothing on a host can be induced to exercise them. The splice guard is the detect-only default (`tests/test_archive_reconcile_command.py::test_detect_only_is_the_default_and_mints_nothing`); the detector is `is_total_loss`'s `alive_witness` in `cli/archive/settle.py` (`tests/test_archive_settle.py::test_absent_trades_hour_is_not_a_loss_when_the_book_hour_proves_the_stream_was_alive`). Their coverage question is a test question and is answered where tests are.

### What to do

**N has been re-run: 2026-08-31, `pass`** (entry `N` in `docs/reference/drill-log.md`). It was due because \[[T0048]\]'s fix changed the path its 2026-07-15/16 proof rested on, and the re-run confirms the dead-man still catches a stalled pull on the new path. **Two things it established that this page did not say.** The stop's collateral is four pages, not three — beyond the gate exporter, the `zcrypto-gate-verify` dead-man and the three gate rules that correctly stay quiet on frozen figures, `zcrypto-reconcile-source-lag` fires on BOTH mirror sources at once, because the NAS pull is the channel feeding both. Its summary is the most alarming in the set ("the fleet has no witness and the next primary gap is permanent"), it fires on a healthy fleet during this drill, and it is the one an executor meets cold. And **the recovery read must name a capture channel**: the first `pull complete` line back was `(no verify) … dest=/archive/engine-journal`, a clean line on a channel that is not the unbackfillable one. Accept only a line naming `zcrypto` or `zcrypto-red` with `failed=0`. Its proof was the 2026-07-15/16 incident, in which the NAS archive-pull's log shipping went dark and `zcrypto-nas-archive-pull-stalled` was the rule that noticed. The path it fired through has been rebuilt since: `discovery.docker` and `loki.source.docker` are gone from every Alloy config, and that container's lines now reach Loki over the journald driver through `loki.source.journal` and its `journal_units` relabel (`infra/nas/config.alloy`). The dead-man is unchanged; **the transport underneath it is not the one the incident proved**, so the proof no longer covers what runs today.

Re-run it as a drill, record it in `docs/reference/drill-log.md` under the id `N`, and amend this section with the outcome. **N gets no section of its own** — this is where it lives.

**Read `max(hc_checks_down_total) == 0` by value immediately before the stop** — `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. `zcrypto-hcio-watchdog` is in the *Must fire* below with a number, and as a fleet-wide aggregate it is already firing if an earlier drill left a check down. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

- **Induce**, on the NAS (`ssh nas`): `sudo /usr/local/bin/docker stop zcrypto-archive-pull`. **`docker` is at `/usr/local/bin/docker` on that host and is not on a non-interactive ssh `PATH`** — called bare it prints nothing and reads as "no containers" rather than "command not found". Stopping the **container** is the induction: the dead-man matches a clean `zcrypto archive pull` line from **any** channel inside it, so silencing one channel leaves it green.
- **Must fire**: [`nas.md#zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled) (critical, `logs`) — a `[3h]` no-clean-line window plus `for: 0s` plus the 60 s group interval ≈ **3 h 1 min after the last clean `pull complete … failed=0` line**, which is where the hold ends. **It is not the only page**: this container also runs the gate export and writes the ops writer's `.pull-status` gate, so expect [`gate.md#zcrypto-gate-exporter-stale`](gate.md#zcrypto-gate-exporter-stale) (critical, `metrics`) on the shorter clock — 7200 s + `for: 5m` + 60 s ≈ **2 h 6 min** from the last successful export — and the unpinged `zcrypto-gate-verify` check at `timeout` 3900 s + `grace` 3600 s = 7500 s = **2 h 5 min**, bringing `zcrypto-hcio-watchdog` ≈7 min behind it, at ≈2 h 12 min. **Expect all three inside about seven minutes of each other, roughly an hour before the drill's own page** — they are not staged, and three unnamed criticals arriving together mid-hold read as a real fault and stop the chain on a healthy induction. Name all three in the entry, or the next reader is left with two unexplained criticals and a healthchecks.io notification from a domain the drill never mentions.
- **Expect silence that proves nothing.** `zcrypto-gate-mismatch`, `zcrypto-gate-pull-lag` and `zcrypto-gate-streak-reset` stay quiet on **frozen** figures: the textfile persists and is still scraped, so `increase()`/`delta()` read 0 and the gauges hold their last values. The gate domain is suspended for the hold, not healthy.
- **Read `/archive/.pull-status`'s `ts_epoch` against the current epoch before the stop.** Over an hour old, wait out the next `pull complete` line and induce against a fresh one. That file is at most one loop period old when the stop lands (~1.2 h) and the ops overlay-writer's `MAX_STATUS_AGE` is 4 h, so it can age out **inside** this hold, after which that writer's fail-closed gate skips reconcile and backfill on every `:12`/`:42` cycle — and nothing pages to say it began. A crossing that happens anyway goes in the entry's *follow-ups* clause as the skipped cycles it is. **End the hold at the derived bound above; an overrun only buys more of them.**
- **Restore** with the recipe in [`nas.md#zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled), then read a `pull complete … failed=0` line back **naming the capture channels** — `sudo /usr/local/bin/docker logs zcrypto-archive-pull --since 4h`. The dead-man goes green on any single verified channel, so a bare clean line proves the mirror is being fed, not that the unbackfillable half is.

### Retire when

`docs/reference/drill-log.md` no longer exists — every rule above is about what gets written there, so with no log there is nothing to re-verify into.
