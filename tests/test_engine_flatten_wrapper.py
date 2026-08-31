"""Guard: the rendered `zcrypto-flatten` wrapper starts the flatten command and not the capture
daemon, refuses to run a second live client beside a still-running engine, and writes the kill file
BEFORE it stops the unit.

Rendered through a bare jinja2 Environment with Ansible's own block settings
(`tests/test_infra_tape_bars_template.py`'s precedent), then EXECUTED against fakes on PATH
(`tests/test_converge_sh.py`'s precedent) -- the properties that matter here are orderings, and no
text assertion can see an ordering.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2"
ROLE_TASKS = REPO / "infra/ansible/roles/engine/tasks/main.yml"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

DIGEST = "sha256:" + "d" * 64
CONTEXT = {
    "engine_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "engine_image_digest": DIGEST,
    # uid/gid arrive as STRINGS from the role's getent-driven set_fact, not the ints a guess supplies.
    "engine_uid": "998",
    "engine_gid": "998",
    "engine_state_dir": "/var/lib/zcrypto-engine",
}

_FAKE = """#!/bin/sh
echo "$0 $*" >> "$LOG"
"""


def _render(**overrides) -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**{**CONTEXT, **overrides})


def _harness(tmp_path, *, state_dir=None, unit_active_calls=0, create_exec_dir=True):
    """A bin/ of fakes on PATH. `systemctl is-active` succeeds for the first `unit_active_calls`
    probes, so a unit that never goes inactive can be modelled.

    `sleep` is faked to a no-op: the wrapper's stop-wait polls once a second for its whole bound, and
    the property under test is the refusal, never the wall clock spent reaching it.

    `create_exec_dir=False` models the FRESHLY CONVERGED host: the role creates the state dir,
    store/ and journal/ and never exec/, which the engine's own kill-file writer creates lazily on
    a host that has tripped a kill. Creating it unconditionally here would put every wrapper test on
    a host that has already tripped one, which is the case the button is least often used on."""
    state = state_dir or (tmp_path / "state")
    if create_exec_dir:
        (state / "exec").mkdir(parents=True, exist_ok=True)
    else:
        state.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    counter = tmp_path / "is-active-count"

    (bin_dir / "id").write_text("#!/bin/sh\necho 0\n")
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "chown").write_text(_FAKE)
    (bin_dir / "docker").write_text(_FAKE)
    (bin_dir / "systemctl").write_text(
        "#!/bin/sh\n"
        'echo "systemctl $*" >> "$LOG"\n'
        "# the kill file must already exist by the time the unit is stopped\n"
        'if [ "$1" = "stop" ]; then [ -f "$KILLPATH" ] && echo "kill-file-present-at-stop" >> "$LOG"; fi\n'
        'if [ "$1" = "is-active" ]; then\n'
        '  n=$(cat "$COUNTER" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$COUNTER"\n'
        '  [ "$n" -le "$ACTIVE_CALLS" ] && exit 0\n'
        "  exit 3\n"
        "fi\n"
        "exit 0\n"
    )
    for name in ("id", "sleep", "chown", "docker", "systemctl"):
        p = bin_dir / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)

    script = tmp_path / "zcrypto-flatten"
    script.write_text(_render(engine_state_dir=str(state)))
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LOG": str(log),
        "COUNTER": str(counter),
        "ACTIVE_CALLS": str(unit_active_calls),
        "KILLPATH": str(state / "exec" / "kill"),
    }
    return script, state, log, env


def _run(script, env, args=()):
    return subprocess.run([str(script), *args], capture_output=True, text=True, env=env)


def _log(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def _docker_argv(log: Path) -> list[str]:
    """The argv the fake `docker` was actually invoked with. Every assertion about what the container
    is told to run reads THIS and never the rendered text: a value the wrapper holds in a shell
    variable is not a token of the render, so a text assertion hunting for one silently pins
    nothing."""
    (line,) = [entry for entry in _log(log) if "docker" in entry]
    return line.split()


def test_the_rendered_invocation_overrides_the_image_entrypoint_before_the_image(tmp_path):
    """The image's own ENTRYPOINT is the capture daemon's shell script. Without the override the
    words `engine flatten` are appended to THAT, and the container starts capture on a host whose
    engine was just stopped with positions open."""
    script, _state, log, env = _harness(tmp_path)
    assert _run(script, env).returncode == 0
    argv = _docker_argv(log)
    image = f"{CONTEXT['engine_image']}@{DIGEST}"
    assert "--entrypoint" in argv
    assert argv[argv.index("--entrypoint") + 1] == "zcrypto"
    assert image in argv
    assert argv.index("--entrypoint") < argv.index(image)
    assert argv[argv.index(image) + 1 : argv.index(image) + 3] == ["engine", "flatten"]


def test_the_container_runs_as_the_engine_account_and_names_the_state_dir(tmp_path):
    """`--user` is what keeps the journal out of root's ownership inside the engine's own control
    directory, and `--state-dir` is what keeps the button off a config mount."""
    script, state, log, env = _harness(tmp_path)
    assert _run(script, env).returncode == 0
    argv = _docker_argv(log)
    assert argv[argv.index("--user") + 1] == "998:998"
    assert argv[argv.index("--state-dir") + 1] == str(state)
    assert f"{state}:{state}" in argv  # mounted at the path it is named at


def test_the_default_invocation_writes_no_kill_file_stops_nothing_and_passes_no_execute(tmp_path):
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env)
    assert result.returncode == 0, result.stderr
    # The dry run's reads run beside a LIVE engine on the same key. Spec 00106 D1 accepts that cost
    # on condition the wrapper says so, and stdout is the only place it can.
    assert "share the trade key" in result.stdout
    assert not (state / "exec" / "kill").exists()
    assert not any(line.startswith("systemctl") for line in _log(log))
    docker_lines = [line for line in _log(log) if "docker" in line]
    assert docker_lines and "--execute" not in docker_lines[0]


def test_execute_writes_the_kill_file_before_it_stops_the_unit(tmp_path):
    """The order is the whole point: stopping first leaves a window in which a restart re-opens
    what is about to be closed."""
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env, ["--execute"])
    assert result.returncode == 0, result.stderr
    assert "flatten" in (state / "exec" / "kill").read_text()
    assert "kill-file-present-at-stop" in _log(log)
    # The ownership hand-over, asserted where the fake already records it: a root-owned kill file in
    # the engine's 0750 control directory makes the engine's own later write fail EACCES.
    assert any(line.endswith(f"chown 998:998 {state}/exec/kill") for line in _log(log))
    assert any("--execute" in line for line in _log(log) if "docker" in line)


def test_execute_creates_the_missing_exec_directory_before_writing_the_kill_file(tmp_path):
    """A freshly converged or rebuilt host has no `exec/`: the role creates only the state dir,
    store/ and journal/, and the engine's own kill-file writer is what creates it lazily — on a host
    that has already tripped a kill, which is not the host the button is pressed on. Without the
    wrapper's own mkdir the redirection dies under `set -eu` with nothing latched and the engine
    still trading."""
    script, state, log, env = _harness(tmp_path, create_exec_dir=False)
    assert not (state / "exec").exists()
    result = _run(script, env, ["--execute"])
    assert result.returncode == 0, result.stderr
    assert "flatten" in (state / "exec" / "kill").read_text()
    assert "kill-file-present-at-stop" in _log(log)


def test_execute_refuses_to_start_the_container_while_the_unit_is_still_active(tmp_path):
    """One key, one client. A flatten running beside a live engine fights it over nonces, and the
    writes are exactly where that is not acceptable."""
    script, state, log, env = _harness(tmp_path, unit_active_calls=999)
    result = _run(script, env, ["--execute"])
    assert result.returncode == 1
    assert not any("docker" in line for line in _log(log))
    assert (state / "exec" / "kill").exists()  # the latch stays; it is what stops a restart


def test_an_unknown_argument_refuses_before_anything_is_written(tmp_path):
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env, ["--dry-run"])
    assert result.returncode == 1
    assert not (state / "exec" / "kill").exists()
    assert _log(log) == [] or not any("docker" in line for line in _log(log))


def test_a_non_root_invocation_refuses(tmp_path):
    script, state, log, env = _harness(tmp_path)
    bin_dir = Path(env["PATH"].split(":")[0])
    (bin_dir / "id").write_text("#!/bin/sh\necho 1000\n")
    result = _run(script, env, ["--execute"])
    assert result.returncode == 1
    assert not (state / "exec" / "kill").exists()


def test_the_role_installs_the_wrapper_root_owned_and_not_world_readable():
    """Root-owned and 0750: a wrapper the engine account could rewrite would turn the engine's own
    compromise into a path to the trade key. Read from the PARSED task -- a substring search over
    the whole file is satisfied by any other task's owner and mode."""
    (task,) = [t for t in yaml.safe_load(ROLE_TASKS.read_text()) if "zcrypto-flatten.sh.j2" in str(t)]
    template = task["ansible.builtin.template"]
    assert template["dest"] == "/usr/local/sbin/zcrypto-flatten"
    assert template["owner"] == "root" and template["group"] == "root"
    assert template["mode"] == "0750"


def test_the_template_renders_with_nothing_left_undefined():
    """`_ENV` is `StrictUndefined`, so a `{{ name }}` this file's own CONTEXT does not carry
    RAISES rather than surviving into the output -- the assertion is that the render completes
    and produces the script. Whether the ROLE defines every name is
    `tests/test_infra_shell_templates_render.py`'s question, not this file's."""
    assert _render().startswith("#!/bin/sh")
