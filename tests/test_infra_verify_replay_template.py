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
