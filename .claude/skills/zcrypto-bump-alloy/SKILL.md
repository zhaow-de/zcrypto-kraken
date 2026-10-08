---
name: zcrypto-bump-alloy
description: Human-run only — invoke when `infra/scripts/alloy-version.py gate` prints a target for every Alloy on the fleet, container and apt, or one host's Alloy must roll back.
disable-model-invocation: true
---

# zcrypto-bump-alloy

## What this is

The codified Alloy bump: one wave that moves every Alloy of the inventory's `observed` group to the version `infra/ansible/group_vars/observed/alloy.yml` names, host by host, each by that host's `--tags alloy` converge. A container Alloy is a digest-pinned `grafana/alloy` container named `grafana-alloy`, logging through the journald driver; an apt Alloy is the package `alloy` under systemd, held in `dpkg` and pinned at priority 1001 at the fleet's version, so no `apt upgrade` moves it. Each serves its self-metrics on loopback `127.0.0.1:12345`.

A bump is telemetry-only. `--tags alloy` runs each play's `always` tasks and its role's Alloy part and nothing else (`tests/test_alloy_tag.py`), and the engine play carries no Alloy task. On ops, the cache nodes and the capture hosts Alloy is its own compose project, so the run restarts neither the liquidations poller, Valkey, Sentinel nor the unbackfillable capture daemon; on the NAS the narrow run recreates Alloy alone and leaves `archive-pull` running, so the gate export is not replayed (`tests/test_nas_alloy_tag.py`); on the apt hosts it touches nothing of Caddy, WireGuard, the SSH relay, the probe, Grafana or its stores, or the dead-man service. The container hosts' `./alloy-data` volume keeps the remote_write WAL and the Loki positions across a recreate, so a bump does not re-ship the log backlog into the ingest quota.

The role lands the version, and no host-side `up -d` follows the converge. A container role's Alloy part refuses an operand other than the digest committed for its host — `alloy_image_digest`, from the host's hold file while it is held — unless `-e '{"alloy_override": "<reason>"}'` rides beside it, and refuses a run whose container does not run the digest it was handed; the NAS's and the apt hosts' runs are their legs' below.

A `config.alloy` edit outside a bump ships by the same converge, the host's `--tags alloy` form of Step 2, with the digest committed for it where its role takes one: once the deployed config differs from the repo's, a container role's digest-drift assert refuses a converge without that digest, and a run with it copies the file and reloads Alloy, recreating nothing while the digest and the secrets file are unchanged.

**No canary bake is owed.** `fleet-deploys.md`'s canary rule is scoped to *capture-image* digests; an Alloy version is not one. The bump's only hard clocks are alert windows: each host's `Fleet · Alloy dark` dead-man fires after `for: 10m` (+~5 m Prometheus staleness ≈ 15 m effective), and on **ops** the tighter clock is `zcrypto-hcio-watchdog` (~10 m total: `hc_checks_down_total` goes stale ~5 m after Alloy stops shipping, then `vector(999)` + `for: 5m`). Keep each host's dark window under ~8 minutes — a normal recreate or restart is seconds.

## Standing cautions

- Timeout-guard each network read; an empty filtered query is not an absent event — verify by positive trace.
- NAS docker is `/usr/local/bin/docker`, not on sudo's PATH: `sudo /usr/local/bin/docker`.
- A `docker inspect` here names its fields, `.Config.Image`, `.State.StartedAt`, `.Created`, `.RestartCount` or `.Name`, and not `.Config.Env`: a container's environment, the Alloy secrets files and the NAS's `.env` carry credentials and stay unprinted.
- The converge mechanics — the `--check --diff` read, `converge.sh`'s confirm, the pins refusal, `.Config.Image`, the empty-`-e` trap, the STATE-record row, the prune order, verify-by-outcome — are `zcrypto-rollout-image`'s *Converge mechanics* block: read it before Step 2.

## The hosts — three naming schemes, one map

