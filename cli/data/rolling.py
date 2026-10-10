"""The rolling canonical, `ohlc-rolling` (spec 00125): a 15-minute base copied from a frozen quarter and a daily extension
copied from tape-bars, every UTC day attested by a write-once index line whose `prev` is the sha256 of the line before it.

A pin is an as-of day, identified by the sha256 of that day's line; every reader reaches a file only through the lines."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import polars as pl

from cli.data.manifest import ManifestError, read_manifest
from cli.ohlc.dataset import FRAME_SCHEMA, dataset_hash, read_parquet
from cli.tick.errors import TickError
from cli.tick.materialize import RESCAN_DAYS, _final_path, _fsync, _watermark, derive_bars

ROLLING_SET = "ohlc-rolling"
_BASE_GRID = 15
_GRIDS = (_BASE_GRID, 60, 240, 1440)
_KEYS = frozenset({"day", "prev", "files", "holes"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_BASE_FILE = re.compile(r"base/[A-Z0-9]+/[A-Z0-9]+/15\.parquet")
_DAY_FILE = re.compile(r"days/[A-Z0-9]+/[A-Z0-9]+/(\d{4}/\d{2}/\d{2})\.parquet")
_CLOSED = "closed "
BASE_DAY = date(2026, 9, 30)
_SEAM = "2026-10-01T00:00:00+00:00"
_VWAP = "the dump's close-weighted proxy before the seam, the tape's tick-weighted mean from it"
_PAST_THE_WINDOW = "no tape-bars final past the re-scan window"
_OWNERS_CLOSE = "closed on the owner's word"
_DIR_MODE = 0o2775
_FILE_MODE = 0o664

# The sha256 of each of `ohlc-15m-20261007`'s twelve 15-minute files, the frame the base is copied from: every 15-minute
# sibling with the same paths has a conformant manifest of its own, so only these bytes bind the base to that frame.
Q3_15M_SHA256 = {
    "ADA/EUR": "2f97a4e799d4f7232e813c8d7b937680046c1e52cd16391cdae853bc37f8fe74",
    "AVAX/EUR": "3613a84673b0bb70c7f0568a051561c1cd18dfa834aad6c6121b99c304e0b918",
    "BTC/EUR": "5b4f4a1ca279e1787791bad3613d238ab709a7243f782d3e5a8f5dac5445d8a8",
    "DOGE/EUR": "ad39c224de57b3d373284c0b9234938a3028fc5a97bd4953ad65f502f18c84d2",
    "DOT/EUR": "40bb776753c1844fd67d3462b14626ccff6de83ae463bb5fb1a9ca39f1c3f574",
    "ETH/BTC": "30e1bc25f4723b90213220a84b3bf5477478471711503a6fa89e691bc3cbcf7a",
    "ETH/EUR": "190a577355181c6a45c5ae58d6ef3bd702fac6c3ade1c014ebd968f20bfc6aa2",
    "LINK/EUR": "82ecb1abc7460e5e6f042b5466f0b0377e309a2432ce6a5ef31da1f04cbee7ea",
    "LTC/EUR": "19316cec547ef142d0fefa58b2a8d283d8724703b253f85420c6e4efab58f5f4",
    "SOL/BTC": "51bf01fe3a64fdbaa80aabfa7bec461de42a10cf3d30fc40b03cf6b69321425e",
    "SOL/EUR": "74e02128964419a9adee8079bb23c37d13474acc44efdd6a72a15a5607cf56c4",
    "XRP/EUR": "9f294239916b7c1afe679fbcd440bbcca9900a252fcab65f9f0539320813982b",
}


class RollingError(Exception):
    """A refusal by the set's reader or writer: the set, the base's source or tape-bars' tree is not what the set requires."""


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


@dataclass(frozen=True)
class Close:
    """The owner's close of `pairs` from `from_day`: each a hole from that day on, until a final of its own reappears."""

    pairs: tuple[str, ...]
    from_day: date
    word: str
    word_date: date


@dataclass(frozen=True)
class ExtendResult:
    days_written: int
    holes: int
    head: Line
    ended: bool


@dataclass(frozen=True)
class _Day:
    line: Line
    data: bytes
    files: dict[str, bytes]


def _make_dirs(directory: Path) -> None:
    """`directory` and its missing ancestors, each created `_DIR_MODE` whatever the umask. A directory already present
    keeps its mode: another user's directory refuses a chmod."""
    missing = []
    present = directory
    while not present.is_dir():
        missing.append(present)
        present = present.parent
    for each in reversed(missing):
        os.mkdir(each)
    for each in missing:
        os.chmod(each, _DIR_MODE)


