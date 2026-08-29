"""ops-postverify.sh: verify-by-outcome as one command (spec 00083 D3).

The grafana query command is stubbed via ZCRYPTO_GRAFANA_QUERY; the stub replays canned
output keyed by which query it receives, so each check's parse path is exercised for real.
"""

import os
import re
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
  *tapebars_exit*)    printf '%s\\n' "$TB_EXIT_OUT" ;;
  *tapebars_days_gap*) printf '%s\\n' "$TB_GAP_OUT" ;;
  *tapebars_last_publish*) printf '%s\\n' "$TB_PUBLISH_OUT" ;;
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
    "TB_EXIT_OUT": "zcrypto_tapebars_exit_code\n  {host=ops} = 0",
    "TB_GAP_OUT": "zcrypto_tapebars_days_gap\n  {host=ops} = 0",
    "TB_PUBLISH_OUT": "query\n  {host=ops} = 3600",
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
    assert check_lines(r.stdout, "PASS") == 9 and check_lines(r.stdout, "FAIL") == 0


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
    assert check_lines(r.stdout, "FAIL") == 9


def test_tape_bars_nonzero_exit_fails(tmp_path):
    r = run_postverify(tmp_path, {"TB_EXIT_OUT": "zcrypto_tapebars_exit_code\n  {host=ops} = 1"})
    assert r.returncode == 1
    assert "tape-bars exit code" in r.stdout


def test_a_permanent_gap_fails(tmp_path):
    """days_gap > 0 means a settled day fell out of the re-scan window unpublished. Nothing else
    reports it: days_unhealed stops counting that day at exactly the moment it becomes permanent."""
    r = run_postverify(tmp_path, {"TB_GAP_OUT": "zcrypto_tapebars_days_gap\n  {host=ops} = 2"})
    assert r.returncode == 1
    assert "tape-bars permanent gaps" in r.stdout


def test_a_frozen_watermark_fails_even_though_the_sweep_exits_clean(tmp_path):
    """THE case last_success cannot see. A stalled healer leaves every sweep exiting 0 -- the
    not-yet-healed path is a deferral, not a failure -- so exit_code stays 0 while the dataset stops
    growing. Only publish-freshness catches it, which is why this check reads last_PUBLISH."""
    r = run_postverify(
        tmp_path,
        {"TB_PUBLISH_OUT": "query\n  {host=ops} = 200000", "TB_EXIT_OUT": "zcrypto_tapebars_exit_code\n  {host=ops} = 0"},
    )
    assert r.returncode == 1
    assert "publish freshness" in r.stdout
    assert "tape-bars exit code (0)" in r.stdout, "the sweep is clean; only freshness may fail"


def test_a_never_published_tape_bars_fails_rather_than_reading_as_fresh(tmp_path):
    """The runner emits last_publish=0 before the first publish, so time()-0 is a huge number. It
    must FAIL loudly rather than underflow into something that reads fresh."""
    r = run_postverify(tmp_path, {"TB_PUBLISH_OUT": "query\n  {host=ops} = 1786000000"})
    assert r.returncode == 1
    assert "publish freshness" in r.stdout


def test_header_containing_comparison_cannot_mint_a_value(tmp_path):
    """A header line containing `== ` must never be mistaken for a series value.

    grafana-query.py echoes the PromQL as the header line at column 0; a future query
    containing `== ` (e.g. `increase(x[2h]) == 0`) must not let the extraction pick up a
    phantom value from that header when there is no indented series line beneath it — that
    would turn a genuine `(no series)` into a false ALL PASS.
    """
    r = run_postverify(tmp_path, {"RESIDUAL_OUT": "query with increase(x[2h]) == 0\n  (no series)"})
    assert r.returncode == 1
    assert "no series" in r.stdout


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
        assert name in script  # config-selector-ok: presence only; the keep-regex fullmatch on the next line is the real assertion
        assert any(re.fullmatch(alt, name) for alt in alternatives), f"{name} not admitted by any keep regex"
        assert name.removeprefix("zcrypto_reconcile_") in exporter  # command.py assembles prefix + leg
