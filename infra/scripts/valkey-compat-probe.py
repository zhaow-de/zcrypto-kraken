#!/usr/bin/env python3
"""The pinned nautilus-trader cache client against one Valkey server: the version line it parses, and an order
written by one node and restored by the next.

  --host H --port P --username U --password-env VAR --expect-nautilus VERSION

1. A raw RESP read, the standard library only: AUTH, INFO server, DBSIZE. It prints the `redis_version:` line the
   library's version check parses and the `valkey_version:` line, and passes when `redis_version` is present and at
   or above 6.2.0, the floor below which the library logs an error and carries on.
2. Two nodes, each in its own forked child, both with the engine's cache settings (`use_instance_id=False`,
   `flush_on_start=False`, `load_cache` at its default): the first mints one limit order and submits it with no
   execution client, so the order is denied, never sent, and still lands in the cache; the second prints the client
   order ids its cache restored at start. It passes when those are exactly the one the first wrote.

It writes under `trader-PROBE-001:` in database 0 and deletes nothing, so it refuses a server whose database 0 holds
any key: run it against a throwaway server, never the engine's set.

Exit: 0 both halves pass; 1 a half failed, the server unreachable or the login refused among them; 2 refused before
anything was written (usage, a password on the command line, the variable unset or shorter than five characters, a
nautilus-trader other than the expected one, a non-empty database 0).

Run it inside the app image on the server's host, the script on stdin, the password in a root-only env file:
    ssh <host> sudo docker run --rm -i --network host --memory 512m --env-file <env file> \
      --entrypoint python ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest> - --host 127.0.0.1 --port <port> \
      --username <user> --password-env <VAR> --expect-nautilus <version> < infra/scripts/valkey-compat-probe.py
The password is read from the environment and never printed: the library's own log lines pass through a filter that
replaces it, and an argument that could carry it is refused without being echoed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import signal
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from importlib import metadata

TRADER_ID = "PROBE-001"
INSTRUMENT = "XBT/EUR.KRAKEN"
LIBRARY_FLOOR = (6, 2, 0)
MIN_PASSWORD_CHARS = 5
SOCKET_TIMEOUT_SECS = 5.0
# Three retries of five-second timeouts bound a node that cannot reach the server well inside this.
NODE_DEADLINE_SECS = 120.0
# valkey-cli's password flags: the habit an operator brings to a Valkey command line.
PASSWORD_FLAGS = ("-a", "--auth", "--askpass")
REDACTED = "<redacted>"
_QUOTED = re.compile(r"'[^']*'")
_ELIDED = "'...'"


class Refusal(RuntimeError):
    """Raised before anything connects. Names flags and variables, never values."""


class RespError(RuntimeError):
    """The server's error reply, verbatim."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        # argparse quotes the words it rejects and lists the ones it does not know, and either may be the password.
        if message.startswith("unrecognized arguments"):
            message = "unrecognized arguments"
        message = _QUOTED.sub(_ELIDED, message)
        raise Refusal(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    for word in argv:
        flag = word.split("=", 1)[0]
        if flag in PASSWORD_FLAGS or (flag.startswith("--pass") and flag != "--password-env"):
            # A `--pass...` word can be the flag with the password run into it, so only a fixed spelling is named.
            named = flag if flag in PASSWORD_FLAGS else "a --pass... flag"
            raise Refusal(
                f"{named} would put the password on the command line; put it in the environment and name the variable "
                "with --password-env"
            )
    parser = _Parser(prog="valkey-compat-probe", allow_abbrev=False)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-env", required=True)
    parser.add_argument("--expect-nautilus", required=True)
    return parser.parse_args(argv)


def read_password(variable: str) -> str:
    # The name came from the command line, where the password itself may have been typed in its place: name the flag.
    password = os.environ.get(variable, "")
    if not password:
        raise Refusal("the variable --password-env names is not set in the environment")
    if len(password) < MIN_PASSWORD_CHARS:
        raise Refusal(
            f"the variable --password-env names is shorter than {MIN_PASSWORD_CHARS} characters, which the library logs unredacted"
        )
    return password


def require_library(expected: str) -> str:
    try:
        found = metadata.version("nautilus-trader")
    except metadata.PackageNotFoundError as exc:
        raise Refusal("no nautilus-trader in this interpreter") from exc
    if found != expected:
        # `expected` came from the command line, which may carry the password; only the installed version is printed.
        raise Refusal(f"this interpreter carries nautilus-trader {found}, not the version --expect-nautilus names")
    return found


def redact(text: str, password: str) -> str:
    """The literal password replaced. The library builds a `redis://user:password@host` URL, which percent-encodes
    the password, so a password with a character that encoding changes would pass this filter in its encoded form:
    the rollout mints a hex password, which encodes to itself."""
    return text.replace(password, REDACTED)


def encode(*words: str | bytes) -> bytes:
    """One RESP command, an array of bulk strings."""
    out = [b"*%d\r\n" % len(words)]
    for word in words:
        data = word.encode() if isinstance(word, str) else word
        out.append(b"$%d\r\n%s\r\n" % (len(data), data))
    return b"".join(out)


def decode(reader) -> object:
    """One RESP2 reply off a binary file object: a simple string as `str`, an integer as `int`, a bulk string as
    `bytes`, a null as None, an array as a list; an error reply raises `RespError`."""
    line = reader.readline()
    if not line.endswith(b"\r\n"):
        raise ConnectionError("the server closed the connection mid-reply")
    kind, body = line[:1], line[1:-2]
    if kind == b"+":
        return body.decode()
    if kind == b"-":
        raise RespError(body.decode(errors="replace"))
    if kind == b":":
        return int(body)
    if kind == b"$":
        size = int(body)
        if size < 0:
            return None
        data = reader.read(size + 2)
        if len(data) != size + 2 or not data.endswith(b"\r\n"):
            raise ConnectionError("the server closed the connection mid-reply")
        return data[:-2]
    if kind == b"*":
        size = int(body)
        return None if size < 0 else [decode(reader) for _ in range(size)]
    raise RespError(f"not a RESP2 reply: {line[:16]!r}")


def parse_info(text: str) -> dict[str, str]:
    return dict(line.split(":", 1) for line in text.splitlines() if line and not line.startswith("#") and ":" in line)


def version_tuple(text: str | None) -> tuple[int, ...] | None:
    if text is None or not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


@dataclass(frozen=True)
class ServerReading:
    redis_version: str | None
    valkey_version: str | None
    dbsize: int


def read_server(host: str, port: int, username: str, password: str) -> ServerReading:
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT_SECS) as sock:
        reader = sock.makefile("rb")

        def call(*words: str) -> object:
            sock.sendall(encode(*words))
            return decode(reader)

        call("AUTH", username, password)
        info = parse_info(call("INFO", "server").decode())
        dbsize = call("DBSIZE")
    return ServerReading(info.get("redis_version"), info.get("valkey_version"), dbsize)


