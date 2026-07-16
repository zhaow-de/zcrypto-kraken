# OPS-5 Offload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the overlay writer — the reconciler and the trade-backfill, as one unit — off the NAS's Atom onto the ops node, after making the ops node observable enough to host it.

**Architecture:** Three movements in a fixed order. **First** Alloy lands on the ops node and its four already-written-but-unscraped textfiles reach Grafana with alerts (spec D1 — a host whose failures are invisible must not be given the writer). **Second** the NAS acquires a `RECONCILED_SOURCE` pull channel of exactly the existing `PANEL_SOURCE` shape, so the overlay can flow ops→NAS while the NAS still only ever *pulls* (spec 00051 D10). **Third** the writer itself moves: the ops node's hourly `archive-pull` script gains the reconcile + backfill blocks (ported verbatim from the NAS's `pull-entrypoint.sh`, including their pull-failure gate and daily stamp), stops pulling `capture-reconciled`, and the NAS's `pull-entrypoint.sh` loses those blocks.

**Tech Stack:** Ansible (the `ops` role, Debian) · Grafana Alloy · Docker Compose · systemd timers · Grafana Cloud (Prometheus + Loki) · POSIX shell · pytest (for the one guard test).

## Global Constraints

Copied verbatim from spec `00054` and the repo's standing rules. **Every task's requirements implicitly include this section.**

