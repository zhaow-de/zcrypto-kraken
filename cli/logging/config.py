from __future__ import annotations

import logging
import sys
from pathlib import Path

from cli.logging.formatters import JsonLineFormatter, PlainTextFormatter
from cli.logging.ship import LokiShipHandler, ShipConfig

_TARGET_LOGGERS = ("zcrypto",)


def configure(path: Path | None, level: str, ship: ShipConfig | None = None) -> None:
    """Configure the project ``zcrypto`` logger. Idempotent across repeated calls.

    When `ship` is given, a `LokiShipHandler` is attached IN ADDITION to the console/file
    handler -- never replacing it (log shipping is additive to stdout/file, spec 00068 T3).
    """
    numeric = logging.getLevelNamesMapping().get(level)
    if numeric is None:
        raise ValueError(f"invalid log level: {level!r}")

    handler: logging.Handler
    if path is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(PlainTextFormatter())
    else:
        # delay=True: open (create) the file only on the first emitted record, so a bare
        # `-l PATH` with no log-emitting subcommand doesn't leave an empty file behind.
        handler = logging.FileHandler(path, mode="a", encoding="utf-8", delay=True)
        handler.setFormatter(JsonLineFormatter())
    handler.setLevel(numeric)
    handler._zcrypto_owned = True  # type: ignore[attr-defined]

    handlers = [handler]
    if ship is not None:
        ship_handler = LokiShipHandler(ship)
        ship_handler.setLevel(numeric)
        ship_handler._zcrypto_owned = True  # type: ignore[attr-defined]
        handlers.append(ship_handler)

    for name in _TARGET_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            if getattr(h, "_zcrypto_owned", False):
                lg.removeHandler(h)
                try:
                    h.close()
                except OSError:
                    pass
        for h in handlers:
            lg.addHandler(h)
        lg.setLevel(numeric)
        lg.propagate = False
