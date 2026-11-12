"""One tick: every source fetched, each kept body stored as served, gzipped, read back and checked against the source's
last ok body along the chain, and the tick published as one directory by one rename, naming the head it chains to."""

from __future__ import annotations

import base64
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
import stat
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cli.logging import get_logger
from cli.vintage.chain import TICK_JSON, TickFile, chain, check_head, scan
from cli.vintage.credential import ApiKey
from cli.vintage.fetch import Attempt, Clock, Exchange, SystemClock, _header, build_openers, fetch_all
from cli.vintage.sources import SOURCES, BodySummary, Source, check_block, check_body, summarise
from cli.vintage.storage import create_exclusive, fsync_dir, gzip_bytes, publish_tick

RECORD_SUBDIR = "record"
STAGING_SUBDIR = "staging"
TICK_DEADLINE_SECONDS = 20 * 60
TICK_SCHEMA = 1
EMPTY_RECORD = "empty record"
CLOCK_OFFSET = "zcrypto_clock_offset_seconds"
CLOCK_SYNCHRONISED = "zcrypto_clock_synchronised"

log = get_logger("vintage.record")


class RecordRefused(Exception):
    """Nothing was published; the message says why."""


@dataclass
class Published:
    stamp: str
    dir: Path
    tick_json_sha256: str
    manifest: dict
    exchanges: list[Exchange]
    regression: bool


