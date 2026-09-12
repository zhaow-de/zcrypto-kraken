# Bridgehead runbooks — the internet access host

You are here because **an alert fired in Slack** — find the section whose anchor matches the alert `uid` — or because you mean to revoke a client certificate or ship its Alloy config: the two procedures at the top, found by heading. Each section is written to be actioned without opening any other document.

Everything here is one Linode VPS, `zaccess`, reached as `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`; the other end of its WireGuard tunnel is `zcrypto-ops`, `ssh hp`. It runs no containers — Alloy, Caddy and WireGuard are apt packages under systemd — and holds no capture data: everything on it is re-issuable.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="zaccess-revoke-client-cert"></a>

## zaccess-revoke-client-cert — PROCEDURE: revoking a client cert

### What you are seeing

Nothing fired. A client certificate is to lose its access to the mTLS edge.

### What it means

The pins are PEMs in `infra/ansible/roles/access/files/pinned-leaves/`: `access_pinned_leaves` globs that directory and the Caddyfile template renders one `file /etc/caddy/pinned-leaves/<name>.pem` line per PEM inside its `verifier leaf` block, so deleting a PEM and converging drops the pin, and the `reload caddy` handler makes the running edge refuse that leaf at its next handshake. The role ships the directory with `ansible.builtin.copy`, which has no delete, so the host keeps a PEM the repo no longer has — inert, the Caddyfile no longer names it. A task failing after the Caddyfile is written strands that reload (`force_handlers` is off): the file is revoked and the running Caddy is not, which is why the confirm is a handshake, not a grep. The edge gates `:443` alone; SSH on `:10022` and the relay on `:20022` do not pass through it. Deleting the last PEM renders an empty `verifier leaf { }` block, and what Caddy does with that is recorded nowhere in this tree — the procedure assumes another pin remains.

### What to do

