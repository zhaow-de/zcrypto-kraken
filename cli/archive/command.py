"""The `zcrypto archive` Typer sub-app (spec 00048 Role A): pull a source tree via rsync-over-ssh
and hash-verify it against its manifest sidecars, so a transport failure and a hash mismatch are
distinguished exit codes -- neither is ever silently archived as good."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import typer

from cli.archive.pull import pull_lag_seconds, verify_tree
from cli.logging import get_logger

logger = get_logger("archive.command")

archive_app = typer.Typer(
    no_args_is_help=True,
    help="The NAS pull/archive tier (Role A): rsync a source tree, then hash-verify it.",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _run_rsync(source: str, dest: Path) -> int:
    ssh_key = os.environ["ARCHIVE_SSH_KEY"]
    ssh_port = os.environ.get("ARCHIVE_SSH_PORT") or "10022"  # empty-string-safe (compose may pass "")
    ssh_command = f"ssh -i {ssh_key} -p {ssh_port} -o StrictHostKeyChecking=accept-new"
    argv = ["rsync", "-a", "-e", ssh_command, source, str(dest)]
    return subprocess.run(argv).returncode


@archive_app.command()
def pull(
    source: str = typer.Argument(..., help="rsync source spec, e.g. deploy@host:/var/lib/zcrypto-capture/segments/"),
    dest: Path = typer.Argument(..., help="Local destination directory to rsync into and verify."),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Hash-verify pulled segments against their .sha256 sidecars (default). Use --no-verify "
        "for archive-only sources like the engine journal, which has no sidecars.",
    ),
) -> None:
    """Pull `source` into `dest` via rsync-over-ssh, then hash-verify every segment against its
    manifest sidecar. Exits 2 on a transport failure (partial pull, never verified as authoritative),
    1 on a hash mismatch, 0 when every checked segment verifies."""
    returncode = _run_rsync(source, dest)
    if returncode != 0:
        logger.error("archive pull: rsync failed source=%s dest=%s returncode=%s", source, dest, returncode)
        raise typer.Exit(2)

    if not verify:
        logger.info("archive pull complete (no verify) source=%s dest=%s", source, dest)
        return

    result = verify_tree(dest, now=_utc_now())
    lag_s = pull_lag_seconds(result, now=_utc_now())
    logger.info(
        "pull complete source=%s checked=%d ok=%d failed=%d lag_s=%s",
        source,
        result.checked,
        result.ok,
        len(result.failed),
        lag_s,
    )
    if result.failed:
        for path in result.failed:
            logger.error("archive pull: verify failed path=%s", path)
        raise typer.Exit(1)
