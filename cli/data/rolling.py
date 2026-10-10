"""The rolling canonical, `ohlc-rolling` (spec 00125): a 15-minute base copied from a frozen quarter and a daily extension
copied from tape-bars, every UTC day attested by a write-once index line whose `prev` is the sha256 of the line before it.

A pin is an as-of day, identified by the sha256 of that day's line; every reader reaches a file only through the lines."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import FRAME_SCHEMA, read_parquet
from cli.tick.materialize import derive_bars

ROLLING_SET = "ohlc-rolling"
_BASE_GRID = 15
_GRIDS = (_BASE_GRID, 60, 240, 1440)
_KEYS = frozenset({"day", "prev", "files", "holes"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_BASE_FILE = re.compile(r"base/[A-Z0-9]+/[A-Z0-9]+/15\.parquet")
_DAY_FILE = re.compile(r"days/[A-Z0-9]+/[A-Z0-9]+/(\d{4}/\d{2}/\d{2})\.parquet")
_CLOSED = "closed "


class RollingError(Exception):
    """The rolling set does not read as its index lines attest it."""


@dataclass(frozen=True)
class Line:
    day: date
    prev: str | None
    files: dict[str, str]
    holes: dict[str, str]
    notes: dict[str, str]
    relpath: str
    sha256: str


@dataclass(frozen=True)
class RollingRead:
    frame: pl.DataFrame
    holes: tuple[date, ...]
    line: Line


def line_relpath(day: date) -> str:
    return f"index/{day:%Y}/{day:%m}/{day:%d}.json"


def _base_relpath(pair: str) -> str:
    asset, quote = pair.split("/")
    return f"base/{asset}/{quote}/15.parquet"


def _day_relpath(pair: str, day: date) -> str:
    asset, quote = pair.split("/")
    return f"days/{asset}/{quote}/{day:%Y}/{day:%m}/{day:%d}.parquet"


def _pair_of(relpath: str) -> str:
    return "/".join(relpath.split("/")[1:3])


def _canonical(line: dict) -> bytes:
    return (json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _is_text_map(value: object) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())


def is_chained(root: Path) -> bool:
    return (root / "index").is_dir()


def line_days(root: Path) -> list[date]:
    days = []
    for path in (root / "index").glob("*/*/*.json"):
        relpath = path.relative_to(root).as_posix()
        try:
            day = date(int(path.parent.parent.name), int(path.parent.name), int(path.stem))
        except ValueError as exc:
            raise RollingError(f"{root}: {relpath} is not named for a day") from exc
        if line_relpath(day) != relpath:
            raise RollingError(f"{root}: {relpath} is not named for a day")
        days.append(day)
    return sorted(days)


def _read(root: Path, day: date) -> Line:
    """`day`'s line with every part of its shape checked that the set's pairs do not decide."""
    relpath = line_relpath(day)
    try:
        data = (root / relpath).read_bytes()
    except FileNotFoundError as exc:
        raise RollingError(f"{root}: {relpath} is absent") from exc
    try:
        line = json.loads(data)
    except ValueError as exc:
        raise RollingError(f"{relpath}: not JSON ({exc})") from exc
    if not isinstance(line, dict) or _canonical(line) != data:
        raise RollingError(f"{relpath}: not an index line in its canonical form")
    is_base = "prev" in line and line["prev"] is None
    keys = _KEYS | {"notes"} if is_base or "notes" in line else _KEYS
    if line.keys() != keys:
        raise RollingError(f"{relpath}: its keys are {sorted(line)}, not {sorted(keys)}")
    if line["day"] != day.isoformat():
        raise RollingError(f"{relpath}: its day is {line['day']!r}, not the {day} its name gives")
    files, holes, notes = line["files"], line["holes"], line.get("notes", {})
    if not (_is_text_map(files) and _is_text_map(holes) and _is_text_map(notes)):
        raise RollingError(f"{relpath}: its files, holes and notes must each map text to text")
    if not all(_SHA256.fullmatch(digest) for digest in files.values()):
        raise RollingError(f"{relpath}: a file it lists is not mapped to a sha256")
    if is_base:
        if not files or holes or not all(_BASE_FILE.fullmatch(name) for name in files):
            raise RollingError(f"{relpath}: a base line lists base/<BASE>/<QUOTE>/15.parquet files and no hole")
    else:
        if not isinstance(line["prev"], str) or not _SHA256.fullmatch(line["prev"]):
            raise RollingError(f"{relpath}: its prev is neither null nor a sha256")
        if not all((m := _DAY_FILE.fullmatch(name)) and m[1] == f"{day:%Y/%m/%d}" for name in files):
            raise RollingError(f"{relpath}: a file it lists is not a days/<BASE>/<QUOTE>/ file of {day}")
        if "notes" in line and not (notes and all(k.startswith(_CLOSED) and k.removeprefix(_CLOSED) in holes for k in notes)):
            raise RollingError(f"{relpath}: a day line's notes are closed <PAIR> keys, each pair under its holes")
    return Line(day, line["prev"], files, holes, notes, relpath, hashlib.sha256(data).hexdigest())


def _check_pairs(line: Line, set_pairs: tuple[str, ...]) -> None:
    named = {_pair_of(relpath) for relpath in line.files}
    if named & line.holes.keys() or named | line.holes.keys() != set(set_pairs):
        raise RollingError(
            f"{line.relpath}: its files ({', '.join(sorted(named))}) and holes ({', '.join(sorted(line.holes))}) "
            f"do not name each of the set's pairs ({', '.join(set_pairs)}) once"
        )


def pairs(root: Path) -> tuple[str, ...]:
    days = line_days(root)
    if not days:
        raise RollingError(f"{root} holds no base line")
    base = _read(root, days[0])
    if base.prev is not None:
        raise RollingError(f"{base.relpath}: the oldest line under {root} is not a base line, its prev is not null")
    return tuple(sorted(_pair_of(relpath) for relpath in base.files))


def read_line(root: Path, day: date) -> Line:
    """`day`'s line read and its shape checked; its link to the line before it is not walked."""
    line = _read(root, day)
    if line.prev is not None:
        _check_pairs(line, pairs(root))
    return line


