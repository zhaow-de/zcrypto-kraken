# Day-2 runbooks and the daily operations pass — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every alert rule carries a resolving runbook link, enforced by a test; a read-only instrument reads alert states, Loki, the dead-men (two ways), a fleet verdict and the window's deploys; a Markdown journal and a skill make a daily pass that follows the runbook for whatever fired.

**Architecture:** The guard lands red first and names the gap. Seven new subsystem files under `infra/runbooks/` take the 51 sections; one file move keeps `engine.md` under the split bar. `infra/scripts/ops-daily.py` is a plain script beside `grafana-query.py`, sharing a new `grafana_auth.py` resolver, tested on fixture responses with live paths behind an opt-in env var. The journal is `docs/reference/ops-journal/<YYYY-MM>.md`; the skill `.claude/skills/zcrypto-daily-ops/SKILL.md` is the procedure.

**Tech Stack:** Python 3.14 via `uv run`; `urllib.request` (no new dependency); PyYAML (already a dev dependency, used by the alert tests); pytest with `monkeypatch`; Markdown runbooks under mdformat.

**Spec:** `docs/specs/00104-day2-runbooks-and-daily-ops-pass-design.md`

## Global Constraints

- **Verify, never transcribe.** The reader drafts under the SDD workspace `drafts/` directory (copied from the session scratchpad; if absent, derive as each task describes) are starting points. Every command, path, unit name, metric and threshold in a runbook section is grep-verified against `infra/`, `cli/` or `infra/grafana/alerts.yaml` before it lands — a draft is never a citation.
- **Operator-facing text carries no internal tokens** (`.claude/rules/operator-facing-text.md`): no `T<NNNN>`, `spec NNNNN`, `iter-<N>` in alert summaries, runbook section headings, `--help`, or metric HELP. Runbook *bodies* may cite topics and specs.
- **Runbook section shape** (`infra/runbooks/README.md`): `<a name="<uid>"></a>` on its own line, blank line, `## <uid> — ALERT` (or `— KNOWN LIMITATION` / `— PROCEDURE` / `— SCHEDULED REMINDER`), then `### What you are seeing` · `### What it means` · `### What to do` · `### Retire when`, in that order. A section serving several uids carries one `<a name>` per uid, stacked, above one heading. Every `Retire when` names something checkable.
- **Alert summary link line**: the summary's last line is exactly `Runbook: infra/runbooks/<file>.md#<anchor>` (see `infra/grafana/alerts.yaml` line ~340 for the shape).
- **No host is touched by Tasks 1–18, and they never ssh.** Task 19 is where the credentialed, fleet-touching steps live, and it runs in the main loop after the merge. `grafana-push.sh`, the healthchecks.io description writes and the first live pass all live in Task 19, which runs in the main loop after the merge — and the first pass may ssh under the skill's own autonomous tier, which is why the no-ssh claim is scoped to Tasks 1–18.
- **Never print a container's environment; never run `ansible-inventory --host/--list/--graph --vars`** (CLAUDE.md `## Secrets`, `fleet-deploys.md`). Vault variable *names* may be read; values are resolved only inside `grafana_auth.vault_var`, never printed.
- **Secrets never reach stdout, argv or a file**: the token and the healthchecks key live in locals and request headers only.
- **Stage by explicit path, one commit-type per commit**; every commit carries `Co-Authored-By: <actual model> <noreply@anthropic.com>`.
- Markdown: one line per paragraph; escape `|` as `\|` inside a table's code spans.

---

### Task 1: The guard — every rule must carry a resolving runbook link

**Files:**
- Modify: `tests/test_infra_alert_rules.py` (beside `test_every_runbook_link_in_an_alert_summary_resolves`, line ~589)

**Interfaces:**
- Consumes: `_rules()`, `_runbook_anchors()`, `_RUNBOOK_LINK` already in the file.
- Produces: `test_every_alert_rule_carries_a_resolving_runbook_link` — the red run's output is the uid set every later task shrinks.

- [ ] **Step 1: Write the failing test**

```python
def test_every_alert_rule_carries_a_resolving_runbook_link():
    """A rule with no runbook is read on a phone, in Slack, with nothing open -- the situation the
    runbook protocol exists for. Requiring the link on EVERY rule is what keeps a new rule from
    shipping without a procedure; the sibling test above only checks links that are present."""
    anchors = _runbook_anchors()
    unlinked = []
    for rule in _rules():
        summary = (rule.get("annotations") or {}).get("summary") or ""
        links = _RUNBOOK_LINK.findall(summary)
        if not links or any(filename not in anchors.get(anchor, ()) for filename, anchor in links):
            unlinked.append(rule["uid"])
    assert not unlinked, f"{len(unlinked)} rule(s) carry no resolving runbook link in their summary: {sorted(unlinked)}"
```

- [ ] **Step 2: Run it and record the red set**

Run: `uv run pytest tests/test_infra_alert_rules.py::test_every_alert_rule_carries_a_resolving_runbook_link -v 2>&1 | tail -5`
Expected: FAIL naming **51** uids. Save the sorted list to the SDD workspace as `red-set.txt` — it is the acceptance set for Tasks 3–9 (set equality, not a count).

- [ ] **Step 3: Confirm the sibling tests still pass**

Run: `uv run pytest tests/test_infra_alert_rules.py -q 2>&1 | tail -2`
Expected: exactly 1 failed (the new test), everything else passed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_infra_alert_rules.py
git commit -m "test(obs): every alert rule must carry a resolving runbook link -- red on 51 today"
```

---

### Task 2: Move the two PROCEDURE sections to `engine-procedures.md`

**Files:**
- Create: `infra/runbooks/engine-procedures.md`
- Modify: `infra/runbooks/engine.md` (remove `engine-probe-window` and `engine-tracking-band` sections — from the `<a name="engine-probe-window"></a>` line to end of file)
- Modify: `infra/runbooks/README.md` (index rows lines ~67–68 → new heading), `infra/grafana/engine-dashboard.json` (line ~1803 cites `engine.md#engine-tracking-band`)

**Interfaces:**
- Produces: anchors `engine-probe-window`, `engine-tracking-band` now defined in `engine-procedures.md`; `engine.md` at 7 sections so Task 9's +4 lands at 11.

- [ ] **Step 1: Cut the two sections byte-identical**

```bash
cd infra/runbooks
start=$(grep -n '^<a name="engine-probe-window"></a>' engine.md | cut -d: -f1)
{ printf '# Engine — attended procedures\n\nNothing fires these; you run them deliberately. Alert-triggered sections stay in [`engine.md`](engine.md).\n\n'; tail -n +"$start" engine.md; } > engine-procedures.md
head -n $((start - 1)) engine.md > engine.md.tmp && mv engine.md.tmp engine.md
grep -c '^<a name=' engine.md engine-procedures.md
```
Expected: `engine.md:7`, `engine-procedures.md:2`.

- [ ] **Step 2: Update every citation**

```bash
cd /home/zhaow/Projects/zcrypto-kraken
grep -rln 'engine.md#engine-probe-window\|engine.md#engine-tracking-band' infra/ docs/open-topics docs/reference cli/ tests/ .claude/ | grep -v 'infra/runbooks/engine-procedures.md'
```
For each hit outside `docs/open-topics/archive/`, replace `engine.md#engine-probe-window` → `engine-procedures.md#engine-probe-window` and likewise for `engine-tracking-band` (`sed -i` per file). In `README.md`, move the two rows under a new heading `### [`engine-procedures.md`](engine-procedures.md) — the engine's attended procedures` placed right after the `engine.md` heading's rows. Archived topics are point-in-time and stay.