| host | ssh alias | ansible `--limit` | Cloud `host=` label | Alloy, and the operand its role takes |
|---|---|---|---|---|
| ops node | `hp` | `zcrypto-ops` | `ops` | container, `ops_alloy_digest` |
| observability node | `mon` | `zcrypto-mon` | `zcrypto-mon`, on the node's own stack | apt, none |
| bridgehead | `access` | `zaccess` | `zaccess` | apt, none |
| dead-man node | `hc` | `zcrypto-hc` | `zcrypto-hc`, on the observability node's stack | apt, none |
| NAS | `nas` | `nas` | `nas` | container, none: the pin is `nas_alloy_image` |
| cache node 1 | `db1` | `zcrypto-valkey1` | `zcrypto-valkey1` | container, `cache_alloy_digest` |
| cache node 2 | `db2` | `zcrypto-valkey2` | `zcrypto-valkey2` | container, `cache_alloy_digest` |
| cache node 3 | `db3` | `zcrypto-valkey3` | `zcrypto-valkey3` | container, `cache_alloy_digest` |
| capture secondary | `red` | `zcrypto-red` | `zcrypto-red` | container, `capture_alloy_digest` |
| capture primary | `zcrypto` | `zcrypto` | `zcrypto` | container, `capture_alloy_digest` |

`up{host="hp"}` returns silence, not an error — query the label column. Grafana Cloud holds no `host="zcrypto-mon"` or `host="zcrypto-hc"` series: the two nodes' are read with `uv run python infra/scripts/grafana-query.py --stack mon`.

## Step 0 — The gate: the target, the dry-starts, the baseline

1. **Read the gate**, from the workstation at the repository root: `uv run python infra/scripts/alloy-version.py gate`. Its first line, `fleet: <version> <digest> <deb>`, is the fleet file's. Its second is `target: <version> <index digest> <deb version>` — the newest version above the fleet's that Docker Hub carries as a `v<x.y.z>` tag whose registry index holds a linux/amd64 image and apt.grafana.com's index carries as `alloy`, with the three values Step 1 writes — or `target: none — the fleet runs the newest version present in both`, which ends the bump here. Each `image only: v<version>` or `apt only: <deb>` line after them is a newer version one source alone carries: the fleet waits for the other source, and one that carries a fix the fleet needs goes to the owner. `gate: failed: <source>: …` with exit 2 is a source that did not answer: read the gate again later. Two such lines a re-read does not cure: `gate: failed: fleet file: …` is the tree's own file unreadable, the tree's to fix; a `registry:` line quoting a `Docker-Content-Digest` is an answer of an unexpected shape, which goes to the owner.
2. **Read the release notes** of the target and of each version between the fleet's and it, `https://github.com/grafana/alloy/releases/tag/v<version>`, for config-language breaking changes and deprecations: the notes name a deprecation, and the dry-starts show whether a config here trips it.
3. **Dry-start each config at the target**, on the workstation at the repository root, against the target's release binary — seven configs: `infra/nas/config.alloy` and the `config.alloy` under `infra/ansible/roles/<ops|capture|cache|access|mon|hc>/files/`. The workstation is the live fleet host `zcrypto-ops`: its own Alloy holds `127.0.0.1:12345`, its loopback ports serve live services (the liquidations poller's metrics on `9103`), and its user is outside the `docker` group, so the copy runs the release binary and dials nothing live. In a scratch directory, `.tmp/alloy-dry/`: the binary unzipped from `https://github.com/grafana/alloy/releases/download/v<target>/alloy-linux-amd64.zip` and made executable, `chmod +x .tmp/alloy-dry/alloy-linux-amd64`, since the zip stores it without its execute bit; a copy of the config with `procfs_path = "/proc"`, `sysfs_path = "/sys"`, `rootfs_path = "/"`, each textfile `directory` and each `loki.source.journal`'s `path` at an empty scratch directory, and each loopback address it dials — each scrape `__address__`, each `redis_addr`, each URL on `127.0.0.1` — and ops's dead-man service scrape target, `zcrypto-hc.zhaow.me`, at `127.0.0.1:9`, a closed port; each `sys.env` name the copy reads, `grep -o 'sys.env("[A-Z_]*")' <the copy>`, set in the process to a dummy, each `*_URL` to `http://127.0.0.1:9/x`. Start it in the background, its output to a log file in the scratch directory, as `.tmp/alloy-dry/alloy-linux-amd64 run --disable-reporting --server.http.listen-addr=127.0.0.1:<a free port> --storage.path=.tmp/alloy-dry/store <the copy>`, and after 75 seconds read `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<the port>/-/ready` and the log, before the stop, whose one-minute flush to the closed port logs a `non-recoverable error` of its own. Expected: `200`, and no `level=error` line in the log but, on the cache config, `Couldn't connect to redis instance` lines, their number set by when the exporters' scrapes land. A config the target refuses holds the bump. A config changed since the fleet last ran the fleet file's version is dry-started at that version too, the version the fleet's rollback returns to. Remove `.tmp/alloy-dry/` after.
4. **Read the baseline**, each host's running Alloy against its `alloy` row in `docs/reference/fleet-pins.md`, before changing anything — the row is what a rollback returns to. On the container hosts the field is `.Config.Image` (`.Image` is host-dependent and lies under classic storage); on the apt hosts the installed package:

   ```bash
   for h in hp db1 db2 db3 red zcrypto; do printf '%s ' "$h"; ssh "$h" "sudo docker inspect grafana-alloy --format '{{.Config.Image}}'"; done
   ssh nas "sudo /usr/local/bin/docker inspect grafana-alloy --format '{{.Config.Image}}'"
   for h in mon access hc; do printf '%s ' "$h"; ssh "$h" 'dpkg-query -W alloy'; done
   ```

   A read that differs from its row is a row to re-true before Step 2.

