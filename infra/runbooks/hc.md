# Dead-man runbooks — the dead-man node

You are here because **an alert fired in the shadow channel** — find the section whose anchor matches the alert `uid` — or because you mean to replace one of the node's secrets, rotate the service's keys, take or restore a backup, or re-create the project after its database was lost, or because the node or the service on it is down and you opened `hc-dark` deliberately, or because the daily pass's reminders name the monthly patch pass: the procedures and the reminder's section at the top, found by heading. Each section is written to be actioned without opening any other document.

Everything here is one Linode VPS, `zcrypto-hc` (the workstation's ssh alias `hc`; `Dead-man` in Slack and on the Logs board), reached by people and pingers as `https://zcrypto-hc.zhaow.me`. It runs the dead-man service, the owner's healthchecks clone `ghcr.io/zhaow-de/healthchecks`, pinned by version tag, as one container, `zcrypto-hc`, under the systemd unit `zcrypto-hc.service`, which runs `docker compose up` in `/opt/zcrypto-hc`. The service's state is one SQLite database, `/data/hc.sqlite` in the named volume `hc-data`, and the container listens on `127.0.0.1:8000`. Caddy is the one public listener, on 443, and passes everything to the container. Alloy, an apt package under systemd, ships the node's metrics, its units' journals and the service's records to the observability node alone, under `host="zcrypto-hc"`, and to Grafana Cloud nothing. Three timers run on the node: `zcrypto-hc-selfcheck` every five minutes, which reads the service's status endpoint and pings the service's own check, `zcrypto-hc`, while it answers `OK`; `zcrypto-sqlite-backup` nightly at 02:47 UTC; and `zcrypto-reboot-check`.

The service holds every dead-man check of the fleet, the project's three keys and its Slack integration in its database, and pages the main channel through that integration. The node holds no key to another host. Its configuration is the `hc` role, and its state is the database, backed up nightly. Its own rules, the `zcrypto-hc` group, are evaluated on the observability node and page the shadow channel; the service's death pages the main channel through Grafana Cloud's `zcrypto-hcio-watchdog` (`observability.md#zcrypto-hcio-watchdog`).

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="hc-dark"></a>

## hc-dark — PROCEDURE: while the node or the service is down or being rebuilt

### What you are seeing

The node is unreachable, powered off or being rebuilt, or the service on it does not answer: `curl -fsS https://zcrypto-hc.zhaow.me/api/v3/status/` does not print `OK`, and `infra/scripts/hc-provision.py status` and the daily pass's direct read of the service fail naming it. What tells you is Grafana Cloud's `zcrypto-hcio-watchdog` in the main channel at value `999`: the ops node's 60 s scrape of the service fails, then the rule's `for: 5m`, then the group interval. When the service answers its status read and its database refuses writes, the scrape still answers, and the service's own check `zcrypto-hc`, unpinged, goes down at its `timeout` 600 s + `grace` 600 s, 20 minutes from its last ping: the watchdog then pages its count of down checks, 1 or more. On the observability node, `zcrypto-alloy-dark-hc` pages the shadow channel ten minutes into a node that is down, and `zcrypto-hc-service-down` fifteen minutes into a service that fails its status read.

### What it means

While the service is down, the fleet's dead-man domain is dark: no check is evaluated, no check's page is sent, and the fleet's pings to the service are refused and recorded nowhere. Grafana Cloud's rules page the main channel throughout, and the watchdog's `999` is the one page of the dark domain. When the service returns, each check whose `timeout` + `grace` the outage outlasted reads `DOWN` until its next ping and pages `DOWN`, then `UP`, through the service's Slack integration: those pages are the outage's, not their hosts'. A rebuild starts the service on an empty database until `hc-restore` puts the last backup back, and on a database lost with its backups, `hc-lost-database`.

The two figures the drills measured: a thirty-minute power-off read `[[ROLLOUT: R15's X2 reading — the page and the self-check's first -> pinged after boot]]`, and a rebuild from nothing took `[[ROLLOUT: R15's X3 reading — the time from the rebuild to the first stored ping]]` from the rebuild to the first stored ping (`drills-telemetry.md`'s dead-man node drills).

### What to do

1. **Confirm it is the service and not your route**: `curl -fsS -m 20 https://zcrypto-hc.zhaow.me/api/v3/status/` from the workstation and from ops (`ssh hp`), then the Linode's state on its page in the Cloud Manager, running or offline, and its LISH console, which answers while the host does.

2. **Read the fleet without the dead-man domain**: `uv run python infra/scripts/ops-daily.py report --since 24h` reads Grafana Cloud as on a quiet day, and names `the dead-man service could not be read directly` under its unreadable sources. The node's own telemetry, while its Alloy ships: `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-hc"})'` reads 2.

3. **A node that answers ssh**: `ssh hc 'sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -3'`. `web=FAIL` is the service failing its status read: `zcrypto-hc-service-down` below, from its step 2. `web=ok` with `-> ping failed: HTTPError` is the ping refused: with `zcrypto-hc-error-logs` paging `Internal Server Error` records on `/ping/` paths, the database refusing the ping's write; with that rule quiet, a ping key the service does not hold, which `hc-lost-database` step 3 sets back to the vault's. `web=ok … -> pinged` with the watchdog still at `999` is the ops node's scrape, `observability.md#zcrypto-hcio-watchdog` step 4.

4. **A node that does not answer**: in the Cloud Manager, a Linode reading offline is powered on from its page; one reading running and answering nothing on ssh or in LISH is rebooted from its page.

5. **A node whose disk is gone** is rebuilt from the repository, as the observability node is: `drills-telemetry.md#drill-w3`'s *Induce* steps 1 and 2 over the Linode and the firewall `zcrypto-hc` and the known host `[zcrypto-hc.zhaow.me]:10022`, then from the repo root:

   ```
   (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-hc -e ansible_user=root -e ansible_port=22)
   ssh hc 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags base,hardening,firewall,fail2ban,chrony,docker -e daemon_json_ack=true
   ssh hc 'sudo docker pull ghcr.io/zhaow-de/healthchecks:<tag>'
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc -e hc_image_tag=<tag>
   ```

   `<tag>` is the pinned tag, the `hc` row of `docs/reference/fleet-pins.md`; the first converge acknowledges the Docker daemon's new `daemon.json`, absent on a fresh node. Then remove the firewall's TCP `22` rule, and put the database back by `hc-restore` from the newest backup file that survives the disk, the NAS's copy among them, or by `hc-lost-database` when none does; the NAS's pull of the backups refuses the rebuilt node's new host key until `hc-backup` step 6 replaces its line.

6. **Change nothing on the fleet for it.** The pingers keep pinging, and their pings land again once the service answers; no host is converged for the outage.

7. **On return**: `ssh hc systemctl is-active zcrypto-hc caddy alloy` reads `active` three times; `ssh hc "sudo docker inspect zcrypto-hc --format '{{.State.Health.Status}}'"` reads `healthy`; the self-check's next line reads `-> pinged`; `uv run python infra/scripts/hc-provision.py status` reads each check's `last_ping` moving past the outage as its pinger's next ping lands, and `uv run python infra/scripts/grafana-query.py 'max(hc_checks_down_total)'` reads 0 on Grafana Cloud once each check that paged `DOWN` has pinged. The day's journal entry carries the minutes, in which no check was evaluated.

### Retire when

`infra/ansible/roles/hc/tasks/main.yml` no longer includes `node_common`'s `selfcheck` task file, at which point the service's own check `zcrypto-hc` is pinged by nothing and this page's reads of the service's health have no line to read.

______________________________________________________________________

<a name="hc-secrets"></a>

## hc-secrets — PROCEDURE: generating or replacing one of the node's vaulted secrets or plain values

### What you are seeing

Nothing fired, or one of the `hc` role's first two tasks refused a converge, naming a key in `infra/ansible/host_vars/zcrypto-hc/vault.yml` or `infra/ansible/host_vars/zcrypto-hc/vars.yml` as missing or misshapen.

### What it means

The role's first task reads four values from `host_vars/zcrypto-hc/vault.yml` and refuses each off its shape: `hc_secret_key`, the service's Django secret key, 64 hex characters; `hc_admin_password`, the superuser's password, 48 hex characters; and `hc_email_host_user` and `hc_email_host_password`, the SMTP credential AWS SES issues, which the service sends its sign-in and sudo-mode mail through. The two generated values are hex, since Docker Compose interpolates a `$` inside an env file's value, and are generated and encrypted in one pipe, neither typed nor printed; the SES pair is pasted once into `infra/scripts/vault-append-secret.sh`'s prompt.

The role's second task refuses four plain values off their shapes, each a line of `host_vars/zcrypto-hc/vars.yml`: `hc_email_host`, the SES region's SMTP endpoint, `email-smtp.<region>.amazonaws.com`; `hc_email_from`, the sender SES has verified; `hc_admin_email`, the owner's mailbox, where the sudo-mode codes land; and `hc_selfcheck_healthcheck_url`, `"{{ hc_ping_base }}/zcrypto-hc"`, rendered from the project's ping key, whose rotation is `hc-keys`.

The secret key signs every API key and every link the service mails, and it is the vault's, so a database restored on a rebuilt node takes the keys it holds. Replacing it voids the project's two API keys and every signed-in session: `hc-keys` re-mints the keys after it. The role keeps the superuser's password equal to the vault's at each converge of the node, so a replaced password is applied by the converge.

### What to do

1. **A generated value**, from `infra/ansible`: `openssl rand -hex 32 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name hc_secret_key` for the secret key, or `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name hc_admin_password` for the password, prints the entry; replace the key's block in `host_vars/zcrypto-hc/vault.yml` with it. A replaced secret key is followed by `hc-keys` steps 6 and 7 once step 4 below has converged it.

2. **The SES pair**: in AWS SES, create an SMTP credential, then from `infra/ansible`, each value pasted at its prompt:

   ```bash
   ../scripts/vault-append-secret.sh host_vars/zcrypto-hc/vault.yml hc_email_host_user '[A-Z0-9]{16,}' --replace
   ../scripts/vault-append-secret.sh host_vars/zcrypto-hc/vault.yml hc_email_host_password '[A-Za-z0-9+/=]{40,}' --replace
   ```

   Each prints `<key>: replaced`. A credential of another shape is refused there: the two shapes are re-trued in the role's first task, `infra/ansible/roles/hc/tasks/main.yml`, and here, in one commit, before it is vaulted. The old credential is deleted in SES once step 4's converge is followed by a sudo-mode code that arrives.

3. **A plain value** is its line in `host_vars/zcrypto-hc/vars.yml`, edited on a branch: the SES endpoint of the credential's region, the sender as SES verified it, the owner's mailbox. `hc_selfcheck_healthcheck_url` stays `"{{ hc_ping_base }}/zcrypto-hc"`.

4. **Converge the node**: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>`, the tag the `hc` row of `docs/reference/fleet-pins.md` records. A changed env file restarts the service, which answers nothing for the restart's seconds. A code that does not arrive by email under sudo mode, in the service's UI, is the SES values: `ssh hc 'sudo docker logs zcrypto-hc --since 10m 2>&1 | grep -i smtp'` names the SMTP error.

### Retire when

`infra/ansible/roles/hc/tasks/main.yml` no longer opens with the task `refuse a missing or misshapen secret, naming the key and never the value`.

______________________________________________________________________

<a name="hc-keys"></a>

## hc-keys — PROCEDURE: rotating the dead-man service's keys

### What you are seeing

Nothing fired. A key of the service's project is to be replaced: it may have been exposed, the go-live rotation is due, the service's secret key was replaced (`hc-secrets`), or a database restored from an older backup holds an older key (`hc-restore`).

### What it means

The project holds three keys, each minted in the service's UI, on the project's Settings page, under sudo mode, whose code the service mails to the superuser's mailbox; no script generates one and no API sets one. Each enters the vault through `infra/scripts/vault-append-secret.sh`, pasted once at its prompt.

**The ping key**, `hc_ping_key` in `infra/ansible/group_vars/observed/vault.yml`. Each ping URL of the fleet is `https://zcrypto-hc.zhaow.me/ping/<the key>/<the check's name>`, rendered on its host from this key, so each pinging host takes a new key at its own converge. The service replaces a ping key by Revoke, then Create, and a ping under a revoked key answers `404` and records nothing; a paused check resumes at its next ping, since each check is provisioned with `manual_resume` false. The rotation is one attended sitting, outside a rung box (`engine-procedures.md#engine-rung-2-box`), since its last converge restarts the engine.

**The read-only key**, `hc_readonly_api_key` in the same file. The ops node's Alloy sends it as the bearer token of its scrape of the service, which Grafana Cloud's `zcrypto-hcio-watchdog` reads, and the daily pass and `infra/scripts/hc-provision.py` read it from the vault by file path. Between its Revoke and ops' Alloy recreated on the new key, the scrape is refused, and the watchdog pages `999` once that has lasted its five minutes.

**The read-write key**, `hc_readwrite_api_key` in `infra/ansible/group_vars/all/vault.yml`, read on the workstation by `hc-provision.py`'s writes. No host holds it.

### What to do

1. **The ping key's sitting**: announce it in the main channel, read the Kraken feed whole at planning (`.claude/rules/fleet-deploys.md`), and read `uv run python infra/scripts/hc-provision.py status`, each of the twelve checks `up`.

2. **Revoke the ping key**, on the project's Settings page, and note the time: `date -u +%FT%TZ`. From here each ping answers `404`.

3. **Pause the twelve checks** in the service's UI, the last pause within nine minutes of the Revoke: the shortest `timeout` + `grace` among the checks is 1200 s, and `zcrypto-liquidations`' poller leaves a little over 600 s between two pings when one of its polls fails, so a check still unpaused past nine minutes can go down and page. No ping resumes a paused check while the key is revoked.

4. **Create the new ping key** on the same page and vault it at once, from the repo root: `(cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_ping_key '[A-Za-z0-9_-]{16,}' --replace)` prints `hc_ping_key: replaced`. A key of another shape is refused there: the shape the roles' preflights hold each ping URL to is re-trued first, in one commit.

5. **Converge the node and each pinging host**, in this order, the venue-facing converges under `.claude/rules/fleet-deploys.md` with the Kraken feed read whole immediately before each, and each running digest read off its container's `{{.Config.Image}}`, not its `.Image`, and matched against `docs/reference/fleet-pins.md`:

   ```
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_alloy_digest=sha256:<running alloy> -e ops_image_digest=sha256:<running ops>
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon
   infra/ansible/scripts/converge.sh site.yml --limit nas --tags nas -e nas_apply_compose=true
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running capture> -e capture_alloy_digest=sha256:<running alloy>
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture -e converge_primary=true -e capture_image_digest=sha256:<running capture> -e capture_alloy_digest=sha256:<running alloy>
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<running engine> -e cache_proxy_image_digest=sha256:<running cache proxy>
   ```

   The node's self-check pings at its next run. After the ops converge, `ssh hp 'cd /etc/zcrypto-ops && sudo docker compose up -d'` recreates the liquidations poller on its new URL, a gap of seconds in its stream; the five ops timers read their rendered scripts at their next ticks. The NAS's apply recreates `archive-pull` and replays the gate export, sized beforehand by `docs/reference/fleet-pins.md`'s standing constraint. `zcrypto` follows `zcrypto-red` by an hour, each converge restarting that host's capture daemon. The engine's converge runs inside the inter-cycle gap and under `engine-procedures.md#engine-restart-margin-position`, and restarts the engine on its new `engine.env`.

6. **The scrape's key, `hc_readonly_api_key`**: announce the possible `999` in the main channel; on the project's Settings page revoke that key and create it again; vault it, `(cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_readonly_api_key 'hcr_[A-Za-z0-9]{28}' --replace)`; then, with the Kraken feed read whole immediately before, ops' Alloy converge with the fleet's digest, `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags alloy -e ops_alloy_digest=<the fleet's>` — `alloy_image_digest` in `infra/ansible/group_vars/observed/alloy.yml`, or while ops is held the digest `infra/ansible/host_vars/zcrypto-ops/alloy.yml` names — whose role re-renders `alloy-secrets.env` and recreates Alloy on it, proven by `ssh hp "sudo docker inspect grafana-alloy --format '{{.State.StartedAt}}'"` moving.

7. **The read-write key**: revoke it and create it again on the same page, then `(cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/all/vault.yml hc_readwrite_api_key 'hcw_[A-Za-z0-9]{28}' --replace)`. No converge is owed.

8. **Close the rotation by value.** No check is unpaused by hand: each resumes at its first ping under the new key, and a check whose host has not yet converged stays paused and unwatched until it does, the two daily replay checks until their next ticks, 03:41 and 05:23 UTC. `uv run python infra/scripts/hc-provision.py status` reads each of the twelve with a `last_ping` later than step 2's time, which also proves the read-write key; `uv run python infra/scripts/grafana-query.py 'count(hc_check_up)'` reads 12 on Grafana Cloud, which proves the scrape's key; `uv run python infra/scripts/ops-daily.py report --since 24h` names no `the dead-man service could not be read directly`. No check is deleted and no history is lost.

### Retire when

None of `hc_ping_key`, `hc_readonly_api_key` and `hc_readwrite_api_key` is a key of a `vault.yml` under `infra/ansible/`.

______________________________________________________________________

<a name="hc-backup"></a>

## hc-backup — PROCEDURE: the nightly backup, and one taken by hand

### What you are seeing

Nothing fired. A backup is wanted before a step that rewrites the database, a release with a migration or a restore, or the node's backups or the NAS's copy of them are to be read; or `zcrypto-hc-backup-stale` sent you here, or `zcrypto-nas-archive-pull-errors` paged an `hc backup pull failed` line.

### What it means

The timer `zcrypto-sqlite-backup` runs nightly at 02:47 UTC. It runs `VACUUM INTO` inside the service's container, through Compose's `exec`, into `/data/backups/hc-<UTC date and time>.sqlite` inside the volume, so the container's own uid writes the file and nothing is created by root beside the live database; it copies that file out of the container, through Compose's `cp`, into `/var/backups/zcrypto-hc.incoming/` on the node and renames it, whole, into `/var/backups/zcrypto-hc/`; it prunes all three directories past 14 days, by the date in each file's name; and it writes the gauge `zcrypto_sqlite_backup_last_success_timestamp_seconds{db="hc"}` into the node's textfile directory, which the node's Alloy ships. A run writes the gauge only when each of those steps succeeded, so the gauge's age is a failed run's signal, `zcrypto-hc-backup-stale` below. A backup file is a closed, consistent database: Linode Backups carry the node's disk, the backup files among them, while their snapshot of the live database can catch it mid-write, so a restore reads a backup file, by `hc-restore`. One run at a time: a run started while another holds the lock exits naming it. The files carry the project's keys, its ping key and the Slack integration's webhook.

The NAS keeps a copy off the node. Its `zcrypto-archive-pull` loop pulls `/var/backups/zcrypto-hc/` each hour into `/volume1/docker/zcrypto-archive/hc-backups/`, logging in as the node's `zcrypto-data` account with the key `sync_hc_backup`, which the node admits as `rrsync -ro` pinned at that directory: the NAS reads the backups and nothing else, and the node holds no key to the NAS. Each run holds the directory at `0750` and every file in it at `0640`, root's with the group `zcrypto-data`, so that account reads them. The pull deletes nothing on the NAS, which keeps every file it has pulled, those the node has pruned and those a rebuilt node never had among them. A failed pull logs `hc backup pull failed (source=… dest=…), continuing` at `ERROR` in the NAS's pull log and pages `zcrypto-nas-archive-pull-errors` (`nas.md#zcrypto-nas-archive-pull-errors`).

### What to do

1. **Take one now**, on the node: `sudo systemctl start zcrypto-sqlite-backup.service`, which returns when the run ends. `sudo journalctl -u zcrypto-sqlite-backup --no-pager -n 5` carries `backed up /data/hc.sqlite to /data/backups/hc-<UTC date and time>.sqlite and copied it into /var/backups/zcrypto-hc`.
2. **Read what is kept**: `sudo ls -l /var/backups/zcrypto-hc/`, one file per run of the last 14 days, each named for its UTC date and time, and `sudo cat /var/lib/zcrypto-node-textfile/sqlite-backup.prom`, the gauge with the last completed run's time.
3. **A run that failed** logs an `ERROR` line naming its step and leaves the gauge as it was: `zcrypto-hc-backup-stale` step 1 reads which.
4. **Confirm by value**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'time() - max(zcrypto_sqlite_backup_last_success_timestamp_seconds{host="zcrypto-hc"})'` reads the seconds since step 1's run, within a minute or two of it.
5. **Read the NAS's copy**, on the NAS, once a pull cycle has passed since the run: `sudo ls -l /volume1/docker/zcrypto-archive/hc-backups/` names each file step 2 names, and `sudo /usr/local/bin/docker logs --since 3h zcrypto-archive-pull 2>&1 | grep -B5 'hc backup pull failed'` prints nothing. A failure's cause is in the `rsync` and `ssh` lines before it: `Host key verification failed.` after a rebuild is step 6's; `rrsync error: Restricted directory does not exist!` on a rebuilt node is the directory its first backup run creates, and `unable to chdir to restricted dir: [Errno 13] Permission denied: '/var/backups/zcrypto-hc'` is that directory left at `0700`, which a run holds at `0750` under the group `zcrypto-data`: both are step 1's; a refused login is the node's `zcrypto-data` account or its key, which the node's converge, `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>`, puts back.
6. **After the node is rebuilt**, its host key is new, and the NAS's pull refuses it until the line for `[zcrypto-hc.zhaow.me]:10022` in the NAS's `/volume1/docker/zcrypto-archive/keys/known_hosts` is replaced: on the workstation, `ssh-keyscan -t ed25519 -p 10022 zcrypto-hc.zhaow.me`, its `ssh-keygen -lf` fingerprint read equal to the one the node's LISH console prints for `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`; then on the NAS that line in the file replaced by the new one, the file staying root's at `0644` (`infra/nas/README.md`, bootstrap step 4). Step 5 reads the next pull.

### Retire when

`infra/ansible/roles/hc/tasks/main.yml` no longer includes `node_common`'s `sqlite-backup` task file.

______________________________________________________________________

<a name="hc-restore"></a>

## hc-restore — PROCEDURE: restoring the service's database from a backup file

### What you are seeing

Nothing fired. The service's database is to be put back from a backup file: it was lost or damaged, the node was rebuilt (`hc-dark`), or a release's migration is to be undone (`hc-patch-pass`).

### What it means

A backup file, `hc-<UTC date and time>.sqlite` from `hc-backup`, is read before it is swapped in. The read runs the service's image once over a copy of the file, with the node's env file, no network and Django's shell in place of the service, so no notifier runs against a database whose checks all look overdue and nothing the run does can leave the node; Django's test client then lists the checks with the read-only key, piped from the workstation, its request naming `zcrypto-hc.zhaow.me` as its host, since the service answers any other host `400`. That one read proves the file, the key under the vaulted secret key, and the listing. The swap stops the service, moves the live database aside in the volume with its `-wal`, `-shm` and `-journal` files, which belong to the database being replaced and are deleted with it once the restore reads green, copies the file in as the container's own uid 100, and starts the service, whose start runs the release's migrations. A backup run follows, so the gauge `zcrypto-hc-backup-stale` reads exists from the restore on: on a rebuilt node that rule pages its no-data state from five minutes after the node's Alloy first ships until that run.

A restored database brings back the superuser, the project, its three keys, its ping key, the Slack integration and each check with its history up to the backup. The secret key that signs the keys is the vault's, so the keys the backup holds work as they did. What was written after the backup is gone: the pings and flips since, and a key rotated since — a ping key is set back to the vault's in `/admin/` (`hc-lost-database` step 3), and an API key is re-minted by `hc-keys`. While the service is stopped no check is evaluated, and on its return each check whose `timeout` + `grace` the stop outlasted pages `DOWN`, then `UP`.

### What to do

1. **Stage the file on the node**, two copies in a directory the container's uid owns, one for the read and one for the swap, `f` set to the file to restore — a file under `/var/backups/zcrypto-hc/`, or, with the node and its Linode Backups gone, the newest file the NAS's copy holds (`hc-backup`), listed on the NAS by `sudo ls -l /volume1/docker/zcrypto-archive/hc-backups/` and piped onto the node from the workstation:

   ```bash
   ssh nas 'sudo cat /volume1/docker/zcrypto-archive/hc-backups/hc-<UTC date and time>.sqlite' | ssh hc 'umask 077 && cat >/tmp/hc-<UTC date and time>.sqlite'
   ```

   Then, on the node:

   ```bash
   f=/var/backups/zcrypto-hc/hc-<UTC date and time>.sqlite  # or f=/tmp/hc-<UTC date and time>.sqlite, a file piped in from the NAS's copy
   sudo install -d -o 100 -m 0700 /tmp/hc-restore /tmp/hc-restore/read && sudo install -o 100 -m 0600 "$f" /tmp/hc-restore/hc.sqlite && sudo install -o 100 -m 0600 "$f" /tmp/hc-restore/read/hc.sqlite
   ```

2. **Read it**, from the workstation at the repository root, with `<tag>` the release the backup was written under: the pinned one, the `hc` row of `docs/reference/fleet-pins.md`, or the previous one when a release's migration is being undone:

   ```bash
   uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("hc_readonly_api_key", "group_vars/observed/vault.yml"))' \
     | ssh hc 'sudo docker run --rm -i --network none --env-file /opt/zcrypto-hc/hc.env -v /tmp/hc-restore/read:/data ghcr.io/zhaow-de/healthchecks:<tag> ./manage.py shell --no-imports -c "import sys; from django.test import Client; r = Client().get(\"/api/v3/checks/\", HTTP_X_API_KEY=sys.stdin.read().strip(), HTTP_HOST=\"zcrypto-hc.zhaow.me\"); print(r.status_code, len(r.json()[\"checks\"]) if r.status_code == 200 else \"\")"'
   ```

   It prints `200 12`, the twelve checks. A `401` is a file older than the vaulted read-only key: the swap still restores it, and `hc-keys` step 6 re-mints the key after. Another status, or a traceback, is a file the service cannot read: stage an older one.

3. **Swap it in**, on the node, the volume's name read first: `sudo docker volume ls --format '{{.Name}}' | grep hc-data` prints one name, `zcrypto-hc_hc-data`, Compose naming the volume for its directory. A name that is absent from the list is not mounted below, since Docker would create it empty. Then, with that name and `<tag>` the pinned one:

   ```bash
   sudo systemctl stop zcrypto-hc.service
   sudo docker run --rm --network none -v zcrypto-hc_hc-data:/data -v /tmp/hc-restore:/restore:ro --entrypoint sh ghcr.io/zhaow-de/healthchecks:<tag> -c 'mkdir -p /data/replaced && for f in /data/hc.sqlite /data/hc.sqlite-wal /data/hc.sqlite-shm /data/hc.sqlite-journal; do [ ! -e "$f" ] || mv "$f" /data/replaced/; done && cp /restore/hc.sqlite /data/hc.sqlite'
   sudo systemctl start zcrypto-hc.service
   ```

   `sudo docker inspect zcrypto-hc --format '{{.State.Health.Status}}'` reads `healthy` within a minute or two of the start.

4. **Run a backup at once**, on the node, after step 3 wherever step 3 ran: `sudo systemctl start zcrypto-sqlite-backup.service`, then `sudo cat /var/lib/zcrypto-node-textfile/sqlite-backup.prom` names the run's time.

5. **Confirm by value**, from the workstation: `uv run python infra/scripts/hc-provision.py status` reads each check's `last_ping` moving past the restore as its pinger's next ping lands, and the self-check's next line, `ssh hc 'sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'`, reads `-> pinged`. A self-check reading `-> ping failed: HTTPError` and no check moving is a ping key rotated after the backup: `hc-lost-database` step 3 sets it back. `status` refused on a key is an API key re-minted after the backup: `hc-keys` steps 6 and 7.

6. **Remove the copies**, on the node, once step 5 reads green, since they carry the project's keys and the Slack webhook: `sudo rm -rf /tmp/hc-restore` and, for a file step 1 piped in from the NAS's copy, `rm -f /tmp/hc-<UTC date and time>.sqlite`, then the replaced database, `sudo docker run --rm --network none -v zcrypto-hc_hc-data:/data --entrypoint rm ghcr.io/zhaow-de/healthchecks:<tag> -r /data/replaced`.

### Retire when

`infra/ansible/roles/hc/tasks/main.yml` no longer includes `node_common`'s `sqlite-backup` task file, so no backup file exists to restore.

______________________________________________________________________

<a name="hc-lost-database"></a>

## hc-lost-database — PROCEDURE: re-creating the project after its database was lost with no backup

### What you are seeing

Nothing fired. The service's database is gone and no backup file survives it — not on the node, in its Linode Backups or wherever its files are kept — so `hc-restore` has nothing to read.

### What it means

The project, its uuid, its three keys and its Slack integration live in the database alone, and no API sets a key or a check's uuid; the project's ping key is a field the service's `/admin/` sets. The secret key is the vault's. So a database lost with its backups costs, in this order: the node's converge, which creates the superuser again; the project and its Slack integration added again by hand; the ping key set back to the vault's, so each pinger's URL stays valid and no pinging host's converge is owed; the two API keys minted again and the project's new uuid written, which the ops node's scrape reads, so ops' Alloy is recreated; the twelve checks created again from the tree's fixture, with new uuids and the same names, slugs and periods, their history gone; and a backup run. Until the checks exist, the pingers' pings answer `404` and no check is evaluated: the fleet's dead-man domain is dark, as in `hc-dark`.

### What to do

1. **Converge the node**: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>`, the tag the `hc` row of `docs/reference/fleet-pins.md` records. The service's start creates an empty database, and the role's admin task creates the superuser from the vault. A damaged database file that is still present is moved aside first and kept until the owner has read it, the service stopped and the volume's name read as `hc-restore` step 3 reads it: `sudo systemctl stop zcrypto-hc.service`, then `sudo docker run --rm --network none -v zcrypto-hc_hc-data:/data --entrypoint sh ghcr.io/zhaow-de/healthchecks:<the pinned tag> -c 'mkdir -p /data/lost && mv /data/hc.sqlite* /data/lost/'`, then the converge.

2. **Add the project and its integration**, in the service's UI at `https://zcrypto-hc.zhaow.me`: the owner signs in with `hc_admin_email`, `infra/ansible/host_vars/zcrypto-hc/vars.yml`, and the password pasted from the vault rather than typed: `uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var(sys.argv[1], "host_vars/zcrypto-hc/vault.yml"), end="")' hc_admin_password | wl-copy` (or `xclip -selection clipboard`), the clipboard cleared after. Add the project `zcrypto`; add its Slack integration, its one integration, with a new incoming webhook for the main channel minted in Slack for the service alone, and no email or other integration beside it; send that integration's test notification and read it arriving in the main channel; set Email Reports Off at `https://zcrypto-hc.zhaow.me/accounts/profile/notifications/`, the service's default being monthly.

3. **Set the ping key back**: in `https://zcrypto-hc.zhaow.me/admin/`, under sudo mode, set the project `zcrypto`'s ping key to the vaulted `hc_ping_key`, pasted the same way: the line of step 2 with `"group_vars/observed/vault.yml"` as its file and `hc_ping_key` as its argument.

4. **Mint the two API keys and write the uuid**: on the project's Settings page, under sudo mode, create the project's two API keys, each vaulted at once from the repo root, each pasted at its prompt:

   ```bash
   (cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/all/vault.yml hc_readwrite_api_key 'hcw_[A-Za-z0-9]{28}' --replace)
   (cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_readonly_api_key 'hcr_[A-Za-z0-9]{28}' --replace)
   ```

   Write the project's uuid, read off the same page, over `hc_project_uuid` in `infra/ansible/group_vars/observed/vars.yml`. Then ops' Alloy converge with its recreate, `hc-keys` step 6's converge, which takes the new key and the new project's metrics path to the scrape.

5. **Create the checks again**: `uv run python infra/scripts/hc-provision.py apply --from-fixture`, or `apply` alone while the fixture lacks each check's period and grace, writes the twelve checks, each on the Slack integration alone, and reads each back. Grafana's series keep each check's `name` label; its uuid is new.

6. **Run a backup**: `hc-restore` step 4.

7. **Confirm by value**: `uv run python infra/scripts/hc-provision.py status` reads each check's `last_ping` arriving as its pinger's next ping lands, and the self-check's next line reads `-> pinged`.

### Retire when

`infra/scripts/hc-provision.py` no longer takes `apply --from-fixture`, the step that creates the checks again.

______________________________________________________________________

<a name="hc-patch-pass"></a>

## hc-patch-pass — SCHEDULED REMINDER: the monthly patch pass

### What you are seeing

The daily pass's reminders read `OWED hc patch pass`: a month has gone by since the node's last full converge, and the service's image and the packages the node does not upgrade by itself are due their pass. It is not an alert, and nothing is wrong on the node.

### What it means

Unattended upgrades install Debian's security patches alone. Caddy and Docker come from their vendors' repositories, which that origin does not cover, and are upgraded here, by hand, once a month. The service runs one release of the owner's healthchecks clone, pinned by version tag: a newer release is taken by moving the pin, the new tag pulled on the node, the converge naming it, and the `hc` row of `docs/reference/fleet-pins.md` re-trued, the previous tag kept on the node as the rollback. A release whose records stop being JSON objects leaves the stream with no `level` label, and `zcrypto-hc-error-logs` reads nothing from it, so step 6 reads the new release's records. Alloy is held at the fleet's version and moved by a bump alone, the whole fleet together. The reminder counts the month from the node's last full converge in `docs/reference/deploy-log.jsonl`, the one that names no tag, which step 5 runs; the procedures on this page converge under `--tags hc` or `--tags alloy` and leave the count where it is. The log does not say why a converge was run, so an un-tagged converge of the node made for another reason restarts the month too: such a run is followed by this pass, in the same sitting. The service's sign-in page is public: a security release of the clone, or of Caddy, is taken the day it is read, outside the monthly pass, by steps 2 to 6.

### What to do

1. **Read what runs**, from the workstation: `ssh hc dpkg-query -W caddy alloy docker-ce`, and `ssh hc "sudo docker inspect zcrypto-hc --format '{{.Config.Image}}'"`, the tag the `hc` row of `docs/reference/fleet-pins.md` records. The `alloy` line names `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml`, or while the node is held the version `infra/ansible/host_vars/zcrypto-hc/alloy.yml` names. The pass waits while that line names another version and `uv run python infra/scripts/alloy-version.py off-fleet` names `zcrypto-hc` on stderr: the node's own step of an open Alloy wave is still to run, and step 5's un-tagged converge would take it out of the wave's order.

2. **Read the clone's newer releases**: `git ls-remote --tags https://github.com/zhaow-de/healthchecks 'refs/tags/v*'` against the pinned tag. A newer one is read before it is taken, in a scratch clone removed after: `git clone --depth 1 --branch <new> https://github.com/zhaow-de/healthchecks .tmp/hc-<new>`, then `git -C .tmp/hc-<new> fetch --depth 1 origin tag <pinned>` and `git -C .tmp/hc-<new> diff --stat <pinned> <new>`. A release that changes `hc/api/models.py`'s `_failure_log`, the record `zcrypto-hc-error-logs` pages, or the service's JSON log format goes to the owner before it is taken.

3. **Back up, then pull the new release**: `hc-backup` step 1, so the database before the new release's migrations is a file on the node, the rollback's restore point; then `ssh hc 'sudo docker pull ghcr.io/zhaow-de/healthchecks:<tag>'`, `<tag>` the new release.

4. **Upgrade the packages**, on the node: `sudo apt-get update`, then `apt list --upgradable`, then as one line `sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade caddy docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`. `--force-confold` keeps the role's file wherever a package ships a changed config. Docker's packages restart its daemon, which stops the service's container until it is started again: the fleet's pings in that minute or so are lost, inside the twenty minutes of the shortest `timeout` + `grace`. `alloy` is not in the line: it is held and pinned at the fleet's version. Then `systemctl is-active zcrypto-hc caddy docker` reads `active` three times.

5. **Re-converge in full**, from the workstation, naming no tag: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc -e hc_image_tag=<tag>`, `<tag>` the new release step 3 pulled, or the pinned one when none is taken. Its preview shows no change to a rendered file but, with a new release, the compose file's image line; a change elsewhere is a package that replaced a config, and the converge puts the role's back. It also installs Alloy at the version step 1 compared against. With a new release, `ssh hc "sudo docker inspect zcrypto-hc --format '{{.Config.Image}} {{.State.Health.Status}}'"` reads the new tag and `healthy`, and the `hc` row of `docs/reference/fleet-pins.md` takes the new tag and the converge's time on a branch, its notes naming the previous tag as the rollback. The row the converge appends to `docs/reference/deploy-log.jsonl` is the record the reminder counts the next month from.

6. **With a new release, read its records** on the observability node within the hour after the converge: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (level) (count_over_time({host="zcrypto-hc", container="hc"} |= "is now running" [1h]))'` reads `level="INFO"` at 2 for each start of the service in the hour, the alert sender's and the report sender's, and no row without a `level`. The replaced release's stop records carry no such text, and its start records are older than the hour unless step 4 restarted it. A row without a `level` is the new release writing records that are not JSON objects: roll it back by step 5 with the previous tag, by `hc-restore` from step 3's backup when the new release migrated the database, and take the release to the owner.

7. **Read the reboot flag**, on the node: `ls /run/reboot-required`. `No such file or directory` is no reboot pending; the file listed is one, taken by `zcrypto-hc-reboot-pending` below from its first step. Until the observability node pages the main channel, that alert reaches the shadow channel alone, and this read is the one that brings a pending reboot to a person.

### Retire when

The base role's unattended-upgrades origins cover the vendors' repositories, and `infra/ansible/roles/hc/` no longer pins the service's image by `hc_image_tag`.

______________________________________________________________________

<a name="zcrypto-alloy-dark-hc"></a>

## zcrypto-alloy-dark-hc — ALERT

### What you are seeing

A **critical** Grafana alert from the observability node, `Fleet · Alloy dark — Dead-man`: the dead-man node's `up` series have been absent there for more than ten minutes. The Fleet health board's *Dead-man node — its Alloy shipping* panel (921), on the observability node's Grafana, draws it against the green line at 1.

### What it means

The node's Alloy, an apt package under systemd, stopped shipping to the observability node. The node's host series, its backup gauge, its units' journals and the service's records are dark there, so `zcrypto-hc-error-logs` reads nothing, and `zcrypto-hc-service-down` and `zcrypto-hc-backup-stale` page the absence, until this clears. The service itself is not read through this Alloy: Grafana Cloud's `zcrypto-hcio-watchdog` reads it through the ops node's scrape, and the fleet's pings reach it as before. A node that is down altogether is `hc-dark`.

### What to do

1. On the node: `systemctl status alloy`.
2. `sudo journalctl -u alloy --no-pager -n 100`. A config that fails to load is the usual cause; the role validates the file before it lands, so look for a hand edit of `/etc/alloy/config.alloy`.
3. `sudo systemctl restart alloy` is the usual fix. If it will not stay up, re-converge: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags alloy -e hc_image_tag=<the pinned tag>` from the workstation, the tag the `hc` row of `docs/reference/fleet-pins.md` records.
4. Confirm from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-hc"})'` reads 2.

### Retire when

`zcrypto-alloy-dark-hc` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-hc-disk-low"></a>

## zcrypto-hc-disk-low — ALERT

### What you are seeing

A **warning** Grafana alert from the observability node, `Dead-man · root filesystem low`: the dead-man node's root filesystem has been below 15% free for thirty minutes. The Fleet health board's *Dead-man node — root filesystem free* panel (922) draws it against the green line at 0.15.

### What it means

The node is one disk. Docker's images and the service's volume are under `/var/lib/docker`, the volume holding the database and the staged copies of its nightly backups; the backups' copies out are under `/var/backups/zcrypto-hc`, 14 days of each; the journal is under `/var/log/journal`. A full disk stops the database's writes, so the service stores no ping, and stops the nightly backup.

### What to do

1. **Read what fills it**, on the node: `df -h /`, then `sudo du -xsh /var/lib/docker /var/backups/zcrypto-hc /var/log/journal /var/lib/alloy`.
2. **The journal:** `sudo journalctl --vacuum-size=500M` removes its oldest archived files until they hold 500M.
3. **The service's images**: `sudo docker image ls ghcr.io/zhaow-de/healthchecks` lists the tags on the node. The running tag and the previous one stay, the previous being the rollback the `hc` row of `docs/reference/fleet-pins.md` names; an older one is removed by `sudo docker image rm ghcr.io/zhaow-de/healthchecks:<that tag>`.
4. **The backups**: two copies of each night's database for 14 days. A database grown past what the disk holds that many times over is taken to the owner with `hc_backup_keep_days` in `infra/ansible/roles/hc/defaults/main.yml`; a changed value reaches the node by `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>`.
5. **Confirm by value:** panel 922 reads above 0.15 and the rule is back to **Normal**.

### Retire when

`zcrypto-hc-disk-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-hc-reboot-pending"></a>

## zcrypto-hc-reboot-pending — ALERT

### What you are seeing

A **warning** Grafana alert from the observability node, `Dead-man · reboot pending, reboot by hand`: `/run/reboot-required` has been present on the dead-man node for fifteen minutes.

### What it means

The node installs Debian's security patches by itself and does not reboot itself: a reboot stops the service, and with it each dead-man check, for its duration, so it is taken by hand, in the node's 10:25 UTC slot. While the node is down the fleet's pings are lost and no check is evaluated; a reboot of a few minutes ends inside each check's `timeout` + `grace`, so no check pages for it, and one back within `zcrypto-hcio-watchdog`'s five minutes at `999` pages nothing in the main channel. Until the observability node pages the main channel, this alert reaches the shadow channel alone, and the reboot flag comes to a person through `hc-patch-pass` step 7.

### What to do

1. **Reboot in the slot**, on the node: `sudo systemctl reboot`.
2. **Confirm it came back**, from the workstation: `ssh hc uptime -s`, then `ssh hc systemctl is-active zcrypto-hc caddy alloy` reads `active` three times, and `ssh hc "sudo docker inspect zcrypto-hc --format '{{.State.Health.Status}}'"` reads `healthy`.
3. **Confirm by value:** `uv run python infra/scripts/grafana-query.py --stack mon 'node_reboot_required{host="zcrypto-hc"}'` reads 0 within twenty minutes, and the self-check's next line, `ssh hc 'sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'`, reads `-> pinged`.

### Retire when

`zcrypto-hc-reboot-pending` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-hc-service-down"></a>

## zcrypto-hc-service-down — ALERT

### What you are seeing

A **critical** Grafana alert from the observability node, `Dead-man · service not answering its status read`: the dead-man node's self-check has logged no `web=ok` for fifteen minutes. The Fleet health board's *Dead-man node — status reads that answered OK* panel (924) draws the count of reads that passed against the green line at 1.

### What it means

The self-check runs every five minutes on the node. It reads the service's status endpoint, `http://127.0.0.1:8000/api/v3/status/`, naming the service's own host, and pings the service's own check, `zcrypto-hc`, when that read answers `OK`. No `web=ok` in fifteen minutes is each run failing its read, or no run logging at all. A service that fails its read refuses the fleet's pings too, and they are lost. Grafana Cloud's `zcrypto-hcio-watchdog` reads the same service through the ops node's scrape and pages the main channel: `999` when the scrape fails, or the count of down checks once `zcrypto-hc` goes down, twenty minutes from its last ping. With `zcrypto-alloy-dark-hc` firing beside this one, the lines are absent because the node's Alloy is dark: that alert first.

### What to do

1. **Read the self-check's lines**, on the node: `sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -3`. `answered 5xx` is the service failing; `unreadable: URLError` is nothing listening on its port; `answered 400` is a request naming another host than the service's, the unit's `HC_SELFCHECK_HOST`. No line in fifteen minutes is the timer: `systemctl list-timers zcrypto-hc-selfcheck.timer`, and `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>` from the workstation puts its unit back.
2. **Read the container**: `systemctl is-active zcrypto-hc caddy docker`, then `sudo docker inspect zcrypto-hc --format '{{.State.Status}} {{.State.Health.Status}} {{.RestartCount}} {{.State.StartedAt}}'`.
3. **Read its records** on the observability node, where the ping key in a path is already written over, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (level, message) (count_over_time({host="zcrypto-hc", container="hc", level=~"ERROR|CRITICAL|WARNING"} | json message="message" | drop __error__, __error_details__ [1h]))' 'sum(count_over_time({host="zcrypto-hc", container="hc", level=""} [1h]))'`. The second counts lines that are not the service's JSON records, uWSGI's own among them.
4. **Bring it back**: `sudo systemctl restart zcrypto-hc.service`, which keeps the volume. A start that fails again is a full disk, `zcrypto-hc-disk-low` above, or a database the release fails to open, which step 3's records name: `hc-restore` from the newest backup file.
5. **Confirm by value**: the self-check's next line reads `-> pinged`, the rule is back to **Normal**, and `uv run python infra/scripts/hc-provision.py status` reads each check's `last_ping` moving as its pinger's next ping lands.

### Retire when

`zcrypto-hc-service-down` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-hc-backup-stale"></a>

## zcrypto-hc-backup-stale — ALERT

### What you are seeing

A **warning** Grafana alert from the observability node, `Dead-man · backup stale`: the dead-man node's last completed database backup is more than 26 hours old, or the node publishes no backup gauge at all. The Fleet health board's *Dead-man node — age of the last backup* panel (925) draws the age against the red line at 26 hours.

### What it means

The backup runs nightly at 02:47 UTC and writes its gauge only when the run completed each step (`hc-backup`), so a failed run leaves the gauge to age. No gauge at all is a node whose backup has not completed since it was built — a rebuilt node until `hc-restore`'s backup run — or a node whose telemetry is not arriving, which `zcrypto-alloy-dark-hc` pages beside this one. Until it clears, the newest backup file a restore reads is more than a day old, and a database lost now costs every ping and flip since that file.

### What to do

1. **Read the last runs**, on the node: `systemctl list-timers zcrypto-sqlite-backup.timer`, then `sudo journalctl -u zcrypto-sqlite-backup --no-pager -n 20`. The `ERROR` line names the step that failed: `VACUUM INTO … failed` is the container not running, `zcrypto-hc-service-down` above, or a full disk, `zcrypto-hc-disk-low` above; `copying … failed`, `renaming … failed` and `pruning … failed` name the directory that failed; `cannot hold … under the group zcrypto-data` is that account missing, which the node's converge, `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>`, creates; `another run of the hc backup holds …` is a run still going.
2. **Take one by hand** once the cause is cleared: `hc-backup` step 1.
3. **Confirm by value**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'time() - max(zcrypto_sqlite_backup_last_success_timestamp_seconds{host="zcrypto-hc"})'` reads under 93600, and the rule is back to **Normal**.

### Retire when

`zcrypto-hc-backup-stale` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-hc-error-logs"></a>

## zcrypto-hc-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert from the observability node, `Dead-man · ERROR records`, on the `logs` receiver, `for: 0s`, `noDataState: OK`. **The record's message is on the page** — read it before opening anything.

The rule reads `{host="zcrypto-hc", container="hc", level=~"ERROR|CRITICAL"}` over a 15 m window, wrapped in `topk(5, …)`, each message truncated at 200 characters. The Fleet health board's *Dead-man node — the service's ERROR records* panel (926) draws them.

### What it means

The service writes one JSON object per record to its container's output. The node's Alloy ships that stream to the observability node, writes over the path segment after each `/ping/` and lifts each record's `level` to the label this rule selects. The message names what failed:

- **`Notification failed: check '<name>', <kind> channel <8 characters>: <transport error>`**, from the logger `hc.api.models` — the service failed to dispatch a notification, and the check named is the one whose page did not arrive. A Slack `404`, or a `400` reading `invalid_token`, is a refusal for good, which disables the integration: the service then sends it nothing and logs nothing, so this page is that one dispatch, and the state it leaves pages nothing again from the service. A check that goes down in that state still pages through Grafana Cloud's `zcrypto-hcio-watchdog`, by value; the page that state silences whole is `zcrypto-grafana-watchdog`'s, the service's own page when Grafana Cloud is dark, which no Grafana rule can send. Another transport error leaves the integration enabled, and the next notification dispatches again.
- **`Internal Server Error: <path>`**, from the logger `django.request` — a request the service failed; a ping's key in its path is written over before the record leaves the node.

A page that did not arrive with this rule quiet is a dispatch failure the service did not record at `ERROR`: a defect of the clone, fixed in the clone's repository, `https://github.com/zhaow-de/healthchecks`, and worked around nowhere here.

### What to do

1. **Act on the message on the page first.** It names the check and the integration's kind, or the request's path.
2. **Get the full set out of the observability node** — `topk(5, …)` truncates a storm, so five instances is a floor, not a count. Read the set with `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (level, message) (count_over_time({host="zcrypto-hc", container="hc", level=~"ERROR|CRITICAL"} | json message="message" | drop __error__, __error_details__ [1h]))'`.
3. **A `Notification failed` record**: open the project's Integrations page in the service's UI and read the integration's last error beside the record. A disabled integration is marked there, and `uv run python infra/scripts/hc-provision.py status` refuses while the project's Slack integration is disabled.
4. **A disabled Slack integration is removed and added again**, in the service's UI, at the page: a disabled Slack integration can be neither edited nor re-enabled (the service's `https://zcrypto-hc.zhaow.me/docs/configuring_notifications/`, Disabled Integrations). Add it with the main channel's webhook — a new incoming webhook minted in Slack for the service alone when Slack's `404` says the old one is gone — and no email or other integration beside it; send its test notification and read it arriving in the main channel. Then `uv run python infra/scripts/hc-provision.py apply`, or `apply --from-fixture` once the fixture carries each check's period and grace, puts each check on it and reads each back on it alone.
5. **An `Internal Server Error` record**: the path names the route; a record that recurs is a defect of the clone, taken to its repository with the record's message.

### Retire when

`zcrypto-hc-error-logs` is absent from `infra/grafana/alerts.yaml`.