- [ ] **Step 3: Prove the anchors resolve and nothing is duplicated**

Run: `uv run pytest tests/test_infra_alert_rules.py -q -k "runbook" 2>&1 | tail -2`
Expected: only Task 1's new test fails (51 uids); the anchor-uniqueness, summary-link and dashboard-link tests pass.

- [ ] **Step 4: Commit**

```bash
git add infra/runbooks/engine.md infra/runbooks/engine-procedures.md infra/runbooks/README.md infra/grafana/engine-dashboard.json
git commit -m "docs(runbooks): the two attended procedures move to engine-procedures.md, anchors byte-identical"
```

---

### Task 3: `gate.md` — the five gate rules

**Files:**
- Create: `infra/runbooks/gate.md`
- Modify: `infra/grafana/alerts.yaml` (summaries of `zcrypto-gate-streak-reset`, `zcrypto-gate-mismatch`, `zcrypto-gate-pull-lag`, `zcrypto-gate-exporter-stale`, `zcrypto-gate-cache-reverify-stalled`), `infra/runbooks/README.md` (new heading + 5 rows)
- Draft input: `drafts/alerts-gate-engine-nas.md` (gate section)

**Interfaces:**
- Produces: five anchors named exactly as the uids.

- [ ] **Step 1: For each rule, read its definition and its producer**

For each uid: `grep -n -A40 "uid: <uid>" infra/grafana/alerts.yaml` (title, expr, `for`, severity, `noDataState`, annotations); then grep the expr's metric name in `cli/` and `infra/` (the gate exporter is `infra/nas/pull-entrypoint.sh` + `cli/engine/command.py` `gate-export`) and read what moves it. Write down the evaluation interval of the rule's group.

- [ ] **Step 2: Write the file**

`# Gate — the shadow-concordance export on the NAS` as the H1, one paragraph naming the producer (`gate-export` in the NAS pull loop, textfile → NAS Alloy → Prometheus), then five sections in the Global-Constraints shape. Each `### What to do` is numbered commands an operator runs: on the NAS `sudo /usr/local/bin/docker logs --since 2h zcrypto-archive-pull` (full path — `docker` is off the non-interactive ssh `PATH` there), the textfile path and its mtime, `uv run python infra/scripts/grafana-query.py '<the rule's expr>'` from the workstation. `zcrypto-gate-mismatch`'s section states that the metric is a per-run recount over the whole journal (not a counter) so `increase()` re-fires for a day after one mismatch. `zcrypto-gate-cache-reverify-stalled`'s reset is `rm /tmp/gate-cache.json` inside the container (the cache is on no mount and replays cold on recreate — say so). Every `### Retire when` names the rule uid's absence from `alerts.yaml`.

- [ ] **Step 3: Link the five summaries; index the file**

Append the line `Runbook: infra/runbooks/gate.md#<uid>` as the summary's last line for each rule (keep the summary's existing wording; fix only what is false against the producer you read, and say what you fixed in the commit body). Add to `README.md` a heading `### [`gate.md`](gate.md) — the shadow-concordance export on the NAS` with one row per uid in the index's existing row shape.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_infra_alert_rules.py -q 2>&1 | tail -3`
Expected: the new test's list is `red-set.txt` minus these five; every other test passes. Run `uv run pre-commit run -a` until clean (mdformat may reflow the file).

- [ ] **Step 5: Commit**

```bash
git add infra/runbooks/gate.md infra/runbooks/README.md infra/grafana/alerts.yaml
git commit -m "docs(runbooks): gate.md -- the five gate rules get their procedures"
```

---

### Task 4: `nas.md` — the four NAS rules

**Files:**
- Create: `infra/runbooks/nas.md`
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-nas-disk-low`, `zcrypto-nas-load-high`, `zcrypto-nas-archive-pull-errors`, `zcrypto-nas-archive-pull-stalled`), `infra/runbooks/README.md`
- Draft input: `drafts/alerts-gate-engine-nas.md` (NAS section)

Same five steps as Task 3, with these section-specific facts verified before they land: `nas-disk-low` reclaims **only** images (`uv run python infra/scripts/prune-host-images.py nas`, then `--apply`) and never archive data; `nas-load-high` names the loop's own steps (full hash scope, gate-export) against DSM jobs, and says to watch the `pull complete` cadence rather than the load number; `nas-archive-pull-errors` tabulates the producer lines (`cli/archive/command.py` — grep `logger.error`); `nas-archive-pull-stalled` is the Loki dead-man (`pull complete ... failed=0` absent 3 h) and its first step separates host-down / telemetry-dark / loop-dead, pointing the ledger-correction procedure at `infra/nas/README.md`. Commit: `docs(runbooks): nas.md -- the four NAS rules get their procedures`.

---

### Task 5: `hosts.md` — OS-level signals across the fleet

**Files:**
- Create: `infra/runbooks/hosts.md`
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-capture-disk-low`, `zcrypto-capture-load-high`, `zcrypto-capture-reboot-pending`, `zcrypto-capture-textfile-missing`, `zcrypto-capture-textfile-unreadable`, `zcrypto-reboot-probe-stale`, `zcrypto-oneoff-textfile-stale`), `infra/runbooks/README.md`
- Draft input: `drafts/alerts-capture-logship-alloy.md` (A–D)

