"""run.sh: the throwaway agent holds one deploy key when --limit names a host, every fleet key otherwise."""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "run.sh"
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess")

# `uv run ansible-vault view … <key>` prints the key's path so ssh-add's stdin names what was loaded;
# `uv run ansible-playbook …` records its argv and the ssh extra-args it was handed.
FAKE_UV = """#!/usr/bin/env bash
if [ "$2" = ansible-vault ]; then printf '%s\\n' "${@: -1}"; exit 0; fi
printf '%s\\n' "$*" > "$HARNESS/playbook.argv"
printf '%s\\n' "${ANSIBLE_SSH_EXTRA_ARGS:-}" > "$HARNESS/playbook.sshargs"
"""
FAKE_SSH_AGENT = """#!/usr/bin/env bash
[ "$1" = -s ] && echo 'SSH_AUTH_SOCK=/nonexistent; export SSH_AUTH_SOCK;'
exit 0
"""
FAKE_SSH_ADD = """#!/usr/bin/env bash
cat >> "$HARNESS/added.log"
"""


def make_harness(tmp_path):
    ansible = tmp_path / "ansible"
    (ansible / "scripts").mkdir(parents=True)
    (ansible / "files").mkdir()
    for h in HOSTS:
        (ansible / "files" / f"deploy_{h}_ed25519").write_text(f"private {h}\n")
        (ansible / "files" / f"deploy_{h}_ed25519.pub").write_text(f"public {h}\n")
    script = ansible / "scripts" / "run.sh"
    script.write_text(SCRIPT.read_text())
    (ansible / "scripts" / "vault-pass.sh").write_text("#!/usr/bin/env bash\necho x\n")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in (("uv", FAKE_UV), ("ssh-agent", FAKE_SSH_AGENT), ("ssh-add", FAKE_SSH_ADD)):
        (stubs / name).write_text(body)
    for p in (script, ansible / "scripts" / "vault-pass.sh", *stubs.iterdir()):
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return script, ansible


def run(tmp_path, args, extra_env=None):
    script, ansible = make_harness(tmp_path)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "HARNESS": str(ansible)}
    env.pop("ANSIBLE_SSH_EXTRA_ARGS", None)
    env.update(extra_env or {})
    proc = subprocess.run([str(script), *args], capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    added = [line.split()[-1] for line in (ansible / "added.log").read_text().splitlines()]
    return added, (ansible / "playbook.argv").read_text().strip(), (ansible / "playbook.sshargs").read_text().strip(), ansible


def test_a_single_host_limit_loads_that_key_alone_and_offers_only_it(tmp_path):
    added, argv, sshargs, ansible = run(tmp_path, ["site.yml", "--limit", "zaccess", "--tags", "access"])
    assert added == ["files/deploy_zaccess_ed25519"]
    assert "-o IdentitiesOnly=yes" in sshargs
    assert f"-o IdentityFile={ansible}/files/deploy_zaccess_ed25519.pub" in sshargs
    assert argv == "run ansible-playbook site.yml --limit zaccess --tags access"


def test_the_equals_form_selects_the_key_too(tmp_path):
    added, _, sshargs, _ = run(tmp_path, ["site.yml", "--limit=nas"])
    assert added == ["files/deploy_nas_ed25519"]
    assert "IdentitiesOnly=yes" in sshargs


def test_no_limit_loads_every_fleet_key_with_the_bridgehead_last(tmp_path):
    added, _, sshargs, _ = run(tmp_path, ["site.yml", "--check"])
    assert added == [f"files/deploy_{h}_ed25519" for h in HOSTS]
    assert added[-1] == "files/deploy_zaccess_ed25519"
    assert sshargs == ""


def test_a_group_or_list_limit_has_no_key_and_loads_every_fleet_key(tmp_path):
    added, _, sshargs, _ = run(tmp_path, ["site.yml", "--limit", "zcrypto,zcrypto-red"])
    assert added == [f"files/deploy_{h}_ed25519" for h in HOSTS]
    assert sshargs == ""


def test_an_operators_own_ssh_extra_args_are_kept_ahead_of_the_identity(tmp_path):
    _, _, sshargs, _ = run(tmp_path, ["site.yml", "--limit", "nas"], {"ANSIBLE_SSH_EXTRA_ARGS": "-o LogLevel=ERROR"})
    assert sshargs.startswith("-o LogLevel=ERROR -o IdentitiesOnly=yes")


def test_a_host_key_without_its_pub_falls_back_to_every_fleet_key(tmp_path):
    script, ansible = make_harness(tmp_path)
    (ansible / "files" / "deploy_nas_ed25519.pub").unlink()
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "HARNESS": str(ansible)}
    env.pop("ANSIBLE_SSH_EXTRA_ARGS", None)
    proc = subprocess.run([str(script), "site.yml", "--limit", "nas"], capture_output=True, text=True, env=env, timeout=30)
    assert proc.returncode == 0, proc.stderr
    added = [line.split()[-1] for line in (ansible / "added.log").read_text().splitlines()]
    assert added == [f"files/deploy_{h}_ed25519" for h in HOSTS]
    assert (ansible / "playbook.sshargs").read_text().strip() == ""
