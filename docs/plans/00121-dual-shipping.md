# SKELETON, drafted 2026-10-03 — the observability node, phase 2: every fleet host dual-ships to `zcrypto-mon` and Grafana Cloud — implementation plan

> This is a skeleton, not the plan: its tasks are named and scoped, its fenced code is written only where the spec and the existing configs already determine it, and every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end. It becomes `docs/plans/00121-dual-shipping.md` once phase 1's rollout (R0–R10 of `docs/plans/00121-mon-node.md`) has been read and the workstation proof of P0 below has run; `zcrypto-plan-review` reads it then, not now.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every fleet host's Alloy ships its metrics, unfiltered, to the node beside its filtered push to Grafana Cloud, and every host that ships logs ships them to the node's Loki beside Cloud's; the node's rules then read real data for every host, its self-check pings a healthchecks.io check of its own, and `infra/scripts/grafana-compare.py` can run every rule's query on both stacks. Grafana Cloud's rules, receivers, keep-lists and vault values are untouched, the box's order is kept, and the four telemetry drills the node owes are run and logged. This is phase 2 of the spec's four: nothing pages the main channel from the node yet.

**Architecture:** Eight build tasks on the fleet's existing shapes, grouped into five pull requests by the box's order, then an attended runsheet of eight converges, one per fleet host, beside the node's own for its self-check URL. The five Alloy configs each gain a second `endpoint` in `prometheus.remote_write "grafana"` and, where the host ships logs, a `loki.write "mon"` added to the parse stage's `forward_to`, both reading `MON_*` names rendered from new vault and group values; the Cloud blocks are not touched. Each role lands its `MON_*` names and the config that reads them in one tree state: on the three container roles with a reload handler (ops, cache, capture) one converge with the host's running Alloy digest renders the secrets file and copies the config, the handler's reload reads the config with the names still unset — harmless, P0's proof — and `docker compose up -d` in the Alloy project then recreates the container with the names, replaying the second endpoint's queue; the bridgehead and the NAS take their one state, since their converge restarts Alloy after both files. A comparison script reads both stacks through the datasource proxies the uids already name. Four drill procedures join `infra/runbooks/drills-telemetry.md`, the healthchecks.io check map gains the node's own check, and the push skill takes its two-stack wording.

**Tech Stack:** Grafana Alloy v1.19.2 (the fleet's pinned container, `grafana/alloy@sha256:b8ec653c4423…`) and the node's apt Alloy 1.20, Ansible (ansible-core 2.21, the `access`, `ops`, `cache`, `capture`, `nas` and `mon` roles), Docker Compose on the container hosts, Prometheus 2.53.3 and Loki 3.7.8 on the node, `infra/scripts/grafana_auth.py`'s stack table, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00121-self-hosted-observability-design.md`, phase 2: D12 to D15, D19 to D21 as they bear on this phase, the "Phase 2, dual-shipping" line of "What changes in the repo, by phase", the "Phase 2" line of "Proofs each phase owes", the measured basis, and the open questions that name this plan (D14's workstation proof; the bridgehead's `prometheus.exporter.self`; the Cloud push URL and Loki hostname as label values on the node). Phase 1 is `docs/plans/00121-mon-node.md`, whose Produces lines name everything this plan consumes; phases 3 and 4 each take a plan of their own under the same serial.

## Global Constraints

- The node's leg ships unfiltered and the Cloud leg keeps its drop and keep pair untouched: the new `endpoint` carries no `write_relabel_config`, the existing one keeps both of its blocks byte for byte, and no keep-list, REQUIRED list or keep-list test changes in this phase (spec D12; the invariant).
- Dual-shipping is a second `endpoint` block and a second `loki.write` component under new names only: the new blocks read `MON_PROM_URL`, `MON_PROM_USERNAME`, `MON_PROM_PASSWORD`, `MON_LOKI_URL`, `MON_LOKI_USERNAME`, `MON_LOKI_PASSWORD` and nothing else; `GRAFANA_*` names, `grafana_prom_url`, `grafana_loki_url` and every other existing vault value are never repointed or renamed; logs take `loki.write "mon"` in the parse stage's `forward_to`, never a second endpoint inside `loki.write "grafana"`; the bridgehead ships no logs and gains none (spec D13; the invariant).
- A name reaches an Alloy process with the config that reads it, one tree state per container role: on ops, the cache nodes and the capture pair one converge with the host's running Alloy digest renders the role's secrets file and copies its config, the handler's reload reads the config with the `MON_*` names still unset — harmless, P0's verdict of 2026-10-03: the reload answers 200, the first endpoint keeps shipping, the second retries its own queue at `level=warn` — and the container is then recreated with `docker compose up -d` in the Alloy project, the bump-alloy skill's step, on each host of the role, which starts the process with the names and replays the second endpoint's queue; the bridgehead and the NAS take their one state, their converge restarting Alloy after both files land. Each role's names and config land in the same commit, so `test_the_cache_secrets_template_renders_every_name_the_config_reads` holds `read == rendered` throughout and is not widened (spec D14).
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
- No container's environment is printed on any host, by `docker inspect … .Config.Env`, `docker exec … env` or `docker compose config`: a recreate is proven by `.State.StartedAt` moving and a name's arrival by the series that reach the node after the config lands, never by reading the environment.
- No executor step reaches a host, a venue, Grafana Cloud, the node's Grafana, Slack, healthchecks.io, the Linode Cloud Manager or DNS; every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No operator-read surface (the runbook pages, the drill procedures, the rule file's text, the healthchecks.io description, the Slack template) carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; where a provenance token is wanted it goes in an adjacent code comment.
- A comment or docstring stays only where a reader would do something differently without it; an event goes to the commit message. It carries a count of another file's contents only where a test holds that count.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean. The branch is unpushed while the tasks run, so the amend rewrites nothing a reader holds.
- Every commit is green over the changed files' consumers, the tests each task's consumer step names; never the full suite locally, which is CI's on every push.
- `uv run pre-commit run -a` runs clean before every commit; a run that rewrites files is re-run until clean and the rewrites staged.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. A universal word in a new runbook bullet (every, never, always, only, any, cannot) carries its `(set: …; count: …)` or `(no count command: …)` clause, or the bullet is worded without it.
- Task 4 alone edits files under `.claude/`, the three skills `zcrypto-grafana-push`, `zcrypto-bump-alloy` and `zcrypto-daily-ops`, in a `claude` commit that carries no other file; no task edits `CLAUDE.md`.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `infra/ansible/group_vars/observed/vars.yml` (new): the node's two ingest URLs and the `fleet` user's name, plain, beside the vaulted passwords phase 1 appended to `group_vars/observed/vault.yml` (Task 1).
- `infra/ansible/roles/access/templates/alloy-env.j2`: the three `MON_PROM_*` names (Task 1); `roles/ops/templates/alloy-secrets.env.j2` (Task 5), `roles/cache/templates/alloy-secrets.env.j2` (Task 6), `roles/nas/templates/alloy-secrets.env.j2` (Task 7), `roles/capture/templates/alloy-secrets.env.j2` (Task 8): the six `MON_*` names, each in the commit of the config that reads them.
- `infra/ansible/roles/access/files/config.alloy`: the second endpoint and `prometheus.exporter.self` (Task 1); `roles/ops/files/config.alloy`: the second endpoint, `loki.write "mon"`, the `netdev` exclusion (Task 5); `roles/cache/files/config.alloy`: the second endpoint and `loki.write "mon"` (Task 6); `infra/nas/config.alloy` and `roles/capture/files/config.alloy`: all three (Tasks 7, 8).
- `infra/ansible/host_vars/zcrypto-mon/vars.yml` and `vault.yml`: the self-check's healthchecks.io URL, wired from a vault value the owner appends in the Rollout's P1 (Task 5).
- `infra/scripts/grafana-compare.py` (new) and `tests/test_grafana_compare.py` (new) (Task 2).
- `infra/runbooks/drills-telemetry.md`: four drill procedures and the standing rule's subject list; `infra/runbooks/mon.md`: a `mon-dark` procedure, and the shipper-loss section's sentence on the bridgehead (Tasks 1, 3); `infra/runbooks/observability.md`: the dead-man map's row and its count (Task 5); `infra/nas/README.md`: the secrets file's names (Task 7).
- `tests/fixtures/healthchecks_descriptions.json`: the node's check, re-fetched through the read-only key (Task 5).
- `.claude/skills/zcrypto-grafana-push/SKILL.md`: the two-stack wording of every push in the dual period; `.claude/skills/zcrypto-bump-alloy/SKILL.md`: Step 3's shipping-health read sees two destinations per host (Task 4).
- `tests/test_infra_alloy_series.py`: the `GRAFANA_*` literal case over each template, and the new guards over the second endpoint, the second `loki.write`, the `netdev` exclusion and the bridgehead's self scrape (Tasks 1, 5, 6, 7, 8); `tests/test_infra_mon_role.py`: the group vars held to the role's hostname and the Caddyfile's two paths (Task 1); `tests/test_ops_daily.py`: the fixture's count (Task 5); `tests/test_drill_log.py`: unchanged, it reads the entries the Rollout appends.
- `docs/reference/deploy-log.jsonl`, `drill-log.md`, `fleet-pins.md`, `fleet.md`, `docs/open-topics/T0217-self-hosted-observability-stack.md`, the spec's measured basis: the Rollout's records pull requests, not a task's.

