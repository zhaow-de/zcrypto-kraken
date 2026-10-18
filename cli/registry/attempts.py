"""The trial-attempts log: one hash-chained JSONL file per clone, in the main checkout's `.local/`, and the count that
reconciles its attempts with the landed records and readings; design in docs/specs/00133-t0222-trial-attempts-design.md."""

from __future__ import annotations

import dataclasses
import fcntl
import os
import re
import secrets
import socket
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cli.registry import ReadingLedger, TrialRegistry
from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import GENESIS_HASH, VERDICTS, canonical_json, compute_hash, loads_strict
from cli.registry.store import _read_healing

LOG_RELPATH = Path(".local") / "trial-attempts.jsonl"
REGISTRY_RELPATH = "docs/reference/trial-registry.jsonl"
LEDGER_RELPATH = "docs/reference/reading-ledger.jsonl"
ALLOWLIST = "docs/reference/trial-attempt-logs.txt"
DEVELOP = "refs/remotes/origin/develop"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
_ALLOWLIST_ROW = re.compile(r"[0-9a-f]{32} \S+")

_LINE_KEYS = {
    "genesis": frozenset({"seq", "kind", "log_id", "host", "timestamp", "prev_hash", "line_hash"}),
    "begin": frozenset(
        {
            "seq",
            "kind",
            "attempt",
            "timestamp",
            "host",
            "pid",
            "boot",
            "worktree",
            "branch",
            "invocation",
            "spec_hash",
            "family",
            "bucket",
            "n_trials",
            "registry",
            "ledger",
            "prev_hash",
            "line_hash",
        }
    ),
    "end": frozenset(
        {"seq", "kind", "attempt", "timestamp", "verdict", "stop", "failed", "metrics", "metrics_hash", "prev_hash", "line_hash"}
    ),
}


class AttemptLogError(RegistryError):
    pass


def _git(code_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(code_root), *args], capture_output=True, encoding="utf-8", check=False)


