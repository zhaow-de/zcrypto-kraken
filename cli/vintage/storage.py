"""The record's write primitives: a file created exclusive and read-only, gzip with no clock in its bytes, a directory's
fsync, and the two renames that publish a tick and a `.prom`."""

from __future__ import annotations

import errno
import gzip
import os
import tempfile
from pathlib import Path


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


def publish_tick(staged: Path, target: Path) -> None:
    """Moves the assembled tick to its target by one rename; `os.rename` replaces an empty directory, so the target's
    absence is checked here, under the caller's lock."""
    if target.exists():
        raise FileExistsError(errno.EEXIST, "the tick's target exists", str(target))
    for directory in reversed(target.parents):
        if not directory.exists():
            directory.mkdir(mode=0o755)
            os.chmod(directory, 0o755)
    os.rename(staged, target)
    fsync_dir(target.parent)
    os.chmod(target, 0o555)


def publish_prom(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        _write_all(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
