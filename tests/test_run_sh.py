"""run.sh: the throwaway agent holds every fleet deploy key, the --limit host's first when --limit names a host."""

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "run.sh"
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess")
DEFAULT = [f"files/deploy_{h}_ed25519" for h in HOSTS]

# `uv run ansible-vault view … <key>` prints the key's path so ssh-add's stdin names what was loaded, in order;
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
    return added, (ansible / "playbook.argv").read_text().strip(), (ansible / "playbook.sshargs").read_text().strip()


def test_a_single_host_limit_loads_every_key_with_that_hosts_first(tmp_path):
    added, argv, sshargs = run(tmp_path, ["site.yml", "--limit", "zaccess", "--tags", "access"])
    assert added == ["files/deploy_zaccess_ed25519", *DEFAULT[:4]]
    assert sorted(added) == sorted(DEFAULT)  # the other hosts' keys stay: a play's ssh reaches more than its --limit host
    assert sshargs == ""
    assert argv == "run ansible-playbook site.yml --limit zaccess --tags access"


def test_the_equals_form_moves_the_key_too(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit=nas"])
    assert added == ["files/deploy_nas_ed25519", *[k for k in DEFAULT if "nas" not in k]]


def test_no_limit_loads_every_fleet_key_in_the_listed_order(tmp_path):
    added, _, sshargs = run(tmp_path, ["site.yml", "--check"])
    assert added == DEFAULT
    assert sshargs == ""


def test_a_group_or_list_limit_has_no_key_and_keeps_the_listed_order(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit", "zcrypto,zcrypto-red"])
    assert added == DEFAULT


def test_a_host_without_a_key_file_keeps_the_listed_order(tmp_path):
    added, _, _ = run(tmp_path, ["site.yml", "--limit", "localhost"])
    assert added == DEFAULT


def test_the_operators_ssh_extra_args_pass_through_untouched(tmp_path):
    _, _, sshargs = run(tmp_path, ["site.yml", "--limit", "nas"], {"ANSIBLE_SSH_EXTRA_ARGS": "-o LogLevel=ERROR"})
    assert sshargs == "-o LogLevel=ERROR"