- **D1 ordering is a safety property, not a preference:** observability lands on ops FIRST (Task 3's gate), the writer moves SECOND (Task 7). No task may reorder this.
- **D2 — the overlay writer moves as ONE unit:** reconciler + trade-backfill together. Never one without the other; two writers on one overlay with an rsync between them would clobber ops-side mints.
- **D3 — what STAYS on the NAS, permanently:** custody of every tree; Role A's pull from the capture hosts + its prune-after-verified; the NAS's own Alloy.
- **D4 — the NAS PULLS, it never receives a push.** The `RECONCILED_*` channel is exactly the `PANEL_*` shape: rrsync `-ro` forced-command key on ops pinning the overlay root, host keys pinned, hash-verified, optional (unset ⇒ skipped).
- **D6 — `gate-export` does NOT move.** D3 — **Role A does NOT move.** No `--mint` flip (that is T0039's call). No workstation `data/` migration (that is T0033's OPS-6).
- **No `cli/` changes.** The move is mechanical; spec `00053` D4 built the backfill where the reconciler already lived precisely so no new code is in flight. `zcrypto engine replay --date` already exists (verified) — D9 is a template change only.
- **T0051's lesson is binding:** a `keep` relabel action drops everything unlisted, so an omitted series does not merely go undashboarded — **it does not exist**.
- **NEVER run `ansible-inventory --host` or `--list`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so both silently decrypt the vault and print every secret — including the live Kraken trade key — in cleartext. Use `--graph` / `--list-tags` only.
- **Never write a decrypted secret to a file or echo one.** Encrypt via `ansible-vault encrypt --output <file> -` reading plaintext on **stdin**, and do **NOT** pass `--vault-password-file` (ansible.cfg supplies it via `scripts/vault-pass.sh`).
- **Run playbooks via `infra/ansible/scripts/run.sh`**; preview with `--check --diff` before any converge.
- **The ops node must never join `engine_host` and holds no trade key** (spec 00051 D10). It is pull-only, derived-data.
- **L2 capture is unbackfillable.** Nothing in this plan touches the capture hosts; if a step seems to, stop.
- **Commit convention:** `<type>(<scope>): <subject>`, imperative, lowercase, no trailing period; `Co-Authored-By:` naming the **subagent's own actual model**; `Reviewed-by:` added by the orchestrator after review. Never `--no-verify`.
- **The commit gate is `uv run pre-commit run -a`** — a run that rewrites files reports Failed and leaves rewrites unstaged; re-run until clean, then stage everything it rewrote.

## Two hazards this plan fixes that the spec did not name

Both were found while writing this plan, by reading the live system rather than the design:

1. **The stale-textfile trap (Task 7).** `infra/grafana/alerts.yaml`'s reconciler rules evaluate bare instant vectors (`time() - zcrypto_reconcile_last_success_timestamp_seconds`) with **no instance aggregation**. After the writer moves, the NAS's `reconcile.prom` and `trade-backfill.prom` remain on disk and its Alloy keeps scraping them, so those series **freeze at the cutover instant** and age past the 3h threshold forever — paging permanently from a host that no longer does the work, while ops publishes a healthy copy of the same series names. The cutover MUST delete them. This is the exact shape of T0052's lesson, inverted: not a metric nobody watches, but a metric watching a corpse.
2. **The reconcile gate must survive the move (Task 6).** On the NAS, `zcrypto archive reconcile` is skipped on any cycle whose primary **or** secondary pull failed — because the reconciler reads the two local mirrors and *cannot tell "this hour does not exist" from "this hour did not arrive"*. A wrong verdict there is permanent and unwalkable-back. On ops the mirrors arrive via ops's own `archive-pull`, so the same gate must hold — which is why Task 6 puts reconcile **inside** `archive-pull.sh` (preserving same-cycle `primary_ok`/`secondary_ok` semantics structurally) rather than in a separate timer that would have to re-derive the gate from a textfile.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `infra/ansible/roles/ops/templates/config.alloy.j2` | **create** | The ops node's Alloy pipeline: host metrics + textfile collector + container logs → Grafana Cloud. |
| `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2` | **create** | The Alloy service, as its own compose project (kept out of the liquidations project so an Alloy redeploy can never restart the unbackfillable poller). |
| `infra/ansible/roles/ops/defaults/main.yml` | modify | Alloy image/digest, secrets path, `ops_reconciled_*` producer vars. |
| `infra/ansible/roles/ops/tasks/main.yml` | modify | Render + start Alloy; render the reconcile env. |
| `infra/ansible/roles/ops/templates/archive-pull.sh.j2` | modify | Drops `capture-reconciled` from the pulled trees; gains the reconcile + backfill blocks (D2). |
| `infra/ansible/roles/ops/templates/verified-replay.sh.j2` | modify | `--date` scoping (D9). |
| `infra/nas/pull-entrypoint.sh` | modify | Loses reconcile + backfill; gains the `RECONCILED_SOURCE` pull block. |
| `infra/nas/compose.yaml` | modify | `RECONCILED_*` channel env; retires the writer-side env. |
| `infra/grafana/alerts.yaml` | modify | Ops-node rules + replay staleness. |
| `tests/test_infra_alloy_series.py` | **create** | The T0051 guard: every series the stack publishes must match its host's keep-regex. |
| `infra/ops/README.md`, `infra/nas/README.md` | modify | Channel + deploy docs. |

---

### Task 1: The ops node's Alloy stack

**Files:**

- Create: `infra/ansible/roles/ops/templates/config.alloy.j2`
- Create: `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2`
- Modify: `infra/ansible/roles/ops/defaults/main.yml`
- Modify: `infra/ansible/roles/ops/tasks/main.yml`
- Test: `tests/test_infra_alloy_series.py`

**Interfaces:**

- Consumes: the existing `ops_textfile_dir` (`{{ ops_data_dir }}/textfile`), already populated by the four timers.
- Produces: `ops_alloy_image`, `ops_alloy_digest`, `ops_alloy_dir` (defaults); a running `alloy` container on the ops node; the keep-regex that Task 2's alerts depend on.

**Context you need:**

`infra/nas/config.alloy` is the reference shape — read it first. Mirror its structure (unix exporter with `set_collectors`, `textfile` block, `prometheus.scrape` → `prometheus.remote_write`, `discovery.docker` → `loki.source.docker` → `loki.process` → `loki.write`), its `sys.env(...)` secrets handling, and its two write_relabel_configs (drop `go_.*|process_.*|alloy_.*`, then keep-only).

**Three deliberate divergences from the NAS's file — do not copy blindly:**

1. **cadvisor:** the NAS omits it because it SIGSEGVs on Synology DSM's cgroup-less kernel, taking down all of Alloy. **The ops node is Debian with a normal cgroup hierarchy, so that rationale does not apply.** Still do **not** add cadvisor: this task's job is the four textfile series + host metrics reaching Grafana (D1), and container CPU/mem is not part of D1's gate. Adding it would also enlarge the active-series budget the spec flags as an open risk. Record the *reason* in a comment — "omitted by choice here, not by DSM constraint" — so the next reader does not re-derive it.
2. **`user:`/`group_add`:** the NAS's `1031:1000` + `group_add: ["0"]` exists to satisfy DSM ACLs while keeping Alloy off the 0600 rrsync keys (T0030). On ops, run Alloy as the `deploy` uid/gid (the role already derives `ops_uid`/`ops_gid` via `getent`), and add `group_add: ["docker"]`. **Do not mount `/:/host/root:ro`** — the NAS needs it for its rootfs collector, but ops holds rrsync keys under `/home/deploy/.ssh` and this task has no reason to expose them. Set `rootfs_path` to `/host/root` only if you mount it; otherwise omit both the mount and the `rootfs_path` line and drop `filesystem` from `set_collectors`… **except** free-disk-space on ops IS wanted (it holds 5 GB+ of mirrors and will hold the overlay). So: mount `/:/host/root:ro` and keep `filesystem`, and note in a comment that this is the T0042/T0030 residual replicated to ops **with a smaller blast radius** (no trade key, no capture-VPS rrsync key) — exactly as spec D7 states.
3. **The `host` label:** the NAS's `discovery.relabel` block hardcodes `replacement = "nas"`. Use `"ops"` here. The NAS's container-name regex strips a `zcrypto-archive-` compose prefix; ops's compose projects are different — derive the label from `__meta_docker_container_name` with a regex that strips the leading `/` and any trailing `-N` replica index, without assuming the NAS's project prefix.

**The keep-regex (T0051 — this is the part that must be exactly right):**

It MUST match, at minimum, every series below. The first four already exist on the node and currently reach nobody; the last two arrive when Task 6 lands, and a keep-regex written without them would make the moved writer invisible on the very host it moved to.

```
up|node_load1|node_load5|node_load15|node_memory_MemTotal_bytes|node_memory_MemAvailable_bytes|node_memory_MemFree_bytes|node_filesystem_avail_bytes|node_filesystem_size_bytes|node_filesystem_free_bytes|node_network_receive_bytes_total|node_network_transmit_bytes_total|node_cpu_seconds_total|node_textfile_scrape_error|node_scrape_collector_success|node_scrape_collector_duration_seconds|ops_archive_pull_.*|ops_panel_.*|ops_verify_replay_.*|ops_verified_replay_.*|zcrypto_reconcile_.*|zcrypto_trade_backfill_.*
```

**Secrets:** Alloy's Grafana Cloud credentials arrive exactly as on the NAS — an out-of-band, 0600, never-committed env file read via `sys.env(...)`. Add `ops_alloy_secrets_path: /etc/zcrypto-ops/alloy-secrets.env` to defaults. **Do not render, generate, echo, or commit the credentials**; the role only references the path, and Task 3 (attended) places the file by hand. Do not add it to the vault in this task.

- [ ] **Step 1: Write the failing guard test**

Create `tests/test_infra_alloy_series.py`. This is the T0051 regression guard: it asserts that each series the stack publishes actually survives its host's keep-regex. It must be able to fail — verify that in Step 2.

```python
"""Guard: a `keep` relabel drops every series it does not list (T0051), so a series missing from
the keep-regex does not go undashboarded -- it does not exist. These tests pin the regexes against
the series the stack actually publishes, so deleting one from the config fails here rather than
silently going dark in production."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NAS_ALLOY = REPO / "infra/nas/config.alloy"
OPS_ALLOY = REPO / "infra/ansible/roles/ops/templates/config.alloy.j2"

# The series each host must ship. NAS: Role A/B (gate) + its host metrics. OPS: the four timer
# textfiles (written since OPS-3/OPS-4 but scraped by nothing until spec 00054 Task 1) plus the
# overlay writer's series, which move to this host in Task 6.
NAS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "zcrypto_gate_streak_days",
    "zcrypto_reconcile_last_success_timestamp_seconds",
    "zcrypto_trade_backfill_exit_code",
]
OPS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "ops_archive_pull_exit_code",
    "ops_archive_pull_last_success_timestamp",
    "ops_panel_exit_code",
    "ops_verify_replay_exit_code",
    "ops_verified_replay_exit_code",
    "ops_verified_replay_last_success_timestamp",
    "zcrypto_reconcile_last_success_timestamp_seconds",
    "zcrypto_reconcile_source_lag_seconds",
    "zcrypto_trade_backfill_exit_code",
    "zcrypto_trade_backfill_last_success_timestamp",
]


def _keep_regex(path: Path) -> re.Pattern:
    """Extract the `keep` write_relabel_config's regex from an Alloy config."""
    text = path.read_text()
    blocks = re.findall(
        r'write_relabel_config\s*\{(.*?)\}', text, re.DOTALL
    )
    keeps = [b for b in blocks if 'action' in b and '"keep"' in b]
    assert len(keeps) == 1, f"{path}: expected exactly one keep block, found {len(keeps)}"
    m = re.search(r'regex\s*=\s*"([^"]+)"', keeps[0])
    assert m, f"{path}: keep block has no regex"
    # Prometheus relabel regexes are fully anchored.
    return re.compile(r"\A(?:" + m.group(1) + r")\Z")


@pytest.mark.parametrize(
    ("path", "required"),
    [(NAS_ALLOY, NAS_REQUIRED), (OPS_ALLOY, OPS_REQUIRED)],
    ids=["nas", "ops"],
)
def test_keep_regex_admits_every_published_series(path, required):
    keep = _keep_regex(path)
    missing = [s for s in required if not keep.match(s)]
    assert not missing, f"{path}: keep-regex drops {missing} -- those series will NOT exist"


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY], ids=["nas", "ops"])
def test_alloy_self_metrics_are_dropped_before_the_keep(path):
    """Defence in depth, and the ordering matters: the drop must precede the keep."""
    text = path.read_text()
    drop_at = text.find('"drop"')
    keep_at = text.find('"keep"')
    assert drop_at != -1, f"{path}: no drop block"
    assert keep_at != -1, f"{path}: no keep block"
    assert drop_at < keep_at, f"{path}: the drop block must come before the keep block"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_infra_alloy_series.py -v`

Expected: the `nas` parametrisations PASS (that config already exists and already lists these series), and **both `ops` parametrisations FAIL** with a file-not-found error on `config.alloy.j2` — proving the test is actually reaching for the file this task creates. If the `ops` cases pass, the test is not testing anything: stop and fix it.

- [ ] **Step 3: Write `infra/ansible/roles/ops/templates/config.alloy.j2`**

Follow `infra/nas/config.alloy`'s structure and the three divergences above. Use `{{ ops_textfile_dir }}`-independent paths: the container sees the textfile dir at `/textfile` (the compose file maps it), so `directory = "/textfile"` exactly like the NAS's. Include the keep-regex verbatim from this task's block above. Comment the cadvisor and `host`-label decisions.

- [ ] **Step 4: Write `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2`**

Its own compose project, in `{{ ops_alloy_dir }}`. Model it on the NAS compose's `alloy` service: `image: "{{ ops_alloy_image }}@{{ ops_alloy_digest }}"`, `restart: unless-stopped`, `network_mode: host`, `GOMEMLIMIT: 460MiB`, `env_file: [./alloy-secrets.env]`, the same `command:` list, the `/proc`,`/sys`,`/`,`docker.sock`,`config.alloy`,`alloy-data` volume set, `{{ ops_textfile_dir }}:/textfile:ro`, and a `memory: 512m` limit. Unlike the NAS, DO set `cpus:` — Debian has a CPU cgroup (say `cpus: "2.0"`; the box has 24 threads and Alloy must never contend with the writer this iteration exists to make fast). `user: "{{ ops_uid }}:{{ ops_gid }}"`, `group_add: ["docker"]`.

- [ ] **Step 5: Add the defaults**

In `infra/ansible/roles/ops/defaults/main.yml`, following the file's existing commenting style:

```yaml
# --- Alloy (spec 00054 D1/D7): the ops node's telemetry stack. D1 is an ORDERING constraint --
# this lands, and its series are confirmed in Grafana, BEFORE the overlay writer moves here
# (plan 00054 Task 3 gates Task 7). Without it the node's four textfiles reach nobody, and moving
# the writer onto an unobservable host would be T0052's defect one level up.
ops_alloy_dir: /etc/zcrypto-ops/alloy
ops_alloy_image: grafana/alloy
# 0600, out-of-band, NEVER committed: GRAFANA_PROM_URL/USERNAME/PASSWORD +
# GRAFANA_LOKI_URL/USERNAME/PASSWORD, same contract as infra/nas/alloy-secrets.env. The role only
# references this path -- it never renders the credentials (they are not in the vault).
ops_alloy_secrets_path: "{{ ops_alloy_dir }}/alloy-secrets.env"
```

`ops_alloy_digest` gets **no default**, exactly like `ops_image_digest`: pass it per-run and guard its tasks with `when: ops_alloy_digest is defined`, so a converge without it skips the Alloy install rather than rendering a unit pointing at a broken image reference.

- [ ] **Step 6: Wire the role tasks**

In `infra/ansible/roles/ops/tasks/main.yml`, add a block after the existing `ops_image_digest` block:

```yaml
- name: install the ops telemetry stack — Grafana Alloy (spec 00054 D1; needs the pinned Alloy digest)
  when: ops_alloy_digest is defined
  block:
    - name: ensure the alloy project + data directories exist
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        owner: deploy
        group: deploy
        mode: "0755"
      loop:
        - "{{ ops_alloy_dir }}"
        - "{{ ops_alloy_dir }}/alloy-data"

    - name: render the alloy pipeline config
      ansible.builtin.template:
        src: config.alloy.j2
        dest: "{{ ops_alloy_dir }}/config.alloy"
        owner: deploy
        group: deploy
        mode: "0644"

    - name: render the alloy compose file
      ansible.builtin.template:
        src: alloy-compose.yaml.j2
        dest: "{{ ops_alloy_dir }}/compose.yaml"
        owner: deploy
        group: deploy
        mode: "0644"
```

The `getent`/`set_fact` that derive `ops_uid`/`ops_gid` currently live inside the `ops_image_digest` block; the Alloy templates need them too. **Hoist those two tasks above both blocks** so either can converge independently — this is a real coupling bug you would otherwise introduce (an Alloy-only converge without `ops_image_digest` would render `user: ":"`). Removing them from the old block and placing them before both is the minimal fix.

Deliberately **do not** `docker compose up` here: first start is attended (Task 3), matching the liquidations poller's existing rationale in this same file.

- [ ] **Step 7: Run the guard test — it must now pass**

Run: `uv run pytest tests/test_infra_alloy_series.py -v`
Expected: 4 passed.

- [ ] **Step 8: Prove the test can still fail (mutation check)**

Temporarily delete `ops_verified_replay_.*` from the keep-regex in `config.alloy.j2`, re-run the test, and confirm the `ops` case FAILS naming that series. Restore it. A guard test that cannot fail is decoration — this step is how you know it works.

- [ ] **Step 9: Lint + commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/ops tests/test_infra_alloy_series.py
git commit -m "$(cat <<'EOF'
feat(config): render Grafana Alloy on the ops node (spec 00054 D1/D7)

The ops node has written four textfile metric families since OPS-3/OPS-4
(ops_archive_pull/ops_panel/ops_verify_replay/ops_verified_replay) with nothing
scraping them, so they reached nobody. Alloy lands FIRST, before the overlay
writer moves here (D1): moving it onto a host whose failures are invisible would
be T0052's defect one level up.

The keep-regex already lists zcrypto_reconcile_.* and zcrypto_trade_backfill_.*,
which arrive with Task 6 -- a `keep` action drops anything unlisted (T0051), so
writing the regex without them would make the moved writer invisible on the very
host it moved to. tests/test_infra_alloy_series.py pins that both ways.

Divergences from the NAS's config, each deliberate: no cadvisor (the NAS omits it
because it SIGSEGVs on DSM's cgroup-less kernel -- that reason does NOT apply to
Debian; omitted here by choice, to hold the active-series budget); a real cpus:
limit (DSM has no CPU cgroup, Debian does); host="ops". Alloy runs as deploy, not
root. T0042's root-equivalent-Docker residual is thereby replicated to a second
host, with a smaller blast radius (no trade key, no capture-VPS rrsync key) -- as
D7 states rather than leaves to be discovered.

