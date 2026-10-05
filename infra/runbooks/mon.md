# Monitor runbooks — the observability node

You are here because **an alert fired in Slack** — find the section whose anchor matches the alert `uid` — or because you mean to push to the node, compare the two stacks' answers, replace one of its secrets, re-mint the tools' token or restart one of its stores, or because the node itself is down or being rebuilt and you opened `mon-dark` deliberately, or because the daily pass's reminders name the monthly patch pass: the procedures and the reminder's section at the top, found by heading. Each section is written to be actioned without opening any other document.

Everything here is one Linode VPS, `zcrypto-mon` (the workstation's ssh alias `mon`; `Monitor` in Slack and on the Fleet health board), reached by people and tools as `https://zcrypto-mon.zhaow.me`. It runs no containers: Grafana (`grafana-server`), Prometheus, Loki, Caddy and Alloy are apt packages under systemd. Caddy is the one public listener, on 443: it passes `/api/v1/write` to Prometheus and `/loki/api/v1/push` to Loki behind basic auth, answers 404 for `/metrics`, for what lies under it and for `/swagger`, and passes everything else to Grafana, whose own login and tokens guard it. Grafana, Prometheus, Loki and Alloy listen on loopback: `127.0.0.1:3000`, `:9090`, `:3100` and `:12345`. The node's own Alloy ships the node's metrics and journals to its own stores under `host="zcrypto-mon"`. A timer, `zcrypto-mon-selfcheck`, reads every five minutes whether Grafana's rule scheduler is ticking, a fleet sample is fresh and Loki is ready, and its journal line says what it read.

The node holds the fleet's telemetry, the Slack webhook and the power to silence alerts, and no key to another host. Its configuration is the `mon` role and one push, so a lost node is rebuilt from the repository; its metric and log history is on its one disk.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="mon-push"></a>

## mon-push — PROCEDURE: pushing the rules and dashboards to the node

### What you are seeing

Nothing fired. The rule file, a dashboard or the notification template changed, or the node was rebuilt, and the node's Grafana is to carry the tree.

### What it means

`infra/scripts/grafana-push.sh` pushes to the stack its environment names. With no `GRAFANA_URL` it goes to Grafana Cloud and leaves the `zcrypto-mon` rule group out; addressed to the node it sends that group, and step 1 passes `GRAFANA_SKIP_RULE_GROUPS` empty so that a shell which exported the variable cannot make the push skip the group, nor a prune delete it. The script rewrites both contact points when `GRAFANA_SLACK_WEBHOOK_URL` holds a value, whichever channel's it is, so a routine push passes that variable empty: a shell that exported the other stack's webhook then leaves the node's receivers where they point. The conditions on where a push runs from are `.claude/skills/zcrypto-grafana-push/SKILL.md`'s, for this stack as for the other. The token is the Editor service-account token the `mon` role minted into `~/.config/zcrypto/grafana-mon.vault.yml` at its last converge; `grafana_auth.py` reads it as the `mon` stack.

### What to do

1. **Push**, from the repo root, in a checkout that passes the push skill's freshness test:

   ```bash
   GRAFANA_URL=https://zcrypto-mon.zhaow.me GRAFANA_SKIP_RULE_GROUPS= GRAFANA_SLACK_WEBHOOK_URL= \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.token("mon"))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
   ```

   Its first line reads `stack=https://zcrypto-mon.zhaow.me` and `skip-groups=<none>`; a first line naming another stack means the variables did not reach the script, and nothing after it is the node's. Its `GRAFANA_SLACK_WEBHOOK_URL not set` line says the two contact points were left as they are.

2. **A push that mints or moves the node's two contact points** — the first push after a rebuild, or a change of channel — carries the webhook: it is step 1's line with the empty `GRAFANA_SLACK_WEBHOOK_URL=` replaced by `GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_shadow_webhook_url"))')"`. The node pages the shadow channel, so the value is `slack_shadow_webhook_url`.

3. **Confirm by value.** `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-mon"})'` reads 5, and `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` prints no `Rules not evaluating` section.

### Retire when

`infra/scripts/grafana-push.sh` no longer reads `GRAFANA_SKIP_RULE_GROUPS`, so one stack is left and the push needs no stack named.

______________________________________________________________________

<a name="mon-compare"></a>

## mon-compare — PROCEDURE: comparing the rules' queries on both stacks

### What you are seeing

Nothing fired. The daily pass's report printed a `## Comparison` section whose line counts differences or reads `compare: failed`, or a day's comparison is to be run by hand.

### What it means

`infra/scripts/grafana-compare.py` sends each query node of `infra/grafana/alerts.yaml` to both stacks' datasource proxies as an instant query at the same 24 instants, the top of each UTC hour of one day, and compares the two answers by value: a label set present on one stack and not the other, a value off by more than a relative 1e-6, and an empty result against rows are each a difference, and an empty result on both is a match. Three things are outside it by name, the script's three constants: the rules of the node's own group, `zcrypto-mon`; rows whose `host` is `zcrypto-mon`; and the seven rules that read a direct-shipped log stream, which reaches the node at the cutover and not before. The requests go one at a time to either stack, on the live pager's query path, so a run takes ten minutes or so, longer as the hosts ship to the node. The daily pass runs it for the preceding day from the first day the tree names, `COMPARISON_FROM` in `infra/scripts/ops_daily.py`, and its journal entry carries the line; the cutover is gated by seven consecutive daily lines reading `0 differences`, or whose differences the cutover pull request explains.

### What to do

1. **Run it**, from the repo root, for the day whose hour tops are compared; with no `--day` it is the preceding UTC day, and a day that has not ended is refused:

   ```bash
   uv run python infra/scripts/grafana-compare.py --day 2026-11-20
   ```

   It prints one line per difference, `<rule uid> <refId> <instant> <what differs>`, then its summary as the last line, whatever happened. A run outside a pass counts for no day of the seven.

2. **Read the last line.** `compare: <nodes> nodes × 24 instants, 0 differences`, exit 0, is a clean day. `<n> differences`, exit 1: each line above it is a finding for the cutover pull request, fixed or explained there, and not a fault to remediate on the fleet. `compare: failed: <stack> <rule uid> <refId> at <epoch>: …`, exit 2, is that stack refusing, timing out or answering a malformed body at that node and instant, and the day is not a clean one: the node's store is `zcrypto-mon-store-down` below, and a Grafana Cloud refusal is its own status page. Another `compare: failed:` line, the script's refusal before its first query or, under the pass, a run past its 2700 s bound or not ending on its summary, reads as its text says, and that day is not a clean one either.

3. **Read a difference** at the instant it names. `only on <stack> {labels}` is a series one stack holds and the other lacks: a host not yet shipping to the node, a series Grafana Cloud's keep-list drops at the shipper (the `write_relabel_config` keep block of that role's `config.alloy`), or a label one leg rewrites. `value cloud=<a> mon=<b>` is a sample one stack lacks at the instant, or the two engines reading a range differently. `empty on <stack>, <n> rows on <other>` is a query one stack has no data for. A Prometheus node is re-read on both stacks, `--stack mon` the second, with `@ <epoch>` (`date -u -d 2026-11-20T03:00Z +%s`) after each selector and range selector and `time()` written as `<epoch>`: `uv run python infra/scripts/grafana-query.py 'delta(zcrypto_gate_streak_days[6h] @ <epoch>)'`. A Loki node has no `@`: re-read its expression on both stacks with `--loki`, whose window has moved on since the instant, and read the stream's presence on the node by `count_over_time` over the day.

