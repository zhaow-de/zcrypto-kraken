# `verify-replay` new-breakage alerting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the ops `verify-replay` runner publishes `failed_hours` / `hours_total` / `run_ok`, carries `failed_hours` forward on a broken run, and gates the dead-man ping on `run_ok` instead of `rc`; the alert rules page on *new* breakage and on a broken run instead of on exit code.

**Architecture:** one Jinja template (`verify-replay.sh.j2`) gains an output capture + logfmt parse + three `printf` lines, modelled verbatim on `archive-pull.sh.j2`'s existing repair-count block. One alerts file gains two rules and loses one. One render-harness test pins the whole thing.

**Tech Stack:** bash (the rendered runner), Jinja2 (Ansible templating), pytest + jinja2 (render harness), Grafana provisioned alert rules (YAML).

## Global Constraints

- Spec of record: `docs/specs/00077-verify-replay-new-breakage-alerting-design.md`. Every step cites its D-number; invent no behavior the spec does not name.
- **No change to `cli/`.** This ships without an image rebuild; the CLI's existing `logger.info("verify-replay complete hours=%d ok=%d failed=%d", ...)` is the parse target.
- **Never pipe `docker run`.** The script sets `set -u` but NOT `pipefail`, so `docker run | tee` reports tee's status and every failure reads as success. Capture to a temp file, then `cat` it back to the journal unchanged.
- **`10#` on BOTH operands of any arithmetic.** A bare `$(( ))` reads `08` as octal; the expansion error leaves the variable UNSET and `set -u` aborts the shell at the next `printf`, so the `mv` never runs and the `.prom` keeps stale content with `exit_code` still 0.
- **Every series is written on every path.** Omitting a line deletes the series — the shape that already paged this fleet once.
- The render harness mirrors `tests/test_infra_archive_pull_template.py`: `jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)`, assertions read the RENDERED text.
- Every guard is proven by constructing the defect it names (`.claude/rules/agent-ops.md`); reading the assertion is not verification.
- Verification scope: `uv run pytest tests/test_infra_verify_replay_template.py` plus `uv run pre-commit run -a` (which runs `yamllint` over the alerts file). Do NOT run the full suite — nothing in `cli/` changes.
- Commit per task, explicit paths, `Co-Authored-By: <your actual model> <noreply@anthropic.com>` last line, never `--no-verify`.

---

### Task 1: Publish the three series and fix the ping gate

**Files:**
- Modify: `infra/ansible/roles/ops/templates/verify-replay.sh.j2`
- Create: `tests/test_infra_verify_replay_template.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the rendered runner emitting `ops_verify_replay_failed_hours`, `ops_verify_replay_hours_total`, `ops_verify_replay_run_ok`, with the ping gated on `run_ok`.

- [ ] **Step 1: Read the precedent before writing anything**

Read `infra/ansible/roles/ops/templates/archive-pull.sh.j2` lines ~160–200 — the `backfill_repaired` block. It already solves this exact problem (capture, parse a logfmt count, carry a value forward, write every series). Follow its shape; do not invent a different one. Read the current `verify-replay.sh.j2` in full.

- [ ] **Step 2: Write the failing test**

Create `tests/test_infra_verify_replay_template.py`:

```python
"""Guard: the ops verify-replay runner must publish the counts its alerting now reads, and must
ping the dead-man on RUN success rather than on exit code (spec 00077 D5).

The pre-00077 shape gated the ping on `rc == 0`. Once any bad hour exists `rc` is 1 forever, so the
ping is withheld forever and healthchecks.io pages forever -- the same defect the exit-code alert
had, in a second channel. These tests exist to keep that from coming back.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's own Jinja defaults, matching
`test_infra_archive_pull_template.py`."""

import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/ops/templates/verify-replay.sh.j2"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

CONTEXT = {
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_verify_replay_healthcheck_url": "https://hc-ping.com/deadbeef",
    "ops_nas_mount": "/mnt/zhao-crypto",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_uid": "1001",
    "ops_gid": "1001",
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "0" * 64,
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
}


def _render() -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**CONTEXT)


def test_renders_valid_bash(tmp_path):
    script = tmp_path / "verify-replay.sh"
    script.write_text(_render())
    assert subprocess.run([shutil.which("bash"), "-n", str(script)], capture_output=True).returncode == 0


@pytest.mark.parametrize("series", [
    "ops_verify_replay_failed_hours",
    "ops_verify_replay_hours_total",
    "ops_verify_replay_run_ok",
    "ops_verify_replay_exit_code",
    "ops_verify_replay_last_run_timestamp",
    "ops_verify_replay_last_success_timestamp",
])
def test_every_series_is_emitted_with_help_and_type(series):
    out = _render()
    assert f"# HELP {series} " in out, f"{series} needs a HELP line"
    assert f"# TYPE {series} " in out, f"{series} needs a TYPE line"
    assert re.search(rf"^{re.escape(series)} ", out, re.M) or f"'{series} %s\\n'" in out


