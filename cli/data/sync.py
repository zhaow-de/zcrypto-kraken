"""The hot-cluster sync mechanics (spec 00056 D1c/D2): plain rsync `--archive --ignore-existing`,
never `--delete` -- additive-only by construction, so a fetch can never clobber a local edit and a
push can never clobber what another node already deposited."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from cli.data.errors import DataSyncError
from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet

logger = get_logger("data.sync")


@dataclass(frozen=True)
class SyncReport:
    new_files: tuple[str, ...]  # relative paths rsync actually created
    skipped_existing: int  # files present on both sides (never transmitted)


def _run_rsync(src: Path, dst: str, runner) -> str:
    argv = ["rsync", "--archive", "--ignore-existing", "--itemize-changes", "--out-format=%i %n", f"{src}/", dst]
    result = runner(argv, capture_output=True, text=True)
    if result.returncode != 0:
        raise DataSyncError(f"data sync: rsync {src} -> {dst} failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout


def _parse_new_files(output: str) -> tuple[str, ...]:
    new_files = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        flags, _, name = line.partition(" ")
        # itemize-changes: 2nd char is the item type ('f' file, 'd' directory, ...) -- only newly
        # transmitted regular files are "new files"; directory-creation lines are not.
        if len(flags) > 1 and flags[1] == "f":
            new_files.append(name.strip())
    return tuple(new_files)


def _count_files(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file())


def _manifest_sha256s(node: object) -> set[str]:
    """Every per-artifact ``sha256`` value anywhere in a (possibly deeply nested) manifest -- the
    content hashes the producer vouches for. The hot sets' manifests nest ``series`` by symbol (and
    by grid for OHLC: ``series[symbol][grid].sha256``; funding is ``series[symbol].sha256``), and
    each set lays its parquets out differently, so a file path cannot be derived from the manifest
    keys without per-set knowledge. Instead we attest each fetched parquet's content hash against
    this set -- catching transfer corruption (the real risk on an append-only, rsync-checksummed
    channel) without coupling this code to any set's on-disk layout. A manifest-level ``manifest_sha256``
    (the holdout carries one; it is not a per-parquet hash) is deliberately NOT collected -- the key
    must be exactly ``sha256``, so a set that exposes no per-parquet hashes yields the empty set."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "sha256" and isinstance(value, str):
                found.add(value)
            else:
                found |= _manifest_sha256s(value)
    elif isinstance(node, list):
        for item in node:
            found |= _manifest_sha256s(item)
    return found


def _verify_new_files(hot_dir: Path, data_root: Path, new_files: tuple[str, ...]) -> None:
    new_by_set: dict[str, set[str]] = {}
    for rel in new_files:
        set_name, _, sub_path = rel.partition("/")
        if sub_path.endswith(".parquet"):  # only parquet content is manifest-attested; skip json/ledgers
            new_by_set.setdefault(set_name, set()).add(sub_path)

    for set_name, sub_paths in new_by_set.items():
        manifest_path = hot_dir / set_name / "manifest.json"
        if not manifest_path.is_file():
            continue  # e.g. universe/snapshots ship no manifest
        vouched = _manifest_sha256s(json.loads(manifest_path.read_text()))
        if not vouched:
            logger.warning(
                "data fetch verify: %s manifest exposes no per-parquet sha256 -- transfer integrity for "
                "this set rests on rsync + the append-only contract, not a content re-check",
                set_name,
            )
            continue
        for sub_path in sub_paths:
            actual = dataset_hash(read_parquet(data_root / set_name / sub_path))
            if actual not in vouched:
                raise DataSyncError(f"data fetch: {set_name}/{sub_path} content hash {actual} is not attested by the manifest")


def fetch_hot(hot_dir: Path, data_root: Path, *, verify: bool = True, runner=subprocess.run) -> SyncReport:
    if not hot_dir.is_dir():
        raise DataSyncError(f"data fetch: hot_dir {hot_dir} does not exist or is not mounted")

    total_files = _count_files(hot_dir)
    output = _run_rsync(hot_dir, f"{data_root}/", runner)
    new_files = _parse_new_files(output)

    if verify:
        _verify_new_files(hot_dir, data_root, new_files)

    return SyncReport(new_files=new_files, skipped_existing=total_files - len(new_files))


def push_hot(
    data_root: Path, authored_sets: Sequence[str], dest: str, *, extra_sets: Sequence[str] = (), runner=subprocess.run
) -> SyncReport:
    all_sets = [*authored_sets, *extra_sets]
    missing = [s for s in all_sets if not (data_root / s).is_dir()]
    if missing:
        raise DataSyncError(f"data push: authored set(s) not found under {data_root}: {', '.join(missing)}")

    all_new: list[str] = []
    skipped_total = 0
    for set_name in all_sets:
        set_dir = data_root / set_name
        total_files = _count_files(set_dir)
        output = _run_rsync(set_dir, f"{dest}{set_name}/", runner)
        new = _parse_new_files(output)
        all_new.extend(f"{set_name}/{n}" for n in new)
        skipped_total += total_files - len(new)

    return SyncReport(new_files=tuple(all_new), skipped_existing=skipped_total)