4. **Record it.** Under the pass, the `## Comparison` line goes into the day's journal entry with the pass's paragraph, where the cutover's seven days are read from.

### Retire when

`infra/scripts/grafana_auth.py`'s `STACKS` holds one stack, so there is nothing to compare.

______________________________________________________________________

<a name="mon-dark"></a>

## mon-dark — PROCEDURE: while the node is down or being rebuilt

### What you are seeing

The node is unreachable, powered off or being rebuilt: `https://zcrypto-mon.zhaow.me/api/health` does not answer, `infra/scripts/grafana-query.py --stack mon` and `infra/scripts/ops-daily.py report --stack mon` fail naming it, and the shadow channel is silent. No rule on the node can page this, since a rule cannot page the death of the node it runs on. What tells you is the node's healthchecks.io check, `zcrypto-mon`, which goes down on staleness at its `timeout` 600 s + `grace` 600 s = 20 min from its last ping, through healthchecks.io's own Slack integration; and, about seven minutes behind it, Grafana Cloud's `zcrypto-hcio-watchdog` in the main channel, which counts every down check: the ops Alloy's 60 s scrape of healthchecks.io, then `for: 5m`, then the group interval. Re-quote the two check settings from healthchecks.io; they are settings on a third party's dashboard, and this file does not change when one does. Until the check is minted, with the self-check's last journal line ending `no ping URL is set`, nothing pages the node's death, and a `--stack mon` read failing is the first notice.

### What it means

The fleet is still watched: Grafana Cloud's rules page the main channel throughout. What is gone is the node's own evaluation, so the rules the node alone carries, the `zcrypto-mon` group, are not evaluated, and the node's history for those minutes. Per plane, from the shippers' side: metrics scraped while the node is down are held in each shipper's WAL, up to eight hours, and replayed when it returns; log lines bound for the node are retried about ten times, some seven minutes, then dropped and counted, and `zcrypto-mon-shipper-loss` below follows for each host that ships logs to it, once the node takes that host's metrics again. An outage of the node's ingest past about seven minutes brings Grafana Cloud's `Ops · ERROR logs` page too, from ops' own Alloy stream: `loki.write "mon"` logs the batch it gives up on at `level=error`, which the parse stage labels `ERROR` (`ops-node.md#zcrypto-ops-error-logs`). A store outage with the node up drops the alert history of its minutes, `zcrypto-mon-store-down` below: a transition in that time is in no history read afterwards, although its message was sent. A rebuild starts the stores empty, since the node's history is on its one disk, and the comparison's seven consecutive days (`mon-compare` above) count again from the first day whose 00:00 UTC is at least 50 h after the rebuilt node's converge.

The two figures the drills measured: a thirty-minute power-off lost `[[ROLLOUT: R3's W2 reading — the log lines a 30-minute outage lost]]` (`drills-telemetry.md#drill-w2`), and a rebuild from nothing leaves the node's rules unevaluated for `[[ROLLOUT: R3's W3 reading — the time from the rebuild to the first evaluated rule]]`, from the loss to the first evaluated rule (`drills-telemetry.md#drill-w3`).

### What to do