Same five steps. Sections: `zcrypto-capture-disk-low`; `zcrypto-capture-load-high` (the runbook says read the vCPU count from the series, never from prose); `zcrypto-capture-reboot-pending` (its summary's `fleet-deploys.md` citation is replaced by `docs/reference/fleet.md` § Reboots — the discipline lives there); one section `capture-textfile-transport` with four stacked `<a name>` tags (`zcrypto-capture-textfile-missing`, `zcrypto-capture-textfile-unreadable`, `zcrypto-reboot-probe-stale`, `zcrypto-oneoff-textfile-stale`) — the exporters write via `mktemp` 0600 + `mv`, the collector runs as the Alloy user, the fix is the script in the repo and never `chmod` on the host, and a **deleted** `.prom` vanishes rather than stales (only the `count()` shape sees it). Commit: `docs(runbooks): hosts.md -- disk, load, reboot and the textfile transport get their procedures`.

---

### Task 6: `observability.md` — the telemetry planes themselves

**Files:**
- Create: `infra/runbooks/observability.md`
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-alloy-dark-nas`, `-ops`, `-capture-primary`, `-capture-secondary`; `zcrypto-capture-log-dead-primary`, `-secondary`; `zcrypto-logship-lines-dropped`, `zcrypto-logship-worker-stalled`; `zcrypto-ops-log-pipeline-dead`, `zcrypto-ops-poller-log-dead`, `zcrypto-ops-unit-parse-dead`, `zcrypto-ops-journal-transport-dead`; `zcrypto-node-collector-failed`; `zcrypto-hcio-watchdog`), `infra/runbooks/README.md`
- Draft inputs: `drafts/alerts-capture-logship-alloy.md` (E, I, J, K), `drafts/alerts-ops-reconcile.md` (the four ops log-plane rules), `drafts/alerts-gate-engine-nas.md` (hcio-watchdog)

Same five steps. Sections (14 uids, 7 sections): `alloy-dark` (four tags; restart + verify recipe from `.claude/skills/zcrypto-bump-alloy/SKILL.md` Step 3; **scoped** `docker inspect` fields only; names the undetected alive-but-discovery-wedged state, [[T0048]]); `capture-log-plane-dead` (two tags; distinguish daemon-down via hc.io from not-shipping — `env_file: required: false` starts the daemon without `--ship-logs`); `logship-direct-ship` (two tags; ring overflow 4096 or a non-429 4xx; `last_cycle` stalls only on retry, a rejected push still cycles green — read with lines-dropped); `ops-log-plane` (four tags; the ops `config.alloy` journald stream, the liquidations container's direct ship, the parse stage; `journal-transport-dead`'s "hourly" becomes half-hourly); `zcrypto-node-collector-failed` (query for the `collector` label the page lacks; a 0 collector silently disarms the disk/textfile/load rules); `zcrypto-hcio-watchdog` (value N = a check down — **the dead-man map table** lives here: every healthchecks check → owning section: `zcrypto-capture`/`zcrypto-capture-red` → `capture-log-plane-dead` + hc.io; `zcrypto-engine-shadow` → `engine.md#zcrypto-engine-cycle-stale`; `gate-verify` → `gate.md#zcrypto-gate-exporter-stale`; `nas` → `nas.md#zcrypto-nas-archive-pull-stalled`; the five ops checks → their `ops-node.md` sections; `zcrypto-grafana-watchdog` → this section; 999 = the ops Alloy's hc.io scrape is dark). Read the actual check names from the ops `config.alloy` scrape and archived [[T0083]] — never invent one. Commit: `docs(runbooks): observability.md -- the telemetry planes get their procedures, and the dead-men their map`.

---

### Task 7: `capture-daemon.md` — the daemon's own guards

**Files:**
- Create: `infra/runbooks/capture-daemon.md`
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-capture-book-desync-stuck`, `zcrypto-capture-resubscribe-rate`, `zcrypto-capture-resubscribe-failing`, `zcrypto-capture-watermark-breached`, `zcrypto-capture-error-logs`), `infra/runbooks/README.md`
- Draft input: `drafts/alerts-capture-logship-alloy.md` (F, G, H)

Same five steps, plus one expression change. `book-desync-stuck`'s comment and summary describe a single fire-and-forget resubscribe; the daemon runs spec `00072`'s ladder (20 s grace, 5/10/20 s retries, one `force_reconnect`, 3600 s cooldown — verify the constants in `cli/capture/`), so 15 min stuck is post-ladder; rewrite both. `resubscribe` (two tags): **change the expression** of `zcrypto-capture-resubscribe-failing` from a bare `sum(...)` to `sum by (host) (...)` so its summary's "named host" is true; the runbook says read both hosts if the label is ever absent. `watermark-breached`: free space from image layers and journal first, never hand-delete in the spool; self-clears within 30 s. `capture-error-logs`: map the known ERROR lines to their owning sections. Run `uv run pytest tests/test_infra_alert_rules.py -q` (the expression tests must still pass). Commit: `feat(obs): capture-daemon.md, and the resubscribe-failing rule names its host`.

---

### Task 8: `ops-node.md` and the two `ops.md` additions

**Files:**
- Create: `infra/runbooks/ops-node.md`
- Modify: `infra/runbooks/ops.md` (+`zcrypto-reconcile-exporter-stale`, +`zcrypto-reconcile-source-lag`), `infra/grafana/alerts.yaml` (those two, plus `zcrypto-reconcile-healable-gap-rate`'s missing link line, plus the nine ops-node rules: `zcrypto-ops-archive-pull-stalled`, `-exit-nonzero`, `zcrypto-ops-verified-replay-stale`, `-exit-nonzero`, `zcrypto-ops-panel-exit-nonzero`, `zcrypto-trade-backfill-stale`, `-exit-nonzero`, `zcrypto-ops-load-high`, `zcrypto-ops-error-logs`), `infra/runbooks/README.md`
- Draft input: `drafts/alerts-ops-reconcile.md`

Same five steps. `ops-node.md` H1: `# Ops node — its timers and units`; sections name the systemd units and timers from `infra/ansible/roles/ops/` by their real names and their stamp files under `/var/lib/zcrypto-ops/`; `trade-backfill`'s re-run is `rm <stamp>` + `systemctl start zcrypto-archive-pull.service`; `verified-replay`'s watermark refusal names the file; `panel-exit-nonzero` states that no panel staleness rule exists (a deliberate gap — the drill program's O measures whether the dead-man alone catches it). `ops-load-high`'s comment counts the timers correctly. The two reconcile sections join `ops.md` (→ 11 sections). Commit: `docs(runbooks): ops-node.md and the reconcile exporter's two rules get their procedures`.

---

### Task 9: `engine.md` — the four engine rules

**Files:**
- Modify: `infra/runbooks/engine.md` (+`zcrypto-engine-cycle-stale`, `zcrypto-engine-cycle-failed`, `zcrypto-engine-error-logs`, `zcrypto-engine-log-dead`), `infra/grafana/alerts.yaml`, `infra/runbooks/README.md`
- Draft input: `drafts/alerts-gate-engine-nas.md` (engine section)

Same five steps. `cycle-stale`: rule out Alloy-dark first; scoped inspect; journal artifacts; a restart **only inside the inter-cycle gap** and stop-after-a-boundary per the existing `engine-data-socket-idle` section. `cycle-failed`: the sidecar's reasons; re-run only via `cycle --at --replace`, which cannot make the day clean. `error-logs`: classify by message; if an execution-path error while armed, `exec-status` then disarm per the arm/disarm procedure. `log-dead`: separate a missed-cycle echo from log-plane death via cycle age + logship gauges. **Then the acceptance check of Tasks 3–9**:

Run: `uv run pytest tests/test_infra_alert_rules.py -v 2>&1 | tail -4`
Expected: every test passes, the new one included — the unlinked set is empty. Diff the union of anchors added in Tasks 3–9 against `red-set.txt`: identical sets.

Then discharge D1's mutation-probe sentence: run `infra/scripts/mutate-probe.sh` with a mutation that deletes one summary's `Runbook:` line (`--collect-only` first, to prove the probe actually collects the guard — a `-k` filter that deselects it proves nothing), confirm the tightened test names that uid, and restore.

Commit: `docs(runbooks): engine.md -- the four engine rules get their procedures; every rule now links`.

---

### Task 10: `grafana_auth.py` — the vault resolver both scripts share

**Files:**
- Create: `infra/scripts/grafana_auth.py`, `tests/test_grafana_auth.py`
- Modify: `infra/scripts/grafana-query.py` (import the sibling instead of defining the resolver), `tests/test_grafana_query.py` (all four vault-resolver tests move)

**Interfaces:**
- Produces: `ANSIBLE_DIR`, `GRAFANA_URL`, `vault_password_file() -> Path`, `vault_password() -> bytes`, `vault_var(name: str, vault_file: str = "group_vars/all/vault.yml") -> str`. Tasks 11–14 import these; Task 13 reads `healthchecks_readonly_api_key` from the default file, and `00105`'s J′ reads `engine_healthcheck_url` with `vault_file="group_vars/engine_host/vault.yml"`.

- [ ] **Step 1: Write the failing test**

`tests/test_grafana_auth.py` — **all four** vault-resolver tests move here (`tests/test_grafana_query.py` lines 26, 36, 55, 84: the password-file, the EXECUTE-not-read, the context-initialized-first, and the second-credential one), patching the `grafana_auth` module directly — patching `gq.*` could not reach the sibling's own globals, and the last two also touch `_CONTEXT_READY`, which no re-export can carry. Below are the first two plus the new parameter; move the context pair unchanged except for the module name:

```python
"""infra/scripts/ is not a package, so the module loads by path."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra/scripts/grafana_auth.py"
_spec = importlib.util.spec_from_file_location("grafana_auth", _SCRIPT)
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)


def test_the_vault_password_file_comes_from_ansible_cfg_not_a_hardcoded_path():
    path = ga.vault_password_file()
    assert path.is_relative_to(ga.ANSIBLE_DIR)
    assert path.name == "vault-pass.sh"


def test_the_password_helper_is_EXECUTED_never_read(monkeypatch):
    """Reading its bytes yields shell source, and the failure reads as a wrong key."""
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout=b"secret\n")

    monkeypatch.setattr(ga.subprocess, "run", fake_run)
    assert ga.vault_password() == b"secret"
    assert seen["argv"] == [str(ga.vault_password_file())]


def test_vault_var_reads_the_file_it_is_given(monkeypatch):
    """The engine's healthcheck URL and the healthchecks admin key live in per-group vault files,
    not `all/`; a resolver fixed to one file cannot reach them."""
    seen = {}

    class _Loader:
        def set_vault_secrets(self, secrets): pass

        def load_from_file(self, path):
            seen["path"] = path
            return {"engine_healthcheck_url": "https://example.invalid/abc"}

    monkeypatch.setattr(ga, "vault_password", lambda: b"pw")
    monkeypatch.setattr(ga, "_load_ansible_vault", lambda: (_Loader(), object()))
    got = ga.vault_var("engine_healthcheck_url", vault_file="group_vars/engine_host/vault.yml")
    assert got == "https://example.invalid/abc"
    assert seen["path"].endswith("group_vars/engine_host/vault.yml")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_grafana_auth.py -v 2>&1 | tail -5`
Expected: collection error — `grafana_auth.py` does not exist.

- [ ] **Step 3: Create the module**

Move `ANSIBLE_DIR`, `GRAFANA_URL`, `vault_password_file`, `vault_password`, `_CONTEXT_READY` and `vault_var` out of `grafana-query.py` verbatim, with two changes: `vault_var` gains `vault_file: str = "group_vars/all/vault.yml"` and uses it in the final `load_from_file`; the ansible imports and context init move into a `_load_ansible_vault()` helper returning `(loader, secrets)` so the test can substitute it. The module docstring carries the two decrypt footguns verbatim from `grafana-query.py`'s — they are the reason the module exists — and nothing else.

- [ ] **Step 4: Rewire `grafana-query.py`**

Delete the moved definitions; load the sibling by path (its directory is not on `sys.path` under pytest) and re-export what its own tests use:

```python
_AUTH = Path(__file__).resolve().parent / "grafana_auth.py"
_auth_spec = importlib.util.spec_from_file_location("grafana_auth", _AUTH)
grafana_auth = importlib.util.module_from_spec(_auth_spec)
_auth_spec.loader.exec_module(grafana_auth)

ANSIBLE_DIR = grafana_auth.ANSIBLE_DIR
GRAFANA_URL = grafana_auth.GRAFANA_URL
vault_password_file = grafana_auth.vault_password_file
vault_password = grafana_auth.vault_password
vault_var = grafana_auth.vault_var
```

Trim the moved footgun paragraphs from `grafana-query.py`'s docstring, leaving its own subject (PromQL, the alert-state caveat). In `tests/test_grafana_query.py`, delete the **four** vault-resolver tests that moved and keep the query/render/token/usage tests, which patch `gq.query` and `gq.vault_var` — both still resolvable through the re-exports (`query` is this script's own function, untouched by the move).

