"""A logger's messages during a block, read off a handler on that logger rather than through
pytest's caplog: `cli.logging.configure` turns the `zcrypto` logger's propagation off, so what a
record does at the root handlers depends on which tests ran first."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@contextmanager
def messages_of(logger: logging.Logger) -> Iterator[list[str]]:
    handler = _Lines()
    logger.addHandler(handler)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
