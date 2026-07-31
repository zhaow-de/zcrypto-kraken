# `verify-replay` new-breakage alerting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the ops `verify-replay` runner publishes `failed_hours` / `hours_total` / `run_ok`, carries `failed_hours` forward on a broken run, and gates the dead-man ping on `run_ok` instead of `rc`; the alert rules page on *new* breakage and on a broken run instead of on exit code.

**Architecture:** one Jinja template (`verify-replay.sh.j2`) gains an output capture + logfmt parse + three `printf` lines, modelled verbatim on `archive-pull.sh.j2`'s existing repair-count block. One alerts file gains two rules and loses one. One render-harness test pins the whole thing.

**Tech Stack:** bash (the rendered runner), Jinja2 (Ansible templating), pytest + jinja2 (render harness), Grafana provisioned alert rules (YAML).

## Global Constraints

- Spec of record: `docs/specs/00077-verify-replay-new-breakage-alerting-design.md`. Every step cites its D-number; invent no behavior the spec does not name.
- **`cli/` changes in exactly one place** (Task 1, spec D9): the per-hour failure log level. The parse target — `logger.info("verify-replay complete hours=%d ok=%d failed=%d", ...)` — is unchanged and needs no edit. Nothing else in `cli/` may move; the replay semantics are a Non-goal.
- **Never pipe `docker run`.** The script sets `set -u` but NOT `pipefail`, so `docker run | tee` reports tee's status and every failure reads as success. Capture to a temp file, then `cat` it back to the journal unchanged.
- **`10#` on BOTH operands of any arithmetic.** A bare `$(( ))` reads `08` as octal; the expansion error leaves the variable UNSET and `set -u` aborts the shell at the next `printf`, so the `mv` never runs and the `.prom` keeps stale content with `exit_code` still 0.
- **Every series is written on every path.** Omitting a line deletes the series — the shape that already paged this fleet once.
- The render harness mirrors `tests/test_infra_archive_pull_template.py`: `jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)`, assertions read the RENDERED text.
- Every guard is proven by constructing the defect it names (`.claude/rules/agent-ops.md`); reading the assertion is not verification.
- Verification scope: Task 1 touches `cli/`, so run `uv run pytest tests/test_archive_replay_command.py -q` (or the archive-command tests that exist) plus the new template test; Tasks 2-3 need only `uv run pytest tests/test_infra_verify_replay_template.py tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py -q`. `uv run pre-commit run -a` before every commit. The data-dependent full suite is not needed — no capture, engine or panel path changes.
- Commit per task, explicit paths, `Co-Authored-By: <your actual model> <noreply@anthropic.com>` last line, never `--no-verify`.

---

### Task 1: A failed hour logs at WARNING, not ERROR

**Files:**
- Modify: `cli/archive/command.py`
- Test: the archive-command test module (find it — `tests/` has the archive CLI tests; add there rather than creating a new file if one exists)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing later tasks import — but it is what makes the whole change honest, so it goes first.

- [ ] **Step 1: Find where the per-hour failure is logged, and what tests cover it**

`cli/archive/command.py`, inside `verify_replay`'s result loop: `if not result.passed:` → `logger.error("archive verify-replay: hour failed pair=%s hour=%s anchored=%s ...")`. Locate the existing tests for that command so the new test lands beside them.

- [ ] **Step 2: Write the failing test**

Assert the per-hour failure is logged at **WARNING**, and that the sweep's own summary/exception paths keep their levels. Use `caplog` at `logging.WARNING`, run `verify_replay` (or the command) over a fixture with one failing hour, and assert the record's `levelno == logging.WARNING` and that no `ERROR` record was emitted for a per-hour finding. Give the test a docstring naming exactly what it protects:

> A failed hour is a finding about DATA; the sweep reporting it is the program working. `Ops · ERROR logs` fires on any ops ERROR within 15 minutes, so logging findings at ERROR pages nightly, forever, for a hour that is already triaged — the third channel spec 00077 exists to close. Restoring `logger.error` here silently re-arms that page.

- [ ] **Step 3: Run it — must FAIL** (`levelno` is ERROR today).

- [ ] **Step 4: Change the level**