Alloy is its own compose project, not a service in the liquidations project: an
Alloy redeploy must never restart the unbackfillable poller.

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Grafana alerts for the ops node

**Files:**

- Modify: `infra/grafana/alerts.yaml`

**Interfaces:**

- Consumes: the series Task 1's keep-regex admits.
- Produces: alert rules in the `zcrypto-ops` ruleGroup.

**Context you need:**

Read an existing rule end-to-end first — `Reconciler · exporter stale` (around line 413) is the canonical staleness template: `relativeTimeRange`, a `refId: A` Prometheus query, a `refId: C` `__expr__` threshold, `noDataState`, `execErrState`, `for`, `annotations.summary`, `labels.severity`, `notification_settings.receiver`. Copy that shape exactly.

The receiver split (documented at the top of the file): `receiver: metrics` for Prometheus-sourced rules, `receiver: logs` for Loki-sourced rules.

**`noDataState` is a real decision, not boilerplate — get it right per rule:**

- A **dead-man** rule (nothing ran) uses `noDataState: Alerting`: no series at all means the host, Alloy, or the timer is gone, and that IS the alarm.
- An **exit-code** rule uses `noDataState: OK`: the metric is absent until the job first runs, and a brand-new host must not page for never having run. This is the exact split the existing `zcrypto-trade-backfill-stale` (Alerting) / `zcrypto-trade-backfill-exit-nonzero` (OK) pair uses.

- [ ] **Step 1: Add the ops rule group**

Append a `zcrypto-ops` ruleGroup with these five rules. Use the existing file's exact YAML shape.

| Title | expr | Threshold | noData | severity |
|---|---|---|---|---|
| `Ops · archive-pull stalled (dead-man)` | `time() - ops_archive_pull_last_success_timestamp` | `gt 10800` (3h; hourly timer at `:12`, so ~2 missed cycles) | `Alerting` | critical |
| `Ops · archive-pull non-zero exit` | `ops_archive_pull_exit_code` | `gt 0` | `OK` | warning |
| `Ops · verified-replay stale` (D9's rule) | `time() - ops_verified_replay_last_success_timestamp` | `gt 172800` (48h; the timer is daily at 05:23, so this is 2 missed days — matching the trade-backfill staleness rule's reasoning) | `Alerting` | warning |
| `Ops · verified-replay non-zero exit` | `ops_verified_replay_exit_code` | `gt 0` | `OK` | critical |
| `Ops · node load high` | `node_load1` (see below) | `gt 20` | `OK` | warning |

For `Ops · node load high`, the ops box has 24 threads, so the NAS's threshold is meaningless here — read the existing `NAS · load high` rule and set the ops threshold from the core count, not by copying the number. **The series must be scoped to the ops host** or this rule will also read the NAS's `node_load1`: use the `host` label Task 1's relabel sets — `node_load1{host="ops"}`. Check the existing NAS rule: if it does not scope by host, note that in your report as a pre-existing gap (do **not** fix it here — that is scope creep; it becomes a finding for the orchestrator).

Write each `annotations.summary` to say what is broken and **why it matters**, in the voice of the existing rules — e.g. for the archive-pull dead-man: "The ops node's mirror is the input to the overlay writer, the panel, and both replays. While the pull is stalled every one of them is reasoning from a mirror that is silently ageing."

- [ ] **Step 2: Validate the YAML**

Run: `uv run pre-commit run -a`
Expected: yamllint passes. If it rewrites the file, re-stage.

- [ ] **Step 3: Verify the rules parse as Grafana expects**

Run: `uv run python -c "import yaml,sys; d=yaml.safe_load(open('infra/grafana/alerts.yaml')); rules=[r for g in d['groups'] for r in g['rules']] if 'groups' in d else d['rules']; ops=[r for r in rules if r['title'].startswith('Ops · ')]; print(len(ops), 'ops rules'); [print(' ', r['title'], '| noData=', r['noDataState'], '| recv=', r['notification_settings']['receiver']) for r in ops]"`

Expected: `5 ops rules`, each printing its `noDataState` and `receiver`. If the file's top-level shape differs from the snippet above, adapt the one-liner to the real structure rather than editing the file to fit the snippet.

- [ ] **Step 4: Commit**

```bash
git add infra/grafana/alerts.yaml
git commit -m "$(cat <<'EOF'
feat(config): alert on the ops node's series (spec 00054 D1, D9)

Five rules in a new zcrypto-ops group, covering the textfiles Task 1 made
scrapable. noDataState is per-rule, not boilerplate: dead-man rules use Alerting
(no series = the host/Alloy/timer is gone, which IS the alarm), exit-code rules
use OK (the metric is absent until the job first runs, and a new host must not
page for never having run) -- the same split the trade-backfill pair already uses.

The load rule is scoped host="ops" and thresholded off this box's core count; the
NAS's number would be meaningless on 24 threads.

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 (ATTENDED — orchestrator only, no subagent): deploy Alloy and PROVE the series land

**This task is D1's gate. Task 7 must not begin until this one has passed.** It touches a real host, so it is orchestrator-only.

- [ ] **Step 1: Place the secrets file by hand**

The credentials are the same Grafana Cloud pair the NAS uses. Copy `infra/nas/alloy-secrets.env`'s contract to `/etc/zcrypto-ops/alloy/alloy-secrets.env` on the ops node, `0600`, owned by `deploy`. **Never echo the values, never write them to a repo path, never commit them, never add them to the vault in this task.**

- [ ] **Step 2: Resolve the Alloy image digest**

```bash
timeout 60 ssh hp 'docker pull grafana/alloy:latest && docker inspect --format="{{index .RepoDigests 0}}" grafana/alloy:latest'
```

Record the digest. The ops node is x86-64 with AVX, so the plain image is correct — the `-compat` variant is the NAS Atom's problem, not this host's.

- [ ] **Step 3: Preview the converge**

```bash
cd infra/ansible
timeout 300 ./scripts/run.sh site.yml --limit zcrypto-ops --tags ops \
  -e ops_alloy_digest=sha256:<...> -e ops_image_digest=sha256:<...> --check --diff