## Step 1 — The fleet file

One commit writes the gate's `target:` values into `infra/ansible/group_vars/observed/alloy.yml` — `alloy_version`, `alloy_image_digest` (the full `sha256:` index digest) and `alloy_deb_version` (the index's own string, not derived from the version) — and `nas_alloy_image: grafana/alloy@<that digest>` into `infra/ansible/host_vars/nas/vars.yml`, bare: `converge.sh` records the NAS's `committed_pins` by a regex that drops a quoted value or a trailing comment. A held NAS keeps its hold file's literal (*Held hosts*). The message carries the gate's lines and each dry-start's reading. `fleet-pins.md` is not edited in that commit: each row records what its host runs and is re-trued after that host's converge (*Closeout*).

## Step 2 — The wave, host by host in canary order

The order: `zcrypto-ops`, the stop point; `zcrypto-mon`, then `zaccess`, then `zcrypto-hc`; `nas`; `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`, one per run; `zcrypto-red`; `zcrypto`, attended and last. Telemetry-only, so the order serves verification, not blast radius: ops first, for its fast independent detectors — `zcrypto-hcio-watchdog` and the 6 h `container="alloy"` log canary — and as the wave's first run of the role's recreate and image read; the apt hosts next, holding nothing unbackfillable, the observability node before the edge so the hold, the pin and the install are proven away from the bridgehead's revocation path first; the NAS, whose pull loop is read untouched; the cache nodes, whose set holds nothing unbackfillable; the capture hosts, the primary last. The next host follows as soon as the previous host's Step 3 reads green; no timed bake is owed beyond it. Before the first converge, `date -u +%Y-%m-%dT%H:%M:%SZ` prints the instant the wave's close counts its venue-facing rows from: keep it.

`converge.sh` previews each wave form (`--check --diff`), then asks for the typed `--limit` — read the preview before typing it, or add `--check` for the preview alone. Every converge runs from merged `develop`, and `<alloy_image_digest>` is that key's full `sha256:<64 hex>` in `infra/ansible/group_vars/observed/alloy.yml` there. A held host takes no wave converge (*Held hosts*).

**One wave at a time.** The wave opens when the change that moves the fleet file merges; a change that moves the fleet file again does not merge while it is open, the fleet's rollback aside (*Rollback*). From the merge until a host's own wave converge, no other converge lands Alloy there: any converge of an apt host or of the NAS whose tags reach its role — `--tags mon`, `--tags access` and `--tags hc` among them — lands the new version out of the wave's order, as a container role's run with the fleet's digest does; the observability node's monthly patch pass waits by `infra/runbooks/mon.md`'s `mon-patch-pass` step 1, and the dead-man node's by `infra/runbooks/hc.md`'s `hc-patch-pass` step 1.

