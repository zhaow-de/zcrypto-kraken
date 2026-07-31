"""Guard: the ops verify-replay runner must publish the counts its alerting now reads, and must
ping the dead-man on RUN success rather than on exit code (spec 00077 D5).

The pre-00077 shape gated the ping on `rc == 0`. Once any bad hour exists `rc` is 1 forever, so the
ping is withheld forever and healthchecks.io pages forever -- the same defect the exit-code alert
had, in a second channel. These tests exist to keep that from coming back.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's own Jinja defaults, matching
`test_infra_archive_pull_template.py`."""

import os
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


@pytest.mark.parametrize(
    "series",
    [
        "ops_verify_replay_failed_hours",
        "ops_verify_replay_hours_total",
        "ops_verify_replay_run_ok",
        "ops_verify_replay_exit_code",
        "ops_verify_replay_last_run_timestamp",
        "ops_verify_replay_last_success_timestamp",
    ],
)
def test_every_series_is_emitted_with_help_and_type(series):
    out = _render()
    assert f"# HELP {series} " in out, f"{series} needs a HELP line"
    assert f"# TYPE {series} " in out, f"{series} needs a TYPE line"
    # %d (not just %s) is valid: node_exporter rejects the WHOLE file on one blank-value line, so
    # a count that could be empty prints as %d, which bash coerces to 0.
    assert re.search(rf"^{re.escape(series)} ", out, re.M) or re.search(rf"'{re.escape(series)} %[sd]\\n'", out)


