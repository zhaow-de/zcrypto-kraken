# Telemetry-tier drills — induce the fault, measure what fires

Nothing fires these; you open this page deliberately, in an attended window, to break a telemetry path on purpose and prove that the alert or dead-man that watches it actually pages. No money moves. The order-path drills — the ones where it does — live in `drills-order-path.md` and are fitted around [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window).

**Every section below is one drill, and every drill has the same seven parts**: *What this proves* · *Preconditions* · *Induce* · *Must fire* · *Operator action* · *Record* · *Retire when*. Read all seven before touching anything: the *Preconditions* are what keep a drill from becoming an incident, and several of them are the difference between a real reading and a fabricated one.

### Standing rules

These bind every section below.

- **The primary's capture daemon and the primary's Alloy are never a drill's subject** (set: the rule's, `.claude/rules/fleet-deploys.md`; count: `infra/scripts/count-list.sh drills-on-the-primary`); the subjects here are ops, the secondary, the NAS and the observability node, `zcrypto-mon`.
- **Never induce inside a published Kraken maintenance window** (no count command: a drill's feed read is entry prose; the converge count reads the deploy log) (`.claude/rules/fleet-deploys.md`). Read `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time **and again immediately before each induction**: a window can be published between the two reads. Which entries count is the converge bullet's test in `.claude/rules/fleet-deploys.md`; an empty `components` array is not an absent impact. The node, `zcrypto-mon`, speaks to no venue, so a drill whose subject is the node alone, W1 to W3 below, owes no feed read; W4's subject is the secondary, which does.
- **One induction at a time. Revert it and verify the revert BY VALUE before the next one starts.** A drill that leaves the fleet degraded is an incident, not a drill.
- **A stop and start moves the container's `.State.StartedAt`, which is what a `since` cell of [`fleet-pins.md`](../../docs/reference/fleet-pins.md) records — re-true that row in the same step as the restore** (no count command: a drill entry's *operator action* clause is prose). One `docker inspect <name> --format '{{.State.StartedAt}}'` — `/usr/local/bin/docker` on the NAS — is the whole cost; skipped, the cell keeps a value the container no longer has and no later reader can tell it from a converge-clock value.
- **Induce on a throwaway subject wherever one carries the fault.** A container from the *same pinned digest* on the ops node — isolated data dir, no Loki credentials, no dead-man URL — driven against the real venue, with `docker network disconnect/connect` as the fault, exercises WS-reconnect handling end to end while production keeps running. Drill I builds its subject the same way, with a throwaway check in place of the absent url; its *Preconditions* carry what such a check needs before any reading from it means anything (no count command: whether a reading means anything is judged at run time, against that list).
- **Inject the alert path itself with a textfile when no daemon needs to be involved.** Writing a synthetic `.prom` into the node-exporter textfile directory fires a real rule through the real transport into the real Slack channel, and resolves when the file is removed.
- **An instrument is never widened** (no count command: an entry's *induction* clause is prose no tool compares with its *Induce*). Each *Induce* below names exactly what to do — a container stop, a unit stop, a timer stop. Anything heavier (a reboot, a power-off, a firewall rule) is a different act with a different blast radius and is not licensed by the fact that a drill was authorized.
- **Predict an induction's collateral from its own *Must fire* clause first, never from a fresh sweep of `alerts.yaml` alone** (no count command: a prediction made before an induction leaves no artefact). Each section below enumerates what else pages. Treat the clause as a floor and add to it: where a section has never been induced its clause is derived rather than observed. To extend it, do not sweep for rules NAMING what you stop; those are only the first ring. Ask what stops being PRODUCED, then what watches that. `zcrypto-reconcile-source-lag` carries no host, container or job matcher and names nothing drill N touches, yet the stop freezes the mirror it watches. An unlisted page during an induction is *unclassified*, not *unexpected*.
- **A drill that cannot be induced is `blocked`, never `fail`** (no count command: whether an induction landed is prose in the entry, which no test reads). `fail` asserts a guard did not fire when nothing exercised it. The four statuses are fixed at `pass`, `fail`, `partial`, `blocked`.
- **Every run gets an entry in `docs/reference/drill-log.md` and lands its findings in the section it ran from** (no count command: a run leaves no record but the entry it owes). A result that lives only in a report is not recorded. That file's own preamble is the entry contract: the heading shape and every labelled clause, including when the *time-to-alert* clause owes a **device** timestamp and when it names the drill that measures that route instead.

### How every bound on this page was derived

A bound is derived or it is not written. Nothing below is an estimate.

- **A Grafana rule's bound is its own `for`, quoted from `infra/grafana/alerts.yaml`, plus its group's evaluation interval.**
- **The two Grafana endpoints key on different fields, and neither substitutes for the other.** The live rule-state endpoint `GET /api/prometheus/grafana/api/v1/rules` carries each rule's `uid` and its title under `name`; `read_alerts` in `infra/scripts/ops_daily.py` reads that `uid` and refuses the whole pass when one is missing. The **history** endpoint takes `ruleUID` (`/api/v1/rules/history?ruleUID=<uid>`); take any title from that rule's own `title:` in `infra/grafana/alerts.yaml`. **History is the only way to recover a transition after the fact** (no count command: Grafana's API behaviour, and run-time reads of it that nothing records): the live endpoint carries the current state and nothing else, so a `Pending` `activeAt` not read while pending is recoverable only there. **Its `from`/`to` are epoch SECONDS**: milliseconds return HTTP 200 with a well-formed body of three empty frames, which reads as "the rule never transitioned" rather than as a bad query. Validate any empty history against a rule you know transitioned in the same window before recording it as an absence.
- **A title filter matches the title WHOLE, never as a substring** (no count command: a live watcher is written at run time and nothing in the tree keeps it). The titles form host-prefixed families, so a substring collapses two rules into one reading: such a watch reports one name flipping between states when it is two rules disagreeing, and it books **another host's** page as your induction's. Assert each filter matches exactly one rule before trusting a single reading from it, and cross-check the page set against the Slack messages, whose links carry the uid.
- **A firing rule's `activeAt` is when it started FIRING, not when its condition went true.** This is Grafana-managed behaviour; Prometheus's own `activeAt` is condition-onset and does not move on the `Pending` → `Alerting` transition. Reading it off a firing rule and calling it condition-onset understates the operator's real notice by that `for`, in the flattering direction. **A drill's time-to-alert is neither reading**: it is page time minus INDUCTION time, so timestamp the induction yourself; no rule carries that moment. **The firing time itself is read from the rule or from `/api/v1/rules/history`, never from the Slack delivery stamp** (no count command: Grafana's `activeAt` semantics; an entry's timestamps are prose no test reads), which bounds delivery and nothing earlier.
- **Every rule group evaluates at 60 s** (no count command for the interval: it is a stack setting; and for the folder uid, set: the rules of `infra/grafana/alerts.yaml` whose `folderUID` is not the `${GRAFANA_ALERT_FOLDER_UID}` literal; count: `infra/scripts/count-list.sh alert-rules-without-the-folder-literal`). That number is in neither `infra/grafana/alerts.yaml` nor `infra/scripts/grafana-push.sh`, which sets none. Read it from Grafana's provisioning rule-group endpoint (`/api/v1/provisioning/folder/<folder uid>/rule-groups/<group>`, the `interval` field) rather than trusting this line: it is a setting in the stack and nothing in this repo changes when it moves. The folder uid is not in `alerts.yaml` either: every rule there carries the literal `${GRAFANA_ALERT_FOLDER_UID}` and `infra/scripts/grafana-push.sh` substitutes it, so take the value from that script's default. The node's Grafana holds the same groups and the `zcrypto-mon` group beside them, each at the same 60 s, read from its own rules endpoint with the `mon` token — `mon.md`'s `mon-patch-pass` step 5 prints `intervals=[60]` from it — and the push sets none there either.
- **Add ~5 minutes of Prometheus staleness wherever the condition cannot go true until the series goes stale** (no count command: staleness is upstream Prometheus's; `alerts.yaml` holds the shapes): the `count(up{…}) or on() vector(0)` silence shape every `zcrypto-alloy-dark-*` rule carries, and every instant **Prometheus** rule whose only path to firing is its series going away — not `zcrypto-gate-mismatch`, whose `increase(…[1d])` can go true on a live series, and which takes the term on its NoData path alone. The Loki dead-men take no such term although they carry `noDataState: Alerting` too: their `count_over_time` window empties on its own clock, which is why drill N derives `zcrypto-nas-archive-pull-stalled` from its `[3h]` window alone. Without that term the Alloy-dark bound understates the real notice by a third, which is why those rules' own comment in `alerts.yaml` puts the effective notice at ~15 min against a `for: 10m`.
- **A drill proves wiring, never timing** (no count command: upstream `min_over_time` behaviour and a reading's use, neither in the tree). A brand-new injected series fires in minutes where a real one takes the full window, because `min_over_time` aggregates only the samples present. Read a drill's latency as evidence about the path, never about the threshold.
- **A rule on the `logs` receiver sends no resolved notice, and its labels are not why.** That contact point is minted `disableResolveMessage: true` (`infra/scripts/grafana-push.sh`), which is right for the ERROR-log rules that age out; the Loki dead-men pin `metrics` instead and their clears reach `#zcrypto`. **Read a clear from rule state, `/api/prometheus/grafana/api/v1/rules`, never from channel silence** (no count command: where a clear was read is entry prose; `grafana-push.sh` mints the silent receiver), which cannot distinguish resolved from still-firing. A silent clear is a routing question; re-grouping the expression does not fix it.
- **A third party's own timestamp beats a local poll for the same event.** A notification cannot precede its own detection (no count command: causality, not a property of anything in the tree). Take the page time and the downtime from the service that owns the check, and use the local poll as corroboration.
- **A stopped daemon is invisible to the silence rules; the dead-man is its only detector until `zcrypto-reconcile-source-lag`, the reconciler's gap rules or `zcrypto-capture-log-dead-*` catch what it stopped producing** (no count command: a reading of `infra/grafana/alerts.yaml`'s exprs, not a countable set). `zcrypto-capture-all-streams-silent` scopes both capture hosts with `for: 0s` and an evaluator of `gt 120`, and carries `noDataState: OK`. A stopped daemon does not publish a large value; it stops publishing, the series vanishes, and `noDataState: OK` reads that as healthy. The silence rule and the dead-man cover opposite failures, a running daemon gone quiet and a daemon that is gone, so neither's silence says anything about the other's case.
- **A compose-level failure where the container is never created is seen by no log pipeline at all.** No container exists, so nothing is written on the docker path, and the owning unit's own journal lines are dropped on the capture hosts: `loki.relabel "journal_units"` keeps `zcrypto-(capture-prune|engine-journal-prune|reboot-check).service` and Alloy's container stream, nothing else (`infra/ansible/roles/capture/files/config.alloy`). The dead-man is the only catcher until `zcrypto-reconcile-source-lag`, the reconciler's gap rules or `zcrypto-capture-log-dead-*` catch what the capture daemon stopped producing, and its bound below is the detection bound (no count command: a reading of `infra/grafana/alerts.yaml`'s exprs, not a countable set); drill P is what exercises that.
- **A dead-man's bound is that check's own `timeout` + `grace`**, from the dead-man service's checks listing, `https://zcrypto-hc.zhaow.me/api/v3/checks/`, under the read-only key (`hc_readonly_api_key`, `group_vars/observed/vault.yml`). **Re-quote the values below immediately before a run**: they are settings on the service's checks and this page does not change when one does. **The listing takes a check NAME**: `capture`, `capture-redundant`, `ops`, `nas`, `engine` are node **tags** and resolve to nothing there, and a lookup that returns nothing is never repaired by reaching for the adjacent check (no count command: a run-time API lookup leaves nothing in the tree). [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) carries the tag-to-daemon map.
- **A `/fail` ping carries no timeout + grace term at all.** healthchecks.io moves the check down on receipt, so what is measured on that route is notification latency alone.
- **`zcrypto-hcio-watchdog` trails every dead-man on this page by ~7 min**, and it is in the *Must fire* of every drill that puts a check down (no count command: this page's *Must fire* lists, the ops Alloy's 60 s scrape, the watchdog's expr): the ops Alloy scrapes healthchecks.io every 60 s (`prometheus.scrape "healthchecks"`, `infra/ansible/roles/ops/files/config.alloy`), then `for: 5m` plus the 60 s group interval. It is a **fleet-wide** aggregate, `max(hc_checks_down_total) or on() vector(999)`, so it is already firing whenever any check anywhere is down, and an `activeAt` read off it is an unrelated event's time unless it postdates your induction. **That test alone is NOT sufficient, given the firing-onset rule above**: a check that went down up to one scrape interval before your induction puts the watchdog `Pending` before you induced and `Alerting` a full `for` later, so its `activeAt` postdates your induction, passes this test, and is still not your page. **No before-the-fact green read closes it**: every such read is served by a scrape up to 60 s stale, so a check going down after that scrape is invisible to it by construction; the exposed window is (induction − precondition read) + one scrape interval, not 60 s. **What closes it is the `Pending` `activeAt`, read BEFORE the rule fires**: in the `Pending` state `activeAt` is condition-onset, so a value postdating your induction proves no earlier scrape saw a check already down. Read it once while the rule is still `Pending`; once it fires that value is gone from the live endpoint and is recoverable only from the history endpoint above.

<a name="drill-c"></a>

## Drill C — the ingest plane goes dark — PROCEDURE

### What this proves

What a restarted shipper recovers **per plane**, and which rules misfire on the way back. Logs and metrics behave differently and the difference is the whole point: Alloy's journal reader replays the outage from its positions file under a `max_age = 48h` ceiling, while nothing scraped means the metrics window is simply **absent**; no backfill exists for it.

**A stopped shipper is not a dark destination.** Under a Grafana Cloud outage the two planes invert: `prometheus.remote_write` buffers to its WAL and replays, `loki.write` has no WAL and drops. So this drill measures one half of the permanent-loss statement [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark) needs and derives nothing about the other.

### Preconditions

- An attended window, the standing rules above satisfied, and the Kraken maintenance feed read immediately before.
- **Ops and the secondary only** (set: the rule's, `.claude/rules/fleet-deploys.md`; count: `infra/scripts/count-list.sh drills-on-the-primary`) (standing rules above).
- The previous induction reverted and verified by value.
- **`max(hc_checks_down_total) == 0`, read by value immediately before**: `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number on the ops half and with *must stay quiet* on the secondary half, and it is a fleet-wide aggregate: a check left down by an earlier drill has it already firing, which turns the ops reading into an unrelated event's `activeAt` and the secondary assertion into one nothing can satisfy. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.
- Budget two holds of **2 h each**, one per host, sequentially. The hold is the backfill horizon this drill exists to measure; a short hold measures the bound instead, which is drill K.

### Induce

On ops (`ssh hp`), then separately on the secondary (`ssh red`):

```
sudo docker stop grafana-alloy
```

**Not `docker network disconnect`.** Both Alloy containers are `network_mode: host` (`infra/ansible/roles/ops/templates/alloy-compose.yaml.j2`, `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2`), and Docker refuses to disconnect a container from the host network. **An egress rule is not the substitute**: it is a firewall change rather than a container start–stop, and inside the shared host netns it cannot be scoped to Alloy alone.

The stop reaches nothing else. Each Alloy is its own compose project and its own container; the capture daemon and the liquidations poller are separate, bridge-networked ones. On the secondary that is the whole assurance: **the capture daemon keeps running**, its dead-man keeps pinging, and its direct-shipped logs keep flowing; what goes dark is that host's `up` and node metrics.

### Must fire

**Ops half — nine pages.** An entry that names fewer books a nine-page blackout as a smaller one, and teaches the next responder to discount the rest.

- `zcrypto-alloy-dark-ops` (critical, `metrics`): `for: 10m` + 60 s + ~5 min staleness ≈ **16 min**.
- `zcrypto-hcio-watchdog` (critical, `metrics`), **ahead of it, at ≈11 min**: the ops Alloy *is* the healthchecks.io scrape, so `hc_checks_down_total` goes stale with it and the rule's `or on() vector(999)` fallback trips at ~5 min staleness + `for: 5m` + 60 s. This is the one route where the watchdog leads rather than trails.
- Six instant rules page by **NoData** at ≈11 min each (~5 min staleness + `for: 5m` + 60 s), because every series only the ops Alloy carries goes stale with it (no count command: upstream Prometheus staleness over the ops `config.alloy` keep-regex) and each carries `noDataState: Alerting`: [`zcrypto-ops-archive-pull-stalled`](ops-node.md#zcrypto-ops-archive-pull-stalled) (critical), [`zcrypto-reconcile-exporter-stale`](ops.md#zcrypto-reconcile-exporter-stale) (critical), [`zcrypto-trade-backfill-stale`](ops-node.md#zcrypto-trade-backfill-stale) (critical), [`zcrypto-ops-verified-replay-stale`](ops-node.md#zcrypto-ops-verified-replay-stale) (warning), [`zcrypto-ops-verify-replay-stale`](ops.md#zcrypto-ops-verify-replay-stale) (warning) and [`zcrypto-ops-grafana-keepalive-stale`](ops-node.md#zcrypto-ops-grafana-keepalive-stale) (warning). They are self-attributing: `zcrypto-alloy-dark-ops` fires in the same window and names the cause.
- `zcrypto-capture-textfile-missing` (warning, `metrics`), **last, at ≈26 min**: ops publishes the reboot probe the rule counts, so the count falls to 2 once its series goes stale (~5 min), then `for: 20m` + 60 s. A **value** page, not a NoData one; its summary names the capture hosts beside ops, and when ops alone is induced the host that stopped is ops.
- **Not** the Grafana watchdog check. It `curl`s Grafana from the host, not through Alloy, and keeps pinging success throughout.
- The ops Loki rules stay quiet: their `[6h]`/`[26h]` windows still hold hours of prior lines.

**Secondary half — two pages, not one**, for the same reason the ops half spells out: an unnamed page mid-hold reads as a real fault. `zcrypto-alloy-dark-capture-secondary` (critical, `metrics`) at ≈16 min, and **`zcrypto-capture-textfile-missing` (warning, `metrics`) about 10 min behind it**: `count(node_reboot_required{host=~"zcrypto|zcrypto-red|ops"})` with evaluator `lt 3` and `for: 20m`, so it is a **value** page rather than a NoData one and fires whenever one of the three hosts stops publishing. Read its summary carefully before reacting: it names the attended-reboot net on the capture hosts and ops, so on a secondary-only induction it is easily misread as a primary-side fault on the unbackfillable host. `zcrypto-hcio-watchdog` must stay **quiet**; no check is fed by that host's Alloy.

### Operator action

None during the hold; that is the drill. At the end of each hold:

```
sudo docker start grafana-alloy
```

Then read the recovery by value, `sudo docker ps --format '{{.Names}} {{.Status}}'` and `sudo docker logs grafana-alloy --since 15m`, and confirm the pages resolve before starting the next induction.

### Record

**Recovery is a property of the host's workload, not of Alloy.** "A stopped shipper loses metrics and recovers logs" holds only where something **writes to the journal during the outage**. Ops has timer units doing that; the secondary has none, since its capture daemon direct-ships and the three `zcrypto-*` units its Alloy relabel keeps write nothing to the shipped journal on an ordinary hold. **Count in-window lines by WHERE THEY FALL, never in bulk**, and derive the expected volume from the units' own `OnCalendar`. **`msg="Done replaying WAL"` on restart is not evidence of backfill**: the remote_write WAL buffers scraped-but-unsent samples, so a stopped Alloy has none to replay; that message attests to a dark destination, never to a stopped shipper.

**Checking for misfires on return: the window must outlive every candidate's `for`, or its zeros are guaranteed by construction.** The candidates are the rules blind to a condition already present in a series' first sample after a gap. Enumerate them from their expressions in `infra/grafana/alerts.yaml` (`changes()`, `delta()`, `increase()`, `resets()`), take each one's `for` from there, and end the window past the longest you intend to claim. A control proving the query saw the window is NOT a control proving the window outlived the rules. **Name as unverified, rather than counting clean, any candidate whose `for` no drill hold can outlive.** `zcrypto-fleet-daemon-restarted` is tripped by a SHORT hold and not a long one: past `[15m]` its window holds only the post-restore sample, so `changes()` counts none.

Two entries, `C-ops` and `C-secondary`. Beyond the standard clauses each carries what the restarted shipper recovered **per plane**, journal replay against the `max_age = 48h` ceiling and the metrics window absent, and which rules misfired on return.

A run's measured half, what a **restarted shipper** replays, lands in [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark), labelled *measured*, beside the Cloud-dark half derived from `config.alloy` and labelled *derived*, in the same sitting.

### Retire when

`zcrypto-alloy-dark-ops` and `zcrypto-alloy-dark-capture-secondary` are both absent from `infra/grafana/alerts.yaml`.

<a name="drill-c-prime"></a>

## Drill C′ — Grafana Cloud dark — PROCEDURE

### What this proves

The page time on each of the **two** routes by which the ops-side Grafana watchdog can fail, and the "you are here" a responder needs while the whole Grafana half of the stack is unreadable. The dead-man domain is a deliberately separate failure domain from Grafana Cloud; this drill is what proves it still answers when the other one is gone.

### Preconditions

- An attended window; standing rules above.
- **The `/fail` route restores only by a second converge** (no count command: the ops role renders the url into `grafana-watchdog.sh.j2`; a timer stop does not). A converge is a human step outside the routine window, so that route is written here and run when a converge window is open. The staleness route needs no converge and can run in any attended window.
- `zcrypto-grafana-watchdog` read green by value immediately before: `uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-grafana-watchdog"}' 'hc_checks_down_total'`. Green means **`hc_check_up == 1` and `max(hc_checks_down_total) == 0`**, both read as values: a check already down produces no up→down transition and therefore no notification at all, and the run would book `fail` against a route that works, while the fleet aggregate NARROWS, but does not close, the chance that the page this drill later times belongs to a check already down elsewhere. **What dates the page to this run is the watchdog's `Pending` `activeAt`** (standing rules above), read while the rule is still pending and shown to postdate the induction; that reading is destroyed when it fires. **Not green ⇒ the drill is recorded `blocked` with the reason**: never `pass`, and never `fail`, which would assert a route failed that was never exercised (no count command: whether an induction landed is prose in the entry, which no test reads).

### Induce

**Route 1, staleness**: on ops (`ssh hp`), stop the pinger and let its check go stale:

```
sudo systemctl stop zcrypto-grafana-watchdog.timer
```

**Route 2, `/fail`**: a converge that overrides the probe url with an unreachable one, so the probe fails and `infra/ansible/roles/ops/templates/grafana-watchdog.sh.j2` pings `<url>/fail` instead of the success url:

```
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops \
  -e ops_grafana_watchdog_probe_url=https://grafana-watchdog-drill.invalid/api/health
```

**The revert is the same command without the `-e`**: the role default (`infra/ansible/roles/ops/defaults/main.yml`) restores the real probe url. Write that second invocation down before running the first. `converge.sh` requires `--limit`, shows a `--check --diff` preview and takes a typed confirm of the limit value; **never wrap it in `timeout`**, which kills the wrapper while its child keeps converging.

**The preview cannot show you the url you are setting.** The task that renders the runner script carries `no_log: true` and `diff: false` (`infra/ansible/roles/ops/tasks/main.yml`), because the real probe url is a credential-adjacent value, so `--check --diff` reports that task **changed** and nothing more, on the override pass and on the revert alike. Check the `-e` you typed against this page before confirming; the preview will not catch a typo in it, and a typo lands a *different* unreachable url, which still induces the drill but is not what the entry says was set.

### Must fire

- **Route 1**: the `zcrypto-grafana-watchdog` check pages natively at its own `timeout` 600 s + `grace` 600 s = **20 min from its last ping**. The timer probes every 5 min (no count command: `grafana-watchdog.timer.j2`'s `OnCalendar` holds it), so the page lands 15–20 min after the stop, not 20 min after it. Then `zcrypto-hcio-watchdog` at ≈7 min behind the check.
- **Route 2**: the same check pages natively **on receipt**. A `/fail` is an immediate down transition, so there is no timeout + grace term and what you are timing is notification latency. Then `zcrypto-hcio-watchdog`, again ≈7 min behind.

Both routes reach the phone through healthchecks.io's own Slack integration, which no Grafana notification template touches.

### Operator action

Route 1: `sudo systemctl start zcrypto-grafana-watchdog.timer`, then confirm the next probe pings and the check reads green by value. Route 2: the reverting converge, then the same green read.

### Record

One entry per route, and the two routes take different ids: the staleness route holds `C′`, the `/fail` route `C′-fail`. Each carries its own page bound; the two numbers are what an operator uses to tell "the pinger died" from "Grafana died" while looking at neither.

The page bound belongs in [`observability.md#grafana-cloud-dark`](observability.md#grafana-cloud-dark), the procedure a responder opens for the duration of an outage.

### Retire when

The `zcrypto-grafana-watchdog` check is absent from the healthchecks.io checks listing, or `grafana-watchdog.timer.j2` is absent from `infra/ansible/roles/ops/templates/`.

<a name="drill-i"></a>

## Drill I — disk watermark breach to page, end to end — PROCEDURE

### What this proves

The breach → withheld ping → page path, whole, on real code, **on the ops node and on no capture host**.

### Preconditions

- An attended window; standing rules above. Nothing on a capture host is touched.
- **A green control runs first.** Start the throwaway container on a normally-sized data dir and see its throwaway check go **green**. Without it the drill is degenerate: a container that never reached the venue's WS (wrong pairs, missing config, no egress), or one whose disk probe raised and left `watermark.measurable` False, withholds the ping identically, and a check that only ever breached cannot tell any of them apart (no count command: a withheld ping carries no cause, so there is nothing to count).
- **Then `max(hc_checks_down_total) == 0`, read by value immediately before the breaching container starts**: `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. This read comes after the control, not before it, so that "immediately before" has nothing between it and the induction. `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number, and it is a fleet-wide aggregate already firing whenever any check anywhere is down (no count command: `infra/grafana/alerts.yaml`'s `zcrypto-hcio-watchdog` expr holds it), so a page that predates the induction is booked as this drill's measurement. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

### Induce

A throwaway capture container on ops from the capture-image digest in `docs/reference/fleet-pins.md`, with a **tmpfs data dir a few hundred MiB wide**, pointed at a throwaway healthchecks.io check.

- **The tmpfs width IS the induction; nothing has to be filled.** `DEFAULT_MIN_FREE_BYTES` is 1 GiB (`cli/capture/gap_monitor.py`), so a few-hundred-MiB filesystem is under the watermark from the moment it mounts.
- **The gate is the `not watermark.breached` conjunct in `_healthcheck_loop`** (`cli/capture/command.py`), not `GapMonitor.is_healthy()`, which reads open gaps only and stays True right through a breach (no count command: `cli/capture/gap_monitor.py:GapMonitor.is_healthy` reads `is_open` alone). Diagnosing a ping that did *not* stop by hunting for an open gap finds none and concludes the dead-man path is broken, the one wrong answer available here.
- **The throwaway check is created with its Slack integration named explicitly.** A check created through the management API inherits **no** integrations, and an unchannelled one breaches in silence, which would be recorded as a failure of the dead-man domain that never happened. Creating a check needs the full admin key (`healthchecks_api_key`, `group_vars/capture_host/vault.yml`), not the read-only one; resolve it in-process through the vault resolver and place it in a request header, never in argv where `ps` shows it. The integration's own identifier comes from the same API's channels listing under that same admin key: never guessed, and never under the read-only key, whose failure here reads as a missing integration rather than as the wrong credential (no count command: run-time API calls leave nothing in the tree; the inheritance is healthchecks.io's).
- **`timeout` and `grace` are set explicitly at creation: 120 s each.** For a check the drill mints, the drill chooses the bound. Derived from what is being watched, the capture daemon's 60 s ping (`HEALTHCHECK_INTERVAL_SECONDS`, `cli/capture/command.py`): `timeout: 120` clears one jittered ping without paging during the green control, and `grace: 120` puts the page within four minutes of the withheld one. Left unset the wait is whatever the API's defaults happen to be, and the drill holds a throwaway container on the ops node for however long that is.
- **The check's `desc` carries `Runbook: infra/runbooks/drills-telemetry.md#drill-i`.** The daily pass reports every live check whose description carries no resolving citation (no count command: `tests/test_ops_daily.py::test_a_missing_or_dangling_runbook_link_is_a_finding` holds it), and this one is live across a whole sitting.
- The container's `HEALTHCHECK_URL` env var, what the capture role renders from `capture_healthcheck_url`, is what points it at the throwaway check. Left pointing anywhere else, the drill withholds a **production** dead-man.

### Must fire

- The throwaway check pages natively at **its own 120 s + 120 s ≈ 4 min** after the ping is withheld. That is this drill's chosen bound and is **not** the production capture check's notice time, which is 600 s + 600 s; say which one the entry quotes.
- `zcrypto-hcio-watchdog` (critical, `metrics`) fires with it, ≈7 min behind: the minted check going down puts `hc_checks_down_total` above 0 exactly as a production one would. Two pages, not one.

### Operator action

**The by-value read is `sudo docker logs <the throwaway container> --since 10m`**: the `disk watermark breached path=… free=… min_free_bytes=…` ERROR line from `cli/capture/gap_monitor.py`. Ops runs no `capture_app` scrape job and its Alloy keep-regex admits no `zcrypto_capture_*` series, so **no capture gauge is readable from Grafana on that host at all**.

Then delete the throwaway check through the management API and remove the container and its tmpfs. Both go in the same sitting; the only safe stopping point is the boundary between drills.

### Record

The watermark ERROR is logged **once**, not once per probe: the gap opens and stays open. `zcrypto-hcio-watchdog` reads **1** on this induction where drill K drives it to **999**: K takes out the hc.io scrape itself, this one only puts a check down.

Entry `I`. The *time-to-alert* clause records this check's own timeout + grace and **says which check it quotes**. The *channels* clause names both pages, the native one and the watchdog, or a two-page induction is booked as one.

The healthchecks-native path of drill Q is read here; see [`drills-telemetry.md#drill-q`](drills-telemetry.md#drill-q).

### Retire when

`DEFAULT_MIN_FREE_BYTES` is absent from `cli/capture/gap_monitor.py`, or the `not watermark.breached` conjunct is absent from `_healthcheck_loop` in `cli/capture/command.py`, at which point a breach no longer withholds the ping and there is no path to exercise. The alert side of the same signal is [`capture-daemon.md#zcrypto-capture-watermark-breached`](capture-daemon.md#zcrypto-capture-watermark-breached).

<a name="drill-j-prime"></a>

## Drill J′ — the `/fail` route on a dead-man — PROCEDURE

### What this proves

That an explicit `/fail` ping leaves a process, moves the check and reaches **Slack** on both routes: the **routing**, not the caller, whose own call is unit-tested. The device leg is drill Q's path 3, which rides drill I on this same route, and is not proven here; the entry says so.

### Preconditions

**Both read by value immediately before the induction**, and each narrows a different confound. A third read, the watchdog's `Pending` `activeAt`, is taken *after* the induction and is what actually dates the page to this run; it is timed by the rule's own state, not by this list:

- `hc_check_up{name="zcrypto-engine-shadow"} == 1`: healthchecks.io notifies on the up→down **transition** only (no count command: healthchecks.io's notification behaviour, a property of the third party), so a check already down produces no message and the run would book `fail` against a routing path that works.
- `max(hc_checks_down_total) == 0`: `zcrypto-hcio-watchdog` is a fleet-wide aggregate already firing whenever any check anywhere is down (no count command: `infra/grafana/alerts.yaml`'s `zcrypto-hcio-watchdog` expr holds it), so an `activeAt` read off an instance that predates the induction is an unrelated event's time. **Postdating your induction is not sufficient on its own** (standing rules above): read the watchdog's `activeAt` while it is still `Pending`, confirm THAT postdates the induction, and write it into the log as the page bound a responder will later trust.

```
uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-engine-shadow"}' 'hc_checks_down_total'
```

Not green ⇒ the drill is **`blocked`** with the reason, never `pass`, never `fail`.

The engine is **disarmed** for the window.

### Induce

Until `uv run python infra/scripts/hc-provision.py status` reads `zcrypto-engine-shadow` moved, read `hcio_engine_healthcheck_url` from `group_vars/engine_host/vault.yml` through the vault resolver **on the workstation**; from then, read `hc_ping_key` from `group_vars/observed/vault.yml` the same way, the url being `https://zcrypto-hc.zhaow.me/ping/<key>/zcrypto-engine-shadow`. Issue the `<url>/fail` GET **from that same Python process**.

- **Never issue that GET with `curl`** (no count command: a one-off workstation call during the drill leaves nothing in the tree). The URL *is* the ping secret and `ps` shows argv.
- **Never from the engine host** (no count command: a drill-time call leaves no trace; `roles/engine/templates/engine.env.j2` is the one render). Its only copies sit beside the live trade key, in `engine.env` and the container environment.

### Must fire

- `zcrypto-engine-shadow` pages natively **on receipt**: a `/fail` is an immediate down transition, so no timeout + grace term applies. For contrast, the same check going *silent* would take `timeout` 14400 s + `grace` 2100 s = **4 h 35 m**; the two numbers answer different questions and the entry says which route it timed.
- `zcrypto-hcio-watchdog` (critical, `metrics`) ≈7 min behind.

### Operator action

A success ping to the same url, from the same process, to clear the check. Then read it green by value with the same query as the precondition; the induction is not reverted until the check is measured up again.

### Record

Entry `J′`. It records the two green precondition readings taken **before** the induction and the two machine timestamps (`zcrypto-hcio-watchdog`'s rule `activeAt`, and the Slack message). What makes those timestamps this run's is the watchdog's `Pending` `activeAt`, not the green readings. It does **not** carry a device timestamp and does not mark one owed: this route's device leg is drill Q's path 3, which rides drill I's throwaway check into the same channel, so a reading here would duplicate I's rather than add one.

`Engine · cycles have stopped` stays quiet throughout and its silence is not recorded as evidence of route separation: that rule reads an engine-side gauge on a 4 h 35 m bar, which no healthchecks.io ping can move.

### Retire when

`_ping_healthcheck` in `cli/engine/cycle.py` no longer appends `/fail`, or `engine_healthcheck_url` is absent from `group_vars/engine_host/vars.yml`. The alert that reads the same check's silence is [`engine.md#zcrypto-engine-cycle-stale`](engine.md#zcrypto-engine-cycle-stale).

<a name="drill-k"></a>

## Drill K — Alloy kill, timed — PROCEDURE

### What this proves

The Alloy-dark bound, measured rather than computed, and the restart recipe verified by value. Same instrument as drill C, short hold: C measures what a 2 h outage costs, K measures how fast anyone finds out.

### Preconditions

An attended window; standing rules above. **Ops only.** Nothing else induced at the same time: the metrics path of drill Q is read off this induction and needs the page set to be attributable.

**`max(hc_checks_down_total) == 0`, read by value immediately before**:

```
uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'
```

This one bites in practice rather than in theory: drill I mints a throwaway check and drill O puts `zcrypto-panel` down, so running K later in the same sitting with either still down has `zcrypto-hcio-watchdog` **already firing**, and its ≈11 min here is the number K exists to measure. An `activeAt` that predates the stop is an unrelated event's time. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

### Induce

On ops (`ssh hp`):

```
sudo docker stop grafana-alloy
```

### Must fire

Eight of the nine pages drill C's ops half lists, on the same clocks: `zcrypto-hcio-watchdog` at ≈11 min, `zcrypto-alloy-dark-ops` at ≈16 min, and the six NoData rules at ≈11 min. Each trips inside K's shorter hold, which is why K is the induction that times them; `zcrypto-capture-textfile-missing`'s ≈26 min falls past a hold ended at ≈16 min, and it stays quiet here.

### Operator action

**Hold to `zcrypto-alloy-dark-ops`'s own ≈16 min, never to the earlier watchdog page.** Below roughly 13 minutes the restore itself trips [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) (warning, `metrics`): it reads `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, and the ops Alloy is one of its `integrations/self` targets, so a restore landing while the pre-stop sample is still inside that 15 min window counts the return as a restart. Waiting `zcrypto-alloy-dark-ops` out clears the window. A restore that lands inside it anyway is **named in the entry, never chased**.

**Read drill Q's metrics path here, while the alert is still firing.** Every induction is reverted before the next starts, so a reading deferred past the restore has nothing left to read and costs a second, unplanned Alloy stop.

Then restore with the recipe from [`observability.md#zcrypto-alloy-dark-ops`](observability.md#zcrypto-alloy-dark-ops), which works on a stopped container:

```
sudo docker restart grafana-alloy
```

Not `sudo docker start grafana-alloy`: it restores the container but exercises no recipe, and verifying the recipe by value is half of what this drill is for. Read the recovery back by value, `sudo docker ps --format '{{.Names}} {{.Status}}'`, then the six NoData rules resolving.

### Record

**Slack delivery is not part of any of these bounds**; report it separately. The entry records which rules ran tightest: the margin is `60 s − scrape residue`, so the whole spread is one group evaluation interval, and a rule whose residue reached 60 s would fire exactly at its bound. `zcrypto-hcio-watchdog` reads **999** here, its hc.io-dark branch, because the ops Alloy IS that scrape.

Entry `K`, with every page in the set and its measured time against the derived bound. Drill Q's metrics-path `activeAt` is quoted from `zcrypto-alloy-dark-ops`, the page this induction is for, and lands in this entry, not in one of its own.

### Retire when

`zcrypto-alloy-dark-ops` is absent from `infra/grafana/alerts.yaml`.

<a name="drill-o"></a>

## Drill O — timer death — PROCEDURE

### What this proves

Whether a systemd timer with **no Grafana staleness rule** is caught by its healthchecks.io dead-man alone, and, if it is not, that a rule is owed. The panel-materialize timer is specifically the one with no staleness rule ([`ops-node.md#zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) records the gap); any other ops timer measures a different thing.

### Preconditions

**Both read by value immediately before the stop**, for the same two reasons drill J′ reads its pair:

```
uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-panel"}' 'hc_checks_down_total'
```

`hc_check_up{name="zcrypto-panel"} == 1` with its last ping inside one timer period, **and** `max(hc_checks_down_total) == 0`. An unset or paused check has been down independently of this drill and its page predates it, and a native healthchecks.io page carries no rule `activeAt` to separate the two afterwards; the aggregate is the second half because the only rule `activeAt` this drill produces is the watchdog's.

**Not green is diagnosed, never guessed at.** Whether the url is configured at all is a repo read: the `ops_panel_healthcheck_url` line of `host_vars/zcrypto-ops/vars.yml`, the project ping key's base and the slug `zcrypto-panel`, and `hc_ping_key` present in `group_vars/observed/vault.yml`, `grep -c '^hc_ping_key: !vault' infra/ansible/group_vars/observed/vault.yml` printing `1`. Whether the live host is *pinging* it is what the green read answers.

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

On `fail`, the entry's *follow-ups* clause names the owed staleness rule on `ops_panel_last_success_timestamp` and it is registered where work is registered: **a rule found owed is a change to `infra/grafana/alerts.yaml`, never a closure written into a runbook.**

Restore either way:

```
sudo systemctl start zcrypto-panel-materialize.timer
```

Then confirm the next ping lands and the check reads green by value.

### Record

**Anchor the bound on the check's `last_ping`, never the timer's `LastTriggerUSec`**: the unit pings on completion, so the trigger predicts the page early. **Restoring an `OnCalendar` timer fires a run immediately, and `Persistent=` does not predict it**, so `LastTriggerUSec` after a restore is never evidence of a healthy schedule; the returning ping is.

Entry `O`, with the measured time-to-page against the 3 h bound, or the non-page recorded as the finding. Either outcome, `pass` or `fail`, re-tenses the no-staleness-rule paragraph in [`ops-node.md#zcrypto-ops-panel-exit-nonzero`](ops-node.md#zcrypto-ops-panel-exit-nonzero) in the same change, if the outcome changes what that paragraph claims.

### Retire when

A rule in `infra/grafana/alerts.yaml` reads `ops_panel_last_success_timestamp`, at which point the dead-man is no longer the only catcher and this question is answered, or the `zcrypto-panel` check is absent from the healthchecks.io checks listing.

<a name="drill-p-plus-r"></a>

## Drill P+R — the secondary goes away — PROCEDURE

### What this proves

That the **one log class no Alloy pipeline sees** is caught, and in how long: a compose service that is never created writes nothing anywhere, so its liveness rests entirely on a dead-man. R is the unit stopped; P is the unit looping because the container cannot be created. And that **the primary stays whole** across the window.

### Preconditions

**Read all four of these immediately before the stop.** Each is a point-in-time read, the loss they guard against is permanent, and nothing in a before-and-after pair can see the primary going silent *between* them, so **the first three, which are the four primary-whole signals, are re-read on a 60 s cadence through the whole hold**. The fourth is an attribution read, taken once.

- `up{job="capture_app",host="zcrypto"}` reads **1**.
- `min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})` reads **under 120 s**, the threshold `zcrypto-capture-all-streams-silent` itself carries.
- Every primary instance of `zcrypto-capture-all-streams-silent` and of `zcrypto-capture-stream-silent` is **Normal** (no count command: a live rule-state read at run time; the tree holds no instance state).
- `max(hc_checks_down_total)` reads **0**: the attribution read, and the only one here that says nothing about the primary (no count command: a property of this list, whose first three bullets alone feed the abort predicate). `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number, and as a fleet-wide aggregate it is already firing if an earlier drill left a check down. Not 0 ⇒ clear the down check first, or record **`blocked`**. It is not on the cadence and never aborts a hold under way.

**The pre-read, once, before the stop**, all three by-value queries:

```
uv run python infra/scripts/grafana-query.py 'up{job="capture_app",host="zcrypto"}' 'min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})' 'hc_checks_down_total'
```

**The cadence, every 60 s from the stop until the restore: two queries, and never the third:**

```
uv run python infra/scripts/grafana-query.py 'up{job="capture_app",host="zcrypto"}' 'min(zcrypto_capture_seconds_since_last_book_message{host="zcrypto"})'
```

**`hc_checks_down_total` is absent from that second line deliberately, and adding it back breaks the drill**: `zcrypto-capture-red` going down IS this drill's *Must fire*, so the aggregate rises above 0 mid-hold by design. A cadence that read it would abort a healthy hold at the moment the induction succeeded, and an operator who learned to ignore the value would be ignoring one the abort predicate never reads.

Two instruments, because that is two kinds of read: the by-value ones through the query script, and the two **rule states** through `GET /api/prometheus/grafana/api/v1/rules` with the same bearer token, re-read on the same 60 s cadence. `ALERTS{alertstate="firing"}` is structurally empty for Grafana-managed rules and reads `(no series)` on a firing fleet, so it is never the instrument here.

**Those four primary-whole signals are four because no one of them covers another.** Every pair can go silent on **both** hosts at once while the socket reads connected and the process keeps scraping, so `up` reads 1 throughout and only the gauge moves; both silence rules carry `noDataState: OK`, so a primary whose exporter or Alloy has gone away leaves them Normal while `up` goes 0 or empty; and on a single stuck stream neither by-value read moves at all: one pair stops while its siblings keep flowing, the live pairs hold the cross-pair minimum down, and [`capture.md#zcrypto-capture-stream-silent`](capture.md#zcrypto-capture-stream-silent) is the only one of the four that fires. Drop it from the predicate and a per-pair primary silence runs the whole hold out with the secondary's daemon stopped and nothing left to heal that pair from.

**Any one of those four reading anything but the green above, an EMPTY result included, aborts the hold**: run the revert immediately instead of waiting out the cap, record the abort time, and record the run **`partial`**, never `pass`. An abort costs a re-taken window; the overlap it prevents costs L2 that nothing recovers.

Also required: **no primary converge, reboot, or published Kraken maintenance inside the window** (`.claude/rules/fleet-deploys.md`). A converge restarts live capture, and one overlap with both hosts silent books straight to `residual_gap_seconds_total`.

**Hard cap on the hold: `zcrypto-capture-red`'s `timeout` 600 s + `grace` 600 s + one 60 s evaluation = 21 min.** Re-quote the two values from the check itself immediately before. `capture-redundant` is that check's node **tag**, not a check name: a management-API lookup by that string returns nothing, and the adjacent `zcrypto-capture` is the **primary's** check, never the substitute.

### Induce

**Arm the timed restore on the secondary itself, before the stop**; a revert that lives only in this session dies with it:

```
sudo systemd-run --on-active=26min --unit=zcrypto-capture-restore systemctl start zcrypto-capture
```

`--on-active` is the cap **plus a 5 min margin**, so the fence expires after the deliberate revert and never truncates the hold. **Read that command's exit status before issuing the stop.** `systemd-run --unit=` refuses while a transient unit of that name is still loaded, and an abort by definition leaves the timer pending: a re-taken window then re-arms into a live name, gets the refusal, and an unread exit status puts the retaken hold behind no fence at all. The other refusal, and the one a stop cannot clear, is a fence that **fired** and whose `systemctl start` then failed: that transient service stays `loaded failed` and holds the name. Recovery on a non-zero arm exit is `sudo systemctl reset-failed zcrypto-capture-restore.service`, then arm again and read the status again.

**R**: on the secondary (`ssh red`), and nothing heavier (standing rules above):

```
sudo systemctl stop zcrypto-capture
```

**P**: with R's stop in place, break the compose so the container is never created (a nonexistent image reference) and let the unit's `Restart=always` loop (`infra/ansible/roles/capture/files/zcrypto-capture.service`, `RestartSec=10`). **P's restore is a secondary converge**, because the compose file is role-rendered. Write that converge command down **before** breaking the compose, and note that a converge is a human step outside the routine window.

### Must fire

- The `zcrypto-capture-red` check pages natively by staleness, **inside the cap**.
- `zcrypto-alloy-dark-capture-secondary` must stay **quiet**. Alloy is up; a firing there says the induction hit the wrong thing.
- `zcrypto-hcio-watchdog` follows the check by ≈7 min, which is past the 21 min cap, so expect it during or after the restore rather than during the hold.
- **On the restore**, [`zcrypto-fleet-daemon-restarted`](fleet.md#zcrypto-fleet-daemon-restarted) (warning, `metrics`) fires if the hold came back short of roughly 13 min: the secondary's daemon is a `capture_app` target of its `changes(…[15m]) > 0` read with `for: 2m`. A 21 min cap is above that line. Quote the actual cap into the entry and name this page there if it fires; it is the drill's own record, arriving at the one moment where an unexplained page invites the wrong reaction.

### Operator action

Revert at the cap, or immediately on any abort:

```
sudo systemctl start zcrypto-capture
```

**Disarm the fence the moment the daemon is read back up**, `sudo systemctl stop zcrypto-capture-restore.timer`, on an abort exactly as at the cap. That stop collects both transient units and frees the name only while the timer is still **pending**; it exits 5 once the timer has already fired and collected itself, which is a disarm that was not needed rather than one that failed.

A start on an already-running unit is a no-op, so whichever revert runs second changes nothing. The entry names whichever actually issued the start.

Then two reads close the run:

- **The secondary is back**: `up{job="capture_app",host="zcrypto-red"} == 1` and `hc_check_up{name="zcrypto-capture-red"}` back to 1. The induction is not reverted until the daemon it stopped is measured running again.
- **The primary is whole a second time**: no `minted`/`would_mint` record for the window's hours, row counts and hashes intact, `residual_gap_seconds_total` unchanged before and after. The secondary's own silence should appear at most as `trade_deficit`; the reconciler heals a silent primary from a live secondary and never the reverse (no count command: `tests/test_archive_reconcile.py::test_a_secondary_only_deficit_is_a_qa_signal_not_a_mint` holds it).

### Record

One entry each, `R` and `P`.

**R's entry is written after the tick, not beside its induction.** The reconciler books hour H only at the first `:12`/`:42` tick after H+2 h, so until that tick the primary-whole read is **pending, not clean**. Write R's entry once, after the tick, carrying the post-restore readings and not only the pre-stop one.

`partial` is also the status when the through-hold watch was lost mid-hold: the cover the entry would otherwise claim was not taken.

### Retire when

The `zcrypto-capture-red` check is absent from the healthchecks.io checks listing, or `Restart=always` is absent from `infra/ansible/roles/capture/files/zcrypto-capture.service`, at which point the unit no longer loops on a container that cannot be created and P has no behaviour to exercise.

<a name="drill-q"></a>

## Drill Q — does the phone actually buzz — PROCEDURE

### What this proves

That a page reaches a **phone**, on each of the three receivers independently. Everything else on this page proves a rule fired; this proves someone finds out.

### Preconditions

Q induces almost nothing of its own. It **rides** other drills, so its preconditions are theirs. It needs the phone in hand, and it needs the reading taken while the alert is still firing.

The one exception is its `logs` path, which has an induction of its own and runs **before** the long holds begin, so all three paths close in one sitting.

### Induce

**Path 1, `metrics` receiver**: rides drill K. No separate induction.

**Path 3, healthchecks.io native**: rides drill I's throwaway check. No separate induction.

**Path 2, `logs` receiver**: one failing invocation inside the liquidations container on ops, and the shape is load-bearing:

```
sudo docker exec -e COINALYZE_API_KEY= zcrypto-ops-liquidations zcrypto --ship-logs liquidations-poll
```

**A bare failing command in that container is not a substitute and would be recorded as a failure of a healthy receiver.** Output from an exec goes to the exec client, never to the container's log stream, and the ops Alloy's journal relabel keeps only the `zcrypto-*.service` units its keep-regex names plus Alloy's own container; the liquidations container is dropped deliberately, because it ships its own logs. A process that merely raises there reaches Loki by neither path. With `--ship-logs` the exec'd process installs the push handler from the container's own environment, which `docker exec` inherits, and pushes straight to Loki, landing the line as `{host="ops", container="liquidations", level="ERROR"}`, [`ops-node.md#zcrypto-ops-error-logs`](ops-node.md#zcrypto-ops-error-logs)'s own selector. The emptied `COINALYZE_API_KEY` is what makes it ERROR; `-e` scopes the override to this exec alone, and if the override somehow did not take, the data dir's `flock` refuses a second poller rather than double-polling the venue.

### Must fire

- **Path 1**: `zcrypto-alloy-dark-ops` at ≈16 min; the `activeAt` is quoted from that rule, which is the page drill K's induction is for.
- **Path 2**: `zcrypto-ops-error-logs` (warning, `logs`), `for: 0s` over a 15 min `count_over_time` window, so it fires on the **first evaluation** after the line is in Loki: ≈60 s, the group interval. **Confirm the line is in Loki before waiting on the rule**: no line means the induction never landed, and this path is **`blocked`** with the reason, never `fail` (no count command: whether an induction landed is prose in the entry, which no test reads).
- **Path 3**: the throwaway check natively at ≈4 min, through healthchecks.io's own Slack integration.

### Operator action

Per path, record: arrived or not; the three timestamps (rule `activeAt`, Slack message, device); and **the channel's mobile setting and DND state at the time**. Without the mobile setting a push that did not arrive cannot be told from a channel set to "mentions only", which is the leading hypothesis.

**With no mention anywhere, paths 1 and 2 push only under "all new messages".** Two fix candidates: an `<!channel>` in the notification template, and the mobile setting itself. **The mention candidate is scoped by severity, not by path**: the Slack template branches on `severity`, so putting a mention on the critical branch alone reaches path 1 only. Path 2 rides a `warning` rule, and path 3 is healthchecks.io's own integration, which no Grafana template touches at all. A critical-only mention leaves two of the three paths exactly where they are.

### Record

**Established here:** the healthchecks-native route carries **no rule `activeAt` at all**, because that page is healthchecks.io's own notification and not a Grafana rule. Q's three paths are not three readings of one shape, and only two of them can be timed from a rule.

**Q has no entry of its own, by design.** Its readings land in the entries whose inductions produced them, and this section is the cross-path summary. Where a reading is taken with no human at the device, the device timestamp and the channel's mobile/DND state are marked **owed** in that entry rather than omitted.

### Retire when

**Never.** Every other section here retires when its code path goes away; this one asks whether a notification reaches a human, and the answer is a property of a phone, a Slack workspace and a notification setting, all three of which change without anything in this repo changing.

<a name="drill-w1"></a>

## Drill W1 — the node's stores restarted, bare and ordered, and its edge stopped — PROCEDURE

### What this proves

Three things about the observability node, `zcrypto-mon`, one leg each. Whether a bare `systemctl restart` of a store under a running Grafana pages: Grafana evaluates each rule every minute against the two stores, and a rule whose query cannot run pages in its error state unless its `execErrState` is `OK` ([`mon.md#mon-store-restart`](mon.md#mon-store-restart)), so a restart lasting seconds pages only if an evaluation falls inside it, and the reading decides whether `prometheus$` returns to the node's unattended-upgrades blacklist, `base_unattended_upgrades_package_blacklist` in `infra/ansible/host_vars/zcrypto-mon/vars.yml`. That the ordered restart, `mon-store-restart` itself, pages nothing and leaves every rule `health=ok`. And the order in which the node's edge going dark pages, `zcrypto-mon-ingest-dark` first and the per-host Alloy-dark pages after it, the order [`mon.md#zcrypto-mon-ingest-dark`](mon.md#zcrypto-mon-ingest-dark) rests on.

### Preconditions

- An attended window; standing rules above.
- The bridgehead and ops ship to the node, read by value: `uv run python infra/scripts/grafana-query.py --stack mon 'count by (host) (up{host!="zcrypto-mon", job="integrations/unix"})'` lists them, and the hosts it lists are the ones the last leg's per-host pages can come from. On a node no host ships to, `zcrypto-mon-ingest-dark` is already firing and the last leg measures nothing: record **`blocked`** with the reason.
- The node's rules read clean before the first restart, with `mon_get` as [`mon.md#mon-patch-pass`](mon.md#mon-patch-pass) step 5 defines it: `mon_get /api/prometheus/grafana/api/v1/rules | jq -r '[.data.groups[].rules[] | select(.health != "ok") | .name]'` prints `[]`. A rule in error before the induction would have its page booked as a restart's.
- `max(hc_checks_down_total) == 0` on Grafana Cloud, read by value immediately before: `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. The last leg can put the node's own healthchecks.io check down for one timer period, and `zcrypto-hcio-watchdog` is a fleet-wide aggregate (standing rules above). Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.
- The self-check's last journal line, `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'`, ends `-> pinged`. A line ending `no ping URL is set` is a check not yet minted: the last leg then puts no check down, and the entry says so.
- **Announced in the main channel beforehand**, naming the three pages the last leg can send there: the node's own healthchecks.io check, down for up to one timer period; `zcrypto-hcio-watchdog`, if the check stays down past its `for: 5m`; and `Ops · ERROR logs`, on ops' Alloy giving up a node-bound log batch about seven minutes into the stop (*Must fire* below).
- The previous induction reverted and verified by value.

### Induce

On the node (`ssh mon`), four legs in this order, each read before the next starts, and `date -u` beside each command: no rule carries the moment.

**Leg 1, Prometheus bare, three times, Grafana running.** Two restarts at any moment; the third timed to start one second before the next evaluation of `zcrypto-reconciler`, a group holding `for: 0s` Prometheus rules, so that an evaluation falls inside it; the group's next evaluation is its `lastEvaluation` on the rules endpoint plus its 60 s interval:

```
mon_get /api/prometheus/grafana/api/v1/rules | jq -r '.data.groups[] | select(.name == "zcrypto-reconciler") | "last=\(.lastEvaluation) interval=\(.interval)"'
```

Each restart is `sudo systemctl restart prometheus`, and each one's duration is read from its journal, the `Stopping` line to Prometheus's own ready line, `Server is ready to receive web requests`:

```
sudo journalctl -u prometheus --no-pager -o short-precise --since -30min | grep -E 'Stopping|Server is ready'
```

**Leg 2, Loki bare, once, Grafana running**, timed the same way against `zcrypto-ops`, which holds `for: 0s` Loki rules: `sudo systemctl restart loki` one second before that group's next evaluation, its duration from the `Stopping` line to Loki's own `Loki started` line, `sudo journalctl -u loki --no-pager -o short-precise --since -30min | grep -E 'Stopping|Loki started'`.

Each restart of legs 1 and 2 is read twice: the rules endpoint first, `mon_get /api/prometheus/grafana/api/v1/rules | jq -r '[.data.groups[].rules[] | select(.health != "ok") | "\(.name) \(.health)"]'`, once the store's ready line is in and before the group's next evaluation, its `lastEvaluation` plus its 60 s `interval`, at which a rule in error reads `ok` again; then the shadow channel for an error page, a message carrying the template's error block, which stays where it was sent. A restart silent on both reads is silent; one that paged is read for which rules. The Prometheus leg reads silent only when all three of its restarts did.

**Leg 3, the ordered restart**: [`mon.md#mon-store-restart`](mon.md#mon-store-restart) steps 1 to 4, Prometheus and then Loki in its step 2, Grafana stopped around them. Its step 4's report, `## Alerts firing` with neither `Rules not evaluating` nor `the rules API`, and a shadow channel without an error page are its reading.

**Leg 4, the edge**: with the stores and Grafana running, `sudo systemctl stop caddy`, held until the first `zcrypto-alloy-dark-*` page reaches the shadow channel, `zcrypto-alloy-dark-ops` or `zcrypto-alloy-dark-zaccess` for the hosts the precondition listed; then `sudo systemctl start caddy` at once. Nothing heavier: Caddy is the one public listener, and its stop is what the fleet's shippers see as the node gone while the node itself keeps evaluating.

### Must fire

Legs 1 to 3 have no *Must fire*: a page in leg 1 or 2 is the reading, and a page in leg 3 is a `fail`. Leg 4, on the node's clocks, into the shadow channel:

- `zcrypto-mon-ingest-dark` (critical, `metrics`) at ≈ **10 min** from the stop: `count(up{host!="zcrypto-mon"}) or on() vector(0)` reads 0 once the fleet's series go stale, ~5 min, then `for: 5m`, then up to the 60 s group interval. It must have fired before the first per-host page below, the order `zcrypto-mon-ingest-dark`'s section rests on; the entry says which order it saw.
- The node's copies of `zcrypto-hcio-watchdog` (critical, `metrics`) and of the six NoData rules drill C's ops half lists, seven pages in the shadow channel about a minute before `zcrypto-mon-ingest-dark`, their groups' ticks a phase apart from the `zcrypto-mon` group's, on the sum drill C derives for them: ops ships to the node unfiltered and the node holds the same groups, so the series ops alone carries, the healthchecks.io scrape's among them, go stale on the node with the edge. Grafana Cloud's copies see ops still shipping and stay quiet.
- `zcrypto-alloy-dark-ops` and `zcrypto-alloy-dark-zaccess` (critical, `metrics`), the first of them at ≈ **16 min**: the same staleness term, then `for: 10m`, then the interval. The hold ends at the first; the second may land after Caddy is back and resolves with the first.
- The node's healthchecks.io check, down for at most one timer period, and `zcrypto-hcio-watchdog` on Grafana Cloud possibly behind it, both in the main channel. The self-check pings on its timer, `OnCalendar=*:0/5:23`, the `node_common_selfcheck_on_calendar` that `infra/ansible/roles/mon/tasks/main.yml` passes to `node_common`'s `selfcheck` task file, and while a fleet sample is under five minutes old, the reach of `FLEET_QUERY` in `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`: its last ping, the last `-> pinged` line of the unit's journal before its first `-> not pinging`, falls between about a minute before the stop and five minutes after it, and the check goes down 20 min after that ping, its `timeout` 600 s + `grace` 600 s, unless the run 15 min after it finds Caddy back. A start at the first Alloy-dark page, ≈16 min after the stop, can miss that run: the check is then down until the first run after the start pings, at most one timer period, and Cloud's `zcrypto-hcio-watchdog` (`for: 5m` behind a 60 s scrape) pages the main channel if that period outlives its wait.
- `Ops · ERROR logs` (`zcrypto-ops-error-logs`, warning, `logs`) on Grafana Cloud, in the main channel, about **7 min** into the stop: ops' Alloy retries a node-bound log batch about ten times and then gives up, the count [`mon.md#zcrypto-mon-shipper-loss`](mon.md#zcrypto-mon-shipper-loss) states, logging `level=error msg="final error sending batch, no retries left, dropping data"` with `component_id=loki.write.mon`, and that rule reads ops' Alloy stream with `for: 0s`. It is the node's ingest, not ops', and the announcement says so.

Expected after the leg, not held for:

- `zcrypto-mon-shipper-loss` (warning, `metrics`) for `ops`, in the shadow channel, about **15 min** after Caddy returns: the dropped batches were counted on ops at the give-up, the counter's increase reaches the node with the WAL's replay once Caddy is back, then `for: 15m` and the interval; it holds up to its `[6h]` window. The bridgehead ships no logs and its samples were held, so it is not in it.
- The node's `zcrypto-capture-textfile-missing` (warning, `metrics`) staying Normal, nothing in the shadow channel: `count(node_reboot_required{host=~"zcrypto|zcrypto-red|ops"})` with evaluator `lt 3` reads 3 while the capture pair and ops ship to the node beside Grafana Cloud, as they do since the Alloy wave of 2026-10-07; once the three hosts' series are stale, ~5 min into the stop, its `noDataState: OK` reads Normal, and a count under 3 while their series go stale, or come back after Caddy, lasts far less than its `for: 20m`.
- The node's own copy of `Ops · ERROR logs` (`zcrypto-ops-error-logs`, warning, `logs`), in the shadow channel, once Caddy is back: ops' Alloy ships its own container stream to the node as `container="alloy"`, the give-up lines logged from ≈7 min into the stop sit in batches still being retried when Caddy returns at ≈16 min, and the rule reads that stream over `[15m]` with `for: 0s`, so the first evaluation after a delivered line fires it. A line whose own batch was given up on reaches no store, so the page may not come: the entry records whether it did. It is the same event as the main channel's page, read on the node.

### Operator action

Legs 1 to 3 are their own restore: the store comes back, and a rule in error returns to `health=ok` at its next evaluation. Leg 4's restore is `sudo systemctl start caddy` at the first Alloy-dark page, then by value from the workstation: the precondition's `count by (host)` read back to the same hosts; `zcrypto-mon-ingest-dark`, the two Alloy-dark rules, the node's watchdog copy and the six NoData rules, ten in all, back to **Normal** on the rules endpoint and the unhealthy list `[]`, `zcrypto-capture-textfile-missing` Normal throughout; the self-check's next line `-> pinged`, and the check up on healthchecks.io. `zcrypto-mon-shipper-loss` is read when it fires, not reverted: that section's step 4 records the gap.

### Record

Entry `W1`, its *host* clause opening with `zcrypto-mon`, with each leg's reading: the three Prometheus restarts and the Loki one, each with its duration from the journal, whether it spanned an evaluation, and which rules paged or none; the ordered restart paging nothing; leg 4's page times against ≈10 and ≈16 min and their order, the seven beside `zcrypto-mon-ingest-dark` named rule by rule; the check's down and up times from healthchecks.io and whether the watchdog paged; the `Ops · ERROR logs` page time; the shipper-loss page; the textfile rule's clear and re-fire, and whether the node's `Ops · ERROR logs` copy fired.

The Prometheus leg decides the blacklist: three silent restarts keep it empty, the entry saying so; one page puts `prometheus$` back into `host_vars/zcrypto-mon/vars.yml` in a pull request of its own, named in the entry's *follow-ups*, the entry naming the rule that paged and the comment beside the variable re-trued in the same change. A page in leg 3 is `fail`: the ordered restart is what `mon-store-restart` and the role's handlers rest on.

### Retire when

`zcrypto-mon-ingest-dark` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/mon/handlers/main.yml` no longer carries the handler `stop grafana around a store restart`.

<a name="drill-w2"></a>

## Drill W2 — the node powered off for thirty minutes — PROCEDURE

### What this proves

That the node's death reaches a person while the node pages the shadow channel alone, through its healthchecks.io check and then Grafana Cloud's `zcrypto-hcio-watchdog`, and what a thirty-minute outage costs per plane: the metrics the shippers hold in their WAL and replay, and the log lines they retry and then drop, which nothing recovers. The figure lands in [`mon.md#mon-dark`](mon.md#mon-dark).

### Preconditions

- An attended window; standing rules above.
- The node's check minted and pinging: the self-check's last journal line (drill W1's read) ends `-> pinged`, and the `zcrypto-mon` check reads up on healthchecks.io. A line ending `no ping URL is set` is a check not yet minted, with no native page to time: record **`blocked`** with the reason.
- `max(hc_checks_down_total) == 0` on Grafana Cloud, read by value immediately before: `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. `zcrypto-hcio-watchdog` is in this drill's *Must fire* with a number and is a fleet-wide aggregate (standing rules above): not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.
- The hosts that ship to the node, read by value and written down, since the readings below take each by name: `uv run python infra/scripts/grafana-query.py --stack mon 'count by (host) (up{host!="zcrypto-mon", job="integrations/unix"})'`.
- The node's rules read clean (drill W1's read) and the shadow channel quiet of error pages: a page at boot is a reading, and it has to be this drill's.
- **Announced in the main channel beforehand**: the check's own page, `zcrypto-hcio-watchdog` about 7 min behind it, and `Ops · ERROR logs` about seven minutes in, as drill W1's leg 4 derives them.
- The previous induction reverted and verified by value.

### Induce

In the Linode Cloud Manager, on the Linode `zcrypto-mon`'s page, **Power Off**, with `date -u` on the workstation beside the click; thirty minutes later, **Power On**, timestamped the same way. Nothing from inside the host: the induction is the provider's, as a lost host's would be. Nothing on the fleet is touched.

### Must fire

- The `zcrypto-mon` check pages natively at its own `timeout` 600 s + `grace` 600 s = **20 min from its last clean ping**, through healthchecks.io's own Slack integration. The self-check pings on `OnCalendar=*:0/5:23`, so the last ping falls within five minutes before the power-off and the page lands 15 to 20 min after it.
- `zcrypto-hcio-watchdog` (critical, `metrics`) on Grafana Cloud, in the main channel, ≈7 min behind the check (standing rules above), its `Pending` `activeAt` read while pending and shown to postdate the induction.
- `Ops · ERROR logs` (warning, `logs`) on Grafana Cloud, in the main channel, about 7 min into the outage, on ops' Alloy's give-up line, as drill W1's leg 4 derives it.
- Nothing from the node for the whole outage, and the shadow channel's silence is not an all-clear: [`mon.md#mon-dark`](mon.md#mon-dark) is the page for those minutes.
- At boot, no error page: Grafana's unit waits for both stores to answer ready, the `ExecStartPre` lines of `infra/ansible/roles/mon/templates/grafana-server.dropin.conf.j2`, so the first evaluation after boot has its stores.

Expected after the boot, not held for: `zcrypto-mon-shipper-loss` (warning, `metrics`) for each host that ships logs to the node, `ops` while the bridgehead ships none, about 15 min after the node takes that host's metrics again, as in drill W1's leg 4.

### Operator action

At thirty minutes, **Power On**. Then, from the workstation: [`mon.md#zcrypto-mon-reboot-pending`](mon.md#zcrypto-mon-reboot-pending) step 2's five `active` reads; the rules endpoint's unhealthy list `[]` (drill W1's read); the self-check's next line `-> pinged`, and the check up on healthchecks.io; and [`mon.md#mon-store-restart`](mon.md#mon-store-restart) step 5, the silences re-read in the node's UI, since a Grafana that lost power may have lost the last fifteen minutes of them.

Then the three readings, between an hour and ninety minutes after the power-on, so that a `[2h]` window holds the whole outage and the shippers' WAL has drained:

- **The Cloud leg shows no gap**: `uv run python infra/scripts/grafana-query.py 'count_over_time(up{host="<host>", job="integrations/unix"}[2h])'` for each host the precondition listed reads 120 give or take an edge sample, the 60 s scrape's count over two hours.
- **The node's replay**: the same query with `--stack mon`, the same reading for each host; the samples scraped during the outage were held in each shipper's WAL, up to eight hours, and re-sent.
- **The lines lost**: `uv run python infra/scripts/grafana-query.py --loki 'sum(count_over_time({host="ops", container!="liquidations"}[2h]))'` and the same with `--stack mon`; Cloud's count minus the node's is the figure. `liquidations` is the poller's own push, which reaches Grafana Cloud alone until the cutover hands it over, so counting it would read two hours of it as lost. The figure goes into [`mon.md#mon-dark`](mon.md#mon-dark)'s first slot.

Read on return for misfires, by drill C's rule: `zcrypto-mon-retention-by-size` and `zcrypto-mon-shipper-loss`, the `zcrypto-mon` group's `increase()` rules, are the node's candidates blind to a first sample after a gap.

### Record

Entry `W2`, its *host* clause opening with `zcrypto-mon`: the power-off and power-on times; the check's page time from healthchecks.io against 20 min from its last ping, the last ping quoted from the check; the watchdog's `Pending` `activeAt` and its page; the `Ops · ERROR logs` page; the boot's reads, and whether a page came at boot; the three readings, hosts by name; a silence lost, if one was. The lines-lost figure is written into [`mon.md#mon-dark`](mon.md#mon-dark) in the same change.

### Retire when

The `zcrypto-mon` check is absent from the healthchecks.io checks listing, or `infra/ansible/roles/mon/tasks/main.yml` no longer includes `node_common`'s `selfcheck` task file.

<a name="drill-w3"></a>

## Drill W3 — the node rebuilt from nothing — PROCEDURE

### What this proves

That a lost node is rebuilt from the repository with no UI step and no secret copied by hand, the bootstrap, one converge whose preview passes on the fresh host, and one push, and how long the node's rules go unevaluated from the loss to the first evaluated rule, the exposure [`mon.md#mon-dark`](mon.md#mon-dark) quotes.

### Preconditions

- An attended window; standing rules above; drill W2 passed before it.
- In the Cloud Manager: the Linode `zcrypto-mon` with Backups enabled, read on its Backups tab, and the firewall `zcrypto-mon` attached to it with inbound Accept TCP `10022` and TCP `443` for both families and ICMP, the state the node's first converge left it in.
- The owner's master key in the agent, `ssh-add -l` listing it, and the GPG agent unlocked; not through `run.sh`, whose throwaway agent excludes the master key. The bootstrap connects as root on port 22 with that key, which the rebuild dialog takes as root's.
- The cached token left where it is, `~/.config/zcrypto/grafana-mon.vault.yml`: the converge must find it refused by the new Grafana and re-mint it, a must-hold below. Deleted first, that reading becomes the absent-token branch, a different one.
- `max(hc_checks_down_total) == 0` on Grafana Cloud, read by value immediately before, as drill W2 reads it; the check up and the self-check's last line `-> pinged`.
- **Announced in the main channel beforehand**: the check's own page, `zcrypto-hcio-watchdog` about 7 min behind it, and `Ops · ERROR logs` about seven minutes in, as drill W2's are. The shadow channel's standing NoData pages for the hosts not yet shipping return with the push and are not this drill's.
- The previous induction reverted and verified by value.

### Induce

The rebuild's start is the firewall step's timestamp, `date -u` on the workstation beside each click.

1. **The firewall**: in the Cloud Manager, add to `zcrypto-mon` an inbound Accept TCP `22` rule for IPv4 and for IPv6 from all sources. The bootstrap connects as root on port 22, and the node's first converge removed that rule.

2. **The rebuild**: on the Linode's page, **Rebuild** from the Debian 13 image, the owner's master key as root's, Backups left enabled. Then in LISH, the new host key's fingerprint, `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, and on the workstation the stale line removed, `ssh-keygen -R '[zcrypto-mon.zhaow.me]:10022'`, since the alias `mon` connects on 10022 and its known host has changed.

3. **The bootstrap, the alias and the converge**, from the repo root, in that order; the deploy key `~/.ssh/deploy_zcrypto-mon_ed25519` and the `Host mon` stanza are the workstation's from the node's first build and need no step:

   ```
   (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-mon -e ansible_user=root -e ansible_port=22)
   ssh mon 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon
   ```

   The bootstrap's recap reads `failed=0 unreachable=0`, its re-bootstrap probe finding no `zcrypto-deploy`; the refusal firing means the Linode was not rebuilt: stop, and do not answer it with `-e rebootstrap=true`. The first `ssh mon` prompts with the fingerprint read in LISH, then prints the provider-assigned hostname and `sudo-ok`. The converge names no tag, since each role of the node's play is wanted: its preview's recap reads `failed=0`, with the installs, the unit starts and the token task `skipping`, and no step is re-run; the real pass's recap reads `failed=0 unreachable=0`, and its token task, under `no_log`, reads `changed`. Then remove the TCP `22` rule from the firewall in the Cloud Manager: the rule list reads TCP `10022`, TCP `443` and ICMP again.

4. **The push**: [`mon.md#mon-push`](mon.md#mon-push) step 1 in its step 2 form, with the shadow webhook, since the contact points are minted anew. Its first line reads `stack=https://zcrypto-mon.zhaow.me` and `skip-groups=<none>`.

5. **The first evaluated rule**: from the push's last line, read the rules endpoint each ten seconds until this prints a time, the end of the measurement: `mon_get /api/prometheus/grafana/api/v1/rules | jq -r '[.data.groups[].rules[] | select(.health == "ok" and (.lastEvaluation | startswith("0001") | not)) | .lastEvaluation] | min // "none yet"'`, with `mon_get` as [`mon.md#mon-patch-pass`](mon.md#mon-patch-pass) step 5 defines it, reading the re-minted token from the cache. A rule scheduled and not yet evaluated reads `health=ok` with the zero `lastEvaluation`, which the filter sets aside.

### Must fire

Must hold, each a **`fail`** when it does not, where an induction that did not land is `blocked`:

- The preview passes on the fresh host with no step re-run.
- No UI step between the rebuild and the first evaluated rule: the Cloud Manager's clicks are the provider's, not Grafana's.
- The cached token is refused and re-minted into the cache by the converge, the token task reading `changed`, and `stat -c '%a %s' ~/.config/zcrypto/grafana-mon.vault.yml` reads `600` with a non-zero size afterwards.
- Each rule evaluated and `health=ok` by 2 × the 60 s group interval (standing rules above) from the push's last line, its first evaluation inside one interval and a read one interval later seeing it: drill W1's unhealthy read, its `select` widened by `or (.lastEvaluation | startswith("0001"))`, prints `[]`.

Must fire, in the main channel:

- The `zcrypto-mon` check, natively at its `timeout` 600 s + `grace` 600 s from its last ping, 15 to 20 min after the rebuild as in drill W2; the node pings nothing from the rebuild until the push schedules its rules, since the self-check withholds its ping with no rule scheduled (`rules_fresh` in `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`), and the first ping after the push brings it up.
- `zcrypto-hcio-watchdog` (critical, `metrics`) ≈7 min behind it, its `Pending` `activeAt` read while pending.
- `Ops · ERROR logs` (warning, `logs`) about 7 min into the rebuild, on ops' Alloy's give-up line, as drill W1's leg 4 derives it.

Expected after the push, not held for: `zcrypto-mon-shipper-loss` (warning, `metrics`) for `ops`, in the shadow channel, about 15 min after the node takes ops' metrics again, as in drill W1's leg 4; and the shadow channel's NoData pages for the hosts not yet shipping, as the node's first push left them.

### Operator action

The induction is its own restore. Confirm by value: [`mon.md#mon-push`](mon.md#mon-push) step 3; `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`, whose real pass reads `changed=0 failed=0`, the re-minted token kept; drill W2's `count by (host)` read on the node listing the hosts W2 wrote down; the self-check's next line `-> pinged`, and the check up on healthchecks.io; the firewall's rule list without TCP `22`; and `ssh mon hostname` printing `zcrypto-mon`. The node's Loki starts empty, so the daily pass's history read covers nothing before the push, and the seven days are counted again as [`mon.md#mon-dark`](mon.md#mon-dark) counts them.

### Record

Entry `W3`, its *host* clause opening with `zcrypto-mon`: the rebuild's start and the first `health=ok` rule's `lastEvaluation`, their difference the measurement; each must-hold with its reading, the token task's `changed` among them; the check's page, the watchdog's `Pending` `activeAt` and page, the `Ops · ERROR logs` page; the day whose comparison restarts. The measurement is written into [`mon.md#mon-dark`](mon.md#mon-dark)'s second slot in the same change; the converges' rows are in `docs/reference/deploy-log.jsonl` as `converge.sh` appended them.

### Retire when

`infra/ansible/roles/mon/tasks/token.yml` no longer exists, or `infra/ansible/host_vars/zcrypto-mon/vars.yml` is absent from the tree.

<a name="drill-w4"></a>

## Drill W4 — the secondary's shipper stopped, read on the node — PROCEDURE

### What this proves

That the node's dead-men agree with Grafana Cloud's on a real host: with the secondary's Alloy stopped, `up{host="zcrypto-red"}` goes absent on the node and not to 0, and the node's copy of `zcrypto-alloy-dark-capture-secondary` reaches the shadow channel on the timing Cloud's copy pages the main channel. Drill K's instrument and hold, on drill C's secondary half.

### Preconditions

- An attended window; standing rules above; after the Alloy wave (`.claude/skills/zcrypto-bump-alloy/SKILL.md`) and its verifications, on a later day than its last converge, inside rung 2's box and outside its day's window ([`engine-procedures.md#engine-rung-2-box`](engine-procedures.md#engine-rung-2-box), [`engine-procedures.md#rung-2-the-day-s-window`](engine-procedures.md#rung-2-the-day-s-window)), once `zcrypto-red` ships to the node: `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-red"})'` reads above 0, and the same query on Grafana Cloud without `--stack`. Both counts are written down; the restore is read against them.
- **The secondary is a venue-facing host**: the Kraken maintenance feed read at planning time and again immediately before the stop (standing rules above).
- **The secondary only** (set: the rule's, `.claude/rules/fleet-deploys.md`; count: `infra/scripts/count-list.sh drills-on-the-primary`). The capture daemon keeps running, as drill C's *Induce* states; the primary is not touched.
- `max(hc_checks_down_total) == 0` on Grafana Cloud, read by value immediately before: `zcrypto-hcio-watchdog` must stay quiet here, and a check left down makes that unverifiable. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.
- The node's rules read clean (drill W1's read), and nothing else induced.
- The previous induction reverted and verified by value.

### Induce

On the secondary (`ssh red`), with `date -u` beside it:

```
sudo docker stop grafana-alloy
```

### Must fire

- `zcrypto-alloy-dark-capture-secondary` (critical, `metrics`) at ≈ **16 min** on both stacks, `for: 10m` + 60 s + ~5 min staleness: the node's copy into the shadow channel and Cloud's into the main channel, each `activeAt` read from its own stack's rules endpoint. On the node, `uv run python infra/scripts/grafana-query.py --stack mon 'up{host="zcrypto-red"}'` reads `(no series)` once the series are stale, and not 0; `count(up{host="zcrypto-red"}) or on() vector(0)`, the rule's own query, reads 0 by its fallback.
- `zcrypto-capture-textfile-missing` (warning, `metrics`) on both stacks at ≈ **26 min**, drill C's secondary half: a **value** page, `count(node_reboot_required{host=~"zcrypto|zcrypto-red|ops"})` with `lt 3` and `for: 20m`, past a hold ended at ≈16 min; it pages where the hold overruns, and its summary names the capture hosts beside ops.
- `zcrypto-hcio-watchdog` quiet on Grafana Cloud: no check is fed by that host's Alloy, and the node's own check keeps pinging while ops and the other hosts ship.
- `zcrypto-fleet-daemon-restarted` (warning, `metrics`) on both stacks if the restore lands before about 13 min: `changes(process_start_time_seconds{…}[15m]) > 0` with `for: 2m`, whose hosts include `zcrypto-red` and whose jobs include the Alloy's `integrations/self`, as drill K states.

Read on 2026-10-08, drill-log entry `W4`: both copies of `zcrypto-alloy-dark-capture-secondary` `Alerting` with `activeAt` 16:18:40Z, 15 min 16 s from the stop on both stacks, against the ≈16 min above; on the node `up{host="zcrypto-red"}` `(no series)`, absent and not 0, and the rule's own query 0 by its fallback; `zcrypto-capture-textfile-missing` `Alerting` on both stacks from 16:29:00Z, 25 min 36 s from the stop against the ≈26 min above, the hold having run 29 min 23 s to the 16:32:47Z restore; `zcrypto-hcio-watchdog` quiet; `zcrypto-fleet-daemon-restarted` never alerted, read inactive on both stacks at 17:08:10Z, past its `for: 2m`, and no misfire on return.

### Operator action

**Hold to the Alloy-dark page on both stacks**, not to an earlier page; a restore before about 13 min trips `zcrypto-fleet-daemon-restarted`, which is named in the entry and not chased. Then drill K's recipe:

```
sudo docker restart grafana-alloy
```

The restore restarts the same container on the same image; a recreate is the host's `--tags alloy` converge, attended, and not this restore. Read the recovery by value: `sudo docker ps --format '{{.Names}} {{.Status}}'`; `count(up{host="zcrypto-red"})` back to the precondition's reading on both stacks; both copies of the rule back to **Normal**. **Re-true the `since` cell of the secondary's `alloy` row in [`fleet-pins.md`](../../docs/reference/fleet-pins.md) in the same step** (standing rules above): `sudo docker inspect grafana-alloy --format '{{.State.StartedAt}}'`.

### Record

Entry `W4`, its *host* clause opening with `zcrypto-red`: both copies' `activeAt` against ≈16 min, each with its channel; the absent-not-0 read on the node; the collateral, `zcrypto-hcio-watchdog`'s silence and `zcrypto-capture-textfile-missing` if the hold overran; misfires on return by drill C's rule, with the window's end past each candidate's `for`; the `since` cell re-trued.

### Retire when

`zcrypto-alloy-dark-capture-secondary` is absent from `infra/grafana/alerts.yaml`, or `infra/scripts/grafana_auth.py`'s `STACKS` holds one stack, so there is no second copy to agree with.

<a name="proven-tier-reverification"></a>

## Re-verifying an already-proven scenario — PROCEDURE

### What you are seeing

You are deciding whether a scenario that has **already** been proven, by a drill or by a real incident, needs another run. It usually does not.

### What it means

**A proven scenario is re-verified only when the code path it proved has changed since the proof.** Not on a schedule, and not because the proof is old: a drill that re-exercises an unchanged path costs an attended window and buys nothing, and on the capture side it costs a fault induced on live, unbackfillable data.

The record of a proof is `docs/reference/drill-log.md`, one entry per run under the scenario id, for every run since the log exists; the proofs that predate it — F, H, J, L, M and T — are in the matrix of `docs/open-topics/archive/T0049-go-live-drill-matrix-day2-runbook.md`. Read what was proved and when there, not here. The scenarios with a section above rest on the code path that section's *Retire when* names. The scenarios with no section here:

- **F**, WS loss on the capture side: [`capture.md#zcrypto-capture-all-streams-silent`](capture.md#zcrypto-capture-all-streams-silent).
- **H**, the capture daemon stopped, and the host down.
- **J**, an engine cycle failure with the engine dead. Its `/fail` route is drill J′ above.
- **L**, healthchecks.io dark, or a check down, in both directions: [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog).
- **M**, a Kraken maintenance colliding with a converge: the standing rule is `.claude/rules/fleet-deploys.md`, not a drill.
- **N**, a NAS archive-pull stall: its proof rests on a transport, and its procedure is below.
- **T**, an alert firing for something already over.

**Two scenarios from the original matrix are in no tier at all; they were considered and deliberately dropped.**

- **A reboot-window overlap check.** Both capture hosts are attended-reboot, so no automatic reboot window exists that could overlap another host's. `docs/reference/fleet.md` § Reboots holds the procedure, and [`hosts.md#zcrypto-capture-reboot-pending`](hosts.md#zcrypto-capture-reboot-pending) is the alert that exists precisely because a pending reboot waits for a human. There is nothing here a drill could induce.
- **Drills for the reconciler's phantom-splice guard and for the lost-trades detector.** Both are code guards with tests, not fleet failure scenarios; nothing on a host can be induced to exercise them. The splice guard is the detect-only default (`tests/test_archive_reconcile_command.py::test_detect_only_is_the_default_and_mints_nothing`) (no count command: a mode's name, not a quantifier; the test cited holds the default); the detector is `is_total_loss`'s `alive_witness` in `cli/archive/settle.py` (`tests/test_archive_settle.py::test_absent_trades_hour_is_not_a_loss_when_the_book_hour_proves_the_stream_was_alive`). Their coverage question is a test question and is answered where tests are.

### What to do

**N's proof rests on a transport, and that is what decides when it is next due.** `discovery.docker` and `loki.source.docker` are gone from every Alloy config; that container's lines reach Loki over the journald driver through `loki.source.journal` and its `journal_units` relabel (`infra/nas/config.alloy`). The dead-man itself is unchanged. N is next due when that transport changes. **N gets no section of its own**; this is where it lives.

**Read `max(hc_checks_down_total) == 0` by value immediately before the stop**: `uv run python infra/scripts/grafana-query.py 'hc_checks_down_total'`. `zcrypto-hcio-watchdog` can page at or after the restore, and as a fleet-wide aggregate it is already firing if an earlier drill left a check down. Not 0 ⇒ clear the down check first, or record **`blocked`** with the reason.

- **Induce**, on the NAS (`ssh nas`): `sudo /usr/local/bin/docker stop zcrypto-archive-pull`. **`docker` is at `/usr/local/bin/docker` on that host and is not on a non-interactive ssh `PATH`**: called bare it prints nothing and reads as "no containers" rather than "command not found". Stopping the **container** is the induction: the dead-man matches a clean `zcrypto archive pull` line from **any** channel inside it (no count command: `infra/grafana/alerts.yaml`'s `zcrypto-nas-archive-pull-stalled` expr holds it), so silencing one channel leaves it green.
- **Must fire, three pages**: [`nas.md#zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled) (critical, `metrics`), a `[3h]` no-clean-line window plus `for: 0s` plus the 60 s group interval ≈ **3 h 1 min after the last clean `pull complete … failed=0` line**, which is where the hold ends. The other two land roughly an hour ahead of it, because this container also runs the gate export and writes the ops writer's `.pull-status` gate: [`gate.md#zcrypto-gate-exporter-stale`](gate.md#zcrypto-gate-exporter-stale) (critical, `metrics`) at 7200 s + `for: 5m` + 60 s ≈ **2 h 6 min** from the last successful export; and `zcrypto-reconcile-source-lag` (`Reconciler · capture mirror lagging`, **warning**, `metrics`; `> 10800` with `for: 10m`), which fires on `source=primary` and `source=secondary` together because the NAS pull feeds both mirrors. **Do not triage on arrival ORDER**, and name both in the entry: an unnamed critical arriving mid-hold reads as a real fault and stops the chain on a healthy induction, and the warning's summary is the most alarming prose in the set.
- **The unpinged `zcrypto-gate-verify` check lands after the hold**, at `timeout` 3900 s + `grace` 7200 s = **3 h 5 min** from its last ping. The export sends that ping seconds before the cycle's last clean line, since the liquidations, panel and reconciled pulls follow it, so the check goes down about 4 min past the bound, with `zcrypto-hcio-watchdog` ≈7 min behind it at ≈3 h 12 min. Expect either at or after the restore rather than during the hold: the first export after the restore has to ping inside those 4 min, or the check goes down and the watchdog follows if it stays down past its `for: 5m`, both clearing on that ping. Name whichever paged in the entry.
- **Expect silence that proves nothing.** `zcrypto-gate-mismatch`, `zcrypto-gate-pull-lag` and `zcrypto-gate-streak-reset` stay quiet on **frozen** figures: the textfile persists and is still scraped, so `increase()`/`delta()` read 0 and the gauges hold their last values. The gate domain is suspended for the hold, not healthy.
- **Read `/archive/.pull-status`'s `ts_epoch` against the current epoch before the stop.** Over an hour old, wait out the next `pull complete` line and induce against a fresh one. That file is at most one loop period old when the stop lands (~1.2 h) and the ops overlay-writer's `MAX_STATUS_AGE` is 4 h, so it can age out **inside** this hold, after which that writer's fail-closed gate skips reconcile and backfill on every `:12`/`:42` cycle, and nothing pages to say it began (no count command: `roles/ops/templates/archive-pull.sh.j2`'s gate skips a cycle at rc 0). A crossing that happens anyway goes in the entry's *follow-ups* clause as the skipped cycles it is. **End the hold at the derived bound above; an overrun only buys more of them.**
- **Restore** with the recipe in [`nas.md#zcrypto-nas-archive-pull-stalled`](nas.md#zcrypto-nas-archive-pull-stalled), then read a `pull complete … failed=0` line back **naming the capture channels**: `sudo /usr/local/bin/docker logs zcrypto-archive-pull --since 4h`. The dead-man goes green on any single verified channel (no count command: `infra/grafana/alerts.yaml`'s `zcrypto-nas-archive-pull-stalled` expr holds it), so a bare clean line proves the mirror is being fed, not that the unbackfillable half is.

### Retire when

`docs/reference/drill-log.md` no longer exists: every rule above is about what gets written there, so with no log there is nothing to re-verify into.
