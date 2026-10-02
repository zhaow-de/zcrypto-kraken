# The observability node, phase 1: `zcrypto-mon` up and taking a shadow push of every rule — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One Linode node, `zcrypto-mon`, joins the fleet and one converge after its bootstrap leaves it running Grafana OSS on SQLite, one Prometheus as a remote_write receiver, single-binary Loki, Caddy as the one public listener and a native Alloy shipping the node to itself; the workstation's tools address it by name; one push sends it every rule, the node's own group included, paging a shadow Slack channel. Nothing in the fleet ships to it yet and Grafana Cloud is untouched: this is phase 1 of the spec's four.

**Architecture:** Seven build tasks on the fleet's existing shapes and one guidance edit, then an attended runsheet. The host joins the hand-kept lists as the bridgehead and the cache nodes did (inventory, vars, keys, the converge whitelist, the instruments' host sets), and the base role's unattended-upgrades template takes a per-host package blacklist. A new `mon` role installs five apt packages and renders their configs, with the evaluator ordered behind its stores, then keeps one Editor service account and its one token, cached vault-encrypted on the controller, and last ships the node's own telemetry and runs a self-check on a timer. `grafana_auth.py` becomes a table of two stacks which `grafana-query.py` and `ops_daily.py` take by name, `grafana-push.sh` learns to leave named rule groups out, and the rule file, the Fleet health board and a new runbook page gain the node's own group. Three seams are built here for later phases and used by none of this plan's own steps beyond their proof: the `fleet` and `logship` ingest users (phase 2's second endpoints and phase 3's log hand-over), the stack table (phase 2's comparison script and phase 3's default flip), and `GRAFANA_SKIP_RULE_GROUPS` (every push of the dual period, removed at phase 4).

**Tech Stack:** Ansible (ansible-core 2.21, devsec.hardening, the fleet's roles), Debian 13, Grafana OSS 13.2, Prometheus 2.53.3 (Debian main), Loki 3.7 and Alloy 1.20 (`apt.grafana.com`), Caddy 2.11 (cloudsmith), systemd units and timers, `infra/scripts/grafana-push.sh`, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00121-self-hosted-observability-design.md`, phase 1: D2 to D11, D16 to D18, the phase-1 lines of "What changes in the repo, by phase" and "Proofs each phase owes". Phases 2 to 4 each take a plan of their own under the same serial, written once the phase before it has been read.

## Global Constraints

- The host is `zcrypto-mon` (`zcrypto-mon.zhaow.me`, an A and an AAAA record), inventory group `mon_host`, a child of `observed`; the admin user is `zcrypto-deploy` on port 10022; its play runs `base`, `hardening`, `firewall`, `fail2ban`, `chrony` and `mon`, the last under the tag `mon`, and no `docker` role (spec D2).
- Grafana, Loki, Alloy and Caddy are followed from their apt repositories and `prometheus` from Debian main without recommends: no task forces, holds or pins a version, and none takes a `docs/reference/fleet-pins.md` row; the role refuses a `loki` candidate whose origin is not `apt.grafana.com` (spec D2).
- Grafana, Prometheus, Loki and Alloy bind `127.0.0.1` alone (3000, 9090, 3100, 12345). Caddy is the one public listener, on 443: `/api/v1/write` and `/loki/api/v1/push` behind its basic auth, `/metrics`, `/metrics/*` and `/swagger*` answered 404, every other path to Grafana. The firewall opens 443 beside 10022 and nothing else (spec D4).
- `[auth.basic]`, `[auth.proxy]`, `[auth.jwt]` and anonymous access are off in `grafana.ini`; the login form stays on, and the admin login's name is a generated one, vaulted beside its password. The tools hold one Editor service-account token and no Admin service account exists (spec D5, D6).
- No Grafana token is rendered on a managed host or written to a tracked file, and no task prints one. No secret appears in a command line, a log, a diff or a plan step. No executor decrypts, prints or generates a vault value; `ansible-inventory --host`, `--list` and `--graph --vars` are never run.
- The role's bootstrap carries the spec's five corrections (D7): a token is held to its pattern before it is placed in a header and written with no newline added; a refused sign-in is repaired once from the vault and a second refusal fails naming the lockout, with no retry; the files `$__file{}` reads are `root:grafana 0640`; the CLI reset passes `--configOverrides cfg:default.paths.data=/var/lib/grafana`; the preview passes on a node that has none of the packages. Every controller-delegated task carries `become: false`.
- The two datasource uids and the alert folder uid are Grafana Cloud's, `grafanacloud-prom`, `grafanacloud-logs` and `bfrxdfoybx98gb`, file-provisioned; dashboards, rules, contact points, the policy and the template are pushed, never file-provisioned (spec D8).
- Both stores keep 90 days; Prometheus's size cap is `8GB` and its out-of-order window 8 h (spec D10, D11).
- A store on the node is restarted with Grafana stopped around it, by the role's handlers and by the runbook's hand procedure; `prometheus` is on the node's unattended-upgrades blacklist (spec D17).
- `grafana_auth.py`'s default stack stays `cloud`, and `grafana-push.sh` leaves the `zcrypto-mon` group out unless its caller passes `GRAFANA_SKIP_RULE_GROUPS` otherwise, and refuses a push addressed to Grafana Cloud that does not skip it: a rule of that group is never pushed to Grafana Cloud (spec D18).
- Nothing here changes a fleet host's config, a Grafana Cloud rule, receiver or vault value, and nothing converges `zcrypto`; no existing vault value is repointed (the spec's invariants).
- No executor step reaches a host, a venue, Grafana Cloud, the node's Grafana, Slack, the Linode Cloud Manager or DNS; every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No file under `infra/ansible/group_vars/mon_host/`, `infra/ansible/host_vars/zcrypto-mon/` or `infra/ansible/roles/mon/` carries the word the venue's name spells: `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` walks them, and a `__pycache__` beside a role script counts.
- No operator-read surface (the runbook page, the rule file's text, the dashboard, the Slack template) carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; where a provenance token is wanted it goes in an adjacent code comment.
- A comment or docstring stays only where a reader would do something differently without it; an event goes to the commit message.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean. The branch is unpushed while the tasks run, so the amend rewrites nothing a reader holds.
- Every commit is green over the changed files' consumers, the tests each task's consumer step names; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs clean before every commit; a run that rewrites files is re-run until clean and the rewrites staged.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. A universal word in a new runbook bullet (every, never, always, only, any, cannot) carries its `(set: …; count: …)` or `(no count command: …)` clause, or the bullet is worded without it.
- Task 8 alone edits a file under `.claude/`, the push skill, in a `claude` commit that carries no other file; no task edits `CLAUDE.md`.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `infra/ansible/inventory/hosts.yml`, `group_vars/mon_host/vars.yml`, `host_vars/zcrypto-mon/vars.yml` and `vault.yml`, `files/deploy_zcrypto-mon_ed25519{,.pub}`, `files/README.md`, `bootstrap.yml`, `site.yml`: the group, its connection, hardening and firewall vars, the host's name, slot, reboot flag and blacklist, the deploy key, the bootstrap play's hosts and the node's play (Task 1; the vault file in the Rollout's P2; the `mon` role's line in the play in Task 2).
- `infra/ansible/roles/base/`: the collision assert's fourth group and the unattended-upgrades template's per-host package blacklist (Task 1).
- `infra/ansible/scripts/run.sh`, `scripts/converge.sh`: the key ring, the host, the tag `mon` and the key `mon_grafana_token_rotate` (Task 1).
- `infra/scripts/deploy-log-audit.py`, `count-list.sh`, `ops_daily.py`, `infra/external-systems.md`: `NO_VENUE_EXPOSURE`, the hosts that reboot by hand, the ssh alias `mon`, the telemetry hosts and the one unit the daily pass may restart there, the `Host mon` stanza (Task 1); `ops_daily.py`'s `--stack` and the `grafana-query.py` shape that takes one (Task 5), its `_UID_HOST` entries and the patch pass's reminder (Task 7).
- `infra/ansible/roles/mon/`: `defaults/main.yml`, `tasks/main.yml`, `handlers/main.yml` and the templates `grafana.ini.j2`, `Caddyfile.j2`, `prometheus.default.j2`, `prometheus.yml.j2`, `loki-config.yml.j2`, `grafana-server.dropin.conf.j2`, `datasources.yml.j2`, `folder-anchor.yml.j2` (Task 2); `tasks/token.yml` (Task 3); `files/config.alloy`, `files/zcrypto-reboot-check.sh` and `.timer`, `templates/zcrypto-reboot-check.service.j2`, `files/zcrypto-mon-selfcheck.py` and `.timer`, `templates/zcrypto-mon-selfcheck.service.j2` and `.env.j2` (Task 4).
- `infra/scripts/grafana_auth.py`, `grafana-query.py` (Task 5); `infra/scripts/grafana-push.sh` (Task 6).
- `infra/grafana/alerts.yaml`, `fleet-health-dashboard.json`, `notification-templates/zcrypto-slack.tmpl`; `infra/runbooks/mon.md`, `observability.md` (Tasks 4 and 7).
- `docs/reference/fleet.md`: Hosts and Reboots (Task 1); Services and instruments, Telemetry labels (Task 7).
- `.claude/skills/zcrypto-grafana-push/SKILL.md`: the preflight and the verify step leave the skipped group's rules and the node's dashboard row to the node (Task 8).
- `tests/test_run_sh.py`, `test_converge_sh.py`, `test_infra_converge_guards.py`, `test_infra_unattended_upgrades.py`, `test_infra_firewall_template.py`, `test_pins_converged.py`, `test_deploy_log_audit.py`, `test_ops_daily.py`, `test_ops_daily_soak.py`, `test_reboot_check.py`, `test_dashboards_cover_metrics.py`, `test_grafana_auth.py`, `test_grafana_query.py`, `test_grafana_push_sh.py`, `test_infra_alert_rules.py`: the contracts the new host, role and seams fall under (Tasks 1 to 7); new: `tests/test_infra_mon_role.py` (Tasks 2, 4), `tests/test_infra_mon_token.py` (Task 3), `tests/test_mon_selfcheck.py` (Task 4).

## Review Focus

- A cached token stored with a trailing newline, which `$` admits and which made a later request fail with the token in the error text despite `no_log`: the pattern must end `\Z`, a cached value must reach an `Authorization` header only through the task that checks it, and a minted one must be checked before it is written with `stdin_add_newline: false`; Task 3 owns `test_the_pattern_ends_where_the_string_ends`, `test_a_cached_value_reaches_a_header_only_in_a_tokens_shape` and `test_a_minted_token_is_held_to_the_shape_before_it_is_written_with_no_newline_added`.
- The preview on a node that has none of the packages, which `converge.sh` always runs first and stops on: `apt` fails on a name its cache does not hold, `systemd_service` fails on a unit not yet installed and every API call would meet no Grafana; each such task must skip exactly that preview and run on every real converge; Task 2 owns `test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find`, `test_what_needs_a_repository_or_a_unit_skips_the_preview_that_has_neither` and the widened `test_every_register_a_preview_guard_reads_is_set_in_its_own_role`, Task 3 `test_the_token_tasks_run_only_outside_check_mode`.
- A push to Grafana Cloud from a tree that carries the node's rule group, where the group has no data and its two dead-men would page the main channel: the push must leave the group out when its caller names nothing, an empty value must mean "skip none" and not fall back to the default, a push addressed to Grafana Cloud must refuse to run unless it skips the group, and no rule outside the group may name the node in a `host` matcher; Task 6 owns `test_a_push_that_names_no_stack_sends_no_rule_of_the_observability_node`, `test_the_nodes_push_passes_the_variable_empty_and_sends_its_own_group`, `test_a_push_addressed_to_grafana_cloud_refuses_to_send_the_nodes_group` and `test_the_committed_default_skips_exactly_the_observability_nodes_group`, Task 7 `test_the_push_keeps_the_mon_group_off_grafana_cloud_by_default` and `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group`.
- Grafana's login lockout met by the converge, after the owner mistyped in the UI or the password drifted from the vault, or held shut by a stranger: the lockout is by account name, so the admin's name must be the vaulted, generated one in the ini and in both sign-ins, never the default one a scanner tries; a refused sign-in must be repaired exactly once by the CLI reset against the unit's own data path, and a second refusal must fail the converge naming the lockout with no retry, since each attempt counts toward it; Task 2 owns `test_a_missing_or_misshapen_secret_is_refused_by_its_key` and `test_the_ini_carries_what_the_public_login_rests_on`, Task 3 `test_a_refused_sign_in_is_repaired_once_from_the_vault_and_never_retried`.
- A store restarted under a running Grafana, where all but two rules page on an evaluation error and 24 have no pending period: the handlers must stop Grafana before either store restarts and start it after, the stores must be running their rendered configs before Grafana's first start, the unit must wait for both to answer ready, `prometheus` must stay out of unattended upgrades, and the daily pass must leave every unit on the node but its Alloy to the operator; Task 2 owns `test_a_store_is_restarted_with_grafana_stopped_around_it`, `test_the_stores_are_running_their_rendered_configs_before_grafana_is_started` and `test_grafana_starts_after_its_stores_and_waits_for_both_to_be_ready`, Task 1 `test_the_observability_node_keeps_prometheus_for_a_hand_pass` and `test_on_the_observability_node_a_restart_that_is_not_alloy_is_the_operators`.

---

### Task 1: The node joins the fleet: inventory, key, the hand-kept lists, the package blacklist and the fleet page

**Files:**
- Create: `infra/ansible/files/deploy_zcrypto-mon_ed25519` (vault-encrypted) and `infra/ansible/files/deploy_zcrypto-mon_ed25519.pub` (generated and vault-encrypted by the owner in operator step O0 before Step 1, never by the executor and never hand-written; committed by Step 11)
- Create: `infra/ansible/group_vars/mon_host/vars.yml`
- Create: `infra/ansible/host_vars/zcrypto-mon/vars.yml`
- Modify: `infra/ansible/inventory/hosts.yml` (the `observed` children; a `mon_host` group before `workstation:`)
- Modify: `infra/ansible/bootstrap.yml` (the first play's `name:` and `hosts:`)
- Modify: `infra/ansible/site.yml` (the node's play appended, the five base roles; Task 2 appends the `mon` role's line)
- Modify: `infra/ansible/roles/base/tasks/main.yml` (the header comment, `base_fleet_hosts`, the template task's name)
- Modify: `infra/ansible/roles/base/defaults/main.yml` (the reboot-flag comment; the new `base_unattended_upgrades_package_blacklist`)
- Modify: `infra/ansible/roles/base/templates/50unattended-upgrades.j2` (a `Package-Blacklist` block rendered only for a non-empty list)
- Modify: `infra/ansible/scripts/run.sh` (the key-order comment and `KEYS=`)
- Modify: `infra/ansible/scripts/converge.sh` (`HOSTS`, `TAGNAMES`, `EVKEYS` and their comments)
- Modify: `infra/ansible/files/README.md`
- Modify: `infra/scripts/deploy-log-audit.py`
- Modify: `infra/scripts/count-list.sh` (the host loop of `attended-hosts-with-automatic-reboot`)
- Modify: `infra/scripts/ops_daily.py` (the two alias maps, `_TELEMETRY_HOSTS`, a second allowlist in `_classify_one`)
- Modify: `infra/external-systems.md` (the key sentence and a `Host mon` stanza in the SSH config block)
- Modify: `docs/reference/fleet.md` (one Hosts row; the Reboots bullet)
- Test: `tests/test_run_sh.py`
- Test: `tests/test_converge_sh.py`
- Test: `tests/test_infra_converge_guards.py`
- Test: `tests/test_infra_unattended_upgrades.py`
- Test: `tests/test_infra_firewall_template.py`
- Test: `tests/test_pins_converged.py`
- Test: `tests/test_deploy_log_audit.py`
- Test: `tests/test_ops_daily.py`

**Interfaces:**
- Consumes: the inventory's existing groups; `devsec.hardening`'s `ssh_allow_users` through `hardening_ssh_allow_users`; the base role's `base_hostname`, `base_unattended_upgrades_reboot_time`, `base_unattended_upgrades_automatic_reboot`, its collision assert and its `50unattended-upgrades.j2`; the firewall role's `firewall_extra_tcp_ports`; `bootstrap.yml`'s first play and its two refusals; `run.sh`'s ring and `--limit` reordering; `converge.sh`'s whitelist; `NO_VENUE_EXPOSURE`; `ops_daily`'s `ssh_alias`, `host_label`, `_TELEMETRY_HOSTS`, `_classify_one`, `classify_action`, `Tier`; `count-list.sh`'s `c_attended_hosts_with_automatic_reboot`; the test helpers the edited test files already import.
- Produces, for Tasks 2 to 7 and the Rollout to use by these exact names: the group `mon_host` (a child of `observed`) holding `zcrypto-mon`; `infra/ansible/group_vars/mon_host/vars.yml` and `infra/ansible/host_vars/zcrypto-mon/vars.yml`, beside which the Rollout's P2 writes `vault.yml`; the node's play in `site.yml`, to which Task 2 appends the `mon` role; the `converge.sh` host `zcrypto-mon`, tag `mon` and extra-var key `mon_grafana_token_rotate` (Task 3's role reads exactly that name); `base_unattended_upgrades_package_blacklist`; the workstation alias `mon` and the ops-daily label `zcrypto-mon`; `_MON_HOSTS` and `_MON_AUTONOMOUS_OBJECTS`.

**What this task decides, where the spec leaves it open:**
- The workstation's ssh alias is `mon`, as the cache nodes' are `db1` to `db3`; `infra/external-systems.md` carries its stanza and `tests/test_ops_daily.py` holds every Linode node's stanza to the inventory, a case generalised here from the cache nodes to a map of groups.
- `group_vars/mon_host/vars.yml` sets `hardening_extra_sysctl` to the two kernel keys alone: the fleet default also force-enables `net.ipv4.ip_forward` for Docker hosts, and this node runs no container.
- The blacklist is a role default, `base_unattended_upgrades_package_blacklist: []`, rendered as an `Unattended-Upgrade::Package-Blacklist` block only when non-empty, so every other host's rendered file is byte-identical to today's (`test_an_empty_blacklist_renders_the_file_the_fleet_already_has`). The node's entry is `prometheus$`: unattended-upgrades matches each entry as a regular expression from the start of the package name, so a bare `prometheus` would also hold every package the name prefixes.
- `converge.sh` admits the bare `--limit zcrypto-mon` (the node's first converge names no tag, since every role of its play is wanted), `--tags mon`, and `--tags mon -e mon_grafana_token_rotate=true`; `mon_host` stays refused as a limit, as `cache_host` is. The three are the `PUBLISHED` entries this task adds, and the `OUTSIDE` entries refuse a group limit, a tag `grafana` and a token passed as an operand.
- The daily pass may restart one unit on the node by itself, the node's own Alloy (`alloy`, `alloy.service`); a restart of `grafana-server`, `prometheus`, `loki` or `caddy` there is classified for the operator, because each is restarted in an order the runbook gives (spec D17). The allowlist is a second one beside the cache nodes', read in `_classify_one`.
- `bootstrap.yml`'s first play widens to `capture_host:cache_host:mon_host` with both refusals unchanged, and `tests/test_infra_converge_guards.py`'s cache-node case becomes one case parametrised over the two groups.
- `count-list.sh attended-hosts-with-automatic-reboot` walks four hosts; `tests/test_infra_unattended_upgrades.py` extracts that function from the script and holds the node in its loop.

**Operator step O0 (attended), before Step 1: the deploy keypair.** The owner runs it, never the executor, from this branch's worktree root before the executor's Step 1; the two files it writes stay uncommitted until Step 11 commits them. The private half exists in plaintext only between the two commands below. If `ansible-vault encrypt` fails (it reads the vault password through `infra/ansible/scripts/vault-pass.sh`, `sops` over the owner's GPG key, so the GPG agent must be unlocked), delete the private half at once with `rm -f infra/ansible/files/deploy_zcrypto-mon_ed25519`, unlock the agent and run O0 again from the top.

```bash
ssh-keygen -q -t ed25519 -C zcrypto-mon -N '' -f infra/ansible/files/deploy_zcrypto-mon_ed25519
(cd infra/ansible && uv run ansible-vault encrypt files/deploy_zcrypto-mon_ed25519)
```

Expected: `Encryption successful`. Then check the file by count, never by printing it:

```bash
f=infra/ansible/files/deploy_zcrypto-mon_ed25519
printf 'vault-header=%s plaintext-key-lines=%s pub=%s\n' \
  "$(grep -c '^\$ANSIBLE_VAULT;1\.1;AES256$' "$f")" "$(grep -c 'PRIVATE KEY' "$f")" \
  "$(ssh-keygen -lf "$f.pub" | awk '{print $3, $4}')"
```

Expected: `vault-header=1 plaintext-key-lines=0 pub=zcrypto-mon (ED25519)`.

- [ ] **Step 1: The owner's two key files are in the tree**

Run: `ls infra/ansible/files/deploy_zcrypto-mon_ed25519{,.pub} | wc -l`

Expected: `2`. A lower count means O0 has not run: stop and report it to the controller. The executor generates, decrypts and prints neither file; Step 2's ring case reads the public half's opening `ssh-ed25519 `, so a placeholder in the key's place is refused there.

- [ ] **Step 2: Write the failing tests**

The ring and the node's limit, in `tests/test_run_sh.py`:

`tests/test_run_sh.py` — replace

```python
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3")
```

with

```python
HOSTS = (
    "zcrypto",
    "zcrypto-red",
    "zcrypto-ops",
    "nas",
    "zaccess",
    "zcrypto-valkey1",
    "zcrypto-valkey2",
    "zcrypto-valkey3",
    "zcrypto-mon",
)
```

`tests/test_run_sh.py` — after

```python
def test_a_cache_node_limit_offers_its_key_first(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit", "zcrypto-valkey2", "--tags", "cache"])
    assert added == ["files/deploy_zcrypto-valkey2_ed25519", *[k for k in DEFAULT if "valkey2" not in k]]
```

insert (the insert opens with 2 blank lines, kept)

```python


def test_the_observability_node_limit_offers_its_key_first(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit", "zcrypto-mon", "--tags", "mon"])
    assert added == ["files/deploy_zcrypto-mon_ed25519", *DEFAULT[:-1]]
```

The converge whitelist, in `tests/test_converge_sh.py`:

`tests/test_converge_sh.py` — before

```python
]


@pytest.mark.parametrize("args,limit,tags,extra", PUBLISHED)
```

insert

```python
    (["--limit", "zcrypto-mon"], "zcrypto-mon", "", {}),
    (["--limit", "zcrypto-mon", "--tags", "mon"], "zcrypto-mon", "mon", {}),
    (
        ["--limit", "zcrypto-mon", "--tags", "mon", "-e", "mon_grafana_token_rotate=true"],
        "zcrypto-mon",
        "mon",
        {"mon_grafana_token_rotate": "true"},
    ),
```

`tests/test_converge_sh.py` — after

```python
    (["--limit", "cache_host"], "the cache group, whose nodes converge one per run", "unknown host"),
```

insert

```python
    (["--limit", "mon_host"], "the observability group where its one host belongs", "unknown host"),
    (["--limit", "zcrypto-mon", "--tags", "grafana"], "a component of the node, which is no tag", "unknown tag"),
    (
        ["--limit", "zcrypto-mon", "-e", "mon_grafana_token=x"],
        "a token as an operand, which the row would record",
        "not in this script's key set",
    ),
```

The bootstrap play's hosts and its two guards:

`tests/test_infra_converge_guards.py` — replace

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

with

```python
@pytest.mark.parametrize("group", ["cache_host", "mon_host"])
def test_the_other_public_nodes_bootstrap_under_the_capture_plays_guards(group):
    """A cache node and the observability node are public VPSes like a capture host, so each takes this play's sshd
    drop-in and, with it, the re-bootstrap refusal, unnarrowed; the primary refusal stays keyed on `engine_host`, which
    neither joins."""
    plays = load_tasks(BOOTSTRAP)
    play = next(p for p in plays if p["hosts"].split(":")[0] == "capture_host")
    assert play["hosts"].split(":") == ["capture_host", "cache_host", "mon_host"]
    assert "when" not in find_task(play["tasks"], REBOOTSTRAP)
    primary = find_task(play["tasks"], PRIMARY_REFUSAL)
    assert when_conditions(primary) == ["inventory_hostname in groups['engine_host'] | default([])"]
    assert [p["hosts"] for p in plays if group in p["hosts"].split(":")] == [play["hosts"]]
```

The reboot slot, the reboot by hand, the blacklist and the count entry's host loop, in `tests/test_infra_unattended_upgrades.py`:

`tests/test_infra_unattended_upgrades.py` — replace

```python
`Automatic-Reboot` is a variable so the two capture VPSes and the ops node reboot by hand while the
cache nodes and the bridgehead keep the role default and reboot themselves. The value must be a quoted string: a bare YAML `false` renders through Jinja as Python's
```

with

```python
`Automatic-Reboot` is a variable so the two capture VPSes, the ops node and the observability node reboot by hand while
the cache nodes and the bridgehead keep the role default and reboot themselves. The value must be a quoted string: a bare YAML `false` renders through Jinja as Python's
```

`tests/test_infra_unattended_upgrades.py` — replace

```python
import re
from pathlib import Path
```

with

```python
import re
import subprocess
from pathlib import Path
```

`tests/test_infra_unattended_upgrades.py` — replace

```python
OPS_HOST_VARS = HOST_VARS / "zcrypto-ops/vars.yml"
CACHE_NODES = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
# The groups whose hosts run the base role and so hold an unattended-upgrades slot; DSM owns the NAS's.
SLOT_GROUPS = ("capture_host", "ops_host", "access_host", "cache_host")
```

with

```python
OPS_HOST_VARS = HOST_VARS / "zcrypto-ops/vars.yml"
MON_HOST_VARS = HOST_VARS / "zcrypto-mon/vars.yml"
CACHE_NODES = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
# The groups whose hosts run the base role and so hold an unattended-upgrades slot; DSM owns the NAS's.
SLOT_GROUPS = ("capture_host", "ops_host", "access_host", "cache_host", "mon_host")
BLACKLIST = "base_unattended_upgrades_package_blacklist"
COUNT_LIST = REPO / "infra/scripts/count-list.sh"
```

`tests/test_infra_unattended_upgrades.py` — replace

```python
        "base_unattended_upgrades_reboot_time": "21:25",
        "base_unattended_upgrades_mail_to": "root",
        **overrides,
```

with

```python
        "base_unattended_upgrades_reboot_time": "21:25",
        "base_unattended_upgrades_mail_to": "root",
        BLACKLIST: [],
        **overrides,
```

`tests/test_infra_unattended_upgrades.py` — replace

```python
def test_the_ops_node_reboots_by_hand():
    assert _yaml(OPS_HOST_VARS)[VAR] == "false"


@pytest.mark.parametrize("path", [BASE_DEFAULTS, CAPTURE_GROUP_VARS, OPS_HOST_VARS], ids=["defaults", "capture", "ops"])
```

with

```python
def test_the_ops_node_reboots_by_hand():
    assert _yaml(OPS_HOST_VARS)[VAR] == "false"


def test_the_observability_node_reboots_by_hand():
    """A reboot there blanks rule evaluation for its duration, so it is taken by hand, in the node's slot."""
    assert _group_hosts("mon_host") == {"zcrypto-mon"}
    assert _yaml(MON_HOST_VARS)[VAR] == "false"


@pytest.mark.parametrize(
    "path", [BASE_DEFAULTS, CAPTURE_GROUP_VARS, OPS_HOST_VARS, MON_HOST_VARS], ids=["defaults", "capture", "ops", "mon"]
)
```

`tests/test_infra_unattended_upgrades.py` — replace

```python
    for group in ("capture_host", "ops_host", "cache_host"):
        assert f"groups['{group}']" in expr, f"{group} is not in the collision assert's host list: {expr}"
```

with

```python
    for group in ("capture_host", "ops_host", "cache_host", "mon_host"):
        assert f"groups['{group}']" in expr, f"{group} is not in the collision assert's host list: {expr}"
```

`tests/test_infra_unattended_upgrades.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- the per-host package blacklist: a package the security origin may upgrade, and so restart, kept for a hand pass.
_BLACKLIST_BLOCK = re.compile(r"\{% if base_unattended_upgrades_package_blacklist %\}\n.*?\{% endif %\}\n", re.DOTALL)


def test_an_empty_blacklist_renders_the_file_the_fleet_already_has():
    source = TEMPLATE.read_text()
    before = _BLACKLIST_BLOCK.sub("", source, count=1)
    assert before != source, "the blacklist block was not found, so this compares the template with itself"
    context = {VAR: "true", "base_unattended_upgrades_reboot_time": "21:25", "base_unattended_upgrades_mail_to": "root"}
    assert _render(**{VAR: "true"}) == _ENV.from_string(before).render(**context)
    assert _yaml(BASE_DEFAULTS)[BLACKLIST] == []


def test_the_observability_node_keeps_prometheus_for_a_hand_pass():
    """Debian's package restarts the daemon on upgrade, under a Grafana that pages on every evaluation error."""
    declared = _yaml(MON_HOST_VARS)[BLACKLIST]
    assert declared == ["prometheus$"], declared
    lines = _render(**{VAR: "false", BLACKLIST: declared}).splitlines()
    start = lines.index("Unattended-Upgrade::Package-Blacklist {")
    assert lines[start + 1 : lines.index("};", start)] == ['        "prometheus$";'], lines


def test_no_other_host_declares_a_blacklist():
    declaring = sorted(
        str(path.relative_to(REPO))
        for root in (HOST_VARS, HOST_VARS.parent / "group_vars")
        for path in root.rglob("vars.yml")
        if BLACKLIST in _yaml(path)
    )
    assert declaring == ["infra/ansible/host_vars/zcrypto-mon/vars.yml"], declaring


def _attended_hosts_with_automatic_reboot(tree: Path) -> int:
    function = re.search(r"^c_attended_hosts_with_automatic_reboot\(\) \{.*?^\}", COUNT_LIST.read_text(), re.S | re.M)
    assert function, "the entry's function is gone or renamed"
    script = f"{function.group(0)}\nc_attended_hosts_with_automatic_reboot"
    return int(subprocess.run(["bash", "-c", script], cwd=tree, capture_output=True, text=True, check=True).stdout)


def test_the_attended_hosts_count_walks_the_observability_node(tmp_path):
    """The counter's host list is hand-kept: a host missing from it can flip to an automatic reboot uncounted."""
    for rel in ("group_vars/capture_host/vars.yml", "host_vars/zcrypto-ops/vars.yml", "host_vars/zcrypto-mon/vars.yml"):
        copy = tmp_path / "infra/ansible" / rel
        copy.parent.mkdir(parents=True)
        copy.write_text((REPO / "infra/ansible" / rel).read_text())
    assert _attended_hosts_with_automatic_reboot(tmp_path) == 0
    mon = tmp_path / "infra/ansible/host_vars/zcrypto-mon/vars.yml"
    mon.write_text(mon.read_text().replace(f'{VAR}: "false"', f'{VAR}: "true"'))
    assert _attended_hosts_with_automatic_reboot(tmp_path) == 1
```

The opener files, in `tests/test_infra_firewall_template.py`:

`tests/test_infra_firewall_template.py` — replace

```python
    "group_vars/cache_host/vars.yml": ["firewall_extra_udp_ports", "firewall_interface_tcp_ports"],
    "host_vars/zcrypto/vars.yml": ["firewall_extra_udp_ports"],
}
```

with

```python
    "group_vars/cache_host/vars.yml": ["firewall_extra_udp_ports", "firewall_interface_tcp_ports"],
    "group_vars/mon_host/vars.yml": ["firewall_extra_tcp_ports"],
    "host_vars/zcrypto/vars.yml": ["firewall_extra_udp_ports"],
}
```

`tests/test_infra_firewall_template.py` — after

```python
def test_the_copied_var_files_alone_red_nothing(tmp_path, monkeypatch):
    """The true positive beside it: the copy passes until the case above plants something."""
    monkeypatch.setitem(globals(), "VAR_ROOTS", _var_roots_copy(tmp_path))
    test_only_the_opener_files_open_extra_ports()
```

insert (the insert opens with 2 blank lines, kept)

```python


def test_the_observability_node_opens_443_and_nothing_else():
    """One public name on one port: 80 stays shut, so the edge's certificate is issued over 443 alone, and the stores'
    and Grafana's own ports are never opened."""
    declared = yaml.safe_load((ANSIBLE / "group_vars/mon_host/vars.yml").read_text())
    assert declared["firewall_extra_tcp_ports"] == [443], declared
    out = _render({**BASE, "firewall_extra_tcp_ports": declared["firewall_extra_tcp_ports"]})
    accepts = [line.strip() for line in out.splitlines() if line.strip().startswith(("tcp dport", "udp dport", "iifname"))]
    assert accepts == ["tcp dport 10022 accept", "tcp dport { 443 } accept"], accepts
```

The inventory's groups, the venue-facing filter and the daily pass's host sets:

`tests/test_pins_converged.py` — replace

```python
    assert groups["cache_host"] <= groups["observed"]
```

with

```python
    assert groups["cache_host"] <= groups["observed"]
    assert groups["mon_host"] == {"zcrypto-mon"} and groups["mon_host"] <= groups["observed"]
```

`tests/test_deploy_log_audit.py` — replace

```python
@pytest.mark.parametrize("host", ["nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"])
```

with

```python
@pytest.mark.parametrize("host", ["nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3", "zcrypto-mon"])
```

`tests/test_ops_daily.py` — replace

```python
    nodes = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"}
    assert set(rows) == {"zcrypto", "zcrypto-red", "zcrypto-ops", "nas"} | nodes, rows
```

with

```python
    nodes = {"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3", "zcrypto-mon"}
    assert set(rows) == {"zcrypto", "zcrypto-red", "zcrypto-ops", "nas"} | nodes, rows
```

`tests/test_ops_daily.py` — replace

```python
def test_every_published_ssh_destination_has_a_stanza_and_the_cache_nodes_match_the_inventory():
    repo = Path(__file__).resolve().parents[1]
    rows = dict(re.findall(r"^\| `([^`]+)` \| `ssh ([a-z0-9-]+)` \|", (repo / "docs/reference/fleet.md").read_text(), re.M))
    stanzas = _published_ssh_stanzas(repo)
    for fleet_host, destination in rows.items():
        assert destination in stanzas, (fleet_host, destination, sorted(stanzas))
    ansible = repo / "infra/ansible"
    group = yaml.safe_load((ansible / "group_vars/cache_host/vars.yml").read_text())
    for node in ("zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"):
        stanza = stanzas[rows[node]]
```

with

```python
def test_every_published_ssh_destination_has_a_stanza_and_the_linode_nodes_match_the_inventory():
    repo = Path(__file__).resolve().parents[1]
    rows = dict(re.findall(r"^\| `([^`]+)` \| `ssh ([a-z0-9-]+)` \|", (repo / "docs/reference/fleet.md").read_text(), re.M))
    stanzas = _published_ssh_stanzas(repo)
    for fleet_host, destination in rows.items():
        assert destination in stanzas, (fleet_host, destination, sorted(stanzas))
    ansible = repo / "infra/ansible"
    groups = {
        "zcrypto-valkey1": "cache_host",
        "zcrypto-valkey2": "cache_host",
        "zcrypto-valkey3": "cache_host",
        "zcrypto-mon": "mon_host",
    }
    for node, group_name in groups.items():
        group = yaml.safe_load((ansible / f"group_vars/{group_name}/vars.yml").read_text())
        stanza = stanzas[rows[node]]
```

`tests/test_ops_daily.py` — after

```python
def test_the_cache_allowlist_leaves_a_daemon_restart_on_ops_autonomous():
    assert ops_daily.classify_action("sudo systemctl restart docker", host="ops", resolve=_identity) is ops_daily.Tier.AUTONOMOUS
```

insert (the insert opens with 2 blank lines, kept)

```python


@pytest.mark.parametrize("host", ["zcrypto-mon", "mon"])
def test_the_observability_node_is_a_telemetry_host_under_either_of_its_names(host):
    step = "sudo systemctl restart alloy"
    assert ops_daily.classify_action(step, host=host, resolve=_identity) is ops_daily.Tier.AUTONOMOUS
    assert ops_daily.classify_action(f"ssh mon {step}", host=None, resolve=_identity) is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize(
    ("step", "host"),
    [
        ("sudo systemctl restart prometheus", "zcrypto-mon"),
        ("sudo systemctl restart loki", "zcrypto-mon"),
        ("sudo systemctl restart loki.service", "zcrypto-mon"),
        ("sudo systemctl stop grafana-server", "zcrypto-mon"),
        ("sudo systemctl start grafana-server", "zcrypto-mon"),
        ("sudo systemctl restart caddy", "zcrypto-mon"),
        ("ssh mon sudo systemctl restart prometheus", None),
        ("sudo systemctl restart alloy prometheus", "zcrypto-mon"),
    ],
)
def test_on_the_observability_node_a_restart_that_is_not_alloy_is_the_operators(step, host):
    """A store restarted under a running Grafana puts every rule that reads it in error, and a stopped Grafana or edge
    stops evaluation or ingest: each stays the operator's, in the order the node's runbook gives."""
    assert ops_daily.classify_action(step, host=host, resolve=_identity) is ops_daily.Tier.PREPARED
```

- [ ] **Step 3: Run the edited files and watch the new and re-pinned cases fail**

```bash
uv run pytest tests/test_converge_sh.py tests/test_deploy_log_audit.py tests/test_infra_converge_guards.py tests/test_infra_firewall_template.py tests/test_infra_unattended_upgrades.py tests/test_ops_daily.py tests/test_pins_converged.py tests/test_run_sh.py -q -p no:cacheprovider
```

Expected: `31 failed`, the rest passed, each failure for its own reason: seven `tests/test_run_sh.py` cases (the ring holds eight keys and `DEFAULT` nine, and the inventory has no `zcrypto-mon`); the three new `PUBLISHED` entries (`unknown host: zcrypto-mon`) and two of the three new `OUTSIDE` entries (`mon_host` is refused already, as an unknown host, so that one passes); the `zcrypto-mon` case of `test_venue_facing_drops_a_host_a_window_cannot_harm`; both cases of `test_the_other_public_nodes_bootstrap_under_the_capture_plays_guards` (the play's hosts are `capture_host:cache_host`); three firewall cases (the opener file does not exist); eight cases of `tests/test_infra_unattended_upgrades.py` (no `host_vars/zcrypto-mon`, no blacklist variable, no fourth host in the count's loop); four `tests/test_ops_daily.py` cases (no alias, no stanza, no telemetry host); and the pins case (`KeyError: 'mon_host'`). `test_on_the_observability_node_a_restart_that_is_not_alloy_is_the_operators` passes already, since an unknown host's restart is the operator's: Step 13's probes are what show it bites once the node is a telemetry host.

- [ ] **Step 4: Membership: the inventory, the group and host vars, the bootstrap play, the node's play and the base role**

`infra/ansible/inventory/hosts.yml` — replace

```yaml
        access_host: {}
        cache_host: {}
```

with

```yaml
        access_host: {}
        cache_host: {}
        mon_host: {}
```

`infra/ansible/inventory/hosts.yml` — replace

```yaml
        zcrypto-valkey3: {}
    workstation:
```

with

```yaml
        zcrypto-valkey3: {}
    # The observability node (spec 00121): Grafana, Prometheus, Loki, their Caddy edge and Alloy, as
    # packages. NEVER engine_host/capture_host — no trade key, no capture data.
    mon_host:
      hosts:
        zcrypto-mon: {}
    workstation:
```

Create `infra/ansible/group_vars/mon_host/vars.yml`:

```yaml
# bootstrap.yml's first play connects as root on 22 at play scope, since a new node has no
# zcrypto-deploy yet; every converge after it connects as below.
ansible_user: zcrypto-deploy
ansible_port: 10022
# ssh_hardening AllowUsers: no zcrypto-data here, since no NAS pull channel reaches this node.
hardening_ssh_allow_users: zcrypto-deploy root
# The fleet default force-enables ip_forward for Docker hosts; this node runs no container, so the
# hardening role's own default of 0 stands and only the two kernel keys are set.
hardening_extra_sysctl:
  kernel.dmesg_restrict: 1
  kernel.yama.ptrace_scope: 1
# The one public port beyond sshd: Caddy's 443, where the UI, the API and both ingest paths answer.
# 80 stays shut. Open a public port in the Linode Cloud Firewall by hand too.
firewall_extra_tcp_ports: [443]
```

Create `infra/ansible/host_vars/zcrypto-mon/vars.yml`:

```yaml
# The observability node: Linode 4 GB, Debian 13, in a region apart from the engine host's.
ansible_host: zcrypto-mon.zhaow.me
# The base role defaults to "zcrypto"; without this the node would converge to the primary's hostname.
base_hostname: zcrypto-mon
# 06:25 is 145 min past a 4 h bar boundary and an hour from the bridgehead's 05:25, the nearest slot.
# The node reboots by hand, so this is the attended window; the base role's collision assert reads it.
base_unattended_upgrades_reboot_time: "06:25"
# A reboot blanks rule evaluation for its duration. Patches install; the reboot is a human act, and
# the node's pending-reboot rule fires until it is taken.
base_unattended_upgrades_automatic_reboot: "false"
# Debian's package restarts the daemon on upgrade, and a store restarted under a running Grafana
# puts every rule that reads it in error. Upgraded in the monthly hand pass instead.
base_unattended_upgrades_package_blacklist: ["prometheus$"]
deploy_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/deploy_zcrypto-mon_ed25519.pub') }}"
```

`infra/ansible/bootstrap.yml` — replace

```yaml
- name: Bootstrap capture and cache hosts — deploy user + SSH lockdown (keep 22 until converge proves 10022)
  hosts: capture_host:cache_host
```

with

```yaml
- name: Bootstrap capture, cache and observability hosts — deploy user + SSH lockdown (keep 22 until converge proves 10022)
  hosts: capture_host:cache_host:mon_host
```

`infra/ansible/site.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

# spec 00121.
- name: converge the observability node — Grafana, its stores and the ingest edge
  hosts: mon_host
  become: true
  pre_tasks:
    - name: note — the observability node's charter
      ansible.builtin.debug:
        msg: >-
          The fleet's metrics, logs and alert evaluation on one node, with no containers: no trade
          key and no capture data. Its configuration is this play and one push of the rules and
          dashboards, so a lost node is rebuilt from the repository. Run bootstrap.yml first.
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
```

`infra/ansible/roles/base/tasks/main.yml` — replace

```yaml
# Fleet policy, pinned in config (spec 00050, spec 00051, spec 00118): no two hosts in the capture,
# ops and cache fleet may share an unattended-upgrades slot, because a same-night kernel reboot would
# take several down at once: a book gap with no surviving witness is permanent, and two cache nodes
# down leave one Sentinel, below its quorum of two. The slots come from `hostvars`, which resolves
```

with

```yaml
# Fleet policy, pinned in config (spec 00050, spec 00051, spec 00118, spec 00121): no two hosts in
# the capture, ops, cache and observability fleet may share an unattended-upgrades slot, because a
# same-night kernel reboot would take several down at once: a book gap with no surviving witness is
# permanent, two cache nodes down leave one Sentinel, below its quorum of two, and the observability
# node down leaves the other reboot unwatched. The slots come from `hostvars`, which resolves
```

`infra/ansible/roles/base/tasks/main.yml` — replace

```yaml
    base_fleet_hosts: "{{ (groups['capture_host'] | default([])) + (groups['ops_host'] | default([])) + (groups['cache_host'] | default([])) }}"
```

with

```yaml
    base_fleet_hosts: "{{ (groups['capture_host'] | default([])) + (groups['ops_host'] | default([])) + (groups['cache_host'] | default([])) + (groups['mon_host'] | default([])) }}"
```

`infra/ansible/roles/base/tasks/main.yml` — replace

```yaml
- name: configure unattended-upgrades — security pocket, auto-reboot, mail on failure only
```

with

```yaml
- name: configure unattended-upgrades — security pocket, the host's blacklist, auto-reboot, mail on failure only
```

`infra/ansible/roles/base/defaults/main.yml` — replace

```yaml
# This governs only the reboot; security patches install regardless. "true" keeps the cache nodes
# and the bridgehead automatic; group_vars/capture_host flips the two capture VPSes to attended
# (T0027, spec 00071 D4) and host_vars/zcrypto-ops flips the ops node. MUST be a QUOTED string: a
# bare YAML false renders as Python's "False", which apt reads as not-true.
base_unattended_upgrades_automatic_reboot: "true"
```

with

```yaml
# This governs only the reboot; security patches install regardless. "true" keeps the cache nodes
# and the bridgehead automatic; group_vars/capture_host flips the two capture VPSes to attended
# (T0027, spec 00071 D4), host_vars/zcrypto-ops flips the ops node and host_vars/zcrypto-mon the
# observability node. MUST be a QUOTED string: a bare YAML false renders as Python's "False", which
# apt reads as not-true.
base_unattended_upgrades_automatic_reboot: "true"

# Packages unattended-upgrades leaves alone on this host, each a Python regex matched from the start
# of the package name, so a bare name also holds every package it prefixes: end it with `$`.
base_unattended_upgrades_package_blacklist: []
```

`infra/ansible/roles/base/templates/50unattended-upgrades.j2` — replace (the block ends with 1 blank line, kept)

```
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename},label=Debian-security";
};

```

with (the block ends with 1 blank line, kept)

```
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename},label=Debian-security";
};
{% if base_unattended_upgrades_package_blacklist %}

Unattended-Upgrade::Package-Blacklist {
{% for package in base_unattended_upgrades_package_blacklist %}
        "{{ package }}";
{% endfor %}
};
{% endif %}

```

- [ ] **Step 5: The key ring, the converge whitelist and the key inventory**

`infra/ansible/scripts/run.sh` — replace

```bash
# A group, a comma list or no --limit keeps the listed order, the bridgehead's key fifth and the cache nodes'
# sixth to eighth: each of those converges under its own --limit only.
```

with

```bash
# A group, a comma list or no --limit keeps the listed order, the bridgehead's key fifth, the cache nodes'
# sixth to eighth and the observability node's ninth: each of those converges under its own --limit only.
```

`infra/ansible/scripts/run.sh` — replace

```bash
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519 files/deploy_zcrypto-valkey1_ed25519 files/deploy_zcrypto-valkey2_ed25519 files/deploy_zcrypto-valkey3_ed25519)
```

with

```bash
KEYS=(files/deploy_zcrypto_ed25519 files/deploy_zcrypto-red_ed25519 files/deploy_zcrypto-ops_ed25519 files/deploy_nas_ed25519 files/deploy_zaccess_ed25519 files/deploy_zcrypto-valkey1_ed25519 files/deploy_zcrypto-valkey2_ed25519 files/deploy_zcrypto-valkey3_ed25519 files/deploy_zcrypto-mon_ed25519)
```

`infra/ansible/scripts/converge.sh` — replace

```bash
# The four the deploy log records, plus `zaccess`: `infra/runbooks/zaccess.md` publishes its only
# converge, `--limit zaccess --tags access`; plus the three cache nodes, whose rollout (spec 00118
# D14) converges one node per run, so `cache_host` is not a host here.
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3"
# The five converged, plus `chrony`: `infra/runbooks/capture.md` prescribes re-converging that role
# as the repair for a stopped or hand-edited chrony on a capture host; plus the cache nodes' converges
# spec 00118 names: a node's first under the six base roles, the mesh's `firewall,cache-link` on a
# node or the engine host, and `cache` on a node.
TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link"
```

with

```bash
# The four the deploy log records, plus `zaccess`: `infra/runbooks/zaccess.md` publishes its only
# converge, `--limit zaccess --tags access`; plus the three cache nodes, whose rollout (spec 00118
# D14) converges one node per run, so `cache_host` is not a host here; plus the observability node
# (spec 00121).
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3 zcrypto-mon"
# The five converged, plus `chrony`: `infra/runbooks/capture.md` prescribes re-converging that role
# as the repair for a stopped or hand-edited chrony on a capture host; plus the cache nodes' converges
# spec 00118 names: a node's first under the six base roles, the mesh's `firewall,cache-link` on a
# node or the engine host, and `cache` on a node; plus `mon`, the observability node's own role,
# whose first converge names no tag.
TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link mon"
```

`infra/ansible/scripts/converge.sh` — replace

```bash
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9); spec
# 00120's two: the engine host's cache proxy digest, and the cache table's switch, the way back.
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset cache_proxy_image_digest engine_cache_enabled"
```

with

```bash
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9); spec
# 00120's two: the engine host's cache proxy digest, and the cache table's switch, the way back;
# spec 00121's one: the observability node's deliberate re-mint of its tools' Grafana token (D7).
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset cache_proxy_image_digest engine_cache_enabled mon_grafana_token_rotate"
```

`infra/ansible/files/README.md` — after

```markdown
| `deploy_zcrypto-valkey3_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-valkey3`; the workstation's `db3` alias |
```

insert

```markdown
| `deploy_zcrypto-mon_ed25519{,.pub}` | vaulted here (+ operator `~/.ssh`) | `run.sh`; `host_vars/zcrypto-mon`; the workstation's `mon` alias |
```

`infra/external-systems.md` — replace the text below, which is part of a longer line whose rest stays

```markdown
and, for the three cache nodes, `~/.ssh/deploy_zcrypto-valkey{1,2,3}_ed25519`, pubkeys recorded
```

with

```markdown
and, for the three cache nodes and the observability node, `~/.ssh/deploy_zcrypto-valkey{1,2,3}_ed25519` and `~/.ssh/deploy_zcrypto-mon_ed25519`, pubkeys recorded
```

`infra/external-systems.md` — after

```
Host db3
  HostName zcrypto-valkey3.zhaow.me
  Port 10022
  User zcrypto-deploy
  IdentityFile ~/.ssh/deploy_zcrypto-valkey3_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes
```

insert (the insert opens with 1 blank line, kept)

```

Host mon
  HostName zcrypto-mon.zhaow.me
  Port 10022
  User zcrypto-deploy
  IdentityFile ~/.ssh/deploy_zcrypto-mon_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes
```

- [ ] **Step 6: The instruments' host sets**

`infra/scripts/deploy-log-audit.py` — replace

```python
NO_VENUE_EXPOSURE = frozenset({"nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
```

with

```python
NO_VENUE_EXPOSURE = frozenset({"nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3", "zcrypto-mon"})
```

`infra/scripts/count-list.sh` — replace

```bash
  for h in zcrypto:capture_host zcrypto-red:capture_host zcrypto-ops:ops_host; do
```

with

```bash
  for h in zcrypto:capture_host zcrypto-red:capture_host zcrypto-ops:ops_host zcrypto-mon:mon_host; do
```

`infra/scripts/ops_daily.py` — replace

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

with

```python
# The ops host has three names -- the `host` label its rules carry, the fleet name its check rows
# print and the ssh destination -- and `zcrypto-red`, each cache node and the observability node two;
# `zaccess` has no bare-name destination.
_SSH_ALIASES = {
    "ops": "hp",
    "zcrypto-red": "red",
    "zcrypto-valkey1": "db1",
    "zcrypto-valkey2": "db2",
    "zcrypto-valkey3": "db3",
    "zcrypto-mon": "mon",
}
_HOST_LABELS = {
    "hp": "ops",
    "zcrypto-ops": "ops",
    "red": "zcrypto-red",
    "db1": "zcrypto-valkey1",
    "db2": "zcrypto-valkey2",
    "db3": "zcrypto-valkey3",
    "mon": "zcrypto-mon",
}
```

`infra/scripts/ops_daily.py` — replace

```python
_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
# A cache node's Docker daemon carries Valkey and Sentinel, so any other restart there can be a failover: the one
# object the pass may take is Alloy's container. An allowlist, because a container id names nothing a denylist matches.
_CACHE_HOSTS = frozenset({"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
_CACHE_AUTONOMOUS_OBJECTS = frozenset({"grafana-alloy"})
```

with

```python
_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess", "zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3", "zcrypto-mon"})
# A cache node's Docker daemon carries Valkey and Sentinel, so any other restart there can be a failover: the one
# object the pass may take is Alloy's container. An allowlist, because a container id names nothing a denylist matches.
_CACHE_HOSTS = frozenset({"zcrypto-valkey1", "zcrypto-valkey2", "zcrypto-valkey3"})
_CACHE_AUTONOMOUS_OBJECTS = frozenset({"grafana-alloy"})
# The observability node carries the evaluator, its two stores and the ingest edge, each restarted in an order its
# runbook gives: the one unit the pass may take is the node's own Alloy.
_MON_HOSTS = frozenset({"zcrypto-mon"})
_MON_AUTONOMOUS_OBJECTS = frozenset({"alloy", "alloy.service"})
```

`infra/scripts/ops_daily.py` — replace

```python
            if host_label(lands_on) in _CACHE_HOSTS and not (operands and _CACHE_AUTONOMOUS_OBJECTS.issuperset(operands)):
                operands = None
```

with

```python
            if host_label(lands_on) in _CACHE_HOSTS and not (operands and _CACHE_AUTONOMOUS_OBJECTS.issuperset(operands)):
                operands = None
            if host_label(lands_on) in _MON_HOSTS and not (operands and _MON_AUTONOMOUS_OBJECTS.issuperset(operands)):
                operands = None
```

- [ ] **Step 7: The fleet page**

`docs/reference/fleet.md` — after

```markdown
| `zcrypto-valkey3` | `ssh db3` | `cache_host`, `observed` | the engine's cache (spec `00118`): Valkey and its Sentinel, in a region apart from the engine host's, the copy a regional outage leaves | Linode VPS, 1 GB; no trade key, no capture data; Valkey and Sentinel listen on loopback and `zcache0` alone |
```

insert

```markdown
| `zcrypto-mon` | `ssh mon` | `mon_host`, `observed` | the observability node (spec `00121`): Grafana, Prometheus, Loki, their Caddy edge and the node's own Alloy, in a region apart from the engine host's | Linode VPS, 4 GB; no trade key, no capture data, no containers; holds the telemetry and the Slack webhook, and no key to another host |
```

`docs/reference/fleet.md` — replace

```markdown
- The capture VPSes and the ops node never reboot themselves: patches auto-install, and *Node · reboot pending, reboot by hand (capture, ops)* — a Grafana rule paging Slack — fires until you reboot (set: the three hosts' `base_unattended_upgrades_automatic_reboot`, in `host_vars` or their group's `group_vars`; count: `infra/scripts/count-list.sh attended-hosts-with-automatic-reboot`). Ops reboots by hand, in its 02:25 slot, with no capture gap and no canary order (`infra/runbooks/hosts.md#zcrypto-capture-reboot-pending`); the three `host_vars` slots — 21:25, 22:25 and ops' 02:25 — stay, read by the base role's window-collision assert.
```

with

```markdown
- The capture VPSes, the ops node and the observability node never reboot themselves: patches auto-install, and a Grafana rule paging Slack — *Node · reboot pending, reboot by hand (capture, ops)*, or the observability node's own — fires until you reboot (set: the four hosts' `base_unattended_upgrades_automatic_reboot`, in `host_vars` or their group's `group_vars`; count: `infra/scripts/count-list.sh attended-hosts-with-automatic-reboot`). Ops reboots by hand, in its 02:25 slot, with no capture gap and no canary order (`infra/runbooks/hosts.md#zcrypto-capture-reboot-pending`); the four `host_vars` slots (21:25, 22:25, 02:25, 06:25) stay, read by the base role's window-collision assert.
```

The Reboots bullet sits six characters under `tests/test_fleet_contracts.py`'s 700-character cap for a block; a word added to it is a word taken out of it.

- [ ] **Step 8: Run the edited files again**

Run Step 3's command.

Expected: no failure and no skip.

- [ ] **Step 9: The consumers**

```bash
uv run pytest tests/test_run_sh.py tests/test_converge_sh.py tests/test_deploy_log.py tests/test_infra_converge_guards.py tests/test_infra_unattended_upgrades.py tests/test_infra_firewall_template.py tests/test_pins_converged.py tests/test_deploy_log_audit.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_engine_soak.py tests/test_engine_flatten.py tests/test_fleet_contracts.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_merge_gate.py tests/test_grafana_auth.py tests/test_mint_with_vaulted_key_sh.py tests/test_probe_with_vaulted_key_sh.py tests/test_prune_host_images.py tests/test_infra_cache_templates.py tests/test_infra_cache_proxy.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_message_citations.py tests/test_scripts_have_tests.py tests/test_open_topics_frontmatter.py tests/test_config_selectors_are_parsed.py tests/test_internal_terms_not_operator_visible.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`4278 passed, 4 skipped` on the tree this plan was written against; the four skips are the files' own data and venue gates). `tests/test_prune_host_images.py` is in the run because it holds the pruner's host set equal to the hosts the pins file names and must stay green with the node in neither: the node takes no pins row. `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` must pass over `host_vars/zcrypto-mon` and `group_vars/mon_host`. The full suite is CI's, on the pull request.

- [ ] **Step 10: The commit gate**

Run: `uv run pre-commit run -a`

Expected: every hook Passed; re-run after any rewrite (ruff may reflow a tuple, `mdformat` owns `infra/external-systems.md`) until clean, then stage what it rewrote. The commit-msg hooks (`guidance-guard` over `docs/reference/fleet.md`, `message-citations`, `staged-kind`) run at Step 11.

- [ ] **Step 11: Commit**

```bash
git add infra/ansible/files/deploy_zcrypto-mon_ed25519 infra/ansible/files/deploy_zcrypto-mon_ed25519.pub \
  infra/ansible/files/README.md infra/ansible/inventory/hosts.yml infra/ansible/group_vars/mon_host/vars.yml \
  infra/ansible/host_vars/zcrypto-mon/vars.yml infra/ansible/bootstrap.yml infra/ansible/site.yml \
  infra/ansible/roles/base/tasks/main.yml infra/ansible/roles/base/defaults/main.yml \
  infra/ansible/roles/base/templates/50unattended-upgrades.j2 infra/ansible/scripts/run.sh \
  infra/ansible/scripts/converge.sh infra/scripts/deploy-log-audit.py infra/scripts/count-list.sh \
  infra/scripts/ops_daily.py infra/external-systems.md docs/reference/fleet.md \
  tests/test_run_sh.py tests/test_converge_sh.py tests/test_infra_converge_guards.py \
  tests/test_infra_unattended_upgrades.py tests/test_infra_firewall_template.py tests/test_pins_converged.py \
  tests/test_deploy_log_audit.py tests/test_ops_daily.py
git commit -F- <<'MSG'
feat(fleet): the observability node joins the inventory, the deploy-key ring and the hand-kept host lists

`zcrypto-mon` forms the `mon_host` group, a child of `observed`, converged as `zcrypto-deploy` on
10022 with `AllowUsers` naming no `zcrypto-data`, 443 its one opened port beside sshd's, and the
fleet's Docker `ip_forward` left off, since it runs no container. It has a plaintext `ansible_host`,
its hostname, its own deploy key and the reboot slot 06:25, which it takes by hand: patches install
and the node never reboots itself, as on the capture pair and ops. Its play in `site.yml` runs the
five base roles; the role that makes it the observability node lands in the next commit. The first
play of `bootstrap.yml` widens to `capture_host:cache_host:mon_host` with both refusals unchanged,
and the base role's window-collision assert reads the group beside the capture, ops and cache groups.

The base role's unattended-upgrades template takes a per-host package blacklist, rendered only
when the list is non-empty, so every other host's file is the one it has. The node's one entry is
`prometheus$`: Debian's package restarts the daemon on upgrade, under a Grafana that pages on an
evaluation error, and an entry is a regular expression matched from the start of the name.

The hand-kept lists gain the node: `run.sh`'s ring, ninth; `converge.sh`'s hosts, the tag `mon` and
the key `mon_grafana_token_rotate`; the deploy-log audit's `NO_VENUE_EXPOSURE`; the count of hosts
that reboot by hand; the daily pass's telemetry hosts with the alias `mon` in both alias maps, and
an allowlist of the one unit the pass may restart there, the node's own Alloy, every other restart
on it being the operator's; the workstation's `Host mon` stanza; the fleet page's Hosts row and
Reboots bullet.

Cases: the ring against the inventory and the key files; the node's `--limit` offering its key
first; three converges recorded (the bare limit, `--tags mon`, the token re-mint) and the group, a
component's name as a tag and a token as an operand refused; the bootstrap play's hosts and guards
for the cache and observability groups; the collision assert's four groups and the eight slots an
hour apart; the node's reboot by hand; an empty blacklist rendering today's file, the node's entry
anchored, no other host declaring one; the count entry's loop walking the node; the opener file
opening 443 and nothing else; the node dropped by `--venue-facing`; its telemetry tier under either
name and the restarts the pass leaves to the operator; every Linode node's ssh stanza against the
inventory.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 12: The tree is clean**

Run: `git status --porcelain`

Expected: empty. A plaintext private half left behind would show here as untracked; there is none, because operator step O0 encrypted it in place.

- [ ] **Step 13: Prove the guards with twenty-five probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time, never beside a pytest run in the same checkout. The controls: `run.sh`'s limit-first reorder emptied; a capture host renamed in the inventory; `converge.sh`'s unknown-host refusal reworded; the re-bootstrap assert inverted; the ops group renamed in the collision assert; the template's reboot-time line deleted; the role default's reboot flag flipped; the node's slot line deleted; the ops node's reboot flag flipped; the group's opener line deleted; the count's increment zeroed; the `--venue-facing` filter disabled; the telemetry gate disabled; a cache node's `HostName` changed in its stanza; a cache node's destination changed in the fleet page's row. The mutations remove or loosen each thing this task added, one at a time:

```bash
RING="tests/test_run_sh.py::test_no_limit_loads_every_fleet_key_in_the_listed_order tests/test_run_sh.py::test_a_single_host_limit_loads_every_key_with_that_hosts_first tests/test_run_sh.py::test_the_observability_node_limit_offers_its_key_first tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation"
INV="tests/test_run_sh.py::test_the_ring_is_every_inventory_host_but_the_workstation tests/test_pins_converged.py::test_the_inventory_expands_a_group_to_its_hosts_at_any_depth tests/test_infra_unattended_upgrades.py::test_the_observability_node_reboots_by_hand"
CONV="tests/test_converge_sh.py::test_every_invocation_this_fleet_publishes_records_its_operands tests/test_converge_sh.py::test_every_spelling_outside_the_grammar_is_refused_before_anything_runs"
BOOT="tests/test_infra_converge_guards.py::test_rebootstrap_refusal tests/test_infra_converge_guards.py::test_the_other_public_nodes_bootstrap_under_the_capture_plays_guards"
UU="tests/test_infra_unattended_upgrades.py"
OPS="tests/test_ops_daily.py::test_the_observability_node_is_a_telemetry_host_under_either_of_its_names tests/test_ops_daily.py::test_on_the_observability_node_a_restart_that_is_not_alloy_is_the_operators tests/test_ops_daily.py::test_the_ops_host_answers_both_kinds_of_step_under_either_of_its_names tests/test_ops_daily.py::test_the_ssh_aliases_are_the_fleet_tables_and_the_label_is_alloys"
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/run.sh \
  --control 's/^  ordered=("files\/deploy_\${LIMIT}_ed25519")$/  ordered=()/' \
  --mutation 's/ files\/deploy_zcrypto-mon_ed25519)$/)/' \
  -- uv run pytest $RING -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/inventory/hosts.yml \
  --control 's/^        zcrypto-red: {}$/        zcrypto-rot: {}/' \
  --mutation '/^        mon_host: {}$/d' \
  -- uv run pytest $INV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/inventory/hosts.yml \
  --control 's/^        zcrypto-red: {}$/        zcrypto-rot: {}/' \
  --mutation 's/^        zcrypto-mon: {}$/        zcrypto-mon2: {}/' \
  -- uv run pytest $INV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/ zcrypto-valkey3 zcrypto-mon"$/ zcrypto-valkey3"/' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/ cache cache-link mon"$/ cache cache-link"/' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh \
  --control 's/refuse "unknown host: \$LIMIT"/refuse "unknown node: \$LIMIT"/' \
  --mutation 's/ engine_cache_enabled mon_grafana_token_rotate"$/ engine_cache_enabled"/' \
  -- uv run pytest $CONV -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/bootstrap.yml \
  --control 's/that: bootstrap_deploy_user_probe.rc != 0 or rebootstrap/that: bootstrap_deploy_user_probe.rc == 0 or rebootstrap/' \
  --mutation 's/^  hosts: capture_host:cache_host:mon_host$/  hosts: capture_host:cache_host/' \
  -- uv run pytest $BOOT -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/base/tasks/main.yml \
  --control 's/ops_host/ops_hosts/' \
  --mutation 's/ + (groups\[.mon_host.\] | default(\[\]))//' \
  -- uv run pytest tests/test_infra_unattended_upgrades.py::test_the_collision_assert_reads_the_cache_group -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/base/templates/50unattended-upgrades.j2 \
  --control '/^Unattended-Upgrade::Automatic-Reboot-Time /d' \
  --mutation 's/^        "{{ package }}";$/        "{{ package }}"/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/base/templates/50unattended-upgrades.j2 \
  --control '/^Unattended-Upgrade::Automatic-Reboot-Time /d' \
  --mutation 's/^{% if base_unattended_upgrades_package_blacklist %}$/{% if true %}/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/roles/base/defaults/main.yml \
  --control 's/^base_unattended_upgrades_automatic_reboot: "true"$/base_unattended_upgrades_automatic_reboot: "false"/' \
  --mutation 's/^base_unattended_upgrades_package_blacklist: \[\]$/base_unattended_upgrades_package_blacklist: ["prometheus$"]/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-mon/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/"06:25"/"05:55"/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-mon/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/^base_unattended_upgrades_automatic_reboot: "false"$/base_unattended_upgrades_automatic_reboot: "true"/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-mon/vars.yml \
  --control '/^base_unattended_upgrades_reboot_time:/d' \
  --mutation 's/\["prometheus\$"\]/["prometheus"]/' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/host_vars/zcrypto-ops/vars.yml \
  --control 's/^base_unattended_upgrades_automatic_reboot: "false"$/base_unattended_upgrades_automatic_reboot: "true"/' \
  --mutation '$a base_unattended_upgrades_package_blacklist: ["docker-ce$"]' \
  -- uv run pytest $UU -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/ansible/group_vars/mon_host/vars.yml \
  --control '/^firewall_extra_tcp_ports:/d' \
  --mutation 's/^firewall_extra_tcp_ports: \[443\]$/firewall_extra_tcp_ports: [80, 443]/' \
  -- uv run pytest tests/test_infra_firewall_template.py -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/count-list.sh \
  --control 's/|| n=\$((n + 1))$/|| n=$((n + 0))/' \
  --mutation 's/ zcrypto-ops:ops_host zcrypto-mon:mon_host; do$/ zcrypto-ops:ops_host; do/' \
  -- uv run pytest tests/test_infra_unattended_upgrades.py::test_the_attended_hosts_count_walks_the_observability_node -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/deploy-log-audit.py \
  --control 's/if not (venue_facing_only and row.get("limit", "") in NO_VENUE_EXPOSURE)/if True/' \
  --mutation 's/, "zcrypto-mon"})/})/' \
  -- uv run pytest tests/test_deploy_log_audit.py::test_venue_facing_drops_a_host_a_window_cannot_harm -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation 's/"zcrypto-valkey3", "zcrypto-mon"})$/"zcrypto-valkey3"})/' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation '/^    "mon": "zcrypto-mon",$/d' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation '/^    "zcrypto-mon": "mon",$/d' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation 's/if host_label(lands_on) in _MON_HOSTS and not /if host_label(lands_on) in frozenset() and not /' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if operands is None and lands_on and host_label(lands_on) in _TELEMETRY_HOSTS:/if False:/' \
  --mutation 's/^_MON_AUTONOMOUS_OBJECTS = frozenset({"alloy", "alloy.service"})$/_MON_AUTONOMOUS_OBJECTS = frozenset({"alloy", "alloy.service", "prometheus"})/' \
  -- uv run pytest $OPS -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/external-systems.md \
  --control 's/^  HostName zcrypto-valkey3.zhaow.me$/  HostName zcrypto-valkey9.zhaow.me/' \
  --mutation 's/^  HostName zcrypto-mon.zhaow.me$/  HostName zcrypto-mon2.zhaow.me/' \
  -- uv run pytest tests/test_ops_daily.py::test_every_published_ssh_destination_has_a_stanza_and_the_linode_nodes_match_the_inventory -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file docs/reference/fleet.md \
  --control 's/^| `zcrypto-valkey3` | `ssh db3` |/| `zcrypto-valkey3` | `ssh db9` |/' \
  --mutation 's/^| `zcrypto-mon` | `ssh mon` |/| `zcrypto-mon` | `ssh mon2` |/' \
  -- uv run pytest $OPS -q -p no:cacheprovider
```

The `$RING`-style variables are left unquoted on purpose: each holds several node ids that must reach pytest as separate words. Expected: each of the twenty-five runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. If ruff's Step 10 rewrite changed the shape of a line a sed anchors on, that expression is re-anchored on the committed text before running, since a sed that matches nothing is refused as a no-op (rc 6), never scored. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 11 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, twenty-five runs, each KILLED with its control proven.
`infra/ansible/scripts/run.sh`, control the limit-first reorder emptied, over the ordering cases,
the node's own among them, and the ring case: the node's key dropped from the ring, KILLED,
control proven.
`infra/ansible/inventory/hosts.yml`, control a capture host renamed, over the ring, pins-inventory
and reboot cases: `mon_host` removed from `observed`, KILLED, control proven; the node renamed in
its group, KILLED, control proven. `infra/ansible/scripts/converge.sh`, control the unknown-host
refusal reworded, over the published and outside-the-grammar cases: the node dropped from the
hosts, KILLED, control proven; `mon` dropped from the tags, KILLED, control proven;
`mon_grafana_token_rotate` dropped from the keys, KILLED, control proven.
`infra/ansible/bootstrap.yml`, control the re-bootstrap assert inverted: the play narrowed back to
`capture_host:cache_host`, KILLED, control proven. `infra/ansible/roles/base/tasks/main.yml`,
control the ops group renamed: the observability group dropped from the collision assert, KILLED,
control proven. The base role's unattended-upgrades template, control its reboot-time line deleted:
an entry rendered without its semicolon, KILLED, control proven; the block rendered for an empty
list, KILLED, control proven. The base role's defaults, control the reboot flag flipped: a default
blacklist entry, KILLED, control proven. The node's `host_vars`, control its slot deleted: the slot
30 min from the bridgehead's, KILLED, control proven; the automatic reboot switched on, KILLED,
control proven; the entry's `$` dropped, KILLED, control proven. The ops node's `host_vars`, control
its reboot flag flipped: a blacklist declared on a second host, KILLED, control proven.
`group_vars/mon_host`, control the opener deleted: port 80 opened beside 443, KILLED, control
proven. `infra/scripts/count-list.sh`, control the increment zeroed: the node dropped from the
loop, KILLED, control proven.
`infra/scripts/deploy-log-audit.py`, control the venue-facing filter disabled: the node dropped
from `NO_VENUE_EXPOSURE`, KILLED, control proven. `infra/scripts/ops_daily.py`, control the
telemetry gate disabled: the node dropped from the telemetry hosts, KILLED, control proven; `mon`
dropped from the label map, KILLED, control proven; the node dropped from the alias map, KILLED,
control proven; the node's allowlist bypassed, KILLED, control proven; `prometheus` added to it,
KILLED, control proven. `infra/external-systems.md`, control a cache node's `HostName` changed,
over the stanza case: the node's `HostName` changed, KILLED, control proven.
`docs/reference/fleet.md`, control a cache node's destination changed: the node's destination
changed, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 2: The mon role's core: the packages, the two stores, Grafana hardened behind its own login, and Caddy as the one public listener

**Files:**
- Create: `infra/ansible/roles/mon/defaults/main.yml`
- Create: `infra/ansible/roles/mon/templates/grafana.ini.j2`
- Create: `infra/ansible/roles/mon/templates/Caddyfile.j2`
- Create: `infra/ansible/roles/mon/templates/prometheus.default.j2`
- Create: `infra/ansible/roles/mon/templates/prometheus.yml.j2`
- Create: `infra/ansible/roles/mon/templates/loki-config.yml.j2`
- Create: `infra/ansible/roles/mon/templates/grafana-server.dropin.conf.j2`
- Create: `infra/ansible/roles/mon/templates/datasources.yml.j2`
- Create: `infra/ansible/roles/mon/templates/folder-anchor.yml.j2`
- Create: `infra/ansible/roles/mon/tasks/main.yml`
- Create: `infra/ansible/roles/mon/handlers/main.yml`
- Modify: `infra/ansible/site.yml` (the `mon` role's line appended to the node's play)
- Test (new): `tests/test_infra_mon_role.py`
- Test: `tests/test_infra_converge_guards.py` (`test_every_register_a_preview_guard_reads_is_set_in_its_own_role` reads a preview fact's registers too)

**Interfaces:**
- Consumes: Task 1's play in `site.yml` and its group and host vars; the five vault values the Rollout's P2 writes, by these names: `mon_grafana_admin_user`, `mon_grafana_admin_password`, `mon_grafana_secret_key`, `mon_ingest_fleet_password_hash`, `mon_ingest_logship_password_hash` (the tests supply stand-ins; no task here reads the vault); the test helpers of `tests/test_infra_converge_guards.py` (`load_tasks`, `iter_tasks`, `find_task`, `when_conditions`, `truthy`, `set_facts`, `assert_that`).
- Produces, for Tasks 3, 4 and 7 and the Rollout to use by these exact names: the role `mon` under the tag `mon`; the defaults `mon_hostname`, `mon_grafana_port`, `mon_prometheus_port`, `mon_loki_port`, `mon_retention_days`, `mon_folder_uid`, `mon_prom_ds_uid`, `mon_loki_ds_uid`, `mon_ingest_fleet_user`, `mon_ingest_logship_user`; the preview facts `mon_repos_previewed` and `mon_units_previewed`, which every later task of the role that needs an installed package or unit gates on; the handlers `restart prometheus`, `restart loki`, `restart grafana`, `reload caddy`, `reload systemd`; `tests/test_infra_mon_role.py`, to which Task 4 appends.

**What this task decides, where the spec leaves it open:**
- The role installs before it renders. Debian's `prometheus` and Grafana's `loki` start at install with their packaged configs, behind the firewall the play's `firewall` role has already rendered; the role then renders the loopback configs, each validated by the installed binary before it replaces the live file (`promtool check config`, `loki -verify-config`, `caddy validate`), and the handlers restart the stores. `grafana-server` is not started by its package, so its first start is the role's, after its ini, the three files the ini reads through `$__file{}`, its provisioning and its drop-in are in place and after `meta: flush_handlers` has put both stores on their rendered configs.
- The preview's two cases are two facts, not a condition repeated on each task: `mon_repos_previewed` (a check-mode run in which a repository would be added, so `apt` cannot see the packages) and `mon_units_previewed` (a check-mode run in which a package would be installed, so systemd cannot see its unit). The existing guard `test_every_register_a_preview_guard_reads_is_set_in_its_own_role` reads registers out of `when:` gates alone, so it is widened to read a fact whose value names check mode as well; without that it would refuse the role for reading none.
- No task clears a `dpkg` hold or pins a version, and `prometheus` is installed with `install_recommends: false`, which keeps Debian's node exporter off the node: the node's own Alloy carries the host metrics (Task 4).
- Caddy listens on 443 alone: `auto_https disable_redirects` and the ACME issuer's `disable_http_challenge` leave port 80 unbound, which leaves TLS-ALPN on 443 as the one challenge the certificate can be issued over. Issuance itself is first proven on the node, by R5's reads. The ACME account address is the access role's own default, repeated as `mon_acme_email`.
- The 404 matcher is `path /metrics /metrics/* /swagger*`, placed after the two ingest handles and before the fallback: Grafana serves `/metrics`, a second metrics tree per plugin under `/metrics/plugins/` and its API browser under `/swagger` without a login. `/api/health` is not special-cased and reaches Grafana with the rest.
- The admin login's name is a third vaulted value, `mon_grafana_admin_user`, generated by the Rollout's P2 and read through `$__file{}` as the password is. Grafana's lockout is by account name, so under the default name a stranger's guesses would keep the role's sign-in and the owner's locked; a sign-in under a name that is not the account's leaves the account unlocked. Grafana reads the name only when it creates its database: the vaulted name is stable across rebuilds, as the password is.
- `[plugins] preinstall_disabled = true`. Grafana 13.2 carries its Prometheus and Loki datasources as plugins bundled with the package, and its preinstaller, on by default, downloads further plugins from grafana.com at every start and replaces the bundled ones with a newer release. Disabled, the two datasources are the package's own copies, they change only when the package is upgraded, and a start reaches no other site.
- The two generated secrets are refused by name unless they are 32 or more letters and digits, the admin login's name unless it is its generator's shape, `u` and 16 hex digits, which no name a stranger tries is, and the two hashes unless they are a bcrypt string, each pattern ending `\Z`; the refusal is the role's first task and names the key, never the value.
- Grafana's unit waits for readiness in two `ExecStartPre` lines, `curl` against Prometheus's `/-/ready` and Loki's `/ready` with forty retries three seconds apart, under `TimeoutStartSec=600`; `curl` is installed with `prometheus` for it. `OOMScoreAdjust=-500` sits Grafana below the stores' default of 0.
- Loki's schema starts `2020-10-24`, the upstream example's date, so every line the node ever takes falls in the one v13 period.
- The folder's provider reads an empty directory the role creates: the folder exists under its uid and nothing is provisioned into it, so every dashboard stays editable through the API the push uses.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_infra_mon_role.py`:

```python
"""The observability node's role, read without a host: its templates rendered through Ansible's own templar over
the role's defaults, and its task and handler conditions evaluated the same way. What only a converge can show --
a package's first start, certificate issuance, the edge's answers -- is the node's acceptance, not this file."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import assert_that, find_task, iter_tasks, load_tasks, set_facts, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/mon"
TASKS = ROLE / "tasks/main.yml"
HANDLERS = ROLE / "handlers/main.yml"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
PUSH = REPO / "infra/scripts/grafana-push.sh"
# Shaped like what the generator writes; none is a credential.
SECRETS = {
    "mon_grafana_admin_user": "u" + "0123456789abcdef",
    "mon_grafana_admin_password": "A" * 48,
    "mon_grafana_secret_key": "B" * 48,
    "mon_ingest_fleet_password_hash": "$2b$10$" + "f" * 53,
    "mon_ingest_logship_password_hash": "$2b$10$" + "l" * 53,
}


def _variables(**extra) -> dict:
    # A default that templates another variable is trusted, so it resolves the way the play resolves it; the one
    # that looks up the controller's environment is left out, since no template here reads it.
    defaults = {
        k: trust_as_template(v) if isinstance(v, str) and "{{" in v else v for k, v in DEFAULTS.items() if k != "mon_token_cache"
    }
    return {**defaults, **SECRETS, **extra}


def _render(name: str, **extra) -> str:
    text = (ROLE / "templates" / name).read_text()
    return Templar(loader=DataLoader(), variables=_variables(**extra)).template(trust_as_template(text))


def _ini() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(_render("grafana.ini.j2"))
    return parser


# --- grafana.ini: the settings a public login rests on -----------------------------------------------------------
@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("server", "http_addr", "127.0.0.1"),
        ("server", "root_url", "https://zcrypto-mon.zhaow.me/"),
        ("security", "admin_user", "$__file{/etc/grafana/admin_user}"),
        ("security", "admin_password", "$__file{/etc/grafana/admin_password}"),
        ("security", "secret_key", "$__file{/etc/grafana/secret_key}"),
        ("security", "cookie_secure", "true"),
        ("security", "cookie_samesite", "strict"),
        ("security", "disable_brute_force_login_protection", "false"),
        ("auth", "disable_login_form", "false"),
        ("auth.basic", "enabled", "false"),
        ("auth.anonymous", "enabled", "false"),
        ("auth.anonymous", "hide_version", "true"),
        ("auth.proxy", "enabled", "false"),
        ("auth.jwt", "enabled", "false"),
        ("users", "allow_sign_up", "false"),
        ("users", "allow_org_create", "false"),
        ("snapshots", "enabled", "false"),
        ("snapshots", "external_enabled", "false"),
        ("public_dashboards", "enabled", "false"),
        ("plugins", "plugin_admin_enabled", "false"),
        ("plugins", "preinstall_disabled", "true"),
        ("feature_toggles", "sqlExpressions", "false"),
        ("database", "wal", "true"),
        ("unified_alerting.state_history", "backend", "loki"),
        ("unified_alerting.state_history", "loki_remote_url", "http://127.0.0.1:3100"),
        ("analytics", "reporting_enabled", "false"),
        ("analytics", "check_for_updates", "false"),
        ("analytics", "check_for_plugin_updates", "false"),
    ],
)
def test_the_ini_carries_what_the_public_login_rests_on(section, key, value):
    ini = _ini()
    assert ini.has_option(section, key), f"[{section}] {key} is not set, so Grafana's own default stands"
    assert ini.get(section, key) == value


def test_the_ini_names_the_secret_files_and_carries_none_of_their_values():
    rendered = _render("grafana.ini.j2")
    for name in ("mon_grafana_admin_user", "mon_grafana_admin_password", "mon_grafana_secret_key"):
        assert SECRETS[name] not in rendered, f"{name} is rendered into grafana.ini"
    files = find_task(load_tasks(TASKS), "grafana's admin name and two secrets, each a file read through $__file{}")
    copy = files["ansible.builtin.copy"]
    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "grafana", "0640"), copy
    assert files["no_log"] is True
    assert {(item["file"], item["value"]) for item in files["loop"]} == {
        ("admin_user", "{{ mon_grafana_admin_user }}"),
        ("admin_password", "{{ mon_grafana_admin_password }}"),
        ("secret_key", "{{ mon_grafana_secret_key }}"),
    }
    assert copy["dest"] == "/etc/grafana/{{ item.file }}"


# --- the Caddyfile: one public name, two authenticated ingest paths, two refusals --------------------------------
def _blocks(lines: list[str]) -> list[tuple[str, list]]:
    """A Caddyfile body as (line, children) pairs: a line ending in `{` opens a block its `}` closes."""
    out: list[tuple[str, list]] = []
    stack = [out]
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "}":
            stack.pop()
        elif line.endswith("{"):
            children: list = []
            stack[-1].append((line[:-1].strip(), children))
            stack.append(children)
        else:
            stack[-1].append((line, []))
    assert len(stack) == 1, "unbalanced braces"
    return out


def _caddyfile() -> dict[str, list]:
    return dict(_blocks(_render("Caddyfile.j2").splitlines()))


def _site() -> dict[str, list]:
    caddyfile = _caddyfile()
    assert set(caddyfile) == {"", DEFAULTS["mon_hostname"]}, f"one global block and one site: {sorted(caddyfile)}"
    return dict(caddyfile[DEFAULTS["mon_hostname"]])


def _users(handle: list) -> list[str]:
    (auth,) = [children for line, children in handle if line == "basic_auth"]
    for _user, children in auth:
        assert children == []
    users = [line.split() for line, _ in auth]
    for user, hashed in users:
        assert re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", hashed), f"{user} carries something that is not a bcrypt hash"
    return [user for user, _ in users]


def _upstream(handle: list) -> str:
    (proxy,) = [line for line, _ in handle if line.startswith("reverse_proxy ")]
    return proxy.split()[1]


def test_remote_write_takes_the_fleet_user_alone_and_reaches_prometheus():
    handle = _site()["handle /api/v1/write"]
    assert _users(handle) == ["fleet"]
    assert _upstream(handle) == "127.0.0.1:9090"


def test_the_loki_push_takes_both_ingest_users_and_reaches_loki():
    handle = _site()["handle /loki/api/v1/push"]
    assert _users(handle) == ["fleet", "logship"]
    assert _upstream(handle) == "127.0.0.1:3100"


def test_the_two_paths_grafana_serves_without_a_login_answer_404_at_the_edge():
    site = _site()
    matchers = {line: None for line in site if line.startswith("@")}
    assert list(matchers) == ["@served_without_a_login path /metrics /metrics/* /swagger*"], list(matchers)
    assert site["handle @served_without_a_login"] == [("respond 404", [])]


def test_everything_else_goes_to_grafana_with_no_credential_added():
    site = _site()
    assert site["handle"] == [("reverse_proxy 127.0.0.1:3000", [])]
    handles = [line for line in site if line.startswith("handle")]
    assert handles == ["handle /api/v1/write", "handle /loki/api/v1/push", "handle @served_without_a_login", "handle"], handles


def test_the_edge_listens_on_443_alone_and_takes_its_certificate_there():
    caddyfile = _caddyfile()
    assert ("auto_https disable_redirects", []) in caddyfile[""], "the redirect listener would bind port 80"
    assert dict(_site())["tls"] == [("issuer acme", [("disable_http_challenge", [])])]
    assert not re.search(r"(?m)^\s*(http://|:80\b)", _render("Caddyfile.j2"))


def test_the_caddyfile_is_validated_before_it_replaces_the_live_one_and_never_shown():
    task = find_task(
        load_tasks(TASKS), "Caddyfile — the two ingest paths behind basic auth, two refusals, everything else to grafana"
    )
    template = task["ansible.builtin.template"]
    assert template["validate"] == "caddy validate --adapter caddyfile --config %s"
    assert (template["owner"], template["group"], template["mode"]) == ("root", "caddy", "0640")
    assert task["no_log"] is True and task["diff"] is False, "the diff of a preview would print the hashes"


# --- the stores: loopback, the retention, no scrape job ----------------------------------------------------------
def test_prometheus_is_a_loopback_receiver_kept_ninety_days():
    (args,) = re.findall(r'^ARGS="(.*)"$', _render("prometheus.default.j2"), re.M)
    assert args.split() == [
        "--web.listen-address=127.0.0.1:9090",
        "--web.enable-remote-write-receiver",
        "--storage.tsdb.retention.time=90d",
        "--storage.tsdb.retention.size=8GB",
    ]
    config = yaml.safe_load(_render("prometheus.yml.j2"))
    assert config == {"storage": {"tsdb": {"out_of_order_time_window": "8h"}}}, config


def test_loki_is_a_loopback_single_binary_whose_compactor_enforces_the_same_retention():
    config = yaml.safe_load(_render("loki-config.yml.j2"))
    server = config["server"]
    assert (server["http_listen_address"], server["grpc_listen_address"]) == ("127.0.0.1", "127.0.0.1")
    assert (server["http_listen_port"], config["auth_enabled"]) == (3100, False)
    assert config["common"]["path_prefix"] == "/var/lib/loki"
    assert config["common"]["storage"]["filesystem"]["chunks_directory"] == "/var/lib/loki/chunks"
    (schema,) = config["schema_config"]["configs"]
    assert (schema["store"], schema["object_store"], schema["schema"], schema["index"]["period"]) == (
        "tsdb",
        "filesystem",
        "v13",
        "24h",
    )
    compactor = config["compactor"]
    assert compactor["retention_enabled"] is True and compactor["delete_request_store"] == "filesystem"
    assert config["limits_config"]["retention_period"] == f"{DEFAULTS['mon_retention_days'] * 24}h" == "2160h"
    assert config["analytics"]["reporting_enabled"] is False


@pytest.mark.parametrize(
    ("name", "validate"),
    [
        ("prometheus config — no scrape job, the out-of-order window", "promtool check config %s"),
        ("loki config — loopback, filesystem storage, the compactor's retention", "loki -verify-config -config.file %s"),
    ],
)
def test_a_store_config_is_validated_by_the_installed_binary_before_it_lands(name, validate):
    assert find_task(load_tasks(TASKS), name)["ansible.builtin.template"]["validate"] == validate


# --- the evaluator never starts ahead of its stores --------------------------------------------------------------
def test_grafana_starts_after_its_stores_and_waits_for_both_to_be_ready():
    unit = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    unit.optionxform = str
    dropin = _render("grafana-server.dropin.conf.j2")
    unit.read_string("\n".join(line for line in dropin.splitlines() if not line.startswith("ExecStartPre=")))
    assert unit.get("Unit", "After").split() == ["prometheus.service", "loki.service"]
    waits = [line.removeprefix("ExecStartPre=") for line in dropin.splitlines() if line.startswith("ExecStartPre=")]
    assert [wait.split()[-1] for wait in waits] == ["http://127.0.0.1:9090/-/ready", "http://127.0.0.1:3100/ready"]
    for wait in waits:
        assert wait.split()[:2] == ["/usr/bin/curl", "-fsS"] and "--retry-all-errors" in wait.split(), wait
    assert int(unit.get("Service", "OOMScoreAdjust")) < 0, "the stores keep the default of 0, and Grafana must rank below them"
    install = find_task(load_tasks(TASKS), "prometheus present, from Debian main, without the node exporter it recommends")
    assert "curl" in install["ansible.builtin.apt"]["name"], "the drop-in's wait runs a curl the role never installed"


def test_a_store_is_restarted_with_grafana_stopped_around_it():
    handlers = yaml.safe_load(HANDLERS.read_text())
    names = [handler["name"] for handler in handlers]
    order = ["stop grafana around a store restart", "restart prometheus", "restart loki", "restart grafana"]
    assert [name for name in names if name in order] == order, names
    by_name = {handler["name"]: handler for handler in handlers}
    for name, state in (("stop grafana around a store restart", "stopped"), ("restart grafana", "restarted")):
        handler = by_name[name]
        assert handler["ansible.builtin.systemd_service"] == {"name": "grafana-server", "state": state} | (
            {"daemon_reload": True} if state == "restarted" else {}
        )
        assert handler["listen"] == ["restart prometheus", "restart loki"], handler
    assert names.index("reload systemd") < names.index("restart grafana"), "the drop-in would be restarted into unread"


def test_the_stores_are_running_their_rendered_configs_before_grafana_is_started():
    tasks = load_tasks(TASKS)
    names = [task.get("name") for task in tasks]
    flush = names.index("apply the pending store and grafana restarts")
    assert tasks[flush] == {"name": names[flush], "ansible.builtin.meta": "flush_handlers"}
    assert names.index("prometheus and loki enabled + started") < flush < names.index("grafana-server enabled + started")
    rendered_before = [
        "prometheus flags — loopback, the receiver, the retention",
        "loki config — loopback, filesystem storage, the compactor's retention",
        "grafana.ini",
        "grafana's admin name and two secrets, each a file read through $__file{}",
        "the two datasources, file-provisioned read-only under the uids the rule file names",
        "the folder the push writes into, anchored under its uid",
        "grafana-server drop-in — after its stores, waiting for both to be ready",
    ]
    assert all(names.index(name) < flush for name in rendered_before)


# --- provisioning: the uids the push, the dashboards and the tools already name ----------------------------------
def _push_default(name: str) -> str:
    (value,) = re.findall(rf'^export {name}="\$\{{{name}:-([^}}]+)\}}"$', PUSH.read_text(), re.M)
    return value


def test_the_two_datasources_are_read_only_under_the_uids_the_push_defaults_to():
    provisioned = yaml.safe_load(_render("datasources.yml.j2"))
    assert provisioned["prune"] is True
    by_uid = {source["uid"]: source for source in provisioned["datasources"]}
    assert set(by_uid) == {_push_default("GRAFANA_PROM_DS_UID"), _push_default("GRAFANA_LOKI_DS_UID")}
    prom, loki = by_uid[_push_default("GRAFANA_PROM_DS_UID")], by_uid[_push_default("GRAFANA_LOKI_DS_UID")]
    assert (prom["type"], prom["url"], prom["editable"]) == ("prometheus", "http://127.0.0.1:9090", False)
    assert (loki["type"], loki["url"], loki["editable"]) == ("loki", "http://127.0.0.1:3100", False)


def test_the_folder_is_anchored_under_the_uid_the_push_defaults_to_and_nothing_is_provisioned_into_it():
    (provider,) = yaml.safe_load(_render("folder-anchor.yml.j2"))["providers"]
    assert provider["folderUid"] == _push_default("GRAFANA_ALERT_FOLDER_UID")
    assert provider["options"]["path"] == DEFAULTS["mon_folder_anchor_dir"]
    assert sorted(p.name for p in (ROLE / "templates").iterdir() if "dashboard" in p.name or "alert" in p.name) == []
    assert not (ROLE / "files").exists() or not list((ROLE / "files").glob("*.json"))


# --- packages: followed from apt, loki from Grafana's repository alone -------------------------------------------
_POLICY_GRAFANA = """loki:
  Installed: (none)
  Candidate: 3.7.8
  Version table:
     3.7.8 500
        500 https://apt.grafana.com stable/main amd64 Packages
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_INSTALLED = """loki:
  Installed: 3.7.8
  Candidate: 3.7.8
  Version table:
 *** 3.7.8 500
        500 https://apt.grafana.com stable/main amd64 Packages
        100 /var/lib/dpkg/status
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_DEBIAN = """loki:
  Installed: (none)
  Candidate: 2.4.7.4-12
  Version table:
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""
_POLICY_DEBIAN_PINNED = """loki:
  Installed: (none)
  Candidate: 2.4.7.4-12
  Version table:
     3.7.8 100
        100 https://apt.grafana.com stable/main amd64 Packages
     2.4.7.4-12 500
        500 http://deb.debian.org/debian trixie/main amd64 Packages"""


@pytest.mark.parametrize(
    ("policy", "admitted"),
    [(_POLICY_GRAFANA, True), (_POLICY_INSTALLED, True), (_POLICY_DEBIAN, False), (_POLICY_DEBIAN_PINNED, False), ("", False)],
    ids=["grafana's", "installed", "debian's", "debian's by priority", "no output"],
)
def test_loki_is_installed_only_when_apts_candidate_is_grafanas(policy, admitted):
    task = find_task(load_tasks(TASKS), "refuse a loki candidate that does not come from apt.grafana.com")
    variables = {**{k: trust_as_template(v) for k, v in task["vars"].items()}, "mon_loki_policy": {"stdout": policy}}
    assert truthy(assert_that(task), variables) is admitted


def test_no_package_is_forced_held_or_pinned_to_a_version():
    installs = [task["ansible.builtin.apt"] for task, _ in iter_tasks(load_tasks(TASKS)) if "ansible.builtin.apt" in task]
    names = sorted(name for task, _ in iter_tasks(load_tasks(TASKS)) for name in _apt_names(task))
    assert names == ["alloy", "caddy", "curl", "grafana", "loki", "prometheus"], names
    for apt in installs:
        assert apt.get("state", "present") == "present" and "allow_downgrade" not in apt and "force" not in apt, apt
    assert all("=" not in name for name in names)
    modules = {key for task, _ in iter_tasks(load_tasks(TASKS)) for key in task}
    assert "ansible.builtin.dpkg_selections" not in modules, "a hold makes `apt upgrade` skip a package silently"
    recommends = find_task(load_tasks(TASKS), "prometheus present, from Debian main, without the node exporter it recommends")
    assert recommends["ansible.builtin.apt"]["install_recommends"] is False


# --- the preview on a node that has nothing yet ------------------------------------------------------------------
_CHANGED, _UNCHANGED, _SKIPPED = {"changed": True}, {"changed": False}, {"changed": False, "skipped": True}


# The second fact is true when any one of four things is: each has a case in which it alone is.
@pytest.mark.parametrize(
    ("check", "repos", "debian", "grafana", "caddy", "expected"),
    [
        (True, _CHANGED, _CHANGED, _SKIPPED, _SKIPPED, (True, True)),  # a fresh node's preview
        (True, _CHANGED, _UNCHANGED, _SKIPPED, _SKIPPED, (True, True)),  # the repositories alone still to write
        (True, _UNCHANGED, _CHANGED, _UNCHANGED, _UNCHANGED, (False, True)),  # prometheus alone still to install
        (True, _UNCHANGED, _UNCHANGED, _CHANGED, _UNCHANGED, (False, True)),  # a Grafana package alone
        (True, _UNCHANGED, _UNCHANGED, _UNCHANGED, _CHANGED, (False, True)),  # caddy alone
        (True, _UNCHANGED, _UNCHANGED, _UNCHANGED, _UNCHANGED, (False, False)),  # an established node's preview
        (False, _CHANGED, _CHANGED, _CHANGED, _CHANGED, (False, False)),  # the real first converge
    ],
)
def test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find(check, repos, debian, grafana, caddy, expected):
    tasks = load_tasks(TASKS)
    variables = {"ansible_check_mode": check, "mon_grafana_repo": repos, "mon_caddy_repo": _UNCHANGED}
    first = set_facts(find_task(tasks, "note a preview that runs before the repositories exist"), variables)
    variables |= first | {"mon_debian_install": debian, "mon_grafana_install": grafana, "mon_caddy_install": caddy}
    second = set_facts(find_task(tasks, "note a preview that runs before the packages are installed"), variables)
    assert (bool(first["mon_repos_previewed"]), bool(second["mon_units_previewed"])) == expected


def _apt_names(task: dict) -> set[str]:
    name = task.get("ansible.builtin.apt", {}).get("name", [])
    return {name} if isinstance(name, str) else set(name)


def test_what_needs_a_repository_or_a_unit_skips_the_preview_that_has_neither():
    tasks = iter_tasks(load_tasks(TASKS))
    units = [(task["name"], gates) for task, gates in tasks if "ansible.builtin.systemd_service" in task]
    assert len(units) >= 3, units
    for name, gates in units:
        # Held whole: an inverted gate names the fact too, and it would skip every real converge.
        timer = len(gates) == 1 and re.fullmatch(r"not \(ansible_check_mode and mon_[a-z_]+_timer_install is changed\)", gates[0])
        assert gates == ("not mon_units_previewed",) or timer, (name, gates)
    third_party = [gates for task, gates in tasks if _apt_names(task) & {"grafana", "loki", "alloy", "caddy"}]
    assert len(third_party) == 2 and all(gates == ("not mon_repos_previewed",) for gates in third_party), third_party
    origin = find_task(load_tasks(TASKS), "refuse a loki candidate that does not come from apt.grafana.com")
    assert when_conditions(origin) == ["not mon_repos_previewed"]
    for handler in yaml.safe_load(HANDLERS.read_text()):
        if "name" in handler.get("ansible.builtin.systemd_service", {}):
            assert when_conditions(handler) == ["not mon_units_previewed"], handler["name"]


# --- the vaulted secrets: refused by name when missing or misshapen ----------------------------------------------
@pytest.mark.parametrize(
    ("override", "refused"),
    [
        ({}, None),
        ({"mon_grafana_admin_user": "root"}, "mon_grafana_admin_user"),
        ({"mon_grafana_admin_user": "administrator"}, "mon_grafana_admin_user"),
        ({"mon_grafana_admin_password": None}, "mon_grafana_admin_password"),
        ({"mon_grafana_admin_password": "short"}, "mon_grafana_admin_password"),
        ({"mon_grafana_secret_key": "has a space in it, which a generator never writes"}, "mon_grafana_secret_key"),
        ({"mon_ingest_fleet_password_hash": "A" * 48}, "mon_ingest_fleet_password_hash"),
        (
            {"mon_ingest_logship_password_hash": SECRETS["mon_ingest_logship_password_hash"] + "\n"},
            "mon_ingest_logship_password_hash",
        ),
    ],
    ids=[
        "all five",
        "a name a stranger tries",
        "a long name a stranger tries",
        "one missing",
        "too short",
        "not letters and digits",
        "a password where a hash belongs",
        "a trailing newline",
    ],
)
def test_a_missing_or_misshapen_secret_is_refused_by_its_key(override, refused):
    task = load_tasks(TASKS)[0]
    assert task["name"] == "refuse a missing or misshapen secret, naming the key and never the value"
    values = {k: v for k, v in {**SECRETS, **override}.items() if v is not None}
    templar = Templar(loader=DataLoader(), variables=values)
    faults = templar.template(trust_as_template(task["vars"]["mon_secret_faults"]))
    assert faults == ([refused] if refused else [])
    assert truthy(assert_that(task), {"mon_secret_faults": faults}) is (refused is None)
    rendered = Templar(loader=DataLoader(), variables={"mon_secret_faults": faults}).template(
        trust_as_template(task["ansible.builtin.assert"]["fail_msg"])
    )
    assert all(str(value) not in rendered for value in values.values()), "the refusal printed a value"
    assert (refused or "") in rendered


def test_the_play_runs_the_role_under_its_own_tag_with_no_container_runtime():
    plays = load_tasks(ANSIBLE / "site.yml")
    (play,) = [p for p in plays if p["hosts"] == "mon_host"]
    assert [(role["role"], role["tags"]) for role in play["roles"]] == [
        ("base", ["base"]),
        ("hardening", ["hardening"]),
        ("firewall", ["firewall"]),
        ("fail2ban", ["fail2ban"]),
        ("chrony", ["chrony"]),
        ("mon", ["mon"]),
    ]
```

The existing preview guard, widened to the role's facts:

`tests/test_infra_converge_guards.py` — replace

```python
            for gate in gates:
                if "ansible_check_mode" in gate:
                    read.update(re.findall(r"\b([a-z_][a-z0-9_]*) is changed", gate))
    assert read, role
```

with

```python
            # A fact whose value names check mode is a preview guard too: the gates read it by the fact's name.
            facts = (str(value) for value in (task.get("ansible.builtin.set_fact") or {}).values())
            for guard in (*gates, *facts):
                if "ansible_check_mode" in guard:
                    read.update(re.findall(r"\b([a-z_][a-z0-9_]*) is changed", guard))
    assert read, role
```

- [ ] **Step 2: Run them and read the failure**

Run: `uv run pytest tests/test_infra_mon_role.py -q -p no:cacheprovider`

Expected: `1 error` during collection, a `FileNotFoundError` on a file under `infra/ansible/roles/mon/`: the module reads the role's defaults at import.

- [ ] **Step 3: The role's defaults**

Create `infra/ansible/roles/mon/defaults/main.yml`:

```yaml
---
# Defaults for the `mon` role (spec 00121): the fleet's metrics, logs and alert evaluation on one node.
# The five vaulted values it reads are host_vars/zcrypto-mon/vault.yml's: the role's first task names them.

# The one public name: Caddy's site address and Grafana's root_url, from which every Slack link is built.
mon_hostname: zcrypto-mon.zhaow.me
mon_acme_email: zhaow.km@gmail.com

# Every listener but Caddy's binds loopback.
mon_grafana_port: 3000
mon_prometheus_port: 9090
mon_loki_port: 3100
mon_loki_grpc_port: 9096

# One retention for both stores.
mon_retention_days: 90
# 8 GiB in Prometheus 2.53's units, above what the period holds, so the period governs; the node's
# retention-by-size rule pages when it stops governing.
mon_prometheus_retention_size: 8GB
# How late a shipper may write after an outage; its WAL keeps eight hours.
mon_prometheus_out_of_order_window: 8h
mon_loki_dir: /var/lib/loki

# The folder every rule and dashboard is pushed into and the two datasource uids the rule file, the dashboards
# and the tools name: Grafana Cloud's, reused so that nothing which names them moves.
mon_folder_uid: bfrxdfoybx98gb
mon_folder_title: zcrypto
mon_folder_anchor_dir: /var/lib/grafana/zcrypto-folder-anchor
mon_prom_ds_uid: grafanacloud-prom
mon_loki_ds_uid: grafanacloud-logs

# Caddy's two ingest users: `fleet` for the Alloys on both paths, `logship` for the applications' own log push
# on the Loki path alone, so that push can be revoked without blinding fleet telemetry.
mon_ingest_fleet_user: fleet
mon_ingest_logship_user: logship
```

- [ ] **Step 4: The templates**

Create `infra/ansible/roles/mon/templates/grafana.ini.j2`:

```ini
# Rendered by the `mon` role at /etc/grafana/grafana.ini — edit infra/ansible/roles/mon/templates/grafana.ini.j2.
# tests/test_infra_mon_role.py holds the settings the public login rests on.

[server]
http_addr = 127.0.0.1
http_port = {{ mon_grafana_port }}
domain = {{ mon_hostname }}
root_url = https://{{ mon_hostname }}/

[security]
# A generated name, never the default one: the lockout below is by account name, and a name a stranger
# can guess is one a stranger can keep locked. Grafana reads it only when it creates its database.
admin_user = $__file{/etc/grafana/admin_user}
admin_password = $__file{/etc/grafana/admin_password}
secret_key = $__file{/etc/grafana/secret_key}
cookie_secure = true
cookie_samesite = strict
disable_brute_force_login_protection = false

[auth]
disable_login_form = false

[auth.basic]
enabled = false

[auth.anonymous]
enabled = false
hide_version = true

[auth.proxy]
enabled = false

[auth.jwt]
enabled = false

[users]
allow_sign_up = false
allow_org_create = false

[snapshots]
enabled = false
external_enabled = false

[public_dashboards]
enabled = false

[plugins]
plugin_admin_enabled = false
# The Prometheus and Loki datasources are plugins bundled with the package. The preinstaller would
# download others at each start and replace the bundled ones with a newer release.
preinstall_disabled = true

[feature_toggles]
sqlExpressions = false

[database]
wal = true

[unified_alerting.state_history]
enabled = true
backend = loki
loki_remote_url = http://127.0.0.1:{{ mon_loki_port }}

[analytics]
reporting_enabled = false
check_for_updates = false
check_for_plugin_updates = false
```

Create `infra/ansible/roles/mon/templates/Caddyfile.j2`:

```
# Rendered by the `mon` role at /etc/caddy/Caddyfile — edit infra/ansible/roles/mon/templates/Caddyfile.j2.
# tests/test_infra_mon_role.py holds the four routes below.
{
	email {{ mon_acme_email }}
	auto_https disable_redirects
}

{{ mon_hostname }} {
	tls {
		issuer acme {
			disable_http_challenge
		}
	}

	handle /api/v1/write {
		basic_auth {
			{{ mon_ingest_fleet_user }} {{ mon_ingest_fleet_password_hash }}
		}
		reverse_proxy 127.0.0.1:{{ mon_prometheus_port }}
	}

	handle /loki/api/v1/push {
		basic_auth {
			{{ mon_ingest_fleet_user }} {{ mon_ingest_fleet_password_hash }}
			{{ mon_ingest_logship_user }} {{ mon_ingest_logship_password_hash }}
		}
		reverse_proxy 127.0.0.1:{{ mon_loki_port }}
	}

	@served_without_a_login path /metrics /metrics/* /swagger*
	handle @served_without_a_login {
		respond 404
	}

	handle {
		reverse_proxy 127.0.0.1:{{ mon_grafana_port }}
	}
}
```

The Caddyfile's blocks are indented with tabs, as `caddy fmt` writes them.

Create `infra/ansible/roles/mon/templates/prometheus.default.j2`:

```
# Rendered by the `mon` role at /etc/default/prometheus — edit infra/ansible/roles/mon/templates/prometheus.default.j2.
ARGS="--web.listen-address=127.0.0.1:{{ mon_prometheus_port }} --web.enable-remote-write-receiver --storage.tsdb.retention.time={{ mon_retention_days }}d --storage.tsdb.retention.size={{ mon_prometheus_retention_size }}"
```

Create `infra/ansible/roles/mon/templates/prometheus.yml.j2`:

```yaml
# Rendered by the `mon` role at /etc/prometheus/prometheus.yml — edit infra/ansible/roles/mon/templates/prometheus.yml.j2.
# A remote_write receiver: every sample arrives through /api/v1/write, so this file names no scrape job.
storage:
  tsdb:
    out_of_order_time_window: {{ mon_prometheus_out_of_order_window }}
```

Create `infra/ansible/roles/mon/templates/loki-config.yml.j2`:

```yaml
# Rendered by the `mon` role at /etc/loki/config.yml — edit infra/ansible/roles/mon/templates/loki-config.yml.j2.
auth_enabled: false

server:
  http_listen_address: 127.0.0.1
  http_listen_port: {{ mon_loki_port }}
  grpc_listen_address: 127.0.0.1
  grpc_listen_port: {{ mon_loki_grpc_port }}
  log_level: info

common:
  instance_addr: 127.0.0.1
  path_prefix: {{ mon_loki_dir }}
  storage:
    filesystem:
      chunks_directory: {{ mon_loki_dir }}/chunks
      rules_directory: {{ mon_loki_dir }}/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: "2020-10-24"
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

# Without the compactor's retention Loki keeps every line for good.
compactor:
  working_directory: {{ mon_loki_dir }}/compactor
  retention_enabled: true
  delete_request_store: filesystem

limits_config:
  retention_period: {{ mon_retention_days * 24 }}h

analytics:
  reporting_enabled: false
```

Create `infra/ansible/roles/mon/templates/grafana-server.dropin.conf.j2`:

```ini
# Rendered by the `mon` role at /etc/systemd/system/grafana-server.service.d/10-zcrypto-mon.conf — edit
# infra/ansible/roles/mon/templates/grafana-server.dropin.conf.j2.
[Unit]
After=prometheus.service loki.service

[Service]
# After= orders the start and does not wait for readiness. A Grafana evaluating against a store that is not
# ready puts every rule that reads it in error, and all but two rules page on an error.
ExecStartPre=/usr/bin/curl -fsS -o /dev/null --max-time 3 --retry 40 --retry-delay 3 --retry-all-errors http://127.0.0.1:{{ mon_prometheus_port }}/-/ready
ExecStartPre=/usr/bin/curl -fsS -o /dev/null --max-time 3 --retry 40 --retry-delay 3 --retry-all-errors http://127.0.0.1:{{ mon_loki_port }}/ready
TimeoutStartSec=600
# Below the stores' default of 0: a killed Grafana loses up to fifteen minutes of silences.
OOMScoreAdjust=-500
```

Create `infra/ansible/roles/mon/templates/datasources.yml.j2`:

```yaml
# Rendered by the `mon` role at /etc/grafana/provisioning/datasources/zcrypto.yml — edit
# infra/ansible/roles/mon/templates/datasources.yml.j2.
apiVersion: 1
prune: true
datasources:
  - name: Prometheus
    uid: {{ mon_prom_ds_uid }}
    type: prometheus
    access: proxy
    url: http://127.0.0.1:{{ mon_prometheus_port }}
    isDefault: true
    editable: false
  - name: Loki
    uid: {{ mon_loki_ds_uid }}
    type: loki
    access: proxy
    url: http://127.0.0.1:{{ mon_loki_port }}
    editable: false
```

Create `infra/ansible/roles/mon/templates/folder-anchor.yml.j2`:

```yaml
# Rendered by the `mon` role at /etc/grafana/provisioning/dashboards/zcrypto.yml — edit
# infra/ansible/roles/mon/templates/folder-anchor.yml.j2.
# This provider reads an empty directory: it exists to create the folder under the uid the push names. The
# dashboards and rules themselves are pushed, never file-provisioned, since a provisioned one cannot be
# edited through the API the push uses.
apiVersion: 1
providers:
  - name: zcrypto-folder-anchor
    type: file
    folder: {{ mon_folder_title }}
    folderUid: {{ mon_folder_uid }}
    disableDeletion: true
    options:
      path: {{ mon_folder_anchor_dir }}
```

- [ ] **Step 5: The tasks and the handlers**

Create `infra/ansible/roles/mon/tasks/main.yml`:

```yaml
---
# The observability node (spec 00121): Grafana on SQLite, one Prometheus as the remote_write receiver,
# single-binary Loki, Caddy as the one public listener, and the node's own Alloy. Packages followed from
# apt, never forced or held; tests/test_infra_mon_role.py holds what the public login rests on.

# First, so a missing or misshapen vault value fails here by name and not inside a no_log task. The two
# generated strings are letters and digits, the admin's name `u` and 16 hex digits, the two hashes bcrypt's.
- name: refuse a missing or misshapen secret, naming the key and never the value
  ansible.builtin.assert:
    that: mon_secret_faults | length == 0
    fail_msg: >-
      {{ mon_secret_faults | join(', ') }} in host_vars/zcrypto-mon/vault.yml: missing, or not the shape
      its generator writes. Re-generate it with infra/runbooks/mon.md's mon-secrets procedure.
  vars:
    mon_secret_faults: >-
      {{ ([['mon_grafana_admin_password', mon_grafana_admin_password | default('')],
           ['mon_grafana_secret_key', mon_grafana_secret_key | default('')]]
          | rejectattr('1', 'match', '[A-Za-z0-9]{32,}\Z') | map('first') | list)
         + ([['mon_grafana_admin_user', mon_grafana_admin_user | default('')]]
            | rejectattr('1', 'match', 'u[0-9a-f]{16}\Z') | map('first') | list)
         + ([['mon_ingest_fleet_password_hash', mon_ingest_fleet_password_hash | default('')],
             ['mon_ingest_logship_password_hash', mon_ingest_logship_password_hash | default('')]]
            | rejectattr('1', 'match', '\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}\Z') | map('first') | list) }}

# ---- Packages and their sources ------------------------------------------------------------------
- name: add the Grafana apt repository (grafana, loki, alloy)
  ansible.builtin.deb822_repository:
    name: grafana
    types: [deb]
    uris: https://apt.grafana.com
    suites: [stable]
    components: [main]
    signed_by: https://apt.grafana.com/gpg.key
  register: mon_grafana_repo

- name: add the Caddy apt repository
  ansible.builtin.deb822_repository:
    name: caddy
    types: [deb]
    uris: https://dl.cloudsmith.io/public/caddy/stable/deb/debian
    suites: [any-version]
    components: [main]
    signed_by: https://dl.cloudsmith.io/public/caddy/stable/gpg.key
  register: mon_caddy_repo

# A preview on a node that never had the repositories cannot see their packages: apt fails on a name its
# cache does not hold, and converge.sh stops on a failed preview. Every task below that needs an installed
# package or its unit skips exactly that case, and every real converge runs it.
- name: note a preview that runs before the repositories exist
  ansible.builtin.set_fact:
    mon_repos_previewed: "{{ ansible_check_mode and (mon_grafana_repo is changed or mon_caddy_repo is changed) }}"

# Unconditional: a converge that added a repository and failed before this would otherwise never see it.
- name: refresh the apt cache, so the candidates below are the repositories' own
  ansible.builtin.apt:
    update_cache: true
  changed_when: false

- name: read which loki apt would install
  ansible.builtin.command: apt-cache policy loki
  register: mon_loki_policy
  changed_when: false
  check_mode: false

# Debian's own `loki` is unrelated software under the same name.
- name: refuse a loki candidate that does not come from apt.grafana.com
  ansible.builtin.assert:
    that: mon_loki_policy.stdout is search(mon_loki_origin_pattern)
    fail_msg: >-
      apt's candidate for `loki` is not Grafana's: Debian carries an unrelated package of that name.
      Read `apt-cache policy loki` on the node; the candidate's source line must name apt.grafana.com.
  vars:
    mon_loki_candidate: "{{ mon_loki_policy.stdout | regex_search('Candidate: (\\S+)', '\\1') | default(['none'], true) | first }}"
    mon_loki_origin_pattern: "\\n\\s+(\\*\\*\\* )?{{ mon_loki_candidate | regex_escape }} \\d+\\n(\\s{8}.*\\n)*?\\s{8}\\d+ https://apt\\.grafana\\.com[/ ]"
  when: not mon_repos_previewed

- name: prometheus present, from Debian main, without the node exporter it recommends
  ansible.builtin.apt:
    name: [prometheus, curl]
    state: present
    install_recommends: false
  register: mon_debian_install

- name: grafana, loki and alloy present — versions FOLLOWED from apt, never forced or held
  ansible.builtin.apt:
    name: [grafana, loki, alloy]
    state: present
  register: mon_grafana_install
  when: not mon_repos_previewed

- name: caddy present — version FOLLOWED from apt, never forced or held
  ansible.builtin.apt:
    name: caddy
    state: present
  register: mon_caddy_install
  when: not mon_repos_previewed

# A preview that would install a package has no unit of it for systemd to find, the fail2ban role's case.
- name: note a preview that runs before the packages are installed
  ansible.builtin.set_fact:
    mon_units_previewed: >-
      {{ ansible_check_mode and (mon_repos_previewed or mon_debian_install is changed
         or mon_grafana_install is changed or mon_caddy_install is changed) }}

# ---- Prometheus: the remote_write receiver --------------------------------------------------------
- name: prometheus flags — loopback, the receiver, the retention
  ansible.builtin.template:
    src: prometheus.default.j2
    dest: /etc/default/prometheus
    owner: root
    group: root
    mode: "0644"
  notify: restart prometheus

- name: prometheus config — no scrape job, the out-of-order window
  ansible.builtin.template:
    src: prometheus.yml.j2
    dest: /etc/prometheus/prometheus.yml
    owner: root
    group: root
    mode: "0644"
    validate: promtool check config %s
  notify: restart prometheus

# ---- Loki: the single binary on the local filesystem ----------------------------------------------
- name: loki's data directory
  ansible.builtin.file:
    path: "{{ mon_loki_dir }}"
    state: directory
    owner: loki
    group: root
    mode: "0750"

- name: loki config — loopback, filesystem storage, the compactor's retention
  ansible.builtin.template:
    src: loki-config.yml.j2
    dest: /etc/loki/config.yml
    owner: root
    group: root
    mode: "0644"
    validate: loki -verify-config -config.file %s
  notify: restart loki

# ---- Grafana ---------------------------------------------------------------------------------------
# The unit runs as `grafana`, and a $__file{} it cannot read stops Grafana at start.
- name: grafana's admin name and two secrets, each a file read through $__file{}
  ansible.builtin.copy:
    content: "{{ item.value }}"
    dest: "/etc/grafana/{{ item.file }}"
    owner: root
    group: grafana
    mode: "0640"
  loop:
    - {file: admin_user, value: "{{ mon_grafana_admin_user }}"}
    - {file: admin_password, value: "{{ mon_grafana_admin_password }}"}
    - {file: secret_key, value: "{{ mon_grafana_secret_key }}"}
  loop_control:
    label: "{{ item.file }}"
  no_log: true
  notify: restart grafana

- name: grafana.ini
  ansible.builtin.template:
    src: grafana.ini.j2
    dest: /etc/grafana/grafana.ini
    owner: root
    group: grafana
    mode: "0640"
  notify: restart grafana

- name: the two datasources, file-provisioned read-only under the uids the rule file names
  ansible.builtin.template:
    src: datasources.yml.j2
    dest: /etc/grafana/provisioning/datasources/zcrypto.yml
    owner: root
    group: grafana
    mode: "0640"
  notify: restart grafana

- name: the empty directory the folder's provider reads
  ansible.builtin.file:
    path: "{{ mon_folder_anchor_dir }}"
    state: directory
    owner: root
    group: grafana
    mode: "0750"

- name: the folder the push writes into, anchored under its uid
  ansible.builtin.template:
    src: folder-anchor.yml.j2
    dest: /etc/grafana/provisioning/dashboards/zcrypto.yml
    owner: root
    group: grafana
    mode: "0640"
  notify: restart grafana

- name: grafana-server drop-in directory
  ansible.builtin.file:
    path: /etc/systemd/system/grafana-server.service.d
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: grafana-server drop-in — after its stores, waiting for both to be ready
  ansible.builtin.template:
    src: grafana-server.dropin.conf.j2
    dest: /etc/systemd/system/grafana-server.service.d/10-zcrypto-mon.conf
    owner: root
    group: root
    mode: "0644"
  notify:
    - reload systemd
    - restart grafana

# ---- Caddy: the one public listener ----------------------------------------------------------------
# Validated by the installed binary before it replaces the live file, so a Caddyfile this Caddy cannot
# parse fails the converge and the edge keeps serving the old one. It carries the ingest users' hashes.
- name: Caddyfile — the two ingest paths behind basic auth, two refusals, everything else to grafana
  ansible.builtin.template:
    src: Caddyfile.j2
    dest: /etc/caddy/Caddyfile
    owner: root
    group: caddy
    mode: "0640"
    validate: caddy validate --adapter caddyfile --config %s
  no_log: true
  diff: false
  notify: reload caddy

# ---- Services --------------------------------------------------------------------------------------
- name: prometheus and loki enabled + started
  ansible.builtin.systemd_service:
    name: "{{ item }}"
    enabled: true
    state: started
  loop: [prometheus, loki]
  when: not mon_units_previewed

# The stores carry their rendered configs before Grafana starts against them, on a first converge and
# on every later one.
- name: apply the pending store and grafana restarts
  ansible.builtin.meta: flush_handlers

- name: grafana-server enabled + started
  ansible.builtin.systemd_service:
    name: grafana-server
    enabled: true
    state: started
    daemon_reload: true
  when: not mon_units_previewed

- name: caddy enabled + started
  ansible.builtin.systemd_service:
    name: caddy
    enabled: true
    state: started
  when: not mon_units_previewed
```

Create `infra/ansible/roles/mon/handlers/main.yml`:

```yaml
---
# In file order, which is the order a flush runs them in: a store is restarted with Grafana stopped
# around it, since a Grafana evaluating against a restarting store puts every rule that reads it in
# error. `restart grafana` listens to both store handlers, so it starts Grafana again after either; on a
# stopped unit `restarted` is a start. Each skips a preview that runs before its package is installed.
- name: reload systemd
  ansible.builtin.systemd_service:
    daemon_reload: true

- name: stop grafana around a store restart
  ansible.builtin.systemd_service:
    name: grafana-server
    state: stopped
  listen: [restart prometheus, restart loki]
  when: not mon_units_previewed

- name: restart prometheus
  ansible.builtin.systemd_service:
    name: prometheus
    state: restarted
  when: not mon_units_previewed

- name: restart loki
  ansible.builtin.systemd_service:
    name: loki
    state: restarted
  when: not mon_units_previewed

- name: restart grafana
  ansible.builtin.systemd_service:
    name: grafana-server
    state: restarted
    daemon_reload: true
  listen: [restart prometheus, restart loki]
  when: not mon_units_previewed

- name: reload caddy
  ansible.builtin.systemd_service:
    name: caddy
    state: reloaded
  when: not mon_units_previewed
```

- [ ] **Step 6: The role in the node's play**

`infra/ansible/site.yml` — append at the end of the file:

```yaml
    - role: mon
      tags: [mon]
```

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_infra_mon_role.py tests/test_infra_converge_guards.py::test_every_register_a_preview_guard_reads_is_set_in_its_own_role -q -p no:cacheprovider`

Expected: no failure and no skip.

- [ ] **Step 8: The consumers**

```bash
uv run pytest tests/test_infra_mon_role.py tests/test_infra_converge_guards.py tests/test_converge_sh.py tests/test_run_sh.py tests/test_deploy_log_audit.py tests/test_infra_unattended_upgrades.py tests/test_infra_firewall_template.py tests/test_chrony_role.py tests/test_infra_cache_templates.py tests/test_infra_compose_templates.py tests/test_infra_alloy_series.py tests/test_config_selectors_are_parsed.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`2007 passed` on the tree this plan was written against). `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` walks the new role's files.

- [ ] **Step 9: The commit gate**

Run: `uv run pre-commit run -a`

Expected: every hook Passed (`yamllint` and `ansible-lint` read the role); re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 10: Commit**

```bash
git add infra/ansible/roles/mon infra/ansible/site.yml tests/test_infra_mon_role.py tests/test_infra_converge_guards.py
git commit -F- <<'MSG'
feat(mon): the mon role installs Grafana, Prometheus, Loki and Caddy and renders them loopback-bound behind one public edge

The role follows five packages from apt, forcing, holding and pinning none: `grafana`, `loki` and
`alloy` from `apt.grafana.com`, `caddy` from cloudsmith, `prometheus` from Debian main without its
recommends. Debian carries an unrelated `loki`, so the role reads `apt-cache policy` and refuses a
candidate whose source is not Grafana's. Its first task refuses a missing or misshapen vault value
by its key, never its value.

Prometheus is a remote_write receiver on `127.0.0.1:9090` with no scrape job, 90 days, an `8GB` size
cap and an 8 h out-of-order window. Loki is the single binary on `127.0.0.1:3100`, filesystem
storage, schema v13, the compactor enforcing the same 90 days. Each store's config is validated by
the installed binary before it replaces the live file.

`grafana.ini` binds `127.0.0.1:3000` under `root_url` `https://zcrypto-mon.zhaow.me/`, reads the
admin's name, its password and the secret key through `$__file{}` from three `root:grafana 0640`
files, and turns off basic auth, the proxy and JWT logins, anonymous access, sign-up, snapshots,
public dashboards, plugin administration, the plugin preinstaller, `sqlExpressions`, analytics and
update checks; alert history goes to the node's Loki. The admin's name is a generated one: the
login lockout is by account name, so the default name is one a stranger's guesses would keep
locked. With the preinstaller off, the Prometheus and Loki datasource plugins are the copies the
package bundles and a start downloads nothing. Two read-only datasources and the alert folder are
file-provisioned under Grafana Cloud's uids, so the rule file, the dashboards and the push script's
defaults name them unchanged.

`grafana-server` takes a drop-in: after both stores, two `ExecStartPre` reads that wait for their
readiness, and an OOM score below theirs. The handlers stop Grafana before either store restarts
and start it after, and the tasks flush them before Grafana's first start.

Caddy listens on 443 alone, with no redirect listener and the certificate taken over TLS-ALPN:
`/api/v1/write` behind basic auth for `fleet`, `/loki/api/v1/push` for `fleet` and `logship`,
`/metrics`, `/metrics/*` and `/swagger*` answered 404, everything else to Grafana with no
credential added. The Caddyfile is validated before it replaces the live one and never shown in a
diff.

`converge.sh` previews first, and a node with none of the packages fails a preview at `apt` and at
`systemd_service`: two facts mark a preview with no repository and one with no unit, and every task
and handler that needs either skips exactly that run. The existing guard over preview registers
reads `when:` gates alone, so it now reads a fact whose value names check mode as well.

Cases: 22 over the rendered templates, the tasks and the handlers, each read through Ansible's own
templar; the widened register guard.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 11: The tree is clean**

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 12: Prove the guards with thirty-six probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time. The controls: Grafana's bind address widened; the 404 answered 403; Prometheus's listener widened; the out-of-order key misspelled; Loki's schema version changed; Loki dropped from the unit's `After=`; the datasources' prune switched off; a port default moved; the `restart loki` handler deleted; `promtool`'s subcommand changed; the play's group renamed; a repository's register renamed. The mutations take away, one at a time, each thing the public login, the edge, the stores' ordering and the preview rest on:

```bash
R=infra/ansible/roles/mon
ROLE="uv run pytest tests/test_infra_mon_role.py -q -p no:cacheprovider"
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation '/^\[auth.basic\]$/,/^$/s/^enabled = false$/enabled = true/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation '/^\[auth.proxy\]$/,/^$/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation 's/^hide_version = true$/hide_version = false/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation 's/^backend = loki$/backend = annotations/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation 's/^admin_user = \$__file{\/etc\/grafana\/admin_user}$/admin_user = admin/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana.ini.j2 \
  --control 's/^http_addr = 127.0.0.1$/http_addr = 0.0.0.0/' \
  --mutation 's/^preinstall_disabled = true$/preinstall_disabled = false/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/Caddyfile.j2 \
  --control 's/respond 404/respond 403/' \
  --mutation '/^\t\t\t{{ mon_ingest_logship_user }} /d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/Caddyfile.j2 \
  --control 's/respond 404/respond 403/' \
  --mutation '/handle \/api\/v1\/write {/,/reverse_proxy/{/basic_auth {/,/}/d}' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/Caddyfile.j2 \
  --control 's/respond 404/respond 403/' \
  --mutation 's#path /metrics /metrics/\* /swagger\*#path /metrics /swagger*#' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/Caddyfile.j2 \
  --control 's/respond 404/respond 403/' \
  --mutation '/disable_http_challenge/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/Caddyfile.j2 \
  --control 's/respond 404/respond 403/' \
  --mutation '/auto_https disable_redirects/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/prometheus.default.j2 \
  --control 's/127.0.0.1/0.0.0.0/' \
  --mutation 's/ --web.enable-remote-write-receiver//' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/prometheus.yml.j2 \
  --control 's/out_of_order_time_window/out_of_order_window/' \
  --mutation '$a scrape_configs: [{job_name: prometheus, static_configs: [{targets: ["localhost:9090"]}]}]' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/loki-config.yml.j2 \
  --control 's/schema: v13/schema: v12/' \
  --mutation 's/retention_enabled: true/retention_enabled: false/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/loki-config.yml.j2 \
  --control 's/schema: v13/schema: v12/' \
  --mutation 's/http_listen_address: 127.0.0.1/http_listen_address: 0.0.0.0/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana-server.dropin.conf.j2 \
  --control 's/^After=prometheus.service loki.service$/After=prometheus.service/' \
  --mutation '/mon_loki_port }}\/ready$/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/grafana-server.dropin.conf.j2 \
  --control 's/^After=prometheus.service loki.service$/After=prometheus.service/' \
  --mutation 's/^OOMScoreAdjust=-500$/OOMScoreAdjust=0/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/templates/datasources.yml.j2 \
  --control 's/^prune: true$/prune: false/' \
  --mutation '0,/editable: false/s/editable: false/editable: true/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/defaults/main.yml \
  --control 's/^mon_loki_port: 3100$/mon_loki_port: 3101/' \
  --mutation 's/^mon_folder_uid: bfrxdfoybx98gb$/mon_folder_uid: zcrypto/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/handlers/main.yml \
  --control '/^- name: restart loki$/,/^$/d' \
  --mutation '/^- name: stop grafana around a store restart$/,/^$/s/  listen: \[restart prometheus, restart loki\]/  listen: [restart prometheus]/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/handlers/main.yml \
  --control '/^- name: restart loki$/,/^$/d' \
  --mutation '/^- name: reload caddy$/,$s/^  when: not mon_units_previewed$//' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation "s/\[A-Za-z0-9\]{32,}/[A-Za-z0-9]{1,}/" -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/u\[0-9a-f\]{16}/[a-z]{4,}/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/and (mon_repos_previewed or mon_debian_install is changed$/and (mon_debian_install is changed/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/and (mon_repos_previewed or mon_debian_install is changed$/and (mon_repos_previewed/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/ or mon_caddy_install is changed) }}$/) }}/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/https:\/\/apt\\\\\.grafana\\\\\.com\[\/ \]/https?:\/\/[a-z.]+[\/ ]/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^- name: caddy present/,/^$/{/^  when: not mon_repos_previewed$/d}' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^- name: caddy enabled + started$/,$s/^  when: not mon_units_previewed$//' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^- name: caddy enabled + started$/,$s/^  when: not mon_units_previewed$/  when: mon_units_previewed/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^- name: grafana.s admin name and two secrets/,/^$/s/^    group: grafana$/    group: root/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^    validate: caddy validate --adapter caddyfile --config %s$/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^- name: apply the pending store and grafana restarts$/,/^$/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation 's/^    install_recommends: false$/    install_recommends: true/' -- $ROLE
infra/scripts/mutate-probe.sh --file infra/ansible/site.yml \
  --control 's/^  hosts: mon_host$/  hosts: mon_hosts/' \
  --mutation '$d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^  register: mon_grafana_repo$/  register: mon_grafana_repos/' \
  --mutation 's/^  register: mon_caddy_install$/  register: mon_caddy_installed/' \
  -- uv run pytest tests/test_infra_converge_guards.py::test_every_register_a_preview_guard_reads_is_set_in_its_own_role -q -p no:cacheprovider
```

Expected: each of the thirty-six runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 10 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, thirty-six runs, each KILLED with its control proven.
`grafana.ini.j2`, control the bind address widened: basic auth switched on, KILLED, control proven;
the `[auth.proxy]` section deleted, KILLED, control proven; the version shown, KILLED, control
proven; alert history returned to annotations, KILLED, control proven; the admin's name returned to
the default, KILLED, control proven; the plugin preinstaller switched on, KILLED, control proven.
`Caddyfile.j2`, control the 404 answered 403: `logship` dropped from the Loki path, KILLED, control
proven; the write path's basic auth deleted, KILLED, control proven; the per-plugin metrics tree
dropped from the refusals, KILLED, control proven; the HTTP challenge allowed, KILLED, control
proven; the redirect listener allowed, KILLED, control proven. `prometheus.default.j2`, control the
listener widened: the receiver flag dropped, KILLED, control proven. `prometheus.yml.j2`, control
the out-of-order key misspelled: a scrape job added, KILLED, control proven. `loki-config.yml.j2`,
control the schema version changed: retention switched off, KILLED, control proven; the listener
widened, KILLED, control proven. The
`grafana-server` drop-in, control Loki dropped from `After=`: Loki's readiness wait deleted, KILLED,
control proven; the OOM score returned to 0, KILLED, control proven. `datasources.yml.j2`, control
prune switched off: a datasource made editable, KILLED, control proven. The role's defaults, control
a port moved: the folder uid changed, KILLED, control proven. The handlers, control `restart loki`
deleted: Grafana's stop no longer listening to a Loki restart, KILLED, control proven; a handler's
preview gate removed, KILLED, control proven. The tasks, control `promtool`'s subcommand changed: a
one-character secret admitted, KILLED, control proven; a guessable admin name admitted, KILLED,
control proven; the repositories, then the Debian install, then Caddy's install dropped from the
second preview fact, each KILLED, control proven; any origin admitted for `loki`, KILLED, control
proven; Caddy's install run in a preview with no repository, KILLED, control proven; a unit's start
run in a preview with no unit, KILLED, control proven; a unit's gate inverted, KILLED, control
proven; the three secret files' group returned to root, KILLED, control proven; the Caddyfile's
validation dropped, KILLED, control proven; the flush before Grafana's start dropped, KILLED,
control proven; Prometheus's recommends installed, KILLED, control proven; and, control a
repository's register renamed, over the widened register guard: an install's register renamed,
KILLED, control proven. `infra/ansible/site.yml`, control the play's group renamed: the role's tag
dropped, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 3: The role keeps one Editor service account and its one token, cached vault-encrypted on the controller

**Files:**
- Create: `infra/ansible/roles/mon/tasks/token.yml`
- Modify: `infra/ansible/roles/mon/defaults/main.yml` (the service account, the cache path, the token pattern, appended)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the `include_tasks`, appended)
- Test (new): `tests/test_infra_mon_token.py`

**Interfaces:**
- Consumes: Task 2's role, its `mon_grafana_port` and its running Grafana; `mon_grafana_admin_password`; Task 1's `converge.sh` key `mon_grafana_token_rotate`; `ansible-vault encrypt_string` on the controller under the repo's `ansible.cfg`; the test helpers of `tests/test_infra_converge_guards.py`.
- Produces, for Task 5 and the Rollout to use by these exact names: the service account `zcrypto-tools`, role Editor; the controller-side cache `~/.config/zcrypto/grafana-mon.vault.yml`, mode 0600, holding one vault-encrypted variable `mon_grafana_tools_token`; the defaults `mon_service_account`, `mon_token_var`, `mon_token_cache`, `mon_grafana_api`, `mon_token_pattern`.

**What this task decides, where the spec leaves it open:**
- The token tasks are one included file, `tasks/token.yml`, under `when: not ansible_check_mode`: every task in it calls Grafana's API or acts on what one returned, so the preview skips it whole, and `tests/test_infra_mon_token.py` holds that no other task of the role calls the API.
- The pattern is the spec's, ending `\Z` and not `$`. Ansible's `match` is Python's, where `$` also matches before a trailing newline, the one shape the spec's first correction exists to refuse; `test_the_pattern_ends_where_the_string_ends` holds both halves.
- "The cached token is this account's" is read off `/api/user`'s `login`, compared with the service account's own `login`: for a service-account token that endpoint answers `id: 0`, so an id comparison would re-mint on every converge.
- The CLI reset runs as the `grafana` user through `runuser`, so the database keeps its owner, and takes the password on stdin with no newline added.
- The cache is written by `ansible.builtin.copy` on the controller from `ansible-vault encrypt_string`'s output, the token passed on stdin with `stdin_add_newline: false`, and its directory is created `0700`; the vault variable is named `mon_grafana_tools_token` and the minted token `zcrypto-tools-<UTC timestamp>`.
- Both sign-ins name the vaulted `mon_grafana_admin_user`, the name Task 2's ini hands Grafana. The refusal names the two things a second 401 can be: the lockout, and a vaulted name that is not the one the database was created with, which the reset cannot repair since it resets the password alone.
- The lockout message names no count: the spec measured the lock after six failed sign-ins, the count is a Grafana setting, and the operator's step is the same whatever it is, wait five minutes without signing in.
- The admin session is ended in an `always:` section, so a failed task between sign-in and sign-out leaves no session behind.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_infra_mon_token.py`:

```python
"""The observability node's token tasks, read without a host: one Editor service account holding one token, cached
vault-encrypted on the controller, with every condition evaluated through Ansible's own templar."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.test_infra_converge_guards import assert_that, find_task, iter_tasks, load_tasks, set_facts, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/mon"
TOKEN = ROLE / "tasks/token.yml"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
PATTERN = DEFAULTS["mon_token_pattern"]
# Assembled, never spelled: no tracked file carries a token-shaped literal, this one included.
WELL_SHAPED = "glsa_" + "a" * 32 + "_" + "0" * 8
SECRET_NAMES = ("mon_grafana_admin_password", "mon_session", "mon_token_candidate", "mon_token_cached", "mon_token_minted")


def _tasks() -> list[tuple[dict, tuple[str, ...]]]:
    return iter_tasks(load_tasks(TOKEN))


def _uri(task: dict) -> dict:
    return task.get("ansible.builtin.uri", {})


def test_the_token_tasks_run_only_outside_check_mode():
    include = find_task(load_tasks(ROLE / "tasks/main.yml"), "the tools' service account and its one token")
    assert include["ansible.builtin.include_tasks"] == "token.yml"
    assert when_conditions(include) == ["not ansible_check_mode"]
    apis = [task["name"] for task, _ in iter_tasks(load_tasks(ROLE / "tasks/main.yml")) if "ansible.builtin.uri" in task]
    assert apis == [], f"a call to Grafana's API outside the token tasks would run in a preview: {apis}"


def test_every_call_goes_to_grafana_on_loopback():
    assert DEFAULTS["mon_grafana_api"] == "http://127.0.0.1:{{ mon_grafana_port }}"
    urls = [_uri(task)["url"] for task, _ in _tasks() if _uri(task)]
    assert len(urls) >= 10 and all(url.startswith("{{ mon_grafana_api }}/") for url in urls), urls


@pytest.mark.parametrize(
    ("cached", "kept"),
    [
        (WELL_SHAPED, WELL_SHAPED),
        (WELL_SHAPED + "\n", ""),
        (" " + WELL_SHAPED, ""),
        (WELL_SHAPED.replace("glsa_", "glsa-"), ""),
        (WELL_SHAPED + "0", ""),
        ("", ""),
        (None, ""),
    ],
    ids=["a token", "a trailing newline", "a leading space", "another prefix", "too long", "empty", "no cache"],
)
def test_a_cached_value_reaches_a_header_only_in_a_tokens_shape(cached, kept):
    task = find_task(load_tasks(TOKEN), "keep the cached token only when it has a token's shape")
    variables = {"mon_token_var": DEFAULTS["mon_token_var"], "mon_token_pattern": PATTERN}
    if cached is not None:
        variables["mon_token_cached"] = {DEFAULTS["mon_token_var"]: cached}
    assert set_facts(task, variables) == {"mon_token_candidate": kept}
    probe = find_task(load_tasks(TOKEN), "ask grafana whose token the cached one is")
    assert _uri(probe)["headers"] == {"Authorization": "Bearer {{ mon_token_candidate }}"}
    assert when_conditions(probe) == ["mon_token_candidate | length > 0"]
    bearers = [task["name"] for task, _ in _tasks() if "Bearer" in str(_uri(task).get("headers", ""))]
    assert bearers == [probe["name"]], "only the checked value is ever placed in an Authorization header"


def test_the_pattern_ends_where_the_string_ends():
    """`$` also matches before a trailing newline, and a token stored with one failed a request with the token in
    the error text."""
    assert PATTERN.endswith("\\Z") and "$" not in PATTERN, PATTERN
    assert re.match(PATTERN, WELL_SHAPED) and not re.match(PATTERN, WELL_SHAPED + "\n")


def test_a_minted_token_is_held_to_the_shape_before_it_is_written_with_no_newline_added():
    names = [task["name"] for task, _ in _tasks()]
    mint, check, encrypt, write = (
        "mint the tools' token",
        "refuse a minted token of another shape before it is written",
        "encrypt the minted token under the repo's vault password",
        "write the token cache on the controller",
    )
    assert names.index(mint) < names.index(check) < names.index(encrypt) < names.index(write)
    refusal = find_task(load_tasks(TOKEN), check)
    for key, admitted in ((WELL_SHAPED, True), (WELL_SHAPED + "\n", False), ("", False)):
        variables = {"mon_token_pattern": PATTERN, "mon_token_minted": {"json": {"key": key}}}
        assert truthy(assert_that(refusal), variables) is admitted, repr(key)
    command = find_task(load_tasks(TOKEN), encrypt)["ansible.builtin.command"]
    assert command["argv"] == ["ansible-vault", "encrypt_string", "--stdin-name", "{{ mon_token_var }}"]
    assert command["stdin"] == "{{ mon_token_minted.json.key }}" and command["stdin_add_newline"] is False
    copy = find_task(load_tasks(TOKEN), write)["ansible.builtin.copy"]
    assert (copy["dest"], copy["mode"]) == ("{{ mon_token_cache }}", "0600")


def test_the_token_never_lands_on_the_node():
    """Whatever reads or writes the cache runs on the controller, as the operator and not as root."""
    # include_vars is an action that reads on the controller whatever the task's host; every other task naming the
    # cache's path, and the one that encrypts for it, is delegated there.
    names_the_cache = re.compile(r"\bmon_token_cache\b")
    controller = [
        task
        for task, _ in _tasks()
        if (names_the_cache.search(str(task)) and "ansible.builtin.include_vars" not in task)
        or task.get("register") == "mon_token_encrypted"
    ]
    assert len(controller) == 4, [task["name"] for task in controller]
    for task in controller:
        assert task.get("delegate_to") == "localhost" and task.get("become") is False, task["name"]
    delegated = [task for task, _ in _tasks() if "delegate_to" in task]
    assert all(task["become"] is False for task in delegated), (
        "a delegated task under the play's become runs sudo on the workstation"
    )
    assert "ansible.builtin.env" in DEFAULTS["mon_token_cache"] and "/.config/zcrypto/" in DEFAULTS["mon_token_cache"]


@pytest.mark.parametrize(
    ("variables", "minted"),
    [
        ({}, False),
        ({"mon_grafana_token_rotate": "true"}, True),
        ({"mon_token_candidate": ""}, True),
        ({"mon_token_probe": {"status": 401, "json": {"message": "Invalid API key"}}}, True),
        ({"mon_token_probe": {"status": 200, "json": {"login": "sa-1-another"}}}, True),
        ({"mon_sa_tokens": {"json": [{"id": 1}, {"id": 2}]}}, True),
        ({"mon_sa_tokens": {"json": []}}, True),
    ],
    ids=["steady", "rotation asked", "no usable cache", "refused", "another account's", "not the only token", "no token"],
)
def test_a_token_is_minted_exactly_when_the_cached_one_cannot_be_kept(variables, minted):
    steady = {
        "mon_token_candidate": WELL_SHAPED,
        "mon_token_probe": {"status": 200, "json": {"login": "sa-1-zcrypto-tools"}},
        "mon_sa": {"id": 2, "login": "sa-1-zcrypto-tools"},
        "mon_sa_tokens": {"json": [{"id": 1}]},
    }
    task = find_task(load_tasks(TOKEN), "decide whether a token is minted")
    assert bool(set_facts(task, {**steady, **variables})["mon_token_mint"]) is minted
    for name in ("mint the tools' token", "write the token cache on the controller"):
        assert when_conditions(find_task(load_tasks(TOKEN), name)) == ["mon_token_mint"]
    delete = find_task(load_tasks(TOKEN), "delete every token the mint superseded")
    assert delete["loop"] == "{{ mon_sa_tokens.json if mon_token_mint else [] }}", "a kept token must never be deleted"


def test_the_one_service_account_is_an_editor_and_no_other_is_created():
    creates = [
        task for task, _ in _tasks() if _uri(task).get("method") == "POST" and _uri(task)["url"].endswith("/api/serviceaccounts")
    ]
    assert len(creates) == 1, [task["name"] for task in creates]
    body = _uri(creates[0])["body"]
    assert body == {"name": "{{ mon_service_account }}", "role": "Editor", "isDisabled": False}
    assert DEFAULTS["mon_service_account"] == "zcrypto-tools"
    roles = [_uri(task)["body"]["role"] for task, _ in _tasks() if "role" in (_uri(task).get("body") or {})]
    assert roles == ["Editor", "Editor"], f"the account is created an Editor and returned to one, never more: {roles}"
    drift = find_task(load_tasks(TOKEN), "return a drifted service account to an enabled Editor")
    for account, corrected in (
        ({"role": "Editor", "isDisabled": False}, False),
        ({"role": "Admin", "isDisabled": False}, True),
        ({"role": "Viewer", "isDisabled": False}, True),
        ({"role": "Editor", "isDisabled": True}, True),
    ):
        assert truthy(when_conditions(drift), {"mon_sa": account}) is corrected, account


def test_a_refused_sign_in_is_repaired_once_from_the_vault_and_never_retried():
    sign_ins = [task for task, _ in _tasks() if _uri(task).get("url", "").endswith("/login")]
    assert [task["name"] for task in sign_ins] == [
        "sign in on loopback with the vaulted admin password",
        "sign in again after the reset",
    ]
    for task in sign_ins:
        assert _uri(task)["status_code"] == [200, 401] and "retries" not in task and "until" not in task, task["name"]
        assert _uri(task)["body"] == {"user": "{{ mon_grafana_admin_user }}", "password": "{{ mon_grafana_admin_password }}"}
    reset = find_task(load_tasks(TOKEN), "reset the admin password from the vault")
    command = reset["ansible.builtin.command"]
    assert command["argv"][:5] == ["runuser", "-u", "grafana", "--", "/usr/share/grafana/bin/grafana"]
    override = command["argv"].index("--configOverrides")
    assert command["argv"][override + 1] == "cfg:default.paths.data=/var/lib/grafana"
    assert command["argv"][-3:] == ["admin", "reset-admin-password", "--password-from-stdin"]
    assert command["stdin"] == "{{ mon_grafana_admin_password }}" and command["stdin_add_newline"] is False
    assert when_conditions(reset) == when_conditions(sign_ins[1]) == ["mon_login.status == 401"]
    refusal = find_task(load_tasks(TOKEN), "refuse to go on when the vaulted password is still refused")
    for first, second, admitted in ((200, None, True), (401, 200, True), (401, 401, False)):
        variables = {"mon_login": {"status": first}, "mon_login_again": {"status": second} if second else {"skipped": True}}
        assert truthy(assert_that(refusal), variables) is admitted, (first, second)
    said = refusal["ansible.builtin.assert"]["fail_msg"]
    assert "lockout" in said and "mon_grafana_admin_user" in said, "a second refusal has two causes, and the message names both"


def test_every_task_that_carries_a_secret_is_silent_and_the_session_is_always_ended():
    for task, _ in _tasks():
        text = yaml.safe_dump({k: v for k, v in task.items() if k not in ("name", "when", "register")})
        if any(name in text for name in SECRET_NAMES):
            assert task.get("no_log") is True, f"{task['name']} carries a secret and would print it on failure"
    (session,) = [task for task in load_tasks(TOKEN) if "always" in task]
    assert [task["name"] for task in session["always"]] == ["end the admin session"]
    assert _uri(session["always"][0])["url"] == "{{ mon_grafana_api }}/logout"


def test_no_tracked_file_carries_a_token_shaped_literal():
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=True).stdout.split(
        "\0"
    )
    assert len(tracked) > 500, "the walk is broken, not the tree clean"
    shaped = re.compile(rb"glsa_[A-Za-z0-9]{32}_[0-9a-f]{8}")
    found = [path for path in tracked if path and (REPO / path).is_file() and shaped.search((REPO / path).read_bytes())]
    assert found == [], f"a Grafana service-account token, or a literal shaped like one, is tracked in: {found}"
```

`WELL_SHAPED` is assembled from its parts on purpose: `test_no_tracked_file_carries_a_token_shaped_literal` walks every tracked file, this one included.

- [ ] **Step 2: Run them and read the failure**

Run: `uv run pytest tests/test_infra_mon_token.py -q -p no:cacheprovider`

Expected: `1 error` during collection, a `KeyError: 'mon_token_pattern'`: the role's defaults do not carry it yet.

- [ ] **Step 3: The defaults**

`infra/ansible/roles/mon/defaults/main.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

# The one service account the workstation's tools hold a token of, and where the role caches that token on the
# controller: outside the tree, since it is minted here and re-minted by any converge that finds it unusable.
mon_service_account: zcrypto-tools
mon_token_var: mon_grafana_tools_token
mon_token_cache: "{{ lookup('ansible.builtin.env', 'HOME') }}/.config/zcrypto/grafana-mon.vault.yml"
# Grafana on loopback, where the role signs in with the vaulted admin password to manage the service account.
mon_grafana_api: "http://127.0.0.1:{{ mon_grafana_port }}"
# What a service-account token looks like. A cached value is held to it before it is placed in a header, and a
# minted one before it is written: a value of another shape makes the request fail with the value in the error.
# It ends in \Z because `$` also matches before a trailing newline, the one shape that has done that.
mon_token_pattern: '^glsa_[A-Za-z0-9]{32}_[0-9a-f]{8}\Z'
```

- [ ] **Step 4: The token tasks**

Create `infra/ansible/roles/mon/tasks/token.yml`:

```yaml
---
# The tools' token: one Editor service account holding exactly one token, cached vault-encrypted on the
# controller. Included only outside check mode: every task here calls Grafana's API or acts on what one returned.
- name: wait for grafana to answer
  ansible.builtin.uri:
    url: "{{ mon_grafana_api }}/api/health"
  register: mon_grafana_health
  until: mon_grafana_health.status | default(0) == 200
  retries: 30
  delay: 2

- name: look for the token cache on the controller
  ansible.builtin.stat:
    path: "{{ mon_token_cache }}"
  register: mon_token_cache_stat
  delegate_to: localhost
  become: false

# An unreadable cache is an absent one: the token is re-minted and the file rewritten.
- name: read the token cache
  ansible.builtin.include_vars:
    file: "{{ mon_token_cache }}"
    name: mon_token_cached
  when: mon_token_cache_stat.stat.exists
  failed_when: false
  no_log: true

- name: keep the cached token only when it has a token's shape
  ansible.builtin.set_fact:
    mon_token_candidate: >-
      {{ (mon_token_cached | default({}))[mon_token_var] | default('') | string
         if ((mon_token_cached | default({}))[mon_token_var] | default('') | string) is match(mon_token_pattern)
         else '' }}
  no_log: true

- name: ask grafana whose token the cached one is
  ansible.builtin.uri:
    url: "{{ mon_grafana_api }}/api/user"
    headers:
      Authorization: "Bearer {{ mon_token_candidate }}"
    status_code: [200, 401, 403]
  register: mon_token_probe
  when: mon_token_candidate | length > 0
  no_log: true

- name: sign in on loopback with the vaulted admin password
  ansible.builtin.uri:
    url: "{{ mon_grafana_api }}/login"
    method: POST
    body_format: json
    body:
      user: "{{ mon_grafana_admin_user }}"
      password: "{{ mon_grafana_admin_password }}"
    status_code: [200, 401]
  register: mon_login
  no_log: true

# A 401 is first read as a password that drifted from the vault. The unit hands Grafana its data path on the
# command line, so the CLI is handed the same one, or it reports success against a new database elsewhere.
- name: reset the admin password from the vault
  ansible.builtin.command:
    argv:
      - runuser
      - -u
      - grafana
      - --
      - /usr/share/grafana/bin/grafana
      - cli
      - --homepath
      - /usr/share/grafana
      - --config
      - /etc/grafana/grafana.ini
      - --configOverrides
      - cfg:default.paths.data=/var/lib/grafana
      - admin
      - reset-admin-password
      - --password-from-stdin
    stdin: "{{ mon_grafana_admin_password }}"
    stdin_add_newline: false
  when: mon_login.status == 401
  changed_when: true
  no_log: true

- name: sign in again after the reset
  ansible.builtin.uri:
    url: "{{ mon_grafana_api }}/login"
    method: POST
    body_format: json
    body:
      user: "{{ mon_grafana_admin_user }}"
      password: "{{ mon_grafana_admin_password }}"
    status_code: [200, 401]
  register: mon_login_again
  when: mon_login.status == 401
  no_log: true

# Never retried: each attempt counts toward the lockout it would be waiting out.
- name: refuse to go on when the vaulted password is still refused
  ansible.builtin.assert:
    that: mon_login.status == 200 or mon_login_again.status == 200
    fail_msg: >-
      Grafana refused the vaulted admin sign-in twice, the second time after resetting the password from the
      vault. Either that is its login lockout: a run of failed sign-ins under the admin's name locks the
      account for about five minutes, and a mistyped password in the UI counts. Wait five minutes without
      signing in, then converge again. Or mon_grafana_admin_user is not the name this database was created
      with: Grafana reads the name only then, so the vault carries the first one for as long as the database
      lives.

- name: act on the service account under the admin session, and end the session whatever happens
  vars:
    mon_session: "{{ (mon_login_again if mon_login.status == 401 else mon_login).cookies_string }}"
  block:
    - name: find the tools' service account by name
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts/search?perpage=1000&query={{ mon_service_account | urlencode }}"
        headers:
          Cookie: "{{ mon_session }}"
      register: mon_sa_search
      no_log: true

    - name: create the tools' service account, an Editor
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts"
        method: POST
        headers:
          Cookie: "{{ mon_session }}"
        body_format: json
        body:
          name: "{{ mon_service_account }}"
          role: Editor
          isDisabled: false
        status_code: [201]
      register: mon_sa_created
      changed_when: true
      when: mon_sa_search.json.serviceAccounts | selectattr('name', 'equalto', mon_service_account) | list | length == 0
      no_log: true

    - name: note the service account as grafana holds it
      ansible.builtin.set_fact:
        mon_sa: >-
          {{ mon_sa_created.json if mon_sa_created is not skipped
             else (mon_sa_search.json.serviceAccounts | selectattr('name', 'equalto', mon_service_account) | first) }}

    - name: return a drifted service account to an enabled Editor
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts/{{ mon_sa.id }}"
        method: PATCH
        headers:
          Cookie: "{{ mon_session }}"
        body_format: json
        body:
          role: Editor
          isDisabled: false
      changed_when: true
      when: mon_sa.role != 'Editor' or mon_sa.isDisabled
      no_log: true

    - name: list the service account's tokens
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts/{{ mon_sa.id }}/tokens"
        headers:
          Cookie: "{{ mon_session }}"
      register: mon_sa_tokens
      no_log: true

    # Kept only when the cached token is this account's and its only one.
    - name: decide whether a token is minted
      ansible.builtin.set_fact:
        mon_token_mint: >-
          {{ (mon_grafana_token_rotate | default(false) | bool)
             or mon_token_candidate | length == 0
             or mon_token_probe.status | default(0) != 200
             or mon_token_probe.json.login | default('') != mon_sa.login
             or mon_sa_tokens.json | length != 1 }}
      no_log: true

    - name: mint the tools' token
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts/{{ mon_sa.id }}/tokens"
        method: POST
        headers:
          Cookie: "{{ mon_session }}"
        body_format: json
        body:
          name: "{{ mon_service_account }}-{{ now(utc=true).strftime('%Y%m%dT%H%M%SZ') }}"
      register: mon_token_minted
      changed_when: true
      when: mon_token_mint
      no_log: true

    - name: refuse a minted token of another shape before it is written
      ansible.builtin.assert:
        that: mon_token_minted.json.key | default('') is match(mon_token_pattern)
        fail_msg: >-
          Grafana returned a token that is not the shape the tools and this role expect; nothing was written
          to the cache. Read the release notes of the installed Grafana for a changed token format.
        quiet: true
      when: mon_token_mint
      no_log: true

    - name: the cache's directory on the controller
      ansible.builtin.file:
        path: "{{ mon_token_cache | dirname }}"
        state: directory
        mode: "0700"
      delegate_to: localhost
      become: false
      when: mon_token_mint

    # The token goes in on stdin with no newline added: one stored with a trailing newline fails the next
    # converge's probe with the token in the error text.
    - name: encrypt the minted token under the repo's vault password
      ansible.builtin.command:
        argv: [ansible-vault, encrypt_string, --stdin-name, "{{ mon_token_var }}"]
        chdir: "{{ playbook_dir }}"
        stdin: "{{ mon_token_minted.json.key }}"
        stdin_add_newline: false
      register: mon_token_encrypted
      changed_when: false
      delegate_to: localhost
      become: false
      when: mon_token_mint
      no_log: true

    - name: write the token cache on the controller
      ansible.builtin.copy:
        content: "{{ mon_token_encrypted.stdout }}\n"
        dest: "{{ mon_token_cache }}"
        mode: "0600"
      delegate_to: localhost
      become: false
      when: mon_token_mint
      no_log: true

    - name: delete every token the mint superseded
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/api/serviceaccounts/{{ mon_sa.id }}/tokens/{{ item.id }}"
        method: DELETE
        headers:
          Cookie: "{{ mon_session }}"
      changed_when: true
      loop: "{{ mon_sa_tokens.json if mon_token_mint else [] }}"
      loop_control:
        label: "{{ item.name }}"
      no_log: true

  always:
    - name: end the admin session
      ansible.builtin.uri:
        url: "{{ mon_grafana_api }}/logout"
        headers:
          Cookie: "{{ mon_session }}"
        follow_redirects: none
        status_code: [200, 302]
      no_log: true
```

- [ ] **Step 5: The include, outside check mode**

`infra/ansible/roles/mon/tasks/main.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

# ---- The tools' credential -------------------------------------------------------------------------
# Every task in it calls Grafana's API or acts on what one returned, so a preview skips it whole.
- name: the tools' service account and its one token
  ansible.builtin.include_tasks: token.yml
  when: not ansible_check_mode
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_infra_mon_token.py tests/test_infra_mon_role.py -q -p no:cacheprovider`

Expected: no failure and no skip.

- [ ] **Step 7: The consumers**

```bash
uv run pytest tests/test_infra_mon_token.py tests/test_infra_mon_role.py tests/test_infra_converge_guards.py tests/test_converge_sh.py tests/test_deploy_log_audit.py tests/test_grafana_auth.py tests/test_config_selectors_are_parsed.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`1827 passed` on the tree this plan was written against).

- [ ] **Step 8: The commit gate**

Run: `uv run pre-commit run -a`

Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 9: Commit**

```bash
git add infra/ansible/roles/mon/defaults/main.yml infra/ansible/roles/mon/tasks/main.yml \
  infra/ansible/roles/mon/tasks/token.yml tests/test_infra_mon_token.py
git commit -F- <<'MSG'
feat(mon): the role keeps one Editor service account and its one token, cached vault-encrypted on the controller

One converge leaves the tools a working credential with no step in the UI and no secret copied by
hand. Outside check mode the role waits for Grafana's health, signs in on loopback through the
login form with the vaulted admin name and password, finds the service account `zcrypto-tools` by
name, creates it an Editor when absent and returns a drifted one to an enabled Editor, and keeps
exactly one token: it mints when the cached one is absent, not a token's shape, refused, another
account's, not the account's only one, or when `-e mon_grafana_token_rotate=true` is passed,
writes the new one to `~/.config/zcrypto/grafana-mon.vault.yml` on the controller, vault-encrypted
and mode 0600, deletes every other, and ends the session whatever happened. No token reaches the
node's disk, a tracked file or a task's output, and the role creates no other account.

The pattern a token is held to ends `\Z`: `$` also matches before a trailing newline, and a token
stored with one made a later request fail with the token in the error text despite `no_log`. A
cached value reaches a header only after that check, and a minted one is checked before it is
written, with no newline added on the way into `ansible-vault`.

A refused sign-in is first read as a password that drifted from the vault and repaired by the CLI
reset, run as `grafana` against the unit's own data path, since without the path override the CLI
reports success against a new database elsewhere. A second refusal fails the converge naming
Grafana's login lockout, and beside it a vaulted name the database was not created with, and is not
retried: each attempt counts toward the lockout.

Whose token the cached one is, is read off the `login` of `/api/user`: for a service-account token
that endpoint answers `id: 0`.

Cases: 11, the conditions evaluated through Ansible's own templar, the last walking every tracked
file for a token-shaped literal.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 10: The tree is clean**

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 11: Prove the guards with fourteen probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time. The controls: the service account renamed in the defaults; the sign-out moved off loopback; the include's file renamed. The mutations take away each of the five corrections, the vaulted admin name and each limit on the credential, and the last writes a token-shaped literal into a tracked file, assembled by the shell so that this plan carries none:

```bash
R=infra/ansible/roles/mon
TOKEN="uv run pytest tests/test_infra_mon_token.py -q -p no:cacheprovider"
infra/scripts/mutate-probe.sh --file $R/defaults/main.yml \
  --control 's/^mon_service_account: zcrypto-tools$/mon_service_account: zcrypto-push/' \
  --mutation "s/_\[0-9a-f\]{8}\\\\Z'$/_[0-9a-f]{8}\$'/" -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^    - name: encrypt the minted token/,/no_log: true/s/stdin_add_newline: false/stdin_add_newline: true/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^- name: reset the admin password from the vault$/,/no_log: true/s/stdin_add_newline: false/stdin_add_newline: true/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^      - --configOverrides$/,+1d' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^- name: sign in again after the reset$/,/no_log: true/s/user: "{{ mon_grafana_admin_user }}"/user: admin/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '0,/role: Editor/s/role: Editor/role: Admin/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^    - name: write the token cache on the controller$/,/no_log: true/{/become: false/d}' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/mon_token_probe.json.login/d' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation 's/^      loop: "{{ mon_sa_tokens.json if mon_token_mint else \[\] }}"$/      loop: "{{ mon_sa_tokens.json }}"/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation '/^    - name: mint the tools. token$/,/^$/{/no_log: true/d}' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation 's/^    that: mon_login.status == 200 or mon_login_again.status == 200$/    that: true/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/token.yml \
  --control 's/^        url: "{{ mon_grafana_api }}\/logout"$/        url: "https:\/\/zcrypto-mon.zhaow.me\/logout"/' \
  --mutation 's/^  always:$/  rescue:/' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^  ansible.builtin.include_tasks: token.yml$/  ansible.builtin.include_tasks: tokens.yml/' \
  --mutation '/^- name: the tools. service account and its one token$/,$s/^  when: not ansible_check_mode$//' -- $TOKEN
infra/scripts/mutate-probe.sh --file $R/defaults/main.yml \
  --control 's/^mon_service_account: zcrypto-tools$/mon_service_account: zcrypto-push/' \
  --mutation "\$a # glsa_$(printf 'a%.0s' $(seq 32))_00000000" -- $TOKEN
```

Expected: each of the fourteen runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 9 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, fourteen runs, each KILLED with its control proven. The
role's defaults, control the service account renamed: the pattern ended `$`, KILLED, control
proven; a token-shaped literal written into the file, KILLED, control proven. `tasks/token.yml`,
control the sign-out moved off loopback: a newline added on the way into `ansible-vault`, KILLED,
control proven; a newline added to the reset's password, KILLED, control proven; the data-path
override dropped from the reset, KILLED, control proven; the second sign-in made under the default
name, KILLED, control proven; the account created an Admin, KILLED,
control proven; the cache written under `become`, KILLED, control proven; the login comparison
dropped from the mint decision, KILLED, control proven; the other tokens deleted without a mint,
KILLED, control proven; the mint's `no_log` dropped, KILLED, control proven; the lockout refusal
made to pass, KILLED, control proven; the sign-out moved from `always` to `rescue`, KILLED, control
proven. `tasks/main.yml`, control the include's file renamed: the include run in check mode,
KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 4: The node ships its own telemetry, checks its reboot flag and reads its own health every five minutes

**Files:**
- Create: `infra/ansible/roles/mon/files/config.alloy`
- Create: `infra/ansible/roles/mon/files/zcrypto-reboot-check.sh`
- Create: `infra/ansible/roles/mon/files/zcrypto-reboot-check.timer`
- Create: `infra/ansible/roles/mon/templates/zcrypto-reboot-check.service.j2`
- Create: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`
- Create: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.timer`
- Create: `infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.service.j2`
- Create: `infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.env.j2`
- Modify: `infra/ansible/roles/mon/defaults/main.yml` (the textfile directory and the self-check's ping URL, appended)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (Alloy, the reboot check and the self-check, appended)
- Modify: `infra/ansible/roles/mon/handlers/main.yml` (`restart alloy`, appended)
- Modify: `infra/grafana/notification-templates/zcrypto-slack.tmpl` (the node's display name)
- Test (new): `tests/test_mon_selfcheck.py`
- Test: `tests/test_infra_mon_role.py` (four Alloy cases appended)
- Test: `tests/test_reboot_check.py`
- Test: `tests/test_dashboards_cover_metrics.py`

**Interfaces:**
- Consumes: Task 2's role, its stores on loopback, its preview fact `mon_units_previewed` and its `reload systemd` handler; the `alloy` package Task 2 installs; the capture role's `zcrypto-reboot-check.sh` and `.timer`, whose program the copy keeps; `tests/test_reboot_check.py`'s `COPY_ROLES` and `tests/test_dashboards_cover_metrics.py`'s `KEEP_REGEX_FILES`.
- Produces, for Task 7 and the Rollout to use by these exact names: the labels `host="zcrypto-mon"` and the jobs `integrations/unix`, `integrations/self`, `grafana`, `prometheus`, `loki`; the log label `container`, the unit's name without `.service`, for `grafana-server`, `prometheus`, `loki`, `caddy`, `alloy`, `zcrypto-mon-selfcheck`, `zcrypto-reboot-check`; `node_reboot_required` from `/var/lib/zcrypto-node-textfile/reboot.prom`; the timer `zcrypto-mon-selfcheck.timer` and the default `mon_selfcheck_healthcheck_url`, empty; the Slack name `Monitor`; `UNFILTERED_HOSTS` in `tests/test_dashboards_cover_metrics.py`.

**What this task decides, where the spec leaves it open:**
- The series the self-check reads as "rule evaluation is fresh" (the spec's open question, read off Grafana 13.2.3's `/metrics`): `grafana_alerting_ticker_last_consumed_tick_timestamp_seconds`, which must be within 60 s of now, and `grafana_alerting_schedule_alert_rules`, which must be at least 1, so a Grafana with no rule pushed does not read as healthy. The scheduler ticks every 10 s, so 60 s is six missed ticks and one evaluation interval.
- The self-check is one Python file on the node's own `python3`, standard library alone, run by a oneshot unit under `DynamicUser=yes`: it reads three loopback URLs and writes nothing. It pings only when all three reads pass and a URL is set, always exits 0, and prints one line saying what it read, never the URL. Its fleet read is `count(count by (host) (up{host!="zcrypto-mon"}))`, at least 1, which in this phase fails by design: no fleet host ships yet, the URL is empty, and the line reads `fleet=FAIL … -> not pinging` until phase 2.
- The ping URL is the default `mon_selfcheck_healthcheck_url: ""`, rendered into `/etc/default/zcrypto-mon-selfcheck`, mode 0600, for systemd's manager to read before the unit drops to its dynamic user; R4's journal read of the unit is the first proof of that on the node, and no line there, or `Failed to load environment files`, is a stop. Phase 2 vaults the minted check's URL under that name when the power-off drill is scheduled (spec D16).
- The timer fires at `*:0/5:23`, every five minutes and off the minute boundary, with no `Persistent=`: a slot missed while the node was down is the signal.
- Alloy's config is the role's sixth: the unix exporter's six collectors with the textfile directory, Alloy's own metrics, and three scrapes of Grafana, Prometheus and Loki on loopback, written to `http://127.0.0.1:9090/api/v1/write` with no `basic_auth` and no `write_relabel_config`; the journals of the seven units, kept by one `regex` on `_SYSTEMD_UNIT`, with a `level` label parsed from logfmt and JSON lines, written to `http://127.0.0.1:3100/loki/api/v1/push`. It is validated by `alloy validate` before it replaces the live file, and a change restarts Alloy.
- `UNFILTERED_HOSTS` names the node in `tests/test_dashboards_cover_metrics.py`: a host whose config carries no keep regex admits every family, so a panel or rule over the node's series is not held to a keep-list. A host that admits everything is no evidence that a family exists on Grafana Cloud, which never receives it, so a check that asks "does some host admit this family" leaves the unfiltered hosts out. `keep_regexes()` has two callers before this task: `_host_variables`, which reads the cache role's regex alone, and `test_every_alerted_family_is_admitted_where_its_rule_selects`, whose per-host loop reads one host's regex at a time and whose `any()`, for a rule that names no host and whose publisher is unmapped, is the one use that aggregates across hosts. This task narrows that `any()` to the filtered hosts. The same file gains the case that holds the Slack template's host names to the topology.
- No clock-offset copy: the capture hosts' probe exists for the order path's timestamps, and the node's `chrony` role is its clock.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mon_selfcheck.py`:

```python
"""The observability node's self-check, `zcrypto-mon-selfcheck.py`, driven with a canned opener: it pings the node's
dead-man only while the scheduler ticks, a fleet sample is fresh and Loki is ready, and a failing check sends
nothing -- the missing ping is the page."""

from __future__ import annotations

import configparser
import io
import json
import re
import types
import urllib.error
from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import find_task, load_tasks, when_conditions

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/mon"
SCRIPT = ROLE / "files/zcrypto-mon-selfcheck.py"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
# Compiled from its text, never imported by path: an import writes a bytecode cache beside the script, inside a
# role's files/, and the cache names the checkout's own path, which tests/test_deploy_log_audit.py walks the role for.
selfcheck = types.ModuleType("mon_selfcheck")
exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), selfcheck.__dict__)

NOW = 1_790_000_000.0
PING = "https://hc-ping.invalid/abc"
ENV = {
    "MON_SELFCHECK_GRAFANA": "http://127.0.0.1:3000",
    "MON_SELFCHECK_PROMETHEUS": "http://127.0.0.1:9090",
    "MON_SELFCHECK_LOKI": "http://127.0.0.1:3100",
    "MON_SELFCHECK_HEALTHCHECK_URL": PING,
}


def _metrics(tick_age: float | None = 4.0, scheduled: int | None = 114) -> str:
    lines = ["# TYPE grafana_alerting_ticker_last_consumed_tick_timestamp_seconds gauge"]
    if tick_age is not None:
        lines.append(f"grafana_alerting_ticker_last_consumed_tick_timestamp_seconds {NOW - tick_age!r}")
    if scheduled is not None:
        lines.append(f"grafana_alerting_schedule_alert_rules {scheduled}")
        lines.append("grafana_alerting_schedule_alert_rules_hash 1.4695981039346655e+19")
    return "\n".join(lines) + "\n"


def _fleet(hosts: int | None) -> str:
    result = [] if hosts is None else [{"metric": {}, "value": [NOW, str(hosts)]}]
    return json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}})


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _run(capsys, *, metrics=None, fleet=8, loki="ready\n", refused=None, env=ENV, broken=()):
    """`refused` is Loki's own not-ready answer: a 503 whose body is the reason."""
    asked: list[str] = []
    bodies = {
        "http://127.0.0.1:3000/metrics": _metrics() if metrics is None else metrics,
        "http://127.0.0.1:9090/api/v1/query": _fleet(fleet),
        "http://127.0.0.1:3100/ready": loki,
        PING: "OK",
    }

    def opener(request, timeout):
        url = request.full_url
        asked.append(url)
        base = url.split("?")[0]
        if base in broken:
            raise urllib.error.URLError("connection refused")
        if refused is not None and base == "http://127.0.0.1:3100/ready":
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, io.BytesIO(refused.encode()))
        return _Response(bodies[base].encode())

    rc = selfcheck.main(env, opener=opener, now=lambda: NOW)
    return rc, asked, capsys.readouterr().out.strip()


def test_a_node_doing_its_job_pings_and_says_what_it_read(capsys):
    rc, asked, out = _run(capsys)
    assert rc == 0 and asked[-1] == PING
    assert out == (
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> pinged"
    )
    query = next(url for url in asked if url.startswith("http://127.0.0.1:9090/"))
    assert "query=count%28count+by+%28host%29+%28up%7Bhost%21%3D%22zcrypto-mon%22%7D%29%29" in query


@pytest.mark.parametrize(
    ("fault", "said"),
    [
        ({"metrics": _metrics(tick_age=61.0)}, "rules=FAIL (the scheduler's last tick is 61 s old)"),
        ({"metrics": _metrics(tick_age=None)}, "rules=FAIL (Grafana's /metrics carries no scheduler tick)"),
        ({"metrics": _metrics(scheduled=0)}, "rules=FAIL (no rule is scheduled)"),
        ({"fleet": None}, "fleet=FAIL (no fleet host has a sample in the last five minutes)"),
        ({"fleet": 0}, "fleet=FAIL (no fleet host has a sample in the last five minutes)"),
        (
            {"refused": "Ingester not ready: waiting for 15s after being ready\n"},
            "loki=FAIL (answered 503: 'Ingester not ready: waiting for 15s after being ready')",
        ),
        ({"loki": "starting\n"}, "loki=FAIL (answered 'starting')"),
        ({"broken": ("http://127.0.0.1:3000/metrics",)}, "rules=FAIL (unreadable: URLError)"),
        ({"broken": ("http://127.0.0.1:9090/api/v1/query",)}, "fleet=FAIL (unreadable: URLError)"),
        ({"broken": ("http://127.0.0.1:3100/ready",)}, "loki=FAIL (unreadable: URLError)"),
    ],
    ids=[
        "tick stale",
        "no tick",
        "no rules",
        "no fleet series",
        "zero fleet hosts",
        "loki not ready",
        "loki answering something else",
        "grafana down",
        "prometheus down",
        "loki down",
    ],
)
def test_one_failing_check_sends_no_ping_and_still_exits_clean(capsys, fault, said):
    rc, asked, out = _run(capsys, **fault)
    assert rc == 0, "a failing unit every five minutes would be the noise; the missing ping is the page"
    assert PING not in asked
    assert said in out and out.endswith("-> not pinging")
    assert len([url for url in asked if url != PING]) == 3, "one unreadable endpoint must not hide the other two readings"


def test_the_tick_bar_is_one_minute(capsys):
    assert selfcheck.TICK_MAX_AGE_SECONDS == 60
    assert _run(capsys, metrics=_metrics(tick_age=60.0))[1][-1] == PING


def test_with_no_ping_url_a_healthy_node_reads_everything_and_pings_nothing(capsys):
    """The check is minted when the power-off drill is scheduled; until then the timer runs and pings nothing."""
    rc, asked, out = _run(capsys, env={**ENV, "MON_SELFCHECK_HEALTHCHECK_URL": ""})
    assert rc == 0 and len(asked) == 3 and out.endswith("-> healthy, and no ping URL is set")


def test_a_ping_that_fails_is_reported_and_the_unit_still_exits_clean(capsys):
    rc, asked, out = _run(capsys, broken=(PING,))
    assert rc == 0 and asked[-1] == PING and out.endswith("-> ping failed: URLError")


def test_the_ping_url_never_reaches_the_output(capsys):
    for kwargs in ({}, {"broken": (PING,)}, {"fleet": 0}):
        assert PING not in _run(capsys, **kwargs)[2]


# --- the unit, its environment file and its timer ----------------------------------------------------------------
def _render(name: str, **extra) -> str:
    variables = {k: v for k, v in DEFAULTS.items() if k != "mon_token_cache"} | extra
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template((ROLE / "templates" / name).read_text()))


def test_the_unit_and_its_environment_file_set_every_name_the_script_reads():
    read = set(re.findall(r'env(?:\.get\(|\[)"(MON_SELFCHECK_[A-Z_]+)"', SCRIPT.read_text()))
    unit = _render("zcrypto-mon-selfcheck.service.j2")
    in_unit = dict(line.removeprefix("Environment=").split("=", 1) for line in unit.splitlines() if line.startswith("Environment="))
    assert in_unit == {
        "MON_SELFCHECK_GRAFANA": "http://127.0.0.1:3000",
        "MON_SELFCHECK_PROMETHEUS": "http://127.0.0.1:9090",
        "MON_SELFCHECK_LOKI": "http://127.0.0.1:3100",
    }
    env_file = _render("zcrypto-mon-selfcheck.env.j2", mon_selfcheck_healthcheck_url=PING)
    in_file = dict(line.split("=", 1) for line in env_file.splitlines() if line and not line.startswith("#"))
    assert in_file == {"MON_SELFCHECK_HEALTHCHECK_URL": PING}
    assert read == set(in_unit) | set(in_file), "a name the script reads that nothing sets is a KeyError on every run"
    assert DEFAULTS["mon_selfcheck_healthcheck_url"] == "", "the check is not minted at node-up, so the default pings nothing"


def test_the_unit_runs_what_the_role_installs_as_no_standing_user_and_reads_the_url_from_a_root_only_file():
    parser = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str
    unit = _render("zcrypto-mon-selfcheck.service.j2")
    parser.read_string("\n".join(line for line in unit.splitlines() if not line.startswith("Environment=")))
    service = parser["Service"]
    assert service["ExecStart"] == "/usr/bin/python3 /usr/local/sbin/zcrypto-mon-selfcheck"
    assert (service["Type"], service["DynamicUser"], service["EnvironmentFile"]) == (
        "oneshot",
        "true",
        "/etc/default/zcrypto-mon-selfcheck",
    )
    tasks = load_tasks(ROLE / "tasks/main.yml")
    script = find_task(tasks, "install the self-check script")["ansible.builtin.copy"]
    assert (script["src"], script["dest"]) == ("zcrypto-mon-selfcheck.py", "/usr/local/sbin/zcrypto-mon-selfcheck")
    env = find_task(tasks, "render the self-check's ping URL, read by systemd alone")
    assert env["ansible.builtin.template"]["dest"] == service["EnvironmentFile"]
    assert (env["ansible.builtin.template"]["mode"], env["no_log"], env["diff"]) == ("0600", True, False)


def test_the_timer_runs_every_five_minutes_and_is_what_the_role_enables():
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string((ROLE / "files/zcrypto-mon-selfcheck.timer").read_text())
    assert parser["Timer"]["OnCalendar"] == "*:0/5:23" and "Persistent" not in parser["Timer"]
    assert parser["Timer"]["Unit"] == "zcrypto-mon-selfcheck.service"
    enable = find_task(load_tasks(ROLE / "tasks/main.yml"), "enable + start the self-check timer")
    assert enable["ansible.builtin.systemd_service"] == {
        "name": "zcrypto-mon-selfcheck.timer",
        "daemon_reload": True,
        "enabled": True,
        "state": "started",
    }
    assert when_conditions(enable) == ["not (ansible_check_mode and mon_selfcheck_timer_install is changed)"]
```

The module is loaded with `exec(compile(...))` and not imported, so no `__pycache__` appears beside the role's script, where `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` would read its path.

`tests/test_infra_mon_role.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- the node's own Alloy: on loopback, with no credential and no filter -----------------------------------------
ALLOY = ROLE / "files/config.alloy"


def _alloy_blocks() -> dict[str, list]:
    lines = [line for line in ALLOY.read_text().splitlines() if not line.strip().startswith("//")]
    return dict(_blocks(lines))


def _assigned(block: list, key: str) -> str:
    (value,) = [line.split("=", 1)[1].strip() for line, _ in block if line.split("=")[0].strip() == key]
    return value


def test_the_node_ships_to_its_own_stores_on_loopback_with_no_credential_and_no_filter():
    blocks = _alloy_blocks()
    remote = blocks['prometheus.remote_write "mon"']
    endpoint = dict(remote)["endpoint"]
    assert endpoint == [(f'url = "http://127.0.0.1:{DEFAULTS["mon_prometheus_port"]}/api/v1/write"', [])], endpoint
    assert dict(remote)["external_labels ="] == [('host = "zcrypto-mon",', [])]
    assert dict(blocks['loki.write "mon"'])["endpoint"] == [
        (f'url = "http://127.0.0.1:{DEFAULTS["mon_loki_port"]}/loki/api/v1/push"', [])
    ]
    kinds = {line.split()[0] for line in blocks}
    assert not kinds & {"prometheus.relabel", "write_relabel_config"}, "the node's leg carries no keep or drop list"


def test_the_node_scrapes_its_host_itself_and_its_three_services():
    blocks = _alloy_blocks()
    unix = blocks['prometheus.exporter.unix "host"']
    assert _assigned(unix, "set_collectors") == '["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"]'
    assert dict(unix)["textfile"] == [(f'directory = "{DEFAULTS["mon_textfile_dir"]}"', [])]
    assert 'prometheus.exporter.self "alloy"' in {line.removesuffix(" {}") for line in blocks}
    ports = {"grafana": "mon_grafana_port", "prometheus": "mon_prometheus_port", "loki": "mon_loki_port"}
    for job, port in ports.items():
        scrape = blocks[f'prometheus.scrape "{job}"']
        assert _assigned(scrape, "targets") == f'[{{"__address__" = "127.0.0.1:{DEFAULTS[port]}"}}]', job
        assert _assigned(scrape, "job_name") == f'"{job}"'
    for name, block in blocks.items():
        if name.startswith("prometheus.scrape "):
            assert _assigned(block, "forward_to") == "[prometheus.remote_write.mon.receiver]", name
            assert _assigned(block, "scrape_interval") == '"60s"', name


def test_the_journal_keep_rule_names_the_units_this_role_runs():
    relabel = _alloy_blocks()['loki.relabel "journal_units"']
    (keep,) = [rule for line, rule in relabel if line == "rule" and ('action        = "keep"', []) in rule]
    (pattern,) = re.findall(r'^"\((.*)\)\\\\\.service"$', _assigned(keep, "regex"))
    timers = {p.name.removesuffix(".timer") for p in (ROLE / "files").glob("*.timer")}
    assert set(pattern.split("|")) == {"grafana-server", "prometheus", "loki", "caddy", "alloy"} | timers
    assert ('replacement  = "zcrypto-mon"', []) in [entry for line, rule in relabel if line == "rule" for entry in rule]


def test_the_alloy_config_is_validated_and_alloy_restarted_on_a_change():
    tasks = load_tasks(TASKS)
    copy = find_task(tasks, "alloy config — the node's own metrics and journals, written to its stores on loopback")
    assert copy["ansible.builtin.copy"]["validate"] == "alloy validate %s" and copy["notify"] == "restart alloy"
    (handler,) = [h for h in yaml.safe_load(HANDLERS.read_text()) if h["name"] == "restart alloy"]
    assert handler["ansible.builtin.systemd_service"] == {"name": "alloy", "state": "restarted"}
```

`tests/test_reboot_check.py` — replace

```python
COPY_ROLES = {"cache": "cache_textfile_dir", "ops": "ops_textfile_dir"}
```

with

```python
COPY_ROLES = {"cache": "cache_textfile_dir", "ops": "ops_textfile_dir", "mon": "mon_textfile_dir"}
```

`tests/test_reboot_check.py` — replace

```python
# --- the cache and ops roles' copies ------------------------------------------------------------
# The cache nodes and ops publish the same flag from a copy of this role's script, timer and unit, so the fleet's
```

with

```python
# --- the cache, ops and mon roles' copies -------------------------------------------------------
# The cache nodes, ops and the observability node publish the same flag from a copy of this role's script, timer and unit, so the fleet's
```

`tests/test_reboot_check.py` — after

```python
def test_the_cache_unit_writes_into_the_directory_the_cache_alloy_scrapes():
    unit = (CACHE_ROLE_DIR / "templates/zcrypto-reboot-check.service.j2").read_text()
    unit = unit.replace("{{ cache_textfile_dir }}", _resolved_default("cache", "cache_textfile_dir"))
    host_dir = str(Path(next(line for line in unit.splitlines() if line.startswith("ExecStart=")).split()[-1]).parent)
    assert host_dir == "/var/lib/zcrypto-node-textfile", host_dir
    alloy = (CACHE_ROLE_DIR / "files/config.alloy").read_text()
    directory = next(line for line in alloy.splitlines() if line.strip().startswith("directory")).split('"')[1]
    assert directory == f"/host/root{host_dir}", f"unit writes {host_dir}, collector reads {directory}"
```

insert (the insert opens with 2 blank lines, kept)

```python


def test_the_mon_unit_writes_into_the_directory_the_mon_alloy_scrapes():
    """The node's Alloy is the apt package, not a container: it reads the host's own path, with no /host/root in front."""
    mon = REPO / "infra/ansible/roles/mon"
    unit = (mon / "templates/zcrypto-reboot-check.service.j2").read_text()
    unit = unit.replace("{{ mon_textfile_dir }}", _resolved_default("mon", "mon_textfile_dir"))
    host_dir = str(Path(next(line for line in unit.splitlines() if line.startswith("ExecStart=")).split()[-1]).parent)
    alloy = (mon / "files/config.alloy").read_text()
    set_collectors = next(line for line in alloy.splitlines() if line.strip().startswith("set_collectors"))
    # config-selector-ok: the needle carries both quotes, so "textfiles" cannot satisfy it
    assert '"textfile"' in set_collectors, f"the textfile collector is not enabled: {set_collectors.strip()}"
    directory = next(line for line in alloy.splitlines() if line.strip().startswith("directory")).split('"')[1]
    assert directory == host_dir, f"unit writes {host_dir}, collector reads {directory}"
```

`tests/test_dashboards_cover_metrics.py` — replace

```python
    "zcrypto-valkey3": REPO / "infra/ansible/roles/cache/files/config.alloy",
}
```

with

```python
    "zcrypto-valkey3": REPO / "infra/ansible/roles/cache/files/config.alloy",
    "zcrypto-mon": REPO / "infra/ansible/roles/mon/files/config.alloy",
}
# The hosts whose config ships with no keep and no drop list, so every family they publish exists: the
# observability node writes to its own stores, where no series budget applies.
UNFILTERED_HOSTS = frozenset({"zcrypto-mon"})
```

`tests/test_dashboards_cover_metrics.py` — replace

```python
    for host, path in KEEP_REGEX_FILES.items():
        blocks = re.findall(r"write_relabel_config\s*\{(.*?)\}", path.read_text(), re.DOTALL)
        keeps = [b for b in blocks if "action" in b and '"keep"' in b]
```

with

```python
    for host, path in KEEP_REGEX_FILES.items():
        blocks = re.findall(r"write_relabel_config\s*\{(.*?)\}", path.read_text(), re.DOTALL)
        if host in UNFILTERED_HOSTS:
            assert blocks == [], f"{path}: {host} is listed as unfiltered and its config carries a relabel block"
            compiled[host] = re.compile(r"\A.*\Z", re.DOTALL)
            continue
        keeps = [b for b in blocks if "action" in b and '"keep"' in b]
```

`tests/test_dashboards_cover_metrics.py` — replace

```python
        if hosts is None:
            if not any(keep.match(family) for keep in keeps.values()):
```

with

```python
        if hosts is None:
            # An unfiltered host admits every family, so its admitting this one is no evidence the family exists.
            if not any(keep.match(family) for host, keep in keeps.items() if host not in UNFILTERED_HOSTS):
```

`tests/test_dashboards_cover_metrics.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


def test_an_unfiltered_host_admits_every_family_and_a_filtered_one_does_not():
    keeps = keep_regexes()
    for family in ("node_filesystem_avail_bytes", "prometheus_tsdb_head_series", "grafana_alerting_rule_evaluations_total"):
        assert keeps["zcrypto-mon"].match(family), family
    assert not keeps["zaccess"].match("prometheus_tsdb_head_series")
    assert UNFILTERED_HOSTS <= set(KEEP_REGEX_FILES)


def test_a_family_only_an_unfiltered_host_admits_is_still_refused(monkeypatch):
    family = "zcrypto_family_no_keep_list_admits_total"
    assert keep_regexes()["zcrypto-mon"].match(family) and publishing_hosts(family) is None
    monkeypatch.setitem(globals(), "_admission_expectations", lambda: [("a-rule", family, None, _BECAUSE_PUBLISHED)])
    with pytest.raises(AssertionError, match="NO host's keep-regex admits it"):
        test_every_alerted_family_is_admitted_where_its_rule_selects()


def test_the_slack_template_names_every_host_of_the_topology():
    """A host the template's map lacks reaches a phone as its raw label."""
    template = (REPO / "infra/grafana/notification-templates/zcrypto-slack.tmpl").read_text()
    define = template[template.index('{{ define "zcrypto.host" -}}') :]
    named = set(re.findall(r'eq \. "([^"]+)" \}\}', define[: define.index("{{- end -}}")]))
    assert named == set(KEEP_REGEX_FILES), (
        f"only in the template {sorted(named - set(KEEP_REGEX_FILES))}, only in the topology {sorted(set(KEEP_REGEX_FILES) - named)}"
    )
```

- [ ] **Step 2: Run them and read the failure**

Run: `uv run pytest tests/test_mon_selfcheck.py tests/test_infra_mon_role.py tests/test_reboot_check.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`

Expected: `1 error` during collection, a `FileNotFoundError` on `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`, which stops the run before the other three files' new cases are reached.

- [ ] **Step 3: The defaults**

`infra/ansible/roles/mon/defaults/main.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

# The directory the node's Alloy textfile collector reads.
mon_textfile_dir: /var/lib/zcrypto-node-textfile

# The healthchecks.io ping URL of the node's self-check. Empty skips the ping, the ops role's semantics: the
# check is minted when the node's power-off drill is scheduled, and until then the timer runs and pings nothing.
mon_selfcheck_healthcheck_url: ""
```

- [ ] **Step 4: The node's config.alloy**

Create `infra/ansible/roles/mon/files/config.alloy`:

```alloy
// Grafana Alloy config for the observability node (zcrypto-mon). Installed by the `mon` role with
// `ansible.builtin.copy` at /etc/alloy/config.alloy, so edit this file, never the host's copy.
//
// Native Alloy, the apt package under systemd: it reads the host's real /proc, /sys and journal, and
// writes to the node's own Prometheus and Loki on loopback, with no credential and no filter: a fleet
// host that ships to the node goes through Caddy with a credential, and this one is on the node.
//
// EDITING NOTE -- test suites pull assignments out of this file by PREFIX (`line.strip().startswith(<key>)`).
// Keep every config key the first non-space token on exactly one line.

// ---- Host metrics -------------------------------------------------------------------------------
// The textfile directory is where the role's reboot check writes reboot.prom, the pending-reboot flag.
prometheus.exporter.unix "host" {
  set_collectors = ["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"]

  textfile {
    directory = "/var/lib/zcrypto-node-textfile"
  }
}

prometheus.exporter.self "alloy" {}

// No `job_name` here: exporter targets carry their own `job` label (integrations/unix, integrations/self).
prometheus.scrape "host" {
  targets         = array.concat(prometheus.exporter.unix.host.targets, prometheus.exporter.self.alloy.targets)
  forward_to      = [prometheus.remote_write.mon.receiver]
  scrape_interval = "60s"
}

// ---- The node's own services --------------------------------------------------------------------
// Grafana, Prometheus and Loki each serve /metrics on loopback. The node's rules select them by these
// job names.
prometheus.scrape "grafana" {
  targets         = [{"__address__" = "127.0.0.1:3000"}]
  job_name        = "grafana"
  forward_to      = [prometheus.remote_write.mon.receiver]
  scrape_interval = "60s"
}

prometheus.scrape "prometheus" {
  targets         = [{"__address__" = "127.0.0.1:9090"}]
  job_name        = "prometheus"
  forward_to      = [prometheus.remote_write.mon.receiver]
  scrape_interval = "60s"
}

prometheus.scrape "loki" {
  targets         = [{"__address__" = "127.0.0.1:3100"}]
  job_name        = "loki"
  forward_to      = [prometheus.remote_write.mon.receiver]
  scrape_interval = "60s"
}

// ---- remote_write -------------------------------------------------------------------------------
prometheus.remote_write "mon" {
  external_labels = {
    host = "zcrypto-mon",
  }

  endpoint {
    url = "http://127.0.0.1:9090/api/v1/write"
  }
}

// ---- Logs: the node's units ---------------------------------------------------------------------
loki.relabel "journal_units" {
  forward_to = []

  rule {
    source_labels = ["__journal__systemd_unit"]
    regex         = "(grafana-server|prometheus|loki|caddy|alloy|zcrypto-mon-selfcheck|zcrypto-reboot-check)\\.service"
    action        = "keep"
  }

  // Unit name minus ".service" -> `container`, the label every fleet log selector keys on.
  rule {
    source_labels = ["__journal__systemd_unit"]
    regex         = "(.+)\\.service"
    target_label  = "container"
    replacement   = "$1"
  }

  rule {
    target_label = "host"
    replacement  = "zcrypto-mon"
  }
}

loki.source.journal "mon_units" {
  relabel_rules = loki.relabel.journal_units.rules
  forward_to    = [loki.process.parse.receiver]
  // Unset, an outage longer than 7h skips the journal between the cursor and now-7h for good.
  max_age       = "48h"
}

loki.process "parse" {
  forward_to = [loki.write.mon.receiver]

  // Grafana, Prometheus, Loki and Alloy log logfmt with a `level` key. A line of another shape renders
  // an empty level, which the labels stage drops, so it ships with no `level` label.
  stage.match {
    selector = "{container=~\"grafana-server|prometheus|loki|alloy\"}"

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

  // Caddy logs JSON with a `level` key.
  stage.match {
    selector = "{container=\"caddy\"}"

    stage.json {
      expressions = { level = "level" }
    }

    stage.template {
      source   = "level"
      template = "{{ if eq .Value \"warn\" }}WARNING{{ else if eq .Value \"fatal\" }}CRITICAL{{ else }}{{ ToUpper .Value }}{{ end }}"
    }

    stage.labels {
      values = { level = "level" }
    }
  }
}

loki.write "mon" {
  endpoint {
    url = "http://127.0.0.1:3100/loki/api/v1/push"
  }
}
```

- [ ] **Step 5: The reboot check, a copy of the capture hosts'**

The script's program and the timer's settings are the capture role's, as the cache role's copies are; the header comments name this role. `tests/test_reboot_check.py` holds each copying role's program equal to the capture role's, comments aside.

Create `infra/ansible/roles/mon/files/zcrypto-reboot-check.sh`, mode `0755` (`chmod 0755 infra/ansible/roles/mon/files/zcrypto-reboot-check.sh`):

```bash
#!/usr/bin/env bash
# Installed by the `mon` role at /usr/local/sbin/zcrypto-reboot-check, a copy of the capture role's;
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

Create `infra/ansible/roles/mon/files/zcrypto-reboot-check.timer`:

```ini
# Installed by the `mon` Ansible role at /etc/systemd/system/zcrypto-reboot-check.timer, a copy of
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

Create `infra/ansible/roles/mon/templates/zcrypto-reboot-check.service.j2`:

```ini
# Rendered by the `mon` Ansible role at /etc/systemd/system/zcrypto-reboot-check.service; edit
# infra/ansible/roles/mon/templates/zcrypto-reboot-check.service.j2 and re-converge. A copy of the
# capture role's unit.
[Unit]
Description=Publish the pending-reboot flag as a node-exporter textfile

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zcrypto-reboot-check /run/reboot-required {{ mon_textfile_dir }}/reboot.prom
# This unit only ever writes one .prom, which ProtectSystem=strict makes structural.
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={{ mon_textfile_dir }}
```

- [ ] **Step 6: The self-check, its unit, its timer and its environment file**

Create `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`, mode `0755` (`chmod 0755 infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`):

```python
#!/usr/bin/env python3
"""The observability node's self-check, installed by the `mon` role at /usr/local/sbin/zcrypto-mon-selfcheck.

A rule cannot page the death of the node it runs on, so this pings a healthchecks.io check only while the node
does its job: Grafana's rule scheduler is ticking, a fleet host's sample is fresh in Prometheus, and Loki answers
ready. A failing check sends nothing and exits 0: the missing ping is the page. The unit's Environment= lines
name the three loopback endpoints; its environment file carries the ping URL, empty until the check is minted.
tests/test_mon_selfcheck.py drives this file.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TICK = "grafana_alerting_ticker_last_consumed_tick_timestamp_seconds"
SCHEDULED = "grafana_alerting_schedule_alert_rules"
# The scheduler ticks every ten seconds, so a minute without one is six missed.
TICK_MAX_AGE_SECONDS = 60
# An instant query reaches back five minutes, so this counts the fleet hosts with a sample at most that old.
FLEET_QUERY = 'count(count by (host) (up{host!="zcrypto-mon"}))'
TIMEOUT_SECONDS = 10


def _get(url: str, opener) -> str:
    with opener(urllib.request.Request(url), timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode()


def _sample(text: str, name: str) -> float | None:
    for line in text.splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    return None


def rules_fresh(base: str, *, opener, now: float) -> tuple[bool, str]:
    text = _get(f"{base}/metrics", opener)
    tick, scheduled = _sample(text, TICK), _sample(text, SCHEDULED)
    if tick is None or scheduled is None:
        return False, "Grafana's /metrics carries no scheduler tick"
    age = now - tick
    if scheduled < 1:
        return False, "no rule is scheduled"
    if age > TICK_MAX_AGE_SECONDS:
        return False, f"the scheduler's last tick is {age:.0f} s old"
    return True, f"{scheduled:.0f} rules scheduled, last tick {age:.0f} s ago"


def fleet_fresh(base: str, *, opener) -> tuple[bool, str]:
    reply = json.loads(_get(f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": FLEET_QUERY}), opener))
    result = reply["data"]["result"]
    hosts = int(float(result[0]["value"][1])) if result else 0
    if hosts < 1:
        return False, "no fleet host has a sample in the last five minutes"
    return True, f"{hosts} fleet hosts shipping"


def loki_ready(base: str, *, opener) -> tuple[bool, str]:
    try:
        body = _get(f"{base}/ready", opener).strip()
    except urllib.error.HTTPError as refused:
        # Loki answers a not-ready ingester with a 503 whose body is the reason.
        return False, f"answered {refused.code}: {refused.read().decode().strip()[:60]!r}"
    return (True, "ready") if body == "ready" else (False, f"answered {body[:60]!r}")


def main(env=os.environ, *, opener=urllib.request.urlopen, now=time.time) -> int:
    checks = (
        ("rules", lambda: rules_fresh(env["MON_SELFCHECK_GRAFANA"], opener=opener, now=now())),
        ("fleet", lambda: fleet_fresh(env["MON_SELFCHECK_PROMETHEUS"], opener=opener)),
        ("loki", lambda: loki_ready(env["MON_SELFCHECK_LOKI"], opener=opener)),
    )
    healthy, parts = True, []
    for name, check in checks:
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 -- an endpoint that cannot be read is the finding, whatever it raised
            ok, detail = False, f"unreadable: {type(exc).__name__}"
        healthy = healthy and ok
        parts.append(f"{name}={'ok' if ok else 'FAIL'} ({detail})")
    url = env.get("MON_SELFCHECK_HEALTHCHECK_URL", "")
    if not healthy:
        verdict = "not pinging"
    elif not url:
        verdict = "healthy, and no ping URL is set"
    else:
        try:
            _get(url, opener)
            verdict = "pinged"
        except Exception as exc:  # noqa: BLE001 -- a ping that fails is reported; the next run sends another
            verdict = f"ping failed: {type(exc).__name__}"
    print(f"selfcheck: {' '.join(parts)} -> {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Create `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.timer`:

```ini
# Installed by the `mon` Ansible role at /etc/systemd/system/zcrypto-mon-selfcheck.timer; edit this file
# and re-converge instead of editing the host's copy.
[Unit]
Description=Every-5-minutes self-check of the observability node

[Timer]
# Every 5 minutes, off the minute boundary: the check's 600 s timeout and 600 s grace tolerate one missed
# slot before paging. No Persistent=: a slot missed while the node was down is the signal.
OnCalendar=*:0/5:23
Unit=zcrypto-mon-selfcheck.service

[Install]
WantedBy=timers.target
```

Create `infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.service.j2`:

```ini
# Rendered by the `mon` Ansible role at /etc/systemd/system/zcrypto-mon-selfcheck.service; edit
# infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.service.j2 and re-converge.
[Unit]
Description=Ping the observability node's dead-man while rules evaluate, fleet samples arrive and Loki is ready
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
Environment=MON_SELFCHECK_GRAFANA=http://127.0.0.1:{{ mon_grafana_port }}
Environment=MON_SELFCHECK_PROMETHEUS=http://127.0.0.1:{{ mon_prometheus_port }}
Environment=MON_SELFCHECK_LOKI=http://127.0.0.1:{{ mon_loki_port }}
# The ping URL, MON_SELFCHECK_HEALTHCHECK_URL, in a root-only file systemd reads before it drops privileges.
EnvironmentFile=/etc/default/zcrypto-mon-selfcheck
ExecStart=/usr/bin/python3 /usr/local/sbin/zcrypto-mon-selfcheck
DynamicUser=true
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
```

Create `infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.env.j2`:

```
# Rendered by the `mon` Ansible role at /etc/default/zcrypto-mon-selfcheck; edit
# infra/ansible/roles/mon/templates/zcrypto-mon-selfcheck.env.j2 and re-converge.
MON_SELFCHECK_HEALTHCHECK_URL={{ mon_selfcheck_healthcheck_url }}
```

- [ ] **Step 7: The tasks, the handler and the Slack name**

`infra/ansible/roles/mon/tasks/main.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

# ---- The node's own telemetry ----------------------------------------------------------------------
- name: alloy config — the node's own metrics and journals, written to its stores on loopback
  ansible.builtin.copy:
    src: config.alloy
    dest: /etc/alloy/config.alloy
    owner: root
    group: alloy
    mode: "0640"
    validate: alloy validate %s
  notify: restart alloy

- name: alloy enabled + started
  ansible.builtin.systemd_service:
    name: alloy
    enabled: true
    state: started
  when: not mon_units_previewed

- name: ensure the node-exporter textfile directory exists
  ansible.builtin.file:
    path: "{{ mon_textfile_dir }}"
    state: directory
    owner: root
    group: root
    mode: "0755"

# The node reboots by hand, so it publishes the pending-reboot flag the way the capture pair and ops
# do: a copy of the capture role's check.
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
  register: mon_reboot_timer_install

# A first-install preview never wrote the timer, so systemd cannot find it there.
- name: enable + start the reboot-check timer
  ansible.builtin.systemd_service:
    name: zcrypto-reboot-check.timer
    daemon_reload: true
    enabled: true
    state: started
  when: not (ansible_check_mode and mon_reboot_timer_install is changed)

# A rule cannot page the death of the node it runs on: the self-check pings a healthchecks.io check
# while the node does its job, and the missing ping is the page.
- name: install the self-check script
  ansible.builtin.copy:
    src: zcrypto-mon-selfcheck.py
    dest: /usr/local/sbin/zcrypto-mon-selfcheck
    owner: root
    group: root
    mode: "0755"

- name: render the self-check's ping URL, read by systemd alone
  ansible.builtin.template:
    src: zcrypto-mon-selfcheck.env.j2
    dest: /etc/default/zcrypto-mon-selfcheck
    owner: root
    group: root
    mode: "0600"
  no_log: true
  diff: false

- name: render the self-check systemd unit
  ansible.builtin.template:
    src: zcrypto-mon-selfcheck.service.j2
    dest: /etc/systemd/system/zcrypto-mon-selfcheck.service
    owner: root
    group: root
    mode: "0644"

- name: install the self-check systemd timer
  ansible.builtin.copy:
    src: zcrypto-mon-selfcheck.timer
    dest: /etc/systemd/system/zcrypto-mon-selfcheck.timer
    owner: root
    group: root
    mode: "0644"
  register: mon_selfcheck_timer_install

# A first-install preview never wrote the timer, so systemd cannot find it there.
- name: enable + start the self-check timer
  ansible.builtin.systemd_service:
    name: zcrypto-mon-selfcheck.timer
    daemon_reload: true
    enabled: true
    state: started
  when: not (ansible_check_mode and mon_selfcheck_timer_install is changed)
```

`infra/ansible/roles/mon/handlers/main.yml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

- name: restart alloy
  ansible.builtin.systemd_service:
    name: alloy
    state: restarted
  when: not mon_units_previewed
```

`infra/grafana/notification-templates/zcrypto-slack.tmpl` — replace

```
  {{- else if eq . "zcrypto-valkey3" }}Cache 3
```

with

```
  {{- else if eq . "zcrypto-valkey3" }}Cache 3
  {{- else if eq . "zcrypto-mon" }}Monitor
```

- [ ] **Step 8: Run the tests**

Run Step 2's command.

Expected: no failure; `tests/test_dashboards_cover_metrics.py` skips nothing new.

- [ ] **Step 9: The consumers**

```bash
uv run pytest tests/test_mon_selfcheck.py tests/test_infra_mon_role.py tests/test_infra_mon_token.py tests/test_reboot_check.py tests/test_clock_offset.py tests/test_dashboards_cover_metrics.py tests/test_infra_alloy_series.py tests/test_infra_alloy_stages.py tests/test_infra_alert_rules.py tests/test_grafana_push_sh.py tests/test_ops_daily.py tests/test_deploy_log_audit.py tests/test_scripts_have_tests.py tests/test_error_paths_are_logged.py tests/test_config_selectors_are_parsed.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`2184 passed, 1 skipped` on the tree this plan was written against). `tests/test_scripts_have_tests.py` reads the new script's test; `tests/test_grafana_push_sh.py` reads the Slack template the push sends.

- [ ] **Step 10: The commit gate**

Run: `uv run pre-commit run -a`

Expected: every hook Passed (`shellcheck` reads the copied script, `ruff` the self-check); re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 11: Commit**

```bash
git add infra/ansible/roles/mon infra/grafana/notification-templates/zcrypto-slack.tmpl \
  tests/test_mon_selfcheck.py tests/test_infra_mon_role.py tests/test_reboot_check.py tests/test_dashboards_cover_metrics.py
git commit -F- <<'MSG'
feat(mon): the node ships its own telemetry, checks its reboot flag and reads its own health every five minutes

The node's Alloy is the native package with a config of its own: the unix exporter's six
collectors with the textfile directory, Alloy's own metrics and the `/metrics` of Grafana,
Prometheus and Loki, written to the node's Prometheus on loopback with no credential and no filter,
under `host="zcrypto-mon"`; and the journals of the seven units the role runs, their level parsed,
written to the node's Loki. The config is validated by `alloy validate` before it replaces the
live file, and a change restarts Alloy.

The reboot check is the capture hosts' script and timer, copied, writing `node_reboot_required`
into the textfile directory the node's Alloy scrapes.

A rule cannot page the death of the node it runs on, so a timer runs a self-check every five
minutes: Grafana's rule scheduler ticked within the last minute and has rules scheduled, a fleet
sample is fresh, Loki answers ready. It pings its healthchecks.io URL only when all three hold and
a URL is set, always exits 0, and says in one journal line what it read, never the URL. The URL is
empty by default, so the timer pings nothing until the check is minted.

The Slack template names the node `Monitor`. The dashboard guard learns a host whose config carries
no keep regex, which admits every family, and its check that some host admits a family leaves such
a host out: one that admits everything is no evidence the family reaches Grafana Cloud.

Cases: nine over the self-check and its units; four over the Alloy config; the node's reboot-check
copy and its unit; the unfiltered host, a family it alone admits still refused, and the Slack
template's names against the topology.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 12: The tree is clean**

Run: `git status --porcelain`

Expected: empty, and no `__pycache__` under `infra/ansible/roles/mon/` (`find infra/ansible/roles/mon -name __pycache__` prints nothing).

- [ ] **Step 13: Prove the guards with seventeen probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time. The controls: the tick bar raised a hundredfold; the unit's type changed; the timer's unit renamed; the script's install path moved; `promtool`'s subcommand changed; the node's `host` label changed; the textfile directory moved; the script's `pending` start value flipped; another host's Slack name broken; the set of unfiltered hosts emptied. The mutations loosen each read of the self-check, each property of the node's shipping and the copy, and the guard's own exclusion:

```bash
R=infra/ansible/roles/mon
SELF="uv run pytest tests/test_mon_selfcheck.py -q -p no:cacheprovider"
ROLE="uv run pytest tests/test_infra_mon_role.py -q -p no:cacheprovider"
REBOOT="uv run pytest tests/test_reboot_check.py -q -p no:cacheprovider"
COVER="uv run pytest tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider"
BOTH="uv run pytest tests/test_infra_mon_role.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider"
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.py \
  --control 's/^TICK_MAX_AGE_SECONDS = 60$/TICK_MAX_AGE_SECONDS = 6000/' \
  --mutation 's/^    if hosts < 1:$/    if hosts < 0:/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.py \
  --control 's/^TICK_MAX_AGE_SECONDS = 60$/TICK_MAX_AGE_SECONDS = 6000/' \
  --mutation 's/^    if not healthy:$/    if False:/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.py \
  --control 's/^TICK_MAX_AGE_SECONDS = 60$/TICK_MAX_AGE_SECONDS = 6000/' \
  --mutation 's/^    if scheduled < 1:$/    if scheduled < 0:/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.py \
  --control 's/^TICK_MAX_AGE_SECONDS = 60$/TICK_MAX_AGE_SECONDS = 6000/' \
  --mutation 's/^    return (True, "ready") if body == "ready" else/    return (True, "ready") if body else/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.py \
  --control 's/^TICK_MAX_AGE_SECONDS = 60$/TICK_MAX_AGE_SECONDS = 6000/' \
  --mutation 's/^    print(f"selfcheck: {. .\.join(parts)} -> {verdict}")$/    print(f"selfcheck: {url} -> {verdict}")/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/templates/zcrypto-mon-selfcheck.service.j2 \
  --control 's/^Type=oneshot$/Type=simple/' \
  --mutation '/^Environment=MON_SELFCHECK_LOKI=/d' -- $SELF
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    dest: \/usr\/local\/sbin\/zcrypto-mon-selfcheck$/    dest: \/usr\/local\/bin\/zcrypto-mon-selfcheck/' \
  --mutation '/^- name: render the self-check.s ping URL, read by systemd alone$/,/^$/s/mode: "0600"/mode: "0644"/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-mon-selfcheck.timer \
  --control 's/^Unit=zcrypto-mon-selfcheck.service$/Unit=zcrypto-mon-check.service/' \
  --mutation 's/^OnCalendar=\*:0\/5:23$/OnCalendar=*:0\/10:23/' -- $SELF
infra/scripts/mutate-probe.sh --file $R/tasks/main.yml \
  --control 's/^    validate: promtool check config %s$/    validate: promtool check rules %s/' \
  --mutation '/^    validate: alloy validate %s$/d' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/files/config.alloy \
  --control 's/^    host = "zcrypto-mon",$/    host = "mon",/' \
  --mutation 's#^    url = "http://127.0.0.1:9090/api/v1/write"$#    url = "https://zcrypto-mon.zhaow.me/api/v1/write"#' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/files/config.alloy \
  --control 's/^    host = "zcrypto-mon",$/    host = "mon",/' \
  --mutation 's/(grafana-server|prometheus|/(prometheus|/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/files/config.alloy \
  --control 's/^    host = "zcrypto-mon",$/    host = "mon",/' \
  --mutation 's/"cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"/"cpu", "loadavg", "meminfo", "filesystem", "textfile"/' -- $ROLE
infra/scripts/mutate-probe.sh --file $R/files/config.alloy \
  --control 's/^    directory = "\/var\/lib\/zcrypto-node-textfile"$/    directory = "\/var\/lib\/textfile"/' \
  --mutation 's/^  set_collectors = \["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"\]$/  set_collectors = ["cpu", "loadavg", "meminfo", "filesystem", "netdev"]/' -- $REBOOT
infra/scripts/mutate-probe.sh --file $R/files/zcrypto-reboot-check.sh \
  --control 's/^pending=0$/pending=1/' \
  --mutation 's/\[ -e "\$flag" \] \&\& pending=1/[ -f "$flag" ] \&\& pending=1/' -- $REBOOT
infra/scripts/mutate-probe.sh --file $R/files/config.alloy \
  --control 's/^    host = "zcrypto-mon",$/    host = "mon",/' \
  --mutation '/^    url = "http:\/\/127.0.0.1:9090\/api\/v1\/write"$/a\    write_relabel_config {\n      source_labels = ["__name__"]\n      regex         = "up"\n      action        = "keep"\n    }' -- $BOTH
infra/scripts/mutate-probe.sh --file infra/grafana/notification-templates/zcrypto-slack.tmpl \
  --control 's/eq \. "zaccess" }}Edge/eq . "zaccess2" }}Edge/' \
  --mutation '/eq \. "zcrypto-mon" }}Monitor/d' -- $COVER
infra/scripts/mutate-probe.sh --file tests/test_dashboards_cover_metrics.py \
  --control 's/^UNFILTERED_HOSTS = frozenset({"zcrypto-mon"})$/UNFILTERED_HOSTS = frozenset()/' \
  --mutation 's/ for host, keep in keeps.items() if host not in UNFILTERED_HOSTS):$/ for keep in keeps.values()):/' -- $COVER
```

Expected: each of the seventeen runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 11 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, seventeen runs, each KILLED with its control proven. The
self-check script, control the tick bar raised a hundredfold: no fleet host read as fresh, KILLED,
control proven; a failed read pinging all the same, KILLED, control proven; no scheduled rule read
as healthy, KILLED, control proven; any Loki answer read as ready, KILLED, control proven; the URL
printed in the journal line, KILLED, control proven. Its unit, control the type changed: Loki's
address dropped from its environment, KILLED, control proven. Its timer, control its unit renamed:
the interval doubled, KILLED, control proven. The role's tasks, control the script's install path
moved: the environment file made world-readable, KILLED, control proven; and, control `promtool`'s
subcommand changed, over the role's cases: the Alloy config's validation dropped, KILLED, control
proven. The node's `config.alloy`, control the `host` label changed: metrics written through the
public edge, KILLED, control proven; Grafana's journal dropped from the keep rule, KILLED, control
proven; a collector dropped, KILLED, control proven; a filter added to the write, KILLED, control
proven; and, control the textfile directory moved, over the reboot-check cases: the textfile
collector dropped, KILLED, control proven. The copied reboot-check script, control its start value
flipped: the flag test changed, KILLED, control proven. The Slack template, control another host's
name broken: the node's name dropped, KILLED, control proven.
`tests/test_dashboards_cover_metrics.py`, control the set of unfiltered hosts emptied: the
unfiltered host counted among the hosts that admit a family, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 5: The tools address a stack by name: `grafana_auth.py`'s table, `grafana-query.py --stack` and the daily pass's `--stack`

**Files:**
- Modify: `infra/scripts/ops_daily.py`
- Modify: `infra/scripts/grafana_auth.py`
- Modify: `infra/scripts/grafana-query.py`
- Test: `tests/test_grafana_auth.py`
- Test: `tests/test_grafana_query.py` (five stubs take the vault file; three cases appended)
- Test: `tests/test_ops_daily.py`
- Test: `tests/test_ops_daily_soak.py` (two stubs take the vault file)

**Interfaces:**
- Consumes: `grafana_auth.vault_var(name, vault_file)`, unchanged, whose `vault_file` already takes an absolute path; Task 3's cache path and variable name, which `tests/test_grafana_auth.py` holds equal to the role's defaults; `ops_daily.py`'s `_Shape` grammar for the commands a runbook step may carry.
- Produces, for Task 7's runbook page, the Rollout and phases 2 and 3 to use by these exact names: `grafana_auth.Stack(url, token_var, vault_file)`, `grafana_auth.STACKS` with the keys `cloud` and `mon`, `grafana_auth.DEFAULT_STACK`, `grafana_auth.stack(name)`; `grafana-query.py --stack <name>`; `ops-daily.py report --stack <name>`; the `--stack` operand in the `grafana-query.py` shape, so a runbook step naming a stack is classified as the read it is.

**What this task decides, where the spec leaves it open:**
- The table lives in `grafana_auth.py` as a `NamedTuple` per stack, and `GRAFANA_URL` stays a module constant equal to the default stack's URL, so every existing importer keeps reading Grafana Cloud unchanged. Phase 2's comparison script reads both entries; phase 3 flips `DEFAULT_STACK`; phase 4 collapses the table.
- Both tools build their URLs from a module-level `GRAFANA_URL` read at call time, so each rebinds that one name to the named stack's URL at the top of `main` instead of threading a parameter through every endpoint builder: one stack per process.
- An unknown stack, or `--stack` with nothing after it, is a usage error (exit 2) before any vault read or request; `grafana_auth.stack()` itself raises `SystemExit` naming the known stacks.
- The test stubs for `vault_var` take the vault file as a second parameter: ten existing stubs in three files change shape and nothing else.

- [ ] **Step 1: Write the failing tests**

`tests/test_grafana_auth.py` — replace

```python
import importlib.util
import subprocess
from pathlib import Path

import pytest
```

with

```python
import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml
```

`tests/test_grafana_auth.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- the stack table: one tree feeds two Grafanas until the Grafana Cloud leg retires --------------
MON_DEFAULTS = Path(__file__).resolve().parents[1] / "infra/ansible/roles/mon/defaults/main.yml"


def test_the_table_holds_the_two_stacks_and_reads_cloud_when_none_is_named():
    assert set(ga.STACKS) == {"cloud", "mon"}
    assert ga.DEFAULT_STACK == "cloud", "the default moves at the cutover, with the push script's own"
    assert ga.stack() is ga.STACKS["cloud"] and ga.GRAFANA_URL == ga.STACKS["cloud"].url
    cloud = ga.STACKS["cloud"]
    assert (cloud.url, cloud.token_var, cloud.vault_file) == ("https://zcrypto2026.grafana.net", "grafana_sa_token", ga.VAULT_FILE)


def test_the_mon_stack_is_the_role_s_public_name_and_the_cache_the_role_writes():
    """The role mints the token into a file outside the tree; a tool reading another file or another variable finds
    nothing, or yesterday's token."""
    defaults = yaml.safe_load(MON_DEFAULTS.read_text())
    mon = ga.STACKS["mon"]
    assert mon.url == f"https://{defaults['mon_hostname']}"
    assert mon.token_var == defaults["mon_token_var"]
    assert defaults["mon_token_cache"] == "{{ lookup('ansible.builtin.env', 'HOME') }}/.config/zcrypto/grafana-mon.vault.yml"
    assert mon.vault_file == str(Path.home() / ".config/zcrypto/grafana-mon.vault.yml")
    assert Path(mon.vault_file).is_absolute() and not Path(mon.vault_file).is_relative_to(ga.ANSIBLE_DIR.parents[1])


def test_an_unknown_stack_is_refused_by_name():
    with pytest.raises(SystemExit) as refused:
        ga.stack("grafana-cloud")
    assert str(refused.value) == "unknown stack 'grafana-cloud': one of cloud, mon"


def test_a_stack_s_token_is_read_from_its_own_file(monkeypatch):
    seen = {}

    class FakeLoader:
        def set_vault_secrets(self, secrets): ...

        def load_from_file(self, path):
            seen["path"] = path
            return {"mon_grafana_tools_token": TOKEN}

    monkeypatch.setattr(ga, "_load_ansible_vault", lambda: (FakeLoader(), object()))
    mon = ga.stack("mon")
    assert ga.vault_var(mon.token_var, mon.vault_file) == TOKEN
    assert seen["path"] == mon.vault_file, "an absolute vault file is read where it is, never under infra/ansible"
```

`tests/test_grafana_query.py` — replace each of the 5 occurrences of

```python
    monkeypatch.setattr(gq, "vault_var", lambda name: TOKEN)
```

with

```python
    monkeypatch.setattr(gq, "vault_var", lambda name, vault_file: TOKEN)
```

`tests/test_grafana_query.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- one tree, two stacks: the stack is named, and the default is the one that pages ---------------
class _Recorded:
    def __init__(self, monkeypatch):
        self.urls: list[str] = []
        self.vault: list[tuple[str, str]] = []
        monkeypatch.setattr(gq, "GRAFANA_URL", gq.GRAFANA_URL)  # main rebinds it; this puts it back
        monkeypatch.setattr(gq, "vault_var", lambda name, vault_file: self.vault.append((name, vault_file)) or TOKEN)
        monkeypatch.setattr(gq.urllib.request, "urlopen", self._urlopen)

    def _urlopen(self, request, timeout):
        self.urls.append(request.full_url)

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"data": {"result": []}}'

        return _Response()


def test_no_stack_named_reads_grafana_cloud_with_its_token(monkeypatch, capsys):
    seen = _Recorded(monkeypatch)
    assert gq.main(["up"]) == 0
    assert seen.vault == [("grafana_sa_token", gq.grafana_auth.VAULT_FILE)]
    assert seen.urls == ["https://zcrypto2026.grafana.net/api/datasources/proxy/uid/grafanacloud-prom/api/v1/query?query=up"]


def test_the_mon_stack_is_read_at_its_own_url_with_its_own_token(monkeypatch, capsys):
    seen = _Recorded(monkeypatch)
    assert gq.main(["--stack", "mon", "--loki", "up"]) == 0
    mon = gq.grafana_auth.STACKS["mon"]
    assert seen.vault == [(mon.token_var, mon.vault_file)]
    assert seen.urls == ["https://zcrypto-mon.zhaow.me/api/datasources/proxy/uid/grafanacloud-logs/loki/api/v1/query?query=up"]
    assert "--stack" not in capsys.readouterr().out, "the flag and its value are not expressions"


@pytest.mark.parametrize(
    "argv", [["--stack", "prod", "up"], ["up", "--stack"]], ids=["an unknown stack", "no stack after the flag"]
)
def test_a_stack_that_cannot_be_resolved_is_a_usage_error_before_any_read(monkeypatch, capsys, argv):
    seen = _Recorded(monkeypatch)
    assert gq.main(argv) == 2
    assert seen.vault == [] and seen.urls == []
    assert "usage: grafana-query.py [--stack cloud|mon] [--loki]" in capsys.readouterr().out
```

`tests/test_ops_daily.py` — replace each of the 3 occurrences of

```python
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
```

with

```python
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name, vault_file: "tok")
```

`tests/test_ops_daily_soak.py` — replace each of the 2 occurrences of

```python
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
```

with

```python
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name, vault_file: "tok")
```

`tests/test_ops_daily.py` — after

```python
def test_a_bad_since_suffix_is_a_usage_error_not_a_traceback():
    assert ops_daily.main(["report", "--since", "24w"]) == 2
    assert ops_daily.main(["report", "--since", "abc"]) == 2
```

insert (the insert opens with 2 blank lines, kept)

```python


def _a_quiet_pass(monkeypatch) -> dict:
    """Every reader stubbed to an empty read that records the stack URL it would have built its request from."""
    seen: dict = {"vault": [], "urls": []}
    monkeypatch.setattr(ops_daily, "GRAFANA_URL", ops_daily.GRAFANA_URL)  # main rebinds it; this puts it back
    monkeypatch.setattr(
        ops_daily.grafana_auth, "vault_var", lambda name, vault_file: seen["vault"].append((name, vault_file)) or "tok"
    )

    def reading(empty):
        return lambda *a, **k: seen["urls"].append(ops_daily.GRAFANA_URL) or empty

    monkeypatch.setattr(ops_daily, "read_alerts", reading(ops_daily.AlertsRead()))
    monkeypatch.setattr(ops_daily, "read_logs", reading(ops_daily.LogsRead()))
    monkeypatch.setattr(ops_daily, "read_deadmen", reading(ops_daily.DeadmenRead(via_prometheus=0.0)))
    monkeypatch.setattr(ops_daily, "read_verdict", reading([]))
    monkeypatch.setattr(ops_daily, "read_reminders", reading(ops_daily.RemindersRead()))
    monkeypatch.setattr(ops_daily, "read_deploys", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "ssh_read", _host_answering(StampEpoch=str(int(datetime.now(timezone.utc).timestamp()))))
    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_a_current_soak_payload()))
    return seen


def test_the_pass_reads_grafana_cloud_when_no_stack_is_named(monkeypatch, capsys):
    seen = _a_quiet_pass(monkeypatch)
    assert ops_daily.main(["report"]) == 0
    assert seen["vault"] == [("grafana_sa_token", ops_daily.grafana_auth.VAULT_FILE)]
    assert set(seen["urls"]) == {"https://zcrypto2026.grafana.net"} and len(seen["urls"]) == 5


def test_the_pass_reads_the_named_stack_at_its_own_url_with_its_own_token(monkeypatch, capsys):
    seen = _a_quiet_pass(monkeypatch)
    assert ops_daily.main(["report", "--stack", "mon", "--since", "24h"]) == 0
    mon = ops_daily.grafana_auth.STACKS["mon"]
    assert seen["vault"] == [(mon.token_var, mon.vault_file)]
    assert set(seen["urls"]) == {"https://zcrypto-mon.zhaow.me"} and len(seen["urls"]) == 5


@pytest.mark.parametrize("argv", [["report", "--stack", "prod"], ["report", "--stack"]], ids=["unknown", "no value"])
def test_a_stack_the_pass_cannot_resolve_is_a_usage_error_before_any_read(monkeypatch, capsys, argv):
    seen = _a_quiet_pass(monkeypatch)
    assert ops_daily.main(argv) == 2
    assert seen["vault"] == [] and seen["urls"] == []
    assert "--stack takes one of cloud, mon" in capsys.readouterr().out
```

`tests/test_ops_daily.py` — replace

```python
        ("uv run python infra/scripts/grafana-query.py 'up{job=\"capture_app\"}'", "ops"),
        ("sudo docker logs --since 5h zcrypto-engine | grep 'not scored'", "zcrypto"),
```

with

```python
        ("uv run python infra/scripts/grafana-query.py 'up{job=\"capture_app\"}'", "ops"),
        ("uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host=\"zcrypto-mon\"})'", "ops"),
        ("sudo docker logs --since 5h zcrypto-engine | grep 'not scored'", "zcrypto"),
```

`tests/test_ops_daily.py` — after

```python
    `docker exec` fronting a genuine read, and PromQL full of braces and quotes."""
    assert ops_daily.classify_action(cmd, host=host, resolve=_identity) is ops_daily.Tier.AUTONOMOUS
```

insert (the insert opens with 2 blank lines, kept)

```python


def test_the_query_tools_stack_flag_takes_a_name_and_nothing_else():
    """The value is a stack's name: one that carries a shell's or a URL's characters is no name, and is refused."""
    for value in ("https://example.invalid", "mon;id", "../mon"):
        step = f"uv run python infra/scripts/grafana-query.py --stack {value} 'up'"
        assert ops_daily.classify_action(step, host="ops", resolve=_identity) is ops_daily.Tier.PREPARED, value
    assert ops_daily.classify_action("uv run python infra/scripts/grafana-query.py --stack", host="ops", resolve=_identity) is (
        ops_daily.Tier.PREPARED
    )
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_ops_daily_soak.py -q -p no:cacheprovider`

Expected: `23 failed`, the rest passed: the four new `tests/test_grafana_auth.py` cases (`AttributeError`, no `STACKS`); nine `tests/test_grafana_query.py` cases and nine of `tests/test_ops_daily.py` and `tests/test_ops_daily_soak.py`, the new ones for want of `--stack` and the existing ones because their stub now takes a second argument the tool does not pass yet; and the `grafana-query.py --stack mon` step of `test_the_wrappers_and_quoting_the_runbooks_really_use`, which the shape refuses. `test_the_query_tools_stack_flag_takes_a_name_and_nothing_else` passes already, since an unknown flag is refused: Step 9's probes are what show it holds the flag's operand class.

- [ ] **Step 3: The stack table**

`infra/scripts/grafana_auth.py` — replace

```python
import configparser
import subprocess
from pathlib import Path

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"

# Deliberately baked in rather than re-guessed: a wrong datasource uid is accepted happily and still
# reports health=ok, so a guess fails silently.
GRAFANA_URL = "https://zcrypto2026.grafana.net"
```

with

```python
import configparser
import subprocess
from pathlib import Path
from typing import NamedTuple

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
VAULT_FILE = "group_vars/all/vault.yml"


class Stack(NamedTuple):
    """One Grafana the tools address: where it answers, and the vault variable and file holding its token."""

    url: str
    token_var: str
    vault_file: str


# Baked in rather than re-guessed: a wrong URL or datasource uid is accepted happily and still reports
# health=ok, so a guess fails silently. Two stacks until the Grafana Cloud leg retires. `mon`'s token is
# minted by the `mon` role into a vault-encrypted cache outside the tree, the role's `mon_token_cache` and
# `mon_token_var`; `vault_var` reads an absolute file where it is.
STACKS = {
    "cloud": Stack("https://zcrypto2026.grafana.net", "grafana_sa_token", VAULT_FILE),
    "mon": Stack(
        "https://zcrypto-mon.zhaow.me", "mon_grafana_tools_token", str(Path.home() / ".config/zcrypto/grafana-mon.vault.yml")
    ),
}
# The stack a tool reads when none is named: the one that pages.
DEFAULT_STACK = "cloud"
GRAFANA_URL = STACKS[DEFAULT_STACK].url


def stack(name: str = DEFAULT_STACK) -> Stack:
    if name not in STACKS:
        raise SystemExit(f"unknown stack {name!r}: one of {', '.join(sorted(STACKS))}")
    return STACKS[name]
```

- [ ] **Step 4: `grafana-query.py` takes a stack**

`infra/scripts/grafana-query.py` — replace

```python
"""Read PromQL, or with --loki a LogQL metric query, from Grafana Cloud with the vaulted service-account token.
    uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' hc_check_up
    uv run python infra/scripts/grafana-query.py --loki 'sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))'
```

with

```python
"""Read PromQL, or with --loki a LogQL metric query, from a Grafana stack with its vaulted service-account token.
    uv run python infra/scripts/grafana-query.py 'up{job="capture_app"}' hc_check_up
    uv run python infra/scripts/grafana-query.py --loki 'sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))'
    uv run python infra/scripts/grafana-query.py --stack mon 'up{host="zcrypto-mon"}'
`--stack` names one of `grafana_auth.STACKS`; with none, the default stack, the one that pages, is read.
```

`infra/scripts/grafana-query.py` — replace

```python
def endpoint(expr: str, loki: bool = False) -> str:
    """The instant-query URL through the Grafana datasource proxy, so the stack's own auth is what is used."""
```

with

```python
def endpoint(expr: str, loki: bool = False) -> str:
    """The instant-query URL through the Grafana datasource proxy, so the stack's own auth is what is used. It reads
    `GRAFANA_URL` when called: `main` rebinds that name to the stack it was asked for."""
```

`infra/scripts/grafana-query.py` — replace

```python
def main(argv: list[str]) -> int:
    loki = "--loki" in argv
    argv = [a for a in argv if a != "--loki"]
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: grafana-query.py [--loki] '<query>' ['<query>' ...]")
        return 2
    token = vault_var("grafana_sa_token")
```

with

```python
def main(argv: list[str]) -> int:
    global GRAFANA_URL
    loki = "--loki" in argv
    argv = [a for a in argv if a != "--loki"]
    name = grafana_auth.DEFAULT_STACK
    if "--stack" in argv:
        at = argv.index("--stack")
        name, argv = (argv[at + 1] if at + 1 < len(argv) else ""), argv[:at] + argv[at + 2 :]
    if not argv or name not in grafana_auth.STACKS:
        print(__doc__.strip().splitlines()[0])
        print(f"usage: grafana-query.py [--stack {'|'.join(sorted(grafana_auth.STACKS))}] [--loki] '<query>' ['<query>' ...]")
        return 2
    stack = grafana_auth.stack(name)
    GRAFANA_URL = stack.url
    token = vault_var(stack.token_var, stack.vault_file)
```

- [ ] **Step 5: The daily pass takes a stack, and a runbook step may name one**

`infra/scripts/ops_daily.py` — replace

```python
    if not argv or argv[0] != "report":
        print('usage: ops-daily.py report [--since 24h] [--journal-entry]\n       ops-daily.py classify --host <host> "<command>"')
        return 2
    try:
        window = _parse_since(argv[argv.index("--since") + 1]) if "--since" in argv else timedelta(hours=24)
    except (KeyError, ValueError, IndexError) as exc:
        print(f"--since takes a count and h or d, like 24h or 3d: {exc}")
        return 2
```

with

```python
    if not argv or argv[0] != "report":
        print(
            "usage: ops-daily.py report [--since 24h] [--journal-entry] [--stack cloud|mon]\n"
            '       ops-daily.py classify --host <host> "<command>"'
        )
        return 2
    try:
        window = _parse_since(argv[argv.index("--since") + 1]) if "--since" in argv else timedelta(hours=24)
    except (KeyError, ValueError, IndexError) as exc:
        print(f"--since takes a count and h or d, like 24h or 3d: {exc}")
        return 2
    # One stack per pass: the three endpoint builders read `GRAFANA_URL` when called, so the name is rebound here.
    global GRAFANA_URL
    try:
        named = argv[argv.index("--stack") + 1] if "--stack" in argv else grafana_auth.DEFAULT_STACK
        stack = grafana_auth.STACKS[named]
    except KeyError, IndexError:
        print(f"--stack takes one of {', '.join(sorted(grafana_auth.STACKS))}")
        return 2
    GRAFANA_URL = stack.url
```

`except KeyError, IndexError:` is Python 3.14's PEP 758 form and is what `ruff format` writes for a clause with no `as`; it is not a Python 2 leftover.

`infra/scripts/ops_daily.py` — replace

```python
        token = grafana_auth.vault_var("grafana_sa_token")
```

with

```python
        token = grafana_auth.vault_var(stack.token_var, stack.vault_file)
```

`infra/scripts/ops_daily.py` — replace

```python
    _Shape(("grafana-query.py",), {"--since": _SINCE, "--step": _NAME}, arity=(1, 6), classes=(_QUOTED,)),
```

with

```python
    _Shape(("grafana-query.py",), {"--since": _SINCE, "--step": _NAME, "--stack": _NAME}, arity=(1, 6), classes=(_QUOTED,)),
```

- [ ] **Step 6: Run the tests**

Run Step 2's command.

Expected: no failure.

- [ ] **Step 7: The consumers**

```bash
uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_engine_soak.py tests/test_ops_postverify.py tests/test_order_semantics_probe.py tests/test_infra_alert_rules.py tests/test_infra_mon_token.py tests/test_scripts_have_tests.py tests/test_error_paths_are_logged.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`919 passed, 3 skipped` on the tree this plan was written against).

- [ ] **Step 8: The commit gate and the commit**

Run: `uv run pre-commit run -a`

Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

```bash
git add infra/scripts/grafana_auth.py infra/scripts/grafana-query.py infra/scripts/ops_daily.py \
  tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_ops_daily_soak.py
git commit -F- <<'MSG'
feat(grafana): the tools address a Grafana stack by name, reading Grafana Cloud when none is named

One tree feeds two Grafanas until the Grafana Cloud leg retires. `grafana_auth.py`'s one URL
becomes a table of two stacks, each a URL, the vault variable holding its token and the file that
variable is in: `cloud` as today, and `mon` at `https://zcrypto-mon.zhaow.me` with the token the
`mon` role mints into `~/.config/zcrypto/grafana-mon.vault.yml`. The default stays `cloud`, the
stack that pages, so every existing caller reads what it read.

`grafana-query.py` and `ops-daily.py report` take `--stack <name>`. Both build their URLs from a
module-level name read at call time, so each rebinds it once at the top of `main`. An unknown
stack, or the flag with nothing after it, is a usage error before any vault read or request. The
daily pass's grammar for a runbook step admits `--stack` with a bare name on `grafana-query.py`, so
a step that reads the node is classified as the read it is.

Cases: the table's two stacks and its default; the node's entry against the role's public name,
cache path and variable name; an unknown stack refused by name; a stack's token read from its own
file; each tool reading Grafana Cloud unnamed and the node named, at its own URL with its own
token; the usage errors; the step grammar's operand. Ten existing `vault_var` stubs take the vault
file as their second parameter.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 9: Prove the guards with ten probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time. The controls: the default stack flipped; a datasource uid changed in each tool. The mutations point the node's entry at Grafana Cloud's token or file, drop the unknown-stack refusal, leave the URL unbound or the token Cloud's in each tool, and drop or loosen the shape's operand:

```bash
AUTH="uv run pytest tests/test_grafana_auth.py -q -p no:cacheprovider"
QUERY="uv run pytest tests/test_grafana_query.py -q -p no:cacheprovider"
OPS="uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider"
infra/scripts/mutate-probe.sh --file infra/scripts/grafana_auth.py \
  --control 's/^DEFAULT_STACK = "cloud"$/DEFAULT_STACK = "mon"/' \
  --mutation 's/"https:\/\/zcrypto-mon.zhaow.me", "mon_grafana_tools_token"/"https:\/\/zcrypto-mon.zhaow.me", "grafana_sa_token"/' -- $AUTH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana_auth.py \
  --control 's/^DEFAULT_STACK = "cloud"$/DEFAULT_STACK = "mon"/' \
  --mutation 's/".config\/zcrypto\/grafana-mon.vault.yml"/".config\/zcrypto\/grafana.vault.yml"/' -- $AUTH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana_auth.py \
  --control 's/^DEFAULT_STACK = "cloud"$/DEFAULT_STACK = "mon"/' \
  --mutation 's/^    if name not in STACKS:$/    if False:/' -- $AUTH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-query.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/^    GRAFANA_URL = stack.url$/    pass/' -- $QUERY
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-query.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/^    token = vault_var(stack.token_var, stack.vault_file)$/    token = vault_var("grafana_sa_token", grafana_auth.VAULT_FILE)/' -- $QUERY
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-query.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/^    if not argv or name not in grafana_auth.STACKS:$/    if not argv:/' -- $QUERY
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/^    GRAFANA_URL = stack.url$/    pass/' -- $OPS
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/^        token = grafana_auth.vault_var(stack.token_var, stack.vault_file)$/        token = grafana_auth.vault_var("grafana_sa_token", grafana_auth.VAULT_FILE)/' -- $OPS
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/, "--stack": _NAME}/}/' -- $OPS
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^PROM_DS_UID = "grafanacloud-prom"$/PROM_DS_UID = "prom"/' \
  --mutation 's/, "--stack": _NAME}/, "--stack": _QUOTED}/' -- $OPS
```

Expected: each of the ten runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 8 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, ten runs, each KILLED with its control proven.
`infra/scripts/grafana_auth.py`, control the default stack flipped: the node's entry given Grafana
Cloud's token variable, KILLED, control proven; given Grafana Cloud's file name, KILLED, control
proven; the unknown-stack refusal dropped, KILLED, control proven. `infra/scripts/grafana-query.py`,
control a datasource uid changed: the URL left unbound, KILLED, control proven; the token read as
Grafana Cloud's whatever the stack, KILLED, control proven; an unknown stack let through, KILLED,
control proven. `infra/scripts/ops_daily.py`, control a datasource uid changed: the URL left
unbound, KILLED, control proven; the token read as Grafana Cloud's, KILLED, control proven;
`--stack` dropped from the query tool's shape, KILLED, control proven; its operand widened to a
quoted string, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 6: A push leaves named rule groups out, the node's own by default

**Files:**
- Modify: `infra/scripts/grafana-push.sh`
- Test: `tests/test_grafana_push_sh.py`

**Interfaces:**
- Consumes: `grafana-push.sh`'s environment-driven defaults, its rule loop, its orphan report and `GRAFANA_PRUNE`; the test harness of `tests/test_grafana_push_sh.py` (its fake Grafana and its fixture tree).
- Produces, for Task 7's runbook page and its rule-file case, the Rollout and every push of phases 2 and 3: `GRAFANA_SKIP_RULE_GROUPS`, space-separated group names, default `zcrypto-mon`; the first line's `skip-groups=<names or <none>>`; the line `grafana-push: skipping N rule(s) of group(s): …` on stderr; the refusal, exit 1 before any call, of a push addressed to Grafana Cloud whose skip list does not name `zcrypto-mon`.

**What this task decides, where the spec leaves it open:**
- The default is taken with `${GRAFANA_SKIP_RULE_GROUPS-zcrypto-mon}`, the unset-only form: set and empty means "skip none", which is how the node's push sends its own group, and `:-` would turn that push back into Grafana Cloud's. `test_the_committed_default_skips_exactly_the_observability_nodes_group` reads the line itself.
- A skipped group's rule found live is reported through the script's existing orphan path, with no new mechanism: the rule is not in the pushed set, so the read-back names it, and `GRAFANA_PRUNE=1` deletes it. That is what removes a node rule pushed to Grafana Cloud by mistake.
- The variable names groups, never uids, and a rule that carries no `ruleGroup` is always sent.
- The unset-only default keeps the node's group off Grafana Cloud only while the variable is unset, and the node's push leaves it set and empty in the shell that ran it. So the script ties the group to the destination: a push whose `GRAFANA_URL` is a `grafana.net` stack and whose skip list does not name `zcrypto-mon` is refused before any call. The test reads the Grafana Cloud URL off the script's own default line, so the refusal's pattern and the default cannot part.

- [ ] **Step 1: Write the failing tests**

`tests/test_grafana_push_sh.py` — replace

```python
import json
import os
import shutil
```

with

```python
import json
import os
import re
import shutil
```

`tests/test_grafana_push_sh.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- GRAFANA_SKIP_RULE_GROUPS: one tree feeds two stacks, and a stack never receives a group it is told to skip ----
_MON_RULE = """  - uid: r3
    title: three
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    data:
      - refId: A
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
      - refId: C
        datasourceUid: __expr__
"""


@pytest.fixture
def stack_with_a_mon_rule(stack):
    alerts = stack.root / "infra" / "grafana" / "alerts.yaml"
    alerts.write_text(_ALERTS + _MON_RULE, encoding="utf-8")
    stack.respond(
        "GET",
        "api/v1/provisioning/alert-rules/r3",
        {"uid": "r3", "data": [{"datasourceUid": "prom-x"}, {"datasourceUid": "__expr__"}]},
    )
    return stack


def _rule_calls(stack, uid: str) -> list[tuple[str, str]]:
    return [(m, p) for m, p, d in stack.recorded() if p.endswith(f"alert-rules/{uid}") or (d and json.loads(d).get("uid") == uid)]


def test_a_push_that_names_no_stack_sends_no_rule_of_the_observability_node(stack_with_a_mon_rule):
    done = stack_with_a_mon_rule.run()
    assert done.returncode == 0, done.stderr
    assert _rule_calls(stack_with_a_mon_rule, "r3") == [], "the node's rule reached a stack the push was not told is the node"
    assert _rule_calls(stack_with_a_mon_rule, "r2") != []
    assert "grafana-push: skipping 1 rule(s) of group(s): zcrypto-mon" in done.stderr
    assert "skip-groups=zcrypto-mon" in done.stderr.splitlines()[0]


def test_a_skipped_groups_rule_found_live_is_an_orphan_and_a_prune_deletes_it(stack_with_a_mon_rule):
    stack = stack_with_a_mon_rule
    stack.respond(
        "GET",
        "api/v1/provisioning/alert-rules",
        [{"uid": "r1", "folderUID": "fold-x"}, {"uid": "r2", "folderUID": "fold-x"}, {"uid": "r3", "folderUID": "fold-x"}],
    )
    done = stack.run()
    assert re.findall(r"ORPHAN \(live but not in alerts\.yaml\): (\S+)", done.stderr) == ["r3"]
    done = stack.run(GRAFANA_PRUNE="1")
    assert done.returncode == 0, done.stderr
    assert [p for m, p, _ in stack.recorded() if m == "DELETE"] == ["api/v1/provisioning/alert-rules/r3"]


def test_the_nodes_push_passes_the_variable_empty_and_sends_its_own_group(stack_with_a_mon_rule):
    done = stack_with_a_mon_rule.run(GRAFANA_SKIP_RULE_GROUPS="")
    assert done.returncode == 0, done.stderr
    assert ("POST", "api/v1/provisioning/alert-rules") in _rule_calls(stack_with_a_mon_rule, "r3")
    assert ("GET", "api/v1/provisioning/alert-rules/r3") in _rule_calls(stack_with_a_mon_rule, "r3")
    assert "rule(s) of group(s)" not in done.stderr and "skip-groups=<none>" in done.stderr.splitlines()[0]


def test_several_groups_are_skipped_by_name_and_a_rule_of_no_group_is_always_sent(stack_with_a_mon_rule):
    alerts = stack_with_a_mon_rule.root / "infra" / "grafana" / "alerts.yaml"
    alerts.write_text(alerts.read_text().replace("uid: r2\n    title: two\n", "uid: r2\n    title: two\n    ruleGroup: other\n"))
    done = stack_with_a_mon_rule.run(GRAFANA_SKIP_RULE_GROUPS="zcrypto-mon other")
    assert done.returncode == 0, done.stderr
    assert _rule_calls(stack_with_a_mon_rule, "r2") == [] and _rule_calls(stack_with_a_mon_rule, "r3") == []
    assert _rule_calls(stack_with_a_mon_rule, "r1") != []
    assert "grafana-push: skipping 2 rule(s) of group(s): zcrypto-mon other" in done.stderr


def _cloud_url() -> str:
    (default,) = re.findall(r'^export GRAFANA_URL="\$\{GRAFANA_URL:-([^}]+)\}"$', _SCRIPT.read_text(), re.M)
    return default


@pytest.mark.parametrize("skipped", ["", "other"], ids=["no group skipped", "another group skipped"])
def test_a_push_addressed_to_grafana_cloud_refuses_to_send_the_nodes_group(stack_with_a_mon_rule, skipped):
    """The shell that pushed the node still holds the emptied variable when the next push names no stack."""
    done = stack_with_a_mon_rule.run(GRAFANA_URL=_cloud_url(), GRAFANA_SKIP_RULE_GROUPS=skipped)
    assert done.returncode != 0
    assert stack_with_a_mon_rule.recorded() == [], "the refusal comes before the first call"
    assert "refusing to push to Grafana Cloud without skipping the zcrypto-mon rule group" in done.stderr


@pytest.mark.parametrize(
    "env", [{}, {"GRAFANA_SKIP_RULE_GROUPS": "other zcrypto-mon"}], ids=["the default", "a list naming the group"]
)
def test_a_push_addressed_to_grafana_cloud_that_skips_the_nodes_group_runs(stack_with_a_mon_rule, env):
    done = stack_with_a_mon_rule.run(GRAFANA_URL=_cloud_url(), **env)
    assert done.returncode == 0, done.stderr
    assert _rule_calls(stack_with_a_mon_rule, "r3") == [] and _rule_calls(stack_with_a_mon_rule, "r1") != []


def test_the_committed_default_skips_exactly_the_observability_nodes_group():
    (default,) = re.findall(
        r'^export GRAFANA_SKIP_RULE_GROUPS="\$\{GRAFANA_SKIP_RULE_GROUPS-([^}]*)\}"$', _SCRIPT.read_text(), re.M
    )
    assert default == "zcrypto-mon"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_grafana_push_sh.py -q -p no:cacheprovider`

Expected: `9 failed, 9 passed`: the script sends every rule, prints no `skip-groups=` and refuses no push.

- [ ] **Step 3: The variable, its default and the filter**

`infra/scripts/grafana-push.sh` — replace

```bash
# Rules go one per call through Grafana's Alerting Provisioning HTTP API; the `apiVersion: 1` /
```

with

```bash
# Two stacks take this push until the Grafana Cloud leg retires. With no GRAFANA_URL it goes to Grafana
# Cloud and leaves out the observability node's own rule group, which has no data there. The node's push
# names the node, its own token and no skipped group:
#   GRAFANA_URL=https://zcrypto-mon.zhaow.me GRAFANA_SKIP_RULE_GROUPS= GRAFANA_SA_TOKEN=<the node's token> ...
# with the token read by `grafana_auth.py`'s `stack("mon")`.
#
# Rules go one per call through Grafana's Alerting Provisioning HTTP API; the `apiVersion: 1` /
```

`infra/scripts/grafana-push.sh` — replace

```bash
export GRAFANA_ALERT_FOLDER_UID="${GRAFANA_ALERT_FOLDER_UID:-bfrxdfoybx98gb}"
echo "grafana-push: stack=$GRAFANA_URL prom=$GRAFANA_PROM_DS_UID loki=$GRAFANA_LOKI_DS_UID folder=$GRAFANA_ALERT_FOLDER_UID" >&2
```

with

```bash
export GRAFANA_ALERT_FOLDER_UID="${GRAFANA_ALERT_FOLDER_UID:-bfrxdfoybx98gb}"
# The rule groups this push leaves out, space-separated: none of their rules is sent, and one found live is
# reported as an orphan, which a prune deletes. `-`, never `:-`: set and empty skips no group, which is how the
# observability node's own push sends its group.
export GRAFANA_SKIP_RULE_GROUPS="${GRAFANA_SKIP_RULE_GROUPS-zcrypto-mon}"
echo "grafana-push: stack=$GRAFANA_URL prom=$GRAFANA_PROM_DS_UID loki=$GRAFANA_LOKI_DS_UID folder=$GRAFANA_ALERT_FOLDER_UID skip-groups=${GRAFANA_SKIP_RULE_GROUPS:-<none>}" >&2
# Grafana Cloud never takes the observability node's group: it has no data there, and a rule of it that fires
# on no data would page the main channel. The shell that pushed the node still holds the emptied variable, so
# a push addressed to Grafana Cloud that does not skip the group is refused here, before any call.
case "${GRAFANA_URL}" in
  *.grafana.net | *.grafana.net/*)
    case " ${GRAFANA_SKIP_RULE_GROUPS} " in
      *" zcrypto-mon "*) ;;
      *)
        echo "grafana-push: refusing to push to Grafana Cloud without skipping the zcrypto-mon rule group -- GRAFANA_SKIP_RULE_GROUPS is set and does not name it: unset it for a Grafana Cloud push, or name the node in GRAFANA_URL" >&2
        exit 1
        ;;
    esac
    ;;
esac
```

`infra/scripts/grafana-push.sh` — replace

```bash
rules_json=$(python3 -c '
import json, sys, yaml
print(json.dumps(yaml.safe_load(open(sys.argv[1]))["rules"]))
' "${root}/infra/grafana/alerts.yaml")
```

with

```bash
rules_json=$(python3 -c '
import json, os, sys, yaml
skipped = os.environ["GRAFANA_SKIP_RULE_GROUPS"]
rules = yaml.safe_load(open(sys.argv[1]))["rules"]
kept = [r for r in rules if r.get("ruleGroup") not in skipped.split()]
if len(kept) != len(rules):
    print(f"grafana-push: skipping {len(rules) - len(kept)} rule(s) of group(s): {skipped}", file=sys.stderr)
print(json.dumps(kept))
' "${root}/infra/grafana/alerts.yaml")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_grafana_push_sh.py -q -p no:cacheprovider`

Expected: `18 passed`.

- [ ] **Step 5: The consumers**

```bash
uv run pytest tests/test_grafana_push_sh.py tests/test_grafana_push.py tests/test_dashboards_cover_metrics.py tests/test_infra_alert_rules.py tests/test_infra_mon_role.py tests/test_ops_daily.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`1585 passed` on the tree this plan was written against).

- [ ] **Step 6: The commit gate and the commit**

Run: `uv run pre-commit run -a`

Expected: every hook Passed (`shellcheck` reads the script); re-run after any rewrite until clean, then stage what it rewrote.

```bash
git add infra/scripts/grafana-push.sh tests/test_grafana_push_sh.py
git commit -F- <<'MSG'
feat(grafana): a push leaves named rule groups out, the observability node's own by default

`grafana-push.sh` reads `GRAFANA_SKIP_RULE_GROUPS`, space-separated group names: it sends none of
their rules, says how many it left out, and its existing orphan report names one it finds live, so
a prune deletes it. The default is `zcrypto-mon`, beside the Grafana Cloud URL default: the node's
own group has no data on Grafana Cloud, and its two dead-men would page the main channel from
there. The node's push passes the variable empty and names the node's URL and token, which sends
every group. The default is taken with `-`, never `:-`, so set-and-empty skips nothing instead of
falling back.

That default holds only while the variable is unset, and the shell that pushed the node still holds
it empty. So a push addressed to a `grafana.net` stack whose skip list does not name `zcrypto-mon`
is refused before any call.

Cases: a push naming no stack sends no rule of the node's group and says so on its first line; a
skipped group's rule found live is an orphan and a prune deletes it; the node's push sends its own
group; several groups skipped by name, a rule of no group always sent; a push addressed to Grafana
Cloud refused with no group or another group skipped, and run under the default and under a list
naming the group; the committed default line itself.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 7: Prove the guards with five probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time. The control flips the prune default. The mutations empty the default, turn `-` into `:-`, disable the filter two ways, and point the refusal at a domain no push names:

```bash
PUSH="uv run pytest tests/test_grafana_push_sh.py -q -p no:cacheprovider"
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-push.sh \
  --control 's/GRAFANA_PRUNE:-0/GRAFANA_PRUNE:-1/' \
  --mutation 's/GRAFANA_SKIP_RULE_GROUPS-zcrypto-mon}/GRAFANA_SKIP_RULE_GROUPS-}/' -- $PUSH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-push.sh \
  --control 's/GRAFANA_PRUNE:-0/GRAFANA_PRUNE:-1/' \
  --mutation 's/GRAFANA_SKIP_RULE_GROUPS-zcrypto-mon}/GRAFANA_SKIP_RULE_GROUPS:-zcrypto-mon}/' -- $PUSH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-push.sh \
  --control 's/GRAFANA_PRUNE:-0/GRAFANA_PRUNE:-1/' \
  --mutation 's/not in skipped.split()\]/not in []]/' -- $PUSH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-push.sh \
  --control 's/GRAFANA_PRUNE:-0/GRAFANA_PRUNE:-1/' \
  --mutation 's/^print(json.dumps(kept))$/print(json.dumps(rules))/' -- $PUSH
infra/scripts/mutate-probe.sh --file infra/scripts/grafana-push.sh \
  --control 's/GRAFANA_PRUNE:-0/GRAFANA_PRUNE:-1/' \
  --mutation 's/^  \*\.grafana\.net | \*\.grafana\.net\/\*)$/  *.grafana.invalid)/' -- $PUSH
```

Expected: each of the five runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 6 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, five runs, each KILLED with its control proven.
`infra/scripts/grafana-push.sh`, control the prune default flipped: the default emptied, KILLED,
control proven; `-` turned into `:-`, KILLED, control proven; the filter comparing against an
empty list, KILLED, control proven; the unfiltered rules sent, KILLED, control proven; the refusal
pointed at a domain no push names, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 7: The node's rule group, its runbook page, its Fleet health row and the fleet page

**Files:**
- Create: `infra/runbooks/mon.md`
- Modify: `infra/grafana/alerts.yaml` (the `zcrypto-mon` group's eight rules, appended)
- Modify: `infra/scripts/ops_daily.py` (seven `_UID_HOST` entries; the patch pass's reminder in `read_reminders`)
- Modify: `infra/grafana/fleet-health-dashboard.json` (a row and eight panels, ids 900 to 908, at the end of `panels`)
- Modify: `infra/runbooks/observability.md` (one sentence pointing at the node's own Alloy-dark section)
- Modify: `docs/reference/fleet.md` (four Services rows; one Telemetry labels bullet)
- Test: `tests/test_infra_alert_rules.py`
- Test: `tests/test_ops_daily.py` (the reminder's cases; the existing case over the committed files admits the reminder)

**Interfaces:**
- Consumes: Task 4's labels and jobs (`host="zcrypto-mon"`; `integrations/unix`, `grafana`, `prometheus`, `loki`; `container="grafana-server"`) and its `UNFILTERED_HOSTS`; Task 5's `--stack mon` on both tools; Task 6's `GRAFANA_SKIP_RULE_GROUPS` and its default line; Task 1's `mon` alias, converge shapes and `_MON_AUTONOMOUS_OBJECTS`; the rule file's helpers in `tests/test_infra_alert_rules.py` (`_rules`, `_rule`, `_prom_exprs`, `_duration_seconds`, `PUSH`, `ANSIBLE`); the runbook page's four-part section form and `infra/runbooks/README.md`.
- Produces, for the Rollout and phases 2 to 4: the rule group `zcrypto-mon` and its eight uids; the anchors of `infra/runbooks/mon.md`, five procedures (`mon-push`, `mon-secrets`, `mon-token-rotate`, `mon-store-restart`, `mon-patch-pass`) and one per rule; the Fleet health board's row `Observability node`, panels 901 to 908; the daily pass's reminder `mon patch pass`, due a month after the node's last full converge in `docs/reference/deploy-log.jsonl`.

**What this task decides: the eight rules' thresholds and `for` values, each verified by value at the first push (Rollout R9).** The spec states two (the series bar and the retention rule's meaning); the rest are this plan's, each with its basis in one clause.
- `zcrypto-alloy-dark-mon`, critical: `count(up{host="zcrypto-mon"}) or on() vector(0)` below 1 for 10 m, NoData alerting; the fleet's per-host Alloy-dark rules' own shape and duration. First push: reads 5, one per scrape job.
- `zcrypto-mon-disk-low`, warning: root filesystem free below 0.15 for 30 m; `zaccess-disk-high`'s bar and duration, the ops and cache root-disk rules' too, which on 80 GB leaves 12 GB, more than both stores are sized to hold. First push: one series, above 0.9.
- `zcrypto-mon-reboot-pending`, warning: `node_reboot_required{host="zcrypto-mon"}` above 0.5 for 15 m; `zcrypto-capture-reboot-pending`'s bar and duration, which a test holds equal. First push: one series, 0; no series is a fail, the timer not having run.
- `zcrypto-mon-store-down`, critical: the count of stores up and ready below 2 for 3 m, NoData OK; three scrapes, so one failed scrape does not page and a restart in the role's order is over before the rule next evaluates. Loki counts only while its ingester is `ACTIVE` in the ring; its `/ready` is a separate signal, which the self-check and Grafana's unit read; a dark Alloy returns nothing here and is the first rule's page. First push: reads 2.
- `zcrypto-mon-sqlite-locked`, warning, receiver `logs`: any `database is locked` line of Grafana's in 15 m that is not a retry, `for: 0s`; the burst rules' window. Grafana 13.2 logs `Database locked, sleeping then retrying` at info on its ordinary retry path, at each start and beside its own cleanup job, and that line carries the string too: the selector leaves it out, so the rule counts a write Grafana gave up on, the assessment's trigger for PostgreSQL. First push: reads 0, beside R9's read that the stream it selects has lines.
- `zcrypto-mon-ingest-dark`, critical: `count(up{host!="zcrypto-mon"}) or on() vector(0)` below 1 for 5 m, NoData alerting; half the Alloy-dark rules' 10 m, so with the five minutes a vanished series stays readable it pages about ten minutes after ingest stops and five ahead of the first per-host page, which a test holds. First push: reads 0 and fires, by design, until phase 2's first host ships; the shadow channel takes it (spec D18).
- `zcrypto-mon-series-high`, warning: `prometheus_tsdb_head_series{host="zcrypto-mon"}` above 20,000 for 3 h; the spec's bar, held for three hours because the head keeps a restarted shipper's old series until its next truncation. First push: the node's own unfiltered count alone, read and recorded (`## What this plan asks of the spec` says why the reading matters).
- `zcrypto-mon-retention-by-size`, warning: `increase(prometheus_tsdb_size_retentions_total{host="zcrypto-mon"}[6h])` above 0, `for: 0s`; any deletion by the size cap is the event, and six hours spans three of Prometheus's two-hour compactions. First push: reads 0.

**What else this task decides:**
- Each rule but `zcrypto-mon-ingest-dark` selects `host="zcrypto-mon"` and nothing else, and no rule outside the group carries a `host` matcher that admits the node, a regex or a negative one included: `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` holds both directions, so a rule pushed to both stacks does not name a host Grafana Cloud never receives. A rule with no `host` matcher is outside that test: it reads whatever hosts its stack holds, and the spec's comparison by value is what shows an extra row from the node.
- The monthly patch pass is brought due by the daily pass, on the refdata sweep's pattern: `read_reminders` gains `mon patch pass`, owed a month after the node's last full converge, the last successful `site.yml` row of `docs/reference/deploy-log.jsonl` whose `limit` is `zcrypto-mon` and whose `tags` and `skip_tags` are empty. The node's first converge is such a row, the pass's own re-converge is written as one, and every other procedure on the page converges under `--tags mon`, so the record is the row the pass already leaves and nothing new is kept. A log with no such row yields no reminder: the node is not built.
- Until the node pages the main channel, its pending-reboot rule reaches the shadow channel alone, so the patch pass reads the reboot flag itself, and the reminder is what brings the pass, and that read, to a person.
- `_UID_HOST` gains seven of the eight uids; `zcrypto-mon-ingest-dark` is left out because it pins no one host.
- The runbook page is `infra/runbooks/mon.md`, in the directory's four-part form. Its commands are written so the daily pass's classifier reads them: `systemctl is-active` over at most three units a line, one `&&` line for the upgrade, `--stack mon` on each read. The corpus floor `tests/test_ops_daily.py` holds, 0.70 of runbook commands classified autonomous, stays above its bar with the page added.
- The exposure page's "read ingest-dark first" step is not added to `infra/runbooks/engine.md` here: the node's exposure rule pages a shadow channel no one acts on in this phase, and the step is true of the operator's path from phase 3's cutover. The spec's phase-3 change list names `infra/runbooks/engine.md` for it, so the plan written from that list delivers it.
- The ingest-dark section's credential read is taken from the workstation, through the edge, with the vaulted `fleet` password: Caddy writes no access log, so nothing on the node counts a refused push, and a 401 there says the node's hash is not the vaulted password's.
- The dashboard row is inserted at the end of the Fleet health board's `panels`, ids 900 to 908, each rule's `__panelId__` naming its own panel; the row is drawn from the node's series, so on Grafana Cloud it is empty by construction, and its first panel's description says so.

- [ ] **Step 1: Write the failing tests**

`tests/test_infra_alert_rules.py` — append at the end of the file (the block opens with 2 blank lines, kept):

```python


# --- the observability node's own group: evaluated on the node alone -----------------------------
_MON_GROUP = "zcrypto-mon"
_MON_RULES = {
    "zcrypto-alloy-dark-mon": ("critical", "901"),
    "zcrypto-mon-disk-low": ("warning", "902"),
    "zcrypto-mon-reboot-pending": ("warning", "903"),
    "zcrypto-mon-store-down": ("critical", "904"),
    "zcrypto-mon-sqlite-locked": ("warning", "905"),
    "zcrypto-mon-ingest-dark": ("critical", "906"),
    "zcrypto-mon-series-high": ("warning", "907"),
    "zcrypto-mon-retention-by-size": ("warning", "908"),
}


def _mon_rules() -> list[dict]:
    return [r for r in _rules() if r["ruleGroup"] == _MON_GROUP]


def _evaluator(rule: dict) -> dict:
    return next(q for q in rule["data"] if q["model"].get("type") == "threshold")["model"]["conditions"][0]["evaluator"]


def test_the_mon_group_is_its_eight_rules_each_with_its_own_section_and_panel():
    found = {
        r["uid"]: (r["labels"]["severity"], r["annotations"]["__panelId__"])
        for r in _mon_rules()
        if r["annotations"]["__dashboardUid__"] == "zcrypto-fleet"
    }
    assert found == _MON_RULES
    for rule in _mon_rules():
        assert rule["annotations"]["summary"].endswith(f"Runbook: infra/runbooks/mon.md#{rule['uid']}"), rule["uid"]


def test_the_push_keeps_the_mon_group_off_grafana_cloud_by_default():
    """Grafana Cloud holds no series of the node, so the group's two dead-men would page there for good."""
    (skipped,) = re.findall(r'^export GRAFANA_SKIP_RULE_GROUPS="\$\{GRAFANA_SKIP_RULE_GROUPS-([^}]*)\}"$', PUSH.read_text(), re.M)
    assert skipped.split() == [_MON_GROUP]
    dead_men = sorted(r["uid"] for r in _mon_rules() if r["noDataState"] == "Alerting")
    assert dead_men == ["zcrypto-alloy-dark-mon", "zcrypto-mon-ingest-dark"], dead_men


def _admits_the_node(op: str, value: str) -> bool:
    matched = bool(re.fullmatch(value, "zcrypto-mon")) if "~" in op else value == "zcrypto-mon"
    return matched if op in ("=", "=~") else not matched


def test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group():
    """A rule outside the group whose `host` matcher admitted the node would be pushed to Grafana Cloud, where the node
    has no series. A rule with no `host` matcher is not held here."""
    for rule in _rules():
        matchers = [
            (op, value)
            for q in rule["data"]
            for op, value in re.findall(r'\bhost\s*(=~|!=|!~|=)\s*"([^"]*)"', str((q.get("model") or {}).get("expr", "")))
        ]
        admits_the_node = [(op, value) for op, value in matchers if _admits_the_node(op, value)]
        if rule["ruleGroup"] != _MON_GROUP:
            assert not admits_the_node, f"{rule['uid']} is pushed to both stacks and its matcher {admits_the_node} admits the node"
        elif rule["uid"] == "zcrypto-mon-ingest-dark":
            assert matchers == [("!=", "zcrypto-mon")], matchers
        else:
            assert matchers and set(matchers) == {("=", "zcrypto-mon")}, (rule["uid"], matchers)


def test_ingest_dark_pages_ahead_of_every_per_host_alloy_dark_rule():
    """Every fleet host absent at once is the node's edge, and the page that says so has to arrive before the per-host
    pages and the exposure page that the same fault produces."""
    ingest = _rule("zcrypto-mon-ingest-dark")
    assert _prom_exprs(ingest) == ['count(up{host!="zcrypto-mon"}) or on() vector(0)']
    assert _evaluator(ingest) == {"type": "lt", "params": [1]}
    per_host = [r for r in _rules() if r["uid"].startswith("zcrypto-alloy-dark-") and r["ruleGroup"] != _MON_GROUP]
    assert len(per_host) == 8, [r["uid"] for r in per_host]
    assert all(_duration_seconds(ingest["for"]) < _duration_seconds(r["for"]) for r in per_host)
    assert _duration_seconds(ingest["for"]) < _duration_seconds(_rule("zcrypto-engine-dark-with-exposure")["for"])


def test_the_store_rule_counts_two_stores_and_leaves_a_dark_alloy_to_its_own_rule():
    rule = _rule("zcrypto-mon-store-down")
    (expr,) = _prom_exprs(rule)
    for leg in ('up{host="zcrypto-mon", job="prometheus"} == 1', 'up{host="zcrypto-mon", job="loki"} == 1'):
        assert expr.count(leg) == 1, leg
    assert expr.endswith('and on() (up{host="zcrypto-mon", job="integrations/unix"} == 1)')
    assert _evaluator(rule) == {"type": "lt", "params": [2]}
    assert rule["noDataState"] == "OK", "a dark Alloy returns nothing here, and that is zcrypto-alloy-dark-mon's page"
    assert "alert history is not written" in rule["annotations"]["summary"]


def test_the_two_budget_fences_read_what_prometheus_reports_about_itself():
    series = _rule("zcrypto-mon-series-high")
    assert _prom_exprs(series) == ['prometheus_tsdb_head_series{host="zcrypto-mon"}']
    assert _evaluator(series) == {"type": "gt", "params": [20000]}
    retention = _rule("zcrypto-mon-retention-by-size")
    (expr,) = _prom_exprs(retention)
    assert expr == 'increase(prometheus_tsdb_size_retentions_total{host="zcrypto-mon"}[6h])'
    assert retention["data"][0]["relativeTimeRange"] == {"from": 21600, "to": 0}
    assert _evaluator(retention) == {"type": "gt", "params": [0]}


def test_the_database_lock_rule_is_a_burst_rule_over_grafanas_own_journal():
    rule = _rule("zcrypto-mon-sqlite-locked")
    (query,) = [q for q in rule["data"] if q["datasourceUid"] == "${GRAFANA_LOKI_DS_UID}"]
    # The retry line carries the same text at info, at every start: without the second filter the rule fires on it.
    assert query["model"]["expr"] == (
        'sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "database is locked"'
        ' != "sleeping then retrying" [15m])) or on() vector(0)'
    )
    assert (rule["for"], rule["notification_settings"]["receiver"]) == ("0s", "logs")
    alloy = (ANSIBLE / "roles/mon/files/config.alloy").read_text()
    (units,) = re.findall(r'^\s*regex\s*=\s*"\(([a-z|-]+)\)\\\\\.service"$', alloy, re.M)
    assert "grafana-server" in units.split("|"), (
        "the node's Alloy no longer ships Grafana's journal, so this rule would read nothing"
    )


def test_the_node_reboot_rule_keeps_the_capture_rules_bar_and_duration():
    ours, theirs = _rule("zcrypto-mon-reboot-pending"), _rule("zcrypto-capture-reboot-pending")
    assert _prom_exprs(ours) == ['node_reboot_required{host="zcrypto-mon"}']
    assert (_evaluator(ours), ours["for"]) == (_evaluator(theirs), theirs["for"])
```

The patch pass's reminder, in `tests/test_ops_daily.py`. The existing case over the committed files reads the committed deploy log from here on, which gains the node's rows at the rollout, so it stops holding the set of reminders closed against this one:

`tests/test_ops_daily.py` — replace

```python
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)))
    assert read.unreadable is None, read.unreadable
    assert {r.name for r in read.reminders} == {"refdata sweep", "healable re-derivation"}
```

with

```python
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)))
    assert read.unreadable is None, read.unreadable
    # The committed deploy log decides whether the observability node's patch pass is a third.
    assert {r.name for r in read.reminders} - {"mon patch pass"} == {"refdata sweep", "healable re-derivation"}


def _converge(ts: str, *, limit="zcrypto-mon", tags="", rc=0, playbook="site.yml") -> dict:
    return {"ts": ts, "limit": limit, "tags": tags, "skip_tags": "", "rc": rc, "playbook": playbook}


def _deploy_log(tmp_path, *rows):
    log = tmp_path / "deploy-log.jsonl"
    log.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return log


_MON_LOG = (
    _converge("2026-10-06T09:00:00Z"),  # the node's first converge
    _converge("2026-11-03T10:00:00Z"),  # a patch pass's re-converge
    _converge("2026-11-20T10:00:00Z", tags="mon"),  # a token re-mint or a replaced secret, which is no pass
    _converge("2026-11-21T10:00:00Z", rc=2),  # a full converge that failed
    _converge("2026-11-22T10:00:00Z", limit="zcrypto-ops"),
    _converge("2026-11-23T10:00:00Z", playbook="bootstrap.yml"),
)


@pytest.mark.parametrize(
    "now,status,owed",
    [
        (datetime(2026, 11, 28, 3, 0, tzinfo=timezone.utc), "due in 5 days", False),
        (datetime(2026, 12, 3, 3, 0, tzinfo=timezone.utc), "due in 0 days", True),
        (datetime(2026, 12, 9, 3, 0, tzinfo=timezone.utc), "OVERDUE by 6 days", True),
    ],
)
def test_the_mon_patch_pass_is_due_a_month_after_the_nodes_last_full_converge(tmp_path, now, status, owed):
    read = ops_daily.read_reminders(
        "tok",
        now=now,
        window=DAY,
        opener=_canned(_counter(0)),
        register=_register(tmp_path, *_TWO_SWEEPS),
        deploy_log=_deploy_log(tmp_path, *_MON_LOG),
    )
    patch = _reminder(read, "mon patch pass")
    assert patch.status.startswith(status) and "2026-11-03" in patch.status, patch.status
    assert patch.owed is owed
    assert patch.runbook == "infra/runbooks/mon.md#mon-patch-pass"
    assert read.unreadable is None


@pytest.mark.parametrize("rows", [(), _MON_LOG[2:]], ids=["an empty log", "no full converge of the node"])
def test_a_deploy_log_with_no_full_converge_of_the_node_owes_no_patch_pass(tmp_path, rows):
    read = ops_daily.read_reminders(
        "tok",
        now=NOW,
        window=DAY,
        opener=_canned(_counter(0)),
        register=_register(tmp_path, *_TWO_SWEEPS),
        deploy_log=_deploy_log(tmp_path, *rows),
    )
    assert read.unreadable is None, read.unreadable
    assert {r.name for r in read.reminders} == {"refdata sweep", "healable re-derivation"}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_ops_daily.py -q -p no:cacheprovider`

Expected: `12 failed`, the rest passed: seven of the eight new rule-file cases meet no `zcrypto-mon` rule, and the five reminder cases meet a `read_reminders` that takes no `deploy_log`. `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` passes over a rule file with no such rule; Step 9's probes are what show it bites.

- [ ] **Step 3: The rule group**

`infra/grafana/alerts.yaml` — append at the end of the file (the block opens with 1 blank line, kept):

```yaml

  # ---- zcrypto-mon: the observability node's own rules -------------------------------------------
  # Pushed to the node alone: grafana-push.sh leaves this group out of a push that names no stack
  # (GRAFANA_SKIP_RULE_GROUPS), since Grafana Cloud holds no `host="zcrypto-mon"` series and the two
  # dead-men here would page there for good. A rule cannot page the death of the node it runs on:
  # that is the node's healthchecks.io self-check, not a rule of this group.
  - uid: zcrypto-alloy-dark-mon
    title: "Fleet · Alloy dark — Monitor"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # The family's shape, `zcrypto-alloy-dark-nas` above: presence of `up`, with the fallback
          # that lets noDataState stay Alerting.
          expr: >-
            count(up{host="zcrypto-mon"}) or on() vector(0)
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
      summary: "The observability node's own Alloy has shipped no metrics for >10m. The node's host, Grafana, Prometheus and Loki series are dark, so every other rule of the node's own group is blind until this clears; the fleet's rules read the fleet's own Alloys and are unaffected. First checks on the node: `systemctl status alloy`, then `journalctl -u alloy -n 50`; a restart is the usual fix. Runbook: infra/runbooks/mon.md#zcrypto-alloy-dark-mon"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "901"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-disk-low
    title: "Monitor · root filesystem low"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # The threshold and the duration are zaccess-disk-high's. On this node's 80 GB the bar leaves
          # 12 GB, more than both stores are sized to hold between them.
          expr: >-
            node_filesystem_avail_bytes{host="zcrypto-mon", mountpoint="/"} / node_filesystem_size_bytes{host="zcrypto-mon", mountpoint="/"}
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
            - evaluator: {type: lt, params: [0.15]}  # < 15% free
    noDataState: OK
    execErrState: Alerting
    for: 30m
    annotations:
      summary: "The observability node's root filesystem has been below 15% free for 30+ minutes. Prometheus's blocks, Loki's chunks, Grafana's database and the journal share it: a full disk stops ingestion and then evaluation. Runbook: infra/runbooks/mon.md#zcrypto-mon-disk-low"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "902"
      unit: "of the root filesystem still free (a fraction, not a percent)"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-reboot-pending
    title: "Monitor · reboot pending, reboot by hand"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      # The node runs unattended-upgrades with Automatic-Reboot "false": patches install, the reboot is
      # a human act, and this rule is what makes the pending one visible. The capture pair's rule,
      # zcrypto-capture-reboot-pending, cannot carry this host: it is pushed to Grafana Cloud too,
      # where this host has no series.
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 3600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: 'node_reboot_required{host="zcrypto-mon"}'
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
            - evaluator: {type: gt, params: [0.5]}  # == 1, pending
    noDataState: OK
    execErrState: Alerting
    # zcrypto-capture-reboot-pending's duration: one failed publish does not page.
    for: 15m
    annotations:
      summary: "The observability node has a pending reboot (/run/reboot-required) and does not reboot itself. Reboot it by hand in its 06:25 UTC slot: rule evaluation stops for the reboot's duration, and Grafana starts again only once both stores answer ready. Runbook: infra/runbooks/mon.md#zcrypto-mon-reboot-pending"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "903"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-store-down
    title: "Monitor · a store down or not ready"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # How many of the two stores the node's Alloy scrapes as up, Loki counted only while its
          # ingester is ACTIVE in the ring. The `and on()` arm leaves a dark Alloy to
          # zcrypto-alloy-dark-mon: with no host scrape the query returns nothing, and noDataState is
          # OK. Prometheus itself down is this rule's own ERROR state, since the query has nowhere to
          # run.
          expr: >-
            (count((up{host="zcrypto-mon", job="prometheus"} == 1) or ((up{host="zcrypto-mon", job="loki"} == 1) and on(host) (loki_ring_members{host="zcrypto-mon", name="ingester", state="ACTIVE"} == 1))) or on() vector(0)) and on() (up{host="zcrypto-mon", job="integrations/unix"} == 1)
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
    # Three scrapes at 60 s: a store restarted in the role's order, with Grafana stopped around it,
    # is back inside one, and a single failed scrape does not page.
    for: 3m
    annotations:
      summary: "Fewer than two of the observability node's stores are up and ready: Prometheus or Loki is down, or Loki's ingester is not ACTIVE. If this page is in its ERROR state, Prometheus is the store that is down. While Loki is down the rules that read logs are in error and alert history is not written: a transition in that time is missing from the daily pass's fired-in-window list. Runbook: infra/runbooks/mon.md#zcrypto-mon-store-down"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "904"
      unit: "stores up and ready, of 2"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-sqlite-locked
    title: "Monitor · Grafana's database locked"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      # A text match, since the line is Grafana's own and carries no label for it. Grafana's retry of
      # a locked write logs the same text at info, `Database locked, sleeping then retrying`, at each
      # start and beside its cleanup job: the second filter leaves those out, so what is counted is
      # a write Grafana gave up on. The window is the burst rules' 15 minutes.
      - refId: A
        queryType: instant
        relativeTimeRange: {from: 900, to: 0}
        datasourceUid: "${GRAFANA_LOKI_DS_UID}"
        model:
          expr: >-
            sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "database is locked" != "sleeping then retrying" [15m])) or on() vector(0)
          queryType: instant
          refId: A
      - refId: B
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: reduce
          reducer: last
          expression: "A"
          refId: B
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "B"
          refId: C
          conditions:
            - evaluator: {type: gt, params: [0]}
    noDataState: OK  # `or on() vector(0)` makes a clean window evaluate to 0, not NoData
    execErrState: Alerting
    for: 0s
    annotations:
      summary: "Grafana gave up on a write to its embedded SQLite database in the last 15 minutes: the database stayed locked through its retries, and the line it logged is not one of those retries. While a push runs it is a call that push failed on, and the push is run again; recurring with no push running, it is the sign that the database has outgrown SQLite, the recorded condition for moving Grafana's own state to PostgreSQL. Runbook: infra/runbooks/mon.md#zcrypto-mon-sqlite-locked"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "905"
      unit: "failed writes logging `database is locked` in the last 15 minutes"
    labels:
      severity: warning
    notification_settings:
      receiver: logs

  - uid: zcrypto-mon-ingest-dark
    title: "Monitor · ingest dark, every fleet host absent at once"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # Every host but the node itself: the fleet arrives through Caddy, the node's own Alloy on
          # loopback, so this goes to 0 on a fault of the edge or its certificate and never on one
          # host's.
          expr: >-
            count(up{host!="zcrypto-mon"}) or on() vector(0)
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
    # Half the Alloy-dark rules' 10m, so that with the five minutes a vanished series stays readable
    # this pages about ten minutes after ingest stops and five ahead of the first per-host page.
    for: 5m
    annotations:
      summary: "No fleet host has a sample on the observability node: every host went absent at once, which is the node's own edge, its certificate or its firewall, not the fleet. The per-host Alloy-dark pages and the engine-dark-with-exposure page that follow within minutes are this fault seen from each rule, and the fleet itself may be healthy and still shipping to its other destination. Runbook: infra/runbooks/mon.md#zcrypto-mon-ingest-dark"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "906"
      unit: "fleet series present"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-series-high
    title: "Monitor · head series above budget"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: 'prometheus_tsdb_head_series{host="zcrypto-mon"}'
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
            - evaluator: {type: gt, params: [20000]}
    noDataState: OK
    execErrState: Alerting
    # The head keeps a series a restarted shipper stopped writing until its next truncation, up to
    # three hours, so a restart's doubled count clears itself and growth that stays pages.
    for: 3h
    annotations:
      summary: "The observability node's Prometheus has held more than 20,000 series in its head for three hours. The node ships unfiltered, so this bar is the series budget's fence: a new exporter, a label that grew a value per request, or a shipper's collector set widened. Memory and disk follow the count. Runbook: infra/runbooks/mon.md#zcrypto-mon-series-high"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "907"
      unit: "series in the head"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-mon-retention-by-size
    title: "Monitor · Prometheus retention cut by size"
    ruleGroup: zcrypto-mon
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 21600, to: 0}  # 6h, matching the increase window below
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # Prometheus deletes blocks at most once per two-hour compaction, so six hours keeps
          # consecutive cuts one firing and clears six hours after the last.
          expr: >-
            increase(prometheus_tsdb_size_retentions_total{host="zcrypto-mon"}[6h])
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
    for: 0s
    annotations:
      summary: "Prometheus on the observability node deleted a block because its size cap was reached, in the last 6 hours: the store now keeps less than its 90 days, and the size cap, not the period, governs what is kept. The series count or the sample rate outgrew what the cap was sized for. Runbook: infra/runbooks/mon.md#zcrypto-mon-retention-by-size"
      __dashboardUid__: "zcrypto-fleet"
      __panelId__: "908"
      unit: "blocks deleted by the size cap in the last 6 hours"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics
```

`infra/scripts/ops_daily.py` — replace

```python
    "zcrypto-alloy-dark-cache-3": "zcrypto-valkey3",
}
```

with

```python
    "zcrypto-alloy-dark-cache-3": "zcrypto-valkey3",
    "zcrypto-alloy-dark-mon": "zcrypto-mon",
    "zcrypto-mon-disk-low": "zcrypto-mon",
    "zcrypto-mon-reboot-pending": "zcrypto-mon",
    "zcrypto-mon-store-down": "zcrypto-mon",
    "zcrypto-mon-sqlite-locked": "zcrypto-mon",
    "zcrypto-mon-series-high": "zcrypto-mon",
    "zcrypto-mon-retention-by-size": "zcrypto-mon",
}
```

The patch pass's reminder, beside the refdata sweep's:

`infra/scripts/ops_daily.py` — replace

```python
HEALABLE_COUNTER = "zcrypto_reconcile_healable_gap_seconds_total"
REFDATA_RUNBOOK = "infra/runbooks/reference-data.md#refdata-sweep-due"
HEALABLE_RUNBOOK = "infra/runbooks/ops.md#healable-threshold-rederivation-due"
```

with

```python
HEALABLE_COUNTER = "zcrypto_reconcile_healable_gap_seconds_total"
REFDATA_RUNBOOK = "infra/runbooks/reference-data.md#refdata-sweep-due"
HEALABLE_RUNBOOK = "infra/runbooks/ops.md#healable-threshold-rederivation-due"
MON_PATCH_RUNBOOK = "infra/runbooks/mon.md#mon-patch-pass"
MON_NODE = "zcrypto-mon"


def last_full_converge(log: Path, host: str) -> date | None:
    """The date of `host`'s last successful `site.yml` converge that named no tag, or None when the log holds none."""
    if not log.exists():
        return None
    found = None
    for line in log.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        whole = row.get("playbook") == "site.yml" and not row.get("tags") and not row.get("skip_tags")
        if whole and row.get("limit") == host and row.get("rc") == 0:
            found = date.fromisoformat(row["ts"][:10])
    return found
```

`infra/scripts/ops_daily.py` — replace

```python
def read_reminders(
    token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen, register: Path = REGISTER
) -> RemindersRead:
    """Due-ness computed from state the pass can read, so a Slack reminder that never arrives costs
    nothing (spec 00107 D1). Each reminder comes from the source that actually knows: the sweep from
    the register's last re-confirmation row plus the monthly cadence, the healable re-derivation from
    whether its counter moved in the window.
```

with

```python
def read_reminders(
    token: str,
    *,
    now: datetime,
    window: timedelta,
    opener=urllib.request.urlopen,
    register: Path = REGISTER,
    deploy_log: Path = DEPLOY_LOG,
) -> RemindersRead:
    """Due-ness computed from state the pass can read, so a Slack reminder that never arrives costs
    nothing (spec 00107 D1). Each reminder comes from the source that actually knows: the sweep from
    the register's last re-confirmation row plus the monthly cadence, the observability node's patch
    pass from its last full converge in the deploy log plus the same cadence, the healable
    re-derivation from whether its counter moved in the window.
```

`infra/scripts/ops_daily.py` — replace

```python
                Reminder("refdata sweep", f"{status} (last sweep {last.isoformat()})", owed=days <= 0, runbook=REFDATA_RUNBOOK)
            )

    hours = max(1, int(window.total_seconds() // 3600))
```

with

```python
                Reminder("refdata sweep", f"{status} (last sweep {last.isoformat()})", owed=days <= 0, runbook=REFDATA_RUNBOOK)
            )

    try:
        patched = last_full_converge(deploy_log, MON_NODE)
    except _UNREACHABLE as exc:
        note(f"the deploy log could not be read: {exc}")
    else:
        # No full converge on record is a node that is not built: nothing is owed on it.
        if patched is not None:
            days = (_a_month_after(patched) - now.date()).days
            status = f"due in {days} days" if days >= 0 else f"OVERDUE by {-days} days"
            last_pass = f"{status} (last full converge {patched.isoformat()})"
            read.reminders.append(Reminder("mon patch pass", last_pass, owed=days <= 0, runbook=MON_PATCH_RUNBOOK))

    hours = max(1, int(window.total_seconds() // 3600))
```

- [ ] **Step 4: The dashboard row**

The insertion is the tail of the board's `panels` list: the list's last panel closes with `    }` and the list with `  ],`, and the row and its eight panels go between the two.

`infra/grafana/fleet-health-dashboard.json` — replace

```json
    }
  ],
  "refresh": "1m",
```

with

```json
    },
    {
      "id": 900,
      "type": "row",
      "title": "Observability node",
      "collapsed": false,
      "panels": [],
      "gridPos": {
        "h": 1,
        "w": 24,
        "x": 0,
        "y": 111
      }
    },
    {
      "id": 901,
      "type": "timeseries",
      "title": "Monitor — its own Alloy shipping",
      "description": "Is the observability node's own Alloy shipping? The count of scrape targets it reports, 0 when it reports none: the alert pages when this falls below the green line at 1 and stays there for ten minutes. This row is drawn from the node's own series, which the node alone holds, so on any other Grafana the whole row is empty. A dark Alloy here blinds this row and nothing else: the fleet's panels read the fleet's own shippers.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 0,
        "y": 112
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "count(up{host=\"zcrypto-mon\"}) or on() vector(0)",
          "refId": "A",
          "legendFormat": "scrape targets the node's Alloy reports"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "thresholdsStyle": {
              "mode": "line"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 902,
      "type": "timeseries",
      "title": "Monitor — root filesystem free",
      "description": "How much of the node's one disk is left? Prometheus's blocks, Loki's chunks, Grafana's database and the journal share it. The alert pages below the green line at 15% free, held for thirty minutes.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 6,
        "y": 112
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "node_filesystem_avail_bytes{host=\"zcrypto-mon\", mountpoint=\"/\"} / node_filesystem_size_bytes{host=\"zcrypto-mon\", mountpoint=\"/\"}",
          "refId": "A",
          "legendFormat": "free"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percentunit",
          "custom": {
            "thresholdsStyle": {
              "mode": "line"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 0.15
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 903,
      "type": "timeseries",
      "title": "Monitor — reboot pending",
      "description": "Does the node need its reboot by hand? It installs patches and does not reboot itself, so a flag at 1 stays until someone reboots it, and the alert pages once the flag has been up for fifteen minutes. A flat zero is the healthy state.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 12,
        "y": 112
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "node_reboot_required{host=\"zcrypto-mon\"}",
          "refId": "A",
          "legendFormat": "reboot pending"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "lineInterpolation": "stepAfter",
            "thresholdsStyle": {
              "mode": "line"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 0.5
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 904,
      "type": "timeseries",
      "title": "Monitor — stores up and ready",
      "description": "Are both stores serving? The first line is how many of Prometheus and Loki are up and ready, and the alert pages when it falls below the green line at 2 for three minutes; the other lines show which store's scrape failed. A Grafana that cannot reach Prometheus cannot draw this panel at all, which is itself the answer.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 18,
        "y": 112
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "(count((up{host=\"zcrypto-mon\", job=\"prometheus\"} == 1) or ((up{host=\"zcrypto-mon\", job=\"loki\"} == 1) and on(host) (loki_ring_members{host=\"zcrypto-mon\", name=\"ingester\", state=\"ACTIVE\"} == 1))) or on() vector(0)) and on() (up{host=\"zcrypto-mon\", job=\"integrations/unix\"} == 1)",
          "refId": "A",
          "legendFormat": "stores up and ready"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "up{host=\"zcrypto-mon\", job=~\"prometheus|loki\"}",
          "refId": "B",
          "legendFormat": "{{job}} scrape up"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "lineInterpolation": "stepAfter",
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byFrameRefID",
              "options": "A"
            },
            "properties": [
              {
                "id": "custom.thresholdsStyle",
                "value": {
                  "mode": "line"
                }
              },
              {
                "id": "thresholds",
                "value": {
                  "mode": "absolute",
                  "steps": [
                    {
                      "color": "red",
                      "value": null
                    },
                    {
                      "color": "green",
                      "value": 2
                    }
                  ]
                }
              }
            ]
          }
        ]
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 905,
      "type": "timeseries",
      "title": "Monitor — Grafana writes failed on a locked database",
      "description": "Is Grafana's embedded database keeping up? Each point is the number of writes Grafana gave up on with `database is locked` in the fifteen minutes before it, its ordinary retries left out; the alert pages on the first one. One while a push runs is a call that push failed on; a steady run with no push is the sign the database has outgrown SQLite.",
      "datasource": {
        "type": "loki",
        "uid": "grafanacloud-logs"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 0,
        "y": 120
      },
      "targets": [
        {
          "datasource": {
            "type": "loki",
            "uid": "grafanacloud-logs"
          },
          "expr": "sum(count_over_time({host=\"zcrypto-mon\", container=\"grafana-server\"} |= \"database is locked\" != \"sleeping then retrying\" [15m])) or on() vector(0)",
          "refId": "A",
          "legendFormat": "failed writes in the last 15 minutes"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "thresholdsStyle": {
              "mode": "line"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 906,
      "type": "timeseries",
      "title": "Monitor — fleet series arriving",
      "description": "Is anything from the fleet reaching the node? The first line counts the fleet's scrape-health series, 0 when none arrives, and the alert pages when it falls below the green line at 1 for five minutes: every host absent at once is the node's own edge or certificate, not the fleet. The second line is how many fleet hosts are shipping.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 6,
        "y": 120
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "count(up{host!=\"zcrypto-mon\"}) or on() vector(0)",
          "refId": "A",
          "legendFormat": "fleet scrape-health series"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "count(count by (host) (up{host!=\"zcrypto-mon\"}))",
          "refId": "B",
          "legendFormat": "fleet hosts shipping"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byFrameRefID",
              "options": "A"
            },
            "properties": [
              {
                "id": "custom.thresholdsStyle",
                "value": {
                  "mode": "line"
                }
              },
              {
                "id": "thresholds",
                "value": {
                  "mode": "absolute",
                  "steps": [
                    {
                      "color": "red",
                      "value": null
                    },
                    {
                      "color": "green",
                      "value": 1
                    }
                  ]
                }
              }
            ]
          }
        ]
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 907,
      "type": "timeseries",
      "title": "Monitor — Prometheus head series",
      "description": "How many series is Prometheus holding in memory? The fleet ships to this node unfiltered, so this count is the budget: the alert pages above the red line at 20,000, held for three hours. A step up that stays is a new exporter or a label that grew a value per request; a bump that clears within three hours is a shipper restart.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 12,
        "y": 120
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "prometheus_tsdb_head_series{host=\"zcrypto-mon\"}",
          "refId": "A",
          "legendFormat": "series in the head"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "thresholdsStyle": {
              "mode": "line"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 20000
              }
            ]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    },
    {
      "id": 908,
      "type": "timeseries",
      "title": "Monitor — blocks deleted, by size and by age",
      "description": "Is Prometheus keeping its full ninety days? Blocks deleted by age are the retention period at work and are healthy. A block deleted by the size cap means the cap, not the period, now decides what is kept: the alert pages on the first one in six hours.",
      "datasource": {
        "type": "prometheus",
        "uid": "grafanacloud-prom"
      },
      "gridPos": {
        "h": 8,
        "w": 6,
        "x": 18,
        "y": 120
      },
      "targets": [
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "increase(prometheus_tsdb_size_retentions_total{host=\"zcrypto-mon\"}[6h])",
          "refId": "A",
          "legendFormat": "deleted by the size cap, last 6 h"
        },
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "increase(prometheus_tsdb_time_retentions_total{host=\"zcrypto-mon\"}[6h])",
          "refId": "B",
          "legendFormat": "deleted by age, last 6 h"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": [
          {
            "matcher": {
              "id": "byFrameRefID",
              "options": "A"
            },
            "properties": [
              {
                "id": "custom.thresholdsStyle",
                "value": {
                  "mode": "line"
                }
              },
              {
                "id": "thresholds",
                "value": {
                  "mode": "absolute",
                  "steps": [
                    {
                      "color": "green",
                      "value": null
                    },
                    {
                      "color": "red",
                      "value": 1
                    }
                  ]
                }
              }
            ]
          }
        ]
      },
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom",
          "showLegend": true
        },
        "tooltip": {
          "mode": "multi",
          "sort": "none"
        }
      }
    }
  ],
  "refresh": "1m",
```

Run: `python3 -c 'import json; d = json.load(open("infra/grafana/fleet-health-dashboard.json")); print(len(d["panels"]), [p["id"] for p in d["panels"][-9:]])'`

Expected: the count is nine more than before the edit and the last nine ids read `[900, 901, 902, 903, 904, 905, 906, 907, 908]`. The file must still round-trip through `json.dumps(…, indent=2, ensure_ascii=False)` with a final newline, which is how the push and the tests read it.

- [ ] **Step 5: The runbook page**

Create `infra/runbooks/mon.md`:

````markdown
# Monitor runbooks — the observability node

You are here because **an alert fired in Slack** — find the section whose anchor matches the alert `uid` — or because you mean to push to the node, replace one of its secrets, re-mint the tools' token, restart one of its stores or run its monthly patch pass: the procedures at the top, found by heading. Each section is written to be actioned without opening any other document.

Everything here is one Linode VPS, `zcrypto-mon` (the workstation's ssh alias `mon`; `Monitor` in Slack and on the Fleet health board), reached by people and tools as `https://zcrypto-mon.zhaow.me`. It runs no containers: Grafana (`grafana-server`), Prometheus, Loki, Caddy and Alloy are apt packages under systemd. Caddy is the one public listener, on 443: it passes `/api/v1/write` to Prometheus and `/loki/api/v1/push` to Loki behind basic auth, answers 404 for `/metrics`, for what lies under it and for `/swagger`, and passes everything else to Grafana, whose own login and tokens guard it. Grafana, Prometheus, Loki and Alloy listen on loopback: `127.0.0.1:3000`, `:9090`, `:3100` and `:12345`. The node's own Alloy ships the node's metrics and journals to its own stores under `host="zcrypto-mon"`. A timer, `zcrypto-mon-selfcheck`, reads every five minutes whether Grafana's rule scheduler is ticking, a fleet sample is fresh and Loki is ready, and its journal line says what it read.

The node holds the fleet's telemetry, the Slack webhook and the power to silence alerts, and no key to another host. Its configuration is the `mon` role and one push, so a lost node is rebuilt from the repository; its metric and log history is on its one disk.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="mon-push"></a>

## mon-push — PROCEDURE: pushing the rules and dashboards to the node

### What you are seeing

Nothing fired. The rule file, a dashboard or the notification template changed, or the node was rebuilt, and the node's Grafana is to carry the tree.

### What it means

`infra/scripts/grafana-push.sh` pushes to the stack its environment names. With no `GRAFANA_URL` it goes to Grafana Cloud and leaves the `zcrypto-mon` rule group out; the node's push names the node, reads the node's own token and passes `GRAFANA_SKIP_RULE_GROUPS` empty, so the node's group is sent. The conditions on where a push runs from are `.claude/skills/zcrypto-grafana-push/SKILL.md`'s, for this stack as for the other. The token is the Editor service-account token the `mon` role minted into `~/.config/zcrypto/grafana-mon.vault.yml` at its last converge; `grafana_auth.py` reads it as the `mon` stack.

### What to do

1. **Push**, from the repo root, in a checkout that passes the push skill's freshness test:

   ```bash
   GRAFANA_URL=https://zcrypto-mon.zhaow.me GRAFANA_SKIP_RULE_GROUPS= \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; s = g.stack("mon"); print(g.vault_var(s.token_var, s.vault_file))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
   ```

   Its first line reads `stack=https://zcrypto-mon.zhaow.me` and `skip-groups=<none>`; a first line naming another stack means the variables did not reach the script, and nothing after it is the node's.

2. **A push that mints or moves the node's two contact points** — the first push after a rebuild, or a change of channel — also carries the webhook, as `GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_shadow_webhook_url"))')"` in front of step 1's line. The node pages the shadow channel, so the value is `slack_shadow_webhook_url`; a routine push leaves the variable unset.

3. **Confirm by value.** `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-mon"})'` reads 5, and the `Alerts` section of `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` names no rule as unhealthy.

### Retire when

`infra/scripts/grafana-push.sh` no longer reads `GRAFANA_SKIP_RULE_GROUPS`, so one stack is left and the push needs no stack named.

______________________________________________________________________

<a name="mon-secrets"></a>

## mon-secrets — PROCEDURE: generating or replacing one of the node's vaulted secrets

### What you are seeing

Nothing fired, or the `mon` role's first task refused a converge, naming a key in `infra/ansible/host_vars/zcrypto-mon/vault.yml` as missing or misshapen.

### What it means

The role reads five values from that file: `mon_grafana_admin_user`, the admin login's name, `u` and 16 hex digits; `mon_grafana_admin_password` and `mon_grafana_secret_key`, 48 hex characters each; and `mon_ingest_fleet_password_hash` and `mon_ingest_logship_password_hash`, the bcrypt hashes Caddy checks the two ingest users against. The two ingest passwords themselves are `mon_ingest_fleet_password` and `mon_ingest_logship_password` in `infra/ansible/group_vars/observed/vault.yml`, which the fleet's shippers present. A hash and its password are generated together or they do not match. Each value is generated and encrypted in one pipe and is neither typed nor printed. The admin's name is a generated one because Grafana locks an account by its name after a run of failed sign-ins, so a name a stranger can guess is one a stranger can keep locked. Grafana reads the name when it creates its database and not afterwards.

### What to do

1. **A generated string** (`mon_grafana_admin_password`, `mon_grafana_secret_key`), from `infra/ansible`: `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` prints the entry; replace the key's block in `host_vars/zcrypto-mon/vault.yml` with it. Replacing `mon_grafana_secret_key` on a running node makes Grafana unable to read what it encrypted under the old one, the contact points' webhook among them: follow it with step 2 of `mon-push`.

2. **An ingest password and its hash**, from `infra/ansible`, with `<user>` one of `fleet` and `logship`:

   ```bash
   uv run --with bcrypt python - <user> <<'PY'
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

4. **A changed ingest password reaches a shipper at that host's own converge**: until then the shipper presents the old one and Caddy answers 401, so the hosts that ship to the node are converged in the same sitting.

5. **The admin's name** (`mon_grafana_admin_user`) is restored and not regenerated on a running node: Grafana keeps the name its database was created with and refuses another as it refuses a wrong password. `git log -p -- infra/ansible/host_vars/zcrypto-mon/vault.yml` holds the entry to put back. A new name fits a node rebuilt with an empty database, from `infra/ansible`: `printf 'u%s' "$(openssl rand -hex 8)" | uv run ansible-vault encrypt_string --stdin-name mon_grafana_admin_user`.

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

Grafana evaluates each rule every minute against the two stores, and all but two rules page when their query cannot run. A store restarted under a running Grafana therefore puts the rules that read it in error for the length of the restart, and the ones with no pending period page at once. The role's handlers restart a store with Grafana stopped around it, and this procedure does the same by hand. A converge that fails part-way runs none of the restarts it had queued, and the next one finds the files unchanged and queues none: a store whose config such a converge rendered keeps running the old one until it is restarted here. Grafana's unit waits for both stores to answer ready before it starts, so starting it early is safe. Grafana writes its silences and its notification log to disk every fifteen minutes and at a clean stop: after a stop that was not clean, a silence set in the last fifteen minutes may be gone and a notification may be sent a second time.

### What to do

1. **Stop Grafana**, on the node: `sudo systemctl stop grafana-server`. Rule evaluation stops here; say so in the channel the node pages if the stop will be long.
2. **Restart the store**: `sudo systemctl restart prometheus`, or `sudo systemctl restart loki`.
3. **Start Grafana**: `sudo systemctl start grafana-server`. The command returns once both stores answered ready and Grafana started; `curl -fsS http://127.0.0.1:9090/-/ready` and `curl -fsS http://127.0.0.1:3100/ready` are the two reads it waits on.
4. **Confirm by value**, from the workstation: the `Alerts` section of `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` names no rule as unhealthy.
5. **After a Grafana that was killed or lost power**, re-read the silences in the node's UI, under Alerting, and set again the ones that are gone.

### Retire when

`infra/ansible/roles/mon/handlers/main.yml` no longer carries the handler `stop grafana around a store restart`.

______________________________________________________________________

<a name="mon-patch-pass"></a>

## mon-patch-pass — PROCEDURE: the monthly patch pass

### What you are seeing

Nothing fired. The daily pass's reminders read `OWED mon patch pass`: a month has gone by since the node's last full converge, and the packages the node does not upgrade by itself are due their pass.

### What it means

Unattended upgrades install Debian's security patches alone. Grafana, Loki, Alloy and Caddy come from their vendors' repositories, which that origin does not cover, and `prometheus` is on the node's unattended-upgrades blacklist because its package restarts the daemon on upgrade. All five are upgraded here, by hand, once a month. The reminder counts the month from the node's last full converge in `docs/reference/deploy-log.jsonl`, the one that names no tag, which step 4 runs; the other procedures on this page converge under `--tags mon` and leave the count where it is. A Grafana upgrade is a reviewed change: the provisioning endpoints the push script calls are marked deprecated upstream. Grafana's login is public, so an advisory that needs no authentication is patched the day it is read, outside the monthly pass. Prometheus's, Loki's and Grafana's packages each restart their own daemon when they are upgraded, so the order of step 3 is what keeps Grafana stopped while the stores restart.

### What to do

1. **Read Grafana's security advisories first**, `https://grafana.com/security/security-advisories/`, against the installed version: `ssh mon dpkg-query -W grafana loki alloy caddy prometheus`.
2. **Read what would move**, on the node: `sudo apt-get update`, then `apt list --upgradable`.
3. **Upgrade the stores with Grafana stopped, then Grafana**, on the node, as one line: `sudo systemctl stop grafana-server && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade loki alloy caddy prometheus && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade grafana && sudo systemctl start grafana-server`. The stores' packages restart them inside the first install, while Grafana is stopped. Grafana's package restarts it at the end of the second, behind its unit's wait for both stores, and the last command starts it when the pass upgraded no Grafana. `--force-confold` keeps the role's file wherever a package ships a changed config, and asks nothing: the package's own `/etc/default/prometheus` would start Prometheus on its 15-day default retention, which deletes the older blocks. A line that stops part-way leaves Grafana stopped: run its remaining commands by hand, the start last.
4. **Re-converge in full**, from the workstation, so the role's files are what the upgraded packages run: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon`, naming no tag. Its preview shows no change to a rendered file; a change there is a package that replaced a config, and the converge puts the role's back. The row it appends to `docs/reference/deploy-log.jsonl` is the record the reminder counts the next month from.
5. **After a Grafana upgrade, run the acceptance reads**: `mon-push` step 1, which re-sends the tree and reads the template back byte-identical and each rule's datasource; then `mon-push` step 3; then, in the node's UI, open one firing rule's Slack message and follow its panel link and its silence link.
6. **Read the reboot flag**, on the node: `ls /run/reboot-required`. `No such file or directory` is no reboot pending; the file listed is one, taken by `zcrypto-mon-reboot-pending` below from its first step. Until the node pages the main channel, that alert reaches the shadow channel alone, and this read is the one that brings a pending reboot to a person.

### Retire when

`infra/ansible/host_vars/zcrypto-mon/vars.yml` no longer sets `base_unattended_upgrades_package_blacklist`, and the base role's unattended-upgrades origins cover the vendors' repositories.

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

The node is one 80 GB disk. Prometheus's blocks are under `/var/lib/prometheus`, capped at 8 GiB; Loki's chunks under `/var/lib/loki`; Grafana's database under `/var/lib/grafana`; the journal under `/var/log/journal`. A full disk stops ingestion first and evaluation after it.

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
3. **Confirm by value:** `uv run python infra/scripts/grafana-query.py --stack mon 'node_reboot_required{host="zcrypto-mon"}'` reads 0 within twenty minutes, and the `Alerts` section of `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` names no rule as unhealthy.

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
3. **Bring it back** by `mon-store-restart` above, which stops Grafana around the restart.
4. **Record the gap.** The minutes Loki was down are minutes with no alert history: note them in the day's journal entry, so a quiet fired-in-window list for that time is not read as a quiet fleet.

### Retire when

`zcrypto-mon-store-down` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-mon-sqlite-locked"></a>

## zcrypto-mon-sqlite-locked — ALERT

### What you are seeing

A **warning** Grafana alert from the node, `Monitor · Grafana's database locked`: Grafana gave up on a write with `database is locked` in the last fifteen minutes. It clears by itself when the window empties and sends no resolved message.

### What it means

Grafana keeps its own state — rules, dashboards, alert instances, silences — in an embedded SQLite database, `/var/lib/grafana/grafana.db`, in WAL mode. A write that finds the database locked sleeps and is retried, and each retry logs `Database locked, sleeping then retrying` at info: those lines are routine, at each start and beside Grafana's own cleanup job, and the rule leaves them out. What it counts is the line logged when the retries ran out and the write failed. While a push runs, which writes each rule in turn, that is a call the push failed on. Lines that keep coming with no push running are the recorded condition for moving Grafana's state to PostgreSQL.

### What to do

1. **Read the lines**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "database is locked" != "sleeping then retrying" [24h]))'`, and on the node `sudo journalctl -u grafana-server --no-pager --since -1h | grep 'database is locked' | grep -vc 'sleeping then retrying'`.
2. **A push was running**: run it again once it has ended, by `mon-push`; the rule clears fifteen minutes after the last line.
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

A **warning** Grafana alert from the node, `Monitor · head series above budget`: Prometheus has held more than 20,000 series in its head for three hours. The Fleet health board's *Monitor — Prometheus head series* panel (907) draws the count against the red line.

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

Prometheus on the node keeps 90 days or 8 GiB, whichever is reached first, and the cap is sized so that the 90 days are reached first. A deletion by size means the store now holds less than 90 days: the series count or the sample rate outgrew what the cap was sized for. Nothing is lost that a rule reads, since the widest rule window is 27 hours; what shortens is how far back a dashboard can look.

### What to do

1. **Read the store's size and reach**, from the workstation: `uv run python infra/scripts/grafana-query.py --stack mon 'prometheus_tsdb_storage_blocks_bytes{host="zcrypto-mon"}' '(time() - prometheus_tsdb_lowest_timestamp_seconds{host="zcrypto-mon"}) / 86400'`: bytes on disk, and the days the oldest sample reaches back.
2. **Read the series count**: `zcrypto-mon-series-high` above, steps 1 and 2. A count far above the budget is the cause, and is fixed at the shipper.
3. **The count is right and the cap is small**: take `mon_prometheus_retention_size` in `infra/ansible/roles/mon/defaults/main.yml` to the owner; the disk's free space is `df -h /` on the node. A changed value reaches the node by `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`, whose handler restarts Prometheus with Grafana stopped around it.

### Retire when

`zcrypto-mon-retention-by-size` is absent from `infra/grafana/alerts.yaml`.
````

`infra/runbooks/observability.md` — replace the text below, which is part of a longer line whose rest stays

```markdown
have theirs at `cache.md#zcrypto-alloy-dark-cache-1`, since their set is watched from the other two nodes while one is dark.)
```

with

```markdown
have theirs at `cache.md#zcrypto-alloy-dark-cache-1`, since their set is watched from the other two nodes while one is dark. The observability node's own sibling, `zcrypto-alloy-dark-mon`, is evaluated on that node and nowhere else, and has its section at `mon.md#zcrypto-alloy-dark-mon`.)
```

- [ ] **Step 6: The fleet page**

`docs/reference/fleet.md` — after

```markdown
| cache node timers | zcrypto-valkey1 to 3 | `zcrypto-reboot-check` (15-min) and `zcrypto-clock-offset` (5-min), copies of the capture hosts' | `.prom` into `/var/lib/zcrypto-node-textfile`, read by the node's Alloy |
```

insert

```markdown
| `grafana-server`, `prometheus`, `loki` | zcrypto-mon | apt packages under systemd; Grafana's SQLite under `/var/lib/grafana`, Prometheus's blocks under `/var/lib/prometheus`, Loki's chunks under `/var/lib/loki`, 90 days each | loopback: `127.0.0.1:3000`, `:9090`, `:3100` |
| Caddy (ingest and UI edge) | zcrypto-mon | `/etc/caddy/Caddyfile`; ACME certs under `/var/lib/caddy`; `/api/v1/write` and `/loki/api/v1/push` behind basic auth, `/metrics`, `/metrics/*` and `/swagger*` 404, the rest to Grafana | `:443` at `zcrypto-mon.zhaow.me`; nothing on `:80` |
| `alloy` (native) | zcrypto-mon | the node's own metrics and journals, written unfiltered to its own stores on loopback; scrape jobs `grafana`, `prometheus`, `loki` beside host and self | self-metrics `127.0.0.1:12345` |
| mon node timers | zcrypto-mon | `zcrypto-reboot-check` (15-min, a copy of the capture hosts') and `zcrypto-mon-selfcheck` (5-min: reads Grafana's scheduler, a fleet sample and Loki, and pings the node's dead-man once one is minted) | `reboot.prom` into `/var/lib/zcrypto-node-textfile`; the self-check's verdict in its journal |
```

`docs/reference/fleet.md` — after

```markdown
- The cache nodes ship under `host="zcrypto-valkey1"` to `"zcrypto-valkey3"`, shown as `Cache 1` to `Cache 3` in Slack and on the Logs board; their Valkey and Sentinel series carry `job="valkey"` and `job="sentinel"`, their log lines `container` `valkey`, `sentinel`, `alloy` and `zcache-probe`, and `zcache_wireguard_handshake_age_seconds`, which the engine host ships too, a `peer` label holding the far end's mesh address.
```

insert

```markdown
- The observability node ships to its own stores and to no other, under `host="zcrypto-mon"`, shown as `Monitor` in Slack: that host value exists on the node's Grafana and not on Grafana Cloud. Its Grafana, Prometheus and Loki series carry `job` `grafana`, `prometheus` and `loki`, and its log lines the unit's name as `container`: `grafana-server`, `prometheus`, `loki`, `caddy`, `alloy`, `zcrypto-mon-selfcheck`, `zcrypto-reboot-check`.
```

- [ ] **Step 7: Run the tests and the runbook instruments**

```bash
uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_ops_daily.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_fleet_contracts.py tests/test_guidance_guard.py -q -p no:cacheprovider
for entry in runbook-sections-without-a-trigger runbook-sections-without-a-retire-when runbook-universals-without-a-count; do infra/scripts/count-list.sh "$entry"; done
```

Expected: no failure; each of the three count lines ends `0`.

- [ ] **Step 8: The consumers, the commit gate and the commit**

```bash
uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_fleet_contracts.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_refs_resolve.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_message_citations.py tests/test_merge_gate.py tests/test_grafana_push_sh.py tests/test_infra_alloy_series.py tests/test_infra_alloy_stages.py tests/test_infra_grafana_keepalive.py tests/test_infra_unattended_upgrades.py tests/test_infra_mon_role.py tests/test_engine_soak.py tests/test_engine_metrics.py tests/test_engine_journal_prune.py tests/test_engine_execgate.py tests/test_prose_chars.py -q -p no:cacheprovider
```

Expected: no failure (`2472 passed, 4 skipped` on the tree this plan was written against).

Run: `uv run pre-commit run -a`

Expected: every hook Passed; `mdformat` owns `infra/runbooks/mon.md` and may re-space it once: re-run until clean, then stage what it rewrote.

```bash
git add infra/grafana/alerts.yaml infra/grafana/fleet-health-dashboard.json infra/runbooks/mon.md \
  infra/runbooks/observability.md infra/scripts/ops_daily.py docs/reference/fleet.md tests/test_infra_alert_rules.py \
  tests/test_ops_daily.py
git commit -F- <<'MSG'
feat(alerts): the zcrypto-mon rule group, its runbook page and its Fleet health row

The observability node carries a rule group of its own, evaluated on the node alone: the push
leaves it out of Grafana Cloud, where the node has no series. Eight rules, each with its section in
`infra/runbooks/mon.md` and its panel in a new row of the Fleet health board: the node's own Alloy
dark (below one scrape target for 10 m); the root filesystem under 15% free for 30 m; a reboot
pending for 15 m, the capture rule's bar and duration; a store down or not ready, fewer than two
for 3 m, Loki counted only while its ingester is active; a write Grafana gave up on with
`database is locked`, a burst rule on the `logs` receiver whose selector leaves out the retry lines
Grafana logs with the same text at each start; ingest dark, no fleet series for 5 m, half the
per-host Alloy-dark rules' wait so it pages ahead of them when the node's edge fails; head series
above 20,000 for 3 h; and a block deleted by the size cap in the last 6 h. Each rule but
ingest-dark selects the node and nothing else, and no rule outside the group carries a `host`
matcher that admits it.

The runbook page carries five procedures beside the eight alert sections: pushing to the node,
generating or replacing one of its vaulted secrets, re-minting the tools' token, restarting a store
by hand with Grafana stopped around it, and the monthly patch pass over the packages the node does
not upgrade by itself. The pass upgrades the stores with Grafana stopped and Grafana after them,
since the stores' packages and Grafana's each restart their own daemon, keeps the role's config
files, and reads the reboot flag, which reaches no one's channel until the node pages the main
one. The daily pass maps seven of the uids to the node; ingest-dark pins no one host. The fleet
page gains the node's four Services rows and its Telemetry labels.

The patch pass has a trigger: the daily pass's reminders gain `mon patch pass`, due a month after
the node's last full converge in the deploy log, the row the pass's own re-converge leaves.

Cases: the group's eight rules against their sections and panels; the push default against the
group's two dead-men; a rule reading the node exactly when it is in the group; ingest-dark ahead of
every per-host Alloy-dark rule and of the exposure rule; the store rule's count and its dark-Alloy
arm; the two budget fences; the database-lock rule against the journal the node's Alloy ships; the
reboot rule held to the capture rule's; the reminder's three dates against a log that also holds a
tagged converge, a failed one, another host's and a bootstrap, and a log with no full converge of
the node owing nothing.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 9: Prove the guards with sixteen probes, then record their verdicts by a message-only amend**

Every probe runs from the worktree root on the committed tree, one at a time; the rule file's suite takes about half a minute a run. The controls: a node rule's dashboard uid moved off the Fleet health board; a node rule moved out of the group; a rule's runbook anchor deleted; a panel id changed; another host's `_UID_HOST` entry deleted; the refdata reminder's runbook anchor changed. The mutations move each threshold, duration, receiver, group and filter this task chose, widen a fleet rule's matcher to a regex that admits the node, change the board's bar and query, and let a tagged or a failed converge count as a patch pass:

```bash
RULES="uv run pytest tests/test_infra_alert_rules.py -q -p no:cacheprovider"
NODE="uv run pytest tests/test_infra_alert_rules.py::test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group -q -p no:cacheprovider"
COVER="uv run pytest tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider"
UIDS="uv run pytest tests/test_ops_daily.py::test_the_uid_map_is_every_rule_that_pins_one_host_and_can_fire_with_no_host_label -q -p no:cacheprovider"
DUE="uv run pytest tests/test_ops_daily.py::test_the_mon_patch_pass_is_due_a_month_after_the_nodes_last_full_converge tests/test_ops_daily.py::test_a_deploy_log_with_no_full_converge_of_the_node_owes_no_patch_pass tests/test_ops_daily.py::test_the_refdata_reminder_is_computed_from_the_register_and_the_monthly_cadence -q -p no:cacheprovider"
A=infra/grafana/alerts.yaml
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-ingest-dark$/,/^      receiver: metrics$/s/^    for: 5m$/    for: 10m/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-series-high$/,/^      receiver: metrics$/s/params: \[20000\]/params: [30000]/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-store-down$/,/^      receiver: metrics$/s/params: \[2\]/params: [1]/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-sqlite-locked$/,/^      receiver: logs$/s/^      receiver: logs$/      receiver: metrics/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-reboot-pending$/,/^      receiver: metrics$/s/^    ruleGroup: zcrypto-mon$/    ruleGroup: zcrypto-fleet/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-retention-by-size$/,/^      receiver: metrics$/s/\[6h\]/[1h]/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-reboot-pending$/,/^      receiver: metrics$/s/^    for: 15m$/    for: 5m/' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-store-down$/,/^      receiver: metrics$/s/ and on() (up{host="zcrypto-mon", job="integrations\/unix"} == 1)$//' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/zcrypto-fleet/zcrypto-cache/' \
  --mutation '/^  - uid: zcrypto-mon-sqlite-locked$/,/^      receiver: logs$/s/ != "sleeping then retrying"//' -- $RULES
infra/scripts/mutate-probe.sh --file $A \
  --control '/^  - uid: zcrypto-mon-disk-low$/,/^      receiver: metrics$/s/^    ruleGroup: zcrypto-mon$/    ruleGroup: zcrypto-fleet/' \
  --mutation 's/^            count(up{host="nas"}) or on() vector(0)$/            count(up{host=~"nas|zcrypto-.*"}) or on() vector(0)/' -- $NODE
infra/scripts/mutate-probe.sh --file infra/runbooks/mon.md \
  --control '/^<a name="zcrypto-mon-disk-low"><\/a>$/d' \
  --mutation 's/^<a name="zcrypto-mon-ingest-dark"><\/a>$/<a name="zcrypto-mon-ingest"><\/a>/' -- $RULES
infra/scripts/mutate-probe.sh --file infra/grafana/fleet-health-dashboard.json \
  --control 's/^      "id": 901,$/      "id": 911,/' \
  --mutation 's/^                "value": 20000$/                "value": 25000/' -- $COVER
infra/scripts/mutate-probe.sh --file infra/grafana/fleet-health-dashboard.json \
  --control 's/^      "id": 901,$/      "id": 911,/' \
  --mutation 's/"expr": "prometheus_tsdb_head_series{host=\\"zcrypto-mon\\"}"/"expr": "prometheus_tsdb_head_chunks{host=\\"zcrypto-mon\\"}"/' -- $COVER
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control '/^    "zcrypto-alloy-dark-cache-3": "zcrypto-valkey3",$/d' \
  --mutation '/^    "zcrypto-mon-store-down": "zcrypto-mon",$/d' -- $UIDS
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^REFDATA_RUNBOOK = "infra\/runbooks\/reference-data.md#refdata-sweep-due"$/REFDATA_RUNBOOK = "infra\/runbooks\/reference-data.md#refdata-sweep"/' \
  --mutation 's/ and not row.get("tags") and not row.get("skip_tags")$//' -- $DUE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^REFDATA_RUNBOOK = "infra\/runbooks\/reference-data.md#refdata-sweep-due"$/REFDATA_RUNBOOK = "infra\/runbooks\/reference-data.md#refdata-sweep"/' \
  --mutation 's/ and row.get("rc") == 0:$/:/' -- $DUE
```

Expected: each of the sixteen runs ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message, by `git commit --amend -F-` with the whole message of Step 8 re-supplied and nothing else changed, with:

```
Probe: `infra/scripts/mutate-probe.sh`, sixteen runs, each KILLED with its control proven.
`infra/grafana/alerts.yaml`, control a node rule's dashboard moved off the Fleet health board:
ingest-dark's wait doubled to the per-host rules', KILLED, control proven; the series bar raised,
KILLED, control proven; the store rule's bar lowered to one, KILLED, control proven; the
database-lock rule moved to the `metrics` receiver, KILLED, control proven; the reboot rule moved
out of the group, KILLED, control proven; the retention window shortened, KILLED, control proven;
the reboot rule's wait shortened, KILLED, control proven; the store rule's dark-Alloy arm dropped,
KILLED, control proven; the retry filter dropped from the database-lock rule, KILLED, control
proven; and, control a node rule moved out of the group, over the group-membership case: a fleet
rule's matcher widened to a regex that admits the node, KILLED, control proven.
`infra/runbooks/mon.md`, control a rule's anchor deleted: ingest-dark's anchor renamed, KILLED,
control proven. The Fleet health board, control a panel id changed: the series panel's bar moved
off the rule's, KILLED, control proven; its query changed, KILLED, control proven.
`infra/scripts/ops_daily.py`, control another host's entry deleted: the store rule's entry deleted,
KILLED, control proven; and, control the refdata reminder's anchor changed, over the reminder
cases: a tagged converge counted as a pass, KILLED, control proven; a failed converge counted as
one, KILLED, control proven.
```

Run: `git status --porcelain` — Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` — Expected: `0`.

---

### Task 8: The push skill leaves the skipped group's rules and the node's dashboard row to the node

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md` (one sentence in Step 1, one in Step 3)

**Interfaces:**
- Consumes: Task 6's `GRAFANA_SKIP_RULE_GROUPS`; Task 5's `--stack mon`; Task 7's rule group, its row `Observability node` and `infra/runbooks/mon.md#mon-push`.
- Produces: a push skill whose preflight and verify step a push to Grafana Cloud passes with the node's group and row in the tree.

**What this task decides:**
- The edit lands on this branch and not with phase 2's two-stack wording. From this branch's merge the rule file carries the eight `zcrypto-mon` rules and the Fleet health board the node's row. The skill's Step 1 holds a push on `(no series)` for a rule the push adds, and its Step 3 fails a new rule or panel on `(no series)`; on Grafana Cloud the node's series read `(no series)` by construction, since no converge makes that stack hold them. Unchanged, the skill would hold or fail each push to the stack that pages, on readings that are correct.
- Two sentences, in the skill's body. The body is outside the always-loaded set, so the commit owes no `Ambient grows by` line. Each push of the dual period going to both stacks, the skill's two-stack wording, stays phase 2's (spec D18).
- The commit is a `claude` commit carrying the one file, and `zcrypto-refine-rules` is loaded before the edit, as for every skill file. No guard changes, so the commit records no probe verdict.

- [ ] **Step 1: Load `zcrypto-refine-rules`**

Load the skill and read its *Before you write guidance*. The two sentences land on its first ground: the push script skips the group and refuses to send it to Grafana Cloud (Task 6), and the first sentence names the variable.

- [ ] **Step 2: The two sentences**

`.claude/skills/zcrypto-grafana-push/SKILL.md` — replace the text below, which is part of a longer line whose rest stays

```markdown
returns a value and fires the rule.
```

with

```markdown
returns a value and fires the rule. A rule of a group the push skips (`GRAFANA_SKIP_RULE_GROUPS`, by default the observability node's `zcrypto-mon`) is not sent by this push and is not read here: it is read on the stack that takes it, with `--stack mon`, by `infra/runbooks/mon.md#mon-push`.
```

`.claude/skills/zcrypto-grafana-push/SKILL.md` — replace the text below, which is part of a longer line whose rest stays

```markdown
`(no series)` is a fail, not a zero.
```

with

```markdown
`(no series)` is a fail, not a zero. A rule the push skipped, and a panel of the Fleet health board's `Observability node` row, read the node's own series, which Grafana Cloud does not hold: `(no series)` is their reading here, and they are read by value with `--stack mon`, by `infra/runbooks/mon.md#mon-push`.
```

- [ ] **Step 3: The consumers**

```bash
uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_internal_terms_not_operator_visible.py tests/test_merge_gate.py tests/test_count_list.py tests/test_grafana_push_sh.py tests/test_staged_kind_check.py tests/test_message_citations.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 4: The commit gate and the commit**

Run: `uv run pre-commit run -a`

Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

```bash
git add .claude/skills/zcrypto-grafana-push/SKILL.md
git commit -F- <<'MSG'
claude(skills): grafana-push leaves a skipped group's rules and the node's dashboard row to the node

The rule file now carries the observability node's `zcrypto-mon` group and the Fleet health board
its `Observability node` row. A push to Grafana Cloud skips the group, and that stack holds none of
the node's series. The skill's preflight holds a push on `(no series)` for a rule the push adds,
and its verify step fails a new rule or panel on `(no series)`: unchanged, both would hold or fail
each push to the stack that pages, on readings that are correct. Step 1 now leaves a skipped
group's rules out of the preflight, and Step 3 reads them and the node's row on the node, with
`--stack mon`, by `infra/runbooks/mon.md#mon-push`.

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

Run: `git status --porcelain`

Expected: empty.

- [ ] **Step 5: The branch reads clean**

```bash
git status --porcelain
uv run python infra/scripts/message-citations.py --range develop..HEAD
for entry in probe-verdicts-without-the-script operator-term-surfaces prose-chars; do infra/scripts/count-list.sh "$entry"; done
```

Expected: an empty status; no citation refused; the `probe-verdicts-without-the-script` line ends `0`; the other two lines carry the numbers the pull request's body quotes.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches the node, the Linode Cloud Manager, DNS, Slack, GitHub, Grafana Cloud or the node's Grafana, or writes a secret. Phase P runs on this branch before its pull request opens, so the code and its secrets merge together; phase R runs from merged `develop`. `W$` is the workstation at the repository root, `H$` a shell on the node, reached as `ssh mon` once R4 has written the alias. Every converge goes through `infra/ansible/scripts/converge.sh`, which previews, asks for the typed `--limit` and appends its line to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`. A port is opened in two layers, each by its own hand: the nftables rules the firewall role renders from the vars Task 1 commits, and the Linode Cloud Firewall, edited in the Cloud Manager. No secret is typed on a command line or shown: the vault values are generated by a script that prints none of them, the webhook is read without echo, and a token or password reaches the process that presents it through its environment or its stdin, from `vault_var` inside a command substitution.

**The Kraken maintenance read is not owed for this node, and neither is the engine's gap.** `.claude/rules/fleet-deploys.md` binds the read to the venue-facing hosts, `zcrypto`, `zcrypto-red` and `zcrypto-ops`, where the `capture`, `engine` and `ops` roles run. `zcrypto-mon` runs none of them and speaks to no venue (the spec's invariant); Task 1 enters it in `NO_VENUE_EXPOSURE`, the set `infra/scripts/count-list.sh converges-inside-a-kraken-window` leaves out, and `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` holds that none of its vars or its role names the venue. No step below converges or restarts `zcrypto`, `zcrypto-red` or `zcrypto-ops`, so no step falls under the engine's inter-cycle gap or the capture pair's hour; the daily report R9 runs takes its two read-only ssh reads, of `zcrypto` and of ops, whichever stack it is given.

**P1. The deploy keypair** (Task 1 operator step O0), run by the owner before Task 1's Step 1; Task 1's Step 11 commits the two files.

**P2. The seven vault values, generated by script, none shown.** Run by the owner once Task 8's Step 5 has read the branch clean, with no executor step running and the GPG agent unlocked: the two files it writes make a task's clean-tree check and each `mutate-probe.sh` run refuse, and a commit made between a task's commit and its message-only amend would take that amend's message. The admin login's name is `u` and 16 hex digits; the admin password, the secret key and the two ingest passwords are 48 hex characters each; each ingest password's bcrypt hash is made beside it, at cost 10, so a hash and its password cannot disagree. Five values go to a new `infra/ansible/host_vars/zcrypto-mon/vault.yml` and the two passwords are appended to `infra/ansible/group_vars/observed/vault.yml`, where phase 2's shippers read them; the script refuses to run a second time, since the values are stable across rebuilds of the node.

```bash
(cd infra/ansible && uv run --with bcrypt python - <<'PY'
import pathlib
import secrets
import subprocess

import bcrypt


def entry(name: str, value: str) -> str:
    done = subprocess.run(
        ["ansible-vault", "encrypt_string", "--stdin-name", name], input=value, capture_output=True, text=True, check=True
    )
    return done.stdout.rstrip() + "\n"


node = pathlib.Path("host_vars/zcrypto-mon/vault.yml")
fleet = pathlib.Path("group_vars/observed/vault.yml")
assert not node.exists(), f"{node} exists: these values are generated once, and a second run would orphan the first"
assert "mon_ingest_" not in fleet.read_text(), f"{fleet} already carries an ingest password"
passwords = {user: secrets.token_hex(24) for user in ("fleet", "logship")}
node.write_text(
    "# host_vars/zcrypto-mon -- SECRETS for the observability node (spec 00121). Per-VALUE vault encryption: the\n"
    "# variable NAMES stay readable, every value stays `!vault`-encrypted at rest. Generated once, by script, and\n"
    "# stable across rebuilds of the node: Grafana takes its admin's name from this file when it creates its\n"
    "# database, the role resets the admin password from it, and the two hashes are the bcrypt hashes of the\n"
    "# ingest passwords in group_vars/observed/vault.yml, which the fleet's shippers present. Replacing one:\n"
    "# infra/runbooks/mon.md's mon-secrets.\n"
    "#\n"
    "# NEVER run `ansible-inventory --host/--list` from infra/ansible/: ansible.cfg supplies the vault\n"
    "# password, so both silently print every value below in cleartext.\n"
    "\n"
    + entry("mon_grafana_admin_user", "u" + secrets.token_hex(8))
    + entry("mon_grafana_admin_password", secrets.token_hex(24))
    + entry("mon_grafana_secret_key", secrets.token_hex(24))
    + "".join(
        entry(f"mon_ingest_{user}_password_hash", bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode())
        for user, password in passwords.items()
    )
)
with fleet.open("a") as out:
    out.write(
        "\n"
        "# The observability node's two ingest users (spec 00121): `fleet` is every Alloy's, on both ingest paths;\n"
        "# `logship` is the applications' own log push, on the Loki path alone, so it can be revoked without\n"
        "# blinding fleet telemetry. Caddy on the node holds their bcrypt hashes, host_vars/zcrypto-mon/vault.yml's\n"
        "# `mon_ingest_<user>_password_hash`: a password and its hash are replaced together (infra/runbooks/mon.md's\n"
        "# mon-secrets).\n"
        + "".join(entry(f"mon_ingest_{user}_password", password) for user, password in passwords.items())
    )
print(f"wrote {node} (5 values) and appended 2 values to {fleet}; nothing was printed")
PY
)
```

Expected: `wrote host_vars/zcrypto-mon/vault.yml (5 values) and appended 2 values to group_vars/observed/vault.yml; nothing was printed`. Then the check, which prints booleans alone:

```bash
uv run --with bcrypt python - <<'PY'
import re
import sys

import bcrypt

sys.path.insert(0, "infra/scripts")
from grafana_auth import vault_var

node, fleet = "host_vars/zcrypto-mon/vault.yml", "group_vars/observed/vault.yml"
print("mon_grafana_admin_user u and 16 hex digits:", bool(re.fullmatch(r"u[0-9a-f]{16}", vault_var("mon_grafana_admin_user", node))))
for name in ("mon_grafana_admin_password", "mon_grafana_secret_key"):
    print(name, "48 hex characters:", bool(re.fullmatch(r"[0-9a-f]{48}", vault_var(name, node))))
for user in ("fleet", "logship"):
    password, hashed = vault_var(f"mon_ingest_{user}_password", fleet), vault_var(f"mon_ingest_{user}_password_hash", node)
    print(user, "48 hex characters:", bool(re.fullmatch(r"[0-9a-f]{48}", password)), "hash is its own:", bcrypt.checkpw(password.encode(), hashed.encode()))
PY
git status --porcelain
```

Expected: five lines, each `True` throughout (`mon_grafana_admin_user u and 16 hex digits: True`, `mon_grafana_admin_password 48 hex characters: True`, the same for `mon_grafana_secret_key`, and `fleet 48 hex characters: True hash is its own: True` with its sibling for `logship`); the status names the new file and the appended one and nothing else. Commit the two files as `chore(mon): the observability node's seven vaulted values, generated by script`, with the trailer of `## Global Constraints`.

**P3. The shadow Slack webhook.** The owner creates the shadow channel and an incoming webhook for it in Slack, then vaults the URL as `slack_shadow_webhook_url` beside `slack_webhook_url`. The URL is read from the terminal without echo and goes into `ansible-vault` on stdin; the three `sed` expressions keep the file's own account of its values true: its two counts, and the paragraph that names the one value no host and no file-path reader takes, which gains its sibling.

```bash
cd infra/ansible
sed -i -e 's/^# MIXED CUSTODY — do not read this file as workstation-only\. Ten of the fifteen values ARE$/# MIXED CUSTODY — do not read this file as workstation-only. Ten of the sixteen values ARE/' \
  -e 's/^# The other five never reach a host\. Four are read from the WORKSTATION BY FILE PATH:$/# The other six never reach a host. Four are read from the WORKSTATION BY FILE PATH:/' \
  -e 's/^# `slack_webhook_url` is the odd one: NOTHING in production reads it from this file\. It is vaulted$/# `slack_webhook_url` is the odd one, `slack_shadow_webhook_url` at the end of this file its sibling: NOTHING in production reads it from this file. It is vaulted/' group_vars/all/vault.yml
grep -c -e 'Ten of the sixteen values' -e 'The other six never reach a host' -e 'at the end of this file its sibling' group_vars/all/vault.yml
bash -c 'set -euo pipefail
read -rs -p "shadow webhook URL (not echoed): " hook < /dev/tty; echo > /dev/tty
entry=$(printf %s "$hook" | uv run ansible-vault encrypt_string --stdin-name slack_shadow_webhook_url)
{
  printf "\n# The shadow Slack channel'"'"'s incoming-webhook URL (spec 00121), minted and vaulted by the owner. The\n"
  printf "# observability node'"'"'s two contact points are minted with it: it reaches grafana-push.sh through the\n"
  printf "# environment as GRAFANA_SLACK_WEBHOOK_URL, as slack_webhook_url does (infra/runbooks/mon.md'"'"'s mon-push),\n"
  printf "# and nothing in production reads it from this file. Treat as a credential.\n"
  printf "%s\n" "$entry"
} >> group_vars/all/vault.yml'
uv run python -c 'import sys; sys.path.insert(0, "../scripts"); from grafana_auth import vault_var; v = vault_var("slack_shadow_webhook_url"); print("a Slack webhook:", v.startswith("https://hooks.slack.com/services/"), "no newline:", v == v.strip())'
```

Expected: `3`, the prompt, then `a Slack webhook: True no newline: True`. `cd ../..` back to the repository root, and commit `infra/ansible/group_vars/all/vault.yml` as `chore(vault): the shadow channel's webhook, for the observability node's contact points`, with the trailer.

Then the pull request opens through the `open-pr` skill, a different agent reads the branch, and `merge-pr` merges it. Everything below runs from merged `develop`.

**R0. The operands, read once.**

```
W$ git switch develop && git pull --ff-only && git status --porcelain
W$ CAP=$(mktemp -d) && echo "$CAP"
W$ infra/scripts/count-list.sh converges-inside-a-kraken-window | tee "$CAP/kraken-window-count"
W$ ls ~/.config/zcrypto/ 2>/dev/null
```

`git status --porcelain` prints nothing (a dirty tree is recorded as `dirty` on every deploy-log line). `CAP` holds what R10's commit message quotes, and the count line R10 compares its own against. The listing shows no `grafana-mon.vault.yml` before the first converge; one left by an earlier build of the node is harmless, since its token is refused and the converge mints again.

**R1. The Linode, its Backups and its two records, by hand.** In the Cloud Manager: a Linode `g6-standard-2` (4 GB, 2 vCPU, 80 GB), Debian 13, in a region apart from the engine host's, label `zcrypto-mon`, the owner's master key as root's, Backups enabled at creation. At the DNS host of `zhaow.me`: an A record and an AAAA record for `zcrypto-mon`, the node's two public addresses.

```
W$ A=$(dig +short A zcrypto-mon.zhaow.me) && AAAA=$(dig +short AAAA zcrypto-mon.zhaow.me) && echo "$A $AAAA"
W$ dig +short CAA zcrypto-mon.zhaow.me; dig +short CAA zhaow.me
```

The two addresses are the ones the Cloud Manager shows. The CAA read, the name's own set and then its parent's, which applies while the name has none: no `issue` tag, or one that admits `letsencrypt.org`, Caddy's issuer. An `issuewild` tag governs wildcard names and not this one, so the parent's `0 issuewild "comodoca.com"` standing alone is a pass. An `issue` tag naming other authorities alone stops the certificate at R3: give the name its own set, as `zaccess.zhaow.me` has, never a wider one at the parent.

**R2. The node's Cloud Firewall, by hand.** In the Cloud Manager: a firewall `zcrypto-mon`, inbound policy Drop, outbound policy Accept; inbound rules Accept TCP `22`, TCP `10022` and TCP `443`, each for IPv4 and IPv6 from all sources, and Accept ICMP for both; attached to the node. Nothing about the owner's home address enters a rule. Port 80 takes no rule.

```
W$ for a in "$A" "$AAAA"; do for p in 22 80 443 10022; do timeout 5 bash -c "</dev/tcp/$a/$p" 2>/dev/null && echo "$a $p open" || echo "$a $p closed"; done; done
```

Expected, on each address: `22 open` and the other three `closed`, nothing listening on them yet. A workstation with no IPv6 route reads every port of the second address `closed`: take that half of this read, and of R3's and R5's, from a cache node (`ssh db1`), which has one.

**R3. Bootstrap, the alias, then the preview and the converge** (Tasks 1 to 4). First the host key's fingerprint, read out of band once in the node's LISH console: `H$ ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. It is what the alias's first prompt, on port 10022 below, is checked against. The bootstrap's own connection, as root on port 22, checks no host key: `infra/ansible/ansible.cfg` sets `host_key_checking = False` for each Ansible connection of the fleet. Then, with the owner's master key in the agent (`W$ ssh-add -l` lists it), the GPG agent unlocked, and not through `run.sh`, whose throwaway agent excludes the master key:

```
W$ (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-mon -e ansible_user=root -e ansible_port=22)
W$ (cd infra/ansible && umask 077 && uv run ansible-vault view files/deploy_zcrypto-mon_ed25519 > "$HOME/.ssh/deploy_zcrypto-mon_ed25519")
W$ ssh mon 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'
```

Between the second line and the third, the `Host mon` stanza of `infra/external-systems.md`'s SSH config block is copied verbatim into `~/.ssh/config`; `IdentitiesOnly yes` is load-bearing, since the hardened sshd allows two authentication tries. The bootstrap's recap reads `failed=0 unreachable=0`, its primary refusal `skipping` and its re-bootstrap probe finding no `zcrypto-deploy`; the re-bootstrap refusal firing means the node was provisioned before: stop and read it, never pass `-e rebootstrap=true` on a node this runsheet has not first rebuilt. The first `ssh mon` prints the fingerprint read in LISH, then the provider-assigned hostname and `sudo-ok`. Then the converge, which names no tag because every role of the node's play is wanted:

```
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon
```

The preview is the first proof the spec owes: on a node with none of the packages its recap reads `failed=0`, with the two repositories and the rendered files `changed`, and with the origin check, the installs of `grafana`, `loki`, `alloy` and `caddy`, every unit start, the timers and `the tools' service account and its one token` reading `skipping`. A preview that fails stops here: the failing task is a preview guard this plan's Review Focus names, fixed on a branch that merges before R3 is run again, never worked around by converging without the preview. After the typed limit, the real pass's recap reads `failed=0 unreachable=0`. A real pass that fails after it rendered a store's config has lost that store's queued restart, and the next pass renders nothing and queues none: once a pass has succeeded, and before R4, restart both stores by `infra/runbooks/mon.md`'s `mon-store-restart`. Its token tasks show nothing but their names (`no_log`); a pass that stops at `refuse to go on when the vaulted password is still refused` met the login lockout and is re-run after five minutes with no sign-in in between. Then:

```
W$ ssh mon hostname
W$ stat -c '%a %s' ~/.config/zcrypto/grafana-mon.vault.yml && grep -c '^mon_grafana_tools_token: !vault' ~/.config/zcrypto/grafana-mon.vault.yml
W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon
W$ for a in "$A" "$AAAA"; do for p in 22 80 443 10022; do timeout 5 bash -c "</dev/tcp/$a/$p" 2>/dev/null && echo "$a $p open" || echo "$a $p closed"; done; done
```

`zcrypto-mon`; `600` with a non-zero size, and `1`; the second converge's real pass reads `changed=0 failed=0`, the cached token kept and nothing re-rendered (a task that reads `changed` there is a finding: its fix is a branch whose pull request is opened before R10's, and R10's message names that pull request by number); the ports read `443 open` and `10022 open`, `22 closed` (the hardening role removed the bootstrap drop-in) and `80 closed`, on both addresses. Then remove the TCP `22` rule from the `zcrypto-mon` firewall in the Cloud Manager and run the port read again: the same reading.

**R4. The node, read on the node** (Tasks 1, 2 and 4).

```
W$ ssh mon "sudo ss -ltnH | awk '{print \$4}' | grep -vE '^(127\.[0-9.]+|\[::1\]):' | sort -u"
W$ ssh mon "sudo ss -ltnH | awk '{print \$4}' | grep -E '^(127\.[0-9.]+|\[::1\]):' | sort -u"
W$ ssh mon sudo nft list chain inet filter input
W$ ssh mon 'curl -fsS http://127.0.0.1:9090/api/v1/targets | python3 -c "import json, sys; print(len(json.load(sys.stdin)[\"data\"][\"activeTargets\"]))"'
W$ ssh mon 'systemctl is-active grafana-server prometheus loki'
W$ ssh mon 'systemctl is-active caddy alloy zcrypto-mon-selfcheck.timer'
W$ ssh mon 'systemctl is-enabled grafana-server prometheus loki caddy alloy'
W$ ssh mon 'systemctl show grafana-server -p After --value' | tr ' ' '\n' | grep -cE '^(prometheus|loki)\.service$'
W$ ssh mon 'apt-config dump | grep Package-Blacklist'
W$ ssh mon "curl -fsS http://127.0.0.1:2019/config/ | grep -o '\"hash_cache\"' | wc -l"
W$ ssh mon "caddy list-modules | grep -cE '^(http\.authentication\.providers\.http_basic|http\.authentication\.hashes\.bcrypt|tls\.issuance\.acme)\$'"
W$ ssh mon 'cat /var/lib/zcrypto-node-textfile/reboot.prom'
W$ ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck -n 1 --no-pager -o cat'
W$ ssh mon 'sudo ls /var/lib/grafana/plugins 2>/dev/null | wc -l'
W$ ssh mon dpkg-query -W grafana loki alloy caddy prometheus
```

In order. The public listeners are three lines, `*:443`, `0.0.0.0:10022` and `[::]:10022`: Caddy's one socket for both families and sshd's two, since the hardening role lists both addresses for it. A fourth line is a stop. The loopback ones are 3000, 9090, 3100 with Loki's gRPC 9096, 12345 and Caddy's admin 2019. The chain accepts `10022` and `443` and names no other port. Prometheus has `0` scrape targets, the receiver alone. Six `active` lines, then five `enabled` ones: a unit that is started and not enabled is gone at the first reboot. `2`. A line reading `Unattended-Upgrade::Package-Blacklist:: "prometheus$";`, the rendered block as apt parses it. `2`, one `hash_cache` per ingest path, so the bcrypt cost is paid once per shipper after a Caddy reload. `3`, the cloudsmith build carrying the three modules the Caddyfile uses. A `node_reboot_required` line reading 0, or 1 when the first patches want a reboot, in which case the node is rebooted by hand now, before anything depends on it. The self-check's line reads `selfcheck: rules=FAIL (…) fleet=FAIL (…) loki=ok (…) -> not pinging`: no rule is pushed yet and no fleet host ships. No line there, or a unit that failed with `Failed to load environment files`, is a stop before R8: it is systemd unable to read the root-only file for a unit under a dynamic user, which this read is the first to prove. `0`, no plugin downloaded: the preinstaller is off, and the two datasources' plugins are the package's own under `/var/lib/grafana/plugins-bundled`, which R9's `unhealthy=[]` shows loaded. The five versions go into R10's message, and Grafana's is read against the fix version of each advisory the spec's measured basis lists (`https://grafana.com/security/security-advisories/`: CVE-2026-42127, CVE-2026-8609, CVE-2026-27880, CVE-2026-33382 and CVE-2026-21720, which need no authentication, then CVE-2026-42129, CVE-2025-3454, CVE-2026-21724, CVE-2025-12141, CVE-2026-13719, CVE-2026-33380 and CVE-2026-27876); an installed version below the fix of one that needs no authentication stops the rollout with `ssh mon sudo systemctl stop caddy` until the package carries it.

**R5. The edge, read from outside** (Task 2).

```
W$ curl -4 -sS -o /dev/null -w '%{http_code} %{ssl_verify_result} %{remote_ip}\n' https://zcrypto-mon.zhaow.me/api/health
W$ curl -6 -sS -o /dev/null -w '%{http_code} %{ssl_verify_result} %{remote_ip}\n' https://zcrypto-mon.zhaow.me/api/health
W$ curl -sS https://zcrypto-mon.zhaow.me/api/health
W$ curl -sSv -o /dev/null https://zcrypto-mon.zhaow.me/api/health 2>&1 | grep -E 'issuer:|subject:'
W$ for p in /metrics /metrics/plugins/prometheus /swagger /swagger-ui /api/v1/write /loki/api/v1/push; do printf '%s ' "$p"; curl -sS -o /dev/null -w '%{http_code}\n' "https://zcrypto-mon.zhaow.me$p"; done
W$ curl -sS -o /dev/null -w '%{http_code}\n' -u probe:probe https://zcrypto-mon.zhaow.me/api/org
W$ for n in 1 2 3 4 5 6; do curl -sS -o /dev/null -w '%{http_code} ' -H 'Content-Type: application/json' -d '{"user":"admin","password":"probe"}' https://zcrypto-mon.zhaow.me/login; done; echo
W$ uv run python -c 'import json, sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; node = "host_vars/zcrypto-mon/vault.yml"; print(json.dumps({"user": vault_var("mon_grafana_admin_user", node), "password": vault_var("mon_grafana_admin_password", node)}))' | curl -sS -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d @- https://zcrypto-mon.zhaow.me/login
```

`200 0` and the node's IPv4 address; `200 0` and its IPv6 address, which is the certificate issued over 443 alone and verified on both families; a health body with `"database": "ok"` and no `version` key; the subject `zcrypto-mon.zhaow.me` and a Let's Encrypt issuer; `/metrics 404`, `/metrics/plugins/prometheus 404`, `/swagger 404`, `/swagger-ui 404`, `/api/v1/write 401`, `/loki/api/v1/push 401`; `401` for `Authorization: Basic` on an API path, which Grafana refuses because basic auth is off; six `401` for the default admin name; and then `200` for the vaulted name and password, which is the lockout left open: Grafana locks an account by its name, and six refused sign-ins under a name that is not the admin's lock nothing the role or the owner signs in with. A certificate not yet issued shows as a TLS error on the first line: `ssh mon 'sudo journalctl -u caddy -n 30 --no-pager'` names the ACME failure, and the two usual ones are R1's CAA set and a missing 443 rule in R2.

**R6. Both ingest paths, through the edge** (Tasks 2 and 3; the seam phases 2 and 3 use). The application shipper's own handler pushes one line as `logship`, and `logship` is then refused on the metrics path:

```
W$ MON_LOGSHIP_PASSWORD="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("mon_ingest_logship_password", "group_vars/observed/vault.yml"))')" uv run python - <<'PY'
import logging
import os
import time

from cli.logging.ship import LokiShipHandler, ShipConfig

handler = LokiShipHandler(
    ShipConfig(
        url="https://zcrypto-mon.zhaow.me/loki/api/v1/push",
        username="logship",
        password=os.environ["MON_LOGSHIP_PASSWORD"],
        host="acceptance",
        service="logship",
    )
)
log = logging.getLogger("zcrypto.acceptance")
log.setLevel(logging.INFO)
log.addHandler(handler)
log.info("the application log shipper's JSON push, through the node's edge")
time.sleep(3)
handler.close()
print("shipped", handler.shipped_lines_total, "dropped", handler.dropped_total)
PY
W$ uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print("user = \"logship:" + vault_var("mon_ingest_logship_password", "group_vars/observed/vault.yml") + "\"")' | curl -sS -K - -o /dev/null -w '%{http_code}\n' -X POST https://zcrypto-mon.zhaow.me/api/v1/write
```

`shipped 1 dropped 0`, the JSON push accepted through Caddy's basic auth; then `401`. Alloy's push as `fleet`, on both paths, from a one-off Alloy on the node that goes out to the public name and back in through the edge, shipping one `up` series and one log line under `host="acceptance"`:

```
W$ ssh mon 'mkdir -p /tmp/mon-accept && cat > /tmp/mon-accept/accept.alloy' <<'EOF'
prometheus.exporter.self "accept" {}

discovery.relabel "accept" {
  targets = prometheus.exporter.self.accept.targets

  rule {
    target_label = "job"
    replacement  = "acceptance"
  }
}

prometheus.scrape "accept" {
  targets         = discovery.relabel.accept.output
  forward_to      = [prometheus.remote_write.edge.receiver]
  scrape_interval = "15s"
}

prometheus.remote_write "edge" {
  external_labels = {
    host = "acceptance",
  }

  endpoint {
    url = "https://zcrypto-mon.zhaow.me/api/v1/write"

    basic_auth {
      username = "fleet"
      password = sys.env("MON_ACCEPT_PASSWORD")
    }

    write_relabel_config {
      source_labels = ["__name__"]
      regex         = "up"
      action        = "keep"
    }
  }
}

loki.source.file "accept" {
  targets       = [{"__path__" = "/tmp/mon-accept/line.log", "host" = "acceptance", "container" = "alloy"}]
  forward_to    = [loki.write.edge.receiver]
  tail_from_end = false
}

loki.write "edge" {
  endpoint {
    url = "https://zcrypto-mon.zhaow.me/loki/api/v1/push"

    basic_auth {
      username = "fleet"
      password = sys.env("MON_ACCEPT_PASSWORD")
    }
  }
}
EOF
W$ ssh mon alloy validate /tmp/mon-accept/accept.alloy && echo valid
W$ uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("mon_ingest_fleet_password", "group_vars/observed/vault.yml"))' | ssh mon 'read -r MON_ACCEPT_PASSWORD && export MON_ACCEPT_PASSWORD && echo "acceptance $(date -u +%FT%TZ)" > /tmp/mon-accept/line.log && timeout 90 alloy run --disable-reporting --server.http.listen-addr=127.0.0.1:12346 --storage.path=/tmp/mon-accept/store /tmp/mon-accept/accept.alloy > /tmp/mon-accept/alloy.log 2>&1; grep -ciE "level=(error|warn)" /tmp/mon-accept/alloy.log; true'
W$ uv run python infra/scripts/grafana-query.py --stack mon 'count by (__name__, job) ({host="acceptance"})'
W$ uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (container) (count_over_time({host="acceptance"}[30m]))'
W$ ssh mon rm -rf /tmp/mon-accept
```

`valid`; `0` warning or error lines after the ninety seconds; one series, `up` under `job="acceptance"`, the write filter of the one-off config keeping nothing else; two series, `alloy` and `logship`, 1 each. The two `--stack mon` reads are also the first use of the token the converge minted. `(no series)` on either is a fail, never a zero: the Alloy log names a 401 (the `fleet` hash and password disagree, P2's check) or a TLS error (R5).

**R7. Memory and the head, read before anything is pushed** (Task 4; the spec's unmeasured items).

```
W$ uv run python infra/scripts/grafana-query.py --stack mon 'count by (job) (up{host="zcrypto-mon"})' 'process_resident_memory_bytes{host="zcrypto-mon"}' 'prometheus_tsdb_head_series{host="zcrypto-mon"}'
W$ ssh mon 'for u in grafana-server prometheus loki alloy caddy; do printf "%s " $u; systemctl show $u -p MemoryCurrent --value; done; free -m | sed -n 2p'
```

Five jobs, `integrations/unix`, `integrations/self`, `grafana`, `prometheus` and `loki`, 1 each; one resident-memory series per process that exports it, Loki's and Prometheus's among them; one head-series value. All three readings go into R10's message. The head-series value is the node's own unfiltered contribution with no fleet host shipping: it is what `## What this plan asks of the spec` asks the spec to add to its sizing, and a value above 12,000 goes to the owner before phase 2 is planned, since the fleet's 9,400 to 10,600 land on top of it against a 20,000 bar.

**R8. The first push, to the shadow channel** (Tasks 5 to 7). A workstation command under `.claude/skills/zcrypto-grafana-push/SKILL.md`'s Step 2, its conditions on where a push runs from, from merged `develop`. The skill's Step 1 preflight and Step 3 render are written for a push to Grafana Cloud and are not this push's: on a node no host ships to yet, each fleet rule reads `(no series)` by design, and R9 is this push's verification. It is `infra/runbooks/mon.md`'s `mon-push` with its step 2, the webhook, because this push mints the node's two contact points:

```
W$ git switch develop && git pull --ff-only && git status --porcelain
W$ GRAFANA_URL=https://zcrypto-mon.zhaow.me GRAFANA_SKIP_RULE_GROUPS= \
     GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_shadow_webhook_url"))')" \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; s = g.stack("mon"); print(g.vault_var(s.token_var, s.vault_file))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
```

Its first line reads `grafana-push: stack=https://zcrypto-mon.zhaow.me prom=grafanacloud-prom loki=grafanacloud-logs folder=bfrxdfoybx98gb skip-groups=<none>`; it prints no `skipping` line, upserts 114 rules, reads the template back byte-identical and every rule's datasource, and reports no orphan. A first line naming `zcrypto2026.grafana.net` means `GRAFANA_URL` did not reach the script: stop, nothing was sent to the node. With `GRAFANA_SKIP_RULE_GROUPS` empty beside it, the script refused that push before any call; had neither variable reached it, Grafana Cloud took its ordinary push, without the node's group.

**R9. The acceptance reads** (the spec's phase-1 proofs). The token is held in the shell for these reads and unset after them.

```
W$ MON_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; s = g.stack("mon"); print(g.vault_var(s.token_var, s.vault_file))')"
W$ rules() { printf 'Authorization: Bearer %s\n' "$MON_TOKEN" | curl -fsS -H @- https://zcrypto-mon.zhaow.me/api/prometheus/grafana/api/v1/rules; }
W$ rules | jq -r '[.data.groups[] | {interval, n: (.rules | length), bad: [.rules[] | select(.health != "ok") | .name]}] | "groups=\(length) rules=\(map(.n) | add) intervals=\(map(.interval) | unique) unhealthy=\(map(.bad) | add)"'
W$ rules | jq -r '[.data.groups[].rules[] | (.alerts // [])[] | .state] | group_by(.) | map("\(.[0])=\(length)") | join("  ")'
W$ for p in policies mute-timings; do printf 'Authorization: Bearer %s\n' "$MON_TOKEN" | curl -fsS -H @- "https://zcrypto-mon.zhaow.me/api/v1/provisioning/$p" | jq -cS . > "$CAP/mon-$p.json"; uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print("Authorization: Bearer " + vault_var("grafana_sa_token"))' | curl -fsS -H @- "https://zcrypto2026.grafana.net/api/v1/provisioning/$p" | jq -cS . > "$CAP/cloud-$p.json"; cmp "$CAP/mon-$p.json" "$CAP/cloud-$p.json" && echo "$p equal: $(cat "$CAP/mon-$p.json")"; done
W$ printf 'Authorization: Bearer %s\n' "$MON_TOKEN" | curl -fsS -H @- https://zcrypto-mon.zhaow.me/api/v1/ngalert | jq -c .
W$ uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host="zcrypto-mon"}) or on() vector(0)' 'node_filesystem_avail_bytes{host="zcrypto-mon", mountpoint="/"} / node_filesystem_size_bytes{host="zcrypto-mon", mountpoint="/"}' 'node_reboot_required{host="zcrypto-mon"}' 'count(up{host!="zcrypto-mon"}) or on() vector(0)' 'prometheus_tsdb_head_series{host="zcrypto-mon"}' 'increase(prometheus_tsdb_size_retentions_total{host="zcrypto-mon"}[6h])'
W$ uv run python infra/scripts/grafana-query.py --stack mon '(count((up{host="zcrypto-mon", job="prometheus"} == 1) or ((up{host="zcrypto-mon", job="loki"} == 1) and on(host) (loki_ring_members{host="zcrypto-mon", name="ingester", state="ACTIVE"} == 1))) or on() vector(0)) and on() (up{host="zcrypto-mon", job="integrations/unix"} == 1)'
W$ uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (container) (count_over_time({host="zcrypto-mon"}[24h]))'
W$ uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum(count_over_time({host="zcrypto-mon", container="grafana-server"} |= "database is locked" != "sleeping then retrying" [15m])) or on() vector(0)'
W$ rules | jq -r '.data.groups[] | select(.name == "zcrypto-mon") | .rules[] | "\(.uid) \(.state) \(.health)"'
W$ uv run python infra/scripts/ops-daily.py report --stack mon --since 1h
W$ ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck -n 1 --no-pager -o cat'
```

In order, ten minutes or more after the push, so each rule has evaluated and `zcrypto-mon-ingest-dark` is past its five minutes. `groups=10 rules=114 intervals=[60] unhealthy=[]`: every rule `health=ok` and every group at 60 s, the interval the push never sets. A state count that carries `Alerting (NoData)` beside `Normal`, `Normal (NoData)` and `Alerting`: the NoData firing, since the fleet's dead-men have no series on a node no host ships to yet, and the shadow channel holds their messages. `policies equal:` followed by the tree `{"group_by":["grafana_folder","alertname"],"receiver":"metrics"}` and `mute-timings equal: []`, the stack-held settings the same on both stacks (the Grafana Cloud reads are GETs). `{"alertmanagersChoice":"internal","numExternalAlertmanagers":0}`. Then each of the node's eight rules by value, which is the verification Task 7's thresholds were marked for: 5; one series above 0.9; one series, 0; 0, which is `zcrypto-mon-ingest-dark` on the firing side of its bar by design until phase 2; the head-series value R7 read, under 20,000; 0; then 2 for the stores. `(no series)` on any of them is a fail. Then the node's own log streams by unit, a row for `grafana-server` with a count above 0 and rows for the other units that logged in the day, `prometheus`, `loki`, `caddy` and `alloy` among them when the converge fell inside it: the database-lock rule ends in a fallback that reads 0 whether or not Grafana's journal reaches Loki, so this row, and not that 0, is what shows the rule has its input. `(no series)` here, or no `grafana-server` row, is a fail. Then 0 for the database-lock count. Of the group's eight lines seven read `inactive ok` and `zcrypto-mon-ingest-dark` reads `firing ok`. The daily report's `Alerts` section lists what fired in the hour, read from the node's history in Loki, with no line saying the alert read was unreadable: that is the history-read proof. Its other sections report the fleet's hosts absent, which is true of this stack until phase 2. The self-check's line now reads `rules=ok (…) fleet=FAIL (…) loki=ok (…) -> not pinging`.

Then the store stop, Prometheus for about three minutes with Grafana running, which the spec's invariant allows in this acceptance and nowhere else:

```
W$ ssh -n mon 'sudo systemctl stop prometheus && sleep 180 && sudo systemctl start prometheus' &
W$ sleep 120; rules | jq -r '.data.groups[].rules[] | select(.uid == "zcrypto-capture-all-streams-silent" or .uid == "zcrypto-capture-stream-silent") | "\(.uid) \([(.alerts // [])[].state] | unique)"'
W$ wait
W$ rules | jq -r '[.data.groups[].rules[] | select(.health != "ok")] | length'
```

The stop runs in the background of the one shell that holds `rules` and `MON_TOKEN`, a second terminal having neither, and the second line reads two minutes into it: both rules read `["Normal (Error)"]`, the two whose error state is OK. During the stop the shadow channel takes error pages carrying the template's error block. `wait` returns when Prometheus is started again; within three minutes of that the last line reads `0`, and the `metrics` receiver's resolves arrive in the channel. Then Loki for about six minutes, which shows the node's own store rule by value, the `logs` receiver's silence on resolve and the history gap the runbook states:

```
W$ ssh -n mon 'sudo systemctl stop loki && sleep 360 && sudo systemctl start loki' &
W$ sleep 330; rules | jq -r '.data.groups[] | select(.name == "zcrypto-mon") | .rules[] | select(.uid == "zcrypto-mon-store-down") | "\(.uid) \(.state)"'
W$ wait
W$ ssh mon "sudo journalctl -u grafana-server --since -15min --no-pager | grep -c 'Failed to save alert state history'"
W$ rules | jq -r '[.data.groups[].rules[] | select(.health != "ok")] | length'
W$ unset MON_TOKEN; unset -f rules
```

Five and a half minutes into the stop, `zcrypto-mon-store-down firing`: its message is in the shadow channel, and so are error pages from the six rules on the `logs` receiver. The rule waits 3 m after the first evaluation that sees Loki's failed scrape, each of the two up to a minute after the stop, so it fires between three and five minutes in, and a read at four would find it `pending` as often as not. After the start the store rule's resolve arrives, sent by `metrics`, and none arrives for the six, `logs` sending no resolves. The journal count is above 0, the transitions of those minutes that no history holds, which `infra/runbooks/mon.md` says of a Loki outage; the unhealthy count returns to `0`.

Last, the one step with a person in it. The owner signs in at `https://zcrypto-mon.zhaow.me/login` with the vaulted name and password, each pasted, never typed: `uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var(sys.argv[1], "host_vars/zcrypto-mon/vault.yml"), end="")' mon_grafana_admin_user | wl-copy` (or `xclip -selection clipboard`) for the name, the same line with `mon_grafana_admin_password` for the password, and the clipboard cleared afterwards. A run of failed sign-ins under that name locks the account for about five minutes and the converge's own sign-in counts against the same lock, so no converge runs while this is tried, and one refused paste is a stop, not a retry. Signed in, the owner opens one of the store stop's messages in the shadow channel and follows its three links: the panel, the rule and the silence form each open under `https://zcrypto-mon.zhaow.me/`, none under `localhost`; the silence form is closed without saving. Under Administration, the service accounts list shows `zcrypto-tools`, Editor, with one token, and no other account.

**R10. The records: one pull request** (the `open-pr` skill; a different agent reads it; `merge-pr` merges it). From `develop`, carrying the deploy-log lines the two converges appended:

```
W$ git switch develop && git pull --ff-only && git switch -c chore/mon-node-records
W$ git status --porcelain
W$ infra/scripts/count-list.sh converges-inside-a-kraken-window | diff "$CAP/kraken-window-count" -
W$ uv run pytest tests/test_deploy_log.py tests/test_deploy_log_audit.py tests/test_fleet_contracts.py -q -p no:cacheprovider
W$ uv run pre-commit run -a
W$ git add docs/reference/deploy-log.jsonl docs/reference/fleet.md
```

The status names `docs/reference/deploy-log.jsonl`; `diff` prints nothing, the count being the one R0 kept, the node's rows outside its set; the tests pass. `docs/reference/fleet.md` is re-trued where the node read differently from what Tasks 1 and 7 wrote (the region, a port, a unit name). The commit is `chore(fleet): the observability node runs Grafana, Prometheus, Loki and Caddy and takes a shadow push of every rule`, its message carrying R4's five versions and the advisory read, R5's two address lines, R6's two acceptances, R7's memory and head-series readings, and R9's reads and the two store stops, with the trailer of `## Global Constraints`. The node takes no `docs/reference/fleet-pins.md` row and no pruner entry: its packages are followed from apt.

## Resolution

The branch delivers phase 1 of the spec: the node's place in the fleet, the `mon` role, the stack table, the push's skip list, the node's rule group, runbook page and dashboard row, in Tasks 1 to 7, and the two sentences that let the push skill's checks pass a Grafana Cloud push with the node's group in the tree, in Task 8. Once `## Rollout (attended)` has run, `zcrypto-mon` evaluates every rule of the tree against its own stores and pages a shadow channel; no fleet host ships to it, Grafana Cloud is what it was, and rolling back is deleting the Linode, the role staying inert (spec D25).

Two of the spec's open questions are settled here. The series the self-check reads as "rule evaluation is fresh" is `grafana_alerting_ticker_last_consumed_tick_timestamp_seconds` within 60 s, beside `grafana_alerting_schedule_alert_rules` at 1 or more (Task 4). The thresholds and `for` of the node's eight rules are Task 7's list, each read by value at R9. The items the spec left unmeasured and assigned to this phase's first converge are read in the Rollout: the deb's first start under the role and certificate issuance over 443 alone (R3, R5), the cloudsmith Caddy's module set (R4), both ingest paths through Caddy's basic auth (R6), Loki's and Prometheus's memory (R7), and the installed Grafana's version against each listed advisory's fix (R4).

It does not deliver phases 2 to 4, each a plan of its own under this serial. Phase 2's plan takes from this one: the `fleet` and `logship` passwords in `group_vars/observed/vault.yml` for the shippers' `MON_*` names; `grafana_auth.STACKS` for `infra/scripts/grafana-compare.py`; `mon_selfcheck_healthcheck_url` for the minted healthchecks.io check; the self-check's fleet read and `zcrypto-mon-ingest-dark`, both of which turn healthy at the first shipping host; and R7's head-series reading for its sizing. The push skill's two-stack wording, the exposure page's "read ingest-dark first" step and the `prometheus` blacklist's review are named where they fall: phase 2's first dual push, phase 3's cutover, whose change list in the spec names `infra/runbooks/engine.md` for the step, and the store-restart drill. From R3's first converge the daily pass's reminders carry `mon patch pass`, which is what brings the node's monthly pass, and its read of the reboot flag, to a person while the node pages the shadow channel alone. T0217 stays open until the phase that delivers its solution merges; `docs/reference/fleet.md` is re-trued twice, by Tasks 1 and 7 on this branch and by R10's records pull request where the node read differently.

## What this plan asks of the spec

The plan itself changes no line of the spec. The spec was amended for each item below, the first seven when this plan was committed, and the fifth and sixth again with the six after them when its review was folded, except the second, which stays the owner's call once R7 has read the real figure and is carried in the spec's open questions; none blocks a task.

- D7's pattern ended `$`, which under Ansible's `match`, Python's, also matches before a trailing newline, the one shape D7's first correction exists to refuse. It now ends `\Z`, as the role's does.
- D10's sizing and D16's series bar count the fleet and not the node. The node's own Alloy ships unfiltered too: Grafana's, Loki's and Prometheus's own `/metrics`, Alloy's and the host's came to between 9,700 and 10,300 series on the workstation's loopback (Grafana 5,819, Loki 2,277, Prometheus 591, Alloy 544, the host 458 on 24 cores, fewer on the node's two). With the fleet's 9,400 to 10,600 on top, the expected head is near 20,000, which is D16's bar, described there as "about twice the expected count", and the margin under the 8 GiB cap shrinks from three or four times to under two. R7 reads the real figure. The choices are the owner's: raise the bar and re-state the sizing, or thin the node's self-scrape at its source, which is the one endpoint the "never filtered" invariant was not written about.
- D7 said a token is re-minted when "refused by `/api/user`". For a service-account token that endpoint answers 200 with `id: 0`, so the role compares its `login` with the service account's, and D7's list now names another account's token as a mint condition.
- The phase-1 change list omitted files the phase must change, each for a guard that already exists, and now names them: `infra/external-systems.md` (the ssh stanza a test holds to the inventory), `infra/ansible/files/README.md`, `infra/scripts/count-list.sh`, `tests/test_infra_converge_guards.py`, `tests/test_pins_converged.py`, `tests/test_reboot_check.py`, `tests/test_ops_daily_soak.py`, `infra/runbooks/observability.md`. It named `tests/test_fleet_contracts.py`, which needs no edit and is gone from it: that file reads `docs/reference/fleet.md` and passes over the new rows.
- "Proofs each phase owes" listed one store stop and "a resolve on `metrics` and none on `logs`". No rule on the `logs` receiver reads Prometheus, so a Prometheus stop cannot show the second half; R9 stops Loki a second time, inside the same acceptance the invariant exempts, which also reads `zcrypto-mon-store-down` by value, and the spec lists that stop, at about six minutes since the review: the rule fires three to five minutes in, and a five-minute stop left no moment at which its `firing` was certain to be read.
- D18 left the push skill untouched until phase 2's first dual push, and the phase-1 list named no skill edit. From this branch's merge the unchanged skill would hold or fail each Grafana Cloud push on `(no series)` for the node's rules and row, so Task 8 edits its two checks, and D18 and the phase-1 list say so; the skill's two-stack wording stays phase 2's.
- D4's 404s were `/metrics` and `/swagger*`. Grafana also serves its OpenAPI documents at `/public/api-merged.json` and `/public/openapi3.json` without a login; they are static files that describe the API and carry no instance data, and D4 says they stay served.
- D4 refused `/metrics` and left what lies under it: Grafana serves a metrics tree per plugin, `/metrics/plugins/<id>`, without a login. D4 and the phase-1 proofs now name `/metrics/*`.
- D5 and D7 named no admin login, which left Grafana's default. The lockout D2 relies on is by account name, so under the default name a stranger's guesses would keep the role's sign-in and the owner's locked. They now carry a generated name, vaulted beside the password, and "What stays manual" lists it.
- D5 was silent on Grafana's plugin preinstaller, which downloads plugins from grafana.com at each start and replaces the bundled Prometheus and Loki datasources with a newer release. D5 now turns it off, and the measured basis carries the reading.
- D5 and D16 described the database-lock rule as `database is locked` in Grafana's journal. Grafana's ordinary retries log that text at info, so D16's rule is now a write Grafana gave up on.
- D18's invariant, a `zcrypto-mon` rule never pushed to Grafana Cloud, held only while `GRAFANA_SKIP_RULE_GROUPS` was unset. D18 now carries the push's refusal.
- D3 named the monthly patch pass and nothing that starts it, and through phases 1 and 2 the node's pending-reboot rule reaches a channel no one reads. D3 now names the daily pass's reminder and the pass's own read of the reboot flag, and the phase-1 list `infra/scripts/ops_daily.py`'s reminder. The phase-3 list names `infra/runbooks/engine.md`, for the exposure page's first step, which D16 and D20 speak of and no list carried.
