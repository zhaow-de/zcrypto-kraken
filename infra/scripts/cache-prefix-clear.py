#!/usr/bin/env python3
"""Clear the engine's whole trader store from the cache, one key at a time: the prefix-wide form of
`infra/runbooks/engine-procedures.md#engine-clear-stored-account`.

Run from the workstation, each mode its own call, in this order:
    ssh zcrypto sudo python3 - inventory < infra/scripts/cache-prefix-clear.py
    ssh zcrypto sudo python3 - clear <list-file> < infra/scripts/cache-prefix-clear.py
    ssh zcrypto sudo python3 - verify <dbsize-before> <deleted> < infra/scripts/cache-prefix-clear.py

  inventory  DBSIZE; the keys under `trader-SHADOW-001:` per collection, the second `:` field; the keys
             outside it, 0 expected; and the keys under it written one per line to a new file,
             /var/lib/zcrypto-engine/cache-prefix-clear-<UTC stamp>.keys, whose path and line count it prints.
  clear      Refused while `zcrypto-engine` runs, read with a docker inspect of `{{.State.Running}}` and no
             other field. Then one DEL per key the list names, never a scan piped into DEL. It prints
             `listed=… deleted=… failed=…` and exits 1 unless every listed key was deleted.
  verify     No key left under the prefix, and DBSIZE the inventory's less the deleted count.

The process enters the cache proxy container's network namespace, where the proxy listens on loopback, so
every command reaches the node the Sentinels name as the primary, the one the engine loads from. It
authenticates as `engine`, the one user the cache admits writes from, with the password read from the
`ZCRYPTO_CACHE_PASSWORD=` line of /opt/zcrypto-engine/engine.env inside this process: neither the password
nor the file is printed, and a refused AUTH prints the server's first error word alone. Standard library
only, and no syntax newer than the host's python3.

Exit: 0 done, 1 refused or a check that did not pass, 2 failed (the exception's type is printed, nothing else).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "trader-SHADOW-001:"
PASSWORD_LINE = "ZCRYPTO_CACHE_PASSWORD="
USER = "engine"
ENGINE_CONTAINER = "zcrypto-engine"
PROXY_CONTAINER = "zcrypto-cache-proxy"
# How many keys outside the prefix, or left under it, are named before the rest are only counted.
SHOWN = 20
USAGE = "usage: inventory | clear <list-file> | verify <dbsize-before> <deleted>"


@dataclass(frozen=True)
class Host:
    """Where a run reads and writes: the defaults are the engine host's, and a test passes its own."""

    env_file: str = "/opt/zcrypto-engine/engine.env"
    addr: str = "127.0.0.1"
    port: int = 6379
    out_dir: str = "/var/lib/zcrypto-engine"
    docker: tuple[str, ...] = ("docker",)
    proxy_namespace: bool = True


class Refused(Exception):
    """A state the run stops at, named in the line it prints."""


class ErrorReply(Exception):
    """The server's error answer to one command."""

    def word(self) -> str:
        return str(self).split(" ")[0]


def in_prefix(key: str) -> bool:
    return key.startswith(PREFIX)


def _enc(*words: object) -> bytes:
    out = b"*%d\r\n" % len(words)
    for w in words:
        b = w if isinstance(w, bytes) else str(w).encode("utf-8", "surrogateescape")
        out += b"$%d\r\n%s\r\n" % (len(b), b)
    return out


def _dec(reader):
    line = reader.readline()
    if not line.endswith(b"\r\n"):
        raise ConnectionError("the cache closed the connection mid-reply")
    kind, body = line[:1], line[1:-2]
    if kind == b"+":
        return body.decode()
    if kind == b"-":
        raise ErrorReply(body.decode("ascii", "replace"))
    if kind == b":":
        return int(body)
    if kind == b"$":
        n = int(body)
        return None if n < 0 else reader.read(n + 2)[:-2]
    if kind == b"*":
        n = int(body)
        return None if n < 0 else [_dec(reader) for _ in range(n)]
    raise ConnectionError("the cache answered in a shape this does not read")


