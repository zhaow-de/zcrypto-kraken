# The engine's cache, the infrastructure half: three Valkey nodes under Sentinel on a WireGuard mesh — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three dedicated Linode nodes join the fleet, form a WireGuard mesh with the engine host, run Valkey 9.1.2 as one primary and two replicas under three Sentinels, ship logs and metrics to Grafana Cloud with their own dashboard and rule group, and prove the pinned nautilus-trader client works against Valkey; nothing in this plan attaches the cache to the engine.

**Architecture:** Four Ansible pieces on the fleet's existing shapes: the fleet-membership edits (inventory, vars, keys, the hand-enumerated lists), an interface-scoped port list in the firewall role, a `cache_link` role rendering `zcache0` on the four hosts, and a `cache` role rendering the Valkey, Sentinel and Alloy compose projects on the nodes with the capture role's guards. Observability rides the capture host's Alloy pattern with a cache-specific config, one dashboard and one rule group. The engine-side half of spec 00118 (D4, D10, D11, the harness and the live proof of D15) is a second plan under the same spec, written at Rung 2's design point.

**Tech Stack:** Ansible (devsec.hardening, community.docker, the fleet's roles), WireGuard (`wg-quick`), Docker Compose with digest pins, Valkey 9.1.2 (`valkey-server`, `valkey-sentinel`), Grafana Alloy 1.19 with `prometheus.exporter.unix` and `prometheus.exporter.redis`, Grafana Cloud rules and dashboards through `infra/scripts/grafana-push.sh`, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00118-engine-cache-design.md`

## Global Constraints

- The hosts are `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3` (`<name>.zhaow.me`), inventory group `cache_host`, a child of `observed`; the admin user is `zcrypto-deploy` on port 10022 (spec D13); `deploy` is never created.
- The mesh is `zcache0`, `10.98.0.0/24`: `zcrypto` at `10.98.0.1`, the nodes at `10.98.0.11`, `10.98.0.12`, `10.98.0.13`; port `51821/udp`; `AllowedIPs` one `/32` per peer; `PersistentKeepalive 25`; `MTU = 1380` (spec D5).
- Valkey and Sentinel bind `127.0.0.1` and the host's mesh address only, run with `network_mode: host`, and announce the mesh address (spec D3, D5); no database port is opened on a public address (spec D6).
- The image is `valkey/valkey` at the 9.1.2 index digest, one image for both containers, passed per converge as `-e cache_image_digest=sha256:<64 hex>`; the role refuses a digest the host has not pulled and one `docs/reference/fleet-pins.md` does not record (spec D2, D14).
- Replication: `replica-priority` 100 on valkey1 and valkey2, 250 on valkey3; `min-replicas-to-write 1`, `min-replicas-max-lag 10`; Sentinel `monitor zcache <first primary> 6379 2`, `down-after-milliseconds 5000`, `failover-timeout 60000`, `parallel-syncs 1`, `resolve-hostnames no` (spec D3).
- Durability and memory: `appendonly yes`, `appendfsync always`, RDB snapshots kept; `maxmemory 128mb`, `maxmemory-policy noeviction`; container caps Valkey 256m, Sentinel 64m, Alloy 256m with `GOMEMLIMIT 230MiB`; each Alloy cap takes a leg under `zcrypto-fleet-alloy-memory-headroom` in the commit that adds its compose file, and the Valkey and Sentinel caps are recorded in `_HEADROOM_DELIBERATELY_ABSENT` in theirs, guarded by `zcrypto-cache-memory-70pct` against `maxmemory` (spec D7, amended: `## Spec amendments`).
- ACL users `engine`, `replica`, `sentinel`, `exporter`, the `default` user off; Sentinel `requirepass`; the five secrets in `group_vars/cache_host/vault.yml`; `users.acl` mode 0600 owned by the container's uid; a password shorter than five characters is refused by the role (spec D8). No secret appears in a command line, a log, a diff or a plan step.
- `valkey.conf` and `sentinel.conf` are rendered only when absent; `-e cache_config_reset=true`, on a converge that also carries the node's `cache_image_digest`, is the one way to re-render them, and the role refuses the flag without the digest; drift between the recorded template hash and the current template is reported, never applied (spec D9).
- No role delegates a task between cache nodes: run.sh offers the --limit host's key first and MaxAuthTries is 2, so a delegate_to a peer node exhausts the tries before the peer's key is offered.
- One node per converge, `converge.sh` refusing a group; the first converge goes valkey1, then valkey2, then valkey3; a later re-pin goes replicas first, a deliberate `SENTINEL failover zcache`, then the old primary, each node's `master_link_status:up` before the next (spec D14).
- The converges are tagged: a node's first `--tags base,hardening,firewall,fail2ban,chrony,docker -e daemon_json_ack=true` (the docker role refuses to write the `daemon.json` a fresh node lacks until that ack is passed), the mesh `--tags firewall,cache-link`, Valkey, Sentinel and Alloy `--tags cache` with both `-e cache_image_digest=...` and `-e cache_alloy_digest=...` in one run. The engine host's mesh converge, `--limit zcrypto --tags firewall,cache-link -e converge_primary=true`, restarts no container, and it is a converge of the primary: inside an inter-cycle gap, after a whole read of Kraken's maintenance feed, per `.claude/rules/fleet-deploys.md`.
- No task in this plan touches `cli/`; the engine's compose project, `cli/engine/node.py`, `cli/config.py` and the engine role's templates are the second plan's (spec D4, D10, D11, D15).
- No executor step reaches a host, a venue, Grafana Cloud or Docker Hub; every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean.
- Every commit is green over the changed files' consumers: `grep -rl <script or role name> tests/ infra/ .claude/` before the first commit, and the tests it lists; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs clean before every push; a run that rewrites files is re-run until clean and the rewrites staged.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. A universal word in a new rule, runbook or skill bullet (every, never, always, only, any, cannot) carries its `(set: …; count: …)` or `(no count command: …)` clause.
- A commit message ends with these two trailers, the model name being the executing model's own (`Claude Fable 5.1`, `Claude Opus 5.5`, ...):

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC
```

## File structure

- `infra/ansible/inventory/hosts.yml`: the `cache_host` group, a child of `observed` (Task 1).
- `infra/ansible/group_vars/cache_host/vars.yml`, `vault.yml`: the group's connection, hardening and firewall vars; the five Valkey secrets (Tasks 1, 2, 4).
- `infra/ansible/host_vars/zcrypto-valkey{1,2,3}/vars.yml`: hostname, reboot slot, `ansible_host`, the deploy key lookup, the mesh address, the replica priority (Tasks 1, 3, 4); `host_vars/zcrypto/vars.yml`: the engine host's `51821/udp` and its mesh address (Tasks 2, 3).
- `infra/ansible/files/deploy_zcrypto-valkey{1,2,3}_ed25519{,.pub}`, `files/README.md`: the deploy keys (Task 1).
- `infra/ansible/scripts/run.sh`, `scripts/converge.sh`, `bootstrap.yml`, `roles/base/tasks/main.yml`: the hand-enumerated hosts, tags and extra-var keys; the bootstrap play's hosts; the reboot-slot assert (Task 1).
- `infra/scripts/deploy-log-audit.py`, `ops_daily.py` and their tests: the host lists (Task 1); `ops_daily.py`'s protected objects (Task 4) and its `_UID_HOST` entries for the three Alloy-dark rules (Task 5). `infra/scripts/prune-host-images.py` and its test gain the nodes in the Rollout's records commit, with their first pins rows, not in a task.
- `docs/reference/fleet.md`: Hosts, Reboots, Telemetry labels (Task 1); Services and instruments, Storage topology, Telemetry labels (Task 5).
- `infra/ansible/roles/firewall/`: the interface-scoped port list; `tests/test_infra_firewall_template.py` (Task 2).
- `infra/ansible/roles/cache_link/`: defaults, tasks, handlers, `templates/zcache0.conf.j2`, the handshake-age probe `files/zcache-probe.sh` and its units; `group_vars/all/vars.yml` (public keys) and `vault.yml` (private keys); `site.yml` (the `cache_host` play, the engine host's `cache-link` tag) (Task 3); `tests/test_zcache_probe.py` (Task 3).
- `infra/ansible/roles/cache/`: defaults, tasks, handlers, `templates/compose.yaml.j2`, `valkey.conf.j2`, `sentinel.conf.j2`, `users.acl.j2`, `cli-exporter.env.j2`, `cli-sentinel.env.j2`, `zcrypto-cache.service.j2`; the Alloy compose and secrets templates and `files/config.alloy` (Tasks 4, 5); `roles/capture/files/config.alloy`'s keep list (Task 5).
- `tests/test_infra_firewall_template.py`, `test_infra_cache_templates.py`, `test_infra_compose_templates.py`, `test_infra_converge_guards.py`, `test_infra_alert_rules.py` (`_LIMITED_JOBS`, `_HEADROOM_DELIBERATELY_ABSENT`), `test_infra_alloy_series.py`, `test_dashboards_cover_metrics.py`, `test_ops_daily.py`: the guards and contracts the new roles fall under (Tasks 2–5).
- `infra/grafana/cache-dashboard.json`, `alerts.yaml`, `zcrypto-logs-dashboard.json`, `notification-templates/zcrypto-slack.tmpl`; `infra/runbooks/cache.md`, `observability.md`, `fleet.md` (Task 5).
- `infra/scripts/valkey-compat-probe.py`, `tests/test_valkey_compat_probe.py` (Task 6).
- `.claude/skills/zcrypto-bump-alloy/SKILL.md`, `.claude/skills/zcrypto-daily-ops/SKILL.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md`: the cache nodes in the Alloy bump's host map, canary order and legs, among the daily pass's telemetry-only hosts, and the Valkey re-pin order (Task 7).

## Review Focus

- A node rebooting under unattended-upgrades while it holds the primary, with a second node's slot inside the same failover or resync window, which leaves one Sentinel below the quorum of two: every two hosts' slots must sit an hour apart, off the hour and an hour from a 4 h bar boundary, and the base role's collision assert must read the cache group; Task 1 owns `test_every_reboot_slot_is_an_hour_from_every_other_and_from_a_bar_boundary` and `test_the_collision_assert_reads_the_cache_group`.
- A peer's public key rotated on one side only, which stops that pair's handshake while the others stay up and only the handshake-age rule sees: each member's public key must be one `cache_wg_<member>_public_key` variable, set in no host_vars, which every other member's `zcache0.conf` renders; Task 3 owns `test_each_zcache_peer_key_is_one_variable_every_member_renders` and `test_the_zcache_conf_names_each_other_member_once_as_one_host`.
- A Valkey password carrying a character `users.acl`, `valkey.conf` or `sentinel.conf` splits or quotes on (a space, `>`, `<`, `#`, `%`, a quote, a newline), which would render another password or another rule: `users.acl` must carry each password as `#<sha256>` alone and the role must refuse any password outside five or more letters and digits, naming the key and never the value; Task 4 owns `test_the_acl_file_carries_password_hashes_and_never_a_password`, `test_cache_password_refusal` and `test_cache_password_refusal_names_the_key_and_never_the_value`.
- The daemons rewriting `valkey.conf` and `sentinel.conf` between two converges, as the Rollout's R6 failover does, where a re-render would reset a node's `replicaof` and Sentinel's epoch: a routine converge must leave both as the daemons wrote them (the render's `force` false unless `cache_config_reset`), and the drift report must compare the recorded template hash with the current template's, never the live file, without failing the play; Task 4 owns `test_cache_configs_render_only_when_absent_unless_reset`, `test_cache_drift_reports_a_config_whose_template_moved` and `test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered`.
- The `engine` ACL line against the commands the library issues: on the loopback Redis 8.0.2 used while Task 6 was drafted, `+@all -@admin -@dangerous` refused `INFO`, which the library's version check and the probe both send, and adding `+info` round-tripped the order; the rendered line must admit `KEYS` and `INFO` after `-@dangerous` and subtract none of `@keyspace`, `@read` or `@write`; Task 4 owns `test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous`, and the Rollout's R4 runs the probe under that same line.

---

### Task 1: The three nodes join the fleet: inventory, keys, the hand-kept lists and the fleet page

*Rulings: R1 set `TAGNAMES` to the six base roles' tags plus `cache` and `cache-link`, moved the refused `OUTSIDE` example from `fail2ban` to `bootstrap` and made the published converges the tagged ones; R3 kept `prune-host-images.py` unedited; R18 kept the workstation-side items in the operator block, whose host steps are the Rollout's.*

**Files:**
- Create: `infra/ansible/files/deploy_zcrypto-valkey1_ed25519` (vault-encrypted), `infra/ansible/files/deploy_zcrypto-valkey1_ed25519.pub`, and the same pair for `zcrypto-valkey2` and `zcrypto-valkey3` (generated and vault-encrypted by the owner in operator step O0 before Step 1, never by the executor and never hand-written; committed by Step 11)
- Create: `infra/ansible/group_vars/cache_host/vars.yml`
- Create: `infra/ansible/host_vars/zcrypto-valkey1/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey3/vars.yml`
- Modify: `infra/ansible/inventory/hosts.yml` (the `observed` children, lines 7-12; a `cache_host` group inserted after the `access_host` block, lines 37-41, before `workstation:`)
- Modify: `infra/ansible/host_vars/zaccess/vars.yml` (the reboot-slot comment, lines 4-7)
- Modify: `infra/ansible/bootstrap.yml` (the capture play's `name:` and `hosts:`, lines 1-2; the re-bootstrap comment, lines 23-26)
- Modify: `infra/ansible/roles/base/tasks/main.yml` (the header comment, lines 1-8; `base_fleet_hosts`, line 21)
- Modify: `infra/ansible/scripts/run.sh` (the key-order comment's last two lines, 10-11; `KEYS=`, line 18)
- Modify: `infra/ansible/scripts/converge.sh` (lines 20-33: the `HOSTS`, `TAGNAMES` and `EVKEYS` sets and their comments)
- Modify: `infra/ansible/files/README.md` (three rows inserted after the `deploy_zaccess_ed25519` row, line 13)
- Modify: `infra/scripts/deploy-log-audit.py` (`NO_VENUE_EXPOSURE`, line 112)
- Modify: `infra/scripts/ops_daily.py` (the alias comment and the two alias maps, lines 584-587; `_TELEMETRY_HOSTS`, line 1427)
- Modify: `docs/reference/fleet.md` (three Hosts rows after line 13; one Reboots bullet after line 53; the Telemetry labels bullets, lines 66 and 68)
- Test: `tests/test_run_sh.py` (imports; `HOSTS`, line 14; the `_signalled` sleep, line 108; `test_a_single_host_limit_loads_every_key_with_that_hosts_first`, line 125; two cases appended)
- Test: `tests/test_converge_sh.py` (five `PUBLISHED` entries before its closing `]`, line 344; the `fail2ban` entry of `OUTSIDE`, line 390, and one `OUTSIDE` entry before its closing `]`, line 418)
- Test: `tests/test_infra_converge_guards.py` (`capture_play_tasks`, line 1153; one case after `test_rebootstrap_guard_follows_the_primary_refusal_and_its_probe`)
- Test: `tests/test_infra_unattended_upgrades.py` (imports; five constants after `VAR`; two helpers and four cases appended)
- Test: `tests/test_pins_converged.py` (`test_the_inventory_expands_a_group_to_its_hosts_at_any_depth`, lines 115-117)
- Test: `tests/test_deploy_log_audit.py` (the `parametrize` of `test_venue_facing_drops_a_host_a_window_cannot_harm`, line 121)
- Test: `tests/test_ops_daily.py` (`test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys`, lines 2853-2854; one case appended after it)

**Interfaces:**
- Consumes: the inventory's existing groups; `devsec.hardening`'s `ssh_allow_users` through `hardening_ssh_allow_users`; the base role's `base_hostname`, `base_unattended_upgrades_reboot_time` and its collision assert; `bootstrap.yml`'s capture play and its two refusals; `run.sh`'s ring and `--limit` reordering; `converge.sh`'s whitelist; `NO_VENUE_EXPOSURE`; `ops_daily`'s `ssh_alias`, `host_label`, `_TELEMETRY_HOSTS`, `classify_action`, `Tier`; `pins.inventory_groups`; the test helpers `run`, `run_recording`, `run_no_tty`, `make_harness`, `DIGEST`, `find_task`, `when_conditions`, `load_tasks`, `_identity`, `_yaml`, all existing.
- Produces, for Tasks 2-5 to use by these exact names: the group `cache_host` (a child of `observed`) holding `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`; `infra/ansible/group_vars/cache_host/vars.yml`, which the firewall task appends its port lists to and beside which D8's `vault.yml` lands; the `converge.sh` tags `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `cache` and `cache-link` (the roles of the `cache_host` play in `site.yml` are tagged with exactly these) and extra-var keys `cache_image_digest`, `cache_alloy_digest`, `cache_config_reset` (the `cache` role reads exactly these); the workstation aliases `db1`, `db2`, `db3`; the ops-daily labels `zcrypto-valkey1..3` and aliases `db1..3`.

**What this task decides, where the spec leaves it open:**
- Reboot slots `09:25` (valkey1), `13:25` (valkey2), `17:25` (valkey3): each is 85 min past a 4 h bar boundary (08:00, 12:00, 16:00) and 155 min before the next, four hours from each other, and at least three hours from 21:25, 22:25, 02:25 and 05:25. The nodes keep the base role's automatic reboot (`"true"`, the spec's "unattended-reboot slot"): a reboot of the node holding the primary is a Sentinel failover with both other copies up, where two nodes down together would leave one Sentinel, below the quorum of two, which is what the slots keep apart.
- The collision assert widens to `cache_host` alone, as D13 says. The bridgehead stays outside it; `tests/test_infra_unattended_upgrades.py` gains a case that holds all seven slots (capture, ops, access and cache groups) an hour apart, off the hour and an hour from a bar boundary, so the bridgehead's slot is machine-checked for the first time, and its host_vars comment says so.
- `group_vars/cache_host/vars.yml` carries no firewall declaration in this task. `tests/test_infra_firewall_template.py::test_only_the_bridgehead_group_opens_extra_ports` admits extra-port lists in the access group's vars alone, so `firewall_extra_udp_ports: [51821]` and D6's interface-scoped list land with the task that widens the firewall role and that test together. The Linode Cloud Firewall's `51821/udp` rule is Task 3's operator step O2, for the same two-layer reason; this task opens `22` and `10022` only.
- `infra/scripts/prune-host-images.py`'s `HOSTS` is NOT edited here. `tests/test_prune_host_images.py::test_the_real_pins_file_parses_into_exactly_the_service_host_pairs_the_fleet_runs` asserts `HOSTS` equals the set of hosts the pins file names, and no cache node has a pins row until its first converge; the three entries, `HostAccess(ssh="db1", docker=("docker",))` and its siblings, land in the commit that writes the nodes' first pins rows, which edits that same test's pair set.
- `converge.sh`'s `TAGNAMES` becomes `base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link`. A node's first converge runs the six base roles by their own tags, `--tags base,hardening,firewall,fail2ban,chrony,docker`, with `-e daemon_json_ack=true`, since the docker role diffs its rendered `daemon.json` against the `/etc/docker/daemon.json` a fresh node lacks and refuses that change unacknowledged; the tags keep the `cache_link` and `cache` roles off the node until the Rollout's mesh and probe steps; the mesh converge is `--tags firewall,cache-link`, on a node and on the engine host; the Valkey converge is `--tags cache` with both digests. `cache-proxy` joins with the second plan's proxy, when a procedure first publishes its converge, per the script's rule that a tag enters when it is first used. `tests/test_converge_sh.py`'s `OUTSIDE` example of a role tag the fleet never converged, `fail2ban`, is admitted from here on, so that entry moves to `bootstrap`, which no play in `site.yml` carries.
- `ops_daily.py` gains the two alias maps' entries beside `_TELEMETRY_HOSTS`, because `classify_action` resolves a step's `ssh db1 …` through `host_label` before it reads the telemetry set; without them the set would name hosts no step's spelling reaches. `_UID_HOST` gains the three Alloy-dark uids in Task 5's commit B, beside the rules that mint them: their expression aggregates the `host` label away, so without the map a firing Cache node's Alloy-dark alert reaches the daily pass with no host to classify its restart against.
- A cache node's `host_vars` carries a plaintext `ansible_host`, as the bridgehead's does: the inventory name is not a resolvable name, and the workstation alias `db1` is not what Ansible dials.
- No file under `infra/ansible/group_vars/cache_host/` or `infra/ansible/host_vars/zcrypto-valkey*/` carries the word the venue's name spells: `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` walks the vars of every `NO_VENUE_EXPOSURE` host, and the roles directory whole, so the `cache` and `cache_link` roles later tasks write must not carry it either, or that test names them.

**Operator step O0 (attended), before Step 1: the three deploy keypairs.** The owner runs it, never the executor, from this branch's worktree root before the executor's Step 1; the six files it writes stay uncommitted until Step 11 commits them. The private halves exist in plaintext only between the two commands below. If `ansible-vault encrypt` fails (it reads the vault password through `infra/ansible/scripts/vault-pass.sh`, `sops` over the owner's GPG key, so the GPG agent must be unlocked), delete the three private halves at once with `rm -f infra/ansible/files/deploy_zcrypto-valkey1_ed25519 infra/ansible/files/deploy_zcrypto-valkey2_ed25519 infra/ansible/files/deploy_zcrypto-valkey3_ed25519`, unlock the agent and run O0 again from the top.

```bash
for n in 1 2 3; do
  ssh-keygen -q -t ed25519 -C "zcrypto-valkey$n" -N '' -f "infra/ansible/files/deploy_zcrypto-valkey${n}_ed25519"
done
(cd infra/ansible && uv run ansible-vault encrypt files/deploy_zcrypto-valkey1_ed25519 files/deploy_zcrypto-valkey2_ed25519 files/deploy_zcrypto-valkey3_ed25519)
```

Expected: `Encryption successful`. Then check each file by count, never by printing it:

```bash
for n in 1 2 3; do
  f="infra/ansible/files/deploy_zcrypto-valkey${n}_ed25519"
  printf '%s vault-header=%s plaintext-key-lines=%s pub=%s\n' "$n" \
    "$(grep -c '^\$ANSIBLE_VAULT;1\.1;AES256$' "$f")" "$(grep -c 'PRIVATE KEY' "$f")" \
    "$(ssh-keygen -lf "$f.pub" | awk '{print $3, $4}')"
done
```

Expected, three lines: `1 vault-header=1 plaintext-key-lines=0 pub=zcrypto-valkey1 (ED25519)`, and the same for 2 and 3.

- [ ] **Step 1: The owner's six key files are in the tree**

Task 1 starts with operator step O0 done: `infra/ansible/files/` holds the three vault-encrypted private halves and the three public halves, untracked. The executor generates, decrypts and prints none of them. Step 2's ring case reads each public half's opening `ssh-ed25519 `, so a placeholder in a key's place is refused there, and Step 11 commits the six.

Run: `ls infra/ansible/files/deploy_zcrypto-valkey{1,2,3}_ed25519{,.pub} | wc -l`
Expected: `6`. A lower count means O0 has not run: stop and report it to the controller.

- [ ] **Step 2: Write the failing tests**

`tests/test_run_sh.py` — in the imports, replace the line `import pytest` with:

```python
import pytest
import yaml
```

Replace the two lines

```python
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess")
DEFAULT = [f"files/deploy_{h}_ed25519" for h in HOSTS]
```

with:

```python
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")
DEFAULT = [f"files/deploy_{h}_ed25519" for h in HOSTS]
INVENTORY = SCRIPT.parent.parent / "inventory" / "hosts.yml"
```

In `_signalled`, replace the line `    time.sleep(1.2)  # past the five key loads and into the play` with:

```python
    time.sleep(2.0)  # past the eight key loads and into the play
```

In `test_a_single_host_limit_loads_every_key_with_that_hosts_first`, replace the line `    assert added == ["files/deploy_zaccess_ed25519", *DEFAULT[:4]]` with:

```python
    assert added == ["files/deploy_zaccess_ed25519", *DEFAULT[:4], *DEFAULT[5:]]
```

After `test_a_host_without_a_key_file_keeps_the_listed_order`, insert:

```python
def test_a_cache_node_limit_offers_its_key_first(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit", "zcrypto-valkey2", "--tags", "cache"])
    assert added == ["files/deploy_zcrypto-valkey2_ed25519", *[k for k in DEFAULT if "valkey2" not in k]]


def _inventory_hosts(node: dict) -> set[str]:
    found = set((node or {}).get("hosts") or {})
    for child in ((node or {}).get("children") or {}).values():
        found |= _inventory_hosts(child)
    return found


def test_the_ring_is_every_inventory_host_but_the_workstation():
    """A host missing from the ring is offered its key only when `--limit` names it alone: a group run, or another
    host's play reaching it by `delegate_to`, meets it keyless. The private halves are checked for presence, never
    read; each public half must open `ssh-ed25519 `, so a placeholder in a key's place is refused."""
    ring = next(line for line in SCRIPT.read_text().splitlines() if line.startswith("KEYS=("))
    assert ring.removeprefix("KEYS=(").removesuffix(")").split() == DEFAULT
    children = yaml.safe_load(INVENTORY.read_text())["all"]["children"]
    assert _inventory_hosts({"children": {g: n for g, n in children.items() if g != "workstation"}}) == set(HOSTS)
    ansible = SCRIPT.parent.parent
    assert all((ansible / key).is_file() for key in DEFAULT)
    not_keys = [key for key in DEFAULT if not (ansible / f"{key}.pub").read_text().startswith("ssh-ed25519 ")]
    assert not not_keys, f"these public halves are not ed25519 public keys: {not_keys}"
```

`tests/test_converge_sh.py` — insert before the closing `]` of `PUBLISHED` (line 344, the line after the `ops_grafana_watchdog_probe_url` entry's `),`):

```python
    (
        ["--limit", "zcrypto-valkey1", "--tags", "base,hardening,firewall,fail2ban,chrony,docker", "-e", "daemon_json_ack=true"],
        "zcrypto-valkey1",
        "base,hardening,firewall,fail2ban,chrony,docker",
        {"daemon_json_ack": "true"},
    ),
    (["--limit", "zcrypto-valkey2", "--tags", "firewall,cache-link"], "zcrypto-valkey2", "firewall,cache-link", {}),
    (
        ["--limit", "zcrypto", "--tags", "firewall,cache-link", "-e", "converge_primary=true"],
        "zcrypto",
        "firewall,cache-link",
        {"converge_primary": "true"},
    ),
    (
        [
            "--limit",
            "zcrypto-valkey3",
            "--tags",
            "cache",
            "-e",
            f"cache_image_digest={DIGEST}",
            "-e",
            f"cache_alloy_digest={DIGEST}",
        ],
        "zcrypto-valkey3",
        "cache",
        {"cache_image_digest": DIGEST, "cache_alloy_digest": DIGEST},
    ),
    (
        ["--limit", "zcrypto-valkey1", "--tags", "cache", "-e", "cache_config_reset=true", "-e", f"cache_image_digest={DIGEST}"],
        "zcrypto-valkey1",
        "cache",
        {"cache_config_reset": "true", "cache_image_digest": DIGEST},
    ),
```

replace the `OUTSIDE` line `    (["--limit", "zcrypto", "--tags", "fail2ban"], "a role tag this fleet has never converged", "unknown tag"),` (line 390), whose tag this task admits, with:

```python
    (["--limit", "zcrypto", "--tags", "bootstrap"], "a tag no play in site.yml carries", "unknown tag"),
```

and insert before the closing `]` of `OUTSIDE` (line 418, after the `(["--limit"], "a flag with no value", "--limit with no value"),` line):

```python
    (["--limit", "cache_host"], "the cache group, whose nodes converge one per run", "unknown host"),
```

`tests/test_infra_converge_guards.py` — in `capture_play_tasks`, replace the line `    play = next(p for p in load_tasks(BOOTSTRAP) if p["hosts"] == "capture_host")` with:

```python
    play = next(p for p in load_tasks(BOOTSTRAP) if p["hosts"].split(":")[0] == "capture_host")
```

After `test_rebootstrap_guard_follows_the_primary_refusal_and_its_probe`, insert:

```python
def test_the_cache_nodes_bootstrap_under_the_capture_plays_guards():
    """A cache node is a public VPS like a capture host, so it takes this play's sshd drop-in and, with it, the
    re-bootstrap refusal, unnarrowed; the primary refusal stays keyed on `engine_host`, which no cache node joins."""
    plays = load_tasks(BOOTSTRAP)
    play = next(p for p in plays if p["hosts"].split(":")[0] == "capture_host")
    assert play["hosts"].split(":") == ["capture_host", "cache_host"]
    assert "when" not in find_task(play["tasks"], REBOOTSTRAP)
    primary = find_task(play["tasks"], PRIMARY_REFUSAL)
    assert when_conditions(primary) == ["inventory_hostname in groups['engine_host'] | default([])"]
    assert [p["hosts"] for p in plays if "cache_host" in p["hosts"].split(":")] == [play["hosts"]]
```

`tests/test_infra_unattended_upgrades.py` — replace the line `from pathlib import Path` with:

```python
import re
from pathlib import Path
```

After the line `VAR = "base_unattended_upgrades_automatic_reboot"`, insert:

```python
BASE_TASKS = REPO / "infra/ansible/roles/base/tasks/main.yml"
CACHE_GROUP_VARS = REPO / "infra/ansible/group_vars/cache_host/vars.yml"
HOST_VARS = REPO / "infra/ansible/host_vars"
CACHE_NODES = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
# The groups whose hosts run the base role and so hold an unattended-upgrades slot; DSM owns the NAS's.
SLOT_GROUPS = ("capture_host", "ops_host", "access_host", "cache_host")
```

Append at the end of the file:

```python
def _group_hosts(group: str) -> set[str]:
    return set(_yaml(INVENTORY)["all"]["children"][group]["hosts"])


def _slot_minutes(host: str) -> int:
    slot = _yaml(HOST_VARS / host / "vars.yml").get("base_unattended_upgrades_reboot_time")
    assert isinstance(slot, str) and re.fullmatch(r"\d{2}:\d{2}", slot), f"{host}: no quoted HH:MM slot in its host_vars ({slot!r})"
    hours, minutes = slot.split(":")
    return int(hours) * 60 + int(minutes)


def test_the_cache_group_reboots_itself():
    """The cache nodes keep the role default: a reboot of the node holding the primary is a Sentinel failover with both
    other copies up, where on a capture host it is an unbackfillable gap. Their slots keep two from rebooting together."""
    assert _group_hosts("cache_host") == CACHE_NODES
    declared = [_yaml(path).get(VAR) for path in (CACHE_GROUP_VARS, *(HOST_VARS / h / "vars.yml" for h in sorted(CACHE_NODES)))]
    assert all(value in (None, "true") for value in declared), declared


def test_the_collision_assert_reads_the_cache_group():
    """Two cache nodes down at once leave one Sentinel, below the quorum of two. The assert reads its hosts from
    `groups`, so a group absent from this expression is a group whose slots nothing compares."""
    name = "assert the fleet's maintenance windows do not collide"
    task = next(t for t in yaml.safe_load(BASE_TASKS.read_text()) if t.get("name") == name)
    expr = task["vars"]["base_fleet_hosts"]
    for group in ("capture_host", "ops_host", "cache_host"):
        assert f"groups['{group}']" in expr, f"{group} is not in the collision assert's host list: {expr}"


def test_every_reboot_slot_is_an_hour_from_every_other_and_from_a_bar_boundary():
    """The base role's assert compares slots for equality over three groups; this holds the schedule `fleet.md`'s
    Reboots section states over all four groups whose hosts run the base role, the bridgehead's included: an hour
    between any two hosts, an hour from each 4 h bar boundary, off the hour."""
    slots = {host: _slot_minutes(host) for group in SLOT_GROUPS for host in _group_hosts(group)}
    for host, at in slots.items():
        assert at % 60 != 0, f"{host}: {at // 60:02d}:00 is on the hour boundary"
        assert 60 <= at % 240 <= 180, f"{host}: {at // 60:02d}:{at % 60:02d} is within an hour of a 4 h bar boundary"
    ordered = sorted(slots.items(), key=lambda item: item[1])
    for (a, at_a), (b, at_b) in zip(ordered, ordered[1:] + ordered[:1], strict=True):
        gap = (at_b - at_a) % 1440
        assert gap >= 60, f"{a} and {b} are {gap} min apart; the fleet keeps an hour between reboot slots"
```

`tests/test_pins_converged.py` — replace the body of `test_the_inventory_expands_a_group_to_its_hosts_at_any_depth`, the two lines

```python
    groups = pins.inventory_groups(pathlib.Path(__file__).resolve().parents[1])
    assert groups["capture_host"] == {"zcrypto", "zcrypto-red"} and "nas" in groups["observed"]
```

with:

```python
    groups = pins.inventory_groups(pathlib.Path(__file__).resolve().parents[1])
    assert groups["capture_host"] == {"zcrypto", "zcrypto-red"} and "nas" in groups["observed"]
    assert groups["cache_host"] == {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
    assert groups["cache_host"] <= groups["observed"]
```

`tests/test_deploy_log_audit.py` — replace the line `@pytest.mark.parametrize("host", ["nas", "zaccess"])` with:

```python
@pytest.mark.parametrize("host", ["nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"])
```

`tests/test_ops_daily.py` — in `test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys`, replace the two lines

```python
    rows = dict(re.findall(r"^\| `([^`]+)` \| `ssh ([a-z-]+)` \|", table, re.M))
    assert set(rows) == {"zcrypto", "zcrypto-red", "zcrypto-ops", "nas"}, rows
```

with:

```python
    rows = dict(re.findall(r"^\| `([^`]+)` \| `ssh ([a-z0-9-]+)` \|", table, re.M))
    nodes = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
    assert set(rows) == {"zcrypto", "zcrypto-red", "zcrypto-ops", "nas"} | nodes, rows
```

and insert after that test (after its last line, `    assert any(line.strip().startswith('host = "ops"') for line in alloy.splitlines())`):

```python
@pytest.mark.parametrize("host", ["zcrypto-valkey1", "db1"])
def test_a_cache_node_is_a_telemetry_host_under_either_of_its_names(host):
    """A step names a cache node by its Alloy `host` label or by its ssh alias; neither spelling may lose the tier."""
    step = "sudo docker restart grafana-alloy"
    assert ops_daily.classify_action(step, host=host, resolve=_identity) is ops_daily.Tier.AUTONOMOUS
    assert ops_daily.classify_action(f"ssh db1 {step}", host=None, resolve=_identity) is ops_daily.Tier.AUTONOMOUS
```

- [ ] **Step 3: Run the new and re-pinned cases and watch them fail**

```bash
uv run pytest tests/test_run_sh.py::test_no_limit_loads_every_fleet_key_in_the_listed_order tests/test_run_sh.py::test_a_single_host_limit_loads_every_key_with_that_hosts_first tests/test_run_sh.py::test_a_cache_node_limit_offers_its_key_first tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation tests/test_converge_sh.py::test_every_invocation_this_fleet_publishes_records_its_operands tests/test_converge_sh.py::test_every_spelling_outside_the_grammar_is_refused_before_anything_runs tests/test_infra_converge_guards.py::test_rebootstrap_refusal tests/test_infra_converge_guards.py::test_the_cache_nodes_bootstrap_under_the_capture_plays_guards tests/test_infra_unattended_upgrades.py tests/test_pins_converged.py::test_the_inventory_expands_a_group_to_its_hosts_at_any_depth tests/test_deploy_log_audit.py::test_venue_facing_drops_a_host_a_window_cannot_harm tests/test_ops_daily.py::test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys tests/test_ops_daily.py::test_a_cache_node_is_a_telemetry_host_under_either_of_its_names -q -p no:cacheprovider
```

Expected failures, each for its own reason: the three `run.sh` ordering cases (the ring still holds five keys, so `added` lacks the three cache keys) and the ring case (`KEYS=` differs from `DEFAULT`, and the inventory has no cache hosts); the five new `PUBLISHED` entries (`unknown host: zcrypto-valkey1` and its siblings on the four node entries, `unknown tag: firewall` on the engine host's); `test_rebootstrap_refusal` passes and `test_the_cache_nodes_bootstrap_under_the_capture_plays_guards` fails (`['capture_host'] != ['capture_host', 'cache_host']`); in `tests/test_infra_unattended_upgrades.py` the cache-group case (`KeyError: 'cache_host'`), the collision-assert case (`cache_host is not in the collision assert's host list`) and the slot case (`KeyError: 'cache_host'`) fail while the file's existing cases pass; the pins case (`KeyError: 'cache_host'`); the three new `--venue-facing` parametrisations (`rows inside an API-impacting window 0 of 1 venue-facing` expected, `1 of 2 venue-facing` printed, since nothing drops the node's row); the aliases case (the fleet table has no `ssh db1` rows); both telemetry parametrisations (`Tier.PREPARED`). The `OUTSIDE` entries for `cache_host` and `bootstrap` pass already, since the script refuses every name outside its sets; they pin those refusals from here on.

- [ ] **Step 4: Membership: the inventory, the group and host vars, the bootstrap play and the base assert**

`infra/ansible/inventory/hosts.yml` — replace the five lines

```yaml
      children:
        capture_host: {}
        ops_host: {}
        nas_host: {}
        access_host: {}
```

with:

```yaml
      children:
        capture_host: {}
        ops_host: {}
        nas_host: {}
        access_host: {}
        cache_host: {}
```

and replace the three lines

```yaml
    access_host:
      hosts:
        zaccess: {}
```

with:

```yaml
    access_host:
      hosts:
        zaccess: {}
    # The engine's cache (spec 00118): Valkey, Sentinel and Alloy on three dedicated nodes, converged
    # one node per run. NEVER engine_host/capture_host — no trade key, no capture data.
    cache_host:
      hosts:
        zcrypto-valkey1: {}
        zcrypto-valkey2: {}
        zcrypto-valkey3: {}
```

Create `infra/ansible/group_vars/cache_host/vars.yml`:

```yaml
# bootstrap.yml's capture play connects as root on 22 at play scope, since a new node has no
# zcrypto-deploy yet; every converge after it connects as below.
ansible_user: zcrypto-deploy
ansible_port: 10022
# ssh_hardening AllowUsers: no zcrypto-data here, since no NAS pull channel reaches these nodes.
hardening_ssh_allow_users: zcrypto-deploy root
```

Create `infra/ansible/host_vars/zcrypto-valkey1/vars.yml`:

```yaml
# A cache node: Linode 1 GB, Debian 13, in the engine host's region.
ansible_host: zcrypto-valkey1.zhaow.me
# The base role defaults to "zcrypto"; without this the node would converge to the primary's hostname.
base_hostname: zcrypto-valkey1
# Fleet reboot slots: 21:25 zcrypto, 22:25 zcrypto-red, 02:25 ops, 05:25 zaccess; the cache nodes take
# 09:25, 13:25 and 17:25, each 85 min past a 4 h bar boundary and 4 h from the next, so two nodes'
# automatic reboots do not overlap. The base role's collision assert reads this out of hostvars;
# tests/test_infra_unattended_upgrades.py holds the seven an hour apart.
base_unattended_upgrades_reboot_time: "09:25"
deploy_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/deploy_zcrypto-valkey1_ed25519.pub') }}"
```

Create `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`:

```yaml
# A cache node: Linode 1 GB, Debian 13, in the engine host's region.
ansible_host: zcrypto-valkey2.zhaow.me
# The base role defaults to "zcrypto"; without this the node would converge to the primary's hostname.
base_hostname: zcrypto-valkey2
# The slot's derivation is in host_vars/zcrypto-valkey1/vars.yml.
base_unattended_upgrades_reboot_time: "13:25"
deploy_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/deploy_zcrypto-valkey2_ed25519.pub') }}"
```

Create `infra/ansible/host_vars/zcrypto-valkey3/vars.yml`:

```yaml
# A cache node: Linode 1 GB, Debian 13, in a region apart from the engine host's.
ansible_host: zcrypto-valkey3.zhaow.me
# The base role defaults to "zcrypto"; without this the node would converge to the primary's hostname.
base_hostname: zcrypto-valkey3
# The slot's derivation is in host_vars/zcrypto-valkey1/vars.yml.
base_unattended_upgrades_reboot_time: "17:25"
deploy_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/deploy_zcrypto-valkey3_ed25519.pub') }}"
```

`infra/ansible/host_vars/zaccess/vars.yml` — replace the four lines

```yaml
# Fleet reboot slots: 21:25 zcrypto, 22:25 zcrypto-red, 02:25 ops. 05:25 is >=1 h from every
# other slot, off the hour boundary, >=1 h from the 4-hourly engine boundaries (04:00/08:00).
# The base role's collision assert covers capture_host + ops_host only, so this host's slot is NOT
# machine-checked — this list is the guard.
```

with:

```yaml
# Fleet reboot slots: 21:25 zcrypto, 22:25 zcrypto-red, 02:25 ops, 09:25/13:25/17:25 the cache
# nodes. 05:25 is >=1 h from every other slot, off the hour boundary, >=1 h from the 4-hourly
# engine boundaries (04:00/08:00). The base role's collision assert covers capture_host, ops_host
# and cache_host, not this host; tests/test_infra_unattended_upgrades.py holds this slot against theirs.
```

`infra/ansible/bootstrap.yml` — replace the two lines

```yaml
- name: Bootstrap capture host — deploy user + SSH lockdown (keep 22 until converge proves 10022)
  hosts: capture_host
```

with:

```yaml
# A cache node is a public VPS like a capture host: it takes this play's sshd drop-in and both refusals.
- name: Bootstrap capture and cache hosts — deploy user + SSH lockdown (keep 22 until converge proves 10022)
  hosts: capture_host:cache_host
```

and replace the four comment lines

```yaml
    # Generalises the refusal above to the SECONDARY: bootstrap is first-provision only, re-running
    # it rewrites the sshd drop-in below, and the deploy user is the evidence that provisioning
    # already happened. Capture play only, deliberately -- the ops and access plays are LAN-side and
    # write no drop-in, so the refusal's own message would be false there.
```

with:

```yaml
    # Generalises the refusal above to the SECONDARY and the cache nodes: bootstrap is first-provision
    # only, re-running it rewrites the sshd drop-in below, and the deploy user is the evidence that
    # provisioning already happened. This play only, deliberately -- the ops and access plays write
    # no drop-in, so the refusal's own message would be false there.
```

`infra/ansible/roles/base/tasks/main.yml` — replace the first four header lines

```yaml
# Fleet policy, pinned in config (spec 00050, spec 00051, .claude/rules/fleet-deploys.md): no two
# hosts in the capture and ops fleet may share an unattended-upgrades slot, because a same-night
# kernel reboot would take several down at once and a book gap with no surviving witness is
# permanent. The slots come from `hostvars`, which resolves inventory, group and host vars but NOT
```

with:

```yaml
# Fleet policy, pinned in config (spec 00050, spec 00051, spec 00118,
# .claude/rules/fleet-deploys.md): no two hosts in the capture, ops and cache fleet may share an
# unattended-upgrades slot, because a same-night kernel reboot would take several down at once: a
# book gap with no surviving witness is permanent, and two cache nodes down leave one Sentinel,
# below its quorum of two. The slots come from `hostvars`, which resolves inventory, group and host vars but NOT
```

and replace the line

```yaml
    base_fleet_hosts: "{{ (groups['capture_host'] | default([])) + (groups['ops_host'] | default([])) }}"
```

with:

```yaml
    base_fleet_hosts: "{{ (groups['capture_host'] | default([])) + (groups['ops_host'] | default([])) + (groups['cache_host'] | default([])) }}"
```

Run: `(cd infra/ansible && uv run ansible-inventory --graph cache_host)` — `--graph` is the vault-safe form CLAUDE.md names; `--host`, `--list` and `--vars` are never run.
Expected:

```
@cache_host:
  |--zcrypto-valkey1
  |--zcrypto-valkey2
  |--zcrypto-valkey3
```

- [ ] **Step 5: The key ring, the converge whitelist and the key inventory**

`infra/ansible/scripts/run.sh` — replace the two comment lines

```bash
# A group, a comma list or no --limit keeps the listed order, the bridgehead's key fifth: it converges under
# its own --limit only.
```

with:

```bash
# A group, a comma list or no --limit keeps the listed order, the bridgehead's key fifth and the cache nodes'
# sixth to eighth: each of those converges under its own --limit only.
```

and replace the line

```bash
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519)
```

with:

```bash
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519 files/deploy_zcrypto-valkey1_ed25519 files/deploy_zcrypto-valkey2_ed25519 files/deploy_zcrypto-valkey3_ed25519)
```

`infra/ansible/scripts/converge.sh` — replace the fourteen lines from `# The four the deploy log records, plus \`zaccess\`:` through `docker_apt_distribution access_ops_agentboard_live"`, which read today:

```bash
# The four the deploy log records, plus `zaccess`: `infra/runbooks/zaccess.md` publishes its only
# converge, `--limit zaccess --tags access`.
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess"
# The five converged, plus `chrony`: `infra/runbooks/capture.md` prescribes re-converging that role
# as the repair for a stopped or hand-edited chrony on a capture host.
TAGNAMES="capture engine ops nas access chrony"
# The keys converges have carried, minus `nas_capture_image_digest` -- no role reads it, so the one
# row that passed it re-pinned nothing -- plus the ones a live page publishes as an `-e`:
# `daemon_json_ack` and `ops_panel_timer_hold` (the rollout skill), `ops_reconcile_mint` (the ops
# host_vars), `docker_apt_distribution` and `access_ops_agentboard_live` (their role defaults).
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live"
```

with:

```bash
# The four the deploy log records, plus `zaccess`: `infra/runbooks/zaccess.md` publishes its only
# converge, `--limit zaccess --tags access`; plus the three cache nodes, whose rollout (spec 00118
# D14) converges one node per run, so `cache_host` is not a host here.
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3"
# The five converged, plus `chrony`: `infra/runbooks/capture.md` prescribes re-converging that role
# as the repair for a stopped or hand-edited chrony on a capture host; plus spec 00118's: a cache
# node's first converge names the six base roles (`--tags base,hardening,firewall,fail2ban,chrony,docker`),
# the mesh converge `firewall,cache-link` on a node or the engine host, and `cache` Valkey, Sentinel
# and Alloy on a node.
TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link"
# The keys converges have carried, minus `nas_capture_image_digest` -- no role reads it, so the one
# row that passed it re-pinned nothing -- plus the ones a live page publishes as an `-e`:
# `daemon_json_ack` and `ops_panel_timer_hold` (the rollout skill), `ops_reconcile_mint` (the ops
# host_vars), `docker_apt_distribution` and `access_ops_agentboard_live` (their role defaults); plus
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9).
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset"
```

`infra/ansible/files/README.md` — after the row that begins `| \`deploy_zaccess_ed25519{,.pub}\` |`, insert:

```markdown
| `deploy_zcrypto-valkey1_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-valkey1`; the workstation's `db1` alias |
| `deploy_zcrypto-valkey2_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-valkey2`; the workstation's `db2` alias |
| `deploy_zcrypto-valkey3_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-valkey3`; the workstation's `db3` alias |
```

- [ ] **Step 6: The two instruments' host sets**

`infra/scripts/deploy-log-audit.py` — replace the line `NO_VENUE_EXPOSURE = frozenset({"nas", "zaccess"})` with:

```python
NO_VENUE_EXPOSURE = frozenset({"nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
```

`infra/scripts/ops_daily.py` — replace the four lines

```python
# The ops host has three names -- the `host` label its rules carry, the fleet name its check rows
# print and the ssh destination -- and `zcrypto-red` two; `zaccess` has no bare-name destination.
_SSH_ALIASES = {"ops": "hp", "zcrypto-red": "red"}
_HOST_LABELS = {"hp": "ops", "zcrypto-ops": "ops", "red": "zcrypto-red"}
```

with:

```python
# The ops host has three names -- the `host` label its rules carry, the fleet name its check rows
# print and the ssh destination -- and `zcrypto-red` and each cache node two; `zaccess` has no
# bare-name destination.
_SSH_ALIASES = {"ops": "hp", "zcrypto-red": "red", "zcrypto-valkey1": "db1", "zcrypto-valkey2": "db2", "zcrypto-valkey3": "db3"}
_HOST_LABELS = {
    "hp": "ops",
    "zcrypto-ops": "ops",
    "red": "zcrypto-red",
    "db1": "zcrypto-valkey1",
    "db2": "zcrypto-valkey2",
    "db3": "zcrypto-valkey3",
}
```

and replace the line `_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess"})` with:

```python
_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
```

- [ ] **Step 7: The fleet page**

`docs/reference/fleet.md` is a contract page: `tests/test_fleet_contracts.py` caps a cell at 200 characters and a bullet at 700 and refuses a date, and the commit-msg `guidance-guard` refuses a universal word (every, never, always, only, any, cannot) outside code spans in a bullet with no count entry. The texts below carry none, and their longest cell is 135 characters.

After the `zaccess` row of the Hosts table (the row beginning `| \`zaccess\` | \`ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me\` |`) and before the `workstation` row, insert:

```markdown
| `zcrypto-valkey1` | `ssh db1` | `cache_host`, `observed` | the engine's cache (spec `00118`): Valkey and its Sentinel, in the engine host's region | Linode VPS, 1 GB; no trade key, no capture data; Valkey and Sentinel listen on loopback and `zcache0` alone |
| `zcrypto-valkey2` | `ssh db2` | `cache_host`, `observed` | the engine's cache (spec `00118`): Valkey and its Sentinel, in the engine host's region | Linode VPS, 1 GB; no trade key, no capture data; Valkey and Sentinel listen on loopback and `zcache0` alone |
| `zcrypto-valkey3` | `ssh db3` | `cache_host`, `observed` | the engine's cache (spec `00118`): Valkey and its Sentinel, in a region apart from the engine host's, the copy a regional outage leaves | Linode VPS, 1 GB; no trade key, no capture data; Valkey and Sentinel listen on loopback and `zcache0` alone |
```

In the Reboots section, after the bullet that begins `- The capture VPSes never reboot themselves:` and before the bullet `- Reboot the secondary first, then the primary`, insert:

```markdown
- The cache nodes reboot themselves at 09:25, 13:25 and 17:25, one node per slot, so a reboot of the node holding the primary fails over with both other copies up; the base role's window-collision assert reads their slots beside the capture and ops ones, and `tests/test_infra_unattended_upgrades.py` holds all seven slots, the bridgehead's 05:25 among them, an hour apart and an hour from each 4 h bar boundary.
```

In the Telemetry labels section, replace the bullet

```markdown
- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red}`.
```

with:

```markdown
- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red, zcrypto-valkey1, zcrypto-valkey2, zcrypto-valkey3}`.
```

and in the bullet that begins `- Prometheus carries the same four \`host\` values`, replace `the same four` with `the same seven`; the rest of that bullet is unchanged.

- [ ] **Step 8: Run the cases**

```bash
uv run pytest tests/test_run_sh.py::test_no_limit_loads_every_fleet_key_in_the_listed_order tests/test_run_sh.py::test_a_single_host_limit_loads_every_key_with_that_hosts_first tests/test_run_sh.py::test_a_cache_node_limit_offers_its_key_first tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation tests/test_converge_sh.py::test_every_invocation_this_fleet_publishes_records_its_operands tests/test_converge_sh.py::test_every_spelling_outside_the_grammar_is_refused_before_anything_runs tests/test_infra_converge_guards.py::test_rebootstrap_refusal tests/test_infra_converge_guards.py::test_the_cache_nodes_bootstrap_under_the_capture_plays_guards tests/test_infra_unattended_upgrades.py tests/test_pins_converged.py::test_the_inventory_expands_a_group_to_its_hosts_at_any_depth tests/test_deploy_log_audit.py::test_venue_facing_drops_a_host_a_window_cannot_harm tests/test_ops_daily.py::test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys tests/test_ops_daily.py::test_a_cache_node_is_a_telemetry_host_under_either_of_its_names -q -p no:cacheprovider
```

Expected: every case passed, none failed or skipped; the count is the collected total pytest prints.

- [ ] **Step 9: The consumers**

The changed files' test consumers, the whole of `grep -rlE 'run\.sh|converge\.sh|bootstrap\.yml|hosts\.yml|group_vars|host_vars|roles/base|deploy-log-audit|ops_daily|fleet\.md|pins-converged|ansible/files' tests/test_*.py`, with `tests/test_internal_terms_not_operator_visible.py` and `tests/test_prune_host_images.py` beside them:

```bash
uv run pytest tests/test_run_sh.py tests/test_converge_sh.py tests/test_deploy_log.py tests/test_infra_converge_guards.py tests/test_infra_unattended_upgrades.py tests/test_infra_firewall_template.py tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py tests/test_pins_converged.py tests/test_deploy_log_audit.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_engine_soak.py tests/test_fleet_contracts.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_merge_gate.py tests/test_engine_flatten.py tests/test_grafana_auth.py tests/test_mint_with_vaulted_key_sh.py tests/test_probe_with_vaulted_key_sh.py tests/test_internal_terms_not_operator_visible.py tests/test_prune_host_images.py -q -p no:cacheprovider
```

Expected: no failure. `tests/test_prune_host_images.py` is in the run because it reads the fleet's host set against the pins file and must stay green with `HOSTS` unedited; `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` must pass over the three new `host_vars` directories and `group_vars/cache_host`. The full suite is CI's, on the pull request.

- [ ] **Step 10: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite (ruff may reflow a long tuple in `tests/test_converge_sh.py` or the `_SSH_ALIASES` line, `end-of-file-fixer` may touch a generated `.pub`) until clean, then stage what it rewrote. The commit-msg hooks (`guidance-guard` over `docs/reference/fleet.md`, `message-citations`, `staged-kind`) run at Step 11.

- [ ] **Step 11: Commit**

```bash
git add infra/ansible/files/deploy_zcrypto-valkey1_ed25519 infra/ansible/files/deploy_zcrypto-valkey1_ed25519.pub \
  infra/ansible/files/deploy_zcrypto-valkey2_ed25519 infra/ansible/files/deploy_zcrypto-valkey2_ed25519.pub \
  infra/ansible/files/deploy_zcrypto-valkey3_ed25519 infra/ansible/files/deploy_zcrypto-valkey3_ed25519.pub \
  infra/ansible/files/README.md infra/ansible/inventory/hosts.yml infra/ansible/group_vars/cache_host/vars.yml \
  infra/ansible/host_vars/zcrypto-valkey1/vars.yml infra/ansible/host_vars/zcrypto-valkey2/vars.yml \
  infra/ansible/host_vars/zcrypto-valkey3/vars.yml infra/ansible/host_vars/zaccess/vars.yml infra/ansible/bootstrap.yml \
  infra/ansible/roles/base/tasks/main.yml infra/ansible/scripts/run.sh infra/ansible/scripts/converge.sh \
  infra/scripts/deploy-log-audit.py infra/scripts/ops_daily.py docs/reference/fleet.md \
  tests/test_run_sh.py tests/test_converge_sh.py tests/test_infra_converge_guards.py tests/test_infra_unattended_upgrades.py \
  tests/test_pins_converged.py tests/test_deploy_log_audit.py tests/test_ops_daily.py
git commit -F- <<'MSG'
feat(fleet): the three cache nodes join the inventory, the deploy-key ring and the hand-kept host lists

`zcrypto-valkey1`, `zcrypto-valkey2` and `zcrypto-valkey3` form the `cache_host` group, a child of
`observed`, converged as `zcrypto-deploy` on 10022 with `AllowUsers` naming no `zcrypto-data`. Each
has a plaintext `ansible_host`, its hostname, its own deploy key and a reboot slot of its own, 09:25,
13:25 and 17:25: 85 minutes past a 4 h bar boundary, four hours from each other and at least three
from the fleet's other four, with the role default's automatic reboot kept, since a node's reboot
is a Sentinel failover the set absorbs and two nodes down would leave one Sentinel below quorum.
Three ed25519 deploy keypairs are added under `infra/ansible/files/`, the private halves
vault-encrypted, listed in its README and in `run.sh`'s ring after the bridgehead's. The capture
play of `bootstrap.yml` widens to `capture_host:cache_host` with both refusals unchanged, and the
base role's window-collision assert reads the cache group beside the capture and ops groups.

The hand-kept lists gain the three: `converge.sh`'s hosts; the tags a node's first converge names,
`base`, `hardening`, `firewall`, `fail2ban`, `chrony` and `docker`, and `cache` and `cache-link`;
and the keys `cache_image_digest`, `cache_alloy_digest` and `cache_config_reset`; the deploy-log audit's
`NO_VENUE_EXPOSURE`; the daily pass's telemetry hosts with their aliases `db1` to `db3` in both
alias maps, since a step's `ssh db1` reaches the telemetry set only through `host_label`. The fleet
page carries their Hosts rows, their reboot slots and their telemetry `host` labels.
`prune-host-images.py` gains them with their first pins rows: its pins test holds its host set equal
to the hosts the pins file names.

Cases: the ring against the inventory and the key files on disk, each public half an ed25519 key;
a cache node's `--limit` offering its key first; five cache converges recorded (a node's first under the six base tags
with the docker role's ack, `firewall,cache-link` on a node and on the engine host, `cache` with both digests, `cache`
with the config reset and its digest), `cache_host` refused as a limit and `bootstrap` as a tag; the bootstrap play's hosts and its two guards; the collision assert's three groups; the
seven slots an hour apart, off the hour and an hour from a bar boundary, the bridgehead's checked
for the first time; the cache group's automatic reboot; the cache group under `observed`; the three
nodes dropped by `--venue-facing`; a cache node's telemetry tier under either name.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC
MSG
```

The executor writes its own model name in place of `<model>` (`Claude Fable 5.1`, `Claude Opus 5.5`, ...), here and in the amend of Step 13.

- [ ] **Step 12: The tree is clean**

Run: `git status --porcelain`
Expected: empty. A plaintext private half left behind would show here as untracked; there is none, because operator step O0 encrypted all three in place.

- [ ] **Step 13: Prove the guards with seventeen probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time, never beside a pytest run in the same checkout. The controls: `run.sh`'s limit-first reorder emptied, which fails every single-host case; valkey2's public half turned into another key type; a capture host renamed in the inventory, which fails the ring case; the refusal word `host` changed in `converge.sh`, which fails every `unknown host` case; the re-bootstrap assert inverted; the ops group's name changed in the collision assert; valkey2's slot line deleted; a YAML boolean written as the cache group's reboot flag; the `--venue-facing` filter disabled; the telemetry gate disabled. The mutations remove each thing this task added, one at a time, one writes a placeholder over valkey2's public half, and three move valkey2's slot onto each arm of the slot case separately (40 min from valkey1's, 30 min past a bar boundary, on the hour):

```bash
RING="tests/test_run_sh.py::test_no_limit_loads_every_fleet_key_in_the_listed_order tests/test_run_sh.py::test_a_single_host_limit_loads_every_key_with_that_hosts_first tests/test_run_sh.py::test_a_cache_node_limit_offers_its_key_first tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation"
INV="tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation tests/test_pins_converged.py::test_the_inventory_expands_a_group_to_its_hosts_at_any_depth tests/test_infra_unattended_upgrades.py::test_the_cache_group_reboots_itself"
CONV="tests/test_converge_sh.py::test_every_invocation_this_fleet_publishes_records_its_operands tests/test_converge_sh.py::test_every_spelling_outside_the_grammar_is_refused_before_anything_runs"
BOOT="tests/test_infra_converge_guards.py::test_rebootstrap_refusal tests/test_infra_converge_guards.py::test_rebootstrap_guard_follows_the_primary_refusal_and_its_probe tests/test_infra_converge_guards.py::test_the_cache_nodes_bootstrap_under_the_capture_plays_guards"
SLOT="tests/test_infra_unattended_upgrades.py::test_every_reboot_slot_is_an_hour_from_every_other_and_from_a_bar_boundary"
OPS="tests/test_ops_daily.py::test_a_cache_node_is_a_telemetry_host_under_either_of_its_names tests/test_ops_daily.py::test_the_ops_host_answers_both_kinds_of_step_under_either_of_its_names tests/test_ops_daily.py::test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys"
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/run.sh \
  --control 's/^  ordered=("files\/deploy_\${LIMIT}_ed25519")$/  ordered=()/' \
  --mutation 's/ files\/deploy_zcrypto-valkey3_ed25519)$/)/' \
  -- uv run pytest $RING -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/files/deploy_zcrypto-valkey2_ed25519.pub \
  --control 's/^ssh-ed25519 /ssh-rsa /' \
  --mutation 's/^.*$/PLACEHOLDER: not a key/' \
  -- uv run pytest tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/inventory/hosts.yml \
  --control 's/^        zcrypto-red: {}$/        zcrypto-rot: {}/' \
  --mutation '/^        cache_host: {}$/d' \
  -- uv run pytest $INV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/inventory/hosts.yml \
  --control 's/^        zcrypto-red: {}$/        zcrypto-rot: {}/' \
  --mutation '/^        zcrypto-valkey3: {}$/d' \
  -- uv run pytest $INV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/ zcrypto-valkey2 / /' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/^TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link"$/TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache"/' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/^cache_config_reset"$/"/' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/bootstrap.yml \
  --control 's/that: bootstrap_deploy_user_probe.rc != 0 or rebootstrap/that: bootstrap_deploy_user_probe.rc == 0 or rebootstrap/' \
  --mutation 's/^  hosts: capture_host:cache_host$/  hosts: capture_host/' \
  -- uv run pytest $BOOT -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/base/tasks/main.yml \
  --control 's/ops_host/ops_hosts/' \
  --mutation 's/ + (groups\[.cache_host.\] | default(\[\]))//' \
  -- uv run pytest tests/test_infra_unattended_upgrades.py::test_the_collision_assert_reads_the_cache_group -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-valkey2/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/"13:25"/"10:05"/' \
  -- uv run pytest $SLOT -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-valkey2/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/"13:25"/"12:30"/' \
  -- uv run pytest $SLOT -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-valkey2/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/"13:25"/"14:00"/' \
  -- uv run pytest $SLOT -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/group_vars/cache_host/vars.yml \
  --control '$a base_unattended_upgrades_automatic_reboot: yes' \
  --mutation '$a base_unattended_upgrades_automatic_reboot: "false"' \
  -- uv run pytest tests/test_infra_unattended_upgrades.py::test_the_cache_group_reboots_itself -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/deploy-log-audit.py \
  --control 's/if not (venue_facing_only and row.get("limit", "") in NO_VENUE_EXPOSURE)/if True/' \
  --mutation 's/, "zcrypto-valkey3"})/})/' \
  -- uv run pytest tests/test_deploy_log_audit.py::test_venue_facing_drops_a_host_a_window_cannot_harm -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation 's/"zaccess", "zcrypto-valkey1", /"zaccess", /' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation '/^    "db1": "zcrypto-valkey1",$/d' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation 's/, "zcrypto-valkey1": "db1"//' \
  -- uv run pytest $OPS -q -p no:cacheprovider
```

The `$RING`-style variables are left unquoted on purpose: each holds several node ids that must reach pytest as separate words. Expected: each of the seventeen runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. If ruff's Step 10 rewrite changed the shape of `_SSH_ALIASES` or `_HOST_LABELS`, the last two mutation expressions are re-anchored on the committed text before running, since a sed that matches nothing is refused as a no-op (rc 6), never scored. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 11 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, seventeen runs, each KILLED with its control proven.
`infra/ansible/scripts/run.sh`, control the limit-first reorder emptied, over the three ordering
cases and the ring case: the last cache key dropped from the ring, KILLED, control proven.
`infra/ansible/files/deploy_zcrypto-valkey2_ed25519.pub`, control its key type changed, over the
ring case: a placeholder written in the key's place, KILLED, control proven.
`infra/ansible/inventory/hosts.yml`, control a capture host renamed, over the ring, pins-inventory
and cache-group cases: `cache_host` removed from `observed`, KILLED, control proven; valkey3
removed from `cache_host`, KILLED, control proven. `infra/ansible/scripts/converge.sh`, control the
unknown-host refusal reworded, over the published and outside-the-grammar cases: valkey2 dropped
from the hosts, KILLED, control proven; `cache-link` dropped from the tags, KILLED, control proven;
`cache_config_reset` dropped from the keys, KILLED, control proven. `infra/ansible/bootstrap.yml`,
control the re-bootstrap assert inverted: the play narrowed back to `capture_host`, KILLED, control
proven. `infra/ansible/roles/base/tasks/main.yml`, control the ops group renamed: the cache group
dropped from the collision assert, KILLED, control proven. valkey2's `host_vars`, control its slot
deleted: the slot 40 min from valkey1's, KILLED, control proven; 30 min past a bar boundary,
KILLED, control proven; on the hour, KILLED, control proven. `group_vars/cache_host`, control a
YAML boolean reboot flag: the attended flip, KILLED, control proven.
`infra/scripts/deploy-log-audit.py`, control the venue-facing filter disabled: valkey3 dropped from
`NO_VENUE_EXPOSURE`, KILLED, control proven. `infra/scripts/ops_daily.py`, control the telemetry
gate disabled: valkey1 dropped from the telemetry hosts, KILLED, control proven; `db1` dropped from
the label map, KILLED, control proven; valkey1 dropped from the alias map, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

**Operator steps (attended)**

These are the workstation-side items `## Rollout (attended)` calls on, in its order: O0, above Step 1, at P1; O1 at R1, O2 to O4 at R2. The host-reaching steps, the bootstrap, a node's first converge and the removal of port 22, are R2's, run from merged `develop`, and R9 commits the deploy-log rows they append. `W$` is the workstation, `H$` a node's own shell (Linode LISH).

O1. Linode Cloud Firewall, by hand in the Cloud Manager (Firewalls → Create Firewall, or edit the one attached if a node already carries one): label `zcrypto-cache`; inbound policy Drop, outbound policy Accept; inbound rules Accept TCP `22` (IPv4 and IPv6, all sources), Accept TCP `10022` (IPv4 and IPv6, all sources), Accept ICMP (IPv4 and IPv6); attach `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`. This is the provider layer of the two-layer rule; the host layer is the firewall role's nftables (`10022/tcp` and ICMP by default), which the node receives at its first converge in R2. `51821/udp` opens in nftables at that same first converge, from the vars Task 2 commits, and in the Cloud Firewall by Task 3's operator step O2, at R3.

```
W$ for h in zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3; do for p in 22 10022; do timeout 5 bash -c "</dev/tcp/$h.zhaow.me/$p" 2>/dev/null && echo "$h $p open" || echo "$h $p closed"; done; done
```

Expected: `22 open` and `10022 closed` on each node (nothing listens on 10022 before the bootstrap).

O2. Each node's host key, read out of band once, so the first ssh prompt is checked rather than trusted: `H$ ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` in each node's LISH console; the fingerprint the first `ssh dbN` in R2 prints must be the one read here.

O3. The workstation's copies of the three deploy keys, written to files, never printed:

```
W$ (cd infra/ansible && umask 077 && for n in 1 2 3; do uv run ansible-vault view "files/deploy_zcrypto-valkey${n}_ed25519" > "$HOME/.ssh/deploy_zcrypto-valkey${n}_ed25519"; done)
```

O4. The aliases in `~/.ssh/config`, one stanza per node, on the shape of the existing `red` stanza, which the operator compares against (this plan does not read that file). `IdentitiesOnly yes` is load-bearing: the hardened sshd allows two authentication tries, and an agent offering other keys first exhausts them.

```
Host db1
    HostName zcrypto-valkey1.zhaow.me
    Port 10022
    User zcrypto-deploy
    IdentityFile ~/.ssh/deploy_zcrypto-valkey1_ed25519
    IdentitiesOnly yes

Host db2
    HostName zcrypto-valkey2.zhaow.me
    Port 10022
    User zcrypto-deploy
    IdentityFile ~/.ssh/deploy_zcrypto-valkey2_ed25519
    IdentitiesOnly yes

Host db3
    HostName zcrypto-valkey3.zhaow.me
    Port 10022
    User zcrypto-deploy
    IdentityFile ~/.ssh/deploy_zcrypto-valkey3_ed25519
    IdentitiesOnly yes
```

---

### Task 2: The firewall accepts ports on a named interface, and the mesh's ports open

*Rulings: R4 placed the cache group's interface-scoped ports and both `51821/udp` declarations here, with the firewall-template test widened; R7 made the Task 3 probe the plan's one handshake-age probe (the decisions below say so); R18 kept the Cloud Firewall rule in Task 3's operator block.*

What Tasks 2 and 3 decide, where the spec leaves it open:

- The engine host's `firewall_extra_udp_ports: [51821]` goes in `infra/ansible/host_vars/zcrypto/vars.yml`. `group_vars/engine_host/` holds only `vault.yml` today, and the host_vars file is already the one plaintext var file that is zcrypto's alone; `zcrypto` runs the firewall role from the capture play, and both files reach it.
- The peer list is the whole four-member mesh in `roles/cache_link/defaults/main.yml`, this host included; the conf renders every member but the one named `inventory_hostname`, and the probe reads its peers from the rendered conf. Each member's `cache_link_address` and `cache_link_private_key` live in its own host_vars, the key wired from a vault var by name (`cache_link_private_key: "{{ cache_wg_zcrypto_valkey1_private_key }}"`), the fleet's wiring idiom (`host_vars/zcrypto-ops/vars.yml` wires its healthcheck URLs the same way). A hostname's hyphen is not legal in a variable name, so the vault keys are `cache_wg_zcrypto_private_key`, `cache_wg_zcrypto_valkey1_private_key`, `cache_wg_zcrypto_valkey2_private_key`, `cache_wg_zcrypto_valkey3_private_key`, and the public halves are the same names ending `_public_key`.
- Endpoints are IPv4 literals (the spec's measured addresses), not names: each `zcrypto-valkeyN.zhaow.me` also carries an AAAA record, and the Cloud Firewall rules are written per IPv4 address.
- The mesh runs MTU 1380, the fleet's one tunnel MTU after #606 (zaccess moved to 1380 because its IPv4 path from the ops LAN carries 1460 bytes whole). No path of this mesh has been measured and valkey3's crosses regions; 1380 fits any path of 1440 bytes or more (WireGuard adds 60 over IPv4) and costs 40 bytes a packet against wg-quick's default 1420 on a cache's small messages. A case holds the mesh's MTU equal to the zaccess tunnel's.
- No PresharedKey: spec D5 names four keypairs and nothing else.
- The guard is the role's first task and refuses what would make a peer's AllowedIPs wider than one host (the template appends `/32` to every address, so the address must be a bare host address inside `cache_link_network`) and what would render this host as its own peer (a second entry with its name, address or public key, or no entry at its own address). It also refuses a member missing its address or a 44-character private key, because the conf task is `no_log` and would hide which variable was undefined.
- The handler and the two `systemd` enable tasks skip exactly the first-run dry run (`when: not (ansible_check_mode and <install> is changed)`, the engine role's shape), not every check run: `converge.sh` previews in check mode before the real pass, and on a host that has never had `wireguard-tools` the `systemd` module fails with "Could not find the requested service" even in check mode, which aborts the converge.
- The probe is the plan's one handshake-age probe (ruling R7), on all four members, and writes `/var/lib/zcrypto-node-textfile/zcache.prom`: on `zcrypto` the capture role's Alloy reads that directory (`capture_textfile_dir`, and the engine role's `engine_textfile_dir` names the same path), so one path on all four hosts lets the nodes' Alloy config (Task 5) read it unchanged. The directory task writes the same owner and mode as the capture role's, so the two roles never flap it.
- The probe is a plain script, `files/zcache-probe.sh`, that reads the peers from the rendered conf's `AllowedIPs = <address>/32` lines, never from the running interface, and emits `zcache_wireguard_handshake_age_seconds{peer="<mesh address>"}` every minute for each, `+Inf` for a peer that never handshook, one the interface no longer lists, or a tunnel that is down, where the zaccess probe writes no sample and its rule reads no data as OK. The label is the mesh address, not a member name, so the script carries none of the role's variable names and one file serves all four hosts.
- The `cache_host` play in `site.yml` ends at `cache_link` in Task 3; the `cache` role line is appended by Task 4, which creates `roles/cache` (ruling R8), so `site.yml` never names a role that does not exist at its commit.
- `cache_link` sits in the engine play under `cache-link`, ahead of the engine role. The engine play carries no `converge_primary` guard of its own and none is added: the capture play's `refuse to converge the live primary unless explicitly asked` is tagged `always`, runs first, and a host that fails it is dropped from every later play of the run, which is how `--tags engine` is gated today.
- No file under `infra/ansible/roles/cache_link/`, `group_vars/cache_host/` or the three nodes' `host_vars/` says the venue's name: `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` fails the moment a role or those hosts' vars mention it.
- Every new test but the probe's lives in a file `tests/test_config_selectors_are_parsed.py` already grandfathers (`test_infra_firewall_template.py`, `test_infra_converge_guards.py`); the probe's new `tests/test_zcache_probe.py` drives the script over fixtures it writes itself and reads the unit as whole lines. The new assertions parse or compare whole lines rather than test substrings of a config file's text.

**Files:**
- Modify: `infra/ansible/roles/firewall/defaults/main.yml` (the whole file, three lines, rewritten to four)
- Modify: `infra/ansible/roles/firewall/templates/nftables.conf.j2` (a block inserted after the UDP block, lines 33–37: from `{% if firewall_extra_udp_ports %}` to its `{% endif %}`)
- Modify: `infra/ansible/group_vars/cache_host/vars.yml` (Task 1 creates it; three comment lines and two keys appended at its end)
- Modify: `infra/ansible/host_vars/zcrypto/vars.yml` (a blank line, three comment lines and one key appended after line 11, `# docker_deploy_user in the docker role).`)
- Test: `tests/test_infra_firewall_template.py` (the module docstring, lines 1–3; the import block, line 5; `BASE`, line 17; two cases inserted after `test_extra_ports_render_accept_rules`, line 32; the scan's constants, lines 35–41; `test_only_the_bridgehead_group_opens_extra_ports`, lines 74–84, renamed; its two callers and one docstring, lines 93, 99 and 105)

**Interfaces:**
- Consumes: `infra/ansible/group_vars/cache_host/vars.yml` from Task 1, declaring no `firewall_` key; the template's `_render` and `BASE` in `tests/test_infra_firewall_template.py`.
- Produces: `firewall_interface_tcp_ports` (a list of `{iface, ports}`, default `[]`) in the firewall role; the cache group's `firewall_extra_udp_ports: [51821]` and `firewall_interface_tcp_ports: [{iface: zcache0, ports: [6379, 26379]}]`; the engine host's `firewall_extra_udp_ports: [51821]`. Task 3's port case reads all three.

- [ ] **Step 1: Confirm Task 1's cache var file opens nothing yet**

Run: `grep -c '^firewall_' infra/ansible/group_vars/cache_host/vars.yml`
Expected: `0`. Any other count means Task 1 declared a firewall key; stop and report it to the controller, since the keys below would then be declared twice.

- [ ] **Step 2: The failing cases in `tests/test_infra_firewall_template.py`**

Replace the module docstring and the import line under it, from `"""The capture hosts pass neither extra-port variable, so their rendered ruleset must be` through `import shutil`:

```python
"""A host whose var files declare no port variable renders a ruleset BYTE-IDENTICAL to the pre-seam
output (spec 00075 D8), and each port variable is declared only in the var files named here, so an
internet-facing L2 host's firewall changes through its own var file, never as a side effect of
another host's feature."""

import re
import shutil
```

Replace the line `BASE = {"firewall_ssh_port": "10022", "firewall_extra_tcp_ports": [], "firewall_extra_udp_ports": []}` with:

```python
BASE = {
    "firewall_ssh_port": "10022",
    "firewall_extra_tcp_ports": [],
    "firewall_extra_udp_ports": [],
    "firewall_interface_tcp_ports": [],
}
```

Replace the block from `# --- what makes BASE the capture context rather than a literal: the role's own defaults, and the` through `OPENER = "group_vars/access_host/vars.yml"` (the two comment lines and the five constants below them) with:

```python
def test_interface_ports_render_only_as_iifname_rules():
    out = _render({**BASE, "firewall_interface_tcp_ports": [{"iface": "zcache0", "ports": [6379, 26379]}]})
    lines = [line.strip() for line in out.splitlines()]
    assert 'iifname "zcache0" tcp dport { 6379, 26379 } accept' in lines
    # a port rendered on a line without its interface match would be open on the public side
    naming = [line for line in lines if "6379" in line and not line.startswith("#")]
    assert naming == ['iifname "zcache0" tcp dport { 6379, 26379 } accept'], naming


# The pre-seam template is this one with the interface block cut out, so rendering both under a
# context whose interface list is empty proves the block adds nothing there, for the contexts the
# golden above does not pin.
_INTERFACE_BLOCK = re.compile(r"\{% if firewall_interface_tcp_ports %\}\n.*?\{% endif %\}\n", re.DOTALL)


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"firewall_extra_tcp_ports": [80, 443, 20022], "firewall_extra_udp_ports": [51820]},
        {"firewall_extra_udp_ports": [51821]},
    ],
    ids=["no-ports", "bridgehead", "udp-only"],
)
def test_an_empty_interface_list_renders_the_pre_seam_ruleset(extra):
    source = TEMPLATE.read_text()
    pre_seam = _INTERFACE_BLOCK.sub("", source, count=1)
    assert pre_seam != source, "the interface block was not found, so this compares the template with itself"
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    ctx = {**BASE, **extra}
    assert _render(ctx) == env.from_string(pre_seam).render(ctx)


# --- what makes BASE the capture secondary's context rather than a literal: the role's own
# defaults, and the three opener files being the only var files that override any of them.
ANSIBLE = REPO / "infra/ansible"
FIREWALL_DEFAULTS = ANSIBLE / "roles/firewall/defaults/main.yml"
VAR_ROOTS = (ANSIBLE / "group_vars", ANSIBLE / "host_vars")
EXTRA_PORT_VARS = ("firewall_extra_tcp_ports", "firewall_extra_udp_ports", "firewall_interface_tcp_ports")
# The bridgehead's edge; the zcache mesh's nodes (the tunnel port, and the database ports on the
# tunnel alone); the engine host's end of that mesh.
OPENERS = {
    "group_vars/access_host/vars.yml": ["firewall_extra_tcp_ports", "firewall_extra_udp_ports"],
    "group_vars/cache_host/vars.yml": ["firewall_extra_udp_ports", "firewall_interface_tcp_ports"],
    "host_vars/zcrypto/vars.yml": ["firewall_extra_udp_ports"],
}
```

Replace the whole of `test_only_the_bridgehead_group_opens_extra_ports`, from `def test_only_the_bridgehead_group_opens_extra_ports():` through `    )` (the line closing its last assert), with:

```python
def test_only_the_opener_files_open_extra_ports():
    """BASE's empty lists are the firewall role's own defaults, and the opener files are the only var
    files overriding any of them -- so the render above is what the capture secondary's own inventory
    produces."""
    defaults = yaml.safe_load(FIREWALL_DEFAULTS.read_text())
    for var in EXTRA_PORT_VARS:
        assert defaults[var] == BASE[var] == [], f"{var} defaults to {defaults[var]!r}, not the empty list BASE renders with"
    found = _extra_port_declarations(VAR_ROOTS)
    print(f"var files declaring an extra-port list: {found}")
    assert found == OPENERS, f"only the opener files may declare an extra-port list, each exactly its own — found: {found}"
```

In `test_a_capture_group_opening_an_inbound_port_reds_the_scan`, replace its docstring line `    """The defect the scan exists to catch: a var file other than the bridgehead's opening a port."""` with `    """The defect the scan exists to catch: a var file other than an opener's opening a port."""`. Replace both remaining calls `test_only_the_bridgehead_group_opens_extra_ports()` (one in that case, one in `test_the_copied_var_files_alone_red_nothing`) with `test_only_the_opener_files_open_extra_ports()`; `grep -c 'bridgehead_group' tests/test_infra_firewall_template.py` prints `0`.

- [ ] **Step 3: Run the cases and watch them fail**

Run: `uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider`
Expected: `7 failed, 2 passed`. `test_interface_ports_render_only_as_iifname_rules` fails on the missing `iifname` line; the three `test_an_empty_interface_list_renders_the_pre_seam_ruleset` cases on `the interface block was not found`; `test_only_the_opener_files_open_extra_ports`, `test_a_capture_group_opening_an_inbound_port_reds_the_scan` and `test_the_copied_var_files_alone_red_nothing` on `KeyError: 'firewall_interface_tcp_ports'` from the role's defaults. `test_capture_render_is_byte_identical_to_pre_seam` and `test_extra_ports_render_accept_rules` pass.

- [ ] **Step 4: The role's default and the template's block**

Write `infra/ansible/roles/firewall/defaults/main.yml` whole (its third line's comment named the bridgehead alone, which the mesh makes false):

```yaml
firewall_ssh_port: "10022"
firewall_extra_tcp_ports: []  # additional TCP ports to expose (zaccess bridgehead)
firewall_extra_udp_ports: []  # additional UDP ports to expose (the WireGuard listeners: the bridgehead, the zcache mesh)
firewall_interface_tcp_ports: []  # TCP ports accepted only on a named interface: a list of {iface, ports}
```

In `infra/ansible/roles/firewall/templates/nftables.conf.j2`, replace the UDP block's last two lines,

```
    udp dport { {{ firewall_extra_udp_ports | join(', ') }} } accept
{% endif %}
```

with:

```
    udp dport { {{ firewall_extra_udp_ports | join(', ') }} } accept
{% endif %}
{% if firewall_interface_tcp_ports %}

    # TCP services accepted only on a named interface, never on the public side. `iifname`, not
    # `iif`: nftables loads at boot before wg-quick creates a tunnel, and `iif` refuses a name that
    # does not exist yet, which would fail the whole ruleset.
{% for rule in firewall_interface_tcp_ports %}
    iifname "{{ rule.iface }}" tcp dport { {{ rule.ports | join(', ') }} } accept
{% endfor %}
{% endif %}
```

The UDP block's rendered comment (`per-group, spec 00075: WireGuard`) stays as it is: rewording it would change the bridgehead's rendered ruleset, which this task holds byte-identical.

- [ ] **Step 5: The mesh's ports in the two var files**

Append at the end of `infra/ansible/group_vars/cache_host/vars.yml`, after Task 1's last line:

```yaml
# The zcache mesh (spec 00118 D6): the tunnel's UDP port on the public side, and the Valkey and
# Sentinel ports on the tunnel alone. The Linode Cloud Firewall mirrors the UDP port and not the TCP
# ones — a future addition to either list opens BOTH layers where it is public.
firewall_extra_udp_ports: [51821]
firewall_interface_tcp_ports:
  - {iface: zcache0, ports: [6379, 26379]}
```

Append at the end of `infra/ansible/host_vars/zcrypto/vars.yml`, after `# docker_deploy_user in the docker role).`:

```yaml

# The engine host's end of the zcache mesh (spec 00118 D6): the tunnel's UDP port. It listens for
# the nodes' handshakes and serves no database port. A Cloud Firewall attached to this Linode opens
# it by hand as well.
firewall_extra_udp_ports: [51821]
```

- [ ] **Step 6: Run the cases and watch them pass**

Run: `uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider`
Expected: `9 passed`.

- [ ] **Step 7: The consumers**

The union of `grep -rlE 'host_vars|group_vars|roles/firewall|nftables|test_infra_firewall_template' tests/test_*.py` as it read when this section was written:

Run: `uv run pytest tests/test_config_selectors_are_parsed.py tests/test_converge_sh.py tests/test_deploy_log_audit.py tests/test_fleet_contracts.py tests/test_grafana_auth.py tests/test_infra_alert_rules.py tests/test_infra_converge_guards.py tests/test_infra_firewall_template.py tests/test_infra_unattended_upgrades.py tests/test_mint_with_vaulted_key_sh.py tests/test_ops_daily.py tests/test_probe_with_vaulted_key_sh.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a data gate, none failed.

- [ ] **Step 8: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 9: Commit**

```bash
git add infra/ansible/roles/firewall/defaults/main.yml infra/ansible/roles/firewall/templates/nftables.conf.j2 infra/ansible/group_vars/cache_host/vars.yml infra/ansible/host_vars/zcrypto/vars.yml tests/test_infra_firewall_template.py
git commit -m "feat(firewall): ports accepted on a named interface alone, and the zcache mesh's ports opened

The firewall role takes \`firewall_interface_tcp_ports\`, a list of iface and ports rendered as one
\`iifname\` accept line per entry, empty by default and guarded like the two extra-port lists, so a
host that declares none renders byte-identically: the golden still pins the capture secondary's
ruleset, and a new case renders the template beside itself with the interface block cut out, under
three contexts with the list empty -- no ports, the bridgehead's, a UDP-only opener -- and requires
the two equal. \`iifname\` rather than \`iif\`: nftables loads at boot before wg-quick creates the
tunnel, and \`iif\` refuses a name that does not exist yet.

The cache group opens the mesh's UDP port 51821 on the public side and 6379 and 26379 on zcache0
alone; the engine host opens 51821 in its host_vars, the one plaintext var file that is zcrypto's
alone, group_vars/engine_host holding only its vault. The scan that admitted extra-port
declarations in the bridgehead's group alone now admits exactly three opener files, each with
exactly its own keys, and the role's defaults for all three lists stay the empty list BASE renders
with.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

The executor writes its own model name for `<model>` (`Claude Fable 5.1`, `Claude Opus 5.5`, ...).

- [ ] **Step 10: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 11: Prove the guards with three probes, then record their verdicts by a message-only amend**

The first two probes' control recases the template's `# SSH` comment, which the golden pins. The first mutation renders the interface block whatever the list holds, the regression that would change every host's ruleset; the second drops the interface match from the rule line, which opens the database ports on the public side. The third, over the cache group's var file, plants a public TCP list beside the mesh's keys, its control misspelling the UDP key the scan expects there:

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/roles/firewall/templates/nftables.conf.j2 \
  --control 's/^    # SSH$/    # ssh/' \
  --mutation 's/{% if firewall_interface_tcp_ports %}/{% if true %}/' \
  -- uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider -k "byte_identical or pre_seam_ruleset or iifname"
infra/scripts/mutate-probe.sh --file infra/ansible/roles/firewall/templates/nftables.conf.j2 \
  --control 's/^    # SSH$/    # ssh/' \
  --mutation 's/^    iifname "{{ rule.iface }}" tcp dport/    tcp dport/' \
  -- uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider -k "byte_identical or pre_seam_ruleset or iifname"
infra/scripts/mutate-probe.sh --file infra/ansible/group_vars/cache_host/vars.yml \
  --control 's/^firewall_extra_udp_ports: \[51821\]$/firewall_extra_udp_port: [51821]/' \
  --mutation '$a firewall_extra_tcp_ports: [6379]' \
  -- uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider -k opener_files
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over
`infra/ansible/roles/firewall/templates/nftables.conf.j2`, control the SSH comment recased so the
golden fails, through `-k "byte_identical or pre_seam_ruleset or iifname"`: the interface block
rendered whatever the list holds, KILLED, control proven; the interface match dropped from the
rule line, KILLED, control proven; over `infra/ansible/group_vars/cache_host/vars.yml`, control its
UDP key misspelled, through `-k opener_files`: a public TCP port list planted beside the mesh's
keys, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 3: The cache_link role: the zcache WireGuard mesh on the engine host and the three nodes

*Rulings: R7 moved Task 5's handshake-age probe into this role whole (a plain script over the rendered conf's `AllowedIPs` lines, labelled by mesh address, with its tests), replacing this task's templated probe; R17 dropped the #606 ancestry step; R1 set the mesh converges' tags; R20 added the one-key-variable case; R18 kept the keypairs and the Cloud Firewall rule in the operator block, whose converges are the Rollout's.*

**Files:**
- Create: `infra/ansible/roles/cache_link/defaults/main.yml`
- Create: `infra/ansible/roles/cache_link/tasks/main.yml`
- Create: `infra/ansible/roles/cache_link/handlers/main.yml`
- Create: `infra/ansible/roles/cache_link/templates/zcache0.conf.j2`
- Create: `infra/ansible/roles/cache_link/files/zcache-probe.sh` (mode `0755`)
- Create: `infra/ansible/roles/cache_link/templates/zcache-probe.service.j2`
- Create: `infra/ansible/roles/cache_link/templates/zcache-probe.timer.j2`
- Modify: `infra/ansible/host_vars/zcrypto/vars.yml` (three comment lines and two keys appended after the key Task 2 appended, `firewall_extra_udp_ports: [51821]`)
- Modify: `infra/ansible/host_vars/zcrypto-valkey1/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey3/vars.yml` (Task 1 creates them; the same block appended at each one's end)
- Modify: `infra/ansible/site.yml` (the engine play's `  roles:` block, lines 153–155 as of `develop` at `331a67dae`, from `  roles:` through `      tags: [engine]` before the ops play's `# spec 00051` comment; a new play appended after the access play's last line, `      tags: [access]`)
- Test: `tests/test_infra_converge_guards.py` (a block appended at the end of the file, after `test_the_copied_role_alone_reds_nothing`)
- Test: `tests/test_zcache_probe.py` (new)

**Interfaces:**
- Consumes: from Task 1, the inventory group `cache_host` with `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3` and a plaintext `host_vars/<node>/vars.yml` for each; from Task 2, `firewall_extra_udp_ports` in `group_vars/cache_host/vars.yml` and `host_vars/zcrypto/vars.yml` and `firewall_interface_tcp_ports` in the former; from #606 (`331a67dae`), `_wg_value`, `_declared`, `_tunnel_mtus`, `WG_UDP_PORTS`, `find_task`, `load_tasks`, `assert_that`, `truthy`, `Templar`, `DataLoader`, `ANSIBLE`, `re`, `yaml`, `pytest` in `tests/test_infra_converge_guards.py`.
- Produces: the role `cache_link` (variables `cache_link_interface`, `cache_link_listen_port`, `cache_link_network`, `cache_link_peers`, `cache_link_textfile_dir`; per host `cache_link_address`, `cache_link_private_key`; handler `restart zcache0`; unit `wg-quick@zcache0`; `/usr/local/sbin/zcache-probe` and the `zcache-probe.timer` writing `zcache_wireguard_handshake_age_seconds{peer="<mesh address>"}` to `/var/lib/zcrypto-node-textfile/zcache.prom`, which Task 5 admits, charts and alerts on); the tag `cache-link` on the engine play and the `cache_host` play; the vault key names the operator steps below fill.

- [ ] **Step 1: The failing cases**

Create `tests/test_zcache_probe.py`:

```python
"""The zcache mesh probe: the shell script the `cache_link` role installs on the engine host and the three cache
nodes, driven with `bash` over a fixture WireGuard config and a stub `wg` on PATH. The handshake-stale rule reads what
it writes, so a peer it leaves out is a link nothing watches."""

from __future__ import annotations

import math
import os
import stat
import subprocess
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/cache_link"
SCRIPT = ROLE / "files/zcache-probe.sh"
UNIT = ROLE / "templates/zcache-probe.service.j2"

CONF = """[Interface]
Address = 10.98.0.11/24
ListenPort = 51821

[Peer]
PublicKey = AAAA
AllowedIPs = 10.98.0.1/32
Endpoint = 172.105.64.43:51821
PersistentKeepalive = 25

[Peer]
PublicKey = BBBB
AllowedIPs = 10.98.0.12/32
Endpoint = 139.162.163.39:51821
PersistentKeepalive = 25

[Peer]
PublicKey = CCCC
AllowedIPs = 10.98.0.13/32
Endpoint = 172.233.51.246:51821
PersistentKeepalive = 25
"""


def _stub_wg(tmp_path: Path, dump: str | None) -> Path:
    """A `wg` that prints `dump` for `wg show zcache0 dump`, or fails as it does on an absent interface."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    wg = bin_dir / "wg"
    body = f"cat <<'DUMP'\n{dump}DUMP\n" if dump is not None else "echo 'Unable to access interface: No such device' >&2; exit 1\n"
    wg.write_text(f'#!/usr/bin/env bash\n[ "$*" = "show zcache0 dump" ] || exit 64\n{body}')
    wg.chmod(wg.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run(tmp_path: Path, dump: str | None, conf: str = CONF) -> tuple[subprocess.CompletedProcess[str], Path]:
    conf_path = tmp_path / "zcache0.conf"
    conf_path.write_text(conf)
    out = tmp_path / "zcache.prom"
    env = {**os.environ, "PATH": f"{_stub_wg(tmp_path, dump)}:{os.environ['PATH']}"}
    args = ["bash", str(SCRIPT), str(conf_path), str(out)]
    return subprocess.run(args, capture_output=True, text=True, check=False, env=env), out


def _series(prom: Path) -> dict[str, float]:
    return {
        name: float(value)
        for name, value in (ln.rsplit(" ", 1) for ln in prom.read_text().splitlines() if ln and not ln.startswith("#"))
    }


def _dump(*peers: tuple[str, str, int]) -> str:
    lines = ["PRIVATE\tPUBLIC\t51821\toff"]
    lines += [f"{key}\t(none)\t1.2.3.4:51821\t{ip}/32\t{latest}\t100\t200\t25" for key, ip, latest in peers]
    return "\n".join(lines) + "\n"


def _age(peer: str) -> str:
    return f'zcache_wireguard_handshake_age_seconds{{peer="{peer}"}}'


def test_each_configured_peer_gets_its_age_and_a_peer_with_no_handshake_reads_infinite(tmp_path):
    now = int(time.time())
    result, out = _run(tmp_path, _dump(("AAAA", "10.98.0.1", now - 40), ("BBBB", "10.98.0.12", 0)))
    assert result.returncode == 0, result.stderr
    series = _series(out)
    assert 40 <= series[_age("10.98.0.1")] <= 45
    assert math.isinf(series[_age("10.98.0.12")])  # listed by the interface, never handshaken
    assert math.isinf(series[_age("10.98.0.13")])  # in the config, absent from the interface
    assert oct(out.stat().st_mode & 0o777) == "0o644"


def test_a_down_interface_reads_every_configured_peer_as_infinite(tmp_path):
    result, out = _run(tmp_path, None)
    assert result.returncode == 0, result.stderr
    ages = _series(out)
    assert set(ages) == {_age("10.98.0.1"), _age("10.98.0.12"), _age("10.98.0.13")}
    assert all(math.isinf(v) for v in ages.values())


def test_a_config_naming_no_peer_fails_and_publishes_nothing(tmp_path):
    result, out = _run(tmp_path, _dump(), conf="[Interface]\nAddress = 10.98.0.11/24\n")
    assert result.returncode == 1
    assert "names no /32 AllowedIPs peer" in result.stderr
    assert not out.exists()


def test_the_unit_runs_the_probe_over_the_rendered_conf_into_the_textfile_directory():
    """The unit hands the script the conf the role renders and the directory the host's Alloy reads, and lets it write
    nowhere else."""
    textfile_dir = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["cache_link_textfile_dir"]
    assert textfile_dir == "/var/lib/zcrypto-node-textfile"
    lines = [line.strip() for line in UNIT.read_text().splitlines()]
    # config-selector-ok: each expected text is a whole stripped line of the unit, compared for equality
    assert (
        "ExecStart=/usr/local/sbin/zcache-probe /etc/wireguard/{{ cache_link_interface }}.conf {{ cache_link_textfile_dir }}/zcache.prom"
        in lines
    )
    # config-selector-ok: a whole stripped line, compared for equality
    assert "ReadWritePaths={{ cache_link_textfile_dir }}" in lines
```

Append at the end of `tests/test_infra_converge_guards.py`, after `test_the_copied_role_alone_reds_nothing`:

```python


# --- the zcache mesh: each member's conf names the other three, one /32 each, and the role refuses
# a peer list that would render otherwise. The guard's conditions are fed constructed peer lists
# through Ansible's templar, and the conf is rendered through it for each member as committed.
CACHE_LINK = ANSIBLE / "roles" / "cache_link"
CACHE_LINK_TASKS = CACHE_LINK / "tasks" / "main.yml"
CACHE_LINK_DEFAULTS = CACHE_LINK / "defaults" / "main.yml"
CACHE_LINK_WG_CONF = CACHE_LINK / "templates" / "zcache0.conf.j2"
CACHE_HOST_VARS = ANSIBLE / "group_vars" / "cache_host" / "vars.yml"
ENGINE_HOST_VARS = ANSIBLE / "host_vars" / "zcrypto" / "vars.yml"
MESH_GUARD = "refuse a mesh whose peers are not one host address each, or that lists this host as its own peer"
MESH_MEMBERS = ("zcrypto", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")
# The shape of a WireGuard key, and distinct per member, so no fixture key collides with another.
FAKE_KEY = {name: f"{i}" * 43 + "=" for i, name in enumerate(MESH_MEMBERS, 1)}


class _VaultKeptLoader(yaml.SafeLoader):
    """A host_vars file may carry an inline `!vault` value; its ciphertext is kept, never decrypted."""


_VaultKeptLoader.add_constructor("!vault", lambda loader, node: node.value)


def _mesh_vars(host: str) -> dict:
    """The committed mesh as `host` sees it at converge time, its keys replaced by fixtures."""
    defaults = yaml.safe_load(CACHE_LINK_DEFAULTS.read_text())
    host_vars = yaml.load((ANSIBLE / "host_vars" / host / "vars.yml").read_text(), Loader=_VaultKeptLoader)
    return {
        "inventory_hostname": host,
        "cache_link_peers": [{**p, "public_key": FAKE_KEY[p["name"]]} for p in defaults["cache_link_peers"]],
        "cache_link_network": defaults["cache_link_network"],
        "cache_link_listen_port": defaults["cache_link_listen_port"],
        "cache_link_address": host_vars["cache_link_address"],
        "cache_link_private_key": "P" * 43 + "=",
    }


@pytest.mark.parametrize("host", MESH_MEMBERS)
def test_the_committed_mesh_passes_its_guard_on_each_member(host):
    assert truthy(assert_that(find_task(load_tasks(CACHE_LINK_TASKS), MESH_GUARD)), _mesh_vars(host))


def _peer(v: dict, name: str) -> dict:
    return next(p for p in v["cache_link_peers"] if p["name"] == name)


def _prefixed(v):
    _peer(v, "zcrypto-valkey2")["address"] = "10.98.0.12/24"


def _outside(v):
    _peer(v, "zcrypto-valkey2")["address"] = "10.99.0.12"


def _self_absent(v):
    v["cache_link_peers"] = [p for p in v["cache_link_peers"] if p["name"] != "zcrypto-valkey1"]


def _other_twice(v):
    v["cache_link_peers"].append({**_peer(v, "zcrypto-valkey2"), "address": "10.98.0.14", "public_key": "9" * 43 + "="})


def _own_address_elsewhere(v):
    _peer(v, "zcrypto-valkey2")["address"] = _peer(v, "zcrypto-valkey1")["address"]


def _own_key_elsewhere(v):
    _peer(v, "zcrypto-valkey2")["public_key"] = _peer(v, "zcrypto-valkey1")["public_key"]


def _peer_key_short(v):
    _peer(v, "zcrypto-valkey2")["public_key"] = "3" * 43


def _address_disagrees(v):
    v["cache_link_address"] = "10.98.0.14"


def _address_unset(v):
    del v["cache_link_address"]


def _key_unset(v):
    del v["cache_link_private_key"]


def _key_short(v):
    v["cache_link_private_key"] = "P" * 43


@pytest.mark.parametrize(
    "spoil",
    [
        _prefixed,
        _outside,
        _self_absent,
        _other_twice,
        _own_address_elsewhere,
        _own_key_elsewhere,
        _peer_key_short,
        _address_disagrees,
        _address_unset,
        _key_unset,
        _key_short,
    ],
    ids=lambda f: f.__name__.lstrip("_"),
)
def test_the_mesh_guard_refuses_a_peer_list_that_would_render_wrong(spoil):
    variables = _mesh_vars("zcrypto-valkey1")
    spoil(variables)
    assert not truthy(assert_that(find_task(load_tasks(CACHE_LINK_TASKS), MESH_GUARD)), variables)


def _render_conf(host: str) -> dict[str, list[dict[str, str]]]:
    """The rendered conf as wg reads it: section name -> one {key: value} per section occurrence."""
    from ansible.template import trust_as_template

    rendered = Templar(loader=DataLoader(), variables=_mesh_vars(host)).template(trust_as_template(CACHE_LINK_WG_CONF.read_text()))
    sections: dict[str, list[dict[str, str]]] = {}
    for raw in rendered.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("[") and line.endswith("]"):
            sections.setdefault(line, []).append({})
        elif "=" in line:
            key, _, value = line.partition("=")
            current = list(sections.values())[-1][-1] if sections else None
            assert current is not None, f"{line!r} precedes every section"
            assert key.strip() not in current, f"{key.strip()} repeats inside one section"
            current[key.strip()] = value.strip()
    return sections


@pytest.mark.parametrize("host", MESH_MEMBERS)
def test_the_zcache_conf_names_each_other_member_once_as_one_host(host):
    v = _mesh_vars(host)
    conf = _render_conf(host)
    assert set(conf) == {"[Interface]", "[Peer]"}, conf
    (interface,) = conf["[Interface]"]
    assert interface["Address"] == f"{v['cache_link_address']}/24"
    assert interface["ListenPort"] == str(v["cache_link_listen_port"])
    others = [p for p in v["cache_link_peers"] if p["name"] != host]
    assert sorted(p["AllowedIPs"] for p in conf["[Peer]"]) == sorted(f"{p['address']}/32" for p in others)
    assert sorted(p["PublicKey"] for p in conf["[Peer]"]) == sorted(p["public_key"] for p in others)
    assert {p["Endpoint"] for p in conf["[Peer]"]} == {f"{p['endpoint']}:{v['cache_link_listen_port']}" for p in others}
    assert {p["PersistentKeepalive"] for p in conf["[Peer]"]} == {"25"}


def test_each_zcache_peer_key_is_one_variable_every_member_renders():
    """A rotated key is one edit: each member's public half is read from its own `cache_wg_<member>_public_key`, set in
    group_vars/all/vars.yml and in no member's host_vars, and every other member's conf renders it, so no host holds a
    copy that can fall behind."""
    defaults = yaml.safe_load(CACHE_LINK_DEFAULTS.read_text())
    wired = {p["name"]: p["public_key"] for p in defaults["cache_link_peers"]}
    assert wired == {name: "{{ cache_wg_" + name.replace("-", "_") + "_public_key }}" for name in MESH_MEMBERS}, wired
    assert _wg_value(CACHE_LINK_WG_CONF, "PublicKey") == "{{peer.public_key}}"
    for host in MESH_MEMBERS:
        host_vars = yaml.load((ANSIBLE / "host_vars" / host / "vars.yml").read_text(), Loader=_VaultKeptLoader)
        assert not [key for key in host_vars if key.startswith("cache_wg_")], f"{host}'s host_vars set a mesh key"


def test_the_zcache_mesh_runs_the_fleets_one_tunnel_mtu():
    mtus = {**_tunnel_mtus(), str(CACHE_LINK_WG_CONF.relative_to(ANSIBLE)): int(_wg_value(CACHE_LINK_WG_CONF, "MTU"))}
    assert len(set(mtus.values())) == 1, f"the fleet's tunnels declare different MTUs: {mtus}"


def test_the_zcache_ports_are_one_value_in_every_declaration():
    """The listen port is also every peer's Endpoint port and the one port each member's firewall opens
    for the mesh; a drift among them is a tunnel that never handshakes."""
    assert re.fullmatch(r"\{\{\s*cache_link_listen_port\s*\}\}", _wg_value(CACHE_LINK_WG_CONF, "ListenPort"))
    assert re.search(r":\{\{\s*cache_link_listen_port\s*\}\}$", _wg_value(CACHE_LINK_WG_CONF, "Endpoint"))
    defaults = yaml.safe_load(CACHE_LINK_DEFAULTS.read_text())
    assert all(":" not in p["endpoint"] for p in defaults["cache_link_peers"]), "an endpoint carries its own port"
    ports = {"roles/cache_link/defaults:cache_link_listen_port": defaults["cache_link_listen_port"]}
    for path in (CACHE_HOST_VARS, ENGINE_HOST_VARS):
        opened = _declared(path, WG_UDP_PORTS)
        assert isinstance(opened, list) and len(opened) == 1, (
            f"{path.relative_to(ANSIBLE)}:{WG_UDP_PORTS} is {opened!r}, not the single tunnel port this selection can read"
        )
        ports[f"{path.relative_to(ANSIBLE)}:{WG_UDP_PORTS}"] = opened[0]
    assert len(set(ports.values())) == 1, f"the zcache mesh's port declarations disagree: {ports}"
    # the interface the database ports are scoped to is the mesh's own
    scoped = _declared(CACHE_HOST_VARS, "firewall_interface_tcp_ports")
    assert [rule["iface"] for rule in scoped] == [defaults["cache_link_interface"]], scoped
```

- [ ] **Step 2: Run the cases and watch them fail**

Run: `uv run pytest tests/test_infra_converge_guards.py tests/test_zcache_probe.py -q -p no:cacheprovider -k "mesh or zcache"`
Expected: `26 failed`: the 22 mesh and zcache cases of `tests/test_infra_converge_guards.py` on `FileNotFoundError` for `infra/ansible/roles/cache_link/...`, the three script cases of `tests/test_zcache_probe.py` on the missing script (`bash` exits 127), and its unit case on `FileNotFoundError`. The deselected count depends on what Tasks 1 and 2 added and is not pinned.

- [ ] **Step 3: The role's defaults**

Create `infra/ansible/roles/cache_link/defaults/main.yml`:

```yaml
---
# Defaults for the `cache_link` role (spec 00118 D5): the zcache WireGuard mesh between the engine
# host and the three cache nodes. Each member sets its own `cache_link_address` and wires
# `cache_link_private_key` from its vault var in its host_vars; the role's first task refuses a
# member missing either.
cache_link_interface: zcache0
# The one member of firewall_extra_udp_ports in group_vars/cache_host/vars.yml and in
# host_vars/zcrypto/vars.yml; tests/test_infra_converge_guards.py holds the three to one value.
cache_link_listen_port: 51821
cache_link_network: 10.98.0.0/24
# The whole mesh, this host included: the conf renders every member but the one named
# inventory_hostname. Each endpoint is an IPv4 literal because each name also carries an AAAA
# record, and the Linode Cloud Firewall rules are written per IPv4 address; a re-IP edits it here.
cache_link_peers:
  - {name: zcrypto, address: 10.98.0.1, endpoint: 172.105.64.43, public_key: "{{ cache_wg_zcrypto_public_key }}"}
  - {name: zcrypto-valkey1, address: 10.98.0.11, endpoint: 172.104.159.221, public_key: "{{ cache_wg_zcrypto_valkey1_public_key }}"}
  - {name: zcrypto-valkey2, address: 10.98.0.12, endpoint: 139.162.163.39, public_key: "{{ cache_wg_zcrypto_valkey2_public_key }}"}
  - {name: zcrypto-valkey3, address: 10.98.0.13, endpoint: 172.233.51.246, public_key: "{{ cache_wg_zcrypto_valkey3_public_key }}"}
# The directory the host's Alloy textfile collector reads: the capture role's `capture_textfile_dir`
# on the engine host, and the same path on the nodes so their Alloy config reads it unchanged.
cache_link_textfile_dir: /var/lib/zcrypto-node-textfile
```

- [ ] **Step 4: The role's tasks and handlers**

Create `infra/ansible/roles/cache_link/tasks/main.yml`:

```yaml
# The cache_link role (spec 00118 D5): the zcache WireGuard mesh, one conf per member naming the
# other three, and a probe publishing each peer's handshake age.

# First, so a member missing its address or key fails here by name rather than inside the conf
# task, whose no_log would hide which variable was undefined. The template appends /32 to every
# peer address, so an address that is not a bare host address inside the mesh network is what an
# AllowedIPs wider than one host would come from; and a second entry carrying this host's name,
# address or key would render this host as its own peer.
- name: refuse a mesh whose peers are not one host address each, or that lists this host as its own peer
  ansible.builtin.assert:
    that:
      - cache_link_address is defined
      - cache_link_private_key is defined and (cache_link_private_key | length) == 44
      - (cache_link_peers | map(attribute='name') | unique | list | length) == (cache_link_peers | length)
      - (cache_link_peers | map(attribute='address') | unique | list | length) == (cache_link_peers | length)
      - (cache_link_peers | map(attribute='public_key') | unique | list | length) == (cache_link_peers | length)
      - (cache_link_peers | map(attribute='public_key') | map('length') | unique | list) == [44]
      - (cache_link_peers | map(attribute='address') | map('regex_replace', '[.][0-9]{1,3}$', '.0/24') | unique | list) == [cache_link_network]
      - (cache_link_peers | selectattr('name', 'equalto', inventory_hostname) | map(attribute='address') | list) == [cache_link_address]
    fail_msg: >-
      REFUSING the zcache mesh on {{ inventory_hostname }}. Every member of cache_link_peers needs its
      own name, address and 44-character public key, every address a bare host address inside
      {{ cache_link_network }} (the conf adds the /32), and this host exactly one entry, whose address
      is its own cache_link_address ({{ cache_link_address | default('undefined') }}); the host_vars
      also wire cache_link_private_key from its vault var, a 44-character WireGuard key. Members as
      read: {{ cache_link_peers | map(attribute='name') | list }} at
      {{ cache_link_peers | map(attribute='address') | list }}.

- name: wireguard tools (wg, wg-quick and the wg-quick@ unit)
  ansible.builtin.apt:
    name: [wireguard-tools]
    state: present
    update_cache: true
    cache_valid_time: 3600
  register: cache_link_wireguard_install

- name: zcache mesh conf (this host's end and a peer per other member)
  ansible.builtin.template:
    src: zcache0.conf.j2
    dest: "/etc/wireguard/{{ cache_link_interface }}.conf"
    owner: root
    group: root
    mode: "0600"
  no_log: true # renders the WireGuard private key -- keep it out of --diff output
  diff: false
  notify: restart zcache0

# A first-run dry run never installed wireguard-tools, so systemd cannot find wg-quick@ and the
# module fails even in check mode, and converge.sh aborts on a failed preview. Skip exactly that
# case; every real converge still runs this.
- name: zcache mesh enabled + started
  ansible.builtin.systemd:
    name: "wg-quick@{{ cache_link_interface }}"
    enabled: true
    state: started
  when: not (ansible_check_mode and cache_link_wireguard_install is changed)

- name: textfile directory for the mesh probe
  ansible.builtin.file:
    path: "{{ cache_link_textfile_dir }}"
    state: directory
    owner: root
    group: root
    mode: "0755"
- name: mesh probe script
  ansible.builtin.copy:
    src: zcache-probe.sh
    dest: /usr/local/sbin/zcache-probe
    owner: root
    group: root
    mode: "0755"
# The unit passes the rendered conf and the textfile directory to the script, so both follow the defaults.
- name: mesh probe service + timer
  ansible.builtin.template:
    src: "zcache-probe.{{ item }}.j2"
    dest: "/etc/systemd/system/zcache-probe.{{ item }}"
    owner: root
    group: root
    mode: "0644"
  loop: [service, timer]
  register: cache_link_probe_units
  notify: reload systemd
# The same first-run dry-run case as the tunnel above: the unit files were never written.
- name: mesh probe timer enabled
  ansible.builtin.systemd:
    name: zcache-probe.timer
    enabled: true
    state: started
    daemon_reload: true
  when: not (ansible_check_mode and cache_link_probe_units is changed)
```

Create `infra/ansible/roles/cache_link/handlers/main.yml`:

```yaml
---
- name: restart zcache0
  # wg-quick has no reload -- a restart is the only way to apply a changed conf, and it drops every
  # connection through the mesh for as long as the interface is down. The first-run dry-run case of
  # the enable task in tasks/main.yml is skipped here too.
  ansible.builtin.systemd:
    name: "wg-quick@{{ cache_link_interface }}"
    state: restarted
  when: not (ansible_check_mode and cache_link_wireguard_install is changed)

- name: reload systemd
  ansible.builtin.systemd: {daemon_reload: true}
```

- [ ] **Step 5: The role's templates and the probe script**

Create `infra/ansible/roles/cache_link/templates/zcache0.conf.j2`:

```
# Rendered by the `cache_link` role at /etc/wireguard/zcache0.conf — edit the template.
[Interface]
Address = {{ cache_link_address }}/{{ cache_link_network | split('/') | last }}
# The fleet's one tunnel MTU (the access_ops template's zaccess0.conf.j2 says why 1380). No path of
# this mesh has been measured and one of them crosses regions: 1380 fits any path of 1440 bytes or
# more, and costs 40 bytes a packet against wg-quick's default 1420.
MTU = 1380
ListenPort = {{ cache_link_listen_port }}
PrivateKey = {{ cache_link_private_key }}
{% for peer in cache_link_peers if peer.name != inventory_hostname %}

[Peer]
# {{ peer.name }}
PublicKey = {{ peer.public_key }}
AllowedIPs = {{ peer.address }}/32
Endpoint = {{ peer.endpoint }}:{{ cache_link_listen_port }}
PersistentKeepalive = 25
{% endfor %}
```

Create `infra/ansible/roles/cache_link/files/zcache-probe.sh`:

```bash
#!/usr/bin/env bash
# Installed by the `cache_link` role at /usr/local/sbin/zcache-probe, so a hand-edit there is lost on
# the next converge; tests/test_zcache_probe.py drives this file.
set -euo pipefail

usage="usage: zcache-probe <wireguard-conf> <output.prom>"
conf=${1:-}
out=${2:-}
[ -n "$conf" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }
iface=$(basename "$conf" .conf)

# The peers are read from the rendered config, never from the running interface: an interface that is
# down lists no peers, and a peer absent from the output would read as healthy by omission.
mapfile -t peers < <(sed -n 's|^AllowedIPs[[:space:]]*=[[:space:]]*\([0-9.]*\)/32[[:space:]]*$|\1|p' "$conf")
[ "${#peers[@]}" -gt 0 ] || { echo "zcache-probe: $conf names no /32 AllowedIPs peer" >&2; exit 1; }

# `wg show <if> dump`: an interface line, then one tab-separated line per peer whose fourth field is its
# allowed-ips and fifth its latest handshake in epoch seconds, 0 when it has none.
declare -A handshake=()
if dump=$(wg show "$iface" dump 2>/dev/null); then
  while IFS=$'\t' read -r _key _psk _endpoint allowed latest _rest; do
    handshake[${allowed%/32}]=$latest
  done < <(printf '%s\n' "$dump" | tail -n +2)
fi
now=$(date +%s)

# Atomic publish: the collector globs this directory continuously, and a sibling mktemp makes the mv a
# same-filesystem rename.
tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP zcache_wireguard_handshake_age_seconds Seconds since the mesh peer's last WireGuard handshake, +Inf when it has none."
  echo "# TYPE zcache_wireguard_handshake_age_seconds gauge"
  for peer in "${peers[@]}"; do
    latest=${handshake[$peer]:-0}
    if [ "$latest" -gt 0 ]; then age=$((now - latest)); else age=+Inf; fi
    printf 'zcache_wireguard_handshake_age_seconds{peer="%s"} %s\n' "$peer" "$age"
  done
} > "$tmp"
chmod 0644 -- "$tmp"   # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out"
trap - EXIT
```

Then `chmod 0755 infra/ansible/roles/cache_link/files/zcache-probe.sh` (the shebang hooks refuse a script git records as 0644).

Create `infra/ansible/roles/cache_link/templates/zcache-probe.service.j2`:

```ini
# Rendered by the `cache_link` Ansible role at /etc/systemd/system/zcache-probe.service; edit
# infra/ansible/roles/cache_link/templates/zcache-probe.service.j2 and re-converge.
[Unit]
Description=zcache mesh probe writing each peer's WireGuard handshake age

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zcache-probe /etc/wireguard/{{ cache_link_interface }}.conf {{ cache_link_textfile_dir }}/zcache.prom
# Root, for `wg show` and the 0600 WireGuard config; the one path it may write is the textfile directory.
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={{ cache_link_textfile_dir }}
```

Create `infra/ansible/roles/cache_link/templates/zcache-probe.timer.j2`:

```
# Rendered by the `cache_link` Ansible role at /etc/systemd/system/zcache-probe.timer — do not
# hand-edit on the host, edit infra/ansible/roles/cache_link/templates/zcache-probe.timer.j2 instead.
[Unit]
Description=zcache mesh probe cadence — every minute

[Timer]
OnCalendar=*:*:23
# AccuracySec defaults to one minute, which lets each run slide by a whole period against the
# three-minute staleness the handshake-age rule reads.
AccuracySec=1s
# Deliberately NO Persistent=true, as for the zaccess probe timers: this reports CURRENT state, and a
# run missed while the host was down is meaningless to catch up on.
Unit=zcache-probe.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 6: Each member's address and key wiring**

Append at the end of `infra/ansible/host_vars/zcrypto/vars.yml`, after Task 2's `firewall_extra_udp_ports: [51821]`:

```yaml

# This host's member of the zcache mesh (roles/cache_link): its tunnel address, and its private key
# wired from the vault var in group_vars/all/vault.yml.
cache_link_address: 10.98.0.1
cache_link_private_key: "{{ cache_wg_zcrypto_private_key }}"
```

Append at the end of `infra/ansible/host_vars/zcrypto-valkey1/vars.yml`:

```yaml

# This host's member of the zcache mesh (roles/cache_link): its tunnel address, and its private key
# wired from the vault var in group_vars/all/vault.yml.
cache_link_address: 10.98.0.11
cache_link_private_key: "{{ cache_wg_zcrypto_valkey1_private_key }}"
```

Append at the end of `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`:

```yaml

# This host's member of the zcache mesh (roles/cache_link): its tunnel address, and its private key
# wired from the vault var in group_vars/all/vault.yml.
cache_link_address: 10.98.0.12
cache_link_private_key: "{{ cache_wg_zcrypto_valkey2_private_key }}"
```

Append at the end of `infra/ansible/host_vars/zcrypto-valkey3/vars.yml`:

```yaml

# This host's member of the zcache mesh (roles/cache_link): its tunnel address, and its private key
# wired from the vault var in group_vars/all/vault.yml.
cache_link_address: 10.98.0.13
cache_link_private_key: "{{ cache_wg_zcrypto_valkey3_private_key }}"
```

The eight `cache_wg_*` variables these name do not exist in this commit; the operator steps below create them, and until they land the role's first task refuses every member.

- [ ] **Step 7: The two plays in `site.yml`**

In the engine play, replace

```yaml
  roles:
    - role: engine
      tags: [engine]
```

(the three lines between `      tags: [engine]` closing `engine window override accepted — the reason, on the record` and the ops play's `# spec 00051; the pull-only-transport ruling is its D10.`) with:

```yaml
  roles:
    # The engine host's end of the zcache mesh, under its own tag: it restarts no container, so it
    # takes no engine window. It is still a converge of the primary: the capture play's always-tagged
    # guard above has already failed this host without -e converge_primary=true, and a host that
    # fails leaves every later play. `--skip-tags engine` runs it too, idempotently.
    - role: cache_link
      tags: [cache-link]
    - role: engine
      tags: [engine]
```

Append after the file's last line, the access play's `      tags: [access]`:

```yaml

# spec 00118.
- name: converge the cache nodes — the engine's Valkey replica set
  hosts: cache_host
  become: true
  pre_tasks:
    - name: note — the cache nodes' charter
      ansible.builtin.debug:
        msg: >-
          The engine's cache: Valkey and Sentinel on three nodes, one node per converge. No trade
          key and no capture data; the engine's ledger and the venue stay the truth, so a lost
          node is re-provisioned and re-synced from its peers. This play targets
          zcrypto-deploy@{{ ansible_port }} and assumes bootstrap.yml already ran.
      tags: [always]
  roles:
    - role: base
      tags: [base]
    - role: hardening
      tags: [hardening]
    - role: firewall
      tags: [firewall]
    - role: fail2ban
      tags: [fail2ban]
    - role: chrony
      tags: [chrony]
    - role: docker
      tags: [docker]
    - role: cache_link
      tags: [cache-link]
```

- [ ] **Step 8: Run the cases and watch them pass**

Run: `uv run pytest tests/test_infra_converge_guards.py tests/test_zcache_probe.py -q -p no:cacheprovider -k "mesh or zcache"`
Expected: `26 passed`: the 22 mesh and zcache cases of `tests/test_infra_converge_guards.py` and the four of `tests/test_zcache_probe.py`.

- [ ] **Step 9: The consumers**

The union of `grep -rlE 'host_vars|group_vars|site\.yml|roles/\*|ROLES|shell_templates|infra/ansible/roles' tests/test_*.py` as it read when this section was written, with `tests/test_internal_terms_not_operator_visible.py` (it walks every task name, `fail_msg`, `msg`, `.sh.j2` line and `Description=` under `infra/`), `tests/test_config_selectors_are_parsed.py` (it reads every test module for substring selectors, the new `tests/test_zcache_probe.py` among them) and the new module itself:

Run: `uv run pytest tests/test_capture_prune.py tests/test_capture_segment_writer.py tests/test_clock_offset.py tests/test_config.py tests/test_config_selectors_are_parsed.py tests/test_converge_sh.py tests/test_dashboards_cover_metrics.py tests/test_deploy_log_audit.py tests/test_engine_flatten_wrapper.py tests/test_engine_journal_prune.py tests/test_fleet_contracts.py tests/test_grafana_auth.py tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py tests/test_infra_archive_pull_template.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_infra_firewall_template.py tests/test_infra_grafana_keepalive.py tests/test_infra_shell_templates_render.py tests/test_infra_tape_bars_template.py tests/test_infra_tmux_conf_no_window_size_manual.py tests/test_infra_unattended_upgrades.py tests/test_infra_verify_replay_template.py tests/test_internal_terms_not_operator_visible.py tests/test_merge_gate.py tests/test_mint_with_vaulted_key_sh.py tests/test_ops_daily.py tests/test_probe_with_vaulted_key_sh.py tests/test_reboot_check.py tests/test_run_sh.py tests/test_systemd_user_units.py tests/test_zcache_probe.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a data gate, none failed. `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` passing is the check that no new role or node var file names the venue.

- [ ] **Step 10: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed, `ansible-lint` over `infra/ansible/` and shellcheck over the probe script included; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 11: Commit**

```bash
git add infra/ansible/roles/cache_link infra/ansible/host_vars/zcrypto/vars.yml infra/ansible/host_vars/zcrypto-valkey1/vars.yml infra/ansible/host_vars/zcrypto-valkey2/vars.yml infra/ansible/host_vars/zcrypto-valkey3/vars.yml infra/ansible/site.yml tests/test_infra_converge_guards.py tests/test_zcache_probe.py
git commit -m "feat(cache): the zcache WireGuard mesh, one role on the engine host and the three nodes

\`roles/cache_link\` renders /etc/wireguard/zcache0.conf from one peer list, the whole mesh in its
defaults: the engine host at 10.98.0.1 and the nodes at .11, .12 and .13, each endpoint the
member's public IPv4 on 51821, each peer's AllowedIPs its /32, PersistentKeepalive 25, and every
member but the one named inventory_hostname rendered, so each conf names the other three. MTU
1380, the fleet's one tunnel MTU, which a case holds equal to the zaccess tunnel's: no path of this
mesh has been measured and one crosses regions, and 1380 fits any path of 1440 bytes or more at 40
bytes a packet against wg-quick's 1420. Each member's address and private key come from its
host_vars, the key wired from \`cache_wg_<member>_private_key\` in group_vars/all/vault.yml, the
public halves \`cache_wg_<member>_public_key\` in group_vars/all/vars.yml. Neither half exists in
this commit: the keypairs are an attended step, and until they land the role refuses to converge.

The role's first task refuses a peer list whose members do not each carry their own name, address
and 44-character public key, whose addresses are not bare host addresses in 10.98.0.0/24 -- the
template appends /32, so a prefixed address is the one way to an AllowedIPs wider than a host --,
or in which this host is not exactly one entry at its own cache_link_address, which is how it would
be rendered as its own peer; and a member missing its address or a 44-character private key. It
runs first because the conf task is no_log and would hide which variable was undefined. The conf
renders at 0600 root with no_log and diff false; wg-quick@zcache0 is enabled and started, a changed
conf restarts it, and both skip exactly the first-run dry run, where wireguard-tools was never
installed and systemd cannot find the unit, the engine role's shape for its own unit.

\`zcache-probe\`, a one-minute root timer on all four members, reads the peers from the rendered
conf's \`AllowedIPs = <address>/32\` lines and writes \`zcache_wireguard_handshake_age_seconds\`
per peer, labelled by its mesh address, into the Alloy textfile directory: +Inf for a peer that
never handshook, one the interface no longer lists, or a tunnel that is down, so a rule over the age
fires there rather than reading no data.

site.yml gains the cache nodes' play (base, hardening, firewall, fail2ban, chrony, docker,
cache_link) and the engine play the role under \`cache-link\`, ahead of the engine role; the capture
play's always-tagged converge_primary guard still decides whether the primary converges at all.

Cases: the committed mesh passes the guard on each of the four members; eleven spoiled peer lists
refused; the conf rendered for each member names each other member once, as one host, at its
endpoint and key; each member's public key is one variable, set in no host_vars; the three port
declarations and the scoped interface agree; the mesh's MTU is the zaccess tunnel's. The probe,
driven over a fixture conf and a stub wg: a peer's age, +Inf for a peer with no handshake and for
one absent from the interface, every peer +Inf on a down interface, a conf naming no peer refused
with nothing published; the unit's conf and directory.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

The executor writes its own model name for `<model>`.

- [ ] **Step 12: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 13: Prove the guards with fifteen probes, then record their verdicts by a message-only amend**

Seven over the guard, its control renaming the task so `find_task` finds nothing: each removes one condition, or loosens the private-key length, and a spoiled list only that condition refuses survives otherwise. Three over the conf template, its control zeroing the keepalive: this host rendered as its own peer, AllowedIPs widened to /24, the MTU back at wg-quick's 1420. Two over the defaults, their control renaming the interface: the listen port moved off the firewalls' 51821, and valkey2's public key wired from valkey3's variable. Three over the probe script, their control renaming the published family: a peer with no handshake published as 0, the no-peer refusal disarmed, the interface's handshakes ignored.

```bash
C_GUARD='s/^- name: refuse a mesh whose peers are not one host address each/- name: refuse a mesh whose peers are not one address each/'
for M in "/regex_replace/d" \
         "/map(attribute='address') | unique/d" \
         "/selectattr('name', 'equalto', inventory_hostname)/d" \
         "/map(attribute='public_key') | unique/d" \
         "/map('length')/d" \
         "/map(attribute='name') | unique/d" \
         "s/(cache_link_private_key | length) == 44/(cache_link_private_key | length) > 0/"; do
  infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache_link/tasks/main.yml \
    --control "$C_GUARD" --mutation "$M" \
    -- uv run pytest tests/test_infra_converge_guards.py -q -p no:cacheprovider -k mesh_guard
done
for M in 's/ if peer.name != inventory_hostname %}/ %}/' \
         's#^AllowedIPs = {{ peer.address }}/32$#AllowedIPs = {{ peer.address }}/24#' \
         's/^MTU = 1380$/MTU = 1420/'; do
  infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache_link/templates/zcache0.conf.j2 \
    --control 's/^PersistentKeepalive = 25$/PersistentKeepalive = 0/' --mutation "$M" \
    -- uv run pytest tests/test_infra_converge_guards.py -q -p no:cacheprovider -k zcache
done
for M in 's/^cache_link_listen_port: 51821$/cache_link_listen_port: 51820/' \
         's/{{ cache_wg_zcrypto_valkey2_public_key }}/{{ cache_wg_zcrypto_valkey3_public_key }}/'; do
  infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache_link/defaults/main.yml \
    --control 's/^cache_link_interface: zcache0$/cache_link_interface: zcache1/' --mutation "$M" \
    -- uv run pytest tests/test_infra_converge_guards.py -q -p no:cacheprovider -k zcache
done
P=tests/test_zcache_probe.py
N_PROBE="$P::test_each_configured_peer_gets_its_age_and_a_peer_with_no_handshake_reads_infinite $P::test_a_down_interface_reads_every_configured_peer_as_infinite $P::test_a_config_naming_no_peer_fails_and_publishes_nothing"
for M in 's/else age=+Inf; fi/else age=0; fi/' \
         's/ -gt 0 \] || { echo/ -ge 0 ] || { echo/' \
         's/handshake\[\${allowed%\/32}\]=\$latest/:/'; do
  infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache_link/files/zcache-probe.sh \
    --control 's/zcache_wireguard_handshake_age_seconds{peer=/zcache_wg_age{peer=/' --mutation "$M" \
    -- uv run pytest $N_PROBE -q -p no:cacheprovider
done
```

`$N_PROBE` is left unquoted on purpose: it holds three node ids that must reach pytest as separate words. Expected: each of the fifteen runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `infra/ansible/roles/cache_link/tasks/main.yml`,
control the guard's task name changed so its lookup fails, through `-k mesh_guard`: the network
condition removed, KILLED, control proven; the address uniqueness removed, KILLED, control
proven; the own-entry condition removed, KILLED, control proven; the public-key uniqueness
removed, KILLED, control proven; the public-key length removed, KILLED, control proven; the name
uniqueness removed, KILLED, control proven; the private-key length loosened to any, KILLED,
control proven; over `infra/ansible/roles/cache_link/templates/zcache0.conf.j2`, control the
keepalive zeroed, through `-k zcache`: this host rendered as its own peer, KILLED, control proven;
AllowedIPs widened to /24, KILLED, control proven; the MTU at wg-quick's 1420, KILLED, control
proven; over `infra/ansible/roles/cache_link/defaults/main.yml`, control the interface renamed,
through `-k zcache`: the listen port moved off the firewalls' 51821, KILLED, control proven;
valkey2's public key wired from valkey3's variable, KILLED, control proven; over
`infra/ansible/roles/cache_link/files/zcache-probe.sh`, control the published family renamed,
through the three script cases of `tests/test_zcache_probe.py`: a peer with no handshake published
as 0, KILLED, control proven; the no-peer refusal disarmed, KILLED, control proven; the
interface's handshakes ignored, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

**Operator steps (attended)**

These are not executor steps: the owner runs them. `W$` is the workstation at the root of a checkout of this branch; O1 is `## Rollout (attended)` step P2, run before the pull request opens, and O2 is step R3's first half, run from merged `develop`; the mesh converges and their reads are R3's. No command prints a private key: each private half passes from `wg genkey` to `ansible-vault` through a shell variable and a pipe, never an argument or a file.

O1. The four keypairs, on this branch after Task 3's commit and before its pre-review.

```
W$ command -v wg || sudo apt install wireguard-tools
W$ for h in zcrypto zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3; do
     v="cache_wg_${h//-/_}"
     priv="$(wg genkey)"
     printf '%s_public_key: "%s"\n' "$v" "$(printf '%s' "$priv" | wg pubkey)"
     printf '%s' "$priv" | uv run ansible-vault encrypt_string --vault-password-file infra/ansible/scripts/vault-pass.sh --stdin-name "${v}_private_key"
     unset priv
   done
```

The loop prints, per member, one `cache_wg_<member>_public_key: "..."` line and one `cache_wg_<member>_private_key: !vault |` block. Append the four public lines to `infra/ansible/group_vars/all/vars.yml` under a blank line and the comment `# The zcache mesh (roles/cache_link): each member's public half; the private halves are the !vault scalars cache_wg_<member>_private_key in vault.yml beside this file.`. Paste the four blocks into `infra/ansible/group_vars/all/vault.yml` directly after the `zaccess_wg_preshared_key` block, under the comment `# zcache WireGuard mesh (roles/cache_link): the four members' private halves; publics in group_vars/all/vars.yml`. In that file's header, change `# four of these DO render onto managed hosts` to `# eight of these DO render onto managed hosts`, `Four of the nine values ARE` to `Eight of the thirteen values ARE`, `Three are WireGuard secrets:` to `Seven are WireGuard secrets, three of them the zaccess tunnel's:`, and replace the line `# public key. The fourth is \`grafana_ro_token\`, rendered onto \`zcrypto-ops\` alone by \`roles/ops\`'s` with these four lines:

```
# public key. The four `cache_wg_<member>_private_key` render each onto its own member of the zcache
# mesh by `roles/cache_link`, templating `/etc/wireguard/zcache0.conf`; rotating one needs a converge
# of all four members, since every other member's peer block carries its public key. The eighth is
# `grafana_ro_token`, rendered onto `zcrypto-ops` alone by `roles/ops`'s
```

Check each private half against its public half without printing either secret (the header's read recipe, piped into `wg pubkey`):

```
W$ for h in zcrypto zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3; do
     v="cache_wg_${h//-/_}"
     awk -v v="${v}_private_key:" '$1==v{f=1;next} /^[^ ]/{f=0} f && NF' infra/ansible/group_vars/all/vault.yml \
       | sed 's/^ *//' | uv run ansible-vault decrypt --vault-password-file infra/ansible/scripts/vault-pass.sh --output - | wg pubkey
     grep "^${v}_public_key:" infra/ansible/group_vars/all/vars.yml
   done
```

Expected: for each member, the derived key equals the quoted value on the line below it. Then `uv run pre-commit run -a` until clean and `uv run pytest tests/test_infra_converge_guards.py -q -p no:cacheprovider -k "mesh or zcache"` (`22 passed`), and commit the two files alone:

```
W$ git add infra/ansible/group_vars/all/vars.yml infra/ansible/group_vars/all/vault.yml
W$ git commit -m "feat(fleet): the zcache mesh's four WireGuard keypairs

The private halves are vaulted in group_vars/all/vault.yml as cache_wg_<member>_private_key and
the public halves are plain in group_vars/all/vars.yml; each private half was checked against its
public half by deriving it through the vault read recipe into wg pubkey. The vault header's custody
paragraph counts them: eight of thirteen values now render onto managed hosts.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

O2. The Cloud Firewall, by hand; nftables opens the same port in the role, and the two layers are maintained separately. In Linode Cloud Manager, Firewalls, open `zcrypto-cache` (the firewall Task 1's operator steps attach to the three nodes) and add an inbound rule: label `zcache-mesh`, protocol UDP, port `51821`, sources the four members' IPv4 addresses as `/32` (`172.105.64.43/32`, `172.104.159.221/32`, `139.162.163.39/32`, `172.233.51.246/32`; a node's own address among them admits nothing it does not already send itself), action Accept. For `zcrypto`, open Linodes, `zcrypto`, Network, Firewalls: when a firewall is attached, add the same rule with the three nodes' addresses as sources; when none is attached, nftables is that host's only inbound layer. No TCP rule for 6379 or 26379 is added on either layer: those ports are accepted on `zcache0` alone.

O3. The mesh converges, the nodes' `--tags firewall,cache-link` one per run and then the engine host's `--limit zcrypto --tags firewall,cache-link -e converge_primary=true` inside an inter-cycle gap after a whole read of Kraken's maintenance feed, and their reads on all four members, are `## Rollout (attended)` step R3.

---

### Task 4: The cache role: Valkey and Sentinel on the three nodes, one pinned image, their configs theirs after the first render

*Rulings: R2 gated the Valkey and Sentinel tasks on `cache_image_digest is defined` with no role default; R5 added the two container names to `ops_daily.py`'s `_PROTECTED_OBJECTS`; R8 appended the `cache` role to Task 3's `cache_host` play; R9 recorded the six Valkey and Sentinel headroom pairs absent for good, with its reason; R10 renamed the containers `zcrypto-valkey` and `zcrypto-sentinel`; R11 moved the exporter ACL read into this task's operator block, before the first converge; R20 added the engine line's `@keyspace`, `@read` and `@write` assertion; R1 and R18 moved the converges to the Rollout, one run carrying both digests; the coordinator's ruling on the reboot flag added a copy of the capture role's reboot check, so the nodes publish `node_reboot_required`.*

This task builds `roles/cache` (spec D2, D3, D7, D8, D9, D14) and its tests. It converges nothing: the attended rollout is `## Rollout (attended)`, whose steps R5, R6 and R9 run this role's converges, reads and records after the branch merges; this task's **Operator steps (attended)** are the two that land on the branch first. The decisions below are the ones the spec leaves to the plan; each is taken here and the code follows it.

- The Valkey and Sentinel tasks are one block gated `when: cache_image_digest is defined`, the ops role's convention, and `cache_image_digest` has no role default: a converge without the digest, the mesh's or an Alloy-only one, skips the block; one with it asserts the digest non-empty, pre-staged on the node and, when a container already runs, recorded in `docs/reference/fleet-pins.md`, before anything is rendered.
- `cache_config_reset` is read by the render inside that block alone, so a reset converge without the digest would skip every render and exit 0 with nothing applied. A refusal before the block, `refuse a config reset without the pinned image digest`, turns that converge away, and every published reset form carries the digest: the Global Constraints, Task 1's recorded converge, the drift report's remedy, and the runbook's `cache-config-reset` and `cache-password-rotation`, which read the digest the node runs before its containers stop.

- The containers run as a dedicated host account, `zcrypto-cache` (system, nologin), whose uid/gid the role reads with `getent`, the engine role's idiom, and not as the image's uid 999: a Debian host can hand uid 999 to a system user of its own, and the files the daemons write (AOF, RDB, rewritten configs) are then owned by a name. The official image's entrypoint skips its `chown`/`setpriv` step when the container is not started as root, so nothing in the image needs uid 999.
- The daemon-owned configs live in `{{ cache_state_dir }}/conf/` (`/var/lib/zcrypto-cache/conf`), owned by `zcrypto-cache` at 0700, bind-mounted read-write as a directory at `/etc/valkey` into both containers: Valkey's `CONFIG REWRITE` and Sentinel's state writes replace their file by renaming a temporary file beside it, which a single-file mount refuses. Valkey's data is `{{ cache_state_dir }}/data` at `/data`, the image's workdir, mounted into Valkey alone.
- `users.acl` joins `valkey.conf` and `sentinel.conf` as rendered only when absent or under `-e cache_config_reset=true`. Rendered on every converge, a rotated replica password would reach `users.acl` and restart the node while every node's `masterauth` in its daemon-owned `valkey.conf` still carried the old one, breaking replication on a routine converge. With all three coupled, a routine converge applies no changed password and the drift report names each file one moves; the change itself is `cache-password-rotation` in `infra/runbooks/cache.md` (Task 5), the three nodes' files replaced in one stop, since the nodes authenticate to each other and a node reset alone to a new password fails against the two still holding the old one. `cache-config-reset`, one node per converge, is for a template change.
- `users.acl` carries each password as `#<sha256>`, never in the clear. `valkey.conf` (`masterauth`) and `sentinel.conf` (`requirepass`, `sentinel auth-pass`) carry theirs in the clear, which Valkey requires; all three are 0600 `zcrypto-cache`, rendered `no_log: true` and `diff: false`.
- The render record is `{{ cache_compose_dir }}/rendered-sha256.yml`, a YAML map `<file>: '<sha256>'` (root 0600), one line per file maintained by `lineinfile`, rather than a `sha256sum`-format file: the role reads it back with `from_yaml`. The hash is of the template's render on the controller (`lookup('ansible.builtin.template', ...) | hash('sha256')`) both when recording and when comparing, so the two sides hash the same bytes.
- Drift is an `assert` looped over the three files with `ignore_errors: true` and a `register`, so a converge whose template moved prints a red `...ignoring` with the remedy and counts `ignored=1` in the recap without failing the node: a fatal drift check would block every re-pin of the node until a reset, and a reset is a replication change the runbook's `cache-config-reset` and `cache-password-rotation` procedures own (D9: "visible without being applied"). A file rendered in the same run is skipped, and an unrecorded file reads as no drift.
- The password refusal is five or more characters from `[A-Za-z0-9]`, over all five keys: five is spec D8's floor, and letters and digits because each password lands unquoted in `valkey.conf`, `sentinel.conf` and the proxy's `tcp-check` lines, where a space or a quote splits it. The message names the failing keys and never a value. The operator recipe generates 48 hex characters.
- Sentinel authenticates clients by `requirepass` alone (spec D8): the Sentinel exporter and the proxy's checks present it, so no ACL user is defined on the Sentinel port. The data node's ACL users are four: `engine` (`~* &* +@all -@dangerous +keys +info`: every key, and nothing from `@dangerous` but `KEYS`, with which the library's Redis backing lists its keys, and `INFO`, whose `redis_version` line the library's version check parses; `FLUSHDB`, `FLUSHALL`, `CONFIG`, `DEBUG`, `SHUTDOWN`, `REPLICAOF` and `CLIENT KILL` stay refused, so a `flush_on_start=True` misconfiguration cannot empty the cache, and the library logs the refusal on its native side alone, which reaches no log store; `&*` is kept because pub/sub carries no data here and the spec gives the engine every key), `replica` (`+psync +replconf +ping`, valkey.io's replication ACL), `sentinel` (valkey.io's documented Sentinel grant `&* +multi +slaveof +ping +exec +subscribe +config|rewrite +role +publish +info +client|setname +client|kill +script|kill`, plus `+replicaof`, the command's current name, so the grant holds whichever name the pinned Sentinel sends), and `exporter` (the read-only ACL line of the redis_exporter v1.86.0 README, the version Alloy v1.19.2 embeds, less three of its tokens: `+arcount`, a command Valkey 9.1.2 does not know, so an `aclfile` naming it aborts Valkey's start, and `+cluster|slots` and `+cluster|nodes`, which serve a cluster-mode server this set does not run; operator step O2 re-reads the README at the embedded version before the branch merges). `default` is `off`.
- `valkey-cli` reads on a node take their password from two root-only env files the role renders, `{{ cache_compose_dir }}/cli-exporter.env` and `cli-sentinel.env` (`VALKEYCLI_AUTH`, and `REDISCLI_AUTH`, the name valkey-cli still honours), through `docker exec --env-file`, so no password is ever an argument on a command line or in a shell history.
- The unit is a template (`zcrypto-cache.service.j2`) so its paths follow `cache_compose_dir`; its `ExecStartPre` pull carries systemd's `-` prefix because the converge's preflight has already pre-staged the digest, and a Docker Hub outage at boot must not hold the cache down. It orders after `wg-quick@zcache0.service` and wants it, without requiring it, so a tunnel restart does not stop the daemons.
- `cache_replica_priority` has no role default: each node's `host_vars` carries it (100, 100, 250), so a node missing it fails the render loudly instead of joining at a default priority.
- The headroom map (`tests/test_infra_alert_rules.py`) gains the compose file with six (host, job) pairs, the jobs `valkey` and `sentinel` that Task 5's exporters ship under, and records all six in `_HEADROOM_DELIBERATELY_ABSENT` for good (ruling R9): the headroom rules parse `process_resident_memory_bytes`, which neither daemon publishes; Valkey's memory is `zcrypto-cache-memory-70pct`'s against `maxmemory` (Task 5), and Sentinel has no memory family. Task 5 leaves the six entries as they are; `## Spec amendments` records the departure from spec D7's every-cap-a-leg.
- The nodes publish `node_reboot_required` from a copy of the capture role's reboot check, `zcrypto-reboot-check` (the script, the 15-minute timer and the `ProtectSystem=strict` oneshot), writing `reboot.prom` into `cache_textfile_dir`, `/var/lib/zcrypto-node-textfile`, the directory the node's Alloy reads and Task 3's mesh probe writes. Its tasks sit outside the digest gate, since the flag publishes whatever a converge carries, and the timer's enable skips the first-install preview as the unit's does. The copies differ from the capture role's in their comments alone, which `tests/test_reboot_check.py` holds, and carry no word the venue's name spells, since the deploy-log audit walks the roles directory.
- `infra/scripts/ops_daily.py`'s `_PROTECTED_OBJECTS` gains `zcrypto-valkey`, `zcrypto-sentinel`, `zcrypto-cache` and `zcache0`: Task 1 made the cache nodes telemetry hosts, whose `docker` and `systemctl` restarts, stops and starts the daily pass may take on its own, and restarting Valkey or Sentinel is a replication event, a failover when the node holds the primary, which stays the operator's. The veto is a substring test over the step, so each spelling a runbook step uses is an entry: the two containers, the unit `zcrypto-cache.service` that starts and stops both (the runbook's steps restart, stop and start a node through it, and `zcrypto-cache` covers it with or without its suffix), and the tunnel `wg-quick@zcache0`, whose restart drops the node's replication links for its seconds. The veto reads the mutation shapes alone, so reads naming the same objects keep their tier. Alloy's restart there stays the pass's.

**Files:**
- Create: `infra/ansible/roles/cache/defaults/main.yml`
- Create: `infra/ansible/roles/cache/handlers/main.yml`
- Create: `infra/ansible/roles/cache/tasks/main.yml`
- Create: `infra/ansible/roles/cache/templates/compose.yaml.j2`
- Create: `infra/ansible/roles/cache/templates/valkey.conf.j2`
- Create: `infra/ansible/roles/cache/templates/sentinel.conf.j2`
- Create: `infra/ansible/roles/cache/templates/users.acl.j2`
- Create: `infra/ansible/roles/cache/templates/cli-exporter.env.j2`
- Create: `infra/ansible/roles/cache/templates/cli-sentinel.env.j2`
- Create: `infra/ansible/roles/cache/templates/zcrypto-cache.service.j2`
- Create: `infra/ansible/roles/cache/files/zcrypto-reboot-check.sh` (mode `0755`), `infra/ansible/roles/cache/files/zcrypto-reboot-check.timer`, `infra/ansible/roles/cache/templates/zcrypto-reboot-check.service.j2`
- Modify: `infra/ansible/host_vars/zcrypto-valkey1/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`, `infra/ansible/host_vars/zcrypto-valkey3/vars.yml` (created by Task 1; two lines appended at the end of each)
- Modify: `infra/ansible/site.yml` (the `cache_host` play's `roles:` list, below its `cache_link` entry)
- Modify: `infra/scripts/ops_daily.py` (`_PROTECTED_OBJECTS`, the line `    "zcrypto-red",`)
- Test: `tests/test_infra_cache_templates.py` (new)
- Test: `tests/test_infra_compose_templates.py` (line 15 `OPS_DEFAULTS = ...`; lines 63-71, the end of `OPS_CONTEXT` through `_IDS`; the two blank lines before line 129 `# infra/nas/compose.yaml is not Ansible-rendered, ...`)
- Test: `tests/test_infra_converge_guards.py` (a block appended at the end of the file, after the last line of Task 3's mesh block, `    assert [rule["iface"] for rule in scoped] == [defaults["cache_link_interface"]], scoped`)
- Test: `tests/test_infra_alert_rules.py` (line 1272 `    "infra/docker/compose.yaml": (),` and the `}` after it; the comment line `# (host, job) with a limit and no headroom leg, each with the reason it is left out.`; lines 1288-1290, the end of the agentboard entry through the `}` closing `_HEADROOM_DELIBERATELY_ABSENT`)
- Test: `tests/test_ops_daily.py` (one case appended after Task 1's `test_a_cache_node_is_a_telemetry_host_under_either_of_its_names`)
- Test: `tests/test_reboot_check.py` (a block appended after `test_the_timer_actually_repeats`, the file's last case)
- Created by the operator, not the executor: `infra/ansible/group_vars/cache_host/vault.yml` (operator step O1); rows in `docs/reference/fleet-pins.md` and `docs/reference/deploy-log.jsonl` (`## Rollout (attended)` step R9)

**Interfaces:**
- Consumes: the inventory group `cache_host` holding `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`, each with `infra/ansible/host_vars/<host>/vars.yml` (Task 1); `cache_link_address` in each node's `host_vars` file, the node's `zcache0` address `10.98.0.11`/`.12`/`.13` (Task 3); the `cache_host` play in `site.yml` running base, hardening, firewall, fail2ban, chrony, docker and `cache_link` (Task 3); the firewall's interface-scoped accept of 6379 and 26379 on `zcache0` (Task 2); `converge.sh`'s whitelists admitting the three hosts, the tag `cache` and the keys `cache_image_digest`, `cache_alloy_digest` and `cache_config_reset` (Task 1); `ops_daily.py`'s telemetry hosts holding the three nodes (Task 1); in the tests, `load_tasks`, `find_task`, `truthy`, `assert_that`, `when_conditions`, `task_index`, `iter_tasks`, `Templar`, `DataLoader`, `yaml`, `pytest` in `tests/test_infra_converge_guards.py`, and `_render`, `_CASES`, `_IDS`, `yaml`, `pytest` in `tests/test_infra_compose_templates.py`, all existing.
- Produces: the role `cache` under the tag `cache`, its Valkey and Sentinel block gated on `cache_image_digest is defined`; the unit `zcrypto-cache.service`; the compose directory `/opt/zcrypto-cache` and the state directory `/var/lib/zcrypto-cache`; the containers `zcrypto-valkey` (port 6379) and `zcrypto-sentinel` (port 26379) on loopback and the node's `zcache0` address; the master name `zcache`; the ACL users `engine`, `replica`, `sentinel`, `exporter` and Sentinel's `requirepass`; the five vault keys `cache_engine_password`, `cache_replica_password`, `cache_sentinel_password` (the Valkey-side `sentinel` user's), `cache_sentinel_requirepass` (Sentinel's own), `cache_exporter_password` in `group_vars/cache_host/vault.yml` (the second plan's proxy reads `cache_sentinel_requirepass` and its engine wiring `cache_engine_password`; Task 5 reads `cache_exporter_password` and `cache_sentinel_requirepass`); the read forms `/opt/zcrypto-cache/cli-exporter.env` and `/opt/zcrypto-cache/cli-sentinel.env` for Task 5's runbook; the extra var `cache_config_reset`, refused without `cache_image_digest`, and the drift report whose message points at the `cache-config-reset` and `cache-password-rotation` procedures in `infra/runbooks/cache.md` (Task 5 writes them); the six `_HEADROOM_DELIBERATELY_ABSENT` entries over the jobs `valkey` and `sentinel`, which stay; the four protected objects in `ops_daily.py`, the two container names, the unit's and the tunnel's; `cache_textfile_dir` and the `zcrypto-reboot-check` timer publishing `node_reboot_required` into its `reboot.prom`, which Task 5 admits and charts.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_infra_cache_templates.py` with this content:

```python
"""The cache role's daemon-owned configs, rendered through Ansible's own templar over the role's defaults and each
node's host_vars: what a node starts from on its first render or a reset."""

import hashlib
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/cache"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
NODES = ("zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")
PASSWORDS = {
    "cache_engine_password": "engine0pw",
    "cache_replica_password": "replica0pw",
    "cache_sentinel_password": "sentinel0pw",
    "cache_sentinel_requirepass": "requirepass0pw",
    "cache_exporter_password": "exporter0pw",
}


def _host_vars(host: str) -> dict:
    return yaml.safe_load((ANSIBLE / "host_vars" / host / "vars.yml").read_text())


def _render(name: str, host: str) -> str:
    # A default that templates another var is trusted, so it resolves over the node's vars the way the play resolves
    # it, and a changed default changes the render.
    defaults = {k: trust_as_template(v) if isinstance(v, str) and "{{" in v else v for k, v in DEFAULTS.items()}
    variables = {**defaults, **_host_vars(host), **PASSWORDS}
    text = (ROLE / "templates" / name).read_text()
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("host", NODES)
def test_the_first_primary_renders_no_replicaof_and_every_other_node_replicates_from_it(host):
    replicaof = [line for line in _lines(_render("valkey.conf.j2", host)) if line.startswith("replicaof")]
    if _host_vars(host)["cache_link_address"] == DEFAULTS["cache_first_primary"]:
        assert replicaof == [], f"{host} is the first primary and must start as one: {replicaof}"
    else:
        assert replicaof == [f"replicaof {DEFAULTS['cache_first_primary']} 6379"], replicaof


def test_exactly_one_node_is_the_first_primary():
    firsts = [h for h in NODES if _host_vars(h)["cache_link_address"] == DEFAULTS["cache_first_primary"]]
    assert firsts == ["zcrypto-valkey1"], firsts


@pytest.mark.parametrize("name", ["valkey.conf.j2", "sentinel.conf.j2"])
@pytest.mark.parametrize("host", NODES)
def test_valkey_and_sentinel_bind_loopback_and_the_mesh_address_alone(host, name):
    binds = [line for line in _lines(_render(name, host)) if line.startswith("bind ")]
    assert binds == [f"bind 127.0.0.1 {_host_vars(host)['cache_link_address']}"], binds


def test_promotion_prefers_the_engine_region_over_the_remote_copy():
    priorities = {h: _host_vars(h)["cache_replica_priority"] for h in NODES}
    assert priorities == {"zcrypto-valkey1": 100, "zcrypto-valkey2": 100, "zcrypto-valkey3": 250}, priorities
    for host in NODES:
        assert f"replica-priority {priorities[host]}" in _lines(_render("valkey.conf.j2", host))


@pytest.mark.parametrize(
    "line",
    [
        "appendonly yes",
        "appendfsync always",
        "save 3600 1 300 100 60 10000",
        "maxmemory 128mb",
        "maxmemory-policy noeviction",
        "min-replicas-to-write 1",
        "min-replicas-max-lag 10",
        "protected-mode yes",
        "aclfile /etc/valkey/users.acl",
        "masteruser replica",
    ],
)
def test_valkey_refuses_writes_without_a_replica_and_never_evicts(line):
    assert line in _lines(_render("valkey.conf.j2", "zcrypto-valkey2"))


def test_sentinel_monitors_the_first_primary_at_quorum_two():
    lines = _lines(_render("sentinel.conf.j2", "zcrypto-valkey3"))
    for expected in (
        "sentinel monitor zcache 10.98.0.11 6379 2",
        "sentinel down-after-milliseconds zcache 5000",
        "sentinel failover-timeout zcache 60000",
        "sentinel parallel-syncs zcache 1",
        "sentinel resolve-hostnames no",
        "sentinel announce-ip 10.98.0.13",
        "sentinel auth-user zcache sentinel",
        f"sentinel auth-pass zcache {PASSWORDS['cache_sentinel_password']}",
        f"requirepass {PASSWORDS['cache_sentinel_requirepass']}",
    ):
        assert expected in lines, expected


def _acl() -> dict[str, list[str]]:
    lines = [line for line in _render("users.acl.j2", "zcrypto-valkey1").splitlines() if line.strip()]
    assert all(line.startswith("user ") for line in lines), f"Valkey's ACL file takes `user` lines alone: {lines}"
    return {line.split()[1]: line.split()[2:] for line in lines}


def test_the_acl_file_carries_password_hashes_and_never_a_password():
    acl = _acl()
    text = _render("users.acl.j2", "zcrypto-valkey1")
    for name, secret in PASSWORDS.items():
        assert secret not in text, f"{name} is in users.acl in the clear"
    for user, key in (
        ("engine", "cache_engine_password"),
        ("replica", "cache_replica_password"),
        ("sentinel", "cache_sentinel_password"),
        ("exporter", "cache_exporter_password"),
    ):
        assert "#" + hashlib.sha256(PASSWORDS[key].encode()).hexdigest() in acl[user], user


def test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous():
    acl = _acl()
    assert acl["default"] == ["off"], acl["default"]
    engine = acl["engine"]
    assert engine[0] == "on" and "~*" in engine and "+@all" in engine
    dangerous = engine.index("-@dangerous")
    assert engine.index("+keys") > dangerous and engine.index("+info") > dangerous, engine
    assert not {"+flushdb", "+flushall", "+@admin"} & set(engine), engine
    # the library's reads and writes: a category subtracted here is a cache the engine cannot use
    assert not {"-@keyspace", "-@read", "-@write"} & set(engine), engine


def test_the_replica_and_sentinel_users_carry_what_their_documented_acls_grant():
    acl = _acl()
    assert set(acl["replica"][2:]) == {"+psync", "+replconf", "+ping"}, acl["replica"]
    sentinel = {"&*", "+slaveof", "+replicaof", "+config|rewrite", "+client|kill", "+role", "+info", "+subscribe", "+publish"}
    assert sentinel <= set(acl["sentinel"]), acl["sentinel"]
    assert "-@all" in acl["exporter"] and "+@all" not in acl["exporter"], acl["exporter"]
```

In `tests/test_infra_compose_templates.py`, replace line 15:

```python
OPS_DEFAULTS = REPO / "infra/ansible/roles/ops/defaults/main.yml"
```

with:

```python
OPS_DEFAULTS = REPO / "infra/ansible/roles/ops/defaults/main.yml"
CACHE_TEMPLATE = REPO / "infra/ansible/roles/cache/templates/compose.yaml.j2"
CACHE_DEFAULTS = yaml.safe_load((REPO / "infra/ansible/roles/cache/defaults/main.yml").read_text())
```

Replace lines 63-71:

```python
    "ops_compose_dir": "/etc/zcrypto-ops",
}

_CASES = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT),
    (OPS_TEMPLATE, OPS_CONTEXT),
]
_IDS = ["capture", "engine", "ops"]
```

with:

```python
    "ops_compose_dir": "/etc/zcrypto-ops",
}

# The paths and caps come from the role's defaults, so the render below reads the values a converge deploys.
CACHE_CONTEXT = {
    **{
        k: CACHE_DEFAULTS[k]
        for k in ("cache_image", "cache_compose_dir", "cache_state_dir", "cache_valkey_memory_limit", "cache_sentinel_memory_limit")
    },
    "cache_image_digest": "sha256:" + "d" * 64,
    "cache_uid": 996,
    "cache_gid": 996,
}

_CASES = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT),
    (OPS_TEMPLATE, OPS_CONTEXT),
    (CACHE_TEMPLATE, CACHE_CONTEXT),
]
_IDS = ["capture", "engine", "ops", "cache"]
```

Insert above the comment line `# infra/nas/compose.yaml is not Ansible-rendered, but shares the single-file bind-mount pattern the`, keeping two blank lines on each side:

```python
@pytest.mark.parametrize(
    ("service", "command", "limit"),
    [
        ("valkey", ["valkey-server", "/etc/valkey/valkey.conf"], "cache_valkey_memory_limit"),
        ("sentinel", ["valkey-sentinel", "/etc/valkey/sentinel.conf"], "cache_sentinel_memory_limit"),
    ],
)
def test_cache_valkey_and_sentinel_run_one_pinned_image_on_the_host_network(service, command, limit):
    """Sentinel announces and discovers its peers by address, which a published port rewrites; both daemons log to
    the journal, where the node's Alloy reads them."""
    spec = _render(CACHE_TEMPLATE, CACHE_CONTEXT)["services"][service]
    assert spec["image"] == f"{CACHE_DEFAULTS['cache_image']}@{CACHE_CONTEXT['cache_image_digest']}"
    assert spec["network_mode"] == "host" and "ports" not in spec
    assert spec["command"] == command
    assert spec["user"] == "996:996"
    assert spec["logging"] == {"driver": "journald"}
    assert spec["deploy"]["resources"]["limits"]["memory"] == CACHE_DEFAULTS[limit]
    # the directory, never the file: both daemons replace their config by renaming a file beside it
    assert f"{CACHE_DEFAULTS['cache_state_dir']}/conf:/etc/valkey" in spec["volumes"]


def test_cache_data_is_mounted_into_valkey_alone():
    services = _render(CACHE_TEMPLATE, CACHE_CONTEXT)["services"]
    data = f"{CACHE_DEFAULTS['cache_state_dir']}/data:/data"
    assert data in services["valkey"]["volumes"] and data not in services["sentinel"]["volumes"]
```

Append to `tests/test_infra_converge_guards.py`, at the end of the file, after the last line of Task 3's mesh block, `    assert [rule["iface"] for rule in scoped] == [defaults["cache_link_interface"]], scoped`, two blank lines and then:

```python


# --- the cache role: the capture role's digest and pins guards over Valkey and Sentinel, the password-shape refusal,
# and the daemon-owned configs rendered only when absent, their drift reported and never applied.
CACHE = ANSIBLE / "roles" / "cache" / "tasks" / "main.yml"
CACHE_HANDLERS = ANSIBLE / "roles" / "cache" / "handlers" / "main.yml"
CACHE_DEFAULTS = ANSIBLE / "roles" / "cache" / "defaults" / "main.yml"
CACHE_BLOCK = "install Valkey and Sentinel (needs the pinned image digest)"
CACHE_FAILFAST = "fail fast if the pinned cache image digest was not supplied"
CACHE_PREFLIGHT = "preflight — refuse a digest the host has not pulled"
CACHE_PINS = "pins recording — refuse to replace a digest fleet-pins.md does not record"
CACHE_PINS_ECHO = "pins override accepted — the reason, on the record"
CACHE_PASSWORDS = "refuse a cache password shorter than five characters or outside letters and digits"
CACHE_RENDER = "render the daemon-owned configs when absent, or under cache_config_reset"
CACHE_DRIFT = "drift — report a daemon-owned config whose template no longer renders what this node was given"
CACHE_CLI_ENV = "render the root-only valkey-cli credential files"
CACHE_RESET_NEEDS_DIGEST = "refuse a config reset without the pinned image digest"
CACHE_PASSWORD_NAMES = (
    "cache_engine_password",
    "cache_replica_password",
    "cache_sentinel_password",
    "cache_sentinel_requirepass",
    "cache_exporter_password",
)
CACHE_GOOD_PASSWORDS = {name: "a1B2c3D4e5" for name in CACHE_PASSWORD_NAMES}


def _template(expr: str, variables: dict):
    from ansible.template import trust_as_template

    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(expr))


def test_cache_digest_failfast_refuses_an_empty_digest():
    task = find_task(load_tasks(CACHE), CACHE_FAILFAST)
    assert not truthy(assert_that(task), {"cache_image_digest": ""})
    assert truthy(assert_that(task), {"cache_image_digest": "sha256:" + "d" * 64})


def test_the_valkey_and_sentinel_tasks_run_only_on_a_converge_carrying_the_digest():
    """A converge without the digest, the mesh's or an Alloy-only one, skips every task that reads it: the digest has
    no role default, so the gate is the ops role's `is defined`, and the fail-fast opens the block. The reset refusal
    before the block tests the digest with `is defined` alone."""
    tasks = load_tasks(CACHE)
    block = find_task(tasks, CACHE_BLOCK)
    assert when_conditions(block) == ["cache_image_digest is defined"]
    assert "cache_image_digest" not in yaml.safe_load(CACHE_DEFAULTS.read_text())
    assert block["block"][0]["name"] == CACHE_FAILFAST
    exempt = (CACHE_BLOCK, CACHE_RESET_NEEDS_DIGEST)
    outside = [t.get("name") for t in tasks if t.get("name") not in exempt and "cache_image_digest" in yaml.safe_dump(t)]
    assert outside == [], f"tasks outside the gated block read the digest: {outside}"


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({"cache_config_reset": "true"}, False),
        ({"cache_config_reset": "true", "cache_image_digest": "sha256:" + "d" * 64}, True),
        ({"cache_config_reset": False}, True),
    ],
    ids=["reset-without-digest", "reset-with-digest", "no-reset"],
)
def test_cache_config_reset_without_the_digest_is_refused_before_the_gate(variables, expected):
    """The reset re-renders inside the digest-gated block, so without the digest it would skip every render and exit
    0; the refusal sits before the block, where a converge without the digest still runs it."""
    tasks = load_tasks(CACHE)
    assert task_index(tasks, CACHE_RESET_NEEDS_DIGEST) < task_index(tasks, CACHE_BLOCK)
    assert truthy(assert_that(find_task(tasks, CACHE_RESET_NEEDS_DIGEST)), variables) is expected


def test_cache_empty_digest_failfast_precedes_residency_preflight():
    tasks = find_task(load_tasks(CACHE), CACHE_BLOCK)["block"]
    assert task_index(tasks, CACHE_FAILFAST) < task_index(tasks, CACHE_PREFLIGHT)


def test_cache_digest_preflight_refuses_an_unpulled_digest():
    task = find_task(load_tasks(CACHE), CACHE_PREFLIGHT)
    assert not truthy(assert_that(task), {"cache_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"cache_digest_probe": {"rc": 0}})


CACHE_PINS_BASE = {"cache_running_digest_probe": {"rc": 0, "stdout": "valkey/valkey@sha256:" + "d" * 64}}
CACHE_PINS_WITH = "| valkey + sentinel | zcrypto-valkey1 | `" + "d" * 12 + "` |"
CACHE_PINS_WITHOUT = "| valkey + sentinel | zcrypto-valkey1 | `" + "e" * 12 + "` |"
CACHE_PINS_REASON = "first pin recorded right after this converge"


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (CACHE_PINS_WITH, "", True),
        (CACHE_PINS_WITHOUT, "", False),
        (CACHE_PINS_WITHOUT, "true", False),
        (CACHE_PINS_WITHOUT, "short", False),
        (CACHE_PINS_WITHOUT, CACHE_PINS_REASON, True),
    ],
)
def test_cache_pins_recording_semantics(pins_text, override, expected):
    task = find_task(load_tasks(CACHE), CACHE_PINS)
    variables = {**CACHE_PINS_BASE, "cache_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [(CACHE_PINS_WITHOUT, CACHE_PINS_REASON, True), (CACHE_PINS_WITHOUT, "", False), (CACHE_PINS_WITH, CACHE_PINS_REASON, False)],
)
def test_cache_pins_override_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    task = find_task(load_tasks(CACHE), CACHE_PINS_ECHO)
    variables = {**CACHE_PINS_BASE, "cache_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(task), variables) is expected


@pytest.mark.parametrize("name", CACHE_PASSWORD_NAMES)
@pytest.mark.parametrize(
    ("value", "expected"),
    [("abcd", False), ("abcde", True), ("", False), ("abc de", False), ("abc'de", False), ("abcde\n", False), ("a1B2c3D4e5", True)],
)
def test_cache_password_refusal(name, value, expected):
    task = find_task(load_tasks(CACHE), CACHE_PASSWORDS)
    assert truthy(assert_that(task), {**CACHE_GOOD_PASSWORDS, name: value}) is expected


def test_cache_password_refusal_names_the_key_and_never_the_value():
    task = find_task(load_tasks(CACHE), CACHE_PASSWORDS)
    variables = {**CACHE_GOOD_PASSWORDS, "cache_sentinel_requirepass": "ab c", "cache_exporter_password": "xyz"}
    message = _template(task["ansible.builtin.assert"]["fail_msg"], variables)
    assert message.startswith("cache_sentinel_requirepass, cache_exporter_password in group_vars/cache_host/vault.yml"), message
    assert "ab c" not in message and "xyz" not in message


@pytest.mark.parametrize(("reset", "expected"), [(False, False), ("false", False), (True, True), ("true", True)])
def test_cache_configs_render_only_when_absent_unless_reset(reset, expected):
    """`-e cache_config_reset=true` arrives as the string "true", so the string arms are the ones a converge passes."""
    task = find_task(load_tasks(CACHE), CACHE_RENDER)
    assert _template(task["ansible.builtin.template"]["force"], {"cache_config_reset": reset}) is expected


def test_cache_render_covers_the_daemon_files_and_each_has_a_template():
    task = find_task(load_tasks(CACHE), CACHE_RENDER)
    files = yaml.safe_load(CACHE_DEFAULTS.read_text())["cache_daemon_files"]
    assert task["loop"] == "{{ cache_daemon_files }}"
    assert files == ["valkey.conf", "sentinel.conf", "users.acl"], files
    assert all((CACHE.parents[1] / "templates" / f"{f}.j2").is_file() for f in files)


RENDERED = {"results": [{"item": "valkey.conf", "changed": True}, {"item": "sentinel.conf", "changed": False}]}


@pytest.mark.parametrize(
    ("recorded", "expected"),
    [({"sentinel.conf": "b" * 64}, True), ({"sentinel.conf": "a" * 64}, False), ({}, True)],
    ids=["recorded-and-matching", "recorded-and-drifted", "never-recorded"],
)
def test_cache_drift_reports_a_config_whose_template_moved(recorded, expected):
    task = find_task(load_tasks(CACHE), CACHE_DRIFT)
    variables = {"item": "sentinel.conf", "cache_recorded_sha": recorded, "cache_template_sha": {"sentinel.conf": "b" * 64}}
    assert truthy(assert_that(task), variables) is expected


def test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered():
    task = find_task(load_tasks(CACHE), CACHE_DRIFT)
    assert task.get("ignore_errors") is True, "a drift report that fails the play blocks every converge of the node until a reset"
    assert task.get("register"), "ansible-lint's ignore-errors rule admits an ignored failure only when its result is registered"
    assert not truthy(when_conditions(task), {"item": "valkey.conf", "cache_conf_render": RENDERED})
    assert truthy(when_conditions(task), {"item": "sentinel.conf", "cache_conf_render": RENDERED})


@pytest.mark.parametrize("name", [CACHE_RENDER, CACHE_CLI_ENV])
def test_every_cache_secret_render_is_never_logged_or_diffed(name):
    task = find_task(load_tasks(CACHE), name)
    assert task.get("no_log") is True and task.get("diff") is False, name
    assert task["ansible.builtin.template"]["mode"] == "0600", name


def test_every_cache_probe_never_fails_changes_or_skips_under_check():
    probes = [t for t, _ in iter_tasks(load_tasks(CACHE)) if str(t.get("name", "")).startswith("probe")]
    assert len(probes) >= 3, [t["name"] for t in probes]
    for probe in probes:
        modes = (probe.get("failed_when"), probe.get("changed_when"), probe.get("check_mode"))
        assert modes == (False, False, False), f"{probe['name']!r}: failed_when, changed_when, check_mode = {modes}"


@pytest.mark.parametrize(
    ("check_mode", "unit_changed", "expected"),
    [(True, True, False), (True, False, True), (False, True, True), (False, False, True)],
)
def test_the_cache_restart_handler_stands_down_only_on_a_first_install_preview(check_mode, unit_changed, expected):
    handler = find_task(load_tasks(CACHE_HANDLERS), "restart cache service")
    variables = {"ansible_check_mode": check_mode, "cache_unit_install": {"changed": unit_changed}}
    assert truthy(when_conditions(handler), variables) is expected
```

In `tests/test_infra_alert_rules.py`, replace the two lines ending `_LIMITED_JOBS`:

```python
    "infra/docker/compose.yaml": (),
}
```

with:

```python
    "infra/docker/compose.yaml": (),
    "infra/ansible/roles/cache/templates/compose.yaml.j2": (
        ("zcrypto-valkey1", "valkey"),
        ("zcrypto-valkey1", "sentinel"),
        ("zcrypto-valkey2", "valkey"),
        ("zcrypto-valkey2", "sentinel"),
        ("zcrypto-valkey3", "valkey"),
        ("zcrypto-valkey3", "sentinel"),
    ),
}
```

Replace the comment line above `_HEADROOM_DELIBERATELY_ABSENT`:

```python
# (host, job) with a limit and no headroom leg, each with the reason it is left out.
```

with:

```python
_CACHE_DAEMONS_UNLEGGED = (
    "Valkey exposes redis_memory_used_rss_bytes rather than the process family the fleet rule parses, and the cache "
    "group's zcrypto-cache-memory-70pct rule guards it against maxmemory; Sentinel exposes no memory family"
)
# (host, job) with a limit and no headroom leg, each with the reason it is left out.
```

and replace lines 1288-1290, the agentboard entry's close and the dict's:

```python
        "(`AGENTBOARD_PROPERTIES` in infra/scripts/ops_daily.py), off the host rather than off a series."
    )
}
```

with:

```python
        "(`AGENTBOARD_PROPERTIES` in infra/scripts/ops_daily.py), off the host rather than off a series."
    ),
    ("zcrypto-valkey1", "valkey"): _CACHE_DAEMONS_UNLEGGED,
    ("zcrypto-valkey1", "sentinel"): _CACHE_DAEMONS_UNLEGGED,
    ("zcrypto-valkey2", "valkey"): _CACHE_DAEMONS_UNLEGGED,
    ("zcrypto-valkey2", "sentinel"): _CACHE_DAEMONS_UNLEGGED,
    ("zcrypto-valkey3", "valkey"): _CACHE_DAEMONS_UNLEGGED,
    ("zcrypto-valkey3", "sentinel"): _CACHE_DAEMONS_UNLEGGED,
}
```

The six absences are listed one per line, not derived from the map, so deleting one is a failure the headroom test reports; Step 12's probe 27 proves it.

In `tests/test_ops_daily.py`, insert after Task 1's `test_a_cache_node_is_a_telemetry_host_under_either_of_its_names`:

```python
@pytest.mark.parametrize(
    "step",
    [
        "sudo docker restart zcrypto-valkey",
        "sudo docker stop zcrypto-sentinel",
        "ssh db2 sudo docker restart zcrypto-valkey",
        "sudo systemctl restart zcrypto-cache.service",
        "sudo systemctl stop zcrypto-cache.service",
        "sudo systemctl start zcrypto-cache",
        "ssh db2 sudo systemctl restart zcrypto-cache.service",
        "sudo systemctl restart wg-quick@zcache0",
    ],
)
def test_a_cache_daemon_restart_is_never_the_passs_own(step):
    """A cache node is a telemetry host, whose container restarts the pass may take; restarting, stopping or starting
    Valkey and Sentinel, by container or through their unit, is a replication event, a failover when the node holds the
    primary, and so is restarting the mesh tunnel replication runs over: each stays the operator's."""
    assert ops_daily.classify_action(step, host="zcrypto-valkey1", resolve=_identity) is ops_daily.Tier.PREPARED
```

Append at the end of `tests/test_reboot_check.py`, after `test_the_timer_actually_repeats`:

```python
# --- the cache role's copy ------------------------------------------------------------------------
# The cache nodes publish the same flag from a copy of this role's script, timer and unit, so the fleet's reboot-pending
# series covers them. The copies' comments are their own, naming the role that installs them; what a shell or systemd
# reads must be this role's, the unit's one variable renamed.
CACHE_ROLE = REPO / "infra/ansible/roles/cache"
REBOOT_CHECK_FILES = (
    "files/zcrypto-reboot-check.sh",
    "files/zcrypto-reboot-check.timer",
    "templates/zcrypto-reboot-check.service.j2",
)


def _program(path: Path) -> list[str]:
    """The lines a shell or systemd reads: every line but a blank or a whole-line comment."""
    return [line for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]


@pytest.mark.parametrize("relative", REBOOT_CHECK_FILES)
def test_the_cache_roles_reboot_check_is_the_capture_roles_program(relative):
    copy = [line.replace("cache_textfile_dir", "capture_textfile_dir") for line in _program(CACHE_ROLE / relative)]
    assert copy == _program(ROLE / relative), f"the cache role's {relative} drifted from the capture role's"


def test_the_cache_role_installs_what_its_unit_runs_and_enables_the_timer_alone():
    import yaml

    textfile_dir = yaml.safe_load((CACHE_ROLE / "defaults/main.yml").read_text())["cache_textfile_dir"]
    assert textfile_dir == "/var/lib/zcrypto-node-textfile", textfile_dir
    unit = (CACHE_ROLE / "templates/zcrypto-reboot-check.service.j2").read_text()
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    binary = exec_start.removeprefix("ExecStart=").split()[0]
    cache_tasks_yaml = (CACHE_ROLE / "tasks/main.yml").read_text()
    assert binary in _installed_dests(cache_tasks_yaml), f"the unit runs {binary}, which the cache role does not install"
    enabled = [
        t["ansible.builtin.systemd_service"]["name"]
        for t in _flatten(yaml.safe_load(cache_tasks_yaml))
        if "ansible.builtin.systemd_service" in t and t["ansible.builtin.systemd_service"].get("enabled")
    ]
    assert "zcrypto-reboot-check.timer" in enabled, f"the timer is not enabled: {enabled}"
    assert "zcrypto-reboot-check.service" not in enabled, f"the oneshot must not be enabled: {enabled}"
```

- [ ] **Step 2: Run the new tests and watch them fail**

Run: `uv run pytest tests/test_infra_cache_templates.py -q -p no:cacheprovider`
Expected: `1 error` at collection, `FileNotFoundError: [Errno 2] No such file or directory: '.../infra/ansible/roles/cache/defaults/main.yml'`.

Run: `uv run pytest tests/test_infra_compose_templates.py -q -p no:cacheprovider`
Expected: `1 error` at collection, the same `FileNotFoundError` from `CACHE_DEFAULTS`.

Run: `uv run pytest tests/test_infra_converge_guards.py::test_cache_digest_failfast_refuses_an_empty_digest tests/test_infra_converge_guards.py::test_the_valkey_and_sentinel_tasks_run_only_on_a_converge_carrying_the_digest tests/test_infra_converge_guards.py::test_cache_config_reset_without_the_digest_is_refused_before_the_gate tests/test_infra_converge_guards.py::test_cache_empty_digest_failfast_precedes_residency_preflight tests/test_infra_converge_guards.py::test_cache_digest_preflight_refuses_an_unpulled_digest tests/test_infra_converge_guards.py::test_cache_pins_recording_semantics tests/test_infra_converge_guards.py::test_cache_pins_override_echo_fires_only_on_an_accepted_override tests/test_infra_converge_guards.py::test_cache_password_refusal tests/test_infra_converge_guards.py::test_cache_password_refusal_names_the_key_and_never_the_value tests/test_infra_converge_guards.py::test_cache_configs_render_only_when_absent_unless_reset tests/test_infra_converge_guards.py::test_cache_render_covers_the_daemon_files_and_each_has_a_template tests/test_infra_converge_guards.py::test_cache_drift_reports_a_config_whose_template_moved tests/test_infra_converge_guards.py::test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered tests/test_infra_converge_guards.py::test_every_cache_secret_render_is_never_logged_or_diffed tests/test_infra_converge_guards.py::test_every_cache_probe_never_fails_changes_or_skips_under_check tests/test_infra_converge_guards.py::test_the_cache_restart_handler_stands_down_only_on_a_first_install_preview -q -p no:cacheprovider`
Expected: `67 failed`, each on `FileNotFoundError` for `infra/ansible/roles/cache/tasks/main.yml`, `.../defaults/main.yml` or `.../handlers/main.yml`.

Run: `uv run pytest tests/test_infra_alert_rules.py::test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence -q -p no:cacheprovider`
Expected: `1 failed`, `the memory-limited compose sources changed: [...] -- update the map`: the map names a compose file that does not exist yet.

Run: `uv run pytest tests/test_ops_daily.py::test_a_cache_daemon_restart_is_never_the_passs_own -q -p no:cacheprovider`
Expected: `8 failed`, each `Tier.AUTONOMOUS`: the node is a telemetry host and nothing yet protects the two containers, their unit or the tunnel.

Run: `uv run pytest tests/test_reboot_check.py -q -p no:cacheprovider -k cache`
Expected: `4 failed`, each on `FileNotFoundError` for a file under `infra/ansible/roles/cache/`.

- [ ] **Step 3: The role's defaults and its handler**

Create `infra/ansible/roles/cache/defaults/main.yml`:

```yaml
---
# The index digest of valkey/valkey 9.1.2 deliberately has no default: it is passed per run and
# pre-staged on the node first, and a converge without it skips the Valkey and Sentinel block:
#   -e cache_image_digest=sha256:<...>   (read it with `docker buildx imagetools inspect valkey/valkey:9.1.2`)
# Valkey and Sentinel both run from it, so one re-pin moves both.
cache_image: valkey/valkey

cache_compose_dir: /opt/zcrypto-cache
cache_state_dir: /var/lib/zcrypto-cache

# Valkey and Sentinel listen on loopback and this node's zcache0 address, never a public one.
cache_bind_address: "{{ cache_link_address }}"

cache_master_name: zcache
# Seeds a first render or a reset alone: once the daemons run, Sentinel decides which node is primary and writes
# `replicaof` into each node's own valkey.conf.
cache_first_primary: 10.98.0.11

# The gap between maxmemory and the Valkey cap is the AOF-rewrite child's copy-on-write.
cache_maxmemory: 128mb
cache_valkey_memory_limit: 256m
cache_sentinel_memory_limit: 64m

cache_down_after_ms: 5000
cache_failover_timeout_ms: 60000

# true re-renders the daemon-owned configs over what Valkey and Sentinel wrote into them, which resets this node's
# replication state: the converge of the reset and rotation procedures in infra/runbooks/cache.md,
# never a routine one.
cache_config_reset: false

# The node-exporter textfile directory the node's Alloy reads; the reboot check publishes reboot.prom
# into it, and the cache_link role's mesh probe its zcache.prom.
cache_textfile_dir: /var/lib/zcrypto-node-textfile

# The configs the daemons read, rendered only when absent or under cache_config_reset.
cache_daemon_files:
  - valkey.conf
  - sentinel.conf
  - users.acl
```

Create `infra/ansible/roles/cache/handlers/main.yml`:

```yaml
---
- name: restart cache service
  ansible.builtin.systemd_service:
    name: zcrypto-cache.service
    daemon_reload: true
    state: restarted
  # A first-install preview never wrote the unit, so systemd cannot find it.
  when: not (ansible_check_mode and cache_unit_install is changed)
```

- [ ] **Step 4: The role's tasks**

Create `infra/ansible/roles/cache/tasks/main.yml`:

```yaml
---
# Deploys Valkey and its Sentinel on a cache node as one compose project. The unit's own
# ExecStartPre/ExecStart/ExecStop pull and run it, which is also what resumes it on boot; Ansible
# starts, enables and restarts it. Roll the set one node per converge, replicas first, and move the
# primary with `SENTINEL failover` before converging it (infra/runbooks/cache.md).
# Outside the block below: the reset re-renders inside it, so a reset converge without the digest
# would skip every render and exit 0 with nothing applied.
- name: refuse a config reset without the pinned image digest
  ansible.builtin.assert:
    that: not (cache_config_reset | bool) or cache_image_digest is defined
    fail_msg: >-
      -e cache_config_reset=true re-renders this node's configs only on a converge that also carries
      -e cache_image_digest=sha256:<...>, the digest docs/reference/fleet-pins.md records for this node.

# Every task below reads or serves cache_image_digest, which has no role default and is passed per
# run, so the block is gated on it, the ops role's convention: a converge without the digest (the
# mesh's, or an Alloy-only one) skips all of it, and one with it asserts it non-empty, pre-staged
# and recorded in fleet-pins.md before anything is rendered.
- name: install Valkey and Sentinel (needs the pinned image digest)
  when: cache_image_digest is defined
  block:
    - name: fail fast if the pinned cache image digest was not supplied
      ansible.builtin.assert:
        that: cache_image_digest | length > 0
        fail_msg: >-
          cache_image_digest is empty — pass the valkey/valkey index digest, e.g.
          -e cache_image_digest=sha256:<...> (read it with `docker buildx imagetools inspect valkey/valkey:9.1.2`),
          pre-staged on this node.

    # Letters and digits alone: a password lands unquoted in valkey.conf, sentinel.conf and the proxy's
    # health-check lines, where a space or a quote splits it. Five characters is the floor below which
    # the engine's library logs the password unredacted at DEBUG.
    - name: refuse a cache password shorter than five characters or outside letters and digits
      ansible.builtin.assert:
        that: >-
          [cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass, cache_exporter_password]
          | reject('match', '[A-Za-z0-9]{5,}\Z') | list | length == 0
        fail_msg: >-
          {{ ['cache_engine_password', 'cache_replica_password', 'cache_sentinel_password', 'cache_sentinel_requirepass', 'cache_exporter_password'] | zip([cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass, cache_exporter_password]) | rejectattr('1', 'match', '[A-Za-z0-9]{5,}\Z') | map('first') | join(', ') }}
          in group_vars/cache_host/vault.yml must be five or more letters and digits. Re-generate it with
          `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` and replace its entry.

    # Probe idiom: probes never fail or change and run under --check; the assert after each refuses
    # with the fix in its message. Tests: tests/test_infra_converge_guards.py.
    - name: probe — is the pinned digest already on this host
      ansible.builtin.command: docker image inspect "{{ cache_image }}@{{ cache_image_digest }}"
      register: cache_digest_probe
      failed_when: false
      changed_when: false
      check_mode: false

    - name: preflight — refuse a digest the host has not pulled
      ansible.builtin.assert:
        that: cache_digest_probe.rc == 0
        fail_msg: >-
          {{ cache_image }}@{{ cache_image_digest }} is not on {{ inventory_hostname }} — the unit's
          ExecStartPre would pull it inside the restart, lengthening the window this node's copy is down.
          Pre-stage it first:
          sudo docker pull {{ cache_image }}@{{ cache_image_digest }}

    - name: probe — the currently-running digest this converge would replace (pins recording)
      ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-valkey
      register: cache_running_digest_probe
      failed_when: false
      changed_when: false
      check_mode: false

    - name: read fleet-pins.md from the controller tree
      ansible.builtin.set_fact:
        cache_fleet_pins_text: "{{ lookup('file', playbook_dir ~ '/../../docs/reference/fleet-pins.md') }}"
      when: cache_running_digest_probe.rc == 0

    - name: pins recording — refuse to replace a digest fleet-pins.md does not record
      ansible.builtin.assert:
        that: >-
          ((cache_running_digest_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in cache_fleet_pins_text)
          or ((pins_override | default('') | string | length > 8)
              and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
        fail_msg: >-
          The digest this converge replaces ({{ cache_running_digest_probe.stdout }}) is not recorded in
          docs/reference/fleet-pins.md — an unrecorded pin is one docker-prune from an unrecoverable
          rollback. Record the CURRENT digest there first (or pass -e '{"pins_override": "<reason>"}' and
          record it immediately after).
      when: cache_running_digest_probe.rc == 0 and cache_fleet_pins_text is defined

    - name: pins override accepted — the reason, on the record
      ansible.builtin.debug:
        msg: "pins_override accepted: {{ pins_override }}"
      when: >-
        cache_running_digest_probe.rc == 0 and cache_fleet_pins_text is defined
        and not ((cache_running_digest_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in cache_fleet_pins_text)
        and (pins_override | default('') | string | length > 8)
        and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])

    # A dedicated host account rather than the image's uid 999, which a Debian host can hand to a system
    # user of its own; the containers run as this account, so the files they write are owned by a name.
    - name: create the zcrypto-cache system user (nologin, owns the cache's state)
      ansible.builtin.user:
        name: zcrypto-cache
        system: true
        shell: /usr/sbin/nologin
        create_home: false
        state: present

    - name: look up the zcrypto-cache service account
      ansible.builtin.getent:
        database: passwd
        key: zcrypto-cache
      register: cache_getent
      # A first-install --check never created the account, so the lookup comes up empty there alone.
      failed_when: cache_getent is failed and not ansible_check_mode

    - name: derive the zcrypto-cache uid/gid for the containers' user mapping
      ansible.builtin.set_fact:
        cache_uid: "{{ cache_passwd['zcrypto-cache'][1] if cache_account_known else 'first-run-check-mode' }}"
        cache_gid: "{{ cache_passwd['zcrypto-cache'][2] if cache_account_known else 'first-run-check-mode' }}"
      vars:
        cache_passwd: "{{ ansible_facts['getent_passwd'] | default({}) }}"
        cache_account_known: "{{ (cache_passwd['zcrypto-cache'] | default(none)) is not none }}"

    - name: ensure the cache compose and state directories exist (root-owned)
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        owner: root
        group: root
        mode: "0755"
      loop:
        - "{{ cache_compose_dir }}"
        - "{{ cache_state_dir }}"

    # conf/ is writable by the daemons: Valkey's CONFIG REWRITE and Sentinel's state updates replace their
    # files through a temporary file beside them.
    - name: ensure the data and config directories exist, owned by zcrypto-cache
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        owner: zcrypto-cache
        group: zcrypto-cache
        mode: "0700"
      loop:
        - "{{ cache_state_dir }}/data"
        - "{{ cache_state_dir }}/conf"

    - name: derive each daemon-owned config's current template hash
      ansible.builtin.set_fact:
        cache_template_sha: "{{ cache_template_sha | default({}) | combine({item: lookup('ansible.builtin.template', item ~ '.j2') | hash('sha256')}) }}"
      loop: "{{ cache_daemon_files }}"

    # force follows cache_config_reset: a routine converge leaves a present file as the daemon wrote it.
    - name: render the daemon-owned configs when absent, or under cache_config_reset
      ansible.builtin.template:
        src: "{{ item }}.j2"
        dest: "{{ cache_state_dir }}/conf/{{ item }}"
        owner: zcrypto-cache
        group: zcrypto-cache
        mode: "0600"
        force: "{{ cache_config_reset | bool }}"
      loop: "{{ cache_daemon_files }}"
      register: cache_conf_render
      no_log: true
      diff: false
      notify: restart cache service

    - name: record the template hash each config was rendered from
      ansible.builtin.lineinfile:
        path: "{{ cache_compose_dir }}/rendered-sha256.yml"
        regexp: "^{{ item.item | regex_escape }}: "
        line: "{{ item.item }}: '{{ cache_template_sha[item.item] }}'"
        create: true
        owner: root
        group: root
        mode: "0600"
      loop: "{{ cache_conf_render.results | selectattr('changed') | list }}"
      loop_control:
        label: "{{ item.item }}"

    - name: probe — the template hashes recorded at each config's last render
      ansible.builtin.slurp:
        src: "{{ cache_compose_dir }}/rendered-sha256.yml"
      register: cache_rendered_record
      failed_when: false
      changed_when: false
      check_mode: false

    - name: derive the recorded template hash per config
      ansible.builtin.set_fact:
        cache_recorded_sha: "{{ (cache_rendered_record.content | b64decode | from_yaml | default({}, true)) if cache_rendered_record.content is defined else {} }}"

    # Reported, never fatal and never applied: the file on the host is the daemon's, and applying the
    # template is a replication reset, which is a procedure's in infra/runbooks/cache.md to make. The
    # play recap counts a report as `ignored`.
    - name: drift — report a daemon-owned config whose template no longer renders what this node was given
      ansible.builtin.assert:
        that: cache_recorded_sha[item] | default(cache_template_sha[item]) == cache_template_sha[item]
        fail_msg: >-
          {{ item }}'s template no longer renders what {{ inventory_hostname }} was given. The file on the
          node is the daemon's and this converge left it as it is. Apply a template change by the
          cache-config-reset procedure in infra/runbooks/cache.md, and a password changed in
          group_vars/cache_host/vault.yml by its cache-password-rotation procedure, which resets the three
          nodes together.
      loop: "{{ cache_daemon_files }}"
      when: item not in (cache_conf_render.results | selectattr('changed') | map(attribute='item') | list)
      register: cache_config_drift
      ignore_errors: true

    # The reads the runbook prints take their password from these through `docker exec --env-file`, so
    # no password is ever an argument on a command line. valkey-cli reads VALKEYCLI_AUTH; REDISCLI_AUTH
    # is the name it still honours.
    - name: render the root-only valkey-cli credential files
      ansible.builtin.template:
        src: "{{ item }}.j2"
        dest: "{{ cache_compose_dir }}/{{ item }}"
        owner: root
        group: root
        mode: "0600"
      loop:
        - cli-exporter.env
        - cli-sentinel.env
      no_log: true
      diff: false

    - name: render the cache compose file
      ansible.builtin.template:
        src: compose.yaml.j2
        dest: "{{ cache_compose_dir }}/compose.yaml"
        owner: root
        group: root
        mode: "0644"
      notify: restart cache service

    - name: render the cache systemd unit
      ansible.builtin.template:
        src: zcrypto-cache.service.j2
        dest: /etc/systemd/system/zcrypto-cache.service
        owner: root
        group: root
        mode: "0644"
      register: cache_unit_install
      notify: restart cache service

    - name: enable + start the cache service (boot resume)
      ansible.builtin.systemd_service:
        name: zcrypto-cache.service
        daemon_reload: true
        enabled: true
        state: started
      # A first-install preview never wrote the unit, so systemd cannot find it.
      when: not (ansible_check_mode and cache_unit_install is changed)

# The pending-reboot flag, outside the digest gate: it publishes whatever a converge carries. A copy of
# the capture role's reboot check; tests/test_reboot_check.py holds the two programs equal.
- name: ensure the node-exporter textfile directory exists
  ansible.builtin.file:
    path: "{{ cache_textfile_dir }}"
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: install the reboot-check script
  ansible.builtin.copy:
    src: zcrypto-reboot-check.sh
    dest: /usr/local/sbin/zcrypto-reboot-check
    owner: root
    group: root
    mode: "0755"

- name: render the reboot-check systemd unit
  ansible.builtin.template:
    src: zcrypto-reboot-check.service.j2
    dest: /etc/systemd/system/zcrypto-reboot-check.service
    owner: root
    group: root
    mode: "0644"

- name: install the reboot-check systemd timer
  ansible.builtin.copy:
    src: zcrypto-reboot-check.timer
    dest: /etc/systemd/system/zcrypto-reboot-check.timer
    owner: root
    group: root
    mode: "0644"
  register: cache_reboot_timer_install

# Only the timer is enabled: enabling the oneshot too would probe on every boot. A first-install
# preview never wrote the timer, so systemd cannot find it there.
- name: enable + start the reboot-check timer
  ansible.builtin.systemd_service:
    name: zcrypto-reboot-check.timer
    daemon_reload: true
    enabled: true
    state: started
  when: not (ansible_check_mode and cache_reboot_timer_install is changed)
```

- [ ] **Step 5: The templates**

Create `infra/ansible/roles/cache/templates/compose.yaml.j2`:

```yaml
# Rendered by the `cache` Ansible role at {{ cache_compose_dir }}/compose.yaml; edit
# infra/ansible/roles/cache/templates/compose.yaml.j2 and re-converge instead of editing it on the node.
# Host networking because Sentinel announces and discovers peers by address, which Docker's port
# mapping rewrites; both daemons bind loopback and the zcache0 address alone (valkey.conf, sentinel.conf).
services:
  valkey:
    image: "{{ cache_image }}@{{ cache_image_digest }}"
    container_name: zcrypto-valkey
    restart: unless-stopped
    user: "{{ cache_uid }}:{{ cache_gid }}"
    network_mode: host
    command: ["valkey-server", "/etc/valkey/valkey.conf"]
    volumes:
      # The directory, read-write: both daemons replace their config by renaming a temporary file beside
      # it, which a single-file mount refuses.
      - "{{ cache_state_dir }}/conf:/etc/valkey"
      - "{{ cache_state_dir }}/data:/data"
    deploy:
      resources:
        limits:
          memory: "{{ cache_valkey_memory_limit }}"
    logging:
      driver: journald
  sentinel:
    image: "{{ cache_image }}@{{ cache_image_digest }}"
    container_name: zcrypto-sentinel
    restart: unless-stopped
    user: "{{ cache_uid }}:{{ cache_gid }}"
    network_mode: host
    command: ["valkey-sentinel", "/etc/valkey/sentinel.conf"]
    volumes:
      - "{{ cache_state_dir }}/conf:/etc/valkey"
    deploy:
      resources:
        limits:
          memory: "{{ cache_sentinel_memory_limit }}"
    logging:
      driver: journald
```

Create `infra/ansible/roles/cache/templates/valkey.conf.j2`:

```
# Rendered by the `cache` Ansible role when absent or under -e cache_config_reset=true, and owned by
# Valkey after its first start: Sentinel's reconfiguration rewrites `replicaof` into this file. The
# role reports a template that no longer matches this render and never applies it on its own.
bind 127.0.0.1 {{ cache_bind_address }}
port 6379
protected-mode yes
dir /data
aclfile /etc/valkey/users.acl
appendonly yes
appendfsync always
save 3600 1 300 100 60 10000
maxmemory {{ cache_maxmemory }}
maxmemory-policy noeviction
min-replicas-to-write 1
min-replicas-max-lag 10
replica-priority {{ cache_replica_priority }}
replica-announce-ip {{ cache_bind_address }}
masteruser replica
masterauth {{ cache_replica_password }}
{% if cache_bind_address != cache_first_primary %}
replicaof {{ cache_first_primary }} 6379
{% endif %}
```

Create `infra/ansible/roles/cache/templates/sentinel.conf.j2`:

```
# Rendered by the `cache` Ansible role when absent or under -e cache_config_reset=true, and owned by
# Sentinel after its first start: it writes the replicas, the other Sentinels and its epoch into this
# file. The role reports a template that no longer matches this render and never applies it on its own.
bind 127.0.0.1 {{ cache_bind_address }}
port 26379
dir /tmp
requirepass {{ cache_sentinel_requirepass }}
sentinel resolve-hostnames no
sentinel announce-ip {{ cache_bind_address }}
sentinel monitor {{ cache_master_name }} {{ cache_first_primary }} 6379 2
sentinel down-after-milliseconds {{ cache_master_name }} {{ cache_down_after_ms }}
sentinel failover-timeout {{ cache_master_name }} {{ cache_failover_timeout_ms }}
sentinel parallel-syncs {{ cache_master_name }} 1
sentinel auth-user {{ cache_master_name }} sentinel
sentinel auth-pass {{ cache_master_name }} {{ cache_sentinel_password }}
```

Create `infra/ansible/roles/cache/templates/users.acl.j2` (no `#` line may reach the rendered file: Valkey's ACL loader takes `user` lines and blank lines alone, so the one comment is a Jinja comment):

```
{# Valkey's ACL file takes `user` lines and blank lines only: a `#` comment here fails the load. #}
user default off
user engine on #{{ cache_engine_password | hash('sha256') }} ~* &* +@all -@dangerous +keys +info
user replica on #{{ cache_replica_password | hash('sha256') }} +psync +replconf +ping
user sentinel on #{{ cache_sentinel_password | hash('sha256') }} &* +multi +slaveof +replicaof +ping +exec +subscribe +config|rewrite +role +publish +info +client|setname +client|kill +script|kill
user exporter on #{{ cache_exporter_password | hash('sha256') }} -@all +@connection +memory -readonly +strlen +config|get +xinfo +pfcount -quit +zcard +type +xlen -readwrite -command +client -wait +scard +llen +hlen +get +eval +slowlog +cluster|info -hello -echo +info +latency +scan -reset -auth -asking
```

Create `infra/ansible/roles/cache/templates/cli-exporter.env.j2`:

```
VALKEYCLI_AUTH={{ cache_exporter_password }}
REDISCLI_AUTH={{ cache_exporter_password }}
```

Create `infra/ansible/roles/cache/templates/cli-sentinel.env.j2`:

```
VALKEYCLI_AUTH={{ cache_sentinel_requirepass }}
REDISCLI_AUTH={{ cache_sentinel_requirepass }}
```

Create `infra/ansible/roles/cache/templates/zcrypto-cache.service.j2`:

```ini
# Rendered by the `cache` Ansible role at /etc/systemd/system/zcrypto-cache.service; edit
# infra/ansible/roles/cache/templates/zcrypto-cache.service.j2 and re-converge instead.
[Unit]
Description=zcrypto cache: Valkey and Sentinel (Docker Compose)
Requires=docker.service
# Wanted, not required: both daemons bind the zcache0 address, and a tunnel restart must not stop them.
After=docker.service network-online.target wg-quick@zcache0.service
Wants=network-online.target wg-quick@zcache0.service

[Service]
Type=simple
WorkingDirectory={{ cache_compose_dir }}
# `-`: the digest is pre-staged by the converge's preflight, so a registry outage at boot must not
# keep the cache down.
ExecStartPre=-/usr/bin/docker compose -f {{ cache_compose_dir }}/compose.yaml pull
ExecStart=/usr/bin/docker compose -f {{ cache_compose_dir }}/compose.yaml up
ExecStop=/usr/bin/docker compose -f {{ cache_compose_dir }}/compose.yaml down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `infra/ansible/roles/cache/files/zcrypto-reboot-check.sh`, then `chmod 0755` it (the shebang hooks refuse a script git records as 0644):

```bash
#!/usr/bin/env bash
# Installed by the `cache` role at /usr/local/sbin/zcrypto-reboot-check, a copy of the capture role's;
# tests/test_reboot_check.py drives the capture role's and holds this one's program equal to it.
set -euo pipefail

usage="usage: zcrypto-reboot-check <flag-path> <output.prom>"
flag=${1:-}
out=${2:-}
[ -n "$flag" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

# /run, not /var/run: the latter is a compatibility symlink; the unit passes /run/reboot-required.
pending=0
[ -e "$flag" ] && pending=1

# Atomic publish: the collector globs this directory continuously and must never read a half-written
# file, and mktemp as a sibling makes the mv a same-filesystem rename. 0 is emitted explicitly: an
# absent series is indistinguishable from a dead exporter.
tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP node_reboot_required 1 when the host has a pending reboot (/run/reboot-required), else 0."
  echo "# TYPE node_reboot_required gauge"
  echo "node_reboot_required $pending"
} > "$tmp"
chmod 0644 -- "$tmp"   # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out"
trap - EXIT
```

Create `infra/ansible/roles/cache/files/zcrypto-reboot-check.timer`:

```ini
# Installed by the `cache` Ansible role at /etc/systemd/system/zcrypto-reboot-check.timer, a copy of
# the capture role's timer; edit this file and re-converge instead of editing the host's copy.
[Unit]
Description=Publish the pending-reboot flag as a node-exporter textfile

[Timer]
# Interval, not OnCalendar: a stat plus a three-line write. Every 15 min bounds how long a kernel flag
# sits unseen; OnBootSec republishes promptly after a reboot so the gauge returns to 0.
OnBootSec=2min
OnUnitActiveSec=15min
# Deliberately no Persistent=true: this reports current state.
Unit=zcrypto-reboot-check.service

[Install]
WantedBy=timers.target
```

Create `infra/ansible/roles/cache/templates/zcrypto-reboot-check.service.j2`:

```ini
# Rendered by the `cache` Ansible role at /etc/systemd/system/zcrypto-reboot-check.service; edit
# infra/ansible/roles/cache/templates/zcrypto-reboot-check.service.j2 and re-converge. A copy of the
# capture role's unit.
[Unit]
Description=Publish the pending-reboot flag as a node-exporter textfile

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zcrypto-reboot-check /run/reboot-required {{ cache_textfile_dir }}/reboot.prom
# This unit only ever writes one .prom, which ProtectSystem=strict makes structural.
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={{ cache_textfile_dir }}
```

- [ ] **Step 6: The nodes' priorities, the site play and the daily pass's protected objects**

Append to the end of `infra/ansible/host_vars/zcrypto-valkey1/vars.yml` and of `infra/ansible/host_vars/zcrypto-valkey2/vars.yml`:

```yaml

# Sentinel promotes the lowest non-zero priority: the engine region's two nodes before the remote copy.
cache_replica_priority: 100
```

Append to the end of `infra/ansible/host_vars/zcrypto-valkey3/vars.yml`:

```yaml

# Sentinel promotes the lowest non-zero priority: the engine region's two nodes before the remote copy.
cache_replica_priority: 250
```

In `infra/ansible/site.yml`, in the `cache_host` play, the one whose line `- name: converge the cache nodes — the engine's Valkey replica set` no other play carries, below that play's entry, the file's last two lines,

```yaml
    - role: cache_link
      tags: [cache-link]
```

add (the engine play carries the same two lines higher up, and they stay as they are)

```yaml
    - role: cache
      tags: [cache]
```

In `infra/scripts/ops_daily.py`, in `_PROTECTED_OBJECTS`, replace the line `    "zcrypto-red",` with:

```python
    "zcrypto-red",
    "zcrypto-valkey",
    "zcrypto-sentinel",
    "zcrypto-cache",
    "zcache0",
```

- [ ] **Step 7: Run the new tests**

Run: `uv run pytest tests/test_infra_cache_templates.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py::test_cache_digest_failfast_refuses_an_empty_digest tests/test_infra_converge_guards.py::test_the_valkey_and_sentinel_tasks_run_only_on_a_converge_carrying_the_digest tests/test_infra_converge_guards.py::test_cache_config_reset_without_the_digest_is_refused_before_the_gate tests/test_infra_converge_guards.py::test_cache_empty_digest_failfast_precedes_residency_preflight tests/test_infra_converge_guards.py::test_cache_digest_preflight_refuses_an_unpulled_digest tests/test_infra_converge_guards.py::test_cache_pins_recording_semantics tests/test_infra_converge_guards.py::test_cache_pins_override_echo_fires_only_on_an_accepted_override tests/test_infra_converge_guards.py::test_cache_password_refusal tests/test_infra_converge_guards.py::test_cache_password_refusal_names_the_key_and_never_the_value tests/test_infra_converge_guards.py::test_cache_configs_render_only_when_absent_unless_reset tests/test_infra_converge_guards.py::test_cache_render_covers_the_daemon_files_and_each_has_a_template tests/test_infra_converge_guards.py::test_cache_drift_reports_a_config_whose_template_moved tests/test_infra_converge_guards.py::test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered tests/test_infra_converge_guards.py::test_every_cache_secret_render_is_never_logged_or_diffed tests/test_infra_converge_guards.py::test_every_cache_probe_never_fails_changes_or_skips_under_check tests/test_infra_converge_guards.py::test_the_cache_restart_handler_stands_down_only_on_a_first_install_preview tests/test_infra_alert_rules.py::test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence tests/test_ops_daily.py::test_a_cache_daemon_restart_is_never_the_passs_own tests/test_reboot_check.py -q -p no:cacheprovider`
Expected: `136 passed`: the new module's 25, the compose module's 18 (five of them this task's), the 67 guard cases, the headroom case, the eight protected-object cases and `tests/test_reboot_check.py`'s 17 (the four copy cases among them this task's); the cases this task adds are 109.

- [ ] **Step 8: The consumers**

The modules that read what this task changes: the four above; the walkers of every role file (`tests/test_internal_terms_not_operator_visible.py`, `tests/test_infra_shell_templates_render.py`); the readers of `host_vars` and `site.yml`, the whole of what `grep -lE 'host_vars|site\.yml' tests/*.py` lists; the readers of `infra/scripts/ops_daily.py`, `tests/test_ops_daily_soak.py` and `tests/test_engine_soak.py` beside `tests/test_ops_daily.py`, the whole of what `grep -rlE ops_daily tests/test_*.py` lists; `tests/test_dashboards_cover_metrics.py`, whose admission rule is why the headroom entries are absences; and `tests/test_config_selectors_are_parsed.py`, which reads every test module for substring selectors over a config file, the reboot-check copy cases among them.

Run: `uv run pytest tests/test_infra_cache_templates.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py tests/test_infra_shell_templates_render.py tests/test_converge_sh.py tests/test_deploy_log_audit.py tests/test_fleet_contracts.py tests/test_infra_firewall_template.py tests/test_run_sh.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_engine_soak.py tests/test_dashboards_cover_metrics.py tests/test_reboot_check.py tests/test_deploy_log_audit.py tests/test_infra_unattended_upgrades.py tests/test_config_selectors_are_parsed.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a data gate, none failed; `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` passing is the check that the unit copy carries no venue name. `tests/test_internal_terms_not_operator_visible.py` walks the new task names, `fail_msg`s and the unit's `Description=`, none of which carries a spec, decision or topic token.

- [ ] **Step 9: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed (ansible-lint over `infra/ansible/` at its production profile, yamllint, ruff); re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 10: Commit**

The executor writes its own model name in place of `<model>` in the trailer.

```bash
git add infra/ansible/roles/cache infra/ansible/host_vars/zcrypto-valkey1/vars.yml infra/ansible/host_vars/zcrypto-valkey2/vars.yml infra/ansible/host_vars/zcrypto-valkey3/vars.yml infra/ansible/site.yml infra/scripts/ops_daily.py tests/test_infra_cache_templates.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_reboot_check.py
git commit -m "feat(cache): Valkey and Sentinel on the three cache nodes, one pinned image, their configs theirs after the first render

The \`cache\` role runs Valkey and its Sentinel from one digest-pinned valkey/valkey image in one
compose project under zcrypto-cache.service: host-networked, bound to loopback and the node's
zcache0 address, run as a dedicated zcrypto-cache account, logging to the journal, capped at 256m
and 64m. Its tasks form one block gated on cache_image_digest being defined, which has no default,
so a converge without it skips them. It carries the capture role's converge guards: the empty-digest
fail-fast ahead of the residency preflight, and the pins-recording refusal with its override echo. A password refusal
turns away any of the five cache passwords under five characters or outside letters and digits,
naming the key and never the value.

valkey.conf, sentinel.conf and users.acl are rendered when absent or under
-e cache_config_reset=true, since Sentinel writes replicaof, its peers and its epoch into the files
the daemons started from. The reset renders inside the gated block, so a refusal before the block
turns away a reset converge that carries no digest, which would otherwise apply nothing and exit 0.
Each render records its template hash in rendered-sha256.yml, and a
converge whose template no longer renders that hash reports the file as ignored drift and leaves it
as it is. The first primary renders no replicaof and the other two replicate from it;
replica-priority is 100, 100 and 250; min-replicas-to-write 1, appendfsync always, noeviction at
128mb; quorum 2. users.acl carries sha256 hashes: default off; engine every key, with KEYS and INFO
past -@dangerous; replica and sentinel on valkey.io's grants; exporter on redis_exporter v1.86.0's,
less +arcount, which Valkey 9.1.2 refuses, and the two cluster tokens a standalone set does not use. Two
root-only env files carry the exporter's and Sentinel's passwords for docker exec --env-file reads.

The headroom map names the new compose file's six (host, job) pairs and records them absent: the
headroom rules parse process_resident_memory_bytes, which neither daemon publishes, Valkey's memory
is the cache group's 70%-of-maxmemory rule's, and Sentinel has none. The daily pass's protected
objects gain zcrypto-valkey, zcrypto-sentinel, their unit's zcrypto-cache and the tunnel's zcache0,
since the nodes are telemetry hosts whose container and unit restarts the pass may otherwise take on
its own. The nodes publish node_reboot_required from a copy of
the capture role's reboot check, its script, timer and unit held equal to the capture role's but for
their comments, the timer enabled outside the digest gate.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

- [ ] **Step 11: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 12: Prove the guards with thirty-eight probes, then record their verdicts by a message-only amend**

Each probe runs on the committed tree, never while a pytest run is in flight in the same checkout. A task-level control renames the task its test looks up, so the test's `find_task` fails; a template-level control changes a line the test asserts; each mutation is the defect the guard exists to catch. The role's tasks sit inside the digest-gated block, so a task's own keys are indented six spaces and a folded `when:` continuation eight, which the anchored expressions below match. Each control and each mutation changes one line of its file, so a verdict names the one site its test isolated: where a pattern recurs in the file, a sed line range scopes it to its own task or service (`/<task name>/,/<its last key>/`), which probes 3 and 4 (the pins refusal's `that:`, which its echo's `when:` repeats), 6 and 7 (the password refusal's `that:`, which its `fail_msg` repeats), 12 (the valkey-cli render's `no_log`, beside the daemon-owned render's), 13 (the digest probe's `check_mode`, one of three probes') and 24 to 26 (Valkey's service, whose lines Sentinel's repeats) take.

```bash
T=infra/ansible/roles/cache/tasks/main.yml
H=infra/ansible/roles/cache/handlers/main.yml
TP=infra/ansible/roles/cache/templates
G=tests/test_infra_converge_guards.py
C=tests/test_infra_cache_templates.py
DR="name: drift — report a daemon-owned config whose template no longer renders what this node was given"
# 1-2: the digest fail-fast and the residency preflight
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: fail fast if the pinned cache image digest was not supplied/name: fail fast renamed/' \
  --mutation 's/that: cache_image_digest | length > 0/that: cache_image_digest | length >= 0/' \
  -- uv run pytest $G::test_cache_digest_failfast_refuses_an_empty_digest -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: preflight — refuse a digest the host has not pulled/name: preflight renamed/' \
  --mutation 's/that: cache_digest_probe.rc == 0/that: cache_digest_probe.rc >= 0/' \
  -- uv run pytest $G::test_cache_digest_preflight_refuses_an_unpulled_digest -q -p no:cacheprovider
# 3-5: the pins refusal (an unrecorded digest admitted; a short override admitted) and its echo (fired with nothing overridden)
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: pins recording — refuse to replace a digest fleet-pins.md does not record/name: pins renamed/' \
  --mutation '/name: pins recording — refuse to replace/,/fail_msg:/s/in cache_fleet_pins_text)$/in cache_fleet_pins_text) or true/' \
  -- uv run pytest $G::test_cache_pins_recording_semantics -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: pins recording — refuse to replace a digest fleet-pins.md does not record/name: pins renamed/' \
  --mutation '/name: pins recording — refuse to replace/,/fail_msg:/s/string | length > 8)/string | length > 0)/' \
  -- uv run pytest $G::test_cache_pins_recording_semantics -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: pins override accepted — the reason, on the record/name: pins echo renamed/' \
  --mutation 's/^        and not ((cache_running_digest_probe/        and ((cache_running_digest_probe/' \
  -- uv run pytest $G::test_cache_pins_override_echo_fires_only_on_an_accepted_override -q -p no:cacheprovider
# 6-7: the password refusal (a four-character floor; any non-space character admitted)
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: refuse a cache password shorter than five characters or outside letters and digits/name: password renamed/' \
  --mutation '/name: refuse a cache password/,/fail_msg:/s/{5,}\\Z/{4,}\\Z/' \
  -- uv run pytest $G::test_cache_password_refusal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: refuse a cache password shorter than five characters or outside letters and digits/name: password renamed/' \
  --mutation '/name: refuse a cache password/,/fail_msg:/s/\[A-Za-z0-9\]{5,}\\Z/[^ ]{5,}\\Z/' \
  -- uv run pytest $G::test_cache_password_refusal -q -p no:cacheprovider
# 8: render-if-absent
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: render the daemon-owned configs when absent, or under cache_config_reset/name: render renamed/' \
  --mutation 's/force: "{{ cache_config_reset | bool }}"/force: true/' \
  -- uv run pytest $G::test_cache_configs_render_only_when_absent_unless_reset -q -p no:cacheprovider
# 9-11: the drift report (its comparison, its non-fatal shape, its skip of a file this run rendered)
infra/scripts/mutate-probe.sh --file $T \
  --control "s/$DR/name: drift renamed/" \
  --mutation 's/that: cache_recorded_sha\[item\] | default(cache_template_sha\[item\]) == cache_template_sha\[item\]/that: true/' \
  -- uv run pytest $G::test_cache_drift_reports_a_config_whose_template_moved -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control "s/$DR/name: drift renamed/" \
  --mutation 's/ignore_errors: true/ignore_errors: false/' \
  -- uv run pytest $G::test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control "s/$DR/name: drift renamed/" \
  --mutation 's/when: item not in (cache_conf_render.results/when: item in (cache_conf_render.results/' \
  -- uv run pytest $G::test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered -q -p no:cacheprovider
# 12-13: the credential render logged, and the digest probe run as a change
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: render the root-only valkey-cli credential files/name: cli renamed/' \
  --mutation '/name: render the root-only valkey-cli credential files/,/diff: false/s/^      no_log: true$/      no_log: false/' \
  -- uv run pytest $G::test_every_cache_secret_render_is_never_logged_or_diffed -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: probe — is the pinned digest already on this host/name: renamed digest probe/' \
  --mutation '/name: probe — is the pinned digest already on this host/,/check_mode:/s/^      check_mode: false$/      check_mode: true/' \
  -- uv run pytest $G::test_every_cache_probe_never_fails_changes_or_skips_under_check -q -p no:cacheprovider
# 14: the restart handler standing down on every preview
infra/scripts/mutate-probe.sh --file $H \
  --control 's/name: restart cache service/name: restart renamed/' \
  --mutation 's/when: not (ansible_check_mode and cache_unit_install is changed)/when: not ansible_check_mode/' \
  -- uv run pytest $G::test_the_cache_restart_handler_stands_down_only_on_a_first_install_preview -q -p no:cacheprovider
# 15-19: valkey.conf (replicaof on the first primary, a public bind, writes without a replica, eviction)
infra/scripts/mutate-probe.sh --file $TP/valkey.conf.j2 \
  --control 's/^replicaof {{ cache_first_primary }} 6379$/replicaof {{ cache_first_primary }} 6380/' \
  --mutation 's/{% if cache_bind_address != cache_first_primary %}/{% if true %}/' \
  -- uv run pytest $C::test_the_first_primary_renders_no_replicaof_and_every_other_node_replicates_from_it -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/valkey.conf.j2 \
  --control 's/^bind 127.0.0.1 /bind 127.0.0.2 /' \
  --mutation 's/^bind 127.0.0.1 {{ cache_bind_address }}$/bind 0.0.0.0/' \
  -- uv run pytest $C::test_valkey_and_sentinel_bind_loopback_and_the_mesh_address_alone -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/sentinel.conf.j2 \
  --control 's/^bind 127.0.0.1 /bind 127.0.0.2 /' \
  --mutation 's/^bind 127.0.0.1 {{ cache_bind_address }}$/bind 0.0.0.0/' \
  -- uv run pytest $C::test_valkey_and_sentinel_bind_loopback_and_the_mesh_address_alone -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/valkey.conf.j2 \
  --control 's/^appendfsync always$/appendfsync everysec/' \
  --mutation 's/^min-replicas-to-write 1$/min-replicas-to-write 0/' \
  -- uv run pytest $C::test_valkey_refuses_writes_without_a_replica_and_never_evicts -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/valkey.conf.j2 \
  --control 's/^appendfsync always$/appendfsync everysec/' \
  --mutation 's/^maxmemory-policy noeviction$/maxmemory-policy allkeys-lru/' \
  -- uv run pytest $C::test_valkey_refuses_writes_without_a_replica_and_never_evicts -q -p no:cacheprovider
# 20: sentinel.conf's quorum
infra/scripts/mutate-probe.sh --file $TP/sentinel.conf.j2 \
  --control 's/^sentinel parallel-syncs {{ cache_master_name }} 1$/sentinel parallel-syncs {{ cache_master_name }} 2/' \
  --mutation 's/^sentinel monitor {{ cache_master_name }} {{ cache_first_primary }} 6379 2$/sentinel monitor {{ cache_master_name }} {{ cache_first_primary }} 6379 1/' \
  -- uv run pytest $C::test_sentinel_monitors_the_first_primary_at_quorum_two -q -p no:cacheprovider
# 21-23: users.acl (the engine's grants reordered, the default user on, a password in the clear)
infra/scripts/mutate-probe.sh --file $TP/users.acl.j2 \
  --control 's/^user engine on /user engine off /' \
  --mutation 's/ -@dangerous +keys +info$/ +keys +info -@dangerous/' \
  -- uv run pytest $C::test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/users.acl.j2 \
  --control 's/^user engine on /user engine off /' \
  --mutation 's/^user default off$/user default on nopass ~* +@all/' \
  -- uv run pytest $C::test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/users.acl.j2 \
  --control 's/cache_replica_password | hash/cache_engine_password | hash/' \
  --mutation 's/#{{ cache_engine_password | hash(.sha256.) }}/>{{ cache_engine_password }}/' \
  -- uv run pytest $C::test_the_acl_file_carries_password_hashes_and_never_a_password -q -p no:cacheprovider
# 24-26: Valkey's service in the compose file (bridge networking, json-file logging, a single-file config mount)
infra/scripts/mutate-probe.sh --file $TP/compose.yaml.j2 \
  --control 's/command: \["valkey-server", /command: ["valkey-server2", /' \
  --mutation '/container_name: zcrypto-valkey$/,/driver: journald/s/network_mode: host/network_mode: bridge/' \
  -- uv run pytest tests/test_infra_compose_templates.py::test_cache_valkey_and_sentinel_run_one_pinned_image_on_the_host_network -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/compose.yaml.j2 \
  --control 's/command: \["valkey-server", /command: ["valkey-server2", /' \
  --mutation '/container_name: zcrypto-valkey$/,/driver: journald/s/driver: journald/driver: json-file/' \
  -- uv run pytest tests/test_infra_compose_templates.py::test_cache_valkey_and_sentinel_run_one_pinned_image_on_the_host_network -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TP/compose.yaml.j2 \
  --control 's/command: \["valkey-server", /command: ["valkey-server2", /' \
  --mutation '/container_name: zcrypto-valkey$/,/driver: journald/s#{{ cache_state_dir }}/conf:/etc/valkey"#{{ cache_state_dir }}/conf/valkey.conf:/etc/valkey/valkey.conf"#' \
  -- uv run pytest tests/test_infra_compose_templates.py::test_cache_valkey_and_sentinel_run_one_pinned_image_on_the_host_network -q -p no:cacheprovider
# 27: the headroom map's per-pair coverage of the new compose file
infra/scripts/mutate-probe.sh --file tests/test_infra_alert_rules.py \
  --control 's#"infra/ansible/roles/cache/templates/compose.yaml.j2": (#"infra/ansible/roles/cache/templates/compose.yml.j2": (#' \
  --mutation '/^    ("zcrypto-valkey2", "sentinel"): _CACHE_DAEMONS_UNLEGGED,$/d' \
  -- uv run pytest tests/test_infra_alert_rules.py::test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence -q -p no:cacheprovider
# 28: the digest gate
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: install Valkey and Sentinel (needs the pinned image digest)/name: install renamed/' \
  --mutation 's/^  when: cache_image_digest is defined$/  when: true/' \
  -- uv run pytest $G::test_the_valkey_and_sentinel_tasks_run_only_on_a_converge_carrying_the_digest -q -p no:cacheprovider
# 29: a command category the engine's reads and writes need, subtracted
infra/scripts/mutate-probe.sh --file $TP/users.acl.j2 \
  --control 's/^user engine on /user engine off /' \
  --mutation 's/ -@dangerous +keys +info$/ -@dangerous +keys +info -@write/' \
  -- uv run pytest $C::test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous -q -p no:cacheprovider
# 30-33: the daily pass's protected cache daemons, their unit and the mesh tunnel
for M in '/^    "zcrypto-valkey",$/d' '/^    "zcrypto-sentinel",$/d' '/^    "zcrypto-cache",$/d' '/^    "zcache0",$/d'; do
  infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
    --control 's/if not any(obj in lowered for obj in _PROTECTED_OBJECTS):/if True:/' --mutation "$M" \
    -- uv run pytest tests/test_ops_daily.py::test_a_cache_daemon_restart_is_never_the_passs_own -q -p no:cacheprovider
done
# 34: the reboot check's copy drifting from the capture role's
infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache/files/zcrypto-reboot-check.sh \
  --control 's/^set -euo pipefail$/set -eu/' \
  --mutation 's/^pending=0$/pending=1/' \
  -- uv run pytest tests/test_reboot_check.py -q -p no:cacheprovider -k cache_roles_reboot_check
# 35: the oneshot enabled in the timer's place
infra/scripts/mutate-probe.sh --file $T \
  --control 's#^    dest: /usr/local/sbin/zcrypto-reboot-check$#    dest: /usr/local/sbin/zcrypto-reboot-checkx#' \
  --mutation 's/^    name: zcrypto-reboot-check.timer$/    name: zcrypto-reboot-check.service/' \
  -- uv run pytest tests/test_reboot_check.py::test_the_cache_role_installs_what_its_unit_runs_and_enables_the_timer_alone -q -p no:cacheprovider
# 36: valkey.conf's RDB snapshots dropped
infra/scripts/mutate-probe.sh --file $TP/valkey.conf.j2 \
  --control 's/^appendfsync always$/appendfsync everysec/' \
  --mutation '/^save 3600 1 300 100 60 10000$/d' \
  -- uv run pytest $C::test_valkey_refuses_writes_without_a_replica_and_never_evicts -q -p no:cacheprovider
# 37: the bind default pointed at the node's public address
infra/scripts/mutate-probe.sh --file infra/ansible/roles/cache/defaults/main.yml \
  --control 's/^cache_bind_address: "{{ cache_link_address }}"$/cache_bind_address: 127.0.0.2/' \
  --mutation 's/^cache_bind_address: "{{ cache_link_address }}"$/cache_bind_address: "{{ ansible_host }}"/' \
  -- uv run pytest $C::test_valkey_and_sentinel_bind_loopback_and_the_mesh_address_alone -q -p no:cacheprovider
# 38: a config reset without the digest admitted
infra/scripts/mutate-probe.sh --file $T \
  --control 's/name: refuse a config reset without the pinned image digest/name: reset refusal renamed/' \
  --mutation 's/that: not (cache_config_reset | bool) or cache_image_digest is defined/that: true/' \
  -- uv run pytest $G::test_cache_config_reset_without_the_digest_is_refused_before_the_gate -q -p no:cacheprovider
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message of Step 10 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, thirty-eight runs, each KILLED, control proven, each
mutation changing one line. Over infra/ansible/roles/cache/tasks/main.yml, each control renaming
the task its test looks up: the digest fail-fast admitting an empty digest; the preflight admitting
an unpulled one; the pins refusal admitting an unrecorded digest, and a four-character override; the
pins echo firing with nothing overridden; the password refusal at a four-character floor, and
admitting any non-space character; the daemon-owned renders forced on every converge; the drift
comparison replaced by true, made fatal, and run over a file this converge rendered; the valkey-cli
credential render logged; the digest probe run under check mode. Over handlers/main.yml, control the
handler renamed: the restart standing down on every preview. Over templates/valkey.conf.j2: replicaof
rendered on the first primary, control the replicas' port moved; a public bind, control the loopback
address moved; min-replicas-to-write 0 and allkeys-lru, control appendfsync moved. Over
templates/sentinel.conf.j2: a public bind, control the loopback address moved; quorum 1, control
parallel-syncs moved. Over templates/users.acl.j2: the engine's KEYS and INFO moved before
-@dangerous and the default user on, control the engine user off; the engine's password in the
clear, control the replica's hash taken from the engine's password. Over templates/compose.yaml.j2,
control valkey's command renamed: Valkey's service on bridge networking, on json-file logging, on a
single-file config mount. Over tests/test_infra_alert_rules.py, control the map's key renamed: one of
the six recorded absences deleted. Over tasks/main.yml, control the block renamed: the digest gate
replaced by true. Over templates/users.acl.j2, control the engine user off: -@write appended to the
engine's grants. Over infra/scripts/ops_daily.py, control the protected-objects veto disabled:
zcrypto-valkey dropped from the protected objects, zcrypto-sentinel, zcrypto-cache and zcache0. Over
files/zcrypto-reboot-check.sh, control its strict mode loosened: the flag published as pending by
default. Over tasks/main.yml, control the reboot-check script's destination moved: the oneshot
enabled in the timer's place. Over templates/valkey.conf.j2, control appendfsync moved: the RDB
snapshot line dropped. Over defaults/main.yml, control the bind default moved to another loopback
address: the bind default pointed at the node's public address. Over tasks/main.yml, control the
refusal renamed: a config reset without the digest admitted.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

**Operator steps (attended)**

Not executor steps: each reaches a network or holds a secret, and the owner runs them or watches them run. `W$` is the workstation, in the repo root unless a step says otherwise. O1 and O2 are `## Rollout (attended)` steps P3 and P4: they land on this branch before the pull request opens, so the role, its secrets and an exporter line checked against its source merge together. The digest read, the converges, the forced failover and the records are the Rollout's R0, R5, R6 and R9, run from merged `develop`; the cache nodes do not speak to the venue, so the Kraken maintenance-window rule of `.claude/rules/fleet-deploys.md` does not gate them, and this task opens no public port, since 6379 and 26379 are accepted on `zcache0` alone by Task 2's nftables rules, so the Linode Cloud Firewall takes no edit here.

O1. `W$` The five passwords, generated and encrypted in one pipe each, never typed, printed or passed as an argument (`ansible.cfg` supplies the vault password file, so `encrypt_string` takes no `--vault-password-file`):

```bash
cd infra/ansible
mkdir -p group_vars/cache_host
cat > group_vars/cache_host/vault.yml <<'VAULT'
---
# Per-value !vault. Each value is generated and encrypted in one pipe, never typed or printed:
#   openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>
VAULT
for k in cache_engine_password cache_replica_password cache_sentinel_password cache_sentinel_requirepass cache_exporter_password; do
  openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name "$k" >> group_vars/cache_host/vault.yml
done
grep -o '^[a-z_]*: !vault' group_vars/cache_host/vault.yml
uv run ansible zcrypto-valkey1 -m ansible.builtin.debug -a 'msg={{ [cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass, cache_exporter_password] | map("length") | list }}'
cd ../..
```

Expected: the five key names, one `: !vault` line each; the `debug` (controller-side, no connection to the node) prints `[48, 48, 48, 48, 48]` and no value. Commit, the executor writing its own model name in place of `<model>` if a session makes the commit:

```bash
git add infra/ansible/group_vars/cache_host/vault.yml
git commit -m "chore(fleet): the cache nodes' five Valkey and Sentinel passwords, vaulted per value

cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass
and cache_exporter_password in group_vars/cache_host/vault.yml, each 48 hex characters from
openssl rand, encrypted by encrypt_string in the same pipe; the cache role's password refusal
admits all five.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

O2. `W$` The exporter's ACL line against the README of the redis_exporter the pinned Alloy embeds, Alloy v1.19.2 (`b8ec653c4423` in `docs/reference/fleet-pins.md`). Read before any converge: Valkey refuses to start on an `aclfile` token it does not know, and the file is re-rendered only under `-e cache_config_reset=true`.

```bash
curl -fsSL https://raw.githubusercontent.com/grafana/alloy/v1.19.2/go.mod | grep -i 'redis_exporter'
curl -fsSL "https://raw.githubusercontent.com/oliver006/redis_exporter/<version>/README.md" | grep -F -- '+@connection'
grep -F 'user exporter ' infra/ansible/roles/cache/templates/users.acl.j2
```

`<version>` is the one the first command prints on its `require` line, or the target of a `replace` line when it prints one, in which case the README is read from that fork at that version. Expected: the first command prints `github.com/oliver006/redis_exporter v1.86.0` and no `replace` line, and the README's data-node ACL line (the one whose tokens include `+memory`) carries the template's `exporter` tokens, in any order, plus three the template leaves out on purpose: `+arcount`, a command Valkey 9.1.2 does not know, so an `aclfile` naming it aborts Valkey's start; and `+cluster|slots` and `+cluster|nodes`, which serve a cluster-mode server this set does not run. At v1.86.0 the exporter scrapes a primary, a replica and a Sentinel with no error under the template's line. A README token is never copied into the template to make the two agree: any other version, or any difference beyond those three tokens, goes to the owner before the branch merges, since the file is re-rendered only under a reset and a token Valkey refuses keeps the node from starting.

---

### Task 5: The cache nodes ship their telemetry, and the Cache board, the zcrypto-cache rules and their runbook land

*Rulings: R7 removed this task's own probe and has it admit, chart and alert on Task 3's `zcache-probe` over all four mesh members (both keep lists, `CAPTURE_REQUIRED`, `PUBLISHER_HOSTS`, `_APP`); R9 kept Task 4's six Valkey and Sentinel absences and gave legs to the three Alloy caps alone; R10 moved the Alloy project under `/opt/zcrypto-cache/alloy` and the runbook's reads onto Task 4's `cli-*.env` files; R12 kept the two proxy rules out; R14 stated the job-label reading as a claim; R16 added the autonomy re-measure step; R1 and R18 moved the converges and the push to the Rollout. The nodes' `node_reboot_required` comes from Task 4's copy of the capture role's reboot check, which this task admits and charts.*

This task is spec D12 for the parts that exist once rollout steps 1–3 of D15 have run: each node's own Alloy, the admission, chart and rule of Task 3's mesh probe on all four members, the node families in the fleet's keep-list and topology tests, the `Cache` board without its proxy row, the `zcrypto-cache` rule group without the two proxy rules, the Alloy headroom legs for the three nodes, `infra/runbooks/cache.md`, and the fleet page's rows for what the plan adds. The engine host's scrape of the proxy's `:9104`, the proxy row and the two proxy rules (`the proxy with no UP backend`, `the engine holding no session through the proxy`) are not in this plan; the board's rows are numbered so the proxy row can take `400` later and the logs row moves then. Two commits: Steps 1–9 land the node's telemetry and the mesh probe's admission on the nodes' keep list (commit A), Steps 10–20 the board, the rules, the runbook, the fleet page and the probe's admission on the capture keep list, beside the rule that reads it (commit B); commit B's tests read commit A's files.

Decisions this section takes, where the spec leaves them open:

- **The probe is Task 3's** (ruling R7). `roles/cache_link`'s `zcache-probe` runs each minute on all four mesh members and writes `zcache_wireguard_handshake_age_seconds{peer="<mesh address>"}` for every `/32` `AllowedIPs` line of the rendered `zcache0.conf` into `/var/lib/zcrypto-node-textfile/zcache.prom`, `+Inf` for a peer with no handshake or an interface that is down: the directory the capture Alloy on `zcrypto` already reads and the nodes' Alloy reads through its `/:/host/root:ro` mount. This task admits the family on both keep lists, the nodes' `config.alloy` and the capture role's with `CAPTURE_REQUIRED` beside it (the capture list is shared with `zcrypto-red`, which runs no `cache_link` and publishes none), maps `infra/ansible/roles/cache_link/` to `zcrypto` and the three nodes in `PUBLISHER_HOSTS`, widens `_APP` to the `zcache` namespace, charts the family and writes the >180 s rule over all four members, so each link is watched from both ends. The `peer` label is the mesh address; the runbook and the rule summary map the four addresses. `node_reboot_required` comes from Task 4's copy of the capture role's reboot check, which writes `reboot.prom` into the same directory; this task admits it and panel 106 draws it.
- **The handshake-stale rule reads the age now, not the age at the last write:** the recorded age plus `time() - node_textfile_mtime_seconds` of `zcache.prom`, so a stopped timer climbs past the bar instead of freezing below it, and the timer's own cadence cannot fire it. It selects `host=~"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3"`, the engine host's end included; the capture keep list already admits `node_textfile_mtime_seconds`.
- **The job labels.** The host scrape carries no `job_name`: an exporter target's own `job` label (`integrations/unix`, `integrations/self`) wins over a scrape's `job_name`, the way the capture config's `host` scrape ships `job="integrations/self"` with none set, and the Alloy headroom rule selects `job="integrations/self"`. The spec's `cache_host` job name would therefore be ignored; it is not written. The two Redis exporters' targets carry one built-in `job` between them, so each passes through a `discovery.relabel` that sets `job` to `valkey` or `sentinel`, and every rule and panel selects those. This reading, an exporter target's own `job` winning over the scrape's `job_name`, is a claim the plan review reads (ruling R14); `## Rollout (attended)` step R7 reads `count by (job) (up{host="zcrypto-valkey1"})` before anything is pushed, and a job that arrives otherwise is corrected there.
- **Sentinel mode is not an argument.** Alloy's `prometheus.exporter.redis` takes `redis_addr`, `redis_user` and `redis_password` (the spec's measured basis); the exporter detects a Sentinel from the `# Sentinel` section of its `INFO` (redis_exporter v1.86.0's `exporter.go`; Valkey's Sentinel prints no `redis_mode:` line) and publishes the `redis_sentinel_*` families from it. The Sentinel exporter carries no `redis_user`: Sentinel authenticates `requirepass` as its default user. `## Rollout (attended)` step R7 reads both exporters' output on db1 before anything is pushed.
- **Logs are keyed by container name**, `zcrypto-valkey`, `zcrypto-sentinel` and `grafana-alloy`, relabelled to `container` `valkey`, `sentinel` and `alloy`, plus Task 3's mesh probe unit `zcache-probe.service`, relabelled `zcache-probe`, kept for its failures. A journald-driver stream carries `docker.service` as its unit, so a unit arm cannot select it, and keying `zcrypto-cache.service` as well would ship each line twice when that unit runs the compose project attached. Valkey's and Sentinel's `#` marks become `level="WARNING"`, `.` `DEBUG`, the rest `INFO`.
- **The Alloy block copies the capture role's**: gated on `cache_alloy_digest is defined`, render-only (the operator starts it with `sudo docker compose up -d`), the drift assert outside the gate, the `reload alloy` handler. It adds two guards the capture block lacks: a refusal of a digest that is not `sha256:<64 hex>`, since an empty `-e cache_alloy_digest=` counts as defined, and the pins refusal the capture role runs for its own container, here over the running `grafana-alloy`. The capture block's stale-layout cleanup is not copied: a node never had that layout.
- **Rules:** the three Alloy-dark rules take the family's title, `Fleet · Alloy dark — Cache N`, in the `zcrypto-cache` group, `critical`, `noDataState: Alerting`; `zcrypto-cache-primary-count` is `critical` (no primary means nowhere to write); the replica, memory, AOF and handshake rules are `warning`. Every rule but the Alloy-dark three reads `noDataState: OK`, since its series stop when a node's telemetry does, which the Alloy-dark three own. `zcrypto-cache-primary-count` counts the primary the Sentinels agree on, `abs((count(count by (master_address) (redis_sentinel_master_status{job="sentinel"} == 1) >= 2) or on() vector(0)) - 1) and on() (count(up{job="sentinel"}) > 1)`: the addresses at least two of the three Sentinels name a healthy master, the quorum's view. A count of each node's own `role="master"` pages falsely twice over: when the primary's node alone goes dark, its role leaves the query while the other nodes' `up` keeps the rule armed, and after a primary's node dies, its last `role="master"` sample outlives it by the query lookback beside its successor's; one node's dark Sentinel costs a single vote of three. With three Sentinels at most one address holds two votes, so spec D12's "primary count not exactly one" reads as no agreed primary, and a node still calling itself master after a failover is `cache-rejoin-node`'s. The distance from one is written because the threshold node takes `gt`/`lt` alone (`tests/test_infra_alert_rules.py::_fires_on_absence` refuses `==`/`!=`), and the `and on()` arm empties the value while fewer than two nodes' Sentinel telemetry ships. The AOF rule multiplies `redis_aof_enabled` into the two statuses, so a node whose AOF is off fires too (spec D7 requires it on).
- **The runbook's Alloy-dark anchors live in `cache.md`, not `observability.md`**: that page's four stacked anchors share one procedure for the capture pair, ops and the NAS, and the cache nodes' procedure differs (their paths, their aliases, and the set watched from the other two nodes while one is dark). An anchor is defined in one file (`tests/test_infra_alert_rules.py::test_every_runbook_anchor_is_defined_in_exactly_one_file`), so `observability.md` gains one sentence pointing at `cache.md`, as it does for the bridgehead. The runbook's `valkey-cli` reads take their passwords from Task 4's root-only `/opt/zcrypto-cache/cli-exporter.env` and `cli-sentinel.env` through `docker exec --env-file`, never from Alloy's secrets file. The Alloy headroom leg's section in `infra/runbooks/fleet.md` names the cache caps and the Cache board panel, since the Fleet health board's panel 601 selects no cache node.
- **The metric names.** None was read from a live endpoint or re-read upstream for this plan. Held from the exporter's INFO-field map and the Alloy component documentation: `redis_up`, `redis_instance_info` and its `role` label, `redis_uptime_in_seconds`, `redis_connected_slaves`, `redis_master_repl_offset`, `redis_memory_used_bytes`, `redis_memory_max_bytes`, `redis_commands_processed_total`, `redis_connected_clients`, `redis_aof_enabled`, `redis_aof_last_write_status`, `redis_aof_last_bgrewrite_status`, `redis_rdb_last_bgsave_status`. Assumed: `redis_connected_slave_offset_bytes` and its `slave_ip` label, `redis_master_link_up`, `redis_sentinel_masters`, `redis_sentinel_master_status` and its `master_address` label, `redis_sentinel_master_sentinels`, `redis_sentinel_master_ok_sentinels`, `redis_sentinel_master_slaves` (the spec's measured basis lists the Sentinel names as unmeasured), and the built-in `job` label the relabel overrides. `## Rollout (attended)` step R7 reads every one of them on db1 before the push, and corrects the tree through a branch when one differs.

Interfaces this task takes from the tasks before it, by name; a mismatch is an open question for the plan review, not a guess the executor makes:

- Task 4's `infra/ansible/roles/cache/` exists with `tasks/main.yml`, `defaults/main.yml` and `handlers/main.yml`, each opening with `---`; this task appends to all three. Its compose project names its containers `zcrypto-valkey` and `zcrypto-sentinel`, logs through the journald driver, runs under `zcrypto-cache.service`, and uses host networking with Valkey on `127.0.0.1:6379` and Sentinel on `127.0.0.1:26379`. Its ACL user `exporter` exists, and its vault keys for the two passwords this task renders are `cache_exporter_password` and `cache_sentinel_requirepass` in `infra/ansible/group_vars/cache_host/vault.yml`. The monitored name is `zcache`.
- Task 3's `cache_link` role renders `/etc/wireguard/zcache0.conf` with one `AllowedIPs = <address>/32` line per peer, and its `zcache-probe` writes `zcache.prom` into `cache_link_textfile_dir`, `/var/lib/zcrypto-node-textfile`, on `zcrypto` and the three nodes.
- Task 1's `infra/ansible/scripts/converge.sh` carries `zcrypto-valkey1`–`3` in `HOSTS`, `cache` in `TAGNAMES` and `cache_alloy_digest` in `EVKEYS`; the `cache_host` group is a child of `observed`, so the six Grafana Cloud vault keys resolve on the nodes.
- Task 4 records its Valkey and Sentinel caps in `_HEADROOM_DELIBERATELY_ABSENT` for good (ruling R9) and owns the `_LIMITED_JOBS` entry for `infra/ansible/roles/cache/templates/compose.yaml.j2`; this task adds the Alloy entry beside it, with its legs, and touches neither. Task 4 also defines `CACHE` in `tests/test_infra_converge_guards.py`, which this task's cases reuse.

Every Python runs through `uv run`; every commit's consumers are the tests that read a file the commit changes, as `grep -rl` reads them over `tests/test_*.py` when this plan was written: `uv run pytest tests/test_bash_guard.py tests/test_clock_offset.py tests/test_code_prose_citations.py tests/test_config_selectors_are_parsed.py tests/test_count_list.py tests/test_dashboards_cover_metrics.py tests/test_engine_execgate.py tests/test_engine_journal_prune.py tests/test_engine_metrics.py tests/test_error_paths_are_logged.py tests/test_fleet_contracts.py tests/test_grafana_push_sh.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_infra_grafana_keepalive.py tests/test_internal_terms_not_operator_visible.py tests/test_merge_gate.py tests/test_message_citations.py tests/test_ops_daily.py tests/test_ops_postverify.py tests/test_prose_chars.py tests/test_reboot_check.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_ops_daily_soak.py tests/test_engine_soak.py -q -p no:cacheprovider` (the consumer command below; `tests/test_config_selectors_are_parsed.py` is in it because it reads every test module for substring selectors over a config file, this task's cases among them, and the two soak modules because commit B changes `infra/scripts/ops_daily.py`, which they read). No executor step reaches a host; the attended ones are `## Rollout (attended)`'s. The commit trailers name the executing model: the executor writes its own model name where the fences below say `<model>`.

**Files:**
- Create: `infra/ansible/roles/cache/files/config.alloy` (Task 5 commit A)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the keep regex's `|node_textfile_mtime_seconds|`, commit B)
- Create: `infra/ansible/roles/cache/templates/alloy-compose.yaml.j2` (commit A)
- Create: `infra/ansible/roles/cache/templates/alloy-secrets.env.j2` (commit A)
- Modify: `infra/ansible/roles/cache/tasks/main.yml` (appended after Task 4's last task, commit A)
- Modify: `infra/ansible/roles/cache/defaults/main.yml` (appended after Task 4's last key, commit A)
- Modify: `infra/ansible/roles/cache/handlers/main.yml` (appended after Task 4's last handler, commit A)
- Modify: `infra/grafana/alerts.yaml` (L4228–4238, the Alloy headroom rule's comment tail and expression; L4260–4261, its summary, commit A; appended after L4813, the `zcrypto-cache` group, commit B)
- Modify: `infra/grafana/notification-templates/zcrypto-slack.tmpl` (L25, commit A)
- Modify: `infra/runbooks/fleet.md` (L42, L46, L52, commit A)
- Create: `infra/grafana/cache-dashboard.json` (commit B)
- Create: `infra/runbooks/cache.md` (commit B)
- Modify: `infra/grafana/zcrypto-logs-dashboard.json` (L982, L988, L1024–1029, commit B)
- Modify: `infra/runbooks/observability.md` (L5, L24, and the `zcrypto-node-collector-failed` section's host list and dependents table, L79, L92, L95, commit B)
- Modify: `docs/reference/fleet.md` (the `grafana-alloy` row and three rows after the `access probe timers` row of Services and instruments, one Storage topology bullet, one Telemetry labels bullet after the one Task 1 rewrote, commit B)
- Test: `tests/test_infra_alloy_series.py` (L16, L303–307, L337–339, L353–355, L376–378, L388, L396, L482, appended after L597, commit A; `CAPTURE_REQUIRED`, commit B)
- Test: `tests/test_infra_converge_guards.py` (appended after its last line, commit A)
- Test: `tests/test_infra_alert_rules.py` (L1270, L1375–1377, L1443, commit A)
- Test: `tests/test_infra_compose_templates.py` (L131–135, commit A)
- Test: `tests/test_dashboards_cover_metrics.py` (L42–48, commit A; L66–67, L214–217, L505–507, before L516, commit B)
- Modify: `infra/scripts/ops_daily.py` (`_UID_HOST`, the line `    "zcrypto-alloy-dark-capture-secondary": "zcrypto-red",`, commit B)
- Test: `tests/test_ops_daily.py` (the parametrization of `test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away`, commit B)

**Interfaces:**
- Consumes: the names in the interface list above; `_compose_alloy_limit_bytes`, `_compose_alloy_gomemlimit_bytes`, `_rule`, `ANSIBLE`, `REPO` in `tests/test_infra_alert_rules.py`; `find_task`, `load_tasks`, `truthy`, `assert_that`, `when_conditions`, `ANSIBLE` in `tests/test_infra_converge_guards.py`; `_keep_regex`, `_drop_regex`, `_journal_keep_block`, `PROCESS_FAMILIES` in `tests/test_infra_alloy_series.py`; `panel_families`, `alerted_families`, `KEEP_REGEX_FILES` in `tests/test_dashboards_cover_metrics.py`.
- Produces: the metric families in `CACHE_REQUIRED` under `host="zcrypto-valkey1"`–`"zcrypto-valkey3"`, with `job="valkey"` and `job="sentinel"` on the Redis families, and `zcache_wireguard_handshake_age_seconds` under `host="zcrypto"` as well; Loki streams `{host="zcrypto-valkeyN", container=~"valkey|sentinel|alloy|zcache-probe"}`; the board `zcrypto-cache` with panel ids 101–108, 201–213, 301–305, 401–402 and the rows 100, 200, 300, 400; the eight rule uids in group `zcrypto-cache`; the runbook anchors `cache-manual-failover`, `cache-rejoin-node`, `cache-config-reset`, `cache-password-rotation` and one per uid; `_UID_HOST` entries in `infra/scripts/ops_daily.py` for the three Alloy-dark uids. The later proxy task adds its row, its two rules and their anchors to these three files.

- [ ] **Step 1: Write the failing tests for the node's telemetry**

In `tests/test_infra_alloy_series.py`, replace the line `ACCESS_ALLOY = REPO / "infra/ansible/roles/access/files/config.alloy"` with:

```python
ACCESS_ALLOY = REPO / "infra/ansible/roles/access/files/config.alloy"
CACHE_ALLOY = REPO / "infra/ansible/roles/cache/files/config.alloy"
CACHE_SECRETS = REPO / "infra/ansible/roles/cache/templates/alloy-secrets.env.j2"
```

Replace the five lines that close `ACCESS_REQUIRED` and open the next function, two blank lines among them —

```python
    *ACCESS_APP_SERIES,
]


def _keep_regex(path: Path) -> re.Pattern:
```

— with:

```python
    *ACCESS_APP_SERIES,
]

# The cache nodes' Valkey and Sentinel families, through Alloy's embedded Redis exporter; the Cache
# board and the zcrypto-cache rules read each of them.
CACHE_REDIS_SERIES = [
    "redis_up",
    "redis_instance_info",
    "redis_uptime_in_seconds",
    "redis_connected_slaves",
    "redis_master_repl_offset",
    "redis_connected_slave_offset_bytes",
    "redis_master_link_up",
    "redis_memory_used_bytes",
    "redis_memory_max_bytes",
    "redis_commands_processed_total",
    "redis_connected_clients",
    "redis_aof_enabled",
    "redis_aof_last_write_status",
    "redis_aof_last_bgrewrite_status",
    "redis_rdb_last_bgsave_status",
    "redis_sentinel_masters",
    "redis_sentinel_master_status",
    "redis_sentinel_master_sentinels",
    "redis_sentinel_master_ok_sentinels",
    "redis_sentinel_master_slaves",
]

# Exact, not a floor: the cache keep regex admits these and nothing else (the equality test below).
# The node families are the Cache board's and the fleet's host-unscoped rules' (`node_scrape_collector_
# success`, `node_filesystem_*`); the textfile three are the reboot check's flag, and the freshness and
# parse state of the directory the reboot check and the mesh probe write.
CACHE_REQUIRED = [
    "up",
    "node_load1",
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemTotal_bytes",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    "node_network_receive_bytes_total",
    "node_network_transmit_bytes_total",
    "node_scrape_collector_success",
    "node_reboot_required",
    "node_textfile_mtime_seconds",
    "node_textfile_scrape_error",
    "zcache_wireguard_handshake_age_seconds",
    *PROCESS_FAMILIES,
    *CACHE_REDIS_SERIES,
]


def _keep_regex(path: Path) -> re.Pattern:
```

In `test_keep_regex_admits_every_published_series`'s and `test_drop_regex_does_not_shadow_the_keep_list`'s parametrizations (both occurrences), replace

```python
        (ACCESS_ALLOY, ACCESS_REQUIRED),
    ],
    ids=["nas", "ops", "capture", "access"],
)
```

with

```python
        (ACCESS_ALLOY, ACCESS_REQUIRED),
        (CACHE_ALLOY, CACHE_REQUIRED),
    ],
    ids=["nas", "ops", "capture", "access", "cache"],
)
```

In `test_keep_regex_excludes_families_not_published_on_this_host`'s parametrization, replace

```python
        (ACCESS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES, *PROCESS_FAMILIES]),
    ],
    ids=["nas", "ops", "capture", "access"],
)
```

with

```python
        (ACCESS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES, *PROCESS_FAMILIES]),
        # Valkey, Sentinel and the probe are all that run on a cache node.
        (CACHE_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
    ],
    ids=["nas", "ops", "capture", "access", "cache"],
)
```

Replace both occurrences of the decorator line `@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY], ids=["nas", "ops", "capture", "access"])` (above `test_keep_regex_excludes_the_retired_sd_pair` and `test_alloy_self_metrics_are_dropped_before_the_keep`) with:

```python
@pytest.mark.parametrize(
    "path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY, CACHE_ALLOY], ids=["nas", "ops", "capture", "access", "cache"]
)
```

In `test_every_published_metric_is_admitted_by_some_hosts_keep_regex`, replace `    keeps = [_keep_regex(p) for p in (NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY)]` with `    keeps = [_keep_regex(p) for p in (NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY, CACHE_ALLOY)]`.

Append at the end of the file, after `test_the_journal_keep_regex_names_no_unit_the_role_does_not_install`:

```python
# --- the cache nodes' config ---------------------------------------------------------------------
def test_the_cache_keep_regex_admits_exactly_the_cache_required_list():
    """Both directions, where the per-host admission test reads one: a family the regex admits that the
    list lacks fails here as well as a listed one the regex drops. Whether each is read by a panel or a
    rule is test_dashboards_cover_metrics.py's."""
    admitted = _keep_regex(CACHE_ALLOY).pattern.removeprefix(r"\A(?:").removesuffix(r")\Z").split("|")
    assert sorted(admitted) == sorted(CACHE_REQUIRED), (
        f"the cache keep regex and CACHE_REQUIRED differ: admitted only {sorted(set(admitted) - set(CACHE_REQUIRED))}, "
        f"listed only {sorted(set(CACHE_REQUIRED) - set(admitted))}"
    )


def test_the_cache_secrets_template_renders_every_name_the_config_reads():
    """A name the config reads that the env file lacks is an empty string at runtime: remote_write or the
    exporter's AUTH fails with nothing in the tree to say why."""
    read = set(re.findall(r'sys\.env\("([A-Z_]+)"\)', CACHE_ALLOY.read_text()))
    rendered = set(re.findall(r"^([A-Z_]+)=", CACHE_SECRETS.read_text(), re.M))
    assert {"CACHE_EXPORTER_PASSWORD", "CACHE_SENTINEL_REQUIREPASS"} <= read, f"the config reads {sorted(read)}"
    assert read == rendered, f"config reads {sorted(read - rendered)} unrendered; template renders {sorted(rendered - read)} unread"


def test_the_redis_exporters_ship_under_the_jobs_the_rules_select():
    """Both exporters' targets carry the same built-in `job`, which wins over a scrape's `job_name`; the
    relabel is what makes `job="valkey"` and `job="sentinel"` exist at all."""
    cache_config = CACHE_ALLOY.read_text()
    targets = [line.split("=", 1)[1].strip() for line in cache_config.splitlines() if line.strip().startswith("targets ")]
    for job in ("valkey", "sentinel"):
        relabel = re.search(rf'discovery\.relabel "{job}" \{{(.*?)\n\}}', cache_config, re.S)
        assert relabel, f"no discovery.relabel for {job}"
        assert f"targets = prometheus.exporter.redis.{job}.targets" in relabel.group(1)
        assert 'target_label = "job"' in relabel.group(1) and f'replacement  = "{job}"' in relabel.group(1)
        assert f"discovery.relabel.{job}.output" in targets, f"the {job} scrape does not read its relabelled targets"


def test_the_cache_journal_keep_rule_keys_the_containers_by_name():
    """Keyed by container name: the journald-driver streams carry `docker.service` as their unit, so a unit
    arm cannot select them, and keying the unit that runs the compose project too would ship each line
    twice."""
    rule = _journal_keep_block(CACHE_ALLOY)
    regex = re.search(r'regex\s*=\s*"(.*?)"\n', rule).group(1)
    assert 'separator     = ";"' in rule and '["__journal__systemd_unit", "__journal_container_name"]' in rule
    assert regex == "zcache-probe\\\\.service;.*|.*;(zcrypto-valkey|zcrypto-sentinel|grafana-alloy)", regex


def test_the_cache_textfile_collector_reads_where_the_mesh_probe_writes():
    """The mesh probe of `roles/cache_link` writes zcache.prom into `cache_link_textfile_dir` and the cache role's
    reboot check writes reboot.prom into `cache_textfile_dir`; the node's Alloy reads that one directory through its
    `/:/host/root:ro` mount, so each path differs from the collector's by that prefix alone."""
    directory = re.search(r'textfile \{\s*directory = "([^"]+)"', CACHE_ALLOY.read_text())
    assert directory, "no textfile directory in the cache config"
    for role, var in (("cache_link", "cache_link_textfile_dir"), ("cache", "cache_textfile_dir")):
        written = re.search(rf"^{var}: (\S+)$", (REPO / f"infra/ansible/roles/{role}/defaults/main.yml").read_text(), re.M)
        assert written and directory.group(1) == "/host/root" + written.group(1), (role, written, directory.group(1))
```

Append at the end of `tests/test_infra_converge_guards.py`:

```python
# --- the cache nodes' Alloy: the digest shape, the pins refusal, and the drift assert ---------------
# `CACHE`, the cache role's tasks file, is defined above with the Valkey and Sentinel block's cases.
CACHE_ALLOY_DIGEST_SHAPE = "refuse an Alloy digest that is not a full sha256"
CACHE_ALLOY_PINS = "alloy pins recording — refuse to replace an Alloy digest fleet-pins.md does not record"
CACHE_ALLOY_PINS_ECHO = "alloy pins recording — the accepted override's reason, on the record"
CACHE_ALLOY_DRIFT = "assert the deployed alloy config matches the repo"
CACHE_ALLOY_RUNNING = {"cache_alloy_running_digest_probe": {"rc": 0, "stdout": "grafana/alloy@sha256:" + "a" * 64}}
CACHE_ALLOY_PINS_WITH = "| alloy | zcrypto-valkey1 | `" + "a" * 12 + "` — v1.19.2 | 2026-09-25 10:00:00 | prior |"
CACHE_ALLOY_PINS_WITHOUT = "| alloy | zcrypto-valkey1 | `" + "b" * 12 + "` — v1.19.2 | 2026-09-25 10:00:00 | prior |"


@pytest.mark.parametrize(
    ("digest", "expected"),
    [("sha256:" + "c" * 64, True), ("", False), ("sha256:" + "c" * 12, False), ("c" * 64, False)],
)
def test_cache_alloy_digest_must_be_a_full_sha256(digest, expected):
    task = find_task(load_tasks(CACHE), CACHE_ALLOY_DIGEST_SHAPE)
    assert truthy(assert_that(task), {"cache_alloy_digest": digest}) is expected


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (CACHE_ALLOY_PINS_WITH, "", True),
        (CACHE_ALLOY_PINS_WITHOUT, "", False),
        (CACHE_ALLOY_PINS_WITHOUT, "true", False),
        (CACHE_ALLOY_PINS_WITHOUT, "recorded in pins right after the emergency roll", True),
    ],
)
def test_cache_alloy_pins_recording_semantics(pins_text, override, expected):
    task = find_task(load_tasks(CACHE), CACHE_ALLOY_PINS)
    variables = {**CACHE_ALLOY_RUNNING, "cache_alloy_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected


def test_cache_alloy_pins_refusal_stands_down_when_no_alloy_runs():
    task = find_task(load_tasks(CACHE), CACHE_ALLOY_PINS)
    assert not truthy(when_conditions(task), {"cache_alloy_running_digest_probe": {"rc": 1, "stdout": ""}})


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [(CACHE_ALLOY_PINS_WITH, "a reason long enough", False), (CACHE_ALLOY_PINS_WITHOUT, "a reason long enough", True)],
)
def test_cache_alloy_pins_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    task = find_task(load_tasks(CACHE), CACHE_ALLOY_PINS_ECHO)
    variables = {**CACHE_ALLOY_RUNNING, "cache_alloy_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(task), variables) is expected


def test_the_cache_alloy_guards_run_only_on_a_converge_carrying_the_digest():
    block = next(t for t in load_tasks(CACHE) if t.get("name", "").startswith("install the cache telemetry stack"))
    assert block["when"] == "cache_alloy_digest is defined"
    names = [t["name"] for t in block["block"]]
    assert names.index(CACHE_ALLOY_DIGEST_SHAPE) == 0
    assert names.index(CACHE_ALLOY_PINS) < names.index("install the alloy pipeline config")


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({"cache_deployed_alloy_config": {"stat": {"exists": True}}}, True),
        ({"cache_deployed_alloy_config": {"stat": {"exists": False}}}, False),
        ({"cache_deployed_alloy_config": {"stat": {"exists": True}}, "cache_alloy_digest": "sha256:" + "c" * 64}, False),
    ],
)
def test_cache_alloy_drift_assert_runs_only_where_it_cannot_be_repaired(variables, expected):
    """A converge carrying the digest is about to copy the file; asserting first would fail the host
    before the copy that repairs it."""
    task = find_task(load_tasks(CACHE), CACHE_ALLOY_DRIFT)
    assert truthy(when_conditions(task), variables) is expected
    assert assert_that(task) == ["cache_deployed_alloy_config.stat.checksum == cache_repo_alloy_config.stat.checksum"]
```

In `tests/test_infra_alert_rules.py`, `_LIMITED_JOBS`, replace the line `    "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2": (("ops", "integrations/self"),),` with:

```python
    "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2": (("ops", "integrations/self"),),
    "infra/ansible/roles/cache/templates/alloy-compose.yaml.j2": (
        ("zcrypto-valkey1", "integrations/self"),
        ("zcrypto-valkey2", "integrations/self"),
        ("zcrypto-valkey3", "integrations/self"),
    ),
```

In `test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling`, replace

```python
        f"the shared leg must divide by the compose literal ({shared}); found: {expr!r}"
    )
```

with

```python
        f"the shared leg must divide by the compose literal ({shared}); found: {expr!r}"
    )
    # The cache nodes' own cap, half the shared one on a 1 GB node, read back from its compose literal.
    cache_cap = _compose_alloy_limit_bytes(ANSIBLE / "roles/cache/templates/alloy-compose.yaml.j2")
    assert re.search(
        rf'host=~"zcrypto-valkey1\|zcrypto-valkey2\|zcrypto-valkey3", job="integrations/self"\}}\s*/\s*{cache_cap}\b', expr
    ), f"the cache leg must divide by the cache compose literal ({cache_cap}); found: {expr!r}"
```

In `test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host`, replace the line `        ("nas", REPO / "infra/nas/compose.yaml"),` with:

```python
        ("nas", REPO / "infra/nas/compose.yaml"),
        ("zcrypto-valkey1", ANSIBLE / "roles/cache/templates/alloy-compose.yaml.j2"),
        ("zcrypto-valkey2", ANSIBLE / "roles/cache/templates/alloy-compose.yaml.j2"),
        ("zcrypto-valkey3", ANSIBLE / "roles/cache/templates/alloy-compose.yaml.j2"),
```

In `tests/test_infra_compose_templates.py`, `ALLOY_COMPOSE_FILES`, replace the line `    REPO / "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2",` with:

```python
    REPO / "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2",
    REPO / "infra/ansible/roles/cache/templates/alloy-compose.yaml.j2",
```

In `tests/test_dashboards_cover_metrics.py`, `KEEP_REGEX_FILES`, replace the line `    "zaccess": REPO / "infra/ansible/roles/access/files/config.alloy",` with:

```python
    "zaccess": REPO / "infra/ansible/roles/access/files/config.alloy",
    "zcrypto-valkey1": REPO / "infra/ansible/roles/cache/files/config.alloy",
    "zcrypto-valkey2": REPO / "infra/ansible/roles/cache/files/config.alloy",
    "zcrypto-valkey3": REPO / "infra/ansible/roles/cache/files/config.alloy",
```

- [ ] **Step 2: Run them and read the failure**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py tests/test_infra_alert_rules.py tests/test_infra_compose_templates.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`
Expected: every failure reads a file this task creates, or a line it adds, and nothing else fails. The failures, by test: in `test_infra_alloy_series.py` the `[cache]` case of each widened parametrization, the five `test_the_cache_*`/`test_the_redis_exporters_*` cases and every case of `test_every_published_metric_is_admitted_by_some_hosts_keep_regex` (`FileNotFoundError` on `config.alloy`, one per published name); the 15 `cache_alloy` cases in `test_infra_converge_guards.py` (14 on `KeyError` for the task name, and `test_the_cache_alloy_guards_run_only_on_a_converge_carrying_the_digest` on `StopIteration`, its `next(...)` finding no block); `test_the_alloy_config_is_never_bind_mounted_as_a_single_file[templates2]`; `test_every_alerted_family_is_admitted_where_its_rule_selects` (`FileNotFoundError` on `config.alloy`); and in `test_infra_alert_rules.py` `test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence`, `test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling` and `test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host`.

- [ ] **Step 3: The node's config.alloy**

Create `infra/ansible/roles/cache/files/config.alloy`:

```alloy
// Grafana Alloy config for a cache node (zcrypto-valkey1/2/3). Installed by the `cache` role with
// `ansible.builtin.copy` at cache_alloy_dir/conf/config.alloy, so edit this file, never the host's copy.
// files/, not templates/: `copy:` searches only a role's files/ dir, and the `{{ }}` in the log stages
// below would be read by Jinja2. The `host` label is `constants.hostname`, which under `network_mode:
// host` is the node's own name, so this one static file labels all three nodes. Credentials arrive as
// environment variables from alloy-secrets.env (0600, rendered by the role), read with `sys.env(...)`.
//
// EDITING NOTE -- test suites pull assignments out of this file by PREFIX (`line.strip().startswith(<key>)`).
// Keep every config key the first non-space token on exactly one line.

// ---- Host metrics -------------------------------------------------------------------------------
// The textfile directory is where the cache_link role's mesh probe (zcache-probe) writes zcache.prom,
// each mesh peer's handshake age, and the cache role's reboot check reboot.prom, the pending-reboot
// flag. It sits inside the `/:/host/root:ro` mount.
prometheus.exporter.unix "host" {
  set_collectors = ["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"]

  procfs_path = "/host/proc"
  sysfs_path  = "/host/sys"
  rootfs_path = "/host/root"

  textfile {
    directory = "/host/root/var/lib/zcrypto-node-textfile"
  }
}

// Alloy's own process_* families, for the fleet's Alloy memory-headroom rule (job="integrations/self").
prometheus.exporter.self "alloy" {}

// No `job_name` here: exporter targets carry their own `job` label (integrations/unix, integrations/self),
// which wins over a scrape's job_name, and the headroom rule selects job="integrations/self".
prometheus.scrape "cache_host" {
  targets         = array.concat(prometheus.exporter.unix.host.targets, prometheus.exporter.self.alloy.targets)
  forward_to      = [prometheus.remote_write.grafana.receiver]
  scrape_interval = "60s"
}

// ---- Valkey and Sentinel ------------------------------------------------------------------------
// The exporter detects Sentinel from the `# Sentinel` section of the server's INFO and publishes the
// redis_sentinel_* families from it; no argument selects that mode. The Sentinel has no ACL user, only
// its requirepass.
prometheus.exporter.redis "valkey" {
  redis_addr     = "127.0.0.1:6379"
  redis_user     = "exporter"
  redis_password = sys.env("CACHE_EXPORTER_PASSWORD")
}

prometheus.exporter.redis "sentinel" {
  redis_addr     = "127.0.0.1:26379"
  redis_password = sys.env("CACHE_SENTINEL_REQUIREPASS")
}

// Both exporters' targets carry the same built-in `job`, so each is relabelled to its own: every
// dashboard panel and alert rule selects job="valkey" or job="sentinel".
discovery.relabel "valkey" {
  targets = prometheus.exporter.redis.valkey.targets

  rule {
    target_label = "job"
    replacement  = "valkey"
  }
}

discovery.relabel "sentinel" {
  targets = prometheus.exporter.redis.sentinel.targets

  rule {
    target_label = "job"
    replacement  = "sentinel"
  }
}

prometheus.scrape "valkey" {
  targets         = discovery.relabel.valkey.output
  job_name        = "valkey"
  forward_to      = [prometheus.remote_write.grafana.receiver]
  scrape_interval = "60s"
}

prometheus.scrape "sentinel" {
  targets         = discovery.relabel.sentinel.output
  job_name        = "sentinel"
  forward_to      = [prometheus.remote_write.grafana.receiver]
  scrape_interval = "60s"
}

// ---- remote_write -------------------------------------------------------------------------------
prometheus.remote_write "grafana" {
  external_labels = {
    host = constants.hostname,
  }

  endpoint {
    url = sys.env("GRAFANA_PROM_URL")

    basic_auth {
      username = sys.env("GRAFANA_PROM_USERNAME")
      password = sys.env("GRAFANA_PROM_PASSWORD")
    }

    // Alloy's own internals first, then keep-only: a series the keep regex does not list does not
    // exist in Grafana. The list is the families the Cache board and the rules read, `up`, the fleet's
    // unscoped node rules' families, and the six process_* names; tests/test_infra_alloy_series.py
    // holds it to CACHE_REQUIRED exactly.
    write_relabel_config {
      source_labels = ["__name__"]
      regex         = "go_.*|alloy_.*"
      action        = "drop"
    }

    write_relabel_config {
      source_labels = ["__name__"]
      regex         = "up|node_load1|node_cpu_seconds_total|node_memory_MemAvailable_bytes|node_memory_MemTotal_bytes|node_filesystem_avail_bytes|node_filesystem_size_bytes|node_network_receive_bytes_total|node_network_transmit_bytes_total|node_scrape_collector_success|node_reboot_required|node_textfile_mtime_seconds|node_textfile_scrape_error|zcache_wireguard_handshake_age_seconds|process_cpu_seconds_total|process_max_fds|process_open_fds|process_resident_memory_bytes|process_start_time_seconds|process_virtual_memory_bytes|redis_up|redis_instance_info|redis_uptime_in_seconds|redis_connected_slaves|redis_master_repl_offset|redis_connected_slave_offset_bytes|redis_master_link_up|redis_memory_used_bytes|redis_memory_max_bytes|redis_commands_processed_total|redis_connected_clients|redis_aof_enabled|redis_aof_last_write_status|redis_aof_last_bgrewrite_status|redis_rdb_last_bgsave_status|redis_sentinel_masters|redis_sentinel_master_status|redis_sentinel_master_sentinels|redis_sentinel_master_ok_sentinels|redis_sentinel_master_slaves"
      action        = "keep"
    }
  }
}

// ---- Logs: the host journal ---------------------------------------------------------------------
// Valkey, Sentinel and Alloy log through the journald driver, so their lines are keyed by container
// name, never by the unit that starts them: a compose project run attached under a unit copies the same
// lines into that unit's journal, and keying both would ship each line twice. The mesh probe's unit is
// kept for its failures.
loki.relabel "journal_units" {
  forward_to = []

  rule {
    source_labels = ["__journal__systemd_unit", "__journal_container_name"]
    separator     = ";"
    regex         = "zcache-probe\\.service;.*|.*;(zcrypto-valkey|zcrypto-sentinel|grafana-alloy)"
    action        = "keep"
  }

  // Unit name minus ".service" -> `container`; the container-name rules below overwrite it for the
  // journald-driver streams, whose unit is docker.service. The order is load-bearing.
  rule {
    source_labels = ["__journal__systemd_unit"]
    regex         = "(.+)\\.service"
    target_label  = "container"
    replacement   = "$1"
  }

  rule {
    source_labels = ["__journal_container_name"]
    regex         = "zcrypto-(valkey|sentinel)"
    target_label  = "container"
    replacement   = "$1"
  }

  rule {
    source_labels = ["__journal_container_name"]
    regex         = "grafana-alloy"
    target_label  = "container"
    replacement   = "alloy"
  }

  rule {
    target_label = "host"
    replacement  = constants.hostname
  }
}

loki.source.journal "cache_units" {
  path          = "/host/journal"
  relabel_rules = loki.relabel.journal_units.rules
  forward_to    = [loki.process.parse.receiver]
  // Unset, an outage longer than 7h skips the journal between the cursor and now-7h for good.
  max_age       = "48h"
}

loki.process "parse" {
  forward_to = [loki.write.grafana.receiver]

  stage.match {
    selector = "{container=\"alloy\"}"

    stage.logfmt {
      mapping = { "level" = "" }
    }

    stage.template {
      source   = "level"
      template = "{{ if eq .Value \"warn\" }}WARNING{{ else if eq .Value \"fatal\" }}CRITICAL{{ else }}{{ ToUpper .Value }}{{ end }}"
    }

    stage.labels {
      values = { level = "level" }
    }
  }

  // Valkey's and Sentinel's line is `<pid>:<role> <dd Mon yyyy hh:mm:ss.mmm> <mark> <message>`, the
  // mark `#` for a warning, `*` for a notice, `-` verbose and `.` debug. A line of another shape
  // renders an empty level, which the labels stage drops, so it ships with no `level` label.
  stage.match {
    selector = "{container=~\"valkey|sentinel\"}"

    stage.regex {
      expression = "^\\d+:[XCSM] \\d{2} \\w{3} \\d{4} [\\d:.]+ (?P<mark>[.*#-]) "
    }

    stage.template {
      source   = "mark"
      template = "{{ if eq .Value \"#\" }}WARNING{{ else if eq .Value \".\" }}DEBUG{{ else if .Value }}INFO{{ end }}"
    }

    stage.labels {
      values = { level = "mark" }
    }
  }
}

loki.write "grafana" {
  endpoint {
    url = sys.env("GRAFANA_LOKI_URL")

    basic_auth {
      username = sys.env("GRAFANA_LOKI_USERNAME")
      password = sys.env("GRAFANA_LOKI_PASSWORD")
    }
  }
}
```

- [ ] **Step 4: The Alloy compose and secrets templates, the defaults, the handler and the tasks**

Create `infra/ansible/roles/cache/templates/alloy-compose.yaml.j2`:

```yaml
# Grafana Alloy compose file for a cache node, rendered by the `cache` role at
# {{ cache_alloy_dir }}/compose.yaml; edit infra/ansible/roles/cache/templates/alloy-compose.yaml.j2.
# Its own compose project, apart from Valkey's and Sentinel's, so an Alloy redeploy never restarts
# either. The role renders it and never starts it: `sudo docker compose up -d` in this directory is
# the operator's step.
services:
  alloy:
    image: "{{ cache_alloy_image }}@{{ cache_alloy_digest }}"
    container_name: grafana-alloy
    restart: unless-stopped
    # The dedicated non-login `zcrypto-alloy` user: /:/host/root is mounted below, and a key-owning
    # user would read its own ~/.ssh straight through it.
    user: "{{ cache_alloy_uid }}:{{ cache_alloy_gid }}"
    group_add:
      # The host's systemd-journal gid, numeric and looked up at converge time: the journal files are
      # root:systemd-journal 0640.
      - "{{ cache_journal_gid }}"
    network_mode: host
    environment:
      # 0.9 of the memory cap below, the fleet's ratio (tests/test_infra_alert_rules.py holds it).
      GOMEMLIMIT: 230MiB
    env_file:
      # The six Grafana Cloud names and the two cache passwords config.alloy reads, 0600, owned by
      # `zcrypto-alloy`, rendered with no_log and diff false.
      - ./alloy-secrets.env
    command:
      - run
      - --storage.path=/var/lib/alloy
      - --server.http.listen-addr=127.0.0.1:12345
      - /etc/alloy/config.alloy
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/host/root:ro
      # The directory, not the file: a single-file bind mount binds the inode, which Ansible's atomic
      # write replaces, and the container would keep reading the old file.
      - ./conf:/etc/alloy:ro
      # The remote_write WAL and the journal cursor survive a container replacement here.
      - ./alloy-data:/var/lib/alloy
      - /var/log/journal:/host/journal:ro
      # The journal reader resolves the current boot's files through the machine id.
      - /etc/machine-id:/etc/machine-id:ro
    deploy:
      resources:
        limits:
          memory: 256m
          cpus: "0.5"
    logging:
      driver: journald
```

Create `infra/ansible/roles/cache/templates/alloy-secrets.env.j2`:

```
# A cache node's Alloy credentials, rendered by the `cache` role from group_vars/observed/vault.yml
# and group_vars/cache_host/vault.yml; do not hand-edit on the host. The names must match
# config.alloy's `sys.env(...)` calls: tests/test_infra_alloy_series.py holds the two sets equal.
GRAFANA_PROM_URL={{ grafana_prom_url }}
GRAFANA_PROM_USERNAME={{ grafana_prom_user }}
GRAFANA_PROM_PASSWORD={{ grafana_prom_token }}
GRAFANA_LOKI_URL={{ grafana_loki_url }}
GRAFANA_LOKI_USERNAME={{ grafana_loki_user }}
GRAFANA_LOKI_PASSWORD={{ grafana_loki_token }}
CACHE_EXPORTER_PASSWORD={{ cache_exporter_password }}
CACHE_SENTINEL_REQUIREPASS={{ cache_sentinel_requirepass }}
```

Append to `infra/ansible/roles/cache/defaults/main.yml`, after Task 4's last key, one blank line first:

```yaml
# The node's own Grafana Cloud shipper. `cache_alloy_digest` has no default and is passed per run: a
# converge without it skips the Alloy block rather than rendering a compose file pointing at a broken
# image reference. The secrets file has no var because alloy-compose.yaml.j2 names it relatively.
cache_alloy_dir: /opt/zcrypto-cache/alloy
cache_alloy_image: grafana/alloy
```

Append to `infra/ansible/roles/cache/handlers/main.yml`, after Task 4's last handler, one blank line first:

```yaml
- name: reload alloy
  # A reload, never a recreate: the directory mount lands the new file in place, and this role never
  # owns the stack's lifecycle. `-1` is the connection failure of an Alloy that is not running, which
  # passes; a 4xx or 5xx from a running one fails, or the copy reports `ok` and nothing re-notifies.
  ansible.builtin.uri:
    url: http://127.0.0.1:12345/-/reload
    method: POST
    status_code: [200, -1]
  register: cache_alloy_reload
  changed_when: cache_alloy_reload.status | default(0) == 200
```

Append to `infra/ansible/roles/cache/tasks/main.yml`, after Task 4's last task, one blank line first:

```yaml
# ---- The node's telemetry ---------------------------------------------------------------------------
# Alloy reads the mesh probe's zcache.prom from the directory the cache_link role creates and writes.
# Outside the gate on purpose: a converge that omits the digest skips the config copy and exits 0, so a
# host could serve a stale keep regex indefinitely. It asserts only when a config is already deployed.
- name: read the deployed alloy config's checksum (drift check, never gated on the digest)
  ansible.builtin.stat:
    path: "{{ cache_alloy_dir }}/conf/config.alloy"
    checksum_algorithm: sha256
    get_checksum: true
  register: cache_deployed_alloy_config

# On the controller, with stat rather than lookup+hash: the file lookup strips the trailing newline, so
# its hash never equals the file's and the assert below would fail on every host.
- name: read the repo's alloy config checksum (controller-side, same algorithm)
  ansible.builtin.stat:
    path: "{{ role_path }}/files/config.alloy"
    checksum_algorithm: sha256
    get_checksum: true
  register: cache_repo_alloy_config
  delegate_to: localhost
  become: false
  changed_when: false

- name: assert the deployed alloy config matches the repo
  ansible.builtin.assert:
    that: "cache_deployed_alloy_config.stat.checksum == cache_repo_alloy_config.stat.checksum"
    fail_msg: >-
      The Alloy config on this node does not match the repo. A converge that omits
      `cache_alloy_digest` skips the config copy and still exits 0, so the node can serve a stale
      keep regex while every other check passes. Re-run this converge with
      `-e cache_alloy_digest=<currently-running>`: that run copies the file and its handler reloads a
      running Alloy; if the container is down, its next start reads the new file.
    success_msg: "deployed Alloy config matches the repo"
  # A run carrying the digest is about to copy the file, so asserting first would fail the host before
  # the copy that repairs it.
  when:
    - cache_alloy_digest is not defined
    - cache_deployed_alloy_config.stat.exists

- name: install the cache telemetry stack — Grafana Alloy (needs the pinned Alloy digest)
  when: cache_alloy_digest is defined
  block:
    # An empty `-e cache_alloy_digest=` counts as defined and would render `grafana/alloy@`.
    - name: refuse an Alloy digest that is not a full sha256
      ansible.builtin.assert:
        that: cache_alloy_digest is match('^sha256:[0-9a-f]{64}$')
        fail_msg: >-
          cache_alloy_digest is not sha256:<64 hex>, so the compose file would name an image docker
          cannot pull. Pass the multi-arch index digest, e.g. -e cache_alloy_digest=sha256:<64 hex>.

    - name: alloy pins recording — probe the Alloy digest this converge would replace
      ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' grafana-alloy
      register: cache_alloy_running_digest_probe
      failed_when: false
      changed_when: false
      check_mode: false

    - name: alloy pins recording — read fleet-pins.md from the controller tree
      ansible.builtin.set_fact:
        cache_alloy_fleet_pins_text: "{{ lookup('file', playbook_dir ~ '/../../docs/reference/fleet-pins.md') }}"
      when: cache_alloy_running_digest_probe.rc == 0

    # A tag-started image ref makes regex_search yield None, which replace() turns into the needle
    # 'None', which no pins row carries: that ref fails closed.
    - name: alloy pins recording — refuse to replace an Alloy digest fleet-pins.md does not record
      ansible.builtin.assert:
        that: >-
          ((cache_alloy_running_digest_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in cache_alloy_fleet_pins_text)
          or ((pins_override | default('') | string | length > 8)
              and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
        fail_msg: >-
          The Alloy digest this converge replaces ({{ cache_alloy_running_digest_probe.stdout }}) is not
          recorded in docs/reference/fleet-pins.md, and an unrecorded pin is one image prune from an
          unrecoverable rollback. Record the running digest there first, or pass
          -e '{"pins_override": "<reason>"}' and record it immediately after.
      when: cache_alloy_running_digest_probe.rc == 0 and cache_alloy_fleet_pins_text is defined

    - name: alloy pins recording — the accepted override's reason, on the record
      ansible.builtin.debug:
        msg: "pins_override accepted: {{ pins_override }}"
      when: >-
        cache_alloy_running_digest_probe.rc == 0 and cache_alloy_fleet_pins_text is defined
        and not ((cache_alloy_running_digest_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in cache_alloy_fleet_pins_text)
        and (pins_override | default('') | string | length > 8)
        and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])

    - name: create the zcrypto-alloy system user (nologin, non-key-owning, dedicated to Alloy)
      ansible.builtin.user:
        name: zcrypto-alloy
        system: true
        shell: /usr/sbin/nologin
        create_home: false
        state: present

    - name: look up the zcrypto-alloy account
      ansible.builtin.getent:
        database: passwd
        key: zcrypto-alloy
      register: cache_alloy_getent
      # A node's first converge previews under --check before the account exists, so the lookup
      # comes up empty there alone; the cache role's own account lookup does the same.
      failed_when: cache_alloy_getent is failed and not ansible_check_mode

    - name: derive the zcrypto-alloy uid/gid for the container user mapping
      ansible.builtin.set_fact:
        cache_alloy_uid: "{{ cache_alloy_passwd['zcrypto-alloy'][1] if cache_alloy_known else 'first-run-check-mode' }}"
        cache_alloy_gid: "{{ cache_alloy_passwd['zcrypto-alloy'][2] if cache_alloy_known else 'first-run-check-mode' }}"
      vars:
        cache_alloy_passwd: "{{ ansible_facts['getent_passwd'] | default({}) }}"
        cache_alloy_known: "{{ (cache_alloy_passwd['zcrypto-alloy'] | default(none)) is not none }}"

    - name: look up the systemd-journal group (Alloy's journal-read group_add needs its numeric gid)
      ansible.builtin.getent:
        database: group
        key: systemd-journal

    - name: derive the systemd-journal group's numeric gid for the alloy container's group_add
      ansible.builtin.set_fact:
        cache_journal_gid: "{{ ansible_facts['getent_group']['systemd-journal'][1] }}"

    - name: ensure the alloy project directory exists
      ansible.builtin.file:
        path: "{{ cache_alloy_dir }}"
        state: directory
        owner: root
        group: root
        mode: "0755"

    # Owned by the Alloy user, which writes the remote_write WAL and the journal cursor here.
    - name: ensure the alloy data directory exists, owned by the dedicated Alloy user
      ansible.builtin.file:
        path: "{{ cache_alloy_dir }}/alloy-data"
        state: directory
        owner: zcrypto-alloy
        group: zcrypto-alloy
        mode: "0755"

    # Its own directory, which the compose file mounts: the project directory also holds
    # alloy-secrets.env, which must not appear inside the container at a second path.
    - name: ensure the alloy config directory exists
      ansible.builtin.file:
        path: "{{ cache_alloy_dir }}/conf"
        state: directory
        owner: root
        group: root
        mode: "0755"

    - name: install the alloy pipeline config
      ansible.builtin.copy:
        src: config.alloy
        dest: "{{ cache_alloy_dir }}/conf/config.alloy"
        owner: root
        group: root
        mode: "0644"
      notify: reload alloy

    # no_log with diff false: without both, a converge prints the Grafana Cloud credentials and the two
    # cache passwords. Owned by the Alloy user so it can read a 0600 file.
    - name: render the alloy secrets env file
      ansible.builtin.template:
        src: alloy-secrets.env.j2
        dest: "{{ cache_alloy_dir }}/alloy-secrets.env"
        owner: zcrypto-alloy
        group: zcrypto-alloy
        mode: "0600"
      no_log: true
      diff: false

    - name: render the alloy compose file
      ansible.builtin.template:
        src: alloy-compose.yaml.j2
        dest: "{{ cache_alloy_dir }}/compose.yaml"
        owner: root
        group: root
        mode: "0644"
```

- [ ] **Step 5: The headroom legs, the Slack names and the fleet runbook's headroom section**

In `infra/grafana/alerts.yaml`, rule `zcrypto-fleet-alloy-memory-headroom`, replace the two comment lines

```yaml
      # before reading a higher value as staleness rather than growth. The
      # bridgehead runs Alloy from apt with no container cap, which is why it is outside the leg.
```

with

```yaml
      # before reading a higher value as staleness rather than growth. The
      # bridgehead runs Alloy from apt with no container cap, which is why it is outside the leg.
      # The three cache nodes are 1 GB machines whose caps are budgeted to 576 MiB in all, so their
      # Alloy is capped at 256m with GOMEMLIMIT at the same 0.9 of it.
```

and the expression's second line and the `instant:` line under it,

```yaml
            or (process_resident_memory_bytes{host=~"zcrypto|zcrypto-red|nas", job="integrations/self"} / 536870912)
          instant: true
```

with

```yaml
            or (process_resident_memory_bytes{host=~"zcrypto|zcrypto-red|nas", job="integrations/self"} / 536870912)
            or (process_resident_memory_bytes{host=~"zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3", job="integrations/self"} / 268435456)
          instant: true
```

and in its summary the two lines

```yaml
        Grafana Alloy on a fleet host is using more than 90% of its container memory limit — 1 GiB on Ops, 512 MiB on the Capture
        primary, the Capture secondary and the NAS. Alloy runs closer to its ceiling than the app daemons do by design, and the `host`
```

with

```yaml
        Grafana Alloy on a fleet host is using more than 90% of its container memory limit — 1 GiB on Ops, 512 MiB on the Capture
        primary, the Capture secondary and the NAS, 256 MiB on Cache 1, Cache 2 and Cache 3. Alloy runs closer to its ceiling than the app daemons do by design, and the `host`
```

In `infra/grafana/notification-templates/zcrypto-slack.tmpl`, replace the line `  {{- else if eq . "zaccess" }}Edge` with:

```
  {{- else if eq . "zaccess" }}Edge
  {{- else if eq . "zcrypto-valkey1" }}Cache 1
  {{- else if eq . "zcrypto-valkey2" }}Cache 2
  {{- else if eq . "zcrypto-valkey3" }}Cache 3
```

In `infra/runbooks/fleet.md`, section `zcrypto-fleet-alloy-memory-headroom`, make three replacements.

`Grafana Alloy there has been above **90 % of its container limit** — 1 GiB on ops, 512 MiB on zcrypto, zcrypto-red and nas — for fifteen minutes.` becomes `Grafana Alloy there has been above **90 % of its container limit** — 1 GiB on ops, 512 MiB on zcrypto, zcrypto-red and nas, 256 MiB on the three cache nodes zcrypto-valkey1 to zcrypto-valkey3 — for fifteen minutes.`

`Each host is read against **its own** cap — 1 GiB on ops, 512 MiB on the other three — and panel 601 plots raw RSS, so divide before judging:` becomes `Each host is read against **its own** cap — 1 GiB on ops, 256 MiB on the cache nodes, 512 MiB on the other three — and panel 601 plots raw RSS, so divide before judging:`

`1. **Read which host, and against its own history** — the fleet board's *Daemon memory* panel (601), `job="integrations/self"`.` becomes `1. **Read which host, and against its own history** — the fleet board's *Daemon memory* panel (601), `job="integrations/self"`; a cache node is on the Cache board's *Alloy memory against its 256 MiB cap* panel (107), already divided.` — the rest of that list item stays as it is.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py tests/test_infra_alert_rules.py tests/test_infra_compose_templates.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`
Expected: every test passed.

Then the consumer command of this task's preamble. Expected: every test passed or skipped by a data gate, none failed.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed (yamllint and ansible-lint over the role, ruff over the tests); re-run after any rewrite until clean, then stage what it rewrote. Then `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/fleet.md` — Expected: no output.

- [ ] **Step 8: Commit A**

```bash
git add infra/ansible/roles/cache/files/config.alloy infra/ansible/roles/cache/templates/alloy-compose.yaml.j2 infra/ansible/roles/cache/templates/alloy-secrets.env.j2 infra/ansible/roles/cache/tasks/main.yml infra/ansible/roles/cache/defaults/main.yml infra/ansible/roles/cache/handlers/main.yml infra/grafana/alerts.yaml infra/grafana/notification-templates/zcrypto-slack.tmpl infra/runbooks/fleet.md tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py tests/test_infra_alert_rules.py tests/test_infra_compose_templates.py tests/test_dashboards_cover_metrics.py
git commit -m "feat(cache): each cache node ships its host, Valkey, Sentinel and mesh telemetry through its own Alloy

Each node runs Grafana Alloy in its own compose project, rendered by the cache role behind
\`cache_alloy_digest\` and started by hand as the capture hosts' is, capped at 256m with GOMEMLIMIT
230MiB, the fleet's 0.9. \`infra/ansible/roles/cache/files/config.alloy\` scrapes the unix exporter,
Alloy's own process families and two embedded Redis exporters, the local Valkey as the \`exporter\`
user and the local Sentinel on its requirepass, each relabelled to the job valkey or sentinel,
since an exporter target's own job wins over a scrape's job_name. The keep regex
admits the families the Cache board and the rules read, \`up\`, the fleet's host-unscoped node
families and the six process_* names, and \`CACHE_REQUIRED\` in \`tests/test_infra_alloy_series.py\`
holds it exactly. The journal keep selects the Valkey, Sentinel and Alloy containers by name and
the mesh probe's unit. The textfile collector reads /var/lib/zcrypto-node-textfile, where the
cache_link role's mesh probe writes each peer's handshake age and the cache role's reboot check the
pending-reboot flag.

The role's Alloy block refuses a digest that is not a full sha256 and, as the capture role does
for its own container, the replacement of an Alloy digest \`docs/reference/fleet-pins.md\` does not
record; the config drift assert runs outside the gate. The Alloy headroom rule gains the nodes'
leg at 268435456 and its summary names Cache 1 to Cache 3, the Slack template maps the three
hosts to those names, and the fleet runbook's headroom section names their cap and their panel.
\`KEEP_REGEX_FILES\` in \`tests/test_dashboards_cover_metrics.py\` gains the three hosts, so the
fleet's host-unscoped node rules are held against the nodes' keep list.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

Run: `git status --porcelain` — Expected: empty.

- [ ] **Step 9: Prove commit A's guards, then record the verdicts by a message-only amend**

The probes run with the tree clean and no pytest in flight. Each file's control breaks a pin every selected case shares; each mutation removes one guard:

```bash
T=tests/test_infra_alloy_series.py
N_ALLOY="$T::test_the_cache_keep_regex_admits_exactly_the_cache_required_list $T::test_the_redis_exporters_ship_under_the_jobs_the_rules_select $T::test_the_cache_journal_keep_rule_keys_the_containers_by_name $T::test_the_cache_secrets_template_renders_every_name_the_config_reads $T::test_the_cache_textfile_collector_reads_where_the_mesh_probe_writes"
CA=infra/ansible/roles/cache/files/config.alloy
infra/scripts/mutate-probe.sh --file $CA --control 's/|redis_up|/|redis_upx|/' \
  --mutation 's/|redis_sentinel_master_slaves"/|redis_sentinel_master_slaves|redis_exporter_scrapes_total"/' \
  -- uv run pytest $N_ALLOY -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $CA --control 's/|redis_up|/|redis_upx|/' \
  --mutation 's/replacement  = "sentinel"/replacement  = "integrations\/redis"/' \
  -- uv run pytest $N_ALLOY -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $CA --control 's/|redis_up|/|redis_upx|/' \
  --mutation 's/;(zcrypto-valkey|zcrypto-sentinel|grafana-alloy)/;(zcrypto-valkey|grafana-alloy)/' \
  -- uv run pytest $N_ALLOY -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $CA --control 's/|redis_up|/|redis_upx|/' \
  --mutation 's/sys.env("CACHE_SENTINEL_REQUIREPASS")/sys.env("CACHE_SENTINEL_PASSWORD")/' \
  -- uv run pytest $N_ALLOY -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $CA --control 's/|redis_up|/|redis_upx|/' \
  --mutation 's|directory = "/host/root/var/lib/zcrypto-node-textfile"|directory = "/host/root/var/lib/zcrypto-textfiles"|' \
  -- uv run pytest $N_ALLOY -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $CA --control 's/|node_scrape_collector_success|/|/' \
  --mutation 's/|process_resident_memory_bytes|/|/' \
  -- uv run pytest tests/test_dashboards_cover_metrics.py::test_every_alerted_family_is_admitted_where_its_rule_selects -q -p no:cacheprovider
G=tests/test_infra_converge_guards.py
N_GUARD="$G::test_cache_alloy_digest_must_be_a_full_sha256 $G::test_cache_alloy_pins_recording_semantics $G::test_cache_alloy_pins_refusal_stands_down_when_no_alloy_runs $G::test_cache_alloy_pins_echo_fires_only_on_an_accepted_override $G::test_the_cache_alloy_guards_run_only_on_a_converge_carrying_the_digest $G::test_cache_alloy_drift_assert_runs_only_where_it_cannot_be_repaired"
TK=infra/ansible/roles/cache/tasks/main.yml
C='s/name: alloy pins recording — refuse to replace an Alloy digest/name: alloy pins recording — refuse to replace a digest/'
infra/scripts/mutate-probe.sh --file $TK --control "$C" --mutation 's/a-f]{64}/a-f]{12}/' \
  -- uv run pytest $N_GUARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TK --control "$C" \
  --mutation 's/^          ((cache_alloy_running_digest_probe.stdout/          (true or (cache_alloy_running_digest_probe.stdout/' \
  -- uv run pytest $N_GUARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TK --control "$C" \
  --mutation 's/^        and not ((cache_alloy_running_digest_probe/        and ((cache_alloy_running_digest_probe/' \
  -- uv run pytest $N_GUARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TK --control "$C" --mutation 's/^    - cache_alloy_digest is not defined$/    - true/' \
  -- uv run pytest $N_GUARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $TK --control "$C" --mutation 's/^  when: cache_alloy_digest is defined$/  when: true/' \
  -- uv run pytest $N_GUARD -q -p no:cacheprovider
R=tests/test_infra_alert_rules.py
N_HEAD="$R::test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling $R::test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence $R::test_the_headroom_summary_names_the_hosts_its_expression_actually_reads $R::test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host"
AL=infra/grafana/alerts.yaml
HC='s/^  - uid: zcrypto-fleet-alloy-memory-headroom$/  - uid: zcrypto-fleet-alloy-memory-headroom-x/'
infra/scripts/mutate-probe.sh --file $AL --control "$HC" \
  --mutation 's/job="integrations\/self"} \/ 268435456)/job="integrations\/self"} \/ 536870912)/' \
  -- uv run pytest $N_HEAD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $AL --control "$HC" \
  --mutation '/zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3", job="integrations\/self"/d' \
  -- uv run pytest $N_HEAD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $AL --control "$HC" --mutation 's/, 256 MiB on Cache 1, Cache 2 and Cache 3\./\./' \
  -- uv run pytest $N_HEAD -q -p no:cacheprovider
AC=infra/ansible/roles/cache/templates/alloy-compose.yaml.j2
infra/scripts/mutate-probe.sh --file $AC --control 's/memory: 256m/memory: 256x/' --mutation 's/GOMEMLIMIT: 230MiB/GOMEMLIMIT: 250MiB/' \
  -- uv run pytest $N_HEAD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $AC --control 's|^      - ./conf:/etc/alloy:ro$|      - ./x:/etc/alloy/config.alloy:ro|' \
  --mutation 's|^      - ./conf:/etc/alloy:ro$|      - ./conf/config.alloy:/etc/alloy/config.alloy:ro|' \
  -- uv run pytest tests/test_infra_compose_templates.py::test_the_alloy_config_is_never_bind_mounted_as_a_single_file -q -p no:cacheprovider
SL=infra/grafana/notification-templates/zcrypto-slack.tmpl
infra/scripts/mutate-probe.sh --file $SL --control 's/eq . "zcrypto-valkey1" }}Cache 1/eq . "zcrypto-valkey1" }}Cache one/' \
  --mutation '/eq . "zcrypto-valkey3" }}Cache 3/d' \
  -- uv run pytest $R::test_the_headroom_summary_names_the_hosts_its_expression_actually_reads -q -p no:cacheprovider
```

Expected: each run ends `KILLED` with `control proven`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh`, seventeen runs. Over
`infra/ansible/roles/cache/files/config.alloy`, control `redis_up` dropped from the keep regex,
through the five cache config cases of `tests/test_infra_alloy_series.py`: an unread family added
to the regex, KILLED, control proven; the Sentinel relabel's job changed, KILLED, control proven;
the Sentinel container dropped from the journal keep, KILLED, control proven; the Sentinel
password read from a name the template does not render, KILLED, control proven; the textfile
collector pointed off the mesh probe's directory, KILLED, control proven; through
`test_every_alerted_family_is_admitted_where_its_rule_selects` under control
`node_scrape_collector_success` dropped, `process_resident_memory_bytes` dropped, KILLED, control
proven. Over `infra/ansible/roles/cache/tasks/main.yml`, control the pins task renamed,
through the six cache_alloy cases of `tests/test_infra_converge_guards.py`: a 12-hex digest
admitted, KILLED, control proven; the pins refusal short-circuited to true, KILLED, control proven;
the override echo's negation dropped, KILLED, control proven; the drift assert let run under a
digest, KILLED, control proven; the Alloy block ungated, KILLED, control proven. Over
`infra/grafana/alerts.yaml`, control the headroom rule's uid renamed, through the four headroom
cases of `tests/test_infra_alert_rules.py`: the cache leg divided by the 512m cap, KILLED, control
proven; the cache leg deleted, KILLED, control proven; the summary's cache clause dropped, KILLED,
control proven. Over `infra/ansible/roles/cache/templates/alloy-compose.yaml.j2`: GOMEMLIMIT
raised to 250MiB under control the cap unparseable, KILLED, control proven; the config mounted as
a single file under control another single-file mount, KILLED, control proven. Over
`infra/grafana/notification-templates/zcrypto-slack.tmpl`, control Cache 1 renamed: Cache 3's
mapping deleted, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

- [ ] **Step 10: Write the failing tests for the board and the rules**

In `tests/test_dashboards_cover_metrics.py`, `PUBLISHER_HOSTS`, replace the line `    ("infra/ansible/roles/engine/", ("zcrypto",)),` with:

```python
    ("infra/ansible/roles/engine/", ("zcrypto",)),
    # The zcache mesh probe runs on the engine host and the three cache nodes, never on zcrypto-red.
    ("infra/ansible/roles/cache_link/", ("zcrypto", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")),
```

Replace the four lines

```python
# Scope is the three namespaces this repo's own producers publish into. `node_*`, `process_*` and
# `hc_*` come from node-exporter, prometheus_client and healthchecks.io -- not ours to chart
# exhaustively, and the alert layer (assertion 1) already pulls in the ones that matter.
_APP = r"(?:zcrypto|ops|zaccess)_[a-z0-9_]*[a-z0-9]"
```

with

```python
# Scope is the four namespaces this repo's own producers publish into. `node_*`, `process_*`, `hc_*`
# and `redis_*` come from node-exporter, prometheus_client, healthchecks.io and Alloy's Redis
# exporter -- not ours to chart exhaustively, and the alert layer (assertion 1) already pulls in the
# ones that matter; the cache nodes' keep list is held to what is charted or alerted below.
_APP = r"(?:zcrypto|ops|zaccess|zcache)_[a-z0-9_]*[a-z0-9]"
```

In `test_the_publisher_scan_still_finds_each_source_kind`'s parametrization, replace the line `        "zcrypto_engine_journal_prune_kept_days",  # an echo in a plain .sh` with:

```python
        "zcrypto_engine_journal_prune_kept_days",  # an echo in a plain .sh
        "zcache_wireguard_handshake_age_seconds",  # an echoed HELP line in a plain .sh, the fourth namespace
```

Insert above the comment line `# A table's frame mixes string label columns with the numeric value, and `fieldConfig.defaults``:

```python
def test_every_family_the_cache_nodes_admit_is_charted_or_alerted():
    """The cache keep regex is written as the families the Cache board and the rules read, the first
    third-party families on the fleet (`redis_*`). One admitted and read by neither is series budget
    spent on nothing, and the per-host lists in test_infra_alloy_series.py cannot see that."""
    text = KEEP_REGEX_FILES["zcrypto-valkey1"].read_text()
    block = next(b for b in re.findall(r"write_relabel_config\s*\{(.*?)\}", text, re.DOTALL) if '"keep"' in b)
    admitted = set(re.search(r'regex\s*=\s*"([^"]+)"', block).group(1).split("|"))
    assert len(admitted) >= 30, f"only {len(admitted)} families parsed from the cache keep regex -- the parse broke"
    unread = sorted(admitted - set(panel_families()) - set(alerted_families()))
    assert not unread, f"the cache nodes admit {unread}, which no panel draws and no rule reads"

```

In `tests/test_ops_daily.py`, in the parametrization of `test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away`, replace the line `        ("zcrypto-alloy-dark-capture-secondary", "zcrypto-red"),` with:

```python
        ("zcrypto-alloy-dark-capture-secondary", "zcrypto-red"),
        ("zcrypto-alloy-dark-cache-1", "zcrypto-valkey1"),
        ("zcrypto-alloy-dark-cache-2", "zcrypto-valkey2"),
        ("zcrypto-alloy-dark-cache-3", "zcrypto-valkey3"),
```

- [ ] **Step 11: Run them and read the failure**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`
Expected: `2 failed, 19 passed`: `test_every_published_app_family_is_charted` names `zcache_wireguard_handshake_age_seconds`, published at `infra/ansible/roles/cache_link/files/zcache-probe.sh`, and `test_every_family_the_cache_nodes_admit_is_charted_or_alerted` names the twenty `redis_*` families and `zcache_wireguard_handshake_age_seconds`, which no panel draws and no rule reads yet.

Run: `uv run pytest tests/test_ops_daily.py::test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away -q -p no:cacheprovider`
Expected: `3 failed, 4 passed`: the three cache uids read no host, since `_UID_HOST` has no entry for them yet.

- [ ] **Step 12: The Cache board**

Create `infra/grafana/cache-dashboard.json`:

```json
{
  "id": null,
  "uid": "zcrypto-cache",
  "title": "Cache",
  "description": "Is the engine's cache set healthy? The three Valkey nodes, their Sentinels and the mesh between them, and the engine's own lines about the cache. Every panel that serves an alert plots that alert's own expression and carries its own threshold line.",
  "tags": [],
  "schemaVersion": 39,
  "version": 0,
  "editable": true,
  "graphTooltip": 1,
  "fiscalYearStartMonth": 0,
  "liveNow": false,
  "links": [],
  "refresh": "1m",
  "timezone": "",
  "weekStart": "",
  "time": {"from": "now-24h", "to": "now"},
  "timepicker": {},
  "templating": {
    "list": [
      {
        "name": "host",
        "label": "Host",
        "type": "custom",
        "query": "Cache 1 : zcrypto-valkey1, Cache 2 : zcrypto-valkey2, Cache 3 : zcrypto-valkey3",
        "multi": true,
        "includeAll": true,
        "allValue": "",
        "hide": 0,
        "skipUrlSync": false,
        "description": "Which cache nodes the panels below select. All expands to the three pinned nodes joined into one matcher. The Alloy tiles and the alert panels name their nodes literally and ignore this picker.",
        "current": {"selected": true, "text": ["All"], "value": ["$__all"]},
        "options": [
          {"selected": true, "text": "All", "value": "$__all"},
          {"selected": false, "text": "Cache 1", "value": "zcrypto-valkey1"},
          {"selected": false, "text": "Cache 2", "value": "zcrypto-valkey2"},
          {"selected": false, "text": "Cache 3", "value": "zcrypto-valkey3"}
        ]
      }
    ]
  },
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "panels": [
    {
      "id": 100,
      "type": "row",
      "title": "Hosts",
      "collapsed": false,
      "panels": [],
      "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
    },
    {
      "id": 101,
      "type": "stat",
      "title": "Alloy up \u2014 per node",
      "description": "Is each cache node's telemetry agent shipping anything at all? One target per node, written out literally rather than driven by the Host picker: a regex selector cannot render a node whose series have vanished, which is the condition this panel exists to catch. A tile reads DARK when the node has shipped nothing; the alert fires after `for: 10m` of that. While a tile is DARK every other panel on this board is blind for that node. Runbook: infra/runbooks/cache.md#zcrypto-alloy-dark-cache-1",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 6, "w": 6, "x": 0, "y": 1},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "count(up{host=\"zcrypto-valkey1\"}) or on() vector(0)",
          "refId": "A",
          "legendFormat": "Cache 1",
          "instant": true
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "count(up{host=\"zcrypto-valkey2\"}) or on() vector(0)",
          "refId": "B",
          "legendFormat": "Cache 2",
          "instant": true
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "count(up{host=\"zcrypto-valkey3\"}) or on() vector(0)",
          "refId": "C",
          "legendFormat": "Cache 3",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [{"type": "value", "options": {"0": {"text": "DARK", "color": "red", "index": 0}}}],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          },
          "noValue": "DARK"
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 102,
      "type": "timeseries",
      "title": "Load per core",
      "description": "The one-minute load divided by the node's core count. The nodes are one-core machines running Valkey, Sentinel and the telemetry agent, so a sustained reading above 1 is the node itself short of CPU, which shows up first as replication lag.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 6, "w": 9, "x": 6, "y": 1},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "node_load1{host=~\"$host\"} / on(host) group_left() count by (host) (node_cpu_seconds_total{host=~\"$host\", mode=\"idle\"})",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 103,
      "type": "timeseries",
      "title": "Memory available",
      "description": "Available memory as a share of the node's total. The containers' caps add up to 576 MiB on a 1 GB node, so this reads what the kernel, the Docker daemon and the page cache are left with; Valkey's own use against its limit is the Memory against maxmemory panel below.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 6, "w": 9, "x": 15, "y": 1},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "node_memory_MemAvailable_bytes{host=~\"$host\"} / node_memory_MemTotal_bytes{host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 104,
      "type": "timeseries",
      "title": "Root filesystem free",
      "description": "Free space on the root filesystem, where Valkey's append-only file and snapshots live. The append-only file grows between rewrites, so a falling line that recovers is a rewrite completing; one that only falls is a rewrite failing, which the AOF panel below shows.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 0, "y": 7},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "node_filesystem_avail_bytes{host=~\"$host\", mountpoint=\"/\"} / node_filesystem_size_bytes{host=~\"$host\", mountpoint=\"/\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 105,
      "type": "timeseries",
      "title": "Mesh handshake age per peer",
      "description": "Seconds since each mesh member last completed a WireGuard handshake with each of its peers, the engine host's own view under host zcrypto and each node's under its name; the peer is named by its mesh address: 10.98.0.1 is the engine host, 10.98.0.11 to 10.98.0.13 are Cache 1 to Cache 3. The line is the recorded age plus the age of the file it was read from, so a probe that stopped writing climbs here too. A healthy peer re-handshakes about every two minutes; the red line is where the alert fires, after `for: 2m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-wg-handshake-stale",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 8, "y": 7},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "max by (host, peer) (zcache_wireguard_handshake_age_seconds{host=~\"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3\"}) + on(host) group_left() (time() - max by (host) (node_textfile_mtime_seconds{host=~\"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3\", file=~\".*/zcache.prom\"}))",
          "refId": "A",
          "legendFormat": "{{host}} to {{peer}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "custom": {"thresholdsStyle": {"mode": "line"}},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "green", "value": null}, {"color": "red", "value": 180}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 106,
      "type": "timeseries",
      "title": "Reboot pending and probe freshness",
      "description": "The pending-reboot flag each node's reboot check publishes (1 means an unattended upgrade is waiting for the node's reboot slot), the age of the mesh probe's file, and whether the collector could parse the directory. A file age climbing past a few minutes is the probe timer stopped, and the handshake panel beside this one climbs with it.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 16, "y": 7},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "node_reboot_required{host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}} reboot pending"
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "time() - max by (host) (node_textfile_mtime_seconds{host=~\"$host\", file=~\".*/zcache.prom\"})",
          "refId": "B",
          "legendFormat": "{{host}} probe file age (s)"
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "max by (host) (node_textfile_scrape_error{host=~\"$host\"})",
          "refId": "C",
          "legendFormat": "{{host}} textfile parse error"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 107,
      "type": "timeseries",
      "title": "Alloy memory against its 256 MiB cap",
      "description": "The telemetry agent's resident memory as a share of its container cap. The red line is the fleet's Alloy headroom bar, the agent's Go soft limit; that rule is shared with the other hosts and its notification links the Fleet health board, so this is where a cache node's reading is. Runbook: infra/runbooks/fleet.md#zcrypto-fleet-alloy-memory-headroom",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 0, "y": 14},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "process_resident_memory_bytes{host=~\"$host\", job=\"integrations/self\"} / 268435456",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "custom": {"thresholdsStyle": {"mode": "line"}},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "green", "value": null}, {"color": "red", "value": 0.9}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 108,
      "type": "timeseries",
      "title": "Network traffic",
      "description": "Bytes per second in and out of each interface but loopback. zcache0 is the mesh, carrying replication and the engine's cache traffic; eth0 carries the mesh's own encrypted packets and the telemetry.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 12, "y": 14},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "rate(node_network_receive_bytes_total{host=~\"$host\", device!=\"lo\"}[5m])",
          "refId": "A",
          "legendFormat": "{{host}} {{device}} in"
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "rate(node_network_transmit_bytes_total{host=~\"$host\", device!=\"lo\"}[5m])",
          "refId": "B",
          "legendFormat": "{{host}} {{device}} out"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "Bps",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 200,
      "type": "row",
      "title": "Valkey",
      "collapsed": false,
      "panels": [],
      "gridPos": {"h": 1, "w": 24, "x": 0, "y": 21}
    },
    {
      "id": 201,
      "type": "stat",
      "title": "Role per node",
      "description": "What each node's Valkey says it is. Exactly one node reads master and the other two slave; the Which node is primary panel shows the same over time.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 8, "x": 0, "y": 22},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "max by (host, role) (redis_instance_info{job=\"valkey\", host=~\"$host\"})",
          "refId": "A",
          "legendFormat": "{{host}}: {{role}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [],
          "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "name",
        "colorMode": "none",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 202,
      "type": "stat",
      "title": "Valkey answering the exporter",
      "description": "Whether the node's exporter could log in to its Valkey and read INFO. DOWN with the node's Alloy up is Valkey stopped, or the exporter user refused.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 8, "x": 8, "y": 22},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_up{job=\"valkey\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 203,
      "type": "stat",
      "title": "Valkey uptime",
      "description": "Seconds since each Valkey process started. A reset that no converge explains is a crash and a restart.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 8, "x": 16, "y": 22},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_uptime_in_seconds{job=\"valkey\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "mappings": [],
          "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "none",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 204,
      "type": "timeseries",
      "title": "Primary count \u2014 the page's value",
      "description": "How far the number of addresses at least two Sentinels name a healthy primary is from one: 0 is healthy, 1 is no primary the Sentinels agree on. It reads nothing while fewer than two nodes' Sentinel telemetry ships, which the Alloy-dark alerts own. The red line is where the alert fires, after `for: 2m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-primary-count",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 0, "y": 27},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "abs((count(count by (master_address) (redis_sentinel_master_status{job=\"sentinel\"} == 1) >= 2) or on() vector(0)) - 1) and on() (count(up{job=\"sentinel\"}) > 1)",
          "refId": "A",
          "legendFormat": "distance from one primary"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "line"}, "lineInterpolation": "stepAfter"},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "green", "value": null}, {"color": "red", "value": 0.5}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 205,
      "type": "timeseries",
      "title": "Which node is primary",
      "description": "One line per node that reports role master, over time. A failover is the line moving from one node to another; two lines at once is two primaries.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 8, "y": 27},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "count by (host) (redis_instance_info{job=\"valkey\", host=~\"$host\", role=\"master\"})",
          "refId": "A",
          "legendFormat": "{{host}} is primary"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 206,
      "type": "timeseries",
      "title": "Replicas connected to the primary",
      "description": "How many replicas the primary has connected. Two is the healthy set; one leaves the primary writable with one copy; zero makes it refuse writes, since it takes writes only with at least one replica within 10 seconds of lag. The red line is where the alert fires, after `for: 5m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-replicas-short",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 16, "y": 27},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_connected_slaves{job=\"valkey\"} and on(host) redis_instance_info{job=\"valkey\", role=\"master\"}",
          "refId": "A",
          "legendFormat": "{{host}} (primary)"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "line"}, "lineInterpolation": "stepAfter"},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 2}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 207,
      "type": "timeseries",
      "title": "Replication lag \u2014 bytes behind the primary",
      "description": "The primary's replication offset minus each replica's acknowledged offset, as the primary reports it, the replica named by its mesh address. Near zero is healthy; a line that climbs and stays is a replica that stopped applying.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 0, "y": 34},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "scalar(max(redis_master_repl_offset{job=\"valkey\"} and on(host) redis_instance_info{job=\"valkey\", role=\"master\"})) - redis_connected_slave_offset_bytes{job=\"valkey\"}",
          "refId": "A",
          "legendFormat": "replica {{slave_ip}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "bytes",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 208,
      "type": "stat",
      "title": "Replica link to the primary",
      "description": "Whether each replica's link to its primary is up, as the replica reports it. The primary itself shows no tile.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 12, "y": 34},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_master_link_up{job=\"valkey\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 209,
      "type": "timeseries",
      "title": "Memory against maxmemory",
      "description": "Valkey's used memory as a share of its maxmemory. The eviction policy is noeviction, so at the limit writes are refused rather than keys dropped; nothing trims the keys, so growth is the signal. The red line is where the alert fires, after `for: 15m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-memory-70pct",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 0, "y": 41},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_memory_used_bytes{job=\"valkey\"} / redis_memory_max_bytes{job=\"valkey\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "custom": {"thresholdsStyle": {"mode": "line"}},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "green", "value": null}, {"color": "red", "value": 0.7}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 210,
      "type": "timeseries",
      "title": "Commands per second",
      "description": "Commands each Valkey processes per second, replication and the exporter's own reads included, so the replicas are never at zero.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 8, "y": 41},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "rate(redis_commands_processed_total{job=\"valkey\", host=~\"$host\"}[5m])",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 211,
      "type": "timeseries",
      "title": "Connected clients",
      "description": "Client connections on each Valkey: the exporter, the Sentinels, the replicas on the primary, and the engine through its proxy once it is wired.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 16, "y": 41},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_connected_clients{job=\"valkey\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 212,
      "type": "timeseries",
      "title": "AOF \u2014 the page's value",
      "description": "1 when the append-only file is enabled and its last write and last rewrite both succeeded, 0 when any of the three is not so. Below the green line is the alert's condition, after `for: 5m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-aof-not-ok",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 0, "y": 48},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "min by (host) (redis_aof_enabled{job=\"valkey\"} * redis_aof_last_write_status{job=\"valkey\"} * redis_aof_last_bgrewrite_status{job=\"valkey\"})",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "line"}, "lineInterpolation": "stepAfter"},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 213,
      "type": "timeseries",
      "title": "RDB last background save",
      "description": "1 when each node's last background snapshot succeeded. The snapshots serve a replica's full resync; a failing one is read beside the AOF panel and the free space above.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 12, "y": 48},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_rdb_last_bgsave_status{job=\"valkey\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 300,
      "type": "row",
      "title": "Sentinel",
      "collapsed": false,
      "panels": [],
      "gridPos": {"h": 1, "w": 24, "x": 0, "y": 55}
    },
    {
      "id": 301,
      "type": "stat",
      "title": "Sentinel answering the exporter",
      "description": "Whether each node's exporter could authenticate to its Sentinel and read INFO. Two of three are needed to agree on a failover.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 6, "x": 0, "y": 56},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_up{job=\"sentinel\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 302,
      "type": "stat",
      "title": "The primary as each Sentinel names it",
      "description": "The address each Sentinel names as the primary, and whether it reads that primary as ok. All three should name the same mesh address, the one the Role per node panel shows as master.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 10, "x": 6, "y": 56},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "max by (host, master_address) (redis_sentinel_master_status{job=\"sentinel\", host=~\"$host\"})",
          "refId": "A",
          "legendFormat": "{{host}} names {{master_address}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "not ok", "color": "red", "index": 0},
                "1": {"text": "ok", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 303,
      "type": "stat",
      "title": "Masters each Sentinel monitors",
      "description": "How many primaries each Sentinel monitors; 1 is the zcache set. 0 is a Sentinel whose configuration lost the monitor line.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 8, "x": 16, "y": 56},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_sentinel_masters{job=\"sentinel\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 304,
      "type": "timeseries",
      "title": "Sentinels each Sentinel knows",
      "description": "The Sentinels each one knows for the set, itself included, and how many of them it reads as healthy. The quorum is 2, so fewer than two healthy leaves the set unable to fail over.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 0, "y": 61},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_sentinel_master_sentinels{job=\"sentinel\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}} known"
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_sentinel_master_ok_sentinels{job=\"sentinel\", host=~\"$host\"}",
          "refId": "B",
          "legendFormat": "{{host}} healthy"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 305,
      "type": "timeseries",
      "title": "Replicas each Sentinel knows",
      "description": "The replicas each Sentinel knows for the set. Two is the healthy set; a Sentinel reading fewer than the others has lost sight of a node.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 12, "x": 12, "y": 61},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "redis_sentinel_master_slaves{job=\"sentinel\", host=~\"$host\"}",
          "refId": "A",
          "legendFormat": "{{host}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 400,
      "type": "row",
      "title": "Logs",
      "collapsed": false,
      "panels": [],
      "gridPos": {"h": 1, "w": 24, "x": 0, "y": 68}
    },
    {
      "id": 401,
      "type": "logs",
      "title": "Engine lines naming the cache",
      "description": "The engine's own log lines that mention the cache, newest first: the counts it restored at each boot, and a refusal to start against a cache that is unreachable or lost its data. The library's own cache errors are written by its native side and never reach this log store.",
      "datasource": {"type": "loki", "uid": "grafanacloud-logs"},
      "gridPos": {"h": 10, "w": 24, "x": 0, "y": 69},
      "targets": [
        {
          "datasource": {"type": "loki", "uid": "grafanacloud-logs"},
          "refId": "A",
          "queryType": "range",
          "expr": "{host=\"zcrypto\", container=\"engine\"} |~ \"(?i)cache\" | json | drop __error__, __error_details__ | line_format \"{{ if .message }}{{ .message }}{{ if .exception }}\\n{{ .exception }}{{ end }}{{ else }}{{ __line__ }}{{ end }}\""
        }
      ],
      "options": {
        "showTime": true,
        "showLabels": false,
        "showCommonLabels": false,
        "wrapLogMessage": true,
        "prettifyLogMessage": false,
        "enableLogDetails": true,
        "dedupStrategy": "none",
        "sortOrder": "Descending"
      }
    },
    {
      "id": 402,
      "type": "logs",
      "title": "Valkey and Sentinel lines",
      "description": "Each node's Valkey and Sentinel log, newest first. A failover reads here as the Sentinels' +sdown, +odown and +switch-master events; a replica's resync as its MASTER <-> REPLICA sync lines.",
      "datasource": {"type": "loki", "uid": "grafanacloud-logs"},
      "gridPos": {"h": 10, "w": 24, "x": 0, "y": 79},
      "targets": [
        {
          "datasource": {"type": "loki", "uid": "grafanacloud-logs"},
          "refId": "A",
          "queryType": "range",
          "expr": "{host=~\"$host\", container=~\"valkey|sentinel\"}"
        }
      ],
      "options": {
        "showTime": true,
        "showLabels": false,
        "showCommonLabels": false,
        "wrapLogMessage": true,
        "prettifyLogMessage": false,
        "enableLogDetails": true,
        "dedupStrategy": "none",
        "sortOrder": "Descending"
      }
    }
  ]
}
```

- [ ] **Step 13: The zcrypto-cache rule group**

Append to `infra/grafana/alerts.yaml`, after its last line (`      receiver: metrics`, closing `zaccess-cert-expiring`):

```yaml
  # ---- zcrypto-cache: the engine's cache nodes ------------------------------------------------------
  # Each node's own Alloy-dark rule, in the `count(up{...}) or on() vector(0)` shape of
  # `zcrypto-alloy-dark-nas`, and so its noDataState: Alerting. Every other rule in this group reads OK
  # on no data: its series stop only when a node's telemetry does, which these three own.
  - uid: zcrypto-alloy-dark-cache-1
    title: "Fleet · Alloy dark — Cache 1"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            count(up{host="zcrypto-valkey1"}) or on() vector(0)
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [1]}
    noDataState: Alerting
    execErrState: Alerting
    for: 10m
    annotations:
      summary: "Cache 1's Alloy has shipped no metrics for >10m — its telemetry plane is dark, taking out that node's host, Valkey, Sentinel and mesh signals. Every other rule reading this node is blind until this clears, and the cache set itself may be healthy. First checks: `sudo docker ps` on the node, then `sudo docker logs grafana-alloy`; a restart is the usual fix. Runbook: infra/runbooks/cache.md#zcrypto-alloy-dark-cache-1"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "101"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-alloy-dark-cache-2
    title: "Fleet · Alloy dark — Cache 2"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            count(up{host="zcrypto-valkey2"}) or on() vector(0)
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [1]}
    noDataState: Alerting
    execErrState: Alerting
    for: 10m
    annotations:
      summary: "Cache 2's Alloy has shipped no metrics for >10m — its telemetry plane is dark, taking out that node's host, Valkey, Sentinel and mesh signals. Every other rule reading this node is blind until this clears, and the cache set itself may be healthy. First checks: `sudo docker ps` on the node, then `sudo docker logs grafana-alloy`; a restart is the usual fix. Runbook: infra/runbooks/cache.md#zcrypto-alloy-dark-cache-2"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "101"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-alloy-dark-cache-3
    title: "Fleet · Alloy dark — Cache 3"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            count(up{host="zcrypto-valkey3"}) or on() vector(0)
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [1]}
    noDataState: Alerting
    execErrState: Alerting
    for: 10m
    annotations:
      summary: "Cache 3's Alloy has shipped no metrics for >10m — its telemetry plane is dark, taking out that node's host, Valkey, Sentinel and mesh signals. Every other rule reading this node is blind until this clears, and the cache set itself may be healthy. First checks: `sudo docker ps` on the node, then `sudo docker logs grafana-alloy`; a restart is the usual fix. Runbook: infra/runbooks/cache.md#zcrypto-alloy-dark-cache-3"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "101"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-primary-count
    title: "Cache · not exactly one primary"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # The primary the Sentinels agree on: the addresses at least two of the three Sentinels name a
          # healthy master, counted, and that count's distance from one, so 0 is healthy and 1 is no
          # agreed primary. Each node's own `role` is not counted: a dark primary would count none, and a
          # dead one's last sample outlives it by the query lookback beside its successor's. The `and
          # on()` arm empties the result while fewer than two nodes' Sentinel telemetry ships, which the
          # Alloy-dark rules own; with Alloy up and the Sentinels down, `up{job="sentinel"}` stays (the
          # exporter answers) and this fires.
          expr: >-
            abs((count(count by (master_address) (redis_sentinel_master_status{job="sentinel"} == 1) >= 2) or on() vector(0)) - 1) and on() (count(up{job="sentinel"}) > 1)
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: gt, params: [0]}
    noDataState: OK
    execErrState: Alerting
    # A Sentinel failover takes about 5 s to detect and seconds more to promote; 2m clears it and a
    # deliberate `SENTINEL failover` with room to spare.
    for: 2m
    annotations:
      summary: "For 2+ minutes no node has been named a healthy primary by at least two of the three Sentinels, so the cache set has no primary its quorum agrees on and cache writes have nowhere to land. One node's telemetry going dark does not fire this; two Sentinels down does. Read each Sentinel's view and the Cache board's primary panels before acting. Runbook: infra/runbooks/cache.md#zcrypto-cache-primary-count"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "204"
      unit: "distance from exactly one primary"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-replicas-short
    title: "Cache · primary has fewer than two replicas"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            redis_connected_slaves{job="valkey"} and on(host) redis_instance_info{job="valkey", role="master"}
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [2]}
    noDataState: OK
    execErrState: Alerting
    # A replica restarted by a converge reconnects and resyncs in seconds; 5m clears one roll.
    for: 5m
    annotations:
      summary: "The cache primary has had fewer than two replicas connected for 5+ minutes. With one, the set holds two copies and survives no further loss; with none, the primary refuses writes, since it accepts them only with at least one replica within 10 seconds of lag. The node this notification names is the primary; the missing replica is the node absent from its replicas list. Runbook: infra/runbooks/cache.md#zcrypto-cache-replicas-short"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "206"
      unit: "replicas connected"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-memory-70pct
    title: "Cache · Valkey memory past 70% of maxmemory"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            redis_memory_used_bytes{job="valkey"} / redis_memory_max_bytes{job="valkey"}
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            # The library never deletes a key and the policy is noeviction, so growth is paged, not
            # trimmed: at 100% writes are refused.
            - evaluator: {type: gt, params: [0.7]}
    noDataState: OK
    execErrState: Alerting
    for: 15m
    annotations:
      summary: "Valkey on a cache node has used more than 70% of its maxmemory for 15+ minutes. The eviction policy is noeviction, so at the limit the set refuses writes instead of dropping keys, and nothing trims the keys, so this does not clear by itself. Runbook: infra/runbooks/cache.md#zcrypto-cache-memory-70pct"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "209"
      unit: "fraction of maxmemory"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-aof-not-ok
    title: "Cache · append-only file off or failing"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # 1 only when all three hold: the AOF enabled, its last write ok, its last rewrite ok.
          expr: >-
            min by (host) (redis_aof_enabled{job="valkey"} * redis_aof_last_write_status{job="valkey"} * redis_aof_last_bgrewrite_status{job="valkey"})
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [1]}
    noDataState: OK
    execErrState: Alerting
    for: 5m
    annotations:
      summary: "A cache node's append-only file has been disabled, or its last write or rewrite has failed, for 5+ minutes. That node's copy is no longer durable on disk: a restart loses what the file lacks, and a failed write makes the primary refuse writes until one succeeds. Runbook: infra/runbooks/cache.md#zcrypto-cache-aof-not-ok"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "212"
      unit: "1 when the AOF is on and its last write and rewrite succeeded"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-wg-handshake-stale
    title: "Cache · mesh peer handshake stale"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # The recorded age plus the age of the file it came from is the age now, so a probe timer
          # that stopped writing climbs past the bar instead of freezing below it. A peer with no
          # handshake is published as +Inf.
          expr: >-
            max by (host, peer) (zcache_wireguard_handshake_age_seconds{host=~"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3"}) + on(host) group_left() (time() - max by (host) (node_textfile_mtime_seconds{host=~"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3", file=~".*/zcache.prom"}))
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            # PersistentKeepalive 25 keeps traffic flowing, so WireGuard re-handshakes about every
            # 120 s plus one keepalive; 180 s is a missed handshake, not the normal cycle.
            - evaluator: {type: gt, params: [180]}
    noDataState: OK
    execErrState: Alerting
    for: 2m
    annotations:
      summary: "A zcache mesh member, the engine host or a cache node, has not completed a WireGuard handshake with one of its peers for more than three minutes. The host this notification names is the end that reports it, and the `peer` label is the other end's mesh address: 10.98.0.1 is the engine host, 10.98.0.11 to 10.98.0.13 are Cache 1 to Cache 3. Replication or the engine's cache traffic over that link is down. Runbook: infra/runbooks/cache.md#zcrypto-cache-wg-handshake-stale"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "105"
      unit: "seconds since the last handshake with that peer"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics
```

Beside that rule, the capture keep list admits the probe's family, so the engine host's end of the mesh reaches Grafana once the Rollout's capture-host converge at R7 deploys the edited `config.alloy`; the edit lands in this commit, not commit A, since `tests/test_infra_alert_rules.py::test_every_fault_signal_metric_is_watched_by_a_rule` holds each family the capture keep list admits, save those `NOT_A_FAULT_SIGNAL` excuses, to a rule that reads it. In `tests/test_infra_alloy_series.py`, in `CAPTURE_REQUIRED`, the list opening `CAPTURE_REQUIRED = [` (the same two lines stand in `ACCESS_REQUIRED` and in Step 1's `CACHE_REQUIRED`, and stay as they are), replace the two lines

```python
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
```

with:

```python
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    # The zcache mesh probe (roles/cache_link) on the engine host: its end of each link is watched from its own
    # side too. zcrypto-red shares this keep list and runs no cache_link, so it admits a family it never publishes.
    "zcache_wireguard_handshake_age_seconds",
```

In `infra/ansible/roles/capture/files/config.alloy`, in the keep regex, replace `|node_textfile_mtime_seconds|` (once, inside the `regex = "up|node_load1|...` line) with `|node_textfile_mtime_seconds|zcache_wireguard_handshake_age_seconds|`: the engine host runs the mesh probe, and its capture Alloy ships the family from R7's capture converge on, since the capture role copies `config.alloy` only on a converge carrying `capture_alloy_digest`; `CAPTURE_REQUIRED` holds it there.

In `infra/scripts/ops_daily.py`, in `_UID_HOST`, replace the line `    "zcrypto-alloy-dark-capture-secondary": "zcrypto-red",` with the four lines below: the three Alloy-dark rules' expression aggregates the `host` label away, so the daily pass reads a firing one's host from its uid.

```python
    "zcrypto-alloy-dark-capture-secondary": "zcrypto-red",
    "zcrypto-alloy-dark-cache-1": "zcrypto-valkey1",
    "zcrypto-alloy-dark-cache-2": "zcrypto-valkey2",
    "zcrypto-alloy-dark-cache-3": "zcrypto-valkey3",
```

- [ ] **Step 14: The cache runbook**

Create `infra/runbooks/cache.md`:

````markdown
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
5. **Still not linked after two minutes** — the node's `vk INFO replication` reads `master_link_status:down` — means its files are the fault: run `cache-config-reset` below on this node.

### Retire when

`infra/ansible/roles/cache/` no longer exists.

______________________________________________________________________

<a name="cache-config-reset"></a>

## cache-config-reset — PROCEDURE: applying a deliberate valkey.conf or sentinel.conf change

### What you are seeing

Nothing fired. You changed the cache role's Valkey or Sentinel template and mean a node to run it, or `cache-rejoin-node` sent you here because a node's own files are broken. A password changed in `group_vars/cache_host/vault.yml` is `cache-password-rotation` below, not this procedure: a node reset alone to a new password fails to authenticate to, and from, the nodes still holding the old one.

### What it means

The role renders `valkey.conf` and `sentinel.conf` when they are absent and leaves them alone after: Valkey rewrites its `replicaof` into its file and Sentinel its known replicas, Sentinels and epoch into its own, and re-rendering them on a routine converge would reset the node's replication state. The role compares the rendered templates' hashes against a recorded copy, so a template change the nodes have not taken shows on the converge without being applied. `-e cache_config_reset=true` replaces both files on the node it converges, and the role refuses it on a converge without the node's image digest, since it renders them inside the digest's block. A replaced `sentinel.conf` monitors the first primary, valkey1, at epoch 0, and the other two Sentinels correct it within seconds, since a Sentinel adopts the configuration carrying the higher epoch. A replaced `valkey.conf` names valkey1 too: when valkey1 is not the primary, the node replicates from it, a replica itself, until the Sentinels repoint the node once `failover-timeout` (60 s) has passed, about a minute and a half. One node per converge, replicas first and the primary last after `cache-manual-failover`.

### What to do

1. **Fail the primary over if this node holds it** — `cache-manual-failover` above — so the node is a replica before its files go.
2. **Read the image digest the node runs**, on the node, before its containers go: `sudo docker inspect zcrypto-valkey --format '{{.Config.Image}}'` prints `valkey/valkey@sha256:<64 hex>`.
3. **Stop the node's cache containers:** `sudo systemctl stop zcrypto-cache.service` on the node.
4. **Converge with the reset and that digest**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<the 64 hex step 2 printed>`.
5. **Start the containers:** `sudo systemctl start zcrypto-cache.service` on the node.
6. **Confirm by value**, as `cache-rejoin-node` steps 3 and 4 do, a minute and a half after step 5; on this node `sn SENTINEL get-master-addr-by-name zcache` names the current primary within seconds.

### Retire when

The tasks in `infra/ansible/roles/cache/tasks/main.yml` that render `valkey.conf` and `sentinel.conf` lose their absent-file condition, which makes the reset flag meaningless.

______________________________________________________________________

<a name="cache-password-rotation"></a>

## cache-password-rotation — PROCEDURE: applying a changed cache password

### What you are seeing

Nothing fired. You mean to change a password in `group_vars/cache_host/vault.yml`, or a converge's drift report named `valkey.conf`, `sentinel.conf` or `users.acl` after one changed there, since their renders carry the passwords.

### What it means

The nodes authenticate to each other: a replica to its primary with the `replica` password, each Sentinel to each Valkey with the `sentinel` password and to the other Sentinels with Sentinel's `requirepass`. A node reset alone to a new password fails to authenticate to, and from, a node still holding the old one, so the three nodes' files are replaced in one stop, the set down for the minutes it takes; once the engine is wired to the set, that is inside an engine inter-cycle gap. The rendered files name valkey1 as the first primary, so valkey1 holds the primary before the stop and starts first, and no write the set took is lost. `vk` and `sn` read their passwords from files a converge carrying the node's image digest re-renders, and Alloy reads the exporter password and `requirepass` from a secrets file the same converge re-renders and the container reads when it is recreated.

### What to do

1. **Put the primary on valkey1 while the nodes still run the old passwords:** `cache-manual-failover` above, repeated until `sn SENTINEL get-master-addr-by-name zcache` names `10.98.0.11`. When a converge already carried the change, `vk` or `sn` answers `WRONGPASS` or `NOAUTH`: put the old value back in `vault.yml`, converge each node with the image digest it runs, read as step 3 reads it, and begin here again.
2. **Change the password** in `group_vars/cache_host/vault.yml` by the recipe in that file's header, merged to `develop`, which the converges below run from.
3. **Read each node's running digests**, on each node: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, then Alloy's.
4. **Stop the three nodes, valkey3 and valkey2 before valkey1:** `sudo systemctl stop zcrypto-cache.service` on each.
5. **Converge each node with the reset, valkey1 first**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`. The converge renders the node's files and starts its daemons.
6. **Recreate each node's Alloy** so it reads the new secrets: `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d` on each node.
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
5. **Confirm by value:** `uv run python infra/scripts/grafana-query.py 'count by (master_address) (redis_sentinel_master_status{job="sentinel"} == 1)'` names one address, counted 3, and the rule is back to **Normal**.

### Retire when

`zcrypto-cache-primary-count` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-cache-replicas-short"></a>

## zcrypto-cache-replicas-short — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · primary has fewer than two replicas`: for five minutes the primary has reported fewer than two connected replicas. The node the notification names is the primary.

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

A **warning** Grafana alert, `Cache · append-only file off or failing`: for five minutes a node's append-only file has been disabled, or its last write or its last rewrite has not been `ok`.

### What it means

The set writes every command to the append-only file before answering (`appendfsync always`), which is what makes a node's copy survive its own restart. A failed write makes Valkey refuse writes on that node until one succeeds; a failed rewrite leaves the file growing; a disabled file means the node's config is not the role's.

### What to do

1. **Read which of the three**, on the node: `vk INFO persistence`, its `aof_enabled`, `aof_last_write_status` and `aof_last_bgrewrite_status` lines.
2. **A failed write or rewrite is usually the disk:** `df -h /var/lib/zcrypto-cache` on the node, and the Cache board's *Root filesystem free* panel (104). Free space, then restart the node's containers, `sudo systemctl restart zcrypto-cache.service`, failing the primary over first if this node holds it; a rewrite on demand, `BGREWRITEAOF`, is outside the `exporter` user's commands.
3. **Disabled** is a config that is not the role's: apply `cache-config-reset` above to the node.

### Retire when

`zcrypto-cache-aof-not-ok` is absent from `infra/grafana/alerts.yaml`.

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
````

- [ ] **Step 15: Re-measure the daily pass's autonomy floor over the runbook corpus**

`tests/test_ops_daily.py` holds the read-only runbook commands the daily pass classifies autonomous on ops at or above 0.70 of all of them (`test_most_read_only_diagnostics_are_autonomous_on_ops` and `test_the_runbook_corpus_reads_identically_under_the_identity_resolver`), and `infra/runbooks/cache.md` adds commands to that corpus. The ratio, read before and after this task's runbook lands:

```bash
uv run python - <<'EOF'
import sys

sys.path.insert(0, "tests")
import test_ops_daily as t

reads = [c for c in t._runbook_commands() if not any(tok in c for tok in t._DESTRUCTIVE)]
auto = [c for c in reads if t.ops_daily.classify_action(f"`{c}`", host="ops", resolve=t._identity) is t.ops_daily.Tier.AUTONOMOUS]
print(f"{len(auto)}/{len(reads)} = {len(auto) / len(reads):.4f}")
EOF
```

Expected: a ratio at or above `0.7000`. The branch read `219/312 = 0.7019` before `infra/runbooks/cache.md` existed; the figure with it is this step's own reading, and the two floor tests run at Step 17. Below `0.7000`, the floor tests fail and their docstring's remedy is the one taken: widen the pass's allowlist with read heads the corpus justifies, never narrow the extraction.

- [ ] **Step 16: The Logs board's host list, the observability page and the fleet page**

In `infra/grafana/zcrypto-logs-dashboard.json`, the `host` variable: replace `        "query": "Capture primary : zcrypto, Capture secondary : zcrypto-red, Ops : ops, NAS : nas, Edge : zaccess",` with `        "query": "Capture primary : zcrypto, Capture secondary : zcrypto-red, Ops : ops, NAS : nas, Edge : zaccess, Cache 1 : zcrypto-valkey1, Cache 2 : zcrypto-valkey2, Cache 3 : zcrypto-valkey3",`; in its `description`, replace `All expands to the five pinned machines joined into one matcher` with `All expands to the eight pinned machines joined into one matcher`; and replace the options list's last entry and its closing bracket,

```json
          {
            "selected": false,
            "text": "Edge",
            "value": "zaccess"
          }
        ]
```

with

```json
          {
            "selected": false,
            "text": "Edge",
            "value": "zaccess"
          },
          {
            "selected": false,
            "text": "Cache 1",
            "value": "zcrypto-valkey1"
          },
          {
            "selected": false,
            "text": "Cache 2",
            "value": "zcrypto-valkey2"
          },
          {
            "selected": false,
            "text": "Cache 3",
            "value": "zcrypto-valkey3"
          }
        ]
```

In `infra/runbooks/observability.md`, replace `These sections cover the instruments, not the things they measure: the four `grafana-alloy` containers that ship every metric` with `These sections cover the instruments, not the things they measure: the `grafana-alloy` containers that ship every metric`, and replace the line

```markdown
(The fifth sibling, `zcrypto-alloy-dark-zaccess`, covers the bridgehead, whose Alloy is a native apt install with a different procedure — it has its own section at `zaccess.md#zaccess-bridgehead-dark`.)
```

with

```markdown
(The fifth sibling, `zcrypto-alloy-dark-zaccess`, covers the bridgehead, whose Alloy is a native apt install with a different procedure — it has its own section at `zaccess.md#zaccess-bridgehead-dark`. The three cache nodes' siblings, `zcrypto-alloy-dark-cache-1` to `-3`, have theirs at `cache.md#zcrypto-alloy-dark-cache-1`, since their set is watched from the other two nodes while one is dark.)
```

In the same page's `zcrypto-node-collector-failed` section, whose rule has no host selector and so reads the cache nodes too (their keep list admits `node_scrape_collector_success`), make three replacements. `both capture hosts, ops, the NAS and the bridgehead. All five run the same six collectors` becomes `both capture hosts, ops, the NAS, the bridgehead and the three cache nodes. All eight run the same six collectors` (the cache config's `set_collectors` is the same six). In the table row beginning `` | `textfile`, on a capture host | ``, `` and on the primary `zcrypto-engine-journal-prune-dead` | `` becomes `` and on the primary `zcrypto-engine-journal-prune-dead` and the engine host's rows of `zcrypto-cache-wg-handshake-stale` | ``. After the row `` | `textfile`, on the bridgehead | `zaccess-tunnel-stale`, `zaccess-cert-expiring` | none | ``, insert the row

```markdown
| `textfile`, on a cache node | that node's rows of `zcrypto-cache-wg-handshake-stale` | none |
```

In `docs/reference/fleet.md`, section `Telemetry labels`, after the Loki bullet Task 1 rewrote (the line beginning `- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red, zcrypto-valkey1,`), insert the bullet

```markdown
- The cache nodes ship under `host="zcrypto-valkey1"` to `"zcrypto-valkey3"`, shown as `Cache 1` to `Cache 3` in Slack and on the Logs board; their Valkey and Sentinel series carry `job="valkey"` and `job="sentinel"`, their log lines `container` `valkey`, `sentinel`, `alloy` and `zcache-probe`, and `zcache_wireguard_handshake_age_seconds`, which the engine host ships too, a `peer` label holding the far end's mesh address.
```

In section `Services and instruments`, in the `grafana-alloy` row (the line beginning `| \`grafana-alloy\` |`), replace its host cell `zcrypto, zcrypto-red, zcrypto-ops, nas` with `zcrypto, zcrypto-red, zcrypto-ops, nas, zcrypto-valkey1 to 3`, and after the `access probe timers` row, the table's last, insert:

```markdown
| `zcrypto-valkey`, `zcrypto-sentinel` | zcrypto-valkey1, zcrypto-valkey2, zcrypto-valkey3 | Valkey and its Sentinel under `zcrypto-cache.service` (compose at `/opt/zcrypto-cache`); master name `zcache`; the node's Alloy scrapes them as jobs `valkey` and `sentinel` | `127.0.0.1` and the node's `zcache0` address, `:6379` and `:26379` |
| `zcache0` WireGuard | zcrypto (10.98.0.1), zcrypto-valkey1 to 3 (10.98.0.11 to .13) | `/etc/wireguard/zcache0.conf`; `:51821/udp`; a full mesh, `AllowedIPs /32` per peer | `wg show zcache0` |
| `zcache-probe` timer | zcrypto, zcrypto-valkey1 to 3 | each minute, `zcache.prom`: each mesh peer's WireGuard handshake age | `.prom` into `/var/lib/zcrypto-node-textfile`, read by the host's Alloy |
| cache node timers | zcrypto-valkey1 to 3 | `zcrypto-reboot-check` (15-min), a copy of the capture hosts' | `.prom` into `/var/lib/zcrypto-node-textfile`, read by the node's Alloy |
```

In section `Storage topology`, after the bullet `- Not replicated: the engine price store, `/var/lib/zcrypto-engine/store` on zcrypto.`, insert:

```markdown
- The cache nodes keep Valkey's data and the daemon-owned configs under `/var/lib/zcrypto-cache/{data,conf}`, a copy per node; valkey3, in another region, is the copy a regional outage leaves, and no backup leaves the three nodes.
```

Then the fleet page's contract, as its own run: `uv run pytest tests/test_fleet_contracts.py -q -p no:cacheprovider` — Expected: every test passed, the longest new cell under the 200-character cap.

- [ ] **Step 17: Run the tests and the runbook instruments**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py tests/test_fleet_contracts.py tests/test_grafana_push_sh.py tests/test_ops_daily.py::test_most_read_only_diagnostics_are_autonomous_on_ops tests/test_ops_daily.py::test_the_runbook_corpus_reads_identically_under_the_identity_resolver -q -p no:cacheprovider`
Expected: every test passed, the two autonomy floors among them.

Then the consumer command of this task's preamble — Expected: every test passed or skipped by a data gate, none failed. Then `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/cache.md infra/runbooks/observability.md docs/reference/fleet.md` — Expected: no output; `uv run python infra/scripts/runbook-internal-tokens.py infra/runbooks/cache.md | wc -l` — Expected: `0`; `git add infra/runbooks/cache.md && uv run python infra/scripts/runbook-triggers.py triggers && uv run python infra/scripts/runbook-triggers.py retire-when` — Expected: `0` and `0`.

- [ ] **Step 18: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; mdformat may renumber or re-space `infra/runbooks/cache.md` on the first run — re-run until clean and stage what it rewrote.

- [ ] **Step 19: Commit B**

```bash
git add infra/grafana/cache-dashboard.json infra/grafana/alerts.yaml infra/runbooks/cache.md infra/grafana/zcrypto-logs-dashboard.json infra/runbooks/observability.md docs/reference/fleet.md infra/ansible/roles/capture/files/config.alloy infra/scripts/ops_daily.py tests/test_dashboards_cover_metrics.py tests/test_infra_alloy_series.py tests/test_ops_daily.py
git commit -m "feat(grafana): the Cache board, the zcrypto-cache rule group and the cache runbook

\`infra/grafana/cache-dashboard.json\`, uid \`zcrypto-cache\`, draws the three nodes in four rows:
the hosts (Alloy up per node, load, memory, disk, the mesh handshake age per peer from all four
mesh members, the reboot flag and the mesh probe's freshness, Alloy against its cap, traffic), Valkey (role per node, reachability,
uptime, the primary count, which node is primary over time, connected replicas, replication lag,
the replica link, memory against maxmemory, commands, clients, the AOF and RDB status), Sentinel
(reachability, the primary each names, masters, known and healthy Sentinels, known replicas) and
the logs (the engine's lines naming the cache, the nodes' Valkey and Sentinel lines). A panel an
alert points at plots that rule's own expression under that rule's bar.

The \`zcrypto-cache\` group: Alloy dark per node, not exactly one primary as the Sentinels agree on
it (an address at least two of the three name healthy, so one node's dark telemetry cannot fire
it), fewer than two replicas on the primary, memory past 70% of maxmemory, the AOF off or failing, and a mesh handshake older
than three minutes on any of the four members, read as the recorded age plus the probe file's own
age so a stopped timer fires it too. Beside that rule the capture keep list admits the mesh probe's
family, since the engine host runs the probe; \`CAPTURE_REQUIRED\` in
\`tests/test_infra_alloy_series.py\` holds it there. \`infra/runbooks/cache.md\` carries a section per rule and the
four procedures the rules and the role's drift report lean on: moving the primary, rejoining a node, resetting a node's
config, and applying a changed password to the three nodes in one stop; its valkey-cli reads take
their passwords from the cache role's root-only env files. \`_UID_HOST\` in
\`infra/scripts/ops_daily.py\` names each Alloy-dark rule's node, which the rule's expression
aggregates away. The
Logs board gains the three hosts; \`docs/reference/fleet.md\` gains their telemetry labels, the
Valkey, mesh and mesh-probe rows of its services table and the cache nodes' storage; the
observability page points the Alloy-dark family at the cache section and names the cache nodes in
its collector-failure section. The daily pass's autonomy
floor over the runbook corpus reads <the ratio Step 15 printed> with the cache runbook in it.

\`_APP\` in \`tests/test_dashboards_cover_metrics.py\` gains the \`zcache\` namespace with its canary,
and \`tests/test_dashboards_cover_metrics.py::test_every_family_the_cache_nodes_admit_is_charted_or_alerted\`
holds the nodes' keep list, the fleet's first third-party families, to what a panel draws or a
rule reads. The proxy's row and its two rules are not here: the engine host's proxy scrape comes
with the proxy.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

Run: `git status --porcelain` — Expected: empty.

- [ ] **Step 20: Prove commit B's guards, then record the verdicts by a message-only amend**

```bash
R=tests/test_infra_alert_rules.py
M=tests/test_dashboards_cover_metrics.py
N_BOARD="$R::test_every_alert_rule_carries_a_resolving_runbook_link $R::test_every_runbook_link_in_an_alert_summary_resolves $R::test_every_runbook_link_in_a_dashboard_description_resolves $R::test_every_rule_routes_to_its_OWN_runbook_section $M::test_every_rule_points_at_a_real_panel_or_a_runbook $M::test_a_panels_red_line_agrees_with_the_rule_it_charts $M::test_every_family_the_cache_nodes_admit_is_charted_or_alerted"
AL=infra/grafana/alerts.yaml
AC2='s/#zcrypto-cache-aof-not-ok"$/#zcrypto-cache-aof-not-okx"/'
infra/scripts/mutate-probe.sh --file $AL --control "$AC2" --mutation 's/__panelId__: "204"/__panelId__: "299"/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $AL --control "$AC2" \
  --mutation 's/evaluator: {type: gt, params: \[180\]}/evaluator: {type: gt, params: [240]}/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $AL --control "$AC2" \
  --mutation 's/#zcrypto-cache-replicas-short"$/#zcrypto-cache-memory-70pct"/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
DB=infra/grafana/cache-dashboard.json
DC='s/"uid": "zcrypto-cache",/"uid": "zcrypto-cachex",/'
infra/scripts/mutate-probe.sh --file $DB --control "$DC" --mutation 's/"id": 212,/"id": 298,/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $DB --control "$DC" \
  --mutation 's/redis_sentinel_master_slaves{/redis_sentinel_master_slavez{/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $DB --control "$DC" \
  --mutation 's/{"color": "red", "value": 0.5}/{"color": "red", "value": 2}/' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/runbooks/cache.md --control 's/<a name="zcrypto-cache-aof-not-ok"><\/a>//' \
  --mutation 's/<a name="zcrypto-cache-replicas-short"><\/a>//' \
  -- uv run pytest $N_BOARD -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file $M --control 's/"zcrypto_capture_book_desynced",  #/"zcrypto_capture_book_desyncedx",  #/' \
  --mutation 's/(?:zcrypto|ops|zaccess|zcache)_/(?:zcrypto|ops|zaccess)_/' \
  -- uv run pytest $M::test_the_publisher_scan_still_finds_each_source_kind -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/capture/files/config.alloy --control 's/"up|node_load1|/"up|/' \
  --mutation 's/|zcache_wireguard_handshake_age_seconds|/|/' \
  -- uv run pytest "tests/test_infra_alloy_series.py::test_keep_regex_admits_every_published_series[capture]" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/ or _UID_HOST.get(uid) for instance in instances)/ for instance in instances)/' \
  --mutation '/^    "zcrypto-alloy-dark-cache-2": "zcrypto-valkey2",$/d' \
  -- uv run pytest tests/test_ops_daily.py::test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away -q -p no:cacheprovider
```

Expected: each run ends `KILLED` with `control proven`. Then replace the `PROBE_VERDICT` line, by `git commit --amend` with the whole message re-supplied, with:

```
Probe: `infra/scripts/mutate-probe.sh`, ten runs, seven of them through the seven board and runbook
cases of `tests/test_infra_alert_rules.py` and `tests/test_dashboards_cover_metrics.py`. Over
`infra/grafana/alerts.yaml`, control the AOF rule's runbook anchor broken: the primary-count
pointer moved to a panel that does not exist, KILLED, control proven; the handshake bar moved off
its panel's line, KILLED, control proven; the replicas rule routed to the memory section, KILLED,
control proven. Over `infra/grafana/cache-dashboard.json`, control the board's uid changed: the AOF
panel's id changed, KILLED, control proven; the Sentinel replicas family undrawn, KILLED, control
proven; the primary-count panel's red line moved to 2, KILLED, control proven. Over
`infra/runbooks/cache.md`, control the AOF anchor deleted: the replicas anchor deleted, KILLED,
control proven. Over `tests/test_dashboards_cover_metrics.py`, control a capture canary renamed,
through `test_the_publisher_scan_still_finds_each_source_kind`: the `zcache` namespace dropped
from `_APP`, KILLED, control proven. Over `infra/ansible/roles/capture/files/config.alloy`, control
`node_load1` dropped from the keep regex, through the capture case of
`test_keep_regex_admits_every_published_series`: the mesh probe's family dropped, KILLED, control
proven. Over `infra/scripts/ops_daily.py`, control the uid fallback removed from `_hosts_of`, through
`test_the_host_is_recovered_from_the_uid_when_the_rule_aggregates_it_away`: Cache 2's uid dropped
from `_UID_HOST`, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

**Operator steps (attended)**

None of this task's attended steps runs on the branch: Alloy's converge and start on each node, the capture hosts' converge that deploys commit B's keep-regex edit to their Alloy, the read of every metric name and job before the push, the correction when one differs, the push from merged `develop`, each rule's first sample by value, a fresh Loki line per node and the Alloy pins rows are `## Rollout (attended)` steps R5, R7, R8 and R9. Alloy opens no port, so neither firewall layer changes: its one listener is `127.0.0.1:12345`, and it reaches Grafana Cloud outbound.

---

### Task 6: The compatibility probe — the pinned library's cache client against one Valkey server

*Rulings: R19 kept this task to the script and its tests, its run an operator step, `## Rollout (attended)` step R4, after the mesh and before the cache role's converge on `zcrypto-valkey1`, against a throwaway `docker run --rm -d --network host valkey/valkey@<digest>` on the node's loopback, removed after the probe; R13 set the probe's image to the engine row's digest in `docs/reference/fleet-pins.md` and its `--expect-nautilus` to `pyproject.toml`'s pin.*

The probe settles spec D15's first item, the one library-side unknown: whether the pinned `nautilus-trader`'s Redis cache backing reads Valkey's `INFO` version line and round-trips an order through Valkey. It is a script, not a `cli/` command: it runs once, by hand, inside the app image on `zcrypto-valkey1`, the source on stdin as `kraken-window-reads.py` runs (`infra/runbooks/engine-procedures.md`'s `--entrypoint python ... - < script.py` form), against a throwaway `valkey/valkey` container at the 9.1.2 digest, before the cache role lands on that node (`## Rollout (attended)` step R4). Decisions this task takes, beyond the brief:

- The order reaches the cache through `submit_order` with no execution client, copied from the construction that round-tripped an order through a real Redis during the estimate (`LiveExecutionEngineConfig(reconciliation=False)`, the strategy's `__new__` override, the 1.5 s stop timer): the risk engine denies the order, so nothing is sent, and the denied order is what the cache holds. The script's docstring states it.
- Each node runs in a forked child (`os.fork`, not `multiprocessing`, whose 3.14 default start method re-imports `__main__`, which a script read from stdin does not have): the library's logging and runtime are process-wide, so a second node in the same process is not a second start. The child's stdout and stderr pass through the parent, which replaces the literal password: the library builds a `redis://user:password@host` URL, and its own log lines never pass through Python.
- It refuses a server whose database 0 holds any key: it writes under `trader-PROBE-001:` and deletes nothing, so the refusal is what keeps it off the engine's set, and what makes "restored exactly the one written" a real comparison on a re-run.
- `--expect-nautilus` is a fifth required argument: the image is chosen by digest, and a digest carrying another `nautilus-trader` would answer a different question, so the probe refuses it (exit 2) rather than report it.
- The password flag refusal covers valkey-cli's own spellings (`-a`, `--auth`, `--askpass`) and every `--pass...` word but `--password-env`, the parser runs with `allow_abbrev=False` (argparse would otherwise take `--password` as an abbreviation of `--password-env`), and the parser's error text is stripped of the words it quotes or lists, since a stray argument may be the password itself.
- A password shorter than five characters is refused, as the cache role refuses one (spec D8).

**Files:**
- Create: `infra/scripts/valkey-compat-probe.py` (mode `0755`: its shebang puts it under `check-shebang-scripts-are-executable`)
- Test: `tests/test_valkey_compat_probe.py`

**Interfaces:**
- Consumes: the `nautilus-trader` pin in `pyproject.toml` (`2.0.0rc6.dev20260921`); `nautilus_trader.common.CacheConfig`, `nautilus_trader.infrastructure.RedisCacheConfig`, `nautilus_trader.live.LiveNode`, `nautilus_trader.config.LiveExecutionEngineConfig` and `LoggerConfig`, `nautilus_trader.trading.Strategy` and `StrategyConfig`, `nautilus_trader.model`'s `InstrumentId`, `OrderSide`, `Price`, `Quantity`, `StrategyId`, `TraderId`, imported inside `run_node` alone. Nothing from Tasks 1–5: the task can land at any point on the branch.
- Produces: `infra/scripts/valkey-compat-probe.py` with the command line `--host H --port P --username U --password-env VAR --expect-nautilus VERSION` and the exit contract 0 both halves pass, 1 a half failed (the server unreachable or the login refused among them), 2 refused before anything was written; `## Rollout (attended)` step R4 runs it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_valkey_compat_probe.py` with exactly:

```python
"""Guard: `infra/scripts/valkey-compat-probe.py` settles whether the pinned library's cache client works against
Valkey, run once by hand on a cache node with a password in its environment, so it must speak RESP correctly with no
client library, refuse a password it would otherwise take on the command line without echoing it, keep the
password out of what it prints, and exit 0 only when both halves pass. Nothing here opens a socket to a server:
the RESP read runs over a fake socket and the node halves are stand-ins."""

import importlib.util
import io
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/valkey-compat-probe.py"
SECRET = "hunter2secret"
REQUIRED = ["--host", "127.0.0.1", "--port", "6390", "--username", "engine", "--password-env", "PROBE_PW"]


def _load():
    """A script, not a package module: loaded by path under a private name."""
    spec = importlib.util.spec_from_file_location("_valkey_compat_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()


class _FakeSocket:
    """What `socket.create_connection` returns, holding the server's replies and recording what was sent."""

    def __init__(self, replies: bytes):
        self.sent = b""
        self._replies = io.BytesIO(replies)

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def makefile(self, mode: str):
        assert mode == "rb"
        return self._replies

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _bulk(text: str) -> bytes:
    data = text.encode()
    return b"$%d\r\n%s\r\n" % (len(data), data)


def _args(*extra: str) -> list[str]:
    return [*REQUIRED, "--expect-nautilus", probe.metadata.version("nautilus-trader"), *extra]


def test_encode_writes_a_resp_array_of_bulk_strings():
    assert probe.encode("AUTH", "engine", "pw") == b"*3\r\n$4\r\nAUTH\r\n$6\r\nengine\r\n$2\r\npw\r\n"
    assert probe.encode("DBSIZE") == b"*1\r\n$6\r\nDBSIZE\r\n"


@pytest.mark.parametrize(
    "wire,value",
    [
        (b"+OK\r\n", "OK"),
        (b":42\r\n", 42),
        (b"$5\r\nhello\r\n", b"hello"),
        (b"$0\r\n\r\n", b""),
        (b"$-1\r\n", None),
        (b"*2\r\n$1\r\na\r\n:1\r\n", [b"a", 1]),
        (b"*-1\r\n", None),
        # INFO's reply is one bulk string whose lines end in CRLF: the length, not the first CRLF, ends it.
        (b"$11\r\na:1\r\nb:22\r\n\r\n", b"a:1\r\nb:22\r\n"),
    ],
)
def test_decode_reads_each_resp2_reply_kind(wire, value):
    assert probe.decode(io.BytesIO(wire)) == value


def test_decode_raises_the_servers_error_reply():
    with pytest.raises(probe.RespError, match="WRONGPASS invalid username-password pair"):
        probe.decode(io.BytesIO(b"-WRONGPASS invalid username-password pair or user is disabled.\r\n"))


@pytest.mark.parametrize("wire", [b"", b"+OK", b"$5\r\nhel", b"$5\r\nhelloXY"])
def test_decode_refuses_a_truncated_reply(wire):
    with pytest.raises(ConnectionError, match="mid-reply"):
        probe.decode(io.BytesIO(wire))


def test_read_server_authenticates_then_reads_info_and_dbsize(monkeypatch):
    info = "# Server\r\nredis_version:7.2.4\r\nserver_name:valkey\r\nvalkey_version:9.1.2\r\n"
    fake = _FakeSocket(b"+OK\r\n" + _bulk(info) + b":0\r\n")
    monkeypatch.setattr(probe.socket, "create_connection", lambda address, timeout: fake)

    reading = probe.read_server("127.0.0.1", 6390, "engine", SECRET)

    assert fake.sent == probe.encode("AUTH", "engine", SECRET) + probe.encode("INFO", "server") + probe.encode("DBSIZE")
    assert reading == probe.ServerReading(redis_version="7.2.4", valkey_version="9.1.2", dbsize=0)


@pytest.mark.parametrize(
    "redis_version,passes",
    [("7.2.4", True), ("6.2.0", True), ("8.0.2", True), ("6.0.16", False), (None, False), ("7.2.4-rc1", False)],
)
def test_the_server_passes_at_the_librarys_version_floor(redis_version, passes):
    assert probe.server_passes(probe.ServerReading(redis_version, "9.1.2", 0)) is passes


@pytest.mark.parametrize(
    "extra",
    [
        ["--password", SECRET],
        [f"--password={SECRET}"],
        ["--pass", SECRET],
        ["-a", SECRET],
        [f"--auth={SECRET}"],
    ],
)
def test_the_parser_refuses_a_password_argument_without_echoing_it(monkeypatch, capsys, extra):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ") and "would put the password on the command line" in out.out
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize("extra", [[SECRET], ["--port", SECRET]])
def test_a_rejected_argument_is_not_echoed(monkeypatch, capsys, extra):
    """A stray positional, or a password typed into another flag's value: argparse would print either word."""
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ")
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize("value,why", [(None, "PROBE_PW is not set in the environment"), ("abcd", "shorter than 5")])
def test_the_password_comes_from_the_named_variable(monkeypatch, capsys, value, why):
    if value is None:
        monkeypatch.delenv("PROBE_PW", raising=False)
    else:
        monkeypatch.setenv("PROBE_PW", value)

    assert probe.main(_args()) == 2

    out = capsys.readouterr().out
    assert why in out
    assert value is None or value not in out


def test_another_library_version_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main([*REQUIRED, "--expect-nautilus", "0.0.0"]) == 2

    assert ", not 0.0.0" in capsys.readouterr().out


@pytest.mark.parametrize(
    "server_ok,written,restored,code",
    [
        (True, ["O-1"], ["O-1"], 0),
        (False, ["O-1"], ["O-1"], 1),
        (True, ["O-1"], [], 1),
        (True, ["O-1"], ["O-1", "O-2"], 1),
        (True, ["O-1"], None, 1),
        (True, None, None, 1),
        (True, [], [], 1),
        (True, ["O-1", "O-2"], ["O-1", "O-2"], 1),
    ],
)
def test_the_verdict_needs_both_halves(server_ok, written, restored, code):
    assert probe.verdict(server_ok, written, restored) == code


@pytest.mark.parametrize(
    "redis_version,dbsize,halves,code,last",
    [
        ("7.2.4", 0, {True: ["O-1"], False: ["O-1"]}, 0, "PASS"),
        ("7.2.4", 0, {True: ["O-1"], False: []}, 1, "FAIL"),
        (None, 0, {True: ["O-1"], False: ["O-1"]}, 1, "FAIL"),
        ("7.2.4", 3, {}, 2, "refusing: database 0 holds 3 key(s); the probe writes there, so it takes an empty server"),
    ],
)
def test_main_composes_the_exit_from_both_halves(monkeypatch, capsys, redis_version, dbsize, halves, code, last):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")
    monkeypatch.setattr(probe, "read_server", lambda *a: probe.ServerReading(redis_version, "9.1.2", dbsize))
    ran = []

    def fake_in_child(half, password, deadline_secs):
        mint = half.args[1]
        ran.append(mint)
        return halves[mint], "ok"

    monkeypatch.setattr(probe, "in_child", fake_in_child)

    assert probe.main(_args()) == code

    assert capsys.readouterr().out.splitlines()[-1] == last
    assert ran == ([] if dbsize else [True, False])


def test_the_restore_is_not_run_when_nothing_was_written(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")
    monkeypatch.setattr(probe, "read_server", lambda *a: probe.ServerReading("7.2.4", "9.1.2", 0))
    ran = []

    def fake_in_child(half, password, deadline_secs):
        ran.append(half.args[1])
        return None, "RuntimeError: no connection"

    monkeypatch.setattr(probe, "in_child", fake_in_child)

    assert probe.main(_args()) == 1

    assert ran == [True]
    assert "restore: skipped, nothing was written" in capsys.readouterr().out


def test_a_server_that_refuses_the_login_fails_the_probe_without_the_password(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", SECRET)
    fake = _FakeSocket(b"-WRONGPASS invalid username-password pair or user is disabled.\r\n")
    monkeypatch.setattr(probe.socket, "create_connection", lambda address, timeout: fake)

    assert probe.main(_args()) == 1

    out = capsys.readouterr().out
    assert "server: FAIL, RespError: WRONGPASS" in out
    assert SECRET not in out


def test_a_half_runs_in_a_child_and_its_output_is_redacted(capsys):
    def half():
        print(f"connecting to redis://engine:{SECRET}@127.0.0.1:6390")
        return ["O-1"]

    assert probe.in_child(half, SECRET, 30) == (["O-1"], "ok")

    out = capsys.readouterr().out
    assert "  | connecting to redis://engine:<redacted>@127.0.0.1:6390" in out
    assert SECRET not in out


def test_a_half_that_raises_reports_its_error_redacted(capsys):
    def half():
        raise RuntimeError(f"could not reach redis://engine:{SECRET}@127.0.0.1:6390")

    ids, why = probe.in_child(half, SECRET, 30)

    assert ids is None
    assert why == "RuntimeError: could not reach redis://engine:<redacted>@127.0.0.1:6390"


def test_a_half_that_hangs_is_killed_at_the_deadline():
    started = time.monotonic()

    assert probe.in_child(lambda: time.sleep(30), SECRET, 0.5) == (None, "did not finish in 0.5 s")

    assert time.monotonic() - started < 10


def test_the_library_accepts_the_cache_settings_the_probe_passes():
    """The probe's two configs, built with no server: a renamed keyword on a bump fails here, not on the node."""
    from nautilus_trader.common import CacheConfig
    from nautilus_trader.infrastructure import RedisCacheConfig

    cache = CacheConfig(use_instance_id=False, flush_on_start=False)
    RedisCacheConfig(
        host="127.0.0.1",
        port=6390,
        username="engine",
        password=SECRET,
        ssl=False,
        connection_timeout=5,
        response_timeout=5,
        number_of_retries=3,
    )
    assert (cache.use_instance_id, cache.flush_on_start) == (False, False)
```

Run: `uv run pytest tests/test_valkey_compat_probe.py::test_encode_writes_a_resp_array_of_bulk_strings -q -p no:cacheprovider`
Expected: `1 error`, `ERROR tests/test_valkey_compat_probe.py - FileNotFoundError: [Errno 2] No such file or directory: '<repo>/infra/scripts/valkey-compat-probe.py'`: the module loads the script by path at import, and the script does not exist yet.

- [ ] **Step 2: Write the probe**

Create `infra/scripts/valkey-compat-probe.py` with exactly:

```python
#!/usr/bin/env python3
"""The pinned nautilus-trader cache client against one Valkey server: the version line it parses, and an order
written by one node and restored by the next.

  --host H --port P --username U --password-env VAR --expect-nautilus VERSION

1. A raw RESP read, the standard library only: AUTH, INFO server, DBSIZE. It prints the `redis_version:` line the
   library's version check parses and the `valkey_version:` line, and passes when `redis_version` is present and at
   or above 6.2.0, the floor below which the library logs an error and carries on.
2. Two nodes, each in its own forked child, both with the engine's cache settings (`use_instance_id=False`,
   `flush_on_start=False`, `load_cache` at its default): the first mints one limit order and submits it with no
   execution client, so the order is denied, never sent, and still lands in the cache; the second prints the client
   order ids its cache restored at start. It passes when those are exactly the one the first wrote.

It writes under `trader-PROBE-001:` in database 0 and deletes nothing, so it refuses a server whose database 0 holds
any key: run it against a throwaway server, never the engine's set.

Exit: 0 both halves pass; 1 a half failed, the server unreachable or the login refused among them; 2 refused before
anything was written (usage, a password on the command line, the variable unset or shorter than five characters, a
nautilus-trader other than the expected one, a non-empty database 0).

Run it inside the app image on the server's host, the script on stdin, the password in a root-only env file:
    ssh <host> sudo docker run --rm -i --network host --memory 512m --env-file <env file> \
      --entrypoint python ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest> - --host 127.0.0.1 --port <port> \
      --username <user> --password-env <VAR> --expect-nautilus <version> < infra/scripts/valkey-compat-probe.py
The password is read from the environment and never printed: the library's own log lines pass through a filter that
replaces it, and an argument that could carry it is refused without being echoed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import signal
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from importlib import metadata

TRADER_ID = "PROBE-001"
INSTRUMENT = "XBT/EUR.KRAKEN"
LIBRARY_FLOOR = (6, 2, 0)
MIN_PASSWORD_CHARS = 5
SOCKET_TIMEOUT_SECS = 5.0
# Three retries of five-second timeouts bound a node that cannot reach the server well inside this.
NODE_DEADLINE_SECS = 120.0
# valkey-cli's password flags: the habit an operator brings to a Valkey command line.
PASSWORD_FLAGS = ("-a", "--auth", "--askpass")
REDACTED = "<redacted>"
_QUOTED = re.compile(r"'[^']*'")
_ELIDED = "'...'"


class Refusal(RuntimeError):
    """Raised before anything connects. Names flags and variables, never values."""


class RespError(RuntimeError):
    """The server's error reply, verbatim."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        # argparse quotes the words it rejects and lists the ones it does not know, and either may be the password.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments"
        message = _QUOTED.sub(_ELIDED, message)
        raise Refusal(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    for word in argv:
        flag = word.split("=", 1)[0]
        if flag in PASSWORD_FLAGS or (flag.startswith("--pass") and flag != "--password-env"):
            raise Refusal(
                f"{flag} would put the password on the command line; put it in the environment and name the variable "
                "with --password-env"
            )
    parser = _Parser(prog="valkey-compat-probe", allow_abbrev=False)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-env", required=True)
    parser.add_argument("--expect-nautilus", required=True)
    return parser.parse_args(argv)


def read_password(variable: str) -> str:
    password = os.environ.get(variable, "")
    if not password:
        raise Refusal(f"{variable} is not set in the environment")
    if len(password) < MIN_PASSWORD_CHARS:
        raise Refusal(f"{variable} is shorter than {MIN_PASSWORD_CHARS} characters, which the library logs unredacted")
    return password


def require_library(expected: str) -> str:
    try:
        found = metadata.version("nautilus-trader")
    except metadata.PackageNotFoundError as exc:
        raise Refusal("no nautilus-trader in this interpreter") from exc
    if found != expected:
        raise Refusal(f"this interpreter carries nautilus-trader {found}, not {expected}")
    return found


def redact(text: str, password: str) -> str:
    """The literal password replaced. The library builds a `redis://user:password@host` URL, which percent-encodes
    the password, so a password with a character that encoding changes would pass this filter in its encoded form:
    the rollout mints a hex password, which encodes to itself."""
    return text.replace(password, REDACTED)


def encode(*words: str | bytes) -> bytes:
    """One RESP command, an array of bulk strings."""
    out = [b"*%d\r\n" % len(words)]
    for word in words:
        data = word.encode() if isinstance(word, str) else word
        out.append(b"$%d\r\n%s\r\n" % (len(data), data))
    return b"".join(out)


def decode(reader) -> object:
    """One RESP2 reply off a binary file object: a simple string as `str`, an integer as `int`, a bulk string as
    `bytes`, a null as None, an array as a list; an error reply raises `RespError`."""
    line = reader.readline()
    if not line.endswith(b"\r\n"):
        raise ConnectionError("the server closed the connection mid-reply")
    kind, body = line[:1], line[1:-2]
    if kind == b"+":
        return body.decode()
    if kind == b"-":
        raise RespError(body.decode(errors="replace"))
    if kind == b":":
        return int(body)
    if kind == b"$":
        size = int(body)
        if size < 0:
            return None
        data = reader.read(size + 2)
        if len(data) != size + 2 or not data.endswith(b"\r\n"):
            raise ConnectionError("the server closed the connection mid-reply")
        return data[:-2]
    if kind == b"*":
        size = int(body)
        return None if size < 0 else [decode(reader) for _ in range(size)]
    raise RespError(f"not a RESP2 reply: {line[:16]!r}")


def parse_info(text: str) -> dict[str, str]:
    return dict(line.split(":", 1) for line in text.splitlines() if line and not line.startswith("#") and ":" in line)


def version_tuple(text: str | None) -> tuple[int, ...] | None:
    if text is None or not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


@dataclass(frozen=True)
class ServerReading:
    redis_version: str | None
    valkey_version: str | None
    dbsize: int


def read_server(host: str, port: int, username: str, password: str) -> ServerReading:
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_SECS) as sock:
        reader = sock.makefile("rb")

        def call(*words: str) -> object:
            sock.sendall(encode(*words))
            return decode(reader)

        call("AUTH", username, password)
        info = parse_info(call("INFO", "server").decode())
        dbsize = call("DBSIZE")
    return ServerReading(info.get("redis_version"), info.get("valkey_version"), dbsize)


def server_passes(reading: ServerReading) -> bool:
    found = version_tuple(reading.redis_version)
    return found is not None and found >= LIBRARY_FLOOR


def report_server(reading: ServerReading) -> bool:
    print(f"redis_version: {reading.redis_version if reading.redis_version is not None else 'absent'}")
    print(f"valkey_version: {reading.valkey_version if reading.valkey_version is not None else 'absent'}")
    passed = server_passes(reading)
    floor = ".".join(str(part) for part in LIBRARY_FLOOR)
    print(f"server: {'PASS' if passed else 'FAIL'} (the library's floor is {floor})")
    return passed


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    username: str
    password: str


def run_node(target: Target, mint: bool) -> list[str]:
    """One LiveNode with no data or execution client and reconciliation off; returns the client order ids its cache
    holds at start, after minting and submitting one limit order first when `mint` is set."""
    import threading

    from nautilus_trader.common import CacheConfig, Environment, LogLevel
    from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
    from nautilus_trader.infrastructure import RedisCacheConfig
    from nautilus_trader.live import LiveNode
    from nautilus_trader.model import InstrumentId, OrderSide, Price, Quantity, StrategyId, TraderId
    from nautilus_trader.trading import Strategy, StrategyConfig

    config = StrategyConfig(strategy_id=StrategyId(TRADER_ID), order_id_tag="001")
    seen: list[str] = []

    class Probe(Strategy):
        def __new__(cls, *args, **kwargs):
            return super().__new__(cls, config)

        def __init__(self, box):
            super().__init__(config=config)
            self._box = box

        def on_start(self):
            try:
                if mint:
                    order = self.order_factory.limit(
                        InstrumentId.from_str(INSTRUMENT), OrderSide.BUY, Quantity.from_str("0.0001"), Price.from_str("90000.0")
                    )
                    self.submit_order(order)
                seen.extend(str(order.client_order_id) for order in self.cache.orders())
            finally:
                threading.Timer(1.5, lambda: self._box[0].stop()).start()

    box = [None]
    node = (
        LiveNode.builder(name="valkey-probe", trader_id=TraderId(TRADER_ID), environment=Environment.LIVE)
        .with_logging(LoggerConfig(stdout_level=LogLevel.INFO))
        .with_cache_config(CacheConfig(use_instance_id=False, flush_on_start=False))
        .with_cache_database_factory(
            RedisCacheConfig(
                host=target.host,
                port=target.port,
                username=target.username,
                password=target.password,
                ssl=False,
                connection_timeout=5,
                response_timeout=5,
                number_of_retries=3,
            )
        )
        .with_exec_engine_config(LiveExecutionEngineConfig(reconciliation=False))
        .build()
    )
    box[0] = node.handle()
    node.add_strategy(Probe(box))
    try:
        node.run()
    finally:
        node.dispose()
    return seen


def in_child(half: Callable[[], list[str]], password: str, deadline_secs: float) -> tuple[list[str] | None, str]:
    """Run `half` in a forked child; return its ids and "ok", or None and why. A child because the library's logging
    and runtime are process-wide, so two nodes in one process are not two starts. Everything the child writes to its
    stdout and stderr, the library's log lines among them, is printed here through `redact`."""
    sys.stdout.flush()
    sys.stderr.flush()
    out_r, out_w = os.pipe()
    res_r, res_w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(out_r)
        os.close(res_r)
        os.dup2(out_w, 1)
        os.dup2(out_w, 2)
        sys.stdout = sys.stderr = open(out_w, "w", buffering=1, closefd=False)
        try:
            payload = {"ids": half()}
        except BaseException as exc:  # noqa: BLE001 -- the parent reports it
            payload = {"error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.flush()
        os.write(res_w, json.dumps(payload).encode())
        os._exit(0)
    os.close(out_w)
    os.close(res_w)
    deadline = time.monotonic() + deadline_secs
    pending, result, timed_out = b"", b"", False
    open_fds = {out_r, res_r}
    while open_fds:
        left = deadline - time.monotonic()
        if left <= 0:
            os.kill(pid, signal.SIGKILL)
            timed_out = True
            break
        ready, _, _ = select.select(sorted(open_fds), [], [], left)
        for fd in ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                open_fds.discard(fd)
            elif fd == res_r:
                result += chunk
            else:
                *lines, pending = (pending + chunk).split(b"\n")
                for line in lines:
                    print(f"  | {redact(line.decode(errors='replace'), password)}")
    if pending:
        print(f"  | {redact(pending.decode(errors='replace'), password)}")
    os.waitpid(pid, 0)
    os.close(out_r)
    os.close(res_r)
    if timed_out:
        return None, f"did not finish in {deadline_secs:g} s"
    try:
        payload = json.loads(result)
    except ValueError:
        return None, "the child exited without a result"
    if "error" in payload:
        return None, redact(payload["error"], password)
    return payload["ids"], "ok"


def verdict(server_ok: bool, written: list[str] | None, restored: list[str] | None) -> int:
    return 0 if server_ok and written is not None and len(written) == 1 and restored == written else 1


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        password = read_password(args.password_env)
        library = require_library(args.expect_nautilus)
    except Refusal as exc:
        print(f"refusing: {exc}")
        return 2
    print(f"nautilus-trader {library}")
    try:
        reading = read_server(args.host, args.port, args.username, password)
    except (OSError, RespError) as exc:
        print(f"server: FAIL, {type(exc).__name__}: {redact(str(exc), password)}")
        return 1
    server_ok = report_server(reading)
    if reading.dbsize:
        print(f"refusing: database 0 holds {reading.dbsize} key(s); the probe writes there, so it takes an empty server")
        return 2
    target = Target(args.host, args.port, args.username, password)
    written, why = in_child(partial(run_node, target, True), password, NODE_DEADLINE_SECS)
    print(f"write: {written if written is not None else why}")
    if written:
        restored, why = in_child(partial(run_node, target, False), password, NODE_DEADLINE_SECS)
    else:
        restored, why = None, "skipped, nothing was written"
    print(f"restore: {restored if restored is not None else why}")
    code = verdict(server_ok, written, restored)
    print("PASS" if code == 0 else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Then `chmod 0755 infra/scripts/valkey-compat-probe.py`; `git ls-files -s` shows `100755` once Step 6 stages it.

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/test_valkey_compat_probe.py::test_encode_writes_a_resp_array_of_bulk_strings tests/test_valkey_compat_probe.py::test_decode_reads_each_resp2_reply_kind tests/test_valkey_compat_probe.py::test_decode_raises_the_servers_error_reply tests/test_valkey_compat_probe.py::test_decode_refuses_a_truncated_reply tests/test_valkey_compat_probe.py::test_read_server_authenticates_then_reads_info_and_dbsize tests/test_valkey_compat_probe.py::test_the_server_passes_at_the_librarys_version_floor tests/test_valkey_compat_probe.py::test_the_parser_refuses_a_password_argument_without_echoing_it tests/test_valkey_compat_probe.py::test_a_rejected_argument_is_not_echoed tests/test_valkey_compat_probe.py::test_the_password_comes_from_the_named_variable tests/test_valkey_compat_probe.py::test_another_library_version_is_refused tests/test_valkey_compat_probe.py::test_the_verdict_needs_both_halves tests/test_valkey_compat_probe.py::test_main_composes_the_exit_from_both_halves tests/test_valkey_compat_probe.py::test_the_restore_is_not_run_when_nothing_was_written tests/test_valkey_compat_probe.py::test_a_server_that_refuses_the_login_fails_the_probe_without_the_password tests/test_valkey_compat_probe.py::test_a_half_runs_in_a_child_and_its_output_is_redacted tests/test_valkey_compat_probe.py::test_a_half_that_raises_reports_its_error_redacted tests/test_valkey_compat_probe.py::test_a_half_that_hangs_is_killed_at_the_deadline tests/test_valkey_compat_probe.py::test_the_library_accepts_the_cache_settings_the_probe_passes -q -p no:cacheprovider`
Expected: `49 passed` (eighteen tests, eight of them parametrised; the file and the script were run together in a scratch copy of the tree while this plan was written, 49 passed, and the whole probe ran end to end, over stdin, against a loopback `redis-server` 8.0.2 with an ACL user: exit 0, the order written and restored, the password absent from the output).

- [ ] **Step 4: Run the consumers**

Run: `grep -rl 'valkey-compat-probe' tests/ infra/ .claude/`
Expected: two lines, `tests/test_valkey_compat_probe.py` and `infra/scripts/valkey-compat-probe.py`, the script itself, whose usage line and `prog=` name it; no other consumer exists to run. `tests/test_internal_terms_not_operator_visible.py` and `tests/test_code_prose_citations.py` walk `infra/scripts/` and read the new file's literals and comments:

Run: `uv run pytest "tests/test_internal_terms_not_operator_visible.py::test_python_string_literals_carry_no_internal_vocabulary[infra/scripts/valkey-compat-probe.py]" tests/test_code_prose_citations.py::test_every_plan_task_number_carries_its_serial -q -p no:cacheprovider`
Expected: `2 passed` (both checks were run over the new files' text while this plan was written, both clean).

- [ ] **Step 5: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/valkey-compat-probe.py tests/test_valkey_compat_probe.py
git commit -m "feat(cache): the compatibility probe runs the pinned library's cache client against one Valkey server

\`infra/scripts/valkey-compat-probe.py\` settles the one library-side unknown before anything is built
on it. A raw RESP read with the standard library alone -- AUTH, INFO server, DBSIZE -- prints the
\`redis_version:\` line the library's version check parses and the \`valkey_version:\` line, and passes
at or above the library's 6.2.0 floor; then two LiveNodes, each in a forked child with the engine's
cache settings, write one limit order through \`submit_order\` with no execution client, so it is
denied and never sent, and read it back at the next start. The probe exits 0 only when the restored
client order ids are exactly the one written, 1 when a half fails, 2 when it refuses before writing.
It refuses a server whose database 0 holds a key, since it writes there and deletes nothing, and a
nautilus-trader other than the one named. A password on the command line, as a flag or a stray
word, is refused without being echoed; the password comes from a named environment variable, and
the library's own log lines pass through a filter that replaces it. It runs inside the app image on
the node, the source on stdin, so it needs nothing the image lacks.

Cases: the RESP encoder and each RESP2 reply kind over fixed bytes, a bulk string carrying CRLF and
four truncations; the login, INFO and DBSIZE sent in order over a fake socket; the version floor;
five password-flag spellings and two rejected arguments refused with the password absent from the
output; the variable unset or short; another library version; the exit composed from both halves,
the restore skipped when nothing was written, the non-empty refusal, a refused login; a forked
half's output redacted, its error redacted, its hang killed at the deadline; the two configs the
library builds with no server.

PROBE_VERDICT

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC"
```

`<model>` is written by the executor as its own model name (`Claude Opus 5.5`, `Claude Fable 5.1`, ...), never copied from this plan.

- [ ] **Step 7: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 8: Prove the guards with eight probes, then record their verdicts by a message-only amend**

The refusal is the guard the brief names; the redaction, the verdict's composition, the non-empty refusal and the version floor are the probe's other guards, each a line whose removal would let the probe print a password or report a pass it did not earn. Four controls: the refusal's `refusing: ` prefix, which the two refusal cases assert; the redaction marker, which the three redaction cases assert; the `PASS` line, which the composition case asserts; and for the floor, the floor itself raised one patch, which its `6.2.0` case catches. Each was run against a scratch copy of the tree while this plan was written, each `KILLED`, `control proven`.

```bash
T=tests/test_valkey_compat_probe.py
F=infra/scripts/valkey-compat-probe.py
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print(f"refusing: {exc}")/print(f"refused: {exc}")/' \
  --mutation 's/if flag in PASSWORD_FLAGS or (flag.startswith("--pass") and flag != "--password-env"):/if False:/' \
  -- uv run pytest "$T::test_the_parser_refuses_a_password_argument_without_echoing_it" "$T::test_a_rejected_argument_is_not_echoed" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print(f"refusing: {exc}")/print(f"refused: {exc}")/' \
  --mutation 's/message = _QUOTED.sub(_ELIDED, message)/pass/' \
  -- uv run pytest "$T::test_the_parser_refuses_a_password_argument_without_echoing_it" "$T::test_a_rejected_argument_is_not_echoed" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print(f"refusing: {exc}")/print(f"refused: {exc}")/' \
  --mutation 's/message = "unrecognized arguments"$/pass/' \
  -- uv run pytest "$T::test_the_parser_refuses_a_password_argument_without_echoing_it" "$T::test_a_rejected_argument_is_not_echoed" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/REDACTED = "<redacted>"/REDACTED = "<hidden>"/' \
  --mutation 's/return text.replace(password, REDACTED)/return text/' \
  -- uv run pytest "$T::test_a_half_runs_in_a_child_and_its_output_is_redacted" "$T::test_a_half_that_raises_reports_its_error_redacted" "$T::test_a_server_that_refuses_the_login_fails_the_probe_without_the_password" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print("PASS" if code == 0 else "FAIL")/print("OK" if code == 0 else "FAIL")/' \
  --mutation 's/and restored == written else 1/and restored is not None else 1/' \
  -- uv run pytest "$T::test_the_verdict_needs_both_halves" "$T::test_main_composes_the_exit_from_both_halves" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print("PASS" if code == 0 else "FAIL")/print("OK" if code == 0 else "FAIL")/' \
  --mutation 's/written is not None and len(written) == 1 and restored == written/restored == written/' \
  -- uv run pytest "$T::test_the_verdict_needs_both_halves" "$T::test_main_composes_the_exit_from_both_halves" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/print("PASS" if code == 0 else "FAIL")/print("OK" if code == 0 else "FAIL")/' \
  --mutation 's/^    if reading.dbsize:$/    if False:/' \
  -- uv run pytest "$T::test_the_verdict_needs_both_halves" "$T::test_main_composes_the_exit_from_both_halves" -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file "$F" \
  --control 's/LIBRARY_FLOOR = (6, 2, 0)/LIBRARY_FLOOR = (6, 2, 1)/' \
  --mutation 's/return found is not None and found >= LIBRARY_FLOOR/return found is not None/' \
  -- uv run pytest "$T::test_the_server_passes_at_the_librarys_version_floor" -q -p no:cacheprovider
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend` with the whole message re-supplied and nothing staged, with:

```
Probe: `infra/scripts/mutate-probe.sh` over `infra/scripts/valkey-compat-probe.py`. Control the
refusal's `refusing: ` prefix changed, through the password-argument and rejected-argument cases:
the password-flag refusal removed, KILLED, control proven; the quoted-word elision removed, KILLED,
control proven; the unrecognized-arguments elision removed, KILLED, control proven. Control the
redaction marker renamed, through the three redaction cases: `redact` returning the text whole,
KILLED, control proven. Control the PASS line renamed, through the verdict and composition cases:
the restore compared as merely present, KILLED, control proven; the one-order and written-present
arms removed, KILLED, control proven; the non-empty-database refusal removed, KILLED, control
proven. Control the version floor raised to 6.2.1, through the floor case: the floor comparison
removed, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

**Operator steps (attended):** the probe is run at `## Rollout (attended)` step R4, on `zcrypto-valkey1`, after the mesh and before the cache role converges there; no executor step runs it.

---

### Task 7: The guidance names the cache nodes: the Alloy bump's host map, the daily pass's telemetry hosts and the Valkey re-pin order

*Ruling: the owner's of 2026-09-25 made the three guidance edits the Resolution had left to a branch of their own this task, the plan's last, after Task 6.*

Tasks 1, 4 and 5 make each cache node an Alloy host, a telemetry host of the daily pass and a digest-pinned Valkey, and the three skills a fleet operation runs from name none of that: `.claude/skills/zcrypto-bump-alloy/SKILL.md` maps four Alloy hosts, `.claude/skills/zcrypto-daily-ops/SKILL.md` grants telemetry-only actions on ops, the NAS and zaccess, and `.claude/skills/zcrypto-rollout-image/SKILL.md` carries no Valkey re-pin. This task writes the nodes into those three files and edits nothing else, so its one commit is `claude(guidance): …`, which the `staged-kind` hook keeps apart from every other kind of file. The edits land on this branch on the owner's word, where `.claude/skills/zcrypto-refine-rules/SKILL.md` sends a guidance change to a branch of its own: the three skills govern fleet operations, and no executor step of this plan performs one (`## Global Constraints`). No skill's `name:` or `description:` line changes, and those two lines are all of a skill `infra/scripts/guidance-guard.py` counts as always-loaded, so the ambient set does not grow and the commit carries no `Ambient grows by` line, which the guard refuses on a commit that does not grow the set. The drafted text adds no universal word (every, never, always, only, any, cannot) to the three files: the daily pass's paragraph, rewritten, keeps the three it has and carries a `(no count command: …)` clause, and Steps 1 and 5 count the words in each file. Decisions this task takes:

- **The cache nodes come third in the Alloy canary order**, after the NAS and before the capture hosts, one node per converge, since `converge.sh` refuses `cache_host` (Task 1): their set holds nothing unbackfillable (spec D14), so they go before the capture pair, whose primary stays last. Their leg passes `cache_alloy_digest` alone, so Task 4's `cache_image_digest` gate skips the Valkey and Sentinel block, and it reads both daemons' `RestartCount` and `StartedAt` before and after the converge.
- **The Valkey re-pin order is a new section of the rollout skill, `## Cache converges (…)`, appended after its NAS converges section.** The skill's canary phases are the capture image's (its opening paragraph: "The canary phases are for capture-image digest re-pins; the sections after Phase 5 carry every other image converge on the fleet"), and a Valkey re-pin owes no bake and has no capture secondary, so it takes the shape of the per-tier sections after Phase 5, the engine's, the ops host's and the NAS's. `.claude/rules/fleet-deploys.md` reaches it through that opening: the rule sends converges and re-pins to this skill, and the skill sends each image converge outside the canary to those sections. The rule's parenthetical, which names app-image and Alloy digests, and the skill's `description:` line are left as they are: both are always-loaded, and growing that set is the owner's word.
- **A re-pin passes the node's running Alloy digest beside the new Valkey one.** Without `cache_alloy_digest`, Task 5's `assert the deployed alloy config matches the repo` runs, and on a tree whose `config.alloy` has moved it fails the play after the compose render has notified `restart cache service`; Ansible runs no pending handler on a host that failed, and neither `infra/ansible/ansible.cfg` nor `infra/ansible/site.yml` sets `force_handlers`, so the node would keep the old image under a compose file naming the new one, which a converge with the same digest renders unchanged and so never restarts.
- **The daily pass names the nodes by their `host` labels**, `zcrypto-valkey1`, `zcrypto-valkey2` and `zcrypto-valkey3`, the spelling Task 1's `_TELEMETRY_HOSTS` holds.
- **Every count the host map moves is re-counted in the same edit:** seven digest-pinned Alloys; six of them with no repo pin (the NAS's is the one in the repo); five `config.alloy` files to dry-start; zaccess's apt-installed Alloy the eighth; six recreates besides ops's that trip no ERROR rule, since `zcrypto-ops-error-logs` is the one ERROR rule in `infra/grafana/alerts.yaml` whose selector names the `alloy` container (`zcrypto-engine-error-logs`, `zcrypto-nas-archive-pull-errors` and `zcrypto-capture-error-logs` name the engine, `archive-pull` and `capture`) and Task 5 adds none; and the host set of `zcrypto-fleet-daemon-restarted`, `zcrypto`, `zcrypto-red`, `ops` and `nas`, which no cache node joins and this plan leaves as it is.

**Files:**
- Modify: `.claude/skills/zcrypto-bump-alloy/SKILL.md` (line 11, the paragraph under `## What this is`; line 22, the host map's heading; three rows after line 27, the NAS row; line 33; Step 0's items 1 and 3, lines 37 and 39; Step 1's second bullet, line 44; Step 2's heading and first paragraph, lines 46 and 48; a leg inserted before line 78, `### capture secondary, then primary`; a bullet after line 125, Step 3's capture-hosts addition; the paragraphs at lines 127 and 129)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (line 46, the paragraph that begins `**Autonomous** —`)
- Modify: `.claude/skills/zcrypto-rollout-image/SKILL.md` (a section appended after line 143, the file's last, which closes its NAS converges section)
- Test: none added or changed; `tests/test_guidance_refs_resolve.py` and `tests/test_internal_terms_not_operator_visible.py` are the guards over these files

**Interfaces:**
- Consumes: Task 1's aliases `db1` to `db3`, `converge.sh`'s refusal of `cache_host` and its `cache` tag and `cache_image_digest` and `cache_alloy_digest` keys, and `_TELEMETRY_HOSTS` holding the three nodes; Task 4's gate on `cache_image_digest`, `zcrypto-cache.service` and its `restart cache service` handler, and the containers `zcrypto-valkey` and `zcrypto-sentinel`; Task 5's Alloy project `/opt/zcrypto-cache/alloy`, which the role renders and never starts, `cache_alloy_digest` with no default, `infra/ansible/roles/cache/files/config.alloy`, `CACHE_REQUIRED`, `redis_up` under `job="valkey"` and `job="sentinel"`, `assert the deployed alloy config matches the repo`, and `infra/runbooks/cache.md` with its `vk` and `sn` and the procedures `cache-manual-failover`, `cache-rejoin-node` and `cache-config-reset`.
- Produces: nothing a later task reads.

- [ ] **Step 1: The baseline**

Read `## Before you write guidance` in `.claude/skills/zcrypto-refine-rules/SKILL.md` first: an edit to a skill file is its trigger. Then, from the worktree root:

```bash
uv run pytest tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
uv run pytest tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
for f in .claude/skills/zcrypto-bump-alloy/SKILL.md .claude/skills/zcrypto-daily-ops/SKILL.md .claude/skills/zcrypto-rollout-image/SKILL.md; do
  uv run python -c 'import re, sys; print(sys.argv[1], len(re.findall(r"\b(every|never|always|only|any|cannot)\b", open(sys.argv[1]).read(), re.I)))' "$f"
done
uv run python infra/scripts/guidance-guard.py --uncounted .claude/skills/zcrypto-bump-alloy/SKILL.md .claude/skills/zcrypto-daily-ops/SKILL.md .claude/skills/zcrypto-rollout-image/SKILL.md | wc -l
uv run python infra/scripts/guidance-guard.py --ambient-bytes
```

Expected: `10 passed`; no failure, and a passed count Step 5 repeats, `680 passed` on this branch before Task 1 when this plan was written, higher by the time this step runs, since the module parametrises over the scripts, shell files, Ansible task names, unit descriptions and runbook pages Tasks 1 to 6 create; the universal-word counts `38`, `45` and `114`, read with the guard's own word list and regex; `47`, the three files' bullets the guard's instrument reads as uncounted today, which this task leaves as they are; and the ambient byte count Step 5 repeats, `20205` when this plan was written. A figure other than these means a skill changed after this plan was written: Step 5 then compares against what this step printed.

- [ ] **Step 2: The Alloy bump skill maps, orders and verifies the cache nodes**

`.claude/skills/zcrypto-bump-alloy/SKILL.md` — in the paragraph under `## What this is`, replace `Four hosts run digest-pinned` with `Seven hosts run digest-pinned`, and after its sentence ending `(unavoidable — the role restarts it on every apply).` insert, one space first:

```markdown
On the cache nodes Alloy is its own compose project as well, apart from Valkey's and Sentinel's, so a bump restarts neither.
```

Replace the heading `## The four hosts — three naming schemes, one map` with `## The seven hosts — three naming schemes, one map`, and after the host map's NAS row insert:

```markdown
| cache node 1 | `db1` | `zcrypto-valkey1` | `zcrypto-valkey1` |
| cache node 2 | `db2` | `zcrypto-valkey2` | `zcrypto-valkey2` |
| cache node 3 | `db3` | `zcrypto-valkey3` | `zcrypto-valkey3` |
```

Replace `A fifth Alloy` with `An eighth Alloy`.

In Step 0's item 1, replace

```markdown
each of the four `config.alloy` files (NAS `infra/nas/`, ops `roles/ops/files/`, capture `roles/capture/files/`, access `roles/access/files/`)
```

with

```markdown
each of the five `config.alloy` files (NAS `infra/nas/`, ops `roles/ops/files/`, capture `roles/capture/files/`, access `roles/access/files/`, cache `roles/cache/files/`)
```

In item 3, replace `for 3 of 4 (per-converge extra-vars, no repo default)` with `for 6 of 7 (per-converge extra-vars, no repo default)`, and

```markdown
on `hp`, `nas`, `red`, `zcrypto` — into
```

with

```markdown
on `hp`, `nas`, `red`, `zcrypto`, `db1`, `db2`, `db3` — into
```

In Step 1, replace

```markdown
- **ops + capture**: deliberately no repo default (`ops_alloy_digest` / `capture_alloy_digest` are per-converge extra-vars;
```

with

```markdown
- **ops + capture + cache**: deliberately no repo default (`ops_alloy_digest` / `capture_alloy_digest` / `cache_alloy_digest` are per-converge extra-vars;
```

Replace the heading `## Step 2 — canary order: ops → NAS → capture secondary → capture primary` with `## Step 2 — canary order: ops → NAS → cache nodes → capture secondary → capture primary`, and in the paragraph under it replace

```markdown
verify the pull loop, not just Alloy), then the capture hosts
```

with

```markdown
verify the pull loop, not just Alloy), the cache nodes third (their set holds nothing unbackfillable), one node per converge, as `converge.sh` refuses their group, then the capture hosts
```

Before the heading `### capture secondary, then primary`, insert this leg, the blank line after it included:

````markdown
### cache nodes, `db1` then `db2` then `db3`

`cache_alloy_digest` alone: without `cache_image_digest` the cache role skips its Valkey and Sentinel block, so the bump leaves both daemons as they run, and the two reads around the converge show it.

```bash
ssh db1 "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"
./scripts/converge.sh site.yml --limit zcrypto-valkey1 --tags cache -e 'cache_alloy_digest=sha256:<new>' --check   # the preview; it changes nothing
./scripts/converge.sh site.yml --limit zcrypto-valkey1 --tags cache -e 'cache_alloy_digest=sha256:<new>'
ssh db1 'cd /opt/zcrypto-cache/alloy && sudo docker compose up -d'   # the role renders it and does not start it
ssh db1 "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"   # the same two lines
```

Then `db2` (`zcrypto-valkey2`) and `db3` (`zcrypto-valkey3`) the same way, in that order.
````

The placeholders are quoted, `'cache_alloy_digest=sha256:<new>'`, so the block parses as shell; `converge.sh` receives the same word unquoted.

In Step 3's host-specific additions, after the bullet that begins `- **capture hosts**:`, insert:

```markdown
- **cache nodes**: the node's series list is `CACHE_REQUIRED`; `redis_up{host="<host>"}` reads 1 on two series, `job="valkey"` and `job="sentinel"`; the leg's two `docker inspect` reads print the same lines, proving the bump did not touch Valkey or Sentinel.
```

At the end of the paragraph about `zcrypto-fleet-daemon-restarted`, after `so the instance stays firing rather than firing a second time.`, insert, one space first:

```markdown
The rule selects `zcrypto`, `zcrypto-red`, `ops` and `nas`, so a cache node's recreate pages nothing.
```

In the paragraph after it, replace `the other three recreates trip nothing` with `the other six recreates trip nothing`.

- [ ] **Step 3: The daily pass names the cache nodes among its telemetry hosts**

`.claude/skills/zcrypto-daily-ops/SKILL.md` — replace the paragraph

```markdown
**Autonomous** — everything read-only, wherever it runs; telemetry-only actions on **ops, the NAS or zaccess only** (restart Alloy, re-arm a timer); and a code fix taken the normal way — fix branch, tests, subagent review, PR, merged on CI green — **when the fix is off the protected paths**.
```

with

```markdown
**Autonomous** — everything read-only, wherever it runs; telemetry-only actions on **ops, the NAS, zaccess or a cache node (`zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`) only** (restart Alloy, re-arm a timer); and a code fix taken the normal way — fix branch, tests, subagent review, PR, merged on CI green — **when the fix is off the protected paths** (no count command: the classifier decides each step, `_TELEMETRY_HOSTS` in `infra/scripts/ops_daily.py` its telemetry set, and the journal records the actions taken in prose that no count reads).
```

- [ ] **Step 4: The rollout skill carries the Valkey re-pin order**

`.claude/skills/zcrypto-rollout-image/SKILL.md` — after its last line, the bullet that begins `- **Every NAS converge that RECREATES the archive-pull container`, append, one blank line first:

```markdown
## Cache converges (`zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`)

Valkey and its Sentinel on the three cache nodes, one `valkey/valkey` digest for both containers, passed per converge as `-e cache_image_digest=sha256:<...>`; outside the canary regime (no bake owed): two copies stay up while one node restarts, and the set holds nothing unbackfillable. A re-pin changes the node's compose file, whose handler restarts `zcrypto-cache.service`, Valkey and Sentinel together, and leaves `valkey.conf` and `sentinel.conf` as the daemons wrote them: a template change is `infra/runbooks/cache.md`'s `cache-config-reset`, not a re-pin. The reads below are that runbook's `vk` and `sn`, which take the passwords from the cache role's root-owned 0600 env files.

- **One node per converge, the replicas first.** Read the primary on one node, `sn SENTINEL get-master-addr-by-name zcache`, then re-pin each replica: `converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_image_digest=sha256:<new> -e cache_alloy_digest=sha256:<running>`, the second the node's running Alloy digest, read from its `grafana-alloy` container: without it, a repo whose `config.alloy` has moved fails the converge at the Alloy drift assert, after the new compose file is written and before its restart handler runs.
- **Each node's replication link up before the next**: on the node just converged, `vk INFO replication` reads `role:slave` and `master_link_status:up`, and on the primary its `slaveK:` line reads `state=online` with `lag=0` or `lag=1`, the reads of `cache-rejoin-node`'s step 3 — seconds after the converge, not a bake.
- **Then a deliberate `SENTINEL failover zcache`, by `cache-manual-failover`**, so the engine's one reconnect, once the engine is wired to the set, lands when you choose rather than on the Sentinels' detection timer — inside an engine inter-cycle gap by preference, not as a gate — and **the old primary last**, a replica by then, re-pinned and read the same way.
```

- [ ] **Step 5: The guards, the counts and the consumers, again**

Run Step 1's block again, then the changed files' consumers and the diff's size:

```bash
grep -rlE 'zcrypto-bump-alloy|zcrypto-daily-ops|zcrypto-rollout-image' tests/
uv run pytest tests/test_archive_reconcile_command.py tests/test_open_topics_frontmatter.py tests/test_prune_host_images.py -q -p no:cacheprovider
git diff --stat
```

Expected: Step 1's block prints `10 passed`, the passed count Step 1 printed with none failed, `38`, `45` and `114`, `47`, and the byte count Step 1 printed, each as before the edits: the new text adds no universal word, the daily pass's paragraph keeps the three it had, and no `name:` or `description:` line moved. The grep lists four modules, `tests/test_archive_reconcile_command.py`, `tests/test_internal_terms_not_operator_visible.py`, `tests/test_open_topics_frontmatter.py` and `tests/test_prune_host_images.py`, each citing a skill in a comment or docstring and reading none of them; `tests/test_guidance_refs_resolve.py` reads every tracked file under `.claude/` and names no skill, so the grep does not list it. The three modules run with no failure. `git diff --stat` ends `3 files changed, 37 insertions(+), 11 deletions(-)`. Each figure was read while this plan was written on a scratch clone of this branch with Steps 2 to 4 applied, and matched the unedited branch: `10 passed`, `680 passed`, `38`, `45`, `114`, `47`, `20205`, the three modules `1167 passed` both ways, and that diff size.

- [ ] **Step 6: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote. The commit-msg hooks `guidance-guard` and `message-citations`, and `staged-kind`, run at Step 7; on the scratch clone the three edited files and Step 7's message passed all three.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/zcrypto-bump-alloy/SKILL.md .claude/skills/zcrypto-daily-ops/SKILL.md .claude/skills/zcrypto-rollout-image/SKILL.md
git commit -F- <<'MSG'
claude(guidance): the Alloy bump, the daily pass and the rollout skill name the three cache nodes

The Alloy bump's host map gains `db1` to `db3`, and its canary order the cache nodes after the NAS,
one node per converge: `--tags cache` with `cache_alloy_digest` alone, which skips the cache role's
Valkey and Sentinel block, then `docker compose up -d` in `/opt/zcrypto-cache/alloy`, the two
daemons' start markers read the same before and after. Its counts follow the map: seven
digest-pinned hosts, six with no repo pin, five `config.alloy` files to dry-start, zaccess's Alloy
the eighth, six recreates past the ops one that trip no ERROR rule; `CACHE_REQUIRED` is the nodes'
series list, and the daemon-restarted rule selects no cache node.

The daily pass's autonomy line names the three nodes among the telemetry-only hosts, as the
classifier's `_TELEMETRY_HOSTS` holds them, with a `(no count command: ...)` clause.

The rollout skill gains `Cache converges`: one node per converge, the replicas first, each with the
node's running Alloy digest beside the new Valkey one, each node's replication link up before the
next, then a deliberate `SENTINEL failover zcache` and the old primary last, through the cache
runbook's `cache-manual-failover` and `cache-rejoin-node`.

No skill's name or description line changes, so the always-loaded set does not grow, and the three
files carry as many universal words as before.

Run: tests/test_guidance_refs_resolve.py and tests/test_internal_terms_not_operator_visible.py,
each with the passed count Step 1 read.

Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HrTEbjo2WydKL5eVoteiSC
MSG
```

`<model>` is written by the executor as its own model name (`Claude Opus 5.5`, `Claude Fable 5.1`, ...), never copied from this plan. The message carries no `Ambient grows by` line, which the guard refuses on a commit that does not grow the always-loaded set, and no probe verdict: the commit changes no guard (a test, an assertion, a hook, an alert rule, a checker), and the two guards run over it as they are.

- [ ] **Step 8: The tree is clean and the range reads clean**

Run: `git status --porcelain` — Expected: empty. Run: `uv run python infra/scripts/guidance-guard.py --range HEAD~1..HEAD`, the form `merge-pr`'s gate runs over the branch — Expected: `guidance-guard: every commit of HEAD~1..HEAD states its ambient growth` (read on the scratch clone's commit of these edits).

**Operator steps (attended):** none. The three skills describe running hosts from `## Rollout (attended)` step R5 on, where the nodes' Valkey, Sentinel and Alloy start.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches a host, the Linode Cloud Manager, Docker Hub, GitHub, Kraken's status feed or Grafana Cloud, or writes a secret. Phase P runs on this branch before its pull request opens, so the code, its secrets and a checked exporter line merge together; phase R runs from merged `develop`. `W$` is the workstation at the repository root, `H$` a shell on the named host, reached as `ssh zcrypto` or by Task 1's aliases `ssh db1`, `ssh db2`, `ssh db3`. Every converge goes through `infra/ansible/scripts/converge.sh`, which previews, asks for the typed `--limit` and appends its line to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`. A port is opened in two layers, each by its own hand: the nftables rules the firewall role renders from the vars Tasks 1 and 2 commit, and the Linode Cloud Firewall, edited in the Cloud Manager. No secret is typed on a command line: the probe's password is minted on the host into a root-only file, every Valkey and Sentinel read takes its password from the cache role's root-only env files through `docker exec --env-file`, and the Grafana token reaches `curl` on stdin.

**P1. The three deploy keypairs** (Task 1 operator step O0), run by the owner before Task 1's Step 1; Task 1's Step 11 commits the six files.

**P2. The four WireGuard keypairs** (Task 3 operator step O1), committed on the branch after Task 3's commit.

**P3. The five cache passwords** (Task 4 operator step O1), committed on the branch.

**P4. The exporter's ACL line against its README** (Task 4 operator step O2), before any converge; a difference beyond the three tokens O2 names goes to the owner.

Then the pull request opens through the `open-pr` skill, a different agent reads the branch, and `merge-pr` merges it. Everything below runs from merged `develop`.

**R0. The operands, read once.**

```
W$ git switch develop && git pull --ff-only && git status --porcelain
W$ CAP=.tmp/cache-rollout && mkdir -p "$CAP"
W$ VK=$(curl -fsSL https://hub.docker.com/v2/repositories/valkey/valkey/tags/9.1.2 | python3 -c 'import json, sys; print(json.load(sys.stdin)["digest"])') && echo "$VK"
W$ curl -fsSL https://hub.docker.com/v2/repositories/valkey/valkey/tags/9 | python3 -c 'import json, sys; print(json.load(sys.stdin)["digest"])'
W$ AL=$(grep -F -- '- `b8ec653c4423` = ' docs/reference/fleet-pins.md | grep -oE 'sha256:[0-9a-f]{64}') && echo "$AL"
W$ NT=$(grep -oE 'nautilus-trader===[^"]+' pyproject.toml | cut -d= -f4) && echo "$NT"
W$ E12=$(awk -F'|' '$2 == " engine " && $3 == " zcrypto " {print $4}' docs/reference/fleet-pins.md | grep -oE '[0-9a-f]{12}' | head -1)
W$ APP=$(grep -F -- "- \`$E12\` = " docs/reference/fleet-pins.md | grep -oE 'sha256:[0-9a-f]{64}') && echo "$E12 $APP"
```

`git status --porcelain` prints nothing (a dirty tree is recorded as `dirty` on every deploy-log line). `VK` is the 9.1.2 index digest, the one `cache_image_digest` carries at every cache converge, and the `9` tag's digest printed under it is the same one: the floating `9` still resolves to 9.1.2, as the spec measured; two different digests mean 9.x has moved past 9.1.2, and the owner says which to pin before anything converges. `AL` is the fleet's Alloy v1.19.2, the one `cache_alloy_digest` carries. `NT` is `pyproject.toml`'s `nautilus-trader` pin, `2.0.0rc6.dev20260921`, and `APP` is the engine row's app image: after the 2026-09-24 engine rollout that row reads `3f291f3cee57`, the dev20260921 image carrying `NT`. The probe refuses an image whose `nautilus-trader` is not `NT` (R4), which stops the rollout and goes to the owner.

**R1. The nodes' Cloud Firewall, by hand** (Task 1 operator step O1): the `zcrypto-cache` firewall on the three nodes, TCP `22` and `10022` and ICMP, and its port probe reading `22 open` and `10022 closed` on each node.

**R2. Bootstrap and the base converge, one node at a time** (Task 1). In R2, R3 and R5 `N` is written in by hand, `1`, then `2`, then `3`, each node's reads clean before the next. Before the first node's bootstrap, Task 1 operator step O2 reads each node's host key in its LISH console; after it and before the first `ssh db1`, steps O3 and O4 write the workstation's key copies and the three `~/.ssh/config` stanzas. For each node, with the owner's master key in the agent (`W$ ssh-add -l` lists it), the GPG agent unlocked (the inventory's vaults are read through `vault-pass.sh`), and not through `run.sh`, whose throwaway agent excludes the master key:

```
W$ (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-valkeyN -e ansible_user=root -e ansible_port=22)
W$ ssh dbN 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkeyN --tags base,hardening,firewall,fail2ban,chrony,docker -e daemon_json_ack=true
W$ ssh dbN hostname
W$ ssh dbN 'sudo nft list ruleset | grep -E "10022|51821|6379|26379"'
W$ ssh dbN sudo docker version --format '{{.Server.Version}}'
```

The bootstrap's recap reads `failed=0 unreachable=0`, its primary refusal `skipping` (no cache node is in `engine_host`) and its re-bootstrap probe finding no `zcrypto-deploy`; the re-bootstrap refusal firing means the node was provisioned before: stop and read it, never pass `-e rebootstrap=true` on a node this plan has not first rebuilt. The first `ssh dbN` prints the fingerprint O2 read, then the provider-assigned hostname and `sudo-ok`. The converge's preview prints the docker role's `daemon.json` diff against a file the node does not have yet, the change `-e daemon_json_ack=true` acknowledges; no container runs on the node to restart. After the converge, `hostname` prints `zcrypto-valkeyN`; the ruleset accepts `10022` and `51821` on the public side and `6379`, `26379` only under `iifname "zcache0"`; the Docker server answers. The tag list keeps the `cache_link` and `cache` roles off the node, so R4 runs the probe on a node with Docker and no Valkey of the role's. Once all three nodes are converged, Task 1 O1's port probe reads `22 closed` and `10022 open` on each (the hardening role removed the bootstrap drop-in); then remove the TCP `22` rule from `zcrypto-cache` in the Cloud Manager and re-run the probe: the same reading, and `W$ for a in db1 db2 db3; do ssh "$a" hostname; done` prints the three names.

**R3. The mesh: the nodes, then the engine host** (Task 3). First Task 3 operator step O2, the Cloud Firewall's `51821/udp` rule on `zcrypto-cache` and, when a firewall is attached to `zcrypto`, on that one. Then for `N` in `1`, `2`, `3`:

```
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkeyN --tags firewall,cache-link
W$ ssh dbN sudo wg show zcache0
W$ ssh dbN sudo nft list chain inet filter input
```

`wg show` reports `listening port: 51821` and three `peer:` entries whose `allowed ips` are the other three members' `/32`, with no handshake yet from a member not yet converged; the chain carries a UDP accept for `51821` and the line `iifname "zcache0" tcp dport { 6379, 26379 } accept`. From valkey2 on, `ssh dbN sudo wg show zcache0 latest-handshakes` shows a non-zero epoch for each earlier node and `ssh dbN ping -c 3 -W 2 10.98.0.11` answers. The engine host is the live primary: `.claude/rules/fleet-deploys.md` holds for it. At planning time and again immediately before the converge, Kraken's maintenance feed, read whole:

```
W$ curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | python3 -c 'import json, re, sys; word = re.compile(r"\b(websocket|rest)\b", re.I); entries = json.load(sys.stdin)["scheduled_maintenances"]; print(len(entries), "entries read"); [print(m["status"], m["scheduled_for"], m["scheduled_until"], m["name"], sep=" | ") for m in entries if word.search(m["name"]) or any(word.search(c["name"]) for c in m["components"])]'
```

A printed window that covers the converge's time stops it; an empty feed is not evidence the window is clear, so the second read is taken regardless. Then the gap, from the boundary's own journal:

```
W$ ssh zcrypto 'B=$(( $(date -u +%s) / 14400 * 14400 )); f=/var/lib/zcrypto-engine/journal/$(date -u -d @$B +%F)/cycle-$(date -u -d @$B +%H).json; sudo python3 -c "import json, sys; print(sys.argv[1], json.load(open(sys.argv[1]))[\"completed_at\"])" "$f"; date -u +%FT%TZ'
```

The converge starts no earlier than five minutes past the printed `completed_at` and finishes at least ten minutes before the next 00/04/08/12/16/20 UTC boundary; a missing `cycle-<HH>.json` stops it, since the engine then has a problem of its own. Before and after, the restart markers the converge must leave unchanged:

```
W$ ssh zcrypto sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags firewall,cache-link -e converge_primary=true
W$ ssh zcrypto sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine
W$ ssh zcrypto sudo wg show zcache0 latest-handshakes
W$ ssh zcrypto 'for ip in 10.98.0.11 10.98.0.12 10.98.0.13; do ping -c 3 -W 2 $ip | tail -1; done'
```

The two marker reads print the same lines, since neither tag restarts a container; the capture play's `refuse to converge the live primary unless explicitly asked` passes on the flag, and the engine window guard does not run (its tasks carry the `engine` tag). `latest-handshakes` shows three peers with a non-zero epoch; each ping reports `0% packet loss`, valkey3 near 8 ms and the others under 1 ms. The next boundary's `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`. Then the mesh on all four members:

```
H$ (ssh zcrypto, ssh db1, ssh db2, ssh db3) sudo wg show zcache0
H$ (each) cat /var/lib/zcrypto-node-textfile/zcache.prom
```

On each member three peers, each `latest handshake` under three minutes and `transfer` non-zero both ways; `zcache.prom` carries three `zcache_wireguard_handshake_age_seconds{peer="10.98.0.<n>"}` samples, one per other member's mesh address, each finite and under 180, none `+Inf`.

**R4. The compatibility probe on `zcrypto-valkey1`, before the cache role** (Task 6). A throwaway Valkey at the 9.1.2 digest, a plain `docker run --rm -d --network host` on the node's loopback port `6390`, no config file, one ACL user `engine` holding the grant Task 4's `users.acl.j2` renders for it and a password minted on the host; the script on stdin inside the app image. The ACL file holds the password's SHA-256 alone; the env file holding the password is root's, mode `0600`.

```
W$ ssh db1 sudo bash -s <<'EOF'
set -euo pipefail
umask 077
install -d -m 0700 /root/valkey-probe
install -d -m 0755 /root/valkey-probe/acl
pw=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')
printf 'VALKEY_PROBE_PASSWORD=%s\n' "$pw" > /root/valkey-probe/probe.env
hash=$(printf %s "$pw" | sha256sum | cut -d' ' -f1)
printf 'user default off\nuser engine on #%s ~* &* +@all -@dangerous +keys +info\n' "$hash" > /root/valkey-probe/acl/users.acl
chmod 0644 /root/valkey-probe/acl/users.acl
EOF
W$ ssh db1 sudo docker pull "valkey/valkey@$VK"
W$ ssh db1 sudo docker run --rm --entrypoint valkey-server "valkey/valkey@$VK" --version
W$ ssh db1 sudo docker run --rm -d --name valkey-probe --network host --memory 256m -v /root/valkey-probe/acl:/probe:ro "valkey/valkey@$VK" valkey-server --bind 127.0.0.1 --port 6390 --aclfile /probe/users.acl --save '""' --appendonly no
W$ ssh db1 sudo docker logs valkey-probe 2>&1 | grep -F 'Ready to accept connections'
W$ ssh db1 sudo docker pull "ghcr.io/zhaow-de/zcrypto-capture@$APP"
W$ ssh db1 sudo docker run --rm -i --network host --memory 512m --env-file /root/valkey-probe/probe.env --entrypoint python "ghcr.io/zhaow-de/zcrypto-capture@$APP" - --host 127.0.0.1 --port 6390 --username engine --password-env VALKEY_PROBE_PASSWORD --expect-nautilus "$NT" < infra/scripts/valkey-compat-probe.py > "$CAP/r4-valkey-compat-probe.txt"; echo "rc=$?"
W$ grep -v '⠀' "$CAP/r4-valkey-compat-probe.txt"
W$ ssh db1 sudo docker stop valkey-probe
W$ ssh db1 sudo rm -rf /root/valkey-probe
```

The `--version` read prints `v=9.1.2`. The probe passes when `rc=0` and the capture reads, in order: `nautilus-trader` followed by `NT`; a `redis_version:` line at or above 6.2.0 (Valkey reports its Redis-compatibility version there); `valkey_version: 9.1.2`; `server: PASS`; the library's own `Connected to redis v...` line in the first child's output; `write: ['O-...']` and `restore:` the same one id; `PASS`. Any other outcome stops the rollout here: no cache role lands, the capture goes to the owner, and the finding is the spec's library-side unknown answered in the negative; `rc=2` with `this interpreter carries nautilus-trader ...` is R0's image read, which goes to the owner the same way. `docker stop` removes the throwaway container (`--rm`), and the app image stays on the node until R9's prune.

**R5. Valkey, Sentinel and Alloy: valkey1, then valkey2, then valkey3** (Tasks 4 and 5). One converge per node carries both digests, `--tags cache -e cache_image_digest=$VK -e cache_alloy_digest=$AL`, each image pre-staged first; the role renders Alloy's project and never starts it, so the operator starts it. For each `N`:

```
W$ ssh dbN sudo wg show zcache0 latest-handshakes
W$ ssh dbN sudo docker pull "valkey/valkey@$VK"
W$ ssh dbN sudo docker pull "grafana/alloy@$AL"
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkeyN --tags cache -e cache_image_digest=$VK -e cache_alloy_digest=$AL
W$ ssh dbN 'cd /opt/zcrypto-cache/alloy && sudo docker compose run --rm --no-deps alloy fmt /etc/alloy/config.alloy > /dev/null && echo parses'
W$ ssh dbN 'cd /opt/zcrypto-cache/alloy && sudo docker compose up -d'
```

Three handshake epochs within the last three minutes before the converge; the preview's recap `failed=0`, the real pass's `failed=0 ignored=0`; `parses`. Then on the node:

```
H$ systemctl is-active zcrypto-cache.service
H$ sudo docker inspect --format '{{.Name}} {{.Config.Image}} {{.State.Status}} {{.RestartCount}}' zcrypto-valkey zcrypto-sentinel grafana-alloy
H$ sudo ss -ltnH '( sport = :6379 or sport = :26379 )'
H$ sudo docker exec --env-file /opt/zcrypto-cache/cli-exporter.env zcrypto-valkey valkey-cli --no-auth-warning --user exporter INFO replication | grep -E '^(role|connected_slaves|slave[0-9]|master_host|master_link_status|master_repl_offset|slave_repl_offset):'
H$ sudo docker exec --env-file /opt/zcrypto-cache/cli-exporter.env zcrypto-valkey valkey-cli --no-auth-warning --user exporter INFO server | grep -E '^(redis_version|valkey_version):'
H$ sudo docker exec --env-file /opt/zcrypto-cache/cli-sentinel.env zcrypto-sentinel valkey-cli --no-auth-warning -p 26379 SENTINEL get-master-addr-by-name zcache
H$ sudo docker exec --env-file /opt/zcrypto-cache/cli-sentinel.env zcrypto-sentinel valkey-cli --no-auth-warning -p 26379 SENTINEL ckquorum zcache
H$ sudo journalctl CONTAINER_NAME=zcrypto-sentinel -n 50 --no-pager | grep -F '+monitor'
```

After valkey1: `active`; `zcrypto-valkey` and `zcrypto-sentinel` at `valkey/valkey@<VK>` and `grafana-alloy` at `grafana/alloy@<AL>`, each `running 0`; four listeners, `127.0.0.1` and `10.98.0.11` on each of 6379 and 26379, and no other address; `role:master`, `connected_slaves:0`; the two `INFO server` lines, recorded verbatim for R9's message (the library's version check parses `redis_version`); Sentinel names `10.98.0.11` and `6379`; a `+monitor master zcache 10.98.0.11 6379 quorum 2` line. A container that restarts in a loop with an ACL error in `sudo journalctl CONTAINER_NAME=zcrypto-valkey -n 50 --no-pager` names the `users.acl` token Valkey 9.1.2 refuses: stop, fix the template on a branch, and re-converge the node with `-e cache_config_reset=true` beside R5's two digests and R6's `pins_override` operand once it merges, since the file is re-rendered only under a reset, and the role refuses a reset without `cache_image_digest`. After valkey2 and after valkey3: on the new node `role:slave`, `master_host:10.98.0.11`, `master_link_status:up`; on `db1` the same `INFO replication` read shows `connected_slaves` one higher, each `slaveK:` line `state=online` with `lag=0` or `lag=1`, and `master_repl_offset` equal to the new node's `slave_repl_offset` (the set is idle, so the two agree within seconds); `ckquorum` answers `OK 2 usable Sentinels. Quorum and failover authorization can be reached` after valkey2 and `OK 3 usable Sentinels. ...` on each node after valkey3. Then the public side, from the workstation:

```
W$ for h in zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3; do for p in 6379 26379; do timeout 5 bash -c "</dev/tcp/$h.zhaow.me/$p" 2>/dev/null && echo "$h:$p OPEN" || echo "$h:$p closed"; done; done
```

Six `closed` lines.

From here the three skills Task 7 edited describe running hosts: the Alloy bump skill's cache leg reaches a `grafana-alloy` on each node, the daily pass's telemetry tier covers the nodes, and the rollout skill's `Cache converges` order serves the next Valkey re-pin (Task 7).

**R6. One forced failover and its fail-back, no engine attached** (Task 4; spec D14, D15). On `db1`:

```
H$ sudo docker exec --env-file /opt/zcrypto-cache/cli-sentinel.env zcrypto-sentinel valkey-cli --no-auth-warning -p 26379 SENTINEL failover zcache
```

`OK`. Within fifteen seconds each node's `SENTINEL get-master-addr-by-name zcache` names `10.98.0.12` (valkey2's priority 100 beats valkey3's 250); on `db1` `INFO replication` reads `role:slave`, `master_host:10.98.0.12`, `master_link_status:up`, and `sudo grep -E '^replicaof' /var/lib/zcrypto-cache/conf/valkey.conf` names `10.98.0.12 6379`, the daemon's own rewrite. Then the render-if-absent proof on a live node, R5's converge again for `zcrypto-valkey1` with the same two digests plus `-e '{"pins_override": "first pins of the cache nodes, recorded by this rollout at R9"}'`, since the pins rows land at R9 and both pins refusals now see a running container: the real pass's recap reads `changed=0 failed=0 ignored=0`, the `grep` still names `10.98.0.12`, and R5's `docker inspect` still reads `RestartCount` 0. Two minutes after the first failover (twice `failover-timeout`), on `db2`, the same `SENTINEL failover zcache`: `OK`; within fifteen seconds all three Sentinels name `10.98.0.11` (valkey1's 100 beats valkey3's 250), `db1` reads `role:master` with `connected_slaves:2`, and `db2` and `db3` read `master_host:10.98.0.11`, `master_link_status:up`. The daemons have now rewritten `valkey.conf` and `sentinel.conf` on every node (spec D9); later converges leave them as they are.

**R7. Every metric name, label and job, read before anything is pushed** (Task 5). First the capture hosts' Alloy config: Task 5's commit B added `zcache_wireguard_handshake_age_seconds` to the keep regex of `infra/ansible/roles/capture/files/config.alloy`, which the capture role copies onto a host only on a converge carrying `capture_alloy_digest`, and until one does, that role's drift assert refuses each capture-tagged converge of either capture host that omits the digest. The shape is `.claude/skills/zcrypto-rollout-image/SKILL.md`'s for a `config.alloy` edit: `zcrypto-red` first, then `zcrypto` at least an hour later (`infra/scripts/count-list.sh capture-hosts-converged-within-an-hour` books a closer pair), each with the digests its containers run, read from the containers; the primary's run takes `-e converge_primary=true`, after Kraken's maintenance feed read whole at planning time and again immediately before, R3's command:

```
W$ ssh red sudo docker inspect --format '{{.Name}} {{.Config.Image}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture grafana-alloy
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red --tags capture -e capture_image_digest=sha256:<zcrypto-capture's> -e capture_alloy_digest=sha256:<grafana-alloy's>
W$ ssh red sudo docker inspect --format '{{.Name}} {{.Config.Image}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture grafana-alloy
W$ ssh zcrypto sudo docker inspect --format '{{.Name}} {{.Config.Image}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine grafana-alloy
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture -e converge_primary=true -e capture_image_digest=sha256:<zcrypto-capture's> -e capture_alloy_digest=sha256:<grafana-alloy's>
W$ ssh zcrypto sudo docker inspect --format '{{.Name}} {{.Config.Image}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-capture zcrypto-engine grafana-alloy
W$ uv run python infra/scripts/grafana-query.py 'zcache_wireguard_handshake_age_seconds{host="zcrypto"}'
```

Each preview's diff is the keep-regex line of `config.alloy`; any other diff stops the run until it is read. Each pair of marker reads prints the same lines: the digests are the running ones, so no compose file changes, and the config's `reload alloy` handler reloads Alloy in place. The last read, at the next scrape after the primary's converge, is three series, one per node's mesh address, each under 180; `(no series)` is a fail. Then the exporters' own output as Alloy serves it on loopback, against the list the tests hold, then what reached Grafana Cloud:

```
W$ uv run python -c 'import sys; sys.path.insert(0, "tests"); import test_infra_alloy_series as t; print("\n".join(sorted(t.CACHE_REDIS_SERIES)))'
H$ (db1) for c in valkey sentinel; do curl -fsS "http://127.0.0.1:12345/api/v0/component/prometheus.exporter.redis.$c/metrics" | grep -oE '^redis_[a-z_]+' | sort -u; done
H$ (db1) curl -fsS http://127.0.0.1:12345/api/v0/component/prometheus.exporter.redis.valkey/metrics | grep -E '^redis_(instance_info|connected_slave_offset_bytes)\{'
H$ (db1) curl -fsS http://127.0.0.1:12345/api/v0/component/prometheus.exporter.redis.sentinel/metrics | grep -E '^redis_sentinel_master_status\{'
H$ (db2) curl -fsS http://127.0.0.1:12345/api/v0/component/prometheus.exporter.redis.valkey/metrics | grep -E '^redis_master_link_up'
W$ uv run python infra/scripts/grafana-query.py 'count by (job) (up{host="zcrypto-valkey1"})'
W$ uv run python infra/scripts/grafana-query.py 'count by (__name__) ({host="zcrypto-valkey1", __name__=~"redis_.*|zcache_.*|node_reboot_required"})'
W$ uv run python infra/scripts/grafana-query.py 'count by (host) (zcache_wireguard_handshake_age_seconds)'
W$ uv run python infra/scripts/grafana-query.py 'count by (host) (up{host=~"zcrypto-valkey[123]"})' 'max by (host) (redis_up{host=~"zcrypto-valkey[123]"})'
W$ uv run python infra/scripts/grafana-query.py 'max_over_time(process_resident_memory_bytes{host=~"zcrypto-valkey[123]", job="integrations/self"}[1h]) / 268435456'
```

Every name of the first list appears in the node's output, the ones read from a replica on `db2`; `redis_instance_info` carries `role`, `redis_sentinel_master_status` carries `master_address`, `redis_connected_slave_offset_bytes` on the primary carries `slave_ip`, and `redis_master_link_up` reads 1 on `db2`. Cloud's first read names `integrations/unix`, `integrations/self`, `valkey` and `sentinel`, 1 each, which settles Task 5's job-label reading; the second lists the `CACHE_REDIS_SERIES` names `db1`'s role publishes plus `zcache_wireguard_handshake_age_seconds` and `node_reboot_required`; the third names `zcrypto` and the three nodes, 3 each; each node answers in the fourth, `redis_up` at 1; the fifth is three series, each under 0.8, each node's Alloy against its 256 MiB cap before R8 pushes the headroom leg that fires above 0.9: spec D7 set that cap without a reading of Alloy under this config, and the fleet's v1.19.2 Alloys read 141 to 291 MiB on their own configs. A node at or above 0.8 stops the rollout before R8, and the owner sets the cap, a change to D7's budget; the reading goes into R9's message. `(no series)` is a fail, never a zero. When a name, a label or a job differs, the tree is corrected before R8: on a branch cut from `develop`, `git grep -lw '<assumed>' -- infra/ansible/roles/cache/files/config.alloy tests/test_infra_alloy_series.py infra/grafana/cache-dashboard.json infra/grafana/alerts.yaml infra/runbooks/cache.md | xargs sed -i 's/\b<assumed>\b/<live>/g'` for each name, `<assumed>` the plan's spelling and `<live>` the endpoint's; a differing label edited in the board's `legendFormat` and `by (...)` and, for `role` or `master_address`, in the rules and the runbook; a family the exporter does not publish removed from the keep regex, `CACHE_REDIS_SERIES` and its panel together; Task 5's Step 6 and Step 17 test runs and `uv run pre-commit run -a`; one commit, `fix(cache): the <family> names what the exporter publishes, read on db1`, with the two trailers of `## Global Constraints`; the commit changes guards, so Task 5's Step 9 and Step 20 probe blocks run again over it, the tree clean, a sed whose target the correction renamed re-anchored on the new name (a no-op sed is refused, rc 6), and their verdicts go into its message by a message-only amend naming `infra/scripts/mutate-probe.sh`; then through `open-pr` and `merge-pr`; then R5's converge per node from `develop` with R6's `pins_override` operand, which copies the config and reloads Alloy, and R7's reads again.

**R8. The board and the rules, then each rule's first sample by value** (Task 5). From merged `develop`, which is what `grafana-push.sh` requires; the plan carries no rule over the proxy's series, so nothing here pages before the proxy exists.

```
W$ git switch develop && git pull --ff-only
W$ export GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))')"
W$ PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
W$ printf 'Authorization: Bearer %s\n' "$GRAFANA_SA_TOKEN" | curl -fsS -H @- "https://zcrypto2026.grafana.net/api/v1/provisioning/folder/bfrxdfoybx98gb/rule-groups/zcrypto-cache" | jq '{interval, rules: (.rules | length)}'
W$ python3 -c 'import json; d = json.load(open("infra/grafana/cache-dashboard.json")); walk = lambda ps: [x for p in ps for x in ([p] if p.get("type") != "row" else walk(p.get("panels", [])))]; [print(p["id"]) for p in walk(d["panels"])]' > "$CAP/r8-panel-ids.txt"
W$ while read -r id; do printf 'Authorization: Bearer %s\n' "$GRAFANA_SA_TOKEN" | curl -fsS -H @- -o "$CAP/r8-cache-panel-$id.png" "https://zcrypto2026.grafana.net/render/d-solo/zcrypto-cache/x?panelId=$id&width=1100&height=420&from=now-6h&to=now"; done < "$CAP/r8-panel-ids.txt"
```

The push names `cache-dashboard.json` among the dashboards, upserts the eight new uids and the changed `zcrypto-fleet-alloy-memory-headroom`, reads every rule's datasource back and reports no orphan; the group reads `interval` 60 and `rules` 8; every rendered panel but 401 shows data, no `NaN` and no `No data` (read each PNG). Panel 401 draws the engine's lines naming the cache, which the second plan's wiring writes, so `No data` there is its expected reading until then. Then each rule's own expression, read from Cloud the same minute:

```
W$ for n in 1 2 3; do uv run python infra/scripts/grafana-query.py "count(up{host=\"zcrypto-valkey$n\"}) or on() vector(0)"; done
W$ uv run python infra/scripts/grafana-query.py 'abs((count(count by (master_address) (redis_sentinel_master_status{job="sentinel"} == 1) >= 2) or on() vector(0)) - 1) and on() (count(up{job="sentinel"}) > 1)'
W$ uv run python infra/scripts/grafana-query.py 'redis_connected_slaves{job="valkey"} and on(host) redis_instance_info{job="valkey", role="master"}'
W$ uv run python infra/scripts/grafana-query.py 'redis_memory_used_bytes{job="valkey"} / redis_memory_max_bytes{job="valkey"}'
W$ uv run python infra/scripts/grafana-query.py 'min by (host) (redis_aof_enabled{job="valkey"} * redis_aof_last_write_status{job="valkey"} * redis_aof_last_bgrewrite_status{job="valkey"})'
W$ uv run python infra/scripts/grafana-query.py 'max by (host, peer) (zcache_wireguard_handshake_age_seconds{host=~"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3"}) + on(host) group_left() (time() - max by (host) (node_textfile_mtime_seconds{host=~"zcrypto|zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3", file=~".*/zcache.prom"}))'
W$ uv run python infra/scripts/grafana-query.py 'process_resident_memory_bytes{host=~"zcrypto-valkey1|zcrypto-valkey2|zcrypto-valkey3", job="integrations/self"} / 268435456'
W$ printf 'Authorization: Bearer %s\n' "$GRAFANA_SA_TOKEN" | curl -fsS -H @- "https://zcrypto2026.grafana.net/api/prometheus/grafana/api/v1/rules" | jq -r '.data.groups[] | select(.name == "zcrypto-cache") | .rules[] | "\(.name) \(.state) \(.health)"'
W$ for n in 1 2 3; do printf 'Authorization: Bearer %s\n' "$GRAFANA_SA_TOKEN" | curl -fsS -H @- -G "https://zcrypto2026.grafana.net/api/datasources/proxy/uid/grafanacloud-logs/loki/api/v1/query" --data-urlencode "query=sum by (container) (count_over_time({host=\"zcrypto-valkey$n\"}[1h]))" | jq -r --arg n "$n" '.data.result[] | "valkey\($n) \(.metric.container) \(.value[1])"'; done
W$ unset GRAFANA_SA_TOKEN
```

In order: 4 on each node (the host scrape's two targets and the two Redis exporters); 0; 2, one series, the primary's; three series, each under 0.7; 1 on each of three; twelve series, three per member, each under 180; three series, each under 0.9; eight lines, each `inactive ok`; each node names `alloy`, `valkey` and `sentinel` with a count of 1 or more, and `zcache-probe` only when the probe has failed. A series absent, a value on the firing side of its bar, or a rule reading `nodata` or `error` stops here: the rule's runbook section is the next step, and the finding is fixed before R9. The captures under `$CAP` are what R9's commit message quotes.

**R9. The records: one pull request** (the `open-pr` skill; a different agent reads it; `merge-pr` merges it). From `develop`, carrying the deploy-log lines the converges appended:

```
W$ git switch develop && git pull --ff-only && git switch -c chore/cache-fleet-records
W$ for N in 1 2 3; do ssh db$N sudo docker inspect --format "'{{.Name}} {{.Config.Image}} {{.State.StartedAt}}'" zcrypto-valkey grafana-alloy; done
```

Each node prints `valkey/valkey@<VK>` and `grafana/alloy@<AL>`, the digests the rows record, and each container's start. In `docs/reference/fleet-pins.md`'s `## Current pins` table, after the `alloy | nas` row, six rows: `| valkey + sentinel | zcrypto-valkeyN | \`<VK's first 12 hex>\` — Valkey 9.1.2, upstream \`valkey/valkey\` | <that node's zcrypto-valkey StartedAt, as YYYY-MM-DD HH:MM:SS> | first pin |` and `| alloy | zcrypto-valkeyN | \`b8ec653c4423\` — v1.19.2 | <that node's grafana-alloy StartedAt> | first pin |` for `N` in 1, 2, 3, `first pin` being the pins parser's own no-rollback-path marker. In `## Full digests`, one line `- \`<VK's first 12 hex>\` = \`<VK>\` — Valkey 9.1.2; valkey and sentinel on the three cache nodes`, and the `b8ec653c4423` line's host list reads `the ops, capture and cache hosts`. The pins file now names the three nodes, so the image pruner learns them in this commit (Task 1 left it alone for this reason): in `infra/scripts/prune-host-images.py`'s `HOSTS`, after the `nas` entry, `"zcrypto-valkey1": HostAccess(ssh="db1", docker=("docker",)),` and its two siblings for `db2` and `db3`; in `tests/test_prune_host_images.py::test_the_real_pins_file_parses_into_exactly_the_service_host_pairs_the_fleet_runs`, the pair set gains `("valkey + sentinel", ("zcrypto-valkeyN",))` and `("alloy", ("zcrypto-valkeyN",))` for `N` in 1, 2, 3, and its operand line becomes `assert len(row.operand) == 12 or row.hosts in {("zcrypto-valkey1",), ("zcrypto-valkey2",), ("zcrypto-valkey3",)}, row`, since a first pin has no rollback operand. `docs/reference/fleet.md` is re-trued where the converges read differently from what Tasks 1 and 5 wrote. Then:

```
W$ uv run python infra/scripts/prune-host-images.py zcrypto-valkey1
W$ uv run python infra/scripts/prune-host-images.py zcrypto-valkey1 --apply
W$ infra/scripts/count-list.sh pins-not-yet-converged
W$ uv run pytest tests/test_fleet_contracts.py tests/test_prune_host_images.py tests/test_pins_converged.py -q -p no:cacheprovider
W$ uv run pre-commit run -a
W$ git add docs/reference/fleet-pins.md docs/reference/deploy-log.jsonl docs/reference/fleet.md infra/scripts/prune-host-images.py tests/test_prune_host_images.py
```

The dry run lists the app image R4 pulled and nothing pinned; `--apply` removes it. `count-list.sh` prints `0` for `pins-not-yet-converged`: each of the six (pin, host) pairs has a successful deploy-log line on its host carrying the digest as `cache_image_digest` or `cache_alloy_digest`. The tests pass. The commit is `chore(fleet): the three cache nodes run Valkey 9.1.2 under Sentinel and Alloy v1.19.2, meshed with the engine host`, its message carrying the evidence the pins file asks of a converge (R3's unchanged markers, R4's verdict lines, R5's and R6's replication and Sentinel reads and the two `INFO server` lines, R7's capture-host markers and Alloy memory reading, R8's values), with the two trailers of `## Global Constraints`. The commit changes a guard, `tests/test_prune_host_images.py`'s pair set and operand line, so its verdict is earned on the committed tree, clean, and recorded by a message-only amend naming the script, before the pull request opens:

```
W$ infra/scripts/mutate-probe.sh --file docs/reference/fleet-pins.md --control '/^| valkey + sentinel | zcrypto-valkey3 |/d' --mutation '/^| archive-pull | nas |/s/| `[0-9a-f]\{12\}` |$/| first pin |/' -- uv run pytest tests/test_prune_host_images.py::test_the_real_pins_file_parses_into_exactly_the_service_host_pairs_the_fleet_runs -q -p no:cacheprovider
```

Expected: `KILLED`, control proven: the relaxed operand line still refuses a first-pin marker on a host outside the three nodes, and the pair set misses a deleted cache row. The mutation's anchor is the `archive-pull | nas` row's last cell as the pins file reads today; a row that reads otherwise then is re-anchored on its own text, since a no-op sed is refused (rc 6).

## Resolution

The branch delivers the infrastructure half of spec 00118, steps 1 to 4 of D15's rollout: the three nodes in the fleet under `cache_host` with their keys, vars and the hand-enumerated lists (Task 1); the firewall role's interface-scoped ports and the mesh's port on both layers' declarations (Task 2); the `zcache0` mesh on the four hosts, with its handshake-age probe on each (Task 3); Valkey 9.1.2 and Sentinel as one primary and two replicas under quorum 2, with the ACL users, the render-once configs, the capture role's guards and the daily pass's protection of the two daemons (Task 4); each node's Alloy, the `Cache` dashboard, the `zcrypto-cache` rule group, `infra/runbooks/cache.md` and the fleet page's rows (Task 5); the compatibility probe, D15's first item (Task 6); and the three skills that carry the nodes into the fleet's operations (Task 7). Once `## Rollout (attended)` has run, the set is live, replicated, failed over and back once, and watched; nothing attaches it to the engine.

It does not deliver the engine half, spec 00118's D1, D4, D10, D11 and D15: a second spec and plan, written at Rung 2's design point on the owner's word of 2026-09-24, whose home is [[T0213]] and whose trigger is the milestone the decisions log records, Rung 1's verdict, the entry tagged `[rung-1]` in `docs/research/14.phase6-decisions.md`. The half is the `cache_proxy` HAProxy service in the engine's compose project and its `cache-proxy` tag, the engine host's `:9104` scrape, the Cache board's proxy row and its two rules, D10's `[zcrypto.engine.cache]` wiring of the library's Redis backing to the proxy, D11's startup pass against the cache, D15's two-process harness with its CI Valkey service, and D1's live proof. The owner's operating rule stands unchanged on every page that carries it — `infra/runbooks/engine-procedures.md`, `infra/runbooks/engine.md`, `infra/runbooks/drills-order-path.md`, `infra/runbooks/order-semantics-verification.md` and `docs/reference/fleet.md`'s Reboots section: an engine converge or restart with a Kraken margin position open still closes positions first, until a pin carries the entry-price fix upstream or the second plan's live proof reads clean.

Task 7 makes the three guidance changes the nodes make due, each true of running hosts once the nodes run Alloy (Rollout R5): the Alloy bump skill's host map, `.claude/skills/zcrypto-bump-alloy/SKILL.md`, gains the three cache nodes beside its four hosts, with their place in its canary order and their leg; the daily-ops skill's autonomy line, `.claude/skills/zcrypto-daily-ops/SKILL.md`, names them among the telemetry-only hosts beside ops, the NAS and zaccess, as Task 1's `_TELEMETRY_HOSTS` holds them; and spec D14's Valkey re-pin order (the replicas, then `SENTINEL failover`, then the old primary, each node's `master_link_status:up` before the next) becomes the `Cache converges` section of `.claude/skills/zcrypto-rollout-image/SKILL.md`, the skill `.claude/rules/fleet-deploys.md` sends converges and re-pins to. The memo's `ENGINE CACHE` entry is updated by `zcrypto-marco`, its owner, when this branch merges: the infrastructure half landed, R4's probe verdict, the second plan held to Rung 2. `docs/reference/fleet.md` is re-trued twice: by Tasks 1 and 5 on this branch (Hosts, Reboots, Telemetry labels, Services and instruments, Storage topology, as designed), and by R9's records pull request where the converges read differently.

## Spec amendments

- D7, "Every new cap takes a leg under the fleet's memory-headroom rule": amended (ruling R9), in the spec's own text and its `## Spec amendments`, with D12's "headroom legs for every new capped container" beside it. The three Alloy caps take legs under `zcrypto-fleet-alloy-memory-headroom` at 268435456 (Task 5). The Valkey and Sentinel caps take none: the headroom rules parse `process_resident_memory_bytes`, which Valkey does not publish (its exporter reports `redis_memory_used_rss_bytes`) and Sentinel has no memory family at all; Valkey's memory is guarded by the cache group's `zcrypto-cache-memory-70pct` against `maxmemory`, and the six (host, job) pairs are recorded in `_HEADROOM_DELIBERATELY_ABSENT` with that reason (Task 4).
- D12, "a textfile probe publishes each mesh peer's WireGuard handshake age": delivered on all four mesh members, the engine host included, by the `cache_link` role (ruling R7), so each link is watched from both ends; the capture keep list admits the family for the engine host. The spec's D12 text now says so, recorded in its `## Spec amendments`.
- D9, "whose effect the runbook's rejoin procedure states": amended in the spec's text and its `## Spec amendments`. The reset is the runbook's `cache-config-reset` procedure, the rejoin procedure being a restart that renders nothing; and a changed password is `cache-password-rotation`'s, the three nodes' files replaced in one stop, since a node reset alone to a new password fails against the two still holding the old one (Tasks 4 and 5).
- D13 and D15 are not amended. D13's bootstrap sentence runs `site.yml --limit <host>` through `converge.sh` whole; the Rollout runs the base roles under their six tags at R2, the mesh at R3 and the rest at R5, which is D15's own sequence — "(1) bootstrap and base-converge the three nodes", then the mesh, then the probe D15 places "once it runs Docker", then Valkey — so the two sentences describe one rollout at two grains. The six base tags join `converge.sh`'s `TAGNAMES` beside D13's `cache` and `cache-link` for that reason, and D13's `cache-proxy` is the second plan's; `prune-host-images.py` gains the nodes at R9, with their first pins rows, rather than in Task 1.

## Self-review

- Spec coverage, per decision: D1 is the second plan's, and the Resolution keeps the operating rule standing on every page that carries it; D2 is Task 1 (the three nodes) and Task 4 (one `valkey/valkey` digest for both containers, refused unless pre-staged and recorded), read at R0 and rolled at R5; D3 is Task 4's `valkey.conf.j2`, `sentinel.conf.j2`, host networking and the per-node `replica-priority`, proven at R5 and R6; D4 is the second plan's; D5 is Task 3's mesh (addresses, `/32` peers, keepalive, MTU 1380, the four keypairs of its O1) and Task 2's `51821/udp` declarations, rolled at R3; D6 is Task 2's `firewall_interface_tcp_ports` and the widened `tests/test_infra_firewall_template.py`, with the Cloud Firewall in Task 1's O1 and Task 3's O2; D7 is Task 4's durability and memory lines and caps and Task 5's Alloy cap and legs, amended for the Valkey and Sentinel legs; D8 is Task 4's ACL users, password refusal and `users.acl` hashes with the five secrets of its O1; D9 is Task 4's render-when-absent, `cache_config_reset` with its refusal without the digest, and drift report, the runbook's `cache-config-reset` and `cache-password-rotation`, and R6's live proof; D10 and D11 are the second plan's; D12 is Task 5 (Alloy, `config.alloy`, the board, the rule group, the runbook, the Logs board, the Slack names, the fleet page's labels) with Task 3's probe and Task 4's copy of the capture role's reboot check for the hosts row's reboot flag, its proxy parts the second plan's; D13 is Task 1 (inventory, vars, bootstrap play, keys, the hand-kept lists, the fleet page), Task 3's `cache_host` play and Task 4's `cache` role in it, with `prune-host-images.py` at R9 and `cache-proxy` the second plan's; D14 is the one-node-per-converge constraint, R5's order, R6, the runbook's `cache-manual-failover` and Task 7's `Cache converges` section of the rollout skill; D15's steps 1 to 4 are R2 to R8, its first verification item Task 6 run at R4, its harness and steps 5 and 6 the second plan's. Found and fixed: no draft wrote the Services and instruments or the Storage topology rows D13 names for `docs/reference/fleet.md`, so Task 5 Step 16 writes them.
- Placeholder scan: no `TBD`, `TODO`, "similar to" or "add appropriate" remains. The tokens left are named where they stand: `PROBE_VERDICT`, replaced by each commit's probe step and checked gone; `<model>`, the executing model's name; the operator's own values `<D>`/`<VK...>`, `<AL>`, `<version>`, `<assumed>`/`<live>`, `<since>`, `<the ratio Step 15 printed>`, R7's `<zcrypto-capture's>`/`<grafana-alloy's>` (the digests the capture hosts' containers run) and the Rollout's hand-written `N`; the runbook's `<N>` and digest placeholders are the paged operator's to fill, and Task 7's skill text keeps the skills' own operator placeholders, `sha256:<new>`, `sha256:<running>`, `sha256:<...>`, `zcrypto-valkey<N>` and `<host>`. Found and fixed: Task 3's operator block pointed at "the open questions" that R1 settles, Task 4's site-play step carried a branch on whether Task 1 had listed the role, and the draft Rollout's list of names "to be matched" is gone, each name now matched.
- Name and type consistency across tasks: the ruling's names hold everywhere, a whole-file search finding `zcrypto-cache-valkey`, `zcrypto-cache-sentinel`, `/etc/zcrypto-cache`, `/var/lib/zcrypto-textfiles`, `zcrypto-cache-probe`, `zcache-nodes`, the jobs `cache_valkey` and `cache_sentinel`, and the draft Rollout's `vcli`, nowhere but in this sentence and, for the old textfile path, the Task 5 probe mutation that plants it; `cache_textfile_dir` is Task 4's, `/var/lib/zcrypto-node-textfile`, the directory the mesh probe writes too. Found and fixed: the containers renamed in Task 4; the Alloy project under `/opt/zcrypto-cache/alloy` and the runbook's reads moved onto Task 4's `cli-*.env` files in Task 5; the draft Rollout's Sentinel reads, which presented `cache_sentinel_password` where Sentinel takes `cache_sentinel_requirepass`, now go through `cli-sentinel.env`; the Cloud Firewall is `zcrypto-cache` throughout; the headroom pairs' jobs are `valkey` and `sentinel`, the jobs Task 5 ships; "Task 2's `cache_link`" and the descriptive task names read as task numbers; Task 5's second definition of `CACHE` is gone; the head's file structure names `zcrypto-cache.service.j2`, the two `cli-*.env.j2` templates, `tests/test_zcache_probe.py` and the test modules each task touches; Task 1 and Task 5 both rewrote the fleet page's Loki bullet, so Task 5 inserts only its second bullet; a first pins row's operand is `first pin`, the parser's own marker, and R9 relaxes `tests/test_prune_host_images.py`'s 12-hex operand assertion for the three nodes; Task 5's Alloy account lookup would fail the first converge's `--check` preview before the account exists, so it takes Task 4's `failed_when` and fallback, and Task 4's reboot-check timer enable skips that preview the same way; Task 4's reboot-check copies are held to the capture role's programs, and their comments carry no venue name, since the deploy-log audit walks the roles directory; R6's re-converge of a running node passes a `pins_override`, since the pins rows land at R9. No code fence destined for `tests/` or `infra/` names a plan task number (`tests/test_code_prose_citations.py`). The `Expected:` counts this assembly changed: Task 3's `26` and `22` are sums of the named cases' parametrizations, not a run; Task 4's `67 failed`, `8 failed`, `4 failed`, `136 passed` and `109` added cases, and Task 5 Step 11's `3 failed, 4 passed`, were read by collect-only and a run over the fence tree carrying these edits; Task 5 Step 15's `219/312 = 0.7019` was read on the branch by that step's own command. Task 7's `10 passed`, `680 passed`, `38`, `45`, `114`, `47`, `20205` and `1167 passed` were read on this branch and again on a scratch clone of it with Task 7's Steps 2 to 4 applied, which read the same; its diff size and its commit-msg hooks' passes were read on the clone.
- Probe scope: each control and mutation of the plan's seven probe blocks changes exactly one line of its file at the commit it runs on, read by applying each sed to the fence tree's files at that commit; Task 4's probes 3, 4, 6, 7, 12, 13 and 24 to 26 matched two or three sites and take a sed line range.
- Review Focus coverage: each of the five lines names tests its task defines — Task 1 `test_every_reboot_slot_is_an_hour_from_every_other_and_from_a_bar_boundary` and `test_the_collision_assert_reads_the_cache_group`; Task 3 `test_each_zcache_peer_key_is_one_variable_every_member_renders`, added for it, and `test_the_zcache_conf_names_each_other_member_once_as_one_host`; Task 4 `test_the_acl_file_carries_password_hashes_and_never_a_password`, `test_cache_password_refusal` and `test_cache_password_refusal_names_the_key_and_never_the_value`; Task 4 `test_cache_configs_render_only_when_absent_unless_reset`, `test_cache_drift_reports_a_config_whose_template_moved` and `test_cache_drift_is_reported_never_fatal_and_skips_a_config_this_run_rendered`; Task 4 `test_the_default_user_is_off_and_the_engine_keeps_keys_and_info_past_dangerous`, which gained its `@keyspace`, `@read` and `@write` assertion and probe 29 for the fifth line, while R4 now runs the probe under the same `engine` grant. Each name was searched for as a `def` in the assembled plan and found once, in the task the line names.
