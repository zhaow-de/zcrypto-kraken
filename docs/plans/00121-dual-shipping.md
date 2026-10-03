# The observability node, phase 2: every fleet host dual-ships to `zcrypto-mon` and Grafana Cloud — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every fleet host's Alloy ships its metrics, unfiltered, to the node beside its filtered push to Grafana Cloud, and every host that ships logs ships them to the node's Loki beside Cloud's; the node's rules then read real data for every host, its self-check pings a healthchecks.io check of its own, and `infra/scripts/grafana-compare.py` can run every rule's query on both stacks. Grafana Cloud's rules, receivers, keep-lists and vault values are untouched, the box's order is kept, and the four telemetry drills the node owes are run and logged. This is phase 2 of the spec's four: nothing pages the main channel from the node yet.

**Architecture:** Eight build tasks on the fleet's existing shapes, grouped into five pull requests by the box's order, then an attended runsheet of eight converges, one per fleet host, beside the node's own for its self-check URL. The five Alloy configs each gain a second `endpoint` in `prometheus.remote_write "grafana"` and, where the host ships logs, a `loki.write "mon"` added to the parse stage's `forward_to`, both reading `MON_*` names rendered from new vault and group values; the Cloud blocks are not touched. Each role lands its `MON_*` names and the config that reads them in one tree state: on the three container roles with a reload handler (ops, cache, capture) one converge with the host's running Alloy digest renders the secrets file and copies the config, the handler's reload reads the config with the names still unset — harmless, P0's proof — and `docker compose up -d` in the Alloy project then recreates the container with the names; the bridgehead and the NAS take their one state, since their converge restarts Alloy after both files. A comparison script reads both stacks through the datasource proxies the uids already name. Four drill procedures join `infra/runbooks/drills-telemetry.md`, the healthchecks.io check map gains the node's own check, and the push skill takes its two-stack wording.

**Tech Stack:** Grafana Alloy v1.19.2 (the fleet's pinned container, `grafana/alloy@sha256:b8ec653c4423…`), the node's apt Alloy 1.20 and the bridgehead's apt Alloy (`1.20.0-1`, read 2026-10-03), Ansible (ansible-core 2.21, the `access`, `ops`, `cache`, `capture`, `nas` and `mon` roles), Docker Compose on the container hosts, Prometheus 2.53.3 and Loki 3.7.8 on the node, `infra/scripts/grafana_auth.py`'s stack table, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00121-self-hosted-observability-design.md`, phase 2: D12 to D15, D19 to D21 as they bear on this phase, the "Phase 2, dual-shipping" line of "What changes in the repo, by phase", the "Phase 2" line of "Proofs each phase owes", the measured basis, and the open questions that name this plan (D14's workstation proof; the bridgehead's `prometheus.exporter.self`; the Cloud push URL and Loki hostname as label values on the node). Phase 1 is `docs/plans/00121-mon-node.md`, whose Produces lines name everything this plan consumes; phases 3 and 4 each take a plan of their own under the same serial.

## Global Constraints

- The node's leg ships unfiltered and the Cloud leg keeps its drop and keep pair untouched: the new `endpoint` carries no `write_relabel_config`, the existing one keeps both of its blocks byte for byte, and no keep-list, REQUIRED list or keep-list test changes in this phase (spec D12; the invariant).
- Dual-shipping is a second `endpoint` block and a second `loki.write` component under new names only: the new blocks read `MON_PROM_URL`, `MON_PROM_USERNAME`, `MON_PROM_PASSWORD`, `MON_LOKI_URL`, `MON_LOKI_USERNAME`, `MON_LOKI_PASSWORD` and nothing else; `GRAFANA_*` names, `grafana_prom_url`, `grafana_loki_url` and every other existing vault value are never repointed or renamed; logs take `loki.write "mon"` in the parse stage's `forward_to`, never a second endpoint inside `loki.write "grafana"`; the bridgehead ships no logs and gains none (spec D13; the invariant).
- A name reaches an Alloy process with the config that reads it, one tree state per container role: on ops, the cache nodes and the capture pair one converge with the host's running Alloy digest renders the role's secrets file and copies its config, the handler's reload reads the config with the `MON_*` names still unset — harmless, P0's verdict of 2026-10-03: the reload answers 200, the first endpoint keeps shipping, the second retries its own queue at `level=warn` — and the container is then recreated with `docker compose up -d` in the Alloy project, the bump-alloy skill's step, on each host of the role, which starts the process with the names, the node's series for that host read from the recreate on; the bridgehead and the NAS take their one state, their converge restarting Alloy after both files land. Each role's names and config land in the same commit, so `test_the_cache_secrets_template_renders_every_name_the_config_reads` holds `read == rendered` throughout and is not widened (spec D14).
- Merging a `config.alloy` arms its role's drift assert on every host the file serves until each is converged with its Alloy digest, so the merges follow the box's order: the ops and access changes first; the cache role's config only after the three node drills, when its three nodes are next to be converged; the NAS and capture changes, their secrets templates included, only after the box (spec D14, D15).
- Inside the box only the bridgehead, ops and the three cache nodes dual-ship, in that order, the node drills between ops and the first cache node; the NAS and both capture hosts follow the box, `zcrypto` last and attended, in the bump-alloy skill's primary form `--skip-tags engine -e converge_primary=true` with both running digests; `-e capture_image_digest=<running>` is passed on every capture-host converge (spec D15; `.claude/rules/fleet-deploys.md`). The box runs Mon 2026-10-05 to Sun 2026-11-01 and may slip one week under its own rule: [[ROLLOUT: the box's closing date, 2026-11-01 or a week later — the earliest R5 may start]].
- The cache nodes converge one node per run, never under the group limit `cache_host`, with `cache_alloy_digest` alone so the Valkey and Sentinel block is skipped, outside the day's plan window and away from an engine restart, and with a day's read of the first node's Alloy headroom, `(go_memstats_sys_bytes - go_memstats_heap_released_bytes)` under `job="integrations/self"`, before the second (spec D15).
- The Kraken maintenance feed `https://status.kraken.com/api/v2/scheduled-maintenances.json` is read whole, never through `head` or `tail`, at planning time and again immediately before every converge of `zcrypto`, `zcrypto-red` and `zcrypto-ops`, the ops converges inside the box included, and before the shipper-stop induction on `zcrypto-red`; an empty or truncated feed is never evidence the window is clear. `zcrypto-mon` speaks to no venue and its drills owe no read (`.claude/rules/fleet-deploys.md`; the invariant).
- `site.yml`'s un-tagged refusal on the primary holds on tuples and refuses `all` and `tagged` (PR #651): the primary's converge names `--skip-tags engine`, never answers the refusal with `-e engine_image_digest`, and runs away from the engine's 4-hourly boundaries; no step here converges the engine.
- The three node drills run inside the box on the node alone; the shipper-stop drill runs on the secondary after the box, in an attended window; the primary's capture daemon and its Alloy are never a drill's subject (spec D21; `.claude/rules/fleet-deploys.md`).
- Outside the store-restart drill's bare legs, a store on the node is restarted only with Grafana stopped around it, by `infra/runbooks/mon.md`'s `mon-store-restart`; `prometheus` stays on the node's unattended-upgrades blacklist until that drill's reading, and stays there if a bare restart pages (spec D17, D21).
- `grafana_auth.py`'s default stack stays `cloud`, and `grafana-push.sh` leaves the `zcrypto-mon` group out unless its caller passes `GRAFANA_SKIP_RULE_GROUPS` otherwise, and refuses a push addressed to Grafana Cloud that does not skip it: a rule of that group is never pushed to Grafana Cloud (spec D18).
- Every push in the dual period goes to both stacks from one checkout under the push skill's conditions; the node is pushed by `infra/runbooks/mon.md`'s `mon-push` and may trail the tree, since it pages the shadow channel alone (spec D18).
- No Grafana token is rendered on a managed host or written to a tracked file, and no task prints one. No secret appears in a command line, a log, a diff or a plan step. No executor decrypts, prints or generates a vault value; `ansible-inventory --host`, `--list` and `--graph --vars` are never run.
- No container's environment is printed on any host, by `docker inspect … .Config.Env`, `docker exec … env` or `docker compose config`: a recreate is proven by `.State.StartedAt` moving (`.Created` on the NAS, whose apply also restarts the container it keeps) and a name's arrival by the series that reach the node after the config lands, never by reading the environment.
- No executor step reaches a host, a venue, Grafana Cloud, the node's Grafana, Slack, healthchecks.io, the Linode Cloud Manager or DNS; every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No operator-read surface (the runbook pages, the drill procedures, the rule file's text, the healthchecks.io description, the Slack template) carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; where a provenance token is wanted it goes in an adjacent code comment.
- A comment or docstring stays only where a reader would do something differently without it; an event goes to the commit message. It carries a count of another file's contents only where a test holds that count.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean. The branch is unpushed while the tasks run, so the amend rewrites nothing a reader holds.
- Every commit is green over the changed files' consumers, the tests each task's consumer step names; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs clean before every commit; a run that rewrites files is re-run until clean and the rewrites staged.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. A universal word in a new runbook bullet (every, never, always, only, any, cannot) carries its `(set: …; count: …)` or `(no count command: …)` clause, or the bullet is worded without it.
- Task 4 alone edits files under `.claude/`, the three skills `zcrypto-grafana-push`, `zcrypto-bump-alloy` and `zcrypto-daily-ops`, in a `claude` commit that carries no other file; no task edits `CLAUDE.md`.
- `zcrypto-refine-rules` is loaded before each edit to a skill file or a top-level page under `infra/runbooks/`: the three skills of Task 4, and `mon.md`, `drills-telemetry.md` and `observability.md` in Tasks 1, 2, 3 and 5.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `infra/ansible/group_vars/observed/vars.yml` (new): the node's two ingest URLs and the `fleet` user's name, plain, beside the vaulted passwords phase 1 appended to `group_vars/observed/vault.yml` (Task 1).
- `infra/ansible/roles/access/templates/alloy-env.j2`: the three `MON_PROM_*` names (Task 1); `roles/ops/templates/alloy-secrets.env.j2` (Task 5), `roles/cache/templates/alloy-secrets.env.j2` (Task 6), `roles/nas/templates/alloy-secrets.env.j2` (Task 7), `roles/capture/templates/alloy-secrets.env.j2` (Task 8): the six `MON_*` names, each in the commit of the config that reads them.
- The comments these edits make false, each re-trued in the commit that falsifies it, by task: Task 1, the access template's header ("Same six names", its one source `group_vars/observed/vault.yml`, and "does not check this file", false once the literal and template-config cases read it), the access config's header ("from the SAME six group_vars/observed vault") and its Cloud endpoint's relabel comment ("no `prometheus.exporter.self` component on this host"), and the comment on `tests/test_infra_alloy_series.py`'s access case of `test_keep_regex_excludes_families_not_published_on_this_host` ("no `exporter.self "alloy"` component", so "none of the app/logship/process families exist there"); Task 5, the ops template's header ("Grafana Cloud credentials", "same six names", "does not check this file") and the ops config's "the NAS's Alloy reads the same six names"; Task 6, the cache template's header list of the vars files it renders from, which gains `group_vars/observed/vars.yml`; Task 7, the NAS template's header ("Grafana Cloud credentials", "the same six names", and its clause that nothing tests the file), `roles/nas/tasks/main.yml`'s "Grafana Cloud creds for the NAS's Alloy" above its render task, and `infra/nas/README.md`; Task 8, the capture template's header ("Grafana Cloud credentials", "The SAME six names", "does not check this file") and the capture config's "the same six names the ops and nas Alloy copies read". A re-trued comment carries no count of another file's names.
- `infra/ansible/roles/access/files/config.alloy`: the second endpoint and `prometheus.exporter.self` (Task 1); `roles/ops/files/config.alloy`: the second endpoint, `loki.write "mon"`, the `netdev` exclusion (Task 5); `roles/cache/files/config.alloy`: the second endpoint and `loki.write "mon"` (Task 6); `infra/nas/config.alloy` and `roles/capture/files/config.alloy`: all three (Tasks 7, 8).
- `infra/ansible/host_vars/zcrypto-mon/vars.yml` and `vault.yml`: the self-check's healthchecks.io URL, wired from a vault value the owner appends in the Rollout's P1; `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py`: the refusal names the series it did not find (Task 5).
- `infra/scripts/grafana-compare.py` (new) and `tests/test_grafana_compare.py` (new); `infra/scripts/ops_daily.py`: the `## Comparison` section and `COMPARISON_FROM`; `infra/scripts/grafana-push.sh`: a skipped group's live rule named as such in the orphan report (Task 2).
- `infra/runbooks/drills-telemetry.md`: four drill procedures and the standing rule's subject list (Task 3); `infra/runbooks/mon.md`: the shipper-loss section's sentence on the bridgehead (Task 1), a `mon-compare` procedure (Task 2), a `mon-dark` procedure (Task 3), and `mon-secrets` step 4 host by host (Task 5); `infra/runbooks/observability.md`: the dead-man map's row and its count (Task 5); `infra/nas/README.md`: the secrets file's names (Task 7).
- `tests/fixtures/healthchecks_descriptions.json`: the node's check, re-fetched through the read-only key (Task 5).
- `.claude/skills/zcrypto-grafana-push/SKILL.md`: the two-stack wording of every push in the dual period; `.claude/skills/zcrypto-bump-alloy/SKILL.md`: Step 3's shipping-health read sees each destination a host ships to; `.claude/skills/zcrypto-daily-ops/SKILL.md`: the `## Comparison` section and its line in the journal entry (Task 4).
- `tests/test_infra_alloy_series.py`: the secrets-lines literal case and the template-config case over each template as its task lands, and the new guards over the second endpoint, the second `loki.write`, the `netdev` exclusion and the bridgehead's self scrape (Tasks 1, 5, 6, 7, 8); `tests/test_infra_mon_role.py`: the group vars held to the role's hostname and the Caddyfile's two paths (Task 1); `tests/test_grafana_push_sh.py`: the skipped group's orphan line, and `tests/test_ops_daily.py`: the `## Comparison` section (Task 2); `tests/test_ops_daily.py`: the fixture's count, and `tests/test_mon_selfcheck.py`: the series named in the refusal (Task 5); `tests/test_drill_log.py`: unchanged, it reads the entries the Rollout appends.
- `docs/reference/deploy-log.jsonl`, `drill-log.md`, `fleet-pins.md`, `fleet.md`, `docs/open-topics/T0217-self-hosted-observability-stack.md`, the spec's measured basis: the Rollout's records pull requests, not a task's.