1. **Confirm it is the node and not your route**: `curl -fsS -m 20 -o /dev/null -w '%{http_code}\n' https://zcrypto-mon.zhaow.me/api/health` from the workstation and from ops (`ssh hp`), then the Linode's state on its page in the Cloud Manager, running or offline, and its LISH console, which answers while the host does.
2. **Read the dead-man domain without the node**: `uv run python infra/scripts/ops-daily.py report --since 24h` reads healthchecks.io through its API with `healthchecks_readonly_api_key`, and Grafana Cloud for the rest; it is the pass's Cloud form, and runs with the node gone.
3. **A node that answers ssh**: `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -3'`. `rules=FAIL` is Grafana: `systemctl is-active grafana-server` on the node, and `mon-store-restart` step 3's failed-start branch. `fleet=FAIL` is the edge: `zcrypto-mon-ingest-dark` below, from its step 1. `loki=FAIL` is the store: `zcrypto-mon-store-down` below. Three `ok` with the check down is the ping's own route, the URL rendered into `/etc/default/zcrypto-mon-selfcheck`, which a converge of the `mon` role re-renders from the vault.
4. **A node that does not answer**: in the Cloud Manager, a Linode reading offline is powered on from its page; one reading running and answering nothing on ssh or in LISH is rebooted from its page. A node whose disk is gone is rebuilt by `drills-telemetry.md#drill-w3`'s *Induce*, which is the rebuild procedure: the firewall rule, the rebuild, the bootstrap, one converge, one push.
5. **Change nothing on the fleet for it.** The fleet's reads through Grafana Cloud still run, `grafana-query.py` with no `--stack`; what is gone is the node's half of each by-value confirm, so a fleet converge waits for the node, whose per-host proof reads it.
6. **On return**: `zcrypto-mon-reboot-pending` step 2's five `active` reads; the rules endpoint's unhealthy list `[]`, `mon-patch-pass` step 5's `intervals=[60] unhealthy=[]` line; the self-check's next line `-> pinged`, and the check up on healthchecks.io; `mon-store-restart` step 5, the silences re-read. The day's journal entry carries the minutes, which hold no alert history and, for each host that ships logs, lines nothing recovers (`zcrypto-mon-shipper-loss` step 4).

### Retire when

`infra/ansible/roles/mon/tasks/main.yml` no longer includes `node_common`'s `selfcheck` task file, at which point nothing pages the node's death and this page has no first fact to open on.

______________________________________________________________________

<a name="mon-secrets"></a>

## mon-secrets — PROCEDURE: generating or replacing one of the node's vaulted secrets

### What you are seeing

Nothing fired, or the `mon` role's first task refused a converge, naming a key in `infra/ansible/host_vars/zcrypto-mon/vault.yml` as missing or misshapen.

### What it means

The role reads from that file `mon_grafana_admin_user`, the admin login's name, `u` and 16 hex digits; `mon_grafana_admin_password` and `mon_grafana_secret_key`, 48 hex characters each; `mon_ingest_fleet_password_hash` and `mon_ingest_logship_password_hash`, the bcrypt hashes Caddy checks the two ingest users against; and `selfcheck_healthcheck_url`, the node's healthchecks.io ping URL (`mon-dark` above), which healthchecks.io mints and only the check's delete-and-recreate replaces. The two ingest passwords themselves are `mon_ingest_fleet_password` and `mon_ingest_logship_password` in `infra/ansible/group_vars/observed/vault.yml`, which the fleet's shippers present. A hash and its password are generated together or they do not match. Each other value is generated and encrypted in one pipe and is neither typed nor printed. The admin's name is a generated one because Grafana locks an account by its name after a run of failed sign-ins, so a name a stranger can guess is one a stranger can keep locked.

### What to do

1. **A generated string** (`mon_grafana_admin_password`, `mon_grafana_secret_key`), from `infra/ansible`: `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` prints the entry; replace the key's block in `host_vars/zcrypto-mon/vault.yml` with it. Replacing `mon_grafana_secret_key` on a running node makes Grafana unable to read what it encrypted under the old one, the contact points' webhook among them: from the converge's restart of Grafana until the webhook is written again, the node's Alertmanager does not load its configuration (`sudo journalctl -u grafana-server --no-pager -n 200 | grep 'Failed to apply Alertmanager config'` shows the line, with the webhook decrypted to garbage as an `invalid URL`), answers not ready, and delivers no message, while the contact points read back as before and a push that passes `GRAFANA_SLACK_WEBHOOK_URL` empty finds nothing wrong. Follow the converge with step 2 of `mon-push`, which rewrites both contact points under the new key; the Alertmanager picks them up at its next sync, within about a minute, and a test of the `metrics` contact point in the node's UI, under Alerting, then reaches the shadow channel.

2. **An ingest password and its hash**, from `infra/ansible`, with `user` set on the block's first line to one of `fleet` and `logship`:

   ```bash
   user=fleet
   uv run --with bcrypt python - "$user" <<'PY'
   import secrets, subprocess, sys

   import bcrypt

   user = sys.argv[1]
   password = secrets.token_hex(24)
   hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()
   for name, value in ((f"mon_ingest_{user}_password", password), (f"mon_ingest_{user}_password_hash", hashed)):
       entry = subprocess.run(["ansible-vault", "encrypt_string", "--stdin-name", name], input=value, capture_output=True, text=True, check=True)
       print(entry.stdout.rstrip())
   PY
   ```

   It prints two entries: the first replaces the key's block in `group_vars/observed/vault.yml`, the second the key's block in `host_vars/zcrypto-mon/vault.yml`.

3. **Converge the node**: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon` from the workstation. A changed admin password is applied by the role's own reset at its sign-in; a changed hash reloads Caddy.

4. **A changed ingest password reaches a shipper at that host's own converge**: until then the shipper presents the old one and Caddy answers 401, so the hosts that ship to the node are converged in the same sitting; a changed password that has reached the node before ops brings Grafana Cloud's `Ops · ERROR logs` page at once, from ops' own Alloy stream logging the 401 on its node-bound writes (`ops-node.md#zcrypto-ops-error-logs`, its `alloy` bullet). The bridgehead takes it by its converge, whose handler restarts Alloy. Ops, the cache nodes and the capture pair take it by a converge carrying the host's running Alloy digest, which renders the secrets file, and then `sudo docker compose up -d` in the host's Alloy project (`/etc/zcrypto-ops/alloy`, `/opt/zcrypto-cache/alloy`, `/etc/zcrypto-capture/alloy`), since the handler's reload keeps the environment the process started with; the recreate is proven by `sudo docker inspect grafana-alloy --format '{{.State.StartedAt}}'` moving, and the capture pair takes its attended form under `.claude/rules/fleet-deploys.md`. The NAS takes it by its apply, `-e nas_apply_compose=true`, proven by `.Created` moving.