def test_the_ping_gates_on_run_ok_not_on_exit_code():
    """spec 00077 D5 -- the load-bearing fix. Findings are a data fact; liveness is a run fact."""
    out = _render()
    ping = out[out.index("curl") - 400:out.index("curl") + 80]
    assert "run_ok" in ping, "the dead-man ping must gate on run_ok"
    assert not re.search(r'\[\s*"\$rc"\s+-eq\s+0\s*\]', ping), "the ping must NOT gate on rc"


def test_the_docker_run_is_captured_not_piped():
    """`set -u` without `pipefail`: `docker run | tee` reports tee's status, so every failure
    would read as success. The precedent (archive-pull.sh.j2) captures to a file and cats it back."""
    out = _render()
    assert "docker run" in out
    run_line = next(ln for ln in out.splitlines() if "docker run" in ln)
    assert "|" not in run_line, "docker run must not be piped"


def test_the_parse_matches_the_clis_actual_log_format():
    """Run the template's own sed over a line in the CLI's REAL format, so wording drift on either
    side fails here. Format from cli/archive/command.py's logger.info at the end of verify_replay."""
    out = _render()
    sed_expr = next(
        m.group(1) for m in re.finditer(r"sed -n '([^']*failed=[^']*)'", out)
    )
    real_line = "2026-07-31 03:41:59,001 INFO zcrypto.archive.command [command.py:912] - verify-replay complete hours=5724 ok=5724 failed=0"
    got = subprocess.run(["sed", "-n", sed_expr], input=real_line, capture_output=True, text=True).stdout.strip()
    assert got == "0", f"the template's sed did not extract failed=0 from the CLI's real line, got {got!r}"


def test_arithmetic_is_base_ten_guarded():
    """A bare $(( )) reads 08 as OCTAL; the expansion error leaves the var UNSET and `set -u`
    aborts before the mv, leaving a stale .prom with exit_code 0."""
    out = _render()
    for expr in re.findall(r"\$\(\(([^)]*)\)\)", out):
        if re.search(r"\b(failed|hours|prev)\w*\b", expr):
            assert "10#" in expr, f"base-10 guard missing in $(( {expr} ))"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_infra_verify_replay_template.py -v`
Expected: `test_renders_valid_bash` and `test_the_docker_run_is_captured_not_piped` PASS against the current template; the series tests, the ping test, the parse test and the base-ten test FAIL.

- [ ] **Step 4: Edit the template**

Model the block on `archive-pull.sh.j2`'s repair-count section. The shape:

```bash
# spec 00077 D6: capture rather than stream, so the counts can be read out, then replay the output
# to the journal unchanged. No pipe on the run itself: this script sets `set -u` but NOT pipefail,
# so `docker run | tee` would report tee's status and every failure would read as success.
replay_log="$(mktemp)"
docker run --rm --pull never \
    ... unchanged flags ...
    archive verify-replay "/nas/{{ ops_capture_subdir }}" "/data/{{ ops_reconciled_subdir }}" \
    > "$replay_log" 2>&1
rc=$?
cat "$replay_log"
```

Then parse and derive, before the textfile block:

```bash
# The CLI logs `verify-replay complete hours=N ok=X failed=Y` (logfmt) at the end of the sweep.
# Explicit digit class + last match, per archive-pull's precedent. Empty means the sweep produced
# no summary -- a crash, an EIO from the ro,soft NAS mount, or a container that never started.
failed_hours=$(sed -n 's/.*failed=\([0-9][0-9]*\).*/\1/p' "$replay_log" | tail -1)
hours_total=$(sed -n 's/.*hours=\([0-9][0-9]*\).*/\1/p' "$replay_log" | tail -1)
rm -f "$replay_log"

# D2/D3: run_ok is the mode-(iii) signal -- did the sweep COMPLETE, regardless of what it found.
# failed_hours is CARRIED FORWARD when it did not: a sentinel would make the next good run look
# like a jump and fire the new-breakage rule falsely.
prev_failed=$(awk '/^ops_verify_replay_failed_hours/ {print $2}' "$PROM" 2>/dev/null)
prev_hours=$(awk '/^ops_verify_replay_hours_total/ {print $2}' "$PROM" 2>/dev/null)
if [ -n "$failed_hours" ]; then
    run_ok=1
else
    run_ok=0
    failed_hours="${prev_failed:-0}"
    hours_total="${prev_hours:-0}"
