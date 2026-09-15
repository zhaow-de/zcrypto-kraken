"""`infra/scripts/zaccess-extract-client-cert.sh` writes the vaulted mTLS client bundle for a device as two 0600 files,
`zaccess-<name>.p12` and `zaccess-<name>.p12.pass`, under `--out-dir` (default `$HOME/Downloads`, name `macbook`),
and prints where each landed and the import instruction, never the passphrase. An unknown argument is usage at exit
2 before any directory exists; a vault password helper that returns nothing or fails, and a bundle that does not
decode to DER, are refused before anything is written. Driven from a copy in a scratch tree: the vault helper is a
stub, the vault a throwaway file the script's own `ZACCESS_*` overrides point at, and `uv` a PATH stub handing
`uv run python` to this interpreter."""

from __future__ import annotations

import base64
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "zaccess-extract-client-cert.sh"
_DER = bytes.fromhex("3082001a") + bytes(range(26))  # opens with the DER SEQUENCE tag the script checks for


def _tree(tmp_path: Path, *, helper: str = "echo pw", bundle: bytes = _DER, passphrase: str = "hunter2") -> Path:
    scripts = tmp_path / "infra" / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / _SCRIPT.name
    shutil.copy(_SCRIPT, script)
    ansible = tmp_path / "infra" / "ansible"
    (ansible / "scripts").mkdir(parents=True)
    (ansible / "scripts" / "vault-pass.sh").write_text(f"#!/usr/bin/env bash\n{helper}\n", encoding="utf-8")
    (ansible / "scripts" / "vault-pass.sh").chmod(0o755)
    (ansible / "tv.yml").write_text(f"p12_b64: {base64.b64encode(bundle).decode()}\np12_pass: {passphrase}\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    uv = tmp_path / "bin" / "uv"
    uv.write_text(
        f'#!/usr/bin/env bash\n[ "$1 $2" = "run python" ] || exit 9\nshift 2\nexec {shlex.quote(sys.executable)} "$@"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    return script


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    root = script.parents[2]
    env = {
        "PATH": f"{root / 'bin'}:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "ZACCESS_P12_B64_VAR": "p12_b64",
        "ZACCESS_P12_PASS_VAR": "p12_pass",
        "ZACCESS_VAULT_FILE": "tv.yml",
    }
    return subprocess.run([str(script), *args], capture_output=True, text=True, env=env)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_an_unknown_argument_is_usage_before_anything_exists(tmp_path):
    script = _tree(tmp_path)
    done = _run(script, "--name", "dev", "--bogus")
    assert done.returncode == 2 and "unknown argument: --bogus" in done.stderr
    assert not (tmp_path / "home").exists()


def test_the_bundle_and_its_passphrase_land_as_0600_files_and_the_passphrase_is_never_printed(tmp_path):
    script = _tree(tmp_path)
    out = tmp_path / "out"
    done = _run(script, "--out-dir", str(out), "--name", "dev")
    assert done.returncode == 0, done.stderr
    p12, pw = out / "zaccess-dev.p12", out / "zaccess-dev.p12.pass"
    assert p12.read_bytes() == _DER and pw.read_text(encoding="utf-8") == "hunter2\n"
    assert _mode(p12) == 0o600 and _mode(pw) == 0o600
    assert (
        f"wrote {p12} ({len(_DER)} bytes)" in done.stdout and f"wrote {pw} (passphrase, mode 0600 -- never printed)" in done.stdout
    )
    assert "next: import zaccess-dev.p12 into the browser / Keychain" in done.stdout
    assert "hunter2" not in done.stdout + done.stderr


def test_the_defaults_are_the_downloads_folder_and_the_macbook(tmp_path):
    done = _run(_tree(tmp_path))
    assert done.returncode == 0, done.stderr
    downloads = tmp_path / "home" / "Downloads"
    assert sorted(p.name for p in downloads.iterdir()) == ["zaccess-macbook.p12", "zaccess-macbook.p12.pass"]


@pytest.mark.parametrize(
    ("helper", "bundle", "message"),
    [
        ("echo pw", b"junk-not-der", "decoded bundle is not a DER PKCS#12 (wrong var or corrupt vault entry)"),
        (":", _DER, "vault password helper returned nothing"),
        ("echo 'gpg locked' >&2; exit 3", _DER, "returned non-zero exit status 3"),
    ],
)
def test_a_refusal_writes_nothing(tmp_path, helper, bundle, message):
    script = _tree(tmp_path, helper=helper, bundle=bundle)
    out = tmp_path / "out"
    done = _run(script, "--out-dir", str(out))
    assert done.returncode == 1 and message in done.stderr
    assert list(out.iterdir()) == [] and "wrote" not in done.stdout