## Review Focus

Five classes, each held by the tests of the tasks named beside it; a test this plan names is named here, and the rest are the cases each task's Step 1 lists.

- A `MON_*` name read by a config before the process holds it: the reload reads empty strings and the second endpoint retries an empty URL until the recreate (P0), so each role's names and config land in one commit, every converge of a container role is followed by the recreate, proven by `.State.StartedAt` moving on every host of the role, and `test_each_secrets_template_renders_the_names_its_config_reads` holds each template to its config's names from its task on, the cache pair held by `test_the_cache_secrets_template_renders_every_name_the_config_reads` across the cache commit, widened by nothing (Tasks 1, 5, 6, 7, 8).
- A relabel block on the node's endpoint, or the Cloud endpoint's pair moved or loosened: the keep and drop extractors in `tests/test_infra_alloy_series.py` assert exactly one block of each per file, so the guard, `test_the_nodes_endpoint_carries_no_relabel_block_and_the_cloud_one_keeps_its_pair`, must read the two endpoints apart, hold the `mon` endpoint free of `write_relabel_config` and the `grafana` endpoint to its existing pair, and hold `loki.write "grafana"` to one endpoint (Tasks 1, 5, 6, 7, 8).
- An existing name repointed: a diff that touches a `GRAFANA_*` line, a `grafana_*` vault reference or the Cloud `endpoint` block is a finding, since `logship-secrets.env` re-renders on every capture-role converge and the engine reads it at its next start; `test_the_secrets_lines_are_held_by_literal` holds the six `GRAFANA_*` lines of each template byte-identical to today's and its `MON_*` lines to their fence, and the endpoint guard holds the Cloud endpoint to its three `GRAFANA_PROM_*` reads with no `MON_` name and the new blocks to `MON_*` names alone (Tasks 1, 5, 6, 7, 8).
- The comparison admitting a false match: an empty result equal only to an empty result, values within a relative 1e-6 and label sets whole, the three exclusions by name and nothing else excluded, every other query node sent through its placeholder's path (`test_the_walk_sends_every_query_node_but_the_three_exclusions`), the same instant sent to both stacks, and a missing stack or a refused query a failure of the run and never a match (Task 2).
- A converge or an induction outside its bounds: a venue-facing host inside a Kraken window, the primary converged un-tagged or with a capture digest that is not the running one, a cache node converged under its group or with the image digest, a drill whose subject is the primary, or the `prometheus` blacklist decided by anything but the store-restart drill's reading (Tasks 3, 5, 6, 8 and the Rollout).

---

### Task 1: The bridgehead ships to both and its Alloy scrapes itself — the node's ingest names reach the group vars and the bridgehead's environment, one tree state