**The Kraken windows.** Before each converge of a venue-facing host — `zcrypto-ops`, `zcrypto-red`, `zcrypto` — Kraken's maintenance feed is read whole at planning and again immediately before, `curl -fsS --max-time 30 https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, and judged by `.claude/rules/fleet-deploys.md`'s test; a window over the converge is waited out, and a read that timed out is no evidence of a clear window.

**Rung 2's box.** While it holds (`infra/runbooks/engine-procedures.md`'s `engine-rung-2-box`), a cache node's converge runs outside the day's window and away from an engine restart (its `rung-2-what-not-to-do`), and the primary's outside the day's window too (`rung-2-the-day-s-window`); in or out of the box, the primary's is attended and away from a 4-hourly boundary and from any engine restart. `--tags alloy` is none of the forms the box refuses against `zcrypto`.

**Refusals and stops.** A refusal by the role — an operand off the host's committed digest, or the fail-fast — means the operand was wrong: re-read the host's committed value, `infra/ansible/host_vars/<host>/alloy.yml`'s where the host is held, else the fleet file's, and re-type the converge with it; no `alloy_override` is passed to get past a refusal in a wave. The NAS takes no operand: its pin read, `refuse to recreate Alloy from a stack .env that names another Alloy pin`, means the stack `.env` does not carry the line the run wrote, and its remedy is the host read its message names, the file's `ALLOY_IMAGE=` lines alone — `ssh nas "sudo grep '^ALLOY_IMAGE=' /volume1/docker/zcrypto-archive/.env"`, the file also holding the gate dead-man URL — before a re-run. A preview that names a file or a task outside the host's Alloy part holds the host until the owner has read it. Any touch of a capture daemon, the engine, the liquidations poller, Valkey or Sentinel, `archive-pull`, Caddy, WireGuard, the SSH relay, Grafana or its stores, or the dead-man service stops the wave for the owner. An image read or a post-condition that fails, or an Alloy not running after the run, darkens the host: its restore is *Rollback*'s one-host form, attended, and the host is then held.

### ops — the stop point

```bash
ssh hp "sudo docker inspect zcrypto-ops-liquidations --format '{{.RestartCount}} {{.State.StartedAt}}'"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags alloy -e ops_alloy_digest=<alloy_image_digest>
ssh hp "sudo docker inspect zcrypto-ops-liquidations --format '{{.RestartCount}} {{.State.StartedAt}}'"   # the same line
```

The preview names files under `/etc/zcrypto-ops/alloy` alone — `compose.yaml` for a new digest — and skips the recreate, the image read and its assert; the real pass's recreate reports `changed` and the assert passes. Ops is the stop point: its preview and its Step 3 read green before another host is touched, and a refusal, a failed image read or a verification that does not read green there holds the wave until the fix is merged.

### The observability node, the bridgehead, then the dead-man node

```bash
ssh mon 'systemctl show -p ActiveEnterTimestamp --value grafana-server prometheus loki caddy'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags alloy
ssh mon 'systemctl show -p ActiveEnterTimestamp --value grafana-server prometheus loki caddy'   # the same four lines

ssh access 'systemctl show -p ActiveEnterTimestamp --value caddy wg-quick@zaccess0 zaccess-ssh-proxy.socket'
infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags alloy
ssh access 'systemctl show -p ActiveEnterTimestamp --value caddy wg-quick@zaccess0 zaccess-ssh-proxy.socket'   # the same three lines

ssh hc "sudo docker inspect zcrypto-hc --format '{{.RestartCount}} {{.State.StartedAt}}'; systemctl show -p ActiveEnterTimestamp --value caddy"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags alloy
ssh hc "sudo docker inspect zcrypto-hc --format '{{.RestartCount}} {{.State.StartedAt}}'; systemctl show -p ActiveEnterTimestamp --value caddy"   # the same two lines
```

No operand: the role reads `alloy_deb_version` from the host's hold file, else the fleet file, on the controller. While the pin file `/etc/apt/preferences.d/alloy` would change, the preview skips the install, the hold and `alloy enabled + started`, since the apt module refuses a version below the pin file on disk or one the host's unrefreshed lists lack, and it names nothing of Caddy, Grafana, Loki, Prometheus, WireGuard, the relay, the probe or the dead-man service; it fetches the Grafana repository's signing key, so a source that does not answer refuses the converge. The real pass installs the version, holds it and writes the pin; its post-condition then restarts Alloy where the process predates the installed binary — on the bridgehead and the dead-man node after a version move, each one's `/etc/default/alloy` rendered without `RESTART_ON_UPGRADE` — and restarts nothing where the package already did, as on the observability node.