```

Expected: the Alloy directory/template tasks show as changed; **nothing touching capture or the engine appears** (the ops play runs `base`/`chrony`/`docker`/`ops` only). If any capture-host task appears, STOP — the `--limit` did not apply.

- [ ] **Step 4: Converge for real**

Same command without `--check --diff`. Expected: `changed` on the Alloy tasks, `failed=0`. **Verify `skipped` did not swallow the block** — iter-099's false-evidence lesson: a `when: ops_alloy_digest is defined` block silently skips when the digest is omitted, and `ok=N` then proves nothing. Confirm the Alloy tasks are in the `changed`/`ok` counts, not `skipped`.

- [ ] **Step 5: Start Alloy**

```bash
timeout 60 ssh hp 'cd /etc/zcrypto-ops/alloy && docker compose up -d && sleep 5 && docker compose ps'
```

Expected: `alloy` Up. If it restarts, read `docker compose logs alloy` — the likely causes are the secrets file (missing/misnamed vars) or a config parse error.

- [ ] **Step 6: THE GATE — prove the series reach Grafana, by outcome**

Do not accept "the container is up" as evidence; that is the exit-code fallacy D10 rejects. Query Grafana Cloud for each series and confirm a **fresh** value with `host="ops"` / the ops instance:

- `ops_archive_pull_last_success_timestamp`
- `ops_panel_exit_code`
- `ops_verify_replay_exit_code`
- `ops_verified_replay_exit_code`
- `node_load1{host="ops"}`
- ops container logs present in Loki with `host="ops"`

**If any of the four textfile series is absent, the keep-regex is wrong — fix Task 1 and re-converge. Do not proceed to Task 7 with a partial gate.** A series that does not arrive here is a series that will not arrive for the writer either.

- [ ] **Step 7: Confirm the active-series budget (spec's stated open risk)**

Check the Grafana Cloud active-series count against the <1k target now that a second host ships host metrics. Record the number in the closeout. If it exceeds budget, trim the keep-regex — do not silently blow through it.

- [ ] **Step 8: Record the gate result**

Append to the progress ledger: the digest deployed, the six confirmations, and the active-series count. Task 7 cites this.

---

### Task 4: Scope the verified-replay timer with `--date` (D9)

**Files:**

- Modify: `infra/ansible/roles/ops/templates/verified-replay.sh.j2`

**Interfaces:**

- Consumes: `zcrypto engine replay --path verified --journal-dir <dir>` — **`--date YYYY-MM-DD` already exists** on this command (verified: "Replay only this UTC day's journaled cycles (YYYY-MM-DD). Defaults to every journaled day."). No `cli/` change.
- Produces: an unchanged `ops_verified_replay_*` textfile contract (Task 2's alerts depend on it).

**Context you need:**

The timer fires daily at `05:23` UTC (`verified-replay.timer.j2`, `Persistent=true`). Today it replays the **whole** journal every day — an unbounded daily cost that grows forever. D9 bounds it.

**Which date:** yesterday (`date -u -d yesterday +%F`), not today. At 05:23 UTC today's journal holds at most the 00:00 and 04:00 cycles — an incomplete day. Yesterday is complete and immutable, so the replay is deterministic and its verdict is final.

**The `Persistent=true` interaction — think before you write:** if the box is off for three days, systemd runs the timer **once** on boot, not three times, so those days are never replayed. That is a real coverage gap this change introduces (today's whole-journal replay accidentally covers it). Do not solve it here — that is scope creep. **Report it to the orchestrator as a finding**; it belongs in the closeout as an open-topic candidate.

- [ ] **Step 1: Scope the replay to yesterday**

In `infra/ansible/roles/ops/templates/verified-replay.sh.j2`, replace the `docker run` invocation's command with a `--date`-scoped one, and add the date to the log context:

```bash
# D9 (spec 00054): scope the replay to ONE day instead of the whole journal. Unscoped, this cost
# grows with the archive forever -- the ops node's speed would merely hide that, which is exactly
# why it is bounded now rather than when it next hurts. YESTERDAY, not today: at 05:23 UTC today's
# journal holds at most the 00:00/04:00 cycles, so scoping to today would replay an incomplete day
# and call it verified. Yesterday is complete and immutable, so the verdict is final.
REPLAY_DATE=$(date -u -d yesterday +%F)

docker run --rm --pull never \
    --user "{{ ops_uid }}:{{ ops_gid }}" \
    -v "{{ ops_data_dir }}:/data:ro" \
    --entrypoint zcrypto \
    "{{ ops_image }}@{{ ops_image_digest }}" \
    engine replay --path verified --date "$REPLAY_DATE" --journal-dir "/data/{{ ops_journal_subdir }}"
rc=$?
```

Leave the textfile block, the `prev_success` carry-forward, the atomic publish, and the dead-man ping **exactly as they are** — Task 2's alerts key on that contract.

- [ ] **Step 2: Verify the date expression on this machine**

Run: `date -u -d yesterday +%F`
Expected: yesterday's date as `YYYY-MM-DD`. (GNU coreutils; the ops node is Debian, so `-d yesterday` is available. Note this is a *host-side* expression in the rendered script, not inside the container.)

- [ ] **Step 3: Verify the CLI accepts the flag combination**

Run: `uv run zcrypto engine replay --help`
Expected: the help lists `--date`, `--path`, and `--journal-dir`. Confirm `--date` takes `YYYY-MM-DD`.

- [ ] **Step 4: Lint + commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/ops/templates/verified-replay.sh.j2
git commit -m "$(cat <<'EOF'
fix(config): scope the ops verified-replay to one day (spec 00054 D9)

It replayed the WHOLE journal daily -- a cost that grows with the archive
forever. The ops node is fast enough to hide that, which is precisely why it is
bounded now rather than when it next matters.

Yesterday, not today: the timer fires 05:23 UTC, when today's journal holds at
most the 00:00/04:00 cycles -- scoping to today would replay an incomplete day
and call it verified. Yesterday is complete and immutable, so the verdict is
final. --date already exists on `engine replay`; no cli/ change.

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: The `RECONCILED_SOURCE` channel — the NAS pulls the overlay from ops (D4)

**Files:**

- Modify: `infra/nas/compose.yaml`
- Modify: `infra/nas/pull-entrypoint.sh`
- Modify: `infra/nas/README.md`
- Modify: `infra/ops/README.md`

**Interfaces:**

- Consumes: `zcrypto archive pull <source> <dest>` — hash-verifies via `.sha256` sidecars.
- Produces: the `RECONCILED_SOURCE` / `RECONCILED_SSH_KEY` / `RECONCILED_SSH_PORT` env contract; `RECONCILED_DEST` keeps its existing value and meaning (`/archive/capture-reconciled`) but becomes a **pull destination** instead of a write destination.

**Context you need — read `infra/nas/pull-entrypoint.sh`'s `PANEL_SOURCE` block first.** This channel is that block, exactly: own least-privilege key, own per-call SSH port (the ops node is a home-LAN box on port 22, not the VPS's 10022), skipped entirely when the source var is unset, best-effort (a failure is logged, never exits the loop), and **not** an input to the reconcile gate.

**Verified fact you can rely on:** the overlay contains 391 `.parquet` + 391 `.sha256` + 391 `.json` + `reconcile-ledger.jsonl` (no sidecar). `verify_tree` (`cli/archive/pull.py:39`) iterates `root.rglob("*.parquet")` only, so the unsidecar'd ledger is simply never checked and the pull verifies cleanly. **This channel therefore uses the default `--verify`, NOT `--no-verify`** — unlike the journal channel, which needs `--no-verify` because it has no sidecars at all. Do not copy the journal block.

- [ ] **Step 1: Add the channel env to `infra/nas/compose.yaml`**

Beside the `PANEL_*` block, matching its comment density:

```yaml
      # OPS-5 (spec 00054 D4): the overlay's flow INVERTS here. The ops node is now the
      # capture-reconciled tree's producer (the reconciler + trade-backfill moved there), so the NAS
      # stops writing it and acquires it instead. The NAS PULLS -- it never receives a push: that is
      # the established shape (PANEL_* above) and it preserves spec 00051 D10's pull-only transport,
      # so a compromised ops node still cannot write into custody.
      #
      # Hash-verified (NOT --no-verify, unlike the journal): every minted hour carries a .sha256
      # sidecar, and verify_tree only walks *.parquet -- so the unsidecar'd reconcile-ledger.jsonl
      # rides along unchecked rather than failing the pull. Same home-LAN port-22 caveat as the
      # panel/liquidations channels. Unset RECONCILED_SOURCE and the pull is skipped entirely, so
      # this compose file stays valid on a NAS that has not been given the channel yet -- which is
      # also the rollback: unset it and the NAS is simply a NAS without the overlay.
      RECONCILED_SOURCE: ${RECONCILED_SOURCE:-}
      RECONCILED_SSH_KEY: /keys/sync_reconciled
      RECONCILED_SSH_PORT: ${RECONCILED_SSH_PORT:-22}
