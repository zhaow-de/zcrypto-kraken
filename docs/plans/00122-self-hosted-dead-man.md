# The dead-man service on `zcrypto-hc`: the shared node code extracted, the clone deployed, the fleet cut over — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every dead-man check the fleet relies on runs on the owner's healthchecks.io replacement at `zcrypto-hc.zhaow.me`: the node built by one bootstrap and one converge from a role that shares its edge, its secrets preflight, its reboot check, its self-check pattern and its backup timer with the observability node's role; the twelve checks provisioned by script; every pinger on a slug URL under one vaulted project key; the daily pass, the ops scrape, the watchdog rule and the watchdog timer reading the clone; healthchecks.io retired after the cutover's first clean day, with the engine's check the one that waits for the box to close.

**Architecture:** Seven extraction tasks first, each behaviour-preserving for `zcrypto-mon` and proven by the existing literal tests, a before-and-after render comparison and a probe that fails both roles' tests, then a converge of the node reading `changed=0`; then the node's tasks on the shared code; then the pingers' and readers' tasks; then the surfaces. Four pull requests by component, an attended runsheet with the owner's P-steps for what the clone's UI alone mints, three drills, and two records pull requests.

**Tech Stack:** Ansible (ansible-core 2.21; the `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `mon`, `ops`, `capture`, `engine`, `nas` roles and the new `edge`, `node_common` and `hc` roles), Docker Compose on `zcrypto-hc`, the clone's image `ghcr.io/zhaow-de/healthchecks` (Python 3.14, Django 6.1, uWSGI, SQLite in WAL mode), Caddy from the cloudsmith repository, Grafana Alloy from `apt.grafana.com`, Prometheus and Loki on the observability node, pytest, `infra/scripts/mutate-probe.sh`, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00122-self-hosted-dead-man-design.md`, every decision; its open questions are answered by the owner (2026-10-04) and the answers written into the spec's table. The 00121 counterparts each task copies from are named in its Files.

## Global Constraints

- The host is `zcrypto-hc` (`zcrypto-hc.zhaow.me`, an A and an AAAA record), inventory group `hc_host`, a child of `observed`; the admin user `zcrypto-deploy` on port 10022; its play runs `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker` and `hc`, each under its own tag, the `hc` role including the shared `edge` role, whose tasks take the `hc` tag; no play lists `edge` (spec D1, D2).
- The service is one container, `zcrypto-hc`, pinned by version tag through `-e hc_image_tag=v6.0.0` (the owner's ruling, spec Open question 5) with a `docs/reference/fleet-pins.md` row; the role refuses a malformed or unpulled tag and a running tag the pins file does not record unless `pins_override` names a reason; the container binds `127.0.0.1:8000` and Caddy is the one public listener on 443 (spec D2, D3).
- The `mon` role's files that move to shared code — its Caddyfile, its reboot-check script, unit and timer, and its self-check unit, env file and timer — render identical before and after each extraction but for their header comments and the self-check unit's one added `Environment=PYTHONPATH=` line, held by `tests/test_infra_mon_role.py`, `tests/test_mon_selfcheck.py` and `tests/test_reboot_check.py` with their assertions unchanged and by the comparison each extraction task's Step 5 runs; no `hc` task merges before `zcrypto-mon` has been converged `changed=0` on the shared code (spec D15; the rollout's R-X).
- No ping key, API key, `SECRET_KEY`, SMTP credential or password appears on a command line, in a log, a diff, a plan step or a tracked file in clear: every UI-minted value enters the vault through `infra/scripts/vault-append-secret.sh`, every generated one through the P2 script, and each reaches a host through a `no_log` render with `diff: false` alone, Task 12 bringing the ping URL's renders that predate this plan to that form, with one exception, the NAS's gate export, which takes its URL as an argument inside its container. No executor decrypts, prints or generates a vault value; `ansible-inventory --host`, `--list` and `--graph --vars` are never run; no container's environment is printed by any form, a recreate being proven by `.State.StartedAt` moving (spec's invariants).
- The read-only key is one vault value, `hc_readonly_api_key` in `group_vars/observed/vault.yml`, rendered by `roles/ops/templates/alloy-secrets.env.j2` alone and read by the workstation by file path; the read-write key, `hc_readwrite_api_key` in `group_vars/all/vault.yml`, never reaches a host (spec D6, D7).
- The ping URLs are rendered from `hc_ping_base` and the slug equal to the check's name; no template changes its variable name; the twelve slugs are the set of the fixture's names with `zcrypto-hc` added; no host's URL moves before `hc-provision.py apply` has created its check, since an unknown slug answers 404 and creates nothing, so R8's `apply` runs from the third pull request's branch before it merges (spec D4, D6, D17).
- The cutover's order is the spec's D5: ops, the node, the NAS, `zcrypto-red`, then `zcrypto` an hour later in the attended form `--tags capture -e converge_primary=true -e capture_image_digest=<running> -e capture_alloy_digest=<running>`, never `--skip-tags engine`, whose run carries the `docker` role and records empty `tags`, both of which the box's step 10 refuses on `zcrypto`; the Kraken feed `https://status.kraken.com/api/v2/scheduled-maintenances.json` read whole, never through `head` or `tail`, at planning and immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`; the engine's converge after the box alone, `--tags engine -e converge_primary=true` with the running engine and cache-proxy digests, inside the inter-cycle gap; no step converges the engine inside the box: [[ROLLOUT: the box's closing date, 2026-11-01 or a week later — the earliest the engine's move may run]] (`.claude/rules/fleet-deploys.md`; `infra/runbooks/engine-procedures.md#engine-rung-2-box`).
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
- Modified by the extraction: `infra/ansible/roles/mon/tasks/main.yml` (the preflight, the Caddy block, the reboot-check and self-check blocks become includes), `roles/mon/handlers/main.yml` (`reload caddy` leaves), `roles/mon/defaults/main.yml` (the include variables), `roles/mon/files/zcrypto-mon-selfcheck.py` (imports the shared module), the removed `roles/mon/templates/Caddyfile.j2`, `files/zcrypto-reboot-check.*`, `templates/zcrypto-reboot-check.service.j2`, `files/zcrypto-mon-selfcheck.timer`, `templates/zcrypto-mon-selfcheck.{env,service}.j2`; `tests/test_infra_mon_role.py`, `tests/test_mon_selfcheck.py`, `tests/test_reboot_check.py`; `infra/scripts/grafana-push.sh`, `tests/test_grafana_push_sh.py`, `tests/test_infra_alert_rules.py`; `infra/scripts/ops_daily.py`'s reminder table, `tests/test_ops_daily.py`; `infra/ansible/group_vars/observed/vars.yml`'s header citation, `infra/runbooks/drills-telemetry.md`'s self-check timer citation, `tests/test_internal_terms_not_operator_visible.py`'s description walker (Tasks 1 to 7).
- The node: `infra/ansible/inventory/hosts.yml`, `site.yml`, `bootstrap.yml`, `scripts/converge.sh`, `scripts/run.sh`, `roles/base/tasks/main.yml`, `files/README.md`, `files/deploy_zcrypto-hc_ed25519{,.pub}`, `group_vars/hc_host/vars.yml`, `host_vars/zcrypto-hc/vars.yml` (and `vault.yml` from P2); `infra/scripts/deploy-log-audit.py`, `ops_daily.py`'s aliases and sets, `infra/scripts/count-list.sh`'s attended-hosts loop, `tests/test_count_list.py`, `infra/external-systems.md`, `docs/reference/fleet.md`'s Hosts row and Reboots bullet, `infra/grafana/notification-templates/zcrypto-slack.tmpl` (Task 8); `infra/ansible/roles/hc/` (`defaults/main.yml`, `tasks/main.yml`, `tasks/admin.yml`, `handlers/main.yml`, `templates/compose.yaml.j2`, `templates/hc.env.j2`, `templates/zcrypto-hc.service.j2`, `templates/alloy-env.j2`, `files/config.alloy`, `files/zcrypto-hc-selfcheck.py`), `tests/test_infra_hc_role.py`, `tests/test_hc_selfcheck.py` (Tasks 9, 10).
- The pingers and readers: `infra/scripts/hc-provision.py`, `tests/test_hc_provision.py` (Task 11); `group_vars/observed/vars.yml`, the key lines of `group_vars/capture_host/vault.yml`, `group_vars/engine_host/vault.yml`, `host_vars/zcrypto-red/vault.yml` and `host_vars/nas/vault.yml`, `group_vars/capture_host/vars.yml`, `group_vars/engine_host/vars.yml` (new), `host_vars/zcrypto-red/vars.yml`, `host_vars/nas/vars.yml`, `host_vars/zcrypto-ops/vars.yml`, `host_vars/zcrypto-mon/vars.yml`, `host_vars/zcrypto-hc/vars.yml`, the preflights' ping-URL shapes, the capture and ops roles' ping-URL renders, `tests/test_logging_redact.py`, `ops_daily.py`'s `_curl_is_read` (Task 12); `ops_daily.py`'s `DEADMAN_API` and `_readonly_key`, `infra/scripts/count-list.sh`'s key entry, `roles/ops/files/config.alloy`, `roles/ops/templates/alloy-secrets.env.j2`, `roles/ops/templates/panel-regenerate.sh.j2`'s two prompts, `infra/grafana/alerts.yaml`'s watchdog text, `fleet-health-dashboard.json`'s two titles, `infra/runbooks/observability.md`'s watchdog section, `tests/test_infra_alloy_series.py`, `tests/test_ops_daily.py`, `tests/test_count_list.py`, `tests/test_panel_regenerate.py` (Task 13).
- The surfaces: `infra/grafana/alerts.yaml`'s `zcrypto-hc` group, `fleet-health-dashboard.json`'s row, `infra/runbooks/hc.md`, `ops_daily.py`'s second patch-pass row and `_UID_HOST`, `tests/test_infra_alert_rules.py`, `tests/test_dashboards_cover_metrics.py` (Task 14); `infra/runbooks/drills-telemetry.md`, `observability.md`, the 116-line sweep's pages (Task 15); `.claude/skills/zcrypto-daily-ops/SKILL.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md` (Task 16).
- `tests/fixtures/healthchecks_descriptions.json` with `tests/test_ops_daily.py`'s fixture count, `docs/reference/deploy-log.jsonl`, `drill-log.md`, `fleet-pins.md`, `fleet.md`'s Services and instruments and Telemetry labels sections, `docs/open-topics/T0218-self-hosted-dead-man-service.md`, the spec's measured basis: the rollout's records pull requests, not a task's; `docs/open-topics/T0085-final-pre-golive-steps.md`: R16's retirement pull request.

## Review Focus

- A rendered file of the live node moved by an extraction: the Caddyfile's routes, the self-check unit's `Environment=` lines and its env file's one name, the reboot-check unit's one variable — each is held by literal in the existing tests and by the before-and-after comparison of Tasks 2 to 4's Step 5, and a probe on the shared file must fail the `mon` test and the `hc` or `edge` test alike.
- A secret reaching the clone's host or the tree in clear: `hc.env` rendered `no_log` with `diff: false` at `0600`, the admin task passing its two values on the command module's `stdin`, never in `environment:` or on a command line, `vault-append-secret.sh` refusing a value that fails its shape before `ansible-vault` runs and writing with `printf %s`, the self-check and the provisioning script printing hostnames and never a key — Tasks 6, 9, 10 and 11's cases.
- A ping URL rendered before its check exists, or a slug that is not its check's name: the twelve slugs held equal to the set of the fixture's names with `zcrypto-hc` added, no ping URL's name shadowed by a vault value of the same name, every preflight holding a URL to the clone's shape, and the rollout's order creating the checks before any host moves — Tasks 11 and 12 and R8.
- The read-only key in two names, or rendered by a second role: `hc-readonly-key-in-a-role` re-pointed, the ops template's two lines held by literal, the daily pass reading the observed vault by file path — Task 13.
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
- [ ] **Step 3: The commit gate**, then commit — `refactor(tests): the node role's render-and-hold helpers and the self-check driver become shared modules`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 4: The tree is clean** — `git status --porcelain`; Expected: empty.
- [ ] **Step 5: Prove the moved driver, then record the verdict by a message-only amend** — `infra/scripts/mutate-probe.sh` over `infra/ansible/roles/mon/tasks/main.yml`'s inline preflight, the admin user's shape `u[0-9a-f]{16}\Z` replaced by `.*`, the probe `uv run pytest tests/test_infra_mon_role.py -k refused_by_its_key -q -p no:cacheprovider`, so `assert_preflight` is shown to fail when the task admits a value it refused; Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 2: The `edge` role — Caddy from the cloudsmith repository and the parametrised Caddyfile, the `mon` role's Caddy block an include, its Caddyfile unchanged but for its header

