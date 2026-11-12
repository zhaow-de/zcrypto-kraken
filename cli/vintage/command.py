"""The `zcrypto vintage` Typer sub-app."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from cli.logging import get_logger
from cli.vintage import verify as verify_mod

log = get_logger("vintage.verify")

vintage_app = typer.Typer(help="The vintage record: every byte the free on-chain and sentiment sources serve, twice a day.")


@vintage_app.command("verify")
def verify_cmd(
    root: Path = typer.Option(..., "--root", help="A copy of the record: the directory holding <year>/<month>/<day>/<stamp>/."),
    custody: bool = typer.Option(
        False,
        "--custody",
        help="Read the copy as the only custody of an acknowledged fork's tick off the chain, as every read of the NAS copy does.",
    ),
    newest: Optional[int] = typer.Option(
        None,
        "--newest",
        min=0,
        metavar="N",
        help="Re-hash the bodies of the newest N ticks along the chain and of the slice alone; takes --slice and --slices.",
    ),
    slice_: Optional[int] = typer.Option(
        None, "--slice", min=0, metavar="K", help="The slice: every tick whose position in stamp order is K modulo M."
    ),
    slices: Optional[int] = typer.Option(None, "--slices", min=1, metavar="M", help="M, the count of slices."),
) -> None:
    """Verify a copy of the record: its chain, its bodies and the files its ticks hold; exit 0 clean, 1 otherwise."""
    if (newest, slice_, slices).count(None) not in (0, 3):
        raise typer.BadParameter("--newest, --slice and --slices go together")
    if slices is not None and slice_ >= slices:
        raise typer.BadParameter("--slice must be below --slices")
    result = verify_mod.verify(root, newest=newest, slice_=slice_, slices=slices, custody=custody)
    for finding in result.breaks:
        log.error("vintage verify %s path=%s: %s", finding.kind, finding.path, finding.detail)
    for finding in result.notes:
        log.info("vintage verify %s path=%s: %s", finding.kind, finding.path, finding.detail)
    log.log(
        logging.ERROR if result.breaks else logging.INFO,
        "vintage verify complete ticks=%d head=%s head_tick_json_sha256=%s bodies_hashed=%d breaks=%d",
        result.ticks,
        result.head or "none",
        result.head_tick_json_sha256 or "none",
        result.bodies_hashed,
        len(result.breaks),
    )
    if result.breaks:
        raise typer.Exit(code=1)
