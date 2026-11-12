"""The record's write primitives: a file created exclusive and read-only, gzip with no clock in its bytes, a directory's
fsync, and the three renames that publish a tick, a `.prom` and a versions-table directory."""

from __future__ import annotations

import errno
import gzip
import os
import tempfile
from pathlib import Path

AFTER_RENAME = "after the rename: "


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def create_exclusive(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def gzip_bytes(raw: bytes) -> bytes:
    return gzip.compress(raw, compresslevel=9, mtime=0)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _make_parents(target: Path) -> None:
    """Every missing directory above the target, each 0755."""
    for directory in reversed(target.parents):
        if not directory.exists():
            directory.mkdir(mode=0o755)
            os.chmod(directory, 0o755)


def _seal_renamed(target: Path) -> None:
    """The parent's fsync and the chmod to 0555 after a publishing rename; an OSError carries a note naming the step,
    the directory being published by then."""
    step = "the parent's fsync"
    try:
        fsync_dir(target.parent)
        step = "the chmod to 0555"
        os.chmod(target, 0o555)
    except OSError as exc:
        exc.add_note(f"{AFTER_RENAME}{step}")
        raise


def publish_tick(staged: Path, target: Path) -> None:
    """Moves the assembled tick to its target by one rename; `os.rename` replaces an empty directory, so the target's
    absence is checked here, under the caller's lock. An OSError raised after the rename carries a note naming the
    step, the tick being published by then."""
    if target.exists():
        raise FileExistsError(errno.EEXIST, "the tick's target exists", str(target))
    _make_parents(target)
    os.rename(staged, target)
    _seal_renamed(target)


def refuse_table_root(table_root: Path, record_root: Path, nas_mount: Path) -> str | None:
    """Why the table root is refused, None when it is admitted: the resolved table root may lie neither in the record
    root, nor in its parent, the recorder's own data root, nor under the NAS mount."""
    table, record, nas = (path.resolve() for path in (table_root, record_root, nas_mount))
    for name, wall in (("the record root", record), ("the record root's parent", record.parent), ("the NAS mount", nas)):
        if table.is_relative_to(wall):
            return f"the table root {table} lies in {name} {wall}"
    return None


def publish_table_dir(staged: Path, target: Path, *, table_root: Path, record_root: Path, nas_mount: Path) -> None:
    """Moves a staged generation, part or head directory to its target in the table by one rename, then sets it 0555;
    `os.rename` replaces an empty directory, so the target's absence is checked here, under the caller's lock. An
    OSError raised after the rename carries a note naming the step, the directory being published by then."""
    refusal = refuse_table_root(table_root, record_root, nas_mount)
    if refusal is not None:
        raise PermissionError(refusal)
    if target.exists():
        raise FileExistsError(errno.EEXIST, "the table directory's target exists", str(target))
    _make_parents(target)
    os.rename(staged, target)
    _seal_renamed(target)


def publish_prom(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        _write_all(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