def server_passes(reading: ServerReading) -> bool:
    found = version_tuple(reading.redis_version)
    return found is not None and found >= LIBRARY_FLOOR


def report_server(reading: ServerReading) -> bool:
    print(f"redis_version: {reading.redis_version if reading.redis_version is not None else 'absent'}")
    print(f"valkey_version: {reading.valkey_version if reading.valkey_version is not None else 'absent'}")
    passed = server_passes(reading)
    floor = ".".join(str(part) for part in LIBRARY_FLOOR)
    print(f"server: {'PASS' if passed else 'FAIL'} (the library's floor is {floor})")
    return passed


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    username: str
    password: str


def run_node(target: Target, mint: bool) -> list[str]:
    """One LiveNode with no data or execution client and reconciliation off; returns the client order ids its cache
    holds at start, after minting and submitting one limit order first when `mint` is set."""
    import threading

    from nautilus_trader.common import CacheConfig, Environment, LogLevel
    from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
    from nautilus_trader.infrastructure import RedisCacheConfig
    from nautilus_trader.live import LiveNode
    from nautilus_trader.model import InstrumentId, OrderSide, Price, Quantity, StrategyId, TraderId
    from nautilus_trader.trading import Strategy, StrategyConfig

    config = StrategyConfig(strategy_id=StrategyId(TRADER_ID), order_id_tag="001")
    seen: list[str] = []

    class Probe(Strategy):
        def __new__(cls, *args, **kwargs):
            return super().__new__(cls, config)

        def __init__(self, box):
            super().__init__(config=config)
            self._box = box

        def on_start(self):
            try:
                if mint:
                    order = self.order_factory.limit(
                        InstrumentId.from_str(INSTRUMENT), OrderSide.BUY, Quantity.from_str("0.0001"), Price.from_str("90000.0")
                    )
                    self.submit_order(order)
                seen.extend(str(order.client_order_id) for order in self.cache.orders())
            finally:
                threading.Timer(1.5, lambda: self._box[0].stop()).start()

    box = [None]
    node = (
        LiveNode.builder(name="valkey-probe", trader_id=TraderId(TRADER_ID), environment=Environment.LIVE)
        .with_logging(LoggerConfig(stdout_level=LogLevel.INFO))
        .with_cache_config(CacheConfig(use_instance_id=False, flush_on_start=False))
        .with_cache_database_factory(
            RedisCacheConfig(
                host=target.host,
                port=target.port,
                username=target.username,
                password=target.password,
                ssl=False,
                connection_timeout=5,
                response_timeout=5,
                number_of_retries=3,
            )
        )
        .with_exec_engine_config(LiveExecutionEngineConfig(reconciliation=False))
        .build()
    )
    box[0] = node.handle()
    node.add_strategy(Probe(box))
    try:
        node.run()
    finally:
        node.dispose()
    return seen


