"""zaccess-client-cert.sh (spec 00075 D16): issue pins a leaf; absence of the PEM is revocation.
Tested against a throwaway CA -- the vault pipeline is override-injected, never touched here."""

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/zaccess-client-cert.sh"


@pytest.fixture()
def ca(tmp_path):
    key, crt = tmp_path / "ca.key", tmp_path / "ca.crt"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-keyout",
            key,
            "-out",
            crt,
            "-subj",
            "/CN=test-ca",
            "-days",
            "2",
        ],
        check=True,
        capture_output=True,
    )
    return key, crt


def _issue(tmp_path, ca, name, *extra):
    key, crt = ca
    return subprocess.run(
        [str(SCRIPT), "issue", name, "--out-dir", str(tmp_path / "leaves"), "--p12-dir", str(tmp_path), *extra],
        env={
            "PATH": "/usr/bin:/bin",
            "ZACCESS_CA_KEY_CMD": f"cat {key}",
            "ZACCESS_CA_CRT": str(crt),
            "ZACCESS_P12_PASS": "test-pass",
            "HOME": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )


def test_issue_creates_pinned_leaf_and_p12(tmp_path, ca):
    r = _issue(tmp_path, ca, "macbook")
    assert r.returncode == 0, r.stderr
    leaf = tmp_path / "leaves/macbook.pem"
    assert leaf.exists() and (tmp_path / "zaccess-macbook.p12").exists()
    verify = subprocess.run(["openssl", "verify", "-CAfile", str(ca[1]), str(leaf)], capture_output=True, text=True)
    assert verify.returncode == 0 and "OK" in verify.stdout


def test_issue_refuses_overwrite(tmp_path, ca):
    assert _issue(tmp_path, ca, "macbook").returncode == 0
    r = _issue(tmp_path, ca, "macbook")
    assert r.returncode != 0 and "exists" in r.stderr


def test_issue_fails_cleanly_on_ca_key_cmd_failure(tmp_path, ca):
    """Failure path: if CA key command fails, no PEM is left behind."""
    r = subprocess.run(
        [str(SCRIPT), "issue", "test-device", "--out-dir", str(tmp_path / "leaves"), "--p12-dir", str(tmp_path)],
        env={
            "PATH": "/usr/bin:/bin",
            "ZACCESS_CA_KEY_CMD": "false",
            "ZACCESS_CA_CRT": str(ca[1]),
            "ZACCESS_P12_PASS": "test-pass",
            "HOME": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    leaf = tmp_path / "leaves/test-device.pem"
    assert not leaf.exists()


def test_issue_bundle_integrity(tmp_path, ca):
    """Bundle integrity: .pass file has correct permissions and p12 is valid."""
    r = _issue(tmp_path, ca, "testnode")
    assert r.returncode == 0
    pf = tmp_path / "zaccess-testnode.p12.pass"
    assert pf.exists()
    # Check passphrase file mode is 0600
    mode = oct(pf.stat().st_mode)[-3:]
    assert mode == "600", f"expected mode 0600, got {mode}"
    # Verify the p12 can be opened with the passphrase
    verify = subprocess.run(
        ["openssl", "pkcs12", "-in", str(tmp_path / "zaccess-testnode.p12"), "-passin", f"file:{pf}", "-nokeys", "-noout"],
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0
