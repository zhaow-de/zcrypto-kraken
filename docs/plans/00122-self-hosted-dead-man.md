# The dead-man service on `zcrypto-hc`: the shared node code extracted, the clone deployed, the fleet cut over — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every dead-man check the fleet relies on runs on the owner's healthchecks.io replacement at `zcrypto-hc.zhaow.me`: the node built by one bootstrap and one converge from a role that shares its edge, its secrets preflight, its reboot check, its self-check pattern and its backup timer with the observability node's role; the twelve checks provisioned by script; every pinger on a slug URL under one vaulted project key; the daily pass, the ops scrape, the watchdog rule and the watchdog timer reading the clone; healthchecks.io retired after the cutover's first clean day, with the engine's check the one that waits for the box to close.

**Architecture:** Seven extraction tasks first, each behaviour-preserving for `zcrypto-mon` and proven by the existing literal tests, a before-and-after render comparison and a probe that fails both roles' tests, then a converge of the node reading `changed=0`; then the node's tasks on the shared code; then the pingers' and readers' tasks; then the surfaces. Five pull requests by component, an attended runsheet with the owner's P-steps for what the clone's UI alone mints, three drills, and two records pull requests.

**Tech Stack:** Ansible (ansible-core 2.21; the `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `mon`, `ops`, `capture`, `engine`, `nas` roles and the new `edge`, `node_common` and `hc` roles), Docker Compose on `zcrypto-hc`, the clone's image `ghcr.io/zhaow-de/healthchecks` (Python 3.14, Django 6.1, uWSGI, SQLite in WAL mode), Caddy from the cloudsmith repository, Grafana Alloy from `apt.grafana.com`, Prometheus and Loki on the observability node, pytest, `infra/scripts/mutate-probe.sh`, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00122-self-hosted-dead-man-design.md`, every decision; its open questions are answered in the review before Task 1, and their answers are written into the spec's table. The 00121 counterparts each task copies from are named in its Files.

## Global Constraints

- The host is `zcrypto-hc` (`zcrypto-hc.zhaow.me`, an A and an AAAA record), inventory group `hc_host`, a child of `observed`; the admin user `zcrypto-deploy` on port 10022; its play runs `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `edge` and `hc`, the last two under the tag `hc` (spec D1, D2).
- The service is one container, `zcrypto-hc`, pinned by digest through `-e hc_image_digest=sha256:<64 hex>` with a `docs/reference/fleet-pins.md` row; the role refuses a malformed or unpulled digest and a running digest the pins file does not record unless `pins_override` names a reason; the container binds `127.0.0.1:8000` and Caddy is the one public listener on 443 (spec D2, D3).
- The `mon` role's three rendered files that move to shared code — its Caddyfile, its reboot-check unit and its self-check unit and env file — render byte-identical before and after each extraction, held by `tests/test_infra_mon_role.py`, `tests/test_mon_selfcheck.py` and `tests/test_reboot_check.py` with their assertions unchanged and by the comparison each extraction task's Step 5 runs; no `hc` task merges before `zcrypto-mon` has been converged `changed=0` on the shared code (spec D15; the rollout's R-X).
- No ping key, API key, `SECRET_KEY`, SMTP credential or password appears on a command line, in a log, a diff, a plan step or a tracked file in clear: every UI-minted value enters the vault through `infra/scripts/vault-append-secret.sh`, every generated one through the P2 script, and each reaches a host through a `no_log` render with `diff: false` alone. No executor decrypts, prints or generates a vault value; `ansible-inventory --host`, `--list` and `--graph --vars` are never run; no container's environment is printed by any form, a recreate being proven by `.State.StartedAt` moving (spec's invariants).
- The read-only key is one vault value, `hc_readonly_api_key` in `group_vars/observed/vault.yml`, rendered by `roles/ops/templates/alloy-secrets.env.j2` alone and read by the workstation by file path; the read-write key, `hc_readwrite_api_key` in `group_vars/all/vault.yml`, never reaches a host (spec D6, D7).
- The ping URLs are rendered from `hc_ping_base` and the slug equal to the check's name; no template changes its variable name; the twelve slugs are the fixture's eleven names plus `zcrypto-hc`; no host's URL moves before `hc-provision.py apply` has created its check, since an unknown slug answers 404 and creates nothing (spec D4, D6, D17).
- The cutover's order is the spec's D5: ops, the node, the NAS, `zcrypto-red`, then `zcrypto` an hour later in the attended form `--skip-tags engine -e converge_primary=true -e capture_image_digest=<running>`, the Kraken feed `https://status.kraken.com/api/v2/scheduled-maintenances.json` read whole, never through `head` or `tail`, at planning and immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`; the engine's converge after the box alone, `--tags engine` inside the inter-cycle gap; no step converges the engine inside the box: [[ROLLOUT: the box's closing date, 2026-11-01 or a week later — the earliest the engine's move may run]] (`.claude/rules/fleet-deploys.md`; `infra/runbooks/engine-procedures.md#engine-rung-2-box`).
- Until retirement no healthchecks.io check is deleted and no vault value removed; retirement comes after the after-box sitting's first clean day (spec D14).
- A rule of the `zcrypto-hc` group is never pushed to Grafana Cloud: `grafana-push.sh`'s default skip names both node-only groups and its refusal reads both (spec D12).
- No file under `infra/ansible/group_vars/hc_host/`, `host_vars/zcrypto-hc/`, `roles/hc/`, `roles/edge/` or `roles/node_common/` carries the word the venue's name spells: `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds` walks them.
- No executor step reaches a host, a venue, Grafana Cloud, the node's Grafana, the clone, Slack, healthchecks.io, AWS, the Linode Cloud Manager or DNS; every such step is an operator step, marked attended, `W$` the workstation and `H$` the host. `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No operator-read surface (the runbook pages, the drill procedures, the rule file's text, the dashboard, the check descriptions, the Slack template) carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; a provenance token goes in an adjacent code comment.
- A comment or docstring stays only where a reader would do something differently without it; an event goes to the commit message; a count of another file's contents appears only where a test holds it.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean, the placeholder line `PROBE_VERDICT` replaced; the branch is unpushed while the tasks run.
- Every commit is green over the changed files' consumers, the tests each task's consumer step names; never the full suite locally. A task that edits a page under `infra/runbooks/` also runs `tests/test_internal_terms_not_operator_visible.py`, `tests/test_runbook_internal_tokens.py` and `tests/test_runbook_triggers.py`.
- The commit gate before every commit: the commit's files staged by path, new files among them, then `uv run pre-commit run -a` clean, a run that rewrites files re-run until clean and the rewrites staged.
- A new Markdown paragraph or list item is one line; a universal word in a new runbook bullet carries its `(set: …; count: …)` or `(no count command: …)` clause or the bullet is worded without it. `zcrypto-refine-rules` is loaded before each edit to a skill file or a top-level page under `infra/runbooks/`.
- Task 16 alone edits files under `.claude/`, the two skills `zcrypto-daily-ops` and `zcrypto-rollout-image`, in a `claude` commit carrying no other file; no task edits `CLAUDE.md`.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- New, shared: `infra/ansible/roles/edge/` (`defaults/main.yml`, `tasks/main.yml`, `handlers/main.yml`, `templates/Caddyfile.j2`); `infra/ansible/roles/node_common/` (`defaults/main.yml`, `tasks/secrets-preflight.yml`, `tasks/reboot-check.yml`, `tasks/selfcheck.yml`, `tasks/sqlite-backup.yml`, `files/zcrypto-reboot-check.sh`, `files/zcrypto-reboot-check.timer`, `templates/zcrypto-reboot-check.service.j2`, `files/zcrypto_selfcheck.py`, `templates/selfcheck.service.j2`, `templates/selfcheck.env.j2`, `templates/selfcheck.timer.j2`, `files/zcrypto-sqlite-backup.sh`, `templates/sqlite-backup.service.j2`, `templates/sqlite-backup.timer.j2`); `tests/role_render.py`, `tests/selfcheck_driver.py`, `tests/test_infra_edge_role.py`, `tests/test_infra_node_common.py`; `infra/scripts/vault-append-secret.sh`, `tests/test_vault_append_secret_sh.py` (Tasks 1 to 6).
- Modified by the extraction: `infra/ansible/roles/mon/tasks/main.yml` (the preflight, the Caddy block, the reboot-check and self-check blocks become includes), `roles/mon/handlers/main.yml` (`reload caddy` leaves), `roles/mon/defaults/main.yml` (the include variables), `roles/mon/files/zcrypto-mon-selfcheck.py` (imports the shared module), the removed `roles/mon/templates/Caddyfile.j2`, `files/zcrypto-reboot-check.*`, `templates/zcrypto-reboot-check.service.j2`, `files/zcrypto-mon-selfcheck.timer`, `templates/zcrypto-mon-selfcheck.{env,service}.j2`; `tests/test_infra_mon_role.py`, `tests/test_mon_selfcheck.py`, `tests/test_reboot_check.py`; `infra/scripts/grafana-push.sh`, `tests/test_grafana_push_sh.py`, `tests/test_infra_alert_rules.py`; `infra/scripts/ops_daily.py`'s reminder table, `tests/test_ops_daily.py`; `infra/scripts/count-list.sh`, `tests/test_count_list.py` (Tasks 1 to 7).
- The node: `infra/ansible/inventory/hosts.yml`, `site.yml`, `bootstrap.yml`, `scripts/converge.sh`, `scripts/run.sh`, `files/README.md`, `files/deploy_zcrypto-hc_ed25519{,.pub}`, `group_vars/hc_host/vars.yml`, `host_vars/zcrypto-hc/vars.yml` (and `vault.yml` from P2); `infra/scripts/deploy-log-audit.py`, `ops_daily.py`'s aliases and sets, `infra/external-systems.md`, `docs/reference/fleet.md`, `infra/grafana/notification-templates/zcrypto-slack.tmpl` (Task 8); `infra/ansible/roles/hc/` (`defaults/main.yml`, `tasks/main.yml`, `tasks/admin.yml`, `handlers/main.yml`, `templates/compose.yaml.j2`, `templates/hc.env.j2`, `templates/zcrypto-hc.service.j2`, `templates/alloy-env.j2`, `files/config.alloy`, `files/zcrypto-hc-selfcheck.py`), `tests/test_infra_hc_role.py`, `tests/test_hc_selfcheck.py` (Tasks 9, 10).
- The pingers and readers: `infra/scripts/hc-provision.py`, `tests/test_hc_provision.py` (Task 11); `group_vars/observed/vars.yml` and `vault.yml`, `group_vars/all/vault.yml`, `group_vars/capture_host/vars.yml`, `group_vars/engine_host/vars.yml`, `host_vars/zcrypto-red/vars.yml`, `host_vars/nas/vars.yml`, `host_vars/zcrypto-ops/vars.yml`, `host_vars/zcrypto-mon/vars.yml`, `host_vars/zcrypto-hc/vars.yml`, the preflights' ping-URL shapes, `tests/test_logging_redact.py`, `ops_daily.py`'s `_curl_is_read` (Task 12); `ops_daily.py`'s `DEADMAN_API` and `_readonly_key`, `roles/ops/files/config.alloy`, `roles/ops/templates/alloy-secrets.env.j2`, `infra/grafana/alerts.yaml`'s watchdog text, `fleet-health-dashboard.json`'s two titles, `tests/test_infra_alloy_series.py`, `tests/test_ops_daily.py` (Task 13).
- The surfaces: `infra/grafana/alerts.yaml`'s `zcrypto-hc` group, `fleet-health-dashboard.json`'s row, `infra/runbooks/hc.md`, `tests/test_infra_alert_rules.py`, `tests/test_dashboards_cover_metrics.py` (Task 14); `infra/runbooks/drills-telemetry.md`, `observability.md`, the 116-line sweep's pages, `docs/open-topics/T0085-final-pre-golive-steps.md` (Task 15); `.claude/skills/zcrypto-daily-ops/SKILL.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md` (Task 16).
- `tests/fixtures/healthchecks_descriptions.json`, `docs/reference/deploy-log.jsonl`, `drill-log.md`, `fleet-pins.md`, `fleet.md`, `docs/open-topics/T0218-self-hosted-dead-man-service.md`, the spec's measured basis: the rollout's records pull requests, not a task's.

