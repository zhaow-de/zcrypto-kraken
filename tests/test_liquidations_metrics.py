"""spec 00069 T5: the Coinalyze poller's `/metrics` tap -- `cli/liquidations/coinalyze.py` only
(`cli/liquidations/command.py` is the shelved Binance WS recorder and carries no tap)."""

import socket
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

from cli.capture.gap_monitor import DiskWatermark
from cli.capture.segment_writer import LIQ_AGG_SCHEMA, SegmentWriter
from cli.liquidations import coinalyze as mod
from cli.liquidations.coinalyze import COINS, _poll_once, _PollMetrics
from cli.liquidations.errors import LiquidationsError
from cli.obs.metrics import METRICS_PORT_ENV_VAR


def _families(registry: CollectorRegistry) -> dict:
    """Sample-name -> the family carrying it (`Counter` strips a trailing `_total` from
    `family.name` and re-adds it per sample -- see `tests/test_capture_metrics.py::_families`)."""
    result: dict = {}
    for family in registry.collect():
        for sample in family.samples:
            result[sample.name] = family
    return result


def _writers(tmp_path: Path) -> dict[str, SegmentWriter]:
    return {coin: SegmentWriter(tmp_path, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id") for coin in COINS}


class _FakeUsage:
    def __init__(self, free: int) -> None:
        self.free = free


def _watermark(tmp_path: Path, *, free: int = 10_000) -> DiskWatermark:
    return DiskWatermark(tmp_path, min_free_bytes=1024, usage_fn=lambda p: _FakeUsage(free=free))


def _one_row_poll_cycle(monkeypatch):
    """A `poll_cycle` stand-in that writes one row to BTC's writer and reports one submission."""

    def fn(api_key, coins, writers, *, watermarks=None, now=None, opener=None):
        writers["BTC"].append(
            {
                "ts": datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC),
                "symbol": "BTCUSDT_PERP.A",
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": "BTCUSDT_PERP.A-1",
            }
        )
        return 1

    monkeypatch.setattr(mod, "poll_cycle", fn)


# --- _poll_once / _record_outcome: every branch ---------------------------------------------------


def test_poll_once_with_no_metrics_is_unaffected(tmp_path, monkeypatch):
    # metrics defaults to None (ZCRYPTO_METRICS_PORT unset) -- must behave exactly as before T5.
    _one_row_poll_cycle(monkeypatch)
    writers = _writers(tmp_path)
    assert _poll_once("key", writers, _watermark(tmp_path), {}) is True
    for w in writers.values():
        w.close()


def test_poll_once_success_increments_ok_and_sets_last_success(tmp_path, monkeypatch):
    _one_row_poll_cycle(monkeypatch)
    writers = _writers(tmp_path)
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)

    before = mod.time.time()
    assert _poll_once("key", writers, _watermark(tmp_path), {}, metrics) is True
    for w in writers.values():
        w.close()

    families = _families(registry)
    ok_sample = next(s for s in families["zcrypto_liquidations_polls_total"].samples if s.labels["outcome"] == "ok")
    assert ok_sample.value == 1.0
    assert "error" not in {s.labels["outcome"] for s in families["zcrypto_liquidations_polls_total"].samples}
    assert families["zcrypto_liquidations_api_errors_total"].samples[0].value == 0.0
    assert families["zcrypto_liquidations_last_success_timestamp_seconds"].samples[0].value >= before


def test_poll_once_watermark_check_raising_counts_as_error_not_api_error(tmp_path):
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)

    def _raising_usage(path):
        raise OSError("flaky mount")

    watermark = DiskWatermark(tmp_path, min_free_bytes=1024, usage_fn=_raising_usage)
    writers = _writers(tmp_path)
    assert _poll_once("key", writers, watermark, {}, metrics) is False
    for w in writers.values():
        w.close()

    families = _families(registry)
    error_sample = next(s for s in families["zcrypto_liquidations_polls_total"].samples if s.labels["outcome"] == "error")
    assert error_sample.value == 1.0
    assert families["zcrypto_liquidations_api_errors_total"].samples[0].value == 0.0  # not an API failure