5. **The admin's name** (`mon_grafana_admin_user`) is restored and not regenerated on a running node: Grafana keeps the name its database was created with and refuses another as it refuses a wrong password. `git log -p -- infra/ansible/host_vars/zcrypto-mon/vault.yml` holds the entry to put back. A new name fits a node rebuilt with an empty database, from `infra/ansible`: `printf 'u%s' "$(openssl rand -hex 8)" | uv run ansible-vault encrypt_string --stdin-name mon_grafana_admin_user`.

6. **The node's ping URL** (`selfcheck_healthcheck_url`), from `infra/ansible`, with the URL read from the terminal so that it is typed on no command line, printed nowhere and written in clear nowhere: `read -rs url`, paste the URL from the check's page (`mon-dark` above) and press Enter, then `printf %s "$url" | uv run ansible-vault encrypt_string --stdin-name selfcheck_healthcheck_url` and `unset url`. `printf %s` writes the value without a trailing newline, which the role's first task refuses; replace the key's block in `host_vars/zcrypto-mon/vault.yml` with the entry it prints.

### Retire when

`infra/ansible/roles/mon/tasks/main.yml` no longer opens with the task `refuse a missing or misshapen secret, naming the key and never the value`.

______________________________________________________________________

<a name="mon-token-rotate"></a>

## mon-token-rotate — PROCEDURE: re-minting the tools' Grafana token

### What you are seeing

Nothing fired. The tools' token is to be replaced: it may have been exposed, or a tool answers 401 from the node.

### What it means

The `mon` role keeps one service account, `zcrypto-tools`, an Editor, holding one token, and caches that token vault-encrypted on the workstation at `~/.config/zcrypto/grafana-mon.vault.yml`. A converge keeps the cached token while Grafana accepts it and it is the account's one token; otherwise, or when asked, it mints a new one, rewrites the cache and deletes the others. A token a tool was holding stops working at that moment, and the next tool run reads the new one from the cache.

### What to do

1. **Re-mint**: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon -e mon_grafana_token_rotate=true` from the workstation. Without the flag the same converge re-mints by itself when the cached token is missing, refused or one of several.
2. **Confirm by value**: `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-mon"})'` reads 5.
3. **A converge that stops at `refuse to go on when the vaulted password is still refused`** met Grafana's login lockout, or a vaulted name the database was not created with. The lockout: a run of failed sign-ins under the admin's name locks the account for about five minutes, and a mistyped password in the UI counts. Wait five minutes without signing in, then run step 1 again. Refused again after a quiet five minutes, it is the name: `mon-secrets` step 5.

### Retire when

`infra/ansible/roles/mon/tasks/token.yml` no longer exists.

______________________________________________________________________

<a name="mon-store-restart"></a>

## mon-store-restart — PROCEDURE: restarting Prometheus, Loki or Grafana by hand

### What you are seeing

Nothing fired, or `zcrypto-mon-store-down` sent you here, or a converge of the node failed after it rendered a store's config: a store on the node is to be restarted, or Grafana is.

### What it means

Grafana evaluates each rule every minute against the two stores, and a rule whose query cannot run pages, unless its `execErrState` is `OK`. A store restarted under a running Grafana therefore puts the rules that read it in error for the length of the restart, which pages only if an evaluation falls inside it. The role's handlers restart a store with Grafana stopped around it, and this procedure does the same by hand. A converge that fails part-way runs none of the restarts it had queued, and the next one finds the files unchanged and queues none: a store whose config such a converge rendered keeps running the old one until it is restarted here. Grafana's unit waits for both stores to answer ready before it starts, so starting it early is safe. Grafana writes its silences and its notification log to disk every fifteen minutes and at a clean stop: after a stop that was not clean, a silence set in the last fifteen minutes may be gone and a notification may be sent a second time.

### What to do

1. **Stop Grafana**, on the node: `sudo systemctl stop grafana-server`. Rule evaluation stops here; say so in the channel the node pages if the stop will be long.
2. **Restart the store**: `sudo systemctl restart prometheus`, or `sudo systemctl restart loki`.
3. **Start Grafana**: `sudo systemctl start grafana-server`. The command returns once both stores answered ready and Grafana started; `curl -fsS http://127.0.0.1:9090/-/ready` and `curl -fsS http://127.0.0.1:3100/ready` are the two reads it waits on. A start that fails — `Job for grafana-server.service failed because the control process exited with error code`, and `systemctl status grafana-server` naming an `ExecStartPre=/usr/bin/curl` process with `code=exited` — is a store that did not answer ready within its wait: Grafana stays stopped and evaluates nothing until the store is ready. Read which and why by `zcrypto-mon-store-down` steps 1 and 2 below, and once the store answers ready run `sudo systemctl start grafana-server` again; the packaged unit's `Restart=on-failure` retries it meanwhile.
4. **Confirm by value**, from the workstation: `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` prints `## Alerts firing` and neither `Rules not evaluating` nor `the rules API`.
5. **After a Grafana that was killed or lost power**, re-read the silences in the node's UI, under Alerting, and set again the ones that are gone.

### Retire when

`infra/ansible/roles/mon/handlers/main.yml` no longer carries the handler `stop grafana around a store restart`.

______________________________________________________________________

<a name="mon-patch-pass"></a>

## mon-patch-pass — SCHEDULED REMINDER: the monthly patch pass

### What you are seeing

The daily pass's reminders read `OWED mon patch pass`: a month has gone by since the node's last full converge, and the packages the node does not upgrade by itself are due their pass. It is not an alert, and nothing is wrong on the node.

### What it means