## Review Focus

- A rendered file of the live node moved by an extraction: the Caddyfile's routes, the self-check unit's `Environment=` lines and its env file's one name, the reboot-check unit's one variable — each is held by literal in the existing tests and by the before-and-after comparison of Tasks 2 to 4's Step 5, and a probe on the shared file must fail the `mon` test and the `hc` or `edge` test alike.
- A secret reaching the clone's host or the tree in clear: `hc.env` rendered `no_log` with `diff: false` at `0600`, the admin task forwarding two names from its own environment and never on a command line, `vault-append-secret.sh` refusing a value that fails its shape before `ansible-vault` runs and writing with `printf %s`, the self-check and the provisioning script printing hostnames and never a key — Tasks 6, 9, 10 and 11's cases.
- A ping URL rendered before its check exists, or a slug that is not its check's name: the twelve slugs held equal to the fixture's names plus `zcrypto-hc`, every preflight holding a URL to the clone's shape, and the rollout's order creating the checks before any host moves — Tasks 11 and 12 and R9.
- The read-only key in two names, or rendered by a second role: `hc-readonly-key-in-a-role` re-pointed, the ops template's two lines held by literal, the daily pass reading the observed vault by file path — Tasks 7 and 13.
- A converge or an induction outside its bounds: the engine inside the box, a venue-facing host inside a Kraken window, the primary un-tagged, the capture pair inside an hour of each other, a drill on anything but `zcrypto-hc` — Task 15 and the Rollout.

---

### Task 1: The shared test helpers — `tests/role_render.py` and `tests/selfcheck_driver.py`, extracted from the node's two tests with their assertions unchanged

