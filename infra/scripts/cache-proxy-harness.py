#!/usr/bin/env python3
"""The engine role's cache proxy configuration, rendered for an unprivileged namespace, the pinned HAProxy image it
runs on, and the run of the one on the other.

    uv run python infra/scripts/cache-proxy-harness.py fetch --digest sha256:<64 hex> --into <dir>
    uv run python infra/scripts/cache-proxy-harness.py run --rootfs <tree> --scratch <dir> [--case <name>]...

fetch  a network read: pulls `library/haproxy` anonymously from Docker Hub by its index digest, checks the index,
       the linux/amd64 manifest and every layer against their sha256, and applies the layers in order, whiteouts
       included, into <dir>, which must be absent or empty. `.harness-image-digest` is written last, so a tree
       without it is a fetch that did not finish.
run    re-runs itself under `unshare -rn`, an unprivileged user and network namespace, which must list `lo` alone,
       and there runs the tree's HAProxy through the tree's own loader and libraries on the role's render, against
       scripted Sentinels and Valkeys, case by case: each `--case`, or every case in order when none is named. Each
       case prints one PASS or FAIL line; the last line counts every PASS and FAIL line printed and names
       `haproxy -vv`'s first line and the image digest's first 12 hex. Each case's render and HAProxy's stdout and
       stderr stay in <dir>/run-<UTC stamp>-<pid>/<case>/, <dir> made when absent; every process the run starts is
       stopped by its own PID before it exits.

Exit: 0 fetched, or every case passing; 1 a case failing or any other error, printed, a run's summary still counting
the cases run; 2 refused, the reason printed; never 5, which mutate-probe.sh reads as no test run.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import io
import json
import os
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import jinja2

NODES = (
    {"name": "node1", "address": "127.0.0.11"},
    {"name": "node2", "address": "127.0.0.12"},
    {"name": "node3", "address": "127.0.0.13"},
)
MASTER_NAME = "zcache"
REQUIREPASS = "harness-dummy-requirepass"
TEMPLATE = Path(__file__).resolve().parents[1] / "ansible/roles/engine/templates/haproxy.cfg.j2"
# The namespace maps one user and has no /var/lib/haproxy, and a wildcard 6379 would collide with the scripted
# Valkeys on the same port.
EDITS = (
    ("    chroot /var/lib/haproxy\n", ""),
    ("    user haproxy\n", ""),
    ("    group haproxy\n", ""),
    ("    bind 0.0.0.0:6379\n", "    bind 127.0.0.1:6379\n"),
)

IMAGE_DIGEST_FILE = ".harness-image-digest"
REPOSITORY = "https://registry-1.docker.io/v2/library/haproxy"
TOKEN_URL = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/haproxy:pull"
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
WHITEOUT = ".wh."
OPAQUE = ".wh..wh..opq"
# The bits the `tar` filter keeps of a member's mode: no setuid, setgid or sticky, no group or other write.
TAR_FILTER_MODE = 0o755
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class FetchRefused(Exception):
    pass


def render(template: str) -> str:
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)
    text = env.from_string(template).render(
        engine_cache_proxy_nodes=list(NODES),
        engine_cache_proxy_master_name=MASTER_NAME,
        cache_sentinel_requirepass=REQUIREPASS,
    )
    for old, new in EDITS:
        text = text.replace(old, new)
    return text


def _urllib_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url)
    # A blob answers with a redirect to its storage host, which must not receive the registry's bearer token.
    for name, value in headers.items():
        request.add_unredirected_header(name, value)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _verified(body: bytes, digest: str) -> bytes:
    if "sha256:" + hashlib.sha256(body).hexdigest() != digest:
        raise FetchRefused(f"the bytes served for {digest} hash to another digest")
    return body


def _member_ok(name: str) -> bool:
    return not os.path.isabs(name) and ".." not in name.split("/")


def _inside(into: Path, path: str) -> Path:
    root = os.path.realpath(into)
    resolved = os.path.realpath(into / path, strict=os.path.ALLOW_MISSING)
    if resolved == root or resolved.startswith(root + "/"):
        return Path(resolved)
    raise FetchRefused(f"{path!r} resolves to {resolved}, outside the tree")


def _remove(path: Path, modes: dict[Path, int]) -> None:
    for gone in [kept for kept in modes if kept == path or path in kept.parents]:
        del modes[gone]
    if path.is_dir(follow_symlinks=False):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        path.unlink()


def _empty(directory: Path, written: set[Path], modes: dict[Path, int]) -> None:
    """Remove what lower layers put under `directory`, keeping what this layer wrote."""
    if not directory.is_dir(follow_symlinks=False):
        return
    for entry in directory.iterdir():
        if entry not in written:
            _remove(entry, modes)
        elif entry.is_dir(follow_symlinks=False):
            _empty(entry, written, modes)


def _apply(blob: bytes, into: Path, modes: dict[Path, int]) -> None:
    written: set[Path] = set()
    with tarfile.open(fileobj=io.BytesIO(blob)) as layer:
        for member in layer:
            base = os.path.basename(member.name)
            whiteout = base.removeprefix(WHITEOUT) if base.startswith(WHITEOUT) else None
            names = [member.name]
            if member.islnk():
                names.append(member.linkname)
            if whiteout is not None:
                names.append(whiteout)
            refused = [name for name in names if not _member_ok(name)]
            # Either names the directory holding the marker, which a whiteout never removes.
            if whiteout in ("", "."):
                refused.append(whiteout)
            if refused:
                raise FetchRefused(f"layer member {member.name!r} names {refused[0]!r}, which no layer may act on")
            directory = _inside(into, os.path.dirname(member.name))
            if member.islnk():
                _inside(into, member.linkname)
            if base == OPAQUE:
                _empty(directory, written, modes)
                continue
            if whiteout is not None:
                if directory / whiteout not in written:
                    _remove(directory / whiteout, modes)
                continue
            existing = directory / base
            if not (member.isdir() and existing.is_dir(follow_symlinks=False)):
                _remove(existing, modes)
            try:
                layer.extract(member, into, set_attrs=not member.isdir(), filter="tar")
            except tarfile.FilterError as exc:
                raise FetchRefused(str(exc)) from exc
            written.add(existing)
            if member.isdir():
                modes[existing] = member.mode & TAR_FILTER_MODE


def _set_modes(modes: dict[Path, int]) -> None:
    # Modes are set after the last layer's members, deepest first, as `extractall` defers them, and only on a path a
    # later member has not replaced with a link.
    for path, mode in sorted(modes.items(), key=lambda item: len(item[0].parts), reverse=True):
        if os.path.realpath(path) == str(path) and path.is_dir(follow_symlinks=False):
            path.chmod(mode)


def fetch(digest: str, into: Path, get: Callable[[str, Mapping[str, str]], bytes] = _urllib_get) -> None:
    if into.exists() and (not into.is_dir() or any(into.iterdir())):
        raise FetchRefused(f"{into} is not an empty directory")
    token = json.loads(get(TOKEN_URL, {}))["token"]
    headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT}
    index = json.loads(_verified(get(f"{REPOSITORY}/manifests/{digest}", headers), digest))
    amd64 = [
        entry
        for entry in index.get("manifests", [])
        if entry.get("platform", {}).get("os") == "linux" and entry.get("platform", {}).get("architecture") == "amd64"
    ]
    if len(amd64) != 1:
        raise FetchRefused(f"the index lists {len(amd64)} linux/amd64 manifests, not one")
    manifest_digest = amd64[0]["digest"]
    manifest = json.loads(_verified(get(f"{REPOSITORY}/manifests/{manifest_digest}", headers), manifest_digest))
    layers = []
    for layer in manifest["layers"]:
        layers.append(_verified(get(f"{REPOSITORY}/blobs/{layer['digest']}", headers), layer["digest"]))
        print(f"verified {layer['digest']}")
    into.mkdir(parents=True, exist_ok=True)
    modes: dict[Path, int] = {}
    for blob in layers:
        _apply(blob, into, modes)
    _set_modes(modes)
    (into / IMAGE_DIGEST_FILE).write_text(digest + "\n")


CASES = (
    "parse",
    "start",
    "no-early-route",
    "vote-down-cuts-nothing",
    "one-vote-cuts-nothing",
    "no-vote-cuts",
    "contradiction-cuts-both",
    "lost-syn-inside-budget",
    "stalled-exchange",
)
# A proxy re-pin moves this to the candidate's version in its own change, before its run.
PINNED_VERSION = "3.4.5"
UNSHARE = "/usr/bin/unshare"
IP = "/usr/bin/ip"
NFT = "/usr/sbin/nft"
LOADER = "/lib64/ld-linux-x86-64.so.2"
BINARY = "/usr/local/sbin/haproxy"
ENTRYPOINT = "/usr/local/bin/docker-entrypoint.sh"
LD_SO_CONF = "/etc/ld.so.conf"
FRONTEND = ("127.0.0.1", 6379)
METRICS = ("127.0.0.1", 9104)
METRICS_URL = "http://127.0.0.1:9104/metrics?scope=server"
SENTINEL_PORT = 26379
VALKEY_PORT = 6379
VOTE_VIA_NODE3 = "votes-node2/via-node3"
# The reads' cadence, finer than the 0.1 s the bounds' margin allows for.
STEP = 0.05
# Each bound is the source's worst case plus this: wake-ups, the reads' cadence and a shared host's scheduling.
MARGIN = 1.0
# The engine's retry budget, which a cold start's route opens inside; also every wait on a start.
START = 3.40
WINDOW = 10.0
# The source's worst cases: a vote rising after its Sentinel's silence ends or after its Sentinel turns to name the
# vote's node, a vote at full health falling, a route falling after its path turns to 503 and rising after a 200.
SILENT_VOTE_RISE = 3.0
SWITCHED_VOTE_RISE = 4.0
VOTE_FALL = 7.0
ROUTE_FALL = 0.5
ROUTE_RISE = 0.25
# The vote's `inter`, `fastinter` and `timeout check`.
INTER = 2.0
FASTINTER = 1.0
TIMEOUT_CHECK = 2.0
# A stalled reply's hold, past `timeout check`, and the half-width of the window it is aimed at.
HOLD = 2.5
AIM = 0.3


class Refused(Exception):
    pass


class CaseFailed(Exception):
    """The read that failed, with the case's figures."""


