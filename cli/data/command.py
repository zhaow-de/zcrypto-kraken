"""The `zcrypto data` Typer sub-app (spec 00056): wiring and exit codes only -- the rsync mechanics live in `cli.data.sync`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import typer

from cli.config import ConfigError, load_config, resolve_data_dir, resolve_hot_source, resolve_ohlcvt_source_dir, resolve_push_dest
from cli.data.errors import DataSyncError
from cli.data.rebuild import BUILDER_REFUSALS, REBUILDABLE, RebuildContext, rebuild_sets
from cli.data.sync import fetch_hot, push_hot
from cli.logging import get_logger

logger = get_logger("data.command")

data_app = typer.Typer(
    no_args_is_help=True,
    help="Hot-cluster dataset exchange: fetch the shared working set, push what this node authored, rebuild frozen sets.",
)
rolling_app = typer.Typer(
    no_args_is_help=True,
    help="The rolling OHLC set: one 15-minute history extended day by day, each day pinned by a chained index line.",
)
data_app.add_typer(rolling_app, name="rolling")


def _abort(message: str) -> typer.Exit:
    """Usage: `raise _abort(...)` -- it RETURNS the exception."""
    logger.error(message)
    return typer.Exit(code=1)


@data_app.command()
def fetch(
    no_verify: bool = typer.Option(
        False, "--no-verify", help="Skip hash verification of newly fetched files against their manifest or index."
    ),
) -> None:
    """Additively mirror the NAS hot/ hub into the local data root."""
    try:
        cfg = load_config()
        resolved_hot_dir = resolve_hot_source(cfg)
        data_root = resolve_data_dir(cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc

    try:
        report = fetch_hot(resolved_hot_dir, data_root, verify=not no_verify)
    except DataSyncError as exc:
        raise _abort(str(exc)) from exc

    logger.info("data fetch: new=%d skipped=%d", len(report.new_files), report.skipped_existing)


@data_app.command()
def push() -> None:
    """Push this node's authored sets to the configured push_dest -- by convention never the rw NFS mount."""
    try:
        cfg = load_config()
        dest = resolve_push_dest(cfg)
        data_root = resolve_data_dir(cfg)
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
        help=f"Dataset names to rebuild ({', '.join(REBUILDABLE)}).",
    ),
    push_after: bool = typer.Option(True, "--push/--no-push", help="Push the minted sibling(s) to push_dest after rebuilding."),
) -> None:
    """Re-freeze/refresh dataset(s) by minting a new sibling dir -- never touches the live set."""
    try:
        cfg = load_config()
        data_root = resolve_data_dir(cfg)
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
    except BUILDER_REFUSALS as exc:
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

    try:
        cfg = load_config()
        data_root = resolve_data_dir(cfg)
    except ConfigError as exc:
        raise _abort(str(exc)) from exc
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


@rolling_app.command("verify")
def rolling_verify(
    root: Path | None = typer.Option(
        None, "--root", help="The set's directory; ohlc-rolling under the configured data root if unset."
    ),
    as_of: str = typer.Option(..., "--as-of", help="The day whose index line to verify the set at, as YYYY-MM-DD."),
) -> None:
    """Walk the set's index from the as-of day down to its base, re-hash every file it lists, and print that day's line sha256."""
    from cli.data.rolling import ROLLING_SET, RollingError, verify, walk_chain

    try:
        day = datetime.strptime(as_of, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _abort(f"--as-of {as_of!r} is not a YYYY-MM-DD date") from exc
    if root is None:
        try:
            root = resolve_data_dir(load_config()) / ROLLING_SET
        except ConfigError as exc:
            raise _abort(str(exc)) from exc

    try:
        line = verify(root, day)
        files = sum(len(each.files) for each in walk_chain(root, day))
    except (RollingError, OSError) as exc:
        raise _abort(str(exc)) from exc

    typer.echo(f"{day} {line.sha256} files={files}")


@rolling_app.command("base")
def rolling_base(
    source: Path = typer.Option(..., "--source", help="The frozen 15-minute set to copy from, its manifest beside its files."),
    out: Path = typer.Option(..., "--out", help="The rolling set's directory, where the base files and the base line land."),
    staging: Path = typer.Option(
        ..., "--staging", help="A directory outside --out on the same filesystem, where each file is written before its rename."
    ),
) -> None:
    """Stage the set's base once: copy the twelve 15-minute files, check them against the frozen frame, write the base line."""
    from cli.data.rolling import RollingError, stage_base

    try:
        line = stage_base(source, out, staging)
    except (RollingError, OSError) as exc:
        raise _abort(str(exc)) from exc

    typer.echo(f"base {line.sha256} files={len(line.files)}")


def _day_option(option: str, text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _abort(f"{option} {text!r} is not a YYYY-MM-DD date") from exc


@rolling_app.command("extend")
def rolling_extend(
    tape_root: Path = typer.Option(..., "--tape-root", help="tape-bars' tree of daily finals and their sidecars, read only."),
    out: Path = typer.Option(..., "--out", help="The rolling set's directory, holding its base line."),
    staging: Path = typer.Option(
        ..., "--staging", help="A directory outside --out on the same filesystem, where each file is written before its rename."
    ),
    close_pairs: list[str] | None = typer.Option(
        None, "--close-pair", help="A pair the owner closes, its days holes until a final reappears; once per pair."
    ),
    from_day: str | None = typer.Option(None, "--from", help="The first day the closed pairs are holes, as YYYY-MM-DD."),
    owner_word: str | None = typer.Option(None, "--owner-word", help="The owner's word closing the pairs, recorded in each line."),
    owner_date: str | None = typer.Option(None, "--owner-date", help="The day the owner gave that word, as YYYY-MM-DD."),
) -> None:
    """Extend the set day by day from tape-bars' finals, each day's index line written after its files, and print the head.

    A day waits while a pair has no final for it and no later final past the re-scan window; a pair the owner closes is a hole
    from --from until a final of its own reappears. The four close options are given together or not at all.
    """
    from cli.data.rolling import Close, RollingError, extend

    given = {"--close-pair": close_pairs, "--from": from_day, "--owner-word": owner_word, "--owner-date": owner_date}
    missing = [option for option, value in given.items() if not value]
    if missing and len(missing) < len(given):
        raise _abort(f"a close takes --close-pair, --from, --owner-word and --owner-date together; missing {', '.join(missing)}")
    close = None
    if not missing:
        close = Close(tuple(close_pairs), _day_option("--from", from_day), owner_word, _day_option("--owner-date", owner_date))

    try:
        result = extend(tape_root, out, staging, close=close)
    except (RollingError, OSError) as exc:
        raise _abort(str(exc)) from exc

    summary = f"head={result.head.day} days_written={result.days_written} holes={result.holes}"
    typer.echo(f"{summary} ended" if result.ended else summary)
