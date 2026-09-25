# Cache runbooks — the engine's Valkey set

You are here because **an alert fired in Slack** — find the section whose anchor matches the alert `uid` — or because you mean to move the primary, rejoin a node, apply a configuration change or apply a changed password: the four procedures at the top, found by heading. Each section is written to be actioned without opening any other document.

The set is three Linode nodes, `zcrypto-valkey1`, `zcrypto-valkey2` and `zcrypto-valkey3` (the workstation's ssh aliases `db1`, `db2` and `db3`; `Cache 1` to `Cache 3` in Slack and on the Cache board), each running Valkey on `6379`, a Sentinel on `26379` and a Grafana Alloy, in containers named `zcrypto-valkey`, `zcrypto-sentinel` and `grafana-alloy`. One node is the primary and two are replicas; the three Sentinels, quorum 2, pick the primary under the name `zcache`. The nodes and the engine host talk over the WireGuard mesh `zcache0`: the engine host is `10.98.0.1`, the nodes are `10.98.0.11` to `10.98.0.13` in order, and Valkey and Sentinel listen on loopback and the mesh address alone. Promotion prefers valkey1 and valkey2 (`replica-priority` 100) over valkey3 (250), which sits in another region as the copy that survives a regional outage.

Two shell functions carry every Valkey and Sentinel command below: paste them into your shell on the node once per login. Each hands `valkey-cli` its password from a root-only env file the cache role renders, `/opt/zcrypto-cache/cli-exporter.env` or `/opt/zcrypto-cache/cli-sentinel.env`, through `docker exec --env-file`, so it reaches neither the terminal, the process list nor a shell history; `vk` runs a command on the node's Valkey as the read-only `exporter` user, `sn` on the node's Sentinel:

```bash
vk() { sudo docker exec --env-file /opt/zcrypto-cache/cli-exporter.env zcrypto-valkey valkey-cli --no-auth-warning --user exporter "$@"; }
sn() { sudo docker exec --env-file /opt/zcrypto-cache/cli-sentinel.env zcrypto-sentinel valkey-cli --no-auth-warning -p 26379 "$@"; }
```

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="cache-manual-failover"></a>

## cache-manual-failover — PROCEDURE: moving the primary on our schedule

### What you are seeing

Nothing fired. You mean to move the primary off a node: before re-pinning or converging the node that holds it, so the engine's one reconnect happens when you choose rather than on the Sentinels' detection timer, or to put the primary back after a drill.

### What it means

`SENTINEL failover zcache` makes the Sentinel you ask promote a replica without waiting for the others to agree the primary is down; it picks by `replica-priority`, then by replication offset, so from valkey1 the primary moves to valkey2 and from valkey2 to valkey1, and valkey3 is picked when it is the one replica left. The old primary is turned into a replica of the new one. The engine, once wired to the set, holds its connection through the proxy on its own host, whose checks cut the session at the switch so its client reconnects to the new primary; do it inside an engine inter-cycle gap by preference.

### What to do

1. **Read the current primary**, on one node: `sn SENTINEL get-master-addr-by-name zcache`. It prints the primary's mesh address and `6379`.
2. **Confirm both replicas are caught up**, on the primary: `vk INFO replication` reads `connected_slaves:2`, and each `slave0:` and `slave1:` line reads `state=online` with `lag=0` or `lag=1`. A replica missing or lagging is the one to repair first — `cache-rejoin-node` below — since the failover can promote it.
3. **Fail over**, on one node: `sn SENTINEL failover zcache`. It answers `OK`.
4. **Confirm by value.** Within about ten seconds `sn SENTINEL get-master-addr-by-name zcache` names another address on each of the three nodes; on the old primary `vk INFO replication` reads `role:slave` and `master_link_status:up`. From the workstation, `uv run python infra/scripts/grafana-query.py 'count by (host) (redis_instance_info{job="valkey", role="master"})'` names the new node alone once its next scrape lands.

### Retire when

`infra/ansible/roles/cache/` no longer exists, or its compose template no longer starts a Sentinel.

______________________________________________________________________

<a name="cache-rejoin-node"></a>

## cache-rejoin-node — PROCEDURE: rejoining a node to the set

### What you are seeing

Nothing fired, or `zcrypto-cache-replicas-short` sent you here: a node is not replicating from the primary — its `INFO replication` reads `master_link_status:down`, it still reads `role:master` while the Sentinels name another node, or its data directory was lost or replaced — and it is to rejoin as a replica.

### What it means

A replica that reconnects to the primary resyncs on its own: a partial resync when its offset is still in the primary's backlog, a full one from a fresh snapshot otherwise, seconds at this dataset's size. The daemons own their config files after the first render, so a node's own replication state survives a routine converge; restarting its containers is enough when the node's files are sound. When they are not — a hand edit, a lost disk — the files are replaced from the templates with `cache-config-reset` below, and the node relearns the set from the Sentinels. A node that is the primary is failed over first; this procedure rejoins replicas.

### What to do

1. **Is the node the primary?** On one node: `sn SENTINEL get-master-addr-by-name zcache`. If it names this node's mesh address, run `cache-manual-failover` above first.
2. **Restart the node's cache containers:** `sudo systemctl restart zcrypto-cache.service` on the node. Valkey reloads its AOF and reconnects to the primary its config names. When the node missed a failover while it was down, that address is a replica now: the node replicates from it, chained, until the Sentinels repoint it, which they do once `failover-timeout` (60 s) has passed, so the chain can last about a minute and a half.
3. **Confirm by value on the node, a minute and a half after step 2:** `vk INFO replication` reads `role:slave` and `master_link_status:up`, then a `master_host` that is the address step 1 printed; another address before then is step 2's chain, not a fault. On the primary, `vk INFO replication` lists the node as `state=online`.
4. **Confirm the Sentinels see it**, on each node: `sn SENTINEL replicas zcache` lists the node's mesh address with `flags` reading `slave` and without `s_down`.
5. **Still not linked after two minutes** — the node's `vk INFO replication` reads `master_link_status:down`, or `vk` finds no Valkey to answer — read the disk before the files: `df -h /var/lib/zcrypto-cache` on the node, and Valkey's own last lines, `sudo journalctl CONTAINER_NAME=zcrypto-valkey -n 200 --no-pager | grep -F "fsync policy is 'always'"`. A full disk, or a line there, is the disk's fault and not the files': Valkey exits on a write that finds no room, and restarted onto the same disk it exits again on the next one, so free space by `zcrypto-cache-disk-low` below and restart the node's containers as in step 2. A disk with room and no such line means its files are the fault: run `cache-config-reset` below on this node.

### Retire when

`infra/ansible/roles/cache/` no longer exists.

______________________________________________________________________

<a name="cache-config-reset"></a>

## cache-config-reset — PROCEDURE: applying a deliberate valkey.conf, sentinel.conf or users.acl change

### What you are seeing

Nothing fired. You changed the cache role's Valkey or Sentinel template and mean a node to run it, or `cache-rejoin-node` sent you here because a node's own files are broken. A password changed in `group_vars/cache_host/vault.yml` is `cache-password-rotation` below, not this procedure: a node reset alone to a new password fails to authenticate to, and from, the nodes still holding the old one.

### What it means

The role renders `valkey.conf`, `sentinel.conf` and `users.acl` when they are absent and leaves them alone after: Valkey rewrites its `replicaof` into its file and Sentinel its known replicas, Sentinels and epoch into its own, and re-rendering them on a routine converge would reset the node's replication state, while `users.acl` carries the hashes of the passwords the nodes authenticate each other with. The role compares the rendered templates' hashes against a recorded copy, so a template change the nodes have not taken shows on the converge without being applied. `-e cache_config_reset=true` replaces the three files on the node it converges. A replaced `sentinel.conf` monitors the first primary, valkey1, at epoch 0, and the other two Sentinels correct it within seconds, since a Sentinel adopts the configuration carrying the higher epoch. A replaced `valkey.conf` names valkey1 too: when valkey1 is not the primary, the node replicates from it, a replica itself, until the Sentinels repoint the node once `failover-timeout` (60 s) has passed, about a minute and a half. One node per converge, replicas first and the primary last after `cache-manual-failover`.

### What to do

1. **Fail the primary over if this node holds it** — `cache-manual-failover` above — so the node is a replica before its files go.
2. **Read the image digests the node runs**, on the node, before its containers go: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, `valkey/valkey@sha256:<64 hex>`, then Alloy's.
3. **Stop the node's cache containers:** `sudo systemctl stop zcrypto-cache.service` on the node.
4. **Converge with the reset and those digests**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`. Without the Alloy digest, on a tree whose `config.alloy` has moved, the role's Alloy config check fails the converge after the reset has already applied.
5. **Start the containers:** `sudo systemctl start zcrypto-cache.service` on the node.
6. **Confirm by value**, as `cache-rejoin-node` steps 3 and 4 do, a minute and a half after step 5; on this node `sn SENTINEL get-master-addr-by-name zcache` names the current primary within seconds.

### Retire when

The tasks in `infra/ansible/roles/cache/tasks/main.yml` that render `valkey.conf`, `sentinel.conf` and `users.acl` lose their absent-file condition, which makes the reset flag meaningless.

______________________________________________________________________

<a name="cache-password-rotation"></a>

## cache-password-rotation — PROCEDURE: applying a changed cache password

### What you are seeing

Nothing fired. You mean to change a password in `group_vars/cache_host/vault.yml`, or a converge's drift report named `valkey.conf`, `sentinel.conf` or `users.acl` after one changed there, since their renders carry the passwords.

### What it means

The nodes authenticate to each other: a replica to its primary with the `replica` password, each Sentinel to each Valkey with the `sentinel` password and to the other Sentinels with Sentinel's `requirepass`. A node reset alone to a new password fails to authenticate to, and from, a node still holding the old one, so the three nodes' files are replaced in one stop, the set down for the minutes it takes; once the engine is wired to the set, that is inside an engine inter-cycle gap. The rendered files name valkey1 as the first primary, so valkey1 holds the primary before the stop and starts first, and no write the set took is lost. `vk` and `sn` read their passwords from files a converge carrying the node's image digest re-renders, and Alloy reads the exporter password and `requirepass` from a secrets file a converge carrying the Alloy digest re-renders and the container reads when it is recreated. The stop fires `zcrypto-cache-primary-count` once its two minutes pass, and it clears when step 5 is done on valkey2, the second node whose Sentinel and Alloy run on the new passwords; `zcrypto-cache-replicas-short` fires when valkey3's step 5 comes more than five minutes after valkey1's, and clears when valkey3's replica connects.

### What to do

1. **Put the primary on valkey1 while the nodes still run the old passwords:** `cache-manual-failover` above, repeated until `sn SENTINEL get-master-addr-by-name zcache` names `10.98.0.11`. When a converge already carried the change, `vk` or `sn` answers `WRONGPASS` or `NOAUTH`: put the old value back in `vault.yml`, converge each node with the two digests it runs, read as step 3 reads them — step 5's command without `-e cache_config_reset=true` — and begin here again.
2. **Change the password** in `group_vars/cache_host/vault.yml` by the recipe in that file's header, merged to `develop`, which the converges below run from. Steps 3 to 5 follow in the same sitting, and no other cache converge — a `cache-config-reset` on another node, an Alloy bump's cache leg — runs between this merge and step 5: a converge without the reset in that window renders the new password into the env files its digests gate, against a `users.acl` and a Sentinel `requirepass` still holding the old one, and two nodes in that state page `zcrypto-cache-primary-count` on a healthy set.
3. **Read each node's running digests**, on each node: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, then Alloy's.
4. **Stop the three nodes, valkey3 and valkey2 before valkey1:** `sudo systemctl stop zcrypto-cache.service` on each.
5. **Converge each node with the reset, valkey1 first, and recreate its Alloy before the next node's converge**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`, which renders the node's files and starts its daemons; then, on the node, `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`, which recreates Alloy so it reads the new secrets.
6. **Confirm by value:** on valkey2 and valkey3, `cache-rejoin-node` steps 3 and 4; on each node, `sn SENTINEL ckquorum zcache` answers `OK 3 usable Sentinels`; from the workstation, `uv run python infra/scripts/grafana-query.py 'redis_up{host=~"zcrypto-valkey[123]"}'` reads 1 on six series, a node's `valkey` and `sentinel` each.

### Retire when

`infra/ansible/roles/cache/templates/users.acl.j2` renders no password, or `infra/ansible/roles/cache/` no longer exists.

______________________________________________________________________

<a name="zcrypto-alloy-dark-cache-1"></a>
<a name="zcrypto-alloy-dark-cache-2"></a>
<a name="zcrypto-alloy-dark-cache-3"></a>

## zcrypto-alloy-dark-cache — ALERT

### What you are seeing

A **critical** Grafana alert, one of three — `Fleet · Alloy dark — Cache 1` / `— Cache 2` / `— Cache 3`. The named node's `up` series has been absent from Grafana Cloud for over 10 minutes: `count(up{host="zcrypto-valkey<N>"}) or on() vector(0)` fell below 1.

### What it means

**Telemetry-only.** Valkey and Sentinel keep running; what stops is your view of that node. Every other rule in the `zcrypto-cache` group reads that node's series and reads no data while this fires, which they take as healthy — read no green as reassurance until `up` is back. The set itself is watched from the other two nodes: a primary that is truly gone still moves, and the other nodes' Sentinels and replica counts show it.

### What to do

1. **Is the node up at all?** Log in with its alias, `db<N>`. No answer is a node incident, not an Alloy one: read `sn SENTINEL get-master-addr-by-name zcache` on the other two nodes to learn whether the set failed over, and the Linode console for the node.
2. **Is the container running?** `sudo docker ps --filter name=grafana-alloy` on the node.
3. **Read the container's state through named fields** — its environment holds the Grafana Cloud push credentials and the two cache passwords, so read these fields by name and not `.Config` whole, `.Config.Env`, `docker exec … env` or `docker compose config`: `sudo docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}} oom={{.State.OOMKilled}}'`. `oom=true` means it hit its 256 MiB cap; `fleet.md#zcrypto-fleet-alloy-memory-headroom` is the warning that precedes it.
4. **Read its logs:** `sudo docker logs grafana-alloy --since 1h 2>&1 | tail -100`. A config parse error names the line; a remote_write auth failure names the credential; a Redis exporter error naming `NOAUTH` or `WRONGPASS` is the exporter password and the node's ACL disagreeing, which leaves `up` present and is not this alert.
5. **Restart it, the usual fix:** `sudo docker restart grafana-alloy`. The `alloy-data` volume keeps the remote_write WAL and the journal cursor.
6. **A recreate is needed when the container is absent or its env or cap changed:** `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`. `sudo` is needed because `alloy-secrets.env` is 0600 and owned by `zcrypto-alloy`.
7. **A config fault is a converge, not a host edit:** compare `sha256sum /opt/zcrypto-cache/alloy/conf/config.alloy` on the node with `sha256sum infra/ansible/roles/cache/files/config.alloy`, then converge the node with its running Alloy digest, `-e cache_alloy_digest=sha256:<running>`, read with `sudo docker inspect grafana-alloy --format '{{.Config.Image}}'`.

**Verify by value:** `uv run python infra/scripts/grafana-query.py 'count(up{host="zcrypto-valkey<N>"})'` reads 4 — the host scrape's two targets and the two Redis exporters — with the rule back to **Normal**; `(no series)` is a fail, not a zero.

### Retire when

All three uids — `zcrypto-alloy-dark-cache-1`, `-2`, `-3` — are absent from `infra/grafana/alerts.yaml`, or `up` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.

______________________________________________________________________

<a name="zcrypto-cache-primary-count"></a>

## zcrypto-cache-primary-count — ALERT

### What you are seeing

A **critical** Grafana alert, `Cache · not exactly one primary`: for two minutes no node has been named a healthy primary by at least two of the three Sentinels. The value is the distance of that count from one, 1 when no primary is agreed; the Cache board's *Which node is primary* panel (205) shows each node's own role beside it.

### What it means

**No agreed primary**: a failover did not complete — fewer than two Sentinels agree the old primary is down, or no replica is eligible — or two of the three Sentinels are down, and cache writes have nowhere to land; the engine, once wired, logs its failed writes on its native side, which reaches no log store. One node's telemetry going dark does not fire it: the other two Sentinels still name the primary. The rule stays quiet while fewer than two nodes' telemetry ships, which the Alloy-dark alerts own. A node that still reads `role:master` after the Sentinels moved the primary is not counted here; `cache-rejoin-node` turns it back into a replica.

### What to do

1. **Read what each Sentinel names**, on each node: `sn SENTINEL get-master-addr-by-name zcache`. Three agreeing on one address is the set's view; the node at that address is the primary the set means.
2. **Read each node's role**, on each node: `vk INFO replication`, its `role:` line.
3. **The Sentinels agree on a dead address, or fewer than two answer:** read `sn SENTINEL ckquorum zcache` on a live node; a quorum shortfall names how many Sentinels it reaches. Bring the dead node back (`sudo systemctl start zcrypto-cache.service` on it) or, with two Sentinels reachable, `sn SENTINEL failover zcache` promotes a live replica.
4. **A node that reads `role:master` while the Sentinels name another** is not this alert's fault: rejoin it with `cache-rejoin-node` above.
5. **Confirm by value:** `uv run python infra/scripts/grafana-query.py 'count by (master_address) (redis_sentinel_master_status{job="sentinel"} == 1)'` names an address counted at least 2, and 3 once all three Sentinels run (a node that went dark keeps its last vote in the read for the query's lookback), and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-primary-count` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-replicas-short"></a>

## zcrypto-cache-replicas-short — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · primary has fewer than two replicas`: for five minutes the primary has reported fewer than two connected replicas. The node the notification names is the primary, or a node still reading `role:master` that `sn SENTINEL get-master-addr-by-name zcache` does not name: rejoin that one with `cache-rejoin-node`.

### What it means

With one replica the set holds two copies and survives no further loss. With none the primary refuses writes, since it takes them with at least one replica within 10 seconds of lag and not otherwise — a cache that refuses writes rather than accepting ones a failover would lose. A converge of a replica restarts it for seconds and does not reach this alert's five minutes.

### What to do

1. **Name the missing replica:** on the primary, `vk INFO replication`; the node absent from its `slave0:`/`slave1:` lines is the one.
2. **Is it up and meshed?** The Cache board's *Mesh handshake age per peer* panel (105) for that node's address, and a login with its alias, `db<N>`. A stale handshake is `zcrypto-cache-wg-handshake-stale` below.
3. **Rejoin it** with `cache-rejoin-node` above.

### Retire when

`zcrypto-cache-replicas-short` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-memory-70pct"></a>

## zcrypto-cache-memory-70pct — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · Valkey memory past 70% of maxmemory`: a node's `used_memory` has been above 70% of its `maxmemory` for fifteen minutes. The primary and its replicas hold the same dataset, so the three normally fire together.

### What it means

The eviction policy is `noeviction`: at 100% the set refuses writes rather than dropping a key silently. The trading library writes its orders, fills and positions and deletes none, so the dataset grows with the engine's history and nothing trims it; at one engine's order rate the limit is years away, which makes a firing a surprise worth reading before acting.

### What to do

1. **Read the growth:** the Cache board's *Memory against maxmemory* panel (209) over its longest range. A step is a burst of writes; a steady climb is the history growing.
2. **Read the keyspace by prefix**, on the primary: `vk INFO keyspace` for the key count, and `vk --scan --pattern 'trader-*' | wc -l` for the engine's own keys. Keys outside the `trader-` prefix are a writer that is not the engine.
3. **Raise `maxmemory`** in the cache role's Valkey template and apply it with `cache-config-reset` above, node by node, keeping it under the container's memory cap with room for the AOF rewrite's copy. Trimming the engine's keys is a decision for the engine, not a repair here.

### Retire when

`zcrypto-cache-memory-70pct` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-aof-not-ok"></a>

## zcrypto-cache-aof-not-ok — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · append-only file off or failing`: for five minutes a node's append-only file has been disabled, or the status of its last write or its last rewrite has not been `ok`.

### What it means

The set writes every command to the append-only file before answering (`appendfsync always`), which is what makes a node's copy survive its own restart. A failed write does not fire this alert: under `appendfsync always` Valkey cannot answer a write it has not made durable, so it logs `Can't recover from AOF write error when the AOF fsync policy is 'always'. Exiting...` and exits, its series stop, and `zcrypto-cache-disk-low` below is the page ahead of that exit. It fires on a failed rewrite, which leaves the file growing, and on a disabled file, which means the node's config is not the role's.

### What to do

1. **Read which of the three**, on the node: `vk INFO persistence`, its `aof_enabled`, `aof_last_write_status` and `aof_last_bgrewrite_status` lines.
2. **A status not `ok` is usually the disk:** `df -h /var/lib/zcrypto-cache` on the node, and the Cache board's *Root filesystem free* panel (104). Free space by `zcrypto-cache-disk-low` below, then restart the node's containers, `sudo systemctl restart zcrypto-cache.service`, failing the primary over first if this node holds it; a rewrite on demand, `BGREWRITEAOF`, is outside the `exporter` user's commands.
3. **Disabled** is a config that is not the role's: apply `cache-config-reset` above to the node.

### Retire when

`zcrypto-cache-aof-not-ok` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-disk-low"></a>

## zcrypto-cache-disk-low — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · root filesystem low`: a node's root filesystem has been below 15% free for thirty minutes. The node the notification names is the one filling; the Cache board's *Root filesystem free* panel (104) draws all three against the green line at 0.15.

### What it means

Valkey's append-only file and snapshots live on this filesystem, under `/var/lib/zcrypto-cache`, and Valkey writes every command to the file before answering (`appendfsync always`). The write that finds the disk full is one it cannot make durable, so Valkey logs `Can't recover from AOF write error when the AOF fsync policy is 'always'. Exiting...` and exits; restarted onto the same disk, it exits again on the next write. When a snapshot meets the full disk first, Valkey stays up and refuses writes instead (`MISCONF`, `rdb_last_bgsave_status:err` in `vk INFO persistence`) until a snapshot succeeds once space is freed. This page comes ahead of both, while the node still has room.

### What to do

1. **Read what fills it**, on the node: `df -h /`, then `sudo du -xsh /var/lib/zcrypto-cache /var/log/journal /var/lib/docker`.
2. **The journal:** `sudo journalctl --vacuum-size=500M` on the node removes its oldest archived files until they hold 500M.
3. **The cache's own directory growing** is Valkey's AOF between rewrites: `zcrypto-cache-aof-not-ok` above reads the rewrite's state.
4. **Read Valkey on the node:** `vk INFO persistence`. No Valkey to answer is one that exited on the full disk and was not brought back: restart the node's containers, `sudo systemctl restart zcrypto-cache.service`, then confirm by `cache-rejoin-node` steps 3 and 4. An answer reading `rdb_last_bgsave_status:err` is a Valkey still refusing writes, which reads `ok` once a snapshot succeeds on the freed disk.
5. **Confirm by value:** the Cache board's panel 104 reads above 0.15 for the node, `vk INFO persistence` on it reads `rdb_last_bgsave_status:ok`, and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-disk-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-wg-handshake-stale"></a>

## zcrypto-cache-wg-handshake-stale — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · mesh peer handshake stale`: a mesh member, the engine host `zcrypto` or a cache node, has not completed a WireGuard handshake with one of its peers for more than three minutes. The host the notification names is the end reporting it; the `peer` label is the other end's mesh address — `10.98.0.1` the engine host, `10.98.0.11` to `10.98.0.13` Cache 1 to Cache 3. A stopped probe timer reads the same way, since the rule adds the probe file's own age.

### What it means

`PersistentKeepalive 25` keeps traffic on every link, so a healthy peer re-handshakes about every two minutes. Past three, the link is down: replication between two nodes, or the engine's cache traffic to one node, is not flowing. A link seen from both ends fires twice, once per reporting end.

### What to do

1. **Is it the probe?** On the reporting host, `systemctl status zcache-probe.timer` and `ls -l --time-style=full-iso /var/lib/zcrypto-node-textfile/zcache.prom`: a file older than two minutes is the timer, and `journalctl -u zcache-probe.service -n 20 --no-pager` says why.
2. **Read the tunnel on both ends:** `sudo wg show zcache0` on the reporting host and on the peer, the engine host (alias `zcrypto`) for `10.98.0.1`. A peer with no `latest handshake` line has not reached it since the interface came up.
3. **Is the peer's port open?** Both layers carry `51821/udp`: the host's nftables, which the firewall role renders and `sudo systemctl status nftables` shows loaded on each end; and the Linode Cloud Firewall, managed by hand, in the Linode console for each end.
4. **Restart the tunnel on the reporting host:** `sudo systemctl restart wg-quick@zcache0`; it restarts no container and drops the link's traffic for the seconds the interface is down.
5. **Confirm by value:** the Cache board's panel 105 falls below 180 for the pair, and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-wg-handshake-stale` is absent from `infra/grafana/alerts.yaml`, or `zcache_wireguard_handshake_age_seconds` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.