`logger.error(` → `logger.warning(` for that one call. Add a short comment citing D9 and naming the ERROR-logs channel, so the next reader sees why the level is deliberate. **Change nothing else** — not the message, not the fields, not the `failed += 1` accounting, and not any other `logger.error` in the file (the sweep's own failure paths keep ERROR by design).

- [ ] **Step 5: Run the tests — must PASS**, and confirm no other archive-command test regressed.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run -a
git add cli/archive/command.py tests/<the archive command test file>
git commit
```
Message: `fix(archive): a failed replay hour is a WARNING finding, not an ERROR fault`

---

### Task 2: Publish the three series and fix the ping gate

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
    would read as success. The precedent (archive-pull.sh.j2) captures to a file and cats it back.

    The naive form of this test cannot fail: the T0060 comment block contains the words "docker
    run", so a first-match line lookup finds prose, and the real command spans continuation lines
    so a pipe would sit on a later line anyway. Join the continuations and assert on the redirect."""
    out = _render()
    joined = out.replace("\\\n", " ")
    cmd = next(ln for ln in joined.splitlines() if "archive verify-replay" in ln and not ln.strip().startswith("#"))
    assert "|" not in cmd, f"the replay command must not be piped: {cmd}"
    assert '> "$replay_log" 2>&1' in cmd, "the replay command must capture to a file"


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


def test_the_design_introduces_no_arithmetic():
    """The carry-forward is an assignment, never arithmetic -- deliberately, so archive-pull's
    octal trap (a bare $(( )) reading 08 as base 8, leaving the var UNSET under `set -u` and
    aborting before the mv) cannot arise here. If a future edit adds arithmetic it must carry 10#
    on both operands, and this test is where that decision gets revisited."""
    out = _render()
    for expr in re.findall(r"\$\(\(([^)]*)\)\)", out):
        assert "10#" in expr, f"arithmetic introduced without a base-10 guard: $(( {expr} ))"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_infra_verify_replay_template.py -v`
Expected: `test_renders_valid_bash` and `test_the_design_introduces_no_arithmetic` PASS against the current template (the latter vacuously — today's template has no `$(( ))`, and the new shape adds none). The three new-series parametrizations, `test_the_ping_gates_on_run_ok_not_on_exit_code`, `test_the_docker_run_is_captured_not_piped` and `test_the_parse_matches_the_clis_actual_log_format` all FAIL. If any of those six passes against today's template, it is not a regression test — fix it before proceeding.

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

- [ ] **Step 6b: Rewrite the template's own header, which now lies**

`verify-replay.sh.j2`'s header block says the runner "pings the dead-man URL on a clean run only" and twice promises "rc!=0 -> the exit-code alert". After this task and Task 3 both statements are false. The repo's rule is to rewrite a stale narrative in place, never to leave it beside a correction — so update those lines to describe the run_ok gate and the two new rules. This is the one place the task's "change nothing else" instruction does NOT apply.

Also update `infra/ops/README.md`: its line "On a clean run (exit 0) each script GETs its healthchecks.io ping URL … A failed run pings nothing" is now false for this runner, and its series table should list the three new series.

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/ops/templates/verify-replay.sh.j2 tests/test_infra_verify_replay_template.py infra/ops/README.md
git commit
```
Message: `feat(infra): publish verify-replay counts and gate the dead-man on run_ok`

---

### Task 3: Replace the exit-code rule with the two new rules

**Files:**
- Modify: `infra/grafana/alerts.yaml`

**Interfaces:**
- Consumes: the series Task 2 publishes.
- Produces: nothing later tasks consume.

- [ ] **Step 1: Read the neighbouring rules first**

Read `Ops · verify-replay non-zero exit` in full, plus one `delta()`/`increase()`-based reconciler rule, so the new rules match this file's established shape (refIds, `datasourceUid: "${GRAFANA_PROM_DS_UID}"`, threshold expression block, `noDataState`, `execErrState`, `notification_settings.receiver`).

- [ ] **Step 2: Replace the rule**

Delete `Ops · verify-replay non-zero exit`. Add, in its place:

- **`Ops · verify-replay NEW hours stopped replaying`** — `expr: "delta(ops_verify_replay_failed_hours[25h])"`, threshold `gt 0`, `for: 0s`, severity critical, receiver `metrics`. Summary must state, in operator language and without internal tokens (`.claude/rules/operator-facing-text.md`): that the canonical archive has hours that no longer replay which did not before, that a *known* bad hour does not fire this, and what to do (read the failed hours from the run's journal line, triage, and record the finding durably — an alert that ages out is not a record).
- **`Ops · verify-replay run broken`** — `expr: "ops_verify_replay_run_ok"`, threshold `lt 1`, `for: 15m`, severity critical, receiver `metrics`. Summary must distinguish this from the rule above: the sweep did not complete at all, so its findings are unknown rather than clean; likely causes are a crashed container or an `EIO` from the read-only NAS mount.

Both rules pin **`noDataState: OK`** and **`execErrState: Alerting`**, matching the rule they replace and the `delta()` precedent (`zcrypto-gate-streak-reset`) — with the one-clause why: the dead-man owns liveness, so a missing series is not breakage, while a broken *evaluation* is. Do not guess these; the file also contains `noDataState: Alerting` rules and the difference has paged before. Both rules also carry a comment recording that `exit_code` is deliberately no longer alerted on, and why (`00077` D1/D4), so a later reader does not "restore" it.

- [ ] **Step 3: Verify the file still parses and lints**

Run: `uv run pre-commit run -a`
Expected: clean, `yamllint` included.

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_infra_alloy_series.py -q`
Expected: pass. (`-k alert` does NOT select the series-admission guard — that lives in `tests/test_infra_alloy_series.py`.)

- [ ] **Step 3b: Pin the three new series by name in the admission guard**

Measured: the ops keep-regex (`infra/ansible/roles/ops/files/config.alloy`) admits all three via its `ops_verify_replay_.*` wildcard, so nothing is dropped today. But two of the three are now alert-bearing, and a future narrowing of that wildcard would leave both new rules NoData → OK → **silent forever**. Follow this repo's own convention (`OPS_REQUIRED` in `tests/test_infra_alloy_series.py`, whose `zcrypto_trade_backfill_hours_repaired_after_loss_total` entry says "Admitted today only by the wildcard — pinned by name so narrowing that wildcard fails here"): add `ops_verify_replay_failed_hours`, `ops_verify_replay_hours_total` and `ops_verify_replay_run_ok` to `OPS_REQUIRED` with the same one-line reason.

Prove it bites: narrow the wildcard in a scratch copy of the regex and confirm the test fails, then restore.

- [ ] **Step 3c: Fix the dangling comment the deletion leaves**

`infra/grafana/alerts.yaml` has a comment on the panel rule reading "The second half of the verify-replay rule's finding above" — it dangles the moment the rule above is deleted. Rewrite it to stand alone.

- [ ] **Step 4: Commit**

```bash
git add infra/grafana/alerts.yaml
git commit
```
Message: `feat(infra): page on new verify-replay breakage and on a broken run`

---

### Task 4: Closeout

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
**This converge MOVES `ops_image_digest`** (Task 1 changed `cli/`), unlike the previous one — so the steps below are not the routine shape.
1. Let CI build the image from `develop` after merge; take the new digest from the build.
2. **Pull the digest on the host first** — every ops runner is `--pull never` and the role has no pull task; without it every timer exits 125.
3. **Record the new digest in `docs/reference/fleet-pins.md` BEFORE converging** — `ops_image_digest` has no repo default, so that row is the only rollback operand. Keep the outgoing digest as the `prior` value.
4. Ops converge: `--limit zcrypto-ops`, `--check --diff` first, `daemon.json` unchanged, the NEW `ops_image_digest` passed — **and `ops_alloy_digest=<the currently-running value from `fleet-pins.md`>`, because this branch edits `config.alloy`** (a comment correction only, but any edit to that file makes Alloy the subject and the drift assert refuses the converge without it). Passing the *currently-running* digest is what keeps this a config-only change with no Alloy roll.
5. **Decide the liquidations question explicitly** (spec D10): the same variable re-pins the liquidations compose, which the role never restarts — the file moves, the container does not. Either roll it (`docker compose up -d` in its project dir) or leave it deliberately pinned-but-not-rolled, and record which.
6. `GRAFANA_SA_TOKEN=… uv run bash infra/scripts/grafana-push.sh` — **push the two new rules, but do NOT prune yet** (the prune is step 8, after the series are proven). **The push upserts and never deletes** — its own comment: *"a rule removed from alerts.yaml keeps evaluating and emailing forever."* So:
   a. Read the orphan report and confirm it names **exactly** `zcrypto-ops-verify-replay-exit-nonzero` — if it names anything else, STOP and report; deleting an alert rule is not reversible from the repo.
   b. Verify both new rules read back from the API. **Leave the old rule live for now** — until the new series have a sample, no metric rule covers verify-replay at all, and the old one is the only cover there is.
7. Verify by outcome at the next daily tick — **for the whole ops tier, not just verify-replay**, because the moving digest re-ran every runner on a new image (`capture-deploys.md`): `ops_archive_pull_exit_code` and `ops_panel_exit_code` 0, `reconcile.prom` mtime advanced, reconcile counters unchanged, `hc_checks_down_total` 0. Then the subject itself: all three new series present, `run_ok=1`, the ERROR-logs rule quiet through a sweep, **and `ops_verify_replay_failed_hours == 0`**.

   That last check is not decoration and it cannot be deferred. `delta()` cannot see breakage that is already present in a series' **first** sample — a bad hour arising between the last pre-deploy sweep and this first post-deploy one is born into the baseline and the new-breakage rule will never page for it, ever. A nonzero value here must be triaged as the page it would otherwise have been.

8. **Only now prune.** Re-run with `GRAFANA_PRUNE=1`, then confirm a GET on `zcrypto-ops-verify-replay-exit-nonzero` returns 404. "The new rules exist" is not evidence the old one is gone — and deleting it before step 7 would leave a window with no metric cover at all, against an irreversible deletion.

## Self-review

**Spec coverage.** D1 → Task 3's two rules. D2 → Task 2 Steps 4–5 + the parametrized series test. D3 → Task 2's carry-forward block and its test. D4 → Task 3. D5 → Task 2's ping change, its dedicated test, and the Step-6 constructed proof. D6 → Task 2's capture/parse block, the no-pipe test, the real-format parse test, the base-ten test. D7/D8 → nothing built, by design; recorded in the spec. D9 → Task 1. D10 → Task 4 Step 4's ordered tail, including the liquidations decision.

**Placeholders:** none — every step carries its code or its exact command.

**Type consistency:** the series names in Task 2's `printf` lines are the same strings Task 3's `expr` fields reference; the parametrized test enumerates them once.
