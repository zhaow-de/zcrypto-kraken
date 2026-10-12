# Bridgehead runbooks — the internet access host

You are here because **an alert fired in Slack** — find the section whose anchor matches the alert `uid` — or because you mean to revoke a client certificate, ship its Alloy config, cut the public SSH relay or sync its Caddy apt mirror: the procedures at the top, found by heading. Each section is written to be actioned without opening any other document.

One Linode VPS, `zaccess`, reached as `ssh access`; its WireGuard tunnel ends on `zcrypto-ops`, `ssh hp`. It runs no containers — Alloy, Caddy and WireGuard are apt packages — and holds no capture data: everything on it is re-issuable.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="zaccess-revoke-client-cert"></a>

## zaccess-revoke-client-cert — PROCEDURE: revoking a client cert

### What you are seeing

Nothing fired. A client certificate is to lose its access to the mTLS edge.

### What it means

The pins are PEMs in `infra/ansible/roles/access/files/pinned-leaves/`: `access_pinned_leaves` globs that directory and the Caddyfile template renders one `file /etc/caddy/pinned-leaves/<name>.pem` line per PEM inside its `verifier leaf` block, so deleting a PEM and converging drops the pin, and the `reload caddy` handler makes the running edge refuse that leaf at its next handshake. The role ships the directory with `ansible.builtin.copy`, which has no delete, so the host keeps a PEM the repo no longer has — inert, the Caddyfile no longer names it. A task failing after the Caddyfile is written strands that reload (`force_handlers` is off): the file is revoked and the running Caddy is not, which is why the confirm is a handshake, not a grep. The edge gates `:443` alone; SSH on `:10022` and the relay on `:20022` do not pass through it. Deleting the last PEM renders an empty `verifier leaf { }` block, and what Caddy does with that is recorded nowhere in this tree — the procedure assumes another pin remains. The converge also runs the bridgehead's Alloy part, after the Caddyfile and its reload, and its preview fetches the Grafana repository's signing key: a key source that does not answer fails the preview, `converge.sh` refuses the whole converge, and the revocation waits until the source answers.

### What to do

