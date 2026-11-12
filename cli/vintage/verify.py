"""The integrity read over one copy of the record: every `tick.json`, the chain their `prev` links make, the bodies
re-hashed, and what the copy breaks against what is only named. Read-only."""

from __future__ import annotations

import gzip
import hashlib
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cli.vintage.chain import TICK_JSON, TickFile, chain, listed, scan
from cli.vintage.sources import FORK_ACKNOWLEDGMENTS, LINK_ACKNOWLEDGMENTS, ForkAcknowledgment, LinkAcknowledgment

MISSING_ROOT = "missing root"
BROKEN_LINK = "broken link"
MISSING_TICK = "missing tick"
MISSING_BODY = "missing body"
TAMPERED_BODY = "tampered body"
UNREADABLE_MANIFEST = "unreadable manifest"
FORK = "fork"
UNLISTED_FILE = "unlisted file"
ACKNOWLEDGED_LINK_MISMATCH = "acknowledged link mismatch"
CLOCK_REGRESSION = "clock regression"
CHAINING_ERROR = "link carries the chaining error"
ACKNOWLEDGED_LINK = "acknowledged link"
ACKNOWLEDGED_FORK = "acknowledged fork"
LOST_TICK = "lost tick"


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    detail: str


@dataclass(frozen=True)
class VerifyResult:
    breaks: list[Finding]
    notes: list[Finding]
    ticks: int
    head: str | None
    head_tick_json_sha256: str | None
    bodies_hashed: int


def _tick_dir(root: Path, stamp: str) -> Path:
    return root / stamp[:4] / stamp[4:6] / stamp[6:8] / stamp


