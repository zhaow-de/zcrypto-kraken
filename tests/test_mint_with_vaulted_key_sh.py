"""`infra/scripts/mint-with-vaulted-key.sh` runs the fixture minter with the vaulted trade credential in its environment
and nothing else, and is `probe-with-vaulted-key.sh` below the guard line with only the target changed. Driven from a
copy in a scratch tree, so every path it derives from its own location lands there: it refuses outside a repo root,
without the minter, and without the venv interpreter; its in-process stage refuses a vault password that cannot be
read or comes back empty, and a credential absent or empty under its names; and the minter receives `-I`, the
arguments verbatim, the two variables from the vault and the repo root as cwd. The vault helper, the vault file and
the minter are stubs -- no key, no order -- and nothing but comments sits above the guard line."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "mint-with-vaulted-key.sh"
_SIBLING = _REPO / "infra" / "scripts" / "probe-with-vaulted-key.sh"
_HARNESS = "kraken-fixture-mint.py"
_SIBLING_HARNESS = "kraken-order-semantics-probe.py"
_GUARD = "set -euo pipefail\n"
_VAULT = "kraken_trade_api_key: k-fixture\nkraken_trade_api_secret: s-fixture\n"
_STUB_HARNESS = (
    "import json, os, sys\n"
    "print(json.dumps({'argv': sys.argv[1:], 'key': os.environ.get('KRAKEN_SPOT_API_KEY'),"
    " 'secret': os.environ.get('KRAKEN_SPOT_API_SECRET'), 'isolated': sys.flags.isolated, 'cwd': os.getcwd()}))\n"
)


def _tree(
    tmp_path: Path, *, root: bool = True, harness: bool = True, venv: bool = True, helper: str = "echo pw", vault: str = _VAULT
) -> Path:
    repo = tmp_path / "repo"
    scripts = repo / "infra" / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / _SCRIPT.name
    shutil.copy(_SCRIPT, script)
    if root:
        (repo / "pyproject.toml").write_text("[project]\nname = 'scratch'\n", encoding="utf-8")
        ansible = repo / "infra" / "ansible"
        (ansible / "scripts").mkdir(parents=True)
        (ansible / "scripts" / "vault-pass.sh").write_text(f"#!/usr/bin/env bash\n{helper}\n", encoding="utf-8")
        (ansible / "scripts" / "vault-pass.sh").chmod(0o755)
        (ansible / "group_vars" / "engine_host").mkdir(parents=True)
        (ansible / "group_vars" / "engine_host" / "vault.yml").write_text(vault, encoding="utf-8")
    if harness:
        (scripts / _HARNESS).write_text(_STUB_HARNESS, encoding="utf-8")
    if venv:
        (repo / ".venv" / "bin").mkdir(parents=True)
        python = repo / ".venv" / "bin" / "python"
        python.write_text(f'#!/usr/bin/env bash\nexec {shlex.quote(sys.executable)} "$@"\n', encoding="utf-8")
        python.chmod(0o755)
    return script


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(script.parents[3])}
    )


def test_below_the_guard_line_it_is_the_probe_wrapper_with_only_the_target_changed():
    mine = _SCRIPT.read_text(encoding="utf-8").partition(_GUARD)
    sibling = _SIBLING.read_text(encoding="utf-8").partition(_GUARD)
    assert mine[1] == _GUARD and sibling[1] == _GUARD
    assert mine[2].replace(_HARNESS, _SIBLING_HARNESS) == sibling[2]
    assert all(line.startswith("#") for line in mine[0].splitlines() if line.strip())


def test_outside_a_repo_root_is_refused(tmp_path):
    script = _tree(tmp_path, root=False)
    done = _run(script)
    assert done.returncode == 2 and f"refusing: {script.parents[2]} is not the repo root" in done.stderr


def test_a_missing_minter_is_refused(tmp_path):
    script = _tree(tmp_path, harness=False)
    done = _run(script)
    assert done.returncode == 2 and f"refusing: {script.parent / _HARNESS} is missing" in done.stderr


def test_a_missing_venv_interpreter_is_refused(tmp_path):
    script = _tree(tmp_path, venv=False)
    done = _run(script)
    assert done.returncode == 2 and "is missing -- run 'uv sync'" in done.stderr


@pytest.mark.parametrize(
    ("helper", "vault", "message"),
    [
        ("echo 'gpg locked' >&2; exit 1", _VAULT, "refusing: the vault password could not be read -- gpg locked"),
        ("exit 0", _VAULT, "refusing: the vault password came back empty"),
        ("echo pw", "other: 1\n", "refusing: the trade credential is absent from the vault under the expected names"),
        (
            "echo pw",
            "- a list, not a mapping\n",
            "refusing: the trade credential is absent from the vault under the expected names",
        ),
        ("echo pw", "kraken_trade_api_key: k\nkraken_trade_api_secret: ''\n", "refusing: the vaulted trade credential is empty"),
    ],
)
def test_the_in_process_stage_refuses_before_the_minter_runs(tmp_path, helper, vault, message):
    done = _run(_tree(tmp_path, helper=helper, vault=vault), "--dry-run")
    assert done.returncode == 1 and message in done.stderr
    assert "argv" not in done.stdout


def test_the_minter_gets_the_arguments_the_credential_isolated_mode_and_the_repo_root(tmp_path):
    script = _tree(tmp_path)
    done = _run(script, "--pair", "BTC/EUR", "--dry-run")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "argv": ["--pair", "BTC/EUR", "--dry-run"],
        "key": "k-fixture",
        "secret": "s-fixture",
        "isolated": 1,
        "cwd": str(script.parents[2]),
    }