def in_child(half: Callable[[], list[str]], password: str, deadline_secs: float) -> tuple[list[str] | None, str]:
    """Run `half` in a forked child; return its ids and "ok", or None and why. A child because the library's logging
    and runtime are process-wide, so two nodes in one process are not two starts. Everything the child writes to its
    stdout and stderr, the library's log lines among them, is printed here through `redact`."""
    sys.stdout.flush()
    sys.stderr.flush()
    out_r, out_w = os.pipe()
    res_r, res_w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(out_r)
        os.close(res_r)
        os.dup2(out_w, 1)
        os.dup2(out_w, 2)
        sys.stdout = sys.stderr = open(out_w, "w", buffering=1, closefd=False)
        try:
            payload = {"ids": half()}
        except BaseException as exc:  # noqa: BLE001 -- the parent reports it
            payload = {"error": f"{type(exc).__name__}: {exc}"}
        sys.stdout.flush()
        os.write(res_w, json.dumps(payload).encode())
        os._exit(0)
    os.close(out_w)
    os.close(res_w)
    deadline = time.monotonic() + deadline_secs
    pending, result, timed_out = b"", b"", False
    open_fds = {out_r, res_r}
    while open_fds:
        left = deadline - time.monotonic()
        if left <= 0:
            os.kill(pid, signal.SIGKILL)
            timed_out = True
            break
        ready, _, _ = select.select(sorted(open_fds), [], [], left)
        for fd in ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                open_fds.discard(fd)
            elif fd == res_r:
                result += chunk
            else:
                *lines, pending = (pending + chunk).split(b"\n")
                for line in lines:
                    print(f"  | {redact(line.decode(errors='replace'), password)}")
    if pending:
        print(f"  | {redact(pending.decode(errors='replace'), password)}")
    os.waitpid(pid, 0)
    os.close(out_r)
    os.close(res_r)
    if timed_out:
        return None, f"did not finish in {deadline_secs:g} s"
    try:
        payload = json.loads(result)
    except ValueError:
        return None, "the child exited without a result"
    if "error" in payload:
        return None, redact(payload["error"], password)
    return payload["ids"], "ok"


def verdict(server_ok: bool, written: list[str] | None, restored: list[str] | None) -> int:
    return 0 if server_ok and written is not None and len(written) == 1 and restored == written else 1


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        password = read_password(args.password_env)
        library = require_library(args.expect_nautilus)
    except Refusal as exc:
        print(f"refusing: {exc}")
        return 2
    print(f"nautilus-trader {library}")
    try:
        reading = read_server(args.host, args.port, args.username, password)
    except (OSError, RespError) as exc:
        print(f"server: FAIL, {type(exc).__name__}: {redact(str(exc), password)}")
        return 1
    server_ok = report_server(reading)
    if reading.dbsize:
        print(f"refusing: database 0 holds {reading.dbsize} key(s); the probe writes there, so it takes an empty server")
        return 2
    target = Target(args.host, args.port, args.username, password)
    written, why = in_child(partial(run_node, target, True), password, NODE_DEADLINE_SECS)
    print(f"write: {written if written is not None else why}")
    if written:
        restored, why = in_child(partial(run_node, target, False), password, NODE_DEADLINE_SECS)
    else:
        restored, why = None, "skipped, nothing was written"
    print(f"restore: {restored if restored is not None else why}")
    code = verdict(server_ok, written, restored)
    print("PASS" if code == 0 else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
