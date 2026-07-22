import asyncio
import logging
import socket
import urllib.request
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner
from websockets.exceptions import ConnectionClosedError

from cli.__main__ import app
from cli.capture import command as cmd
from cli.capture.book import OrderBook
from cli.capture.command import CaptureCollector
from cli.capture.gap_monitor import DiskWatermark, GapMonitor
from cli.capture.ws_client import CaptureClient
from cli.obs.metrics import METRICS_PORT_ENV_VAR

runner = CliRunner()


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2.0) as resp:
        return resp.read().decode()


class _FakeUsage:
    def __init__(self, free: int) -> None:
        self.free = free


class _FakeWriter:
    """A minimal duck-typed stand-in for `SegmentWriter`: `CaptureCollector` reads only these four
    plain-int attributes, never a real writer's disk-backed internals."""

    def __init__(self) -> None:
        self.segments_written = 0
        self.segment_bytes = 0
        self.rows_held = 0
        self.rows_quarantined = 0


def _families(collector: CaptureCollector) -> dict:
    """Sample-name -> the family carrying it. Keyed by the SAMPLE name (not `family.name`):
    `CounterMetricFamily` strips a trailing `_total` from `.name` (it re-adds it per sample), so a
    lookup by the exposed series name -- what a scrape and this test both actually care about --
    has to go through `samples`, not the family object's own (suffix-stripped) name."""
    result: dict = {}
    for family in collector.collect():
        for sample in family.samples:
            result[sample.name] = family
    return result


class _FakeClient:
    """Yields one correctly-in-sync book snapshot + one trade, then hangs -- the same end-to-end
    wiring fixture `tests/test_capture_command.py` uses, duplicated locally (small, self-contained,
    one file's worth of test fixtures) rather than reached into another test module."""

    last_instance = None

    def __init__(self, pairs, depth):
        self.pairs = pairs
        self.depth = depth
        # Mirrors the real CaptureClient's additive counters (spec 00069 T3) so CaptureCollector's
        # duck-typed reads succeed against this stand-in exactly as they would against the real class.
        self.reconnects_total = 0
        self.resubscribes_total = 0
        _FakeClient.last_instance = self

    async def stream(self):
        book = OrderBook("BTC/EUR", depth=100)
        book.bids = {Decimal("100.0"): Decimal("1.0")}
        book.asks = {Decimal("101.0"): Decimal("1.0")}
        checksum = book.checksum()
        yield {
            "channel": "book",
            "type": "snapshot",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "bids": [{"price": 100.0, "qty": 1.0}],
                    "asks": [{"price": 101.0, "qty": 1.0}],
                    "checksum": checksum,
                    "timestamp": "2026-07-08T14:00:00.000000Z",
                }
            ],
        }
        yield {
            "channel": "trade",
            "type": "update",
            "data": [
                {
                    "symbol": "BTC/EUR",
                    "side": "buy",
                    "price": 100.5,
                    "qty": 0.01,
                    "ord_type": "market",
                    "trade_id": 1,
                    "timestamp": "2026-07-08T14:00:01.000000Z",
                }
            ],
        }
        await asyncio.Event().wait()  # hang until cancelled by the --duration timeout

    async def resubscribe_book(self, pair):
        pass


# --- CaptureCollector: reads a snapshot of live objects, never raises into the caller ------------


def test_collector_families_reflect_client_and_writer_state():
    client = CaptureClient(["BTC/EUR"], 100)
    client.reconnects_total = 3
    client.resubscribes_total = 2
    writer = _FakeWriter()
    writer.segments_written = 5
    writer.segment_bytes = 12_345
    writer.rows_held = 7
    writer.rows_quarantined = 4
    collector = CaptureCollector(
        ["BTC/EUR"],
        client,
        {"BTC/EUR": OrderBook("BTC/EUR", 100)},
        {"BTC/EUR": writer},
        {},
        GapMonitor(),
        DiskWatermark(Path("/tmp")),
    )
    families = _families(collector)
    assert families["zcrypto_capture_reconnects_total"].samples[0].value == 3
    assert families["zcrypto_capture_resubscribes_total"].samples[0].value == 2
    assert families["zcrypto_capture_segments_written_total"].samples[0].value == 5
    assert families["zcrypto_capture_segment_bytes_total"].samples[0].value == 12_345
    assert families["zcrypto_capture_rows_held_total"].samples[0].value == 7
    assert families["zcrypto_capture_rows_quarantined_total"].samples[0].value == 4