def _write_line(fd: int, line: bytes) -> None:
    written = os.write(fd, line)
    if written != len(line):
        raise OSError(f"wrote {written} of the line's {len(line)} bytes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main_checkout(code_root: Path) -> Path:
    common = Path(_git(code_root, "rev-parse", "--git-common-dir").stdout.strip())
    parent = (common if common.is_absolute() else Path(code_root) / common).resolve().parent
    top = _git(parent, "rev-parse", "--show-toplevel")
    if top.returncode != 0 or Path(top.stdout.strip()).resolve() != parent:
        raise AttemptLogError(
            f"no main checkout at {parent}, resolved from git rev-parse --git-common-dir: run from a clone with a working tree"
        )
    return parent


def log_path(code_root: Path) -> Path:
    return main_checkout(code_root) / LOG_RELPATH


def current_branch(code_root: Path) -> str | None:
    return _git(code_root, "branch", "--show-current").stdout.strip() or None


def init_log(path: Path, *, host: str | None = None) -> str:
    path.parent.mkdir(parents=False, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        raise AttemptLogError(
            f"{path} exists: a log is created once, never beside the records that cite it; for a damaged one, rename it "
            "aside, then restore it from a backup if one exists; otherwise create a new log with zcrypto research "
            "attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
        ) from None
    try:
        log_id = secrets.token_hex(16)
        host = socket.gethostname() if host is None else host
        line = {"seq": 1, "kind": "genesis", "log_id": log_id, "host": host, "timestamp": _now(), "prev_hash": GENESIS_HASH}
        line["line_hash"] = compute_hash(line)
        _write_line(fd, (canonical_json(line) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    return log_id


def arguments(invocation: dict) -> dict:
    return {key: value for key, value in invocation.items() if key != "commit"}


def _boot_id() -> str:
    return BOOT_ID.read_text(encoding="utf-8").strip()


def _process_marks() -> dict:
    return {"pid": os.getpid(), "boot": _boot_id()}


def _alive(begin: dict) -> bool:
    if begin["boot"] != _boot_id():
        return False
    try:
        os.kill(begin["pid"], 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # The pid runs under another user: a live process.
        return True
    return True


def _validate_line(line: dict, where: str) -> None:
    path, _, n = where.rpartition(" line ")
    kind = line.get("kind") if type(line) is dict else None
    expected = _LINE_KEYS.get(kind) if type(kind) is str else None
    if expected is None or set(line) != expected:
        if expected is None:
            raise AttemptLogError(f"{path}: line {n} kind must be one of {sorted(_LINE_KEYS)}")
        keys = set(line)
        raise AttemptLogError(
            f"{path}: line {n} keys must be exactly {sorted(expected)} "
            f"(missing {sorted(expected - keys)}, unknown {sorted(keys - expected)})"
        )


def _verify_chain(lines: list[dict], path: Path) -> None:
    if not lines or lines[0]["kind"] != "genesis":
        raise AttemptLogError(f"{path}: line 1 is not a genesis line")
    begun = 0
    open_attempts: set[int] = set()
    for n, line in enumerate(lines, start=1):
        if n > 1 and line["kind"] == "genesis":
            raise AttemptLogError(f"{path}: line {n} is a second genesis line")
        if line["seq"] != n:
            raise AttemptLogError(f"{path}: line {n} seq is {line['seq']}, not {n}")
        if line["prev_hash"] != (GENESIS_HASH if n == 1 else lines[n - 2]["line_hash"]):
            raise AttemptLogError(f"{path}: line {n} prev_hash is not line {n - 1}'s line_hash")
        if line["line_hash"] != compute_hash({key: value for key, value in line.items() if key != "line_hash"}):
            raise AttemptLogError(f"{path}: line {n} line_hash is not the hash of its line")
        if line["kind"] == "begin":
            if line["attempt"] != begun + 1:
                raise AttemptLogError(f"{path}: line {n} begins attempt {line['attempt']}, not {begun + 1}")
            begun += 1
            open_attempts.add(line["attempt"])
        elif line["kind"] == "end":
            if line["attempt"] not in open_attempts:
                raise AttemptLogError(f"{path}: line {n} ends attempt {line['attempt']}, which has no open begin")
            open_attempts.remove(line["attempt"])


def _copy_aside(path: Path, raw: bytes) -> Path:
    copy = path.with_name(f"{path.name}.torn-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}")
    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        _write_line(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return copy


def _read_locked(path: Path, fd: int) -> tuple[dict, ...]:
    """The log as read under the flock `fd` holds."""
    raw = path.read_bytes()
    copy = None
    # Tested on the bytes: a tear can fall inside a multibyte character, which no decode survives.
    if raw and not raw.endswith(b"\n"):
        copy = _copy_aside(path, raw)
        os.ftruncate(fd, raw.rfind(b"\n") + 1)
        os.fsync(fd)
    try:
        try:
            lines = _read_healing(path, _validate_line, _verify_chain)
        except RegistryCorruptionError as error:
            n = str(error).rpartition(" line ")[2]
            raise AttemptLogError(f"{path}: line {n} is not JSON" if n.isdigit() else f"{path}: {error}") from error
        if not lines:
            _verify_chain([], path)
    except AttemptLogError as error:
        if copy is None:
            raise
        broken = str(error).removeprefix(f"{path}: ")
        raise AttemptLogError(
            f"{path}: the healed log breaks at {broken}, and its bytes before the heal are kept at {copy}"
        ) from error
    if copy is not None:
        copy.unlink()
    return tuple(lines)


def _open_log(path: Path) -> int:
    try:
        return os.open(path, os.O_WRONLY | os.O_APPEND)
    except FileNotFoundError:
        raise AttemptLogError(f"no trial-attempts log at {path}") from None


def _append(path: Path, fd: int, lines: tuple[dict, ...], fields: dict) -> tuple[dict, ...]:
    line = {**fields, "seq": len(lines) + 1, "prev_hash": lines[-1]["line_hash"]}
    line["line_hash"] = compute_hash(line)
    _verify_chain([*lines, line], path)
    _write_line(fd, (canonical_json(line) + "\n").encode("utf-8"))
    os.fsync(fd)
    return (*lines, line)


@dataclass(frozen=True)
class Attempt:
    id: int
    begin: dict
    end: dict | None


def attempts_of(lines: Sequence[dict]) -> tuple[Attempt, ...]:
    begins = {line["attempt"]: line for line in lines if line["kind"] == "begin"}
    ends = {line["attempt"]: line for line in lines if line["kind"] == "end"}
    return tuple(Attempt(id=attempt, begin=begin, end=ends.get(attempt)) for attempt, begin in sorted(begins.items()))


def begin_hash(lines: Sequence[dict], attempt: int) -> str:
    for line in lines:
        if line["kind"] == "begin" and line["attempt"] == attempt:
            return line["line_hash"]
    raise AttemptLogError(f"the trial-attempts log has no begin line for attempt {attempt}")


class AttemptLog:
    path: Path
    log_id: str
    host: str
    lines: tuple[dict, ...]

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        fd = _open_log(self.path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.lines = _read_locked(self.path, fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.log_id = self.lines[0]["log_id"]
        self.host = self.lines[0]["host"]

    def attempts(self) -> tuple[Attempt, ...]:
        return attempts_of(self.lines)

    def begin(
        self,
        admit: Callable[[tuple[dict, ...]], None],
        *,
        invocation: dict,
        spec_hash: str,
        family: str,
        bucket: str | None,
        n_trials: int,
        worktree: Path,
        branch: str | None,
        registry: Path,
        ledger: Path,
    ) -> int:
        fd = _open_log(self.path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            lines = _read_locked(self.path, fd)
            admit(lines)
            attempt = sum(1 for line in lines if line["kind"] == "begin") + 1
            fields = {
                "kind": "begin",
                "attempt": attempt,
                "timestamp": _now(),
                "host": socket.gethostname(),
                **_process_marks(),
                "worktree": str(Path(worktree).resolve()),
                "branch": branch,
                "invocation": invocation,
                "spec_hash": spec_hash,
                "family": family,
                "bucket": bucket,
                "n_trials": n_trials,
                "registry": str(Path(registry).resolve()),
                "ledger": str(Path(ledger).resolve()),
            }
            lines = _append(self.path, fd, lines, fields)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.lines = lines
        return attempt

    def end(
        self,
        attempt: int,
        *,
        verdict: str | None = None,
        stop: str | None = None,
        failed: str | None = None,
        metrics: dict | None = None,
    ) -> None:
        fd = _open_log(self.path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            lines = _read_locked(self.path, fd)
            found = next((a for a in attempts_of(lines) if a.id == attempt), None)
            if found is None or found.end is not None:
                raise AttemptLogError(f"{self.path}: attempt {attempt} is not open")
            if [verdict, stop, failed].count(None) != 2:
                raise AttemptLogError(f"{self.path}: attempt {attempt}: exactly one of verdict, stop and failed must be set")
            metrics_held = type(metrics) is dict and len(metrics) > 0 if failed is None else metrics is None
            if not metrics_held:
                raise AttemptLogError(
                    f"{self.path}: attempt {attempt}: metrics must be a non-empty dict exactly when failed is null"
                )
            if verdict is not None and verdict not in VERDICTS:
                raise AttemptLogError(f"{self.path}: attempt {attempt}: verdict must be one of {sorted(VERDICTS)}")
            fields = {
                "kind": "end",
                "attempt": attempt,
                "timestamp": _now(),
                "verdict": verdict,
                "stop": stop,
                "failed": failed,
                "metrics": metrics,
                "metrics_hash": None if metrics is None else compute_hash(metrics),
            }
            lines = _append(self.path, fd, lines, fields)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.lines = lines

    @contextmanager
    def locked(self) -> Iterator[tuple[dict, ...]]:
        fd = _open_log(self.path)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self.lines = _read_locked(self.path, fd)
            yield self.lines
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


@dataclass(frozen=True)
class Landed:
    records: tuple[dict, ...]
    readings: tuple[dict, ...]


def _landing_key(entry: dict) -> tuple:
    attempt = entry.get("attempt")
    if attempt:
        return ("attempt", attempt["log"], attempt["id"], attempt["begin"])
    return ("hash", entry["record_hash"])


def _once(entries: Iterable[dict]) -> tuple[dict, ...]:
    seen: set[tuple] = set()
    kept = []
    for entry in entries:
        key = _landing_key(entry)
        if key not in seen:
            seen.add(key)
            kept.append(entry)
    return tuple(kept)


def collect(records: Iterable[dict], readings: Iterable[dict]) -> Landed:
    return Landed(records=_once(records), readings=_once(readings))


def files_landed(registry: Path, ledger: Path) -> Landed:
    return Landed(
        records=tuple(dataclasses.asdict(record) for record in TrialRegistry(registry).records),
        readings=tuple(dataclasses.asdict(reading) for reading in ReadingLedger(ledger).records),
    )


def _show(code_root: Path, ref: str, relpath: str) -> str:
    if _git(code_root, "cat-file", "-e", f"{ref}:{relpath}").returncode == 0:
        shown = _git(code_root, "show", f"{ref}:{relpath}")
        if shown.returncode != 0:
            raise AttemptLogError(f"git show {ref}:{relpath} in {code_root} exited {shown.returncode}: {shown.stderr.strip()}")
        return shown.stdout
    return ""


def _shown(code_root: Path, ref: str, relpath: str) -> list[dict]:
    return [loads_strict(line) for line in _show(code_root, ref, relpath).splitlines() if line]


def parse_allowlist(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for n, row in enumerate(text.splitlines(), start=1):
        if not row:
            continue
        if not _ALLOWLIST_ROW.fullmatch(row):
            raise AttemptLogError(f"{ALLOWLIST}: row {n} is not a log id, 32 lowercase hex, a space and its host: {row!r}")
        log_id, _, host = row.partition(" ")
        if log_id in rows:
            raise AttemptLogError(f"{ALLOWLIST}: row {n} repeats {log_id}: a log takes one row")
        rows[log_id] = host
    return rows


def allowed_log_ids(code_root: Path) -> frozenset[str]:
    return frozenset(parse_allowlist(_show(code_root, DEVELOP, ALLOWLIST)))


def landed(code_root: Path, registry: Path, ledger: Path) -> Landed:
    if _git(code_root, "rev-parse", "--verify", "--quiet", f"{DEVELOP}^{{commit}}").returncode != 0:
        raise AttemptLogError(f"origin/develop does not resolve in {code_root}: run git fetch origin develop, then run again")
    target = files_landed(registry, ledger)
    records, readings = list(target.records), list(target.readings)
    for ref in ("HEAD", DEVELOP):
        records += _shown(code_root, ref, REGISTRY_RELPATH)
        readings += _shown(code_root, ref, LEDGER_RELPATH)
    return collect(records, readings)


@dataclass(frozen=True)
class Orphan:
    log: str
    id: int
    begin: str
    family: str
    subject: str
    spec_hash: str
    verdict: str | None
    metrics: dict | None
    timestamp: str | None = None
    branch: str | None = None
    listed_by: int | None = None

    def entry(self) -> dict:
        return {
            "log": self.log,
            "id": self.id,
            "begin": self.begin,
            "family": self.family,
            "subject": self.subject,
            "spec_hash": self.spec_hash,
            "verdict": self.verdict,
            "metrics": self.metrics,
        }

    def describe(self) -> str:
        head = f"{self.log[:8]}#{self.id} {self.subject}"
        if self.listed_by is not None:
            return f"{head} {self.verdict} listed by trial {self.listed_by}"
        outcome = self.verdict if self.verdict is not None else "no end"
        return f"{head} {outcome} {self.timestamp} on {self.branch if self.branch is not None else 'a detached HEAD'}"


@dataclass(frozen=True)
class Count:
    records: tuple[dict, ...]
    orphans: tuple[Orphan, ...]
    absorbs: tuple[dict, ...]
    bucket_of: Mapping[str, str | None]

    def required_n(self, family: str) -> int:
        landed_n = sum(1 for record in self.records if record["family"] == family)
        return landed_n + sum(1 for orphan in self.orphans if orphan.family == family) + 1

    def spent(self, bucket: str) -> int:
        families = [record["family"] for record in self.records] + [orphan.family for orphan in self.orphans]
        return sum(1 for family in families if self.bucket_of.get(family) == bucket)

    def counted(self, family: str) -> list[dict]:
        bucket = self.bucket_of.get(family)
        return [
            orphan.entry()
            for orphan in sorted(self.orphans, key=lambda o: (o.log, o.id, o.begin))
            if orphan.verdict is not None
            and (orphan.family == family if bucket is None else self.bucket_of.get(orphan.family) == bucket)
        ]


def _landed_ids(landed: Landed) -> set[tuple[str, int, str]]:
    ids: set[tuple[str, int, str]] = set()
    for entry in (*landed.records, *landed.readings):
        attempt = entry.get("attempt")
        if attempt:
            ids.add((attempt["log"], attempt["id"], attempt["begin"]))
            ids.update((attempt["log"], ref["id"], ref["begin"]) for ref in attempt.get("absorbs") or ())
    return ids


def _absorber(x: Attempt, attempts: Sequence[Attempt], *, own: int | None, gone: bool, listed: bool) -> int | None:
    for y in attempts:
        if y.id <= x.id or (listed and y.id != own):
            continue
        if arguments(y.begin["invocation"]) != arguments(x.begin["invocation"]) or y.begin["spec_hash"] != x.begin["spec_hash"]:
            continue
        if x.end is not None:
            if (
                y.end is not None
                and x.end["metrics_hash"] is not None
                and y.end["metrics_hash"] == x.end["metrics_hash"]
                and (y.end["verdict"], y.end["stop"]) == (x.end["verdict"], x.end["stop"])
            ):
                return y.id
        elif gone and y.end is not None:
            return y.id
    return None


def reconcile(
    lines: Sequence[dict],
    landed: Landed,
    *,
    log_id: str,
    bucket_of: Mapping[str, str | None],
    own: int | None = None,
    hold: tuple[str, dict, str] | None = None,
    hold_finished: bool = True,
) -> Count:
    landed_ids = _landed_ids(landed)
    listers = sorted(landed.records, key=lambda record: record["trial_id"])
    listed = {
        (entry["log"], entry["id"], entry["begin"])
        for record in listers
        for entry in (record.get("attempt") or {}).get("counted") or ()
    }
    local = attempts_of(lines)
    orphans: list[Orphan] = []
    absorbs: list[dict] = []
    for x in local:
        if x.id == own:
            continue
        begin = x.begin["line_hash"]
        if (log_id, x.id, begin) in landed_ids:
            continue
        is_listed = (log_id, x.id, begin) in listed
        gone = x.end is None and not _alive(x.begin)
        absorber = _absorber(x, local, own=own, gone=gone, listed=is_listed)
        if absorber is not None:
            if absorber == own:
                absorbs.append({"id": x.id, "begin": begin})
            continue
        if x.end is not None and x.end["stop"] is not None and not is_listed:
            continue
        if x.end is not None and x.end["failed"] is not None and not is_listed:
            continue
        held_key = (x.begin["invocation"]["subject"], arguments(x.begin["invocation"]), x.begin["spec_hash"])
        if hold is not None and held_key == hold and (gone or x.end is not None and hold_finished):
            continue
        orphans.append(
            Orphan(
                log=log_id,
                id=x.id,
                begin=begin,
                family=x.begin["family"],
                subject=x.begin["invocation"]["subject"],
                spec_hash=x.begin["spec_hash"],
                verdict=None if x.end is None else x.end["verdict"],
                metrics=None if x.end is None else x.end["metrics"],
                timestamp=x.begin["timestamp"],
                branch=x.begin["branch"],
            )
        )
    mine = {(log_id, x.id, x.begin["line_hash"]) for x in local}
    carried: set[tuple[str, int, str]] = set()
    for record in listers:
        for entry in (record.get("attempt") or {}).get("counted") or ():
            ref = (entry["log"], entry["id"], entry["begin"])
            if ref in carried:
                continue
            carried.add(ref)
            if ref not in landed_ids and ref not in mine:
                orphans.append(
                    Orphan(
                        log=entry["log"],
                        id=entry["id"],
                        begin=entry["begin"],
                        family=entry["family"],
                        subject=entry["subject"],
                        spec_hash=entry["spec_hash"],
                        verdict=entry["verdict"],
                        metrics=entry["metrics"],
                        listed_by=record["trial_id"],
                    )
                )
    return Count(records=landed.records, orphans=tuple(orphans), absorbs=tuple(absorbs), bucket_of=bucket_of)


def lacking(lines: Sequence[dict], landed: Landed, log_id: str) -> list[tuple[str, int]]:
    begins = {line["attempt"]: line["line_hash"] for line in lines if line["kind"] == "begin"}
    ended = {line["attempt"] for line in lines if line["kind"] == "end"}

    def held(ref: dict) -> bool:
        return begins.get(ref["id"]) == ref["begin"]

    named = [
        *((f"trial {record['trial_id']}", record) for record in landed.records),
        *((f"reading {reading['reading_id']}", reading) for reading in landed.readings),
    ]
    found: list[tuple[str, int]] = []
    for name, entry in named:
        attempt = entry.get("attempt") or {}
        if attempt.get("log") == log_id:
            found += [(name, ref["id"]) for ref in [attempt, *(attempt.get("absorbs") or ())] if not held(ref)]
        found += [
            (name, ref["id"])
            for ref in attempt.get("counted") or ()
            if ref["log"] == log_id and not (held(ref) and ref["id"] in ended)
        ]
    return found
