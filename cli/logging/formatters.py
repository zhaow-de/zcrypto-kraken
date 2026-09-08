from __future__ import annotations

import json
import logging
import time

_OMIT_EXTRA_KEYS = set(logging.LogRecord("x", logging.INFO, "x", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}


def _extract_extra(record: logging.LogRecord) -> dict:
    return {k: v for k, v in record.__dict__.items() if k not in _OMIT_EXTRA_KEYS and not k.startswith("_")}


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ms = int(record.msecs) % 1000
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{ms:03d}Z"
        payload: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        extra = _extract_extra(record)
        if extra:
            payload["extra"] = extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class PlainTextFormatter(logging.Formatter):
    # UTC, matching JsonLineFormatter's time.gmtime; the stdlib default localtime would make console and file logs disagree.
    converter = time.gmtime

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] - %(message)s",
        )

    def formatMessage(self, record: logging.LogRecord) -> str:
        # In formatMessage rather than format, so the pairs land on the message line, before any traceback.
        line = super().formatMessage(record)
        extra = _extract_extra(record)
        if extra:
            line += " " + " ".join(f"{k}={v}" for k, v in extra.items())
        return line
