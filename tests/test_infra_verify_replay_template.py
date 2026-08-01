"""Guard: the ops verify-replay runner must publish the counts its alerting now reads, and must
ping the dead-man on RUN success rather than on exit code (spec 00077 D5).

The pre-00077 shape gated the ping on `rc == 0`. Once any bad hour exists `rc` is 1 forever, so the
ping is withheld forever and healthchecks.io pages forever -- the same defect the exit-code alert
had, in a second channel. These tests exist to keep that from coming back.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's own Jinja defaults, matching
`test_infra_archive_pull_template.py`."""

import logging
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import jinja2
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.archive import command as command_mod
from cli.archive.replay import Census, ReplayResult

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
    "ops_verify_replay_state_subdir": "verify-replay-state",
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
        "ops_verify_replay_replayed_hours",
        "ops_verify_replay_reused_hours",
        "ops_verify_replay_pending_hours",
        "ops_verify_replay_duration_seconds",
        "ops_verify_replay_audit_mismatches",
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


def test_only_the_checkpoint_dir_is_writable():
    """The checkpoint needs a `:rw` mount; the archive it certifies must NOT get one.

    `/data` carries the reconciled overlay this sweep verifies -- an instrument that can write to
    what it audits can heal its own findings away, and the container runs as the same uid that owns
    the tree. So the state dir gets its OWN narrow mount and `/data` stays `:ro`; widening `/data`
    to `:rw` (the one-character "fix" for a checkpoint permission error) must fail here.

    Asserted on the joined docker-run command, not on the whole render: the mount strings also
    appear in prose, so a substring search over the file passes on a comment alone."""
    out = _render()
    joined = out.replace("\\\n", " ")
    cmd = next(ln for ln in joined.splitlines() if "archive verify-replay" in ln and not ln.strip().startswith("#"))
    data = CONTEXT["ops_data_dir"]
    state = f"{data}/{CONTEXT['ops_verify_replay_state_subdir']}"
    assert f'-v "{data}:/data:ro"' in cmd, f"the overlay must stay read-only: {cmd}"
    assert ":/data:rw" not in cmd, f"/data must never be writable -- the instrument would be able to edit what it verifies: {cmd}"
    assert f'-v "{state}:/state:rw"' in cmd, f"the checkpoint dir needs its own writable mount: {cmd}"
    assert "--state-dir /state" in cmd, f"the runner must engage incremental mode: {cmd}"
    # The mount alone is inert without the flag, and the flag alone fails the run (the CLI's
    # write-failure path withholds the summary) -- so both are pinned, and against the SAME command.


def _sed(expr: str, log: str) -> str:
    """The template's own `sed -n <expr> "$replay_log" | tail -1`, over the whole captured log.

    Whole log, not one line: production runs every expression over a file holding the failing-hour
    lines, both census twins and both summary twins at once, so a pattern that collides with a
    NEIGHBOURING line is exactly the drift worth catching -- and `tail -1` is what decides the
    winner when one does."""
    out = subprocess.run(["sed", "-n", expr], input=log, capture_output=True, text=True).stdout.splitlines()
    return out[-1].strip() if out else ""


def _parse_seds(rendered: str) -> dict[str, str]:
    """Every field the template parses, derived FROM the template: {field: sed expression}.

    Derived, never listed here, so a sixth field added to the runner with no coverage fails the
    field-set assertion below instead of being silently skipped -- the `00077` defect in its general
    form (there, covering `failed=` silently dropped `hours=`, and renaming the CLI's `hours=` then
    shipped green while node_exporter rejected the whole textfile)."""
    exprs: dict[str, str] = {}
    for m in re.finditer(r"sed -n '([^']*)'", rendered):
        expr = m.group(1)
        field = re.search(r"s/\.\*([a-z_0-9]+)=\\\(", expr)
        assert field, f"sed expression does not follow the established field idiom, so no field can be derived: {expr!r}"
        # Case-sensitivity is load-bearing, not incidental: every failing-hour line reads
        # `FAILED  anchored=...`, so an `I`-flagged `failed=` pattern would start matching hours.
        assert expr.endswith("/p"), (
            f"sed expression carries a flag after /p (case-insensitivity would collide with FAILED): {expr!r}"
        )
        exprs[field.group(1)] = expr
    return exprs