- [ ] **Step 5: Both suites green**

Run: `uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py -v 2>&1 | tail -4`
Expected: all pass, and `grep -c '^def test_' tests/test_grafana_auth.py` is 5 (four moved plus the new parameter test). Then prove the caller still works end to end — this reads the vault, so it is the real check that the move did not break resolution. **Run it in the main loop, never inside a subagent**: the vault helper can prompt, and a prompt inside a dispatched task dies unseen.
Run: `uv run python infra/scripts/grafana-query.py 'vector(1)' 2>&1 | tail -2`
Expected: the expression echoed and a value printed, not a traceback.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/grafana_auth.py infra/scripts/grafana-query.py tests/test_grafana_auth.py tests/test_grafana_query.py
git commit -m "refactor(infra): the vault resolver moves to a sibling both Grafana scripts import"
```

---

### Task 11: `ops-daily.py` — the alerts read

**Files:**
- Create: `infra/scripts/ops_daily.py` (the module), `infra/scripts/ops-daily.py` (the CLI entry, loading the module by path — the hyphen makes it unimportable), `tests/test_ops_daily.py`
- Test fixtures: inline dicts in the test file; no network.

**Interfaces:**
- Produces: `read_alerts(token, *, now, window, opener) -> AlertsRead` with `AlertsRead(firing_now: list[Alert], fired_in_window: list[Alert], unreadable: str | None)`; `Alert(uid, title, state, active_at, runbook)`. Tasks 12–14 consume `unreadable` for the exit code and the lists for the report.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_rules_read_pairs_every_firing_instance_with_its_runbook_link():
    payload = {"data": {"groups": [{"name": "zcrypto-capture", "rules": [
        {"name": "Capture · stream silent", "uid": "zcrypto-capture-stream-silent", "state": "firing",
         "labels": {"severity": "critical"},
         "annotations": {"summary": "one stream stopped. Runbook: infra/runbooks/capture.md#zcrypto-capture-stream-silent"},
         "alerts": [{"activeAt": "2026-08-29T10:00:00Z", "state": "Alerting"}]},
        {"name": "Capture · venue not online", "uid": "zcrypto-capture-venue-not-online",
         "state": "inactive", "labels": {"severity": "warning"}, "annotations": {}, "alerts": []},
    ]}]}}
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload))
    assert [a.uid for a in read.firing_now] == ["zcrypto-capture-stream-silent"]
    assert read.firing_now[0].runbook == "infra/runbooks/capture.md#zcrypto-capture-stream-silent"
    assert read.unreadable is None


def test_a_history_chunk_at_the_page_limit_is_a_finding_not_a_silent_truncation():
    """The API caps a page; a chunk that comes back exactly at the limit may have dropped
    transitions, and a report that shows the survivors reads as a quiet day."""
    payload = {"data": {"values": [[1, 2], ["Alerting", "Normal"]]}}
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY,
                                 opener=_canned(payload, history_len=ops_daily.HISTORY_PAGE_LIMIT))
    assert read.unreadable and "page limit" in read.unreadable


def test_a_rule_without_a_uid_is_a_finding_never_a_silently_dropped_rule():
    """The uid is how a fired alert reaches its runbook; a shape change that drops it must not
    read as a quiet fleet."""
    payload = {"data": {"groups": [{"name": "g", "rules": [
        {"name": "no uid here", "state": "firing", "labels": {}, "annotations": {}, "alerts": []}]}]}}
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_canned(payload))
    assert read.unreadable and "uid" in read.unreadable


def test_an_unreachable_grafana_is_reported_never_read_as_nothing_firing():
    read = ops_daily.read_alerts("tok", now=NOW, window=DAY, opener=_raises(urllib.error.URLError("down")))
    assert read.firing_now == [] and read.fired_in_window == []
    assert read.unreadable and "down" in read.unreadable
```

- [ ] **Step 2: Run them; watch them fail**

Run: `uv run pytest tests/test_ops_daily.py -v 2>&1 | tail -5` — module missing.

- [ ] **Step 3: Implement**

