# Bridgehead runbooks — the internet access host

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

<a name="zaccess-converge"></a>

## zaccess-converge — PROCEDURE: converging the bridgehead needs a single-identity SSH agent

### What you are seeing

Nothing fired. You are about to converge the bridgehead — `site.yml --limit zaccess --tags access` — or a converge of it died on `Too many authentication failures`.

### What it means

Every converge of this host needs an agent holding **only its own key**. `ssh_hardening` leaves `ssh_max_auth_retries` at its `devsec.hardening` default, so sshd here offers `MaxAuthTries 2`, and `infra/ansible/scripts/run.sh` loads all five vaulted fleet deploy keys into one agent with `files/deploy_zaccess_ed25519` **last** — both tries go to other hosts' keys before the right one is offered, and the run dies on `Too many authentication failures`. The other four hosts sit earlier in that load order, so only `zaccess` trips it.

### What to do

So converge it not through `run.sh` but from `infra/ansible/`, where `ansible.cfg` supplies the vault password independently: `eval "$(ssh-agent -s)"; uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/deploy_zaccess_ed25519 | ssh-add -; ANSIBLE_SSH_EXTRA_ARGS="-o IdentitiesOnly=yes -o IdentityFile=$PWD/files/deploy_zaccess_ed25519.pub" uv run ansible-playbook site.yml --limit zaccess --tags access`. That agent has no trap of its own the way `run.sh`'s does — `ssh-agent -k` when the play is done.

### Retire when

`infra/ansible/roles/hardening/` sets `ssh_max_auth_retries` explicitly above the number of keys `infra/ansible/scripts/run.sh` loads, or `run.sh` stops loading every fleet key into one agent — either one ends the collision this procedure exists for.

<a name="zaccess-revoke-client-cert"></a>

## zaccess-revoke-client-cert — PROCEDURE: revoking a client cert

### What you are seeing

Nothing fired. A client certificate is to lose its access to the mTLS edge.

### What it means

Delete its PEM from `infra/ansible/roles/access/files/pinned-leaves/` and converge. `access_pinned_leaves` globs that directory and the Caddyfile template renders one `file /etc/caddy/pinned-leaves/<name>.pem` line per PEM inside its `verifier leaf` block, so the re-rendered Caddyfile drops the pin and the leaf is refused at the next handshake.

### What to do

The role ships that directory with `ansible.builtin.copy`, which has no `--delete`, so **also `sudo rm /etc/caddy/pinned-leaves/<name>.pem` on the bridgehead** for hygiene; the file is inert either way, because the Caddyfile no longer names it. Confirm by value: `grep -c 'pinned-leaves/<name>.pem' /etc/caddy/Caddyfile` reads 0.

### Retire when

`infra/ansible/roles/access/templates/Caddyfile.j2` no longer renders one `file` line per PEM from `access_pinned_leaves` — the glob is what makes deleting the PEM the revocation.

______________________________________________________________________

<a name="zaccess-bridgehead-dark"></a>

## zaccess-bridgehead-dark — ALERT

### What you are seeing

A critical-severity Grafana alert (`zcrypto-alloy-dark-zaccess`): the internet bridgehead's `up` series has been absent from Grafana Cloud for more than 10 minutes.

### What it means

The bridgehead runs Alloy **natively** (an apt package, no docker) — the only host in the fleet where that's true. When it stops shipping, every other rule scoped to `host="zaccess"` goes blind at the same time: the WireGuard tunnel handshake-age gauge, the edge TLS cert-expiry gauge, and this host's own disk-high content rule all read no data, which renders identically to healthy. Nothing on this host reacts to its own Alloy dying — there is no container to restart, no compose stack to recreate, just the one systemd unit.

### What to do

