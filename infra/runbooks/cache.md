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

`SENTINEL failover zcache` makes the Sentinel you ask promote a replica without waiting for the others to agree the primary is down; it picks by `replica-priority`, then by replication offset, so from valkey1 the primary moves to valkey2 and from valkey2 to valkey1, and valkey3 is picked when it is the one replica left. The old primary is turned into a replica of the new one. The engine holds its connection through the proxy on its own host, whose checks cut the session at the switch (`on-marked-down shutdown-sessions`); the library reconnects lazily, on the engine's next write, which it drops, so the store is behind by that write, which nothing replays — the outage line under `zcrypto-engine-cache-write-failed` below — and the engine's next restart is taken flat: do it inside an engine inter-cycle gap while the engine is flat, by preference.

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

Nothing fired. You changed the cache role's Valkey or Sentinel template and mean a node to run it, or `cache-rejoin-node` sent you here because a node's own files are broken. A password changed in `group_vars/cache_host/vault.yml`, or `cache_engine_password` or `cache_sentinel_requirepass` changed in `group_vars/all/vault.yml`, is `cache-password-rotation` below, not this procedure: a node reset alone to a new password fails to authenticate to, and from, the nodes still holding the old one.

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

Nothing fired. You mean to change a password in `group_vars/cache_host/vault.yml`, or `cache_engine_password` or `cache_sentinel_requirepass` in `group_vars/all/vault.yml`, or a converge's drift report named `valkey.conf`, `sentinel.conf` or `users.acl` after one changed there, since their renders carry the passwords.

### What it means

The nodes authenticate to each other: a replica to its primary with the `replica` password, each Sentinel to each Valkey with the `sentinel` password and to the other Sentinels with Sentinel's `requirepass`. A node reset alone to a new password fails to authenticate to, and from, a node still holding the old one, so the three nodes' files are replaced in one stop, the set down for the minutes it takes, inside an engine inter-cycle gap while the engine is flat: the engine authenticates with the `engine` password and its proxy checks the Sentinels with their `requirepass`, both rendered on the engine host from `group_vars/all/vault.yml`, and between the nodes' stop and the engine converge of step 6 the engine holds no session the new passwords admit, its writes are dropped and the store is behind — the outage the `zcrypto-engine-cache-write-failed` section below describes, whose restart is that converge. The rendered files name valkey1 as the first primary, so valkey1 holds the primary before the stop and starts first, and no write the set took is lost. `vk` and `sn` read their passwords from files a converge carrying the node's image digest re-renders, and Alloy reads the exporter password and `requirepass` from a secrets file a converge carrying the Alloy digest re-renders and the container reads when it is recreated. The stop fires `zcrypto-cache-primary-count` once its two minutes pass, and it clears when step 5 is done on valkey2, the second node whose Sentinel and Alloy run on the new passwords; `zcrypto-cache-replicas-short` fires when valkey3's step 5 comes more than five minutes after valkey1's, and clears when valkey3's replica connects.

### What to do