`read_alerts` calls `GET {GRAFANA_URL}/api/prometheus/grafana/api/v1/rules` for current state (the uid is the rule object's **top-level `uid`** field, and a rule without one sets `unreadable` rather than yielding a silently empty list — **measured 2026-08-29** against the live API: a rule object's keys are `alerts, annotations, duration, evaluationTime, folderUid, health, isPaused, labels, lastEvaluation, name, notificationSettings, provenance, queriedDatasourceUIDs, query, state, totals, totalsFiltered, type, uid`, its `labels` carry only `severity`, and **no `__`-prefixed label exists**; the runbook link is parsed from the summary with the same regex the alert test uses, `infra/runbooks/([\w.-]+\.md)#([\w-]+)`), then `GET {GRAFANA_URL}/api/v1/rules/history?from=&to=&limit=` in chunks no wider than `HISTORY_CHUNK = timedelta(hours=6)`, each chunk's returned row count compared against `HISTORY_PAGE_LIMIT`; a chunk at the limit sets `unreadable`. Every request carries `Authorization: Bearer <token>` and a 30 s timeout. Any `URLError`/`HTTPError`/`KeyError` sets `unreadable` with the reason and returns empty lists — never a partial list presented as complete.

- [ ] **Step 4: Green**

Run: `uv run pytest tests/test_ops_daily.py -v 2>&1 | tail -3` — the three pass.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/ops_daily.py infra/scripts/ops-daily.py tests/test_ops_daily.py
git commit -m "feat(infra): the daily pass reads alert state and its 24 h history"
```

---

### Task 12: `ops-daily.py` — the Loki read

**Files:** Modify `infra/scripts/ops_daily.py`, `tests/test_ops_daily.py`

**Interfaces:**
- Produces: `read_logs(token, *, window, opener) -> LogsRead` with `LogsRead(counts: list[LogCount], top: list[LogLine], unreadable: str | None)`; `LOKI_DS_UID_DEFAULT = "grafanacloud-logs"` overridable by `GRAFANA_LOKI_DS_UID`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_loki_uid_defaults_to_the_named_datasource_and_is_overridable(monkeypatch):
    """A lookup BY TYPE is the T0034 defect: a Cloud stack ships several Loki datasources and
    'the first of each type' silently repointed every rule once."""
    assert ops_daily.loki_ds_uid() == "grafanacloud-logs"
    monkeypatch.setenv("GRAFANA_LOKI_DS_UID", "other-loki")
    assert ops_daily.loki_ds_uid() == "other-loki"


def test_the_log_counts_come_back_by_host_container_and_level():
    payload = {"data": {"result": [
        {"metric": {"host": "zcrypto", "container": "capture", "level": "ERROR"}, "value": [1, "3"]},
        {"metric": {"host": "ops", "container": "alloy", "level": "WARNING"}, "value": [1, "11"]},
    ]}}
    read = ops_daily.read_logs("tok", window=DAY, opener=_canned(payload))
    assert (read.counts[0].host, read.counts[0].level, read.counts[0].count) == ("zcrypto", "ERROR", 3)
    assert read.unreadable is None


def test_an_unreachable_loki_is_reported_never_read_as_no_errors():
    read = ops_daily.read_logs("tok", window=DAY, opener=_raises(urllib.error.HTTPError(
        "u", 502, "bad gateway", {}, None)))
    assert read.counts == [] and read.unreadable and "502" in read.unreadable
```

- [ ] **Step 2–4: red → implement → green**

`read_logs` queries the datasource proxy's `.../api/v1/query` with a Loki instant query over the window: `sum by (host, container, level) (count_over_time({host=~".+", level=~"WARNING|ERROR|CRITICAL"}[<window>]))`, then `topk(10, ...)` with the same selector plus `| json message="message"` for the top lines — the four log rules' own selector shape. `(no series)` is an empty list, never an error; unreachable sets `unreadable`.

- [ ] **Step 5: Commit** — `git commit -m "feat(infra): the daily pass reads the log planes"`

---

### Task 13: `ops-daily.py` — the dead-men, both ways; the fleet verdict; the window's deploys

**Files:** Modify `infra/scripts/ops_daily.py`, `tests/test_ops_daily.py`

**Interfaces:**
- Produces: `read_deadmen(token, *, opener) -> DeadmenRead(via_prometheus, via_healthchecks, unreadable)`; `read_verdict(token, *, opener) -> list[Check]` with `Check(name, expr, ok, value)`; `read_deploys(window, *, now) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_deadmen_are_read_both_through_grafana_and_directly():
    """The direct read is the domain's whole point: it must answer while Grafana is dark."""
    read = ops_daily.read_deadmen("tok", opener=_two_sources(prom_down=0, direct=[
        {"name": "zcrypto-engine-shadow", "status": "up"}]))
    assert read.via_prometheus == 0
    assert [c["name"] for c in read.via_healthchecks] == ["zcrypto-engine-shadow"]


def test_a_missing_readonly_key_is_named_never_silently_skipped(monkeypatch):
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: None)
    read = ops_daily.read_deadmen("tok", opener=_canned({"data": {"result": []}}))
    assert read.unreadable and "healthchecks_readonly_api_key" in read.unreadable


def test_no_series_is_a_verdict_failure_never_a_pass():
    """`ops-postverify.sh`'s rule, carried into the fleet checks: an empty query is not a zero."""
    checks = ops_daily.read_verdict("tok", opener=_canned({"data": {"result": []}}))
    assert checks and all(not c.ok for c in checks)
    assert all(c.value == "(no series)" for c in checks)


def test_the_deploy_window_holds_only_lines_inside_it():
    lines = ops_daily.read_deploys(DAY, now=NOW)
    assert all(_parse(line["ts"]) >= NOW - DAY for line in lines)
```

- [ ] **Step 2–4: red → implement → green**

`read_deadmen`: `max(hc_checks_down_total) or on() vector(999)` through Prometheus, **and** `GET https://healthchecks.io/api/v3/checks/` with `X-Api-Key: <healthchecks_readonly_api_key>` from `grafana_auth.vault_var`. A missing key sets `unreadable` naming the variable — the exit-2 path, never a silent skip. `read_verdict`: the presence-and-freshness PromQL set, each with its own bound, `(no series)` a FAIL. `read_deploys`: `docs/reference/deploy-log.jsonl`, lines whose `ts` falls in the window.

- [ ] **Step 5: Commit** — `git commit -m "feat(infra): the daily pass reads the dead-men twice over, the fleet verdict, and the window's deploys"`

---

### Task 14: `ops-daily.py` — the report, the exit codes, the CLI

**Files:** Modify `infra/scripts/ops_daily.py`, `infra/scripts/ops-daily.py`, `tests/test_ops_daily.py`

**Interfaces:**
- Produces: `build_report(...) -> Report`, `Report.markdown()`, `Report.journal_paragraph()`, `Report.exit_code`; CLI `ops-daily.py report [--since 24h] [--journal-entry]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_all_clear_report_exits_zero():
    r = ops_daily.build_report(alerts=_empty_alerts(), logs=_empty_logs(),
                               deadmen=_deadmen_ok(), verdict=_all_pass(), deploys=[], now=NOW)
    assert r.exit_code == 0 and r.verdict_word == "all-clear"


def test_anything_fired_or_failed_exits_one():
    r = ops_daily.build_report(alerts=_alerts_with_one_firing(), logs=_empty_logs(),
                               deadmen=_deadmen_ok(), verdict=_all_pass(), deploys=[], now=NOW)
    assert r.exit_code == 1 and r.verdict_word == "attention"


def test_a_source_the_instrument_could_not_read_exits_two_and_names_it():
    """A source it cannot reach is a finding ABOUT that source, never a silent gap."""
    r = ops_daily.build_report(alerts=_alerts_unreadable("rules API 502"), logs=_empty_logs(),
                               deadmen=_deadmen_ok(), verdict=_all_pass(), deploys=[], now=NOW)
    assert r.exit_code == 2
    assert "rules API 502" in r.markdown()


def test_the_journal_paragraph_carries_every_labelled_clause():
    r = ops_daily.build_report(alerts=_empty_alerts(), logs=_empty_logs(),
                               deadmen=_deadmen_ok(), verdict=_all_pass(), deploys=[], now=NOW)
    para = r.journal_paragraph()
    for clause in ("window", "alerts", "checks", "logs", "dead-men", "deploys", "actions", "follow-ups"):
        assert clause in para
```

