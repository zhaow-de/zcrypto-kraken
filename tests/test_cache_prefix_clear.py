"""`infra/scripts/cache-prefix-clear.py` against a real `valkey-server` this file starts, the `engine` user
carrying the fleet's ACL line and a password file standing in for engine.env; docker is a stub that
answers the one inspect and records what it was asked."""

from __future__ import annotations

import dataclasses
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from tests.test_cache_restart import ADMIN_PASSWORD, ADMIN_USER, ENGINE_PASSWORD, _resp, _Valkey

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/cache-prefix-clear.py"
INSIDE = {
    "trader-SHADOW-001:accounts:KRAKEN-001": "list",
    "trader-SHADOW-001:currencies:XXBT": "string",
    "trader-SHADOW-001:currencies:ZEUR": "string",
    "trader-SHADOW-001:index:positions_open": "set",
    "trader-SHADOW-001:instruments:BTC/EUR.KRAKEN": "string",
    "trader-SHADOW-001:orders:O-20261101-000000-001-000-1": "string",
    "trader-SHADOW-001:positions:BTC/EUR.KRAKEN-ShadowStrategy-000": "string",
    "trader-SHADOW-001:snapshots:positions:P-1": "list",
}
# An earlier single-key clear's copy carries the prefix inside its name, and a sibling trader's differs
# from it in the last character before the colon: neither is the store's.
OUTSIDE = {
    "aside:trader-SHADOW-001:accounts:KRAKEN-001": "list",
    "trader-SHADOW-0010:accounts:KRAKEN-001": "list",
    "other:key": "string",
}


