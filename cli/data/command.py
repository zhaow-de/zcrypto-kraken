"""The `zcrypto data` Typer sub-app (spec 00056): wiring and exit codes only -- the rsync mechanics live in `cli.data.sync`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from cli.config import ConfigError, load_config, resolve_data_dir, resolve_hot_source, resolve_ohlcvt_source_dir, resolve_push_dest
from cli.data.errors import DataSyncError
from cli.data.rebuild import RebuildContext, rebuild_sets
from cli.data.sync import fetch_hot, push_hot
from cli.logging import get_logger

logger = get_logger("data.command")

data_app = typer.Typer(
    no_args_is_help=True,
    help="Hot-cluster dataset exchange: fetch the shared working set, push what this node authored, rebuild frozen sets.",
)


def _abort(message: str) -> typer.Exit:
    """A clean one-line error (logged, no traceback) + exit code 1. Usage: `raise _abort(...)`."""
    logger.error(message)
    return typer.Exit(code=1)


@data_app.command()
def fetch(
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip manifest hash verification of newly fetched files."),
) -> None:
    """Additively mirror the NAS hot/ hub into the local data root."""
    try:
        cfg = load_config()
        resolved_hot_dir = resolve_hot_source(cfg)
        data_root = resolve_data_dir(None, cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc

    try:
        report = fetch_hot(resolved_hot_dir, data_root, verify=not no_verify)
    except DataSyncError as exc:
        raise _abort(str(exc)) from exc

    logger.info("data fetch: new=%d skipped=%d", len(report.new_files), report.skipped_existing)


@data_app.command()
def push() -> None:
    """Push this node's authored sets to the configured push_dest (never the rw NFS mount)."""
    try:
        cfg = load_config()
        dest = resolve_push_dest(cfg)
        data_root = resolve_data_dir(None, cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc

    try:
        report = push_hot(data_root, cfg.data.authored_sets, dest)
    except DataSyncError as exc:
        raise _abort(str(exc)) from exc

    logger.info("data push: new=%d skipped=%d", len(report.new_files), report.skipped_existing)


@data_app.command()
def rebuild(
    sets: list[str] = typer.Argument(
        ...,
        help="Dataset names to rebuild (ohlc-full, ohlc-reach, ohlc-15m, derivatives-funding, derivatives-oi, snapshots, universe).",
    ),
    push_after: bool = typer.Option(True, "--push/--no-push", help="Push the minted sibling(s) to push_dest after rebuilding."),
) -> None:
    """Re-freeze/refresh dataset(s) by minting a new sibling dir -- never touches the live set."""
    try:
        cfg = load_config()
        data_root = resolve_data_dir(None, cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc

    # The ohlcvt source derives from nfs_mount_dir, so it is always a path; a missing mount fails loudly at read time.
    ctx = RebuildContext(
        data_root=data_root,
        ohlcvt_source_dir=resolve_ohlcvt_source_dir(None, cfg),
        stamp=datetime.now(UTC).strftime("%Y%m%d"),
    )

    try:
        minted = rebuild_sets(sets, ctx)
    except DataSyncError as exc:
        raise _abort(str(exc)) from exc

    logger.info("data rebuild: minted %s", ", ".join(str(p) for p in minted))

    if not push_after:
        return

    try:
        dest = resolve_push_dest(cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc

    try:
        # Push ONLY the freshly-minted siblings, not the whole authored set (a rebuild publishes what
        # it just built; re-pushing every authored set would also abort here on a node missing one).
        report = push_hot(data_root, [], dest, extra_sets=[p.name for p in minted])
    except DataSyncError as exc:
        raise _abort(str(exc)) from exc

    logger.info("data rebuild push: new=%d skipped=%d", len(report.new_files), report.skipped_existing)


@data_app.command("migrate-manifests")
def migrate_manifests(
    apply: bool = typer.Option(False, "--apply", help="Write the converted manifests. Without this, only report."),
) -> None:
    """Rewrite legacy dataset manifests into the current contract, from the parquets on disk.

    No parquet is touched; a set is refused whole if any series no longer hashes to what its legacy manifest attested.
    """
    from cli.data.manifest import ManifestError, convert_dataset

    cfg = load_config()
    data_root = resolve_data_dir(None, cfg)
    if not data_root.is_dir():
        raise _abort(f"data root {data_root} does not exist")

    results = []
    for manifest_path in sorted(data_root.glob("*/manifest.json")):
        root = manifest_path.parent
        # The external freeze is out of contract by design: it is not ours to rewrite, and its
        # attestation content lives in the committed sidecar instead.
        if root.name.startswith("ohlc-holdout-"):
            results.append({"dataset": root.name, "status": "external freeze, skipped", "series": 0})
            continue
        try:
            results.append(convert_dataset(root, apply=apply))
        except ManifestError as exc:
            raise _abort(str(exc)) from exc

    for r in results:
        typer.echo(f"{r['dataset']:32} {r['status']:24} series={r['series']}")
    if not apply:
        typer.echo("\nDry run. Re-run with --apply to write.")
