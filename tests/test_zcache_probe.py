"""The zcache mesh probe the `cache_link` role installs, driven over a fixture conf and a stub `wg`. The
handshake-stale rule reads what it writes, so a peer it leaves out is a link nothing watches."""

from __future__ import annotations

import math
import os
import stat
import subprocess
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/cache_link"
SCRIPT = ROLE / "files/zcache-probe.sh"
UNIT = ROLE / "templates/zcache-probe.service.j2"

CONF = """[Interface]
Address = 10.98.0.11/24
ListenPort = 51821

[Peer]
PublicKey = AAAA
AllowedIPs = 10.98.0.1/32
Endpoint = 172.105.64.43:51821
PersistentKeepalive = 25

[Peer]
PublicKey = BBBB
AllowedIPs = 10.98.0.12/32
Endpoint = 139.162.163.39:51821
PersistentKeepalive = 25

[Peer]
PublicKey = CCCC
AllowedIPs = 10.98.0.13/32
Endpoint = 172.233.51.246:51821
PersistentKeepalive = 25
"""


def _stub_wg(tmp_path: Path, dump: str | None) -> Path:
    """A `wg` that prints `dump` for `wg show zcache0 dump`, or fails as it does on an absent interface."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    wg = bin_dir / "wg"
    body = f"cat <<'DUMP'\n{dump}DUMP\n" if dump is not None else "echo 'Unable to access interface: No such device' >&2; exit 1\n"
    wg.write_text(f'#!/usr/bin/env bash\n[ "$*" = "show zcache0 dump" ] || exit 64\n{body}')
    wg.chmod(wg.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _run(tmp_path: Path, dump: str | None, conf: str = CONF) -> tuple[subprocess.CompletedProcess[str], Path]:
    conf_path = tmp_path / "zcache0.conf"
    conf_path.write_text(conf)
    out = tmp_path / "zcache.prom"
    env = {**os.environ, "PATH": f"{_stub_wg(tmp_path, dump)}:{os.environ['PATH']}"}
    args = ["bash", str(SCRIPT), str(conf_path), str(out)]
    return subprocess.run(args, capture_output=True, text=True, check=False, env=env), out


def _series(prom: Path) -> dict[str, float]:
    return {
        name: float(value)
        for name, value in (ln.rsplit(" ", 1) for ln in prom.read_text().splitlines() if ln and not ln.startswith("#"))
    }


def _dump(*peers: tuple[str, str, int]) -> str:
    lines = ["PRIVATE\tPUBLIC\t51821\toff"]
    lines += [f"{key}\t(none)\t1.2.3.4:51821\t{ip}/32\t{latest}\t100\t200\t25" for key, ip, latest in peers]
    return "\n".join(lines) + "\n"


def _age(peer: str) -> str:
    return f'zcache_wireguard_handshake_age_seconds{{peer="{peer}"}}'


def test_each_configured_peer_gets_its_age_and_a_peer_with_no_handshake_reads_infinite(tmp_path):
    now = int(time.time())
    result, out = _run(tmp_path, _dump(("AAAA", "10.98.0.1", now - 40), ("BBBB", "10.98.0.12", 0)))
    assert result.returncode == 0, result.stderr
    series = _series(out)
    assert 40 <= series[_age("10.98.0.1")] <= 45
    assert math.isinf(series[_age("10.98.0.12")])  # listed by the interface, never handshaken
    assert math.isinf(series[_age("10.98.0.13")])  # in the config, absent from the interface
    assert oct(out.stat().st_mode & 0o777) == "0o644"


def test_a_down_interface_reads_every_configured_peer_as_infinite(tmp_path):
    result, out = _run(tmp_path, None)
    assert result.returncode == 0, result.stderr
    ages = _series(out)
    assert set(ages) == {_age("10.98.0.1"), _age("10.98.0.12"), _age("10.98.0.13")}
    assert all(math.isinf(v) for v in ages.values())


def test_a_config_naming_no_peer_fails_and_publishes_nothing(tmp_path):
    result, out = _run(tmp_path, _dump(), conf="[Interface]\nAddress = 10.98.0.11/24\n")
    assert result.returncode == 1
    assert "names no /32 AllowedIPs peer" in result.stderr
    assert not out.exists()


def test_the_unit_runs_the_probe_over_the_rendered_conf_into_the_textfile_directory():
    textfile_dir = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["cache_link_textfile_dir"]
    assert textfile_dir == "/var/lib/zcrypto-node-textfile"
    lines = [line.strip() for line in UNIT.read_text().splitlines()]
    # config-selector-ok: each expected text is a whole stripped line of the unit, compared for equality
    assert (
        "ExecStart=/usr/local/sbin/zcache-probe /etc/wireguard/{{ cache_link_interface }}.conf {{ cache_link_textfile_dir }}/zcache.prom"
        in lines
    )
    # config-selector-ok: a whole stripped line, compared for equality
    assert "ReadWritePaths={{ cache_link_textfile_dir }}" in lines