```

`RECONCILED_DEST` already exists in this file — **leave the line, update its comment** to say it is now a pull destination, not the reconciler's output.

- [ ] **Step 2: Add the pull block to `infra/nas/pull-entrypoint.sh`**

Immediately after the `PANEL_SOURCE` block, before the reconcile block (which Task 6 removes):

```sh
	# OPS-5 (spec 00054 D4): the healed overlay, now PRODUCED on the ops node and pulled here.
	# Custody stays on the NAS (D3) -- only the computation moved. Own least-privilege key and its
	# own per-call SSH port, exactly like the panel/liquidations channels above. Hash-verified: the
	# overlay's minted hours carry .sha256 sidecars (verify_tree walks *.parquet only, so the
	# unsidecar'd ledger rides along unchecked). Best-effort like every other pull -- a failure is
	# logged and the loop continues; the overlay is recomputable on ops, so a missed cycle costs a
	# delay, not data. Skipped entirely when RECONCILED_SOURCE is unset.
	if [ -n "${RECONCILED_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$RECONCILED_SSH_KEY" ARCHIVE_SSH_PORT="${RECONCILED_SSH_PORT:-22}" \
				zcrypto archive pull "$RECONCILED_SOURCE" "$RECONCILED_DEST"; then
			log ERROR "reconciled pull failed (source=$RECONCILED_SOURCE dest=$RECONCILED_DEST), continuing"
		fi
	fi
```

- [ ] **Step 3: Verify the shell still parses**

Run: `sh -n infra/nas/pull-entrypoint.sh`
Expected: no output (exit 0). The file is `#!/usr/bin/env sh` — POSIX, not bash: `sh -n` is the correct check, and it will catch a bashism-shaped syntax error.

- [ ] **Step 4: Document the channel**

In `infra/ops/README.md`, document the ops-side `sync_reconciled` rrsync forced-command entry alongside the existing `sync_panel` / `sync_liquidations` ones: an `-ro` (read-only) forced command pinning `/var/lib/zcrypto-ops/capture-reconciled`, so the key cannot read anything else on the box and cannot write. Follow the existing entries' exact format — read them first. In `infra/nas/README.md`, add `RECONCILED_SOURCE` / `RECONCILED_SSH_PORT` to the env-var contract and note the `/keys/sync_reconciled` key.

**Do not generate the keypair in this task** — key material is an attended step (Task 7).

- [ ] **Step 5: Lint + commit**

```bash
uv run pre-commit run -a
git add infra/nas infra/ops/README.md
git commit -m "$(cat <<'EOF'
feat(config): add the RECONCILED_SOURCE channel — the NAS pulls the overlay (spec 00054 D4)

The overlay's flow inverts: ops becomes capture-reconciled's producer, so the NAS
must acquire it. The NAS PULLS and never receives a push -- the established
PANEL_* shape, preserving spec 00051 D10's pull-only transport, so a compromised
ops node still cannot write into custody. Custody itself does not move (D3): only
the computation does.

Hash-verified, NOT --no-verify: every minted hour carries a .sha256 sidecar, and
verify_tree walks *.parquet only, so the unsidecar'd reconcile-ledger.jsonl rides
along unchecked rather than failing the pull. The journal channel needs
--no-verify because it has no sidecars at all; this one must not copy it.

Optional by construction (unset RECONCILED_SOURCE => skipped), which is also the
rollback path.

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: The overlay writer moves to ops, as one unit (D2)

**Files:**

- Modify: `infra/ansible/roles/ops/templates/archive-pull.sh.j2`
- Modify: `infra/ansible/roles/ops/defaults/main.yml`
- Modify: `infra/nas/pull-entrypoint.sh`
- Modify: `infra/nas/compose.yaml`

**Interfaces:**

- Consumes: `zcrypto archive reconcile <primary> <secondary> <overlay> --window-hours N --min-gap-seconds N --textfile <path>`; `zcrypto archive backfill-trades <primary> <reconciled>`. **Both unchanged — no `cli/` edits.**
- Produces: `zcrypto_reconcile_*` and `zcrypto_trade_backfill_*` textfiles **on the ops node**, in `{{ ops_textfile_dir }}` (Task 1's Alloy scrapes them; Task 2's alerts read them).

**Context you need — read `infra/nas/pull-entrypoint.sh`'s reconcile and backfill blocks in full before writing anything.** You are porting them, comments included; their reasoning is the point, not decoration.

**The gate is the whole reason this goes INSIDE `archive-pull.sh` rather than in its own timer.** The NAS skips reconcile on any cycle whose primary **or** secondary pull failed, because the reconciler reads the two local mirrors and cannot distinguish *"this hour does not exist"* from *"this hour did not arrive"*. A broken primary pull would mint "healed" full-secondary hours for data that was never lost; a broken secondary pull would classify a real primary outage as `total_loss` — permanent, paged, booked into a monotone counter that can never be walked back. Those detectors run unconditionally (they are not gated by `--mint`), so this bites even in detect-only mode. On ops the mirrors arrive via ops's **own** `archive-pull`, so the same gate must hold — and putting reconcile in the same script preserves same-cycle `primary_ok`/`secondary_ok` semantics structurally, instead of re-deriving them from a textfile. **An unhealed hour costs nothing; a wrong verdict is forever.**

The current script tracks a single aggregate `rc` across all four trees. You must replace that with per-tree tracking so a failed *journal* pull does not needlessly skip reconcile, while a failed *capture* pull still does.

- [ ] **Step 1: Rewrite the pull loop with per-tree gates**

In `infra/ansible/roles/ops/templates/archive-pull.sh.j2`, replace the `for tree in ...` loop. **`capture-reconciled` leaves this list** — ops produces it now; continuing to pull it would overwrite ops's own mints with the NAS's stale copy on the very next cycle.

```bash
    rc=0
    primary_ok=1
    secondary_ok=1
    # The BARE `rsync -a` flags are LOAD-BEARING for the pull(:12)-before-materialize(:22) overlap
    # safety (review M1): default per-file hidden-tmp+rename means a reader never sees a torn
    # parquet, and in-order-per-directory transfer keeps the mirror a sorted PREFIX per pair, so the
    # panel watermark can never leapfrog a mid-tree hole. Adding --inplace/--partial-dir/
    # --delay-updates would silently break that invariant.
    #
    # OPS-5 (spec 00054 D2/D4): {{ ops_reconciled_subdir }} is NOT in this list any more -- this host
    # PRODUCES the overlay now (the reconcile + backfill blocks below). Pulling it would overwrite
    # this node's own mints with the NAS's copy on the next cycle, which is exactly the
    # two-writers-one-tree hazard D2 exists to prevent. The NAS acquires it the other way now, via
    # its own RECONCILED_SOURCE pull (infra/nas/pull-entrypoint.sh).
    #
    # Per-tree outcome tracking, not one aggregate rc: the reconcile gate below must key on the two
    # CAPTURE mirrors specifically. A failed journal pull must not skip reconcile (the reconciler
    # never reads the journal), and a failed capture pull must skip it even if everything else
    # succeeded.
    if ! rsync -a -e "$SSH_CMD" "$SOURCE{{ ops_capture_subdir }}/" "{{ ops_data_dir }}/{{ ops_capture_subdir }}/"; then
        rc=1
        primary_ok=0
    fi
    if ! rsync -a -e "$SSH_CMD" "${SOURCE}capture-segments-red/" "{{ ops_data_dir }}/capture-segments-red/"; then
        rc=1
        secondary_ok=0
    fi
    if ! rsync -a -e "$SSH_CMD" "$SOURCE{{ ops_journal_subdir }}/" "{{ ops_data_dir }}/{{ ops_journal_subdir }}/"; then
        rc=1
    fi
```

- [ ] **Step 2: Port the reconcile block**

After the pull loop and **inside** the `else` branch (i.e. only when `SOURCE` is non-empty — an unwired node must not reconcile against mirrors it never pulled). Port the NAS's comment wholesale; it is the reasoning that keeps the next reader from "simplifying" the gate away.

```bash
    # Role C (spec 00050), moved here by OPS-5 (spec 00054 D2). DETECT-ONLY by default -- it ledgers
    # every `would_mint` and writes no parquet until T0039's soak has pinned --min-gap-seconds from
    # real cross-host data. That flip is T0039's call, NOT this iteration's.
    #
    # SKIPPED on any cycle whose PRIMARY **or SECONDARY** pull failed. The reconciler reasons from the
    # two LOCAL mirrors, and it cannot tell "this hour does not exist" from "this hour did not arrive".
    # A failed pull -- on either channel -- makes local absence uninformative:
    #
    #   * primary pull broken: hours look primary-dark but are not. Reconciling would mint "healed"
    #     full-secondary hours for data that was never lost, quietly substituting one host's stream for
    #     the other's in an archive that cannot be backfilled, and inflating healed_gap_seconds so the
    #     very metric meant to flag a degrading primary reports success instead.
    #   * secondary pull broken: the witness looks dark too. A real primary outage -- the exact event
    #     Role C exists to heal -- would then be classified `both_streams_silent` / `total_loss`:
    #     PERMANENT loss, paged, and booked into a monotone counter that can never be walked back, for
    #     an hour the secondary actually captured and could have healed. The correlated-loss detectors
    #     run unconditionally (they are not gated by --mint), so this bites even in detect-only mode,
    #     and the ledger's dedupe means the false verdict is never revisited.
    #
    # Skipping keeps the ledger honest for free: the hours simply reconcile on the next healthy cycle,
    # against complete mirrors. An unhealed hour costs nothing; a wrong verdict is forever.
    if [ "$primary_ok" -eq 0 ] || [ "$secondary_ok" -eq 0 ]; then
        echo "zcrypto-archive-pull: reconcile skipped: a capture pull failed this cycle (primary_ok=$primary_ok secondary_ok=$secondary_ok), so a mirror's absence cannot be told apart from a pull that has not landed yet"
    elif ! docker run --rm --pull never \
            --user "{{ ops_uid }}:{{ ops_gid }}" \
            -v "{{ ops_data_dir }}:/data" \
            -v "{{ ops_textfile_dir }}:/textfile" \
            --entrypoint zcrypto \
            "{{ ops_image }}@{{ ops_image_digest }}" \
            archive reconcile "/data/{{ ops_capture_subdir }}" "/data/capture-segments-red" "/data/{{ ops_reconciled_subdir }}" \
            --window-hours "{{ ops_reconcile_window_hours }}" \
            --min-gap-seconds "{{ ops_reconcile_min_gap_seconds }}" \
            --textfile /textfile/reconcile.prom; then
        echo "zcrypto-archive-pull: reconcile failed, continuing"
        rc=1
    fi
```

- [ ] **Step 3: Port the backfill block, stamp and all**

Immediately after the reconcile block, still inside the `else` branch:

```bash
    # Trade backfill (spec 00053; T0053), moved here by OPS-5 as ONE unit with the reconciler (D2) --
    # they share this entrypoint, the overlay, and union_trades, so splitting them would put two
    # writers on one tree with an rsync between them.
    #
    # DAILY, not per-cycle -- the detector's scan is O(archive), and there is no urgency cliff
    # (Kraken serves ~18 months of /Trades). Gated on a stamp file holding the last UTC day it ran;
    # the stamp is written UNCONDITIONALLY -- success or failure. A PERMANENT error (an unmapped
    # pair, a structural residual) exits non-zero on every attempt, and writing the stamp only on
    # success once meant that ran the full O(archive) scan plus hundreds of REST calls every hour,
    # forever -- exactly the per-cycle cost this step exists to avoid. Stamping unconditionally makes
    # the daily cost bound absolute; the failure is carried by the metric and its alert
    # (infra/grafana/alerts.yaml), not by a retry. The metric is the signal, not the retry.
    backfill_stamp="{{ ops_data_dir }}/.trade-backfill-last-utc-day"
    backfill_today="$(date -u +%Y-%m-%d)"
    if [ "$(cat "$backfill_stamp" 2>/dev/null || echo none)" != "$backfill_today" ]; then
        echo "$backfill_today" > "$backfill_stamp"
        if docker run --rm --pull never \
                --user "{{ ops_uid }}:{{ ops_gid }}" \
                -v "{{ ops_data_dir }}:/data" \
                --entrypoint zcrypto \
                "{{ ops_image }}@{{ ops_image_digest }}" \
                archive backfill-trades "/data/{{ ops_capture_subdir }}" "/data/{{ ops_reconciled_subdir }}"; then
            backfill_rc=0
        else
            backfill_rc=$?
            echo "zcrypto-archive-pull: trade backfill failed (exit=$backfill_rc), continuing"
        fi
        backfill_textfile="{{ ops_textfile_dir }}/trade-backfill.prom"
        printf 'zcrypto_trade_backfill_exit_code %d\n' "$backfill_rc" > "$backfill_textfile.tmp"
        printf 'zcrypto_trade_backfill_last_run_timestamp %d\n' "$(date -u +%s)" >> "$backfill_textfile.tmp"
        if [ "$backfill_rc" -eq 0 ]; then
            printf 'zcrypto_trade_backfill_last_success_timestamp %d\n' "$(date -u +%s)" >> "$backfill_textfile.tmp"
        fi
        mv "$backfill_textfile.tmp" "$backfill_textfile"
    fi
```

**Note the stamp path changed** from the NAS's `/archive/.trade-backfill-last-utc-day` to `{{ ops_data_dir }}/.trade-backfill-last-utc-day` — it is host-side here, not container-side, because this script runs on the host and only the `docker run` sees `/data`.

- [ ] **Step 4: Add the reconcile knobs to defaults**

In `infra/ansible/roles/ops/defaults/main.yml`:

```yaml
# --- OPS-5 (spec 00054 D2): the overlay writer's knobs, moved here with the writer from the NAS's
# compose (RECONCILE_MIN_GAP_SECONDS / RECONCILE_WINDOW_HOURS). DETECT-ONLY still applies -- the
# reconciler ledgers `would_mint` and writes no parquet until T0039's soak pins the gap threshold
# from real cross-host data. The default is deliberately 2x the measured 14.78 s single-host maximum
# natural quiescence: one secondary update row is enough to witness a gap, so a per-connection
# coalescing artifact could otherwise trip a phantom splice -- an unaudited data swap into an
# archive that cannot be backfilled. Flipping to --mint is T0039's call, not this role's.
ops_reconcile_min_gap_seconds: 30
ops_reconcile_window_hours: 48
```

- [ ] **Step 5: Strip the writer from the NAS**

In `infra/nas/pull-entrypoint.sh`, **delete** the reconcile block and the trade-backfill block wholesale. Leave `capture_ok` / `secondary_ok` in place — they are still assigned and still logged, and the pulls that set them stay. Add one line where the reconcile block was:

```sh
	# The reconcile + trade-backfill steps MOVED to the ops node (spec 00054 D2/OPS-5): this host
	# kept custody, Role A's pull/prune, and its Alloy (D3), and shed the computation -- the Atom tax
	# on every step sharing this clock had stretched the "hourly" loop to ~103 minutes. The healed
	# overlay now arrives via the RECONCILED_SOURCE pull above instead of being written here.
```

In `infra/nas/compose.yaml`, remove `RECONCILE_TEXTFILE`, `RECONCILE_MIN_GAP_SECONDS`, `RECONCILE_WINDOW_HOURS`, and `TRADE_BACKFILL_TEXTFILE`. Keep `RECONCILED_DEST` (Task 5 repurposed it as the pull destination).

- [ ] **Step 6: Verify both scripts parse**

Run: `sh -n infra/nas/pull-entrypoint.sh`
Expected: exit 0, no output.

Run: `uv run python -c "
from jinja2 import Environment
import pathlib, sys
src = pathlib.Path('infra/ansible/roles/ops/templates/archive-pull.sh.j2').read_text()
out = Environment().from_string(src).render(
    ops_textfile_dir='/var/lib/zcrypto-ops/textfile', ops_archive_pull_healthcheck_url='',
    ops_nas_pull_source='deploy@192.168.100.5:', ops_data_dir='/var/lib/zcrypto-ops',
    ops_capture_subdir='capture-segments', ops_reconciled_subdir='capture-reconciled',
    ops_journal_subdir='engine-journal', ops_uid='1000', ops_gid='1000',
    ops_image='ghcr.io/zhaow-de/zcrypto-capture', ops_image_digest='sha256:deadbeef',
    ops_reconcile_window_hours=48, ops_reconcile_min_gap_seconds=30)
pathlib.Path('/tmp/rendered-archive-pull.sh').write_text(out)
assert 'capture-reconciled/\"' not in out.split('reconcile')[0], 'the reconciled tree is still being PULLED'
print('rendered ok')
"`

Expected: `rendered ok`. Then:

Run: `bash -n /tmp/rendered-archive-pull.sh`
Expected: exit 0. (This one IS bash — `archive-pull.sh.j2` is `#!/usr/bin/env bash`.)

- [ ] **Step 7: Verify the reconciled tree is no longer pulled**

Run: `grep -c 'ops_reconciled_subdir' infra/ansible/roles/ops/templates/archive-pull.sh.j2`
Expected: a non-zero count (it appears in the reconcile/backfill invocations) — then read the matches and confirm **none of them is an `rsync` line**. This is the two-writers-one-tree check; do it by eye, not by count alone.

- [ ] **Step 8: Full test suite + lint**

Run: `uv run pytest -q`
Expected: all pass (no `cli/` changed, so this is a regression check that the plan held its non-goal).

Run: `uv run pre-commit run -a` — re-run until clean, then stage anything it rewrote.

- [ ] **Step 9: Commit**

```bash
git add infra/ansible/roles/ops infra/nas
git commit -m "$(cat <<'EOF'
feat(config): move the overlay writer to the ops node (spec 00054 D2)

The reconciler and the trade-backfill move together, as one unit: they share the
entrypoint, the overlay, and union_trades, so splitting them would put two writers
on one tree with an rsync between them. The NAS keeps custody, Role A's
pull/prune, and its Alloy (D3) -- only computation moves. Motivating measurement:
the NAS's "hourly" loop had stretched to a 103-minute period (~43 min compute per
cycle) with zcrypto_reconcile_source_lag_seconds at 4072.

The reconcile blocks live INSIDE archive-pull.sh, not in their own timer, because
the gate must survive the move: the reconciler reads the two local mirrors and
cannot tell "this hour does not exist" from "this hour did not arrive", so it must
skip any cycle whose primary or secondary pull failed. Same-script means same-cycle
primary_ok/secondary_ok semantics structurally, instead of re-deriving them from a
textfile. The pull loop now tracks per-tree outcomes rather than one aggregate rc,
so a failed journal pull does not needlessly skip reconcile while a failed capture
pull still does. An unhealed hour costs nothing; a wrong verdict is forever.

capture-reconciled leaves the ops pull list -- this host produces it now, and
pulling it would overwrite its own mints with the NAS's copy each cycle.

Still detect-only: the --mint flip is T0039's call and is independent of the host
the code runs on. No cli/ changes -- spec 00053 D4 built the backfill where the
reconciler already lived precisely so this move would be mechanical.

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

### Task 7 (ATTENDED — orchestrator only, no subagent): the cutover

**Do not start until Task 3's gate passed.** This is the iteration's only irreversible window, and D5's safety rests on a *measured* fixed point — **re-measure it, do not trust the spec's 2026-07-16 numbers.**

- [ ] **Step 1: RE-VERIFY the byte-identity fixed point (D5)**

The spec measured 1175 files identical on both sides (list sha `0b684ce3…`) on 2026-07-16. That was then. Re-derive now, C-locale-sorted on both sides (a Synology/Debian `sort` locale mismatch produced a false aggregate mismatch once already):

```bash
timeout 120 ssh hp 'cd /var/lib/zcrypto-ops/capture-reconciled && find . -type f | LC_ALL=C sort | xargs sha256sum' | LC_ALL=C sort > /tmp/ops-overlay.list
timeout 120 ssh nas 'cd /volume1/ZhaoCrypto/capture-reconciled && find . -type f | LC_ALL=C sort | xargs sha256sum' | LC_ALL=C sort > /tmp/nas-overlay.list
diff /tmp/ops-overlay.list /tmp/nas-overlay.list && echo "IDENTICAL — fixed point holds"
wc -l /tmp/ops-overlay.list /tmp/nas-overlay.list
```

**If they differ, STOP and escalate.** A diff means the fixed point ended (T0039 flipped `--mint`, or a backfill minted a new gap), and cutting over would either lose an ops-side mint or write the wrong overlay into custody. Re-plan the cutover as a real migration rather than a pointer flip.

- [ ] **Step 2: Confirm the writer is still quiescent**

```bash
timeout 60 ssh nas 'docker logs --since 3h zcrypto-archive-archive-pull-1 2>&1 | grep -cE "minted|would_mint"'
```

Expected: `would_mint` lines are fine (detect-only ledgering); **any `minted` line means T0039's flip already happened** — STOP and escalate, D5's premise is void.

- [ ] **Step 3: Generate the `sync_reconciled` keypair and install the forced command**

On the ops node, create an `-ro` rrsync forced-command entry in `deploy`'s `authorized_keys` pinning `/var/lib/zcrypto-ops/capture-reconciled`, exactly matching the existing `sync_panel` entry's format. Place the private key on the NAS at `infra/nas/keys/sync_reconciled`, `0600`, owned by uid 1000 — **0600 is load-bearing**: Alloy runs as gid 1000 there, so the key's protection rests on owner-only read, not group isolation (T0030). **Never echo the private key; never commit it.**

- [ ] **Step 4: Stop the NAS's writer**

```bash
timeout 60 ssh nas 'cd /volume1/docker/zcrypto-archive && docker compose stop archive-pull'
```

- [ ] **Step 5: DELETE the stale writer textfiles from the NAS — do not skip this**

This is the trap named at the top of this plan. The NAS's Alloy scrapes textfiles **in place**, so leaving these makes the moved writer's series freeze at this instant and age forever, paging permanently from a host that no longer does the work — while ops publishes a healthy copy of the same series names, with no instance aggregation in the rules to tell them apart.

```bash
timeout 60 ssh nas 'rm -f /volume1/docker/zcrypto-archive/textfile/reconcile.prom /volume1/docker/zcrypto-archive/textfile/trade-backfill.prom && ls -l /volume1/docker/zcrypto-archive/textfile/'
```

Expected: only `gate.prom` remains (Role B's `gate-export` stays on the NAS — D6).

- [ ] **Step 6: Deploy the ops-side writer**

```bash
cd infra/ansible
timeout 300 ./scripts/run.sh site.yml --limit zcrypto-ops --tags ops \
  -e ops_image_digest=sha256:<...> -e ops_alloy_digest=sha256:<...> --check --diff
```

Review the diff, then converge for real. Confirm `changed` on `archive-pull.sh` and `verified-replay.sh`, `failed=0`, and that the digest-guarded blocks are **not** in `skipped`.

- [ ] **Step 7: Wire the NAS's pull channel and restart**

Add `RECONCILED_SOURCE=deploy@192.168.100.6:` (and `RECONCILED_SSH_PORT` if not 22) to the NAS's `.env`, then:

```bash
timeout 120 ssh nas 'cd /volume1/docker/zcrypto-archive && docker compose up -d'
```

- [ ] **Step 8: Restart Alloy on the NAS (T0048)**

A recreated container's logs stop shipping until Alloy is restarted — this **will** bite, since Step 7 recreated `archive-pull`:

```bash
timeout 60 ssh nas 'cd /volume1/docker/zcrypto-archive && docker compose restart alloy'
```

- [ ] **Step 9: Force one ops cycle and watch it**

```bash
timeout 600 ssh hp 'sudo systemctl start zcrypto-archive-pull.service; sleep 5; journalctl -u zcrypto-archive-pull -n 60 --no-pager'
```

Expected: the three trees rsync; reconcile runs and writes `/var/lib/zcrypto-ops/textfile/reconcile.prom`; the backfill runs (first run on this host — the stamp is absent) and writes `trade-backfill.prom`. **No `capture-reconciled` rsync line.**

---

### Task 8 (ATTENDED — orchestrator only): verify by outcome (D10)

D10 is explicit that exit codes do not count. Every item below is an observed outcome. **Record each measurement in the ledger — the closeout cites them, and the before-picture is already in the spec.**

- [ ] **Step 1: The NAS loop period drops toward its 60-minute floor**

Before: `reconcile complete` at 11:18:31 / 13:01:07 / 14:44:25 — a **103-minute** period against a `sleep 3600`, i.e. ~43 min of compute per cycle.

```bash
timeout 60 ssh nas 'docker logs --since 6h zcrypto-archive-archive-pull-1 2>&1 | grep -E "pull complete" | tail -6'
```

Expected: consecutive cycles ~60 min apart. **This is the iteration's headline number** — the drift is the thing that was supposed to go away.

- [ ] **Step 2: `zcrypto_reconcile_source_lag_seconds` falls**

Before: **4072 s** (68 minutes) against a stream that lands hourly. Query it in Grafana; expect a materially lower value. Record it.

- [ ] **Step 3: The overlay is identical across hosts after a full cycle in the NEW direction**

Re-run Task 7 Step 1's two-sided diff **after** the NAS has completed one `RECONCILED_SOURCE` pull. Expected: `IDENTICAL`. This proves the inverted flow actually carries the tree, not just that a command exited 0.

- [ ] **Step 4: The raw mirrors are byte-unchanged**

The move must not have touched raw capture. Verify the primary/secondary mirrors on the NAS are unchanged (spot-check hour counts and a sample of manifests). **L2 capture is unbackfillable — this is the check that says we did no harm.**

- [ ] **Step 5: The invariant still holds from the ops-side canonical view**

```bash
timeout 900 ssh hp 'docker run --rm --pull never -v /var/lib/zcrypto-ops:/data:ro --entrypoint zcrypto ghcr.io/zhaow-de/zcrypto-capture@sha256:<...> archive backfill-trades /data/capture-segments /data/capture-reconciled --detect-only 2>&1 | tail -5'
```

Expected: `gaps=0 missing=0 duplicates=0` — the invariant iter-100 established, now confirmed from the new host's view.

- [ ] **Step 6: Both alert families are healthy on exactly one instance**

Confirm in Grafana that `zcrypto_reconcile_*` and `zcrypto_trade_backfill_*` now report from **ops only** — no frozen NAS series (Task 7 Step 5). Confirm no reconciler alert is firing. **A stale duplicate here means Step 5 of Task 7 was skipped.**

---

### Task 9: Closeout

**Files:**

- Modify: `docs/open-topics/T0033-home-ops-node-compute-tier.md`
- Modify: `docs/open-topics/T0044-*.md`
- Modify: `docs/open-topics/README.md`
- Modify: `docs/iterations-history-phase1.md`
- Modify: `.tmp/decisions-phase1.md`
- Modify: `README.md` (only if a user-facing CLI/ops surface changed)

**Context:** `.claude/rules/iterations-history.md` — closeout docs are authored **at closeout, when the work is real**, never pre-written during planning. Everything below is written now because the work now exists.

- [ ] **Step 1: T0033 — OPS-5 → done**

Flip OPS-5's status per `.claude/rules/open-topics.md`. The topic as a whole stays open (OPS-6 remains, now carrying the workstation payloads). Keep `status: partial` and record OPS-5's completion under `## Done so far` with the PR link and the Task 8 measurements — the before/after loop period and the lag figure, not just "moved".

- [ ] **Step 2: T0044 — update findings, LEAVE OPEN (D8)**

Record the measured before/after in `## Findings so far`: its `ripe_when` fires on "the ledger grows large enough that a reconcile cycle's O(ledger) scan slows", and moving that scan to a real CPU released exactly that pressure. **Do not close it.** Its other live sub-item — the correction marker — is independent of where the code runs. **Relieving pressure is not fixing the defect**, and closing it here would repeat the T0051 mistake this project already made once. Update the `ripe_when` to reflect that the pressure is off but the sub-item stands.

- [ ] **Step 3: Register the deferrals found during implementation**

Per `.claude/rules/open-topics.md`, **prose is not registration** — a follow-up mentioned only in a report or PR body is invisible when future work is picked. Each of these gets a topic (or an explicit one-line drop in the decisions log):

1. **The `Persistent=true` replay-coverage gap** (Task 4): a multi-day outage now replays only one day instead of the whole journal. `ripe_when:` the ops node is offline for more than one day.
2. **The `noDataState` / instance-aggregation gap** in the reconciler rules (found in Task 2): the rules read bare instant vectors, so any second publisher of the same series is indistinguishable. The cutover removes today's instance, but the rule shape is still fragile.
3. **Any pre-existing host-scoping gap** the Task 2 implementer reported in the NAS rules.
4. **The stray `reconcile-ledger.jsonl.bak-20260714-220209`** in the overlay (root-owned, mode 777, sitting in a tree whose whole point is an append-only audit ledger) — either drop it explicitly with a reason or register it.

- [ ] **Step 4: Append the iter-101 entry to `docs/iterations-history-phase1.md`**

Per `.claude/rules/iterations-history.md`, route by **subject-matter phase** — this is Phase-1 data-foundation work. One bullet per change: the Alloy stack and what it made visible; the alerts; the `RECONCILED_SOURCE` channel and the flow inversion; the writer's move as one unit and why the gate went inside `archive-pull.sh`; the `--date` scoping; the two hazards this plan caught (the stale-textfile trap, the gate's survival); and the D10 outcome numbers.