1. **Put the primary on valkey1 while the nodes still run the old passwords:** `cache-manual-failover` above, repeated until `sn SENTINEL get-master-addr-by-name zcache` names `10.98.0.11`. When a converge already carried the change, `vk` or `sn` answers `WRONGPASS` or `NOAUTH`: put the old value back in the vault file it changed in, `group_vars/cache_host/vault.yml` or, for `cache_engine_password` and `cache_sentinel_requirepass`, `group_vars/all/vault.yml`, converge each node with the two digests it runs, read as step 3 reads them — step 5's command without `-e cache_config_reset=true` — and begin here again.
2. **Change the password** in `group_vars/cache_host/vault.yml`, or in `group_vars/all/vault.yml` for `cache_engine_password` and `cache_sentinel_requirepass`, by the recipe in the cache file's header, merged to `develop`, which the converges below run from. Steps 3 to 6 follow in the same sitting, and no other converge that renders a password — a `cache-config-reset` on another node, an Alloy bump's cache leg, an engine converge of `zcrypto` — runs between this merge and step 6: a cache converge without the reset in that window renders the new password into the env files its digests gate, against a `users.acl` and a Sentinel `requirepass` still holding the old one, and two nodes in that state page `zcrypto-cache-primary-count` on a healthy set; an engine converge in it — an arm or disarm, the rollout skill's same-day shape — renders the new `engine` password into `engine.env` or the new `requirepass` into `haproxy.cfg` against nodes still holding the old, and its handler restarts the engine into `failed to create cache database backing` at ten-second intervals until step 6.
3. **Read each node's running digests**, on each node: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, then Alloy's.
4. **Stop the three nodes, valkey3 and valkey2 before valkey1:** `sudo systemctl stop zcrypto-cache.service` on each.
5. **Converge each node with the reset, valkey1 first, and recreate its Alloy before the next node's converge**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`, which renders the node's files and starts its daemons; then, on the node, `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`, which recreates Alloy so it reads the new secrets.
6. **Converge the engine host in the same gap, the one engine converge step 2 admits between the merge and here**, when `cache_engine_password` or `cache_sentinel_requirepass` changed: `./scripts/converge.sh site.yml --limit zcrypto -e converge_primary=true -e engine_image_digest=sha256:<the running engine digest> -e cache_proxy_image_digest=sha256:<the running proxy digest> --tags engine`, both digests read off the containers as `docs/reference/fleet-pins.md` prescribes; it re-renders `engine.env` and `haproxy.cfg` and its handler restarts the engine and the proxy, the restart `engine-restart-margin-position` in `infra/runbooks/engine-procedures.md` admits while flat.
7. **Confirm by value:** on valkey2 and valkey3, `cache-rejoin-node` steps 3 and 4; on each node, `sn SENTINEL ckquorum zcache` answers `OK 3 usable Sentinels`; from the workstation, `uv run python infra/scripts/grafana-query.py 'redis_up{host=~"zcrypto-valkey[123]"}'` reads 1 on six series, a node's `valkey` and `sentinel` each.

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
3. **Read the container's state through named fields** — its environment holds the Grafana Cloud push credentials and the two cache passwords, so read these fields by name and not `.Config` whole, `.Config.Env`, `docker exec … env` or `docker compose config`: `sudo docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}} oom={{.State.OOMKilled}}'`. `oom=true` means it hit its 384 MiB cap; `fleet.md#zcrypto-fleet-alloy-memory-headroom` is the warning that precedes it.
4. **Read its logs:** `sudo docker logs grafana-alloy --since 1h 2>&1 | tail -100`. A config parse error names the line; a remote_write auth failure names the credential; a Redis exporter error naming `NOAUTH` or `WRONGPASS` is the exporter password and the node's ACL disagreeing, which leaves `up` present and is `zcrypto-cache-daemon-down` below, not this alert.
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

**No agreed primary**: a failover did not complete — fewer than two Sentinels agree the old primary is down, or no replica is eligible — or two of the three Sentinels are down, and cache writes have nowhere to land; the engine's failed writes page `zcrypto-engine-cache-write-failed` below, and the store is behind from the first one. One node's telemetry going dark does not fire it: the other two Sentinels still name the primary. The rule stays quiet while fewer than two nodes' telemetry ships, which the Alloy-dark alerts own. A node that still reads `role:master` after the Sentinels moved the primary is not counted here; `cache-rejoin-node` turns it back into a replica.

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
3. **Stale images**, from the workstation: `uv run python infra/scripts/prune-host-images.py zcrypto-valkey<N>` lists what it would remove; `--apply` removes it, and `--keep <digest12>` spares one staged for a converge.
4. **The cache's own directory growing** is Valkey's AOF between rewrites: `zcrypto-cache-aof-not-ok` above reads the rewrite's state.
5. **Read Valkey on the node:** `vk INFO persistence`. No Valkey to answer is one that exited on the full disk and was not brought back: restart the node's containers, `sudo systemctl restart zcrypto-cache.service`, then confirm by `cache-rejoin-node` steps 3 and 4. An answer reading `rdb_last_bgsave_status:err` is a Valkey still refusing writes, which reads `ok` once a snapshot succeeds on the freed disk.
6. **Confirm by value:** the Cache board's panel 104 reads above 0.15 for the node, `vk INFO persistence` on it reads `rdb_last_bgsave_status:ok`, and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-disk-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-wg-handshake-stale"></a>

## zcrypto-cache-wg-handshake-stale — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · mesh peer handshake stale`: a mesh member, the engine host `zcrypto` or a cache node, reads a WireGuard handshake age past five minutes with one of its peers. The host the notification names is the end reporting it; the `peer` label is the other end's mesh address — `10.98.0.1` the engine host, `10.98.0.11` to `10.98.0.13` Cache 1 to Cache 3. A stopped probe timer reads the same way, since the rule adds the probe file's own age.