## Review Focus

Five classes, named here and written as tests inside the tasks they belong to; the plan proper lists each class's test names as phase 1's does.

- A `MON_*` name read by a config before the process holds it: the reload reads empty strings and the second endpoint retries an empty URL until the recreate (P0), so each role's names and config land in one commit, every converge of a container role is followed by the recreate, proven by `.State.StartedAt` moving on every host of the role, and the cache template test holds `read == rendered` across the cache commit, widened by nothing (Tasks 1, 5, 6, 7, 8).
- A relabel block on the node's endpoint, or the Cloud endpoint's pair moved or loosened: the keep and drop extractors in `tests/test_infra_alloy_series.py` assert exactly one block of each per file, so the guard must read the two endpoints apart, hold the `mon` endpoint free of `write_relabel_config` and the `grafana` endpoint to its existing pair, and hold `loki.write "grafana"` to one endpoint (Tasks 1, 5, 6, 7, 8).
- An existing name repointed: a diff that touches a `GRAFANA_*` line, a `grafana_*` vault reference or the Cloud `endpoint` block is a finding, since `logship-secrets.env` re-renders on every capture-role converge and the engine reads it at its next start; the guard holds the six `GRAFANA_*` lines of each template byte-identical to today's and the new blocks to `MON_*` names alone (Tasks 1, 5, 6, 7, 8).
- The comparison admitting a false match: an empty result equal only to an empty result, values within a relative 1e-6 and label sets whole, the three exclusions by name and nothing else excluded, the same instant sent to both stacks, and a missing stack or a refused query a failure of the run and never a match (Task 2).
- A converge or an induction outside its bounds: a venue-facing host inside a Kraken window, the primary converged un-tagged or with a capture digest that is not the running one, a cache node converged under its group or with the image digest, a drill whose subject is the primary, or the `prometheus` blacklist decided by anything but the store-restart drill's reading (Tasks 3, 5, 6, 8 and the Rollout).

---

### Task 1: The bridgehead ships to both and its Alloy scrapes itself — the node's ingest names reach the group vars and the bridgehead's environment, one tree state

