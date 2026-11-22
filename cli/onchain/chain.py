"""The vintage chain in `ohlc-rolling`'s form (spec D8): `base/history.parquet` through the base day, one
`days/<YYYY>/<MM>/<DD>.parquet` for each day after it, and one canonical index line per day, each `prev` the sha256 of
the line before it. Every file is created exclusive under `staging/`, linked into place once and never written again."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from cli.data.rolling import RollingError, _sha256, line_relpath
from cli.data.rolling import line_days as _rolling_line_days

CHAIN_GENERATION = 1
VINTAGE_KEYS = frozenset(
    {"written_at", "last_height", "last_hash", "tip_height", "depth", "brk_commit", "bitview_image", "bitcoind_image", "chain"}
)
_STAGING = "staging"
_BASE_RELPATH = "base/history.parquet"
_KEYS = frozenset({"day", "prev", "files", "vintage"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


class ChainError(Exception):
    """A refusal by the chain's reader or writer; its message names the line, the file or the day at fault."""


@dataclass(frozen=True)
class Line:
    day: date
    prev: str | None
    files: dict[str, str]
    vintage: dict
    relpath: str
    sha256: str


def chain_name(brk_commit: str, generation: int = CHAIN_GENERATION) -> str:
    return f"btc-brk{brk_commit[:12]}-g{generation}"


def _day_relpath(day: date) -> str:
    return f"days/{day:%Y}/{day:%m}/{day:%d}.parquet"


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def line_days(root: Path) -> list[date]:
    """`ohlc-rolling`'s walk of `root`'s index, whose lines share its relpaths; a name not of a day is the chain's
    refusal."""
    try:
        return _rolling_line_days(root)
    except RollingError as exc:
        raise ChainError(str(exc)) from exc


def read_line(root: Path, day: date) -> Line:
    """`day`'s line with its shape checked; its link to the line before it is `walk`'s."""
    relpath = line_relpath(day)
    data = (root / relpath).read_bytes()
    try:
        line = json.loads(data)
    except ValueError:
        line = None
    if not isinstance(line, dict) or canonical(line) != data:
        raise ChainError(f"{relpath}: not an index line in its canonical form")
    if line.keys() != _KEYS:
        raise ChainError(f"{relpath}: its keys are {sorted(line)}, not {sorted(_KEYS)}")
    if line["day"] != day.isoformat():
        raise ChainError(f"{relpath}: its day is {line['day']!r}, not the {day} its name gives")
    prev, files, vintage = line["prev"], line["files"], line["vintage"]
    if not isinstance(files, dict) or not all(isinstance(digest, str) and _SHA256.fullmatch(digest) for digest in files.values()):
        raise ChainError(f"{relpath}: a file it lists is not mapped to a sha256")
    if not isinstance(vintage, dict):
        raise ChainError(f"{relpath}: its vintage is not a map")
    if prev is None:
        if files.keys() != {_BASE_RELPATH}:
            raise ChainError(f"{relpath}: a base line lists {_BASE_RELPATH} alone")
    else:
        if not isinstance(prev, str) or not _SHA256.fullmatch(prev):
            raise ChainError(f"{relpath}: its prev is neither null nor a sha256")
        if files.keys() != {_day_relpath(day)}:
            raise ChainError(f"{relpath}: a day line lists {_day_relpath(day)} alone, its own day's file")
    return Line(day, prev, files, vintage, relpath, hashlib.sha256(data).hexdigest())


def _walk(root: Path, as_of: date, newest: int | None) -> list[Line]:
    days = line_days(root)
    if as_of not in days:
        raise ChainError(f"{root} holds no line for {as_of}; its newest is for {days[-1] if days else 'no day'}")
    through = [day for day in days if day <= as_of]
    read = through if newest is None else through[max(len(through) - newest, 0) :]
    lines: list[Line] = []
    for day in reversed(read):
        line = read_line(root, day)
        if lines:
            after = lines[-1]
            if after.day != line.day + timedelta(days=1):
                raise ChainError(f"{after.relpath}: no line for {line.day + timedelta(days=1)}, the day after {line.relpath}")
            if after.prev != line.sha256:
                raise ChainError(f"{after.relpath}: its prev is not the sha256 of {line.relpath}")
        lines.append(line)
    if len(read) == len(through) and lines[-1].prev is not None:
        raise ChainError(f"{lines[-1].relpath}: the oldest line under {root} is not a base line; its prev is not null")
    return lines[::-1]