### What it means

`PersistentKeepalive 25` keeps traffic on every link, so a healthy peer re-handshakes about every two minutes, and the reading runs up to two minutes behind the tunnel, the probe's minute and the scrape's. Past 300 the link has missed WireGuard's 180 s key lifetime and is down: replication between two nodes, or the engine's cache traffic to one node, is not flowing. A link seen from both ends fires twice, once per reporting end.

### What to do

1. **Is it the probe?** On the reporting host, `systemctl status zcache-probe.timer` and `ls -l --time-style=full-iso /var/lib/zcrypto-node-textfile/zcache.prom`: a file older than two minutes is the timer, and `journalctl -u zcache-probe.service -n 20 --no-pager` says why.
2. **Read the tunnel on both ends:** `sudo wg show zcache0` on the reporting host and on the peer, the engine host (alias `zcrypto`) for `10.98.0.1`. A peer with no `latest handshake` line has not reached it since the interface came up.
3. **Is the peer's port open?** Both layers carry `51821/udp`: the host's nftables, which the firewall role renders and `sudo systemctl status nftables` shows loaded on each end; and the Linode Cloud Firewall, managed by hand, in the Linode console for each end.
4. **Restart the tunnel on the reporting host:** `sudo systemctl restart wg-quick@zcache0`; it restarts no container and drops the link's traffic for the seconds the interface is down.
5. **Confirm by value:** `sudo wg show zcache0` on both ends reads the pair's `latest handshake` under three minutes, the key lifetime; the Cache board's panel 105 falls below 300 for the pair, and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-wg-handshake-stale` is absent from `infra/grafana/alerts.yaml`, or `zcache_wireguard_handshake_age_seconds` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.

______________________________________________________________________

<a name="zcrypto-cache-daemon-down"></a>

## zcrypto-cache-daemon-down — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · a node's Valkey or Sentinel is down`: for ten minutes a node's exporter has read `redis_up` 0 for its Valkey or its Sentinel while the node's Alloy ships. The notification names the node and the `job`, `valkey` or `sentinel`; the Cache board's *Valkey and Sentinel answering the exporter, the lowest per node and daemon* panel (306) shows each node's two daemons, the rule's own value.

### What it means

Two causes read the same. The daemon's process is down inside `zcrypto-cache.service`, its container stopped or restarting. Or the daemon runs and the exporter's login is refused, a `NOAUTH` or `WRONGPASS` on the `exporter` user after a password change, which `cache-password-rotation` above applies to the three nodes in one stop. A Sentinel down matters beyond its node: the quorum is two of three, so with one Sentinel down, losing another node leaves one Sentinel, below the quorum, and the set can no longer move its primary. A Valkey down on a replica leaves the primary one replica short, which `zcrypto-cache-replicas-short` above pages; a Valkey down on the primary is failed over by the Sentinels within seconds, and this alert then names the old primary's node. A node whose Alloy is dark ships no `redis_up` at all, which the Alloy-dark alerts above own.

### What to do

1. **Is the daemon running?** On the node, `db<N>`: `sudo systemctl status zcrypto-cache.service` and `sudo docker ps --filter name=zcrypto-`. A container missing or restarting is the process cause.
2. **Does it take a login?** On the node, with the two functions above: `vk PING` for Valkey, `sn PING` for Sentinel. `NOAUTH` or `WRONGPASS` is the node's files and the passwords disagreeing, which `cache-password-rotation` above resolves.
3. **Read the exporter's own error:** `sudo docker logs --since 10m grafana-alloy 2>&1 | grep -i redis` on the node. `NOAUTH` or `WRONGPASS` there while `vk PING` and `sn PING` answer `PONG` is Alloy holding a stale password: `cache-password-rotation` step 5's command without `-e cache_config_reset=true`, then its Alloy recreate.
4. **Restart the daemons when the process is down:** `sudo systemctl restart zcrypto-cache.service` on the node, failing the primary over first with `cache-manual-failover` above when `sn SENTINEL get-master-addr-by-name zcache` on another node names this node's mesh address.
5. **Confirm by value:** the Cache board's panel 306 reads `UP` for the node and daemon, and the rule is back to **Normal** in Grafana's alert rules; a quiet channel is not the clear.