def test_collector_sums_across_every_writer_book_and_trade():
    client = CaptureClient(["BTC/EUR"], 100)
    book_writer, trade_writer = _FakeWriter(), _FakeWriter()
    book_writer.segments_written, trade_writer.segments_written = 2, 3
    collector = CaptureCollector(
        ["BTC/EUR"], client, {}, {"BTC/EUR": book_writer}, {"BTC/EUR": trade_writer}, GapMonitor(), DiskWatermark(Path("/tmp"))
    )
    assert _families(collector)["zcrypto_capture_segments_written_total"].samples[0].value == 5


def test_gap_seconds_family_carries_one_labeled_series_per_pair():
    client = CaptureClient(["BTC/EUR"], 100)
    monitor = GapMonitor()
    collector = CaptureCollector(["BTC/EUR", "ETH/EUR"], client, {}, {}, {}, monitor, DiskWatermark(Path("/tmp")))
    family = _families(collector)["zcrypto_capture_gap_seconds_total"]
    labeled_pairs = {sample.labels["pair"] for sample in family.samples}
    assert labeled_pairs == {"BTC/EUR", "ETH/EUR"}


def test_desynced_gauge_reflects_book_state():
    client = CaptureClient(["BTC/EUR"], 100)
    book = OrderBook("BTC/EUR", 100)
    book.desynced = True
    collector = CaptureCollector(["BTC/EUR"], client, {"BTC/EUR": book}, {}, {}, GapMonitor(), DiskWatermark(Path("/tmp")))
    family = _families(collector)["zcrypto_capture_book_desynced"]
    assert family.samples[0].value == 1.0

    book.desynced = False
    family = _families(collector)["zcrypto_capture_book_desynced"]
    assert family.samples[0].value == 0.0


def test_watermark_gauge_flips_from_0_to_1_on_breach():
    state = {"free": 10_000}
    watermark = DiskWatermark(Path("/tmp"), min_free_bytes=1024, usage_fn=lambda p: _FakeUsage(free=state["free"]))
    watermark.check()  # healthy
    client = CaptureClient(["BTC/EUR"], 100)
    collector = CaptureCollector(["BTC/EUR"], client, {}, {}, {}, GapMonitor(), watermark)
    assert _families(collector)["zcrypto_capture_disk_watermark_breached"].samples[0].value == 0.0

    state["free"] = 10  # below min_free_bytes
    watermark.check()
    assert _families(collector)["zcrypto_capture_disk_watermark_breached"].samples[0].value == 1.0


def test_collector_collect_stays_safe_when_a_writer_mutates_between_yields():
    # `collect()` is a generator: its body only runs up to the next `yield` when resumed. A fixture
    # mutated in the gap between two `next()` calls must never raise and must never leave a family
    # straddling old and new values -- each already-yielded family is a value already captured, and
    # each not-yet-yielded family reads whatever is current when its own turn comes.
    client = CaptureClient(["BTC/EUR"], 100)
    writer = _FakeWriter()
    collector = CaptureCollector(["BTC/EUR"], client, {}, {"BTC/EUR": writer}, {}, GapMonitor(), DiskWatermark(Path("/tmp")))
    gen = collector.collect()
    next(gen)  # reconnects_total, already yielded
    writer.segments_written += 5  # mutate the live object mid-scrape
    writer.rows_held += 3
    remaining = list(gen)  # must not raise
    families = {sample.name: family for family in remaining for sample in family.samples}
    assert families["zcrypto_capture_segments_written_total"].samples[0].value == 5
    assert families["zcrypto_capture_rows_held_total"].samples[0].value == 3


# --- ws_client additive counters -----------------------------------------------------------------


class _FakeConnection:
    def __init__(self, messages, *, raise_at_end=False):
        self.sent: list[str] = []
        self._messages = messages
        self._raise_at_end = raise_at_end

    async def send(self, data):
        self.sent.append(data)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for m in self._messages:
            yield m
        if self._raise_at_end:
            raise ConnectionClosedError(None, None)