**Files:**
- Create: `infra/ansible/group_vars/observed/vars.yml`
- Modify: `infra/ansible/roles/access/templates/alloy-env.j2` (three `MON_PROM_*` lines appended, the bridgehead shipping no logs; its header's comments the File structure lists for Task 1 re-trued)
- Modify: `infra/ansible/roles/access/files/config.alloy` (`prometheus.exporter.self "alloy" {}`, the host scrape's targets concatenated, the second `endpoint`; the header's "SAME six" sentence and the Cloud endpoint's relabel comment, "present even with no `prometheus.exporter.self` component on this host", re-trued)
- Modify: `infra/runbooks/mon.md` (the `zcrypto-mon-shipper-loss` section's sentence that the bridgehead publishes no counter)
- Test: `tests/test_infra_alloy_series.py` (new: the two endpoints read apart; the self targets concatenated on every config; `test_the_secrets_lines_are_held_by_literal` and `test_each_secrets_template_renders_the_names_its_config_reads`, each parametrised over the access template; the access case's comment in `test_keep_regex_excludes_families_not_published_on_this_host` re-trued, its assertion unchanged)
- Test: `tests/test_infra_mon_role.py` (the group vars held to `mon_hostname` and to the Caddyfile's two ingest paths)

**Interfaces:**
- Consumes: `mon_ingest_fleet_password` in `infra/ansible/group_vars/observed/vault.yml` (phase 1's P2); the `mon` role's defaults `mon_hostname`, `mon_ingest_fleet_user`; the Caddyfile's two authenticated paths `/api/v1/write` and `/loki/api/v1/push`; the access role's `restart alloy` handler, which both the env and the config notify, so one converge lands both and restarts; `ACCESS_REQUIRED` and the keep regex, unchanged; the roles' `no_log` render tasks, which this task does not touch.
- Produces, for Tasks 5 to 8 and the Rollout to use by these exact names: `mon_ingest_prom_url`, `mon_ingest_loki_url` and `mon_ingest_fleet_user` in `group_vars/observed/vars.yml`; the environment names `MON_PROM_URL`, `MON_PROM_USERNAME`, `MON_PROM_PASSWORD`, `MON_LOKI_URL`, `MON_LOKI_USERNAME`, `MON_LOKI_PASSWORD`; the helper that reads `prometheus.remote_write "grafana"`'s endpoint blocks apart, the second-endpoint block's exact text, and the guard shape over it; the literal case and the template-config case, each of which a later task parametrises over its role's template; on Cloud, `up{host="zaccess", job="integrations/self"}`, which the keep regex admits.

**What this task decides, where the spec leaves it open:**
- The two URLs are plain group vars, not vault values, since they are the node's public name and two paths the Caddyfile already publishes; `mon_ingest_fleet_user` is declared in the group vars with the role default's value, since a role's defaults are not visible to another role's template, and `tests/test_infra_mon_role.py` holds the three equal to the `mon` role's `mon_hostname`, its `mon_ingest_fleet_user` and the Caddyfile's two paths.
- The bridgehead's env file gains the three `MON_PROM_*` names and not the Loki three, in the commit of the config that reads them: the template renders every name a config may read on that host, and the access config reads no Loki name.
- The literal case, `test_the_secrets_lines_are_held_by_literal`, holds the six `GRAFANA_*` lines of a template byte-identical to their text on `develop` at this plan's base and its `MON_*` lines identical to their fence, this task's three on the access template and Task 5's six on the others, parametrised over the access template here and over each role's template as its task lands, so a repointed Cloud name, or a node name bound to another group var, is a test failure before it is a converge.
- The template-config case, `test_each_secrets_template_renders_the_names_its_config_reads`, holds a secrets template to the `sys.env` names its config reads: `read ⊆ rendered` on the access pair, whose template also renders the unit's `CONFIG_FILE` and `CUSTOM_ARGS` and the three `GRAFANA_LOKI_*` names its config does not read, and `read == rendered` on the ops, NAS and capture pairs, which join it with their tasks; the cache pair stays `test_the_cache_secrets_template_renders_every_name_the_config_reads`'s. Every pair holds it at this plan's base, and each task lands its names and its config in one commit, so a `MON_*` line dropped from a template fails it in that template's own task.
- The open question is answered yes: the bridgehead gains `prometheus.exporter.self "alloy" {}` with its targets concatenated into `prometheus.scrape "host"`, as ops, the NAS and capture concatenate theirs (the cache config's scrape is `prometheus.scrape "cache_host"`, so the self-targets case reads the `array.concat(prometheus.exporter.unix.host.targets, prometheus.exporter.self.alloy.targets)` text in whatever scrape carries it), so `zcrypto-mon-shipper-loss` reads it from the day it ships. The Cloud leg gains one series, `up{job="integrations/self"}`, since the keep regex admits `up` and the drop regex already drops `go_.*|alloy_.*`; `zcrypto-alloy-dark-zaccess` counts `up{host="zaccess"}` and reads 2 where it read 1, still above its bar; `zcrypto-fleet-daemon-restarted`'s host matcher does not name `zaccess`, so a bridgehead restart pages nothing new.
- The second endpoint carries `name = "mon"`, so Alloy's own counters label the node's destination `remote_name="mon"` where the Cloud endpoint keeps its hash; P0 read the attribute accepted by v1.19.2, the container pin; the bridgehead's apt Alloy read `1.20.0-1` on 2026-10-03, so Step 4's dry-start reads it on the edited file in that version's release binary, and R1 re-reads the host's version before its converge.
- The new guard reads the `endpoint` blocks of `prometheus.remote_write "grafana"` apart: exactly two; the first carries the three `sys.env("GRAFANA_PROM_*")` reads, both relabel blocks and no `MON_` token, so a node credential pasted into the Cloud endpoint fails it; the second carries the three `sys.env("MON_PROM_*")` reads, `name = "mon"` and no `write_relabel_config`, and no `GRAFANA_` token at all. The existing extractors, which assert exactly one keep and one drop block per file, hold as they are, which is the measured basis's finding.

The template lines, determined by the vault and group names:

```
MON_PROM_URL={{ mon_ingest_prom_url }}
MON_PROM_USERNAME={{ mon_ingest_fleet_user }}
MON_PROM_PASSWORD={{ mon_ingest_fleet_password }}
```

And the group vars:

```yaml
mon_ingest_prom_url: https://zcrypto-mon.zhaow.me/api/v1/write
mon_ingest_loki_url: https://zcrypto-mon.zhaow.me/loki/api/v1/push
mon_ingest_fleet_user: fleet
```

The endpoint block, determined by the existing endpoint's shape and D13:

```
  endpoint {
    name = "mon"
    url  = sys.env("MON_PROM_URL")

    basic_auth {
      username = sys.env("MON_PROM_USERNAME")
      password = sys.env("MON_PROM_PASSWORD")
    }
  }
```

The test's shape:

```python
def _endpoint_blocks(path: Path) -> list[str]:
    component = re.search(r'\nprometheus\.remote_write "grafana" \{(.*?)\n\}\n', path.read_text(), re.S).group(1)
    return re.findall(r"\n  endpoint \{(.*?)\n  \}", component, re.S)


@pytest.mark.parametrize("path", [ACCESS_ALLOY], ids=["access"])  # the other four join as their tasks land
def test_the_nodes_endpoint_carries_no_relabel_block_and_the_cloud_one_keeps_its_pair(path):
    cloud, mon = _endpoint_blocks(path)
    assert cloud.count("write_relabel_config") == 2 and "MON_" not in cloud
    assert all(f'sys.env("GRAFANA_PROM_{n}")' in cloud for n in ("URL", "USERNAME", "PASSWORD"))
    assert "write_relabel_config" not in mon and "GRAFANA_" not in mon and 'name = "mon"' in mon
    assert all(f'sys.env("MON_PROM_{n}")' in mon for n in ("URL", "USERNAME", "PASSWORD"))
```

- [ ] **Step 1: Write the failing tests** — the endpoint guard, the self targets, the group-vars case, the literal case, the template-config case.
- [ ] **Step 2: Run the tests and read the failure**

```bash
uv run pytest tests/test_infra_alloy_series.py tests/test_infra_mon_role.py -q -p no:cacheprovider
```

Expected: the endpoint guard fails on one block; the self-targets case fails on the access config, which has no `prometheus.exporter.self` yet; the group-vars case fails on the missing file; the literal case fails on the access template's missing `MON_PROM_*` lines; the template-config case passes, as it does at the plan's base.

- [ ] **Step 3: The group vars, the template, the config, the comments the File structure names for this task, and the runbook sentence**
- [ ] **Step 4: Dry-start the edited config on the workstation** — the bump-alloy skill's Step 0 item 1 dry-start, with dummy values for every `sys.env` name, in P0's form, since the workstation is `zcrypto-ops`, whose own Alloy holds `127.0.0.1:12345`, and its user is outside the `docker` group: the release binary of the version the config's host runs (here `1.20.0`, the bridgehead's apt Alloy; Tasks 5 to 8 run v1.19.2's, the container pin, with the config's container paths pointed at the workstation's as P0 pointed them) started as `alloy run --server.http.listen-addr=127.0.0.1:<a free port> --storage.path=<a scratch directory under .tmp/> <the edited config>`, the scratch directory removed after; Expected: the config loads, no `level=error` line, and the `name` attribute accepted.
- [ ] **Step 5: Run the tests** — Expected: no failure, `test_alloy_self_metrics_are_dropped_before_the_keep` and the keep-list cases among them.
- [ ] **Step 6: The consumers**

```bash
grep -rl 'alloy-secrets.env\|alloy-env.j2\|group_vars/observed\|config.alloy' tests/ infra/ .claude/ | sort
```

Run every test file the listing names.

- [ ] **Step 7: The commit gate** — `uv run pre-commit run -a`; Expected: every hook Passed.
- [ ] **Step 8: Commit**

```bash
git commit -F- <<'MSG'
feat(infra): the bridgehead's Alloy ships unfiltered to the node beside its filtered push to Grafana Cloud, and scrapes itself

<what: the plain URLs and user in group_vars/observed, the three MON_PROM_* names beside the config that reads them — one tree state, the reload with unset names proven harmless on 2026-10-03; the self scrape; the secrets-lines literal guard and the template-config case>

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean** — `git status --porcelain`; Expected: empty.
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — `infra/scripts/mutate-probe.sh` with a control and a mutation per case (a `write_relabel_config` copied into the `mon` endpoint; the Cloud endpoint's keep block removed; a `MON_PROM_*` credential substituted into the Cloud endpoint; the self targets dropped from the concat; a `GRAFANA_` line edited; a `MON_` line bound to another group var; a `MON_` line dropped from the template; the URL's path changed); each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`; the `PROBE_VERDICT` line replaced, as phase 1's tasks do.

---

### Task 2: `grafana-compare.py` runs every rule's query on both stacks at the same instants, and the daily pass carries it from its first day

**Files:**
- Create: `infra/scripts/grafana-compare.py`
- Create: `tests/test_grafana_compare.py`
- Modify: `infra/scripts/ops_daily.py` (`COMPARISON_FROM`, a date constant `None` until R-records-2 sets it, and the `## Comparison` section: from that day, while the stack table carries both stacks, the markdown report runs `grafana-compare.py` for the preceding day and prints its last line; absent before it, while the constant is `None`, and once retirement leaves the table one stack) and `tests/test_ops_daily.py` (the section absent the day before `COMPARISON_FROM`, while it is `None`, and with one stack in the table; present on that day with both, carrying the runner's last line, the runner injected)
- Modify: `infra/runbooks/mon.md` (a `mon-compare` procedure, one invocation and how a difference is read)
- Modify: `infra/scripts/grafana-push.sh` (the orphan report reads each orphan's group from the rules file before the skip: a live rule of a group `GRAFANA_SKIP_RULE_GROUPS` skipped prints `ORPHAN (live, of skipped group <group>)`, a rule in no group of the file keeps `ORPHAN (live but not in alerts.yaml)`, and `GRAFANA_PRUNE=1` deletes both, spec D18's remedy for a node rule pushed to Grafana Cloud by mistake; the script's own comment on the variable and `mon.md#mon-push` stay true as they read) and `tests/test_grafana_push_sh.py` (`test_a_skipped_groups_rule_found_live_is_an_orphan_and_a_prune_deletes_it` reads the new line for `r3`, the not-in-file line for no uid, and the prune's `DELETE` of `r3` unchanged — a guard change with its probe)

**Interfaces:**
- Consumes: `grafana_auth.STACKS`, `grafana_auth.stack(name)`, `grafana_auth.vault_var(name, vault_file)`; `grafana-query.py`'s endpoint shape, `<url>/api/datasources/proxy/uid/<uid>/api/v1/query` for Prometheus and `…/loki/api/v1/query` for Loki, and its `PROM_DS_UID` and `LOKI_DS_UID`, the uids both stacks serve (spec D8); `infra/grafana/alerts.yaml`'s rules, each `data[]` node's `model.expr` and `datasourceUid` — the placeholder `${GRAFANA_PROM_DS_UID}` or `${GRAFANA_LOKI_DS_UID}` that `grafana-push.sh` substitutes, or `__expr__` — and its `ruleGroup`; `ops_daily.read_soak_verdict`'s injected `runner`, the seam the comparison's reader copies.
- Produces, for phase 3's gate and the Rollout: `uv run python infra/scripts/grafana-compare.py [--day YYYY-MM-DD]`, whose last line is one summary whatever the outcome: `compare: <nodes> nodes × 24 instants, <n> differences`, exit 0 when `<n>` is 0 and 1 otherwise, with one line per difference above it, `<rule uid> <refId> <instant> <what differs>`; or `compare: failed: <what failed>`, exit 2, naming the stack where a stack failed; the constants `EXCLUDED_GROUPS = ("zcrypto-mon",)`, `EXCLUDED_HOSTS = ("zcrypto-mon",)` and `DIRECT_SHIPPED_RULES`, the seven uids D19 names; `ops_daily.COMPARISON_FROM`, which R-records-2 sets.

**What this task decides, where the spec leaves it open:**
- The 24 instants are the top of each UTC hour of the preceding day, or of `--day`; each query node is sent as an instant query with `time=<epoch>` to both stacks, Loki nodes through `/loki/api/v1/query` with the node's own `expr`, so the two stacks answer the same question at the same instant and the rule's own range selector supplies the window.
- A query node is a `data[]` node whose `datasourceUid` is not `__expr__`. The rule file carries the placeholders, never a uid — 104 `${GRAFANA_PROM_DS_UID}` nodes and 14 `${GRAFANA_LOKI_DS_UID}` at this plan's base — so the walk routes on the placeholder: `${GRAFANA_PROM_DS_UID}` to `PROM_DS_UID` and the Prometheus path, `${GRAFANA_LOKI_DS_UID}` to `LOKI_DS_UID` and the Loki path, the two uids read from `grafana-query.py`'s module rather than written again. A query node whose `datasourceUid` is neither placeholder, and a walk that would send no node, end the run as `compare: failed: …` before any query.
- A difference is any of: a label set present on one stack and not the other, a value differing by more than a relative 1e-6, an empty result against a non-empty one; an empty result on both is a match. A stack that cannot be reached, a 4xx or 5xx, or a malformed body ends the run as `compare: failed: <stack> …`, never as a match or a skip.
- Rows whose `host` label is `zcrypto-mon` are dropped from both result sets before the comparison; nodes of rules in `EXCLUDED_GROUPS` and of the seven `DIRECT_SHIPPED_RULES` are not sent, which leaves 102 nodes at this plan's base, 96 Prometheus and 6 Loki. A test holds `DIRECT_SHIPPED_RULES` equal to what the measured basis's listing prints for the tree, so an eighth rule that selects a direct shipper's stream fails the test rather than the comparison.
- The seven daily runs are the daily operations pass's (the owner's word of 2026-10-03), and they start on a date the tree holds, not on the stack table, which carries both stacks from phase 1 to retirement: `ops_daily.COMPARISON_FROM`, `None` until R-records-2 sets it to R9's day, the section also needing both stacks in the table so that retirement ends it with no edit. From that day the `report` run that prints the markdown — never the `--journal-entry` run, so a pass runs the comparison once — runs `grafana-compare.py` for the preceding day through a runner injected as `read_soak_verdict`'s is, and prints its last line under a `## Comparison` section. The section moves no exit code: a difference is a finding for the cutover pull request, not the fleet's state. Task 4's daily-ops edit names the section and has the pass's journal entry carry its line; the cutover pull request cites the seven.
- The test stubs `grafana_auth.vault_var` and `urllib.request.urlopen` as `tests/test_grafana_query.py`'s `_Recorded` does, feeding canned result sets: the same; a value off by 1e-5; a label set present on one stack whose nearest row on the other differs from it in one label other than `host`, so a comparison keyed on a subset of the labels fails it; empty against empty; empty against one row; a stack refusing; the exclusions by name; the instants' alignment; and the last line of each of the three outcomes.
- `test_the_walk_sends_every_query_node_but_the_three_exclusions` runs the walk over the real `infra/grafana/alerts.yaml` with both stacks answering empty, and holds the (expression, query path) pairs each stack is sent at each instant, counted with their repeats, equal to those the test computes from the YAML itself, never through the script's walk: every node whose `datasourceUid` is a placeholder, less the nodes of `EXCLUDED_GROUPS` and `DIRECT_SHIPPED_RULES`, each on its placeholder's path, both paths present. Two fixture rule files hold the refusals, an unknown `datasourceUid` and a walk that sends nothing, each ending `compare: failed: …` with exit 2.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script, the section, the orphan line and the procedure** — the stack table read, the rule file walked, the instants built, the queries sent, the comparison, the report; `COMPARISON_FROM` and the section; the push script's orphan line.
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_grafana_compare.py tests/test_ops_daily.py tests/test_grafana_push_sh.py tests/test_scripts_have_tests.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The consumers**

```bash
grep -rl --include='test_*.py' 'grafana-push.sh\|ops_daily\|ops-daily\|runbooks/mon\.md\|grafana_auth\|grafana-compare' tests/ | sort
```

Run every test file the listing names, with `tests/test_scripts_have_tests.py`, `tests/test_error_paths_are_logged.py`, `tests/test_code_prose_citations.py` and `tests/test_prose_chars.py`.

- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(grafana): a comparison of every rule's query on both stacks at the same 24 instants, three exclusions by name, the daily pass's from its first day; a skipped group's live rule named as such`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the tolerance widened; an empty result matched against a row; an exclusion dropped; a refused stack read as a match; the instant sent to one stack only; the `${GRAFANA_LOKI_DS_UID}` nodes left unsent; label sets compared on `host` alone; a run with differences ending `0 differences`; the `## Comparison` section printed before `COMPARISON_FROM`; the section printed with one stack in the table; a skipped group's live rule printed as not in `alerts.yaml`; a skipped group's live rule left out of the prune.

---

### Task 3: The four drill procedures and the node-dark procedure

**Files:**
- Modify: `infra/runbooks/drills-telemetry.md` (four sections of seven parts each; the standing rule's subject list gains the node; the bounds derivation names the node's group)
- Modify: `infra/runbooks/mon.md` (a `mon-dark` procedure: what to read and do while the node is down or being rebuilt, and what nothing pages from it yet)
- Test: none new; `tests/test_internal_terms_not_operator_visible.py` and the runbook tests already walk both pages.

**Interfaces:**
- Consumes: the seven-part shape and the entry contract of `docs/reference/drill-log.md`'s preamble; `mon.md`'s anchors `mon-store-restart`, `mon-push`, `mon-token-rotate`, `zcrypto-mon-ingest-dark`, `zcrypto-mon-store-down`, `zcrypto-mon-shipper-loss`; the rule waits `zcrypto-mon-ingest-dark` `for: 5m`, `zcrypto-mon-store-down` `for: 3m`, `zcrypto-alloy-dark-*` `for: 10m` plus the ~5 min staleness term, every group at 60 s; the healthchecks.io check's `timeout 600 + grace 600` of D16, and the self-check's three conditions, rule evaluation fresh, a fleet sample under five minutes old and Loki ready, on its five-minute timer; phase 1's R2 (its TCP `22` rule), R3, R8 and R9 lines, which the rebuild drill re-runs.
- Produces, for the Rollout and the drill log: the anchors `drill-w1` (the store restart), `drill-w2` (the 30-minute power-off), `drill-w3` (the rebuild from nothing), `drill-w4` (the shipper stop on the secondary); the scenario ids `W1` to `W4` for the drill-log headings; `mon.md#mon-dark`, the anchor the node's healthchecks.io check cites.

**What this task decides, where the spec leaves it open:**
- The scenario letter is `W`, its runs `W1` to `W4` as `A1` and `A2` are drill A's: `M` is the proven tier's Kraken-maintenance scenario (`drills-telemetry.md`'s *Re-verifying an already-proven scenario* and the archived matrix of `T0049`), and the letters A to T are taken across the two drill pages, the drill log and that matrix, where `W` occurs in none.
- W1's bounds: a bare `systemctl restart prometheus` and then a bare `systemctl restart loki`, each with Grafana running, each read for error pages in the shadow channel within three minutes and for `health != ok` on the rules endpoint; then the ordered restart, `mon.md#mon-store-restart`, which must page nothing and leave every rule `health=ok`; the last leg stops Caddy with the stores and Grafana running until the first `zcrypto-alloy-dark-*` page (ops or the bridgehead) reaches the shadow channel, `zcrypto-mon-ingest-dark` owing its page about 10 minutes after the stop (`for: 5m` plus staleness) and the first per-host page about 16 (`for: 10m` plus staleness plus the interval), the order the exposure page's runbook will rest on. Caddy is started at that first page: the self-check withholds its ping once no fleet sample is under five minutes old, so its last ping falls within five minutes of the stop and the node's check goes down 20 minutes after it, which leaves about four minutes after the first alloy-dark page; a later start puts the check down and brings W2's two pages. Expected after the leg: `zcrypto-mon-shipper-loss` for ops in the shadow channel about fifteen minutes after Caddy returns, ops' Alloy having given up on its node-bound log batches after about seven minutes of the stop, holding up to six hours.
- W2's bounds: the node's own check pages natively at `timeout 600 + grace 600` from its last clean ping, so inside about 20 minutes of the power-off; Cloud's `zcrypto-hcio-watchdog` trails by about 7 minutes and is announced beforehand; the Cloud leg's "no gap" is `count_over_time(up{host="<host>", job="integrations/unix"}[2h])` on Cloud across the window reading 120 give or take an edge sample for every host that ships to the node, `ops` and `zaccess` at R3; at boot, no error page in the shadow channel and every rule `health=ok` on the rules endpoint; the node's replay is the same read on the node once the shippers' WAL has drained; the lines lost are `sum(count_over_time({host="ops", container!="liquidations"}[2h]))` on each stack across the window, the difference the figure — `liquidations` is the poller's own push, which reaches Cloud alone until the cutover hands it over, so counting it would read two hours of it as lost. `zcrypto-mon-shipper-loss` for ops follows in the shadow channel, as after W1's last leg.
- W3 is phase 1's R2 for its TCP `22` rule alone, re-added to the `zcrypto-mon` firewall for both families, since phase 1's R3 removed it and the bootstrap connects as root on port 22; then phase 1's R3 (bootstrap, alias, preview, converge, its end removing the rule again), R8 (the push) and R9's first rules read, run on a rebuilt Linode, with the host key re-read in LISH and the stale `known_hosts` line removed first; the cached token is refused and re-minted by the converge (D7), which the drill reads as `changed` on the token task; measured from the rebuild's start, the firewall step inside it, to the first `health=ok` rule. Must fire: the node's healthchecks.io check, the node pinging nothing from the rebuild until the push schedules its rules, and Cloud's `zcrypto-hcio-watchdog` about 7 minutes behind it, announced beforehand as W2's are; `zcrypto-mon-shipper-loss` for ops follows once the node takes ops' metrics again.
- W4 is drill K's induction on the secondary, `sudo docker stop grafana-alloy` on `zcrypto-red`, read on the node: `up{host="zcrypto-red"}` absent, never 0, and `zcrypto-alloy-dark-capture-secondary` in the shadow channel on Cloud's timing; the `since` cell of `fleet-pins.md`'s secondary Alloy row is re-trued with the restore.
- `mon-dark` is the phase-2 shape of the node-dark procedure phase 3 widens from `observability.md`'s `grafana-cloud-dark`: it says that while the node pages the shadow channel alone its death reaches the owner through its healthchecks.io check and, about seven minutes later, Grafana Cloud's `zcrypto-hcio-watchdog`, which counts every down check, what to read on the host, that a store outage drops the alert history of its minutes, and the two figures the drills measure: [[ROLLOUT: R3's W2 reading — the log lines a 30-minute outage lost]] and [[ROLLOUT: R3's W3 reading — the time from the rebuild to the first evaluated rule]], both written as prose with no number until read.

- [ ] **Step 1: The four sections and the standing-rule edit**, each section's seven parts, every bound derived from a quoted `for` or a quoted check setting.
- [ ] **Step 2: The `mon-dark` section**
- [ ] **Step 3: The consumers**

```bash
uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_count_list.py tests/test_ops_daily.py tests/test_drill_log.py -q -p no:cacheprovider
```

- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `docs(runbooks): the node's four telemetry drills and its dark procedure`, with the trailer; no guard changes, so no probe.
- [ ] **Step 6: The tree is clean**

---

### Task 4: Three skills take the dual period — the push skill's two-stack wording, the Alloy bump's destinations and the daily pass's comparison

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md` (every push in the dual period goes to both stacks from one checkout; the node's invocation per `mon.md#mon-push`; the two sentences phase 1 added stay)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (the `## Comparison` section Task 2's step prints from `COMPARISON_FROM`, what each of its last lines means, and step 7's entry carrying that line)
- Modify: `.claude/skills/zcrypto-bump-alloy/SKILL.md` (Step 3's shipping-health `grep` prints a `failed_total` and a `dropped_entries_total` for each destination the host ships to, each read 0; the node's own `zcrypto-mon-shipper-loss` is the fleet-wide reading)

**Interfaces:**
- Consumes: Task 1's endpoint text, whose `name = "mon"` labels the node's destination `remote_name="mon"` on Alloy's counters; Task 2's `## Comparison` section and the comparison's three last lines; `GRAFANA_SKIP_RULE_GROUPS` and the stack table.
- Produces: a push skill a push to either stack passes; a bump skill whose Step 3 reads every destination a host ships to, true from this pull request's merge whichever hosts ship to the node yet; a daily-ops skill whose journal entry carries the comparison's line.

**What this task decides, where the spec leaves it open:**
- The daily-ops skill names the `## Comparison` section the pass prints from `COMPARISON_FROM` (the owner's word of 2026-10-03, Task 2's step) and what its last line means: `0 differences`, a clean day; `<n> differences`, a finding for the cutover pull request, never a remediation; `compare: failed: …`, not a clean day, the stack it names read as a source that could not be read. Step 7's entry carries that line beside the paragraph `--journal-entry` prints, since the cutover's seven days are read from the journal. Its telemetry clause already names the node's Alloy unit (phase 1's Task 8).
- The edits are in the skills' bodies, outside the always-loaded set, so the commit owes no `Ambient grows by` line.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*; each sentence lands on a ground it names, the check that enforces it named in the sentence.
- [ ] **Step 2: The three edits**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_daily_ops_skill.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_grafana_push_sh.py -q -p no:cacheprovider`, the tests that read the three skills.
- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `claude(skills): a push in the dual period goes to both stacks, an Alloy bump reads each destination, and the daily pass records the comparison`, with the trailer; a `claude` commit carrying no other file.
- [ ] **Step 6: The tree is clean**

Then the first pull request opens through the `open-pr` skill over Tasks 1 to 4, a different agent reads the branch, and `merge-pr` merges it; the Rollout's R1 follows from merged `develop`.

---

### Task 5: ops ships to both — its six names and its config in one tree state, the node's own dead-man wired, the check map

**Files:**
- Modify: `infra/ansible/roles/ops/templates/alloy-secrets.env.j2` (six `MON_*` lines appended; its header's comments the File structure lists for Task 5 re-trued)
- Modify: `infra/ansible/roles/ops/files/config.alloy` (the second `endpoint` in `prometheus.remote_write "grafana"`; `loki.write "mon"`; `loki.process "parse"`'s `forward_to`; `netdev { device_exclude = "^(veth|br-)" }` in `prometheus.exporter.unix "host"`; the header's "the NAS's Alloy reads the same six names" re-trued)
- Modify: `infra/runbooks/mon.md` (`mon-secrets` step 4, host by host, since a reload keeps the environment the process started with and the container roles render the secrets file only on a converge carrying the host's Alloy digest: the bridgehead by its converge, whose handler restarts Alloy; ops, the cache nodes and the capture pair by a converge carrying the host's running Alloy digest and then `sudo docker compose up -d` in the Alloy project, proven by `.State.StartedAt` moving, the capture pair in its attended form under `.claude/rules/fleet-deploys.md`; the NAS by its apply, `-e nas_apply_compose=true`, proven by `.Created` moving)
- Modify: `infra/ansible/host_vars/zcrypto-mon/vars.yml` (`mon_selfcheck_healthcheck_url: "{{ selfcheck_healthcheck_url }}"`)
- Modify: `infra/ansible/host_vars/zcrypto-mon/vault.yml` (the owner's P1 appends `selfcheck_healthcheck_url`; committed by this task's commit)
- Modify: `tests/fixtures/healthchecks_descriptions.json` (the eleventh check, fetched through the read-only key)
- Modify: `infra/runbooks/observability.md` (the dead-man map's row and its count; "Ten checks exist" becomes eleven)
- Modify: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py` (`rules_fresh`'s refusal names the series it did not find, `grafana_alerting_ticker_last_consumed_tick_timestamp_seconds` or `grafana_alerting_schedule_alert_rules`, where it says "no scheduler tick" — phase 1's rollout left it; its test in `tests/test_mon_selfcheck.py` reads the name in the reason)
- Test: `tests/test_infra_alloy_series.py` (the endpoint guard, the literal case and the template-config case parametrised over ops; the `loki.write "mon"` guard; the `netdev` guard)
- Test: `tests/test_ops_daily.py` (`len(checks) == 11`, and `test_todays_ten_real_descriptions_all_pass` renamed `test_todays_real_descriptions_all_pass`, its name carrying no count)

**Interfaces:**
- Consumes: Task 1's group vars, six names, endpoint text and helper; the ops role's `reload alloy` handler and its digest-gated block, which renders the secrets file and copies the config only on a converge carrying `ops_alloy_digest`, the render notifying nothing, so the recreate is the Rollout's hand step; the `mon` role's `mon_selfcheck_healthcheck_url` default and the ops role's semantics for an empty URL; `ops_daily.check_descriptions`, which holds every check's description to a `Runbook: infra/runbooks/<file>#<anchor>` that resolves.
- Produces, for Tasks 6 to 8 and the Rollout: the six template lines; the `loki.write "mon"` block's text and the `forward_to` line; on the node, `up{host="ops"}` under every ops job and the ops log streams; the check `zcrypto-mon` (tags `mon selfcheck`) in the fixture and the map.

**What this task decides, where the spec leaves it open:**
- The vault name is `selfcheck_healthcheck_url` in `host_vars/zcrypto-mon/vault.yml`, wired in `vars.yml` as the ops host wires its six, since phase 1's P2 script refuses a second run and the value is appended by a P3-shaped `encrypt_string` line.
- The check's description cites `Runbook: infra/runbooks/mon.md#mon-dark` and names what withholds the ping: rule evaluation stale, no fleet sample fresh, Loki not ready; its tags are `mon selfcheck`, the map's row keyed on them.
- The `netdev` guard holds the exclusion `^(veth|br-)` present on ops, the capture config and the NAS config and absent from the cache and access configs, parametrised so Tasks 7 and 8 add their files to the present side.
- The `loki.write "mon"` guard holds the `forward_to` of `loki.process "parse"` to exactly `[loki.write.grafana.receiver, loki.write.mon.receiver]`, `loki.write "mon"` to one endpoint reading the three `MON_LOKI_*` names, and `loki.write "grafana"` to one endpoint reading the three `GRAFANA_LOKI_*` names.

The template lines, determined by the vault and group names:

```
MON_PROM_URL={{ mon_ingest_prom_url }}
MON_PROM_USERNAME={{ mon_ingest_fleet_user }}
MON_PROM_PASSWORD={{ mon_ingest_fleet_password }}
MON_LOKI_URL={{ mon_ingest_loki_url }}
MON_LOKI_USERNAME={{ mon_ingest_fleet_user }}
MON_LOKI_PASSWORD={{ mon_ingest_fleet_password }}
```

The log component and the forward line, determined by D13 and the existing `loki.write "grafana"`:

```
loki.process "parse" {
  forward_to = [loki.write.grafana.receiver, loki.write.mon.receiver]
```

```
loki.write "mon" {
  endpoint {
    url = sys.env("MON_LOKI_URL")

    basic_auth {
      username = sys.env("MON_LOKI_USERNAME")
      password = sys.env("MON_LOKI_PASSWORD")
    }
  }
}
```

The exclusion, determined by D12:

```
prometheus.exporter.unix "host" {
  set_collectors = ["cpu", "loadavg", "meminfo", "filesystem", "netdev", "textfile"]

  netdev {
    device_exclude = "^(veth|br-)"
  }
```

**Operator step P1 (attended), before Step 1: the node's healthchecks.io check.** The owner mints the check `zcrypto-mon` in healthchecks.io with `timeout 600`, `grace 600`, its Slack channel and the description above; reads the ping URL without echo and appends it to `host_vars/zcrypto-mon/vault.yml` as `selfcheck_healthcheck_url` through `ansible-vault encrypt_string`, phase 1's P3 shape; then re-fetches `tests/fixtures/healthchecks_descriptions.json` through the read-only key, `name`, `tags` and `desc` alone. The URL is a ping secret and never enters argv, stdout or a tracked file in clear.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the tests and read the failure**
- [ ] **Step 3: The template, the config, the comments the File structure names for this task, the two host-vars files, the self-check's reason, the fixture, the map row and `mon-secrets` step 4**
- [ ] **Step 4: Dry-start the edited config in Task 1's Step 4 form, against v1.19.2's binary** — Expected: loads clean.
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file Task 1's Step 6 listing names, and every one `grep -rl --include='test_*.py' 'zcrypto-mon-selfcheck\|host_vars/zcrypto-mon\|healthchecks_descriptions\|observability\.md\|runbooks/mon\.md' tests/` names, `tests/test_mon_selfcheck.py`, `tests/test_infra_unattended_upgrades.py` and `tests/test_ops_daily.py` among them at this plan's base.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): the ops Alloy ships unfiltered to the node beside Grafana Cloud, and the node's self-check pings its own dead-man`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `MON_PROM_*` credential substituted into the Cloud endpoint; the second receiver dropped from the `forward_to`; the `netdev` exclusion removed; the self-check's refusal back to naming no series; the fixture's `zcrypto-mon` entry removed.

Then the second pull request opens over Task 5, once the Rollout's P2 has read the log fan-out; the Rollout's R2 and R3 follow.

---

### Task 6: The cache nodes ship to both — the six names and the config in one tree state, the template test's equality kept

**Files:**
- Modify: `infra/ansible/roles/cache/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5 appended; its header's comments the File structure lists for Task 6 re-trued)
- Modify: `infra/ansible/roles/cache/files/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; no `netdev` exclusion, per D12)
- Test: `tests/test_infra_alloy_series.py` (`test_the_cache_secrets_template_renders_every_name_the_config_reads` unchanged, holding `read == rendered` over the commit; the endpoint, `loki.write`, `netdev`-absent and literal guards parametrised over the cache file and template)

**Interfaces:**
- Consumes: Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5; the cache role's `reload alloy` handler and its digest-gated block, which renders the secrets file and copies the config on a converge carrying `cache_alloy_digest`.
- Produces, for the Rollout: on the node, `up{host=~"zcrypto-valkey[123]"}` under `integrations/unix`, `integrations/self`, `valkey` and `sentinel`, the redis families unfiltered, and the three nodes' journal streams.

**What this task decides, where the spec leaves it open:**
- The template's six lines and the config's six reads land in this one commit: the equality test holds before and after it and fails on either half alone, so it is neither widened nor restored.
- The cache config's `host` is `constants.hostname`, so the one file labels all three nodes on the node's leg as it does on Cloud's; nothing per node is rendered.
- The "how many distinct commands each Valkey node has served" reading the spec leaves to the first cache node's read is R4's `count by (__name__) ({__name__=~"redis_command.*", host="zcrypto-valkey1", cmd!=""})` on the node, recorded with the family that answered, not gated: the tree names no exporter family carrying a `cmd` label, so the read matches the family rather than a spelling.

- [ ] **Step 1: Write the failing tests** (the guards; the equality test, unchanged, passes before and after the commit and fails on either half alone).
- [ ] **Step 2: Run the tests and read the failure**
- [ ] **Step 3: The template, the config and the template's header**
- [ ] **Step 4: Dry-start the edited config in Task 1's Step 4 form, against v1.19.2's binary**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file Task 1's Step 6 listing names.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): a cache node's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `MON_PROM_*` credential substituted into the Cloud endpoint; a `netdev` exclusion added to the cache config.

Then the third pull request opens over Task 6, after R3's drills; the Rollout's R4 follows. The inside-box records pull request (R-records-1) closes the box's work.

---

### Task 7: After the box — the NAS ships to both in one state

**Files:**
- Modify: `infra/nas/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; the `netdev` exclusion)
- Modify: `infra/ansible/roles/nas/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5; its header's comments the File structure lists for Task 7 re-trued)
- Modify: `infra/ansible/roles/nas/tasks/main.yml` (the comment above `render the alloy secrets env file`, "Grafana Cloud creds for the NAS's Alloy", re-trued; no task changes)
- Modify: `infra/nas/README.md` (the secrets file's names)
- Test: `tests/test_infra_alloy_series.py` (the endpoint, `loki.write`, `netdev`, literal and template-config guards parametrised over the NAS file and template)

**Interfaces:**
- Consumes: the NAS role's apply, `-e nas_apply_compose=true`, whose `compose up -d` recreates on the env file's change and whose `compose restart alloy` re-reads the config, so one converge lands both files and restarts Alloy after them (D14), and which also restarts `archive-pull`; Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5.
- Produces, for the Rollout: on the node, `up{host="nas"}` under its jobs and the NAS's streams.

**What this task decides, where the spec leaves it open:**
- The NAS merges in a pull request of its own after the box, its file serving one host converged in one pass; the capture pair's is the next, since its file arms the drift assert on two hosts converged an hour apart.
- The NAS's recreate is proven by the Alloy container's `.Created` moving and its `RestartCount` unchanged, read with `/usr/local/bin/docker`: the apply's `compose restart alloy` runs under the flag whatever changed and moves `.State.StartedAt` on the container it keeps, so `started` cannot tell a recreate that loaded the names from a restart of the old container; the NAS's `-compat` build question does not arise, since the Alloy image is upstream's with no variant (`fleet-pins.md`'s row).

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the tests and read the failure**
- [ ] **Step 3: The config, the template, the comments the File structure names for this task, the README**
- [ ] **Step 4: Dry-start the edited NAS config in Task 1's Step 4 form, against v1.19.2's binary**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file Task 1's Step 6 listing names, and every one reading the NAS README.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): the NAS's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `MON_PROM_*` credential substituted into the Cloud endpoint; the second receiver dropped from the `forward_to`; the `netdev` exclusion removed.

Then the fourth pull request opens over Task 7, not before [[ROLLOUT: the box's closing date]]; the Rollout's R5 follows.

---

### Task 8: The capture pair ships to both — the six names and the config in one tree state

**Files:**
- Modify: `infra/ansible/roles/capture/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5 appended; its header's comments the File structure lists for Task 8 re-trued)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; the `netdev` exclusion; the header's "the same six names the ops and nas Alloy copies read" re-trued)
- Test: `tests/test_infra_alloy_series.py` (the guards, the literal case and the template-config case parametrised over the capture file and template)

**Interfaces:**
- Consumes: Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5; the capture role's `reload alloy` handler and its digest-gated block, which renders the secrets file and copies the config on a converge carrying `capture_alloy_digest`.
- Produces, for the Rollout and phase 3: on the node, every capture-host family unfiltered, `capture_app`, `engine_app`, `cache_proxy`, `integrations/unix` and `integrations/self` under both hosts, the one config scraping all five on each, with `engine_app` and `cache_proxy` at `up` 0 on `zcrypto-red`; the journal streams of both; the template-config case over its four pairs, the cache test over the fifth.

**What this task decides, where the spec leaves it open:**
- The capture pair joins the template-config case at `read == rendered`, as ops and the NAS did; with it every pair is held, the bridgehead's at `read ⊆ rendered` and the cache pair by its own test.
- The second endpoint's queue is its own, so the primary's capture series keep reaching Cloud whatever the node does; nothing in this task touches `logship-secrets.env.j2` or the capture compose template (D13's reason).

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the tests and read the failure**
- [ ] **Step 3: The template, the config and the comments the File structure names for this task**
- [ ] **Step 4: Dry-start the edited config in Task 1's Step 4 form, against v1.19.2's binary**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file Task 1's Step 6 listing names, `tests/test_clock_offset.py` among them.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): a capture host's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `MON_PROM_*` credential substituted into the Cloud endpoint; the second receiver dropped from the `forward_to`; the `netdev` exclusion removed.

Then the fifth pull request opens over Task 8; the Rollout's R6 to R9 and the second records pull request follow.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches a fleet host, the node, Grafana Cloud, Slack, healthchecks.io or the Linode Cloud Manager, or writes a secret. P0 ran on the workstation on 2026-10-03; P1 is Task 5's operator step; P2 runs on the workstation before the second pull request opens. Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its line to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`. `W$` is the workstation at the repository root, `H$` a shell on the named host (`ssh hp` for ops, `ssh db1` to `db3`, `ssh red`, `ssh zcrypto`, `ssh mon`, the NAS by its alias). The running Alloy digest a converge is handed is read off the host immediately before, `docker inspect grafana-alloy --format '{{.Config.Image}}'`, the `sha256:…` after the `@`, and matched against `docs/reference/fleet-pins.md` (`b8ec653c4423`, v1.19.2 on all seven); the running capture digest is read the same way from `zcrypto-capture`, `.Config.Image`, never `.Image`. `KRAKEN` below is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, taken at planning and again immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. The node's own reads are `grafana-query.py --stack mon`; Cloud's are the same tool unnamed. `.tmp/mon-dual/` at the repository root holds what a later step reads back, named by that literal path in each step. The preview of each dual-shipping converge, R1 to R6, names that host's Alloy files and nothing else, R1's test; a preview naming anything else holds the host, the bump-alloy skill's rule. On ops, the cache nodes and the capture pair a reload handler that fails stops that host before its recreate, since the recreate starts the same config: the host's Alloy log is read for the refusal first.

**The per-host proof, used by every converge below.** Before the converge, `count by (job) ({host="<host>", device!~"veth.*|br-.*"})` on both stacks and, on Cloud, `count({host="<host>", device!~"veth.*|br-.*"})` and `count({host="<host>", device=~"veth.*|br-.*"})`, each kept under `.tmp/mon-dual/`; after it, the same four reads: Cloud's counts outside those devices unchanged, the bridgehead's `up` under `integrations/self` the one admitted addition (R1); Cloud's veth and `br-` count reading no series five minutes after the recreate on a host whose config gains the `netdev` exclusion, ops, the NAS and the capture pair, since the exclusion sits in the unix exporter upstream of both endpoints (spec D12), and unchanged on the bridgehead and the cache nodes; the node's per-job counts present for every job the host's config scrapes and each above Cloud's for that job, the `zcrypto-mon-shipper-loss` row for the host reading 0 after an hour, and the Alloy on the host reading `prometheus_remote_storage_samples_failed_total` 0 for both `url` values on `127.0.0.1:12345/metrics`. The host's reading goes into the records: [[ROLLOUT: R1 to R6, each host's `count by (job)` on the node after its converge, against Cloud's count for it — bridgehead 37, ops 369, cache 83/82/82, NAS 165, `zcrypto-red` 141, `zcrypto` 452 on 2026-10-01]].

**P0. The workstation proof that decides the tree states** (spec D14's open question; before this plan is final). Alloy v1.19.2, the fleet's pin, from its release binary on the workstation, with the ops config as it stands and a secrets file carrying the six `GRAFANA_*` names against a scratch Prometheus; then a `POST /-/reload` with the Task 5 config, its `MON_*` names unset in the process. Read: whether the first endpoint keeps shipping across and after the reload, what the reload returns against the handler's accepted `[200, -1]`, and what the process logs. The verdict, taken 2026-10-03 on the workstation: Alloy v1.19.2's release binary, the ops config with its three container paths pointed at the workstation's `/proc`, `/sys`, `/` and a scratch textfile directory, the six `GRAFANA_*` names pointed at a scratch Prometheus 2.53.3 with its receiver on and a scratch Loki 3.7.8, shipped `up{host="ops"}` under four jobs; the `POST /-/reload` with the Task 5 config and no `MON_*` name in the process answered `200 config reloaded`, the graph re-evaluated with no error, and the first endpoint kept shipping across and after it (`prometheus_remote_storage_samples_total` 576 before, 872 eighty seconds after, 0 failed, 0 pending); the second endpoint started under `remote_name="mon"` with `url=""`, so `name = "mon"` is accepted by the pin, and it retries its own queue with `Post "": unsupported protocol scheme ""` at `level=warn`, 1,631 samples pending at eighty seconds and nothing of the first endpoint's touched. The reload is harmless and 200: every container role takes one state, converge then recreate, and the tasks above are written to it.

The lines P0 ran, 2026-10-03, in a scratch directory `$L` holding the three release binaries (`alloy-linux-amd64` v1.19.2, `prometheus-2.53.3.linux-amd64/prometheus`, `loki-linux-amd64` 3.7.8), a copy of `infra/ansible/roles/ops/files/config.alloy` as `$L/cfg/config.alloy` with its three container paths pointed at the workstation (`procfs_path = "/proc"`, `sysfs_path = "/sys"`, `rootfs_path = "/"`, the textfile `directory` at `$L/textfile`), the same copy plus Task 5's `name = "mon"` endpoint, `loki.write "mon"` and the two-receiver `forward_to` as `$L/cfg/task6.alloy`, a scratch Prometheus config with no scrape job, and a scratch single-binary Loki config on the filesystem with `instance_addr: 127.0.0.1`:

```
W$ cd "$L" && ./prometheus-2.53.3.linux-amd64/prometheus --config.file=prom/prometheus.yml --storage.tsdb.path=prom/data --web.listen-address=127.0.0.1:19090 --web.enable-remote-write-receiver > prom.log 2>&1 &
W$ ./loki-linux-amd64 -config.file=loki/loki.yaml > loki.log 2>&1 &
W$ printf 'GRAFANA_PROM_URL=http://127.0.0.1:19090/api/v1/write\nGRAFANA_PROM_USERNAME=u\nGRAFANA_PROM_PASSWORD=p\nGRAFANA_LOKI_URL=http://127.0.0.1:13100/loki/api/v1/push\nGRAFANA_LOKI_USERNAME=u\nGRAFANA_LOKI_PASSWORD=p\nHC_METRICS_PATH=/metrics\n' > secrets.env
W$ (set -a; . ./secrets.env; set +a; ./alloy-linux-amd64 run --disable-reporting --server.http.listen-addr=127.0.0.1:12346 --storage.path="$L/alloy/store" "$L/cfg/config.alloy" > alloy.log 2>&1 &)
W$ sleep 100; curl -sS -G --data-urlencode 'query=count(up{host="ops"})' http://127.0.0.1:19090/api/v1/query; curl -sS http://127.0.0.1:12346/metrics | grep '^prometheus_remote_storage_samples_total'
W$ cp cfg/task6.alloy cfg/config.alloy && curl -sS -X POST -w '%{http_code}\n' http://127.0.0.1:12346/-/reload
W$ sleep 80; curl -sS http://127.0.0.1:12346/metrics | grep -E '^prometheus_remote_storage_(samples_total|samples_failed_total|samples_pending|samples_retried_total)\{'; grep -E 'level=(error|warn)' alloy.log | grep -v journal | sed -E 's/ts=[^ ]+ //' | sort | uniq -c
```

The first read printed `4` and `576`; the reload printed `config reloaded` and `200`; the second read printed, per `remote_name`, `cd78c7` (the Cloud endpoint's hash name) `samples_total 872, failed 0, pending 0, retried 0` and `mon` `samples_total 115, failed 0, pending 1631, retried 110`, and two `level=warn msg="Failed to send batch, retrying" … remote_name=mon url="" err="Post \"\": unsupported protocol scheme \"\""` lines; the journal tailer's one error line is the lab's missing `/host/journal`, not the proof's. Loki's own query path was not read: the lab's journal source had nothing to ship, and the fan-out question is P2's.

**P2. The log fan-out, read on the workstation before the second pull request opens** (spec D13's premise, unmeasured until now: `loki.process "parse"` hands each entry to the receivers of its `forward_to`, and whether a `loki.write "mon"` that cannot deliver holds `loki.write "grafana"` behind it has not been read). Alloy v1.19.2's release binary in Task 1's Step 4 form, with a scratch config of the ops pipeline's shape: a `loki.source.file` tailing a scratch file that a shell loop appends one line to each second, `loki.process "parse"` forwarding to `[loki.write.grafana.receiver, loki.write.mon.receiver]`, `loki.write "grafana"` at a scratch Loki 3.7.8 as P0's was, and `loki.write "mon"` at a closed loopback port. Read: the scratch Loki's count of the file's lines over each five minutes, for fifteen minutes, against the loop's own count. The scratch Loki keeping the loop's count throughout is the premise read true, and Task 5's pull request opens; a count that falls behind while the mon leg retries is a stop, since every host shipping logs would then stall its Cloud log leg while the node is down, and the design goes back to the owner before the second pull request opens. The reading is written into the spec's measured basis by amendment in R-records-1; the scratch processes, files and directories are removed after.

**Precondition from phase 1.** Phase 1's R9 read the node-alone head series at 9,740 after the first push (8,033 before it), under the 15,000 line, so this plan proceeds; the bar of 40,000 and the cap of 16GB were sized for 9,700 to 10,300, and the reading sits inside that band. The series the first hosts add are read against the bar at every step below, `prometheus_tsdb_head_series{host="zcrypto-mon"}` after each converge.

**R0. The operands, read once.** `git switch develop && git pull --ff-only && git status --porcelain` empty; `mkdir -p .tmp/mon-dual`; `infra/scripts/count-list.sh converges-inside-a-kraken-window | tee .tmp/mon-dual/kraken-window-count`; the node's head with no fleet host shipping, `uv run python infra/scripts/grafana-query.py --stack mon 'prometheus_tsdb_head_series{host="zcrypto-mon"}' | tee .tmp/mon-dual/head-node-alone`; `KRAKEN` at planning; the seven running Alloy digests read off the hosts and matched to `fleet-pins.md`.

**R1. The bridgehead** (Task 1; after the first pull request merges). No Kraken read owed. `W$ ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me 'dpkg-query -W alloy'` reads the version Task 1's dry-start ran, `1.20.0-1`; another version holds R1 until that dry-start is re-run at it. `W$ infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` — the preview names `/etc/default/alloy` and `/etc/alloy/config.alloy` changed and nothing else; the real pass restarts Alloy through the role's handler. Then the per-host proof; `up{host="zaccess", job="integrations/self"}` present on both stacks.

**R2. ops** (Task 5; after the second pull request merges). `KRAKEN` immediately before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<running>` — the preview names `alloy-secrets.env` changed (`no_log`, so the changed-files report is the signal) and `conf/config.alloy` changed; the handler's reload reads 200, and the outgoing process retries the `mon` endpoint's empty URL at `level=warn`, P0's shape, touching nothing of the Cloud endpoint. Then `H$ cd /etc/zcrypto-ops/alloy && sudo docker compose up -d`, which recreates on the env file's change; `docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'` reads the same digest, 0 restarts and a `started` after the converge. A `started` that did not move is a stop: the env file's change did not reach the service hash, and the recreate is `sudo docker compose up -d --force-recreate alloy`, read the same way, which R4 and R6 then take as their recreate. `Ops · ERROR logs` fires on the outgoing container's two `remotecfg` lines, the bump skill's known shape. Then `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`, which renders the self-check's URL; `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'` reads `rules=ok (…) fleet=ok (…) loki=ok (…) -> pinged`, and healthchecks.io shows the check's first ping. The per-host proof for ops, with `uv run python infra/scripts/grafana-query.py --loki 'sum by (container) (count_over_time({host="ops"}[1h]))'` on both stacks an hour after the recreate for the streams, the node's containers Cloud's less `liquidations`, the poller's own push, which reaches Cloud alone until the cutover; `zcrypto-mon-ingest-dark` reads `inactive ok` on the node's rules endpoint; the node's head series read against the bar.

**R3. The three node drills** (Task 3; while only the bridgehead and ops ship). Each is its section's seven parts, one at a time, the revert verified by value before the next; each run gets its `docs/reference/drill-log.md` entry in the records pull request. Each is announced in the main channel beforehand, since Cloud's `zcrypto-hcio-watchdog` pages there on the node's check going down: W2 and W3 put the check down by construction, and W1's Caddy leg puts it down if it outruns its bound. W1 first, its two bare legs the one place a store is restarted under a running Grafana: the reading [[ROLLOUT: R3's W1 reading — a bare `systemctl restart prometheus`, and one of `loki`, under a running Grafana page, or not]] decides by Prometheus's leg whether `prometheus$` leaves `host_vars/zcrypto-mon/vars.yml`'s blacklist in a pull request of its own, with D17's reasoning line re-trued either way. W2 second; its reading fills `mon-dark`'s first slot. W3 third, the rebuild: the Linode rebuilt from a fresh Debian 13 image in the Cloud Manager, Backups still enabled, and phase 1's TCP `22` rule re-added to the `zcrypto-mon` firewall for both families; the host key re-read in LISH, then phase 1's R3, whose end removes the rule again, R8 and the first lines of R9; the cached token refused and re-minted; every rule `health=ok`; its reading fills `mon-dark`'s second slot.

**R4. The cache nodes** (Task 6; after the third pull request merges, after W3). One node per converge, `db1` then `db2` then `db3`, each outside the day's plan window: `ssh db<n> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"` before and after, the same two lines; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<n> --tags cache -e cache_alloy_digest=sha256:<running>`, the handler's reload 200; `H$ cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`; Alloy's `started` moved, its `RestartCount` 0; then the per-host proof. After `db1`, a day: [[ROLLOUT: R4's day read of `zcrypto-valkey1`'s Alloy headroom, `(go_memstats_sys_bytes - go_memstats_heap_released_bytes) / 402653184` under `job="integrations/self"` on Cloud, its maximum over 24 h against `zcrypto-fleet-alloy-memory-headroom`'s bar — under it, `db2` follows; at or over it, the owner is asked]]. Then `db2`, then `db3`, each the same. The command-count reading of `db1`, `count by (__name__) ({__name__=~"redis_command.*", host="zcrypto-valkey1", cmd!=""})` on the node, goes into the records with the family that answered.

**R-records-1. The inside-box records: one pull request.** From `develop`: the deploy-log rows the converges appended; `docs/reference/drill-log.md`'s three entries `W1`, `W2`, `W3`, each the preamble's clauses, and each run's findings in the `drills-telemetry.md` section it ran from, that page's standing rule; `mon-dark`'s two figures, W2's and W3's readings, written into `infra/runbooks/mon.md`; P2's reading in the spec's measured basis by amendment; `docs/reference/fleet-pins.md`'s `since` cells re-trued for every Alloy row a recreate moved (ops, the three cache nodes); `docs/reference/fleet.md`'s Services and Telemetry labels saying which hosts ship to both; the blacklist decision: when W1 read Prometheus's bare restart silent, T0217's `## Suggested next steps` gains its follow-on pull request, `prometheus$` out of `host_vars/zcrypto-mon/vars.yml` with `tests/test_infra_unattended_upgrades.py`'s `test_the_observability_node_keeps_prometheus_for_a_hand_pass` and `test_no_other_host_declares_a_blacklist` re-trued under their probe and D17's reasoning line, and when it paged, D17's line is re-trued here and nothing follows; T0217's findings gaining the readings; `infra/scripts/count-list.sh converges-inside-a-kraken-window | diff .tmp/mon-dual/kraken-window-count -` printing nothing. Its message carries every slot's reading taken so far.

**R5. After the box — the NAS** (Task 7; after the fourth pull request merges, on or after [[ROLLOUT: the box's closing date]]). No Kraken read owed: `W$ infra/ansible/scripts/converge.sh site.yml --limit nas --tags nas --check`, then `… -e nas_apply_compose=true`; the changed-files report names `config.alloy` and `alloy-secrets.env`; `archive-pull` restarted, its next pull line read in the NAS runbook's shape; the Alloy container's `.Created` moved, `H$ sudo /usr/local/bin/docker inspect grafana-alloy --format '{{.Created}} {{.RestartCount}}'` read before and after, since the apply's `compose restart alloy` moves `started` on a kept container too; the per-host proof.

**R6. The capture pair** (Task 8; after the fifth pull request merges). `zcrypto-red`: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the capture compose render `changed=false` and its restart handler silent, the Alloy reload 200; `H$ cd /etc/zcrypto-capture/alloy && sudo docker compose up -d`; `zcrypto-capture`'s `RestartCount` and `StartedAt` unchanged, Alloy's `started` moved; the per-host proof. Then, an hour later and attended, `zcrypto`: `KRAKEN` immediately before, away from a 4-hourly boundary and from any engine restart; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --skip-tags engine -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the reload 200; the same two reads; `H$ cd /etc/zcrypto-capture/alloy && sudo docker compose up -d`; `zcrypto-capture` untouched by both reads; the per-host proof. The node's head series read against the bar with the whole fleet shipping: [[ROLLOUT: R6's head-series reading with every host shipping, against R0's node-alone reading plus the fleet's 9,400 to 10,600, and the bar of 40,000]].

**R7. The shipper-stop drill on the secondary** (Task 3's W4; after R6, in an attended window). `KRAKEN` at planning and immediately before. Its section's seven parts; `zcrypto-red`'s Alloy row in `fleet-pins.md` re-trued with the restore; its entry in the second records pull request.

**R8. The boundary reading** (spec D20's first trap). One stored sample's timestamp first, `W$ uv run python infra/scripts/grafana-query.py 'timestamp(up{host="ops", job="integrations/unix"})'`, its value `t` to the millisecond, the same sample on both stacks since one Alloy sent it to both; then, once five minutes have passed, `count_over_time(up{host="ops", job="integrations/unix"}[5m] @ <t + 300>)` through `grafana-query.py` on each stack, unnamed and `--stack mon`, the `@` modifier fixing the range's end at `t + 300` exactly: a range closed on the left counts the sample at `t` and one open on the left does not, so the two readings differ by one exactly where the engines differ, where a range ending anywhere else reads alike on both. The two values recorded: [[ROLLOUT: R8's two readings — equal, or off by the boundary sample]], written into the spec's measured basis by amendment in the second records pull request, before phase 3's plan.

**R9. The comparison's clock starts.** The seven consecutive daily runs of `grafana-compare.py` start once the last host has 50 h of data on the node: [[ROLLOUT: the first day whose 00:00 UTC is at least R6's primary converge time plus 50 h — the comparison's first day]], since a run compares the day before it from its 00:00 and a rule's widest range reaches 26 h behind that; a rebuild of the node restarts them. The runs are phase 3's gate and are recorded there.

**R-records-2. The after-box records: one pull request.** The deploy-log rows; the `W4` drill-log entry and its findings in its `drills-telemetry.md` section; the `since` cells for the NAS and both capture hosts; the spec amendment of R8; `docs/reference/fleet.md` re-trued; T0217's `## Done so far` gaining this phase and its `## Suggested next steps` cut to phases 3 and 4; `ripe_when` set to the comparison's first day, and `COMPARISON_FROM` in `infra/scripts/ops_daily.py` set to it, from which the daily pass prints `## Comparison`. The commit `chore(fleet): every fleet host ships to the observability node beside Grafana Cloud`, its message carrying every reading, with the trailer.

## Resolution

Two of the spec's open questions are settled here: the bridgehead's Alloy gains `prometheus.exporter.self` with its second endpoint (Task 1), and the workstation proof of P0 decided the tree states, one per role, this plan written to its verdict. The third, the Cloud push URL and Loki hostname as label values on the node, is the owner's word of 2026-10-03, recorded in the spec's open questions: they age out with the node's 90 days, and the node's endpoint carries no relabel block, as the spec's invariant already holds. The items the spec left unmeasured and assigned to this phase are read in the Rollout: what a bare store restart does (R3, W1), the first cache node's command count (R4), the lines a node outage loses and the rebuild's exposure (R3, W2 and W3), the boundary (R8). The `prometheus` blacklist's fate is W1's: R-records-1 records it, and a silent bare restart puts its follow-on pull request in T0217's next steps.

It does not deliver phases 3 and 4. Phase 3's plan takes from this one: the per-host proof's shape; `mon.md#mon-dark`, which it widens into the node-dark procedure; `grafana-compare.py` and the day its clock starts; the check `zcrypto-mon` and the ops watchdog's probe it re-points; the seven direct-shipped rules by name; and the `since` cells every recreate moved.

## Slots the rollout fills

- `[[ROLLOUT: the box's closing date, 2026-11-01 or a week later …]]` (Global Constraints; Task 7; R5) — the box's own rule, read from the owner's word at its close.
- `[[ROLLOUT: R1 to R6, each host's `count by (job)` on the node after its converge …]]` (the per-host proof) — each converge's post-read, into the two records pull requests.
- `[[ROLLOUT: R3's W1 reading — a bare `systemctl restart prometheus`, and one of `loki`, under a running Grafana page, or not]]` (R3) — W1's two bare legs; Prometheus's decides the blacklist's follow-on pull request.
- `[[ROLLOUT: R3's W2 reading — the log lines a 30-minute outage lost]]` (Task 3's `mon-dark`) — W2's measured clause.
- `[[ROLLOUT: R3's W3 reading — the time from the rebuild to the first evaluated rule]]` (Task 3's `mon-dark`) — W3's measured clause.
- `[[ROLLOUT: R4's day read of `zcrypto-valkey1`'s Alloy headroom …]]` (R4) — the day between the first and second cache node.
- `[[ROLLOUT: R6's head-series reading with every host shipping …]]` (R6) — the node's head after the primary ships.
- `[[ROLLOUT: R8's two readings — equal, or off by the boundary sample]]` (R8) — the spec amendment.
- `[[ROLLOUT: the first day whose 00:00 UTC is at least R6's primary converge time plus 50 h — the comparison's first day]]` (R9) — the comparison's clock and `COMPARISON_FROM`.
