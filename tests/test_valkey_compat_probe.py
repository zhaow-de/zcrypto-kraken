"""Guard: `infra/scripts/valkey-compat-probe.py`, run once by hand on a cache node with a password in its environment.
Nothing here opens a socket to a server: the RESP read runs over a fake socket and the node halves are stand-ins."""

import importlib.util
import io
import json
import subprocess
import sys
import textwrap
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
        [f"--pass{SECRET}"],
    ],
)
def test_the_parser_refuses_a_password_argument_without_echoing_it(monkeypatch, capsys, extra):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ") and "would put the password on the command line" in out.out
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize("extra", [[SECRET], ["--port", SECRET], ["--password-env", SECRET], ["--expect-nautilus", SECRET]])
def test_a_rejected_argument_is_not_echoed(monkeypatch, capsys, extra):
    """A stray positional, or a password typed into another flag's value, which argparse or the probe's own refusal
    would otherwise print."""
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main(_args(*extra)) == 2

    out = capsys.readouterr()
    assert out.out.startswith("refusing: ")
    assert SECRET not in out.out + out.err


@pytest.mark.parametrize(
    "value,why",
    [
        (None, "the variable --password-env names is not set in the environment"),
        ("abcd", "the variable --password-env names is shorter than 5"),
    ],
)
def test_the_password_comes_from_the_named_variable(monkeypatch, capsys, value, why):
    if value is None:
        monkeypatch.delenv("PROBE_PW", raising=False)
    else:
        monkeypatch.setenv("PROBE_PW", value)

    assert probe.main(_args()) == 2

    out = capsys.readouterr().out
    assert why in out
    assert "PROBE_PW" not in out
    assert value is None or value not in out


def test_another_library_version_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("PROBE_PW", "a-long-enough-password")

    assert probe.main([*REQUIRED, "--expect-nautilus", "0.0.0"]) == 2

    found = probe.metadata.version("nautilus-trader")
    assert f"carries nautilus-trader {found}, not the version --expect-nautilus names" in capsys.readouterr().out


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


def _in_fresh_interpreter(snippet: str) -> tuple[object, str]:
    """Runs `snippet` in a new interpreter with the script loaded by path as `probe`, and returns the JSON its last
    line prints and its whole stdout. Not in this process: `in_child` forks, and a lock one of the threads
    `conftest.py`'s imports start holds at the fork stays held in the child; `-W default` prints the fork warning,
    which the empty-stderr assertion then fails."""
    prelude = (
        "import importlib.util, json, sys, time\n"
        f"spec = importlib.util.spec_from_file_location('probe', {str(SCRIPT)!r})\n"
        "probe = importlib.util.module_from_spec(spec)\n"
        "sys.modules[spec.name] = probe\n"
        "spec.loader.exec_module(probe)\n"
        f"SECRET = {SECRET!r}\n"
    )
    proc = subprocess.run(
        [sys.executable, "-W", "default", "-c", prelude + textwrap.dedent(snippet)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (proc.returncode, proc.stderr) == (0, "")
    return json.loads(proc.stdout.splitlines()[-1]), proc.stdout


def test_a_half_runs_in_a_child_and_its_output_is_redacted():
    result, out = _in_fresh_interpreter(
        """
        def half():
            print(f"connecting to redis://engine:{SECRET}@127.0.0.1:6390")
            return ["O-1"]

        print(json.dumps(probe.in_child(half, SECRET, 30)))
        """
    )

    assert result == [["O-1"], "ok"]
    assert "  | connecting to redis://engine:<redacted>@127.0.0.1:6390" in out
    assert SECRET not in out


def test_a_half_that_raises_reports_its_error_redacted():
    (ids, why), _ = _in_fresh_interpreter(
        """
        def half():
            raise RuntimeError(f"could not reach redis://engine:{SECRET}@127.0.0.1:6390")

        print(json.dumps(probe.in_child(half, SECRET, 30)))
        """
    )

    assert ids is None
    assert why == "RuntimeError: could not reach redis://engine:<redacted>@127.0.0.1:6390"


def test_a_half_that_hangs_is_killed_at_the_deadline():
    (result, elapsed), _ = _in_fresh_interpreter(
        """
        started = time.monotonic()
        result = probe.in_child(lambda: time.sleep(30), SECRET, 0.5)
        print(json.dumps([result, time.monotonic() - started]))
        """
    )

    assert result == [None, "did not finish in 0.5 s"]

    assert elapsed < 10


def test_the_library_accepts_the_cache_settings_the_probe_passes():
    """The probe's two configs, built with no server: a renamed keyword on a bump fails here, not on the node."""
    target = probe.Target(host="127.0.0.1", port=6390, username="engine", password=SECRET)

    cache, database = probe.cache_configs(target)

    assert (cache.use_instance_id, cache.flush_on_start) == (False, False)
    assert (database.host, database.port, database.username, database.password) == ("127.0.0.1", 6390, "engine", SECRET)
    assert database.number_of_retries == 3