def _connect_fn_returning(*connections):
    remaining = list(connections)

    def connect_fn(uri):
        return remaining.pop(0)

    return connect_fn


def test_client_reconnects_total_increments_once_per_reconnect():
    async def run():
        conn1 = _FakeConnection(['{"channel": "heartbeat"}'], raise_at_end=True)
        conn2 = _FakeConnection(['{"channel": "heartbeat"}'])
        client = CaptureClient(
            ["BTC/EUR"], 100, uri="wss://fake", connect_fn=_connect_fn_returning(conn1, conn2), sleep_fn=lambda d: asyncio.sleep(0)
        )
        assert client.reconnects_total == 0
        results = []
        async for msg in client.stream():
            results.append(msg)
            if len(results) == 2:
                break
        assert client.reconnects_total == 1  # exactly one reconnect happened

    asyncio.run(run())


def test_client_resubscribes_total_increments_on_resubscribe_book():
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=_connect_fn_returning(conn), sleep_fn=asyncio.sleep)
        async for _ in client.stream():
            break
        assert client.resubscribes_total == 0
        await client.resubscribe_book("BTC/EUR")
        assert client.resubscribes_total == 1

    asyncio.run(run())


def test_client_resubscribes_total_unaffected_by_the_not_connected_noop():
    async def run():
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=lambda uri: None, sleep_fn=asyncio.sleep)
        await client.resubscribe_book("BTC/EUR")  # a no-op: never connected
        assert client.resubscribes_total == 0

    asyncio.run(run())


# --- _run() wiring: opt-in exporter, registered late, isolated from the message-handler path -----


def test_metrics_port_unset_starts_no_server(tmp_path, monkeypatch):
    monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
    monkeypatch.setattr(cmd, "CaptureClient", _FakeClient)
    calls = []
    monkeypatch.setattr(cmd, "start_metrics_server", lambda port, registry: calls.append(port) or True)
    result = runner.invoke(app, ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "1"])
    assert result.exit_code == 0, result.output
    assert calls == []  # the workstation soak (no ZCRYPTO_METRICS_PORT) starts no exporter


def test_metrics_port_set_serves_process_and_capture_series(tmp_path, monkeypatch):
    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    monkeypatch.setattr(cmd, "CaptureClient", _FakeClient)
    result = runner.invoke(app, ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "1"])
    assert result.exit_code == 0, result.output

    body = _get(f"http://127.0.0.1:{port}/metrics")
    for name in (
        "process_resident_memory_bytes",
        "zcrypto_capture_reconnects_total",
        "zcrypto_capture_resubscribes_total",
        "zcrypto_capture_segments_written_total",
        "zcrypto_capture_segment_bytes_total",
        "zcrypto_capture_rows_held_total",
        "zcrypto_capture_rows_quarantined_total",
        "zcrypto_capture_gap_seconds_total",
        "zcrypto_capture_book_desynced",
        "zcrypto_capture_disk_watermark_breached",
    ):
        assert name in body, f"{name} missing from /metrics: {body}"


def test_collector_registration_failure_does_not_stop_the_message_handler_path(tmp_path, monkeypatch, caplog):
    # Isolation invariant (spec 00069 D5): even if wiring the metrics collector itself blows up,
    # capture's real work -- consuming the WS stream and writing rows -- must run exactly as if
    # ZCRYPTO_METRICS_PORT had never been set.
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    monkeypatch.setattr(cmd, "CaptureClient", _FakeClient)

    def _boom(*args, **kwargs):
        raise RuntimeError("collector construction boom")

    monkeypatch.setattr(cmd, "CaptureCollector", _boom)
    with caplog.at_level(logging.ERROR):
        result = runner.invoke(app, ["capture", "--pairs", "BTC/EUR", "--data-dir", str(tmp_path), "--duration", "1"])
    assert result.exit_code == 0, result.output
    parts = list((tmp_path / "BTC/EUR" / "trades" / "2026" / "07" / "08").glob("14.part*.parquet"))
    assert parts, "the message-handler path must complete its real work despite a raising collector"
    assert any(r.levelno == logging.ERROR for r in caplog.records)
