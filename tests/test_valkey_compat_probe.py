"""Guard: `infra/scripts/valkey-compat-probe.py` settles whether the pinned library's cache client works against
Valkey, run once by hand on a cache node with a password in its environment, so it must speak RESP correctly with no
client library, refuse a password it would otherwise take on the command line without echoing it, keep the
password out of what it prints, and exit 0 only when both halves pass. Nothing here opens a socket to a server:
the RESP read runs over a fake socket and the node halves are stand-ins."""

import importlib.util
import io
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/valkey-compat-probe.py"
SECRET = "hunter2secret"
REQUIRED = ["--host", "127.0.0.1", "--port", "6390", "--username", "engine", "--password-env", "PROBE_PW"]


def _load():
    """A script, not a package module: loaded by path under a private name."""
    spec = importlib.util.spec_from_file_location("_valkey_compat_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


probe = _load()


class _FakeSocket:
    """What `socket.create_connection` returns, holding the server's replies and recording what was sent."""

    def __init__(self, replies: bytes):
        self.sent = b""
        self._replies = io.BytesIO(replies)

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def makefile(self, mode: str):
        assert mode == "rb"
        return self._replies

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _bulk(text: str) -> bytes:
    data = text.encode()
    return b"$%d\r\n%s\r\n" % (len(data), data)


def _args(*extra: str) -> list[str]:
    return [*REQUIRED, "--expect-nautilus", probe.metadata.version("nautilus-trader"), *extra]


def test_encode_writes_a_resp_array_of_bulk_strings():
    assert probe.encode("AUTH", "engine", "pw") == b"*3\r\n$4\r\nAUTH\r\n$6\r\nengine\r\n$2\r\npw\r\n"
    assert probe.encode("DBSIZE") == b"*1\r\n$6\r\nDBSIZE\r\n"


@pytest.mark.parametrize(
    "wire,value",
    [
        (b"+OK\r\n", "OK"),
        (b":42\r\n", 42),
        (b"$5\r\nhello\r\n", b"hello"),
        (b"$0\r\n\r\n", b""),
        (b"$-1\r\n", None),
        (b"*2\r\n$1\r\na\r\n:1\r\n", [b"a", 1]),
        (b"*-1\r\n", None),
        # INFO's reply is one bulk string whose lines end in CRLF: the length, not the first CRLF, ends it.
        (b"$11\r\na:1\r\nb:22\r\n\r\n", b"a:1\r\nb:22\r\n"),
    ],
)
def test_decode_reads_each_resp2_reply_kind(wire, value):
    assert probe.decode(io.BytesIO(wire)) == value


def test_decode_raises_the_servers_error_reply():
    with pytest.raises(probe.RespError, match="WRONGPASS invalid username-password pair"):
        probe.decode(io.BytesIO(b"-WRONGPASS invalid username-password pair or user is disabled.\r\n"))


@pytest.mark.parametrize("wire", [b"", b"+OK", b"$5\r\nhel", b"$5\r\nhelloXY"])
def test_decode_refuses_a_truncated_reply(wire):
    with pytest.raises(ConnectionError, match="mid-reply"):
        probe.decode(io.BytesIO(wire))


def test_read_server_authenticates_then_reads_info_and_dbsize(monkeypatch):
    info = "# Server\r\nredis_version:7.2.4\r\nserver_name:valkey\r\nvalkey_version:9.1.2\r\n"
    fake = _FakeSocket(b"+OK\r\n" + _bulk(info) + b":0\r\n")
    monkeypatch.setattr(probe.socket, "create_connection", lambda address, timeout: fake)

    reading = probe.read_server("127.0.0.1", 6390, "engine", SECRET)

    assert fake.sent == probe.encode("AUTH", "engine", SECRET) + probe.encode("INFO", "server") + probe.encode("DBSIZE")
    assert reading == probe.ServerReading(redis_version="7.2.4", valkey_version="9.1.2", dbsize=0)


@pytest.mark.parametrize(
    "redis_version,passes",
    [("7.2.4", True), ("6.2.0", True), ("8.0.2", True), ("6.0.16", False), (None, False), ("7.2.4-rc1", False)],
)
def test_the_server_passes_at_the_librarys_version_floor(redis_version, passes):
    assert probe.server_passes(probe.ServerReading(redis_version, "9.1.2", 0)) is passes


@pytest.mark.parametrize(
    "extra",
    [
        ["--password", SECRET],
        [f"--password={SECRET}"],
        ["--pass", SECRET],
        ["-a", SECRET],
        [f"--auth={SECRET}"],
    ],
)
def test_the_parser_refuses_a_password_argument_without_echoing_it(monkeypatch, capsys, extra):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ") and "would put the password on the command line" in out.out
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize("extra", [[SECRET], ["--port", SECRET]])
def test_a_rejected_argument_is_not_echoed(monkeypatch, capsys, extra):
    """A stray positional, or a password typed into another flag's value: argparse would print either word."""
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ")
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize("value,why", [(None, "PROBE_PW is not set in the environment"), ("abcd", "shorter than 5")])
def test_the_password_comes_from_the_named_variable(monkeypatch, capsys, value, why):
    if value is None:
        monkeypatch.delenv("PROBE_PW", raising=False)
    else:
        monkeypatch.setenv("PROBE_PW", value)

    assert probe.main(_args()) == 2

    out = capsys.readouterr().out
    assert why in out
    assert value is None or value not in out


def test_another_library_version_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main([*REQUIRED, "--expect-nautilus", "0.0.0"]) == 2

    assert ", not 0.0.0" in capsys.readouterr().out


@pytest.mark.parametrize(
    "server_ok,written,restored,code",
    [
        (True, ["O-1"], ["O-1"], 0),
        (False, ["O-1"], ["O-1"], 1),
        (True, ["O-1"], [], 1),
        (True, ["O-1"], ["O-1", "O-2"], 1),
        (True, ["O-1"], None, 1),
        (True, None, None, 1),
        (True, [], [], 1),
        (True, ["O-1", "O-2"], ["O-1", "O-2"], 1),
    ],
)
def test_the_verdict_needs_both_halves(server_ok, written, restored, code):
    assert probe.verdict(server_ok, written, restored) == code


@pytest.mark.parametrize(
    "redis_version,dbsize,halves,code,last",
    [
        ("7.2.4", 0, {True: ["O-1"], False: ["O-1"]}, 0, "PASS"),
        ("7.2.4", 0, {True: ["O-1"], False: []}, 1, "FAIL"),
        (None, 0, {True: ["O-1"], False: ["O-1"]}, 1, "FAIL"),
        ("7.2.4", 3, {}, 2, "refusing: database 0 holds 3 key(s); the probe writes there, so it takes an empty server"),
    ],
)
def test_main_composes_the_exit_from_both_halves(monkeypatch, capsys, redis_version, dbsize, halves, code, last):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")
    monkeypatch.setattr(probe, "read_server", lambda *a: probe.ServerReading(redis_version, "9.1.2", dbsize))
    ran = []

    def fake_in_child(half, password, deadline_secs):
        mint = half.args[1]
        ran.append(mint)
        return halves[mint], "ok"

    monkeypatch.setattr(probe, "in_child", fake_in_child)

    assert probe.main(_args()) == code

    assert capsys.readouterr().out.splitlines()[-1] == last
    assert ran == ([] if dbsize else [True, False])


def test_the_restore_is_not_run_when_nothing_was_written(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")
    monkeypatch.setattr(probe, "read_server", lambda *a: probe.ServerReading("7.2.4", "9.1.2", 0))
    ran = []

    def fake_in_child(half, password, deadline_secs):
        ran.append(half.args[1])
        return None, "RuntimeError: no connection"

    monkeypatch.setattr(probe, "in_child", fake_in_child)

    assert probe.main(_args()) == 1

    assert ran == [True]
    assert "restore: skipped, nothing was written" in capsys.readouterr().out


def test_a_server_that_refuses_the_login_fails_the_probe_without_the_password(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", SECRET)
    fake = _FakeSocket(b"-WRONGPASS invalid username-password pair or user is disabled.\r\n")
    monkeypatch.setattr(probe.socket, "create_connection", lambda address, timeout: fake)

    assert probe.main(_args()) == 1

    out = capsys.readouterr().out
    assert "server: FAIL, RespError: WRONGPASS" in out
    assert SECRET not in out


def test_a_half_runs_in_a_child_and_its_output_is_redacted(capsys):
    def half():
        print(f"connecting to redis://engine:{SECRET}@127.0.0.1:6390")
        return ["O-1"]

    assert probe.in_child(half, SECRET, 30) == (["O-1"], "ok")

    out = capsys.readouterr().out
    assert "  | connecting to redis://engine:<redacted>@127.0.0.1:6390" in out
    assert SECRET not in out


def test_a_half_that_raises_reports_its_error_redacted(capsys):
    def half():
        raise RuntimeError(f"could not reach redis://engine:{SECRET}@127.0.0.1:6390")

    ids, why = probe.in_child(half, SECRET, 30)

    assert ids is None
    assert why == "RuntimeError: could not reach redis://engine:<redacted>@127.0.0.1:6390"


def test_a_half_that_hangs_is_killed_at_the_deadline():
    started = time.monotonic()

    assert probe.in_child(lambda: time.sleep(30), SECRET, 0.5) == (None, "did not finish in 0.5 s")

    assert time.monotonic() - started < 10


def test_the_library_accepts_the_cache_settings_the_probe_passes():
    """The probe's two configs, built with no server: a renamed keyword on a bump fails here, not on the node."""
    from nautilus_trader.common import CacheConfig
    from nautilus_trader.infrastructure import RedisCacheConfig

    cache = CacheConfig(use_instance_id=False, flush_on_start=False)
    RedisCacheConfig(
        host="127.0.0.1",
        port=6390,
        username="engine",
        password=SECRET,
        ssl=False,
        connection_timeout=5,
        response_timeout=5,
        number_of_retries=3,
    )
    assert (cache.use_instance_id, cache.flush_on_start) == (False, False)