def _staged(staging: Path, name: str, source: BinaryIO) -> Path:
    """A temporary under `staging` holding `source`'s bytes, fsynced, mode `_FILE_MODE`."""
    fd, path = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=staging)
    try:
        with os.fdopen(fd, "wb") as f:
            shutil.copyfileobj(source, f)
            f.flush()
            os.fsync(f.fileno())
            os.fchmod(f.fileno(), _FILE_MODE)
    except BaseException:
        Path(path).unlink(missing_ok=True)
        raise
    return Path(path)


def _place(staging: Path, out: Path, relpath: str, data: bytes) -> None:
    """`data` at `out / relpath`, renamed in from a temporary under `staging`. A destination already holding these bytes
    is accepted, so a stopped run completes on the next; one holding other bytes refuses."""
    dest = out / relpath
    if dest.exists():
        if dest.read_bytes() == data:
            return
        raise RollingError(f"{dest} is present with other bytes; the set never rewrites a file")
    _make_dirs(dest.parent)
    tmp = _staged(staging, dest.name, io.BytesIO(data))
    try:
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync(dest.parent)


def stage_base(source: Path, out: Path, staging: Path) -> Line:
    """Copy the 15-minute frame at `source` into `out` as the set's base and write the base line. Each file is copied to
    a temporary under `staging` and checked -- the source's pairs, each temporary's sha256 against `Q3_15M_SHA256`, each
    frame's `dataset_hash` against the source's manifest -- before the first rename into `out`."""
    found = {f"{path.parent.parent.name}/{path.parent.name}" for path in source.glob("*/*/15.parquet")}
    if found != Q3_15M_SHA256.keys():
        missing, outside = sorted(Q3_15M_SHA256.keys() - found), sorted(found - Q3_15M_SHA256.keys())
        raise RollingError(
            f"{source} does not hold the Q3 frame's twelve pairs: "
            f"missing {', '.join(missing) or 'none'}; outside it {', '.join(outside) or 'none'}"
        )
    manifest_path = source / "manifest.json"
    try:
        manifest = read_manifest(manifest_path)
    except ManifestError as exc:
        raise RollingError(str(exc)) from exc
    attested = manifest.hash_by_path()
    staged: dict[str, tuple[Path, str]] = {}
    try:
        for pair in sorted(found):
            name = f"{pair}/15.parquet"
            with (source / name).open("rb") as f:
                tmp = _staged(staging, "15.parquet", f)
            digest = _sha256(tmp)
            staged[_base_relpath(pair)] = (tmp, digest)
            if digest != Q3_15M_SHA256[pair]:
                raise RollingError(f"{source / name}: its sha256 {digest} is not the Q3 frame's {Q3_15M_SHA256[pair]}")
            try:
                frame_hash = dataset_hash(read_parquet(tmp))
            except pl.exceptions.PolarsError as exc:
                raise RollingError(f"{source / name}: polars cannot read it: {exc}") from exc
            if frame_hash != attested.get(name):
                raise RollingError(f"{source / name}: its frame's dataset_hash is not the one {manifest_path} attests for {name}")
        present = [relpath for relpath in staged if (out / relpath).exists()]
        for relpath in present:
            if _sha256(out / relpath) != staged[relpath][1]:
                raise RollingError(f"{out / relpath} is present with other bytes; the set never rewrites a file")
        for relpath, (tmp, _) in staged.items():
            if relpath not in present:
                _make_dirs((out / relpath).parent)
                os.replace(tmp, out / relpath)
                _fsync((out / relpath).parent)
    finally:
        for tmp, _ in staged.values():
            tmp.unlink(missing_ok=True)
    notes = {"seam": _SEAM, "base_from": source.absolute().name, "base_identity_digest": manifest.identity_digest, "vwap": _VWAP}
    files = {relpath: digest for relpath, (_, digest) in staged.items()}
    base = {"day": BASE_DAY.isoformat(), "prev": None, "files": files, "holes": {}, "notes": notes}
    _place(staging, out, line_relpath(BASE_DAY), _canonical(base))
    return read_line(out, BASE_DAY)


def list_tape(tape_root: Path, pairs: tuple[str, ...]) -> None:
    """List `tape_root` and, for each of `pairs` whose directory it holds, that directory and every directory below it,
    so an absent root or a directory this reader cannot list raises its `OSError`: `_watermark`'s `rglob` and a final's
    `is_file` read such a directory as holding no final. Called before the first read of `tape_root`."""

    def refuse(exc: OSError) -> None:
        raise exc

    held = set(os.listdir(tape_root))
    for pair in pairs:
        asset, quote = pair.split("/")
        if asset in held and quote in os.listdir(tape_root / asset):
            for _ in os.walk(tape_root / asset / quote, onerror=refuse):
                pass


def _newest_final(tape_root: Path, pair: str) -> date | None:
    try:
        return _watermark(tape_root, pair)
    except TickError as exc:
        raise RollingError(str(exc)) from exc


