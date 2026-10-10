"""The `zcrypto tax` Typer sub-app: wiring and exit codes only."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from cli.tax.blockpit import transform
from cli.tax.errors import Refused, TaxExportError

logger = logging.getLogger("zcrypto.tax.command")

tax_app = typer.Typer(
    no_args_is_help=True,
    help="Tax bookkeeping: Kraken's ledger and trades exports turned into the tax tool's import file.",
)


@tax_app.command()
def blockpit(
    ledgers: Path = typer.Option(..., "--ledgers", help="Kraken's ledger CSV export for the window."),
    trades: Path = typer.Option(..., "--trades", help="Kraken's trades CSV export for the same window."),
    out: Path = typer.Option(
        ..., "--out", help="The import file to write; its provenance is written beside it as <out>.provenance.json."
    ),
    after: Optional[Path] = typer.Option(
        None,
        "--after",
        help="The window before's provenance file. Required on every window but the first, whose opening balances must all be zero.",
    ),
) -> None:
    """Map one window of Kraken's ledger and trades exports onto Blockpit's manual-import rows, the provenance beside them.

    A row it cannot map or a check that fails refuses the run: every refusal is printed and nothing is written.
    Neither output file may exist beforehand.
    """
    try:
        written = transform(ledgers, trades, out, after)
    except Refused as exc:
        for refusal in exc.refusals:
            typer.echo(refusal.line())
        raise typer.Exit(code=1) from exc
    except (TaxExportError, OSError) as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {written.rows} rows to {written.out} (sha256 {written.sha256})")
    typer.echo(f"provenance {written.provenance} (sha256 {written.provenance_sha256})")
    for label, count in sorted(written.label_rows.items()):
        typer.echo(f"  {label}: {count} rows")
    typer.echo("closing balances: " + ", ".join(f"{asset} {value}" for asset, value in written.closing.items()))