### The NAS

```bash
ssh nas "sudo /usr/local/bin/docker inspect zcrypto-archive-pull --format '{{.State.StartedAt}} {{.RestartCount}}'"
infra/ansible/scripts/converge.sh site.yml --limit nas --tags alloy -e nas_apply_compose=true
ssh nas "sudo /usr/local/bin/docker inspect zcrypto-archive-pull --format '{{.State.StartedAt}} {{.RestartCount}}'"   # the same line
```

No digest operand: the pin is `nas_alloy_image`, which Step 1 moved. The run lands `conf/config.alloy` and `alloy-secrets.env`, writes the stack `.env`'s one `ALLOY_IMAGE=` line, reads that line back, recreates Alloy alone (`compose up -d --no-deps --force-recreate alloy`) and refuses a container whose `.Config.Image` is not `nas_alloy_image`; `archive-pull` keeps running. The `.env` edit is `no_log` with `diff: false`, since the file carries a vaulted URL, so the pin's change shows as the report line `Alloy files changed this run:` naming `.env`, not as a diff.

### The cache nodes, one per run

`zcrypto-valkey1`, then `zcrypto-valkey2`, then `zcrypto-valkey3` (`ssh db1` to `db3`), one node per converge, as `converge.sh` takes no group:

```bash
ssh db<N> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<alloy_image_digest>
ssh db<N> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"   # the same two lines
```

The preview names files under `/opt/zcrypto-cache/alloy` alone. The role's Alloy pins-recording refusal reads the digest the node runs against `fleet-pins.md`: in the wave it passes, the node running its recorded digest; from the node's converge until its row is re-trued the node runs a digest the file does not record, so a later converge of that node carrying `cache_alloy_digest` before then — a re-run, the one-host rollback, an `infra/runbooks/cache.md` procedure — carries `-e '{"pins_override": "<reason>"}'` beside it.

### The capture secondary, then the primary

```bash
ssh red "sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red --tags alloy -e capture_alloy_digest=<alloy_image_digest>
ssh red "sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'"   # the same line

ssh zcrypto "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine"
infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<alloy_image_digest>
ssh zcrypto "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine"   # the same two lines
```

`--tags alloy` runs the capture role's Alloy part and nothing of the capture daemon: no capture compose render, no `restart capture service` handler, no capture digest to pass. The role refuses the tag without `capture_alloy_digest`, and `tests/test_capture_alloy_tag.py` holds what the tag selects. On the primary the tag satisfies `site.yml`'s refusal of an un-tagged run, `-e converge_primary=true` is still required, and the engine play runs its `always` note alone. The preview names files under `/etc/zcrypto-capture/alloy` and nothing under `/opt/zcrypto-capture`.

### Held hosts

A host the wave cannot reach — down or unreachable, its preview naming more than its Alloy part, or the version failing there and rolled back (*Rollback*) — is held, and goes to the owner: the wave stops for the owner's word on carrying on without it. Holding a host is three things in the same breath. Its `fleet-pins.md` `alloy` row carries the version it runs and, after the word `held`, the reason: in a container row's digest cell after the version, in an apt row's notes. Its hold is committed: the value it runs in `infra/ansible/host_vars/<host>/alloy.yml` — `alloy_image_digest: sha256:<64 hex>` on a container host, `alloy_deb_version: "<x.y.z>-<n>"` on an apt host — with the reason in a comment above it; host vars outrank the fleet file, so every later converge of the host reads it, a container role refusing the fleet's digest there and an apt role installing, holding and pinning the held version. The NAS's hold also sets `nas_alloy_image` back to `grafana/alloy@<that digest>` in the same commit, which `tests/test_fleet_contracts.py` holds equal to the hold file, and no NAS converge runs before that commit merges. The commit's message says what the hold is for.

