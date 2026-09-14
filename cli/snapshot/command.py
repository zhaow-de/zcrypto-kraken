"""The `zcrypto snapshot` Typer sub-app: the reference-data sweep's automated half -- wiring and exit codes only."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import typer

from cli.logging import get_logger
from cli.snapshot.assetpairs import _COMMON_TO_KRAKEN, CANDIDATE_SYMBOLS
from cli.snapshot.delistings import scan_delistings
from cli.snapshot.errors import SnapshotError
from cli.snapshot.fetch import fetch_public
from cli.snapshot.register import build_snapshot, render_markdown, sweep_refusals

logger = get_logger("snapshot.command")

_MAINTENANCE_FEED = "https://status.kraken.com/api/v2/scheduled-maintenances.json"
_FEED_TIMEOUT_SECONDS = 30

snapshot_app = typer.Typer(
    no_args_is_help=True,
    help="Kraken reference-data snapshots: re-fetch the public endpoints and check the candidate basket's identity.",
)


def _abort(message: str) -> typer.Exit:
    """Usage: `raise _abort(...)` -- it RETURNS the exception."""
    logger.error(message)
    return typer.Exit(code=1)


def _fetch_maintenance_feed() -> dict:
    try:
        with urllib.request.urlopen(_MAINTENANCE_FEED, timeout=_FEED_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"transport error fetching the maintenance feed: {exc}") from exc


def _selected_assets(symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Every asset a candidate symbol names, in the common spelling and, where the venue spells it differently, in Kraken's."""
    common = {code for symbol in symbols for code in symbol.split("/")}
    kraken = {_COMMON_TO_KRAKEN[code] for code in common if code in _COMMON_TO_KRAKEN}
    return tuple(sorted(common | kraken))


@snapshot_app.command()
def sweep(
    snapshots_dir: Path = typer.Option(
        Path("data/snapshots"),
        "--snapshots-dir",
        help="Where the raw snapshot is archived, as kraken-refdata-<UTC stamp>.json.",
    ),
) -> None:
    """Re-fetch the public endpoints, archive the raw snapshot, render the register's tables, and refuse on an identity change.

    Every fetch precedes the write, so a transport failure leaves no snapshot behind.

    An announced delisting is printed with its own dates and does not fail the run; a refusal fails it.
    """
    try:
        assetpairs, assets, feed = fetch_public("AssetPairs"), fetch_public("Assets"), _fetch_maintenance_feed()
    except SnapshotError as exc:
        raise _abort(str(exc)) from exc

    now = datetime.now(UTC).replace(microsecond=0)
    snapshot = build_snapshot(assetpairs, assets, list(CANDIDATE_SYMBOLS), now.isoformat())
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / f"kraken-refdata-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))

    refusals = sweep_refusals(snapshot)
    announced = scan_delistings(feed, _selected_assets(CANDIDATE_SYMBOLS))

    typer.echo(f"JUDGING SNAPSHOT: {snapshot['fetched_at']} ({path})")
    typer.echo("REFUSALS: none" if not refusals else "REFUSALS:")
    for reason in refusals:
        typer.echo(f"  {reason}")
    typer.echo("ANNOUNCED DELISTINGS: none" if not announced else "ANNOUNCED DELISTINGS:")
    for hit in announced:
        typer.echo(
            f"  {hit['asset']}: {hit['name']} -- scheduled_for {hit['scheduled_for'] or '-'}, "
            f"created_at {hit['created_at'] or '-'}, status {hit['status'] or '-'}"
        )
    typer.echo("")
    typer.echo(render_markdown(snapshot))
    if refusals:
        raise typer.Exit(code=1)
