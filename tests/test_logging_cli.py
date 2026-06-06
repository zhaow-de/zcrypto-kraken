import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_loggers():
    yield
    for name in ("zcrypto",):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            try:
                h.close()
            except OSError:
                pass
        lg.propagate = True
        lg.setLevel(logging.NOTSET)


def test_version_still_works_without_log_flags():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "zcrypto v" in result.output


def test_log_flag_routes_logging_to_a_jsonl_file_handler(tmp_path: Path):
    log = tmp_path / "z.log"
    # No subcommand emits logs yet, so this checks the flag wiring, not output: `-l PATH`
    # must route configure() to a FileHandler bound to PATH (vs the default stdout
    # StreamHandler), while help still goes to stdout. Asserting the handler — not that the
    # file exists — keeps this robust to a future delay=True on the handler.
    result = runner.invoke(app, ["-l", str(log)])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.stdout

    own = [h for h in logging.getLogger("zcrypto").handlers if getattr(h, "_zcrypto_owned", False)]
    assert len(own) == 1, own
    # FileHandler is a StreamHandler subclass, so this also fails for the console-mode default.
    assert isinstance(own[0], logging.FileHandler)
    assert Path(own[0].baseFilename) == log


def test_invalid_log_level_errors():
    result = runner.invoke(app, ["--log-level", "TRACE", "--version"])
    assert result.exit_code != 0