- [ ] **Step 2–4: red → implement → green**

Exit precedence: 2 (any `unreadable`) > 1 (anything fired, failed, or errored) > 0. `markdown()` renders the five reads plus the deploy window; `journal_paragraph()` renders the labelled clauses Task 15's shape test expects. The CLI parses `--since` (`24h`/`6h`/`7d`), resolves the token via `grafana_auth.vault_var("grafana_sa_token")`, and prints. A live smoke test gated on `ZCRYPTO_LIVE_GRAFANA=1` asserts only that the run exits 0/1/2 and names every source — never a value, which drifts.

- [ ] **Step 5: Commit** — `git commit -m "feat(infra): the daily pass reports, and its exit code says which source it could not read"`

---

### Task 15: the operations journal and its shape test

**Files:**
- Create: `docs/reference/ops-journal/README.md`, `tests/test_ops_journal.py`
- Modify: `.claude/rules/` — none here (Task 16 owns the rule edits)

**Interfaces:**
- Produces: the file convention `docs/reference/ops-journal/<YYYY-MM>.md`; entries `## <YYYY-MM-DD> — <all-clear | attention | incident>` followed by one paragraph. Task 16's skill appends them.

- [ ] **Step 1: Write the failing test**

```python
"""The journal is greppable, not a schema: two rules, and nothing about the prose."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

JOURNAL = Path(__file__).resolve().parents[1] / "docs/reference/ops-journal"
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — (all-clear|attention|incident)$")


def _entries(path: Path) -> list[tuple[str, str]]:
    return [m.groups() for line in path.read_text().splitlines() if (m := _HEADING.match(line))]


def test_every_entry_heading_is_a_date_with_one_of_the_three_verdicts():
    """A heading the pass cannot parse is an entry nobody can count -- 'how many all-clear days'
    is the one question the journal exists to answer."""
    for path in sorted(JOURNAL.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].md")):
        for line in path.read_text().splitlines():
            if line.startswith("## "):
                assert _HEADING.match(line), f"{path.name}: unparseable heading {line!r}"


def test_dates_increase_within_a_file_and_match_its_name():
    for path in sorted(JOURNAL.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].md")):
        dates = [date.fromisoformat(d) for d, _ in _entries(path)]
        assert dates == sorted(dates), f"{path.name}: entries out of order"
        assert len(dates) == len(set(dates)), f"{path.name}: a day appears twice"
        assert all(f"{d:%Y-%m}" == path.stem for d in dates), f"{path.name}: an entry from another month"
```

- [ ] **Step 2: Run it — it passes vacuously, so make it bite**

Run: `uv run pytest tests/test_ops_journal.py -v 2>&1 | tail -3` — passes on an empty directory.
Then prove it bites: write `docs/reference/ops-journal/2026-08.md` with a heading `## 2026-08-29 — fine`, re-run, see the first test fail naming it; write two out-of-order dates, see the second fail; delete both. **A guard that has never been seen red is not a guard** (`agent-ops.md`).

- [ ] **Step 3: Write the directory's README**

`docs/reference/ops-journal/README.md`: what the journal is (one entry per daily pass, the verdict in the heading), the entry shape with a worked example, the branch convention (`ops-journal`, cut from `develop`, committed daily, PR'd and merged at month rotation), and what it is not (not a backlog — work goes to the memo queue or a topic). One paragraph each.

- [ ] **Step 4: Commit**

```bash
git add docs/reference/ops-journal/README.md tests/test_ops_journal.py
git commit -m "feat(ops): the operations journal, one entry per pass, shape-tested"
```

---

### Task 15b: the tier classifier — the host comes from the alert, not from the step

**Files:** Modify `infra/scripts/ops_daily.py`, `infra/scripts/ops-daily.py`, `tests/test_ops_daily.py`

**Interfaces:**
- Produces: `Tier(Enum)` with `AUTONOMOUS` / `PREPARED`; `classify_action(text: str, *, host: str | None = None) -> Tier`; and the CLI subcommand `ops-daily.py classify --host <host> "<text>"`, printing the tier and exiting 0 for `AUTONOMOUS`, 3 for `PREPARED`.
- **The host is a separate argument because a runbook step does not carry one.** `infra/runbooks/observability.md`'s alloy-dark section serves four uids — `zcrypto-alloy-dark-nas`, `-ops`, `-capture-primary`, `-capture-secondary` — with one body: *"Restart it — safe, and the usual fix: `sudo docker restart grafana-alloy`."* The same sentence is routine on ops and **attended on the capture pair**. A classifier reading only the text must therefore either allow it everywhere or forbid it everywhere; the host arrives from the fired alert's labels, and the pass must pass it in.
- **Its production caller is the skill** (Task 16 step 3), via the subcommand — `infra/scripts/` is not a package, so an import line in a skill would be the one part nobody verifies.

**The precedence, in order:**

1. A **mutating** action naming a **protected** object → `PREPARED`. ("Stop the daemon, then read its logs" does not become autonomous because it also reads.)
2. Otherwise a purely **read-only** action → `AUTONOMOUS`, whatever it names and wherever it runs. Most capture and engine diagnostics are read-only steps that name the protected object; preparing those would halt the pass at step 1 of every incident it exists for.
3. Otherwise a mutating action on a **telemetry object** with `host` in `{ops, nas, zaccess}` → `AUTONOMOUS`.
4. Otherwise → **`PREPARED`** — including a mutating telemetry action with **no host given or a capture host**: not knowing where an action lands is not permission to run it. A change making this default permissive is wrong however reasonable it looks.

- [ ] **Step 1: Write the failing tests**

The pair is **one string, two hosts** — the only minimal pair available, and the one that encodes the hazard:

```python
# infra/runbooks/observability.md, the alloy-dark section (serving ops, the NAS and BOTH capture hosts).
_ALLOY_RESTART = "Restart it — safe, and the usual fix: `sudo docker restart grafana-alloy`."


@pytest.mark.parametrize("host,expected", [
    ("ops", ops_daily.Tier.AUTONOMOUS),
    ("nas", ops_daily.Tier.AUTONOMOUS),
    ("zcrypto", ops_daily.Tier.PREPARED),          # the primary: attended, via zcrypto-bump-alloy
    ("zcrypto-red", ops_daily.Tier.PREPARED),      # the secondary: likewise
    (None, ops_daily.Tier.PREPARED),               # host unknown => not permission to run it
])
def test_the_same_step_is_routine_on_ops_and_attended_on_the_capture_pair(host, expected):
    # Identical text; only the host differs. The alloy-dark section really does serve all four
    # hosts with one body, so a classifier that reads the text alone must get one of these wrong.
    assert ops_daily.classify_action(_ALLOY_RESTART, host=host) is expected


@pytest.mark.parametrize("text", [
    "Read the ladder in the log: `sudo docker logs zcrypto-capture 2>&1 | grep -E \"checksum desync\"`.",
    "`uv run python infra/scripts/grafana-query.py 'zcrypto_capture_book_desynced'`",
    "`sudo docker inspect --format '{{.RestartCount}}' zcrypto-capture`",
    "`sudo journalctl -u zcrypto-capture --since -1h`",
    "Read the engine's gate: `sudo docker exec zcrypto-engine zcrypto engine exec-status`.",
])
def test_a_read_only_step_is_autonomous_on_any_host_even_naming_a_protected_object(text):
    """Five different read verbs, because a suite that only ever exercises two lets a classifier
    keyed on those two pass while preparing every `logs`, `grep` or `journalctl` step -- which is
    the halt-at-step-1 failure this precedence exists to prevent."""
    assert ops_daily.classify_action(text, host="zcrypto") is ops_daily.Tier.AUTONOMOUS