def _text(reply) -> str:
    return reply.decode("utf-8", "surrogateescape") if isinstance(reply, bytes) else str(reply)


def _password(env_file: str) -> str:
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            if line.startswith(PASSWORD_LINE):
                return line[len(PASSWORD_LINE) :].rstrip("\n")
    raise Refused("the env file carries no cache password line")


def _inspect(docker: tuple[str, ...], field: str, container: str) -> subprocess.CompletedProcess:
    return subprocess.run([*docker, "inspect", "--format", field, container], capture_output=True, text=True, timeout=30)


def engine_state(docker: tuple[str, ...]) -> str:
    """`running`, `stopped` or `absent` -- the unit's stop removes the container -- read off the one scoped
    field; an inspect that answers none of the three refuses, since a state unread is no stopped engine."""
    proc = _inspect(docker, "{{.State.Running}}", ENGINE_CONTAINER)
    out = proc.stdout.strip()
    if proc.returncode == 0 and out in ("true", "false"):
        return "running" if out == "true" else "stopped"
    if proc.returncode != 0 and "no such" in proc.stderr.lower():
        return "absent"
    raise Refused(f"the engine container's state could not be read (docker inspect exited {proc.returncode})")


def _enter_proxy_namespace(docker: tuple[str, ...]) -> None:
    """`nsenter -t <proxy pid> -n`, done in this process: the proxy publishes no port on the host."""
    pid = _inspect(docker, "{{.State.Pid}}", PROXY_CONTAINER).stdout.strip()
    if not pid.isdigit() or int(pid) <= 0:
        raise Refused(f"no running {PROXY_CONTAINER} container")
    fd = os.open(f"/proc/{pid}/ns/net", os.O_RDONLY)
    try:
        os.setns(fd, os.CLONE_NEWNET)
    finally:
        os.close(fd)


class Cache:
    """One authenticated connection, retried for 30 s while the proxy's checks come up."""

    def __init__(self, host: Host):
        if host.proxy_namespace:
            _enter_proxy_namespace(host.docker)
        secret = _password(host.env_file)
        last, deadline = "no attempt", time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                sock = socket.create_connection((host.addr, host.port), timeout=max(0.5, min(5, deadline - time.monotonic())))
                reader = sock.makefile("rb")
                sock.sendall(_enc("AUTH", USER, secret))
                try:
                    _dec(reader)
                except ErrorReply as exc:
                    raise Refused(f"AUTH refused ({exc.word()})") from None
                sock.settimeout(10)
                self._sock, self._reader = sock, reader
                return
            except OSError as exc:
                last = type(exc).__name__
                time.sleep(max(0, min(1, deadline - time.monotonic())))
        raise Refused(f"nothing answered on {host.addr}:{host.port} in 30 s ({last})")

    def __call__(self, *words: object):
        self._sock.sendall(_enc(*words))
        return _dec(self._reader)

    def primary(self) -> int:
        """The answering node's role, printed; anything but the primary refuses. Returns its replica count."""
        info = dict(line.split(":", 1) for line in _text(self("INFO", "replication")).splitlines() if ":" in line)
        server = dict(line.split(":", 1) for line in _text(self("INFO", "server")).splitlines() if ":" in line)
        version = server.get("valkey_version", server.get("redis_version"))
        print(f"answering: role {info.get('role')}, version {version}, replicas connected {info.get('connected_slaves')}")
        if info.get("role") != "master":
            raise Refused("the node answering is not the primary: nothing was sent")
        return int(info.get("connected_slaves") or 0)

    def keys(self) -> set[str]:
        cursor, keys = "0", set()
        while True:
            cursor, batch = self("SCAN", cursor, "COUNT", "1000")
            cursor = _text(cursor)
            keys.update(_text(k) for k in batch)
            if cursor == "0":
                return keys


