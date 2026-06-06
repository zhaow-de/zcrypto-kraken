import json
import logging
from pathlib import Path

import pytest

from cli.logging.config import configure


@pytest.fixture(autouse=True)
def _reset_loggers():
    yield
    for name in ("zcrypto",):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        lg.propagate = True
        lg.setLevel(logging.NOTSET)


def _project_handler(logger: logging.Logger) -> logging.Handler:
    own = [h for h in logger.handlers if getattr(h, "_zcrypto_owned", False)]
    assert len(own) == 1, f"expected exactly one project handler, found {own}"
    return own[0]


def test_console_mode_attaches_stream_handler_with_plain_formatter():
    from cli.logging.formatters import PlainTextFormatter

    configure(None, "INFO")
    for name in ("zcrypto",):
        lg = logging.getLogger(name)
        h = _project_handler(lg)
        assert isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        assert isinstance(h.formatter, PlainTextFormatter)
        assert lg.level == logging.INFO
        assert lg.propagate is False


def test_file_mode_attaches_file_handler_with_json_formatter(tmp_path: Path):
    from cli.logging.formatters import JsonLineFormatter

    log = tmp_path / "z.log"
    configure(log, "DEBUG")
    for name in ("zcrypto",):
        lg = logging.getLogger(name)
        h = _project_handler(lg)
        assert isinstance(h, logging.FileHandler)
        assert Path(h.baseFilename) == log
        assert isinstance(h.formatter, JsonLineFormatter)
        assert lg.level == logging.DEBUG


def test_configure_is_idempotent(tmp_path: Path):
    log = tmp_path / "z.log"
    configure(log, "INFO")
    configure(log, "INFO")
    for name in ("zcrypto",):
        assert len([h for h in logging.getLogger(name).handlers if getattr(h, "_zcrypto_owned", False)]) == 1


def test_invalid_level_raises():
    with pytest.raises(ValueError, match="invalid log level"):
        configure(None, "BADLEVEL")


def test_file_mode_writes_jsonl_end_to_end(tmp_path: Path):
    log = tmp_path / "z.log"
    configure(log, "INFO")
    logging.getLogger("zcrypto.example").info("hello %s", "world")
    for h in logging.getLogger("zcrypto").handlers:
        h.flush()
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert lines, "no log lines written"
    obj = json.loads(lines[-1])
    assert obj["logger"] == "zcrypto.example"
    assert obj["message"] == "hello world"
    assert obj["file"] == "test_logging_config.py"


def test_configure_swallows_owned_handler_close_error():
    # A prior project-owned handler whose close() fails (e.g. a dead fd raising OSError) must not
    # break reconfiguration: configure() removes it, swallows the error, and attaches the new handler.
    lg = logging.getLogger("zcrypto")

    class _CloseRaises(logging.Handler):
        def close(self) -> None:
            raise OSError("cannot close")

    bad = _CloseRaises()
    bad._zcrypto_owned = True  # type: ignore[attr-defined]
    lg.addHandler(bad)

    configure(None, "INFO")  # must not raise

    own = [h for h in lg.handlers if getattr(h, "_zcrypto_owned", False)]
    assert len(own) == 1
    assert own[0] is not bad
