"""The hot-cluster sync mechanics (spec 00056 D1c/D2): plain rsync `--archive --ignore-existing`,
never `--delete` -- additive-only by construction, so a fetch can never clobber a local edit and a
push can never clobber what another node already deposited."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cli.data.errors import DataSyncError
from cli.logging import get_logger
from cli.ohlc.dataset import dataset_hash, read_parquet

logger = get_logger("data.sync")

_REPO_ROOT = Path(__file__).resolve().parents[2]  # cli/data/sync.py -> repo root
_VOUCHED_SIDECAR = _REPO_ROOT / "docs" / "reference" / "vouched-dataset-hashes.jsonl"


@lru_cache(maxsize=1)
def _sidecar_by_dataset() -> dict[str, dict[str, str]]:
    """The committed per-series attestations, keyed by dataset.

    Some canonical sets are produced by a freeze process this repo does not write, whose manifest
    exposes no per-series hash at all -- leaving `_manifest_sha256s` empty and every consumer of it
    silently inert. This file is where those sets' hashes live instead. It is OUR format, uniform
    across sets, so reading it needs none of the per-set manifest knowledge that the manifest
    shapes would demand.

    Values are `dataset_hash` (sha256 of the frame's canonical CSV) -- the SAME grade every manifest
    writer vouches and both consumers compare. A byte-grade digest here would be a second,
    incompatible grade and would refuse every healthy read.
    """
    by_dataset: dict[str, dict[str, str]] = {}
    if not _VOUCHED_SIDECAR.is_file():
        logger.warning(
            "vouched attestations absent at %s -- frozen sets whose manifest vouches nothing are unverified in this environment",
            _VOUCHED_SIDECAR,
        )
        return {}
    for line_no, raw in enumerate(_VOUCHED_SIDECAR.read_text(encoding="utf-8").splitlines(), start=1):
        if not (line := raw.strip()):
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise DataSyncError(f"{_VOUCHED_SIDECAR.name}:{line_no}: unparseable attestation line") from exc
        if not isinstance(row, dict):
            raise DataSyncError(f"{_VOUCHED_SIDECAR.name}:{line_no}: attestation is not an object")
        try:
            series = by_dataset.setdefault(row["dataset"], {})
            relpath, digest = row["relpath"], row["dataset_sha256"]
        except KeyError as exc:
            raise DataSyncError(f"{_VOUCHED_SIDECAR.name}:{line_no}: attestation is missing {exc}") from exc
        # A second line for the same path would shadow the first silently, which is how a set
        # quietly ends up attested by the wrong hash.
        if relpath in series and series[relpath] != digest:
            raise DataSyncError(f"{_VOUCHED_SIDECAR.name}:{line_no}: {row['dataset']}/{relpath} attested twice, differently")
        series[relpath] = digest
    return by_dataset


def sidecar_hash_by_path(dataset: str) -> dict[str, str]:
    """Committed attestations for `dataset` BOUND TO PATHS, or empty when it has none.

    The path binding is what a manifest cannot give without per-set knowledge of that set's layout,
    and it is strictly stronger than a membership test: swapping two series inside one set leaves
    the set of hashes unchanged, so membership passes and a path-bound check does not.
    """
    return dict(_sidecar_by_dataset().get(dataset, {}))


def sidecar_hashes(dataset: str) -> set[str]:
    """Committed attestations for `dataset`, or an empty set when it has none."""
    return set(_sidecar_by_dataset().get(dataset, {}).values())


@dataclass(frozen=True)
class SyncReport:
    new_files: tuple[str, ...]  # relative paths rsync actually created
    skipped_existing: int  # files present on both sides (never transmitted)


def _run_rsync(src: Path, dst: str, runner, *, dry_run: bool = False) -> str:
    argv = ["rsync", "--archive", "--ignore-existing", "--itemize-changes", "--out-format=%i %n"]
    if dry_run:
        argv.append("--dry-run")
    argv += [f"{src}/", dst]
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


def _vouched_for_set(manifest_dir: Path, set_name: str) -> set[str]:
    """Everything that attests `set_name`: its own manifest, plus any committed sidecar line."""
    manifest_path = manifest_dir / "manifest.json"
    from_manifest = _manifest_sha256s(json.loads(manifest_path.read_text())) if manifest_path.is_file() else set()
    return from_manifest | sidecar_hashes(set_name)


def _attestation_failure(set_dir: Path, rel: str, vouched: set[str], by_path: dict[str, str]) -> str | None:
    """Why `rel`'s content is unattested, or None when it is attested. Shared by both directions.

    Path-BOUND whenever a committed attestation names this exact path, which membership cannot be:
    two series swapped inside one set leave the hash SET unchanged, so membership passes on both
    halves of the swap. Sets attested only by their own manifest fall back to membership, because
    deriving a path per hash needs the per-set layout knowledge the manifests share no shape for.
    """
    actual = dataset_hash(read_parquet(set_dir / rel))
    if (expected := by_path.get(rel)) is not None:
        if actual != expected:
            return f"content hash {actual} is not what {_VOUCHED_SIDECAR.name} attests for THAT path ({expected})"
    elif actual not in vouched:
        return f"content hash {actual} is attested by neither its manifest nor {_VOUCHED_SIDECAR.name}"
    return None


def _verify_outgoing(set_dir: Path, set_name: str, planned: tuple[str, ...]) -> None:
    """Re-hash what a push is about to transmit, and refuse content nothing attests.

    This is pre-flight rather than post-hoc for one reason: the channel is `--ignore-existing`, so a
    node that accepts tampered bytes is never corrected by any later push. Detecting it afterwards
    detects a permanent fact. The only containable moment is before the bytes leave.
    """
    parquets = tuple(rel for rel in planned if rel.endswith(".parquet"))
    if not parquets:
        return
    vouched = _vouched_for_set(set_dir, set_name)
    if not vouched:
        # Fail closed, and MORE readily than the fetch side: this is the permanent direction. A
        # fetch writes into our own tree, which can be inspected and re-fetched; a push writes into
        # a hub that never overwrites, so unattested bytes that leave are final everywhere. There is
        # deliberately no `--no-verify` counterpart here -- an escape on this side would be a
        # switch for transmitting content nothing vouches for, onto a channel with no undo.
        raise DataSyncError(
            f"data push: {set_name} ships parquet but is attested by neither its manifest nor "
            f"{_VOUCHED_SIDECAR.name} -- refusing to transmit content nothing vouches for onto a "
            f"channel that never overwrites"
        )
    by_path = sidecar_hash_by_path(set_name)
    for rel in parquets:
        if (why := _attestation_failure(set_dir, rel, vouched, by_path)) is not None:
            raise DataSyncError(
                f"data push: {set_name}/{rel} {why} -- refusing to transmit, because a node that "
                f"accepts these bytes can never be corrected by a later push"
            )


def _verify_new_files(hot_dir: Path, data_root: Path, new_files: tuple[str, ...]) -> None:
    new_by_set: dict[str, set[str]] = {}
    for rel in new_files:
        set_name, _, sub_path = rel.partition("/")
        if sub_path.endswith(".parquet"):  # only parquet content is manifest-attested; skip json/ledgers
            new_by_set.setdefault(set_name, set()).add(sub_path)

    for set_name, sub_paths in new_by_set.items():
        vouched = _vouched_for_set(hot_dir / set_name, set_name)
        if not vouched:
            # Fail closed. This used to warn and continue, which meant a set that silently stopped
            # emitting hashes degraded to no verification at all with only a log line -- and a log
            # line on a healthy-looking fetch is not read. Every set shipping parquet is attested
            # today, so this refuses nothing that works; `--no-verify` accepts it knowingly.
            raise DataSyncError(
                f"data fetch: {set_name} ships parquet but is attested by neither its manifest nor "
                f"{_VOUCHED_SIDECAR.name} -- refusing content nothing vouches for (--no-verify to accept it)"
            )
        by_path = sidecar_hash_by_path(set_name)
        for sub_path in sub_paths:
            if (why := _attestation_failure(data_root / set_name, sub_path, vouched, by_path)) is not None:
                raise DataSyncError(f"data fetch: {set_name}/{sub_path} {why}")


def fetch_hot(hot_dir: Path, data_root: Path, *, verify: bool = True, runner=subprocess.run) -> SyncReport:
    if not hot_dir.is_dir():
        raise DataSyncError(f"data fetch: hot_dir {hot_dir} does not exist or is not mounted")

    total_files = _count_files(hot_dir)
    output = _run_rsync(hot_dir, f"{data_root}/", runner)
    new_files = _parse_new_files(output)

    if verify:
        # After the transfer, not before, unlike the push side: a fetch writes into OUR tree, which
        # we can inspect and re-fetch, whereas a push writes into a never-overwriting hub where the
        # first bytes to arrive are final. So the refusal here reports; there it prevents.
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
        planned = _parse_new_files(_run_rsync(set_dir, f"{dest}{set_name}/", runner, dry_run=True))
        _verify_outgoing(set_dir, set_name, planned)
        output = _run_rsync(set_dir, f"{dest}{set_name}/", runner)
        new = _parse_new_files(output)
        all_new.extend(f"{set_name}/{n}" for n in new)
        skipped_total += total_files - len(new)

    return SyncReport(new_files=tuple(all_new), skipped_existing=skipped_total)