def test_poll_once_watermark_breached_counts_as_error_not_api_error(tmp_path):
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)
    watermark = _watermark(tmp_path, free=10)  # below min_free_bytes
    watermark.check()
    writers = _writers(tmp_path)

    assert _poll_once("key", writers, watermark, {}, metrics) is False
    for w in writers.values():
        w.close()

    families = _families(registry)
    error_sample = next(s for s in families["zcrypto_liquidations_polls_total"].samples if s.labels["outcome"] == "error")
    assert error_sample.value == 1.0
    assert families["zcrypto_liquidations_api_errors_total"].samples[0].value == 0.0


def test_poll_once_liquidations_error_counts_as_error_and_api_error(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "poll_cycle", lambda *a, **kw: (_ for _ in ()).throw(LiquidationsError("boom")))
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)
    writers = _writers(tmp_path)

    assert _poll_once("key", writers, _watermark(tmp_path), {}, metrics) is False
    for w in writers.values():
        w.close()

    families = _families(registry)
    error_sample = next(s for s in families["zcrypto_liquidations_polls_total"].samples if s.labels["outcome"] == "error")
    assert error_sample.value == 1.0
    assert families["zcrypto_liquidations_api_errors_total"].samples[0].value == 1.0  # THE api-error path


def test_poll_once_unexpected_exception_counts_as_error_not_api_error(tmp_path, monkeypatch):
    # A malformed bucket (TypeError/KeyError/AttributeError) is not LiquidationsError -- it must
    # count against polls_total{outcome=error} but NOT api_errors_total (it isn't an API failure).
    monkeypatch.setattr(mod, "poll_cycle", lambda *a, **kw: (_ for _ in ()).throw(TypeError("bad bucket")))
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)
    writers = _writers(tmp_path)

    assert _poll_once("key", writers, _watermark(tmp_path), {}, metrics) is False
    for w in writers.values():
        w.close()

    families = _families(registry)
    error_sample = next(s for s in families["zcrypto_liquidations_polls_total"].samples if s.labels["outcome"] == "error")
    assert error_sample.value == 1.0
    assert families["zcrypto_liquidations_api_errors_total"].samples[0].value == 0.0


# --- isolation regression: a raising metrics update never aborts the poll cycle -------------------


class _RaisingLabels:
    def labels(self, **kwargs):
        raise RuntimeError("metrics boom")


def test_a_raising_metrics_update_never_aborts_a_poll_cycle(tmp_path, monkeypatch, caplog):
    _one_row_poll_cycle(monkeypatch)
    registry = CollectorRegistry()
    metrics = _PollMetrics(registry)
    metrics.polls_total = _RaisingLabels()  # the very first metrics call this cycle makes
    writers = _writers(tmp_path)

    with caplog.at_level("ERROR"):
        ok = _poll_once("key", writers, _watermark(tmp_path), {}, metrics)
    for w in writers.values():
        w.close()

    assert ok is True  # the raise never propagated out of _poll_once
    # 2024-03-01 is more than the 31h finalize lag behind the real wall clock (T0046), so this
    # cycle's own finalize step closes the hour into a FINAL rather than leaving it an open part.
    written = list((tmp_path / "BTC" / "liquidations-1m").rglob("*.parquet"))
    assert written, "the real work (the writer append + finalize) must have happened despite the raising metrics update"
    assert any(r.levelno >= 40 for r in caplog.records)


# --- _run(): opt-in wiring --------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_run_metrics_port_unset_starts_no_server(tmp_path, monkeypatch):
    monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
    _one_row_poll_cycle(monkeypatch)
    monkeypatch.setattr(mod, "_sleep", lambda seconds: None)
    calls = []
    monkeypatch.setattr(mod, "start_metrics_server", lambda port, registry: calls.append(port) or True)

    mod._run(tmp_path, "key", 300, None, duration=0)

    assert calls == []


def test_run_metrics_port_set_serves_process_and_poller_series(tmp_path, monkeypatch):
    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _one_row_poll_cycle(monkeypatch)
    monkeypatch.setattr(mod, "_sleep", lambda seconds: None)

    mod._run(tmp_path, "key", 300, None, duration=0)

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    for name in (
        "process_resident_memory_bytes",
        "zcrypto_liquidations_polls_total",
        "zcrypto_liquidations_api_errors_total",
        "zcrypto_liquidations_last_success_timestamp_seconds",
    ):
        assert name in body, f"{name} missing from /metrics: {body}"