def _load():
    """A script, not a package module: loaded by path under a private name."""
    spec = importlib.util.spec_from_file_location("_cache_prefix_clear", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cpc = _load()


def _seed(port: int, keys: dict[str, str]) -> None:
    for key, kind in keys.items():
        words = {"list": ("RPUSH", key, "{}"), "set": ("SADD", key, "member"), "string": ("SET", key, "{}")}[kind]
        _resp(port, ADMIN_USER, ADMIN_PASSWORD, *words)


def _keys(port: int) -> set[str]:
    cursor, keys = "0", set()
    while True:
        cursor, batch = _resp(port, ADMIN_USER, ADMIN_PASSWORD, "SCAN", cursor, "COUNT", "1000")
        keys.update(batch)
        if cursor == "0":
            return keys


@pytest.fixture
def valkey(tmp_path):
    server = _Valkey(tmp_path / "valkey")
    server.start()
    try:
        _seed(server.port, INSIDE | OUTSIDE)
        yield server
    finally:
        server.stop()


def _docker(tmp_path: Path, answer: str) -> tuple[tuple[str, ...], Path]:
    """A docker stub answering `inspect` as an engine container in `answer`'s state would; each call's
    arguments land one line apiece in the log beside it."""
    log = tmp_path / f"docker-{answer}.log"
    body = {
        "running": "echo true",
        "stopped": "echo false",
        "absent": 'echo "Error: No such object: zcrypto-engine" >&2; exit 1',
        "unreachable": 'echo "Cannot connect to the Docker daemon" >&2; exit 1',
    }[answer]
    stub = tmp_path / f"docker-{answer}"
    stub.write_text(f'#!/bin/sh\nprintf "%s|" "$@" >> "{log}"\necho >> "{log}"\n{body}\n')
    stub.chmod(0o755)
    return (str(stub),), log


def _host(tmp_path: Path, valkey, docker: tuple[str, ...] = ("docker-is-not-called",), password: str = ENGINE_PASSWORD):
    env = tmp_path / "engine.env"
    env.write_text(f"KRAKEN_SPOT_API_KEY=unused\nZCRYPTO_CACHE_PASSWORD={password}\nZCRYPTO_LOKI_URL=unused\n")
    out = tmp_path / "state"
    out.mkdir(exist_ok=True)
    return cpc.Host(env_file=str(env), port=valkey.port, out_dir=str(out), docker=docker, proxy_namespace=False)


def _run(capsys, host, *argv: str) -> tuple[int, str]:
    rc = cpc.main(list(argv), host)
    return rc, capsys.readouterr().out


def _list_file(out: str) -> Path:
    [(path, lines)] = re.findall(r"^list: (\S+), (\d+) line\(s\)$", out, re.M)
    assert int(lines) == len(Path(path).read_text().splitlines())
    return Path(path)


def test_the_inventory_counts_the_store_by_collection_and_lists_the_prefixed_keys(tmp_path, valkey, capsys):
    host = _host(tmp_path, valkey)

    rc, out = _run(capsys, host, "inventory")

    assert rc == 0, out
    assert "DBSIZE 11" in out.splitlines()
    assert "keys under trader-SHADOW-001: 8" in out.splitlines()
    per_collection = dict((name, int(n)) for n, name in re.findall(r"^ +(\d+) (\S+)$", out, re.M))
    assert per_collection == {
        "accounts": 1,
        "currencies": 2,
        "index": 1,
        "instruments": 1,
        "orders": 1,
        "positions": 1,
        "snapshots": 1,
    }
    assert "keys outside trader-SHADOW-001: 3, 0 expected" in out.splitlines()
    path = _list_file(out)
    assert path.parent == Path(host.out_dir) and re.fullmatch(r"cache-prefix-clear-\d{8}T\d{6}Z\.keys", path.name)
    assert path.read_text().splitlines() == sorted(INSIDE)


def test_the_inventory_reads_the_open_positions_index_present_before_a_clear_and_absent_after(tmp_path, valkey, capsys):
    docker, _ = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    _, out = _run(capsys, host, "inventory")
    assert "trader-SHADOW-001:index:positions_open present" in out.splitlines()

    _run(capsys, host, "clear", str(_list_file(out)))
    again = tmp_path / "again"
    again.mkdir()
    rc, out = _run(capsys, dataclasses.replace(host, out_dir=str(again)), "inventory")

    assert rc == 0, out
    assert "trader-SHADOW-001:index:positions_open absent" in out.splitlines()


@pytest.mark.parametrize("state", ["absent", "stopped"])
def test_a_clear_deletes_exactly_the_listed_keys_and_leaves_the_rest(tmp_path, valkey, capsys, state):
    docker, log = _docker(tmp_path, state)
    host = _host(tmp_path, valkey, docker)
    _, out = _run(capsys, host, "inventory")
    listed = _list_file(out)

    rc, out = _run(capsys, host, "clear", str(listed))

    assert rc == 0, out
    assert out.splitlines()[-1] == "listed=8 deleted=8 failed=0"
    assert _keys(valkey.port) == set(OUTSIDE)
    assert log.read_text().splitlines() == ["inspect|--format|{{.State.Running}}|zcrypto-engine|"] * 2


@pytest.mark.parametrize(
    ("state", "refusal"),
    [
        ("running", "REFUSED: the engine container is running: stop the unit first; nothing was deleted"),
        ("unreachable", "REFUSED: the engine container's state could not be read (docker inspect exited 1)"),
    ],
)
def test_a_clear_is_refused_unless_the_engine_container_reads_stopped_or_absent(tmp_path, valkey, capsys, state, refusal):
    docker, log = _docker(tmp_path, state)
    host = _host(tmp_path, valkey, docker)
    _, out = _run(capsys, host, "inventory")
    listed = _list_file(out)

    rc, out = _run(capsys, host, "clear", str(listed))

    assert (rc, out.splitlines()[-1]) == (1, refusal)
    assert _keys(valkey.port) == set(INSIDE) | set(OUTSIDE)
    assert log.read_text().splitlines() == ["inspect|--format|{{.State.Running}}|zcrypto-engine|"]


def test_a_clear_that_deletes_fewer_keys_than_it_lists_exits_1(tmp_path, valkey, capsys):
    docker, _ = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    _, out = _run(capsys, host, "inventory")
    listed = _list_file(out)
    assert _run(capsys, host, "clear", str(listed))[0] == 0

    rc, out = _run(capsys, host, "clear", str(listed))

    assert (rc, out.splitlines()[-1]) == (1, "listed=8 deleted=0 failed=0")
    assert out.count("not deleted (0): trader-SHADOW-001:") == 8


def test_a_list_naming_a_key_outside_the_prefix_is_refused_whole(tmp_path, valkey, capsys):
    docker, log = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    listed = tmp_path / "hand.keys"
    listed.write_text("trader-SHADOW-001:accounts:KRAKEN-001\naside:trader-SHADOW-001:accounts:KRAKEN-001\n")

    rc, out = _run(capsys, host, "clear", str(listed))

    assert rc == 1 and out.startswith("REFUSED: 1 line(s) of ")
    assert _keys(valkey.port) == set(INSIDE) | set(OUTSIDE)
    assert not log.exists()


def test_a_list_naming_a_key_twice_is_refused_whole(tmp_path, valkey, capsys):
    docker, log = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    listed = tmp_path / "hand.keys"
    listed.write_text(
        "trader-SHADOW-001:accounts:KRAKEN-001\ntrader-SHADOW-001:currencies:ZEUR\ntrader-SHADOW-001:accounts:KRAKEN-001\n"
    )

    rc, out = _run(capsys, host, "clear", str(listed))

    assert (rc, out.splitlines()) == (1, [f"REFUSED: {listed} names a key twice, which no inventory writes: nothing was deleted"])
    assert _keys(valkey.port) == set(INSIDE) | set(OUTSIDE)
    assert not log.exists()


def test_verify_passes_after_the_clear_and_fails_on_a_key_written_since(tmp_path, valkey, capsys):
    docker, _ = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    _, out = _run(capsys, host, "inventory")
    _run(capsys, host, "clear", str(_list_file(out)))

    rc, out = _run(capsys, host, "verify", "11", "8")
    assert (rc, out.splitlines()[-2:]) == (0, ["DBSIZE 3, 3 expected (11 less 8)", "VERIFIED"])

    _seed(valkey.port, {"trader-SHADOW-001:accounts:KRAKEN-001": "list"})
    rc, out = _run(capsys, host, "verify", "11", "8")
    assert rc == 1
    assert "keys under trader-SHADOW-001: 1, 0 expected" in out.splitlines()
    assert out.splitlines()[-2:] == ["DBSIZE 4, 3 expected (11 less 8)", "NOT VERIFIED"]


def test_the_password_reaches_neither_stdout_nor_stderr(tmp_path, valkey, capfd):
    docker, _ = _docker(tmp_path, "absent")
    host = _host(tmp_path, valkey, docker)
    assert cpc.main(["inventory"], host) == 0
    first = capfd.readouterr()
    assert cpc.main(["clear", str(_list_file(first.out))], host) == 0
    assert cpc.main(["verify", "11", "8"], host) == 0
    wrong = "a-wrong-harness-password"
    assert cpc.main(["inventory"], _host(tmp_path, valkey, docker, password=wrong)) == 1

    rest = capfd.readouterr()

    assert rest.out.splitlines()[-1] == "REFUSED: AUTH refused (WRONGPASS)"
    for stream in (first.out, first.err, rest.out, rest.err):
        assert ENGINE_PASSWORD not in stream and wrong not in stream


def test_a_run_without_a_running_proxy_container_is_refused_before_it_reads_the_password(tmp_path, valkey, capsys):
    docker, log = _docker(tmp_path, "absent")
    host = cpc.Host(env_file=str(tmp_path / "no-such.env"), port=valkey.port, out_dir=str(tmp_path), docker=docker)

    rc, out = _run(capsys, host, "inventory")

    assert (rc, out.splitlines()) == (1, ["REFUSED: no running zcrypto-cache-proxy container"])
    assert log.read_text().splitlines() == ["inspect|--format|{{.State.Pid}}|zcrypto-cache-proxy|"]