1. `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`.
2. `systemctl status alloy` — is the unit running at all?
3. `journalctl -u alloy --no-pager -n 100` — a config parse failure (a hand edit that didn't survive the next converge, or a credentials rotation that didn't reach `/etc/default/alloy`) is the usual cause on this host, since the config copy here is deliberately ungated (every converge ships it, so there is no separate drift-assert task to catch a bad render before it lands).
4. `systemctl restart alloy` is the usual fix. If it will not stay up, check `/etc/default/alloy` for the six `GRAFANA_*` values and re-converge (`--limit zaccess --tags access`) to re-render them — that converge needs a single-identity SSH agent — [`zaccess-converge`](#zaccess-converge).
5. Confirm recovery from the workstation: `uv run python infra/scripts/grafana-query.py 'up{host="zaccess"}'` → `1`.

**This Alloy takes no digest operand and owes no bake** — unlike the capture and ops Alloys, which refuse an ordinary converge after a config edit. It is a native deb whose version is FOLLOWED from apt: the `access` role installs it `state: present` with no version and clears any `dpkg` hold, because a hold makes `apt upgrade` skip it silently and a forced version turns an upstream bump into a failed task that drops the host from the play. Its `config.alloy` is an ungated `copy`, so every converge ships it and a hand edit cannot outlive the next run. There is no `zaccess_alloy_digest` and no pins row — that is deliberate, not an oversight, so do not add one; read the installed version off the host with `dpkg-query -W alloy`. A keep-regex or `config.alloy` change under `infra/ansible/roles/access/files/` converges with a plain `site.yml --limit zaccess --tags access`, whose SSH-agent constraint is [`zaccess-converge`](#zaccess-converge).

### Retire when

`zcrypto-alloy-dark-zaccess` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-disk-high"></a>

## zaccess-disk-high — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-disk-high`): the bridgehead's root filesystem has been below 15% free for at least 30 minutes.

### What it means

The whole host is one small root filesystem (a 25 GB Linode) — Alloy, Caddy's ACME state, and the WireGuard config all live under `mountpoint="/"`, so there is no separate spool to watch the way the capture hosts' unbackfillable L2 spool needs one. This host holds no capture data and nothing on it is unbackfillable — the risk here is running the box out of room for logs or a stuck ACME renewal artifact, not data loss.

### What to do

1. `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`; `df -h /`.
2. `du -sh /var/log/* /var/lib/alloy* 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small.
3. Check for a stuck ACME renewal loop — Caddy re-requesting a cert repeatedly leaves debug artifacts: `sudo du -sh /var/lib/caddy` and `sudo journalctl -u caddy --no-pager -n 200 | grep -i acme`.
4. Reclaim space (`journalctl --vacuum-size=200M` is the usual first move) rather than resizing the disk — everything on this host is re-issuable, so growing the volume is a last resort, not a routine response.

### Retire when

`zaccess-disk-high` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-tunnel-stale"></a>

## zaccess-tunnel-stale — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-tunnel-stale`): the `zaccess0` WireGuard tunnel's handshake age has been over 300s on at least one end for 10+ minutes.

### What it means

Both ends of the tunnel run a probe timer that writes `zaccess_wireguard_handshake_age_seconds` from `wg show zaccess0 latest-handshakes` — the bridgehead's copy under `host="zaccess"`, the ops node's under `host="ops"`. The rule takes `max by (host)`, so each end is evaluated on its own and the notification names the end that reported stale — a genuine outage is visible from both sides and therefore raises **one instance per end**, so expect two. A healthy tunnel handshakes every couple of minutes given `PersistentKeepalive = 25` on the ops-side client conf, so 300s is already several missed keepalives, not noise. This does not mean the whole bridgehead is unreachable: that is `zaccess-bridgehead-dark`'s job (this host's Alloy itself going dark) and `zcrypto-alloy-dark-ops`'s job (the ops node's).

### What to do

1. `wg show zaccess0` on **both** ends — `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` for the bridgehead, the usual ops access for `zcrypto-ops` — and compare `latest handshake` on each.
2. Check the `Endpoint` the ops-side client conf resolves to (`/etc/wireguard/zaccess0.conf` on `zcrypto-ops`) against the bridgehead's actual public address — a home-ISP IP change on the ops side is the routine cause of a stuck endpoint, not a config error.
3. Confirm UDP `51820` is still open on the Linode Cloud Firewall and the bridgehead's own nftables rules (`firewall_extra_udp_ports` in `group_vars/access_host/vars.yml`) — a firewall change elsewhere in the fleet is the other routine cause.
4. `systemctl restart wg-quick@zaccess0` on the ops node is the usual fix — it re-initiates the handshake against the configured endpoint without touching the bridgehead's own service.
5. Confirm recovery: `wg show zaccess0` on both ends shows a handshake under a few minutes old, and `uv run python infra/scripts/grafana-query.py 'zaccess_wireguard_handshake_age_seconds'` returns a low value for both hosts.

### Retire when

`zaccess-tunnel-stale` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zaccess-cert-expiring"></a>

## zaccess-cert-expiring — ALERT

### What you are seeing

A warning-severity Grafana alert (`zaccess-cert-expiring`): a tracked zaccess endpoint's TLS certificate has been under 14 days from expiry for at least an hour. Each certificate is its own alert instance and the notification names it in the `target` label, so more than one can be in flight at once.

### What it means

Two probe timers write `zaccess_tls_not_after_seconds{target=...}`: the bridgehead's own probe handshakes against each Caddy vhost on `127.0.0.1:443` and writes `target="tmux"`/`target="nas"`; the ops node's probe handshakes against the NAS admin port and writes `target="nas-dsm"`. The rule takes `min by (host, target)`, so each tracked certificate is evaluated on its own and the page names the one that tripped. `tmux` and `nas` are Caddy-managed: Caddy's ACME client renews them automatically, well before 14 days out under normal operation, so either arriving at this threshold usually means renewal has been failing silently rather than an unavoidable expiry. `nas-dsm` is the Synology DSM's own certificate, outside Caddy's control — its renewal (or lack of it) is a DSM-side concern.

### What to do

1. **Read the `target` from the notification** — it names the certificate that tripped. To see every target's expiry at once, `uv run python infra/scripts/grafana-query.py 'zaccess_tls_not_after_seconds'` — one value per `target` label; `date -d @<value>` turns it into a calendar date.
2. **`tmux` or `nas`**: `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me`; `journalctl -u caddy --no-pager -n 200 | grep -i acme` for renewal failures (a failed HTTP-01 challenge, rate limiting, or a stale ACME account are the usual causes — port 80 must stay reachable for the challenge). `systemctl status caddy` — confirm the unit is up and serving both vhosts.
3. **`nas-dsm`**: log into the DSM admin console directly and check its own certificate manager — this is DSM's certificate lifecycle, not something either bridgehead role touches.
4. Confirm recovery: re-run the query in step 1 — the tripped target's value should read comfortably above `time() + 14*86400`.

### Retire when

`zaccess-cert-expiring` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.