fi
```

`last_success` keeps its existing `rc`-based rule. Add the three series to the textfile block with HELP/TYPE lines in the established wording, and change the ping condition:

```bash
# D5: gate on run_ok, NOT on rc. Once any bad hour exists rc is 1 forever; gating the ping on it
# withholds the dead-man forever and pages through healthchecks.io indefinitely -- the same defect
# the exit-code alert had, in a second channel. A sweep that completed and reported bad hours RAN.
if [ "$run_ok" -eq 1 ] && [ -n "$URL" ]; then
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_infra_verify_replay_template.py -v`
Expected: all pass. If the parse test fails, fix the **sed**, never the expected value — the CLI's format is the contract.

- [ ] **Step 6: Prove the two defects the guards name**

Per `agent-ops.md`. Both are edits to the template, reverted after:
1. Change the ping back to `[ "$rc" -eq 0 ]` → `test_the_ping_gates_on_run_ok_not_on_exit_code` must FAIL. Revert; it passes.
2. Drop `10#` from the carry-forward arithmetic (if any remains) or drop a `printf` for one series → the corresponding test must FAIL. Revert; it passes.
Record both outputs in the report.

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/ops/templates/verify-replay.sh.j2 tests/test_infra_verify_replay_template.py
git commit
```
Message: `feat(infra): publish verify-replay counts and gate the dead-man on run_ok`

---

### Task 2: Replace the exit-code rule with the two new rules

**Files:**
- Modify: `infra/grafana/alerts.yaml`

**Interfaces:**
- Consumes: the series Task 1 publishes.
- Produces: nothing later tasks consume.

- [ ] **Step 1: Read the neighbouring rules first**

Read `Ops · verify-replay non-zero exit` in full, plus one `delta()`/`increase()`-based reconciler rule, so the new rules match this file's established shape (refIds, `datasourceUid: "${GRAFANA_PROM_DS_UID}"`, threshold expression block, `noDataState`, `execErrState`, `notification_settings.receiver`).

- [ ] **Step 2: Replace the rule**

Delete `Ops · verify-replay non-zero exit`. Add, in its place:

- **`Ops · verify-replay NEW hours stopped replaying`** — `expr: "delta(ops_verify_replay_failed_hours[25h])"`, threshold `gt 0`, `for: 0s`, severity critical, receiver `metrics`. Summary must state, in operator language and without internal tokens (`.claude/rules/operator-facing-text.md`): that the canonical archive has hours that no longer replay which did not before, that a *known* bad hour does not fire this, and what to do (read the failed hours from the run's journal line, triage, and record the finding durably — an alert that ages out is not a record).
- **`Ops · verify-replay run broken`** — `expr: "ops_verify_replay_run_ok"`, threshold `lt 1`, `for: 15m`, severity critical, receiver `metrics`. Summary must distinguish this from the rule above: the sweep did not complete at all, so its findings are unknown rather than clean; likely causes are a crashed container or an `EIO` from the read-only NAS mount.

Both rules carry a comment recording that `exit_code` is deliberately no longer alerted on, and why (`00077` D1/D4), so a later reader does not "restore" it.

- [ ] **Step 3: Verify the file still parses and lints**

Run: `uv run pre-commit run -a`
Expected: clean, `yamllint` included.

Run: `uv run pytest tests/ -k alert -q`
Expected: pass — the repo's alert-guard tests (the keep-regex admission guard) must still be satisfied by the three new series names. If a guard fails because a published series is not admitted by the ops keep-regex, **that is a real finding**: fix the regex in the same commit, since an unadmitted series is dropped at remote-write and its rule reads no data forever.

- [ ] **Step 4: Commit**

```bash
git add infra/grafana/alerts.yaml
git commit
```
Message: `feat(infra): page on new verify-replay breakage and on a broken run`

---

### Task 3: Closeout

**Files:**
- Modify: `docs/iterations-history-phase6.md`
- Modify: `docs/specs/00076-continuity-instruments-design.md` (D7's superseded note gains the forward pointer to `00077`)

- [ ] **Step 1: Append the iterations-history entry** (phase 6, per `iteration-closeout`)

One bullet each: what D7's revert left owed and why the alert *meaning* was the real defect; the three series and the carry-forward reasoning; **the dead-man gate fix as the load-bearing change** (it would have survived D7 even had D7 worked); the two rules replacing one; and the fact that this needed no CLI change.

- [ ] **Step 2: Point `00076` D7's superseded note at `00077`**

One clause, so a reader who lands on the reverted decision finds where it went.

- [ ] **Step 3: Commit** — `docs(ops): iter closeout — verify-replay pages on new breakage (spec 00077)`

- [ ] **Step 4: Attended tail — the owner runs these, in this order**

Order matters: converge first so the series start flowing while `exit_code` is still the only rule; push rules second.
1. Ops converge: `--limit zcrypto-ops`, `--check --diff` first, `ops_alloy_digest` omitted, currently-running `ops_image_digest` passed.
2. `GRAFANA_SA_TOKEN=… uv run bash infra/scripts/grafana-push.sh`, then read both rules back from the API.
3. Verify by outcome at the next daily tick: all three series present, `run_ok=1`.

## Self-review

**Spec coverage.** D1 → Task 2's two rules. D2 → Task 1 Steps 4–5 + the parametrized series test. D3 → Task 1's carry-forward block and its test. D4 → Task 2. D5 → Task 1's ping change, its dedicated test, and the Step-6 constructed proof. D6 → Task 1's capture/parse block, the no-pipe test, the real-format parse test, the base-ten test. D7/D8 → nothing built, by design; recorded in the spec.

**Placeholders:** none — every step carries its code or its exact command.

**Type consistency:** the series names in Task 1's `printf` lines are the same strings Task 2's `expr` fields reference; the parametrized test enumerates them once.