### Retire when

`zcrypto-cache-daemon-down` is absent from `infra/grafana/alerts.yaml`, or `redis_up` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.

______________________________________________________________________

<a name="zcrypto-cache-valkey-rss-headroom"></a>

## zcrypto-cache-valkey-rss-headroom — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · Valkey resident memory above 70% of its container cap`: for five minutes a node's Valkey has held more than 70% of its 256 MiB container cap resident. The Cache board's *Valkey resident memory against its 256 MiB cap* panel (214) draws the three nodes against the red line at 0.7, beside *Memory against maxmemory* (209).

### What it means

Valkey's resident memory runs above its used memory by fragmentation, or by the pages the append-only-file rewrite's child copies on write while it runs; `zcrypto-cache-memory-70pct` reads used memory against `maxmemory` and sees neither. The cap is the compose `memory:` limit on the Valkey container: at it the kernel OOM-kills the container, which restarts, and on the primary's node that is a failover.

### What to do

1. **Read the memory**, on the node, `db<N>`: `vk INFO memory`, its `used_memory_rss` and `mem_fragmentation_ratio` lines.
2. **Is a rewrite running?** `vk INFO persistence`, its `aof_rewrite_in_progress` line. `1` is a rewrite whose copy-on-write ends with it: read step 1 again once it reads `0`.
3. **Fragmentation that stays**, a `mem_fragmentation_ratio` well above 1 with no rewrite running: `vk MEMORY PURGE` on the node, then step 1 again.
4. **Resident memory still up after the purge:** restart the node's daemons, `sudo systemctl restart zcrypto-cache.service`, one node at a time and replicas first; on the primary's node, run `cache-manual-failover` above first so the primary moves on your schedule.
5. **Confirm by value:** the Cache board's panel 214 reads under 0.7 for the node, and the rule is back to **Normal** in Grafana's alert rules.

### Retire when

`zcrypto-cache-valkey-rss-headroom` is absent from `infra/grafana/alerts.yaml`, or `redis_memory_used_rss_bytes` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.

______________________________________________________________________

<a name="zcrypto-cache-proxy-no-backend"></a>

## zcrypto-cache-proxy-no-backend — ALERT

### What you are seeing

A **critical** Grafana alert, `Cache · proxy has no backend`. For over 2 minutes no backend of the engine's cache proxy has had two Sentinel checks passing: `max(haproxy_backend_active_servers{host="zcrypto"}) or on() vector(0)` read below 2, the frontend's own routing bound.

### What it means

The proxy is HAProxy in the engine's compose project on `zcrypto`, container `zcrypto-cache-proxy`, the engine's only route to the cache set: it routes `6379` to the backend two of the three Sentinels name the primary, each backend a node and each of its servers one Sentinel's check of that node, so a backend with one check passing routes nothing new. Fewer than two passing on every backend means the set has no primary its quorum names (`zcrypto-cache-primary-count` fires beside this), the proxy cannot reach the Sentinels over the `zcache0` mesh (`zcrypto-cache-wg-handshake-stale` on the engine host), or the proxy container is down, which takes the series away and reads 0 through the fallback — as does the primary's Alloy gone dark or `zcrypto` itself down, which take every series of the host with them; step 2's `curl` on the host tells a proxy that answers from one that is gone. Meanwhile every cache write the engine makes fails: the library logs each at ERROR (`zcrypto-engine-cache-write-failed` below) and drops it, and nothing is replayed when the route returns — the store is behind from the first dropped write, and the engine's next restart is taken flat. The engine itself keeps trading: the cache is an accelerator and a recovery, never the authority on what is open. A running engine, that is: no engine start succeeds while this fires, since the node's `run()` creates the cache backing before any venue client connects and raises `failed to create cache database backing` inside about a minute, the unit restarting into it every ten seconds and `zcrypto-engine-error-logs` paging on the traceback ([`engine.md#zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs)) — so hold every restart, an arm or disarm converge, a kill-file clear and a `systemctl restart` alike, until the route is back; one that cannot wait is a re-converge of the engine host with the running digests and `-e engine_cache_enabled=false`, an engine without the cache, whose start is a cold one that the restart rule's test refuses with a position open. With the cache disabled on purpose — `engine_cache_enabled: false` on the engine host, the rollout's abort — the engine runs without the proxy and this page is no incident of the engine's: silence it until the cache is re-enabled, and work the proxy's route on its own clock.