def version_ok(first_line: str) -> bool:
    words = first_line.split()
    if "version" not in words[:-1]:
        return False
    word = words[words.index("version") + 1]
    return word == PINNED_VERSION or word.startswith(PINNED_VERSION + "-")


def tree_whole(root: Path) -> bool:
    return (root / IMAGE_DIGEST_FILE).is_file()


def loopback_only(names: Iterable[str]) -> bool:
    return set(names) == {"lo"}


def foreign_mappings(maps: str, root: str) -> list[str]:
    foreign = []
    for line in maps.splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        path = fields[5].strip()
        if "x" in fields[1] and path.startswith("/") and not path.startswith(root + "/"):
            foreign.append(path)
    return foreign


def in_tree(root: Path, path: str) -> Path:
    """`path` resolved inside `root`: a link's absolute target is re-rooted there, never followed on the host, and `..`
    stops at `root`."""
    pending = [part for part in path.split("/") if part not in ("", ".")]
    done: list[str] = []
    links = 0
    while pending:
        part = pending.pop(0)
        if part == "..":
            if done:
                done.pop()
            continue
        here = root.joinpath(*done, part)
        if not here.is_symlink():
            done.append(part)
            continue
        links += 1
        if links > 40:
            raise Refused(f"{path} does not resolve inside {root}: more than 40 links")
        target = os.readlink(here)
        if target.startswith("/"):
            done = []
        pending = [p for p in target.split("/") if p not in ("", ".")] + pending
    return root.joinpath(*done)


def _library_path(root: Path, conf: str = LD_SO_CONF, found: list[Path] | None = None) -> list[Path]:
    found = [] if found is None else found
    for raw in in_tree(root, conf).read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("include "):
            pattern = line.split(None, 1)[1]
            for match in sorted(in_tree(root, os.path.dirname(pattern)).glob(os.path.basename(pattern))):
                _library_path(root, os.path.join(os.path.dirname(pattern), match.name), found)
        elif line and in_tree(root, line).is_dir() and in_tree(root, line) not in found:
            found.append(in_tree(root, line))
    return found