A hold ends by a change that deletes the host's hold file — the NAS's also moving `nas_alloy_image` to the fleet's digest — merged before the host converges from it; the row keeps `held` and its reason until that converge re-trues it, which the NAS-row contract admits. A held host keeps the wave open, and keeps `Monitor · Alloy versions split across the fleet` firing once its day has passed: both are the hold's, and the hold is the owner's to end.

### Alloy left on its old files after a failed run

On a container host: a run on ops, a cache node or a capture host that failed after `render the alloy secrets env file` changed the file and before `bring the alloy container to the digest, recreated when its secrets file changed` ran leaves the new file on disk and the container on the environment it was created with. The re-run finds the file unchanged, so its `up -d` is not forced, and where the container already runs the run's digest it recreates nothing; a config the failed run copied is stranded the same way, its reload never sent. Remove the host's Alloy secrets file, then re-run the host's `--tags alloy` converge above: the render writes the file again, changed, and the recreate is forced, the new container starting on both files. The running container keeps its environment while the file is gone.

```bash
ssh hp 'sudo rm /etc/zcrypto-ops/alloy/alloy-secrets.env'
ssh db<N> 'sudo rm /opt/zcrypto-cache/alloy/alloy-secrets.env'
ssh red 'sudo rm /etc/zcrypto-capture/alloy/alloy-secrets.env'   # the primary: ssh zcrypto
```

The NAS's narrow run forces its recreate on each applied run, so it takes no such step.

On an apt host: a run that failed after it changed `/etc/default/alloy` (the bridgehead's or the dead-man node's) or the config, and before its `restart alloy` handler flushed, leaves Alloy running on the files it started with. The re-run finds the files unchanged and notifies nothing, and its post-condition restarts Alloy only when the running process's binary was replaced or no process runs, so where the binary was not replaced it restarts nothing and the run ends `rc` 0 with the new files unread. Once the host's `--tags alloy` converge has ended `rc` 0, restart Alloy on the host, then read it by *Step 3 — Per-host verification*:

```bash
ssh mon 'sudo systemctl restart alloy'      # the observability node
ssh access 'sudo systemctl restart alloy'   # the bridgehead
ssh hc 'sudo systemctl restart alloy'       # the dead-man node
```

### The wave's close

The wave closes when the last `observed` host's `alloy` row in `fleet-pins.md` reads the fleet's version, re-trued from its converge (*Closeout*): `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version` reads `0`. At the close the observability node reads one version by value, `uv run python infra/scripts/grafana-query.py --stack mon 'count by (host, version) (alloy_build_info{job="integrations/self"})'`, each host that ships to it on the fleet's `alloy_version`; and the wave's venue-facing rows are read against Kraken's windows, `uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing --since <the instant kept before the first converge>`, owed `0` over the wave's rows.

## Step 3 — Per-host verification

Inside the run: a run that ends `rc` 0 has passed the role's own read — a container role's `refuse a converge whose alloy container does not run the digest it converged`, the NAS's `refuse a converge whose alloy container does not run the committed Alloy pin` — or, on an apt host, run its post-condition, `read whether the running alloy process runs the installed binary` and then `restart alloy when its process predates the installed binary or none runs`, which reports `changed` when it restarted Alloy. Then on the host — a container host:

```bash
ssh <alias> "sudo docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'"
ssh nas "sudo /usr/local/bin/docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'"
# img == grafana/alloy@<the run's digest>, restarts == 0, started after the converge
```

An apt host, as the deploy user:

```bash
ssh <mon|access|hc> 'dpkg-query -W alloy; apt-mark showhold; apt-cache policy alloy'
ssh <mon|access|hc> 'sudo readlink "/proc/$(systemctl show -p MainPID --value alloy)/exe"; echo rc=$?'
# alloy <alloy_deb_version>; showhold lists alloy; policy: Installed and Candidate that version, its line at 1001
# /usr/bin/alloy with no " (deleted)", rc=0 — under sudo, since the deb's unit runs Alloy as the alloy user
```

Shipping health — **read on the host** (`127.0.0.1:12345`; Grafana Cloud admits none of these counters):