def tick_json_bytes(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _clock_nulls(error: str) -> dict:
    return {"offset_seconds": None, "synchronised": None, "prom_age_seconds": None, "error": error}


def _gauge_values(text: str) -> dict[str, float]:
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in (CLOCK_OFFSET, CLOCK_SYNCHRONISED):
            values[parts[0]] = float(parts[1])
    return values


def clock_block(clock_prom: Path | None, now: datetime) -> dict:
    """The host clock's evidence from the clock-offset `.prom`; what cannot be read is null with a reason, never a
    refusal, and a non-finite value is null, so `tick.json` never carries a token a strict JSON reader refuses."""
    if clock_prom is None:
        return _clock_nulls("no clock file")
    try:
        mtime = clock_prom.stat().st_mtime
        data = clock_prom.read_bytes()
    except OSError as exc:
        return _clock_nulls(f"clock file unreadable: {type(exc).__name__}")
    try:
        values = _gauge_values(data.decode("utf-8"))
        offset, synchronised = values[CLOCK_OFFSET], values[CLOCK_SYNCHRONISED]
    except ValueError, KeyError:
        return _clock_nulls("clock file unparseable")
    errors = []
    if not math.isfinite(offset):
        offset = None
        errors.append("offset not finite")
    if not math.isfinite(synchronised):
        synchronised = None
        errors.append("synchronised not finite")
    elif synchronised.is_integer():
        synchronised = int(synchronised)
    return {
        "offset_seconds": offset,
        "synchronised": synchronised,
        "prom_age_seconds": round(now.timestamp() - mtime, 6),
        "error": "; ".join(errors) or None,
    }


def _read_back(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes())


def _store(path: Path, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    create_exclusive(path, gzip_bytes(body))
    if hashlib.sha256(_read_back(path)).hexdigest() != digest:
        raise RecordRefused(f"vintage tick refused: a stored body does not read back file={path.name}")
    return digest


def _ok_entry(manifest: dict, source: Source) -> bool:
    for fetch in manifest.get("fetches") or []:
        if isinstance(fetch, dict) and fetch.get("source") == source.id:
            check, body = fetch.get("check"), fetch.get("body")
            return isinstance(check, dict) and check.get("outcome") == 0 and isinstance(body, dict)
    return False


def _last_ok(order: tuple[TickFile, ...], source: Source) -> tuple[str, BodySummary] | None:
    """The source's newest ok body along the chain, summarised from its stored file; a file that no longer reads is
    passed over for the one before it."""
    for tick in reversed(order):
        if tick.manifest is None or not _ok_entry(tick.manifest, source):
            continue
        try:
            return tick.stamp, summarise(source, gzip.decompress((tick.dir / source.file).read_bytes()))
        except OSError, EOFError, zlib.error, ValueError:
            continue
    return None


def _check(exchange: Exchange, stamp: str, order: tuple[TickFile, ...]) -> dict:
    if exchange.not_fetched is not None or exchange.body is None:
        return {
            "outcome": 1,
            "reason": exchange.not_fetched,
            "newest_day": None,
            "rows": None,
            "metrics_absent": [],
            "metrics_failed": [],
            "acknowledged": [],
        }
    last_ok = _last_ok(order, exchange.source)
    check = check_body(
        exchange.source,
        exchange.body,
        content_encoding=_header(exchange.headers, "Content-Encoding"),
        tick=stamp,
        last_ok=None if last_ok is None else last_ok[1],
        last_ok_tick=None if last_ok is None else last_ok[0],
    )
    return check_block(check)


def _attempt_entry(attempt: Attempt) -> dict:
    return {
        "started_at": _iso(attempt.started_at),
        "ended_at": _iso(attempt.ended_at),
        "duration_seconds": attempt.duration_seconds,
        "status": attempt.status,
        "error": attempt.error,
        "head": None if attempt.head is None else base64.b64encode(attempt.head).decode("ascii"),
        "withheld": None if attempt.withheld is None else {"reason": attempt.withheld[0], "bytes": attempt.withheld[1]},
    }


def _fetch_entry(exchange: Exchange, staged: Path, stamp: str, order: tuple[TickFile, ...]) -> dict:
    source = exchange.source
    stored = None
    if exchange.body is not None:
        stored = {"file": source.file, "bytes": len(exchange.body), "sha256": _store(staged / source.file, exchange.body)}
    return {
        "source": source.id,
        "url": source.url,
        "request_headers": [list(pair) for pair in exchange.request_headers],
        "attempts": [_attempt_entry(attempt) for attempt in exchange.attempts],
        "final_url": exchange.final_url,
        "http_version": exchange.http_version,
        "status": exchange.status,
        "reason": exchange.reason,
        "headers": [list(pair) for pair in exchange.headers],
        "body": stored,
        "check": _check(exchange, stamp, order),
    }


def _seal(ticks: list[TickFile]) -> None:
    """A published tick a crash left writable, between its rename and its chmod, set to 0555; no byte changes."""
    for tick in ticks:
        if stat.S_IMODE(tick.dir.stat().st_mode) & 0o222:
            os.chmod(tick.dir, 0o555)


def _name_leftovers(staging: Path) -> None:
    leftovers = " ".join(sorted(entry.name for entry in staging.iterdir())) if staging.is_dir() else ""
    if leftovers:
        log.warning("vintage staging holds crashed ticks never published; read, then delete by hand: %s", leftovers)


def _prev(head: TickFile | None) -> tuple[dict | None, str | None]:
    if head is None:
        return None, EMPTY_RECORD
    error = check_head(head)
    if error is not None:
        log.error("vintage head fails the chaining check head=%s: %s", head.stamp, error)
    return {"tick": head.stamp, "tick_json_sha256": head.sha256, "error": error}, None


def _regressed(stamp: str, head: TickFile | None) -> bool:
    if head is None:
        return False
    if stamp <= head.stamp:
        log.error("vintage tick stamp at or below its predecessor's, published: tick=%s head=%s", stamp, head.stamp)
        return True
    return False


def record_tick(
    data_dir: Path,
    *,
    key: ApiKey | None,
    key_reason: str | None,
    clock_prom: Path | None,
    https_handler: urllib.request.BaseHandler | None = None,
    clock: Clock | None = None,
    version: str | None = None,
    revision: str | None = None,
    only: frozenset[str] | None = None,
) -> Published:
    """Fetches, stores and publishes one tick; `RecordRefused`, and any exception raised before `publish_tick` is
    called, means nothing was published."""
    clock = SystemClock() if clock is None else clock
    version = importlib.metadata.version("zcrypto") if version is None else version
    revision = os.environ.get("ZCRYPTO_BUILD_REVISION", "") if revision is None else revision
    started = clock.now()
    stamp = started.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = data_dir / RECORD_SUBDIR / stamp[:4] / stamp[4:6] / stamp[6:8] / stamp
    if target.exists():
        raise RecordRefused(f"vintage tick refused: its target exists tick={stamp}")

    ticks = scan(data_dir / RECORD_SUBDIR)
    found = chain(ticks)
    head = found.head
    if found.cycle:
        log.error("vintage chain has no head: every tick's stamp is named by a prev, a cycle; took the newest head=%s", head.stamp)
    if found.other_heads:
        others = " ".join(tick.stamp for tick in found.other_heads)
        log.error("vintage chain has several heads: took head=%s; the others: %s", head.stamp, others)
    _seal(ticks)
    _name_leftovers(data_dir / STAGING_SUBDIR)
    prev, genesis_reason = _prev(head)
    clock_evidence = clock_block(clock_prom, started)

    deadline = clock.monotonic() + TICK_DEADLINE_SECONDS
    exchanges = fetch_all(
        SOURCES,
        key=key,
        key_reason=key_reason,
        openers=build_openers(https_handler),
        clock=clock,
        tick_deadline=deadline,
        user_agent=f"zcrypto-vintage/{version}",
        only=only,
    )

    staged = data_dir / STAGING_SUBDIR / stamp
    staged.mkdir(mode=0o755, parents=True)
    fetches = [_fetch_entry(exchange, staged, stamp, found.order) for exchange in exchanges]
    manifest = {
        "schema": TICK_SCHEMA,
        "tick": stamp,
        "started_at": _iso(started),
        "ended_at": _iso(clock.now()),
        "recorder": f"{version}+{revision[:12]}" if revision else version,
        "prev": prev,
        "genesis_reason": genesis_reason,
        "clock": clock_evidence,
        "fetches": fetches,
    }
    tick_bytes = tick_json_bytes(manifest)
    witness = hashlib.sha256(tick_bytes).hexdigest()
    create_exclusive(staged / TICK_JSON, tick_bytes)
    fsync_dir(staged)
    if target.exists():
        raise RecordRefused(f"vintage tick refused: its target exists tick={stamp}")
    publish_tick(staged, target)
    log.info("vintage tick published tick=%s tick_json_sha256=%s", stamp, witness)
    return Published(stamp, target, witness, manifest, exchanges, _regressed(stamp, head))
