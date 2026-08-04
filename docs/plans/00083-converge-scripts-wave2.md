# T0111 Wave 2 — Converge Scripts & Gap Closures Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** land spec 00083's ten build items — five converge scripts, the engine canary-parity mirror, the window-floor journal probe, the skip-tags tightening, and the two rc/coverage closures plus mutate-probe hermeticity — each refusal proven against its constructed violation.

**Architecture:** bash scripts with stubbed-external pytest harnesses (fake `run.sh`/`systemctl`/`du`/`date`/`grafana-query` prepended on `PATH`, ptys for `/dev/tty` gates); Ansible guard changes tested through the wave-1 Templar substrate in `tests/test_infra_converge_guards.py` (real `that:`/`when:` from committed YAML, `trust_as_template`).

**Tech Stack:** bash, ansible-core 2.21.2, pytest, Python 3.14 stdlib (`pty`, `subprocess`).

## Global Constraints

- **Override convention (spec 00082 D1, verbatim fragment):** `(X | default('') | string | length > 8) and (X | default('') | string | lower not in ['true', 'false', '1', 'yes'])`; an ACCEPTED override echoes its reason into the play log via a debug task whose `when:` byte-mirrors the assert's negated first disjunct.
- **Templar tests MUST wrap expressions with `trust_as_template`** (ansible-core 2.21.2 Data-Tagging) — use the existing `truthy()` helper in `tests/test_infra_converge_guards.py`; a plain-str template is vacuously truthy.
- **ansible-lint `var-naming[no-role-prefix]`**: role-registered vars carry `capture_`/`engine_`/`ops_`/`docker_` prefixes; play-level `pre_tasks` registers are exempt.
- **Operator-facing output carries no internal serials** (`Phase N`, `T####`, `spec #####`, `iter-N`) — every new script's stdout/stderr and every fail_msg; serials go in adjacent comments. Add each new script to `tests/test_internal_terms_not_operator_visible.py`'s enforced surface list in the task that creates it.
- **Scratch git repos in tests set their own identity** (`git config user.email t@example.invalid` + `user.name t`) — CI runners have none.
- **PEP 758 is valid syntax** (unparenthesized multiple exception types without `as`) — never "fix" it.
- Test seams are env vars only where this plan names them (`ZCRYPTO_SOPS_BIN`, `ZCRYPTO_GRAFANA_QUERY`) — no other configurability.
- Gate before every commit: `uv run pre-commit run -a` clean; never `--no-verify`; commits end with the author's own model trailer.
- `/dev/tty` reads never fall back to stdin — a pipe must not be able to drive a confirm gate.

---

### Task 1: `converge.sh` — the documented converge path

**Files:**
- Create: `infra/ansible/scripts/converge.sh` (mode 0755)
- Test: `tests/test_converge_sh.py`

**Interfaces:**
- Consumes: `infra/ansible/scripts/run.sh` (sibling; loads vault keys, execs ansible-playbook).
- Produces: exit contract rc 2 usage / rc 3 confirm-abort-or-no-tty / rc 4 preview-failed / otherwise the real pass's own exit; Task 12 shrinks the rule lines against this contract.

- [ ] **Step 1: Write the failing tests**

```python
"""converge.sh: preview-first, typed-limit confirm, then the real pass (spec 00083 D1).

Every test copies the script into a scratch dir beside a FAKE run.sh that appends its argv
(one line per invocation) to invocations.log — the tests assert on what actually ran, never
only on exit codes.
"""

import os
import pty
import shutil
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "converge.sh"

FAKE_RUN_SH = """#!/usr/bin/env bash
echo "$@" >> "$(dirname "$0")/invocations.log"
exit ${FAKE_RUN_RC:-0}
"""


def make_harness(tmp_path):
    shutil.copy(SCRIPT, tmp_path / "converge.sh")
    (tmp_path / "run.sh").write_text(FAKE_RUN_SH)
    for name in ("converge.sh", "run.sh"):
        p = tmp_path / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return tmp_path / "converge.sh"


def invocations(tmp_path):
    log = tmp_path / "invocations.log"
    return log.read_text().splitlines() if log.exists() else []


def run_no_tty(script, args, env=None):
    return subprocess.run(
        ["setsid", str(script), *args], capture_output=True, text=True,
        stdin=subprocess.DEVNULL, env={**os.environ, **(env or {})},
    )


def run_with_tty(script, args, reply):
    """Run under a pty (the child's controlling terminal) and type `reply` at the confirm."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(str(script), [str(script), *args])
    out = b""
    try:
        while b"aborts:" not in out and b"converge," not in out:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
        os.write(fd, reply.encode() + b"\n")
        while True:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


def test_refuses_without_limit(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml"])
    assert r.returncode == 2
    assert "--limit" in r.stderr
    assert invocations(tmp_path) == []


def test_refuses_without_playbook(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, [])
    assert r.returncode == 2
    r2 = run_no_tty(script, ["--limit", "zcrypto-red"])
    assert r2.returncode == 2
    assert invocations(tmp_path) == []


def test_preview_failure_aborts(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red"], env={"FAKE_RUN_RC": "1"})
    assert r.returncode == 4
    assert len(invocations(tmp_path)) == 1  # only the preview ran


def test_check_only_stops_after_preview(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--check", "--limit", "zcrypto-red"])
    assert r.returncode == 0
    inv = invocations(tmp_path)
    assert len(inv) == 1 and "--check" in inv[0] and "--diff" in inv[0]


def test_no_tty_refuses_before_real_pass(tmp_path):
    script = make_harness(tmp_path)
    r = run_no_tty(script, ["site.yml", "--limit", "zcrypto-red"])
    assert r.returncode == 3
    assert len(invocations(tmp_path)) == 1  # preview ran; the real pass did not


def test_wrong_confirmation_aborts(tmp_path):
    script = make_harness(tmp_path)
    rc, _out = run_with_tty(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto")
    assert rc == 3
    assert len(invocations(tmp_path)) == 1


def test_typed_limit_runs_the_real_pass(tmp_path):
    script = make_harness(tmp_path)
    rc, _out = run_with_tty(script, ["site.yml", "--limit", "zcrypto-red"], "zcrypto-red")
    assert rc == 0
    inv = invocations(tmp_path)
    assert len(inv) == 2
    assert "--check" in inv[0] and "--diff" in inv[0]
    assert "--check" not in inv[1] and "--limit zcrypto-red" in inv[1]


def test_limit_equals_form_is_parsed(tmp_path):
    script = make_harness(tmp_path)
    rc, out = run_with_tty(script, ["site.yml", "--limit=zcrypto-ops"], "zcrypto-ops")
    assert rc == 0
    assert "zcrypto-ops" in out
    assert len(invocations(tmp_path)) == 2
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_converge_sh.py -q`; expected: every test FAILs (script absent).

- [ ] **Step 3: Write the script**

```bash
#!/usr/bin/env bash
# The documented converge path (traceability: spec 00083 D1): preview first, typed-limit confirm,
# then the real pass through run.sh (which loads the vaulted deploy keys into a throwaway agent).
# Usage: converge.sh <playbook.yml> --limit <target> [more ansible args...]
# rc 2 usage | rc 3 confirm-abort / no tty | rc 4 preview failed | else the real pass's own exit.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "converge.sh requires a playbook and --limit — a bare site.yml still runs every play." >&2
  echo "usage: converge.sh <playbook.yml> --limit <host> [more ansible args...]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
PLAYBOOK="$1"; shift
case "$PLAYBOOK" in --*) usage ;; esac

LIMIT=""; CHECK_ONLY=0; prev=""
for a in "$@"; do
  [ "$prev" = "--limit" ] && LIMIT="$a"
  case "$a" in
    --limit=*) LIMIT="${a#--limit=}" ;;
    --check) CHECK_ONLY=1 ;;
  esac
  prev="$a"
done
[ -n "$LIMIT" ] || usage

echo "== preview: --check --diff =="
"$SD/run.sh" "$PLAYBOOK" --check --diff "$@" || {
  echo "converge.sh: preview failed — fix the check pass before converging" >&2
  exit 4
}

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "== --check requested: preview only, nothing to converge =="
  exit 0
fi

# /dev/tty, never stdin: a pipe or heredoc must not be able to drive the confirm. No controlling
# terminal -> refuse; unattended contexts do not converge through this path.
if ! { : < /dev/tty; } 2>/dev/null; then
  echo "converge.sh: no controlling terminal — the confirm gate needs an attended session" >&2
  exit 3
fi
printf 'Type the --limit value (%s) to converge, anything else aborts: ' "$LIMIT" > /dev/tty
IFS= read -r reply < /dev/tty || reply=""
if [ "$reply" != "$LIMIT" ]; then
  echo "converge.sh: aborted — confirmation did not match the --limit value; nothing executed" >&2
  exit 3
fi
exec "$SD/run.sh" "$PLAYBOOK" "$@"
```

