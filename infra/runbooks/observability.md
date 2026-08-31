# Observability — the telemetry planes themselves

You are here because **an alert fired in Slack**, because **a guard in the code pointed you here**, or because Grafana Cloud itself is dark and you opened [`#grafana-cloud-dark`](observability.md#grafana-cloud-dark) deliberately. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

These sections cover the instruments, not the things they measure: the four `grafana-alloy` containers that ship every metric and every journal line to Grafana Cloud, the node-exporter collectors inside them, and the direct-ship path (`cli/logging/ship.py`) by which the capture daemon, the engine and the liquidations poller push their own logs to Loki without touching Alloy at all. A rule here firing means a *signal* is missing or dishonest — read every other rule's silence as meaningless until it clears. The healthchecks.io dead-man checks are a separate, independent failure domain and are **not** part of this stack; the map of which check watches which daemon is in [`#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog).

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-alloy-dark-nas"></a>
<a name="zcrypto-alloy-dark-ops"></a>
<a name="zcrypto-alloy-dark-capture-primary"></a>
<a name="zcrypto-alloy-dark-capture-secondary"></a>

## zcrypto-alloy-dark — ALERT

### What you are seeing

A **critical** Grafana alert, one of four — `Fleet · Alloy dark — NAS` / `— Ops` / `— Capture primary` / `— Capture secondary`. The named host's `up` series has been absent from Grafana Cloud for over 10 minutes: `count(up{host="<host>"}) or on() vector(0)` fell below 1.

Severity is identical on all four deliberately — the responder's first moves are the same on every host. `noDataState` and `execErrState` are both `Alerting`, so a Grafana-side failure to evaluate this rule also pages rather than reading green.

Effective notice is ~15 minutes: Prometheus staleness (~5 min) plus the rule's `for: 10m`.

(The fifth sibling, `zcrypto-alloy-dark-zaccess`, covers the bridgehead, whose Alloy is a native apt install with a different procedure — it has its own section at `zaccess.md#zaccess-bridgehead-dark`.)

### What it means

**Telemetry-only.** No capture, no engine cycle and no archive work stops because of this. What stops is your ability to see any of it.

**Every other Grafana rule scoped to that host is blind while this fires, and their silence means nothing.** Read no green as reassurance until `up` is back.

What accumulates unseen differs by host:

| host | what goes dark with it |
| -- | -- |
| **capture primary** (`zcrypto`) | the unbackfillable L2 capture signals, on the host that also runs the engine and holds the live Kraken trade key |
| **capture secondary** (`zcrypto-red`) | the redundant L2 capture signals |
| **ops** | the panel/verify timer series, the liquidations poller signals, the reconcile and trade-backfill exporter families — expect their exporter-stale rules to double-page — and the healthchecks.io scrape, which makes `zcrypto-hcio-watchdog` read 999 |
| **NAS** | the gate metrics the soak verdict is read from, and the NAS archive-pull log stream |

**The direct-shipped daemon logs do NOT pass through Alloy.** The capture daemon, the engine and the liquidations poller push to Loki themselves (`--ship-logs`), so `zcrypto-capture-log-dead-*` and `zcrypto-ops-poller-log-dead` staying green while this fires is consistent, not contradictory. If they fire *too*, the host's egress or the host itself is down, not just Alloy.

**On ops the tighter clock is `zcrypto-hcio-watchdog`, not this rule** — `hc_checks_down_total` goes stale ~5 min after Alloy stops shipping, then the `vector(999)` fallback plus `for: 5m` pages at roughly 10 minutes total.

**This family sees "not shipping" and nothing else.** The alive-but-wedged state — Alloy up, its `up` series flowing, and its discovery frozen so a whole class of target silently stops being scraped — was the actual 2026-07-15/16 incident (recorded in the archived `T0048`). The rule that detected it, `zcrypto-alloy-docker-sd-wedged`, is **absent from `infra/grafana/alerts.yaml`**; it was retired with the docker-discovery path (spec 00068 D6/D8). **Nothing in the rule set re-detects that shape.** So when a specific family is missing while this rule reads Normal, do not conclude the transport is fine — prove the family by value with `grafana-query.py`, because `(no series)` is a FAIL and never a zero.

### What to do

1. **Is the host up at all?** `ssh zcrypto` / `ssh red` / `ssh hp` / `ssh nas`. No answer ⇒ this is a host incident, not an Alloy one; the host's healthchecks.io checks will speak in the other failure domain within their grace.
2. **Is the container running?** `sudo docker ps --filter name=grafana-alloy` — **on the NAS, `docker` is off the non-interactive ssh PATH, so always `sudo /usr/local/bin/docker …` for every docker command in this section.**
3. **Read the container's state with SCOPED fields only** — this container's environment holds the Grafana Cloud push credentials, so never `docker inspect … '{{json .Config}}'`, never `{{json .Config.Env}}`, never `docker exec … env`, never `docker compose config`:
   `sudo docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}} oom={{.State.OOMKilled}}'`
   `oom=true` ⇒ it hit its container memory cap (1 GiB on ops, 512 MiB on the other three); `fleet.md#zcrypto-fleet-alloy-memory-headroom` is the warning that precedes it.
4. **Read its own logs:** `sudo docker logs grafana-alloy --since 1h 2>&1 | tail -100`. A config parse error names the offending line; a remote_write auth failure names the credential.
5. **Restart it — safe, and the usual fix:** `sudo docker restart grafana-alloy`. It takes seconds, and the `alloy-data` volume preserves the remote_write WAL and the journal cursor across the replacement. The journal reader's `max_age = 48h` bounds the backfill: an outage longer than 48 hours permanently loses the older tail of the journal-carried logs. Note that in the incident record.
6. **A recreate is needed instead when the container is absent, or when its env / memory cap changed** — a config reload is an HTTP `POST /-/reload` that never re-reads container env: `cd /etc/zcrypto-capture/alloy && sudo docker compose up -d` on a capture host, `/etc/zcrypto-ops/alloy` on ops. **`sudo` is required** — `alloy-secrets.env` is mode 0600 owned by the `zcrypto-alloy` user, and an unprivileged `up -d` dies reading it *before* touching the container, so the old one keeps running and no new dark window opens. On the NAS, Alloy shares one compose project with `archive-pull` (`/volume1/docker/zcrypto-archive`), so a `compose up -d` there bounces the pull loop too — prefer `sudo /usr/local/bin/docker restart grafana-alloy`.
7. **A config fault is an attended converge, not a host edit.** Compare the deployed file to the repo (`sha256sum /etc/zcrypto-capture/alloy/conf/config.alloy` against `sha256sum infra/ansible/roles/capture/files/config.alloy`). Re-converging is an attended action with the user's word — load `.claude/skills/zcrypto-bump-alloy/SKILL.md` first; it carries the digest-drift assert (pass the **currently running** Alloy digest, and never an empty `-e …_digest=`, which counts as defined and renders a broken image ref), the primary's mandatory `--skip-tags engine -e converge_primary=true`, and the NAS's `-e nas_apply_compose=true`.

**Verify by value before you call it fixed** — the recipe is `zcrypto-bump-alloy` Step 3, and each check catches something the others do not:

- On the host, **after >60 s** (the scrape interval is 60 s, so a fresh container legitimately reports zero until its first scrape lands):
  `curl -s http://127.0.0.1:12345/metrics | grep -E '^prometheus_remote_storage_samples_(failed_total|pending|total)|^loki_write_(sent|dropped)_entries_total'`
  Want: `failed_total` 0, `samples_total` **climbing on a second read >60 s later**, `sent_entries` ≥ 1, `dropped` 0. A briefly non-zero `pending` is in-flight, not failure. None of these counters is admitted to Cloud — this is host-only.
- From the workstation: `uv run python infra/scripts/grafana-query.py 'count(up{host="<host>"})'` ≥ 1, and the rule back to **Normal**. That is the canonical proof. `(no series)` is a FAIL, never a zero.
- **A fresh Loki line for the host**, which is the only check that proves journald → `loki.source.journal` → parse → write end to end: query `{host="<host>", level=~".+"}` over the last 15 min. **Do not filter on `container="alloy"` in a short window** — Alloy logs at startup and then goes quiet, so that selector reads empty on a perfectly healthy host bumped 30 minutes ago.
- Host-specific: ops ⇒ `zcrypto-hcio-watchdog` back to Normal and `up{job="liquidations_app"} == 1`; NAS ⇒ the next `archive-pull` cycle logs `pull complete … failed=0` and `zcrypto_gate_*` series still arriving; capture hosts ⇒ `up{job="capture_app"} == 1`, the capture container's `RestartCount` unchanged, and `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` > 0 — proving the fix never touched the unbackfillable daemon.

**Expect `zcrypto-fleet-daemon-restarted` to fire once for `job="integrations/self"`**, ~2–3 min after the restart. That is this action's own record; it self-clears within 15 minutes and needs nothing. A second firing on the same host with no action from you is a crash loop.

**On the ops host only, expect `zcrypto-ops-error-logs` to fire ~35 s after a recreate.** The outgoing container logs two `service=remotecfg … err="noop client"` errors on shutdown. Confirm it is that and not something real: those lines are timestamped ~200 ms *before* the new container's `StartedAt`, and `docker logs` on the new container shows zero errors.

### Retire when

All four uids — `zcrypto-alloy-dark-nas`, `-ops`, `-capture-primary`, `-capture-secondary` — are absent from `infra/grafana/alerts.yaml`, or `up` leaves the keep-regex in every host's `config.alloy` (`infra/ansible/roles/{capture,ops}/files/config.alloy`, `infra/nas/config.alloy`), at which point the series this rule reads no longer exists.

______________________________________________________________________

<a name="zcrypto-node-collector-failed"></a>

## zcrypto-node-collector-failed — ALERT

### What you are seeing

A **warning** Grafana alert (`Node · a node-exporter collector is failing`): `min by (host) (node_scrape_collector_success) < 0.5` for 15 minutes.

**The page names the host and not the collector** — `min by (host)` aggregates the `collector` label away. Finding which one is the first step below, and it is not optional.

The rule carries no host selector, so it covers every host whose keep-regex admits the series: both capture hosts, ops, the NAS and the bridgehead. All five run the same six collectors — `cpu`, `loadavg`, `meminfo`, `filesystem`, `netdev`, `textfile` (`set_collectors` in each `config.alloy`). Baseline is 1 everywhere.

### What it means

A `0` means that collector errored on its last scrape, so **its whole metric family goes quietly absent** — and every rule keyed on those series then evaluates NoData, which this fleet maps to OK.

**A failed collector silently disarms the rules that depend on it.** Treat this page as "N rules on this host are switched off right now" until you know which N. From `infra/grafana/alerts.yaml`, the dependents are:

| failed collector | rules it disarms |
| -- | -- |
| `filesystem` | `zcrypto-capture-disk-low`, `zcrypto-nas-disk-low`, `zaccess-disk-high` — the disk alarms |
| `textfile` | `zcrypto-capture-textfile-unreadable`, `zcrypto-reboot-probe-stale`, `zcrypto-capture-clock-exporter-stale`, `zcrypto-oneoff-textfile-stale`; on the NAS the whole `zcrypto_gate_*` family and its five gate rules; on the bridgehead `zaccess-tunnel-stale` and `zaccess-cert-expiring` |
| `loadavg` | `zcrypto-capture-load-high`, `zcrypto-ops-load-high`, `zcrypto-nas-load-high` |
| `cpu` | `zcrypto-capture-load-high` again — `cpu` supplies its per-core denominator |
| `meminfo`, `netdev` | no alert rule reads them today; the panels go blank |

`zcrypto-capture-textfile-missing` is the one exception that still bites: it is shaped as `count(node_reboot_required{…}) < 2`, so a capture host losing its textfile collector drops the count to 1 and that rule fires on its own.

**This is the rule that keeps the other rules honest.** Its own silence is not proof of anything either — if the host's Alloy is dark, this rule is blind too, and `zcrypto-alloy-dark-*` owns that.

### What to do

1. **Name the collector — do this first, everything else depends on it:**
   `uv run python infra/scripts/grafana-query.py 'node_scrape_collector_success == 0'`
   The `collector` label on each returned row is the answer, and the `host` label confirms which machine. `(no series)` here is a FAIL, not a clean bill: it means the query could not read the family at all, so check `count(up{host="<host>"})` next.
2. **Write down which rules are disarmed** from the table above, before you start fixing — that list is what you must re-verify at the end, and it is what you are flying without in the meantime.
3. **Read Alloy's own logs on the named host:** `sudo docker logs grafana-alloy --since 1h 2>&1 | grep -iE 'collector|error'` (NAS: `sudo /usr/local/bin/docker logs …`; the bridgehead runs Alloy as a native unit, so `sudo journalctl -u alloy -n 200 --no-pager` there).
4. **Go to the collector's own cause:**
   - `textfile` — a `.prom` file in the textfile directory is unreadable or malformed. On the capture hosts that is `/var/lib/zcrypto-node-textfile`. Check the modes: the collector runs as the non-root `zcrypto-alloy` user, and a producer script that leaves a file 0600 makes it unreadable — a `chmod` on the host is undone by the next run, so the fix is the script in the repo plus a converge.
   - `filesystem` — a mount the exporter cannot stat. A hung NFS mount is the classic one on ops and the NAS; the tell is `df` itself hanging. `mount | grep nfs`, then `df -h` in a separate shell you are willing to lose.
   - `cpu` / `loadavg` / `meminfo` / `netdev` — the `/host/proc`, `/host/sys` or rootfs mounts are missing after a compose edit. Check them with a **scoped** inspect: `sudo docker inspect grafana-alloy --format '{{json .Mounts}}'` — never `.Config`, never `.Config.Env`.
5. **Fix the underlying mount or file.** Alloy needs no restart for a transient error — the next scrape recovers on its own. `sudo docker restart grafana-alloy` only if the exporter itself is wedged; it is telemetry-only and the WAL survives.
6. **Verify by value, twice:** `grafana-query.py 'min by (host) (node_scrape_collector_success{host="<host>"})'` reads 1, **and** the dependent family is actually back — e.g. `node_filesystem_avail_bytes{host="<host>"}` returns rows. `(no series)` on the second read means the collector reports success while shipping nothing, which is the failure this rule cannot see.

### Retire when

`zcrypto-node-collector-failed` is absent from `infra/grafana/alerts.yaml`, or `node_scrape_collector_success` no longer appears in the keep-regex of any host's `config.alloy` — at which point the series does not exist and the rule can only read NoData.

______________________________________________________________________

<a name="zcrypto-logship-lines-dropped"></a>
<a name="zcrypto-logship-worker-stalled"></a>

## zcrypto-logship — ALERT

### What you are seeing

One of two **warning** Grafana alerts on the direct-ship log path, and **which one fired tells you which fault it is**:

- **`Logs · lines dropped before reaching Loki`** (uid `zcrypto-logship-lines-dropped`) — `increase(zcrypto_logship_dropped_lines_total[6h]) > 0`, held 15 min. Log lines were **discarded**. Measured baseline is zero on every host.
- **`Logs · the shipping worker has stopped cycling`** (uid `zcrypto-logship-worker-stalled`) — `time() - zcrypto_logship_last_cycle_timestamp_seconds > 300`, held 10 min (so ~15 min of real staleness). The shipper thread has not completed a cycle.

Neither rule carries a host selector, so both cover every direct-shipping daemon on the fleet. The `host` and `job` labels on the page name which: `capture_app` on `zcrypto` or `zcrypto-red`, `engine_app` on `zcrypto`, `liquidations_app` on `ops`.

### What it means

**This is the one fault that makes other alerts unreliable.** Every Loki-based rule for the affected daemon — `zcrypto-capture-error-logs`, `zcrypto-capture-log-dead-*`, `zcrypto-engine-error-logs`, `zcrypto-engine-log-dead`, `zcrypto-ops-error-logs`, `zcrypto-ops-poller-log-dead` — is now reasoning over an incomplete stream, so their silence no longer means healthy.

**The two rules are deliberately opposite, and each is blind to the other's fault. Read them together.**

*Dropped* means lines were rejected or evicted. `cli/logging/ship.py` increments `dropped_total` on exactly two paths: the in-memory ring overflowed (`RING_CAPACITY = 4096`, the deque evicts the oldest), or the push came back as a permanent rejection — any HTTP 4xx **other than 429** (`"retry" if (e.code >= 500 or e.code == 429) else "drop"`), which in practice is a revoked token, a wrong URL path, or entries aged past Loki's out-of-order window after a long outage.

*Stalled* means the worker is stuck. 5xx, 429 and network errors are retried with backoff from 1 s to 30 s, and `last_cycle_at` does **not** advance while a retry is in flight. The gauge deliberately advances on an idle cycle too, so a quiet daemon never looks stalled.

**A revoked credential leaves the stalled rule GREEN.** A rejected push still *completes* a cycle and still stamps `last_cycle_at` — that fault shows up only as dropped lines. Conversely, a stall drops nothing at first: it queues into the 4096-line ring and starts dropping only once the ring overflows, at which point both rules fire.

**These series do not exist at all for a daemon running without `--ship-logs`.** `(no series)` on `zcrypto_logship_last_cycle_timestamp_seconds` for a daemon that should be shipping is itself the finding — that container was started without the flag, which happens when its `logship-secrets.env` is missing at render time.

### What to do

1. **Identify the daemon** from the page's `host` and `job` labels: `capture_app` → `zcrypto-capture`, `engine_app` → `zcrypto-engine`, `liquidations_app` → `zcrypto-ops-liquidations`.
2. **Read that daemon's own stdout — it is unaffected by the shipping fault**, which is the whole point of the design: `ssh <host> 'sudo docker logs <container> --since 2h 2>&1 | grep -iE "loki|ship"'`. The handler logs `log shipping recovered; N lines dropped while unreachable` at WARNING on recovery, and a 4xx surfaces as the urllib error text.
3. **Never print the environment to find the credential.** No `docker inspect … '{{json .Config.Env}}'`, no `docker exec … env`, no `docker compose config` — the engine host carries the live Kraken trade key and the Loki push password as env vars. The credential's identity is knowable from the repo: it is `logship_loki_token`, vaulted, rendered into `logship-secrets.env` (mode 0600 root:root at `/opt/zcrypto-capture/logship-secrets.env` on the capture hosts, `/etc/zcrypto-ops/logship-secrets.env` on ops).
4. **Stalled**: this is reachability, not credentials. Check whether the same host's Alloy is also dark (`zcrypto-alloy-dark-*`) — both dying together points at host egress rather than at the shipper. Check `sudo ls -la` on the env file path above to confirm it exists at all.
5. **Dropped, with the worker cycling normally**: this is rejection. Read the daemon's stdout for the HTTP code. A dropped-lines fault caused by a rotated token is fixed by re-rendering the env file through a converge **and recreating the container** — `env_file` is read at container create, so a converge alone changes nothing. That recreate is an **attended** action with real cost: on a capture host it restarts the unbackfillable capture daemon, and on the primary it must not touch the engine outside its 4-hourly inter-cycle gap. Get the user's word, and load `.claude/rules/fleet-deploys.md` before scheduling it.
6. **Verify by value:** `uv run python infra/scripts/grafana-query.py 'increase(zcrypto_logship_shipped_lines_total{host="<host>"}[15m])'` > 0, and a fresh Loki line for that daemon — `{host="<host>", container="<capture|engine|liquidations>", level=~".+"}` inside the last 5 minutes. An empty Loki result is a FAIL, not a zero.

### Retire when

Both `zcrypto-logship-lines-dropped` and `zcrypto-logship-worker-stalled` are absent from `infra/grafana/alerts.yaml`, or `cli/logging/ship.py` no longer exists — i.e. the daemons' logs leave by some other route and `zcrypto_logship_*` is no longer produced.

______________________________________________________________________

<a name="zcrypto-capture-log-dead-primary"></a>
<a name="zcrypto-capture-log-dead-secondary"></a>

## zcrypto-capture-log-dead — ALERT

### What you are seeing

A **critical** Grafana alert, one rule per capture host — `Capture · log pipeline dead — Capture primary` (uid `zcrypto-capture-log-dead-primary`, host `zcrypto`) or `— Capture secondary` (uid `zcrypto-capture-log-dead-secondary`, host `zcrypto-red`).

Not one parsed capture-daemon log line, at any level, reached Loki from that host in 6 hours: `sum by (host) (count_over_time({host="<host>", container="capture", level=~".+"} [6h])) or on() vector(0)` is below 1.

There are two rules rather than one because Loki cannot synthesise a per-host zero — a single rule would go quiet for the wrong host. Each summary names its host in words; the `by (host)` grouping is inert at fire time, because the arm that actually crosses the threshold is the unlabelled `vector(0)` fallback.

`for: 0s`, and `noDataState` is `Alerting`: this is a fires-on-silence dead-man, so a Grafana-side failure to evaluate it pages rather than parking green.

### What it means

**`zcrypto-capture-error-logs` is blind on that host until this clears** — every ERROR and CRITICAL line the daemon emits is now invisible in Slack.

The capture daemon direct-ships its own logs (`--ship-logs`, labels exactly `{host, container="capture", level}` set at the source). **Alloy is not in this path**, so this rule firing while `zcrypto-alloy-dark-*` stays green is normal and expected, and the reverse is too.

Two causes, and they demand opposite responses:

- **The daemon is not running.** Then its healthchecks.io dead-man is also down — that is the independent domain, and it is the check to read first.
- **The daemon is running and not shipping.** Its stdout is unaffected, so `docker logs` still shows everything. This is the `--ship-logs` flag lost at render, the Loki credentials dead, or a label-scheme regression.

**The `zcrypto-logship-*` rules discriminate between the two shipping sub-cases**, and the discriminator is cheap: a *stalled* worker means the metric side is alive and retrying; a climbing *dropped* counter means lines are being rejected.

### What to do

1. **Read the host's healthchecks.io check first** (via `https://healthchecks.io`, or `zcrypto-hcio-watchdog` / `hc_check_up` in Grafana). Down ⇒ the daemon, not the logs. Confirm on the host: `ssh <zcrypto|red> 'sudo docker ps --filter name=zcrypto-capture; systemctl status zcrypto-capture --no-pager'`.
2. **Daemon up ⇒ compare stdout against Loki.** `sudo docker logs zcrypto-capture --since 30m 2>&1 | tail -50`. Lines flowing here and nothing in Loki means the shipping path is the fault, and nothing about the capture data itself is wrong.
3. **Separate "never started shipping" from "shipping is failing":**
   `uv run python infra/scripts/grafana-query.py 'zcrypto_logship_last_cycle_timestamp_seconds{host="<host>",job="capture_app"}'`
   `(no series)` ⇒ the daemon started **without** `--ship-logs`, which happens when its env file was absent at container-create time — confirm with `sudo ls -la /opt/zcrypto-capture/logship-secrets.env` (expect `-rw------- root root`). A fresh timestamp with `zcrypto_logship_dropped_lines_total` climbing ⇒ rejection; go to the logship section above.
4. **Never print the env to inspect the credential** — no `docker inspect … '{{json .Config.Env}}'`, no `docker exec … env`, no `docker compose config`. On the primary that container's host also carries the live trade key.
5. **Fixing it means recreating the capture container, which is an ATTENDED action.** Re-rendering `logship-secrets.env` takes a converge, and the new env only reaches the process on a container recreate — a restart of the unbackfillable capture daemon. Do not do it on your own initiative: get the user's word, read `.claude/rules/fleet-deploys.md`, do the **secondary first**, and on the primary pass `-e converge_primary=true --skip-tags engine` so the engine play is never pulled in.
6. **Verify by positive trace, never by the rule going quiet:** a Loki query `{host="<host>", container="capture", level=~".+"}` showing lines inside the last 5 minutes. An empty result is a FAIL. The rule returns to Normal within one evaluation after real lines land.

### Retire when

Both `zcrypto-capture-log-dead-primary` and `zcrypto-capture-log-dead-secondary` are absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/capture/templates/compose.yaml.j2` no longer renders `ZCRYPTO_LOG_SERVICE: capture` — i.e. the daemon's logs no longer arrive under `container="capture"` and this selector describes nothing.

______________________________________________________________________

<a name="zcrypto-ops-log-pipeline-dead"></a>
<a name="zcrypto-ops-poller-log-dead"></a>
<a name="zcrypto-ops-unit-parse-dead"></a>
<a name="zcrypto-ops-journal-transport-dead"></a>

## zcrypto-ops-log-plane — ALERT

### What you are seeing

One of four **critical** Grafana alerts on the ops node's log plane. All four are `for: 0s` with `noDataState: Alerting` — fires-on-silence dead-men, deliberately unable to park green. **Which one fired, and which others fired with it, is the whole diagnosis:**

| uid | title | query | window |
| -- | -- | -- | -- |
| `zcrypto-ops-log-pipeline-dead` | `Ops · log pipeline dead (no parsed lines)` | `{host="ops", container="alloy", level=~".+"}` | 6 h |
| `zcrypto-ops-poller-log-dead` | `Ops · poller log pipeline dead (no lines)` | `{host="ops", container="liquidations", level=~".+"}` | 6 h |
| `zcrypto-ops-unit-parse-dead` | `Ops · unit log parse dead (no leveled lines)` | `{host="ops", container=~"zcrypto-.*", level=~".+"}` | 26 h |
| `zcrypto-ops-journal-transport-dead` | `Ops · journal transport dead (no unit lines)` | `{host="ops", container="zcrypto-archive-pull"}` — **any** line, no level filter | 26 h |

Each is `count_over_time(...) or on() vector(0)` below 1. The `by (host)` / `by (host, container)` groupings are inert at fire time — the unlabelled fallback is what crosses the threshold — so each summary names its subject literally.

**Two corrections to the rule text, so you do not mis-size the problem.** `zcrypto-ops-journal-transport-dead`'s summary and comment call `zcrypto-archive-pull` "the hourly unit" and its window "a full day of hourly runs": the timer is `OnCalendar=*-*-* *:12,42:00` — **half-hourly**, doubled by T0058. The 26 h threshold is unaffected and still correct; only the prose is stale. And `zcrypto-ops-unit-parse-dead`'s summary says "the four zcrypto-\* ops units": the journal keep-regex in `roles/ops/files/config.alloy` keeps **five** — `archive-pull`, `verify-replay`, `verified-replay`, `panel-materialize`, `tape-bars`.

### What it means

The ops node carries **two independent log paths**, and these four rules exist because no single query can watch both:

- **Through Alloy**: the five `zcrypto-*.service` units and Alloy's own container stream, both read by one `loki.source.journal "zcrypto_units"` component off `/var/log/journal`, then labelled and level-parsed by two separate `stage.match` blocks (`{container=~"zcrypto-.*"}` for the units' Python logging shape, `{container="alloy"}` for Alloy's logfmt).
- **Bypassing Alloy entirely**: the liquidations poller direct-ships (`--ship-logs`, `ZCRYPTO_LOG_SERVICE=liquidations`), stamping `level` at the source.

**Read the combination, not the single page:**

- **`journal-transport-dead` + `unit-parse-dead`** ⇒ the **journal transport**. The reader is seeing nothing at all; the parse rule is a downstream casualty. Go to the transport steps.
- **`unit-parse-dead` alone** ⇒ the **parse stage regressed**. Lines are arriving without a `level` label, which means the `stage.regex` line-shape no longer matches what the CLI emits, or the container selector or label scheme changed. `zcrypto-ops-error-logs` now reads 0 = healthy forever for those units — that is the fault this rule exists to catch.
- **`log-pipeline-dead` too** ⇒ **Alloy itself** is dead or cannot reach Loki. Check whether metrics still flow (`node_load1{host="ops"}` freshness); if they are gone as well, `zcrypto-alloy-dark-ops` owns it.
- **`poller-log-dead` alone** ⇒ the poller's own ship path. The Alloy-side rules say nothing about it and never could.
- **All four** ⇒ the host or its egress, not any one component.
- **The staleness rules firing alongside** (`zcrypto-ops-archive-pull-stalled`, `zcrypto-ops-verified-replay-stale`, …) ⇒ the units are genuinely not running, and the log plane is reporting that correctly.

**What goes blind while any of these fire.** `zcrypto-ops-error-logs` is the only error channel for these streams — including the load-bearing `writer cycle SKIPPED (fail-closed gate)` warning, which exists in no container log at all because the orchestration script echoes it host-side. For the liquidations poller it is the *only* failure signal of any kind: the poller flips no exit-code metric.

**The margin on `log-pipeline-dead` is thin by design.** A healthy 6 h window measured 7 to 9 lines over 14 days — roughly 1.5 an hour. Read a low count on that stream as a reason to look, not as headroom.

**`log-pipeline-dead` is structurally blind to a journal-transport-only death** (Alloy alive, its own stream flowing, the journal reader wedged) — that is exactly why `journal-transport-dead` exists beside it.

### What to do

**First, on any of the four:** `ssh hp`, then `sudo docker ps --filter name=grafana-alloy` and
`sudo docker inspect grafana-alloy --format '{{.State.Status}} {{.RestartCount}} {{.State.OOMKilled}}'`
— **scoped fields only**: this container's environment holds the Loki push credentials, so never `'{{json .Config}}'`, never `.Config.Env`, never `docker exec … env`, never `docker compose config`.

**For `log-pipeline-dead` (Alloy's own stream):**

1. `sudo docker logs grafana-alloy --since 6h 2>&1 | tail -50` — Alloy is quiet but never silent while alive, so an **empty** tail is itself the finding.
2. `sudo journalctl CONTAINER_NAME=grafana-alloy --since -6h --no-pager | wc -l` — print the count. A non-zero count here with nothing in Loki isolates the fault to `loki.write`, not to the journal. **Run it with `sudo`**: unprivileged `journalctl` prints `-- No entries --` above a you-cannot-see-system-messages hint, and that empty result is a permissions artifact, not an idle unit.
3. `sudo docker logs grafana-alloy --since 1h 2>&1 | grep -i 'loki\|remote'` for the push error.

**For `journal-transport-dead` (the reader):**

1. `sudo journalctl -u zcrypto-archive-pull.service --since -2h --no-pager | wc -l` — must be > 0. **Print the count and confirm it is non-zero before trusting any downstream zero.** If it is 0, the unit is not running and the staleness rule owns it, not this one.
2. Is the journal persistent and inside the mount? `ls -ld /var/log/journal /var/log/journal/$(cat /etc/machine-id)` and `ls /run/log/journal`. A populated `/run/log/journal` with an empty `/var/log/journal` means journald flipped to **volatile** storage, which is outside the container's bind mount — Alloy then tails an empty directory forever, with no error. Check `grep -rE '^Storage=' /etc/systemd/journald.conf /etc/systemd/journald.conf.d/ 2>/dev/null`.
3. Is the gid still right? `getent group systemd-journal` against `grep -A3 group_add /etc/zcrypto-ops/alloy/compose.yaml`. Journal files are `root:systemd-journal` 0640 and the container runs as the non-root `zcrypto-alloy` user, so it needs the host's **numeric** systemd-journal gid, which the role derives at converge time — it drifts after an OS reinstall. A converge re-derives it.
4. Did a unit get renamed? `systemctl list-units 'zcrypto-*.service' --all` against the keep-regex in `infra/ansible/roles/ops/files/config.alloy` — `zcrypto-(archive-pull|verify-replay|verified-replay|panel-materialize|tape-bars)\.service`. A rename must touch that regex in the same change or its lines stop being kept.
5. `sudo docker logs grafana-alloy --since 1h 2>&1 | grep -i journal` for the reader's own errors.

**For `unit-parse-dead` (the level label):**

1. Query Loki **without** the level filter: `{host="ops", container="zcrypto-archive-pull"}` over the last 2 h. Lines present but carrying no `level` ⇒ the parse stage. No lines at all ⇒ this is the transport, above.
2. Compare a raw line against the regex: `sudo journalctl -u zcrypto-panel-materialize.service -n 3 -o cat`, against the `stage.regex` under `loki.process "parse"` in `infra/ansible/roles/ops/files/config.alloy`. The shape must be `YYYY-MM-DD HH:MM:SS,mmm` then an upper-case level then the message.
3. Check what moved: `git log -5 -- cli/logging infra/ansible/roles/ops/files/config.alloy`. A logging-format change in `cli/` breaks this stage silently, which is precisely the regression this rule was added for.
4. Note that unparsed lines are **not** lost — `action_on_failure = "skip"` keeps their journal capture time, so the scripts' own echoes still arrive; they simply carry no `level`.

**For `poller-log-dead` (the direct-ship path):**

1. `sudo docker ps -a --filter name=zcrypto-ops-liquidations` and
   `sudo docker inspect zcrypto-ops-liquidations --format '{{.State.Status}} {{.RestartCount}} {{json .Config.Entrypoint}}'`
   — the entrypoint must include `--ship-logs`. It is omitted at render time when the vaulted token is undefined, and the container then starts normally on stdout only. **Inspect the entrypoint, never `.Config.Env`.**
2. Separate "poller dead" from "ship path dead" **before** touching anything: `grafana-query.py 'zcrypto_liquidations_last_success_timestamp_seconds{host="ops"}'` — a fresh timestamp means the recorder is recording and only its logs are missing.
3. `sudo docker logs zcrypto-ops-liquidations --since 1h 2>&1 | tail` — lines here and nothing in Loki ⇒ ship path; read `zcrypto_logship_dropped_lines_total{host="ops"}` and the logship section above.
4. Restart: `cd /etc/zcrypto-ops && sudo docker compose up -d liquidations`. A rotated Loki token additionally needs the converge that re-renders `/etc/zcrypto-ops/logship-secrets.env`, because `env_file` is read at container create.

**Restarting Alloy** — `cd /etc/zcrypto-ops/alloy && sudo docker compose up -d`, `sudo` required (`alloy-secrets.env` is 0600 `zcrypto-alloy`). **A `config.alloy` edit is an attended converge, not a host edit**: load `.claude/skills/zcrypto-bump-alloy/SKILL.md`, which carries the digest-drift assert and refuses an ordinary converge after a config change.

**Verify by positive trace.** Re-run the failing rule's own Loki query and require lines, not an absence of alerts: Alloy logs on start, so `{host="ops", container="alloy", level=~".+"}` should return within minutes of a restart; the unit streams return at the next `:12`/`:42` archive-pull tick or the next panel run. `bash infra/scripts/ops-postverify.sh` bundles the ops-side checks in one command. An empty filtered query is never a zero — validate the filter before trusting its emptiness. Note in the incident record that the journal reader's `max_age = 48h` bounds what backfills: anything older than 48 h is permanently gone.

### Retire when

All four uids — `zcrypto-ops-log-pipeline-dead`, `-poller-log-dead`, `-unit-parse-dead`, `-journal-transport-dead` — are absent from `infra/grafana/alerts.yaml`; or, per rule, `loki.source.journal "zcrypto_units"` leaves `infra/ansible/roles/ops/files/config.alloy` (transport), the `{container=~"zcrypto-.*"}` `stage.match` leaves it (parse), the `{container="alloy"}` `stage.match` leaves it (pipeline), and `infra/ansible/roles/ops/templates/compose.yaml.j2` no longer renders `ZCRYPTO_LOG_SERVICE: liquidations` (poller).

______________________________________________________________________

<a name="zcrypto-hcio-watchdog"></a>

## zcrypto-hcio-watchdog — ALERT

### What you are seeing

A **critical** Grafana alert, `Fleet · healthchecks.io watchdog (check down, or hc.io dark)`: `max(hc_checks_down_total) or on() vector(999)` above 0, held 5 minutes.

**The value is the diagnosis, and there are only two readings:**

- **1 to N** — that many healthchecks.io dead-man checks are DOWN right now.
- **999** — Grafana has no reading from healthchecks.io at all. The scrape returned nothing, so the fallback supplied 999. This is not "999 checks down"; it is "the watchdog's own eyes went dark".

Panel 103 on the `zcrypto-fleet` board shows the same number, and `hc_check_up` names which check.

`noDataState` and `execErrState` are both `Alerting`. The 5-minute hold rides out a scrape blip; healthchecks.io's own grace periods already buffer check lateness, so a `down` here is post-grace and real.

### What it means

**The healthchecks.io dead-men are a separate failure domain from Grafana Cloud, deliberately** — merging them would let one outage take out alerting and dead-mans together. This rule is the Grafana half of a mutual watchdog. The other half is the ops `zcrypto-grafana-watchdog` timer, which probes `zcrypto2026.grafana.net/api/health` every 5 minutes, pings its check only on success and pings `/fail` on probe failure, so a dead Grafana pages through healthchecks.io instead.

**Value 1–N**: a dead-man fired in the other domain — a pinger stopped, or a job's own gate deliberately withheld its ping. healthchecks.io should have paged Slack itself; **this Grafana page is redundant on purpose**, so that a broken hc.io→Slack path cannot hide the event. Which check is down is the entire content of the page.

**Value 999**: the ops Alloy's scrape of healthchecks.io failed — ops Alloy down (then `zcrypto-alloy-dark-ops` is firing too), the read-only metrics key revoked or rotated, or healthchecks.io unreachable from the ops node. No check is known to be down, and **none is known to be up either**: every dead-man is unobserved from Grafana's side until this clears. healthchecks.io's own notifications still work, so the domain is degraded, not gone.

### The dead-man map

**Ten checks exist.** The repo records their node and application **tags** (from the archived `T0083`, where all nine app checks were retagged, plus the watchdog check added in the same window); it records display names for only some of them, and the hc.io dashboard is the authority on names. Use the tags to identify a row, then the runbook column for the daemon that owns it.

| node tag | application tag | what pings it | ping is withheld when | section owning the daemon |
| -- | -- | -- | -- | -- |
| `capture` | `capture-daemon` | the capture daemon on `zcrypto` (`HEALTHCHECK_URL`, every 60 s) | the WS is disconnected, **any** pair has an open gap, the disk watermark is breached, or the disk probe is unmeasurable | `capture.md#zcrypto-capture-all-streams-silent` and `capture.md#zcrypto-capture-stream-silent` |
| `capture-redundant` | `capture-daemon` | the same daemon on `zcrypto-red` | as above | `capture.md#zcrypto-capture-all-streams-silent` and `capture.md#zcrypto-capture-stream-silent` |
| `engine` | `engine-shadow` (check `zcrypto-engine-shadow`) | the engine cycle on `zcrypto` — pings on a completed cycle, pings `/fail` on a failed one | a cycle raised before either ping, so the check goes stale with **no** preceding `/fail` — read that as "the node is up but a cycle raised" | `engine.md#zcrypto-engine-cycle-stale` |
| `nas` | `gate-verify` (check `zcrypto-gate-verify`) | `gate-export` on the NAS — GET on a clean gate, GET `<url>/fail` otherwise | the gate is unclean or the export did not run | `gate.md#zcrypto-gate-exporter-stale` |
| `ops` | `archive-pull` | the half-hourly overlay-writer unit, on a clean cycle only | the fail-closed gate skipped the cycle, or the run failed | `ops-node.md#zcrypto-ops-archive-pull-stalled` |
| `ops` | `panel` | the panel-materialize unit | the run did not complete cleanly | `ops-node.md#zcrypto-ops-panel-exit-nonzero` |
| `ops` | `verify-replay` | the nightly canonical-archive sweep | the run produced no summary — **withheld independently of both Grafana rules for that timer** | `ops.md#zcrypto-ops-verify-replay-run-broken` |
| `ops` | `verified-replay` | the verified-replay unit | the run did not reach its clean-exit ping | `ops-node.md#zcrypto-ops-verified-replay-stale` |
| `ops` | `liquidations` | the liquidations poller (`LIQUIDATIONS_HEALTHCHECK_URL`) | the poller is not cycling, or its disk watermark is breached | `observability.md#zcrypto-ops-poller-log-dead` |
| `ops` | — (check `zcrypto-grafana-watchdog`) | the ops timer probing Grafana every 5 min; pings on success, `/fail` on probe failure; 600 s timeout / 600 s grace | Grafana is unreachable from ops, **or** the pinger itself died (then it pages by staleness) | this section |

**There is no dead-man check for the NAS archive-pull loop.** Nothing in the repo pings one — the NAS's only hc.io check is the gate one above. That pull loop's liveness is Grafana-only, through `nas.md#zcrypto-nas-archive-pull-stalled`, so a Grafana outage leaves it unwatched. Treat that as a known asymmetry, not as a check you have failed to find.

**A withheld ping is not always a broken daemon.** Several of the rows above withhold deliberately when the work was unsafe to certify — that is the design, and the daemon may be perfectly alive. Read the owning section before concluding anything died.

### What to do

1. **Name the check and read the value:**
   `uv run python infra/scripts/grafana-query.py 'hc_check_up' 'hc_checks_down_total'`
   Rows where `hc_check_up` is 0 are the down checks. `(no series)` here is the 999 case, not a clean bill.
2. **Value 1–N** ⇒ open `https://healthchecks.io` and read that check's **last ping time and its last event**. A received `/fail` and a plain silence mean different things — the engine row above is the clearest example. Then go to the owning section in the map, and treat this Grafana page as the redundant copy it is.
3. **`zcrypto-grafana-watchdog` DOWN while you are reading this page in Grafana** means the ops pinger or its probe failed, not Grafana: `ssh hp`, `systemctl status zcrypto-grafana-watchdog.timer --no-pager`, `sudo journalctl -u zcrypto-grafana-watchdog -n 20 --no-pager`.
4. **Value 999** ⇒ `ssh hp`, then `sudo docker ps --format '{{.Names}} {{.Status}}' | grep alloy` and `sudo docker logs grafana-alloy --since 15m 2>&1 | grep -i healthchecks`. A 401/403 means the read-only metrics key changed. **That key lives in TWO vault variables and they must match** — embedded in `hc_prometheus_metrics_path` (`group_vars/observed/`), which is what Alloy scrapes with, and on its own as `healthchecks_readonly_api_key` (`group_vars/all/`), which the daily pass reads; a rotation that touched only one leaves the other presenting a revoked key, and this page is what the Alloy half looks like when it lost. Only the metrics-path copy reaches this host: it lands in the container through `alloy-secrets.env`, so fixing THAT one takes a converge of the ops role plus an Alloy recreate, which is attended. The `group_vars/all/` copy is read from the workstation by file path and needs no converge at all — rewrite it and the daily pass (`infra/scripts/ops-daily.py`, the once-a-day fleet read) picks it up on its next run. A timeout or DNS error is egress from ops: `curl -fsS -m 10 -o /dev/null -w '%{http_code}\n' https://healthchecks.io/` from the ops node separates hc.io being down from ops being unable to reach it. **Never print the container environment to find the key** — no `'{{json .Config.Env}}'`, no `docker exec … env`, no `docker compose config`.
5. **Never silence this rule to stop the double-page.** The double is the design: healthchecks.io's own notification may be the broken half. Silence the check's own cause instead.
6. **Confirm by value:** `hc_checks_down_total` reads 0 **and** every `hc_check_up` reads 1. An empty result is a FAIL — it is the 999 state again, not a green fleet.

### Retire when

`zcrypto-hcio-watchdog` is absent from `infra/grafana/alerts.yaml`, or `prometheus.scrape "healthchecks"` is absent from `infra/ansible/roles/ops/files/config.alloy` — at which point `hc_checks_down_total` is no longer collected and the rule can only read its own fallback.

______________________________________________________________________

<a name="grafana-cloud-dark"></a>

## grafana-cloud-dark — PROCEDURE

### What you are seeing

Grafana Cloud itself is unreadable — the boards, the alert rules, and `infra/scripts/grafana-query.py` with them. **Every other section in this file ends in a verify-by-value through the stack that is gone**, and so does `infra/scripts/ops-postverify.sh`, whose every check is a `grafana-query.py` call. Nothing on this page asks you to read a dashboard.

**No Grafana alert can tell you this** — a rule cannot page about the system that evaluates it. What tells you is the healthchecks.io half of the mutual watchdog, `zcrypto-grafana-watchdog`, and **which of its two routes you got is the first fact of the incident**:

- **A `/fail` on the check** ⇒ the ops timer ran and its probe of `https://zcrypto2026.grafana.net/api/health` (`ops_grafana_watchdog_probe_url`, `infra/ansible/roles/ops/defaults/main.yml`) failed. healthchecks.io moves a check down on receipt of a `/fail`, so no `timeout` + `grace` term applies. The pinger is alive and Grafana is not reachable from ops — this page.
- **Silence** ⇒ nothing pinged at all, and the check went down on staleness at its own `timeout` 600 s + `grace` 600 s = 20 min from its last ping. The timer fires `OnCalendar=*:0/5:41`, so silence is the ops host or the timer, **not** Grafana: work [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog) instead and leave this page.

Those two check settings were read from the healthchecks.io management API on 2026-08-31. **Re-read them** — they are settings on a third party's dashboard and this file does not change when one does.

**Time from the outage to the phone**, measured by [`drills-telemetry.md#drill-c-prime`](drills-telemetry.md#drill-c-prime): PENDING-DRILL-CPRIME-PAGE-BOUND

### What it means

**The live trade path runs unwatched.** The engine keeps cycling and, if armed, keeps submitting. `zcrypto-engine-dark-with-exposure` — the one rule that pages on an open position while the engine is not reporting — is a Grafana rule and cannot fire; [`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) is unreachable as a signal for the duration. Its replacement is a host-local read, step 3 below.

**Nothing else stops either.** Capture keeps capturing, the ops timers keep running, the archive keeps filling. What is gone is every Grafana instrument at once — including both Grafana-side watchdogs: `zcrypto-hcio-watchdog` cannot report a dead-man being down, and `zcrypto-alloy-dark-*` cannot report a shipper going dark.

**There is no Grafana green to read.** Absence of pages is not an all-clear here, for the whole outage.

**The dead-man domain is what is left standing, and that is its entire reason to exist.** The checks reach the phone through healthchecks.io's own Slack integration, which no Grafana notification template touches. They watch **liveness** and nothing else — no thresholds, no rates, no log content. Which check watches which daemon, and what each one withholds its ping for, is [`observability.md#zcrypto-hcio-watchdog`](observability.md#zcrypto-hcio-watchdog).

**Two holes in that cover, named so you do not assume it is total**: the NAS archive-pull loop has no check at all (that map records the asymmetry), and no check reads a position, a resting order or the execution gate — the engine's check pings on a completed *cycle*.

**What a Cloud outage loses permanently, per plane** — a stopped shipper and a dark destination lose opposite planes, so this statement carries a measured half and a derived half, each labelled: PENDING-DRILL-C-PLANE-LOSS

**The direct-shipped daemon logs are on neither of those planes.** The capture daemon, the engine and the liquidations poller push to Loki themselves, so what they lose is bounded by `ship.py`'s ring and counted by `zcrypto_logship_dropped_lines_total` — read that counter's level on return, not the shipper's Alloy.

### What to do

1. **Confirm the stack is dark rather than unreachable from one place.** Run the watchdog's own probe from ops and from the workstation: `ssh hp`, then `curl -fsS -m 10 -o /dev/null -w '%{http_code}\n' https://zcrypto2026.grafana.net/api/health`. Failing from both is the outage. Failing from ops alone is ops egress with Grafana healthy — a fault in the watchdog's route, and this is the wrong page for it.

2. **Read the dead-man domain directly — the one read that never passes through Grafana.** `uv run python infra/scripts/ops-daily.py report --since 24h`: its dead-man half fetches `https://healthchecks.io/api/v3/checks/` with the vaulted read-only key (`healthchecks_readonly_api_key`, `group_vars/all/vault.yml`) and is unaffected. **Expect exit 2 and a `## Sources that could not be read` block naming the Grafana ones** — that is the outage being reported, not a fleet finding, and every other part of the report still stands. **Its `## Dead-men` line prints how many checks were read, never which are down**: for the names, statuses and last ping times, open `https://healthchecks.io` itself.

3. **Then read each host by hand.** Every command here is host-local and needs no telemetry stack:

   - **Capture primary** — `ssh zcrypto`, then `sudo docker ps --format '{{.Names}} {{.Status}}'`, `sudo docker logs zcrypto-capture --since 1h`, and the read that proves it is really writing: `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` > 0.
   - **Capture secondary** — `ssh red`, the same three.
   - **Engine**, on the primary — `sudo docker exec zcrypto-engine zcrypto engine exec-status`. This is the only place the gate's `reasons` and the two arming keys are visible separately, it re-evaluates the gate on the spot, and it is what stands in for the dark position alert. Then `sudo docker logs zcrypto-engine --since 1h` for the cycle.
   - **Ops** — `ssh hp`, then `sudo docker ps --format '{{.Names}} {{.Status}}'` and `sudo systemctl list-timers 'zcrypto-*' --all --no-pager` for each unit's last and next run. **Not `ops-postverify.sh`**: every check in it will read FAIL because the query behind it cannot run, and a FAIL there would be read as a fleet fault.
   - **NAS** — `ssh nas`, then `sudo /usr/local/bin/docker logs zcrypto-archive-pull --since 1h`. `docker` is off the non-interactive ssh PATH on that host, so the absolute path is not optional.

4. **Change nothing you cannot verify.** A converge, a re-pin, a restart or a prune each end in a verify-by-value that this outage has taken away, and `.claude/rules/fleet-deploys.md` requires that verification. Unless a host-local read above found a real fault, the action is to wait — and to write what you read into the incident record, because none of it is recoverable from Grafana afterwards.

5. **On return, re-verify by VALUE what the rules could not see.** A rule reading a *change* across a window is blind to a condition already present in a series' first sample after the gap, so its staying Normal proves nothing about the outage. `grep -nE 'delta\(|increase\(|resets\(' infra/grafana/alerts.yaml` names every rule of that shape. Read each subject's level rather than the rule's state, starting with the ones whose miss is permanent:

   - `zcrypto-reconcile-residual-gap` — permanent, unrecoverable L2 loss, the highest-severity rule in the system. Its authority is the ops ledger, which never went dark: `ssh hp "sudo cat /var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl"`.
   - `zcrypto-gate-mismatch` and `zcrypto-gate-streak-reset` — the go-live gate's own evidence; a mismatch or a streak reset inside the gap shows in the counter's level and in no page.
   - `zcrypto-ops-verify-replay-new-breakage` and `zcrypto-ops-verify-replay-backlog-stuck` — both read `delta()` over a window wider than a day, so a short outage hides inside one evaluation.

6. **A page arriving on the way back is not proof of an event during the gap.** A first-sample rule can fire spuriously on return; which ones do is what [`drills-telemetry.md#drill-c`](drills-telemetry.md#drill-c) measures on the shipper side. Read the subject by value before acting on any of them.

### Retire when

`infra/grafana/alerts.yaml` carries no rules, or no host's `config.alloy` (`infra/ansible/roles/{capture,ops}/files/config.alloy`, `infra/nas/config.alloy`) still declares `prometheus.remote_write "grafana"` — at which point Grafana Cloud is no longer this fleet's telemetry destination and there is no outage of it to work.