def _rehash(path: Path, digest: str) -> str | None:
    """Why the body does not re-hash to its entry, None when it does."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return f"unreadable: {type(exc).__name__}"
    try:
        data = gzip.decompress(raw)
    except OSError, EOFError, zlib.error:
        return "does not decompress"
    if hashlib.sha256(data).hexdigest() != digest:
        return "does not re-hash to its entry"
    return None


def verify(
    root: Path,
    *,
    newest: int | None = None,
    slice_: int | None = None,
    slices: int | None = None,
    acknowledgments: Sequence[LinkAcknowledgment] | None = None,
    forks: Sequence[ForkAcknowledgment] | None = None,
    custody: bool = False,
) -> VerifyResult:
    """With `newest`, the bodies re-hashed are those of the newest `newest` ticks along the chain and of the slice,
    which then takes `slice_` and `slices`; without, every body. `acknowledgments` None reads `LINK_ACKNOWLEDGMENTS`
    and `forks` None reads `FORK_ACKNOWLEDGMENTS`, each at call time. `custody` reads the copy as the only custody of
    a fork's tick off the chain."""
    if not root.is_dir():
        return VerifyResult(
            [Finding(MISSING_ROOT, str(root), "no such directory")],
            [],
            ticks=0,
            head=None,
            head_tick_json_sha256=None,
            bodies_hashed=0,
        )
    scanned = scan(root)
    ticks = scanned.ticks
    breaks = [Finding(UNREADABLE_MANIFEST, str(path), f"listing or stat failed: {reason}") for path, reason in scanned.unreadable]
    if not ticks:
        return VerifyResult(breaks, [], ticks=0, head=None, head_tick_json_sha256=None, bodies_hashed=0)
    found = chain(ticks)
    held = {tick.stamp: tick for tick in ticks}
    notes: list[Finding] = []

    link_entries: dict[str, LinkAcknowledgment] = {}
    for entry in LINK_ACKNOWLEDGMENTS if acknowledgments is None else acknowledgments:
        if entry.successor not in held:
            continue
        link_entries[entry.successor] = entry
    fork_entries: dict[str, ForkAcknowledgment] = {}
    for entry in FORK_ACKNOWLEDGMENTS if forks is None else forks:
        if entry.off_chain in held:
            fork_entries[entry.off_chain] = entry
            continue
        if not custody:
            continue
        path = str(_tick_dir(root, entry.off_chain))
        if entry.lost:
            notes.append(Finding(LOST_TICK, path, "an acknowledged fork's tick off the chain, marked lost"))
        else:
            breaks.append(
                Finding(MISSING_TICK, path, "an acknowledged fork's tick off the chain, of which this copy is the custody")
            )

    for tick in found.unreadable:
        breaks.append(Finding(UNREADABLE_MANIFEST, str(tick.dir / TICK_JSON), tick.error or "unreadable"))
    if found.cycle:
        detail = "no tick is a head candidate; the head taken is the newest stamp"
        breaks.append(Finding(BROKEN_LINK, str(found.head.dir / TICK_JSON), detail))

    namers: dict[str | None, list[TickFile]] = {}
    missing: set[str] = set()
    for tick in ticks:
        if tick.manifest is None:
            continue
        prev = tick.manifest.get("prev")
        if prev is None:
            namers.setdefault(None, []).append(tick)
            continue
        if not (isinstance(prev, dict) and isinstance(prev.get("tick"), str)):
            breaks.append(Finding(BROKEN_LINK, str(tick.dir / TICK_JSON), "prev names no tick"))
            continue
        namers.setdefault(prev["tick"], []).append(tick)
        predecessor = held.get(prev["tick"])
        if predecessor is None:
            if prev["tick"] not in missing:
                missing.add(prev["tick"])
                breaks.append(Finding(MISSING_TICK, str(_tick_dir(root, prev["tick"])), f"named in prev by tick={tick.stamp}"))
            continue
        link = f"tick={tick.stamp} prev={predecessor.stamp}"
        entry = link_entries.get(tick.stamp)
        if entry is not None:
            if prev.get("tick_json_sha256") == entry.recorded_prev_sha256 and predecessor.sha256 == entry.witnessed_sha256:
                notes.append(Finding(ACKNOWLEDGED_LINK, str(tick.dir / TICK_JSON), link))
            else:
                breaks.append(Finding(ACKNOWLEDGED_LINK_MISMATCH, str(tick.dir / TICK_JSON), f"{link} differs from its entry"))
        elif prev.get("error") is not None:
            notes.append(Finding(CHAINING_ERROR, str(tick.dir / TICK_JSON), f"{link}: {prev['error']}"))
        elif prev.get("tick_json_sha256") != predecessor.sha256:
            breaks.append(Finding(BROKEN_LINK, str(tick.dir / TICK_JSON), f"{link} does not hash"))

    on_chain = {tick.stamp for tick in found.order}
    for named, members in sorted(namers.items(), key=lambda item: item[0] or ""):
        if len(members) < 2:
            continue
        both = f"prev={named or 'none'} named by {' '.join(str(member.dir) for member in members)}"
        for member in [member for member in members if member.stamp not in on_chain] or members:
            entry = fork_entries.get(member.stamp)
            if entry is not None and member.sha256 == entry.tick_json_sha256:
                notes.append(Finding(ACKNOWLEDGED_FORK, str(member.dir), both))
            else:
                breaks.append(Finding(FORK, str(member.dir), both))

    for earlier, later in zip(found.order, found.order[1:]):
        if later.stamp <= earlier.stamp:
            notes.append(
                Finding(CLOCK_REGRESSION, str(later.dir), f"tick={later.stamp} at or below its predecessor={earlier.stamp}")
            )

    if newest is None:
        chosen = set(held)
    else:
        if slice_ is None or slices is None:
            raise ValueError("newest takes slice_ and slices")
        chosen = {tick.stamp for tick in found.order[::-1][:newest]}
        chosen |= {tick.stamp for index, tick in enumerate(ticks) if index % slices == slice_}

    hashed = 0
    for tick in ticks:
        if tick.manifest is None:
            continue
        try:
            bodies = listed(tick.manifest)
        except TypeError, AttributeError:
            breaks.append(Finding(UNREADABLE_MANIFEST, str(tick.dir / TICK_JSON), "tick.json fetches unreadable"))
            continue
        try:
            present = {entry.name for entry in tick.dir.iterdir() if entry.name != TICK_JSON}
        except OSError as exc:
            breaks.append(Finding(UNREADABLE_MANIFEST, str(tick.dir), f"tick directory unreadable: {type(exc).__name__}"))
            continue
        for name in sorted(present - bodies.keys()):
            breaks.append(Finding(UNLISTED_FILE, str(tick.dir / name), "a file its tick.json does not list"))
        for name in sorted(bodies.keys() - present):
            breaks.append(Finding(MISSING_BODY, str(tick.dir / name), "a body its tick.json lists"))
        if tick.stamp not in chosen:
            continue
        for name in sorted(bodies.keys() & present):
            hashed += 1
            failure = _rehash(tick.dir / name, bodies[name])
            if failure is not None:
                breaks.append(Finding(TAMPERED_BODY, str(tick.dir / name), failure))

    return VerifyResult(
        breaks,
        notes,
        ticks=len(ticks),
        head=found.head.stamp,
        head_tick_json_sha256=found.head.sha256,
        bodies_hashed=hashed,
    )