- [ ] **Step 4: Confirm the operator-facing sweep collects the new script** — `tests/test_internal_terms_not_operator_visible.py` auto-globs `infra/**/*.sh` (no list to edit); run it and state in the report that the new file was swept.

- [ ] **Step 5: Run to verify pass** — `uv run pytest tests/test_converge_sh.py tests/test_internal_terms_not_operator_visible.py -q`; expected: all PASS. Also `bash -n infra/ansible/scripts/converge.sh`.

- [ ] **Step 6: Prove a refusal bites** — in a scratch copy, flip the confirm comparison `!=` to `=` and confirm `test_wrong_confirmation_aborts` + `test_typed_limit_runs_the_real_pass` both fail against the flipped copy (point the tests' SCRIPT at it via a monkeypatched path or a temporary edit — restore after; do not commit the flip).

- [ ] **Step 7: Commit**

```bash
git add infra/ansible/scripts/converge.sh tests/test_converge_sh.py
git commit -m "feat(infra): converge.sh — preview-first, typed-limit confirm converge path"
```

---

### Task 2: `vault-pass.sh` ancestor check

**Files:**
- Modify: `infra/ansible/scripts/vault-pass.sh`
- Test: `tests/test_vault_pass_guard.py`

**Interfaces:**
- Produces: rc 1 + one stderr line on a banned ancestor; unchanged sops exec otherwise. Test seam: `ZCRYPTO_SOPS_BIN` overrides the sops binary path.

- [ ] **Step 1: Write the failing tests**

```python
"""vault-pass.sh refuses ansible-inventory --host/--list ancestry (spec 00083 D4).

The test launches vault-pass.sh as a CHILD of a wrapper script literally named
`ansible-inventory`, so /proc/<ancestor>/cmdline genuinely contains the banned form —
the ancestry walk is exercised for real, not simulated. sops is stubbed via ZCRYPTO_SOPS_BIN.
"""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "vault-pass.sh"


def make_stub_sops(tmp_path):
    sops = tmp_path / "fake-sops"
    sops.write_text("#!/usr/bin/env bash\necho SOPS-RAN\n")
    sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
    return sops


def run_under(tmp_path, wrapper_name, wrapper_args):
    """Run vault-pass.sh as a CHILD of a process whose cmdline is `<wrapper_name> <args>`.

    No `exec` in the wrapper — exec would replace the wrapper's process image, so no ancestor
    would ever carry the banned cmdline and the walk would find nothing (cold-review C1).
    """
    wrapper = tmp_path / wrapper_name
    wrapper.write_text(f'#!/usr/bin/env bash\n"{SCRIPT}"\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "ZCRYPTO_SOPS_BIN": str(make_stub_sops(tmp_path))}
    return subprocess.run([str(wrapper), *wrapper_args], capture_output=True, text=True, env=env)


def test_refuses_ansible_inventory_list(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--list"])
    assert r.returncode == 1
    assert "cleartext" in r.stderr and "--graph" in r.stderr
    assert "SOPS-RAN" not in r.stdout


def test_refuses_ansible_inventory_host(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--host", "zcrypto"])
    assert r.returncode == 1
    assert "SOPS-RAN" not in r.stdout


def test_allows_other_ancestors(tmp_path):
    r = run_under(tmp_path, "ansible-playbook", ["--list-tags"])
    assert r.returncode == 0
    assert "SOPS-RAN" in r.stdout


def test_allows_ansible_inventory_graph(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--graph"])
    assert r.returncode == 0
    assert "SOPS-RAN" in r.stdout
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_vault_pass_guard.py -q`; the two refusal tests FAIL (script currently execs sops unconditionally; also no `ZCRYPTO_SOPS_BIN` seam yet, so `test_allows_*` fail on the real sops path).

- [ ] **Step 3: Rewrite the script**

```bash
#!/usr/bin/env bash
# Refuses to hand the vault password to `ansible-inventory --host/--list` — both silently decrypt
# the WHOLE vault to stdout (capture-deploys.md "Ansible secrets"). Walks /proc ancestry so the
# refusal fires wherever ansible-inventory sits in the process chain. Traceability: spec 00083 D4.
pid=$$
while [ "$pid" -gt 1 ] 2>/dev/null; do
  cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$cmd" in
    *ansible-inventory*" --host"*|*ansible-inventory*" --list"*)
      echo "vault password refused: ansible-inventory --host/--list prints every vault secret in cleartext — use --graph, --list-tags, or a key-names-only filter" >&2
      exit 1 ;;
  esac
  pid="$(awk '/^PPid:/{print $2}' "/proc/$pid/status" 2>/dev/null)" || break
  [ -n "$pid" ] || break
done
exec "${ZCRYPTO_SOPS_BIN:-/home/zhaow/go/bin/sops}" -d --extract '["vault_password"]' "$(dirname "$0")/../vault-password.sops.yaml"
```

(`" --list"` also matches a hypothetical `--list-tags` on ansible-inventory — it has no such flag, and over-refusing inside ansible-inventory ancestry costs only a listing, never a converge.)

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_vault_pass_guard.py -q`; all 4 PASS. Then prove the real path intact: `infra/ansible/scripts/vault-pass.sh > /dev/null && echo vault-ok` (attended workstation has sops + the sops key; expect `vault-ok`).

- [ ] **Step 5: Commit**

```bash
git add infra/ansible/scripts/vault-pass.sh tests/test_vault_pass_guard.py
git commit -m "feat(infra): vault-pass.sh refuses ansible-inventory --host/--list ancestry"
```

---

### Task 3: `ops-postverify.sh`

**Files:**
- Create: `infra/scripts/ops-postverify.sh` (mode 0755)
- Test: `tests/test_ops_postverify.py`

**Interfaces:**
- Consumes: `infra/scripts/grafana-query.py` output shape — per query: a header line, then `  {labels} = <value>` per series, or a `(no series)` marker. Test seam: `ZCRYPTO_GRAFANA_QUERY` replaces the whole query command.
- Produces: `PASS <name> …` / `FAIL <name> — …` per check; exit 0 iff all six PASS.

- [ ] **Step 1: Write the failing tests**

```python
"""ops-postverify.sh: verify-by-outcome as one command (spec 00083 D3).

The grafana query command is stubbed via ZCRYPTO_GRAFANA_QUERY; the stub replays canned
output keyed by which query it receives, so each check's parse path is exercised for real.
"""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "scripts" / "ops-postverify.sh"

STUB = """#!/usr/bin/env bash
q="$1"
case "$q" in
  *archive_pull*) printf '%s\\n' "$ARCHIVE_OUT" ;;
  *panel_exit*)   printf '%s\\n' "$PANEL_OUT" ;;
  *mtime*)        printf '%s\\n' "$MTIME_OUT" ;;
  *residual_gap*) printf '%s\\n' "$RESIDUAL_OUT" ;;
  *healable_gap*) printf '%s\\n' "$HEALABLE_OUT" ;;
  *hc_checks*)    printf '%s\\n' "$HC_OUT" ;;
  *) echo "unexpected query: $q" >&2; exit 9 ;;
esac
"""

GOOD = {
    "ARCHIVE_OUT": "ops_archive_pull_exit_code\n  {host=zcrypto-ops} = 0",
    "PANEL_OUT": "ops_panel_exit_code\n  {host=zcrypto-ops} = 0",
    "MTIME_OUT": "query\n  {host=zcrypto-ops} = 1800",
    "RESIDUAL_OUT": "query\n  {host=zcrypto-ops} = 0",
    "HEALABLE_OUT": "query\n  {host=zcrypto-ops} = 0",
    "HC_OUT": "hc_checks_down_total\n  {host=zcrypto-ops} = 0",
}


def run_postverify(tmp_path, overrides):
    stub = tmp_path / "fake-gq.sh"
    stub.write_text(STUB)
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, **GOOD, **overrides, "ZCRYPTO_GRAFANA_QUERY": str(stub)}
    return subprocess.run([str(SCRIPT)], capture_output=True, text=True, env=env)


def check_lines(out, kind):
    """Count per-check result lines only — the summary line also contains the bare token."""
    return sum(1 for line in out.splitlines() if line.startswith(f"{kind} "))


def test_all_green_passes(tmp_path):
    r = run_postverify(tmp_path, {})
    assert r.returncode == 0
    assert check_lines(r.stdout, "PASS") == 6 and check_lines(r.stdout, "FAIL") == 0


def test_nonzero_exit_code_fails(tmp_path):
    r = run_postverify(tmp_path, {"PANEL_OUT": "ops_panel_exit_code\n  {host=zcrypto-ops} = 1"})
    assert r.returncode == 1
    assert "FAIL" in r.stdout and "panel" in r.stdout.lower()


def test_no_series_is_a_fail_never_a_zero(tmp_path):
    r = run_postverify(tmp_path, {"HC_OUT": "hc_checks_down_total\n  (no series)"})
    assert r.returncode == 1
    assert "no series" in r.stdout