# One production-shaped log: a currently-failing hour, both census twins (echoed then logged), both
# summary twins (echoed then logged). Every value distinct, so a sed pointed at the wrong field
# fails on the value rather than passing by coincidence.
_REAL_LOG = "\n".join(
    (
        "ETH/EUR  2026-07-14 03:00  FAILED  anchored=False ordered=True checksum=True replay=True rows=12 msgs=12",
        "verify-replay census replayed=288 reused=5712 audited=25 mismatches=0 pending=3 evicted=1 duration_s=1381",
        "2026-08-01 03:41:59,001 INFO zcrypto.archive.command [command.py:988] - verify-replay census "
        "replayed=288 reused=5712 audited=25 mismatches=0 pending=3 evicted=1 duration_s=1381",
        "replayed 6003 hour(s): 6001 ok, 2 failed",
        "2026-08-01 03:41:59,002 INFO zcrypto.archive.command [command.py:1012] - verify-replay complete hours=6003 ok=6001 failed=2",
    )
)
_REAL_LOG_EXPECTED = {
    "hours": "6003",
    "failed": "2",
    "replayed": "288",
    "reused": "5712",
    "pending": "3",
    "duration_s": "1381",
    "mismatches": "0",
}

_STUB_RESULT = ReplayResult(
    pair="BTC/EUR",
    hour=datetime(2026, 7, 14, 2, tzinfo=UTC),
    rows=1,
    messages=1,
    anchored=True,
    ts_ordered=True,
    checksum_present=True,
    replay_ok=True,
    error=None,
)


def _cli_log_lines(caplog: pytest.LogCaptureFixture, argv: list[str]):
    """Invoke the real CLI and return `(result, the log lines it ACTUALLY emitted)`.

    Task 1's ordering hazard: `cli/logging/config.py` flips propagate=False on the "zcrypto" logger
    on the CLI's first-ever invocation, and `caplog` only auto-attaches to an ALREADY
    non-propagating logger at fixture setup -- so a session whose first CLI call is this very test
    would otherwise capture nothing. Attach the handler to "zcrypto" directly so the assertion holds
    regardless of test order/selection (same fix as
    `test_cli_verify_replay_failed_hour_logs_at_warning_not_error` in test_archive_replay.py)."""
    zcrypto_logger = logging.getLogger("zcrypto")
    zcrypto_logger.addHandler(caplog.handler)
    caplog.clear()
    try:
        with caplog.at_level(logging.INFO, logger="zcrypto.archive.command"):
            result = CliRunner().invoke(app, argv)
    finally:
        zcrypto_logger.removeHandler(caplog.handler)
    return result, [r.getMessage() for r in caplog.records]