**Files:**
- Create: `infra/ansible/group_vars/observed/vars.yml`
- Modify: `infra/ansible/roles/access/templates/alloy-env.j2` (three `MON_PROM_*` lines appended, the bridgehead shipping no logs; the header's "same six names" sentence re-trued)
- Modify: `infra/ansible/roles/access/files/config.alloy` (`prometheus.exporter.self "alloy" {}`, the host scrape's targets concatenated, the second `endpoint`; the header's "no `prometheus.exporter.self` component on this host" clause re-trued)
- Modify: `infra/runbooks/mon.md` (the `zcrypto-mon-shipper-loss` section's sentence that the bridgehead publishes no counter)
- Test: `tests/test_infra_alloy_series.py` (new: the two endpoints read apart; the self targets concatenated on every config; the six `GRAFANA_*` lines of a template held by literal, parametrised over the access template)
- Test: `tests/test_infra_mon_role.py` (the group vars held to `mon_hostname` and to the Caddyfile's two ingest paths)

**Interfaces:**
- Consumes: `mon_ingest_fleet_password` in `infra/ansible/group_vars/observed/vault.yml` (phase 1's P2); the `mon` role's defaults `mon_hostname`, `mon_ingest_fleet_user`; the Caddyfile's two authenticated paths `/api/v1/write` and `/loki/api/v1/push`; the access role's `restart alloy` handler, which both the env and the config notify, so one converge lands both and restarts; `ACCESS_REQUIRED` and the keep regex, unchanged; the roles' `no_log` render tasks, which this task does not touch.
- Produces, for Tasks 5 to 8 and the Rollout to use by these exact names: `mon_ingest_prom_url`, `mon_ingest_loki_url` and `mon_ingest_fleet_user` in `group_vars/observed/vars.yml`; the environment names `MON_PROM_URL`, `MON_PROM_USERNAME`, `MON_PROM_PASSWORD`, `MON_LOKI_URL`, `MON_LOKI_USERNAME`, `MON_LOKI_PASSWORD`; the helper that reads `prometheus.remote_write "grafana"`'s endpoint blocks apart, the second-endpoint block's exact text, and the guard shape over it; the `GRAFANA_*` literal case each later task parametrises over its role's template; on Cloud, `up{host="zaccess", job="integrations/self"}`, which the keep regex admits.

**What this task decides, where the spec leaves it open:**
- The two URLs are plain group vars, not vault values, since they are the node's public name and two paths the Caddyfile already publishes; `mon_ingest_fleet_user` is declared in the group vars with the role default's value, since a role's defaults are not visible to another role's template, and `tests/test_infra_mon_role.py` holds the three equal to the `mon` role's `mon_hostname`, its `mon_ingest_fleet_user` and the Caddyfile's two paths.
- The bridgehead's env file gains the three `MON_PROM_*` names and not the Loki three, in the commit of the config that reads them: the template renders every name a config may read on that host, and the access config reads no Loki name.
- The `GRAFANA_*` literal case holds the six `GRAFANA_*` lines of a template byte-identical to their text on `develop` at this plan's base, parametrised over the access template here and over each role's template as its task lands, so a repointed Cloud name is a test failure before it is a converge.
- The open question is answered yes: the bridgehead gains `prometheus.exporter.self "alloy" {}` with its targets concatenated into `prometheus.scrape "host"`, as the other four configs do, so `zcrypto-mon-shipper-loss` reads it from the day it ships. The Cloud leg gains one series, `up{job="integrations/self"}`, since the keep regex admits `up` and the drop regex already drops `go_.*|alloy_.*`; `zcrypto-alloy-dark-zaccess` counts `up{host="zaccess"}` and reads 2 where it read 1, still above its bar; `zcrypto-fleet-daemon-restarted`'s host matcher does not name `zaccess`, so a bridgehead restart pages nothing new.
- The second endpoint carries `name = "mon"`, so Alloy's own counters label the node's destination `remote_name="mon"` where the Cloud endpoint keeps its hash; P0 read the attribute accepted by v1.19.2, and the dry-start in Step 2 reads it again on the edited file.
- The new guard reads the `endpoint` blocks of `prometheus.remote_write "grafana"` apart: exactly two; the first carries `sys.env("GRAFANA_PROM_URL")` and both relabel blocks, the second carries `sys.env("MON_PROM_URL")`, the two `MON_PROM_*` credentials, `name = "mon"` and no `write_relabel_config`, and no `GRAFANA_` token at all. The existing extractors, which assert exactly one keep and one drop block per file, hold as they are, which is the measured basis's finding.

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
    assert 'sys.env("GRAFANA_PROM_URL")' in cloud and cloud.count("write_relabel_config") == 2
    assert 'sys.env("MON_PROM_URL")' in mon and "write_relabel_config" not in mon and "GRAFANA_" not in mon
```

- [ ] **Step 1: Write the failing tests** — the endpoint guard, the self targets, the group-vars case, the `GRAFANA_*` literal case.
- [ ] **Step 2: Dry-start the edited config against the fleet's pinned Alloy on the workstation**, with dummy values for every `sys.env` name, the bump-alloy skill's Step 1 form; Expected: the config loads, no `level=error` line, and the `name` attribute accepted.
- [ ] **Step 3: Run the tests and read the failure**

```bash
uv run pytest tests/test_infra_alloy_series.py tests/test_infra_mon_role.py -q -p no:cacheprovider
```

Expected: the endpoint guard fails on one block; the group-vars case fails on the missing file.

- [ ] **Step 4: The group vars, the template, the config and the runbook sentence**
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

<what: the plain URLs and user in group_vars/observed, the three MON_PROM_* names beside the config that reads them — one tree state, the reload with unset names proven harmless on 2026-10-03; the self scrape; the GRAFANA_* literal guard>

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean** — `git status --porcelain`; Expected: empty.
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — `infra/scripts/mutate-probe.sh` with a control and a mutation per case (a `write_relabel_config` copied into the `mon` endpoint; the Cloud endpoint's keep block removed; the self targets dropped from the concat; a `GRAFANA_` line edited; the URL's path changed); each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`; the `PROBE_VERDICT` line replaced, as phase 1's tasks do.

---

### Task 2: `grafana-compare.py` runs every rule's query on both stacks at the same instants

**Files:**
- Create: `infra/scripts/grafana-compare.py`
- Create: `tests/test_grafana_compare.py`
- Modify: `infra/scripts/ops_daily.py` (the `## Comparison` section: the preceding day's `grafana-compare.py` last line while both stacks are live, absent otherwise) and `tests/test_ops_daily.py` (the section present with both stacks, absent with one)
- Modify: `infra/runbooks/mon.md` (a `mon-compare` procedure, one invocation and how a difference is read)
- Modify: `infra/scripts/grafana-push.sh` (the orphan report: a live rule whose group `GRAFANA_SKIP_RULE_GROUPS` skipped is in `alerts.yaml` and is reported as such, never as `ORPHAN (live but not in alerts.yaml)` — the keep list is built from the rules file before the skip, so a skipped group's rules are neither pushed nor called orphans; phase 1's rollout left it, and its test in `tests/test_grafana_push_sh.py` drives a push with the node's group skipped against a live list that carries it)

**Interfaces:**
- Consumes: `grafana_auth.STACKS`, `grafana_auth.stack(name)`, `grafana_auth.vault_var(name, vault_file)`; `grafana-query.py`'s endpoint shape, `<url>/api/datasources/proxy/uid/<uid>/api/v1/query` for Prometheus and `…/loki/api/v1/query` for Loki, the uids `grafanacloud-prom` and `grafanacloud-logs` being the same on both stacks (spec D8); `infra/grafana/alerts.yaml`'s rules, each `data[]` node's `model.expr` and `datasourceUid`, and its `ruleGroup`.
- Produces, for phase 3's gate and the Rollout: `uv run python infra/scripts/grafana-compare.py [--day YYYY-MM-DD]`, exit 0 with `compare: <nodes> nodes × 24 instants, 0 differences` on its last line, exit 1 with one line per difference `<rule uid> <refId> <instant> <what differs>`; the constants `EXCLUDED_GROUPS = ("zcrypto-mon",)`, `EXCLUDED_HOSTS = ("zcrypto-mon",)` and `DIRECT_SHIPPED_RULES`, the seven uids D19 names.

**What this task decides, where the spec leaves it open:**
- The 24 instants are the top of each UTC hour of the preceding day, or of `--day`; each query node is sent as an instant query with `time=<epoch>` to both stacks, Loki nodes through `/loki/api/v1/query` with the node's own `expr`, so the two stacks answer the same question at the same instant and the rule's own range selector supplies the window.
- A difference is any of: a label set present on one stack and not the other, a value differing by more than a relative 1e-6, an empty result against a non-empty one; an empty result on both is a match. A stack that cannot be reached, a 4xx or 5xx, or a malformed body ends the run as a failure named per stack, never as a match or a skip.
- Rows whose `host` label is `zcrypto-mon` are dropped from both result sets before the comparison; nodes of rules in `EXCLUDED_GROUPS` and of the seven `DIRECT_SHIPPED_RULES` are not sent. A test holds `DIRECT_SHIPPED_RULES` equal to what the measured basis's listing prints for the tree, so an eighth rule that selects a direct shipper's stream fails the test rather than the comparison.
- The seven daily runs are the daily operations pass's (the owner's word of 2026-10-03): `infra/scripts/ops_daily.py` gains a step that runs `grafana-compare.py` for the preceding day while both stacks are live and prints its last line under a `## Comparison` section, which Task 4's daily-ops skill edit names; each day's journal entry carries that line, and the cutover pull request cites the seven.
- The test stubs `vault_var` and the opener the way `tests/test_grafana_query.py` does, feeding canned result sets: the same, a value off by 1e-5, a missing label set, empty against empty, empty against one row, a stack refusing, the exclusions by name, the instants' alignment.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure**
- [ ] **Step 3: The script** — the stack table read, the rule file walked, the instants built, the queries sent, the comparison, the report.
- [ ] **Step 4: Run the tests** — Expected: no failure, `tests/test_scripts_have_tests.py` included.
- [ ] **Step 5: The consumers**

```bash
uv run pytest tests/test_grafana_compare.py tests/test_grafana_auth.py tests/test_scripts_have_tests.py tests/test_error_paths_are_logged.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider
```

- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(grafana): a comparison of every rule's query on both stacks at the same 24 instants, three exclusions by name`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the tolerance widened; an empty result matched against a row; an exclusion dropped; a refused stack read as a match; the instant sent to one stack only.

---

### Task 3: The four drill procedures and the node-dark procedure

**Files:**
- Modify: `infra/runbooks/drills-telemetry.md` (four sections of seven parts each; the standing rule's subject list gains the node; the bounds derivation names the node's group)
- Modify: `infra/runbooks/mon.md` (a `mon-dark` procedure: what to read and do while the node is down or being rebuilt, and what nothing pages from it yet)
- Test: none new; `tests/test_internal_terms_not_operator_visible.py` and the runbook tests already walk both pages.

**Interfaces:**
- Consumes: the seven-part shape and the entry contract of `docs/reference/drill-log.md`'s preamble; `mon.md`'s anchors `mon-store-restart`, `mon-push`, `mon-token-rotate`, `zcrypto-mon-ingest-dark`, `zcrypto-mon-store-down`, `zcrypto-mon-shipper-loss`; the rule waits `zcrypto-mon-ingest-dark` `for: 5m`, `zcrypto-mon-store-down` `for: 3m`, `zcrypto-alloy-dark-*` `for: 10m` plus the ~5 min staleness term, every group at 60 s; the healthchecks.io check's `timeout 600 + grace 600` of D16; phase 1's R3, R8 and R9 lines, which the rebuild drill re-runs.
- Produces, for the Rollout and the drill log: the anchors `drill-m1` (the store restart), `drill-m2` (the 30-minute power-off), `drill-m3` (the rebuild from nothing), `drill-m4` (the shipper stop on the secondary); the scenario ids `M1` to `M4` for the drill-log headings; `mon.md#mon-dark`, the anchor the node's healthchecks.io check cites.

**What this task decides, where the spec leaves it open:**
- The letter `M` is free on both drill pages at this plan's base; the plan proper re-reads both pages' headings before it is written, since the pages name their letters out loud.
- M1's bounds: a bare `systemctl restart prometheus` with Grafana running is read for error pages in the shadow channel within three minutes and for `health != ok` on the rules endpoint; the ordered restart is `mon.md#mon-store-restart`; the last leg stops Caddy with the stores and Grafana running until the first `zcrypto-alloy-dark-*` page (ops or the bridgehead) reaches the shadow channel, `zcrypto-mon-ingest-dark` owing its page about 10 minutes after the stop (`for: 5m` plus staleness) and the first per-host page about 16 (`for: 10m` plus staleness plus the interval), the order the exposure page's runbook will rest on.
- M2's bounds: the node's own check pages natively at `timeout 600 + grace 600` from its last clean ping, so inside about 20 minutes of the power-off; Cloud's `zcrypto-hcio-watchdog` trails by about 7 minutes and is announced beforehand; the Cloud leg's "no gap" is `count_over_time(up{host="ops", job="integrations/unix"}[2h])` on Cloud across the window reading 120 give or take an edge sample; the node's replay is the same read on the node once the shippers' WAL has drained; the lines lost are `sum(count_over_time({host="ops"}[2h]))` on each stack across the window, the difference the figure.
- M3 is phase 1's R3 (bootstrap, alias, preview, converge), R8 (the push) and R9's first rules read, run again on a rebuilt Linode, with the host key re-read in LISH and the stale `known_hosts` line removed first; the cached token is refused and re-minted by the converge (D7), which the drill reads as `changed` on the token task; measured from the rebuild's start to the first `health=ok` rule.
- M4 is drill K's induction on the secondary, `sudo docker stop grafana-alloy` on `zcrypto-red`, read on the node: `up{host="zcrypto-red"}` absent, never 0, and `zcrypto-alloy-dark-capture-secondary` in the shadow channel on Cloud's timing; the `since` cell of `fleet-pins.md`'s secondary Alloy row is re-trued with the restore.
- `mon-dark` is the phase-2 shape of the node-dark procedure phase 3 widens from `observability.md`'s `grafana-cloud-dark`: it says that while the node pages the shadow channel alone its death reaches the owner through its healthchecks.io check only, what to read on the host, that a store outage drops the alert history of its minutes, and the two figures the drills measure: [[ROLLOUT: R3's M2 reading — the log lines a 30-minute outage lost]] and [[ROLLOUT: R3's M3 reading — the time from the rebuild to the first evaluated rule]], both written as prose with no number until read.

- [ ] **Step 1: The four sections and the standing-rule edit**, each section's seven parts, every bound derived from a quoted `for` or a quoted check setting.
- [ ] **Step 2: The `mon-dark` section**
- [ ] **Step 3: The consumers**

```bash
uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbooks.py tests/test_drill_log.py -q -p no:cacheprovider
```

- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `docs(runbooks): the node's four telemetry drills and its dark procedure`, with the trailer; no guard changes, so no probe.
- [ ] **Step 6: The tree is clean**

---

### Task 4: Two skills take the dual period — the push skill's two-stack wording and the Alloy bump's two destinations

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md` (every push in the dual period goes to both stacks from one checkout; the node's invocation per `mon.md#mon-push`; the two sentences phase 1 added stay)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (the `## Comparison` section Task 2's step prints, and a difference as a cutover finding)
- Modify: `.claude/skills/zcrypto-bump-alloy/SKILL.md` (Step 3's shipping-health `grep` now prints a `failed_total` and a `dropped_entries_total` per destination; both must read 0, and the node's own `zcrypto-mon-shipper-loss` is the fleet-wide reading)

**Interfaces:**
- Consumes: Task 5's second endpoint on ops, which is the first host whose bump read shows two destinations; `GRAFANA_SKIP_RULE_GROUPS` and the stack table.
- Produces: a push skill a push to either stack passes; a bump skill whose Step 3 reads both destinations.

**What this task decides, where the spec leaves it open:**
- The daily-ops skill names the `## Comparison` section the pass prints while both stacks are live (the owner's word of 2026-10-03, Task 2's step) and what a difference there means: a finding for the cutover pull request, never a remediation; its telemetry clause already names the node's Alloy unit (phase 1's Task 8).

- [ ] **Step 1: The two edits**
- [ ] **Step 2: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_skills.py -q -p no:cacheprovider` (the skill tests the tree holds at the plan's base).
- [ ] **Step 3: The commit gate**
- [ ] **Step 4: Commit** — `claude(skills): a push in the dual period goes to both stacks, and an Alloy bump reads both destinations`, with the trailer; a `claude` commit carrying no other file.
- [ ] **Step 5: The tree is clean**

Then the first pull request opens through the `open-pr` skill over Tasks 1 to 4, a different agent reads the branch, and `merge-pr` merges it; the Rollout's R1 follows from merged `develop`.

---

### Task 5: ops ships to both — its six names and its config in one tree state, the node's own dead-man wired, the check map

**Files:**
- Modify: `infra/ansible/roles/ops/templates/alloy-secrets.env.j2` (six `MON_*` lines appended; the header's "same six names" sentence re-trued)
- Modify: `infra/ansible/roles/ops/files/config.alloy` (the second `endpoint` in `prometheus.remote_write "grafana"`; `loki.write "mon"`; `loki.process "parse"`'s `forward_to`; `netdev { device_exclude = "^(veth|br-)" }` in `prometheus.exporter.unix "host"`)
- Modify: `infra/ansible/host_vars/zcrypto-mon/vars.yml` (`mon_selfcheck_healthcheck_url: "{{ selfcheck_healthcheck_url }}"`)
- Modify: `infra/ansible/host_vars/zcrypto-mon/vault.yml` (the owner's P1 appends `selfcheck_healthcheck_url`; committed by this task's commit)
- Modify: `tests/fixtures/healthchecks_descriptions.json` (the eleventh check, fetched through the read-only key)
- Modify: `infra/runbooks/observability.md` (the dead-man map's row and its count; "Ten checks exist" becomes eleven)
- Modify: `infra/ansible/roles/mon/files/zcrypto-mon-selfcheck.py` (`rules_fresh`'s refusal names the series it did not find, `grafana_alerting_ticker_last_consumed_tick_timestamp_seconds` or `grafana_alerting_schedule_alert_rules`, where it says "no scheduler tick" — phase 1's rollout left it; its test in `tests/test_mon_selfcheck.py` reads the name in the reason)
- Test: `tests/test_infra_alloy_series.py` (the endpoint guard and the `GRAFANA_*` literal case parametrised over ops; the `loki.write "mon"` guard; the `netdev` guard)
- Test: `tests/test_ops_daily.py` (`len(checks) == 11`)

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
- [ ] **Step 2: Dry-start the edited config against the pinned Alloy** — Expected: loads clean.
- [ ] **Step 3: Run the tests and read the failure**
- [ ] **Step 4: The template, the config, the two host-vars files, the fixture, the map row**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file reading a `config.alloy` or `alloy-secrets.env`, `tests/test_ops_daily.py`, `tests/test_infra_mon_role.py`, and the vault-shape tests over `host_vars/zcrypto-mon`.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): the ops Alloy ships unfiltered to the node beside Grafana Cloud, and the node's self-check pings its own dead-man`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; the second receiver dropped from the `forward_to`; the `netdev` exclusion removed.

Then the second pull request opens over Task 5; the Rollout's R2 and R3 follow.

---

### Task 6: The cache nodes ship to both — the six names and the config in one tree state, the template test's equality kept

**Files:**
- Modify: `infra/ansible/roles/cache/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5 appended)
- Modify: `infra/ansible/roles/cache/files/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; no `netdev` exclusion, per D12)
- Test: `tests/test_infra_alloy_series.py` (`test_the_cache_secrets_template_renders_every_name_the_config_reads` unchanged, holding `read == rendered` over the commit; the endpoint, `loki.write`, `netdev`-absent and `GRAFANA_*` literal guards parametrised over the cache file and template)

**Interfaces:**
- Consumes: Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5; the cache role's `reload alloy` handler and its digest-gated block, which renders the secrets file and copies the config on a converge carrying `cache_alloy_digest`.
- Produces, for the Rollout: on the node, `up{host=~"zcrypto-valkey[123]"}` under `integrations/unix`, `integrations/self`, `valkey` and `sentinel`, the redis families unfiltered, and the three nodes' journal streams.

**What this task decides, where the spec leaves it open:**
- The template's six lines and the config's six reads land in this one commit: the equality test fails on either half alone and holds over the pair, so it is neither widened nor restored.
- The cache config's `host` is `constants.hostname`, so the one file labels all three nodes on the node's leg as it does on Cloud's; nothing per node is rendered.
- The "how many distinct commands each Valkey node has served" reading the spec leaves to the first cache node's read is R4's `count by (host) (redis_commands_total{host="zcrypto-valkey1"})` on the node, recorded, not gated.

- [ ] **Step 1: Write the failing tests** (the guards; the equality test, unchanged, fails until both the template and the config carry the six names).
- [ ] **Step 2: Dry-start the edited config against the pinned Alloy**
- [ ] **Step 3: Run the tests and read the failure**
- [ ] **Step 4: The template and the config**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file reading a `config.alloy` or `alloy-secrets.env`.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): a cache node's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `netdev` exclusion added to the cache config.

Then the third pull request opens over Task 6, after R3's drills; the Rollout's R4 follows. The inside-box records pull request (R-records-1) closes the box's work.

---

### Task 7: After the box — the NAS ships to both in one state

**Files:**
- Modify: `infra/nas/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; the `netdev` exclusion)
- Modify: `infra/ansible/roles/nas/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5)
- Modify: `infra/nas/README.md` (the secrets file's names)
- Test: `tests/test_infra_alloy_series.py` (the endpoint, `loki.write`, `netdev` and `GRAFANA_*` literal guards parametrised over the NAS file and template)

**Interfaces:**
- Consumes: the NAS role's apply, `-e nas_apply_compose=true`, whose `compose up -d` recreates on the env file's change and whose `compose restart alloy` re-reads the config, so one converge lands both files and restarts Alloy after them (D14), and which also restarts `archive-pull`; Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5.
- Produces, for the Rollout: on the node, `up{host="nas"}` under its jobs and the NAS's streams.

**What this task decides, where the spec leaves it open:**
- The NAS merges in a pull request of its own after the box, its file serving one host converged in one pass; the capture pair's is the next, since its file arms the drift assert on two hosts converged an hour apart.
- The NAS's recreate is proven by the Alloy container's `.State.StartedAt` moving and its `RestartCount` unchanged, read with `/usr/local/bin/docker`; the NAS's `-compat` build question does not arise, since the Alloy image is upstream's with no variant (`fleet-pins.md`'s row).

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Dry-start the edited NAS config against the pinned Alloy**
- [ ] **Step 3: Run the tests and read the failure**
- [ ] **Step 4: The config, the template, the README**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file reading a `config.alloy`, `alloy-secrets.env` or the NAS README.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): the NAS's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend**

Then the fourth pull request opens over Task 7, not before [[ROLLOUT: the box's closing date]]; the Rollout's R5 follows.

---

### Task 8: The capture pair ships to both — the six names and the config in one tree state, and every secrets template renders what its config reads

**Files:**
- Modify: `infra/ansible/roles/capture/templates/alloy-secrets.env.j2` (the six `MON_*` lines of Task 5 appended; the header's "same six names" sentence re-trued)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the second `endpoint`; `loki.write "mon"`; the `forward_to`; the `netdev` exclusion)
- Test: `tests/test_infra_alloy_series.py` (the guards and the `GRAFANA_*` literal case parametrised over the capture file and template; a new case over the five template-config pairs)

**Interfaces:**
- Consumes: Task 1's group vars and six names, Task 5's template lines, the block texts of Tasks 1 and 5; the capture role's `reload alloy` handler and its digest-gated block, which renders the secrets file and copies the config on a converge carrying `capture_alloy_digest`.
- Produces, for the Rollout and phase 3: on the node, every capture-host family unfiltered, `capture_app`, `engine_app`, `cache_proxy`, `integrations/unix` and `integrations/self` under `host="zcrypto"` and the first four under `host="zcrypto-red"`; the journal streams of both; every template-config pair holding `read ⊆ rendered`.

**What this task decides, where the spec leaves it open:**
- With every config now reading its names, a new case holds each of the five pairs (ops, cache, capture, access, NAS) to `read ⊆ rendered`; the cache pair alone keeps equality, since its template renders no name its config does not read, where the bridgehead's template renders six `GRAFANA_*` names and its config reads three.
- The second endpoint's queue is its own, so the primary's capture series keep reaching Cloud whatever the node does; nothing in this task touches `logship-secrets.env.j2` or the capture compose template (D13's reason).

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Dry-start the edited config against the pinned Alloy**
- [ ] **Step 3: Run the tests and read the failure**
- [ ] **Step 4: The template and the config**
- [ ] **Step 5: Run the tests**
- [ ] **Step 6: The consumers** — every test file reading a `config.alloy` or `alloy-secrets.env`, `tests/test_engine_metrics.py` and `tests/test_clock_offset.py` among them.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): a capture host's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend**

Then the fifth pull request opens over Task 8; the Rollout's R6 to R9 and the second records pull request follow.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches a fleet host, the node, Grafana Cloud, Slack, healthchecks.io or the Linode Cloud Manager, or writes a secret. P0 ran on the workstation on 2026-10-03, before this skeleton becomes the plan; P1 is Task 5's operator step. Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its line to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`. `W$` is the workstation at the repository root, `H$` a shell on the named host (`ssh hp` for ops, `ssh db1` to `db3`, `ssh red`, `ssh zcrypto`, `ssh mon`, the NAS by its alias). The running Alloy digest a converge is handed is read off the host immediately before, `docker inspect grafana-alloy --format '{{.Config.Image}}'`, the `sha256:…` after the `@`, and matched against `docs/reference/fleet-pins.md` (`b8ec653c4423`, v1.19.2 on all seven); the running capture digest is read the same way from `zcrypto-capture`, `.Config.Image`, never `.Image`. `KRAKEN` below is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, taken at planning and again immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. The node's own reads are `grafana-query.py --stack mon`; Cloud's are the same tool unnamed.

**The per-host proof, used by every converge below.** Before the converge, `count by (job) ({host="<host>"})` on both stacks and `count({host="<host>"})` on Cloud, kept in `$CAP`; after it, the same three reads: Cloud's counts unchanged (the bridgehead's `up` under `integrations/self` the one admitted addition, R1), the node's per-job counts present for every job the host's config scrapes and each above Cloud's for that job, the `zcrypto-mon-shipper-loss` row for the host reading 0 after an hour, and the Alloy on the host reading `prometheus_remote_storage_samples_failed_total` 0 for both `url` values on `127.0.0.1:12345/metrics`. The host's reading goes into the records: [[ROLLOUT: R1 to R6, each host's `count by (job)` on the node after its converge, against Cloud's count for it — bridgehead 37, ops 369, cache 83/82/82, NAS 165, `zcrypto-red` 141, `zcrypto` 452 on 2026-10-01]].

**P0. The workstation proof that decides the tree states** (spec D14's open question; before this plan is final). Alloy v1.19.2, the fleet's pin, from its release binary on the workstation, with the ops config as it stands and a secrets file carrying the six `GRAFANA_*` names against a scratch Prometheus; then a `POST /-/reload` with the Task 5 config, its `MON_*` names unset in the process. Read: whether the first endpoint keeps shipping across and after the reload, what the reload returns against the handler's accepted `[200, -1]`, and what the process logs. The verdict, taken 2026-10-03 on the workstation: Alloy v1.19.2's release binary, the ops config with its three container paths pointed at the workstation's `/proc`, `/sys`, `/` and a scratch textfile directory, the six `GRAFANA_*` names pointed at a scratch Prometheus 2.53.3 with its receiver on and a scratch Loki 3.7.8, shipped `up{host="ops"}` under four jobs; the `POST /-/reload` with the Task 5 config and no `MON_*` name in the process answered `200 config reloaded`, the graph re-evaluated with no error, and the first endpoint kept shipping across and after it (`prometheus_remote_storage_samples_total` 576 before, 872 eighty seconds after, 0 failed, 0 pending); the second endpoint started under `remote_name="mon"` with `url=""`, so `name = "mon"` is accepted by the pin, and it retries its own queue with `Post "": unsupported protocol scheme ""` at `level=warn`, 1,631 samples pending at eighty seconds and nothing of the first endpoint's touched — the backlog a recreate with the names then replays from the WAL. The reload is harmless and 200: every container role takes one state, converge then recreate, and the tasks above are written to it.

**Precondition from phase 1.** Phase 1's R9 read the node-alone head series at 9,740 after the first push (8,033 before it), under the 15,000 line, so this plan proceeds; the bar of 40,000 and the cap of 16GB were sized for 9,700 to 10,300, and the reading sits inside that band. The series the first hosts add are read against the bar at every step below, `prometheus_tsdb_head_series{host="zcrypto-mon"}` after each converge.

**R0. The operands, read once.** `git switch develop && git pull --ff-only && git status --porcelain` empty; `CAP="$PWD/.tmp/mon-dual"`; `infra/scripts/count-list.sh converges-inside-a-kraken-window | tee "$CAP/kraken-window-count"`; `KRAKEN` at planning; the seven running Alloy digests read off the hosts and matched to `fleet-pins.md`.

**R1. The bridgehead** (Task 1; after the first pull request merges). No Kraken read owed. `W$ infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` — the preview names `/etc/default/alloy` and `/etc/alloy/config.alloy` changed and nothing else; the real pass restarts Alloy through the role's handler. Then the per-host proof; `up{host="zaccess", job="integrations/self"}` present on both stacks.

**R2. ops** (Task 5; after the second pull request merges). `KRAKEN` immediately before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<running>` — the preview names `alloy-secrets.env` changed (`no_log`, so the changed-files report is the signal) and `conf/config.alloy` changed; the handler's reload reads 200, and the outgoing process retries the `mon` endpoint's empty URL at `level=warn`, P0's shape, touching nothing of the Cloud endpoint. Then `H$ cd /etc/zcrypto-ops/alloy && sudo docker compose up -d`, which recreates on the env file's change; `docker inspect grafana-alloy --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'` reads the same digest, 0 restarts and a `started` after the converge. A `started` that did not move is a stop: the env file's change did not reach the service hash, and the recreate is `sudo docker compose up -d --force-recreate alloy`, which the plan proper then makes the step. `Ops · ERROR logs` fires on the outgoing container's two `remotecfg` lines, the bump skill's known shape. Then `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon`, which renders the self-check's URL; `ssh mon 'sudo journalctl -u zcrypto-mon-selfcheck --no-pager -o cat | grep -E "^selfcheck:" | tail -1'` reads `rules=ok (…) fleet=ok (…) loki=ok (…) -> pinged`, and healthchecks.io shows the check's first ping. The per-host proof for ops, with `count by (container) ({host="ops"})` on both stacks for the streams; `zcrypto-mon-ingest-dark` reads `inactive ok` on the node's rules endpoint; the node's head series read against the bar.

**R3. The three node drills** (Task 3; while only the bridgehead and ops ship). Each is its section's seven parts, one at a time, the revert verified by value before the next; each run gets its `docs/reference/drill-log.md` entry in the records pull request. M1 first, its bare legs the one place a store is restarted under a running Grafana: the reading [[ROLLOUT: R3's M1 reading — a bare `systemctl restart prometheus` under a running Grafana pages, or not]] decides whether `prometheus$` leaves `host_vars/zcrypto-mon/vars.yml`'s blacklist in a pull request of its own, with D17's reasoning line re-trued either way. M2 second, announced in the main channel beforehand since Cloud's `zcrypto-hcio-watchdog` pages on the node's check going down; its two readings fill `mon-dark`'s slots. M3 third, the rebuild: the Linode rebuilt from a fresh Debian 13 image in the Cloud Manager, Backups still enabled, the host key re-read in LISH, then phase 1's R3, R8 and the first lines of R9; the cached token refused and re-minted; every rule `health=ok`; its reading fills `mon-dark`'s second slot.

**R4. The cache nodes** (Task 6; after the third pull request merges, after M3). One node per converge, `db1` then `db2` then `db3`, each outside the day's plan window: `ssh db<n> "sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel"` before and after, the same two lines; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<n> --tags cache -e cache_alloy_digest=sha256:<running>`, the handler's reload 200; `H$ cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`; Alloy's `started` moved, its `RestartCount` 0; then the per-host proof. After `db1`, a day: [[ROLLOUT: R4's day read of `zcrypto-valkey1`'s Alloy headroom, `(go_memstats_sys_bytes - go_memstats_heap_released_bytes) / 402653184` under `job="integrations/self"` on Cloud, its maximum over 24 h against `zcrypto-fleet-alloy-memory-headroom`'s bar — under it, `db2` follows; at or over it, the owner is asked]]. Then `db2`, then `db3`, each the same. The `redis_commands_total` reading of `db1` goes into the records.

**R-records-1. The inside-box records: one pull request.** From `develop`: the deploy-log rows the converges appended; `docs/reference/drill-log.md`'s three entries `M1`, `M2`, `M3`, each the preamble's clauses; `docs/reference/fleet-pins.md`'s `since` cells re-trued for every Alloy row a recreate moved (ops, the three cache nodes); `docs/reference/fleet.md`'s Services and Telemetry labels saying which hosts ship to both; the blacklist decision's follow-on pull request named; T0217's findings gaining the readings; `infra/scripts/count-list.sh converges-inside-a-kraken-window | diff "$CAP/kraken-window-count" -` printing nothing. Its message carries every slot's reading taken so far.

**R5. After the box — the NAS** (Task 7; after the fourth pull request merges, on or after [[ROLLOUT: the box's closing date]]). No Kraken read owed: `W$ infra/ansible/scripts/converge.sh site.yml --limit nas --tags nas --check`, then `… -e nas_apply_compose=true`; the changed-files report names `config.alloy` and `alloy-secrets.env`; `archive-pull` restarted, its next pull line read in the NAS runbook's shape; the Alloy container's `started` moved; the per-host proof.

**R6. The capture pair** (Task 8; after the fifth pull request merges). `zcrypto-red`: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the capture compose render `changed=false` and its restart handler silent, the Alloy reload 200; `H$ cd /etc/zcrypto-capture/alloy && sudo docker compose up -d`; `zcrypto-capture`'s `RestartCount` and `StartedAt` unchanged, Alloy's `started` moved; the per-host proof. Then, an hour later and attended, `zcrypto`: `KRAKEN` immediately before, away from a 4-hourly boundary and from any engine restart; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --skip-tags engine -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, the reload 200; the same two reads; `H$ cd /etc/zcrypto-capture/alloy && sudo docker compose up -d`; `zcrypto-capture` untouched by both reads; the per-host proof. The node's head series read against the bar with the whole fleet shipping: [[ROLLOUT: R6's head-series reading with every host shipping, against the expected 19,100 to 20,900 and the bar of 40,000]].

**R7. The shipper-stop drill on the secondary** (Task 3's M4; after R6, in an attended window). `KRAKEN` at planning and immediately before. Its section's seven parts; `zcrypto-red`'s Alloy row in `fleet-pins.md` re-trued with the restore; its entry in the second records pull request.

**R8. The boundary reading** (spec D20's first trap). One boundary-aligned `count_over_time(up{host="ops", job="integrations/unix"}[5m])` sent to both stacks at the same aligned `time=`, the two values recorded: [[ROLLOUT: R8's two readings — equal, or off by the boundary sample]], written into the spec's measured basis by amendment in the second records pull request, before phase 3's plan.

**R9. The comparison's clock starts.** The seven consecutive daily runs of `grafana-compare.py` start once the last host has 50 h of data on the node: [[ROLLOUT: R6's primary converge time plus 50 h — the first day the comparison may run]]; a rebuild of the node restarts them. The runs are phase 3's gate and are recorded there.