def test_stale_reconcile_mtime_fails(tmp_path):
    r = run_postverify(tmp_path, {"MTIME_OUT": "query\n  {host=zcrypto-ops} = 90000"})
    assert r.returncode == 1


def test_counter_bump_fails(tmp_path):
    r = run_postverify(tmp_path, {"RESIDUAL_OUT": "query\n  {host=zcrypto-ops} = 12.5"})
    assert r.returncode == 1


def test_any_bad_series_among_many_fails(tmp_path):
    two = "hc_checks_down_total\n  {name=a} = 0\n  {name=b} = 1"
    r = run_postverify(tmp_path, {"HC_OUT": two})
    assert r.returncode == 1


def test_query_error_is_a_fail(tmp_path):
    stub = tmp_path / "fake-gq.sh"
    stub.write_text("#!/usr/bin/env bash\necho boom >&2\nexit 3\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "ZCRYPTO_GRAFANA_QUERY": str(stub)}
    r = subprocess.run([str(SCRIPT)], capture_output=True, text=True, env=env)
    assert r.returncode == 1
    assert check_lines(r.stdout, "FAIL") == 6
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_ops_postverify.py -q`; all FAIL (script absent).

- [ ] **Step 3: Write the script**

```bash
#!/usr/bin/env bash
# Verify-by-outcome after an ops converge, as one command (traceability: spec 00083 D3). Six
# checks through grafana-query.py; each prints PASS/FAIL; exit 0 iff all pass. "(no series)" is a
# FAIL, never a zero — an empty query is not an absent event.
set -uo pipefail   # deliberately NOT -e: a failed query is a FAIL result, not a crash
QUERY="${ZCRYPTO_GRAFANA_QUERY:-uv run python infra/scripts/grafana-query.py}"
fails=0

# check <name> <promql> <mode: zero|under> [limit]
check() {
  local name="$1" q="$2" mode="$3" limit="${4:-0}" out vals bad
  if ! out=$(timeout 60 $QUERY "$q" 2>&1); then
    echo "FAIL $name — query error: $(printf '%s' "$out" | head -1)"
    fails=$((fails + 1)); return
  fi
  vals=$(printf '%s\n' "$out" | sed -n 's/.*= //p')
  if [ -z "$vals" ]; then
    echo "FAIL $name — no series (an empty query is not a zero)"
    fails=$((fails + 1)); return
  fi
  bad=$(printf '%s\n' "$vals" | awk -v mode="$mode" -v l="$limit" \
    'mode=="zero" && $1+0 != 0 {n++} mode=="under" && $1+0 >= l {n++} END{print n+0}')
  if [ "$bad" -eq 0 ]; then
    echo "PASS $name ($(printf '%s' "$vals" | paste -sd, -))"
  else
    echo "FAIL $name — $bad series out of bounds ($(printf '%s' "$vals" | paste -sd, -))"
    fails=$((fails + 1))
  fi
}

check "archive-pull exit code" 'ops_archive_pull_exit_code' zero
check "panel exit code" 'ops_panel_exit_code' zero
check "reconcile freshness (s)" 'time() - node_textfile_mtime_seconds{file=~".*reconcile.prom"}' under 4200
check "residual-gap counter unbumped (2h)" 'increase(zcrypto_reconcile_residual_gap_seconds_total[2h])' zero
check "healable-gap counter unbumped (2h)" 'increase(zcrypto_reconcile_healable_gap_seconds_total[2h])' zero
check "healthchecks down" 'hc_checks_down_total' zero

if [ "$fails" -eq 0 ]; then echo "ops-postverify: ALL PASS"; else echo "ops-postverify: $fails FAIL"; fi
[ "$fails" -eq 0 ]
```

- [ ] **Step 4: Pin the two counter names against the exporter** — add to `tests/test_ops_postverify.py`:

```python
def test_counter_names_match_the_exporter():
    """The two increase() queries must name series the reconcile exporter actually publishes.

    The exporter is cli/archive/command.py's _write_textfile (it assembles zcrypto_reconcile_ +
    leg); the Alloy keep-list at infra/ansible/roles/ops/files/config.alloy admits series via
    regex alternations, not literal names (cold-review I4) — so each name must fullmatch one of
    the keep regexes' alternatives, or it never reaches Cloud and the check reads (no series).
    """
    script = SCRIPT.read_text()
    repo = SCRIPT.parent.parent.parent
    exporter = (repo / "cli" / "archive" / "command.py").read_text()
    alloy = (repo / "infra" / "ansible" / "roles" / "ops" / "files" / "config.alloy").read_text()
    alternatives = [alt for k in re.findall(r'regex\s*=\s*"([^"]*)"', alloy) for alt in k.split("|")]
    for name in ("zcrypto_reconcile_residual_gap_seconds_total", "zcrypto_reconcile_healable_gap_seconds_total"):
        assert name in script
        assert any(re.fullmatch(alt, name) for alt in alternatives), f"{name} not admitted by any keep regex"
        assert name.removeprefix("zcrypto_reconcile_") in exporter  # command.py assembles prefix + leg
```

(`import re` at the top of the test file.)

- [ ] **Step 5: Run** — `uv run pytest tests/test_ops_postverify.py tests/test_internal_terms_not_operator_visible.py -q` (the latter auto-globs `infra/**/*.sh` — no list edit); all PASS; `bash -n infra/scripts/ops-postverify.sh`.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/ops-postverify.sh tests/test_ops_postverify.py
git commit -m "feat(infra): ops-postverify.sh — verify-by-outcome as one command"
```

---

### Task 4: `zcrypto-panel-regenerate`

**Files:**
- Create: `infra/ansible/roles/ops/templates/panel-regenerate.sh.j2`
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (install task, beside the panel timer install block)
- Test: `tests/test_panel_regenerate.py`; extend `tests/test_infra_converge_guards.py` with an install-task presence test

**Interfaces:**
- Consumes: ops role vars `ops_data_dir`, `ops_panel_subdir`, `ops_nas_mount`, `ops_capture_subdir`, `ops_reconciled_subdir` (all existing).
- Produces: `/usr/local/sbin/zcrypto-panel-regenerate` on the ops host; rc 2 usage/bad-override, rc 3 refused (deadline/abort — timer restarted, nothing deleted), rc 4 rebuild failed (timer left stopped).

- [ ] **Step 1: Write the failing tests**

```python
"""zcrypto-panel-regenerate: delete-and-rebuild as one refusing flow (spec 00083 D2).

The template renders with fixed test vars; systemctl/du/date are PATH stubs writing a call
log, so ordering claims ("nothing deleted before the typed gate") are asserted against what
actually ran. /dev/tty gates run under a pty.
"""

import os
import pty
import subprocess
from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "infra" / "ansible" / "roles" / "ops" / "templates" / "panel-regenerate.sh.j2"
)

VARS = {
    "ops_data_dir": "{data}",
    "ops_panel_subdir": "l2-panel",
    "ops_nas_mount": "{nas}",
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
}

# Stubs: date is pinned to 2026-08-03 10:00:00 UTC (epoch 1785751200), far from 02:25.
STUB_DATE = """#!/usr/bin/env bash
case "$*" in
  "-u +%s") echo 1785751200 ;;
  "-u +%F") echo 2026-08-03 ;;
  *-d*) exec /bin/date "$@" ;;
esac
"""
STUB_SYSTEMCTL = """#!/usr/bin/env bash
echo "systemctl $*" >> "$CALL_LOG"
case "$*" in *--wait*) exit ${FAKE_UNIT_RC:-0} ;; esac
exit 0
"""
STUB_DU_SMALL = "#!/usr/bin/env bash\necho -e \"1\\t$2\"\n"
STUB_DU_HUGE = "#!/usr/bin/env bash\necho -e \"99999999\\t$2\"\n"


def render(tmp_path, du_stub):
    text = TEMPLATE.read_text()
    data = tmp_path / "data"; nas = tmp_path / "nas"
    (data / "l2-panel").mkdir(parents=True)
    (data / "l2-panel" / "row.parquet").write_text("x")
    (data / "capture-reconciled").mkdir()
    (nas / "capture-segments").mkdir(parents=True)
    for var, val in VARS.items():
        text = text.replace("{{ %s }}" % var, val.format(data=data, nas=nas))
    assert "{{" not in text, "unrendered template var left behind"
    script = tmp_path / "zcrypto-panel-regenerate"
    script.write_text(text)
    script.chmod(0o755)
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    for name, body in (("date", STUB_DATE), ("systemctl", STUB_SYSTEMCTL), ("du", du_stub)):
        p = bin_dir / name
        p.write_text(body)
        p.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CALL_LOG": str(tmp_path / "calls.log")}
    return script, env, data / "l2-panel", tmp_path / "calls.log"


def calls(log):
    return log.read_text().splitlines() if log.exists() else []


def run_tty(script, env, replies, args=()):
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update(env)
        os.execv(str(script), [str(script), *args])
    out = b""
    replies = list(replies)
    try:
        while True:
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            out += chunk
            if b"to continue" in out and replies:
                os.write(fd, replies.pop(0).encode() + b"\n")
                out = out.replace(b"to continue", b"to-continue-consumed")
    except OSError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), out.decode(errors="replace")


def test_eta_over_deadline_refuses_and_restarts_timer(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_HUGE)
    r = subprocess.run(["setsid", str(script)], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 3
    assert panel.exists()  # nothing deleted
    assert calls(log) == [
        "systemctl stop zcrypto-panel-materialize.timer",
        "systemctl start zcrypto-panel-materialize.timer",
    ]


def test_boolean_override_refused(tmp_path):
    script, env, panel, _log = render(tmp_path, STUB_DU_HUGE)
    r = subprocess.run(["setsid", str(script), "--override", "true"], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 2
    assert panel.exists()


def test_reason_override_crosses_the_deadline(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_HUGE)
    rc, out = run_tty(script, env, ["paused"], args=("--override", "rebuild must land before the audit window"))
    assert rc == 0
    assert "override accepted" in out
    assert not panel.exists()
    assert "systemctl start --wait zcrypto-panel-materialize.service" in calls(log)


def test_abort_at_pause_gate_deletes_nothing(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, _out = run_tty(script, env, ["nope"])
    assert rc == 3
    assert panel.exists()
    assert "systemctl start zcrypto-panel-materialize.timer" in calls(log)  # resumed


def test_happy_path_order_and_checklist(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 0
    assert not panel.exists()
    seq = calls(log)
    assert seq == [
        "systemctl stop zcrypto-panel-materialize.timer",
        "systemctl start --wait zcrypto-panel-materialize.service",
        "systemctl start zcrypto-panel-materialize.timer",
    ]
    assert "NAS" in out and "Un-pause" in out and "ops_panel_timer_hold" in out
```

and the failure-path test:

```python
def test_failed_rebuild_leaves_timer_stopped(tmp_path):
    script, env, panel, log = render(tmp_path, STUB_DU_SMALL)
    env["FAKE_UNIT_RC"] = "1"
    rc, out = run_tty(script, env, ["paused"])
    assert rc == 4
    seq = calls(log)
    assert "systemctl start zcrypto-panel-materialize.timer" not in seq  # stays stopped
    assert "investigate" in out
```

(`STUB_SYSTEMCTL` fails only the `--wait` call under `FAKE_UNIT_RC`, so the initial timer stop still succeeds — that is why its case-match is shaped the way it is.)

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_panel_regenerate.py -q`; all FAIL (template absent).

- [ ] **Step 3: Write the template**

```bash
#!/usr/bin/env bash
# Rendered by the `ops` Ansible role at /usr/local/sbin/zcrypto-panel-regenerate — do not
# hand-edit on the host; edit infra/ansible/roles/ops/templates/panel-regenerate.sh.j2 and
# re-converge instead. Traceability: spec 00083 D2.
#
# Delete-and-rebuild of the L2 panel tree as one refusing flow: timer stopped first, window sized
# from the input tree (~2.1 s/MB, x1.2 margin) against the 02:25 UTC auto-reboot, the dead-man
# pause taken as a TYPED gate (the point of no return stays human), delete, rebuild INSIDE the
# materialize unit (a stray timer tick collides with an active unit instead of double-writing),
# then the operator checklist for the halves this host cannot reach (NAS copy, un-pause).
# rc 2 usage/bad override | rc 3 refused, timer restarted, nothing deleted | rc 4 rebuild failed.
set -euo pipefail

PANEL_ROOT="{{ ops_data_dir }}/{{ ops_panel_subdir }}"
CANONICAL="{{ ops_nas_mount }}/{{ ops_capture_subdir }}"
OVERLAY="{{ ops_data_dir }}/{{ ops_reconciled_subdir }}"

override=""
if [ "$#" -gt 0 ]; then
  if [ "$1" = "--override" ] && [ "$#" -eq 2 ]; then
    override="$2"
  else
    echo 'usage: zcrypto-panel-regenerate [--override "<reason>"]' >&2
    exit 2
  fi
fi
if [ -n "$override" ]; then
  low=$(printf '%s' "$override" | tr '[:upper:]' '[:lower:]')
  if [ "${#override}" -le 8 ] || [ "$low" = "true" ] || [ "$low" = "false" ] || [ "$low" = "1" ] || [ "$low" = "yes" ]; then
    echo "refusing: --override needs a reason (more than 8 chars, not a boolean)" >&2
    exit 2
  fi
fi

echo "== step 1: stopping the hourly timer =="
systemctl stop zcrypto-panel-materialize.timer
echo "timer stopped. Reminder: a converge re-arms it unless -e ops_panel_timer_hold=true is passed."

echo "== step 2: sizing the rebuild =="
mb=$(( $(du -sm "$CANONICAL" | cut -f1) + $(du -sm "$OVERLAY" | cut -f1) ))
eta=$(awk -v m="$mb" 'BEGIN{printf "%d", m * 2.1 * 1.2}')
now=$(date -u +%s)
deadline=$(date -u -d "$(date -u +%F) 02:25" +%s)
[ "$now" -ge "$deadline" ] && deadline=$(( deadline + 86400 ))
echo "input ${mb} MB -> ETA ~$(( eta / 60 )) min incl. margin; auto-reboot deadline epoch $deadline"
if [ $(( now + eta )) -ge "$deadline" ]; then
  if [ -n "$override" ]; then
    echo "override accepted: $override"
  else
    echo "refusing: the rebuild would still be running at the 02:25 UTC auto-reboot (a oneshot unit has no timeout — only that reboot kills it). Re-run earlier in the day, or pass --override \"<reason>\"." >&2
    systemctl start zcrypto-panel-materialize.timer
    echo "timer restarted (nothing was deleted)."
    exit 3
  fi
fi

if ! { : < /dev/tty; } 2>/dev/null; then
  echo "no controlling terminal — the pause gate needs an attended session; timer restarted, nothing deleted" >&2
  systemctl start zcrypto-panel-materialize.timer
  exit 3
fi
echo "== step 3: pause the dead-man check =="
echo "The panel healthcheck pings only on a clean run and is this timer's only liveness signal."
echo "Pause it now, TIME-BOXED, on healthchecks.io (the panel materialize check)."
printf 'Type "paused" to continue (anything else aborts, nothing deleted): ' > /dev/tty
IFS= read -r reply < /dev/tty || reply=""
if [ "$reply" != "paused" ]; then
  systemctl start zcrypto-panel-materialize.timer
  echo "aborted — nothing deleted; timer restarted." >&2
  exit 3
fi

echo "== step 4: deleting the ops-side panel tree =="
rm -rf "$PANEL_ROOT"
echo "deleted $PANEL_ROOT (the per-pair watermarks went with it — the rebuild covers everything, out-of-scope subtrees included)"

echo "== step 5: rebuilding inside the unit =="
if ! systemctl start --wait zcrypto-panel-materialize.service; then
  echo "rebuild FAILED (the unit reported non-zero). The tree is now partial — investigate before anything else. The timer stays STOPPED and the closing checklist is NOT owed yet." >&2
  exit 4
fi
echo "rebuild complete."
systemctl start zcrypto-panel-materialize.timer
echo "timer restarted."

echo "== step 6: your remaining checklist =="
echo "1. Delete the OLD panel copy on the NAS share ({{ ops_panel_subdir }} there) — the hourly pull has no --delete, so it survives until deleted there."
echo "2. Un-pause the healthchecks.io panel check (paused time-boxed in step 3)."
```

- [ ] **Step 4: Install task** — in `infra/ansible/roles/ops/tasks/main.yml`, at TOP LEVEL (not inside the `ops_image_digest is defined`-gated block — the regenerate script must land on the host regardless of whether this converge re-pins), directly after the block that installs the panel-materialize runner, add:

```yaml
- name: install the panel regenerate flow (delete-and-rebuild with its refusals)
  ansible.builtin.template:
    src: panel-regenerate.sh.j2
    dest: /usr/local/sbin/zcrypto-panel-regenerate
    mode: "0755"
    owner: root
    group: root
```

- [ ] **Step 5: Install-task presence test** — in `tests/test_infra_converge_guards.py`'s ops section:

```python
def test_panel_regenerate_is_installed_by_the_ops_role():
    tasks = load_tasks(OPS)
    task = find_task(tasks, "install the panel regenerate flow (delete-and-rebuild with its refusals)")
    assert task["ansible.builtin.template"]["dest"] == "/usr/local/sbin/zcrypto-panel-regenerate"
    assert task["ansible.builtin.template"]["mode"] == "0755"
```

- [ ] **Step 6: Run to verify pass** — `uv run pytest tests/test_panel_regenerate.py tests/test_infra_converge_guards.py -q`; all PASS. `uv run pre-commit run -a` (ansible-lint on the role change).

- [ ] **Step 7: Prove the deadline refusal bites** — scratch-copy the rendered script, flip `-ge "$deadline"` to `-gt` **and** re-run only the huge-du test with a stubbed date sitting exactly at deadline−eta; simpler and sufficient: flip the comparison to `false` (`[ 0 -eq 1 ]`) in the copy and confirm `test_eta_over_deadline_refuses_and_restarts_timer` fails against it. Restore; nothing committed.

- [ ] **Step 8: Commit**

```bash
git add infra/ansible/roles/ops/templates/panel-regenerate.sh.j2 infra/ansible/roles/ops/tasks/main.yml tests/test_panel_regenerate.py tests/test_infra_converge_guards.py
git commit -m "feat(infra): zcrypto-panel-regenerate — the panel delete-and-rebuild as one refusing flow"
```

---

### Task 5: Engine canary-parity mirror

**Files:**
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (insert the four-task parity block directly after the digest-resident preflight `preflight — refuse a digest the host has not pulled`, before anything renders)
- Test: `tests/test_infra_converge_guards.py`

**Interfaces:**
- Consumes: the capture role's parity block (`infra/ansible/roles/capture/tasks/main.yml`, tasks named `probe — the primary's running capture digest (canary scope)` through `canary override accepted — the reason, on the record`) as the mirror source; `canary_override` (shared variable, spec 00083 D5).
- Produces: task names `probe — the running engine digest (canary scope)`, `probe — the secondary's running capture digest (engine canary parity)`, `engine canary parity — refuse an engine re-pin the secondary has not baked`, `engine canary override accepted — the reason, on the record`.

- [ ] **Step 1: Write the failing tests** (wave-1 substrate; `ENGINE` and helpers already exist in the file)

```python
# --- engine canary parity (spec 00083 D5): the capture parity assert, mirrored ------------------
# The engine has no secondary; the secondary's CAPTURE bake is the engine's canary gate. The mirror
# engages only when engine_image_digest differs from the running engine digest, fails CLOSED on an
# unreachable secondary (empty stdout -> refuse via the override path), and shares canary_override.

def test_engine_parity_refuses_unbaked_digest():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_secondary_digest_probe": {"stdout": "ghcr.io/x/y@sha256:" + "cd" * 32},
        "canary_override": "",
    }
    assert not truthy(assert_that(guard), v)


def test_engine_parity_passes_when_secondary_runs_it():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    d = "sha256:" + "ab" * 32
    v = {
        "engine_image_digest": d,
        "engine_secondary_digest_probe": {"stdout": f"ghcr.io/x/y@{d}"},
        "canary_override": "",
    }
    assert truthy(assert_that(guard), v)


def test_engine_parity_fails_closed_on_unreachable_secondary():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {"engine_image_digest": "sha256:" + "ab" * 32, "engine_secondary_digest_probe": {}, "canary_override": ""}
    assert not truthy(assert_that(guard), v)  # no stdout at all -> default('') -> refuse


def test_engine_parity_reason_override_is_accepted_and_boolean_is_not():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {"engine_image_digest": "sha256:" + "ab" * 32, "engine_secondary_digest_probe": {"stdout": ""}}
    assert truthy(assert_that(guard), {**v, "canary_override": "rollback to the only digest carrying the fix"})
    assert not truthy(assert_that(guard), {**v, "canary_override": "true"})


def test_engine_parity_probe_skips_when_digest_already_running():
    tasks = load_tasks(ENGINE)
    probe = find_task(tasks, "probe — the secondary's running capture digest (engine canary parity)")
    d = "sha256:" + "ab" * 32
    v = {"engine_image_digest": d, "engine_running_parity_probe": {"stdout": f"ghcr.io/x/y@{d}"}}
    assert not truthy(" and ".join("(%s)" % c for c in when_conditions(probe)), v)


def test_engine_parity_probe_is_unreachable_tolerant_and_delegated():
    tasks = load_tasks(ENGINE)
    probe = find_task(tasks, "probe — the secondary's running capture digest (engine canary parity)")
    assert probe.get("ignore_unreachable") is True
    assert "difference(groups['engine_host'])" in probe["delegate_to"]


def test_engine_parity_echo_mirrors_the_negated_assert():
    tasks = load_tasks(ENGINE)
    echo = find_task(tasks, "engine canary override accepted — the reason, on the record")
    v_overridden = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_secondary_digest_probe": {"stdout": ""},
        "canary_override": "rollback to the only digest carrying the fix",
    }
    conds = " and ".join("(%s)" % c for c in when_conditions(echo))
    # a dict fixture is `not skipped` under Templar — wave-1's echo tests evaluate this directly
    assert truthy(conds, v_overridden)
    assert not truthy(conds, {**v_overridden, "canary_override": "true"})
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_infra_converge_guards.py -q -k engine_parity`; all FAIL (tasks absent).

- [ ] **Step 3: Insert the block** in `infra/ansible/roles/engine/tasks/main.yml` right after the digest preflight:

```yaml
# spec 00083 D5: the capture role's canary parity, mirrored. There is no engine secondary — the
# secondary's CAPTURE bake is the engine's canary gate (fleet-pins.md records it in those words) —
# so an engine re-pin is refused until the new digest runs as capture on the secondary. This play
# targets the engine host only, so the mirror drops the capture block's inventory_hostname scoping;
# everything else mirrors modulo the engine_ prefix. canary_override is deliberately SHARED with
# the capture assert: one gate concept, one override, and the echo below lands the reason either way.
- name: probe — the running engine digest (canary scope)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-engine
  register: engine_running_parity_probe
  failed_when: false
  changed_when: false
  check_mode: false
  when: engine_image_digest is defined

- name: probe — the secondary's running capture digest (engine canary parity)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-capture
  register: engine_secondary_digest_probe
  delegate_to: "{{ (groups['capture_host'] | difference(groups['engine_host'])) | first }}"
  failed_when: false
  ignore_unreachable: true  # mirror of the capture probe: an unreachable secondary must reach the assert (empty stdout -> refuse via override), never abort or silently pass
  changed_when: false
  check_mode: false
  when: >-
    engine_image_digest is defined
    and engine_running_parity_probe.stdout is defined
    and engine_image_digest not in engine_running_parity_probe.stdout

- name: engine canary parity — refuse an engine re-pin the secondary has not baked
  ansible.builtin.assert:
    that: >-
      (engine_image_digest in engine_secondary_digest_probe.stdout | default(''))
      or ((canary_override | default('') | string | length > 8)
          and (canary_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
    fail_msg: >-
      The secondary does not run {{ engine_image_digest }} as capture — there is no engine
      secondary, so that bake IS the engine's canary gate. Converge the secondary's capture first
      and let it bake, or pass -e canary_override="<why this cannot wait>" (a reason, not a
      boolean; it lands in this log).
  when: >-
    engine_image_digest is defined
    and engine_secondary_digest_probe is not skipped

# An ACCEPTED override lands its reason in the play log — gated on acceptance (the parity check
# failing AND the fragment true), never on mere presence, same as every wave-1 echo.
- name: engine canary override accepted — the reason, on the record
  ansible.builtin.debug:
    msg: "canary_override accepted: {{ canary_override }}"
  when: >-
    engine_image_digest is defined
    and engine_secondary_digest_probe is not skipped
    and not (engine_image_digest in engine_secondary_digest_probe.stdout | default(''))
    and (canary_override | default('') | string | length > 8)
    and (canary_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_infra_converge_guards.py -q`; all green (new + wave-1). `uv run pre-commit run -a`; from `infra/ansible/`: `uv run ansible-playbook --syntax-check site.yml`.

- [ ] **Step 5: Prove the mirror is a mirror** — diff the four new tasks against the capture originals modulo the mechanical substitutions (`capture_`→`engine_`, container name, dropped `inventory_hostname` scoping, ADDED `engine_image_digest is defined` conjuncts — capture's var is mandatory, engine's is optional — and fail_msg wording); paste the diff in the task report. Any structural divergence beyond those is a defect.

- [ ] **Step 6: Commit**

```bash
git add infra/ansible/roles/engine/tasks/main.yml tests/test_infra_converge_guards.py
git commit -m "feat(config): engine canary parity — an engine re-pin is refused until the secondary bakes it"
```

---

### Task 6: Window-floor journal probe

**Files:**
- Modify: `infra/ansible/site.yml` (engine play `pre_tasks`: new probe task; rework guard 5's `that:`, fail_msg, and the echo's mirrored `when:`)
- Test: `tests/test_infra_converge_guards.py`

**Interfaces:**
- Consumes: guard 5 (`engine window — refuse a converge outside the inter-cycle gap`) and its echo task; `engine_epoch_probe`.
- Produces: probe register `engine_cycle_epoch_probe` (play-level pre_task — prefix-exempt but named consistently); the floor expression both branches of which Task 12's rule text describes.

- [ ] **Step 1: Write the failing tests**

```python
# --- window floor from the boundary cycle's completion (spec 00083 D6) --------------------------
# When the boundary's cycle-HH.json already carries completed_at, the floor drops from B+1800 to
# completed_at+300. Absent probe, failed probe, or garbage stdout -> the CONSERVATIVE B+1800 floor.

BOUNDARY = 1785744000  # 2026-08-03 08:00:00 UTC, divisible by 14400


def _window_guard():
    tasks = load_tasks(SITE)
    return find_task(tasks, "engine window — refuse a converge outside the inter-cycle gap")


def test_floor_drops_to_completion_plus_300():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},  # B+500: inside old refusal window
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},  # completed 08:01:48
        "engine_window_override": "",
    }
    assert truthy(assert_that(guard), v)  # 500 >= 108+300 -> allowed early


def test_floor_still_refuses_before_completion_plus_300():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 300)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)  # 300 < 408


def test_failed_probe_keeps_conservative_floor():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},
        "engine_cycle_epoch_probe": {"rc": 1, "stdout": ""},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)  # rc!=0 -> floor stays B+1800


def test_garbage_stdout_keeps_conservative_floor():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": "Traceback (most recent call last)"},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)


def test_undefined_probe_keeps_conservative_floor():
    guard = _window_guard()
    v = {"engine_epoch_probe": {"stdout": str(BOUNDARY + 500)}, "engine_window_override": ""}
    assert not truthy(assert_that(guard), v)


def test_ceiling_unchanged():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 14400 - 300)},  # last 5 min
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)


def test_old_floor_still_passes_after_1800_without_journal():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 1800)},
        "engine_cycle_epoch_probe": {"rc": 1, "stdout": ""},
        "engine_window_override": "",
    }
    assert truthy(assert_that(guard), v)
```

```python
def test_journal_probe_path_matches_the_engine_role_default():
    """site.yml's pre_task cannot see role defaults, so the journal path is a literal — pin it to
    the engine role's engine_state_dir so a relocation cannot silently turn the floor
    permanently conservative (probe rc!=0 forever, guard 'working' but never early)."""
    site_text = SITE.read_text()
    defaults = (SITE.parent / "roles" / "engine" / "defaults" / "main.yml").read_text()
    m = re.search(r"^engine_state_dir:\s*(\S+)", defaults, re.M)
    assert m, "engine_state_dir vanished from the engine role defaults"
    assert f"{m.group(1)}/journal/" in site_text
```

(`SITE` is the test file's existing Path constant for `site.yml`; `import re` if not already there.)

Also update the existing wave-1 window fixtures in this file: they must gain `"engine_cycle_epoch_probe": {"rc": 1, "stdout": ""}` **only if** they fail without it — run them first; the `| default(1)` in the new expression is designed to keep them green untouched. If any needed editing, say so in the task report.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_infra_converge_guards.py -q -k floor`; the new tests FAIL (expression not yet reworked).

- [ ] **Step 3: Implement** — in `infra/ansible/site.yml`, insert after the `probe — the engine host's clock (window guard)` task:

```yaml
    # spec 00083 D6: when the boundary's cycle already completed, the fixed B+30 floor is
    # conservative for no reason — the running cycle it protects is over. The probe computes the
    # boundary and reads its journal artifact ON the engine host; any failure (missing file, parse
    # error) lands rc!=0 and the guard keeps the conservative floor. Journal day-dirs are %Y-%m-%d,
    # files cycle-%H.json, field completed_at (cli/engine/cycle.py's own naming).
    - name: probe — the boundary cycle's completion time (window floor)
      ansible.builtin.command:
        argv:
          - python3
          - -c
          - |
            import datetime, json, time
            b = int(time.time()) // 14400 * 14400
            d = datetime.datetime.fromtimestamp(b, datetime.timezone.utc)
            p = "/var/lib/zcrypto-engine/journal/%s/cycle-%02d.json" % (d.strftime("%Y-%m-%d"), d.hour)
            c = json.load(open(p))["completed_at"]
            t = datetime.datetime.fromisoformat(c.replace("Z", "+00:00"))
            print(int(t.timestamp()))
      register: engine_cycle_epoch_probe
      failed_when: false
      changed_when: false
      check_mode: false
      when: not ansible_check_mode
      tags: [engine]
```

and rework guard 5's `that:` to:

```yaml
        that: >-
          (((engine_epoch_probe.stdout | int) >= (
              ((engine_cycle_epoch_probe.stdout | default('') | trim | int) + 300)
              if ((engine_cycle_epoch_probe.rc | default(1)) == 0
                  and ((engine_cycle_epoch_probe.stdout | default('') | trim) | regex_search('^[0-9]{10}$')))
              else ((((engine_epoch_probe.stdout | int) // 14400) * 14400) + 1800)
            ))
           and (14400 - ((engine_epoch_probe.stdout | int) % 14400) >= 600))
          or ((engine_window_override | default('') | string | length > 8)
              and (engine_window_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
```

fail_msg becomes:

```yaml
        fail_msg: >-
          Outside the engine's inter-cycle gap (boundaries 00/04/08/12/16/20 UTC: the first 30 min
          belong to the running cycle — or 5 min past its journaled completion when that is sooner —
          and the last 10 min are too close to the next). Wait for the gap, or pass
          -e engine_window_override="<why this cannot wait>" (a reason, not a boolean).
```

and the echo task's `when:` replaces its negated window clause with the negation of the NEW first disjunct, character-for-character (the same folded-text discipline the surrounding comment already documents — update that comment's wording if the fold shape changes).

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_infra_converge_guards.py -q`; all green. `uv run pre-commit run -a`; `uv run ansible-playbook --syntax-check site.yml` from `infra/ansible/`.

- [ ] **Step 5: Prove the conservative branch bites** — evaluate the committed `that:` with `engine_cycle_epoch_probe` rc 0 and stdout `"1785744108\n"` (trailing newline: `trim` must save it) and with stdout `"99"` (fails the 10-digit regex → conservative). Both behaviors asserted in the tests above; confirm by flipping `regex_search('^[0-9]{10}$')` to `'^[0-9]+$'` in a scratch copy and watching `test_garbage_stdout_keeps_conservative_floor` still pass but a new short-epoch fixture fail — then state in the report why the 10-digit anchor is load-bearing (a stray short number in stdout must not become a floor).

- [ ] **Step 6: Commit**

```bash
git add infra/ansible/site.yml tests/test_infra_converge_guards.py
git commit -m "feat(config): window floor follows the journaled cycle completion when it is sooner"
```

---

### Task 7: Guard-4 skip-tags tightening

**Files:**
- Modify: `infra/ansible/site.yml` (guard `refuse an un-tagged run on the live primary`)
- Test: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Write the failing tests**

```python
# --- guard 4 tightened (spec 00083 D7): only --skip-tags forms naming engine satisfy it ----------

def _untag_guard():
    tasks = load_tasks(SITE)
    return find_task(tasks, "refuse an un-tagged run on the live primary")


def test_unrelated_skip_tags_now_refused():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": ["something-else"]}
    assert not truthy(assert_that(_untag_guard()), v)


def test_skip_tags_engine_passes():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": ["engine"]}
    assert truthy(assert_that(_untag_guard()), v)


def test_explicit_tags_still_pass():
    v = {"ansible_run_tags": ["capture"], "ansible_skip_tags": []}
    assert truthy(assert_that(_untag_guard()), v)


def test_bare_run_still_refused():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": []}
    assert not truthy(assert_that(_untag_guard()), v)
```

Wave 1 left no fixture pinning the loose any-non-empty-skip-tags pass (that looseness is exactly the registered gap), so nothing existing needs inverting — just add the four tests above and confirm the rest of the guard-4 tests stay green.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_infra_converge_guards.py -q -k "untag or skip_tags"`; new tests FAIL.

- [ ] **Step 3: Implement** — change the guard's `that:` to:

```yaml
        that: ansible_run_tags != ['all'] or 'engine' in ansible_skip_tags
```

and its fail_msg's last sentence to name the three accepted forms: `--tags capture`, `--tags engine`, or `--skip-tags engine` (the existing wording already lists exactly these — keep it, it is now literally true).

- [ ] **Step 4: Run to verify pass** — full guard file green; `pre-commit run -a`; syntax-check `site.yml`.

- [ ] **Step 5: Commit**

```bash
git add infra/ansible/site.yml tests/test_infra_converge_guards.py
git commit -m "fix(config): guard 4 accepts only skip-tags forms that actually exclude the engine"
```

---

### Task 8: Liquidations pin-probe rc split

**Files:**
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (stat probe + unreadable assert before the grep probe; decision guard's `when:` reworked)
- Test: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Write the failing tests**

```python
# --- liquidations rc split (spec 00083 D9): absent file stands down, unreadable file refuses -----

def _liq_readable_guard():
    tasks = load_tasks(OPS)
    return find_task(tasks, "liquidations — an unreadable compose file is a fault, never a first-provision skip")


def _liq_decision_guard():
    tasks = load_tasks(OPS)
    return find_task(tasks, "liquidations — require an explicit roll-after/defer decision on a repin")


def test_unreadable_compose_refuses():
    v = {"ops_image_digest": "sha256:" + "ab" * 32,
         "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": False}}}
    assert not truthy(assert_that(_liq_readable_guard()), v)


def test_readable_compose_passes_the_readability_guard():
    v = {"ops_image_digest": "sha256:" + "ab" * 32,
         "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": True}}}
    assert truthy(assert_that(_liq_readable_guard()), v)


def test_absent_file_skips_both_guards():
    v = {"ops_image_digest": "sha256:" + "ab" * 32,
         "ops_liquidations_compose_stat": {"stat": {"exists": False}}}
    for guard in (_liq_readable_guard(), _liq_decision_guard()):
        conds = " and ".join("(%s)" % c for c in when_conditions(guard))
        assert not truthy(conds, v)


def test_decision_guard_engages_when_file_exists():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": True}},
        "ops_liquidations_pin_probe": {"rc": 1, "stdout": ""},
        "liquidations_decision": "",
    }
    conds = " and ".join("(%s)" % c for c in when_conditions(_liq_decision_guard()))
    assert truthy(conds, v)
    assert not truthy(assert_that(_liq_decision_guard()), v)  # empty stdout + no decision -> refuse
```

Two existing wave-1 tests need syncing: the one pinning the decision guard's `rc != 2` stand-down is superseded by `test_absent_file_skips_both_guards` (rewrite it away), and `test_liquidations_guard_skips_a_digestless_converge`'s live case must gain the new `ops_liquidations_compose_stat` fixture (`{"stat": {"exists": True, "readable": True}}`) or it fails on the reworked `when:`. Name both in the report.

- [ ] **Step 2: Run to verify failure** — `-k liq`; new tests FAIL.

- [ ] **Step 3: Implement** — in the ops role, insert BEFORE `probe — the digest the deployed liquidations compose file pins`:

```yaml
- name: probe — the deployed liquidations compose file (existence vs readability)
  ansible.builtin.stat:
    path: "{{ ops_compose_dir }}/compose.yaml"
  register: ops_liquidations_compose_stat
  check_mode: false
  when: ops_image_digest is defined

# spec 00083 D9: grep answered 2 for BOTH "absent" (legitimate first-provision stand-down) and
# "present but unreadable" (a permission fault on the very file whose pin this converge would
# move). The stat probe splits them: absent skips, unreadable refuses.
- name: liquidations — an unreadable compose file is a fault, never a first-provision skip
  ansible.builtin.assert:
    that: ops_liquidations_compose_stat.stat.readable | default(false)
    fail_msg: >-
      {{ ops_compose_dir }}/compose.yaml exists but cannot be read — a permission fault on the very
      file whose pin this converge would move. Fix its ownership/mode first; neither roll-after nor
      defer addresses an unreadable pin.
  when: >-
    ops_image_digest is defined
    and ops_liquidations_compose_stat.stat.exists | default(false)
```

Gate the grep probe on existence (`when: ops_image_digest is defined and ops_liquidations_compose_stat.stat.exists | default(false)`), and change the decision guard's `when:` from `… and ops_liquidations_pin_probe.rc != 2` to `… and ops_liquidations_compose_stat.stat.exists | default(false)`; rewrite the guard's `rc != 2` comment to describe the stat-based split (the old comment's reasoning is now implemented one task up).

- [ ] **Step 4: Run to verify pass** — full guard file green; `pre-commit run -a`; from `infra/ansible/`: `uv run ansible-playbook --syntax-check site.yml`.

- [ ] **Step 5: Commit**

```bash
git add infra/ansible/roles/ops/tasks/main.yml tests/test_infra_converge_guards.py
git commit -m "fix(config): liquidations pin probe distinguishes an unreadable compose file from an absent one"
```

---

### Task 9: `mutate-probe.sh` hermeticity

**Files:**
- Modify: `infra/scripts/mutate-probe.sh`
- Test: `tests/test_mutate_probe.py`

**Interfaces:**
- Produces: new exit codes — rc 8 sandbox-seeding failure, rc 9 cleanup-restore failure (pristine copy KEPT); the no-op-abort message names `control sed` vs `mutation sed`. Header contract lists 2/3/4/5/6/7/8/9. Wave-1 signal-safety semantics untouched.

- [ ] **Step 1: Write the failing tests**

```python
def test_seeding_failure_is_rc8_not_usage(tmp_path):
    """A repo with no commits makes `git archive HEAD` fail — that must be rc 8, distinct from
    usage (rc 2), and must not leave a temp dir behind."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    target = tmp_path / "mod.py"
    target.write_text("VALUE = 1\n")
    # no commit at all — HEAD is unborn
    r = run(
        ["--sandbox", "--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 2/", "--mutation", "s/1/3/", "--", "true"],
        cwd=tmp_path,
    )
    assert r.returncode == 8
    assert "seeding" in r.stderr.lower()


def test_cleanup_cp_failure_is_rc9_and_keeps_pristine(tmp_path):
    """Signal mid-mutation with the TARGET FILE read-only, so the cleanup cp fails: rc must be 9,
    the stderr must say KEPT, and the pristine copy must SURVIVE (it is the only way back).

    Built on wave-1's slow-probe idiom (cold-review C2): fast on pristine/control content, marker +
    sleep only on the MUTATED content, so the kill window is unambiguous. `chmod 0444` goes on the
    FILE — overwriting needs write permission on the file, not its directory. killpg + re-send,
    exactly like the wave-1 signal test (bash defers trapped signals during foreground commands).
    Assumes a non-root test run (root ignores file modes)."""
    target = make_repo(tmp_path)
    marker = tmp_path / "mutated-seen"
    probe = tmp_path / "probe.sh"
    probe.write_text(
        "#!/bin/sh\n"
        f"if grep -q 'VALUE = 9' mod.py; then touch {marker}; sleep 30; fi\n"
        "grep -q 'VALUE = 1' mod.py\n"
    )
    probe.chmod(0o755)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "slow"], check=True)
    stderr_file = tmp_path / "stderr.txt"
    with stderr_file.open("w") as err:
        proc = subprocess.Popen(
            [str(SCRIPT), "--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 2/",
             "--mutation", "s/VALUE = 1/VALUE = 9/", "--", "./probe.sh"],
            cwd=tmp_path, stderr=err, start_new_session=True,
        )
        for _ in range(200):
            if marker.exists():
                break
            time.sleep(0.05)
        else:
            proc.kill()
            raise AssertionError("mutation phase never observed")
        os.chmod(target, 0o444)  # the cleanup cp to $file now fails
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    break
                os.killpg(proc.pid, signal.SIGTERM)
                time.sleep(0.05)
            rc = proc.wait(timeout=5)
        finally:
            os.chmod(target, 0o644)
    assert rc == 9
    err_text = stderr_file.read_text()
    assert "KEPT" in err_text
    kept = re.search(r"KEPT at (\S+)", err_text)
    assert kept and Path(kept.group(1)).exists()  # the pristine copy genuinely survived
    Path(kept.group(1)).unlink()  # leave no temp behind


def test_noop_control_names_the_control(tmp_path):
    target = make_repo(tmp_path)
    r = run(["--file", "mod.py", "--control", "s/NO-MATCH/x/", "--mutation", "s/VALUE = 1/VALUE = 9/", "--", "./probe.sh"], cwd=tmp_path)
    assert r.returncode == 6
    assert "control sed" in r.stderr


def test_noop_mutation_names_the_mutation(tmp_path):
    target = make_repo(tmp_path)
    r = run(["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 2/", "--mutation", "s/NO-MATCH/x/", "--", "./probe.sh"], cwd=tmp_path)
    assert r.returncode == 6
    assert "mutation sed" in r.stderr
```

(`make_repo` and `SCRIPT` already exist in the file, and its probe-runner helper is `run(args, cwd)` — use its real signature, not a new one. `test_noop_mutation_aborts` is superseded by the two named-phase tests — replace it. Import `time`/`signal`/`os`/`re`/`Path` as needed at the top.)

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_mutate_probe.py -q`; the four new/changed tests FAIL.

- [ ] **Step 3: Implement** — three edits to `infra/scripts/mutate-probe.sh`:

(a) seeding (in the `--sandbox` branch):

```bash
  work="$(mktemp -d)"
  if ! git archive HEAD | tar -x -C "$work"; then
    echo "mutate-probe: sandbox seeding FAILED (git archive HEAD | tar) — no verdict; nothing was mutated." >&2
    exit 8
  fi
  cd "$work"
```

(b) cleanup — the restore-failure path keeps the pristine copy and exits 9; the happy path is unchanged:

```bash
cleanup() {
  if [[ $cleaned -eq 1 ]]; then return 0; fi   # INT/TERM handlers are followed by EXIT — run once
  cleaned=1
  if [[ $mutated -eq 1 && -n "$pristine" && -f "$pristine" ]]; then
    if ! cp "$pristine" "$file"; then
      # KEEP the pristine copy — it is the only way back to the unmutated content.
      echo "mutate-probe: cleanup restore FAILED — $file may still carry the mutation; pristine copy KEPT at $pristine" >&2
      if [[ -n "$work" ]]; then rm -rf "$work"; fi
      exit 9
    fi
  fi
  if [[ -n "$work" ]]; then rm -rf "$work"; fi
  if [[ -n "$pristine" ]]; then rm -f "$pristine"; fi
}
```

(c) `apply` gains a phase name and the message uses it; both call sites update:

```bash
apply() {   # apply <sed-expr> <phase: "control sed"|"mutation sed">
  mutated=1   # BEFORE the write: a signal landing between sed and the flag would strand the file
  sed -i "$1" "$file"
  if cmp -s "$pristine" "$file"; then
    echo "mutate-probe: $2 '$1' did not change $file — a no-op sed proves nothing. Fix the expression." >&2
    exit 6
  fi
  purge
}
```

with `apply "$control" "control sed"` and `apply "$mutation" "mutation sed"`, and the header comment's usage line gaining `| rc 8 seeding failed | rc 9 cleanup restore failed (pristine kept)`.

- [ ] **Step 4: Run the FULL battery** — `uv run pytest tests/test_mutate_probe.py -q` (all, including wave-1's signal tests, seeding test, and baseline gate): all green. Run the signal test 10× in a loop to re-prove flake-freedom: `for i in $(seq 10); do uv run pytest tests/test_mutate_probe.py::test_signal_during_probe_restores_the_target_before_cleaning -q || break; done`.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/mutate-probe.sh tests/test_mutate_probe.py
git commit -m "fix(infra): mutate-probe exit codes are hermetic and the no-op abort names its phase"
```

---

### Task 10: `git-mv-guard.sh` coverage

**Files:**
- Modify: `.claude/hooks/git-mv-guard.sh`
- Test: `tests/test_git_mv_guard.py`

**Interfaces:**
- Produces: the hook resolves the repo dir from `git -C <dir> mv` and from a leading `cd <dir> &&` prefix; unresolvable dirs (shell variables, command substitution, backticks) emit a one-line NOTE on stderr + exit 2; plain `git mv` keeps process-cwd behavior; commit split claude-kind vs test unchanged from wave 1 (two commits).

- [ ] **Step 1: Write the failing tests.** The file's existing harness is a `rm_state_repo` FIXTURE and a `run_hook(repo, payload_json_str)` helper — neither fits the new tests as-is (cold-review I5). First, mechanical refactor with the existing 12 tests staying green: extract the fixture's body into a plain function `make_rm_state_repo(path)` (keeping its self-asserting `RM ` premise) and have the fixture call it; extend `run_hook` to `run_hook(payload: dict, cwd: Path)` (JSON-encode inside; adapt the existing call sites). Then add:

```python
def test_dash_c_form_warns_against_the_named_repo(tmp_path):
    """RM state lives in a DIFFERENT directory than the hook's cwd — `git -C <dir> mv` must be
    judged against <dir>, not the process cwd."""
    other = tmp_path / "other-repo"
    other.mkdir()
    make_rm_state_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    r = run_hook({"tool_input": {"command": f"git -C {other} mv old.txt new.txt"}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "new.txt" in r.stderr


def test_cd_prefix_form_warns_against_the_named_repo(tmp_path):
    other = tmp_path / "other-repo"
    other.mkdir()
    make_rm_state_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    r = run_hook({"tool_input": {"command": f"cd {other} && git mv old.txt new.txt"}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "new.txt" in r.stderr


def test_unresolvable_dir_notes_instead_of_wrong_repo(tmp_path):
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    make_rm_state_repo(clean_cwd)  # RM state in the PROCESS cwd — the note must NOT warn from it
    r = run_hook({"tool_input": {"command": 'git -C "$WORKDIR" mv old.txt new.txt'}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "could not" in r.stderr.lower()
    assert "old.txt" not in r.stderr  # no porcelain from the wrong repo


def test_dash_c_to_a_non_repo_stays_silent(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = run_hook({"tool_input": {"command": f"git -C {empty} mv a b"}}, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == "" and r.stdout == ""
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_git_mv_guard.py -q`; the new tests FAIL (plain-cwd behavior warns from the wrong repo / misses -C).

- [ ] **Step 3: Implement** — replace the python extraction and the case-match in `.claude/hooks/git-mv-guard.sh` (keep the file's header comment, `set -euo pipefail`, and the stderr/exit-2 block) with:

```bash
input="$(cat)"
analysis="$(printf '%s' "$input" | python3 -c '
import json, re, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    print("none")
    sys.exit(0)

m = re.search(r"\bgit\s+(?:-C\s+(\"[^\"]*\"|\x27[^\x27]*\x27|\S+)\s+)?mv\b", cmd)
if not m:
    print("none")
    sys.exit(0)

def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27":
        return s[1:-1]
    return s

d = None
if m.group(1):
    d = unquote(m.group(1))
else:
    cds = re.findall(r"(?:^|&&|;)\s*cd\s+(\"[^\"]*\"|\x27[^\x27]*\x27|\S+)", cmd[: m.start()])
    if cds:
        d = unquote(cds[-1])
if d is None:
    print("warn\t.")
elif any(ch in d for ch in "$`"):
    print("note")
else:
    print("warn\t" + d)
' 2>/dev/null || echo none)"

mode="${analysis%%$'\t'*}"
dir="${analysis#*$'\t'}"
case "$mode" in
  none) exit 0 ;;
  note)
    echo "git-mv-guard: NOTE — a git mv ran with a directory this guard could not resolve (variable or substitution in the path); check 'git status' there yourself for RM entries (rename staged over unstaged edits)." >&2
    exit 2 ;;
esac
rm_lines="$(git -C "$dir" status --porcelain 2>/dev/null | grep -E '^RM ' || true)"
[[ -z "$rm_lines" ]] && exit 0
```

(The warn block below it is unchanged. A `-C` pointing at a non-repo makes `git status` fail → empty `rm_lines` → silent exit 0, matching the original behavior for the process cwd.)

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_git_mv_guard.py -q`; all green (old 12 + new 4). Re-run the wave-1 mutation kill-probe (`^RM ` → `^ZZ ` in a copy): the warn tests must fail against the dead copy.

- [ ] **Step 5: Commit — two commits (staged-kind: claude vs test)**

```bash
git add .claude/hooks/git-mv-guard.sh
git commit -m "claude(config): git-mv-guard resolves -C and cd-prefixed forms to the right repo"
git add tests/test_git_mv_guard.py
git commit -m "test(config): prove the guard judges the named repo and notes unresolvable dirs"
```

---

### Task 11: End-to-end gate

- [ ] Run `uv run pytest tests/test_converge_sh.py tests/test_vault_pass_guard.py tests/test_ops_postverify.py tests/test_panel_regenerate.py tests/test_infra_converge_guards.py tests/test_mutate_probe.py tests/test_git_mv_guard.py tests/test_internal_terms_not_operator_visible.py -q` — all green.
- [ ] Run `uv run pre-commit run -a` — clean.
- [ ] From `infra/ansible/`: `uv run ansible-playbook --syntax-check site.yml bootstrap.yml` — clean.
- [ ] Run the full suite once: `uv run pytest` — green (the data-dependent regression tests run if `data/ohlc-full` is present).

---

### Task 12: Closeout (orchestrator-owned — recorded here as tasks, not pre-written)

- [ ] The `capture-deploys.md` shrink list (protected set — per-edit owner sign-offs): the `--limit`/preview lines → `converge.sh` pointer; the panel-generation section's mechanized steps → `zcrypto-panel-regenerate` pointer (judgment sentences stay); the ops verify-by-outcome bullet → `ops-postverify.sh` pointer; the Ansible-secrets line gains the vault-pass refusal pointer; the engine-parity "no assert enforces engine parity yet" qualifiers come OUT (D5 landed).
- [ ] T0111: wave-2 items → `## Done so far` (the genesis item recorded as already-landed, measured); status stays `partial`; remainder = the attended ops-host drills for `converge.sh` + `zcrypto-panel-regenerate`, with `ripe_when:` a maintenance window; index sync.
- [ ] `agent-ops.md`: offer the owner the grafana-query bullet gaining an `ops-postverify.sh` pointer (spec D12) — an explicit sign-off item beside the capture-deploys list.
- [ ] Decisions log (phase 6): the three scope/confirm/shrink rulings.
- [ ] Iterations-history entry (phase 6), numbers measured at branch end, not drafted mid-branch.
