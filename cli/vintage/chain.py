"""The record's published ticks as the scan finds them, and the chain their `prev` links make: the head, the order from
genesis to it, and what the walk leaves out."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import stat
import zlib
from dataclasses import dataclass
from pathlib import Path

STAMP_RE = re.compile(r"\d{8}T\d{6}Z")
TICK_JSON = "tick.json"
_YEAR = re.compile(r"\d{4}")
_TWO_DIGITS = re.compile(r"\d{2}")


@dataclass(frozen=True)
class TickFile:
    stamp: str
    dir: Path
    raw: bytes | None
    sha256: str | None
    manifest: dict | None
    error: str | None


@dataclass(frozen=True)
class Chain:
    order: tuple[TickFile, ...]
    head: TickFile | None
    other_heads: tuple[TickFile, ...]
    off_chain: tuple[TickFile, ...]
    unreadable: tuple[TickFile, ...]
    # No tick is a head candidate, as under a cycle of `prev` links or a regression over an unreadable predecessor:
    # the head is then the newest stamp.
    cycle: bool = False


@dataclass(frozen=True)
class Scan:
    ticks: list[TickFile]
    # Each path under the root whose listing or stat failed, with the error's type: what it holds is unknown, so the
    # record is read as damaged, never as holding nothing there.
    unreadable: tuple[tuple[Path, str], ...]


def _children(path: Path, pattern: re.Pattern, unreadable: list[tuple[Path, str]]) -> list[Path]:
    """The directories under `path` whose names match, each decided by its stat; `Path.is_dir` would read a failed
    stat as no directory and drop what lies under it."""
    try:
        entries = sorted(entry for entry in path.iterdir() if pattern.fullmatch(entry.name))
    except OSError as exc:
        unreadable.append((path, type(exc).__name__))
        return []
    found = []
    for entry in entries:
        try:
            mode = os.stat(entry).st_mode
        except OSError as exc:
            unreadable.append((entry, type(exc).__name__))
            continue
        if stat.S_ISDIR(mode):
            found.append(entry)
    return found


def _read(directory: Path) -> TickFile:
    try:
        raw = (directory / TICK_JSON).read_bytes()
    except OSError as exc:
        return TickFile(directory.name, directory, None, None, None, f"tick.json unreadable: {type(exc).__name__}")
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        manifest = json.loads(raw)
    except ValueError, RecursionError:
        manifest = None
    if not isinstance(manifest, dict):
        return TickFile(directory.name, directory, raw, sha256, None, "tick.json unparseable")
    return TickFile(directory.name, directory, raw, sha256, manifest, None)


def scan(record_root: Path) -> Scan:
    """Every `<YYYY>/<MM>/<DD>/<stamp>/` directory under the root, oldest stamp first, any other name no tick, and
    every path the walk could not list or stat; a root that does not exist is an empty record."""
    try:
        os.stat(record_root)
    except FileNotFoundError:
        return Scan([], ())
    ticks = []
    unreadable: list[tuple[Path, str]] = []
    for year in _children(record_root, _YEAR, unreadable):
        for month in _children(year, _TWO_DIGITS, unreadable):
            for day in _children(month, _TWO_DIGITS, unreadable):
                for entry in _children(day, STAMP_RE, unreadable):
                    ticks.append(_read(entry))
    return Scan(sorted(ticks, key=lambda tick: tick.stamp), tuple(unreadable))


def _prev_stamp(tick: TickFile) -> str | None:
    prev = tick.manifest.get("prev")
    if isinstance(prev, dict) and isinstance(prev.get("tick"), str):
        return prev["tick"]
    return None


def _continuation(unreadable: TickFile, ticks: list[TickFile], named: set[str]) -> TickFile | None:
    """Where the walk goes on past a tick whose `prev` cannot be read: the newest older tick no readable `prev` names."""
    older = [tick for tick in ticks if tick.stamp < unreadable.stamp and tick.stamp not in named]
    return max(older, key=lambda tick: tick.stamp, default=None)


def _walk(head: TickFile, ticks: list[TickFile], named: set[str]) -> list[TickFile]:
    by_stamp = {tick.stamp: tick for tick in ticks}
    order: list[TickFile] = []
    seen: set[str] = set()
    tick: TickFile | None = head
    while tick is not None and tick.stamp not in seen:
        seen.add(tick.stamp)
        order.append(tick)
        if tick.manifest is None:
            tick = _continuation(tick, ticks, named)
        else:
            stamp = _prev_stamp(tick)
            tick = None if stamp is None else by_stamp.get(stamp)
    return order[::-1]


def chain(ticks: list[TickFile]) -> Chain:
    ticks = sorted(ticks, key=lambda tick: tick.stamp)
    unreadable = tuple(tick for tick in ticks if tick.manifest is None)
    named = {stamp for tick in ticks if tick.manifest is not None and (stamp := _prev_stamp(tick)) is not None}
    continued = {found.stamp for t in unreadable if (found := _continuation(t, ticks, named)) is not None}
    candidates = [tick for tick in ticks if tick.stamp not in named and tick.stamp not in continued]
    if not ticks:
        return Chain((), None, (), (), ())
    head = max(candidates, key=lambda tick: tick.stamp) if candidates else ticks[-1]
    other_heads = tuple(tick for tick in candidates if tick is not head)
    order = tuple(_walk(head, ticks, named))
    placed = {tick.stamp for tick in order + other_heads}
    off_chain = tuple(tick for tick in ticks if tick.stamp not in placed)
    return Chain(order, head, other_heads, off_chain, unreadable, cycle=not candidates)


def listed(manifest: dict) -> dict[str, str]:
    """Each body file `fetches` names, with its sha256; TypeError where the block is not in that shape."""
    bodies: dict[str, str] = {}
    fetches = manifest.get("fetches")
    if not isinstance(fetches, list):
        raise TypeError("fetches is not a list")
    for fetch in fetches:
        entry = fetch.get("body") if isinstance(fetch, dict) else None
        if entry is None:
            continue
        name, digest = entry.get("file"), entry.get("sha256")
        if not (isinstance(name, str) and isinstance(digest, str)):
            raise TypeError("a body entry is not a file and a sha256")
        bodies[name] = digest
    return bodies


def check_head(head: TickFile) -> str | None:
    """The chaining check's failure, None when the head's `tick.json` parses, its `fetches` name exactly the body files
    its directory holds, and every one re-hashes to its entry."""
    if head.manifest is None:
        return head.error
    try:
        bodies = listed(head.manifest)
    except TypeError, AttributeError:
        return "tick.json fetches unreadable"
    try:
        present = {entry.name for entry in head.dir.iterdir() if entry.name != TICK_JSON}
    except OSError as exc:
        return f"tick directory unreadable: {type(exc).__name__}"
    missing, unlisted = sorted(bodies.keys() - present), sorted(present - bodies.keys())
    if missing or unlisted:
        parts = ([f"missing {' '.join(missing)}"] if missing else []) + ([f"unlisted {' '.join(unlisted)}"] if unlisted else [])
        return f"body files differ: {'; '.join(parts)}"
    for name, digest in sorted(bodies.items()):
        try:
            data = gzip.decompress((head.dir / name).read_bytes())
        except OSError, EOFError, zlib.error:
            return f"{name} does not decompress"
        if hashlib.sha256(data).hexdigest() != digest:
            return f"{name} does not re-hash"
    return None