Unattended upgrades install Debian's security patches alone, `prometheus` among them since drill W1 read a bare restart of it under a running Grafana silent. Grafana, Loki, Alloy and Caddy come from their vendors' repositories, which that origin does not cover, and the four are upgraded here, by hand, once a month; step 3's line keeps `prometheus` so that a patch unattended upgrades has not yet taken installs under the same stopped Grafana. The reminder counts the month from the node's last full converge in `docs/reference/deploy-log.jsonl`, the one that names no tag, which step 4 runs; the procedures on this page converge under `--tags mon` and leave the count where it is. The log does not say why a converge was run, so an un-tagged converge of the node made for another reason restarts the month too: such a run is followed by this pass, in the same sitting. Grafana's login is public, so an advisory that needs no authentication is patched the day it is read, outside the monthly pass, by steps 2, 3 and 5.

### What to do

1. **Read Grafana's security advisories first**, `https://grafana.com/security/security-advisories/`, against the installed version: `ssh mon dpkg-query -W grafana loki alloy caddy prometheus`.

2. **Read what would move**, on the node: `sudo apt-get update`, then `apt list --upgradable`. When `grafana` is listed, read its release notes up to the listed version, `https://github.com/grafana/grafana/releases`, for a removal of a deprecated endpoint the push script calls, the provisioning API under `/api/v1/provisioning` or the dashboard write `/api/dashboards/db`. In the monthly pass a release that removes one goes to the owner before it is installed, as what brings the push script's port to Grafana's `/apis` routes due; while it is held, step 3 runs in its held form. An advisory's same-day patch is not held, nor the edge closed, since Caddy carries the ingest paths beside the login: step 3 installs it whatever its notes say, the rules already on the node keep evaluating, and until the port step 5 is taken without its push.

3. **Upgrade the stores with Grafana stopped, then Grafana**, on the node, as one line: `sudo systemctl stop grafana-server && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade loki alloy caddy prometheus && sudo systemctl daemon-reload && sudo systemctl restart loki && curl -fsS -o /dev/null --max-time 3 --retry 40 --retry-delay 3 --retry-all-errors http://127.0.0.1:3100/ready && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade grafana && sudo systemctl start grafana-server`. Prometheus's package restarts it inside the first install, while Grafana is stopped. Loki's does not, so the line restarts Loki, upgraded or not, after a `daemon-reload` that reads the unit file its package ships, and waits for it to answer ready before Grafana's package is installed. Grafana's package restarts it at the end of the second install, behind its unit's wait for both stores, and the last command starts it when the pass upgraded no Grafana. The held form, for a Grafana release the owner is holding, is the same line without the second install: `sudo systemctl stop grafana-server && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade loki alloy caddy prometheus && sudo systemctl daemon-reload && sudo systemctl restart loki && curl -fsS -o /dev/null --max-time 3 --retry 40 --retry-delay 3 --retry-all-errors http://127.0.0.1:3100/ready && sudo systemctl start grafana-server`. `--force-confold` keeps the role's file wherever a package ships a changed config, and asks nothing: the package's own `/etc/default/prometheus` would start Prometheus on its 15-day default retention, which deletes the older blocks. The wait prints a `curl:` error line for each try Loki is not yet ready for, and the line is still running: it has stopped there when the prompt comes back before the second install has run. A line that stops part-way leaves Grafana stopped: run its remaining commands by hand, the start last. One that stops at the wait for Loki is a Loki that did not come ready after its restart: read why by `zcrypto-mon-store-down` step 2 below before the rest. A last command that fails is a store that did not answer ready within Grafana's own wait: `mon-store-restart` step 3's failed-start branch. Then `sudo alloy validate /etc/alloy/config.alloy && echo valid` prints `valid`: an upgraded Alloy was restarted by its package on the new binary, and an `Error:` line there is a release that refuses the role's config, which leaves the node's Alloy dark (`zcrypto-alloy-dark-mon` below) until `infra/ansible/roles/mon/files/config.alloy` is fixed on a branch and converged.

4. **Re-converge in full**, from the workstation, so the role's files are what the upgraded packages run: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon`, naming no tag. Its preview shows no change to a rendered file; a change there is a package that replaced a config, and the converge puts the role's back. The row it appends to `docs/reference/deploy-log.jsonl` is the record the reminder counts the next month from.

