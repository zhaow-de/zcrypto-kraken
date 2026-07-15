import asyncio
import re

import polars as pl
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import verify_manifest
from cli.liquidations.recorder import parse_force_order

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _row(*, price, qty, t_ms):
    import json

    envelope = json.dumps(
        {
            "stream": "!forceOrder@arr",
            "data": {
                "e": "forceOrder",
                "o": {"s": "BTCUSDT", "S": "SELL", "q": qty, "p": price, "ap": price, "X": "FILLED", "T": t_ms},
            },
        }
    )
    return parse_force_order(envelope)


def test_liquidations_help_lists_options():
    result = runner.invoke(app, ["liquidations", "--help"])
    assert result.exit_code == 0
    output = _ANSI_RE.sub("", result.output)
    assert "--data-dir" in output
    assert "--duration" in output


class _FakeClient:
    """Yields a 06:00 event then a 07:00 event (which finalizes hour 06), then hangs — so the
    `--duration` timeout is what stops the run, exercising finalize-on-boundary + shutdown flush."""

    def __init__(self, uri):
        self.connected = True

    async def stream(self):
        yield _row(price="100", qty="1", t_ms=1568008800000)  # 2019-09-09 06:00:00
        yield _row(price="101", qty="2", t_ms=1568012400000)  # 2019-09-09 07:00:00 -> finalizes 06
        await asyncio.Event().wait()


def test_liquidations_end_to_end_writes_segments_with_fake_client(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.liquidations.command.BinanceLiquidationClient", _FakeClient)
    data_dir = tmp_path / "does" / "not" / "exist" / "yet"
    result = runner.invoke(app, ["liquidations", "--data-dir", str(data_dir), "--duration", "1"])
    assert result.exit_code == 0, result.output

    final_06 = data_dir / "BTCUSDT" / "liquidations" / "2019" / "09" / "09" / "06.parquet"
    assert final_06.exists()
    assert verify_manifest(final_06) is True
    assert pl.read_parquet(final_06)["price"].to_list() == [100.0]


class _CrashingFakeClient:
    """`stream()` blows up mid-run — the supervisor (Docker `restart: unless-stopped`) is what
    restarts the recorder, so the crash must propagate, not be swallowed by the `--duration` path."""

    def __init__(self, uri):
        self.connected = True

    async def stream(self):
        yield _row(price="100", qty="1", t_ms=1568008800000)
        raise RuntimeError("boom")


def test_liquidations_propagates_consumer_crash_even_with_duration_set(tmp_path, monkeypatch):
    monkeypatch.setattr("cli.liquidations.command.BinanceLiquidationClient", _CrashingFakeClient)
    result = runner.invoke(app, ["liquidations", "--data-dir", str(tmp_path), "--duration", "5"])
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
