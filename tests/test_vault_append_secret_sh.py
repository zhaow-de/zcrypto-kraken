"""`infra/scripts/vault-append-secret.sh`, driven against scratch vault files with values drawn at run time: a stub `uv`
answers `uv run ansible-vault encrypt_string` with a block carrying the key and the byte length of its stdin, and one
case runs the real `ansible-vault` under a scratch password."""

from __future__ import annotations

import os
import pty
import secrets
import select
import shlex
import string
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


def test_the_value_is_appended_as_one_block_with_no_newline_entered(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE)
    record = (tmp_path / "uv-record").read_text(encoding="utf-8")
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr, vault=vault.read_text(encoding="utf-8"), argv=record)
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{_KEY}: appended\n", "")
    assert record == f"run ansible-vault encrypt_string --stdin-name {_KEY}\n"
    assert vault.read_text(encoding="utf-8") == _BEFORE + _block(_KEY, len(value))
    assert vault.stat().st_mode & 0o777 == 0o640


def test_an_inherited_xtrace_is_turned_off_before_the_value_is_read(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE, extra={"SHELLOPTS": "xtrace"})
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr)
    assert leaked == []
    assert (done.returncode, done.stdout, done.stderr) == (0, f"{_KEY}: appended\n", "+ set +x\n")


@pytest.mark.parametrize(
    "off_shape",
    [lambda v: v[:-1], lambda v: v + "x", lambda v: "x" + v, lambda v: "hcr_" + v[4:], lambda v: ""],
    ids=["short", "trailing-extra", "leading-extra", "other-prefix", "empty"],
)
def test_a_value_off_the_shape_is_refused_before_the_encryption_runs(tmp_path, off_shape):
    vault = _vault(tmp_path, _BEFORE)
    value = off_shape(_value())
    done = _run(tmp_path, value, str(vault), _KEY, _SHAPE)
    leaked = _leaks(value, stdout=done.stdout, stderr=done.stderr) if value else []
    assert leaked == []
    assert done.returncode == 2 and done.stdout == ""
    assert _KEY in done.stderr and _SHAPE in done.stderr
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
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin", "typed", "vault.yml"]


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


def test_the_value_typed_at_a_terminal_is_not_echoed(tmp_path):
    vault = _vault(tmp_path, _BEFORE)
    value = _value()
    master, slave = pty.openpty()
    try:
        echo_at_start = bool(termios.tcgetattr(slave)[3] & termios.ECHO)
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
        while termios.tcgetattr(slave)[3] & termios.ECHO and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        silenced = not termios.tcgetattr(slave)[3] & termios.ECHO
        if silenced:
            os.write(master, value.encode() + b"\n")
        else:
            proc.kill()
        out, err = proc.communicate(timeout=10)
        terminal = b""
        while select.select([master], [], [], 0.2)[0]:
            terminal += os.read(master, 4096)
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
