from __future__ import annotations

import os
import stat
from pathlib import Path


def open_sealed_directories(root: Path) -> list[str]:
    """Owner rwx on every directory under `root`, so a tree a test sealed can be deleted; one fault string per directory
    it could not open."""
    faults: list[str] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            mode = directory.lstat().st_mode
            if not stat.S_ISDIR(mode):
                continue
            if mode & 0o700 != 0o700:
                os.chmod(directory, stat.S_IMODE(mode) | 0o700)
            with os.scandir(directory) as entries:
                stack.extend(Path(e.path) for e in entries if e.is_dir(follow_symlinks=False))
        except OSError as exc:
            faults.append(f"open {directory}: {exc}")
    return faults