@pytest.mark.parametrize("text", [
    "On the named host: `sudo systemctl restart zcrypto-capture`.",
    "Stop the daemon, then read its logs: `sudo systemctl stop zcrypto-capture`, then `docker logs`.",
    "Restart the engine: `sudo systemctl restart zcrypto-engine`.",
    "Clear the kill file: `sudo rm /var/lib/zcrypto-engine/exec/kill`.",
    "Push the rules: `bash infra/scripts/grafana-push.sh`.",
    "Converge the secondary: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red`.",
])
def test_a_mutating_step_on_a_protected_object_is_prepared_on_any_host(text):
    assert ops_daily.classify_action(text, host="ops") is ops_daily.Tier.PREPARED


def test_an_unrecognised_action_is_prepared_never_autonomous():
    assert ops_daily.classify_action("Frobnicate the widget.", host="ops") is ops_daily.Tier.PREPARED


def test_the_classify_subcommand_is_what_the_skill_calls(capsys):
    """The skill branches on this exit code; an incantation nobody runs is how it silently rots."""
    assert ops_daily.main(["classify", "--host", "ops", _ALLOY_RESTART]) == 0
    assert ops_daily.main(["classify", "--host", "zcrypto", _ALLOY_RESTART]) == 3
    assert "prepared" in capsys.readouterr().out
```

- [ ] **Step 2: red** — `Tier`, `classify_action` and the subcommand do not exist.

- [ ] **Step 3: Implement the four rules**

Four named token sets, each with its reason in one clause: `_READ_ONLY_VERBS` (logs, grep, journalctl, inspect, cat, status, exec-status, query, grafana-query, show, ls), `_MUTATING_VERBS` (stop, start, restart, rm, delete, prune, touch, push, converge, arm, submit, kill), `_PROTECTED_OBJECTS` (`zcrypto-capture`, `zcrypto-engine`, the exec control files, `converge.sh`, `site.yml`, `grafana-push.sh`, an image re-pin) and `_TELEMETRY_OBJECTS` (`grafana-alloy`, `alloy`, a `.timer`, a textfile exporter). Host matching is **exact against `{ops, nas, zaccess}`**, never a substring — `zcrypto` is a prefix of `zcrypto-ops` and a substring test would hand every ops unit to rule 3. A step is read-only when it contains a read-only verb and **no** mutating verb. The docstring records that rule 4 is the safety property.

- [ ] **Step 4: green, then prove the pair bites**

Run the suite. Then delete the host condition from rule 3 — the single change the previous draft's fixture would have forced — and confirm the `zcrypto` and `zcrypto-red` cases fail. That is the Critical this task exists to pin.

- [ ] **Step 5: Run the command the skill will run**

```bash
uv run python infra/scripts/ops-daily.py classify --host ops "Restart it: sudo docker restart grafana-alloy"; echo "exit=$?"
uv run python infra/scripts/ops-daily.py classify --host zcrypto "Restart it: sudo docker restart grafana-alloy"; echo "exit=$?"
```
Expected: `autonomous` / `exit=0`, then `prepared` / `exit=3`. Task 16's skill text quotes this command; running it here, **before** the skill is written, is what keeps the skill's first instruction from being one nobody has executed.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/ops_daily.py infra/scripts/ops-daily.py tests/test_ops_daily.py
git commit -m "feat(infra): the tier turns on what an action does, what it touches, and where it lands"
```

---

### Task 16: the `/zcrypto-daily-ops` skill and the five permitted `.claude/*` edits

**Files:**
- Create: `.claude/skills/zcrypto-daily-ops/SKILL.md`
- Modify: `.claude/rules/branch-workflow.md`, `.claude/rules/commit-messages.md`, `.claude/rules/fleet-deploys.md`, `.claude/rules/agent-ops.md`

**Interfaces:**
- Consumes: `ops-daily.py` (Task 14), the journal convention (Task 15), the runbook sections (Tasks 3–9).
- Produces: the procedure the first real pass runs.

- [ ] **Step 1: Write the skill**

Frontmatter `name: zcrypto-daily-ops`, a description naming when it runs (the daily proactive pass) and `disable-model-invocation: false`. Body, in the repo's skill voice — imperative, no narration:

1. **Read** — `uv run python infra/scripts/ops-daily.py report --since 24h`. Exit 2 means a source could not be read: that is the first finding, and the report names it.
2. **The incident loop, per alert that fired** — open its runbook section (every rule has one), follow *What you are seeing* → *What it means* → run *What to do*, and classify: **expected** (a deploy in the window explains it — the report lists them), **transient** (self-resolved, cause identified), **needs a fix**, **needs a human**.
3. **Classify before acting, then remediate within two tiers.** Before running any runbook *What to do* step, classify it — `uv run python infra/scripts/ops-daily.py classify --host <the fired alert's host label> "<the step's text>"` — and read the exit code: 0 autonomous, 3 prepared. **The host comes from the alert, never from the step**: one runbook body serves all four Alloy hosts, and the same restart is routine on ops and attended on the capture pair. **`PREPARED` means prepare the action and stop.** If the command itself errors, treat that as `PREPARED` too: an unclassifiable step and an unrunnable classifier both mean nobody has judged this action. *Autonomous*: read-only anything; telemetry-only runbook steps **on ops, the NAS or zaccess only** — restart Alloy, clear a stale cache, re-arm a timer (the capture pair's Alloy goes through `zcrypto-bump-alloy`, attended); a code fix the normal way — fix branch, tests, subagent review, PR, merged on CI green **when the fix is off the protected paths**. *Prepared, then the user's word*: any restart or converge of a capture daemon or the engine; anything touching the venue account (arm file, kill file, orders); deleting data; a fix landing on the capture write path, the live trade path, canonical data, or anything a host converges; running `grafana-push.sh` after a merged rule fix. Deploying any fix to a host is a converge — always attended. **Every ssh/sudo step runs in the main loop, never in a dispatched subagent** — the permission gate blocks it there and the step dies where nobody sees the prompt.
4. **Read the dashboards numerically** — the verdict tiles' own PromQL, through the report; no pixels.
5. **Evaluate the due SCHEDULED REMINDER sections** (`refdata-sweep-due`, `healable-threshold-rederivation-due`).
6. **Append the journal entry** on the `ops-journal` branch, commit; at a month change, open the finished month's PR and merge it on CI green, then re-cut the branch from `develop`.
7. **Post the paragraph to `#zcrypto`**; if the Slack tool is unavailable, say so in the entry rather than dropping it.
8. **Re-arm tomorrow's reminder** — a scheduled message fires once (`refdata-sweep-due`'s pattern).

A closing table of failure modes in the repo's style: *the impulse* → *the reality* — "restart the capture daemon because the runbook says so" → the tier governs, prepare and stop; "an empty query means healthy" → `(no series)` is a FAIL; "no alerts fired, so nothing to write" → the all-clear entry is the product.

- [ ] **Step 2: The five rule edits, verbatim from spec `00104` D5/D7**

