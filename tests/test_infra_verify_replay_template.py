"""Guard: the ops verify-replay runner must publish the counts its alerting now reads, and must
ping the dead-man on RUN success rather than on exit code (spec 00077 D5)."""

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

# StrictUndefined is the load-bearing setting: a variable the role sets and a test omits must raise
# here, never render empty into a pin that then looks fine
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
    """spec 00077 D5 -- the dead-man ping gates on run_ok, not on the exit code.

    Assert on the literal `if` line that guards `curl`, not a substring window around it: the D5
    comment and the `ops_verify_replay_run_ok` printf line both contain the word "run_ok", so a
    loose "run_ok appears somewhere nearby" check is satisfied by prose and never inspects the
    gate."""
    out = _render()
    assert 'if [ "$run_ok" -eq 1 ] && [ -n "$URL" ]; then' in out, "the dead-man ping must gate on run_ok"


def test_the_docker_run_is_captured_not_piped():
    """`set -u` without `pipefail`: `docker run | tee` reports tee's status, so every failure
    would read as success.

    Comment lines are excluded and continuations joined before the assertion: the template's header
    comment also spells `archive verify-replay`, and the real command spans continuation lines."""
    out = _render()
    joined = out.replace("\\\n", " ")
    cmd = next(ln for ln in joined.splitlines() if "archive verify-replay" in ln and not ln.strip().startswith("#"))
    assert "|" not in cmd, f"the replay command must not be piped: {cmd}"
    assert '> "$replay_log" 2>&1' in cmd, "the replay command must capture to a file"


def test_only_the_checkpoint_dir_is_writable():
    """The checkpoint needs a `:rw` mount; NOTHING this sweep reads may get one.

    `/nas` is the unbackfillable capture archive and `/data` the reconciled overlay this sweep
    verifies -- an instrument that can write to what it audits can heal its own findings away, and
    the container runs as the same uid that owns the overlay. So the state dir gets its OWN narrow
    mount and both source mounts stay `:ro`; widening either (the one-character "fix" for a
    checkpoint permission error) must fail here."""
    out = _render()
    joined = out.replace("\\\n", " ")
    cmd = next(ln for ln in joined.splitlines() if "archive verify-replay" in ln and not ln.strip().startswith("#"))
    data = CONTEXT["ops_data_dir"]
    nas = CONTEXT["ops_nas_mount"]
    state = f"{data}/{CONTEXT['ops_verify_replay_state_subdir']}"
    assert f'-v "{nas}:/nas:ro"' in cmd, f"the capture archive must stay read-only: {cmd}"
    assert ":/nas:rw" not in cmd, f"/nas must never be writable -- it is the unbackfillable capture archive: {cmd}"
    assert f'-v "{data}:/data:ro"' in cmd, f"the overlay must stay read-only: {cmd}"
    assert ":/data:rw" not in cmd, f"/data must never be writable -- the instrument would be able to edit what it verifies: {cmd}"
    assert f'-v "{state}:/state:rw"' in cmd, f"the checkpoint dir needs its own writable mount: {cmd}"
    assert "--state-dir /state" in cmd, f"the runner must engage incremental mode: {cmd}"


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

    Derived, never listed here, so a field added to the runner with no coverage fails the field-set
    assertion below instead of being silently skipped."""
    exprs: dict[str, str] = {}
    for m in re.finditer(r"sed -n '([^']*)'", rendered):
        expr = m.group(1)
        # The parsed field is the one the CAPTURE GROUP sits on, not the first `key=` in the
        # pattern: the two summary expressions are anchored on the whole `verify-replay complete
        # hours=N ok=N failed=N` shape, so each carries literal sibling fields it does not parse.
        field = re.search(r"([a-z_0-9]+)=\\\(\[0-9\]\[0-9\]\*\\\)", expr)
        assert field, f"sed expression does not follow the established field idiom, so no field can be derived: {expr!r}"
        assert expr.startswith("s/.*") and expr.endswith(".*/" + r"\1" + "/p"), (
            f"sed expression is not a whole-line substitution capturing exactly one digit run: {expr!r}"
        )
        # Forbidden PROSPECTIVELY, not because a flag collides today: the day any line prints
        # `Failed=<n>`, a case-insensitive `failed=` would read it as the summary.
        assert expr.endswith("/p"), f"sed expression carries a flag after /p -- keep every pattern case-sensitive: {expr!r}"
        # Keyed by field, so a SECOND sed for an already-seen field would overwrite the first and
        # leave the coverage assertion below satisfied while one expression went entirely unproven.
        assert field.group(1) not in exprs, f"two seds parse {field.group(1)!r}; the later one would be invisible here: {expr!r}"
        exprs[field.group(1)] = expr
    return exprs


# One production-shaped log: a currently-failing hour, both census twins (echoed then logged), both
# summary twins (echoed then logged). Every value distinct, so a sed pointed at the wrong field
# fails on the value rather than passing by coincidence.
#
# The failing hour's `error=` carries a literal `failed=7`: that text is an interpolated exception
# repr / manifest string, never ours, so it can contain anything -- and a summary sed that matched a
# bare `failed=` would read a per-hour line as the summary.
_HOSTILE_ERROR = "OrderBookError('checksum batch failed=7 at seq 4211')"
_REAL_LOG = "\n".join(
    (
        "ETH/EUR  2026-07-14 03:00  FAILED  anchored=False ordered=True checksum=True replay=True "
        f"rows=12 msgs=12  error={_HOSTILE_ERROR}",
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

# A currently-failing hour, so the CLI's own per-hour line puts `_HOSTILE_ERROR`'s `failed=7` into
# a real run's captured output.
_HOSTILE_RESULT = ReplayResult(
    pair="ETH/EUR",
    hour=datetime(2026, 7, 14, 3, tzinfo=UTC),
    rows=12,
    messages=12,
    anchored=False,
    ts_ordered=True,
    checksum_present=True,
    replay_ok=False,
    error=_HOSTILE_ERROR,
)


def _cli_log_lines(caplog: pytest.LogCaptureFixture, argv: list[str]):
    """Invoke the real CLI and return `(result, the log lines it ACTUALLY emitted)`.

    The ordering hazard: `cli/logging/config.py` flips propagate=False on the "zcrypto" logger
    on the CLI's first-ever invocation, and `caplog` only auto-attaches to an ALREADY
    non-propagating logger at fixture setup -- so a session whose first CLI call is this very test
    would otherwise capture nothing. Attach the handler to "zcrypto" directly so the assertion holds
    regardless of test order/selection."""
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
    """The template's own seds, run over lines in the CLI's REAL format, so wording drift on either
    side fails here. Formats: `cli/archive/command.py`'s `logger.info` calls in verify_replay.

    Both sides are executed rather than read: a textual check that the CLI's source contains the
    format string is satisfied by the literal sitting in an adjacent comment, so the log lines come
    from `CliRunner` + `caplog` instead."""
    sed_exprs = _parse_seds(_render())
    assert sorted(sed_exprs) == sorted(_REAL_LOG_EXPECTED), (
        f"the template parses {sorted(sed_exprs)} but this test covers {sorted(_REAL_LOG_EXPECTED)} -- "
        f"a parsed field with no proof against the CLI's real output is the 00077 defect"
    )

    for field, expected in _REAL_LOG_EXPECTED.items():
        got = _sed(sed_exprs[field], _REAL_LOG)
        assert got == expected, f"the template's sed did not extract {field}={expected} from the CLI's real output, got {got!r}"

    # Stub the heavier replay computation so only the CLI's own census/summary formatting is under
    # test, and pass `--state-dir`, which is what makes it print a census at all.
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

    # Neither summary sed may fire on a per-hour line ALONE. That line is the whole hazard: on the
    # audit-mismatch path below it is printed and the summary is not, so a pattern matching a bare
    # `failed=` would make the hostile `error=` text the only match and publish run_ok=1 on the one
    # night the run must read as broken.
    per_hour = _REAL_LOG.splitlines()[0]
    assert _HOSTILE_ERROR in per_hour
    for field in ("failed", "hours"):
        assert _sed(sed_exprs[field], per_hour) == "", (
            f"the {field} sed fired on a per-hour line with no summary present: {per_hour!r} -- "
            f"anchor it on the summary line's own shape, not on a bare field name"
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
    monkeypatch.setattr(
        command_mod.replay_mod, "verify_replay_incremental", lambda *a, **kw: ([_STUB_RESULT, _HOSTILE_RESULT], mismatched)
    )
    result, lines = _cli_log_lines(
        caplog, ["archive", "verify-replay", "/unused-primary-root", "--state-dir", str(tmp_path / "state")]
    )

    assert result.exit_code == 2, result.output
    mismatch_log = "\n".join(lines)
    assert _sed(sed_exprs["mismatches"], mismatch_log) == "2", (
        f"the mismatch count must be parseable off the CLI's real census line: {mismatch_log!r}"
    )
    # Not vacuous: the CLI really did emit the hostile `failed=7` text on this run, so the two
    # emptiness assertions below are measured against the collision, not against its absence.
    assert "failed=7" in mismatch_log, f"the hostile error text never reached the log: {mismatch_log!r}"
    assert _sed(sed_exprs["failed"], mismatch_log) == "", "the summary must stay withheld, so run_ok reads 0"
    assert _sed(sed_exprs["hours"], mismatch_log) == "", "the summary must stay withheld, so run_ok reads 0"


def _val(text: str, name: str) -> str:
    """One series' published value, read out of a rendered textfile."""
    return next(ln for ln in text.splitlines() if ln.startswith(name)).split()[1]


