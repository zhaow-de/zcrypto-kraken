import logging
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.logging.ship import LokiShipHandler, ShipConfig

runner = CliRunner()

# RFC 5737 TEST-NET-1: guaranteed non-routable. Also moot here -- no subcommand emits a log
# record in these tests, so the ring stays empty and the worker never attempts a post.
_LOKI_ENV = {
    "ZCRYPTO_LOKI_URL": "http://192.0.2.1:1/loki/api/v1/push",
    "ZCRYPTO_LOKI_USERNAME": "u",
    "ZCRYPTO_LOKI_PASSWORD": "p",
    "ZCRYPTO_LOG_HOST": "test-host",
    "ZCRYPTO_LOG_SERVICE": "test-service",
}


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


def test_ship_logs_off_leaves_handler_set_unchanged():
    from cli.logging.formatters import PlainTextFormatter

    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output

    own = [h for h in logging.getLogger("zcrypto").handlers if getattr(h, "_zcrypto_owned", False)]
    assert len(own) == 1
    assert isinstance(own[0], logging.StreamHandler) and not isinstance(own[0], logging.FileHandler)
    assert isinstance(own[0].formatter, PlainTextFormatter)


def test_ship_logs_on_with_full_env_attaches_ship_handler_alongside_console(monkeypatch):
    from cli.logging.formatters import PlainTextFormatter

    for name, value in _LOKI_ENV.items():
        monkeypatch.setenv(name, value)

    result = runner.invoke(app, ["--ship-logs"])
    assert result.exit_code == 0, result.output

    own = [h for h in logging.getLogger("zcrypto").handlers if getattr(h, "_zcrypto_owned", False)]
    assert len(own) == 2
    ship = [h for h in own if isinstance(h, LokiShipHandler)]
    console = [h for h in own if h not in ship]
    assert len(ship) == 1
    assert len(console) == 1
    assert isinstance(console[0], logging.StreamHandler)
    assert isinstance(console[0].formatter, PlainTextFormatter)
    assert console[0].level == logging.INFO  # shipping must not mute the local ground truth (D2)

    assert ship[0]._cfg == ShipConfig(
        url=_LOKI_ENV["ZCRYPTO_LOKI_URL"],
        username=_LOKI_ENV["ZCRYPTO_LOKI_USERNAME"],
        password=_LOKI_ENV["ZCRYPTO_LOKI_PASSWORD"],
        host=_LOKI_ENV["ZCRYPTO_LOG_HOST"],
        service=_LOKI_ENV["ZCRYPTO_LOG_SERVICE"],
    )


def test_ship_logs_treats_an_empty_env_var_as_missing(monkeypatch):
    for name, value in _LOKI_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ZCRYPTO_LOKI_URL", "")

    result = runner.invoke(app, ["--ship-logs"])
    assert result.exit_code == 2, result.output
    assert "ZCRYPTO_LOKI_URL" in result.output


def test_ship_logs_missing_one_env_var_errors_naming_it(monkeypatch):
    for name, value in _LOKI_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ZCRYPTO_LOKI_URL", raising=False)

    result = runner.invoke(app, ["--ship-logs"])
    assert result.exit_code == 2, result.output
    assert "ZCRYPTO_LOKI_URL" in result.output


def test_ship_logs_missing_two_env_vars_errors_naming_both(monkeypatch):
    # A fix-one-rerun-find-another loop is a bad deploy experience -- every missing var
    # must be named in the one error, not just the first found.
    for name, value in _LOKI_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ZCRYPTO_LOKI_URL", raising=False)
    monkeypatch.delenv("ZCRYPTO_LOG_SERVICE", raising=False)

    result = runner.invoke(app, ["--ship-logs"])
    assert result.exit_code == 2, result.output
    assert "ZCRYPTO_LOKI_URL" in result.output
    assert "ZCRYPTO_LOG_SERVICE" in result.output
