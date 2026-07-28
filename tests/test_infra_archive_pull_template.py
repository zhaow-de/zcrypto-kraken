"""Guard: `archive-pull.sh.j2` renders to the ops writer cycle's shell script, and its own header
records that a Jinja comment once ended a backslash continuation mid-flags — producing valid bash
whose `if` condition silently became "--mint: command not found", which `bash -n` cannot catch.
So rendering is pinned here, and the assertions read the rendered text rather than the template.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's own Jinja defaults, matching
`test_infra_compose_templates.py`."""

import re
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/ops/templates/archive-pull.sh.j2"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

# `bool` is an Ansible filter, absent from plain Jinja -- the template's own comment calls the cast
# LOAD-BEARING, so the shim must preserve the string/bool distinction it exists to catch.
_ENV.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() in {"true", "yes", "1", "on"}

CONTEXT = {
    "ops_textfile_dir": "/var/lib/node_exporter/textfile",
    "ops_nas_mount": "/mnt/zhao-crypto",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_archive_pull_healthcheck_url": "https://hc-ping.example/abc",
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "c" * 64,
    "ops_uid": 998,
    "ops_gid": 998,
    "ops_reconcile_mint": False,
    "ops_reconcile_min_gap_seconds": 30,
    "ops_reconcile_window_hours": 48,
}


def _rendered() -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**CONTEXT)


def test_the_rendered_script_is_valid_bash():
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - bash is present on every dev and CI image we run
        pytest.skip("bash not available")
    proc = subprocess.run([bash, "-n"], input=_rendered(), text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr


def test_the_repair_count_is_exported_as_a_monotone_total():
    """T0043: the sweep exits 0 on a repair and the next run reports 0, so a per-run gauge would
    erase the evidence. The exported series must therefore ADD to what the file already holds."""
    r = _rendered()
    assert "zcrypto_trade_backfill_hours_repaired_after_loss_total" in r
    assert re.search(r"prev_repaired=\$\(awk\s+'/\^zcrypto_trade_backfill_hours_repaired_after_loss_total/", r), (
        "the previous total must be read back, or the counter resets every run"
    )
    assert "backfill_repaired_total=$(( ${prev_repaired:-0} + ${backfill_repaired:-0} ))" in r


def test_the_repair_count_parse_matches_what_the_cli_actually_prints():
    """The parse reads a log line, so it breaks silently if that line's wording drifts. Rather than
    re-implement the sed in Python, run the real one over a line built from the CLI's own format
    string -- a wording change on either side then fails here."""
    sed = shutil.which("sed")
    if sed is None:  # pragma: no cover - sed is present on every image we run
        pytest.skip("sed not available")
    m = re.search(r"backfill_repaired=\$\(sed -n '([^']+)'", _rendered())
    assert m, "the repair-count parse is missing from the rendered script"

    for emitter in (REPO / "cli/archive/command.py", REPO / "cli/trades/backfill.py"):
        assert "hours_repaired_after_loss=" in emitter.read_text(), f"{emitter.name} no longer prints the field"

    sample = "trade backfill complete pairs=3 hours_minted=1 hours_repaired_after_loss=7 errors=0"
    out = subprocess.run([sed, "-n", m.group(1)], input=sample, text=True, capture_output=True)
    assert out.stdout.strip() == "7", f"parse yielded {out.stdout!r} from {sample!r}"

    # Zero must parse as 0, not as "no match" -- the total would silently stop advancing otherwise.
    zero = subprocess.run(
        [sed, "-n", m.group(1)], input=sample.replace("after_loss=7", "after_loss=0"), text=True, capture_output=True
    )
    assert zero.stdout.strip() == "0"


def test_a_failed_run_still_writes_every_series():
    """The file is rewritten whole each run; omitting a line DELETES the series, and the existing
    staleness rule is noDataState: Alerting -- that shape already paged once (2026-07-17)."""
    r = _rendered()
    block = r[r.index('backfill_textfile="') : r.index('mv "$backfill_textfile.tmp"')]
    for series in (
        "zcrypto_trade_backfill_exit_code",
        "zcrypto_trade_backfill_last_run_timestamp",
        "zcrypto_trade_backfill_last_success_timestamp",
        "zcrypto_trade_backfill_hours_repaired_after_loss_total",
    ):
        assert f"printf '{series} " in block, f"{series} is not written unconditionally"