**Files:**
- Create: `infra/ansible/roles/edge/defaults/main.yml` (`edge_hostname`, `edge_acme_email`, `edge_basic_auth_routes: []`, `edge_paths_404: []`, `edge_head_paths: []`, `edge_session_cookie: ""`, `edge_upstream_port`, `edge_role_name` for the rendered header's "Rendered by the `<role>` role" line)
- Create: `infra/ansible/roles/edge/tasks/main.yml` (the Caddy repository task copied from `roles/mon/tasks/main.yml`'s `add the Caddy apt repository`, the preview fact `edge_repo_previewed`, the install `caddy present — version FOLLOWED from apt, never forced or held`, the preview fact `edge_units_previewed`, the Caddyfile task with `validate`, `no_log` and `diff: false`, `caddy enabled + started` under `not edge_units_previewed`)
- Create: `infra/ansible/roles/edge/handlers/main.yml` (`reload caddy` under `not edge_units_previewed`)
- Create: `infra/ansible/roles/edge/templates/Caddyfile.j2` (the node's Caddyfile with the four parameters rendered in its place: the routes loop, the `404` matcher when `edge_paths_404` is non-empty, the `HEAD` matcher with its comment when `edge_head_paths` is non-empty, the default handle)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the two Caddy tasks and the repository task become `include_role: name: edge` with `vars` — `edge_hostname: "{{ mon_hostname }}"`, the two routes with the ingest users' hashes, `edge_paths_404: [/metrics, /metrics/*, /swagger*]`, `edge_head_paths: [/d/*, /alerting/*]`, `edge_session_cookie: grafana_session`, `edge_upstream_port: "{{ mon_grafana_port }}"`; `mon_repos_previewed` reads `mon_grafana_repo` alone and `mon_units_previewed` drops `mon_caddy_install`)
- Modify: `infra/ansible/roles/mon/handlers/main.yml` (`reload caddy` removed), `roles/mon/defaults/main.yml` (unchanged names; `mon_acme_email` stays and feeds the include)
- Delete: `infra/ansible/roles/mon/templates/Caddyfile.j2`
- Modify: `infra/ansible/group_vars/observed/vars.yml` (its header comment's citation of `roles/mon/templates/Caddyfile.j2` re-pointed at `roles/edge/templates/Caddyfile.j2`); `infra/ansible/site.yml` is unchanged: no play lists `edge`, whose tasks the include runs under the including role's tag, so `test_the_play_runs_the_role_under_its_own_tag_with_no_container_runtime` keeps its six roles
- Test: `tests/test_infra_edge_role.py` (new: the template rendered through `role_render.render` over the edge defaults with each parameter set, held by `site`, `users` and `upstream`: no routes renders one `handle`; a route renders its users' hashes and its upstream; an empty `404` set renders no matcher; the `HEAD` matcher renders only with paths and carries the cookie name; the repository and install tasks held as `test_no_package_is_forced_held_or_pinned_to_a_version` holds the node's; the two preview facts held as the node's are; no play in `site.yml` listing `edge`, since a role a play lists and a role includes runs twice, the first time on its defaults)
- Test: `tests/test_infra_mon_role.py` (the Caddyfile cases read `role_render.render(EDGE, "Caddyfile.j2", …)` with the include's `vars` taken from the `mon` task through `find_task`, so the test holds what the node renders and not a hand copy; the preview-facts case loses its Caddy columns, which `tests/test_infra_edge_role.py` takes)
- Test: `tests/test_infra_converge_guards.py` (the preview-register case, `test_every_register_a_preview_guard_reads_is_set_in_its_own_role`, widened over the `edge` role)

**Interfaces:**
- Consumes: Task 1's helpers; the node's Caddyfile text at this plan's base, kept in Step 5's comparison; `tests/test_infra_converge_guards.py`.
- Produces, for Task 9: `include_role: name: edge` with its eight variables; the `edge_units_previewed` fact the `hc` role's own preview facts read.

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
edge_role_name: mon
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
- [ ] **Step 10: Prove the guards, then record the verdicts by a message-only amend** — `infra/scripts/mutate-probe.sh` with a control and a mutation per case over `roles/edge/templates/Caddyfile.j2` (a route's `basic_auth` dropped; the `404` matcher rendered when the set is empty; the `HEAD` matcher rendered without the cookie line; the default handle given a credential; `auto_https disable_redirects` removed), each run's probe command being both `tests/test_infra_edge_role.py` and `tests/test_infra_mon_role.py`, so a mutation that survives one must be killed by the other, and one over `infra/ansible/site.yml` (`edge` added to the node's play) killed by the no-play case; each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 3: `node_common`'s secrets preflight and reboot check — the `mon` role's first task and its reboot-check block become includes, the ping URL's shape a parameter

**Files:**
- Create: `infra/ansible/roles/node_common/defaults/main.yml` (`secrets_preflight: []`, `secrets_preflight_file`, `secrets_preflight_runbook`, `reboot_check_textfile_dir`, `node_common_role_name`)
- Create: `infra/ansible/roles/node_common/tasks/secrets-preflight.yml` (the one task `refuse a missing or misshapen secret, naming the key and never the value`, its fault list built from `secrets_preflight` — each `{key, shape}` evaluated as `lookup('vars', item.key, default='') is not match(item.shape)` through a `selectattr` chain, or a loop-free Jinja `namespace` accumulation, whichever the test's templar evaluates to the same list — its `fail_msg` naming `secrets_preflight_file` and `secrets_preflight_runbook` and no value)
- Create: `infra/ansible/roles/node_common/tasks/reboot-check.yml` (the four tasks of `roles/mon/tasks/main.yml`'s reboot-check block, `src:` pointing at the shared files, the enable task's `register` named `node_common_reboot_timer_install`), `files/zcrypto-reboot-check.sh`, `files/zcrypto-reboot-check.timer`, `templates/zcrypto-reboot-check.service.j2` (moved from `roles/mon/`, the unit's header comment naming `node_common_role_name` and the script's and the timer's, which name the `mon` role today, naming the shared role)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the first task becomes `include_role: name: node_common tasks_from: secrets-preflight` with `secrets_preflight` listing the six keys and their shapes exactly as the inline task holds them today, `selfcheck_healthcheck_url`'s shape `https://hc-ping\.com/\S+\Z` unchanged until Task 12; the reboot-check block becomes `include_role: name: node_common tasks_from: reboot-check` with `reboot_check_textfile_dir: "{{ mon_textfile_dir }}"`)
- Delete: `roles/mon/files/zcrypto-reboot-check.sh`, `files/zcrypto-reboot-check.timer`, `templates/zcrypto-reboot-check.service.j2`
- Test: `tests/test_infra_node_common.py` (new: `assert_preflight` over the shared task with a two-key list and the twelve cases of `tests/test_infra_mon_role.py`'s preflight parametrisation re-expressed, plus a key with an empty shape list refused as misshapen; the reboot-check tasks held as `tests/test_reboot_check.py`'s copy tests hold a copy)
- Test: `tests/test_infra_mon_role.py` (`test_a_missing_or_misshapen_secret_is_refused_by_its_key` calls `role_render.assert_preflight` over the shared task with the `mon` include's `secrets_preflight` list, its twelve cases unchanged)
- Test: `tests/test_reboot_check.py` (`COPY_ROLES` loses `mon`; a new case holds the shared files under `roles/node_common/` equal to the capture role's program, and the `mon` role's include to the shared task file with its one variable; `test_the_mon_unit_writes_into_the_directory_the_mon_alloy_scrapes`, which reads the deleted template, re-pointed at the shared unit template through the `mon` include's `reboot_check_textfile_dir`)

**Interfaces:**
- Consumes: Task 1's `assert_preflight`; the `mon` role's six keys and shapes; the capture role's reboot-check program.
- Produces, for Task 9: `include_role: name: node_common tasks_from: secrets-preflight` with `secrets_preflight: [{key, shape}]`, `secrets_preflight_file`, `secrets_preflight_runbook`; `tasks_from: reboot-check` with `reboot_check_textfile_dir`.

**What this task decides:**
- The fault list is computed in the task's `vars`, as today, so `assert_preflight` templates one expression; the including role passes the list literally, so a key's shape is readable at the include and `grep -n 'shape:' roles/*/tasks/main.yml` lists every shape the fleet's nodes hold.
- The capture, ops and cache roles keep their reboot-check copies: `tests/test_reboot_check.py` holds them equal to the shared program, and their conversion is dropped (spec D15, Out of scope).

- [ ] **Step 1: Render the node's reboot-check unit at this plan's base into `.tmp/00122/reboot-before`**
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The role's two task files, the moves, the `mon` includes**
- [ ] **Step 5: The comparison** — the unit rendered through the include into `.tmp/00122/reboot-after`, `diff` ignoring comment lines; Expected: empty.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_node_common.py tests/test_infra_mon_role.py tests/test_reboot_check.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'reboot-check\|roles/mon\|roles/node_common' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py` for the task names.
- [ ] **Step 8: The commit gate**, then commit — `refactor(infra): the secrets preflight and the reboot check become shared task files the observability node includes`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations over `roles/node_common/tasks/secrets-preflight.yml` (the `fail_msg` rendering a value; a missing key read as present; the list's first entry skipped), over `roles/mon/tasks/main.yml`'s include list (one shape's `\Z` removed, which its trailing-newline case kills: the shapes are the including role's, so the shared file holds no `\Z`) and over `files/zcrypto-reboot-check.sh` (the gauge written as 1 when the flag is absent), each probe both the `node_common` test and the `mon` or reboot-check test.

---

### Task 4: `node_common`'s self-check pattern — the shared Python module, the unit, env file and timer templates, the `mon` self-check importing the module, its output byte-identical

**Files:**
- Create: `infra/ansible/roles/node_common/files/zcrypto_selfcheck.py` (`get(url, opener, timeout)`, `sample(text, name)`, `run(checks, env, *, ping_var, opener, now) -> int`: the loop, the parts, the `unreadable:` catch, the ping discipline and the `selfcheck:` line, moved from `roles/mon/files/zcrypto-mon-selfcheck.py` with their text unchanged)
- Create: `infra/ansible/roles/node_common/tasks/selfcheck.yml` (create `/usr/local/lib/zcrypto` `0755 root`, since `copy` creates no parent directory, then install the module at `/usr/local/lib/zcrypto/zcrypto_selfcheck.py`; install `selfcheck_script` at `/usr/local/sbin/{{ selfcheck_name }}`; render the env file at `/etc/default/{{ selfcheck_name }}` `0600 root`, `no_log`, `diff: false`; render the unit with `Environment=PYTHONPATH=/usr/local/lib/zcrypto` and `selfcheck_environment`'s lines; render the timer with `selfcheck_on_calendar` and `selfcheck_timer_description`; enable the timer under the preview gate), `templates/selfcheck.service.j2`, `templates/selfcheck.env.j2`, `templates/selfcheck.timer.j2` (from `roles/mon/`'s three, parametrised)
- Modify: `infra/ansible/roles/node_common/defaults/main.yml` (`selfcheck_name`, `selfcheck_script`, `selfcheck_description`, `selfcheck_timer_description`, `selfcheck_environment: {}`, `selfcheck_env_var`, `selfcheck_env_value`, `selfcheck_on_calendar`)
- Modify: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py` (`rules_fresh`, `fleet_fresh`, `loki_ready` and the constants stay; `main` becomes `zcrypto_selfcheck.run(checks, env, ping_var="MON_SELFCHECK_HEALTHCHECK_URL", …)`)
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (the self-check block becomes `include_role: name: node_common tasks_from: selfcheck` with `selfcheck_name: zcrypto-mon-selfcheck`, the script, the unit's and the timer's descriptions as the node's two files carry them, the three `MON_SELFCHECK_*` environment lines, `selfcheck_env_var: MON_SELFCHECK_HEALTHCHECK_URL`, `selfcheck_env_value: "{{ mon_selfcheck_healthcheck_url }}"`, `selfcheck_on_calendar: "*:0/5:23"`)
- Delete: `roles/mon/files/zcrypto-mon-selfcheck.timer`, `templates/zcrypto-mon-selfcheck.env.j2`, `templates/zcrypto-mon-selfcheck.service.j2`
- Modify: `infra/runbooks/drills-telemetry.md` (its one citation of `roles/mon/files/zcrypto-mon-selfcheck.timer` for the self-check's `OnCalendar` re-pointed at the `mon` include's `selfcheck_on_calendar`), `tests/test_internal_terms_not_operator_visible.py` (the systemd-description walker also reads every include's `selfcheck_description` and `selfcheck_timer_description` values, since a `Description=` line now renders one)
- Test: `tests/test_infra_node_common.py` (the three templates rendered through the include's variables, the unit's `Environment=` lines equal to `selfcheck_environment` plus `PYTHONPATH`, the unit carrying no `InaccessiblePaths=` or `ReadOnlyPaths=` line, the env file one line, the timer's `OnCalendar` and no `Persistent`; a `selfcheck_environment` name the script does not read is admitted, since the driver holds the read-equals-set case per script)
- Test: `tests/test_mon_selfcheck.py` (`selfcheck_driver.load(SCRIPT, SHARED)`; every case unchanged; the unit and env-file cases read the shared templates through the `mon` include's variables, `test_the_unit_and_its_environment_file_set_every_name_the_script_reads` now also walking the shared module's `env.get`/`env[` reads)

**Interfaces:**
- Consumes: Task 1's driver; the `mon` self-check's text at this plan's base; Task 3's include shape.
- Produces, for Task 10: `zcrypto_selfcheck.run(checks, env, *, ping_var, opener, now)`, `get`, `sample`; the include `tasks_from: selfcheck` with its eight variables.

**What this task decides:**
- The unit's `PYTHONPATH` line is the one `Environment=` line the include adds; the `mon` unit's rendered `Environment=` set therefore gains it, the one admitted difference of Step 5, and `test_the_unit_and_its_environment_file_set_every_name_the_script_reads` holds the set with it.
- A premise the tree cannot prove: `DynamicUser=true` with `ProtectSystem=strict` leaves `/usr/local/lib` readable to the unit's user, `strict` mounting it read-only, which a read needs no more than; R-X's first read, the owner's host line before the converge, proves it on the node, and the unit carries no `InaccessiblePaths=` or `ReadOnlyPaths=` line, which the test holds.

- [ ] **Step 1: Keep the node's three rendered files and the script's output lines at this plan's base** — the unit, the env file and the timer into `.tmp/00122/selfcheck-before/`, and `tests/test_mon_selfcheck.py`'s expected `selfcheck:` lines are already literal in the test.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The module, the task file, the templates, the `mon` script and include, the deletions, the walker; then load `zcrypto-refine-rules` and re-point the `drills-telemetry.md` citation**
- [ ] **Step 5: The comparison** — the three files rendered through the include into `.tmp/00122/selfcheck-after/`, `diff -r` ignoring comment lines; Expected: the unit's one added `Environment=PYTHONPATH=…` line and nothing else.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_node_common.py tests/test_mon_selfcheck.py tests/test_infra_mon_role.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'zcrypto-mon-selfcheck\|zcrypto_selfcheck\|roles/node_common' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py` for the unit's description.
- [ ] **Step 8: The commit gate**, then commit — `refactor(infra): the self-check's loop, ping discipline and units become shared, the node's script keeping its three probes and its output`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations over `files/zcrypto_selfcheck.py` (a failing probe still pinging; the ping URL printed in the verdict; a non-zero exit on a failure; an unreadable endpoint hiding the other readings) and over `templates/selfcheck.service.j2` (`EnvironmentFile` dropped; `DynamicUser` off), each probe both `tests/test_mon_selfcheck.py` and `tests/test_infra_node_common.py`; and over `roles/mon/tasks/main.yml` (a `T0218` planted in the include's `selfcheck_description`), the probe `tests/test_internal_terms_not_operator_visible.py`.

---

### Task 5: `node_common`'s SQLite backup timer — `zcrypto-sqlite-backup`, nightly `VACUUM INTO` through an optional runner, a copy out, a prune and a gauge

**Files:**
- Create: `infra/ansible/roles/node_common/files/zcrypto-sqlite-backup.sh` (arguments: the database path and the staging directory as the runner sees them, the host-side destination directory, the keep-days, the gauge's textfile path; environment: `SQLITE_BACKUP_RUNNER`, a command prefix, empty on a host that reads the file itself, `docker compose -f <compose> exec -T web` on the clone, and `SQLITE_BACKUP_COPY`, the copy command for a runner that is a container, `docker compose -f <compose> cp web:<staged> <dest>`; the staging directory created and the `VACUUM INTO` run by one `$RUNNER python3 -c`, `os.makedirs(…, exist_ok=True)` first, so the runner's uid owns both, with the two paths passed as `sys.argv`, never interpolated into the SQL; the file named `<name>-<UTC date and time>.sqlite`, so a second run on one date writes a new file where `VACUUM INTO` refuses an existing one; the host-side destination created `0700` if absent, since the copies carry the database, and the copy into `<dest>/`; the prune of both directories past the keep-days by the date in the file's name, the staging directory's through the runner; the gauge `zcrypto_sqlite_backup_last_success_timestamp_seconds{db="<name>"}` written by tmp-and-rename on success alone; a failure logs at `ERROR` and exits non-zero, so the timer's unit goes red and the gauge stays, which the rule reads)
- Create: `infra/ansible/roles/node_common/tasks/sqlite-backup.yml` (install the script; render the service with the arguments and the two environment lines; render the timer with `sqlite_backup_on_calendar`; enable under the preview gate), `templates/sqlite-backup.service.j2`, `templates/sqlite-backup.timer.j2`
- Modify: `infra/ansible/roles/node_common/defaults/main.yml` (`sqlite_backup_name`, `sqlite_backup_db`, `sqlite_backup_staging`, `sqlite_backup_dest`, `sqlite_backup_keep_days: 14`, `sqlite_backup_runner: ""`, `sqlite_backup_copy: ""`, `sqlite_backup_on_calendar: "*-*-* 02:47:00"`, `sqlite_backup_textfile`)
- Test: `tests/test_infra_node_common.py` (the script driven in a scratch directory, neither the staging nor the destination directory present beforehand, with an empty runner over a real SQLite file: the backup file a valid database equal in content to the source; a staged file older than the keep-days pruned and a newer one kept; the gauge's line and its atomic write; a runner that fails leaving the gauge as it was and exiting non-zero; a copy that fails after a clean `VACUUM INTO` leaving the gauge as it was and exiting non-zero; a stub runner mapping the staging path to a directory of its own, the staging prune shown to run through it; two runs on one date writing two files; a runner prefix exercised through a stub command on `PATH` that records its arguments and holds the SQL's paths out of the command line; the unit's `ExecStart` and the timer's `OnCalendar` rendered)

**Interfaces:**
- Consumes: Python 3's `sqlite3` module on Debian 13 (`VACUUM INTO` needs SQLite 3.27, the host's reads 3.46 or above); the textfile directory the host's Alloy reads.
- Produces, for Tasks 9 and 14: the include `tasks_from: sqlite-backup` with its variables; the gauge name `zcrypto_sqlite_backup_last_success_timestamp_seconds`.

**What this task decides:**
- The staging directory is inside the database's own tree so that, on the clone, the file is written by the container's uid and never by root beside the live `-wal` and `-shm` (spec D10); the host-side copy is what Linode Backups and a restore read.
- The script takes the runner as a parameter: on the clone the runner is the compose exec and the copy a compose `cp`; an empty runner reads a database the host holds itself, the form the tests drive; no second node adopts it here (spec Out of scope).

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

### Task 7: The parametrised guards — the push's node-only groups and the daily pass's patch-pass table

**Files:**
- Modify: `infra/scripts/grafana-push.sh` (`skip_default` becomes the space-separated list `zcrypto-mon zcrypto-hc`; the refusal of a Grafana Cloud push reads each name of the list against `GRAFANA_SKIP_RULE_GROUPS` and names the one missing)
- Modify: `tests/test_grafana_push_sh.py` (`test_the_committed_default_skips_the_observability_nodes_group_on_grafana_cloud_and_no_group_elsewhere` held over both names; a push to Grafana Cloud with `GRAFANA_SKIP_RULE_GROUPS=zcrypto-mon` refused, its message naming `zcrypto-hc`; the existing runs case's `"other zcrypto-mon"` refused now, and a value naming both groups running)
- Modify: `tests/test_infra_alert_rules.py` (`_MON_GROUP` becomes `NODE_ONLY_GROUPS = {"zcrypto-mon": "zcrypto-mon", "zcrypto-hc": "zcrypto-hc"}`; `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` holds, per group, that a rule names its host in a `host` matcher exactly when it is in that group, and that no rule outside both names either host; the `zcrypto-hc` group is empty until Task 14, which the test admits; `test_the_push_keeps_the_mon_group_off_grafana_cloud_by_default` held to both groups; `test_ingest_dark_pages_ahead_of_every_per_host_alloy_dark_rule`'s `per_host` filter reading `NODE_ONLY_GROUPS` in place of `_MON_GROUP`, so the node's own alloy-dark rule stays out of its count of eight)
- Modify: `infra/scripts/ops_daily.py` (`MON_NODE` and `MON_PATCH_RUNBOOK` become `PATCH_PASSES = (("zcrypto-mon", "infra/runbooks/mon.md#mon-patch-pass"),)`, the reminder loop over it, each reminder named `<host> patch pass`; the `zcrypto-hc` row joins it in Task 14, beside the anchor it cites, since `tests/test_ops_daily.py::test_every_runbook_citation_the_instrument_itself_prints_resolves` reads every citation in the module's source)
- Modify: `tests/test_ops_daily.py` (the reminder cases parametrised over the table; a host with no full converge on record owes nothing, per host)

**Interfaces:**
- Consumes: the push script's `case " ${GRAFANA_SKIP_RULE_GROUPS} " in` form; `ops_daily.last_full_converge`.
- Produces, for Task 14: `NODE_ONLY_GROUPS`; `PATCH_PASSES`.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The two edits**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_grafana_push_sh.py tests/test_infra_alert_rules.py tests/test_ops_daily.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `grep -rl 'grafana-push.sh\|ops_daily\|ops-daily' tests/ | sort`, every file it lists.
- [ ] **Step 6: The commit gate**, then commit — `refactor(scripts): the push's node-only groups and the daily pass's patch-pass reminders become tables a second node joins`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: the second group dropped from `skip_default`; the refusal reading the first name alone, which the `zcrypto-mon`-alone case kills; a rule naming `zcrypto-hc` outside its group admitted.

Then the first pull request opens through the `open-pr` skill over Tasks 1 to 7, a different agent reads the branch, and `merge-pr` merges it; the rollout's R-X converges `zcrypto-mon` from merged `develop` and reads `changed=0` before Task 8's pull request opens.

---

### Task 8: The node joins the fleet — inventory, key, the hand-kept lists, the fleet page

**Files:**
- Create: `infra/ansible/files/deploy_zcrypto-hc_ed25519` (vault-encrypted) and `.pub` (the owner's P1, in `docs/plans/00121-mon-node.md`'s O0 form, before Step 1; committed by this task)
- Create: `infra/ansible/group_vars/hc_host/vars.yml` (copied from `group_vars/mon_host/vars.yml`: `ansible_user`, `ansible_port`, `hardening_ssh_allow_users`, `hardening_extra_sysctl` with the two kernel keys and `net.ipv4.ip_forward: 1`, since Docker runs here, `firewall_extra_tcp_ports: [443]`)
- Create: `infra/ansible/host_vars/zcrypto-hc/vars.yml` (`ansible_host`, `base_hostname: zcrypto-hc`, `base_unattended_upgrades_reboot_time: [[ROLLOUT: a slot the base role's collision assert admits, an hour from every other host's and 1 h from each 4 h boundary — 10:25 is the candidate, read against the taken slots at Step 1]]`, `base_unattended_upgrades_automatic_reboot: "false"`, `deploy_authorized_key`, `hc_admin_email`, the owner's own mailbox (spec Open question 4), asked of the owner at Step 1, `hc_email_from: z-no-reply@zhaow.pro` (the same answer), `hc_selfcheck_healthcheck_url: ""` until Task 12; `hc_email_host` is P3's to add)
- Modify: `infra/ansible/inventory/hosts.yml` (`observed` gains `hc_host`; the group before `workstation:`), `bootstrap.yml` (the first play's hosts `capture_host:cache_host:mon_host:hc_host`), `site.yml` (the node's play appended: `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker` and `hc`, each under its own tag; the charter note), `scripts/converge.sh` (`HOSTS`, `TAGNAMES` gains `hc`, `EVKEYS` gains `hc_image_tag`), `scripts/run.sh` (`KEYS`), `files/README.md`, `roles/base/tasks/main.yml` (`base_fleet_hosts` gains `groups['hc_host']`, as `docs/plans/00121-mon-node.md`'s Task 1 added `mon_host`, so the collision assert reads the node's slot)
- Modify: `infra/scripts/count-list.sh` (`c_attended_hosts_with_automatic_reboot`'s loop gains `zcrypto-hc:hc_host`, in the task that creates the two files it reads, since the counter counts a host with the key in neither), `infra/scripts/deploy-log-audit.py` (`NO_VENUE_EXPOSURE` gains `zcrypto-hc`), `infra/scripts/ops_daily.py` (the two alias maps gain `zcrypto-hc`/`hc`; `_TELEMETRY_HOSTS` gains it; a third allowlist in `_classify_one`, the node's Alloy alone, since the service's container is restarted by `hc.md`'s procedure), `infra/external-systems.md` (the `Host hc` stanza, port 10022, `deploy_zcrypto-hc_ed25519`), `docs/reference/fleet.md` (a Hosts row; the Reboots bullet's count clause), `infra/grafana/notification-templates/zcrypto-slack.tmpl` (the host name `zcrypto-hc` shown as `Dead-man`)
- Test: `tests/test_run_sh.py`, `test_converge_sh.py`, `test_infra_converge_guards.py`, `test_infra_unattended_upgrades.py` (`SLOT_GROUPS` gains `hc_host`; `test_the_collision_assert_reads_the_cache_group`'s groups gain it), `test_infra_firewall_template.py` (the opener files), `test_pins_converged.py`, `test_deploy_log_audit.py`, `test_ops_daily.py`, `test_fleet_contracts.py`, `test_count_list.py` (the attended-hosts loop held to five)

**Interfaces:**
- Consumes: every contract `docs/plans/00121-mon-node.md`'s Task 1 widened for `zcrypto-mon`, each gaining one more host by the same case; `tests/test_infra_unattended_upgrades.py`'s slot read.
- Produces, for Tasks 9 to 14 and the rollout: the group `hc_host`; the `converge.sh` host `zcrypto-hc`, tag `hc` and key `hc_image_tag`; the alias `hc`; the fleet page's row.

**What this task decides:**
- `converge.sh` admits `--limit zcrypto-hc`, `--tags hc`, `--tags hc -e hc_image_tag=v6.0.0` and a fresh node's first converge, `--tags base,hardening,firewall,fail2ban,chrony,docker -e daemon_json_ack=true`; `hc_host` stays refused as a limit.
- The node runs Docker, so `net.ipv4.ip_forward` is the fleet default and not the node's exception, and `tests/test_infra_firewall_template.py`'s opener holds `[443]`.

- [ ] **Step 1: P1's two key files are in the tree, the slot is read, and the owner's mailbox is asked** — `ls infra/ansible/files/deploy_zcrypto-hc_ed25519{,.pub} | wc -l` prints `2`; `grep -rh 'base_unattended_upgrades_reboot_time' infra/ansible/host_vars infra/ansible/group_vars | sort` lists the taken slots, and the chosen slot is an hour from each; the address for `hc_admin_email` is the owner's answer.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The files**
- [ ] **Step 5: Run the tests** — the ten test files named above.
- [ ] **Step 6: The consumers** — `grep -rl 'hosts.yml\|converge.sh\|run.sh\|external-systems\|fleet.md\|NO_VENUE_EXPOSURE\|_TELEMETRY_HOSTS\|count-list\|base/tasks' tests/ | sort`, every file it lists.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): the dead-man node joins the fleet's inventory, key ring, host lists and fleet page`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: the host dropped from `NO_VENUE_EXPOSURE`; the slot moved onto another host's; the group added under `engine_host`; `hc_host` dropped from `base_fleet_hosts`; `zcrypto-hc` dropped from the attended-hosts loop.

---

### Task 9: The `hc` role — the shared includes, the pinned container, its env file, its unit, the superuser, the backup, the node's Alloy

**Files:**
- Create: `infra/ansible/roles/hc/defaults/main.yml` (`hc_hostname: zcrypto-hc.zhaow.me`, `hc_acme_email`, the address `mon_acme_email` carries, `hc_image: ghcr.io/zhaow-de/healthchecks`, `hc_compose_dir: /opt/zcrypto-hc`, `hc_port: 8000`, `hc_volume: hc-data`, `hc_email_host: ""`, `hc_email_port: 587`, SES's STARTTLS port, `hc_email_from: ""`, `hc_backup_dir: /var/backups/zcrypto-hc`, `hc_backup_keep_days: 14`, `hc_textfile_dir: /var/lib/zcrypto-node-textfile`, `hc_admin_email: ""`, `hc_selfcheck_healthcheck_url: ""`; no `hc_image_tag` default)
- Create: `infra/ansible/roles/hc/tasks/main.yml` (in order: the two secrets preflight includes of the block below, each AWS shape re-trued at P3 from the credential's own form; the compose directory; the pinned-image block copied from the cache role's and re-worded from a digest to a tag — `refuse an Alloy digest that is not a full sha256` becoming the refusal of an `hc_image_tag` not shaped `v[0-9]+\.[0-9]+\.[0-9]+\Z`, the unpulled-image probe `docker image inspect` over `{{ hc_image }}:{{ hc_image_tag }}`, the running-image probe on `zcrypto-hc`, the pins recording against `fleet-pins.md` reading the running tag, `pins_override`'s echo; `hc.env` rendered `0600 root:root`, `no_log`, `diff: false`; the compose file; the unit; `enable + start` under the preview gate; `admin.yml` included outside check mode; the textfile directory; the `edge`, reboot-check, self-check and backup includes of the block below; the Alloy repository, package, `/etc/default/alloy` from `templates/alloy-env.j2` with the three `MON_PROM_*` and three `MON_LOKI_*` names, rendered `no_log` with `diff: false` as the access role renders its own, `files/config.alloy` validated, `alloy enabled + started`)
- Create: `infra/ansible/roles/hc/tasks/admin.yml` (first a wait on the image's own health check, `docker inspect zcrypto-hc --format '{{.State.Health.Status}}'` repeated `until` it reads `healthy`, 60 tries 5 s apart, since the unit's start returns before the container exists and the image runs `migrate` at start; then a probe through `docker compose exec -T web ./manage.py shell -c` printing `absent`, `ok` or `drifted` by `User.objects.filter(email=…)` and `check_password`; one write creating the superuser or setting the password, `changed` on either, `no_log` on both; the email and the password on the command module's `stdin`, one per line, which the program reads from `sys.stdin` — never the task's `environment:`, which Ansible prepends to the remote shell's command line, where sudo logs it)
- Create: `infra/ansible/roles/hc/handlers/main.yml` (`restart hc service` under the preview gate), `templates/compose.yaml.j2` (the one service `web`, `image: "{{ hc_image }}:{{ hc_image_tag }}"`, `container_name: zcrypto-hc`, `restart: unless-stopped`, `ports: ["127.0.0.1:{{ hc_port }}:8000"]`, `env_file: [./hc.env]`, `volumes: ["{{ hc_volume }}:/data"]`, journald logging, the named volume declared), `templates/hc.env.j2` (the names the clone's `docker/` directory and `hc/settings.py` read, taken at Step 1: the secret key, the site root, the allowed host, debug off, the email host, port, TLS flag, user, password and sender, the database path, the proxy-header setting), `templates/zcrypto-hc.service.j2` (the cache unit's shape over `hc_compose_dir`), `templates/alloy-env.j2` (the access role's shape with the six `MON_*` lines and no `GRAFANA_*` line), `files/config.alloy` (the node's shape: the unix exporter's six collectors with the textfile directory, the self exporter, the journal source keeping the four units of spec D12 and neither `caddy` nor the container's stream, whose lines carry the ping key in request paths, `loki.process "parse"`, one `prometheus.remote_write "mon"` and one `loki.write "mon"` reading the six names, `host = "zcrypto-hc"`)
- Test: `tests/test_infra_hc_role.py` (on `role_render`: the compose file's service held whole; the env file's names held equal to the set Step 1 recorded and carrying none of the secrets' values; the unit's `ExecStart`, `Restart` and `WorkingDirectory`; the preflight's refused cases through `assert_preflight` over both of the role's lists, `hc_selfcheck_healthcheck_url` admitted empty; the pinned-image block's three guards held as `tests/test_infra_converge_guards.py` holds the cache role's; the `edge` include's and the five `node_common` includes' variables equal to the block below; `admin.yml` skipped in check mode, its first task the health wait, its probe and write `no_log`, each carrying `stdin` naming the two variables, no `environment:`, and no value on its command; the Alloy config's `host` label, its journal matcher naming the four units and neither `caddy` nor the container, its one endpoint per plane reading the six names, held with `tests/test_infra_alloy_series.py`'s template-config case at rendered minus read equal to `{"CONFIG_FILE", "CUSTOM_ARGS"}`, the apt unit's own; the `/etc/default/alloy` render `no_log`; the reboot-check unit's textfile directory, rendered through the include, equal to the directory `files/config.alloy`'s textfile collector reads, as `tests/test_reboot_check.py` holds the observability node's; the play's seven roles, each under its own tag)
- Test: `tests/test_infra_alloy_series.py` (the template-config case parametrised over the `hc` pair with its two unread names), `tests/test_deploy_log_audit.py` (the venue-name walk over the three new roles), `tests/test_infra_converge_guards.py` (the preview-register case over `hc`)

**Interfaces:**
- Consumes: Tasks 2 to 5's includes; Task 8's group and host vars; the cache role's pinned-image block; the access role's `alloy-env.j2`; the clone's `docker/docker-compose.yml`, `docker/.env.example` or equivalent, `docker/uwsgi.ini` and `hc/settings.py`, read at Step 1 for the env names, the proxy-header setting and the notifier's command line (spec D17).
- Produces, for Tasks 10 to 14 and the rollout: `hc_hostname`; the container `zcrypto-hc`; `/opt/zcrypto-hc/compose.yaml`; the self-check's two environment names; the backup's gauge; the node's series under `host="zcrypto-hc"`.

**What this task decides:**
- The clone's own `docker-compose.yml` is not copied onto the node: the role renders its own compose file so the version pin, the loopback bind and the env file are the fleet's shape, and the clone's file is read for its service's needs alone.
- No host account is created: the image runs as its own uid 100 (spec D10), the compose names no `user:`, and the volume is the image's.
- The superuser's email is plain and the password vaulted; `admin.yml` is the clone's counterpart of the node's `token.yml`, skipped whole in a preview, and its `shell -c` program is a one-line Python string in the task file, read by the test for its reads of `sys.stdin` and the absence of any literal.
- The shared preflight is included twice: over the vault's four values, and over the plain values `hc.env` and the self-check read, so an SES endpoint P3 has not written fails by name before a `no_log` render; the second list admits an empty `hc_selfcheck_healthcheck_url` until Task 12 drops the empty arm, so R3 to R7 converge before any ping URL exists.
- No play lists `edge`; the includes, with their variables, in the role's order:

```yaml
- name: the vault's values, refused by shape before any no_log render
  ansible.builtin.include_role: {name: node_common, tasks_from: secrets-preflight}
  vars:
    node_common_role_name: hc
    secrets_preflight_file: host_vars/zcrypto-hc/vault.yml
    secrets_preflight_runbook: infra/runbooks/hc.md's hc-secrets procedure
    secrets_preflight:
      - {key: hc_secret_key, shape: '[0-9a-f]{64}\Z'}
      - {key: hc_admin_password, shape: '[0-9a-f]{48}\Z'}
      - {key: hc_email_host_user, shape: '[A-Z0-9]{16,}\Z'}
      - {key: hc_email_host_password, shape: '[A-Za-z0-9+/=]{40,}\Z'}
- name: the plain values the env file and the self-check read, refused by shape
  ansible.builtin.include_role: {name: node_common, tasks_from: secrets-preflight}
  vars:
    node_common_role_name: hc
    secrets_preflight_file: host_vars/zcrypto-hc/vars.yml
    secrets_preflight_runbook: infra/runbooks/hc.md's hc-secrets procedure
    secrets_preflight:
      - {key: hc_email_host, shape: 'email-smtp\.[a-z0-9-]+\.amazonaws\.com\Z'}
      - {key: hc_email_from, shape: '[^@\s]+@[^@\s]+\Z'}
      - {key: hc_admin_email, shape: '[^@\s]+@[^@\s]+\Z'}
      - {key: hc_selfcheck_healthcheck_url, shape: '(https://zcrypto-hc\.zhaow\.me/ping/[A-Za-z0-9_-]{16,}/[a-z0-9-]+)?\Z'}
- name: the edge in front of the service on loopback
  ansible.builtin.include_role: {name: edge}
  vars:
    edge_role_name: hc
    edge_hostname: "{{ hc_hostname }}"
    edge_acme_email: "{{ hc_acme_email }}"
    edge_basic_auth_routes: []
    edge_paths_404: []
    edge_head_paths: []
    edge_session_cookie: ""
    edge_upstream_port: "{{ hc_port }}"
- name: the reboot check
  ansible.builtin.include_role: {name: node_common, tasks_from: reboot-check}
  vars:
    node_common_role_name: hc
    reboot_check_textfile_dir: "{{ hc_textfile_dir }}"
- name: the self-check
  ansible.builtin.include_role: {name: node_common, tasks_from: selfcheck}
  vars:
    node_common_role_name: hc
    selfcheck_name: zcrypto-hc-selfcheck
    selfcheck_script: zcrypto-hc-selfcheck.py  # the role's own file, passed in the form Task 4's mon include passes its own
    selfcheck_description: Ping the dead-man service's own check while its web answers, its notifier runs and a ping is stored
    selfcheck_timer_description: Every-5-minutes self-check of the dead-man service
    selfcheck_environment:
      HC_SELFCHECK_STATUS: "http://127.0.0.1:{{ hc_port }}/api/v3/status/"
      HC_SELFCHECK_HOST: "{{ hc_hostname }}"
    selfcheck_env_var: HC_SELFCHECK_HEALTHCHECK_URL
    selfcheck_env_value: "{{ hc_selfcheck_healthcheck_url }}"
    selfcheck_on_calendar: "*:0/5:23"
- name: the nightly backup
  ansible.builtin.include_role: {name: node_common, tasks_from: sqlite-backup}
  vars:
    node_common_role_name: hc
    sqlite_backup_name: hc
    sqlite_backup_db: /data/hc.sqlite
    sqlite_backup_staging: /data/backups
    sqlite_backup_dest: "{{ hc_backup_dir }}"
    sqlite_backup_keep_days: "{{ hc_backup_keep_days }}"
    sqlite_backup_runner: "docker compose -f {{ hc_compose_dir }}/compose.yaml exec -T web"
    sqlite_backup_copy: "docker compose -f {{ hc_compose_dir }}/compose.yaml cp web:"
    sqlite_backup_textfile: "{{ hc_textfile_dir }}/sqlite-backup.prom"
```

- [ ] **Step 1: Read the clone's contract** — `git clone --depth 1 --branch v6.0.0 https://github.com/zhaow-de/healthchecks .tmp/00122/healthchecks`, removed after Step 9; record in the task's commit message the env names `docker/` reads, the `SECURE_PROXY_SSL_HEADER` setting's name, the `uwsgi.ini` daemon lines and the notifier's command line the self-check matches, the status view's body and its allowed host, the read-only listing's fields (`status`, `n_pings`, `last_ping`, `timeout`, `schedule`, `tz`), a never-pinged check's status and its `hc_check_up`, and the HTTP methods that record a ping; the spec's D17 premises are confirmed or corrected here, a correction being a spec amendment in this commit.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The role**
- [ ] **Step 5: Dry-start `files/config.alloy`** in `docs/plans/00121-dual-shipping.md`'s dry-start form (its Global Constraints) against the `1.20` release binary, the six names set to dummies and the journal path at an empty directory; Expected: up, `/-/ready` 200, no `level=error` line.
- [ ] **Step 6: Run the tests** — `uv run pytest tests/test_infra_hc_role.py tests/test_infra_alloy_series.py tests/test_deploy_log_audit.py tests/test_infra_converge_guards.py tests/test_infra_edge_role.py tests/test_infra_node_common.py -q -p no:cacheprovider`
- [ ] **Step 7: The consumers** — `grep -rl 'roles/hc\|roles/edge\|roles/node_common\|config.alloy\|alloy-env.j2' tests/ infra/ .claude/ | sort`, every test file it lists, and `tests/test_internal_terms_not_operator_visible.py`.
- [ ] **Step 8: The commit gate**, then commit — `feat(infra): the hc role — the dead-man service as one pinned container behind the shared edge, with the shared preflight, reboot check, self-check and backup`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record the verdicts** — mutations: the env file rendered without `no_log`; the compose binding `0.0.0.0`; the tag's shape refusal loosened; `admin.yml`'s two values moved from `stdin` to the task's `environment:`; the health wait dropped; one shape's `\Z` removed in the role's first preflight list; the `edge` include given a route; a `GRAFANA_` line in `alloy-env.j2`; `host` changed in `config.alloy`; `caddy` added to the journal matcher.

---

### Task 10: The clone's self-check — three probes over the shared loop

**Files:**
- Create: `infra/ansible/roles/hc/files/zcrypto-hc-selfcheck.py` (`web_up(status_url, host, opener)`: the request carrying `Host: <host>`, since the clone refuses any other host, then a 200 and the body `OK`; `notifier_alive()`: the processes under the module's `PROC`, `/proc`, whose `cmdline` carries the notifier's command line recorded at Task 9's Step 1, a process gone mid-read skipped, printing the count and never a command line — the unit's dynamic user may read `/proc`, where the docker socket refuses it; `ping`: the shared loop's own, the write probe; `main` calling `zcrypto_selfcheck.run` with `ping_var="HC_SELFCHECK_HEALTHCHECK_URL"`)
- Create: `tests/test_hc_selfcheck.py` (on `selfcheck_driver`, its opener stub answering the status URL `OK` only with the `Host` header and 400 without it: a healthy clone pings and says what it read; each failing probe withholds the ping and exits 0, the other reading still taken; the loaded module's `PROC` pointed by the test at a scratch tree of `<pid>/cmdline` files, the notifier's absence a `FAIL`; the ping URL and every command line never in the output; the unit's environment names equal to the script's reads through the include's variables)

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
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: the notifier probe always true; a 500 status read as up; the `Host` header dropped; a command line printed.

Then the rollout's P2 and P3 add their commits, the second pull request opens over Tasks 8 to 10 with them, and R0 to R7 and P4 follow its merge.

---

### Task 11: `hc-provision.py` — the twelve checks from healthchecks.io's listing to the clone, idempotently, the fixture from the clone, and the move's read

**Files:**
- Create: `infra/scripts/hc-provision.py` (`plan`, `apply [--from-fixture]`, `fixture`, `status`, `retire`; the source `https://healthchecks.io/api/v3/checks/` read with `healthchecks_readonly_api_key` from `group_vars/all/vault.yml`; the target `https://zcrypto-hc.zhaow.me/api/v3/` with `hc_readwrite_api_key` from `group_vars/all/vault.yml` for writes and `hc_readonly_api_key` from `group_vars/observed/vault.yml` for the fixture read; `ZCRYPTO_HC` the definition of the clone's own check, name `zcrypto-hc`, tags `hc selfcheck`, `timeout 600`, `grace 600`, its description citing `Runbook: infra/runbooks/hc.md#hc-dark`; per check the body `{name, slug: name, tags, desc, grace, channels: <id>, unique: ["name"]}` with the source's `timeout`, or its `schedule` and `tz` on a cron check; the channel id from `GET channels/` matched by kind `slack`, one and only one, else a refusal; `plan` printing names, slugs, the period (`timeout`, or `schedule` and `tz`) and grace, then `ops_daily.check_descriptions`' findings over the twelve or `descriptions: no finding`, and no key; `apply` writing, then reading each check back and exiting 2 naming the check whose `timeout`, `grace`, `schedule` or `tz` differs from its source, its source healthchecks.io's listing or, with `--from-fixture`, the fixture's definitions, the one source left after retirement; `fixture` writing `tests/fixtures/healthchecks_descriptions.json` sorted by name, each check's `name`, `tags`, `desc`, `grace` and its `timeout` or `schedule` and `tz`; `status` printing per check the clone's `status`, `n_pings` and `last_ping`, healthchecks.io's `last_ping` while its key reads, and `moved` for a clone check with `n_pings` above 0 and status `up`; `retire` refusing, naming each check that fails, unless all twelve on the clone read `moved`, no healthchecks.io check it would delete has a `last_ping` in the last 24 hours, and the fixture equals the clone's listing, then reading healthchecks.io's checks with `healthchecks_api_key` from `group_vars/capture_host/vault.yml` and deleting the eleven the fixture names besides `zcrypto-hc`, by uuid, leaving any other check, printing name and status per delete; every request with a 30 s timeout; a refused or malformed answer ending the run at exit 2 naming the endpoint and never a key)
- Create: `tests/test_hc_provision.py` (`urllib.request.urlopen` and `grafana_auth.vault_var` stubbed as `tests/test_grafana_query.py`'s `_Recorded` does: the twelve bodies from an eleven-check source plus the constant; `unique` on every create; the channel id attached; a cron source written with its `schedule` and `tz` and no `timeout`; a read-back whose `grace` differs ending at exit 2 naming the check; `--from-fixture` writing the same twelve bodies as the source the fixture was fetched from; two Slack channels refused; the fixture's keys the definitions' and its order by name; `plan` printing a description finding; `status` reading a `new` check unmoved and a pinged `up` one moved; `retire` refusing twelve names with one `new`, refusing twelve moved with one healthchecks.io check pinged an hour ago, refusing a fixture that differs from the clone's listing, and with all three held deleting the eleven by name and leaving a twelfth, non-fleet healthchecks.io check alone; the keys absent from stdout; a 500 ending at exit 2 with the endpoint named)
- Modify: `tests/test_ops_daily.py` (`test_the_healthchecks_fixture_carries_no_key_the_read_only_fetch_never_returns` admitting the definitions' keys, each one the read-only listing returns)

**Interfaces:**
- Consumes: `grafana_auth.vault_var(name, vault_file)`; `ops_daily.check_descriptions` for the `plan` output's description check, run over the twelve before `apply`; the clone's v3 endpoints of item 3.
- Produces, for the rollout: `uv run python infra/scripts/hc-provision.py plan|apply [--from-fixture]|fixture|status|retire`.

**What this task decides:**
- The fixture's `zcrypto-hc` entry comes from the clone's listing like the others, never written by hand, so the script's constant and the fixture agree through the clone.
- `retire` is a separate verb with its own precondition rather than a flag of `apply`, so a mis-typed flag cannot delete.
- `status` is the one per-check read of a move, since a never-pinged check reads `new` on the clone, which its metrics report as up and count in no total; `retire`'s precondition is `status`'s verdict over all twelve, so the two cannot disagree.
- The fixture keeps the definitions, so the tree holds the twelve checks' periods after healthchecks.io's account is closed (spec D10), and `retire`'s equality read keeps it current up to the one-way step.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_hc_provision.py tests/test_scripts_have_tests.py tests/test_error_paths_are_logged.py tests/test_code_prose_citations.py -q -p no:cacheprovider`
- [ ] **Step 5: The consumers** — `tests/test_ops_daily.py` (the fixture contract), `tests/test_prose_chars.py`, `tests/test_internal_terms_not_operator_visible.py`.
- [ ] **Step 6: The commit gate**, then commit — `feat(scripts): hc-provision.py creates the fleet's checks on the dead-man service from healthchecks.io's own listing and refreshes the fixture from it`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guards, then record the verdicts** — mutations: `unique` dropped; `retire` proceeding with a `new` check; `retire` deleting every healthchecks.io check rather than the fixture's eleven; the read-back comparison skipped; `schedule` dropped from a cron body; a key printed on a refusal; the fixture written with `unique_key`.

---

### Task 12: The pingers' URL scheme — one key, one base, twelve slugs, the shapes, the redactor's case, the daily pass's curl guard

**Files:**
- Modify: `infra/ansible/group_vars/observed/vars.yml` (`hc_hostname: zcrypto-hc.zhaow.me`, `hc_ping_base: "https://{{ hc_hostname }}/ping/{{ hc_ping_key }}"`, `hc_metrics_path: "/projects/{{ hc_project_uuid }}/metrics/"`, beside the `hc_project_uuid` P5 wrote; P5 alone writes the three new vault keys, the uuid and the `all` vault's header counts)
- Modify, the key line alone and never a value: `group_vars/capture_host/vault.yml` and `host_vars/zcrypto-red/vault.yml` (`capture_healthcheck_url` renamed `hcio_capture_healthcheck_url`), `group_vars/engine_host/vault.yml` (`engine_healthcheck_url` renamed `hcio_engine_healthcheck_url`), `host_vars/nas/vault.yml` (`nas_gate_healthcheck_url` renamed `hcio_nas_gate_healthcheck_url`) — the four whose vaulted name is the name the template reads, which the `vault.yml` beside each new `vars.yml` line would otherwise win over, since Ansible loads a directory's files in name order; the comments naming the four re-trued, `host_vars/nas/vars.yml`'s two among them
- Modify: `infra/ansible/group_vars/capture_host/vars.yml` (`capture_healthcheck_url: "{{ hc_ping_base }}/zcrypto-capture"`), `host_vars/zcrypto-red/vars.yml` (`…/zcrypto-capture-red`), `group_vars/engine_host/vars.yml`, a new file (`engine_healthcheck_url: "{{ hc_ping_base }}/zcrypto-engine-shadow"`), `host_vars/nas/vars.yml` (`nas_gate_healthcheck_url: "{{ hc_ping_base }}/zcrypto-gate-verify"`), `host_vars/zcrypto-ops/vars.yml` (the six, each its check's slug), `host_vars/zcrypto-mon/vars.yml` (`mon_selfcheck_healthcheck_url: "{{ hc_ping_base }}/zcrypto-mon"`, `selfcheck_healthcheck_url` no longer referenced), `host_vars/zcrypto-hc/vars.yml` (`hc_selfcheck_healthcheck_url: "{{ hc_ping_base }}/zcrypto-hc"`)
- Modify: the preflights — the `mon` role's include list drops `selfcheck_healthcheck_url` and gains `mon_selfcheck_healthcheck_url` under the clone's shape `https://zcrypto-hc\.zhaow\.me/ping/[A-Za-z0-9_-]{16,}/[a-z0-9-]+\Z`; the `hc` role's second list the same over `hc_selfcheck_healthcheck_url`, its empty arm dropped; the capture role's defaults comment and the engine role's re-trued; the ops role's defaults comment re-trued
- Modify: the renders that carry a ping URL and predate this plan, each given `no_log: true`, `diff: false` and a mode no other account reads — `roles/capture/tasks/main.yml`'s `render the capture compose file` (`0600`); `roles/ops/tasks/main.yml`'s `render the ops compose file (liquidations poller)`, `install the archive-pull runner script` (`0700`), `install the replay + panel + tape-bars runner scripts` (`0700`), and `install the grafana-watchdog runner script` (`0700`, its `no_log` already set); every unit those scripts run under runs as root
- Modify: `tests/test_logging_redact.py` (a case over `https://zcrypto-hc.zhaow.me/ping/<key>/zcrypto-capture` and its `/fail`: the line carries `zcrypto-hc.zhaow.me` and nothing of the path)
- Modify: `infra/scripts/ops_daily.py` (`_curl_is_read` gains `zcrypto-hc.zhaow.me/ping`), `tests/test_ops_daily.py` (a runbook `curl` of the clone's ping URL classified a write)
- Test: `tests/test_infra_hc_role.py` (a new case holding the twelve slugs — every `*_healthcheck_url` value in a `vars.yml` under `group_vars/` and `host_vars/` rendered through the templar with a dummy key, their last path segment — equal to the set of the fixture's names with `zcrypto-hc` added, and each rendered value matching the preflights' shape; a case holding that no `*_healthcheck_url` name is a key of both a `vars.yml` and a `vault.yml` there, which is what lets the slug case read the vars files alone; a case holding that every `template` task under `infra/ansible/roles/` whose source names a `*_healthcheck_url` variable, a loop's items expanded, carries `no_log: true`, `diff: false` and a mode with no group or other bit, the seven it finds being the capture compose, `engine.env`, the NAS's `.env`, the ops compose, the archive-pull script, the replay-and-panel loop and the grafana-watchdog script; the group vars' hostname equal to the `hc` role's default)

**Interfaces:**
- Consumes: the eleven templates' variable names, unchanged; Task 11's slugs; P5's three vault keys and the uuid.
- Produces, for the rollout: the rendered URLs each host takes at its converge; the four `hcio_` names spec D16's rollback points back at.

**What this task decides:**
- The old vault values stay until retirement under names no template reads: a directory's `vault.yml` loads after its `vars.yml` and wins, so the four whose vaulted name is the template's own are renamed `hcio_<name>` here; the six ops values and the node's are vaulted under names their `vars.yml` wiring does not reuse.
- The shape's key part is widened or narrowed by amendment once P5 has read the minted key's shape, and the same body is passed to `vault-append-secret.sh` at P5.

- [ ] **Step 1: P5's three vault keys and the uuid read present** — `grep -c '^hc_ping_key: !vault' infra/ansible/group_vars/observed/vault.yml`, the same for `hc_readonly_api_key`, `grep -c '^hc_readwrite_api_key: !vault' infra/ansible/group_vars/all/vault.yml`, and `grep -c '^hc_project_uuid: ' infra/ansible/group_vars/observed/vars.yml`; Expected: `1` each; a `0` holds the task.
- [ ] **Step 2: Write the failing tests**
- [ ] **Step 3: Run them and read the failure**
- [ ] **Step 4: The vars, the shapes, the guard, the comments**
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_infra_hc_role.py tests/test_infra_mon_role.py tests/test_logging_redact.py tests/test_ops_daily.py tests/test_infra_firewall_template.py tests/test_infra_compose_templates.py -q -p no:cacheprovider`
- [ ] **Step 6: The consumers** — `grep -rl 'healthcheck_url\|group_vars/observed\|host_vars/zcrypto-ops\|host_vars/nas\|roles/capture\|roles/ops' tests/ | sort`, every file it lists.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): every dead-man ping URL renders from one vaulted project key and its check's slug`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: a slug mistyped; a shape admitting `hc-ping.com`; the redactor keeping the path; the curl guard dropping the clone's host; one renamed vault key restored to its old name, which the both-files case kills; `no_log` dropped from the capture compose render.

---

### Task 13: The readers — the daily pass's API base and key, the ops scrape with a bearer token, the watchdog rule's text, the two panel titles

**Files:**
- Modify: `infra/scripts/ops_daily.py` (`HEALTHCHECKS_API` becomes `DEADMAN_API = "https://zcrypto-hc.zhaow.me/api/v3/checks/"`; `_readonly_key` reads `hc_readonly_api_key` from `group_vars/observed/vault.yml`; the unreadable notes name the service), `tests/test_ops_daily.py` (the URL and key cases; `DEADMAN_API`'s host equal to the `hc` role's default)
- Modify: `infra/ansible/roles/ops/files/config.alloy` (`prometheus.scrape "healthchecks"`: `__address__ = "zcrypto-hc.zhaow.me"`, `bearer_token = sys.env("HC_READONLY_KEY")`, the path still `sys.env("HC_METRICS_PATH")`, its comment re-trued), `roles/ops/templates/alloy-secrets.env.j2` (`HC_METRICS_PATH={{ hc_metrics_path }}`, `HC_READONLY_KEY={{ hc_readonly_api_key }}`, its comment re-trued), `tests/test_infra_alloy_series.py` (the literal case's two lines; the template-config case at `read == rendered` over ops, unchanged in shape; a new case holding the scrape's address, scheme and bearer read)
- Modify: `infra/scripts/count-list.sh` (`c_hc_readonly_key_in_a_role` becomes `git grep -nE 'hc_readonly_api_key' -- infra/ansible/roles ':!infra/ansible/roles/ops/templates/alloy-secrets.env.j2'` over non-comment lines, its comment re-trued, in the task that puts the key in that template), `tests/test_count_list.py` (the entry's exclusion held to the one template)
- Modify: the ops role's operator-read lines naming healthchecks.io, rendered at R9's ops converge: `templates/panel-regenerate.sh.j2`'s two prompts, pausing and un-pausing the panel check on the service, with `tests/test_panel_regenerate.py` where it reads them, and `tasks/main.yml`'s task name `install the grafana-watchdog pinger (mutual watchdog, hc.io half)`, each re-trued to name the service
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-hcio-watchdog`'s title `Fleet · dead-man watchdog (check down, or the service dark)`, its summary and unit naming the service, its uid and expression unchanged), `infra/grafana/fleet-health-dashboard.json` (the two titles and descriptions), `tests/test_infra_alert_rules.py` and `tests/test_dashboards_cover_metrics.py` as they read those texts
- Modify: `infra/runbooks/observability.md` (`zcrypto-hcio-watchdog`'s section re-trued: the service, the one key and step 4's count clause's set text naming the excluded template, step 4's fix as an ops converge with the recreate, step 2 reading the engine's check on healthchecks.io until it moves, step 6's confirm by value naming `hc-provision.py status`, since a never-pinged check reads 1; the dead-man map's row for `zcrypto-hc`)

**Interfaces:**
- Consumes: Task 12's `hc_metrics_path` and `hc_readonly_api_key`; the clone's `/projects/<uuid>/metrics/` with `Authorization: Bearer` (item 4); `tests/test_infra_alloy_series.py`'s literal and template-config cases.
- Produces, for the rollout: the ops converge of R9 and its recreate; the daily pass's `ops-daily.py report` reading the clone.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: Load `zcrypto-refine-rules`**, then the edits.
- [ ] **Step 4: Dry-start the edited ops config** in `docs/plans/00121-dual-shipping.md`'s dry-start form, the two names set to dummies; Expected: up, `/-/ready` 200, no `level=error`.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_ops_daily.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_count_list.py tests/test_panel_regenerate.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py -q -p no:cacheprovider`
- [ ] **Step 6: The consumers** — `docs/plans/00121-dual-shipping.md`'s consumer listing (its Global Constraints), `grep -rl 'alloy-secrets.env\|config.alloy\|alerts.yaml\|fleet-health-dashboard' tests/ | sort`, every file it lists, and the runbook walkers.
- [ ] **Step 7: The commit gate**, then commit — `feat(infra): the daily pass, the ops scrape and the watchdog rule read the dead-man service, the read-only key held once`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record the verdicts** — mutations: the key read from the `all` vault; the scrape's `bearer_token` dropped; the address left at `healthchecks.io`; a `GRAFANA_` line edited; the key named in a second template admitted by the count.

---

### Task 14: The node's rule group, its runbook page and its Fleet health row

**Files:**
- Modify: `infra/grafana/alerts.yaml` (the group `zcrypto-hc`: `zcrypto-alloy-dark-hc`, `zcrypto-hc-disk-low`, `zcrypto-hc-reboot-pending`, `zcrypto-hc-service-down` on the self-check's journal line reading `web=FAIL` or absent 15 minutes, `zcrypto-hc-backup-stale` on the gauge older than 26 h with `noDataState: Alerting`, the last-success shape of `zcrypto-reconcile-exporter-stale`, since a node whose backup never succeeded has no gauge, each with its `Runbook:` citation, panel id and severity in the node's shape)
- Create: `infra/runbooks/hc.md` (the procedures `hc-dark` from `mon-dark` with the host swapped and the two drill figures as slots, `hc-secrets` from `mon-secrets` over the four values of `host_vars/zcrypto-hc/vault.yml` and P2's script, `hc-restore` new, its first half spec D10's one-shot `docker run --rm --network none … ./manage.py shell -c` read with the read-only key piped from the workstation, its second half the live swap, `hc-backup` new, `hc-patch-pass` from `mon-patch-pass` with the image bump through the version pin, the new tag pulled, `-e hc_image_tag=<new>` and the pins row re-trued, `hc-keys` new, the UI-minted keys rotated under sudo mode and re-vaulted through `vault-append-secret.sh --replace`, the converges each takes; the ALERT sections for the five rules, three copied from `mon.md`'s with the host swapped and two new)
- Modify: `infra/grafana/fleet-health-dashboard.json` (a row of five panels), `tests/test_dashboards_cover_metrics.py` (the host map), `tests/test_infra_alert_rules.py` (the group's rules in `NODE_ONLY_GROUPS`' test; `zcrypto-hc-backup-stale`'s `noDataState` held `Alerting`), `infra/scripts/ops_daily.py` (`_UID_HOST` entries for the five; `PATCH_PASSES` gains `("zcrypto-hc", "infra/runbooks/hc.md#hc-patch-pass")` beside the anchor it cites), `tests/test_ops_daily.py` (the reminder cases over the second row)

**Interfaces:**
- Consumes: Task 7's `NODE_ONLY_GROUPS`; Task 9's series; Task 10's journal line; `docs/plans/00121-mon-node.md`'s rule and runbook shapes.
- Produces, for the rollout: `infra/runbooks/hc.md`'s anchors, `hc-dark` among them, which the clone's own check cites before R8's `plan` reads it; the five rules, pushed to the node by `mon.md#mon-push` at R8.

- [ ] **Step 1: Load `zcrypto-refine-rules`**, then write the page and the rules.
- [ ] **Step 2: Run the tests** — `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_ops_daily.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider`
- [ ] **Step 3: The consumers** — `grep -rl 'alerts.yaml\|runbooks/hc\|fleet-health' tests/ | sort`, every file it lists.
- [ ] **Step 4: The commit gate**, then commit — `feat(grafana): the dead-man node's five rules, its runbook page and its Fleet health row`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 5: The tree is clean**
- [ ] **Step 6: Prove the guards, then record the verdicts** — mutations: a rule of the group naming no host; a rule outside it naming `zcrypto-hc`; a section's anchor dropped; `zcrypto-hc-backup-stale`'s `noDataState` set `OK`.

Then the rollout's P5 adds its commit and the third pull request opens over Tasks 11 to 14 with it; R8's provisioning runs from its branch before it merges, and the rest of R8 to R13 follows its merge, one sitting.

---

### Task 15: The drills and the surfaces' sweep

**Files:**
- Modify: `infra/runbooks/drills-telemetry.md` (three sections of seven parts, `drill-x1` the service stopped, `drill-x2` the 30-minute power-off, `drill-x3` the restore's one-shot read then the rebuild from the fetched backup; the standing rules' subject list gains the node; the letter `X` held free by `grep -c '^## Drill X' infra/runbooks/drills-telemetry.md infra/runbooks/drills-order-path.md` reading 0 before the edit)
- Modify: the 116-line sweep — every operator-read line naming `healthchecks.io`, `hc-ping.com` or `hc.io` on the pages the measured basis lists, re-trued to the service by name, `drills-telemetry.md`'s and `observability.md`'s "healthchecks.io's own Slack integration" among them; the drill log untouched; `infra/grafana/alerts.yaml`'s remaining comments; `engine.md`'s three lines and Task 13's step-2 clause in `observability.md` left naming healthchecks.io, since the engine's check stays there until after the box, re-trued by R-records-2

**Interfaces:**
- Consumes: the drill log's entry contract; `mon.md#mon-dark`'s figure-slot shape; Task 14's anchors.
- Produces, for the rollout: `drill-x1` to `drill-x3`, whose readings fill `hc.md#hc-dark`'s two slots (Task 14's).

- [ ] **Step 1: Load `zcrypto-refine-rules`**, then the three sections and the sweep.
- [ ] **Step 2: The count** — the measured basis's sweep command with `git grep -n` in place of `wc -l`; Expected: the lines it lists are `.claude/skills/`'s three, Task 16's, and the engine's dead-man lines R-records-2 re-trues after the engine moves, `engine.md`'s three and `observability.md`'s step 2, and no other.
- [ ] **Step 3: The consumers** — the runbook walkers, `tests/test_drill_log.py`, `tests/test_guidance_guard.py`, `tests/test_guidance_refs_resolve.py`, `tests/test_count_list.py`, `tests/test_infra_alert_rules.py`, `tests/test_dashboards_cover_metrics.py`.
- [ ] **Step 4: The commit gate**, then commit — `docs(runbooks): the dead-man service's three drills, and every operator surface but the engine's re-trued from healthchecks.io to the service`, with the trailer; no guard changes, so no probe.
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

Then the fourth pull request opens over Tasks 15 and 16 once R13 reads clean; it merges before R15, whose drill sections it carries.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step. `W$` is the workstation at the repository root, `H$` a shell on the named host (`ssh hc` once R3 writes the alias; `ssh hp`, `ssh red`, `ssh zcrypto`, `ssh mon`, the NAS by its alias). Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, never wrapped in `timeout`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. A running digest is read off the container, `docker inspect <name> --format '{{.Config.Image}}'`, never `.Image`, and matched against `docs/reference/fleet-pins.md`. No secret is typed on a command line or shown: every UI-minted value goes through `infra/scripts/vault-append-secret.sh`, every generated one through P2's script, and a value reaches a process through `vault_var` inside a command substitution. `.tmp/00122/` holds what a later step reads back. The hc node speaks to no venue, so its own converges owe no Kraken read and fall under no engine gap.

**P1. The deploy keypair** (Task 8's precondition), `docs/plans/00121-mon-node.md`'s O0 form over `deploy_zcrypto-hc_ed25519`, run by the owner before Task 8's Step 1.

**P2. The two generated vault values, by script, none shown.** Run by the owner once Task 10's branch reads clean, with no executor step running and the GPG agent unlocked, from the repository root: `hc_secret_key`, 64 hex characters, since docker compose interpolates a `$` inside an `env_file` value and Django's own generator alphabet carries one, and `hc_admin_password`, 48 hex, each encrypted through `ansible-vault encrypt_string --stdin-name` with no newline into a new `host_vars/zcrypto-hc/vault.yml`, in `docs/plans/00121-mon-node.md`'s P2 shape. The script refuses to run a second time: the `SECRET_KEY` is stable across rebuilds, since every API key's HMAC and every signed link depend on it (item 6).

```bash
(cd infra/ansible && uv run python - <<'PY'
import pathlib
import secrets
import subprocess


def entry(name: str, value: str) -> str:
    done = subprocess.run(
        ["ansible-vault", "encrypt_string", "--stdin-name", name], input=value, capture_output=True, text=True, check=True
    )
    return done.stdout.rstrip() + "\n"


node = pathlib.Path("host_vars/zcrypto-hc/vault.yml")
assert not node.exists(), f"{node} exists: these values are generated once, and a second run would orphan the first"
node.write_text(
    "# host_vars/zcrypto-hc -- SECRETS for the dead-man node. Per-VALUE vault encryption: the variable NAMES stay\n"
    "# readable, every value stays `!vault`-encrypted at rest. The two generated values are made once, by script,\n"
    "# and stable across rebuilds: every API key's HMAC and every signed link depend on the secret key. The SES\n"
    "# SMTP pair is appended by infra/scripts/vault-append-secret.sh. Replacing one: infra/runbooks/hc.md's\n"
    "# hc-secrets.\n"
    "#\n"
    "# NEVER run `ansible-inventory --host/--list` from infra/ansible/: ansible.cfg supplies the vault\n"
    "# password, so both silently print every value below in cleartext.\n"
    "\n"
    + entry("hc_secret_key", secrets.token_hex(32))
    + entry("hc_admin_password", secrets.token_hex(24))
)
print(f"wrote {node} (2 values); nothing was printed")
PY
)
```

Expected: `wrote host_vars/zcrypto-hc/vault.yml (2 values); nothing was printed`. Then the check, which prints booleans alone:

```bash
(cd infra/ansible && uv run python - <<'PY'
import re
import sys

sys.path.insert(0, "../scripts")
from grafana_auth import vault_var

node = "host_vars/zcrypto-hc/vault.yml"
print("hc_secret_key 64 hex characters:", bool(re.fullmatch(r"[0-9a-f]{64}", vault_var("hc_secret_key", node))))
print("hc_admin_password 48 hex characters:", bool(re.fullmatch(r"[0-9a-f]{48}", vault_var("hc_admin_password", node))))
PY
)
git status --porcelain
```

Expected: two lines, each ending `True`; the status names the new file and nothing else. Commit `chore(hc): the dead-man node's two generated vault values`, with the trailer.

**P3. The SES SMTP credential and its endpoint.** In AWS SES, where the sender `z-no-reply@zhaow.pro` is verified already (spec Open question 4), the owner creates an SMTP credential and reads its region's SMTP endpoint, [[ROLLOUT: the SES region's SMTP endpoint, `email-smtp.<region>.amazonaws.com`]], added plain to `host_vars/zcrypto-hc/vars.yml` as `hc_email_host`; then `(cd infra/ansible && ../scripts/vault-append-secret.sh host_vars/zcrypto-hc/vault.yml hc_email_host_user '[A-Z0-9]{16,}')` and the same for `hc_email_host_password` with `[A-Za-z0-9+/=]{40,}`; a credential of another shape re-trues the two shapes in the `hc` role's preflight and here in one commit before it is vaulted. Commit `chore(hc): the SES SMTP credential, vaulted, and its endpoint`, with the trailer.

Then the second pull request opens over Tasks 8 to 10 with P2's and P3's commits; a different agent reads the branch; `merge-pr` merges it. Everything below runs from merged `develop`, R8's provisioning alone excepted.

**R-X. The observability node on the shared code** (after the first pull request merges, before the second opens). First the unit sandbox's read, Task 4's premise, on the node: `H$ sudo systemd-run --wait --pipe --quiet -p DynamicUser=true -p ProtectSystem=strict -p ProtectHome=true -p PrivateTmp=true -p NoNewPrivileges=true /usr/bin/python3 -c 'import os; print(os.access("/usr/local/lib", os.R_OK | os.X_OK))'` prints `True`, a `False` a stop before the converge. Then `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`: the preview names no changed file but these — the Caddyfile, the reboot-check script, unit and timer, and the self-check env file and timer, each for its header comment; the self-check unit for its header and its `PYTHONPATH` line; the self-check script, now importing the module; the new `/usr/local/lib/zcrypto` and its module — and the real pass reads `changed=<those>`, then a second run `changed=0 failed=0`; `ssh mon 'systemctl is-active caddy zcrypto-reboot-check.timer zcrypto-mon-selfcheck.timer'` three `active`; the self-check's next line `-> pinged` with the module imported, `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:|Traceback|ModuleNotFound" | tail -1'`. A `Traceback` is a stop: the module's path or the unit's `PYTHONPATH`, fixed on a branch before the second pull request opens. [[ROLLOUT: R-X's reading — the files the first pass changed and the second pass's `changed=0`]].

**R0. The operands, read once.** `git switch develop && git pull --ff-only && git status --porcelain` empty; `mkdir -p .tmp/00122`; `date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/00122/r0-instant`; `KRAKEN` at planning; the clone's release, `v6.0.0` (spec Open question 5), read present on ghcr.io: `docker manifest inspect ghcr.io/zhaow-de/healthchecks:v6.0.0` answers a manifest.

**R1. The Linode, its Backups and its two records, read where they stand.** `docs/plans/00121-mon-node.md`'s R1 over `zcrypto-hc`: the plan, the image Debian 13, the label, the region apart from the engine host's, Backups enabled; `dig +short A zcrypto-hc.zhaow.me`, `dig +short AAAA zcrypto-hc.zhaow.me`, the CAA read. [[ROLLOUT: R1's readings — the plan, the image, the region, Backups, the two addresses]].

**R2. The Cloud Firewall, by hand.** `docs/plans/00121-mon-node.md`'s R2 over the firewall `zcrypto-hc`: inbound Drop, outbound Accept, Accept TCP `22`, `10022`, `443` and ICMP on both families, attached; the port read from the workstation, `22 open` and the rest `closed` on each address.

**R3. Bootstrap, the alias, the base converge, the pull and the node's converge.** The host key read in LISH, `H$ ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, [[ROLLOUT: the node's host-key fingerprint]]; `W$ (cd infra/ansible && uv run ansible-playbook bootstrap.yml --limit zcrypto-hc -e ansible_user=root -e ansible_port=22)`; the deploy key into `~/.ssh/`, the `Host hc` stanza into `~/.ssh/config`; `W$ ssh hc 'printf "%s " "$(hostname)"; sudo -n true && echo sudo-ok'`. Then the base roles and Docker, a fresh node's first converge, whose absent `daemon.json` the docker role counts a change owing its ack: `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags base,hardening,firewall,fail2ban,chrony,docker -e daemon_json_ack=true`, the preview then the real pass `failed=0`, as `docs/plans/00118-engine-cache-infra.md`'s cache nodes took theirs. Then the image pulled, since the role refuses an unpulled tag: `H$ sudo docker pull ghcr.io/zhaow-de/healthchecks:v6.0.0`. Then `docs/reference/fleet-pins.md` gains the `hc` row in the controller tree, uncommitted until R-records-1, as `docs/plans/00120-engine-cache-engine-half.md`'s cache-proxy row did, since the role's pins recording reads that file whenever the container runs: service `hc`, host `zcrypto-hc`, the pin cell `` `v6.0.0` `` with no digest and so no glossary line, rollback `first pin`, `since` filled after the real pass. Then `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=v6.0.0`: the preview `failed=0` with the repositories, the rendered files and the installs `changed` and the unit starts, the self-check, the backup and `admin.yml` `skipping`; the real pass `failed=0 unreachable=0`, `admin.yml`'s create `changed`; a second run of the same command reads `changed=0`. Then the TCP `22` rule removed in the Cloud Manager and the port read again, `443 open`, `10022 open`, `22 closed`, `80 closed`.

**R4. The node, read on the node.** The listeners: public `*:443`, `0.0.0.0:10022`, `[::]:10022`; loopback `127.0.0.1:8000`, `12345`, Caddy's `2019`; `sudo docker inspect zcrypto-hc --format '{{.State.Status}} {{.State.Health.Status}} {{.RestartCount}}'` reads `running healthy 0`; `systemctl is-active zcrypto-hc caddy alloy zcrypto-reboot-check.timer zcrypto-hc-selfcheck.timer zcrypto-sqlite-backup.timer` six `active`, `is-enabled` on the units; `sudo docker top zcrypto-hc` carrying uWSGI's and the notifier's lines and no environment; the self-check's last line `selfcheck: web=ok (…) notifier=ok (…) -> healthy, and no ping URL is set`, since no check exists yet, its `notifier=ok` the read that the unit's dynamic user sees the notifier in `/proc`; `apt-config dump | grep Automatic-Reboot` reading `"false"`; `dpkg-query -W caddy alloy docker-ce`. [[ROLLOUT: R4's package versions]].

**R5. The edge, read from outside.** `curl -4` and `curl -6 -sS -o /dev/null -w '%{http_code} %{ssl_verify_result} %{remote_ip}\n' https://zcrypto-hc.zhaow.me/api/v3/status/` each `200 0` and the address; `curl -sS https://zcrypto-hc.zhaow.me/api/v3/status/` reads `OK`; the issuer Let's Encrypt; `/metrics` and `/admin/` through the edge: `[[ROLLOUT: R5's readings of /metrics and /admin/ without a login — the clone's own answers, recorded; a 200 on either is a stop before P4]]`; `/ping/not-a-key/not-a-slug` `404`, the clone creating nothing.

**R6. The node's telemetry on the observability node.** `W$ uv run python infra/scripts/grafana-query.py --stack mon 'count by (job) (up{host="zcrypto-hc"})'` two jobs at 1, and `--loki 'sum by (container) (count_over_time({host="zcrypto-hc"}[1h]))'` rows for the four units of spec D12 and none for `caddy` or the service's container; the Alloy's own `samples_failed_total` 0 on `127.0.0.1:12345/metrics`.

**R7. The backup timer's first run.** `H$ sudo systemctl start zcrypto-sqlite-backup.service && ls -l /var/backups/zcrypto-hc/ && cat /var/lib/zcrypto-node-textfile/sqlite-backup.prom`: one file named for its date and time, and the gauge; `W$ uv run python infra/scripts/grafana-query.py --stack mon 'zcrypto_sqlite_backup_last_success_timestamp_seconds{host="zcrypto-hc"}'` one series.

**P4. The owner's first sign-in and the project.** In the clone's UI at `https://zcrypto-hc.zhaow.me`, the owner signs in with `hc_admin_email` and the password read once through `vault_var("hc_admin_password", "host_vars/zcrypto-hc/vault.yml")` into the clipboard and never a terminal line; adds a project named `zcrypto`, since the role's superuser owns none; adds the Slack integration with the webhook of Open question 2 and sends its test notification into the main channel; then, under sudo mode, whose code arrives by email through SES — a code that does not arrive is P3's SES values, `hc_email_host` and the vaulted pair, read in `sudo docker logs zcrypto-hc --since 10m` for the SMTP error — mints the read-write key, the read-only key and the project ping key, and reads the project uuid off the project's settings page. Each key is pasted once into P5's prompt and nowhere else.

**P5. The three keys and the uuid into the tree.** `(cd infra/ansible && ../scripts/vault-append-secret.sh group_vars/all/vault.yml hc_readwrite_api_key 'hcw_[A-Za-z0-9]{28}' && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_readonly_api_key 'hcr_[A-Za-z0-9]{28}' && ../scripts/vault-append-secret.sh group_vars/observed/vault.yml hc_ping_key '[A-Za-z0-9_-]{16,}')`, each printing `<key>: appended`; the uuid into `group_vars/observed/vars.yml` as `hc_project_uuid`, plain, a key P5 alone writes. [[ROLLOUT: the ping key's measured shape — its length and alphabet printed as booleans by `uv run python -c` over `vault_var`, never the value — written into the spec's D4 and the two preflights by amendment in the third pull request]]. The `all` vault's header counts re-trued here, P5 their one writer. Commit `chore(vault): the dead-man service's three keys and its project uuid`, with the trailer; a key of another shape than the one passed is re-pasted after the shape is corrected in the same commit.

Then the third pull request opens over Tasks 11 to 14 with P5's commit; a different agent reads the branch; R8's provisioning runs from that branch at the tip the reader read; then `merge-pr` merges it.

**R8. The twelve checks, the pushes and the node's own check.** Before the third pull request merges, from its branch, so no merged URL names a check the clone lacks: `W$ uv run python infra/scripts/hc-provision.py plan` lists twelve names, slugs, periods and grace values from healthchecks.io's listing plus the constant, and its description line reads `descriptions: no finding`; `apply` reports twelve created and its read-back clean; `status` reads twelve `new`, each with `n_pings` 0; in the clone's UI each check shows the Slack integration attached. Then `merge-pr` merges, and from merged `develop`: `fixture` rewrites `tests/fixtures/healthchecks_descriptions.json`, `git diff --stat` naming the one file, twelve entries; `infra/grafana/alerts.yaml` and the Fleet health dashboard pushed to Grafana Cloud through the `zcrypto-grafana-push` skill, the watchdog's re-titled text and the two panel titles verified by value as it says, and to the node by `mon.md#mon-push`, the five `zcrypto-hc` rules read back by uid. Then the node's own check goes live: `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=v6.0.0`, the env file re-rendered; `ssh hc 'sudo systemctl start zcrypto-hc-selfcheck.service && sudo journalctl -u zcrypto-hc-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'` reads `-> pinged`, the first ping end to end, and `status` reads `zcrypto-hc` moved. The fixture's commit rides R-records-1.

**R9. ops** — the readers and the five timers' URLs and the poller. `KRAKEN` immediately before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_alloy_digest=sha256:<running-alloy> -e ops_image_digest=sha256:<running-ops>`, spec D5's form: the preview names `alloy-secrets.env`, `conf/config.alloy`, the liquidations `compose.yaml`, the five timer scripts, the `tape-bars` script, whose mode Task 12's loop narrows, and the panel-regenerate script changed; the reload 200. Then `H$ cd /etc/zcrypto-ops/alloy && sudo docker compose up -d` and `cd /etc/zcrypto-ops && sudo docker compose up -d`, each container's `.State.StartedAt` moved and `RestartCount` 0; the poller's first clean poll pings, `W$ uv run python infra/scripts/hc-provision.py status` reading `zcrypto-liquidations` moved within its interval; `W$ uv run python infra/scripts/grafana-query.py 'hc_check_up' 'hc_checks_down_total'` on Grafana Cloud reads twelve rows from the clone at 1 and `max(hc_checks_down_total)` 0 — the checks not yet moved read 1 as well, a never-pinged check being `new` on the clone and counted in no total, so a move is read by `status` alone; `ssh hp 'sudo systemctl list-timers zcrypto-\*'`, and after each timer's next tick `status` reads its check moved (the five ops checks); as each ops check reads moved, the owner pauses its healthchecks.io twin in healthchecks.io's UI, the sitting announced in the main channel beforehand with healthchecks.io's DOWN pages expected for any check not yet paused; `uv run python infra/scripts/ops-daily.py report --since 1h` reading the clone's twelve in its dead-man section with no unreadable note.

**R10. The observability node.** `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`; the self-check's next line `-> pinged` and `status` reading `zcrypto-mon` moved; its healthchecks.io twin paused.

**R11. The NAS.** `W$ infra/ansible/scripts/converge.sh site.yml --limit nas --tags nas --check`, then `… -e nas_apply_compose=true`; `archive-pull`'s `.Created` moved; the gate export's replay sized by `fleet-pins.md`'s standing constraint beforehand; the next `gate-export` pings, `status` reading `zcrypto-gate-verify` moved; its healthchecks.io twin paused.

**R12. The capture pair** (Open question 1's answer, in the first sitting). `zcrypto-red`: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the capture compose render `changed` and its restart handler run, `zcrypto-capture`'s `StartedAt` moved and `RestartCount` 0; `status` reading `zcrypto-capture-red` moved within two minutes; its healthchecks.io twin paused. An hour later, `zcrypto`: `KRAKEN` immediately before, away from a 4-hourly boundary and from any engine restart; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, never `--skip-tags engine`, which the box's step 10 refuses; the same reads for `zcrypto-capture`; `zcrypto-engine`'s `StartedAt` unmoved. The capture gap each restart books is read on the pulled copy by the rollout-image skill's verify-by-outcome. After it, `max(hc_checks_down_total)` on Grafana Cloud reads `0`, the engine's clone check `new` until R14.

**R13. The checks' first clean read.** `W$ uv run python infra/scripts/hc-provision.py status` reads eleven moved and `zcrypto-engine-shadow` `new`; `grafana-query.py 'hc_check_up' 'hc_checks_down_total'` reads twelve rows at 1 and the total 0, `zcrypto-hcio-watchdog` quiet and no silence set; on healthchecks.io's UI, the ten moved checks paused and the engine's pinging. One clone Slack message's link, P4's test notification's or the first page's, opened on macOS: [[ROLLOUT: where the clone's Slack link lands — the check's page, or the login redirect, which adds the cookieless-HEAD route to Task 9's edge include in R-records-1 (spec Open question 8)]].

**R-records-1. The inside-box records: one pull request.** The deploy-log rows; `fleet-pins.md`'s `hc` row from R3, its `since` filled, and the `since` cells of ops' two containers and the capture pair's; `fleet.md`'s Services and instruments and Telemetry labels sections; the fixture from R8, with `tests/test_ops_daily.py::test_todays_real_descriptions_all_pass`'s count re-trued from 11 to 12 in the same commit; T0218's findings with R0 to R5's readings; the spec's D4 shape amendment from P5 where the third pull request did not carry it; the edge's cookieless-`HEAD` route if R13's link read landed on the login redirect, converged `--tags hc` after the merge; the `AUDIT` line over this sitting's rows, 0, where `AUDIT` is `docs/plans/00121-dual-shipping.md`'s form over this plan's instant, `uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing --since "$(cat .tmp/00122/r0-instant)"`.

Then the fourth pull request opens over Tasks 15 and 16; a different agent reads the branch; `merge-pr` merges it.

**R14. After the box — the engine** (on or after [[ROLLOUT: the box's closing date]]). `KRAKEN` immediately before; inside the inter-cycle gap, `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<running> -e cache_proxy_image_digest=sha256:<running>`, each digest read off its container, `zcrypto-engine` and `zcrypto-cache-proxy`, the rollout-image skill's engine form, under `infra/runbooks/engine-procedures.md`'s restart rules and the position read it names; the engine's next cycle pings the clone, `status` reading `zcrypto-engine-shadow` moved, `max(hc_checks_down_total)` 0 on Grafana Cloud; its healthchecks.io twin paused.

**R15. The three drills** (Task 15), in an attended window, each announced: X1 the service stopped until `zcrypto-hcio-watchdog`'s `999` page, [[ROLLOUT: X1's reading — the page's `activeAt` and the checks that paged DOWN then UP on return]]; X2 the 30-minute power-off, [[ROLLOUT: X2's reading — the page and the self-check's first `-> pinged` after boot]]; X3 the restore's one-shot read of the last backup (spec D10), twelve checks counted and no Slack message sent, then that backup fetched to `.tmp/00122/` on the workstation and the rebuild from nothing — the Linode rebuilt from Debian 13, the Cloud Firewall's TCP `22` for the bootstrap alone and the host key re-read in LISH as at R2 and R3, R3's bootstrap and converges, and `hc-restore`'s second half from the fetched file — with no key re-minted and no P-step re-run, since the restored database carries the user, the project, its keys, its ping key and the Slack integration under the vaulted `SECRET_KEY`; accepted when `status` reads every check's `last_ping` moving after the restore and the self-check reads `-> pinged`, the fetched file deleted after that read, [[ROLLOUT: X3's reading — the time from the rebuild to the first stored ping]]; the entries into the drill log, the two figures into `hc.md#hc-dark`.

**R16. Retirement** (after R14's first clean day). `W$ uv run python infra/scripts/hc-provision.py fixture` leaves the fixture unchanged, or its change merges first, since `retire` refuses a fixture the clone's listing does not equal; `W$ uv run python infra/scripts/hc-provision.py retire` passes its gate, every clone check moved and no healthchecks.io check pinged in 24 hours, and prints eleven deletes; the owner revokes healthchecks.io's two keys and closes the account; one pull request removes the fourteen vault values and their comments, re-trues T0085's rotation scope as spec D14 names it, and records the date in T0218.

**R-records-2. The after-box records: one pull request.** The deploy-log rows, the three drill-log entries, the `since` cell of the engine, `hc.md`'s two figures, `engine.md`'s three lines and `observability.md`'s step-2 clause on the engine's check re-trued to the service, T0218 resolved, the `AUDIT` line over the after-box rows 0, and the commit `chore(fleet): the fleet's dead-man checks run on the owner's service`, with the trailer.

## Resolution

T0218 is resolved by R-records-2. What this plan leaves: the capture, ops and cache roles' reboot-check copies, dropped while `tests/test_reboot_check.py` holds them equal to the shared program; Grafana's SQLite through the shared backup timer, dropped since 00121 D3 accepted Linode Backups for the node (spec Out of scope); the ops watchdog's probe re-pointed at the node, 00121 phase 3's.

## Slots the rollout fills

- `[[ROLLOUT: the box's closing date, 2026-11-01 or a week later …]]` (Global Constraints; R14).
- `[[ROLLOUT: R-X's reading …]]` (R-X) — the extraction's `changed=0`.
- `[[ROLLOUT: a slot the base role's collision assert admits …]]` (Task 8).
- `[[ROLLOUT: the SES region's SMTP endpoint …]]` (P3) — `hc_email_host`.
- `[[ROLLOUT: R1's readings …]]`, `[[ROLLOUT: the node's host-key fingerprint]]`, `[[ROLLOUT: R4's package versions]]`, `[[ROLLOUT: R5's readings of /metrics and /admin/ …]]` (R1 to R5) — into R-records-1.
- `[[ROLLOUT: the ping key's measured shape …]]` (P5) — the spec's D4 and the two preflights by amendment.
- `[[ROLLOUT: where the clone's Slack link lands …]]` (R13) — the edge include's `HEAD` route, in R-records-1.
- `[[ROLLOUT: X1's reading …]]`, `[[ROLLOUT: X2's reading …]]`, `[[ROLLOUT: X3's reading …]]` (R15) — `hc.md#hc-dark` and the drill log.