5. **After a Grafana upgrade, run the acceptance reads.** An upgrade can rename an ini key or move a default, so these read what the node's hardening and its rule cadence rest on. First `mon-push` step 1, which re-sends the tree and reads the template back byte-identical and each rule's datasource, then `mon-push` step 3. Then, from the workstation at the repository root:

   ```bash
   ssh mon 'sudo ls /var/lib/grafana/plugins 2>/dev/null | wc -l'
   for p in /metrics /metrics/plugins/prometheus /swagger; do curl -sS -o /dev/null -w "$p %{http_code}\n" "https://zcrypto-mon.zhaow.me$p"; done
   uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; node = "host_vars/zcrypto-mon/vault.yml"; print("user = \"" + vault_var("mon_grafana_admin_user", node) + ":" + vault_var("mon_grafana_admin_password", node) + "\"")' | curl -sS -K - -o /dev/null -w '%{http_code}\n' https://zcrypto-mon.zhaow.me/api/org
   for n in 1 2 3 4 5 6; do curl -sS -o /dev/null -w '%{http_code} ' -H 'Content-Type: application/json' -d '{"user":"admin","password":"probe"}' https://zcrypto-mon.zhaow.me/login; done; echo
   uv run python -c 'import json, sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; node = "host_vars/zcrypto-mon/vault.yml"; print(json.dumps({"user": vault_var("mon_grafana_admin_user", node), "password": vault_var("mon_grafana_admin_password", node)}))' | curl -sS -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d @- https://zcrypto-mon.zhaow.me/login
   curl -sS https://zcrypto-mon.zhaow.me/api/health
   mon_get() { uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print("Authorization: Bearer " + g.token("mon"))' | curl -fsS -H @- "https://zcrypto-mon.zhaow.me$1"; }
   mon_get /api/prometheus/grafana/api/v1/rules | jq -r '[.data.groups[] | {interval, bad: [.rules[] | select(.health != "ok") | .name]}] | "intervals=\(map(.interval) | unique) unhealthy=\(map(.bad) | add)"'
   mon_get /api/v1/provisioning/policies | jq -c '{receiver, group_by, routes: (.routes // [] | length)}'
   mon_get /api/v1/provisioning/mute-timings | jq -c .
   mon_get /api/v1/ngalert | jq -r .alertmanagersChoice
   ```

   In order: `0`, the plugin preinstaller still off; three lines ending `404`, the paths Grafana serves without a login still refused at the edge; `401`, basic auth still off, the line presenting the vaulted admin name and password as `Authorization: Basic`, which a Grafana with basic auth on answers `200`; six `401` and then `200`, the lockout still by account name, six refused sign-ins under the default name leaving the vaulted name's open; a health body with `"database": "ok"` and no `version` key; `intervals=[60] unhealthy=[]`, each group still evaluated at the 60 s the push does not set; `{"receiver":"metrics","group_by":["grafana_folder","alertname"],"routes":0}` and `[]`, the notification policy as the push left it and no mute timing; `internal`, Grafana's own Alertmanager. A reading that differs is the upgrade having moved a key or a default, fixed on a branch and converged before the pass is done: a Grafana setting in the role's `grafana.ini.j2`; a route, the `404` set or the `HEAD` set in the edge include's vars in `infra/ansible/roles/mon/tasks/main.yml`; a Caddy directive in the shared role's `infra/ansible/roles/edge/templates/Caddyfile.j2`. Last, in the node's UI, open one firing rule's Slack message and follow its panel link and its silence link.

6. **Read the reboot flag**, on the node: `ls /run/reboot-required`. `No such file or directory` is no reboot pending; the file listed is one, taken by `zcrypto-mon-reboot-pending` below from its first step. Until the node pages the main channel, that alert reaches the shadow channel alone, and this read is the one that brings a pending reboot to a person. It reads the flag and not the published gauge, so it also holds when the reboot-check timer has stopped publishing, which that alert reads as no reboot pending.

### Retire when

The base role's unattended-upgrades origins cover the vendors' repositories.

______________________________________________________________________

<a name="zcrypto-alloy-dark-mon"></a>

## zcrypto-alloy-dark-mon — ALERT

### What you are seeing

A **critical** Grafana alert from the node itself, `Fleet · Alloy dark — Monitor`: the node's own `up` series have been absent for more than ten minutes.

### What it means

The node's Alloy, an apt package under systemd, stopped shipping to the node's own stores. The node's host, Grafana, Prometheus and Loki series are dark, so the other rules of the `zcrypto-mon` group read nothing and say nothing until this clears. The fleet's rules are unaffected: they read what the fleet's own Alloys ship, which reaches the node through Caddy and not through this Alloy.

### What to do

1. On the node: `systemctl status alloy`.
2. `sudo journalctl -u alloy --no-pager -n 100`. A config that fails to load is the usual cause; the role validates the file before it lands, so look for a hand edit of `/etc/alloy/config.alloy`.
3. `sudo systemctl restart alloy` is the usual fix. If it will not stay up, re-converge: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon` from the workstation.
4. Confirm from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-mon"})'` reads 5.

### Retire when

`zcrypto-alloy-dark-mon` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-disk-low"></a>

## zcrypto-mon-disk-low — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · root filesystem low`: the node's root filesystem has been below 15% free for thirty minutes. The Fleet health board's *Monitor — root filesystem free* panel (902) draws it against the green line at 0.15.

### What it means

The node is one 80 GB disk. Prometheus's blocks are under `/var/lib/prometheus`, capped at 16 GiB; Loki's chunks under `/var/lib/loki`; Grafana's database under `/var/lib/grafana`; the journal under `/var/log/journal`. A full disk stops ingestion first and evaluation after it.

### What to do

1. **Read what fills it**, on the node: `df -h /`, then `sudo du -xsh /var/lib/prometheus /var/lib/loki /var/lib/grafana /var/log/journal /var/lib/alloy`.
2. **The journal:** `sudo journalctl --vacuum-size=500M` removes its oldest archived files until they hold 500M.
3. **Prometheus above its cap** is `zcrypto-mon-retention-by-size` below; **Loki growing** past a few hundred megabytes is a shipper logging far more than the fleet's few megabytes a day: read which, from the workstation, with `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (host, container) (bytes_over_time({host=~".+"}[24h]))'`.
4. **Confirm by value:** panel 902 reads above 0.15 and the rule is back to **Normal**.

### Retire when

`zcrypto-mon-disk-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-reboot-pending"></a>

## zcrypto-mon-reboot-pending — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · reboot pending, reboot by hand`: `/run/reboot-required` has been present on the node for fifteen minutes.

### What it means

The node installs Debian's security patches by itself and does not reboot itself: a reboot stops rule evaluation for its duration, so it is taken by hand, in the node's 06:25 UTC slot. At boot Grafana starts after both stores answer ready, so the boot itself puts no rule in error. While the node is down the fleet's shippers keep their metrics for up to eight hours and replay them; log lines pushed while it is down are retried about ten times and then dropped. Until the node pages the main channel, this alert reaches the shadow channel alone, and the reboot flag comes to a person through `mon-patch-pass` step 6.

### What to do