def walk(root: Path, as_of: date) -> list[Line]:
    """Every line from the base through `as_of`'s, each the day after the one before it and its `prev` the sha256 of
    that line's bytes. No file a line lists is opened."""
    return _walk(root, as_of, None)


def verify(root: Path, as_of: date, newest: int | None = None) -> Line:
    """`walk`, then every listed file's bytes against its sha256; `as_of`'s line returned. Given `newest`, only the
    newest that many lines through `as_of` are read: their links to each other and their files."""
    lines = _walk(root, as_of, newest)
    for line in lines:
        for relpath, digest in sorted(line.files.items()):
            try:
                found = _sha256(root / relpath)
            except FileNotFoundError as exc:
                raise ChainError(f"{line.relpath}: {relpath} is listed and absent from {root}") from exc
            if found != digest:
                raise ChainError(f"{line.relpath}: {relpath} does not hash to its listing")
    return lines[-1]


def head(root: Path) -> Line | None:
    """The newest line, its shape read; its links are `walk`'s."""
    days = line_days(root)
    return read_line(root, days[-1]) if days else None


def staging_leftovers(root: Path) -> list[Path]:
    """Every name under `<root>/staging`, each a temporary a writer that died left: a live write renames its own or
    removes it."""
    try:
        return sorted((root / _STAGING).iterdir())
    except FileNotFoundError:
        return []


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _place(root: Path, relpath: str, data: bytes) -> None:
    """`data` at `root / relpath`, written whole to an exclusive temporary under `staging/`, fsynced and renamed in. A
    present target is refused: past `write_base`'s and `write_day`'s refusals, only a writer that died between a file's
    rename and its line's leaves one."""
    target = root / relpath
    if os.path.lexists(target):
        raise ChainError(f"{root}: no line names {relpath}, and it is present: a writer stopped between its rename and its line's")
    staging = root / _STAGING
    staging.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = staging / f"{target.name}.{os.getpid()}.{secrets.token_hex(4)}"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _fsync_directory(target.parent)


def _write(root: Path, day: date, prev: str | None, relpath: str, frame: pl.DataFrame, vintage: dict) -> Line:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    data = buffer.getvalue()
    line = canonical(
        {"day": day.isoformat(), "prev": prev, "files": {relpath: hashlib.sha256(data).hexdigest()}, "vintage": vintage}
    )
    _place(root, relpath, data)
    _place(root, line_relpath(day), line)
    return read_line(root, day)


def write_base(root: Path, frame: pl.DataFrame, vintage: dict) -> Line:
    """`frame`, every day from the first through the base day, as the base file, and the base day's line."""
    days = line_days(root)
    if days:
        raise ChainError(f"{root} holds lines through {days[-1]}; a base is written only into a chain with none")
    return _write(root, frame["ts"].max().date(), None, _BASE_RELPATH, frame, vintage)


def write_day(root: Path, frame: pl.DataFrame, vintage: dict) -> Line:
    """`frame`, one day's row, as that day's file, and its line, linked to the head's."""
    if frame.height != 1:
        raise ChainError(f"{root}: a day line is written from a frame of one day, and this one holds {frame.height} rows")
    day = frame["ts"][0].date()
    last = head(root)
    if last is None:
        raise ChainError(f"{root} holds no base line")
    if day != last.day + timedelta(days=1):
        said = "already written" if day <= last.day else "not the next day"
        raise ChainError(f"{root}: {day} is {said}; its head is {last.day}")
    return _write(root, day, last.sha256, _day_relpath(day), frame, vintage)