def _name(keys: list[str]) -> None:
    for key in keys[:SHOWN]:
        print(f"    {key}")
    if len(keys) > SHOWN:
        print(f"    … and {len(keys) - SHOWN} more")


def inventory(host: Host) -> int:
    cache = Cache(host)
    cache.primary()
    dbsize = cache("DBSIZE")
    keys = cache.keys()
    inside = sorted(k for k in keys if in_prefix(k))
    outside = sorted(k for k in keys if not in_prefix(k))
    print(f"DBSIZE {dbsize}")
    print(f"keys under {PREFIX} {len(inside)}")
    for collection, n in sorted(Counter(k.split(":")[1] for k in inside).items()):
        print(f"  {n:7d} {collection}")
    print(f"keys outside {PREFIX} {len(outside)}, 0 expected")
    _name(outside)
    path = Path(host.out_dir) / f"cache-prefix-clear-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.keys"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write("".join(f"{k}\n" for k in inside))
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        lines = sum(1 for _ in f)
    print(f"list: {path}, {lines} line(s)")
    return 0


def _read_list(list_file: str) -> list[str]:
    with open(list_file, encoding="utf-8", errors="surrogateescape") as f:
        keys = f.read().splitlines()
    outside = [k for k in keys if not in_prefix(k)]
    if outside:
        raise Refused(f"{len(outside)} line(s) of {list_file} name no key under {PREFIX} -- nothing was deleted")
    if len(set(keys)) != len(keys):
        raise Refused(f"{list_file} names a key twice, which no inventory writes: nothing was deleted")
    return keys


def clear(host: Host, list_file: str) -> int:
    keys = _read_list(list_file)
    state = engine_state(host.docker)
    print(f"engine container: {state}")
    if state == "running":
        raise Refused("the engine container is running: stop the unit first; nothing was deleted")
    cache = Cache(host)
    replicas = cache.primary()
    deleted = failed = 0
    try:
        for key in keys:
            try:
                reply = cache("DEL", key)
            except ErrorReply as exc:
                failed += 1
                print(f"DEL refused ({exc.word()}): {key}")
                continue
            if reply == 1:
                deleted += 1
            else:
                print(f"not deleted ({reply}): {key}")
        print(f"replicas acknowledging -> {cache('WAIT', replicas, '5000')} of {replicas}")
        try:
            after = engine_state(host.docker)
        except Refused:
            after = "unread"
        if after not in ("stopped", "absent"):
            print(f"WARNING: the engine container reads {after} now: a start while the clear ran may have written keys")
    finally:
        # Printed whatever stopped the loop: a later verify takes this run's deleted count.
        print(f"listed={len(keys)} deleted={deleted} failed={failed}")
    return 0 if deleted == len(keys) and failed == 0 else 1


def verify(host: Host, dbsize_before: int, deleted: int) -> int:
    cache = Cache(host)
    cache.primary()
    left = sorted(k for k in cache.keys() if in_prefix(k))
    dbsize = cache("DBSIZE")
    expected = dbsize_before - deleted
    print(f"keys under {PREFIX} {len(left)}, 0 expected")
    _name(left)
    print(f"DBSIZE {dbsize}, {expected} expected ({dbsize_before} less {deleted})")
    passed = not left and dbsize == expected
    print("VERIFIED" if passed else "NOT VERIFIED")
    return 0 if passed else 1


def main(argv: list[str], host: Host = Host()) -> int:
    mode, args = (argv[0] if argv else ""), argv[1:]
    try:
        if mode == "inventory" and not args:
            return inventory(host)
        if mode == "clear" and len(args) == 1:
            return clear(host, args[0])
        if mode == "verify" and len(args) == 2 and all(a.isdigit() for a in args):
            return verify(host, int(args[0]), int(args[1]))
        raise Refused(USAGE)
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 1
    except ErrorReply as exc:
        print(f"REFUSED: the cache answered {exc.word()}")
        return 1
    except BaseException as exc:
        print(f"FAILED: {type(exc).__name__}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
