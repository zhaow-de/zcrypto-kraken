"""`infra/scripts/vault-append-secret.sh`, driven against scratch vault files with values drawn at run time: a stub `uv`
answers `uv run ansible-vault encrypt_string` with a block carrying the key and the byte length of its stdin, and one
case runs the real `ansible-vault` under a scratch password."""

from __future__ import annotations

import fcntl
import os
import pty
import secrets
import select
import shlex
import signal
import string
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "vault-append-secret.sh"
_KEY = "scratch_api_key"
_SHAPE = "hcw_[A-Za-z0-9]{28}"
_STUB_UV = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "$UV_STUB_RECORD"
env > "$UV_STUB_ENV"
n=$(wc -c)
printf '%s: !vault |\n          $ANSIBLE_VAULT;1.1;AES256\n          stdin-bytes-%s\n' "${!#}" "${n//[^0-9]/}"
"""
_DECRYPT = """
import sys
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.vault import VaultSecret, VaultSecretsContext
vault_secrets = [("default", VaultSecret(open("pw", "rb").read().strip()))]
VaultSecretsContext.initialize(VaultSecretsContext(vault_secrets))
loader = DataLoader()
loader.set_vault_secrets(vault_secrets)
data = loader.load_from_file(sys.argv[1])
print(sorted(data), data["plain_key"], str(data[sys.argv[2]]) == sys.stdin.read())
"""


def _block(key: str, nbytes: int) -> str:
    return f"{key}: !vault |\n          $ANSIBLE_VAULT;1.1;AES256\n          stdin-bytes-{nbytes}\n"


_BEFORE = "# scratch vault\n" + _block("first_key", 11) + "\n" + _block(f"{_KEY}_old", 12)
_AFTER = _block("last_key", 13)


def _value() -> str:
    return "hcw_" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(28))


def _leaks(value: str, **surfaces: str) -> list[str]:
    # Only the names of the surfaces that carry the value: bind the result to a name before asserting on it, since
    # pytest prints a call's arguments when an assertion over the call fails.
    return [name for name, text in surfaces.items() if value in text]


def _env(tmp_path: Path, tty: Path, uv: str = _STUB_UV) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "uv").write_text(uv, encoding="utf-8")
    (bin_dir / "uv").chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "UV_STUB_RECORD": str(tmp_path / "uv-record"),
        "UV_STUB_ENV": str(tmp_path / "uv-env"),
        "VAULT_APPEND_SECRET_TTY": str(tty),
    }


def _run(
    tmp_path: Path, typed: str | None, *args: str, uv: str = _STUB_UV, extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """`typed` is what the terminal answers, a line; None leaves the terminal a path that does not exist, so a
    refusal that comes before the read is the only line on stderr."""
    tty = tmp_path / "typed"
    if typed is not None:
        tty.write_text(typed + "\n", encoding="utf-8")
    return subprocess.run(
        [str(_SCRIPT), *args],
        cwd=tmp_path,
        env=_env(tmp_path, tty, uv) | (extra or {}),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )


def _vault(tmp_path: Path, text: str) -> Path:
    vault = tmp_path / "vault.yml"
    vault.write_text(text, encoding="utf-8")
    vault.chmod(0o640)
    return vault


def _stub_env(tmp_path: Path) -> str:
    path = tmp_path / "uv-env"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_the_value_is_appended_as_one_block_with_no_newline_entered(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE)
    record = (tmp_path / "uv-record").read_text(encoding="utf-8")
    leaked = _leaks(
        value,
        stdout=done.stdout,
        stderr=done.stderr,
        vault=vault.read_text(encoding="utf-8"),
        argv=record,
        environment=_stub_env(tmp_path),
    )
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{_KEY}: appended\n", "")
    assert record == f"run ansible-vault encrypt_string --stdin-name {_KEY}\n"
    assert vault.read_text(encoding="utf-8") == _BEFORE + _block(_KEY, len(value))
    assert vault.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize(("option", "stderr"), [("xtrace", "+ set +xa\n"), ("allexport", "")])
def test_an_inherited_shell_option_is_turned_off_before_the_value_is_read(tmp_path, option, stderr):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE, extra={"SHELLOPTS": option})
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr, environment=_stub_env(tmp_path))
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{_KEY}: appended\n", stderr)


def test_an_inherited_export_of_the_script_s_variables_is_dropped(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE, extra={"value": "inherited", "block": "inherited"})
    environment = _stub_env(tmp_path)
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr, environment=environment)
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{_KEY}: appended\n", "")
    assert [line for line in environment.splitlines() if line.startswith(("value=", "block="))] == []


def test_the_value_is_held_to_the_shape_exactly_as_typed(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = f" {_value()} "
    done = _run(tmp_path, value, str(vault), _KEY, f" ?{_SHAPE} ?")
    leaked = _leaks(value.strip(), stdout=done.stdout, stderr=done.stderr, vault=vault.read_text(encoding="utf-8"))
    assert leaked == []
    assert (done.returncode, done.stdout) == (0, f"{_KEY}: appended\n")
    assert vault.read_text(encoding="utf-8") == _BEFORE + _block(_KEY, len(value))


@pytest.mark.parametrize(
    "off_shape",
    [lambda v: v[:-1], lambda v: v + "x", lambda v: "x" + v, lambda v: "hcr_" + v[4:], lambda v: f" {v} "],
    ids=["short", "trailing-extra", "leading-extra", "other-prefix", "padded"],
)
def test_a_value_off_the_shape_is_refused_before_the_encryption_runs(tmp_path, off_shape):
    vault = _vault(tmp_path, _BEFORE)
    value = off_shape(_value())
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE)
    leaked = _leaks(value.strip(), stdout=done.stdout, stderr=done.stderr)
    assert leaked == []
    assert done.returncode == 2 and done.stdout == ""
    assert _KEY in done.stderr and _SHAPE in done.stderr
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


@pytest.mark.parametrize(("typed", "stderr_lines"), [("", 1), (None, 2)], ids=["empty-line", "no-terminal"])
def test_an_empty_value_is_refused_under_a_shape_that_admits_it(tmp_path, typed, stderr_lines):
    vault = _vault(tmp_path, _BEFORE)
    done = _run(tmp_path, typed, str(vault), _KEY, "[a-z]*")
    assert done.returncode == 2 and done.stdout == ""
    lines = done.stderr.splitlines()
    assert len(lines) == stderr_lines and _KEY in lines[-1]
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


def test_a_shape_that_is_not_a_regex_is_refused_before_the_value_is_read(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    done = _run(tmp_path, None, str(vault), _KEY, "hcw_[")
    assert done.returncode == 2 and done.stdout == ""
    lines = done.stderr.splitlines()
    assert len(lines) == 1 and "'hcw_['" in lines[0] and "regular expression" in lines[0]
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


def test_a_key_the_file_carries_is_refused_without_replace_and_its_block_replaced_with_it(tmp_path):
    original = _BEFORE + _block(_KEY, 5) + "\n" + _AFTER
    vault = _vault(tmp_path, original)
    refused = _run(tmp_path, None, str(vault), _KEY, _SHAPE)
    assert refused.returncode == 2 and refused.stdout == ""
    assert len(refused.stderr.splitlines()) == 1 and _KEY in refused.stderr and "--replace" in refused.stderr
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == original

    value = _value()
    replaced = _run(tmp_path, value, str(vault), _KEY, _SHAPE, "--replace")
    leaked = _leaks(value, stdout=replaced.stdout, stderr=replaced.stderr, vault=vault.read_text(encoding="utf-8"))
    assert leaked == []
    assert (replaced.returncode, replaced.stdout, replaced.stderr) == (0, f"{_KEY}: replaced\n", "")
    assert vault.read_text(encoding="utf-8") == _BEFORE + _block(_KEY, len(value)) + "\n" + _AFTER
    assert vault.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize(
    "text",
    [_BEFORE + _block(_KEY, 5) + _block(_KEY, 6) + _AFTER, "$ANSIBLE_VAULT;1.1;AES256\n6162636465666768\n" + _block(_KEY, 5)],
    ids=["carried-twice", "encrypted-whole"],
)
def test_replace_is_refused_over_a_key_carried_twice_and_over_a_file_encrypted_whole(tmp_path, text):
    vault = _vault(tmp_path, text)
    done = _run(tmp_path, None, str(vault), _KEY, _SHAPE, "--replace")
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1 and str(vault) in done.stderr
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_bytes() == text.encode()


def test_a_file_encrypted_whole_is_refused_for_an_append(tmp_path):
    text = "$ANSIBLE_VAULT;1.1;AES256\n6162636465666768\n"
    vault = _vault(tmp_path, text)
    done = _run(tmp_path, None, str(vault), _KEY, _SHAPE)
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1 and str(vault) in done.stderr
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_bytes() == text.encode()


def test_replace_for_a_key_the_file_lacks_is_refused(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    done = _run(tmp_path, None, str(vault), _KEY, _SHAPE, "--replace")
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1 and _KEY in done.stderr
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


def test_a_failed_encryption_writes_nothing_and_exits_with_its_rc(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    failing = "#!/usr/bin/env bash\ncat > /dev/null\necho 'the vault password was refused' >&2\nexit 3\n"
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE, uv=failing)
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr)
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (3, "", "the vault password was refused\n")
    assert vault.read_text(encoding="utf-8") == _BEFORE


@pytest.mark.parametrize(
    "answer", ["", "other_key: !vault |\n          $ANSIBLE_VAULT;1.1;AES256\n          00\n"], ids=["empty", "other-key"]
)
def test_an_encryptor_output_that_is_not_the_key_s_block_is_refused_before_any_write(tmp_path, answer):
    original = _BEFORE + _block(_KEY, 5) + "\n" + _AFTER
    vault = _vault(tmp_path, original)
    value = _value()
    uv = f"#!/usr/bin/env bash\ncat > /dev/null\nprintf %s {shlex.quote(answer)}\n"
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE, "--replace", uv=uv)
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr)
    assert leaked == []
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1 and _KEY in done.stderr
    assert vault.read_text(encoding="utf-8") == original


def test_a_step_failing_after_the_temp_file_exists_leaves_no_temp_file(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    env = _env(tmp_path, tmp_path / "typed")
    (tmp_path / "typed").write_text(value + "\n", encoding="utf-8")
    (tmp_path / "bin" / "mv").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    (tmp_path / "bin" / "mv").chmod(0o755)
    done = subprocess.run(
        [str(_SCRIPT), str(vault), _KEY, _SHAPE], cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True
    )
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr)
    assert leaked == []
    assert done.returncode == 1 and done.stdout == ""
    assert (tmp_path / "uv-record").exists()
    assert sorted(p.name for p in tmp_path.glob(".vault-append-secret.*")) == []
    assert vault.read_text(encoding="utf-8") == _BEFORE


def test_a_missing_file_is_refused(tmp_path):
    absent = tmp_path / "absent.yml"
    done = _run(tmp_path, None, str(absent), _KEY, _SHAPE)
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1 and str(absent) in done.stderr
    assert not (tmp_path / "uv-record").exists() and not absent.exists()


@pytest.mark.parametrize(
    "args",
    [[], [_KEY], [_KEY, _SHAPE, "--force"], ["scratch-api-key", _SHAPE], ["", _SHAPE], [_KEY, ""]],
    ids=["none", "two", "unknown-flag", "key-not-a-name", "empty-key", "empty-shape"],
)
def test_a_usage_other_than_the_contract_is_refused(tmp_path, args):
    vault = _vault(tmp_path, _BEFORE)
    done = _run(tmp_path, None, *([str(vault), *args] if args else []))
    assert done.returncode == 2 and done.stdout == ""
    assert len(done.stderr.splitlines()) == 1
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


def _echo_on(fd: int) -> bool:
    return bool(termios.tcgetattr(fd)[3] & termios.ECHO)


def _at_the_hidden_read(tmp_path: Path, vault: Path, slave: int) -> tuple[subprocess.Popen[str], bool]:
    """The script started with the pty as its terminal, and whether its echo went off within the deadline."""
    proc = subprocess.Popen(
        [str(_SCRIPT), str(vault), _KEY, _SHAPE],
        cwd=tmp_path,
        env=_env(tmp_path, Path(os.ttyname(slave))),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 5
    while _echo_on(slave) and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    return proc, not _echo_on(slave)


def _drain(master: int) -> bytes:
    out = b""
    while select.select([master], [], [], 0.2)[0]:
        out += os.read(master, 4096)
    return out


def test_the_value_typed_at_a_terminal_is_not_echoed(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    master, slave = pty.openpty()
    try:
        echo_at_start = _echo_on(slave)
        proc, silenced = _at_the_hidden_read(tmp_path, vault, slave)
        if silenced:
            os.write(master, value.encode() + b"\n")
        else:
            proc.kill()
        out, err = proc.communicate(timeout=10)
        terminal = _drain(master)
    finally:
        os.close(master)
        os.close(slave)
    leaked = _leaks(
        value, stdout=out, stderr=err, terminal=terminal.decode(errors="replace"), vault=vault.read_text(encoding="utf-8")
    )
    assert leaked == []
    assert echo_at_start and silenced
    assert (proc.returncode, out, err) == (0, f"{_KEY}: appended\n", f"{_KEY} (not echoed): \n")
    assert vault.read_text(encoding="utf-8") == _BEFORE + _block(_KEY, len(value))


def test_a_paste_of_more_than_one_line_is_refused_and_leaves_nothing_queued_for_the_shell(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value, rest = _value(), _value()
    master, slave = pty.openpty()
    try:
        proc, silenced = _at_the_hidden_read(tmp_path, vault, slave)
        if silenced:
            os.write(master, f"{value}\n{rest}\n".encode())
        else:
            proc.kill()
        out, err = proc.communicate(timeout=10)
        terminal = _drain(master)
        queued = struct.unpack("i", fcntl.ioctl(slave, termios.FIONREAD, b"\0\0\0\0"))[0]
    finally:
        os.close(master)
        os.close(slave)
    surfaces = {"stdout": out, "stderr": err, "terminal": terminal.decode(errors="replace")}
    leaked = _leaks(value, **surfaces) + _leaks(rest, **surfaces)
    assert leaked == []
    assert silenced
    assert proc.returncode == 2 and out == ""
    assert err.startswith(f"{_KEY} (not echoed): \n") and len(err.splitlines()) == 2 and _KEY in err.splitlines()[-1]
    assert queued == 0
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


@pytest.mark.parametrize("signum", [signal.SIGHUP, signal.SIGINT, signal.SIGTERM], ids=["HUP", "INT", "TERM"])
def test_a_signal_at_the_hidden_read_exits_through_the_cleanup_and_restores_the_echo(tmp_path, signum):
    vault = _vault(tmp_path, _BEFORE)
    master, slave = pty.openpty()
    try:
        proc, silenced = _at_the_hidden_read(tmp_path, vault, slave)
        proc.send_signal(signum)
        proc.communicate(timeout=10)
        echo_after = _echo_on(slave)
    finally:
        os.close(master)
        os.close(slave)
    assert silenced
    assert proc.returncode == 128 + signum
    assert echo_after
    assert not (tmp_path / "uv-record").exists()
    assert vault.read_text(encoding="utf-8") == _BEFORE


def test_the_real_ansible_vault_round_trips_the_value_whole_through_append_and_replace(tmp_path):
    (tmp_path / "pw").write_text(secrets.token_hex(16) + "\n", encoding="utf-8")
    (tmp_path / "ansible.cfg").write_text("[defaults]\nvault_password_file = pw\n", encoding="utf-8")
    vault = _vault(tmp_path, "# scratch vault\nplain_key: kept\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(f'#!/usr/bin/env bash\nshift\nexec {shlex.quote(str(Path(sys.executable).parent))}/"$@"\n')
    (bin_dir / "uv").chmod(0o755)
    tty = tmp_path / "typed"
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "LANG": "C.UTF-8", "VAULT_APPEND_SECRET_TTY": str(tty)}
    for verb, extra in (("appended", []), ("replaced", ["--replace"])):
        value = _value()
        tty.write_text(value + "\n", encoding="utf-8")
        done = subprocess.run(
            [str(_SCRIPT), str(vault), _KEY, _SHAPE, *extra],
            cwd=tmp_path,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
        read = subprocess.run(
            [sys.executable, "-c", _DECRYPT, str(vault), _KEY], cwd=tmp_path, env=env, input=value, capture_output=True, text=True
        )
        leaked = _leaks(
            value, stdout=done.stdout, stderr=done.stderr, vault=vault.read_text(encoding="utf-8"), read=read.stdout + read.stderr
        )
        assert leaked == []
        assert (done.returncode, done.stdout) == (0, f"{_KEY}: {verb}\n")
        assert (read.returncode, read.stdout) == (0, f"['plain_key', '{_KEY}'] kept True\n"), read.stderr
