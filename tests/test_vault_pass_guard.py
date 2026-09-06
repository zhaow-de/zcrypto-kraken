"""vault-pass.sh refuses `ansible-inventory --host/--list/--vars` ancestry (spec 00083 D4)."""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "vault-pass.sh"


def make_stub_sops(tmp_path):
    sops = tmp_path / "fake-sops"
    sops.write_text("#!/usr/bin/env bash\necho SOPS-RAN\n")
    sops.chmod(sops.stat().st_mode | stat.S_IXUSR)
    return sops


def run_under(tmp_path, wrapper_name, wrapper_args):
    """Run vault-pass.sh as a CHILD of a process whose cmdline is `<wrapper_name> <args>`.

    No `exec` in the wrapper: exec would replace its process image, leaving no ancestor carrying
    the banned cmdline for the walk to find."""
    wrapper = tmp_path / wrapper_name
    wrapper.write_text(f'#!/usr/bin/env bash\n"{SCRIPT}"\n')
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "ZCRYPTO_SOPS_BIN": str(make_stub_sops(tmp_path))}
    return subprocess.run([str(wrapper), *wrapper_args], capture_output=True, text=True, env=env)


def test_refuses_ansible_inventory_list(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--list"])
    assert r.returncode == 1
    assert "cleartext" in r.stderr and "--graph" in r.stderr
    assert "SOPS-RAN" not in r.stdout


def test_refuses_ansible_inventory_host(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--host", "zcrypto"])
    assert r.returncode == 1
    assert "SOPS-RAN" not in r.stdout


def test_allows_other_ancestors(tmp_path):
    r = run_under(tmp_path, "ansible-playbook", ["--list-tags"])
    assert r.returncode == 0
    assert "SOPS-RAN" in r.stdout


def test_allows_ansible_inventory_graph(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--graph"])
    assert r.returncode == 0
    assert "SOPS-RAN" in r.stdout


def test_refuses_ansible_inventory_graph_vars(tmp_path):
    r = run_under(tmp_path, "ansible-inventory", ["--graph", "--vars"])
    assert r.returncode == 1
    assert "SOPS-RAN" not in r.stdout
