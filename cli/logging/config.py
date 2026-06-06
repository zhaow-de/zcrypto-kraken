from __future__ import annotations

import logging
import sys
from pathlib import Path

from cli.logging.formatters import JsonLineFormatter, PlainTextFormatter

_TARGET_LOGGERS = ("zcrypto",)


def configure(path: Path | None, level: str) -> None:
    """Configure the project ``zcrypto`` logger. Idempotent across repeated calls."""
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

    for name in _TARGET_LOGGERS:
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            if getattr(h, "_zcrypto_owned", False):
                lg.removeHandler(h)
                try:
                    h.close()
                except OSError:
                    pass
        lg.addHandler(handler)
        lg.setLevel(numeric)
        lg.propagate = False