**R-records-2. The after-box records: one pull request.** The deploy-log rows; the `M4` drill-log entry; the `since` cells for the NAS and both capture hosts; the spec amendment of R8; `docs/reference/fleet.md` re-trued; T0217's `## Done so far` gaining this phase and its `## Suggested next steps` cut to phases 3 and 4; `ripe_when` set to the comparison's first day. The commit `chore(fleet): every fleet host ships to the observability node beside Grafana Cloud`, its message carrying every reading, with the trailer.

## Resolution

Two of the spec's open questions are settled here: the bridgehead's Alloy gains `prometheus.exporter.self` with its second endpoint (Task 1), and the workstation proof of P0 decided the tree states, one per role, this plan written to its verdict. The third, the Cloud push URL and Loki hostname as label values on the node, is the owner's and is not decided by a task: the node's endpoint carries no relabel block by invariant, so the only answer consistent with the spec is to let them age out with the 90 days, and the plan proper records the owner's word. The items the spec left unmeasured and assigned to this phase are read in the Rollout: what a bare store restart does (R3, M1), the first cache node's command count (R4), the lines a node outage loses and the rebuild's exposure (R3, M2 and M3), the boundary (R8). The `prometheus` blacklist's fate is M1's, in a pull request of its own.

It does not deliver phases 3 and 4. Phase 3's plan takes from this one: the per-host proof's shape; `mon.md#mon-dark`, which it widens into the node-dark procedure; `grafana-compare.py` and the day its clock starts; the check `zcrypto-mon` and the ops watchdog's probe it re-points; the seven direct-shipped rules by name; and the `since` cells every recreate moved.