**Files:**
- Create: `tests/role_render.py` (`variables(role_dir, secrets, exclude=(), **extra)`, `render(role_dir, name, secrets, **extra)`, the Caddyfile parsers `blocks(lines)`, `site(caddyfile, hostname)`, `users(handle)`, `upstream(handle)`, and `assert_preflight(task, secrets, override, refused)`; copied from `tests/test_infra_mon_role.py`'s `_variables`, `_render`, `_blocks`, `_site`, `_users`, `_upstream` and the body of `test_a_missing_or_misshapen_secret_is_refused_by_its_key`)
- Create: `tests/selfcheck_driver.py` (`load(script_path, shared_path=None)` compiling a script, and the shared module first when given, from text into module objects with no bytecode cache; `Response`; `run(module, env, bodies, *, broken=(), refused=None, now)` returning `(rc, asked, out)`; copied from `tests/test_mon_selfcheck.py`'s `_Response`, `_run` and the module-from-text loading)
- Modify: `tests/test_infra_mon_role.py` (imports the helpers; every assertion unchanged; `SECRETS` stays the test's)
- Modify: `tests/test_mon_selfcheck.py` (imports the driver; every case unchanged)

**Interfaces:**
- Consumes: `tests/test_infra_converge_guards.py`'s `load_tasks`, `find_task`, `assert_that`, `truthy`, `set_facts`, `when_conditions`, reused as they are; Ansible's `Templar`, `DataLoader`, `trust_as_template`.
- Produces, for Tasks 2 to 4, 9 and 10 by these names: `role_render.render`, `role_render.site`, `role_render.users`, `role_render.upstream`, `role_render.assert_preflight`; `selfcheck_driver.load`, `selfcheck_driver.run`.

**What this task decides:**
- `assert_preflight` takes the preflight task itself, so it drives Task 3's shared task through the including role's variables: it templates the task's fault list over `{**secrets, **override}` with `None` values dropped, holds the list to `[refused]` or `[]`, holds the `that` to the same truth, and holds that no value of the variables appears in the rendered `fail_msg`.
- `selfcheck_driver.load` executes the shared module under the name `zcrypto_selfcheck` in `sys.modules` for the script's import, scoped to the call, so two scripts in one session do not share a stale module.

- [ ] **Step 1: Move the helpers, then run both tests** — `uv run pytest tests/test_infra_mon_role.py tests/test_mon_selfcheck.py -q -p no:cacheprovider`; Expected: the same pass count as at this plan's base, read first.
- [ ] **Step 2: The consumers** — `grep -rl 'test_infra_mon_role\|test_mon_selfcheck\|role_render\|selfcheck_driver' tests/ infra/ .claude/ | sort`, every file it lists, with `tests/test_scripts_have_tests.py` and `tests/test_prose_chars.py`.
- [ ] **Step 3: The commit gate**, then commit — `refactor(tests): the node role's render-and-hold helpers and the self-check driver become shared modules`, with the trailer; no guard changes, so no probe.
- [ ] **Step 4: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The `edge` role — Caddy from the cloudsmith repository and the parametrised Caddyfile, the `mon` role's Caddy block an include, its Caddyfile byte-identical

**Files:**
- Create: `infra/ansible/roles/edge/defaults/main.yml` (`edge_hostname`, `edge_acme_email`, `edge_basic_auth_routes: []`, `edge_paths_404: []`, `edge_head_paths: []`, `edge_session_cookie: ""`, `edge_upstream_port`, `edge_role_name` for the rendered header's "Rendered by the `<role>` role" line)
- Create: `infra/ansible/roles/edge/tasks/main.yml` (the Caddy repository task copied from `roles/mon/tasks/main.yml`'s `add the Caddy apt repository`, the preview fact `edge_repo_previewed`, the install `caddy present — version FOLLOWED from apt, never forced or held`, the preview fact `edge_units_previewed`, the Caddyfile task with `validate`, `no_log` and `diff: false`, `caddy enabled + started` under `not edge_units_previewed`)
- Create: `infra/ansible/roles/edge/handlers/main.yml` (`reload caddy` under `not edge_units_previewed`)
- Create: `infra/ansible/roles/edge/templates/Caddyfile.j2` (the node's Caddyfile with the four parameters rendered in its place: the routes loop, the `404` matcher when `edge_paths_404` is non-empty, the `HEAD` matcher with its comment when `edge_head_paths` is non-empty, the default handle)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the two Caddy tasks and the repository task become `include_role: name: edge` with `vars` — `edge_hostname: "{{ mon_hostname }}"`, the two routes with the ingest users' hashes, `edge_paths_404: [/metrics, /metrics/*, /swagger*]`, `edge_head_paths: [/d/*, /alerting/*]`, `edge_session_cookie: grafana_session`, `edge_upstream_port: "{{ mon_grafana_port }}"`; `mon_repos_previewed` reads `mon_grafana_repo` alone and `mon_units_previewed` drops `mon_caddy_install`)
- Modify: `infra/ansible/roles/mon/handlers/main.yml` (`reload caddy` removed), `roles/mon/defaults/main.yml` (unchanged names; `mon_acme_email` stays and feeds the include)
- Delete: `infra/ansible/roles/mon/templates/Caddyfile.j2`
- Modify: `infra/ansible/site.yml` (the node's play lists `edge` before `mon`, both under the tag `mon`, so `--tags mon` still renders the edge; `tests/test_infra_mon_role.py::test_the_play_runs_the_role_under_its_own_tag_with_no_container_runtime` re-trued to the seven roles)
- Test: `tests/test_infra_edge_role.py` (new: the template rendered through `role_render.render` over the edge defaults with each parameter set, held by `site`, `users` and `upstream`: no routes renders one `handle`; a route renders its users' hashes and its upstream; an empty `404` set renders no matcher; the `HEAD` matcher renders only with paths and carries the cookie name; the repository and install tasks held as `test_no_package_is_forced_held_or_pinned_to_a_version` holds the node's; the two preview facts held as the node's are)
- Test: `tests/test_infra_mon_role.py` (the Caddyfile cases read `role_render.render(EDGE, "Caddyfile.j2", …)` with the include's `vars` taken from the `mon` task through `find_task`, so the test holds what the node renders and not a hand copy; the preview-facts case loses its Caddy columns, which `tests/test_infra_edge_role.py` takes)
- Test: `tests/test_infra_converge_guards.py` (the preview-register case, `test_every_register_a_preview_guard_reads_is_set_in_its_own_role`, widened over the `edge` role)

**Interfaces:**
- Consumes: Task 1's helpers; the node's Caddyfile text at this plan's base, kept in Step 5's comparison; `tests/test_infra_converge_guards.py`.
- Produces, for Task 9: `include_role: name: edge` with the six variables; the `edge_units_previewed` fact the `hc` role's own preview facts read.

**What this task decides:**
- The include's `vars` are evaluated through Ansible's own templar in the test, so `edge_basic_auth_routes` carries `{{ mon_ingest_fleet_password_hash }}` references and the rendered Caddyfile holds the hashes as before.
- The header comment's first line names the including role through `edge_role_name`, so the rendered file's first line stays `# Rendered by the `mon` role at /etc/caddy/Caddyfile — edit …`, re-pointed at the shared template's path; that one path change is the one byte difference Step 5 admits, and the comparison strips the header's comment lines.

The template's parameters, as the `mon` include sets them:

```yaml
edge_hostname: "{{ mon_hostname }}"
edge_acme_email: "{{ mon_acme_email }}"
edge_basic_auth_routes:
  - {path: /api/v1/write, port: "{{ mon_prometheus_port }}", users: [{name: "{{ mon_ingest_fleet_user }}", hash: "{{ mon_ingest_fleet_password_hash }}"}]}
  - {path: /loki/api/v1/push, port: "{{ mon_loki_port }}", users: [{name: "{{ mon_ingest_fleet_user }}", hash: "{{ mon_ingest_fleet_password_hash }}"}, {name: "{{ mon_ingest_logship_user }}", hash: "{{ mon_ingest_logship_password_hash }}"}]}
edge_paths_404: [/metrics, /metrics/*, /swagger*]
edge_head_paths: [/d/*, /alerting/*]
edge_session_cookie: grafana_session
edge_upstream_port: "{{ mon_grafana_port }}"
```

- [ ] **Step 1: Render the node's Caddyfile at this plan's base into a scratch file** — through `role_render.render` over the `mon` defaults and the test's `SECRETS`, kept under `.tmp/00122/caddyfile-before`.
- [ ] **Step 2: Write the failing tests** — the edge cases; the `mon` cases re-pointed at the include.
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The role, the include, the deletion, the play**
- [ ] **Step 5: The comparison** — the Caddyfile rendered through the include's vars into `.tmp/00122/caddyfile-after`; `diff <(grep -v '^#' .tmp/00122/caddyfile-before) <(grep -v '^#' .tmp/00122/caddyfile-after)`; Expected: empty.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_edge_role.py tests/test_infra_mon_role.py tests/test_infra_converge_guards.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 7: The consumers** — `grep -rl 'roles/mon\|Caddyfile\|roles/edge' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_deploy_log_audit.py`.
- [ ] **Step 8: The commit gate**, then commit — `refactor(infra): the Caddy edge becomes a shared role the observability node includes, its Caddyfile unchanged`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts by a message-only amend** — `infra/scripts/mutate-probe.sh` with a control and a mutation per case over `roles/edge/templates/Caddyfile.j2` (a route's `basic_auth` dropped; the `404` matcher rendered when the set is empty; the `HEAD` matcher rendered without the cookie line; the default handle given a credential; `auto_https disable_redirects` removed), each run's probe command being both `tests/test_infra_edge_role.py` and `tests/test_infra_mon_role.py`, so a mutation that survives one must be killed by the other; each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 3: `node_common`'s secrets preflight and reboot check — the `mon` role's first task and its reboot-check block become includes, the ping URL's shape a parameter

**Files:**
- Create: `infra/ansible/roles/node_common/defaults/main.yml` (`secrets_preflight: []`, `secrets_preflight_file`, `secrets_preflight_runbook`, `reboot_check_textfile_dir`, `node_common_role_name`)
- Create: `infra/ansible/roles/node_common/tasks/secrets-preflight.yml` (the one task `refuse a missing or misshapen secret, naming the key and never the value`, its fault list built from `secrets_preflight` — each `{key, shape}` evaluated as `lookup('vars', item.key, default='') is not match(item.shape)` through a `selectattr` chain, or a loop-free Jinja `namespace` accumulation, whichever the test's templar evaluates to the same list — its `fail_msg` naming `secrets_preflight_file` and `secrets_preflight_runbook` and no value)
- Create: `infra/ansible/roles/node_common/tasks/reboot-check.yml` (the four tasks of `roles/mon/tasks/main.yml`'s reboot-check block, `src:` pointing at the shared files, the enable task's `register` named `node_common_reboot_timer_install`), `files/zcrypto-reboot-check.sh`, `files/zcrypto-reboot-check.timer`, `templates/zcrypto-reboot-check.service.j2` (moved from `roles/mon/`, the header comment naming `node_common_role_name`)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the first task becomes `include_role: name: node_common tasks_from: secrets-preflight` with `secrets_preflight` listing the six keys and their shapes exactly as the inline task holds them today, `selfcheck_healthcheck_url`'s shape `https://hc-ping\.com/\S+\Z` unchanged until Task 12; the reboot-check block becomes `include_role: name: node_common tasks_from: reboot-check` with `reboot_check_textfile_dir: "{{ mon_textfile_dir }}"`)
- Delete: `roles/mon/files/zcrypto-reboot-check.sh`, `files/zcrypto-reboot-check.timer`, `templates/zcrypto-reboot-check.service.j2`
- Test: `tests/test_infra_node_common.py` (new: `assert_preflight` over the shared task with a two-key list and the twelve cases of `tests/test_infra_mon_role.py`'s preflight parametrisation re-expressed, plus a key with an empty shape list refused as misshapen; the reboot-check tasks held as `tests/test_reboot_check.py`'s copy tests hold a copy)
- Test: `tests/test_infra_mon_role.py` (`test_a_missing_or_misshapen_secret_is_refused_by_its_key` calls `role_render.assert_preflight` over the shared task with the `mon` include's `secrets_preflight` list, its twelve cases unchanged)
- Test: `tests/test_reboot_check.py` (`COPY_ROLES` loses `mon`; a new case holds the shared files under `roles/node_common/` equal to the capture role's program, and the `mon` role's include to the shared task file with its one variable)

**Interfaces:**
- Consumes: Task 1's `assert_preflight`; the `mon` role's six keys and shapes; the capture role's reboot-check program.
- Produces, for Task 9: `include_role: name: node_common tasks_from: secrets-preflight` with `secrets_preflight: [{key, shape}]`, `secrets_preflight_file`, `secrets_preflight_runbook`; `tasks_from: reboot-check` with `reboot_check_textfile_dir`.

**What this task decides:**
- The fault list is computed in the task's `vars`, as today, so `assert_preflight` templates one expression; the including role passes the list literally, so a key's shape is readable at the include and `grep -n 'shape:' roles/*/tasks/main.yml` lists every shape the fleet's nodes hold.
- The capture, ops and cache roles keep their reboot-check copies: `tests/test_reboot_check.py` holds them equal to the shared program, and their conversion is T0218's follow-on after the box (spec D15, Out of scope).

- [ ] **Step 1: Render the node's reboot-check unit at this plan's base into `.tmp/00122/reboot-before`**
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The role's two task files, the moves, the `mon` includes**
- [ ] **Step 5: The comparison** — the unit rendered through the include into `.tmp/00122/reboot-after`, `diff` ignoring comment lines; Expected: empty.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_node_common.py tests/test_infra_mon_role.py tests/test_reboot_check.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'reboot-check\|roles/mon\|roles/node_common' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py` for the task names.
- [ ] **Step 8: The commit gate**, then commit — `refactor(infra): the secrets preflight and the reboot check become shared task files the observability node includes`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations over `roles/node_common/tasks/secrets-preflight.yml` (a shape no longer anchored with `\Z`; the `fail_msg` rendering a value; a missing key read as present; the list's first entry skipped) and over `files/zcrypto-reboot-check.sh` (the gauge written as 1 when the flag is absent), each probe both the `node_common` test and the `mon` or reboot-check test.

---

### Task 4: `node_common`'s self-check pattern — the shared Python module, the unit, env file and timer templates, the `mon` self-check importing the module, its output byte-identical

**Files:**
- Create: `infra/ansible/roles/node_common/files/zcrypto_selfcheck.py` (`get(url, opener, timeout)`, `sample(text, name)`, `run(checks, env, *, ping_var, opener, now) -> int`: the loop, the parts, the `unreadable:` catch, the ping discipline and the `selfcheck:` line, moved from `roles/mon/files/zcrypto-mon-selfcheck.py` with their text unchanged)
- Create: `infra/ansible/roles/node_common/tasks/selfcheck.yml` (install the module at `/usr/local/lib/zcrypto/zcrypto_selfcheck.py`; install `selfcheck_script` at `/usr/local/sbin/{{ selfcheck_name }}`; render the env file at `/etc/default/{{ selfcheck_name }}` `0600 root`, `no_log`, `diff: false`; render the unit with `Environment=PYTHONPATH=/usr/local/lib/zcrypto` and `selfcheck_environment`'s lines; render the timer with `selfcheck_on_calendar`; enable the timer under the preview gate), `templates/selfcheck.service.j2`, `templates/selfcheck.env.j2`, `templates/selfcheck.timer.j2` (from `roles/mon/`'s three, parametrised)
- Modify: `infra/ansible/roles/node_common/defaults/main.yml` (`selfcheck_name`, `selfcheck_script`, `selfcheck_description`, `selfcheck_environment: {}`, `selfcheck_env_var`, `selfcheck_env_value`, `selfcheck_on_calendar`)
- Modify: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py` (`rules_fresh`, `fleet_fresh`, `loki_ready` and the constants stay; `main` becomes `zcrypto_selfcheck.run(checks, env, ping_var="MON_SELFCHECK_HEALTHCHECK_URL", …)`)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the self-check block becomes `include_role: name: node_common tasks_from: selfcheck` with `selfcheck_name: zcrypto-mon-selfcheck`, the script, the description, the three `MON_SELFCHECK_*` environment lines, `selfcheck_env_var: MON_SELFCHECK_HEALTHCHECK_URL`, `selfcheck_env_value: "{{ mon_selfcheck_healthcheck_url }}"`, `selfcheck_on_calendar: "*:0/5:23"`)
- Delete: `roles/mon/files/zcrypto-mon-selfcheck.timer`, `templates/zcrypto-mon-selfcheck.env.j2`, `templates/zcrypto-mon-selfcheck.service.j2`
- Test: `tests/test_infra_node_common.py` (the three templates rendered through the include's variables, the unit's `Environment=` lines equal to `selfcheck_environment` plus `PYTHONPATH`, the env file one line, the timer's `OnCalendar` and no `Persistent`; a `selfcheck_environment` name the script does not read is admitted, since the driver holds the read-equals-set case per script)
- Test: `tests/test_mon_selfcheck.py` (`selfcheck_driver.load(SCRIPT, SHARED)`; every case unchanged; the unit and env-file cases read the shared templates through the `mon` include's variables, `test_the_unit_and_its_environment_file_set_every_name_the_script_reads` now also walking the shared module's `env.get`/`env[` reads)

**Interfaces:**
- Consumes: Task 1's driver; the `mon` self-check's text at this plan's base; Task 3's include shape.
- Produces, for Task 10: `zcrypto_selfcheck.run(checks, env, *, ping_var, opener, now)`, `get`, `sample`; the include `tasks_from: selfcheck` with its seven variables.

**What this task decides:**
- The unit's `PYTHONPATH` line is the one `Environment=` line the include adds; the `mon` unit's rendered `Environment=` set therefore gains it, the one admitted difference of Step 5, and `test_the_unit_and_its_environment_file_set_every_name_the_script_reads` holds the set with it.
- `DynamicUser=true` with `ProtectSystem=strict` admits `/usr/local/lib`, so the module is readable under the unit's user; the acceptance read of R4 proves it on the node.

- [ ] **Step 1: Keep the node's three rendered files and the script's output lines at this plan's base** — the unit, the env file and the timer into `.tmp/00122/selfcheck-before/`, and `tests/test_mon_selfcheck.py`'s expected `selfcheck:` lines are already literal in the test.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The module, the task file, the templates, the `mon` script and include, the deletions**
- [ ] **Step 5: The comparison** — the three files rendered through the include into `.tmp/00122/selfcheck-after/`, `diff -r` ignoring comment lines; Expected: the unit's one added `Environment=PYTHONPATH=…` line and nothing else.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_node_common.py tests/test_mon_selfcheck.py tests/test_infra_mon_role.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'zcrypto-mon-selfcheck\|zcrypto_selfcheck\|roles/node_common' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py` for the unit's description.
- [ ] **Step 8: The commit gate**, then commit — `refactor(infra): the self-check's loop, ping discipline and units become shared, the node's script keeping its three probes and its output`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations over `files/zcrypto_selfcheck.py` (a failing probe still pinging; the ping URL printed in the verdict; a non-zero exit on a failure; an unreadable endpoint hiding the other readings) and over `templates/selfcheck.service.j2` (`EnvironmentFile` dropped; `DynamicUser` off), each probe both `tests/test_mon_selfcheck.py` and `tests/test_infra_node_common.py`.

---

### Task 5: `node_common`'s SQLite backup timer — `zcrypto-sqlite-backup`, nightly `VACUUM INTO` through an optional runner, a copy out, a prune and a gauge

**Files:**
- Create: `infra/ansible/roles/node_common/files/zcrypto-sqlite-backup.sh` (arguments: the database path and the staging directory as the runner sees them, the host-side destination directory, the keep-days, the gauge's textfile path; environment: `SQLITE_BACKUP_RUNNER`, a command prefix, empty on a host that reads the file itself, `docker compose -f <compose> exec -T web` on the clone, and `SQLITE_BACKUP_COPY`, the copy command for a runner that is a container, `docker compose -f <compose> cp web:<staged> <dest>`; the `VACUUM INTO` through `$RUNNER python3 -c` with the two paths passed as `sys.argv`, never interpolated into the SQL; the copy; the prune of both directories past the keep-days by the file's date in its name; the gauge `zcrypto_sqlite_backup_last_success_timestamp_seconds{db="<name>"}` written by tmp-and-rename on success alone; a failure logs at `ERROR` and exits non-zero, so the timer's unit goes red and the gauge stays, which the rule reads)
- Create: `infra/ansible/roles/node_common/tasks/sqlite-backup.yml` (install the script; render the service with the arguments and the two environment lines; render the timer with `sqlite_backup_on_calendar`; enable under the preview gate), `templates/sqlite-backup.service.j2`, `templates/sqlite-backup.timer.j2`
- Modify: `infra/ansible/roles/node_common/defaults/main.yml` (`sqlite_backup_name`, `sqlite_backup_db`, `sqlite_backup_staging`, `sqlite_backup_dest`, `sqlite_backup_keep_days: 14`, `sqlite_backup_runner: ""`, `sqlite_backup_copy: ""`, `sqlite_backup_on_calendar: "*-*-* 02:47:00"`, `sqlite_backup_textfile`)
- Test: `tests/test_infra_node_common.py` (the script driven in a scratch directory with an empty runner over a real SQLite file: the backup file a valid database equal in content to the source; a staged file older than the keep-days pruned and a newer one kept; the gauge's line and its atomic write; a runner that fails leaving the gauge as it was and exiting non-zero; a runner prefix exercised through a stub command on `PATH` that records its arguments and holds the SQL's paths out of the command line; the unit's `ExecStart` and the timer's `OnCalendar` rendered)

**Interfaces:**
- Consumes: Python 3's `sqlite3` module on Debian 13 (`VACUUM INTO` needs SQLite 3.27, the host's reads 3.46 or above); the textfile directory the host's Alloy reads.
- Produces, for Tasks 9 and 14: the include `tasks_from: sqlite-backup` with its variables; the gauge name `zcrypto_sqlite_backup_last_success_timestamp_seconds`.

**What this task decides:**
- The staging directory is inside the database's own tree so that, on the clone, the file is written by the container's uid and never by root beside the live `-wal` and `-shm` (spec D10); the host-side copy is what Linode Backups and a restore read.
- The script is one program for both nodes: on the clone the runner is the compose exec and the copy a compose `cp`; on the observability node later, an empty runner over `/var/lib/grafana/grafana.db` and no copy, with Grafana stopped around it by its own task, which this plan does not add.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script, the task file, the templates, the defaults**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_infra_node_common.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `tests/test_internal_terms_not_operator_visible.py`, `tests/test_error_paths_are_logged.py`, `tests/test_prose_chars.py`.
- [ ] **Step 6: The commit gate**, then commit — `feat(infra): a shared nightly SQLite backup timer, VACUUM INTO through an optional container runner`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: the prune deleting a file inside the keep-days; the gauge written before the copy; the SQL built from the path string; a failed `VACUUM` exiting 0.

---

### Task 6: `infra/scripts/vault-append-secret.sh` — the generalised P-step, a value read from the tty, held to a shape, encrypted with no newline, appended or replaced by key

**Files:**
- Create: `infra/scripts/vault-append-secret.sh` (`vault-append-secret.sh <vault-file> <key> <shape-regex> [--replace]`, run from `infra/ansible/`: refuses a file that does not exist, a key the file already carries unless `--replace`, and a `--replace` for a key the file lacks; reads with `read -rs -p "<key> (not echoed): " value < "${VAULT_APPEND_SECRET_TTY:-/dev/tty}"`; holds the value to the regex with `[[ $value =~ ^($shape)$ ]]` before anything else, refusing with the key's name and the shape's text; encrypts through `printf %s "$value" | uv run ansible-vault encrypt_string --stdin-name "$key"`; appends the block, or replaces the key's block in place with `--replace`; prints `<key>: appended` or `<key>: replaced` and nothing else; `unset value` on every exit)
- Create: `tests/test_vault_append_secret_sh.py` (a stub `uv` on `PATH` that answers `ansible-vault encrypt_string --stdin-name <key>` with a block carrying the key and a marker of the stdin's byte length; `VAULT_APPEND_SECRET_TTY` pointed at a file holding the value: the append writes one block with the key and the stdin length equal to the value's length, so no newline entered; a value failing the shape refused before the stub runs, by the stub's absence of a record; a present key refused without `--replace` and replaced with it, the other keys' blocks untouched byte for byte; a missing file refused; the value absent from stdout, stderr and the file in clear)

**Interfaces:**
- Consumes: `infra/ansible/ansible.cfg`'s vault password through `vault-pass.sh`, as every `ansible-vault` call does.
- Produces, for the rollout's P-steps: `(cd infra/ansible && ../scripts/vault-append-secret.sh <file> <key> '<shape>')`.

**What this task decides:**
- The shape is anchored by the script, so a caller passes the body alone; the P-steps below pass the same body the role's preflight holds the key to, which is the one place the two can disagree, and the plan quotes each shape once in its P-step.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_vault_append_secret_sh.py tests/test_scripts_have_tests.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `tests/test_prose_chars.py`, `tests/test_internal_terms_not_operator_visible.py`.
- [ ] **Step 6: The commit gate**, then commit — `feat(scripts): a vault P-step script that reads a secret from the tty, holds it to a shape and encrypts it with no newline`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: `printf %s` to `echo`; the shape check after the encryption; `--replace` appending a second block; the value echoed on success.

---

### Task 7: The parametrised guards — the push's node-only groups, the daily pass's patch-pass table, the two count-list entries

**Files:**
- Modify: `infra/scripts/grafana-push.sh` (`skip_default` becomes the space-separated list `zcrypto-mon zcrypto-hc`; the refusal of a Grafana Cloud push reads each name of the list against `GRAFANA_SKIP_RULE_GROUPS` and names the one missing)
- Modify: `tests/test_grafana_push_sh.py` (`test_the_committed_default_skips_exactly_the_observability_nodes_group` becomes `…_the_node_only_groups` over both names; the refusal case over a value naming one of the two)
- Modify: `tests/test_infra_alert_rules.py` (`_MON_GROUP` becomes `NODE_ONLY_GROUPS = {"zcrypto-mon": "zcrypto-mon", "zcrypto-hc": "zcrypto-hc"}`; `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` holds, per group, that a rule names its host in a `host` matcher exactly when it is in that group, and that no rule outside both names either host; the `zcrypto-hc` group is empty until Task 14, which the test admits)
- Modify: `infra/scripts/ops_daily.py` (`MON_NODE` and `MON_PATCH_RUNBOOK` become `PATCH_PASSES = (("zcrypto-mon", "infra/runbooks/mon.md#mon-patch-pass"), ("zcrypto-hc", "infra/runbooks/hc.md#hc-patch-pass"))`, the reminder loop over it, each reminder named `<host> patch pass`; the `hc` anchor resolves from Task 14 on, and `tests/test_runbook_triggers.py` or `check_descriptions` do not read this table, so the row is admitted now)
- Modify: `tests/test_ops_daily.py` (the reminder cases parametrised over the table; a host with no full converge on record owes nothing, per host)
- Modify: `infra/scripts/count-list.sh` (`c_hc_readonly_key_in_a_role` becomes `git grep -nE 'hc_readonly_api_key' -- infra/ansible/roles ':!infra/ansible/roles/ops/templates/alloy-secrets.env.j2'` over non-comment lines, its comment re-trued; `c_attended_hosts_with_automatic_reboot`'s loop gains `zcrypto-hc:hc_host`)
- Modify: `tests/test_count_list.py` and `tests/test_infra_unattended_upgrades.py` (the loop's hosts held to five; the key entry's exclusion held to the one template)
- Modify: `infra/runbooks/observability.md` (step 4 of `zcrypto-hcio-watchdog`'s two-copies sentence, false once the key is one value — re-trued by Task 13 with the rest of that section; here its `count:` clause's set text stays, since the entry's name does not change)

**Interfaces:**
- Consumes: the push script's `case " ${GRAFANA_SKIP_RULE_GROUPS} " in` form; `ops_daily.last_full_converge`; the count loop's host:group pairs.
- Produces, for Tasks 8, 13 and 14: `NODE_ONLY_GROUPS`; `PATCH_PASSES`; the count entry's new predicate.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The four edits**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_grafana_push_sh.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_count_list.py tests/test_infra_unattended_upgrades.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `grep -rl 'grafana-push.sh\|ops_daily\|ops-daily\|count-list' tests/ | sort`, every file it lists.
- [ ] **Step 6: The commit gate**, then commit — `refactor(scripts): the push's node-only groups, the daily pass's patch-pass reminders and two count entries take the second node as a parameter`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: the second group dropped from `skip_default`; the refusal reading the first name alone; a rule naming `zcrypto-hc` outside its group admitted; a sixth host dropped from the count's loop; the key named in a second template admitted.

Then the first pull request opens through the `open-pr` skill over Tasks 1 to 7, a different agent reads the branch, and `merge-pr` merges it; the rollout's R-X converges `zcrypto-mon` from merged `develop` and reads `changed=0` before Task 8's pull request opens.

---

### Task 8: The node joins the fleet — inventory, key, the hand-kept lists, the fleet page

**Files:**
- Create: `infra/ansible/files/deploy_zcrypto-hc_ed25519` (vault-encrypted) and `.pub` (the owner's P1, in the mon-node plan's O0 form, before Step 1; committed by this task)
- Create: `infra/ansible/group_vars/hc_host/vars.yml` (copied from `group_vars/mon_host/vars.yml`: `ansible_user`, `ansible_port`, `hardening_ssh_allow_users`, `hardening_extra_sysctl` with the two kernel keys and `net.ipv4.ip_forward: 1`, since Docker runs here, `firewall_extra_tcp_ports: [443]`)
- Create: `infra/ansible/host_vars/zcrypto-hc/vars.yml` (`ansible_host`, `base_hostname: zcrypto-hc`, `base_unattended_upgrades_reboot_time: [[ROLLOUT: a slot the base role's collision assert admits, an hour from every other host's and 1 h from each 4 h boundary — 10:25 is the candidate, read against the taken slots at Step 1]]`, `base_unattended_upgrades_automatic_reboot: "false"`, `deploy_authorized_key`, `hc_admin_email: <Open question 4's answer>`, `hc_selfcheck_healthcheck_url: ""` until Task 12)
- Modify: `infra/ansible/inventory/hosts.yml` (`observed` gains `hc_host`; the group before `workstation:`), `bootstrap.yml` (the first play's hosts `capture_host:cache_host:mon_host:hc_host`), `site.yml` (the node's play appended: `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `edge` and `hc`, the last two under `hc`; the charter note), `scripts/converge.sh` (`HOSTS`, `TAGNAMES` gains `hc`, `EVKEYS` gains `hc_image_digest`), `scripts/run.sh` (`KEYS`), `files/README.md`
- Modify: `infra/scripts/deploy-log-audit.py` (`NO_VENUE_EXPOSURE` gains `zcrypto-hc`), `infra/scripts/ops_daily.py` (the two alias maps gain `zcrypto-hc`/`hc`; `_TELEMETRY_HOSTS` gains it; a third allowlist in `_classify_one`, the node's Alloy alone, since the service's container is restarted by `hc.md`'s procedure), `infra/external-systems.md` (the `Host hc` stanza, port 10022, `deploy_zcrypto-hc_ed25519`), `docs/reference/fleet.md` (a Hosts row; the Reboots bullet's count clause), `infra/grafana/notification-templates/zcrypto-slack.tmpl` (the host name `zcrypto-hc` shown as `Dead-man`)
- Test: `tests/test_run_sh.py`, `test_converge_sh.py`, `test_infra_converge_guards.py`, `test_infra_unattended_upgrades.py` (`SLOT_GROUPS` gains `hc_host`), `test_infra_firewall_template.py` (the opener files), `test_pins_converged.py`, `test_deploy_log_audit.py`, `test_ops_daily.py`, `test_fleet_contracts.py`

**Interfaces:**
- Consumes: every contract the mon-node plan's Task 1 widened for `zcrypto-mon`, each gaining one more host by the same case; `tests/test_infra_unattended_upgrades.py`'s slot read.
- Produces, for Tasks 9 to 14 and the rollout: the group `hc_host`; the `converge.sh` host `zcrypto-hc`, tag `hc` and key `hc_image_digest`; the alias `hc`; the fleet page's row.

**What this task decides:**
- `converge.sh` admits `--limit zcrypto-hc`, `--tags hc` and `--tags hc -e hc_image_digest=sha256:<64 hex>`; `hc_host` stays refused as a limit.
- The node runs Docker, so `net.ipv4.ip_forward` is the fleet default and not the node's exception, and `tests/test_infra_firewall_template.py`'s opener holds `[443]`.

- [ ] **Step 1: P1's two key files are in the tree, and the slot is read** — `ls infra/ansible/files/deploy_zcrypto-hc_ed25519{,.pub} | wc -l` prints `2`; `grep -rh 'base_unattended_upgrades_reboot_time' infra/ansible/host_vars infra/ansible/group_vars | sort` lists the taken slots, and the chosen slot is an hour from each.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The files**
- [ ] **Step 5: Run the tests** — the nine test files named above.
- [ ] **Step 6: The consumers** — `grep -rl 'hosts.yml\|converge.sh\|run.sh\|external-systems\|fleet.md\|NO_VENUE_EXPOSURE\|_TELEMETRY_HOSTS' tests/ | sort`, every file it lists.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): the dead-man node joins the fleet's inventory, key ring, host lists and fleet page`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: the host dropped from `NO_VENUE_EXPOSURE`; the slot moved onto another host's; the group added under `engine_host`.

---

### Task 9: The `hc` role — the shared includes, the pinned container, its env file, its unit, the superuser, the backup, the node's Alloy

**Files:**
- Create: `infra/ansible/roles/hc/defaults/main.yml` (`hc_hostname: zcrypto-hc.zhaow.me`, `hc_acme_email`, `hc_image: ghcr.io/zhaow-de/healthchecks`, `hc_compose_dir: /opt/zcrypto-hc`, `hc_port: 8000`, `hc_volume: hc-data`, `hc_email_host`, `hc_email_port`, `hc_email_from`, `hc_backup_dir: /var/backups/zcrypto-hc`, `hc_backup_keep_days: 14`, `hc_textfile_dir: /var/lib/zcrypto-node-textfile`, `hc_admin_email: ""`, `hc_selfcheck_healthcheck_url: ""`; no `hc_image_digest` default)
- Create: `infra/ansible/roles/hc/tasks/main.yml` (in order: the secrets preflight include over `hc_secret_key` `[A-Za-z0-9!@#$%^&*(-_=+)]{50,}\Z`, `hc_admin_password` `[0-9a-f]{48}\Z`, `hc_email_host_user` `[A-Z0-9]{16,}\Z`, `hc_email_host_password` `[A-Za-z0-9+/=]{40,}\Z`, each AWS shape re-trued at P3 from the credential's own form, and `hc_selfcheck_healthcheck_url` under Task 12's shape; the `zcrypto-hc` system user and its uid read by `getent`, the uid the compose's `user:` names only if the image runs as a configurable user — the clone runs as uid 100 (item 9), so the compose names none and the volume is the image's; the compose directory; the digest block copied from the cache role's — `refuse an Alloy digest that is not a full sha256` re-worded for `hc_image_digest`, the unpulled-digest probe, the running-digest probe on `zcrypto-hc`, the pins recording against `fleet-pins.md`, `pins_override`'s echo; `hc.env` rendered `0600 root:root`, `no_log`, `diff: false`; the compose file; the unit; `enable + start` under the preview gate; `admin.yml` included outside check mode; the textfile directory; the `edge` include with `edge_hostname: "{{ hc_hostname }}"`, no routes, an empty `404` set, no `HEAD` paths, `edge_upstream_port: "{{ hc_port }}"`; the `node_common` includes for the reboot check, the self-check (`selfcheck_name: zcrypto-hc-selfcheck`, the script, `HC_SELFCHECK_STATUS=http://127.0.0.1:8000/api/v3/status/`, `HC_SELFCHECK_CONTAINER=zcrypto-hc`, `selfcheck_env_var: HC_SELFCHECK_HEALTHCHECK_URL`, `selfcheck_on_calendar: "*:0/5:23"`) and the backup (`sqlite_backup_db: /data/hc.sqlite`, `sqlite_backup_staging: /data/backups`, `sqlite_backup_dest: "{{ hc_backup_dir }}"`, the runner `docker compose -f {{ hc_compose_dir }}/compose.yaml exec -T web`, the copy `docker compose -f … cp web:`); the Alloy repository, package, `/etc/default/alloy` from `templates/alloy-env.j2` with the three `MON_PROM_*` and three `MON_LOKI_*` names, `files/config.alloy` validated, `alloy enabled + started`)
- Create: `infra/ansible/roles/hc/tasks/admin.yml` (a probe through `docker compose exec -T -e HC_ADMIN_EMAIL -e HC_ADMIN_PASSWORD web ./manage.py shell -c` printing `absent`, `ok` or `drifted` by `User.objects.filter(email=…)` and `check_password`; one write creating the superuser or setting the password, `changed` on either, `no_log` on both; the task's `environment:` carrying the two names from the vault)
- Create: `infra/ansible/roles/hc/handlers/main.yml` (`restart hc service` under the preview gate), `templates/compose.yaml.j2` (the one service `web`, `image: "{{ hc_image }}@{{ hc_image_digest }}"`, `container_name: zcrypto-hc`, `restart: unless-stopped`, `ports: ["127.0.0.1:{{ hc_port }}:8000"]`, `env_file: [./hc.env]`, `volumes: ["{{ hc_volume }}:/data"]`, journald logging, the named volume declared), `templates/hc.env.j2` (the names the clone's `docker/` directory and `hc/settings.py` read, taken at Step 1: the secret key, the site root, the allowed host, registration closed, debug off, the email host, port, TLS flag, user, password and sender, the database path, the proxy-header setting), `templates/zcrypto-hc.service.j2` (the cache unit's shape over `hc_compose_dir`), `templates/alloy-env.j2` (the access role's shape with the six `MON_*` lines and no `GRAFANA_*` line), `files/config.alloy` (the node's shape: the unix exporter's six collectors with the textfile directory, the self exporter, the journal source keeping the units of spec D12 and the container's stream, `loki.process "parse"`, one `prometheus.remote_write "mon"` and one `loki.write "mon"` reading the six names, `host = "zcrypto-hc"`)
- Test: `tests/test_infra_hc_role.py` (on `role_render`: the compose file's service held whole; the env file's names held equal to the set Step 1 recorded and carrying none of the secrets' values; the unit's `ExecStart`, `Restart` and `WorkingDirectory`; the preflight's refused cases through `assert_preflight` over the role's list; the digest block's three guards held as `tests/test_infra_converge_guards.py` holds the cache role's; the `edge` include's variables; the three `node_common` includes' variables; `admin.yml` skipped in check mode, its two tasks `no_log`, its command carrying `-e HC_ADMIN_EMAIL -e HC_ADMIN_PASSWORD` and no value; the Alloy config's `host` label, its one endpoint per plane reading the six names, held with `tests/test_infra_alloy_series.py`'s template-config case at `read == rendered`; the play's eight roles and their tags)
- Test: `tests/test_infra_alloy_series.py` (the template-config case parametrised over the `hc` pair), `tests/test_deploy_log_audit.py` (the venue-name walk over the three new roles), `tests/test_infra_converge_guards.py` (the preview-register case over `hc`)

**Interfaces:**
- Consumes: Tasks 2 to 5's includes; Task 8's group and host vars; the cache role's digest block; the access role's `alloy-env.j2`; the clone's `docker/docker-compose.yml`, `docker/.env.example` or equivalent, `docker/uwsgi.ini` and `hc/settings.py`, read at Step 1 for the env names, the proxy-header setting and the notifier's process name (spec D17).
- Produces, for Tasks 10 to 14 and the rollout: `hc_hostname`; the container `zcrypto-hc`; `/opt/zcrypto-hc/compose.yaml`; the self-check's two environment names; the backup's gauge; the node's series under `host="zcrypto-hc"`.

**What this task decides:**
- The clone's own `docker-compose.yml` is not copied onto the node: the role renders its own compose file so the digest pin, the loopback bind and the env file are the fleet's shape, and the clone's file is read for its service's needs alone.
- The superuser's email is plain and the password vaulted; `admin.yml` is the clone's counterpart of the node's `token.yml`, skipped whole in a preview, and its `shell -c` program is a one-line Python string in the task file, read by the test for the two environment names and the absence of any literal.

- [ ] **Step 1: Read the clone's contract** — `git clone --depth 1 https://github.com/zhaow-de/healthchecks .tmp/00122/healthchecks` at the tag the rollout's digest slot names, or `develop` until it exists; record in the task's commit message the env names `docker/` reads, the `SECURE_PROXY_SSL_HEADER` setting's name, the `uwsgi.ini` daemon lines and whether `createsuperuser` is interactive; the spec's D17 premises are confirmed or corrected here, a correction being a spec amendment in this commit.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The role**
- [ ] **Step 5: Dry-start `files/config.alloy`** in the dual-shipping plan's dry-start form against the `1.20` release binary, the six names set to dummies and the journal path at an empty directory; Expected: up, `/-/ready` 200, no `level=error` line.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_hc_role.py tests/test_infra_alloy_series.py tests/test_deploy_log_audit.py tests/test_infra_converge_guards.py tests/test_infra_edge_role.py tests/test_infra_node_common.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'roles/hc\|roles/edge\|roles/node_common\|config.alloy\|alloy-env.j2' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py`.
- [ ] **Step 8: The commit gate**, then commit — `feat(infra): the hc role — the dead-man service as one pinned container behind the shared edge, with the shared preflight, reboot check, self-check and backup`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations: the env file rendered without `no_log`; the compose binding `0.0.0.0`; the digest's shape refusal loosened; `admin.yml` carrying the password on its command line; the `edge` include given a route; a `GRAFANA_` line in `alloy-env.j2`; `host` changed in `config.alloy`.

---

### Task 10: The clone's self-check — three probes over the shared loop

**Files:**
- Create: `infra/ansible/roles/hc/files/zcrypto-hc-selfcheck.py` (`web_up(status_url, opener)`: a 200 with a JSON body; `notifier_alive(container, runner)`: `docker top <container>` through `subprocess.run` with the output read for the daemon's command line recorded at Task 9's Step 1, printing the line count and never the output; `ping`: the shared loop's own, the write probe; `main` calling `zcrypto_selfcheck.run` with `ping_var="HC_SELFCHECK_HEALTHCHECK_URL"`)
- Create: `tests/test_hc_selfcheck.py` (on `selfcheck_driver`: a healthy clone pings and says what it read; each failing probe withholds the ping and exits 0, the other reading still taken; `docker top` stubbed through a recorded runner, its absence of the daemon line a `FAIL`; the ping URL never in the output; the unit's environment names equal to the script's reads through the include's variables)

**Interfaces:**
- Consumes: Task 4's module and driver; Task 9's include variables.
- Produces, for Task 14's `zcrypto-hc-service-down`: the `selfcheck:` line's `web=ok|FAIL` part in the unit's journal.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_hc_selfcheck.py tests/test_mon_selfcheck.py tests/test_infra_hc_role.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `tests/test_error_paths_are_logged.py`, `tests/test_internal_terms_not_operator_visible.py`, `tests/test_prose_chars.py`.
- [ ] **Step 6: The commit gate**, then commit — `feat(infra): the dead-man node's self-check pings its own check only while the web answers and the notifier runs`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: the notifier probe always true; a 500 status read as up; the container's output printed.

Then the second pull request opens over Tasks 8 to 10; the rollout's P2 to P4 and R0 to R7 follow it.

---

### Task 11: `hc-provision.py` — the twelve checks from healthchecks.io's listing to the clone, idempotently, and the fixture from the clone

**Files:**
- Create: `infra/scripts/hc-provision.py` (`plan`, `apply`, `fixture`, `retire`; the source `https://healthchecks.io/api/v3/checks/` read with `healthchecks_readonly_api_key` from `group_vars/all/vault.yml`; the target `https://zcrypto-hc.zhaow.me/api/v3/` with `hc_readwrite_api_key` from `group_vars/all/vault.yml` for writes and `hc_readonly_api_key` from `group_vars/observed/vault.yml` for the fixture read; `ZCRYPTO_HC` the definition of the clone's own check, name `zcrypto-hc`, tags `hc selfcheck`, `timeout 600`, `grace 600`, its description citing `Runbook: infra/runbooks/hc.md#hc-dark`; per check the body `{name, slug: name, tags, desc, timeout, grace, channels: <id>, unique: ["name"]}`, `timeout` only where the source carries one; the channel id from `GET channels/` matched by kind `slack`, one and only one, else a refusal; `plan` printing names, slugs, timeouts and grace and no key; `apply` writing and reading back; `fixture` writing `tests/fixtures/healthchecks_descriptions.json` sorted by name with the trio alone; `retire` reading the clone's listing to twelve names, then healthchecks.io's with `healthchecks_api_key` from `group_vars/capture_host/vault.yml` and deleting each of its checks by uuid, printing name and status per delete; every request with a 30 s timeout; a refused or malformed answer ending the run at exit 2 naming the endpoint and never a key)
- Create: `tests/test_hc_provision.py` (`urllib.request.urlopen` and `grafana_auth.vault_var` stubbed as `tests/test_grafana_query.py`'s `_Recorded` does: the twelve bodies from an eleven-check source plus the constant; `unique` on every create; the channel id attached; a source check without `timeout` written without one; two Slack channels refused; the fixture's keys the trio and its order by name; `retire` refusing with eleven on the clone and deleting eleven with twelve; the keys absent from stdout; a 500 ending at exit 2 with the endpoint named)

**Interfaces:**
- Consumes: `grafana_auth.vault_var(name, vault_file)`; `ops_daily.check_descriptions` for the `plan` output's description check, run over the twelve before `apply`; the clone's v3 endpoints of item 3.
- Produces, for the rollout: `uv run python infra/scripts/hc-provision.py plan|apply|fixture|retire`.

**What this task decides:**
- The fixture's `zcrypto-hc` entry comes from the clone's listing like the others, never written by hand, so the script's constant and the fixture agree through the clone.
- `retire` is a separate verb with its own precondition rather than a flag of `apply`, so a mis-typed flag cannot delete.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_hc_provision.py tests/test_scripts_have_tests.py tests/test_error_paths_are_logged.py tests/test_code_prose_citations.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `tests/test_ops_daily.py` (the fixture contract), `tests/test_prose_chars.py`, `tests/test_internal_terms_not_operator_visible.py`.
- [ ] **Step 6: The commit gate**, then commit — `feat(scripts): hc-provision.py creates the fleet's checks on the dead-man service from healthchecks.io's own listing and refreshes the fixture from it`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: `unique` dropped; `retire` proceeding with eleven; a key printed on a refusal; the fixture written with `unique_key`.

---

### Task 12: The pingers' URL scheme — one key, one base, twelve slugs, the shapes, the redactor's case, the daily pass's curl guard

**Files:**
- Modify: `infra/ansible/group_vars/observed/vars.yml` (`hc_hostname: zcrypto-hc.zhaow.me`, `hc_ping_base: "https://{{ hc_hostname }}/ping/{{ hc_ping_key }}"`, `hc_project_uuid: ""` until P5, `hc_metrics_path: "/projects/{{ hc_project_uuid }}/metrics/"`)
- Modify: `infra/ansible/group_vars/observed/vault.yml` (P5 appends `hc_ping_key` and `hc_readonly_api_key`; committed by this task), `group_vars/all/vault.yml` (P5 appends `hc_readwrite_api_key`; its mixed-custody header's counts re-trued as the mon-node plan's P3 did)
- Modify: `infra/ansible/group_vars/capture_host/vars.yml` (`capture_healthcheck_url: "{{ hc_ping_base }}/zcrypto-capture"`), `host_vars/zcrypto-red/vars.yml` (`…/zcrypto-capture-red`), `group_vars/engine_host/vars.yml` (`engine_healthcheck_url: "{{ hc_ping_base }}/zcrypto-engine-shadow"`), `host_vars/nas/vars.yml` (`nas_gate_healthcheck_url: "{{ hc_ping_base }}/zcrypto-gate-verify"`), `host_vars/zcrypto-ops/vars.yml` (the six, each its check's slug), `host_vars/zcrypto-mon/vars.yml` (`mon_selfcheck_healthcheck_url: "{{ hc_ping_base }}/zcrypto-mon"`, `selfcheck_healthcheck_url` no longer referenced), `host_vars/zcrypto-hc/vars.yml` (`hc_selfcheck_healthcheck_url: "{{ hc_ping_base }}/zcrypto-hc"`)
- Modify: the preflights — the `mon` role's include list drops `selfcheck_healthcheck_url` and gains `mon_selfcheck_healthcheck_url` under the clone's shape `https://zcrypto-hc\.zhaow\.me/ping/[A-Za-z0-9_-]{16,}/[a-z0-9-]+\Z`; the `hc` role's the same over `hc_selfcheck_healthcheck_url`; the capture role's defaults comment and the engine role's re-trued; the ops role's defaults comment re-trued
- Modify: `tests/test_logging_redact.py` (a case over `https://zcrypto-hc.zhaow.me/ping/<key>/zcrypto-capture` and its `/fail`: the line carries `zcrypto-hc.zhaow.me` and nothing of the path)
- Modify: `infra/scripts/ops_daily.py` (`_curl_is_read` gains `zcrypto-hc.zhaow.me/ping`), `tests/test_ops_daily.py` (a runbook `curl` of the clone's ping URL classified a write)
- Test: `tests/test_infra_hc_role.py` (a new case holding the twelve slugs — every `*_healthcheck_url` value under `group_vars/` and `host_vars/` rendered through the templar with a dummy key, their last path segment — equal to the fixture's names plus `zcrypto-hc`, and each rendered value matching the preflights' shape; the group vars' hostname equal to the `hc` role's default)

**Interfaces:**
- Consumes: the eleven templates' variable names, unchanged; Task 11's slugs; Task 6's script for P5.
- Produces, for the rollout: the rendered URLs each host takes at its converge; the vault names `hc_ping_key`, `hc_readonly_api_key`, `hc_readwrite_api_key`.

**What this task decides:**
- The old vault values stay beside the new wiring until retirement, unread: a vars file's value shadows nothing, since each vault value's name is referenced by nothing after this task, and `tests/test_infra_hc_role.py`'s slug case reads the vars files alone.
- The shape's key part is widened or narrowed by amendment once P5 has read the minted key's shape, and the same body is passed to `vault-append-secret.sh` at P5.

- [ ] **Step 1: P5's three vault keys read present** — `grep -c '^hc_ping_key: !vault' infra/ansible/group_vars/observed/vault.yml`, the same for `hc_readonly_api_key`, and `grep -c '^hc_readwrite_api_key: !vault' infra/ansible/group_vars/all/vault.yml`; Expected: `1` each; a `0` holds the task.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The vars, the shapes, the guard, the comments**
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_infra_hc_role.py tests/test_infra_mon_role.py tests/test_logging_redact.py tests/test_ops_daily.py tests/test_infra_firewall_template.py -q -p no:cacheprovider`
- [ ] **Step 6: The consumers** — `grep -rl 'healthcheck_url\|group_vars/observed\|host_vars/zcrypto-ops\|host_vars/nas' tests/ | sort`, every file it lists.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): every dead-man ping URL renders from one vaulted project key and its check's slug`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: a slug mistyped; a shape admitting `hc-ping.com`; the redactor keeping the path; the curl guard dropping the clone's host.

---

### Task 13: The readers — the daily pass's API base and key, the ops scrape with a bearer token, the watchdog rule's text, the two panel titles

**Files:**
- Modify: `infra/scripts/ops_daily.py` (`HEALTHCHECKS_API` becomes `DEADMAN_API = "https://zcrypto-hc.zhaow.me/api/v3/checks/"`; `_readonly_key` reads `hc_readonly_api_key` from `group_vars/observed/vault.yml`; the unreadable notes name the service), `tests/test_ops_daily.py` (the URL and key cases; `DEADMAN_API`'s host equal to the `hc` role's default)
- Modify: `infra/ansible/roles/ops/files/config.alloy` (`prometheus.scrape "healthchecks"`: `__address__ = "zcrypto-hc.zhaow.me"`, `bearer_token = sys.env("HC_READONLY_KEY")`, the path still `sys.env("HC_METRICS_PATH")`, its comment re-trued), `roles/ops/templates/alloy-secrets.env.j2` (`HC_METRICS_PATH={{ hc_metrics_path }}`, `HC_READONLY_KEY={{ hc_readonly_api_key }}`, its comment re-trued), `tests/test_infra_alloy_series.py` (the literal case's two lines; the template-config case at `read == rendered` over ops, unchanged in shape; a new case holding the scrape's address, scheme and bearer read)
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-hcio-watchdog`'s title `Fleet · dead-man watchdog (check down, or the service dark)`, its summary and unit naming the service, its uid and expression unchanged), `infra/grafana/fleet-health-dashboard.json` (the two titles and descriptions), `tests/test_infra_alert_rules.py` and `tests/test_dashboards_cover_metrics.py` as they read those texts
- Modify: `infra/runbooks/observability.md` (`zcrypto-hcio-watchdog`'s section re-trued: the service, the one key, step 4's fix as an ops converge with the recreate; the dead-man map's row for `zcrypto-hc`)

**Interfaces:**
- Consumes: Task 12's `hc_metrics_path` and `hc_readonly_api_key`; the clone's `/projects/<uuid>/metrics/` with `Authorization: Bearer` (item 4); `tests/test_infra_alloy_series.py`'s literal and template-config cases.
- Produces, for the rollout: the ops converge of R9 and its recreate; the daily pass's `ops-daily.py report` reading the clone.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The edits**
- [ ] **Step 4: Dry-start the edited ops config** in the dry-start form, the two names set to dummies; Expected: up, `/-/ready` 200, no `level=error`.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_ops_daily.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`
- [ ] **Step 6: The consumers** — the dual-shipping plan's consumer listing, `grep -rl 'alloy-secrets.env\|config.alloy\|alerts.yaml\|fleet-health-dashboard' tests/ | sort`, every file it lists, and the runbook walkers.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): the daily pass, the ops scrape and the watchdog rule read the dead-man service, the read-only key held once`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: the key read from the `all` vault; the scrape's `bearer_token` dropped; the address left at `healthchecks.io`; a `GRAFANA_` line edited.

Then the third pull request opens over Tasks 11 to 13; the rollout's R8 and R9 follow it.

---

### Task 14: The node's rule group, its runbook page and its Fleet health row

**Files:**
- Modify: `infra/grafana/alerts.yaml` (the group `zcrypto-hc`: `zcrypto-alloy-dark-hc`, `zcrypto-hc-disk-low`, `zcrypto-hc-reboot-pending`, `zcrypto-hc-service-down` on the self-check's journal line `web=FAIL` or the container's stream absent 10 minutes, `zcrypto-hc-backup-stale` on the gauge older than 26 h, each with its `Runbook:` citation, panel id and severity in the node's shape)
- Create: `infra/runbooks/hc.md` (the procedures `hc-dark` from `mon-dark` with the host swapped and the two drill figures as slots, `hc-secrets` from `mon-secrets` over the five vault values and the P2 script, `hc-restore` new, `hc-backup` new, `hc-patch-pass` from `mon-patch-pass` with the image bump through the digest pin in the rollout-image skill's shape, `hc-keys` new, the UI-minted keys rotated under sudo mode and re-vaulted through `vault-append-secret.sh --replace`, the converges each takes; the ALERT sections for the five rules, three copied from `mon.md`'s with the host swapped and two new)
- Modify: `infra/grafana/fleet-health-dashboard.json` (a row of five panels), `tests/test_dashboards_cover_metrics.py` (the host map), `tests/test_infra_alert_rules.py` (the group's rules in `NODE_ONLY_GROUPS`' test, the pending-reboot family's `_REBOOT_HOSTS`), `infra/scripts/ops_daily.py` (`_UID_HOST` entries for the five)

**Interfaces:**
- Consumes: Task 7's `NODE_ONLY_GROUPS`; Task 9's series; Task 10's journal line; the mon-node plan's rule and runbook shapes.
- Produces, for the rollout: `infra/runbooks/hc.md`'s anchors; the five rules pushed to the node by `mon.md#mon-push`.

- [ ] **Step 1: Load `zcrypto-refine-rules`**, then write the page and the rules.
- [ ] **Step 2: Run the tests** — `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_ops_daily.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider`
- [ ] **Step 3: The consumers** — `grep -rl 'alerts.yaml\|runbooks/hc\|fleet-health' tests/ | sort`, every file it lists.
- [ ] **Step 4: The commit gate**, then commit — `feat(grafana): the dead-man node's five rules, its runbook page and its Fleet health row`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 5: The tree is clean**
- [ ] **Step 6: Prove the guards, then record the verdicts** — mutations: a rule of the group naming no host; a rule outside it naming `zcrypto-hc`; a section's anchor dropped.

---

### Task 15: The drills, the surfaces' sweep and the rotation topic

**Files:**
- Modify: `infra/runbooks/drills-telemetry.md` (three sections of seven parts, `drill-x1` the service stopped, `drill-x2` the 30-minute power-off, `drill-x3` the restore on a scratch container then the rebuild from nothing; the standing rules' subject list gains the node; the letter `X` held free by `grep -c '^## Drill X' infra/runbooks/drills-telemetry.md infra/runbooks/drills-order-path.md` reading 0 before the edit)
- Modify: the 116-line sweep — every operator-read line naming `healthchecks.io`, `hc-ping.com` or `hc.io` on the pages the measured basis lists, re-trued to the service by name, `drills-telemetry.md`'s and `observability.md`'s "healthchecks.io's own Slack integration" among them; the drill log untouched; `infra/grafana/alerts.yaml`'s remaining comments
- Modify: `docs/open-topics/T0085-final-pre-golive-steps.md` (the rotation scope: the one ping key in place of the eleven URLs, the clone's two keys UI-minted under sudo mode in place of healthchecks.io's two, the two-copies note gone, the rotation step's delete-and-recreate paragraph replaced by a ping-key mint and the converges of the sitting)

**Interfaces:**
- Consumes: the drill log's entry contract; `mon.md#mon-dark`'s figure-slot shape; Task 14's anchors.
- Produces, for the rollout: `drill-x1` to `drill-x3`; `hc.md#hc-dark`'s two slots.

- [ ] **Step 1: Load `zcrypto-refine-rules`**, then the three sections, the sweep and the topic.
- [ ] **Step 2: The count** — the measured basis's sweep command; Expected: `0`, every remaining mention being a drill-log entry or a commit message.
- [ ] **Step 3: The consumers** — the runbook walkers, `tests/test_drill_log.py`, `tests/test_open_topics_frontmatter.py`, `tests/test_guidance_guard.py`, `tests/test_guidance_refs_resolve.py`, `tests/test_count_list.py`.
- [ ] **Step 4: The commit gate**, then commit — `docs(runbooks): the dead-man service's three drills, every operator surface re-trued from healthchecks.io to the service, the rotation round's scope`, with the trailer; no guard changes, so no probe.
- [ ] **Step 5: The tree is clean**

---

### Task 16: Two skills take the service

**Files:**
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (step 6's description rewrite names the clone's UI and `hc_readwrite_api_key`; the telemetry hosts clause gains the node, its Alloy alone)
- Modify: `.claude/skills/zcrypto-rollout-image/SKILL.md` (the one line naming healthchecks.io re-trued)

- [ ] **Step 1: Load `zcrypto-refine-rules`**, then the two edits.
- [ ] **Step 2: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_daily_ops_skill.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider`
- [ ] **Step 3: The commit gate**, then commit — `claude(skills): the daily pass rewrites a description on the dead-man service, and the rollout skill names it`, with the trailer; a `claude` commit carrying no other file.
- [ ] **Step 4: The tree is clean**

Then the fourth pull request opens over Tasks 14 to 16; the rollout's R10 onward follows it.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step. `W$` is the workstation at the repository root, `H$` a shell on the named host (`ssh hc` once R3 writes the alias; `ssh hp`, `ssh red`, `ssh zcrypto`, `ssh mon`, the NAS by its alias). Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, never wrapped in `timeout`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. A running digest is read off the container, `docker inspect <name> --format '{{.Config.Image}}'`, never `.Image`, and matched against `docs/reference/fleet-pins.md`. No secret is typed on a command line or shown: every UI-minted value goes through `infra/scripts/vault-append-secret.sh`, every generated one through P2's script, and a value reaches a process through `vault_var` inside a command substitution. `.tmp/00122/` holds what a later step reads back. The hc node speaks to no venue, so its own converges owe no Kraken read and fall under no engine gap.

**P1. The deploy keypair** (Task 8's precondition), the mon-node plan's O0 form over `deploy_zcrypto-hc_ed25519`, run by the owner before Task 8's Step 1.

**P2. The two generated vault values, by script, none shown.** Run by the owner once Task 10's branch reads clean, from `infra/ansible`, the GPG agent unlocked: a new `host_vars/zcrypto-hc/vault.yml` with `hc_secret_key` (50 characters of Django's generator alphabet, `secrets.choice` over `abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)`) and `hc_admin_password` (48 hex), each through `ansible-vault encrypt_string --stdin-name` with no newline, the script refusing a file that exists; the check prints two booleans through `vault_var` and `git status --porcelain` names the one file. Commit `chore(hc): the dead-man node's two generated vault values`, with the trailer. The `SECRET_KEY` is stable across rebuilds: every API key's HMAC and every signed link depend on it (item 6).

**P3. The SES SMTP credential.** In AWS SES, the owner verifies the sender (Open question 4) and creates an SMTP credential; then `(cd infra/ansible && ../scripts/vault-append-secret.sh host_vars/zcrypto-hc/vault.yml hc_email_host_user '[A-Z0-9]{16,}')` and the same for `hc_email_host_password` with `[A-Za-z0-9+/=]{40,}`; a credential of another shape re-trues the two shapes in the `hc` role's preflight and here in one commit before it is vaulted. Commit `chore(hc): the SES SMTP credential, vaulted`.

Then the second pull request opens over Tasks 8 to 10 with P2's and P3's commits; a different agent reads the branch; `merge-pr` merges it. Everything below runs from merged `develop`.

**R-X. The observability node on the shared code** (after the first pull request merges, before the second opens). `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`: the preview names no changed file but the three whose header comment moved, the Caddyfile, the reboot-check unit and the self-check unit with its env file, and the real pass reads `changed=<those files>`, then a second run `changed=0 failed=0`; `ssh mon 'systemctl is-active caddy zcrypto-reboot-check.timer zcrypto-mon-selfcheck.timer'` three `active`; the self-check's next line `-> pinged` with the module imported, `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:|Traceback|ModuleNotFound" | tail -1'`. A `Traceback` is a stop: the module's path or the unit's `PYTHONPATH`, fixed on a branch before the second pull request opens. [[ROLLOUT: R-X's reading — the files the first pass changed and the second pass's `changed=0`]].

**R0. The operands, read once.** `git switch develop && git pull --ff-only && git status --porcelain` empty; `mkdir -p .tmp/00122`; `date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/00122/r0-instant`; `KRAKEN` at planning; the clone's release and its image digest: `[[ROLLOUT: the clone's release tag after the django-setup merge and the multi-arch index digest of ghcr.io/zhaow-de/healthchecks at that tag, read with `docker manifest inspect` or `crane digest`, never from a label]]`, kept in `.tmp/00122/hc-digest`.

**R1. The Linode, its Backups and its two records, read where they stand.** The mon-node plan's R1 over `zcrypto-hc`: the plan, the image Debian 13, the label, the region apart from the engine host's, Backups enabled; `dig +short A zcrypto-hc.zhaow.me`, `dig +short AAAA zcrypto-hc.zhaow.me`, the CAA read. [[ROLLOUT: R1's readings — the plan, the region, Backups, the two addresses]].

**R2. The Cloud Firewall, by hand.** The mon-node plan's R2 over the firewall `zcrypto-hc`: inbound Drop, outbound Accept, Accept TCP `22`, `10022`, `443` and ICMP on both families, attached; the port read from the workstation, `22 open` and the rest `closed` on each address.

**R3. Bootstrap, the alias, the preview and the converge.** The host key read in LISH, `H$ ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, [[ROLLOUT: the node's host-key fingerprint]]; `W$ (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-hc -e ansible_user=root -e ansible_port=22)`; the deploy key into `~/.ssh/`, the `Host hc` stanza into `~/.ssh/config`; `W$ ssh hc 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'`. The image pulled first, since the role refuses an unpulled digest: `H$ sudo docker pull ghcr.io/zhaow-de/healthchecks@$(cat .tmp/00122/hc-digest)` with the digest pasted. Then `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc -e hc_image_digest=sha256:<the digest>`: the preview `failed=0` with the repositories, the rendered files and the installs `changed` and the unit starts, the self-check, the backup and `admin.yml` `skipping`; the real pass `failed=0 unreachable=0`, `admin.yml`'s create `changed`; a second run `--tags hc -e hc_image_digest=…` reads `changed=0`. Then the TCP `22` rule removed in the Cloud Manager and the port read again, `443 open`, `10022 open`, `22 closed`, `80 closed`.

**R4. The node, read on the node.** The listeners: public `*:443`, `0.0.0.0:10022`, `[::]:10022`; loopback `127.0.0.1:8000`, `12345`, Caddy's `2019`; `sudo docker inspect zcrypto-hc --format '{{.State.Status}} {{.State.Health.Status}} {{.RestartCount}}'` reads `running healthy 0`; `systemctl is-active zcrypto-hc caddy alloy zcrypto-reboot-check.timer zcrypto-hc-selfcheck.timer zcrypto-sqlite-backup.timer` six `active`, `is-enabled` on the units; `sudo docker top zcrypto-hc` carrying uWSGI's and the notifier's lines and no environment; the self-check's last line `selfcheck: web=ok (…) notifier=ok (…) -> healthy, and no ping URL is set`, since no check exists yet; `apt-config dump | grep Automatic-Reboot` reading `"false"`; `dpkg-query -W caddy alloy docker-ce`. [[ROLLOUT: R4's package versions]].

**R5. The edge, read from outside.** `curl -4` and `curl -6 -sS -o /dev/null -w '%{http_code} %{ssl_verify_result} %{remote_ip}\n' https://zcrypto-hc.zhaow.me/api/v3/status/` each `200 0` and the address; `curl -sS https://zcrypto-hc.zhaow.me/api/v3/status/` a JSON body; the issuer Let's Encrypt; `/metrics` and `/admin/` through the edge: `[[ROLLOUT: R5's readings of /metrics and /admin/ without a login — the clone's own answers, recorded; a 200 on either is a stop before P4]]`; `/ping/not-a-key/not-a-slug` `404`, the clone creating nothing.

**R6. The node's telemetry on the observability node.** `W$ uv run python infra/scripts/grafana-query.py --stack mon 'count by (job) (up{host="zcrypto-hc"})'` two jobs at 1, and `--loki 'sum by (container) (count_over_time({host="zcrypto-hc"}[1h]))'` rows for the units and the container's stream; the Alloy's own `samples_failed_total` 0 on `127.0.0.1:12345/metrics`.

**R7. The backup timer's first run.** `H$ sudo systemctl start zcrypto-sqlite-backup.service && ls -l /var/backups/zcrypto-hc/ && cat /var/lib/zcrypto-node-textfile/sqlite-backup.prom`: one dated file and the gauge; `W$ uv run python infra/scripts/grafana-query.py --stack mon 'zcrypto_sqlite_backup_last_success_timestamp_seconds{host="zcrypto-hc"}'` one series.

**P4. The owner's first sign-in and the project.** In the clone's UI at `https://zcrypto-hc.zhaow.me`, the owner signs in with `hc_admin_email` and the password read once through `vault_var("hc_admin_password", "host_vars/zcrypto-hc/vault.yml")` into the clipboard and never a terminal line; renames the project `zcrypto`; adds the Slack integration with the webhook of Open question 2 and sends its test notification into the main channel; then, under sudo mode, whose code arrives by email through SES — a code that does not arrive is R4's SES settings, read in `sudo docker logs zcrypto-hc --since 10m` for the SMTP error — mints the read-write key, the read-only key and the project ping key, and reads the project uuid off the project's settings page. Each key is pasted once into P5's prompt and nowhere else.

**P5. The three keys and the uuid into the tree.** `(cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/all/vault.yml hc_readwrite_api_key 'hcw_[A-Za-z0-9]{28}' && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_readonly_api_key 'hcr_[A-Za-z0-9]{28}' && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_ping_key '[A-Za-z0-9_-]{16,}')`, each printing `<key>: appended`; the uuid into `group_vars/observed/vars.yml`'s `hc_project_uuid`, plain. [[ROLLOUT: the ping key's measured shape — its length and alphabet printed as booleans by `uv run python -c` over `vault_var`, never the value — written into the spec's D4 and the two preflights by amendment in the third pull request]]. The `all` vault's header counts re-trued. Commit `chore(vault): the dead-man service's three keys and its project uuid`, with the trailer; a key of another shape than the one passed is re-pasted after the shape is corrected in the same commit.

Then the third pull request opens over Tasks 11 to 13 with P5's commit; a different agent reads the branch; `merge-pr` merges it.

**R8. The twelve checks and the fixture.** `W$ uv run python infra/scripts/hc-provision.py plan` lists twelve names, slugs, timeouts and grace values from healthchecks.io's listing plus the constant, and `uv run python -c` over `ops_daily.check_descriptions` on the plan's bodies prints no finding; `apply` reports twelve created; `fixture` rewrites `tests/fixtures/healthchecks_descriptions.json`; `git diff --stat` names the one file, twelve entries; in the clone's UI each check shows the Slack integration attached. Then the node's own check goes live: `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_digest=sha256:<running>`, the env file re-rendered; `ssh hc 'sudo systemctl start zcrypto-hc-selfcheck.service && sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'` reads `-> pinged`, the first ping end to end, and the clone's UI shows `zcrypto-hc` up. The fixture's commit rides R-records-1.

**R9. ops** — the readers and the five timers' URLs and the poller. `KRAKEN` immediately before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<running-alloy> -e ops_image_digest=sha256:<running-ops>`: the preview names `alloy-secrets.env`, `conf/config.alloy`, the liquidations `compose.yaml` and the five timer scripts changed; the reload 200. Then `H$ cd /etc/zcrypto-ops/alloy && sudo docker compose up -d` and `cd /etc/zcrypto-ops && sudo docker compose up -d`, each container's `.State.StartedAt` moved and `RestartCount` 0; the poller's first clean poll pings, `W$ uv run python infra/scripts/grafana-query.py 'hc_check_up' 'hc_checks_down_total'` on Grafana Cloud reading twelve rows from the clone with `zcrypto-liquidations` at 1 within its interval and `max(hc_checks_down_total)` reading the checks not yet moved as down — the capture pair's, the engine's, the gate's and the node's — which is the sitting's own state, announced in the main channel beforehand with `zcrypto-hcio-watchdog`'s page expected until R12 ends; `ssh hp 'sudo systemctl list-timers zcrypto-\*'`, and after each timer's next tick its check's `last_ping` on the clone moved (the five ops checks); `uv run python infra/scripts/ops-daily.py report --since 1h` reading the clone's twelve in its dead-man section with no unreadable note.

**R10. The observability node.** `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`; the self-check's next line `-> pinged` and the clone's `zcrypto-mon` check up.

**R11. The NAS.** `W$ infra/ansible/scripts/converge.sh site.yml --limit nas --tags nas --check`, then `… -e nas_apply_compose=true`; `archive-pull`'s `.Created` moved; the gate export's replay sized by `fleet-pins.md`'s standing constraint beforehand; the next `gate-export` pings, the clone's `zcrypto-gate-verify` up.

**R12. The capture pair** (Open question 1's answer, in the first sitting). `zcrypto-red`: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the capture compose render `changed` and its restart handler run, `zcrypto-capture`'s `StartedAt` moved and `RestartCount` 0; the clone's `zcrypto-capture-red` up within two minutes. An hour later, `zcrypto`: `KRAKEN` immediately before, away from a 4-hourly boundary and from any engine restart; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --skip-tags engine -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`; the same reads; `zcrypto-engine`'s `StartedAt` unmoved. The capture gap each restart books is read on the pulled copy by the rollout-image skill's verify-by-outcome. After it, `max(hc_checks_down_total)` on Grafana Cloud reads `1`, the engine's check, until R14.

**R13. The checks' first clean read.** `W$ uv run python infra/scripts/grafana-query.py 'hc_check_up'` eleven at 1 and `zcrypto-engine-shadow` at 0; on healthchecks.io's UI, every check but the engine's stale and the engine's pinging; `zcrypto-hcio-watchdog` firing in the main channel at `1`, announced, and silenced in Grafana Cloud by the owner for the engine's row alone until R14 — a silence on the whole rule is never set (`observability.md`'s step 5).

**R-records-1. The inside-box records: one pull request.** The deploy-log rows; `fleet-pins.md`'s `hc` row and glossary entry and the `since` cells of ops' two containers and the capture pair's; `fleet.md`'s Services, Reboots and Telemetry labels; the fixture from R8; T0218's findings with R0 to R5's readings; the spec's D4 shape amendment from P5 where the third pull request did not carry it; the `AUDIT` line of the dual-shipping plan over this sitting's rows, 0.

**R14. After the box — the engine** (on or after [[ROLLOUT: the box's closing date]]). `KRAKEN` immediately before; inside the inter-cycle gap, `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e engine_image_digest=sha256:<running>`, under `infra/runbooks/engine-procedures.md`'s restart rules and the position read it names; the engine's next cycle pings the clone, `zcrypto-engine-shadow` up, `max(hc_checks_down_total)` 0 on Grafana Cloud; the silence of R13 ended.

**R15. The three drills** (Task 15), in an attended window, each announced: X1 the service stopped until `zcrypto-hcio-watchdog`'s `999` page, [[ROLLOUT: X1's reading — the page's `activeAt` and the checks that paged DOWN then UP on return]]; X2 the 30-minute power-off, [[ROLLOUT: X2's reading — the page and the self-check's first `-> pinged` after boot]]; X3 the restore on a scratch container, twelve checks counted through its API, then the rebuild from nothing with P4's UI steps re-run and P5's keys re-vaulted with `--replace`, [[ROLLOUT: X3's reading — the time from the rebuild to the first stored ping]]; the entries into the drill log, the two figures into `hc.md#hc-dark`.

**R16. Retirement** (after R14's first clean day). `W$ uv run python infra/scripts/hc-provision.py retire` prints eleven deletes; the owner revokes healthchecks.io's two keys and closes the account; one pull request removes the fourteen vault values and their comments, re-trues T0085 and `observability.md`'s step 4, and records the date in T0218.

**R-records-2. The after-box records: one pull request.** The deploy-log rows, the three drill-log entries, the `since` cell of the engine, `hc.md`'s two figures, T0218 resolved, the `AUDIT` line 0, and the commit `chore(fleet): the fleet's dead-man checks run on the owner's service`, with the trailer.

## Resolution

T0218 is resolved by R-records-2. What this plan leaves to later: the capture, ops and cache roles' reboot-check copies onto the shared task file, after the box; Grafana's SQLite through the shared backup timer; the ops watchdog's probe re-pointed at the node, 00121 phase 3's.

## Slots the rollout fills

- `[[ROLLOUT: the box's closing date, 2026-11-01 or a week later …]]` (Global Constraints; R14).
- `[[ROLLOUT: the clone's release and its image digest …]]` (spec D3; R0) — the first pin.
- `[[ROLLOUT: R-X's reading …]]` (R-X) — the extraction's `changed=0`.
- `[[ROLLOUT: a slot the base role's collision assert admits …]]` (Task 8).
- `[[ROLLOUT: R1's readings …]]`, `[[ROLLOUT: the node's host-key fingerprint]]`, `[[ROLLOUT: R4's package versions]]`, `[[ROLLOUT: R5's readings of /metrics and /admin/ …]]` (R1 to R5) — into R-records-1.
- `[[ROLLOUT: the ping key's measured shape …]]` (P5) — the spec's D4 and the two preflights by amendment.
- `[[ROLLOUT: X1's reading …]]`, `[[ROLLOUT: X2's reading …]]`, `[[ROLLOUT: X3's reading …]]` (R15) — `hc.md#hc-dark` and the drill log.