1. **If `<name>.pem` is the only PEM under `pinned-leaves/` (set: the tracked PEMs under `infra/ansible/roles/access/files/pinned-leaves/`, one rendered `file` line each in the Caddyfile's verifier block; count: `infra/scripts/count-list.sh pinned-leaves-the-edge-renders`), issue its replacement first** — `infra/scripts/zaccess-client-cert.sh issue <new-name>` (it refuses a name that exists) — and converge that in before revoking. **The vault holds one bundle**: before you vault `<new-name>`'s, which the issue script's own next-step line tells you to do, extract `<name>`'s with `infra/scripts/zaccess-extract-client-cert.sh --name <name> --out-dir <dir>`, `<dir>` absolute because the script changes directory first — step 4 needs the two files it writes, so keep them past the script's "DELETE both local files", which means `<new-name>`'s, until step 4 is done; re-vaulting the replacement overwrites the slot.
2. **Delete the PEM from the repo and converge** — `infra/ansible/roles/access/files/pinned-leaves/<name>.pem`, then `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` from the workstation — the bridgehead converges like any other host (no count command: `converge.sh` appends one row per pass to `docs/reference/deploy-log.jsonl`, and the bridgehead's first row lands with its next converge), and the line lands in `docs/reference/deploy-log.jsonl`. This is the revocation; the steps below tidy up and prove it.
3. **Remove the host copy** — `sudo rm /etc/caddy/pinned-leaves/<name>.pem` on the bridgehead, for hygiene.
4. **Confirm by value — the revoked leaf is refused at the handshake.** `grep -c 'pinned-leaves/<name>.pem' /etc/caddy/Caddyfile` reading 0 proves the render only (no count command: the running Caddy's pins are process state the tree does not hold). Using the bundle step 1 extracted — `<name>`'s, not `<new-name>`'s, which is still pinned and would answer — `openssl pkcs12 -in <dir>/zaccess-<name>.p12 -passin file:<dir>/zaccess-<name>.p12.pass -nodes -out leaf.pem`, then `timeout 30 curl -sv --cert leaf.pem https://tmux.zaccess.zhaow.me/ -o /dev/null 2>&1 | grep -c '^< HTTP/'` reads 0 and the trace ends in a TLS alert. A `< HTTP/` line means the running Caddy still pins the leaf: `sudo systemctl reload caddy`, re-run. Delete `leaf.pem` and the two extracted files after.

### Retire when

`infra/ansible/roles/access/templates/Caddyfile.j2` no longer renders one `file` line per PEM from `access_pinned_leaves` — the glob is what makes deleting the PEM the revocation.

______________________________________________________________________

<a name="zaccess-alloy-converge"></a>

## zaccess-alloy-converge — PROCEDURE: shipping an Alloy config change to the bridgehead

### What you are seeing

Nothing fired. You are changing the bridgehead's `config.alloy` and looking for the digest operand the container Alloys take.

### What it means

There is none: **the bridgehead's Alloy takes no digest operand and owes no bake.** It is the apt package, installed at the fleet's version — `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml`, or while the bridgehead is held, the version `infra/ansible/host_vars/zaccess/alloy.yml` names — held in `dpkg` and pinned at priority 1001, so an `apt upgrade` leaves it where it is; the version moves only through the bump skill, `.claude/skills/zcrypto-bump-alloy/SKILL.md`, its rollback included. `--limit zaccess --tags alloy` runs the role's Alloy part alone, nothing of Caddy, WireGuard, the SSH relay or the probe (`tests/test_access_alloy_tag.py`), and copies `config.alloy` only once `alloy validate` has read it with the installed binary. The copy is ungated: every converge of the role ships it, so a hand edit cannot outlive the next run. The preview fetches the Grafana repository's signing key, and a key source that does not answer refuses the converge.

### What to do

1. Edit `infra/ansible/roles/access/files/config.alloy`, then `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags alloy` from the workstation.
2. Read the version and the hold on the host: `dpkg-query -W alloy; apt-mark showhold` names the version the converge installed and lists `alloy`.

### Retire when

`infra/ansible/roles/access/tasks/main.yml` no longer imports the shared Alloy install, `alloy_apt`: the bridgehead's Alloy then installs some other way, which this section does not describe.

______________________________________________________________________

<a name="zaccess-cut-ssh-relay"></a>

## zaccess-cut-ssh-relay — PROCEDURE: cutting the public SSH relay into the ops node

### What you are seeing

Nothing fired. You mean to close the internet's path into `zcrypto-ops:22` through the bridgehead's `:20022` while the bridgehead itself stays up.

### What it means

The relay is `zaccess-ssh-proxy.socket`, listening on `:20022`, and the `zaccess-ssh-proxy.service` it activates, which relays each connection to `10.99.0.2:22` over the tunnel. **Stopping `wg-quick@zaccess0` does not cut it.** The socket keeps listening, and the next connection on `:20022` starts the service, whose `Requires=` starts the tunnel again.

### What to do

1. On the bridgehead, stop both: `sudo systemctl stop zaccess-ssh-proxy.socket zaccess-ssh-proxy.service`.
2. Confirm: `systemctl status zaccess-ssh-proxy.socket` reads `inactive (dead)`, and a connection to `zaccess.zhaow.me:20022` is refused.
3. A converge that runs the whole `access` role reopens it — `--tags access`, as `zaccess-revoke-client-cert` above runs it, or un-tagged — and so does a reboot, through `sockets.target`; `--tags alloy` runs none of the relay's tasks and leaves it closed. To reopen: `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` from the workstation.

### Retire when

`infra/ansible/roles/access/templates/zaccess-ssh-proxy.service.j2` drops its `Requires=wg-quick@zaccess0.service`, so a connection on `:20022` no longer starts a stopped tunnel.

______________________________________________________________________

<a name="zaccess-caddy-mirror"></a>

## zaccess-caddy-mirror — PROCEDURE: syncing and reading the Caddy apt mirror

### What you are seeing

Nothing fired. You mean to bring a Caddy release onto the bridgehead's mirror before its daily sync and onto the bridgehead's own Caddy, or to read whether the mirror is current. Or a converge of the observability node or the dead-man node refused in its preview with `https://apt.zaccess.zhaow.me/dists/any-version/Release answers <status>`, or a read of that address answered other than `200`.

### What it means

The bridgehead mirrors the vendor's Caddy apt repository, one suite (`any-version`), `amd64` and `main`, with `debmirror`, run by `zaccess-caddy-mirror.service` from a daily timer, and its Caddy serves the copy publicly at `https://apt.zaccess.zhaow.me`, `/dists/` and `/pool/` alone. A sync runs over `/var/lib/caddy-apt-mirror/staging`, a hard-linked copy of `/var/lib/caddy-apt-mirror/served`, and the unit exchanges the two trees once debmirror has ended without an error, so the served tree is the last sync that passed and a failed sync leaves it as it was. The vendor's repository is read by the sync alone, so a vendor outage delays a Caddy release and breaks no apt refresh. The observability node and the dead-man node install Caddy from that address, the bridgehead from the served tree on its own disk. The copy keeps the vendor's signed `Release`, and apt on each node checks its signature against the vendor key the converge installs at `/etc/apt/keyrings/caddy-archive-keyring.gpg`; Debian's own older `caddy` is pinned out, so a node whose mirror holds no Caddy fails its install rather than taking Debian's. A `--tags alloy` converge of the observability node or the dead-man node reads nothing of the mirror before its apt refresh, so a procedure that takes one reads it first. A new bridgehead's first access converge syncs the mirror before it installs Caddy, so that converge needs the vendor's repository to answer.

### What to do

1. **Sync now**: `ssh access 'sudo systemctl start zaccess-caddy-mirror.service'` returns when the sync has ended, and prints `Job for zaccess-caddy-mirror.service failed` when it failed.
2. **Read the sync's result**: `ssh access 'systemctl show -p Result -p ExecMainExitTimestamp zaccess-caddy-mirror.service'` reads `Result=success` and the time the sync ended. `Result=exit-code` is read by `ssh access 'sudo journalctl -u zaccess-caddy-mirror.service -I --no-pager'`, the last sync's lines whole, whose indented lines under `Errors:` name each failure, while the mirror goes on serving the last sync that passed. A `Download of pool/… failed: 404 …` is the vendor's repository answering without a file its index names, on which the syncs keep failing until the vendor serves the file, so it goes to the owner the day it is read. A `Download of … failed: 500 Can't connect to …` naming a reason in parentheses other than `(Connection refused)` or `(Connection timed out)` — `(certificate verify failed)` or `(hostname verification failed)` among them — is the bridgehead failing to trust or reach the vendor, a failure on its own side that a later sync need not pass, so it goes to the owner the day it is read. A `Download of … failed: 402 …`, another `Download of … failed: 5…` — among them a `500 Can't connect to …` naming `(Connection refused)`, `(Connection timed out)` or no reason — or a `read timeout at …` is the vendor's repository not answering, which a later sync passes. A line naming `signature does not verify` goes to the owner, since the vendor has rotated its key and each sync fails there until a change vendors the new one. Another failure, or another `Result=`, goes to the owner.
3. **Read whether the mirror is current**: `curl -fsS https://apt.zaccess.zhaow.me/dists/any-version/Release | grep '^Date:'` and `curl -fsS https://dl.cloudsmith.io/public/caddy/stable/deb/debian/dists/any-version/Release | grep '^Date:'` print the same `Date:` on a current mirror. A mirror whose `Date:` is more than a month older than the vendor's goes to the owner, one less than a month older to step 2. A mirror read that prints curl's error in place of a `Date:` is step 6's, by that error. A vendor read that prints curl's error in place of one leaves the mirror's age unread: the mirror's `Date:` is the vendor's at the last sync that passed, which moves when the vendor publishes and not when the mirror syncs, so a current mirror's can be more than a month old after a month without a release, and step 2's read of the last sync stands for it. Another answer goes to the owner.
4. **Read what a node installs from**: `ssh mon 'apt-cache policy caddy'`, or `ssh hc`, names `https://apt.zaccess.zhaow.me any-version/main` under the candidate, and Debian's `caddy` at priority `-1`. Another answer goes to the owner.
5. **Upgrade the bridgehead's own Caddy**, after step 1, for a Caddy security release the day it is read. First, `ssh access 'sudo cat /var/lib/caddy-apt-mirror/caddy-rollback'` prints `No such file or directory` while no Caddy rollback by `zaccess.md`'s `zaccess-caddy-mirror` step 5 awaits the owner's answer, and another answer is a hold, which goes to the owner with what it printed: a version it prints is the one rolled back from, which stays the mirror's candidate until the record is removed on that answer, and the upgrade waits through a hold. Then, before the install, `ssh access 'sudo apt-get update && apt-cache policy caddy'` prints `Candidate: <the version of the security release>`, the release this step installs: an older candidate is a sync that has not passed since the release, which steps 1 and 2 read, another answer goes to the owner, and the upgrade waits for either. `ssh access 'dpkg-query -W caddy'` prints the installed version, the version before, and three reads that decide a rollback below: `ssh access 'systemctl is-active caddy'` reads `active`, `curl -fsS -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/dists/any-version/Release` from the workstation reads `200`, the front door answering a client, and from the workstation `curl -s -o /dev/null -w '%{http_code} %{exitcode}\n' https://tmux.zaccess.zhaow.me/` prints `000 56` or `000 55`, the mTLS edge refusing a client without a certificate, where a front door or a name answering no client prints `000` with another exit code, curl's 35, 7 or 28 among them. An answer other than these before the install is not the upgrade's, and a rollback would not mend it: a mirror read other than `200` is step 6's, another answer goes to the owner, and the upgrade waits for either. Then `ssh access 'sudo apt-get update && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade caddy=<the version of the security release> && sudo systemctl restart caddy'`, and four reads: `ssh access 'apt-cache policy caddy'` reads the installed version equal to the candidate, and the three reads above, again. An installed version other than the candidate goes to the owner. A Caddy that does not read `active`, a mirror read other than `200`, or a `tmux.` read other than `000 56` or `000 55` after the install, the three having read so before it, is the upgrade's: it leaves the front door down or open to a client without a certificate, so it is rolled back at once to the version before, which the mirror keeps, by a line that records the rollback first and downgrades whatever the record's write does: `ssh access 'echo <the version rolled back from> | sudo tee /var/lib/caddy-apt-mirror/caddy-rollback; sudo apt-get -o Dpkg::Options::=--force-confold install -y --allow-downgrades caddy=<the version before> && sudo systemctl restart caddy'`; then the record's read above, which prints that version, and the `active`, mirror and `tmux.` reads again, and it goes to the owner. The record holds the observability node's and the dead-man node's next Caddy install and this step's next upgrade until the owner's answer, since the version rolled back from stays the mirror's candidate: their patch passes leave `caddy` out of their install and their rebuilds wait while it holds, and `ssh access 'sudo rm /var/lib/caddy-apt-mirror/caddy-rollback'` removes it on that answer. The observability node and the dead-man node take the release the same day, with `caddy=<the version of the security release>` in place of `caddy` in the install, once the four reads after the upgrade's install have read so, by the same-day patch their patch passes name, `mon.md`'s `mon-patch-pass` and `hc.md`'s `hc-patch-pass`, whose package step syncs this mirror first.
6. **A preview refused at the mirror read, or a read of it answering other than `200`**, by the answer, which a converge's refusal prints as `-1` with the uri module's message and a `curl` read as `000` with curl's own. `-1` with `CERTIFICATE_VERIFY_FAILED`, or `000` with `SSL certificate problem` (curl's 60), is the `apt.` site's certificate, whose renewal `ssh access 'sudo journalctl -u caddy --no-pager -n 200'` shows. `-1` with `TLSV1_ALERT_INTERNAL_ERROR`, or `000` with `tlsv1 alert internal error` (curl's 35), is a Caddy holding no `apt.` certificate, whose issuance the same journal shows; on a bridgehead without the mirror's units, the access converge below writes the site. `-1` with the connection refused or timed out, or `000` with `Could not connect to server` (curl's 7) or `Connection timed out` (curl's 28), is the bridgehead's Caddy down, which `ssh access 'systemctl status caddy'` reads, or the bridgehead itself where ssh does not answer, `zaccess-bridgehead-dark` below. `404` is a served tree without a passing sync, which step 1 mends and step 2 reads. An access converge, `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access`, mends a bridgehead without the mirror's units alone, `ssh access 'systemctl cat zaccess-caddy-mirror.service'` answering `No files found`, and is taken outside a relay cut, since it reopens a cut SSH relay (`zaccess-cut-ssh-relay` step 3). Another answer goes to the owner.

### Retire when

`infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2` is absent from the tree.

______________________________________________________________________

<a name="zaccess-bridgehead-dark"></a>

## zaccess-bridgehead-dark — ALERT

### What you are seeing

A critical-severity Grafana alert (`zcrypto-alloy-dark-zaccess`): the internet bridgehead's `up` series has been absent from Grafana Cloud for more than 10 minutes.

### What it means

The bridgehead runs Alloy **natively** (an apt package, no docker), as the observability node does, and nothing on the host reacts to that unit dying: no container to restart, one systemd unit. While it is dark, `zaccess-disk-high` — the only other rule scoped to `host="zaccess"` — reads no data, and `noDataState: OK` renders that identically to healthy. The two `zaccess_*` rules keep their ops-side half: `zaccess-tunnel-stale` still watches the tunnel from `host="ops"` and `zaccess-cert-expiring` still watches `target="nas-dsm"`. What goes unwatched are the `tmux` and `nas` edge certificates — only this host's probe writes those two targets.

### What to do

1. On the bridgehead: `systemctl status alloy` — is the unit running at all?
2. `journalctl -u alloy --no-pager -n 100` — a config parse failure is the usual cause here: a hand edit the last converge overwrote, or a credentials rotation that never reached `/etc/default/alloy`. The config copy is ungated — every converge ships it, with no drift assert — and runs `alloy validate` on the new file first, so a config the installed binary cannot load fails the converge before it lands (no count command: the copy task in `infra/ansible/roles/access/tasks/main.yml` is ungated by design and its own task name says so; `tests/test_access_alloy_tag.py` holds its validate).
3. `systemctl restart alloy` is the usual fix. If it will not stay up, `sudo grep -c '^GRAFANA_' /etc/default/alloy` — 6 means the credentials file is populated; fewer, or no file, means re-converge (`infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags alloy`) to re-render it. Count that file, never print it — it carries the Grafana Cloud push passwords (no count command: the file is rendered on the bridgehead, and its contents are secrets nothing in the tree reads).
4. Confirm recovery from the workstation: `uv run python infra/scripts/grafana-query.py 'up{host="zaccess"}'` → `1`.

### Retire when

`zcrypto-alloy-dark-zaccess` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-disk-high"></a>

## zaccess-disk-high — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-disk-high`): the bridgehead's root filesystem has been below 15% free for at least 30 minutes.

### What it means

The whole host is one small root filesystem (a 25 GB Linode) — Alloy, Caddy's ACME state and the WireGuard config all live under `mountpoint="/"`. Nothing on it is unbackfillable: the risk is running the box out of room for logs or a stuck ACME renewal, not data loss.

### What to do

1. On the bridgehead: `df -h /`.
2. `du -sh /var/log/* /var/lib/alloy* /var/lib/caddy-apt-mirror 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small. The Caddy apt mirror holds the vendor's whole release history, about 18 MB more a release, and is not pruned by hand: its signed index names each file in it (`zaccess-caddy-mirror`).
3. Caddy's ACME state is `/var/lib/caddy`: `sudo du -sh /var/lib/caddy`, and `sudo journalctl -u caddy --no-pager -n 200 | grep -i acme` for a renewal loop.
4. Reclaim space (`journalctl --vacuum-size=200M` is the usual first move) rather than resizing the disk — everything on this host is re-issuable, so growing the volume is a last resort, not a routine response.

### Retire when

`zaccess-disk-high` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-tunnel-stale"></a>

## zaccess-tunnel-stale — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-tunnel-stale`): the `zaccess0` WireGuard tunnel's handshake age has been over 300s on at least one end for 10+ minutes.