1. **Reboot in the slot**, on the node: `sudo systemctl reboot`.
2. **Confirm it came back**, from the workstation: `ssh mon uptime -s`, then `ssh mon systemctl is-active grafana-server prometheus loki` and `ssh mon systemctl is-active caddy alloy` read `active` five times between them.
3. **Confirm by value:** `uv run python infra/scripts/grafana-query.py --stack mon 'node_reboot_required{host="zcrypto-mon"}'` reads 0 within twenty minutes, and `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` prints no `Rules not evaluating` section.

### Retire when

`zcrypto-mon-reboot-pending` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-store-down"></a>

## zcrypto-mon-store-down — ALERT

### What you are seeing

A **critical** Grafana alert from the node, `Monitor · a store down or not ready`: fewer than two of Prometheus and Loki have been up and ready for three minutes. When the page is in its error state, with Grafana's own error text in it, the store that is down is Prometheus, which this rule's query runs on.

### What it means

With Prometheus down, every rule that reads metrics is in error and pages as such; with Loki down, the rules that read logs are. While Loki is down Grafana's alert history is not written and is not retried: a transition that happens in that time is missing from the daily pass's fired-in-window list and from a history read afterwards, although its Slack message was sent. Metrics the fleet ships while Prometheus is down are kept by each shipper for up to eight hours and replayed; log lines are retried about ten times and then dropped.

### What to do

1. **Read which**, on the node: `systemctl is-active prometheus loki`, then `curl -fsS http://127.0.0.1:9090/-/ready` and `curl -fsS http://127.0.0.1:3100/ready`.
2. **Read why**: `sudo journalctl -u prometheus --no-pager -n 100` or `sudo journalctl -u loki --no-pager -n 100`. A full disk is `zcrypto-mon-disk-low` above.
3. **Bring it back** by `mon-store-restart` above, clearing first a cause step 2 found: that procedure stops Grafana, and a store that does not come back leaves it stopped, evaluating nothing.
4. **Record the gap.** The minutes Loki was down are minutes with no alert history: note them in the day's journal entry, so a quiet fired-in-window list for that time is not read as a quiet fleet.

### Retire when

`zcrypto-mon-store-down` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-sqlite-locked"></a>

## zcrypto-mon-sqlite-locked — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · Grafana's database locked`: Grafana gave up on a database operation with `database is locked` in the last fifteen minutes. It clears by itself when the window empties and sends no resolved message.

### What it means

Grafana keeps its own state — rules, dashboards, alert instances, silences — in an embedded SQLite database, `/var/lib/grafana/grafana.db`, in WAL mode. A write that finds the database locked sleeps and is retried, and each retry logs `Database locked, sleeping then retrying` at info: those lines are routine, at each start and beside Grafana's own cleanup job, and the rule leaves them out. What it counts is a line logged when Grafana gave up with the database still locked: a write whose retries ran out, or a request it could not authenticate because the session read failed. While a push runs, which writes each rule in turn, such a line is usually one of Grafana's own jobs, its cleanup or its state save, giving up behind the push: the push's exit status says whether a call of its own failed. Lines that keep coming with no push running are the recorded condition for moving Grafana's state to PostgreSQL.

### What to do

1. **Read the lines**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "database is locked" != "sleeping then retrying" [24h]))'`, and on the node `sudo journalctl -u grafana-server --no-pager --since -1h | grep 'database is locked' | grep -vc 'sleeping then retrying'`.
2. **A push was running**: read how it ended. A push that exited 0 lost nothing and is not run again; one that exited non-zero is run again by `mon-push`. The rule clears fifteen minutes after the last line.
3. **No push was running, and the count keeps rising across a day**: take it to the owner as the trigger for PostgreSQL. A restart by `mon-store-restart` step 1 and step 3 clears a lock a crashed writer left.

### Retire when

`zcrypto-mon-sqlite-locked` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-ingest-dark"></a>

## zcrypto-mon-ingest-dark — ALERT

### What you are seeing

A **critical** Grafana alert from the node, `Monitor · ingest dark, every fleet host absent at once`: no fleet host has had a sample on the node for five minutes past the five a vanished series stays readable.

### What it means

Every fleet host ships to the node through Caddy on 443. All of them going absent together is a fault of that edge — Caddy stopped, its certificate expired or was not renewed, the firewall, the DNS name — and not of eight hosts at once. The per-host Alloy-dark pages follow about five minutes later, and so does the engine-dark-with-exposure page when a position is open, because the engine's `up` is absent like every other: read this page first, and those as its echo. The fleet is likely healthy and still shipping to its other destination. Until the fleet's hosts ship to this node at all, this rule fires and stays firing: nothing has arrived yet.

### What to do

1. **Read the edge from outside**, from the workstation: `curl -fsS -o /dev/null -w '%{http_code}\n' https://zcrypto-mon.zhaow.me/api/health` reads 200. A TLS error names the certificate; a timeout names the firewall or the DNS record.
2. **Read Caddy**, on the node: `systemctl is-active caddy`, then `sudo journalctl -u caddy --no-pager -n 100`. Lines naming `acme` or `certificate` are a renewal that failed: the certificate is issued over 443 itself, so a closed 443 at the provider's firewall also stops renewal.
3. **Read the ingest credential through the edge**, from the workstation: `uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print("user = \"fleet:" + vault_var("mon_ingest_fleet_password", "group_vars/observed/vault.yml") + "\"")' | curl -sS -K - -o /dev/null -w '%{http_code}\n' -X POST https://zcrypto-mon.zhaow.me/api/v1/write`. Caddy keeps no access log, so the node holds no count of refused pushes; this presents the vaulted `fleet` password as a shipper does. `401` is the node's hash refusing it: `mon-secrets` steps 2 and 3 put the pair back in step. Another status is Caddy admitting it, and a shipper that is still refused holds an older password: `mon-secrets` step 4.
4. **Bring Caddy back**: `sudo systemctl restart caddy`. It does not touch the stores or Grafana.
5. **Confirm by value**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'count(count by (host) (up{host!="zcrypto-mon"}))'` reads the number of hosts that ship to the node.

### Retire when

`zcrypto-mon-ingest-dark` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-series-high"></a>

## zcrypto-mon-series-high — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · head series above budget`: Prometheus has held more than 40,000 series in its head for three hours. The Fleet health board's *Monitor — Prometheus head series* panel (907) draws the count against the red line.

