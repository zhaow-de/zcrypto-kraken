"""The `zcrypto tick` Typer sub-app: materialize tape-bars from the healed trade archive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer

from cli.logging import get_logger
from cli.tick.errors import TickError
from cli.tick.materialize import RESCAN_DAYS, TAPE_SETTLE, materialize

logger = get_logger("tick.command")

tick_app = typer.Typer(help="Bars derived from the captured trade tape.")


@tick_app.command("materialize")
def materialize_cmd(
    primary_root: Path = typer.Argument(..., help="The primary (raw) canonical trade archive."),
    out_root: Path = typer.Argument(..., help="Dataset root the daily finals are published into."),
    reconciled_root: Path = typer.Option(
        ...,
        "--reconciled-root",
        help="The healed overlay, read first. REQUIRED: an optional overlay is one forgotten flag away from publishing the un-healed stream.",
    ),
    settle_hours: int = typer.Option(
        int(TAPE_SETTLE.total_seconds() // 3600),
        "--settle-hours",
        help="Hours past a day's end before it may be published.",
    ),
    rescan_days: int = typer.Option(
        RESCAN_DAYS,
        "--rescan-days",
        help="Trailing settled days re-attempted, so a late-healed day is still picked up.",
    ),
) -> None:
    """Publish the settled, heal-complete days of 15m tape-bars that have no final yet.

    `days_unsettled` and `days_unhealed` are deferrals, not failures; `days_gap` is unpublished days the sweep did not reach.
    """
    try:
        result = materialize(
            primary_root,
            reconciled_root,
            out_root,
            now=datetime.now(UTC),
            settle=timedelta(hours=settle_hours),
            rescan_days=rescan_days,
        )
    except TickError as exc:
        # A refusal is a decision, not a fault: one logged line and exit 1, the shape
        # `cli/panel/command.py::_abort` uses. Otherwise the operator reads a traceback labelled an
        # unhandled exception and finds the reason only at its foot.
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"days_written={result.days_written} days_skipped={result.days_skipped} "
        f"days_unsettled={result.days_unsettled} days_unhealed={result.days_unhealed} "
        f"days_gap={result.days_gap} "
        f"rows={result.rows} errors={len(result.errors)}"
    )
    for pair, day, message in result.errors:
        typer.echo(f"  ERROR {pair} {day.isoformat()}: {message}", err=True)
    if result.errors:
        raise typer.Exit(code=1)