def _bash_harness(tmp_path):
    """Return `run(docker_stub, seed) -> (rc, textfile)`: writes `seed` as the previous run's
    textfile, stubs `docker` with `docker_stub`, and executes the REAL rendered script under bash.

    Executed rather than re-implemented in Python: the carry-forward, the run_ok gate and the atomic
    publish are all shell. The healthcheck URL is rendered empty so the ping never attempts a real
    network call."""
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
    """failed_hours carries forward when the run breaks; run_ok is 0 exactly when the summary does
    not parse (spec 00077, Verification).

    Simplifying `failed_hours="${prev_failed:-0}"` to a literal `0` passes every OTHER test here and
    silently re-arms the false-page defect D3 exists to prevent."""
    harness = _bash_harness(tmp_path)

    def _run(stub: str, seed: str) -> str:
        rc, written = harness(stub, seed)
        # 0 admitted deliberately: the CLI's own no-canonical-hours path (case (c) below) is rc 0
        # with no summary -- not a shape to filter out here.
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

    # (c) docker exits 0 with NO parseable summary -- the CLI's own no-canonical-hours path
    # (`typer.echo("no canonical book hours found"); return`, rc 0). An unmounted or empty NAS bind
    # reads the same, and dropping `&& [ "$run_ok" -eq 1 ]` from the last_success gate (leaving
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
    census line was found; `audit_mismatches` alone is taken FRESH whenever a census exists.

    An audit mismatch prints a census while withholding the summary, and that census reads entirely
    normally (`replayed=0 reused=4 ...`) -- so publishing it would render a broken night as a small
    quiet one, while gating the mismatch count would carry a stale 0 over the only condition it
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
