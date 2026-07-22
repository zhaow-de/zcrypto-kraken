import os
from importlib.metadata import version
from pathlib import Path
from typing import Optional

import typer

from cli.archive.command import archive_app
from cli.capture.command import capture
from cli.data.command import data_app
from cli.engine.command import engine_app
from cli.liquidations.coinalyze import liquidations_poll
from cli.liquidations.command import liquidations
from cli.logging import ShipConfig, configure, get_logger
from cli.panel.command import panel_app

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.command(name="capture")(capture)
app.command(name="liquidations")(liquidations)
app.command(name="liquidations-poll")(liquidations_poll)
app.add_typer(engine_app, name="engine")
app.add_typer(archive_app, name="archive")
app.add_typer(data_app, name="data")
app.add_typer(panel_app, name="panel")

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_LOKI_ENV_NAMES = (
    "ZCRYPTO_LOKI_URL",
    "ZCRYPTO_LOKI_USERNAME",
    "ZCRYPTO_LOKI_PASSWORD",
    "ZCRYPTO_LOG_HOST",
    "ZCRYPTO_LOG_SERVICE",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"zcrypto v{version('zcrypto')}")
        raise typer.Exit()


def _log_level_callback(ctx: typer.Context, param: typer.CallbackParam, value: str) -> str:
    upper = value.upper()
    if upper not in _VALID_LEVELS:
        raise typer.BadParameter(f"must be one of {', '.join(sorted(_VALID_LEVELS))}, got {value!r}")
    return upper


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version_: bool = typer.Option(
        None,
        "-v",
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the application version and exit.",
    ),
    log: Optional[Path] = typer.Option(
        None,
        "-l",
        "--log",
        help="Append JSONL logs to this file. If unset, plain-text logs go to stdout.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        callback=_log_level_callback,
        # Eager so `--log-level TRACE --version` errors at parse time instead of being swallowed by --version's eager exit.
        is_eager=True,
        case_sensitive=False,
        help="Log threshold. One of DEBUG, INFO, WARNING, ERROR.",
    ),
    ship_logs: bool = typer.Option(
        False,
        "--ship-logs",
        help=f"Also ship logs to Grafana Cloud Loki, in addition to stdout/file. Requires {', '.join(_LOKI_ENV_NAMES)}.",
    ),
) -> None:
    ship: Optional[ShipConfig] = None
    if ship_logs:
        missing = [n for n in _LOKI_ENV_NAMES if not os.environ.get(n)]
        if missing:
            raise typer.BadParameter(f"--ship-logs requires env vars: {', '.join(missing)}")
        ship = ShipConfig(
            url=os.environ["ZCRYPTO_LOKI_URL"],
            username=os.environ["ZCRYPTO_LOKI_USERNAME"],
            password=os.environ["ZCRYPTO_LOKI_PASSWORD"],
            host=os.environ["ZCRYPTO_LOG_HOST"],
            service=os.environ["ZCRYPTO_LOG_SERVICE"],
        )

    configure(log, log_level, ship)

    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def run() -> None:
    """Console-script entry point (`zcrypto`), and the target of `python -m cli`.

    Exists so an unhandled exception is LOGGED before the process dies. Typer installs its own
    `sys.excepthook`, which renders a Rich traceback straight to stderr without ever going through
    `logging` -- so a crash carries no timestamp and no level, Alloy cannot label it at ingest
    (infra/nas/config.alloy), and the level-based alerting is blind to the single worst failure of
    the unbackfillable archive path: the pull loop dying. See T0041.

    Catches `Exception`, not `BaseException`: click already turns its own errors (usage, abort,
    `typer.Exit`) into `SystemExit`, which must pass through untouched, and a KeyboardInterrupt is
    an operator action rather than a fault.
    """
    try:
        app()
    except Exception:
        get_logger("main").exception("unhandled exception -- aborting")
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