def test_the_ping_gates_on_run_ok_not_on_exit_code():
    """spec 00077 D5 -- the load-bearing fix. Findings are a data fact; liveness is a run fact.

    Assert on the literal `if` line that guards `curl`, not a wide substring window around it: the
    D5 comment and the `ops_verify_replay_run_ok` printf line both contain the word "run_ok", so a
    loose "run_ok appears somewhere nearby" check is satisfied by prose and never actually inspects
    the gate -- deleting the gate entirely (`if [ -n "$URL" ]; then`) still passed that shape of
    assertion (review round 1, finding 1)."""
    out = _render()
    assert 'if [ "$run_ok" -eq 1 ] && [ -n "$URL" ]; then' in out, "the dead-man ping must gate on run_ok"


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
    side fails here. Format from cli/archive/command.py's logger.info at the end of verify_replay.

    The hardcoded `real_line` below only catches drift on the TEMPLATE side -- rename the CLI's
    fields and this test still passes, shipping green and surfacing only the next day as a
    run-broken CRITICAL (review round 2, finding 4). Following archive-pull's precedent
    (`test_the_repair_count_parse_matches_what_the_cli_actually_prints`), also assert the emitter
    source still contains the literal format string the parse depends on."""
    out = _render()
    sed_expr = next(m.group(1) for m in re.finditer(r"sed -n '([^']*failed=[^']*)'", out))

    emitter = REPO / "cli/archive/command.py"
    assert "verify-replay complete hours=%d ok=%d failed=%d" in emitter.read_text(), (
        f"{emitter.name} no longer prints the format string this parse depends on"
    )

    real_line = (
        "2026-07-31 03:41:59,001 INFO zcrypto.archive.command [command.py:912] - verify-replay complete hours=5724 ok=5724 failed=0"
    )
    got = subprocess.run(["sed", "-n", sed_expr], input=real_line, capture_output=True, text=True).stdout.strip()
    assert got == "0", f"the template's sed did not extract failed=0 from the CLI's real line, got {got!r}"


def test_a_broken_run_carries_forward_and_flags_run_ok(tmp_path):
    """Spec 00077's Verification promises exactly this: 'failed_hours carries forward when the run
    breaks; run_ok is 0 exactly when the summary does not parse.' No committed test executed that
    block -- both were one-time manual proofs (review round 2, finding 5). Simplifying
    `failed_hours="${prev_failed:-0}"` to a literal `0` passes every OTHER test here and silently
    re-arms the false-page defect D3 exists to prevent.

    Ports archive-pull's executed-block idiom (`test_a_failed_run_still_writes_every_series`): stub
    `docker` so the rendered script's OWN `docker run` call produces each shape, and run the real
    script under bash against a pre-seeded textfile, rather than re-implementing its logic in
    Python. The healthcheck URL is rendered empty so the ping never attempts a real network call."""
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - bash is present on every image we run
        pytest.skip("bash not available")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_stub = bin_dir / "docker"
    prom = tmp_path / "ops-verify-replay.prom"
    context = dict(CONTEXT, ops_verify_replay_healthcheck_url="")
    script = _ENV.from_string(TEMPLATE.read_text()).render(**context)
    target = '"{}/ops-verify-replay.prom"'.format(CONTEXT["ops_textfile_dir"])
    # str.replace no-ops silently on a miss, and the un-substituted target is the LIVE ops path.
    assert target in script, f"the textfile path did not match {target!r} -- the harness would write to the real path"
    script = script.replace(target, f'"{prom}"')
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def _val(text: str, name: str) -> str:
        return next(ln for ln in text.splitlines() if ln.startswith(name)).split()[1]

    def _run(stub: str, seed: str) -> str:
        docker_stub.write_text(stub)
        docker_stub.chmod(0o755)
        prom.write_text(seed)
        proc = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=env)
        assert proc.returncode in (1, 137), f"unexpected script rc, stderr: {proc.stderr}"
        return prom.read_text()

    # (a) docker (standing in for the whole CLI invocation) produces a parseable summary reporting
    # 2 bad hours out of 10 -- the CLI's own real exit path when hours failed (rc 1).
    seed_a = (
        "ops_verify_replay_failed_hours 3\nops_verify_replay_hours_total 100\nops_verify_replay_last_success_timestamp 1753700000\n"
    )
    written_a = _run("#!/usr/bin/env bash\necho 'verify-replay complete hours=10 ok=8 failed=2'\nexit 1\n", seed_a)
    assert _val(written_a, "ops_verify_replay_run_ok") == "1", "a parsed summary must set run_ok=1"
    assert _val(written_a, "ops_verify_replay_failed_hours") == "2", "the NEW count must be used, not the seed"
    assert _val(written_a, "ops_verify_replay_hours_total") == "10"
    # rc=1 (bad hours exist): the sweep RAN but was not CLEAN -- last_success must not advance.
    assert _val(written_a, "ops_verify_replay_last_success_timestamp") == "1753700000"

    # (b) docker produces NO output at all -- a crash before the CLI printed anything. Seeded from
    # (a)'s own output, so this proves carry-forward chains across runs, not just from a fixture.
    written_b = _run("#!/usr/bin/env bash\nexit 137\n", written_a)
    assert _val(written_b, "ops_verify_replay_run_ok") == "0", "run_ok must be 0 exactly when the summary is absent"
    assert _val(written_b, "ops_verify_replay_failed_hours") == "2", "failed_hours was not carried forward"
    assert _val(written_b, "ops_verify_replay_hours_total") == "10", "hours_total was not carried forward"
    assert _val(written_b, "ops_verify_replay_last_success_timestamp") == "1753700000", (
        "last_success was not carried forward on a broken run"
    )


def test_the_design_introduces_no_arithmetic():
    """The carry-forward is an assignment, never arithmetic -- deliberately, so archive-pull's
    octal trap (a bare $(( )) reading 08 as base 8, leaving the var UNSET under `set -u` and
    aborting before the mv) cannot arise here. If a future edit adds arithmetic it must carry 10#
    on both operands, and this test is where that decision gets revisited."""
    out = _render()
    for expr in re.findall(r"\$\(\(([^)]*)\)\)", out):
        assert "10#" in expr, f"arithmetic introduced without a base-10 guard: $(( {expr} ))"