### What to do

1. **Read the set first**, on one cache node: `sn SENTINEL get-master-addr-by-name zcache`. No answer, or three answers that disagree, is the set's incident: `zcrypto-cache-primary-count` above. An agreed address means the proxy does not see it.
2. **Read the proxy's checks**, on `zcrypto`: `sudo docker ps --filter name=zcrypto-cache-proxy` for the container, then `curl -s 127.0.0.1:9104/metrics | grep -E 'haproxy_server_(status|check_status)'` for each server's last check. The Cache board's proxy row shows the same per backend and Sentinel.
3. **Read the mesh from the engine host**: `sudo wg show zcache0 latest-handshakes` names each cache node's mesh address with the seconds since its last handshake; a stale one is `zcrypto-cache-wg-handshake-stale`'s procedure, on the engine host's side.
4. **Read the proxy's own lines**: on `zcrypto`, `sudo journalctl -u zcrypto-engine --since -30m | grep zcrypto-cache-proxy | tail -50`, or the Logs board with container `cache-proxy`. A `WRONGPASS` or `NOAUTH` in a check's reply is the Sentinel `requirepass` disagreeing between the rendered config and the nodes: `cache-password-rotation` above.
5. **Read first whether the unit was stopped on purpose** — `systemctl is-active zcrypto-engine` on `zcrypto`, the kill file `/var/lib/zcrypto-engine/exec/kill`, and the flatten record: an engine the red button or a latched kill file left stopped stays stopped until its reason is decided ([`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten)), and this rule is silenced for that stop rather than answered with a restart. **A proxy container down or wedged under a running engine is restarted with the engine**, inside the inter-cycle gap while the engine is flat, since the unit runs both: `sudo systemctl restart zcrypto-engine`, under [the restart rule](engine-procedures.md#engine-restart-margin-position), once steps 1 to 3 read a quorum-named primary the proxy reaches, since a start under a routeless proxy fails as *What it means* says. A config fault is a converge of the engine host with the running digests, not a host edit.

**Verify by value:** `uv run python infra/scripts/grafana-query.py 'max(haproxy_backend_active_servers{host="zcrypto"})'` reads 2 or 3 with the rule back to **Normal**; `(no series)` is the proxy still dark, not a zero. Then read the engine's next cache write: a `nautilus_infrastructure::redis::cache` line in Loki after the route returned is the one dropped write, and the store is behind by it and by everything written while the route was down.

### Retire when

`zcrypto-cache-proxy-no-backend` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/engine/templates/compose.yaml.j2` no longer renders a `cache-proxy` service.

______________________________________________________________________

<a name="zcrypto-cache-proxy-no-engine-session"></a>

## zcrypto-cache-proxy-no-engine-session — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · engine running with no session through the proxy`. For over 15 minutes the engine's scrape has read 1 while the proxy carried no session: `sum(haproxy_backend_current_sessions{host="zcrypto"})` read 0 with `up{job="engine_app",host="zcrypto"}` at 1.

### What it means

The engine's link to the cache was cut and not yet re-made. The library holds two connections through the proxy from a start that was never cut — the load's, which idles once the store is read, and the writer's — and reconnects lazily: the next write after a cut of the writer's connection fails and is dropped, the write after that opens a fresh connection for the writer, and the load's connection never comes back, so a healthy engine reads 2 sessions from a start never cut, and 1 or 2 after a cut, by whether the cut took the load's connection. A cut is a failover's `shutdown-sessions`; one Sentinel's check going down on the routed backend — each server entry is that backend's node checked through one Sentinel, the default roundrobin balance spreads the engine's sessions over the three, and `on-marked-down shutdown-sessions` closes the sessions an entry carries, so a replica node's reboot, a Sentinel restart or a mesh blip to one node cuts the sessions routed through it; a proxy restart; the `zcache0` interface restarted by a `cache-link` converge; or a node reboot under the primary. After a cut of both connections — a failover, a proxy restart, a dead link — an engine idle between cycles shows no session for as long as it makes no write, which is what this page reads; after a per-entry cut it shows 1 and this page stays quiet: one of the writer's alone is paged by the dropped write's ERROR at the next write ([`#zcrypto-engine-cache-write-failed`](#zcrypto-engine-cache-write-failed)), and one of the load's alone drops no write. The store is behind by the dropped write and by everything written while the link was down, nothing replays it, and the engine's next restart is taken flat. The engine keeps trading. With the cache disabled on purpose — `engine_cache_enabled: false` on the engine host, the rollout's abort — the engine holds no session by design and this page is no incident: silence it until the cache is re-enabled.

### What to do

1. **Read what cut it**: the Cache board's proxy row for a route change (`Backend status per node` moved), `zcrypto-cache-primary-count` or `cache-manual-failover` for a failover, the deploy log for a `cache-link` or engine converge, and on `zcrypto` `sudo journalctl -u zcrypto-engine --since -1h | grep zcrypto-cache-proxy` for the proxy's own lines.
2. **Wait for the engine's next write**, at its next boundary cycle at the latest: the session returns at the write after the dropped one, and the alert clears itself. Nothing on the host re-makes it sooner without a restart.
3. **Treat the store as behind** from this cut until the engine's next restart, which is taken flat: [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test refuses a restart with a position open once a cache outage has fired since the boot.

**Verify by value:** `uv run python infra/scripts/grafana-query.py 'sum(haproxy_backend_current_sessions{host="zcrypto"})'` reads 1 or more with the rule back to **Normal**.

### Retire when

`zcrypto-cache-proxy-no-engine-session` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/engine/templates/compose.yaml.j2` no longer renders a `cache-proxy` service.

______________________________________________________________________

<a name="zcrypto-engine-cache-write-failed"></a>

## zcrypto-engine-cache-write-failed — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · the engine's cache writes failed`. In the last 15 minutes the engine's library logged at least one line naming `nautilus_infrastructure::redis::cache`, shipped from the unit's journal as `container="engine-nautilus"`: `[ERROR] … broken pipe` or `Connection refused (os error 111)` for a write it could not deliver, or `[WARN] … Cannot update order in Redis, no existing state at …` for an event on an order whose key an outage lost.

### What it means

**The store is behind, and it stays behind.** After a cache outage — a proxy without a backend, a session cut by a failover or by one Sentinel's check going down on the routed backend, a dead link — the library reconnects lazily on the next write, which fails and is dropped, and the write after it opens a fresh connection; nothing written during the outage is replayed. An order whose creating write was lost never gets its key and logs the WARN on every later event; a lost position key is a silent no-op. So the store is behind by everything written while the link was down and by the dropped write, and the engine's next restart is taken flat: [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test refuses a restart with a position open once this, `zcrypto-cache-proxy-no-backend` or `zcrypto-cache-proxy-no-engine-session` has fired since the engine's last boot. Detection comes from writes alone: nothing is logged at the cut itself, and an engine idle between cycles logs nothing about an outage, which the no-session rule covers from the proxy's side. The engine itself keeps trading.

### What to do

1. **Read the lines** on the Logs board, container `engine-nautilus`, or on `zcrypto`: `sudo journalctl -u zcrypto-engine --since -1h | grep 'redis::cache'`. A burst of `Connection refused` is the proxy or the set down: `zcrypto-cache-proxy-no-backend` above. One `broken pipe` and nothing after is a cut the reconnect has taken.
2. **Read the proxy** as `zcrypto-cache-proxy-no-backend`'s steps 1 to 4 do, if it fires beside this; a `WRONGPASS` or `NOAUTH` in the library's line is the `engine` password disagreeing between `engine.env` and the nodes' ACL: `cache-password-rotation` above.
3. **Record the outage against the boot**: the engine's next restart is taken flat whatever the positions page reads, until a boot line after it counts the positions again.

**Verify by value:** the next boundary cycle's writes log no `redis::cache` line: in Grafana Explore over the Loki datasource, `{host="zcrypto", container="engine-nautilus"} |= "redis::cache"` returns no line after that cycle, while `{host="zcrypto", container="engine", level=~".+"}` returns the cycle's own lines for the same window — the second read is what makes the first empty result a clean window and not a dead shipper — and the rule reads **Normal** in Grafana's alert list, where no resolve message announces it, since the `logs` receiver sends none; the store's lag is not read back from here, since nothing replays it.

### Retire when

`zcrypto-engine-cache-write-failed` is absent from `infra/grafana/alerts.yaml`, or `roles/capture/files/config.alloy` no longer labels nautilus's lines `engine-nautilus`.