```bash
curl -s http://127.0.0.1:12345/metrics | grep -E \
  '^prometheus_remote_storage_samples_(failed_total|pending|total)|^loki_write_(sent|dropped)_entries_total'
# Per destination the host ships to: the sample counters by `remote_name` (`mon` is the observability
# node's endpoint), the entry counters by `host`, the destination's host and port. On EACH destination:
# failed_total 0, pending 0, samples_total CLIMBING on a second read; sent_entries >= 1, dropped 0
# Leave >60 s between reads and >60 s after the recreate: the scrape interval is 60 s, so a fresh
# container legitimately reports samples_total=0 until its first scrape lands. `pending` briefly
# non-zero is in-flight, not failure — only `failed_total` matters. The bridgehead ships no logs,
# so it prints no loki_write line.
```

In Cloud, per host (the positive traces the alert stack itself keys on); the observability node's and the dead-man node's on the observability node, `--stack mon`:

- `uv run python infra/scripts/grafana-query.py 'count(up{host="<label>"})'` reads 1 or more and the host's `Fleet · Alloy dark` rule is back to **Normal** — the canonical proof; `(no series)` is a FAIL, not a zero.
- A **fresh** Loki line for the host — proves the whole journald → `loki.source.journal` → parse → write path end-to-end (verify end-to-end, not at endpoints: a metric on `:12345` plus a keep-list admitting it does not mean the path between them exists). **Do not filter on `container="alloy"` in a short window**: Alloy logs at startup and then goes quiet, so `{host=…, container="alloy"}` over 15 m reads empty on a healthy host bumped 30 min ago. Query `{host="<label>", level=~".+"}`, whichever container, for the liveness proof, and widen to 60 m for Alloy's own startup lines. The bridgehead ships no logs and has no such line.
- Alloy's own `job="integrations/self"` families present for the host — `tests/test_infra_alloy_series.py` is the authoritative per-host series checklist: read `NAS_REQUIRED`, `OPS_REQUIRED`, `CAPTURE_REQUIRED`, `ACCESS_REQUIRED` and `CACHE_REQUIRED` there rather than a list copied here.

Host-specific additions:

- **ops**: `zcrypto-hcio-watchdog` back to Normal (it races you); `up{job="liquidations_app"} == 1`; the leg's two liquidations reads the same.
- **the observability node**: `zcrypto-alloy-dark-mon` Normal on the node's rules endpoint; the leg's two `systemctl` reads the same.
- **the bridgehead**: `count(up{host="zaccess"})` read on Cloud and on the node; the leg's two `systemctl` reads the same.
- **the dead-man node**: `zcrypto-alloy-dark-hc` Normal on the observability node's rules endpoint; the leg's two reads the same.
- **NAS**: the next `archive-pull` cycle logs `pull complete … failed=0` for each verified channel, and the leg's two `zcrypto-archive-pull` reads are the same — the narrow run left it running; `zcrypto_gate_*` series still arriving (the NAS unix exporter's textfile collector scrapes `/textfile/gate.prom`).
- **capture hosts**: `up{job="capture_app"} == 1`; the leg's two capture reads the same and its newest parquet still advancing (`sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | wc -l` > 0) — proving the bump did not touch the daemon. On the primary `up{job="engine_app"} == 1` and the engine's read the same; on the secondary `up{job="engine_app"}` reads 0 by design.
- **cache nodes**: the node's series list is `CACHE_REQUIRED`; `redis_up{host="<host>"}` reads 1 on two series, `job="valkey"` and `job="sentinel"`; the leg's two `docker inspect` reads print the same lines, proving the bump did not touch Valkey or Sentinel.

**Expect `Fleet · a daemon restarted` (`zcrypto-fleet-daemon-restarted`, `job="integrations/self"`) once per host on ops, the NAS and the capture pair, ~3–8 min after each recreate** — Alloy's own `process_start_time_seconds` moved, and that rule is the bump's own record in the channel; it self-clears within 15 min and needs nothing. A firing that outlives the 15 minutes, or clears and returns with no bump, is a crash loop — under a restart loop `changes(process_start_time_seconds[15m])` never empties, so the instance stays firing rather than firing a second time. The rule selects no cache node, bridgehead, observability node or dead-man node, so their recreate or restart pages nothing.