def walk_chain(root: Path, as_of: date) -> list[Line]:
    """Every line from the base up to `as_of`'s, each day's line the day after the one below it, and each `prev` the
    sha256 of the bytes of the line below it. No file a line lists is opened."""
    days = line_days(root)
    if as_of not in days:
        raise RollingError(f"{root} holds no line for {as_of}; its newest is for {days[-1] if days else 'no day'}")
    set_pairs = pairs(root)
    chain: list[Line] = []
    for day in reversed([day for day in days if day <= as_of]):
        line = _read(root, day)
        if line.prev is not None:
            _check_pairs(line, set_pairs)
        if chain:
            after = chain[-1]
            if after.day != line.day + timedelta(days=1):
                raise RollingError(f"{after.relpath}: no line for {line.day + timedelta(days=1)}, the day after {line.relpath}")
            if after.prev != line.sha256:
                raise RollingError(f"{after.relpath}: its prev is not the sha256 of {line.relpath}")
        chain.append(line)
    return chain[::-1]


def head(root: Path) -> Line:
    """The newest line whose listed files are all present, its chain walked: a line ahead of its files, as a pull can leave
    one, is stepped past, and a broken link at or below the head refuses."""
    for day in reversed(line_days(root)):
        line = read_line(root, day)
        if all((root / relpath).is_file() for relpath in line.files):
            return walk_chain(root, day)[-1]
    raise RollingError(f"{root} holds no line whose listed files are all present")


def verify_line(root: Path, line: Line) -> None:
    for relpath, digest in sorted(line.files.items()):
        path = root / relpath
        if not path.is_file():
            raise RollingError(f"{line.relpath}: {relpath} is listed and absent from {root}")
        if _sha256(path) != digest:
            raise RollingError(f"{line.relpath}: {relpath} does not hash to its listing")


def verify(root: Path, as_of: date) -> Line:
    chain = walk_chain(root, as_of)
    for line in chain:
        verify_line(root, line)
    return chain[-1]


def _meets(day: date, window: tuple[datetime, datetime] | None) -> bool:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return window is None or (window[0] < start + timedelta(days=1) and start <= window[1])


def read_rolling(
    root: Path,
    pair: str,
    interval: int,
    as_of: date,
    *,
    window: tuple[datetime, datetime] | None = None,
    accept_holes: bool = False,
) -> RollingRead:
    """`pair`'s bars at `interval` from the base through `as_of`, in `FRAME_SCHEMA`'s order, every file it opens hashed
    against its listing first. `window`'s UTC bounds are both inclusive. A day `pair` has a hole on whose span meets the
    window refuses the read, unless `accept_holes`, which returns that day in `holes` and leaves it out of the frame."""
    set_pairs = pairs(root)
    if pair not in set_pairs:
        raise RollingError(f"{pair} is not one of {root}'s pairs: {', '.join(set_pairs)}")
    if interval not in _GRIDS:
        raise RollingError(f"{interval} is not one of the set's grids: {', '.join(map(str, _GRIDS))} minutes")
    chain = walk_chain(root, as_of)
    listed = [(_base_relpath(pair), chain[0].files[_base_relpath(pair)])]
    holes = []
    for line in chain[1:]:
        if pair in line.holes:
            if _meets(line.day, window):
                if not accept_holes:
                    raise RollingError(f"{root}: {pair} has a hole on {line.day} ({line.holes[pair]}) inside the window read")
                holes.append(line.day)
            continue
        relpath = _day_relpath(pair, line.day)
        listed.append((relpath, line.files[relpath]))
    frames = []
    for relpath, digest in listed:
        path = root / relpath
        if not path.is_file():
            raise RollingError(f"{root}: {relpath} is listed and absent")
        if _sha256(path) != digest:
            raise RollingError(f"{root}: {relpath} does not hash to its listing")
        frames.append(read_parquet(path).select(FRAME_SCHEMA.names()))
    bars = pl.concat(frames)
    if interval != _BASE_GRID:
        bars = derive_bars(bars, interval_minutes=interval).select(FRAME_SCHEMA.names())
    if window is not None:
        bars = bars.filter(pl.col("ts").is_between(*window))
    return RollingRead(bars, tuple(holes), chain[-1])