def test_the_parse_matches_the_clis_actual_log_format(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Run the template's own seds over lines in the CLI's REAL format, so wording drift on either
    side fails here. Formats from cli/archive/command.py's two `logger.info` calls in verify_replay.

    Two checks, for two kinds of drift. (1) the TEMPLATE side, over a hardcoded log built from
    today's known-good format. (2) the CLI side: an earlier version asserted a literal format
    string was a substring of the emitter's whole source text -- the reviewer proved that
    satisfiable by prose: rename the live `logger.info` call to something else entirely and leave
    the OLD literal sitting in an adjacent comment, and the textual check still passed (review
    round 3, finding 4). Made executable instead: run the real CLI command through `CliRunner`,
    capture the REAL records via `caplog`, and feed their actual `getMessage()` through the same
    seds -- a rename anywhere in the live call, comment loophole included, then changes what is
    actually parsed, not just what text sits nearby.

    EVERY parsed field is covered, and the field list is derived from the template (`_parse_seds`)
    rather than listed here: round 3's version extracted only the `failed=` expression, so renaming
    the CLI's `hours=%d` to `total=%d` left every test green while `hours_total` went empty in
    production -- a valueless printf, which makes node_exporter reject the WHOLE textfile and drop
    every series (review round 4)."""
    sed_exprs = _parse_seds(_render())
    assert sorted(sed_exprs) == sorted(_REAL_LOG_EXPECTED), (
        f"the template parses {sorted(sed_exprs)} but this test covers {sorted(_REAL_LOG_EXPECTED)} -- "
        f"a parsed field with no proof against the CLI's real output is the 00077 defect"
    )

    for field, expected in _REAL_LOG_EXPECTED.items():
        got = _sed(sed_exprs[field], _REAL_LOG)
        assert got == expected, f"the template's sed did not extract {field}={expected} from the CLI's real output, got {got!r}"

    # (2): stub the heavier replay computation (already covered by tests/test_archive_replay.py) so
    # only the CLI's own census/summary formatting is under test, then run the real command the way
    # the runner does -- with `--state-dir`, which is what makes it print a census at all.
    census = Census(replayed=288, reused=5712, audited=25, audit_mismatches=(), pending=3, evicted=1, duration_s=1381.7)
    monkeypatch.setattr(command_mod.replay_mod, "verify_replay_incremental", lambda *a, **kw: ([_STUB_RESULT], census))
    result, lines = _cli_log_lines(
        caplog, ["archive", "verify-replay", "/unused-primary-root", "--state-dir", str(tmp_path / "state")]
    )

    assert result.exit_code == 0, result.output
    assert len([ln for ln in lines if ln.startswith("verify-replay census")]) == 1, lines
    assert len([ln for ln in lines if ln.startswith("verify-replay complete")]) == 1, lines
    live_log = "\n".join(lines)
    # One stubbed result, all ok -> hours=1 ok=1 failed=0, beside the stub census's own numbers.
    # Equality, not truthiness: an empty sed match must read as a failure, since empty is exactly
    # what production would print into a `%d` and node_exporter rejects the whole file over.
    live_expected = {
        "hours": "1",
        "failed": "0",
        "replayed": "288",
        "reused": "5712",
        "pending": "3",
        "duration_s": "1381",
        "mismatches": "0",
    }
    assert sorted(live_expected) == sorted(sed_exprs)
    for field, expected in live_expected.items():
        live_got = _sed(sed_exprs[field], live_log)
        assert live_got == expected, (
            f"the template's sed did not extract {field}={expected} from the CLI's ACTUAL output {live_log!r}, got {live_got!r}"
        )

    # The audit-mismatch shape, live: the census IS printed (with the mismatch count) while the
    # summary is withheld -- which is why `mismatches` is the one census series the runner must NOT
    # gate on run_ok, and why `run_ok` must keep deriving from the summary alone.
    mismatched = Census(
        replayed=0,
        reused=4,
        audited=4,
        audit_mismatches=("BTC/EUR 2026-07-14 02:00", "ETH/EUR 2026-07-14 03:00"),
        pending=0,
        evicted=0,
        duration_s=12.0,
    )
    monkeypatch.setattr(command_mod.replay_mod, "verify_replay_incremental", lambda *a, **kw: ([_STUB_RESULT], mismatched))
    result, lines = _cli_log_lines(
        caplog, ["archive", "verify-replay", "/unused-primary-root", "--state-dir", str(tmp_path / "state")]
    )

    assert result.exit_code == 2, result.output
    mismatch_log = "\n".join(lines)
    assert _sed(sed_exprs["mismatches"], mismatch_log) == "2", (
        f"the mismatch count must be parseable off the CLI's real census line: {mismatch_log!r}"
    )
    assert _sed(sed_exprs["failed"], mismatch_log) == "", "the summary must stay withheld, so run_ok reads 0"
    assert _sed(sed_exprs["hours"], mismatch_log) == "", "the summary must stay withheld, so run_ok reads 0"


def _val(text: str, name: str) -> str:
    """One series' published value, read out of a rendered textfile."""
    return next(ln for ln in text.splitlines() if ln.startswith(name)).split()[1]


def _bash_harness(tmp_path):
    """Return `run(docker_stub, seed) -> (rc, textfile)`: writes `seed` as the previous run's
    textfile, stubs `docker` with `docker_stub`, and executes the REAL rendered script under bash.

    Executing the script beats re-implementing its logic in Python: the carry-forward, the run_ok
    gate and the atomic publish are all shell, and only shell can prove them. The healthcheck URL is
    rendered empty so the ping never attempts a real network call, and the textfile path is
    redirected under `tmp_path` so a mis-render can never write to the live ops path."""
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

    def run(stub: str, seed: str) -> tuple[int, str]:
        docker_stub.write_text(stub)
        docker_stub.chmod(0o755)
        prom.write_text(seed)
        proc = subprocess.run([bash, "-c", script], capture_output=True, text=True, env=env)
        return proc.returncode, prom.read_text()

    return run


def test_a_broken_run_carries_forward_and_flags_run_ok(tmp_path):
    """Spec 00077's Verification promises exactly this: 'failed_hours carries forward when the run
    breaks; run_ok is 0 exactly when the summary does not parse.' No committed test executed that
    block -- both were one-time manual proofs (review round 2, finding 5). Simplifying
    `failed_hours="${prev_failed:-0}"` to a literal `0` passes every OTHER test here and silently
    re-arms the false-page defect D3 exists to prevent.

    Ports archive-pull's executed-block idiom (`test_a_failed_run_still_writes_every_series`): stub
    `docker` so the rendered script's OWN `docker run` call produces each shape, and run the real
    script under bash against a pre-seeded textfile, rather than re-implementing its logic in
    Python."""
    harness = _bash_harness(tmp_path)

    def _run(stub: str, seed: str) -> str:
        rc, written = harness(stub, seed)
        # 0 admitted deliberately (review round 3, finding 1): the CLI's own no-canonical-hours path
        # (case (c) below) is rc 0 with no summary -- not a shape to filter out here.
        assert rc in (0, 1, 137), f"unexpected script rc {rc}"
        return written

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

    # (c) docker exits 0 with NO parseable summary -- the CLI's own real no-canonical-hours path
    # (`typer.echo("no canonical book hours found"); return`, rc 0). Review round 3, finding 1: this
    # is the exact case round 1's `last_success` gate exists for -- an unmounted or empty NAS bind
    # reads as "no canonical hours", and dropping `&& [ "$run_ok" -eq 1 ]` from that gate (leaving
    # `rc -eq 0` alone) advances last_success to now right beside the run_ok=0 CRITICAL page.
    written_c = _run("#!/usr/bin/env bash\necho 'no canonical book hours found'\nexit 0\n", written_b)
    assert _val(written_c, "ops_verify_replay_run_ok") == "0", "run_ok must be 0 on the no-canonical-hours case"
    assert _val(written_c, "ops_verify_replay_failed_hours") == "2", "failed_hours was not carried forward"
    assert _val(written_c, "ops_verify_replay_hours_total") == "10", "hours_total was not carried forward"
    assert _val(written_c, "ops_verify_replay_last_success_timestamp") == "1753700000", (
        "last_success advanced on rc=0/no-summary -- the exact defect round 1's gate exists to prevent"
    )


def test_the_census_series_carry_forward_on_the_run_ok_gate(tmp_path):
    """The census series are gated on the SUMMARY, exactly like `failed_hours` -- never on whether a
    census line was found.

    Measured across nine real CLI runs: a census is emitted on an audit mismatch (rc 2) while the
    run is broken, and it reads entirely normally there (`replayed=0 reused=4 …`) because the
    mismatch count is the only field that betrays it. So "a census was printed" is neither
    necessary nor sufficient for "the sweep completed": publishing those numbers would render a
    broken night as a small quiet one, and a sentinel 0 would make the next good night look like a
    jump and fire the new-breakage rule falsely -- the same D3 reasoning `failed_hours` carries.

    `audit_mismatches` is the deliberate exception and is asserted as such: it is taken FRESH
    whenever a census exists, because the run it must be visible on is precisely the one where the
    summary is withheld. Gating it on run_ok would carry a stale 0 over the only condition it
    exists to trace."""
    run = _bash_harness(tmp_path)

    seed = (
        "ops_verify_replay_failed_hours 1\n"
        "ops_verify_replay_hours_total 6003\n"
        "ops_verify_replay_replayed_hours 7\n"
        "ops_verify_replay_reused_hours 7\n"
        "ops_verify_replay_pending_hours 7\n"
        "ops_verify_replay_duration_seconds 7\n"
        "ops_verify_replay_audit_mismatches 0\n"
    )

    # (a) census + summary -- the healthy nightly shape. Every census value is taken FRESH.
    rc_a, written_a = run(
        "#!/usr/bin/env bash\n"
        "echo 'verify-replay census replayed=288 reused=5712 audited=25 mismatches=0 pending=3 evicted=1 duration_s=1381'\n"
        "echo 'verify-replay complete hours=6003 ok=6003 failed=0'\n"
        "exit 0\n",
        seed,
    )
    assert rc_a == 0
    assert _val(written_a, "ops_verify_replay_run_ok") == "1"
    assert _val(written_a, "ops_verify_replay_replayed_hours") == "288", "the NEW count must be used, not the seed"
    assert _val(written_a, "ops_verify_replay_reused_hours") == "5712"
    assert _val(written_a, "ops_verify_replay_pending_hours") == "3"
    assert _val(written_a, "ops_verify_replay_duration_seconds") == "1381"
    assert _val(written_a, "ops_verify_replay_audit_mismatches") == "0"

    # (b) census only, reporting mismatches -- the audit-mismatch run (rc 2, summary withheld).
    # Seeded from (a)'s own output, so this proves carry-forward chains across runs.
    rc_b, written_b = run(
        "#!/usr/bin/env bash\n"
        "echo 'verify-replay census replayed=0 reused=4 audited=4 mismatches=2 pending=0 evicted=0 duration_s=12'\n"
        "exit 2\n",
        written_a,
    )
    assert rc_b == 2
    assert _val(written_b, "ops_verify_replay_run_ok") == "0", "a census is not a summary -- run_ok must still read 0"
    assert _val(written_b, "ops_verify_replay_failed_hours") == "0", "failed_hours must carry forward on a census-only run"
    assert _val(written_b, "ops_verify_replay_hours_total") == "6003", "hours_total must carry forward on a census-only run"
    assert _val(written_b, "ops_verify_replay_replayed_hours") == "288", "replayed_hours took a broken run's census"
    assert _val(written_b, "ops_verify_replay_reused_hours") == "5712", "reused_hours took a broken run's census"
    assert _val(written_b, "ops_verify_replay_pending_hours") == "3", "pending_hours took a broken run's census"
    assert _val(written_b, "ops_verify_replay_duration_seconds") == "1381", "duration_seconds took a broken run's census"
    assert _val(written_b, "ops_verify_replay_audit_mismatches") == "2", (
        "the mismatch count must be published FRESH -- run_ok=0 alone cannot tell a mismatch from a crash"
    )

    # (c) no output at all -- a crash before the CLI printed anything. Every series carries forward,
    # the mismatch count included: zeroing it here would read as "the mismatch cleared".
    rc_c, written_c = run("#!/usr/bin/env bash\nexit 137\n", written_b)
    assert rc_c == 137
    assert _val(written_c, "ops_verify_replay_run_ok") == "0"
    assert _val(written_c, "ops_verify_replay_replayed_hours") == "288"
    assert _val(written_c, "ops_verify_replay_reused_hours") == "5712"
    assert _val(written_c, "ops_verify_replay_pending_hours") == "3"
    assert _val(written_c, "ops_verify_replay_duration_seconds") == "1381"
    assert _val(written_c, "ops_verify_replay_audit_mismatches") == "2", "a censusless run must not clear the mismatch count"


def test_the_design_introduces_no_arithmetic():
    """The carry-forward is an assignment, never arithmetic -- deliberately, so archive-pull's
    octal trap (a bare $(( )) reading 08 as base 8, leaving the var UNSET under `set -u` and
    aborting before the mv) cannot arise here. If a future edit adds arithmetic it must carry 10#
    on both operands, and this test is where that decision gets revisited."""
    out = _render()
    for expr in re.findall(r"\$\(\(([^)]*)\)\)", out):
        assert "10#" in expr, f"arithmetic introduced without a base-10 guard: $(( {expr} ))"