### What it means

Both ends of the tunnel run a probe timer that writes `zaccess_wireguard_handshake_age_seconds` from `wg show zaccess0 latest-handshakes` — the bridgehead's copy under `host="zaccess"`, the ops node's under `host="ops"`. The rule takes `max by (host)`, so each end is evaluated on its own and the notification names the end that reported stale; a genuine outage is visible from both sides, so expect **one instance per end**. A healthy tunnel handshakes every couple of minutes given `PersistentKeepalive = 25` on the ops-side client conf, so 300s is already several missed keepalives, not noise. One hole: an end whose `latest-handshakes` reads 0 — never handshaked since the interface came up — writes no gauge at all, and this rule is `noDataState: OK`, so a restart that fails to re-establish goes silent rather than staying red. That is why step 5 reads the value rather than watching the alert clear. A fully dark bridgehead or ops node is the Alloy-dark rules' job, not this one's.

### What to do

1. On the bridgehead and on the ops host: `wg show zaccess0` on **both** ends and compare `latest handshake`.
2. Check the `Endpoint` the ops-side client conf resolves to (`/etc/wireguard/zaccess0.conf` on `zcrypto-ops`) against the bridgehead's actual public address — a home-ISP IP change on the ops side is the routine cause of a stuck endpoint, not a config error.
3. Confirm UDP `51820` is still open on the Linode Cloud Firewall and the bridgehead's own nftables rules (`firewall_extra_udp_ports` in `group_vars/access_host/vars.yml`) — the two layers are maintained separately.
4. `systemctl restart wg-quick@zaccess0` on the ops node is the usual fix — it re-initiates the handshake against the configured endpoint without touching the bridgehead's own service; agentboard and the ops-side NAS relay restart with it through `Requires=`.
5. Confirm recovery by value: `wg show zaccess0` on both ends shows a handshake under a few minutes old, and `uv run python infra/scripts/grafana-query.py 'zaccess_wireguard_handshake_age_seconds'` returns a low value for **both** hosts — a missing host is the silent case above, not recovery.