### What it means

The fleet ships to the node unfiltered, so nothing at a shipper bounds the series count, and this rule is the budget's fence. Memory grows by about 2.3 KB a series and disk by the samples those series write. A count that stepped up and stayed is a new exporter, a shipper whose collector set widened, or a label that takes a new value per request or per restart.

### What to do

1. **Read who holds them**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'sort_desc(count by (host, job) ({__name__=~".+"}))'`.
2. **Read which families**, for the host and job at the top: `uv run python infra/scripts/grafana-query.py --stack mon 'topk(15, count by (__name__) ({host="<host>", job="<job>"}))'`.
3. **A label growing a value per request** shows as one family far above the rest: the fix is at the shipper, in that host's `config.alloy`, and reaches the node at that host's converge.
4. **The count is the fleet's honest size**: take the bar to the owner; it is `zcrypto-mon-series-high`'s threshold in `infra/grafana/alerts.yaml` and the red line of panel 907.

### Retire when

`zcrypto-mon-series-high` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-retention-by-size"></a>

## zcrypto-mon-retention-by-size — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · Prometheus retention cut by size`: Prometheus deleted a block because its size cap was reached, in the last six hours.

### What it means

Prometheus on the node keeps 90 days or 16 GiB, whichever is reached first, and the cap is sized so that the 90 days are reached first. A deletion by size means the store now holds less than 90 days: the series count or the sample rate outgrew what the cap was sized for. Nothing is lost that a rule reads, since the widest rule window is 27 hours; what shortens is how far back a dashboard can look.

### What to do

1. **Read the store's size and reach**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'prometheus_tsdb_storage_blocks_bytes{host="zcrypto-mon"}' '(time() - prometheus_tsdb_lowest_timestamp_seconds{host="zcrypto-mon"}) / 86400'`: bytes on disk, and the days the oldest sample reaches back.
2. **Read the series count**: `zcrypto-mon-series-high` above, steps 1 and 2. A count far above the budget is the cause, and is fixed at the shipper.
3. **The count is right and the cap is small**: take `mon_prometheus_retention_size` in `infra/ansible/roles/mon/defaults/main.yml` to the owner; the disk's free space is `df -h /` on the node. A changed value reaches the node by `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`, whose handler restarts Prometheus with Grafana stopped around it.

### Retire when

`zcrypto-mon-retention-by-size` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-shipper-loss"></a>

## zcrypto-mon-shipper-loss — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · a shipper lost samples or log lines`, naming a host: in the last six hours that host's Alloy had samples refused for good by a destination, or gave up on a batch of log lines, and the count has stayed above zero for fifteen minutes. The Fleet health board's *Monitor — samples and log lines a shipper lost* panel (909) draws the count per host.

### What it means

Each Alloy counts what it failed to deliver and ships the counts with its other metrics. A sample is counted once a destination answered it with an error Alloy does not retry, as a rejected credential is; samples a destination is not taking for the moment stay on the shipper for up to eight hours, are retried, and are not counted. A log entry is counted once Alloy gave up on its batch: at once on a rejected credential, and after about ten retries, some seven minutes, when the destination is down or erroring. Log lines have no such store on the shipper, so a counted one is gone, and the rules that read that host's logs then reason over an incomplete stream: their silence no longer means healthy. After a reboot of the node, or a stop of its Loki longer than those minutes, this alert follows for each host that was shipping logs to it, and clears six hours after the last lost line. The applications' own log push is not Alloy's and has its own alert, `zcrypto-logship-lines-dropped`. This alert does not see a host that delivers no metrics at all, since the counts travel with them: that is the host's Alloy-dark alert. It does not see samples a shipper held for a destination longer than eight hours, or held across its own restart: those are dropped without being counted. And it reads an increase, so a loss that fell wholly before a count's first sample reached the node is not in it.

### What to do

1. **Read which shipper and toward which destination**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'sum by (host, url) (increase(prometheus_remote_storage_samples_failed_total{job="integrations/self"}[6h])) > 0' 'sum by (instance, host, reason) (increase(loki_write_dropped_entries_total{job="integrations/self"}[6h])) > 0'`. The first names the shipper as `host` and the destination as `url`; the second names the shipper as `instance`, its machine's hostname, and the destination as `host`.
2. **Read why**, in that shipper's Alloy log: a `non-recoverable error` line is refused samples and a `final error sending batch` line a dropped batch of log lines, and each names the destination and the status it answered. On the node: `sudo journalctl -u alloy --no-pager --since -6h | grep -E 'non-recoverable error|final error sending batch' | tail -5`. On a host whose Alloy is a container: `sudo docker logs grafana-alloy --since 6h 2>&1 | grep -E 'non-recoverable error|final error sending batch' | tail -5` (on the NAS, `sudo /usr/local/bin/docker logs …`).
3. **A `401` from the node** is the shipper's ingest password out of step with the node's hash: `zcrypto-mon-ingest-dark` step 3 above reads which side holds the stale one. **A status of `-1` or `5xx` toward the node's Loki** is that store down or erroring: `zcrypto-mon-store-down` above.
4. **Record the gap.** The lost log lines are not recoverable: note the host and the hours in the day's journal entry, so that a quiet log-based alert for that host in that time is not read as a healthy one.

### Retire when

`zcrypto-mon-shipper-loss` is absent from `infra/grafana/alerts.yaml`.
