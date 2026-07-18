"""The `zcrypto data` Typer sub-app (spec 00056): the hot-cluster dataset exchange -- fetch the
replicated working set from the NAS hot/ hub, push what this node authored back to it. Wiring and
exit codes only -- the rsync mechanics live in `cli.data.sync`."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from cli.config import ConfigError, load_config, resolve_data_dir, resolve_hot_dir, resolve_push_dest
from cli.data.errors import DataSyncError
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
    hot_dir: Optional[Path] = typer.Option(None, "--hot-dir", help="Override the configured [zcrypto.data].hot_dir."),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip manifest hash verification of newly fetched files."),
) -> None:
    """Additively mirror the NAS hot/ hub into the local data root."""
    try:
        cfg = load_config()
        resolved_hot_dir = resolve_hot_dir(hot_dir, cfg)
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