- [ ] **Step 5: Append the `[iter-101]` decisions to `.tmp/decisions-phase1.md`**

Per `.claude/rules/decisions-log.md`, one paragraph per decision, 2–3 options each with a tradeoff, resolution marked `(Decision: N)`. **Append only — do not drain the log**; persistence into a committed sibling is a *phase*-level close-out task, not a per-iteration one.

- [ ] **Step 6: README — only if a user-facing surface changed**

Per `.claude/rules/readme-usage.md`, the `## Usage` section must document CLI subcommands/options. This iteration changes **no `cli/` surface** — it moves hosts, not commands. If `README.md` describes *where* the reconciler runs, update that; otherwise **make no change**, and say so in the report rather than inventing an edit.

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add docs README.md
git commit -m "$(cat <<'EOF'
docs(config): close out OPS-5 — iter-101

T0033's OPS-5 done: the overlay writer runs on the ops node, the NAS kept custody
and Role A. T0044 updated with the measured before/after but LEFT OPEN on its
correction-marker sub-item -- relieving pressure is not fixing the defect (D8).

Co-Authored-By: <your actual model> <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage** — every decision maps to a task:

| Spec | Task |
|---|---|
| D1 observability first | Tasks 1–3; **Task 3 is the gate**, Task 7 the move |
| D2 writer moves as ONE unit | Task 6 |
| D3 custody/Role A/Alloy stay on the NAS | Task 6 Step 5 (removes only the writer); enforced by omission elsewhere |
| D4 flow inverts, NAS pulls | Task 5 |
| D5 cutover safe at a fixed point | Task 7 Steps 1–2 (**re-measured, not trusted**) |
| D6 gate-export does not move | Task 7 Step 5 (`gate.prom` explicitly survives) |
| D7 Alloy on ops inherits T0042 | Task 1 (stated in the config comment + commit body) |
| D8 T0044 relieved, not closed | Task 9 Step 2 |
| D9 `--date` scoping | Task 4 |
| D10 verify by outcome | Task 8 |
| Non-goals (no `cli/`, no `--mint`, no OPS-6) | Task 6 Step 8 (`pytest` regression); no task touches `cli/` |

**Placeholder scan:** the only `<...>` are runtime digests and the subagent's own model name, both of which must be filled from the live system rather than guessed — they are inputs, not unwritten content.

**Type consistency:** `ops_reconciled_subdir`, `ops_capture_subdir`, `ops_journal_subdir`, `ops_textfile_dir`, `ops_uid`/`ops_gid` are used exactly as `defaults/main.yml` defines them. `RECONCILED_SOURCE`/`_DEST`/`_SSH_KEY`/`_SSH_PORT` are consistent between Task 5's compose and entrypoint. Task 1's keep-regex series names match Task 2's alert exprs and Task 6's textfile emissions (`zcrypto_trade_backfill_exit_code`, `zcrypto_reconcile_last_success_timestamp_seconds`, `ops_verified_replay_last_success_timestamp`) — and `tests/test_infra_alloy_series.py` is the machine check on precisely that agreement.

**One coupling bug caught during review:** Task 1 Step 6 hoists the `getent`/`set_fact` uid/gid derivation out of the `ops_image_digest` block, because the Alloy templates need those facts and an Alloy-only converge would otherwise render `user: ":"`.