def haproxy_argv(root: Path) -> list[str]:
    """The tree's binary through the tree's loader and libraries, with the flags the image's entrypoint gives a bare
    `haproxy`."""
    loader, binary = in_tree(root, LOADER), in_tree(root, BINARY)
    for path in (loader, binary):
        if not path.is_file():
            raise Refused(f"{path} is not a file of the tree")
    script = in_tree(root, ENTRYPOINT).read_text()
    flags = [flag for match in re.finditer(r'^\s*set -- haproxy((?:\s+-\S+)*)\s+"\$@"', script, re.M) for flag in match[1].split()]
    # Without them the binary would run as no container runs it: a re-pin's entrypoint is read again by hand.
    if not flags:
        raise Refused(f'{ENTRYPOINT} in the tree gives a bare haproxy no flags in a `set -- haproxy <flags> "$@"` line')
    libraries = ":".join(str(path) for path in _library_path(root))
    return [str(loader), "--library-path", libraries, str(binary), *flags]


def _nft(*args: str) -> str:
    result = subprocess.run([NFT, *args], capture_output=True, text=True, timeout=MARGIN)
    if result.returncode != 0:
        raise RuntimeError(f"nft {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def _stop(process: subprocess.Popen) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=MARGIN)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=MARGIN)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                stream.close()


class Procs:
    """A case's processes and its own `nft` table, so that nothing of a case outlives it in a run's one namespace."""

    def __init__(self, name: str) -> None:
        self.table = name.replace("-", "_")
        self.processes: list[subprocess.Popen] = []
        self.table_made = False

    def start(self, argv: list[str], **popen: Any) -> subprocess.Popen:
        process = subprocess.Popen(argv, **popen)
        self.processes.append(process)
        return process

    def nft(self, *args: str) -> str:
        if not self.table_made:
            _nft("add", "table", "inet", self.table)
            self.table_made = True
        return _nft(*args)

    def stop_all(self) -> None:
        failures: list[BaseException] = []
        try:
            for process in reversed(self.processes):
                try:
                    _stop(process)
                except BaseException as exc:
                    failures.append(exc)
            self.processes.clear()
        finally:
            if self.table_made:
                self.table_made = False
                try:
                    _nft("delete", "table", "inet", self.table)
                except BaseException as exc:
                    failures.append(exc)
        # A signal's SystemExit outranks a stop's or the table's failure, so the run unwinds rather than reading a FAIL.
        unwinding = [failure for failure in failures if not isinstance(failure, Exception)]
        if failures:
            raise (unwinding or failures)[0]


def _described(exc: BaseException) -> str:
    text = str(exc) if isinstance(exc, CaseFailed) else f"{type(exc).__name__}: {exc}"
    if exc.__context__ is not None and not exc.__suppress_context__:
        text += f"; raised while handling {_described(exc.__context__)}"
    return text


def run_case(name: str, body: Callable[[Procs], tuple[bool, str]]) -> str:
    procs = Procs(name)
    try:
        try:
            passed, text = body(procs)
        finally:
            procs.stop_all()
    except Exception as exc:
        return f"FAIL {name}: {_described(exc)}"
    return f"{'PASS' if passed else 'FAIL'} {name}: {text}"


def _wait(check: Callable[[], bool], deadline: float) -> float | None:
    """The time `check` first holds, read every STEP, or None at the deadline."""
    while True:
        now = time.monotonic()
        if check():
            return now
        if now >= deadline:
            return None
        time.sleep(STEP)


def _window(end: float) -> Iterator[float]:
    """The read times of a window held until `end`, every STEP; none starts with less than STEP left, where a read's
    deadline would be too near to answer, and the window still runs its full length."""
    while (now := time.monotonic()) < end:
        if end - now >= STEP:
            yield now
        time.sleep(max(min(STEP, end - time.monotonic()), 0))


def _line(process: subprocess.Popen, deadline: float) -> str | None:
    received = b""
    while not received.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
            return None
        chunk = os.read(process.stdout.fileno(), 256)
        if not chunk:
            return None
        received += chunk
    return received.decode().strip()


def _ping(session: socket.socket, deadline: float) -> bool:
    try:
        session.settimeout(max(deadline - time.monotonic(), 0.001))
        session.sendall(b"PING\r\n")
        reply = b""
        while not reply.endswith(b"\r\n"):
            session.settimeout(max(deadline - time.monotonic(), 0.001))
            chunk = session.recv(64)
            if not chunk:
                return False
            reply += chunk
        return reply == b"+PONG\r\n"
    except OSError:
        return False


def _attempt(deadline: float) -> socket.socket | None:
    """A new session through the frontend, when it gets its PONG by the deadline."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    try:
        session = socket.create_connection(FRONTEND, timeout=remaining)
    except OSError:
        return None
    if _ping(session, deadline):
        return session
    session.close()
    return None


def _ended(session: socket.socket) -> bool:
    try:
        return bool(select.select([session], [], [], 0)[0]) and session.recv(64, socket.MSG_PEEK) == b""
    except OSError:
        return True


def _ends(sessions: Sequence[socket.socket], deadline: float) -> list[float] | None:
    ended: dict[int, float] = {}
    while True:
        now = time.monotonic()
        for index, session in enumerate(sessions):
            if index not in ended and _ended(session):
                ended[index] = now
        if len(ended) == len(sessions):
            return [ended[index] for index in range(len(sessions))]
        if now >= deadline:
            return None
        time.sleep(STEP)


Metrics = dict[tuple[str, str, str], dict[str, float]]
SERIES = re.compile(r"^(haproxy_server_\w+)\{([^}]*)\} (\S+)$", re.M)
LABEL = re.compile(r'(\w+)="([^"]*)"')


def _scrape(deadline: float | None = None) -> Metrics:
    """The exporter's server series, read within the margin, or by `deadline` when that comes sooner: a read inside a
    held window ends with the window."""
    timeout = MARGIN if deadline is None else max(min(MARGIN, deadline - time.monotonic()), 0.001)
    with urllib.request.urlopen(METRICS_URL, timeout=timeout) as response:
        body = response.read().decode()
    metrics: Metrics = {}
    for name, labels, value in SERIES.findall(body):
        label = dict(LABEL.findall(labels))
        key = (name, label.get("proxy", ""), label.get("server", ""))
        metrics.setdefault(key, {})[label.get("state", "")] = float(value)
    return metrics


def _state(metrics: Metrics, name: str, server: str) -> str | None:
    """The `state` label whose series reads 1, for `<backend>/<server>`."""
    states = metrics.get((name, *server.split("/")), {})
    return next((state for state, value in states.items() if value == 1), None)


def _number(metrics: Metrics, name: str, server: str) -> float:
    return metrics[(name, *server.split("/"))][""]


def _up(server: str, deadline: float | None = None) -> Callable[[], bool]:
    return lambda: _state(_scrape(deadline), "haproxy_server_status", server) == "UP"


def _address(node: str) -> str:
    return next(entry["address"] for entry in NODES if entry["name"] == node)


def _start_haproxy(procs: Procs, directory: Path, haproxy: list[str]) -> tuple[subprocess.Popen, float]:
    with (directory / "haproxy.out").open("wb") as out, (directory / "haproxy.err").open("wb") as err:
        started = time.monotonic()
        process = procs.start([*haproxy, "-f", str(directory / "haproxy.cfg")], stdout=out, stderr=err, cwd=directory)
    return process, started


def _listening(process: subprocess.Popen, deadline: float) -> bool:
    while process.poll() is None:
        try:
            socket.create_connection(METRICS, timeout=STEP).close()
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(STEP)
    return False


class Run(NamedTuple):
    directory: Path
    haproxy: list[str]
    render: str


class Bench:
    """One case's directory, scripted peers, HAProxy and client sessions."""

    def __init__(self, run: Run, procs: Procs, name: str) -> None:
        self.procs = procs
        self.haproxy = run.haproxy
        self.directory = run.directory / name
        self.directory.mkdir()
        (self.directory / "haproxy.cfg").write_text(run.render)
        self.sentinels: dict[str, subprocess.Popen] = {}
        self.sessions: list[socket.socket] = []
        self.started = 0.0

    def peers(self) -> None:
        peers = []
        with (self.directory / "peers.err").open("wb") as err:
            for node in NODES:
                for role in ("sentinel", "valkey"):
                    argv = [sys.executable, str(Path(__file__).resolve()), "peer", role, node["address"], str(self.directory)]
                    process = self.procs.start(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, bufsize=0)
                    peers.append((role, node, process))
                    if role == "sentinel":
                        self.sentinels[node["name"]] = process
        deadline = time.monotonic() + START
        for role, node, process in peers:
            if _line(process, deadline) != "listening":
                raise CaseFailed(f"the scripted {role} on {node['address']} was not listening by {START:.2f} s")

    def start_haproxy(self) -> None:
        process, self.started = _start_haproxy(self.procs, self.directory, self.haproxy)
        if not _listening(process, self.started + START):
            raise CaseFailed(f"HAProxy not listening within {START:.2f} s, exit {process.poll()}")

    def tell(self, node: str, command: str) -> float:
        sentinel = self.sentinels[node]
        sentinel.stdin.write(f"{command}\n".encode())
        answer = _line(sentinel, time.monotonic() + MARGIN)
        if answer != "ok":
            raise CaseFailed(f"the scripted Sentinel on {_address(node)} answered {command!r} with {answer!r} in {MARGIN:.1f} s")
        return time.monotonic()

    def silence(self, node: str) -> float:
        table = self.procs.table
        self.procs.nft("add", "chain", "inet", table, f"silent_{node}", "{ type filter hook input priority 0; }")
        self.procs.nft("add", "rule", "inet", table, f"silent_{node}", f"ip daddr {_address(node)} tcp dport {SENTINEL_PORT} drop")
        return time.monotonic()

    def answer(self, node: str) -> float:
        self.procs.nft("flush", "chain", "inet", self.procs.table, f"silent_{node}")
        return time.monotonic()

    def routed(self, deadline: float) -> float | None:
        """The time a new session gets its PONG, tried every STEP until the deadline."""
        while True:
            session = _attempt(deadline)
            if session is not None:
                self.sessions.append(session)
                return time.monotonic()
            if time.monotonic() >= deadline:
                return None
            time.sleep(STEP)

    def votes_up(self) -> None:
        """Waits for node2's three votes, so a fault lands on a vote at full health."""
        votes = [f"votes-node2/via-{node['name']}" for node in NODES]

        def all_up() -> bool:
            metrics = _scrape()
            return all(_state(metrics, "haproxy_server_status", vote) == "UP" for vote in votes)

        if _wait(all_up, self.started + START) is None:
            raise CaseFailed(f"node2's three votes not UP within {START:.2f} s of the start")

    def two_sessions(self) -> list[socket.socket]:
        for _ in range(2):
            if self.routed(time.monotonic() + START) is None:
                raise CaseFailed(f"no route for a session within {START:.2f} s")
        return self.sessions[-2:]

    def out(self) -> str:
        return (self.directory / "haproxy.out").read_text(errors="replace")

    def has_line(self, pattern: str) -> bool:
        return re.search(pattern, self.out(), re.M) is not None

    def terminations(self, sessions: Sequence[socket.socket]) -> list[str]:
        """Each session's connection-log termination state, read until the margin."""
        ports = [f"127.0.0.1:{session.getsockname()[1]}" for session in sessions]
        found: dict[str, str] = {}

        def read() -> bool:
            for line in self.out().splitlines():
                fields = line.split()
                if len(fields) > 6 and fields[0] in ports and fields[2] == "cache":
                    found[fields[0]] = fields[6]
            return len(found) == len(ports)

        if _wait(read, time.monotonic() + MARGIN) is None:
            raise CaseFailed(f"no connection line for {', '.join(p for p in ports if p not in found)} within {MARGIN:.1f} s")
        return [found[port] for port in ports]

    def events(self, role: str, node: str) -> list[tuple[float, str, str]]:
        """A peer's `<stamp> <open|reply|close> <client port>` lines, a line still being written left out."""
        lines = (self.directory / f"{role}-{_address(node)}.events").read_text().split("\n")[:-1]
        return [(float(stamp), event, port) for stamp, event, port in (line.split() for line in lines)]

    def opens(self, role: str, node: str) -> list[float]:
        return [stamp for stamp, event, _ in self.events(role, node) if event == "open"]

    def prompt_close(self, since: float) -> float | None:
        """The first close after `since` of a Sentinel 3 connection the client closed as soon as its master reply
        landed: votes-node2/via-node3's check, the two DOWN votes waiting out `timeout check` on theirs."""
        replied: dict[str, float] = {}
        for stamp, event, port in self.events("sentinel", "node3"):
            if event == "open":
                replied.pop(port, None)
            elif event == "reply":
                replied[port] = stamp
            elif event == "close" and port in replied and since < stamp < replied[port] + TIMEOUT_CHECK / 2:
                return stamp
        return None

    def close(self) -> None:
        for session in self.sessions:
            session.close()


def _case_parse(bench: Bench) -> str:
    directory = bench.directory
    with (directory / "haproxy.out").open("wb") as out, (directory / "haproxy.err").open("wb") as err:
        result = subprocess.run(
            [*bench.haproxy, "-c", "-V", "-f", str(directory / "haproxy.cfg")], stdout=out, stderr=err, timeout=START
        )
    printed = (directory / "haproxy.out").read_text() + (directory / "haproxy.err").read_text()
    noise = [line for line in printed.splitlines() if re.search(r"Warnings were found\.|\[WARNING\]|\[ALERT\]", line)]
    if result.returncode != 0 or "Configuration file is valid" not in printed or noise:
        raise CaseFailed(f"haproxy -c exited {result.returncode}: {' | '.join(noise or printed.splitlines()[:3])}")
    return "Configuration file is valid, no warning or alert"


def _case_start(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    routed = bench.routed(bench.started + START)
    if routed is None:
        raise CaseFailed(f"no PONG through the frontend within {START:.2f} s of the start")
    figure = f"route {routed - bench.started:.2f} s (bound {START:.2f} s)"
    votes = len(re.findall(r"^Server votes-node2/via-node\d is UP", bench.out(), re.M))
    if votes < 2:
        raise CaseFailed(f"a session routed after {votes} votes-node2 UP line(s); {figure}")
    metrics = _scrape()
    reads = [(server, _state(metrics, "haproxy_server_check_status", server)) for server in ("node1/valkey", "node3/valkey")]
    figures = "; ".join([figure, *(f"{server} {state}" for server, state in reads)])
    rose = [server for server, _ in reads if bench.has_line(rf"^Server {server} is UP")]
    if rose or any(state != "L7STS" for _, state in reads):
        raise CaseFailed(f"{', '.join(rose) or 'a route'} read UP or a status other than L7STS; {figures}")
    return figures


def _case_no_early_route(bench: Bench) -> str:
    bench.peers()
    bench.silence("node1")
    bench.silence("node3")
    bench.start_haproxy()
    if _wait(_up("node2/valkey"), bench.started + START) is None:
        raise CaseFailed(f"node2/valkey not UP within {START:.2f} s on one vote")
    opened = time.monotonic()
    for now in _window(opened + WINDOW):
        if not _up("node2/valkey", opened + WINDOW)():
            raise CaseFailed(f"node2/valkey not UP {now - opened:.2f} s into the {WINDOW:.0f} s on one vote")
        session = _attempt(opened + WINDOW)
        if session is not None:
            session.close()
            raise CaseFailed(f"a session got its PONG on one vote, {now - opened:.2f} s into the {WINDOW:.0f} s")
    answered = bench.answer("node1")
    bound = SILENT_VOTE_RISE + MARGIN
    routed = bench.routed(answered + bound)
    if routed is None:
        raise CaseFailed(f"no route within {bound:.2f} s of a second Sentinel answering")
    return f"route {routed - answered:.2f} s after a second Sentinel answered (bound {bound:.2f} s); no PONG on one vote"


def _case_vote_down_cuts_nothing(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    sessions = bench.two_sessions()
    silenced = bench.silence("node3")
    fell = routed = None
    for now in _window(silenced + WINDOW):
        for index, session in enumerate(sessions, 1):
            if not _ping(session, silenced + WINDOW):
                raise CaseFailed(f"session {index} got no PONG {now - silenced:.2f} s into Sentinel 3's silence")
        if fell is None:
            fell = now if bench.has_line(rf"^Server {VOTE_VIA_NODE3} is DOWN") else None
        elif routed is None and (session := _attempt(silenced + WINDOW)) is not None:
            routed = now
            session.close()
    if fell is None or routed is None:
        missing = f"no {VOTE_VIA_NODE3} DOWN line" if fell is None else "no new session routed after the DOWN line"
        raise CaseFailed(f"{missing} in Sentinel 3's {WINDOW:.0f} s of silence")
    answered = bench.answer("node3")
    bound = SILENT_VOTE_RISE + MARGIN
    rose = _wait(_up(VOTE_VIA_NODE3), answered + bound)
    if rose is None:
        raise CaseFailed(f"{VOTE_VIA_NODE3} not UP within {bound:.2f} s of Sentinel 3 answering")
    return f"vote UP again {rose - answered:.2f} s (bound {bound:.2f} s); DOWN at {fell - silenced:.2f} s, both sessions answering"


def _case_one_vote_cuts_nothing(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    sessions = bench.two_sessions()
    bench.tell("node1", "refuse")
    faulted = bench.silence("node3")
    votes = ("votes-node2/via-node1", VOTE_VIA_NODE3)
    deadline = faulted + VOTE_FALL + MARGIN

    def both_down() -> bool:
        metrics = _scrape()
        return all(_state(metrics, "haproxy_server_status", vote) == "DOWN" for vote in votes)

    if _wait(both_down, deadline) is None:
        raise CaseFailed(f"{' and '.join(votes)} not both DOWN within {deadline - faulted:.2f} s")
    metrics = _scrape()
    states = [_state(metrics, "haproxy_server_check_status", vote) for vote in votes]
    reads = f"{votes[0]} {states[0]}; {votes[1]} {states[1]}"
    if states != ["L4CON", "L4TOUT"]:
        raise CaseFailed(f"the two DOWN votes read other than L4CON and L4TOUT; {reads}")
    opened = time.monotonic()
    for now in _window(opened + WINDOW):
        for index, session in enumerate(sessions, 1):
            if not _ping(session, opened + WINDOW):
                raise CaseFailed(f"session {index} got no PONG {now - opened:.2f} s into the {WINDOW:.0f} s at one vote; {reads}")
        if (session := _attempt(opened + WINDOW)) is not None:
            session.close()
            raise CaseFailed(f"a new session routed at one vote, {now - opened:.2f} s into the {WINDOW:.0f} s; {reads}")
    answered = bench.answer("node3")
    bound = SILENT_VOTE_RISE + MARGIN
    routed = bench.routed(answered + bound)
    if routed is None:
        raise CaseFailed(f"no new route within {bound:.2f} s of Sentinel 3 answering; {reads}")
    return f"route {routed - answered:.2f} s after Sentinel 3 answered (bound {bound:.2f} s); {reads}"


def _case_no_vote_cuts(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    sessions = bench.two_sessions()
    silenced = [bench.silence(node["name"]) for node in NODES][-1]
    bound = VOTE_FALL + ROUTE_FALL + MARGIN
    ends = _ends(sessions, silenced + bound)
    if ends is None:
        raise CaseFailed(f"the sessions not both ended within {bound:.2f} s of every Sentinel's silence")
    figure = f"both sessions cut {max(ends) - silenced:.2f} s (bound {bound:.2f} s)"
    terminations = bench.terminations(sessions)
    if any(not state.startswith("D") for state in terminations):
        raise CaseFailed(f"terminations {', '.join(terminations)}, not each opening with D; {figure}")
    return f"{figure}; terminations {', '.join(terminations)}"


def _case_contradiction_cuts_both(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    sessions = bench.two_sessions()
    first = bench.tell("node1", "name node1")
    time.sleep(max(first + 1.0 - time.monotonic(), 0))
    switched = bench.tell("node3", "name node1")
    cut_bound = SWITCHED_VOTE_RISE + ROUTE_FALL + MARGIN
    ends = _ends(sessions, switched + cut_bound)
    if ends is None:
        raise CaseFailed(f"the sessions on node2 not both ended within {cut_bound:.2f} s of the second switch")
    cut = max(ends)
    figures = f"cut {cut - switched:.2f} s (bound {cut_bound:.2f} s)"
    terminations = bench.terminations(sessions)
    state = _state(_scrape(), "haproxy_server_check_status", "node2/valkey")
    figures += f"; terminations {', '.join(terminations)}; node2/valkey {state}"
    if any(not t.startswith("D") for t in terminations) or state != "L7STS":
        raise CaseFailed(f"a termination not opening with D or node2/valkey not L7STS; {figures}")
    route_bound = VOTE_FALL + ROUTE_RISE + MARGIN
    routed = bench.routed(switched + route_bound)
    if routed is None:
        raise CaseFailed(f"no new session routed within {route_bound:.2f} s of the second switch; {figures}")
    figures += f"; route to node1 {routed - switched:.2f} s (bound {route_bound:.2f} s)"
    on_node2 = [t for t in bench.opens("valkey", "node2") if t > cut]
    on_node1 = [t for t in bench.opens("valkey", "node1") if t > cut]
    if on_node2 or not on_node1:
        raise CaseFailed(f"{len(on_node2)} session(s) reached node2 and {len(on_node1)} node1 after the cut; {figures}")
    return figures


def _case_lost_syn_inside_budget(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    failures = "haproxy_server_check_failures_total"
    before = _number(_scrape(), failures, VOTE_VIA_NODE3)
    table = bench.procs.table
    bench.procs.nft("add", "set", "inet", table, "seen", "{ type inet_service; flags dynamic; }")
    bench.procs.nft("add", "chain", "inet", table, "first_syn", "{ type filter hook input priority 0; }")
    rule = f"ip daddr {_address('node3')} tcp dport {SENTINEL_PORT} tcp flags & (syn | ack) == syn"
    bench.procs.nft("add", "rule", "inet", table, "first_syn", f"{rule} tcp sport != @seen add @seen {{ tcp sport }} counter drop")
    began = time.monotonic()
    longest, not_up = 0.0, None
    for now in _window(began + WINDOW):
        metrics = _scrape(began + WINDOW)
        if not_up is None and _state(metrics, "haproxy_server_status", VOTE_VIA_NODE3) != "UP":
            not_up = now - began
        longest = max(longest, _number(metrics, "haproxy_server_check_duration_seconds", VOTE_VIA_NODE3))
    # Sentinel 3's SYNs pass the rule from here, so its counter and its set are read at one count.
    bench.procs.nft("insert", "rule", "inet", table, "first_syn", f"ip daddr {_address('node3')} accept")
    chain = json.loads(bench.procs.nft("-j", "list", "chain", "inet", table, "first_syn"))["nftables"]
    dropped = next(e["counter"]["packets"] for item in chain if "rule" in item for e in item["rule"]["expr"] if "counter" in e)
    listed = json.loads(bench.procs.nft("-j", "list", "set", "inet", table, "seen"))["nftables"]
    ports = len(next(item["set"] for item in listed if "set" in item).get("elem", []))
    bench.procs.nft("flush", "chain", "inet", table, "first_syn")
    after = _number(_scrape(), failures, VOTE_VIA_NODE3)
    if dropped != ports:
        raise CaseFailed(f"the rule dropped {dropped} SYNs for {ports} connections")
    judged = f"{dropped} first SYNs dropped for {ports} connections; failures {before:.0f} -> {after:.0f}"
    if not_up is not None or after != before or bench.has_line(rf"^Server {VOTE_VIA_NODE3} is DOWN"):
        down = "" if not_up is None else f"not UP at {not_up:.2f} s; "
        raise CaseFailed(f"{VOTE_VIA_NODE3} failed a check or fell in the {WINDOW:.0f} s: {down}{judged}")
    if longest < 1.0:
        raise CaseFailed(f"no check of {VOTE_VIA_NODE3} lasted 1.0 s or more, the longest {longest:.3f} s; {judged}")
    return f"longest check {longest:.3f} s (at least 1.000 s); {judged}"


def _case_stalled_exchange(bench: Bench) -> str:
    bench.peers()
    bench.start_haproxy()
    bench.votes_up()
    failures, status = "haproxy_server_check_failures_total", "haproxy_server_check_status"
    for attempt in range(1, 4):
        before = _number(_scrape(), failures, VOTE_VIA_NODE3)
        since = time.monotonic()
        if _wait(lambda: bench.prompt_close(since) is not None, since + INTER + MARGIN) is None:
            raise CaseFailed(f"no check of {VOTE_VIA_NODE3} closed within {INTER + MARGIN:.1f} s, try {attempt}")
        closed = bench.prompt_close(since)
        aimed = closed + INTER
        bench.tell("node3", f"hold {aimed - AIM:.6f} {aimed + AIM:.6f} {HOLD}")

        def landed() -> bool:
            metrics = _scrape()
            return _number(metrics, failures, VOTE_VIA_NODE3) == before + 1 and _state(metrics, status, VOTE_VIA_NODE3) == "L7TOUT"

        failed = _wait(landed, aimed + AIM + TIMEOUT_CHECK + MARGIN)
        if failed is not None:
            break
    else:
        raise CaseFailed("the stall did not land in three tries")
    bound = FASTINTER + MARGIN
    passed = _wait(lambda: _state(_scrape(), status, VOTE_VIA_NODE3) == "L7OK", failed + bound)
    if passed is None or bench.has_line(rf"^Server {VOTE_VIA_NODE3} is DOWN"):
        what = "a DOWN line" if passed is not None else f"no L7OK within {bound:.2f} s"
        raise CaseFailed(f"{VOTE_VIA_NODE3} after one stalled exchange: {what}")
    return f"L7OK {passed - failed:.2f} s after the stalled check failed (bound {bound:.2f} s); landed on try {attempt}, no DOWN"


CASE_BODIES: dict[str, Callable[[Bench], str]] = {
    "parse": _case_parse,
    "start": _case_start,
    "no-early-route": _case_no_early_route,
    "vote-down-cuts-nothing": _case_vote_down_cuts_nothing,
    "one-vote-cuts-nothing": _case_one_vote_cuts_nothing,
    "no-vote-cuts": _case_no_vote_cuts,
    "contradiction-cuts-both": _case_contradiction_cuts_both,
    "lost-syn-inside-budget": _case_lost_syn_inside_budget,
    "stalled-exchange": _case_stalled_exchange,
}


def _bench_body(run: Run, name: str, procs: Procs) -> tuple[bool, str]:
    bench = Bench(run, procs, name)
    try:
        return True, CASE_BODIES[name](bench)
    finally:
        bench.close()


def process_tree(pid: int, proc: Path = Path("/proc")) -> list[int]:
    """`pid` and every descendant, from each task's `children`; a process gone meanwhile is left out of the walk."""
    found, pending = [], [pid]
    while pending:
        current = pending.pop()
        found.append(current)
        for task in sorted((proc / str(current) / "task").glob("*")):
            with contextlib.suppress(OSError):
                pending += [int(child) for child in (task / "children").read_text().split()]
    return found


def foreign_code(pid: int, root: str, proc: Path = Path("/proc")) -> list[str]:
    """`foreign_mappings` over `pid` and every process under it; a master whose maps read nothing is refused."""
    try:
        maps = (proc / str(pid) / "maps").read_text()
    except OSError as exc:
        raise Refused(f"the maps of the once-per-run HAProxy's master, PID {pid}, could not be read: {exc}") from exc
    if not maps.strip():
        raise Refused(f"the maps of the once-per-run HAProxy's master, PID {pid}, read empty: it has exited")
    foreign = foreign_mappings(maps, root)
    for child in process_tree(pid, proc)[1:]:
        with contextlib.suppress(OSError):
            maps = (proc / str(child) / "maps").read_text()
            foreign += [path for path in foreign_mappings(maps, root) if path not in foreign]
    return foreign


def _mapping_read(run: Run, rootfs: Path) -> list[str] | None:
    """The code the once-per-run HAProxy maps from outside the tree; None, no read, when it does not listen in time."""
    directory = run.directory / "maps"
    directory.mkdir()
    (directory / "haproxy.cfg").write_text(run.render)
    procs = Procs("maps")
    try:
        process, _ = _start_haproxy(procs, directory, run.haproxy)
        if not _listening(process, time.monotonic() + START):
            return None
        foreign = foreign_code(process.pid, str(rootfs))
        if process.poll() is not None:
            raise Refused(f"the once-per-run HAProxy's master, PID {process.pid}, exited during its mapping read")
        return foreign
    finally:
        procs.stop_all()


def _exit_on_signal(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def unwind_on_signals() -> None:
    """SIGTERM and SIGHUP raise SystemExit, so every `finally` stops by PID what the run started."""
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, _exit_on_signal)


def _refused(reason: str) -> int:
    print(f"refused: {reason}", file=sys.stderr)
    return 2


def run_inside(rootfs: Path, scratch: Path, cases: Sequence[str]) -> int:
    names = [name for _, name in socket.if_nameindex()]
    if not loopback_only(names):
        return _refused(f"the namespace lists {', '.join(names) or 'no interface'}, not lo alone")
    try:
        subprocess.run([IP, "link", "set", "lo", "up"], check=True, timeout=MARGIN)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return _refused(f"{IP} link set lo up: {exc}")
    try:
        haproxy = haproxy_argv(rootfs)
        printed = subprocess.run([*haproxy, "-vv"], capture_output=True, text=True, timeout=START).stdout
    except (Refused, OSError, subprocess.TimeoutExpired) as exc:
        return _refused(str(exc))
    first = (printed.splitlines() or [""])[0]
    if not version_ok(first):
        return _refused(
            f"the binary printed {first!r}, not {PINNED_VERSION}, PINNED_VERSION in infra/scripts/cache-proxy-harness.py"
        )
    digest = (rootfs / IMAGE_DIGEST_FILE).read_text().strip().removeprefix("sha256:")
    lines: list[str] = []
    broken = False
    try:
        directory = scratch / f"run-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
        directory.mkdir(parents=True)
        run = Run(directory, haproxy, render(TEMPLATE.read_text()))
        try:
            foreign = _mapping_read(run, rootfs)
        except Refused as exc:
            return _refused(str(exc))
        if foreign:
            return _refused(f"HAProxy maps code from outside the tree: {', '.join(foreign)}")
        if foreign is None:
            lines.append(f"FAIL maps: the once-per-run HAProxy did not listen within {START:.2f} s, so no mapping read happened")
            print(lines[-1], flush=True)
        for name in cases:
            lines.append(run_case(name, functools.partial(_bench_body, run, name)))
            print(lines[-1], flush=True)
    except Exception as exc:
        print(f"error outside the cases: {_described(exc)}", file=sys.stderr)
        broken = True
    passed = sum(line.startswith("PASS ") for line in lines)
    print(f"{passed} passed, {len(lines) - passed} failed -- {first} -- image {digest[:12]}", flush=True)
    return 0 if passed == len(lines) == len(cases) and not broken else 1


def run(rootfs: Path, scratch: Path, cases: Sequence[str]) -> int:
    """Refuses outside the namespace what it can, then re-runs itself inside one; nothing of the tree runs here."""
    rootfs, scratch = rootfs.resolve(), scratch.resolve()
    if not tree_whole(rootfs):
        return _refused(f"{rootfs} holds no {IMAGE_DIGEST_FILE}: its fetch did not finish")
    missing = [tool for tool in (UNSHARE, IP, NFT) if not os.access(tool, os.X_OK)]
    if missing:
        return _refused(f"no {', '.join(missing)}")
    try:
        # The scratch path, unread by the empty program, puts this process too in a read by command line.
        made = subprocess.run(
            [UNSHARE, "-rn", sys.executable, "-c", "", str(scratch)], capture_output=True, text=True, timeout=START
        )
    except subprocess.TimeoutExpired:
        return _refused(f"{UNSHARE} -rn did not return within {START:.2f} s")
    if made.returncode != 0:
        return _refused(f"{UNSHARE} -rn cannot make a user and network namespace here: {made.stderr.strip()}")
    scratch.mkdir(parents=True, exist_ok=True)
    argv = [UNSHARE, "-rn", sys.executable, str(Path(__file__).resolve()), "run", "--inside"]
    argv += ["--rootfs", str(rootfs), "--scratch", str(scratch), *(word for case in cases for word in ("--case", case))]
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(UNSHARE, argv)


def _master_reply(address: str) -> bytes:
    fields = {
        "name": MASTER_NAME,
        "ip": address,
        "port": str(VALKEY_PORT),
        "runid": "0" * 40,
        "flags": "master",
        "link-pending-commands": "0",
        "link-refcount": "1",
        "last-ping-sent": "0",
        "last-ok-ping-reply": "100",
        "last-ping-reply": "100",
        "down-after-milliseconds": "5000",
        "info-refresh": "1000",
        "role-reported": "master",
        "role-reported-time": "100000",
        "config-epoch": "1",
        "num-slaves": "2",
        "num-other-sentinels": "2",
        "quorum": "2",
        "failover-timeout": "60000",
        "parallel-syncs": "1",
    }
    items = [word for pair in fields.items() for word in pair]
    return f"*{len(items)}\r\n".encode() + b"".join(f"${len(word)}\r\n{word}\r\n".encode() for word in items)


def peer_command(
    line: str, named: list[str], held: list[tuple[float, float, float]], refuse: threading.Event, refused: threading.Event
) -> str:
    """Applies one command line to a peer and returns its answer: `ok`, or why the command has not taken effect."""
    word, *args = line.split()
    if word == "name":
        named[0] = args[0]
    elif word == "hold":
        held[0] = (float(args[0]), float(args[1]), float(args[2]))
    elif word == "refuse":
        refuse.set()
        # Half the margin, so the answer reaches the harness inside its own read's.
        if not refused.wait(MARGIN / 2):
            return f"refuse not taken: the listener still open after {MARGIN / 2:.1f} s"
    return "ok"


def peer(role: str, address: str, directory: Path) -> int:
    """A scripted Sentinel or Valkey on `address`, taking `peer_command`'s commands one per stdin line; `hold <from> <to>
    <seconds>` holds the master reply on connections accepted in that monotonic window. Each connection's open, master
    reply and close go to its events file."""
    lock = threading.Lock()
    named, held = ["node2"], [(0.0, 0.0, 0.0)]
    refuse, refused = threading.Event(), threading.Event()
    events = (directory / f"{role}-{address}.events").open("a", buffering=1)

    def record(event: str, port: int, stamp: float | None = None) -> None:
        with lock:
            events.write(f"{time.monotonic() if stamp is None else stamp:.6f} {event} {port}\n")

    def answer(word: bytes, opened: float) -> bytes:
        if role == "valkey" or word in (b"AUTH", b"PING"):
            return {b"AUTH": b"+OK\r\n", b"PING": b"+PONG\r\n"}.get(word, b"-ERR unknown command\r\n")
        if word != b"SENTINEL":
            return b"-ERR unknown command\r\n"
        start, end, seconds = held[0]
        if start <= opened <= end:
            time.sleep(seconds)
        return _master_reply(_address(named[0]))

    def serve(connection: socket.socket, port: int, opened: float) -> None:
        record("open", port, opened)
        received = b""
        with connection:
            while True:
                try:
                    chunk = connection.recv(4096)
                except OSError:
                    chunk = b""
                if not chunk:
                    record("close", port)
                    return
                received += chunk
                while b"\r\n" in received:
                    line, received = received.split(b"\r\n", 1)
                    word = line.split(b" ", 1)[0].upper()
                    with contextlib.suppress(OSError):
                        connection.sendall(answer(word, opened))
                    if word == b"SENTINEL" and role == "sentinel":
                        record("reply", port)

    def commands() -> None:
        for line in sys.stdin:
            print(peer_command(line, named, held, refuse, refused), flush=True)
        os._exit(0)

    listener = socket.socket()
    # A connection this side closed first leaves TIME_WAIT on this fixed address, which would refuse the next case's bind.
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((address, SENTINEL_PORT if role == "sentinel" else VALKEY_PORT))
    listener.listen(64)
    listener.settimeout(STEP)
    threading.Thread(target=commands, daemon=True).start()
    print("listening", flush=True)
    while not refuse.is_set():
        try:
            connection, (_, port) = listener.accept()
        except TimeoutError:
            continue
        connection.setblocking(True)
        threading.Thread(target=serve, args=(connection, port, time.monotonic()), daemon=True).start()
    listener.close()
    refused.set()
    threading.Event().wait()
    return 0


def _digest(value: str) -> str:
    if not DIGEST.fullmatch(value):
        raise argparse.ArgumentTypeError("expected sha256:<64 lowercase hex>")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", help="pull the pinned image's layers into an empty directory")
    fetch_parser.add_argument("--digest", required=True, type=_digest)
    fetch_parser.add_argument("--into", required=True, type=Path)
    run_parser = commands.add_parser("run", help="run the role's render on the tree's HAProxy against scripted peers")
    run_parser.add_argument("--rootfs", required=True, type=Path)
    run_parser.add_argument("--scratch", required=True, type=Path)
    run_parser.add_argument("--case", action="append", choices=CASES, dest="cases")
    run_parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    peer_parser = commands.add_parser("peer", help="the run's own scripted Sentinel or Valkey")
    peer_parser.add_argument("role", choices=("sentinel", "valkey"))
    peer_parser.add_argument("address")
    peer_parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    if args.command == "run":
        unwind_on_signals()
        cases = args.cases or list(CASES)
        return run_inside(args.rootfs, args.scratch, cases) if args.inside else run(args.rootfs, args.scratch, cases)
    if args.command == "peer":
        return peer(args.role, args.address, args.directory)
    try:
        fetch(args.digest, args.into)
    except FetchRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"fetched {args.into} from haproxy@{args.digest[:19]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