def is_ended(root: Path, line: Line, tape_root: Path) -> bool:
    """True when `line` closes every one of the set's pairs and none of them has a final under `tape_root` dated after
    it -- the set ended by the owner's closes, which such a later final reopens. The tape is read only for a line that
    closes every pair, and only after `list_tape`."""
    set_pairs = pairs(root)
    if not all(f"{_CLOSED}{pair}" in line.notes for pair in set_pairs):
        return False
    return not any((_newest_final(tape_root, pair) or line.day) > line.day for pair in set_pairs)


def _final_bytes(final: Path) -> bytes:
    """`final`'s bytes, refused unless its tape-bars sidecar names their sha256."""
    data = final.read_bytes()
    sidecar = final.with_suffix(".parquet.sha256")
    if not sidecar.is_file():
        raise RollingError(f"{final} has no sidecar {sidecar.name}")
    if sidecar.read_text() != f"{hashlib.sha256(data).hexdigest()}  {final.name}\n":
        raise RollingError(f"{final} does not hash to its sidecar {sidecar.name}")
    return data


def _plan(tape_root: Path, out: Path, line: Line, set_pairs: tuple[str, ...], close: Close | None) -> tuple[list[_Day], bool, str]:
    """Each day after `line` the run can write, every line built and every final checked against its sidecar before
    any is written; whether the plan stops at an ended line; and where it stops, said for the close's refusal."""
    planned: list[_Day] = []
    while True:
        if is_ended(out, line, tape_root):
            return planned, True, f"the set is ended at {line.day}"
        day = line.day + timedelta(days=1)
        closes = {key.removeprefix(_CLOSED): text for key, text in line.notes.items() if key.startswith(_CLOSED)}
        if close is not None and day == close.from_day:
            closes |= dict.fromkeys(close.pairs, f"from {close.from_day}, the owner's word of {close.word_date}: {close.word}")
        files: dict[str, bytes] = {}
        holes: dict[str, str] = {}
        notes: dict[str, str] = {}
        waiting: list[str] = []
        for pair in set_pairs:
            final = _final_path(tape_root, pair, day)
            if final.is_file():
                files[_day_relpath(pair, day)] = _final_bytes(final)
            elif pair in closes:
                holes[pair] = _OWNERS_CLOSE
                notes[f"{_CLOSED}{pair}"] = closes[pair]
            else:
                waiting.append(pair)
        if waiting and not all((_newest_final(tape_root, pair) or day) > day + timedelta(days=RESCAN_DAYS) for pair in waiting):
            return planned, False, f"{day} waits on {', '.join(waiting)}"
        holes |= dict.fromkeys(waiting, _PAST_THE_WINDOW)
        listed = {relpath: hashlib.sha256(data).hexdigest() for relpath, data in files.items()}
        entry = {"day": day.isoformat(), "prev": line.sha256, "files": listed, "holes": holes}
        if notes:
            entry["notes"] = notes
        data = _canonical(entry)
        line = Line(day, entry["prev"], listed, holes, notes, line_relpath(day), hashlib.sha256(data).hexdigest())
        planned.append(_Day(line, data, files))


def extend(tape_root: Path, out: Path, staging: Path, *, close: Close | None = None) -> ExtendResult:
    """Extend the set at `out` from the day after its head with tape-bars' finals under `tape_root`, each day's files
    renamed in before its line. A day is written once each pair has a final for it, is under the owner's close, or has
    a newest final dated `RESCAN_DAYS` + 1 days or more after it; otherwise the run stops there, and it stops at a line
    `is_ended`. A `close` is refused, nothing written, unless this run writes its first line."""
    if not (out / line_relpath(BASE_DAY)).is_file():
        raise RollingError(f"{out} holds no base line")
    line = head(out)
    set_pairs = pairs(out)
    if close is not None:
        for pair in close.pairs:
            if pair not in set_pairs:
                raise RollingError(f"the close names {pair}, which is not one of {out}'s pairs: {', '.join(set_pairs)}")
    list_tape(tape_root, set_pairs)
    if close is not None:
        for pair in close.pairs:
            if _final_path(tape_root, pair, close.from_day).is_file():
                raise RollingError(f"{pair} has a tape-bars final for {close.from_day}, so it cannot be closed from that day")
    planned, ended, stop = _plan(tape_root, out, line, set_pairs, close)
    if close is not None and close.from_day not in {day.line.day for day in planned}:
        raise RollingError(f"the close from {close.from_day} is refused: this run writes no line for that day ({stop})")
    for day in planned:
        for relpath, data in day.files.items():
            _place(staging, out, relpath, data)
        _place(staging, out, day.line.relpath, day.data)
    return ExtendResult(len(planned), sum(len(day.line.holes) for day in planned), planned[-1].line if planned else line, ended)