**Expect `Ops · ERROR logs` to fire on the ops recreate, ~35 s after it.** The OUTGOING container logs two `service=remotecfg … err="noop client"` errors as it shuts down (remote config is unused here, so there is nothing to unregister from). The rule's container enumeration includes alloy, with `for: 0s` over a 15 m window, so it fires on the old container's dying breath and self-clears ~15 min later. Confirm it is that and not something real: the lines are timestamped ~200 ms BEFORE the new container's `StartedAt`, and `sudo docker logs grafana-alloy` on the new one shows zero errors. Only ops's ERROR rule enumerates the alloy container; no other host's recreate or restart trips one.

If a `Fleet · Alloy dark` or exporter-stale page fires because a window ran long: it self-resolves once `up` returns; note it in the Slack thread rather than silencing anything. A host whose Step 3 is not green within fifteen minutes of its recreate or restart stops the wave.

## Rollback

**One host's**, when a version fails on one host class alone: the host converges `--tags alloy` at its previous value — on a container host its `fleet-pins.md` row's rollback operand, or Step 0's baseline where the row is not yet re-trued, in full, `sha256:<64 hex>`, from that file's *Full digests*; on an apt host, whose package row has no rollback column, Step 0's baseline or the row's previous version in `git log -p docs/reference/fleet-pins.md` — under `-e '{"alloy_override": "<reason>"}'`, a reason longer than 8 characters, and is then held (*Held hosts*), its hold file merged before its next converge:

```bash
infra/ansible/scripts/converge.sh site.yml --limit <host> --tags alloy -e <role>_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}' -e '{"pins_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit <apt host> --tags alloy -e alloy_deb_version=<previous> -e '{"alloy_override": "<reason>"}'
```

The first line is ops's (`ops_alloy_digest`) and the secondary's (`capture_alloy_digest`); an apt host's `<previous>` is the `<x.y.z>-<n>` string.

**The NAS's** takes no operand: it is an attended hand recreate from the previous pin, whose image is still on the NAS, run there (`ssh nas`):

```bash
cd /volume1/docker/zcrypto-archive && sudo sed -i 's|^ALLOY_IMAGE=.*|ALLOY_IMAGE=grafana/alloy@<previous index digest>|' .env && sudo /usr/local/bin/docker compose up -d --no-deps --force-recreate alloy
```

Then its hold, as *Held hosts* says: the previous digest as `alloy_image_digest` in `infra/ansible/host_vars/nas/alloy.yml`, the reason in a comment above it, and `nas_alloy_image` set back to `grafana/alloy@<that digest>` in the same commit; no NAS converge runs before that commit merges, since one from the tree before it writes the fleet's pin back.

**The fleet's**: revert the change that moved the fleet file, merge, and run the wave again in the same order — the fleet moves together, the apt hosts going down under `allow_downgrade`. The revert is the one fleet-file change that merges while a wave is open; a host the wave had not reached moves no version in the second run. The second run puts each config on the previous version, which Step 0's dry-starts read for a config changed since the fleet last ran it.

The container hosts' `alloy-data` WAL and positions survive both directions, and the journal readers resume from their cursor within `max_age = 48h` — an outage longer than that loses the older journal tail, another reason not to park a half-done bump.

## Closeout

- `docs/reference/fleet-pins.md`, per reached host, from its converge's `rc` 0 line in `docs/reference/deploy-log.jsonl`, committed with that line: a container host's `alloy` row — the digest's first 12 hex and the version, the NAS's keeping its build clause, upstream `grafana/alloy`, no `-compat` variant (`infra/scripts/count-list.sh nas-rows-without-compat`), `since` from the container's `.State.StartedAt` (the NAS's from `.Created`, which a later whole apply's `compose restart alloy` leaves in place), its rollback operand the digest it replaced; an apt host's row in the package table — the version `dpkg-query -W alloy` reads, in backticks, `since` the converge's date, notes `dpkg hold; pinned at 1001`, the word `held` in neither unless the host is held. The *Full digests* glossary gains the new digest, and a digest no cell carries leaves it (`tests/test_fleet_contracts.py`).
- The prune (the block) is owed once per container host the bump reached, each after its own row lands: `uv run python infra/scripts/prune-host-images.py <host>`, then `--apply`. The apt hosts owe none: their Alloy is a package.
- The wave closes as *The wave's close* says.