### Retire when

`zaccess-tunnel-stale` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-cert-expiring"></a>

## zaccess-cert-expiring — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-cert-expiring`): a tracked zaccess endpoint's TLS certificate has been under 14 days from expiry for at least an hour. Each certificate is its own alert instance and the notification names it in the `target` label, so more than one can be in flight at once.

### What it means

The probe timers write `zaccess_tls_not_after_seconds{target=...}`: the bridgehead's own handshakes against each Caddy vhost on `127.0.0.1:443` and writes `target="tmux"`/`target="nas"`; the ops node's handshakes against the NAS admin port and writes `target="nas-dsm"`. `tmux` and `nas` are Caddy-managed — its ACME client renews them well before 14 days out, so either reaching this threshold means renewal has been failing silently. `nas-dsm` is the Synology DSM's own certificate, outside Caddy's control — a DSM-side concern.

### What to do

1. **Read the `target` from the notification** — it names the certificate that tripped. To see every target's expiry at once (no count command: the targets are those `zaccess-probe.sh.j2` and `zaccess-probe-ops.sh.j2` write), `uv run python infra/scripts/grafana-query.py 'zaccess_tls_not_after_seconds'` — one value per `target`; `date -d @<value>` turns it into a calendar date.
2. **`tmux` or `nas`**: on the bridgehead, `journalctl -u caddy --no-pager -n 200 | grep -i acme` for renewal failures — a failed HTTP-01 challenge, rate limiting or a stale ACME account; port 80 must stay reachable for the challenge — and `systemctl status caddy` to confirm the unit is up and serving both vhosts.
3. **`nas-dsm`**: log into the DSM admin console and check its own certificate manager — DSM's certificate lifecycle, not something either bridgehead role touches.
4. Confirm recovery: re-run the query in step 1 — the tripped target's value reads comfortably above `time() + 14*86400`.

### Retire when

`zaccess-cert-expiring` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.
