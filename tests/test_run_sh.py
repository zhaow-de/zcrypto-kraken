"""run.sh: the throwaway agent holds every fleet deploy key, the --limit host's first when --limit names a host,
and it is killed on every path out of the script -- the keys do not outlive the converge."""

import os
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "infra" / "ansible" / "scripts" / "run.sh"
HOSTS = ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas", "zaccess")
DEFAULT = [f"files/deploy_{h}_ed25519" for h in HOSTS]

# `uv run ansible-vault view … <key>` prints the key's path so ssh-add's stdin names what was loaded, in order;
# `uv run ansible-playbook …` records its argv and the ssh extra-args it was handed.
# The play stub is PYTHON, not bash, because the cases below turn on what the play RECEIVES: a bash stub sleeping
# in the foreground cannot report a signal, and a case that cannot observe delivery passes whether or not the
# signal arrives (it did, until this stub replaced it). `PLAYBOOK_RC` and `PLAYBOOK_SLEEP` drive the play's exit
# status and hold it open long enough to signal. Every signal it sees goes to `play.log`, and it stops on one as a
# real play does, with the shell's own convention for the status.
FAKE_UV = """#!/usr/bin/env python3
import os, signal, sys, time

H = os.environ["HARNESS"]
if len(sys.argv) > 2 and sys.argv[2] == "ansible-vault":
    print(sys.argv[-1]); sys.exit(0)
open(os.path.join(H, "playbook.argv"), "w").write(" ".join(sys.argv[1:]) + "\\n")
open(os.path.join(H, "playbook.sshargs"), "w").write(os.environ.get("ANSIBLE_SSH_EXTRA_ARGS", "") + "\\n")
log = open(os.path.join(H, "play.log"), "a", buffering=1)


def stop(sig, _frame):
    log.write("signal %s\\n" % signal.Signals(sig).name)
    sys.exit(130 if sig == signal.SIGINT else 143)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)
time.sleep(float(os.environ.get("PLAYBOOK_SLEEP", 0)))
log.write("ran to completion\\n")
sys.exit(int(os.environ.get("PLAYBOOK_RC", 0)))
"""
# `-s` hands back a PID as the real agent does, and `-k` records that it was asked to die, with the PID it read
# from the environment -- so a test sees both THAT the agent was killed and that it was this run's agent.
FAKE_SSH_AGENT = """#!/usr/bin/env bash
[ "$1" = -s ] && { echo 'SSH_AUTH_SOCK=/nonexistent; export SSH_AUTH_SOCK;'; echo 'SSH_AGENT_PID=4242; export SSH_AGENT_PID;'; }
[ "$1" = -k ] && printf 'killed pid=%s\\n' "${SSH_AGENT_PID:-none}" >> "$HARNESS/agent.log"
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


def _env(tmp_path, ansible, extra_env=None):
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}", "HARNESS": str(ansible)}
    env.pop("ANSIBLE_SSH_EXTRA_ARGS", None)
    env.update(extra_env or {})
    return env


def _kills(ansible) -> list[str]:
    log = ansible / "agent.log"
    return log.read_text().splitlines() if log.exists() else []


def _play(ansible) -> list[str]:
    """What the play saw: one line per signal it received, then how it ended."""
    log = ansible / "play.log"
    return log.read_text().splitlines() if log.exists() else []


def _signalled(tmp_path, sig):
    """run.sh in a session of its own, so a signal aimed at its pid is not the ignored-by-inheritance SIGINT a
    background job gets, then the signal, then what the play and the agent did."""
    script, ansible = make_harness(tmp_path)
    proc = subprocess.Popen(
        [str(script), "site.yml"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(tmp_path, ansible, {"PLAYBOOK_SLEEP": "10"}),
        start_new_session=True,
    )
    time.sleep(1.2)  # past the five key loads and into the play, which the stub holds open for ten seconds
    started = time.monotonic()
    os.kill(proc.pid, sig)
    proc.communicate(timeout=30)
    return proc.returncode, time.monotonic() - started, _play(ansible), _kills(ansible)


def run(tmp_path, args, extra_env=None, expect_rc=0):
    script, ansible = make_harness(tmp_path)
    proc = subprocess.run([str(script), *args], capture_output=True, text=True, env=_env(tmp_path, ansible, extra_env), timeout=30)
    assert proc.returncode == expect_rc, f"rc {proc.returncode}: {proc.stderr}"
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


# --- the agent does not outlive the run ----------------------------------------------------------
# `exec uv run ansible-playbook` replaced the shell, so the `trap … EXIT` fired on no path out of the
# script: every converge left an agent holding all five vaulted deploy keys on the workstation, and a
# lab run found eleven of them. Measured before the fix: 0 kills on a finished play, a failed play, a
# SIGINT and a SIGTERM alike.


def test_the_agent_is_killed_when_the_play_finishes(tmp_path):
    script, ansible = make_harness(tmp_path)
    proc = subprocess.run(
        [str(script), "site.yml", "--check"], capture_output=True, text=True, env=_env(tmp_path, ansible), timeout=30
    )
    assert proc.returncode == 0, proc.stderr
    assert _kills(ansible) == ["killed pid=4242"], f"the agent outlived the run: {_kills(ansible)}"


def test_a_failed_play_kills_the_agent_and_keeps_its_exit_status(tmp_path):
    """The script's value to a caller is the play's own rc -- dropping `exec` must not swallow it."""
    script, ansible = make_harness(tmp_path)
    proc = subprocess.run(
        [str(script), "site.yml"],
        capture_output=True,
        text=True,
        env=_env(tmp_path, ansible, {"PLAYBOOK_RC": "2"}),
        timeout=30,
    )
    assert proc.returncode == 2, f"rc {proc.returncode}: the play's status did not survive"
    assert _kills(ansible) == ["killed pid=4242"], f"the agent outlived a failed run: {_kills(ansible)}"


@pytest.mark.parametrize(("sig", "rc"), ((signal.SIGINT, 130), (signal.SIGTERM, 143)), ids=("SIGINT", "SIGTERM"))
def test_a_signal_stops_the_play_and_kills_the_agent(tmp_path, sig, rc):
    """`exec` gave signal delivery for free: the play WAS this process. A waiting shell has to forward, and
    without the forwarding a `kill` leaves ansible converging a production host while the operator believes they
    stopped it -- so the case asserts the play SAW the signal, not merely that the script came back."""
    status, elapsed, play, kills = _signalled(tmp_path, sig)
    assert f"signal {sig.name}" in play, f"the play never saw the signal: {play}"
    assert "ran to completion" not in play, "the play ran on after the signal -- an unsupervised converge"
    assert elapsed < 5, f"the play took {elapsed:.1f}s to stop: the signal did not cut it short"
    assert status == rc, f"rc {status}: the shell's status for a {sig.name} did not reach the caller"
    assert kills == ["killed pid=4242"], f"the agent outlived a signalled run: {kills}"