1. **If `<name>.pem` is the only PEM under `pinned-leaves/` (no count command: the leaves are the PEMs under `roles/access/files/pinned-leaves/`, and no entry counts them), issue its replacement first** — `infra/scripts/zaccess-client-cert.sh issue <new-name>` (it refuses a name that exists) — and converge that in before revoking. **The vault holds one bundle**: before you vault `<new-name>`'s, which the issue script's own next-step line tells you to do, extract `<name>`'s with `infra/scripts/zaccess-extract-client-cert.sh --name <name> --out-dir <dir>`, `<dir>` absolute because the script changes directory first — step 4 needs the two files it writes, so keep them past the script's "DELETE both local files", which means `<new-name>`'s, until step 4 is done; re-vaulting the replacement overwrites the slot.
2. **Delete the PEM from the repo and converge** — `infra/ansible/roles/access/files/pinned-leaves/<name>.pem`, then `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` from the workstation — the bridgehead converges like the other hosts, and the line lands in `docs/reference/deploy-log.jsonl`. This is the revocation; the steps below tidy up and prove it.
3. **Remove the host copy** — `sudo rm /etc/caddy/pinned-leaves/<name>.pem` on the bridgehead, for hygiene.
4. **Confirm by value — the revoked leaf is refused at the handshake.** `grep -c 'pinned-leaves/<name>.pem' /etc/caddy/Caddyfile` reading 0 proves the render only (no count command: the running Caddy's pins are process state the tree does not hold). Using the bundle step 1 extracted — `<name>`'s, not `<new-name>`'s, which is still pinned and would answer — `openssl pkcs12 -in <dir>/zaccess-<name>.p12 -passin file:<dir>/zaccess-<name>.p12.pass -nodes -out leaf.pem`, then `timeout 30 curl -sv --cert leaf.pem https://tmux.zaccess.zhaow.me/ -o /dev/null 2>&1 | grep -c '^< HTTP/'` reads 0 and the trace ends in a TLS alert. A `< HTTP/` line means the running Caddy still pins the leaf: `sudo systemctl reload caddy`, re-run. Delete `leaf.pem` and the two extracted files after.

### Retire when

`infra/ansible/roles/access/templates/Caddyfile.j2` no longer renders one `file` line per PEM from `access_pinned_leaves` — the glob is what makes deleting the PEM the revocation.

______________________________________________________________________

<a name="zaccess-alloy-converge"></a>

## zaccess-alloy-converge — PROCEDURE: shipping an Alloy config change to the bridgehead

### What you are seeing

Nothing fired. You are changing the bridgehead's `config.alloy` and looking for the digest operand and the bake gate the other Alloys make you satisfy.

### What it means

There is none: **the bridgehead's Alloy takes no digest operand and owes no bake.** It is a native deb whose version is FOLLOWED from apt — the `access` role installs it `state: present` with no version and clears any `dpkg` hold, because a hold makes `apt upgrade` skip it silently and a forced version turns an upstream bump into a failed task that drops the host from the play, and the pinned-leaves and Caddyfile tasks below it — the revocation path — with it. Its `config.alloy` is an ungated `copy`: every converge ships it, so a hand edit cannot outlive the next run and there is no drift assert. There is no `zaccess_alloy_digest` and no pins row, deliberately — do not add one. Caddy is on the same footing.

### What to do

1. Edit `infra/ansible/roles/access/files/config.alloy`, then `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` from the workstation.
2. Read the installed versions off the host: `dpkg-query -W alloy caddy`.

### Retire when

`infra/ansible/roles/access/tasks/main.yml` installs Alloy at a pinned version, or stops clearing the `dpkg` hold, or ships `config.alloy` behind a `when:` — any one of those makes the bridgehead owe an operand like every other host, and this section stops being the exception it exists to record.

______________________________________________________________________

<a name="zaccess-bridgehead-dark"></a>

## zaccess-bridgehead-dark — ALERT

### What you are seeing

A critical-severity Grafana alert (`zcrypto-alloy-dark-zaccess`): the internet bridgehead's `up` series has been absent from Grafana Cloud for more than 10 minutes.

### What it means

The bridgehead runs Alloy **natively** (an apt package, no docker) — the only host in the fleet where that is true — and nothing on the host reacts to that unit dying: no container to restart, one systemd unit. While it is dark, `zaccess-disk-high` — the only other rule scoped to `host="zaccess"` — reads no data, and `noDataState: OK` renders that identically to healthy. The two `zaccess_*` rules keep their ops-side half: `zaccess-tunnel-stale` still watches the tunnel from `host="ops"` and `zaccess-cert-expiring` still watches `target="nas-dsm"`. What goes unwatched are the `tmux` and `nas` edge certificates — only this host's probe writes those two targets.

### What to do

1. On the bridgehead: `systemctl status alloy` — is the unit running at all?
2. `journalctl -u alloy --no-pager -n 100` — a config parse failure is the usual cause here: a hand edit the last converge overwrote, or a credentials rotation that never reached `/etc/default/alloy`. The config copy is ungated — every converge ships it, and no drift assert catches a bad render before it lands (no count command: the copy task in `infra/ansible/roles/access/tasks/main.yml` carries no `when:`, unlike the digest-gated tasks above it).
3. `systemctl restart alloy` is the usual fix. If it will not stay up, `sudo grep -c '^GRAFANA_' /etc/default/alloy` — 6 means the credentials file is populated; fewer, or no file, means re-converge (`infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access`) to re-render it. Count that file, never print it — it carries the Grafana Cloud push passwords (no count command: the file is rendered on the bridgehead, and its contents are secrets nothing in the tree reads).
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
2. `du -sh /var/log/* /var/lib/alloy* 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small.
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

Two probe timers write `zaccess_tls_not_after_seconds{target=...}`: the bridgehead's own handshakes against each Caddy vhost on `127.0.0.1:443` and writes `target="tmux"`/`target="nas"`; the ops node's handshakes against the NAS admin port and writes `target="nas-dsm"`. `tmux` and `nas` are Caddy-managed — its ACME client renews them well before 14 days out, so either reaching this threshold means renewal has been failing silently. `nas-dsm` is the Synology DSM's own certificate, outside Caddy's control — a DSM-side concern.

### What to do

1. **Read the `target` from the notification** — it names the certificate that tripped. To see every target's expiry at once (no count command: the targets are those `zaccess-probe.sh.j2` and `zaccess-probe-ops.sh.j2` write), `uv run python infra/scripts/grafana-query.py 'zaccess_tls_not_after_seconds'` — one value per `target`; `date -d @<value>` turns it into a calendar date.
2. **`tmux` or `nas`**: on the bridgehead, `journalctl -u caddy --no-pager -n 200 | grep -i acme` for renewal failures — a failed HTTP-01 challenge, rate limiting or a stale ACME account; port 80 must stay reachable for the challenge — and `systemctl status caddy` to confirm the unit is up and serving both vhosts.
3. **`nas-dsm`**: log into the DSM admin console and check its own certificate manager — DSM's certificate lifecycle, not something either bridgehead role touches.
4. Confirm recovery: re-run the query in step 1 — the tripped target's value reads comfortably above `time() + 14*86400`.

### Retire when

`zaccess-cert-expiring` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.