## Slots the rollout fills

- `[[ROLLOUT: the box's closing date, 2026-11-01 or a week later …]]` (Global Constraints; Task 7; R5) — the box's own rule, read from the owner's word at its close.
- `[[ROLLOUT: R1 to R6, each host's `count by (job)` on the node after its converge …]]` (the per-host proof) — each converge's post-read, into the two records pull requests.
- `[[ROLLOUT: R3's M1 reading — a bare `systemctl restart prometheus` under a running Grafana pages, or not]]` (R3) — M1's first leg; decides the blacklist's follow-on pull request.
- `[[ROLLOUT: R3's M2 reading — the log lines a 30-minute outage lost]]` (Task 3's `mon-dark`) — M2's measured clause.
- `[[ROLLOUT: R3's M3 reading — the time from the rebuild to the first evaluated rule]]` (Task 3's `mon-dark`) — M3's measured clause.
- `[[ROLLOUT: R4's day read of `zcrypto-valkey1`'s Alloy headroom …]]` (R4) — the day between the first and second cache node.
- `[[ROLLOUT: R6's head-series reading with every host shipping …]]` (R6) — the node's head after the primary ships.
- `[[ROLLOUT: R8's two readings — equal, or off by the boundary sample]]` (R8) — the spec amendment.
- `[[ROLLOUT: R6's primary converge time plus 50 h — the first day the comparison may run]]` (R9) — the comparison's clock.