`branch-workflow.md`, in the PR-gate's standing-exception clause: the `ops-journal` branch (opened and merged by the pass at month rotation, no review) and the daily pass's fix PR (bounded to fixes off the capture write path, the live trade path, canonical data, and anything a host converges). `commit-messages.md`, in the review-exemption list: journal commits and the monthly journal PR. `fleet-deploys.md`, Invariants: **inducing a fault on live capture happens only inside an attended window** — one line, and nothing more (protected file; this edit is shown to the user before it lands). `agent-ops.md`: the activeAt-vs-own-changes clause on the attribution bullet, and the independent-producers clause beside the empty-query bullet.

- [ ] **Step 3: Prove the skill's help text and the rules stay clean**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_cli_help_hygiene.py -q 2>&1 | tail -2`
Expected: pass — no `WP<N>`, no `T<NNNN>` on an operator surface. (A docs diff reaches this guard; it is not a `cli/`-only test.)

- [ ] **Step 4: Commit — `claude` kind, on its own**

```bash
git add .claude/skills/zcrypto-daily-ops/SKILL.md .claude/rules/branch-workflow.md .claude/rules/commit-messages.md .claude/rules/fleet-deploys.md .claude/rules/agent-ops.md
git commit -m "claude(config): the daily-ops pass, and the four rules its conventions need"
```

---

### Task 17: the homings — T0049's principles onto operating surfaces

**Files:**
- Modify: `infra/runbooks/README.md`, `docs/reference/fleet.md`, `infra/runbooks/ops.md`

**Interfaces:**
- Consumes: the reader draft `drafts/principles-homes.md` (which principle, which home, and the one to drop).

- [ ] **Step 1: `infra/runbooks/README.md` — the section shape**

Add to the scope block: the four parts in fixed order (*What you are seeing* · *What it means* · *What to do* · *Retire when*) for ALERT, KNOWN LIMITATION and SCHEDULED REMINDER; a PROCEDURE carries those four or, for a drill, the seven parts spec `00105` D1 names. Name the four section kinds. And: **a drill's output is a runbook section, never a report** — the difference between a drill that produced a document and one that produced a procedure someone will find at 03:00.

- [ ] **Step 2: `docs/reference/fleet.md` — the drill recipes and the blind spot**

Two recipes and one caveat: fault injection in a **throwaway container from the same pinned digest** on the ops node (isolated data dir, no Loki creds, no dead-man URL) driven with `docker network disconnect/connect`; **alert-path injection** by writing a synthetic `.prom` into the node-exporter textfile dir, which fires a real rule through the real transport and resolves when the file is removed; and the caveat that an injected brand-new series fires in minutes where a real one takes the full window — **a drill proves wiring, never timing**. Plus the blind spot: a compose-level "container never created" failure writes no docker-path logs and the owning unit's journal is filtered on the capture hosts, so no Alloy pipeline sees it — the healthchecks dead-man is the only catcher.

- [ ] **Step 3: `infra/runbooks/ops.md` — the reconstruction steps**

Into the gap sections' *What to do*: bound the event by widening windows (`increase(<metric>[1h])`, `[6h]`, `[24h]`, `[7d]` — equal values at 6 h and 7 d mean one event, not a trend); read the ledger for **shape**, not just totals (per-pair and per-hour distinguish "every pair briefly" from "one pair for a long time"); when the system already healed it, the remaining work is **measurement** — confirm the mint and the archive, and do not react operationally on a healthy host. **Do not add** the healable-equals-healed step: archived T0101 recorded that verification as circular.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py -q 2>&1 | tail -2` — anchors still resolve, no internal tokens.

```bash
git add infra/runbooks/README.md docs/reference/fleet.md infra/runbooks/ops.md
git commit -m "docs(runbooks): the drill recipes, the section shape, and the reconstruction steps get their homes"
```

---

### Task 18: closeout

**Files:**
- Modify: `docs/iterations-history-phase6.md`, `docs/open-topics/T0157-day2-operations-runbooks-and-daily-pass.md`, `docs/open-topics/README.md`

- [ ] **Step 1: The changelog entry**

Append to `docs/iterations-history-phase6.md` a `## <date> — iter-<N>: …` section whose bullets carry what landed and what is non-obvious: the guard and the red set it named; the seven new subsystem files and the one move; the instrument's five reads and why the dead-men are read twice; the journal and its branch convention; the skill's two tiers; the homings and the one principle deliberately dropped. Recompute `<N>` from the file's last entry at closeout — never from memory.

- [ ] **Step 2: T0157 → `partial`, not resolved**

Flip the frontmatter to `partial`; add `## Done so far` naming what landed with its commits; trim `## Suggested next steps` to the remainder — **the first real pass**, which is the spec's own acceptance test, plus the read-only key mint if it was skipped — web-UI only, and registered as this topic's `(human)` step. Move its index bullet to `### Partially done`. Archiving before the pass has run would record a resolution nothing proved.

- [ ] **Step 3: The audit and the PR**

Run: `bash infra/scripts/review-trailer-audit.sh develop` — every code-kind commit carries `Reviewed-by`.
Then the PR per `open-pr`, and merge on CI green per `merge-pr`.

- [ ] **Step 4: Commit**

```bash
git add docs/iterations-history-phase6.md docs/open-topics/T0157-day2-operations-runbooks-and-daily-pass.md docs/open-topics/README.md
git commit -m "docs(research): iter-<N> closeout -- every alert has a runbook, and the fleet has a daily reader"
```

---

### Task 19: post-merge — the fleet, and the first real pass

**Runs in the MAIN LOOP after Task 18's PR is merged, never in a subagent** — each step touches a credentialed surface, and `grafana-push.sh` must not run from an unmerged branch.

- [ ] **Step 1: Push the rules from merged `develop`**

`grafana-push.sh`'s own header (lines 8–10) forbids pushing summaries that cite repo paths from a branch: a branch push ships summaries naming files `develop` does not have.

**Measured 2026-08-29, so the executor need not rediscover it**: the live stack carries **79** rules against the file's **83**. The four absent ones are spec `00103`'s hour-rotation detectors — `zcrypto-capture-clock-skew`, `-clock-exporter-stale`, `-hour-finalized-early`, `-ts-past-dated-hour` — whose metric families all read `(no series)` because the capture image carrying them has not rolled out ([[T0037]] is `partial` on exactly that rollout). Pushing them is **safe and expected**: all four carry `noDataState: OK`, so absence cannot page, and `fleet-deploys.md`'s spurious-no-data hazard does not apply here. The orphan report must come back empty; a non-empty one is a finding, never something to prune past.

- [ ] **Step 2: The changed expression, read by value**

`zcrypto-capture-resubscribe-failing` gained `by (host)`. Per `fleet-deploys.md`'s alert-rule lifecycle, read its first sample as a VALUE before judging anything else:

Run: `uv run python infra/scripts/grafana-query.py 'sum by (host) (increase(zcrypto_capture_resubscribes_failed_total[1d]))'`
Expected: a value per host — `(no series)` is a FAIL, not a zero.

- [ ] **Step 3: The ten check descriptions**

With the **admin** `healthchecks_api_key` (`group_vars/capture_host/vault.yml`), set each check's description to carry `Runbook: infra/runbooks/<file>#<anchor>` per the map in `observability.md#zcrypto-hcio-watchdog`, then read each back and assert the text landed. The key is a request header only — never argv, never a file, never a log line.

- [ ] **Step 4: The first real pass — the spec's acceptance test**

Cut `ops-journal` from `develop`; run the `/zcrypto-daily-ops` procedure end to end. The journal entry is committed on that branch; the summary is posted to `#zcrypto`, or, if no Slack tool is reachable, the paragraph goes into the handover with the gap named rather than dropped. Correct the skill from what day one shows, and **T0157 → resolved** (archive, index, `## Resolution`) rides that same fold-in PR — after the pass has run, never before.
