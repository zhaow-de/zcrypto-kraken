"""Guard: the daily verify-replay must run WINDOWED (spec 00076 D7).

Unwindowed, one historical bad hour exits 1 every day forever behind a CRITICAL alert -- the
`ops_verify_replay_exit_code` rule -- which is how an operator learns to ignore it. The CLI has
had `--since` all along; only this runner omitted it.

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's Jinja defaults, matching
`test_infra_archive_pull_template.py`.
"""

import shutil
import subprocess
from pathlib import Path

import jinja2

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
    "ops_verify_replay_window_days": 7,
}


def _render() -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**CONTEXT)


def test_renders_valid_bash(tmp_path):
    script = tmp_path / "verify-replay.sh"
    script.write_text(_render())
    assert subprocess.run([shutil.which("bash"), "-n", str(script)], capture_output=True).returncode == 0


def test_the_replay_is_windowed():
    out = _render()
    assert "--since" in out, "an unwindowed daily replay pages forever on one historical bad hour"
    # The window is computed at run time, not baked at render time: a rendered date would freeze
    # on the day of the converge and silently narrow to nothing.
    assert "date -u -d" in out or "date -u --date" in out
    assert "7 days ago" in out


def test_window_days_is_configurable_and_reaches_the_command():
    out = _ENV.from_string(TEMPLATE.read_text()).render(**{**CONTEXT, "ops_verify_replay_window_days": 3})
    assert "3 days ago" in out
