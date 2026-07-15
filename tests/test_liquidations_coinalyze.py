import io
import json
import os
import re
import signal
import urllib.error
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.segment_writer import LIQ_AGG_SCHEMA, SegmentWriter, verify_manifest
from cli.liquidations.coinalyze import fetch_liquidation_history, poll_cycle, symbol_for
from cli.liquidations.errors import LiquidationsError

runner = CliRunner()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _opener(body):
    def _open(request, timeout=None):
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    return _open


# --- fetch_liquidation_history -----------------------------------------------------------------


def test_fetch_liquidation_history_returns_parsed_list_on_success():
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": 1000, "l": 123.4, "s": 56.7}]}]
    rows = fetch_liquidation_history("key", ["BTCUSDT_PERP.A"], 900, 1900, opener=_opener(body))
    assert rows == body


def test_fetch_liquidation_history_sends_the_api_key_header_and_query_params():
    captured = {}

    def _open(request, timeout=None):
        captured["header"] = request.get_header("Api_key")
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return io.BytesIO(b"[]")

    fetch_liquidation_history("secret-key", ["BTCUSDT_PERP.A", "ETHUSDT_PERP.A"], 900, 1900, opener=_open)
    assert captured["header"] == "secret-key"
    assert "symbols=BTCUSDT_PERP.A,ETHUSDT_PERP.A" in captured["url"]
    assert "interval=1min" in captured["url"]
    assert "from=900" in captured["url"]
    assert "to=1900" in captured["url"]
    assert "convert_to_usd=true" in captured["url"]
    assert captured["timeout"] == 15


def test_fetch_liquidation_history_raises_on_transport_error():
    def _raise(request, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(LiquidationsError):
        fetch_liquidation_history("key", ["BTCUSDT_PERP.A"], 0, 1, opener=_raise)


def test_fetch_liquidation_history_raises_on_malformed_json():
    def _open(request, timeout=None):
        return io.BytesIO(b"not json")

    with pytest.raises(LiquidationsError):
        fetch_liquidation_history("key", ["BTCUSDT_PERP.A"], 0, 1, opener=_open)


def test_fetch_liquidation_history_raises_on_non_list_response():
    def _open(request, timeout=None):
        return io.BytesIO(b'{"error": "nope"}')

    with pytest.raises(LiquidationsError):
        fetch_liquidation_history("key", ["BTCUSDT_PERP.A"], 0, 1, opener=_open)


# --- poll_cycle ----------------------------------------------------------------------------------


def test_poll_cycle_writes_closed_buckets_and_excludes_open_ones(tmp_path):
    now = datetime(2024, 3, 1, 12, 5, 0, tzinfo=UTC)
    now_s = int(now.timestamp())
    closed_t = now_s - 200  # closed_t + 60 = now_s - 140 <= now_s - 120 -> proven closed
    open_t = now_s - 100  # open_t + 60 = now_s - 40 > now_s - 120 -> not yet proven closed
    body = [
        {
            "symbol": "BTCUSDT_PERP.A",
            "history": [
                {"t": closed_t, "l": 1000.0, "s": 500.0},
                {"t": open_t, "l": 999.0, "s": 111.0},
            ],
        }
    ]
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}

    written = poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    assert written == 1
    writers["BTC"].close()

    hour_dir = tmp_path / "BTC" / "liquidations-1m" / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
    parts = list(hour_dir.glob(f"{now:%H}.part*.parquet"))
    assert parts
    df = pl.read_parquet(parts[0])
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["symbol"] == "BTCUSDT_PERP.A"
    assert row["long_usd"] == 1000.0
    assert row["short_usd"] == 500.0
    assert row["event_id"] == f"BTCUSDT_PERP.A-{closed_t}"
    assert row["ts"] == datetime.fromtimestamp(closed_t, tz=UTC)


def test_poll_cycle_dedups_across_overlapping_polls(tmp_path):
    now = datetime(2024, 3, 1, 12, 5, 0, tzinfo=UTC)
    now_s = int(now.timestamp())
    closed_t = now_s - 200
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": closed_t, "l": 1000.0, "s": 500.0}]}]
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}

    first = poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    # A later cycle re-fetches the same 24h-back window (the plan's decision: no "since last
    # cycle" state) and gets the SAME bucket again -- SegmentWriter's dedup_key must absorb it.
    second = poll_cycle("key", ["BTC"], writers, now=now + timedelta(seconds=5), opener=_opener(body))
    writers["BTC"].close()

    assert first == 1
    assert second == 1  # poll_cycle counts candidate rows submitted; SegmentWriter drops the dup
    hour_dir = tmp_path / "BTC" / "liquidations-1m" / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
    parts = list(hour_dir.glob(f"{now:%H}.part*.parquet"))
    total_rows = sum(pl.read_parquet(p).height for p in parts)
    assert total_rows == 1


def test_poll_cycle_raises_and_writes_nothing_on_fetch_failure(tmp_path):
    def _raise(request, timeout=None):
        raise urllib.error.URLError("boom")

    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}
    with pytest.raises(LiquidationsError):
        poll_cycle("key", ["BTC"], writers, opener=_raise)
    writers["BTC"].close()

    assert not list(tmp_path.rglob("*.parquet"))
    assert not list(tmp_path.rglob("*.part*.parquet"))


def test_poll_cycle_finalizes_a_crossed_hour_with_a_valid_manifest(tmp_path):
    now = datetime(2024, 3, 1, 13, 10, 0, tzinfo=UTC)  # currently in hour 13
    t_hour12 = int(datetime(2024, 3, 1, 12, 5, 0, tzinfo=UTC).timestamp())
    t_hour13 = int(datetime(2024, 3, 1, 13, 0, 0, tzinfo=UTC).timestamp())  # +60 <= now-120s: closed
    body = [
        {
            "symbol": "BTCUSDT_PERP.A",
            "history": [
                {"t": t_hour12, "l": 1.0, "s": 2.0},
                {"t": t_hour13, "l": 3.0, "s": 4.0},
            ],
        }
    ]
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}

    written = poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    assert written == 2
    writers["BTC"].close()

    final_12 = tmp_path / "BTC" / "liquidations-1m" / "2024" / "03" / "01" / "12.parquet"
    assert final_12.exists()
    assert verify_manifest(final_12) is True
    assert pl.read_parquet(final_12)["event_id"].to_list() == [f"BTCUSDT_PERP.A-{t_hour12}"]


def test_poll_cycle_ignores_a_symbol_with_no_writer(tmp_path):
    now = datetime(2024, 3, 1, 12, 5, 0, tzinfo=UTC)
    now_s = int(now.timestamp())
    closed_t = now_s - 200
    body = [
        {"symbol": "BTCUSDT_PERP.A", "history": [{"t": closed_t, "l": 1.0, "s": 1.0}]},
        {"symbol": "ETHUSDT_PERP.A", "history": [{"t": closed_t, "l": 1.0, "s": 1.0}]},
    ]
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}

    # Only "BTC" was passed in `coins`/`writers` -- ETH's entry must be skipped, not KeyError.
    written = poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    assert written == 1
    writers["BTC"].close()
    assert not (tmp_path / "ETH").exists()


def test_symbol_for_maps_coin_to_the_coinalyze_symbol():
    assert symbol_for("BTC") == "BTCUSDT_PERP.A"


# --- `zcrypto liquidations-poll` command -------------------------------------------------------


def test_liquidations_poll_help_lists_options():
    result = runner.invoke(app, ["liquidations-poll", "--help"])
    assert result.exit_code == 0
    output = _ANSI_RE.sub("", result.output)
    assert "--data-dir" in output
    assert "--duration" in output


def test_liquidations_poll_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("COINALYZE_API_KEY", raising=False)
    result = runner.invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_liquidations_poll_end_to_end_with_duration(tmp_path, monkeypatch):
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")
    monkeypatch.setattr("cli.liquidations.coinalyze._sleep", lambda seconds: None)

    def _fake_poll_cycle(api_key, coins, writers, *, now=None, opener=None):
        assert api_key == "test-key"
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

    monkeypatch.setattr("cli.liquidations.coinalyze.poll_cycle", _fake_poll_cycle)
    result = runner.invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path), "--duration", "0"])
    assert result.exit_code == 0, result.output

    # 2024-03-01 is now (T0046) more than the 31h finalize lag behind the real wall clock, so this
    # cycle's own finalize step closes it into a final rather than leaving it an open part.
    tree = tmp_path / "BTC" / "liquidations-1m"
    finals = [q for q in tree.rglob("*.parquet") if ".part" not in q.name]
    assert finals, "expected a FINAL -- the stale hour must have finalized past the 31h lag (review M-3)"
    assert not list(tree.rglob("*.part*.parquet")), "no open parts should remain"


def test_liquidations_poll_sigterm_flushes_writers_cleanly(tmp_path, monkeypatch):
    # No --duration: SIGTERM is the ONLY way this run stops -- proves the signal interrupts the
    # loop (mid-cycle, not just during the sleep) and the writer still gets flushed on the way out.
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")

    def _fake_poll_cycle(api_key, coins, writers, *, now=None, opener=None):
        writers["BTC"].append(
            {
                "ts": datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC),
                "symbol": "BTCUSDT_PERP.A",
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": "BTCUSDT_PERP.A-1",
            }
        )
        os.kill(os.getpid(), signal.SIGTERM)  # simulate the supervisor stopping the container
        return 1

    monkeypatch.setattr("cli.liquidations.coinalyze.poll_cycle", _fake_poll_cycle)
    result = runner.invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    parts = list((tmp_path / "BTC" / "liquidations-1m").rglob("*.part*.parquet"))
    assert parts


def test_liquidations_poll_skips_ping_and_keeps_looping_on_a_failed_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")
    monkeypatch.setattr("cli.liquidations.coinalyze._sleep", lambda seconds: None)
    pings = []
    monkeypatch.setattr("cli.liquidations.coinalyze.ping_healthcheck", lambda url: pings.append(url))

    calls = {"n": 0}

    def _flaky_poll_cycle(api_key, coins, writers, *, now=None, opener=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LiquidationsError("boom")
        return 0

    monkeypatch.setattr("cli.liquidations.coinalyze.poll_cycle", _flaky_poll_cycle)
    result = runner.invoke(
        app,
        ["liquidations-poll", "--data-dir", str(tmp_path), "--duration", "0"],
        env={"LIQUIDATIONS_HEALTHCHECK_URL": "https://hc.example/ping"},
    )
    assert result.exit_code == 0, result.output
    # duration=0 stops after the FIRST cycle, which failed -> no ping was sent this run.
    assert calls["n"] == 1
    assert pings == []


def test_poll_cycle_resubmission_into_a_finalized_hour_leaves_it_byte_identical(tmp_path):
    """The load-bearing overlap invariant (2026-07-15 review): every cycle re-fetches the whole
    catch-up window, and re-submitted buckets from an already-FINALIZED hour must be dropped by
    SegmentWriter's late-event floor (dedup's `_seen` covers only the open hour). A regression here
    silently duplicates rows into the non-backfillable archive."""
    hour1 = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    hour2 = hour1 + timedelta(hours=1)
    t1 = int(hour1.timestamp()) + 300  # 12:05 bucket
    t2 = int(hour2.timestamp()) + 60  # 13:01 bucket -- crossing into hour 13 finalizes hour 12
    body = [
        {
            "symbol": "BTCUSDT_PERP.A",
            "history": [{"t": t1, "l": 10.0, "s": 5.0}, {"t": t2, "l": 20.0, "s": 2.0}],
        }
    ]
    now = datetime(2024, 3, 1, 13, 30, 0, tzinfo=UTC)  # both buckets proven closed
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}

    poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    day_dir = tmp_path / "BTC" / "liquidations-1m" / "2024" / "03" / "01"
    final_12 = day_dir / "12.parquet"
    assert final_12.exists(), "hour 12 must have finalized when the 13:01 bucket crossed the boundary"
    before = final_12.read_bytes()
    parts_12_before = sorted(p.name for p in day_dir.glob("12.part*.parquet"))

    # Second cycle: the SAME response (the flat catch-up window re-fetch). The hour-12 bucket is now
    # a late event below the writer's floor -- it must be dropped, not appended to a new part.
    poll_cycle("key", ["BTC"], writers, now=now + timedelta(minutes=5), opener=_opener(body))
    writers["BTC"].close()

    assert final_12.read_bytes() == before, "finalized hour mutated by a re-submission"
    assert sorted(p.name for p in day_dir.glob("12.part*.parquet")) == parts_12_before, (
        "a re-submitted bucket re-opened a finalized hour as a new part"
    )


def test_poll_cycle_handles_a_reversed_history_without_dropping_earlier_hours(tmp_path):
    """I2: a non-ascending response must not ratchet the writer's hour forward past earlier buckets
    (which would drop them as late events on EVERY cycle -- a permanent, silent gap)."""
    hour1 = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    hour2 = hour1 + timedelta(hours=1)
    t1 = int(hour1.timestamp()) + 300
    t2 = int(hour2.timestamp()) + 60
    body = [
        {
            "symbol": "BTCUSDT_PERP.A",
            # REVERSED: the later bucket first
            "history": [{"t": t2, "l": 20.0, "s": 2.0}, {"t": t1, "l": 10.0, "s": 5.0}],
        }
    ]
    now = datetime(2024, 3, 1, 13, 30, 0, tzinfo=UTC)
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}
    poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    writers["BTC"].close()

    day_dir = tmp_path / "BTC" / "liquidations-1m" / "2024" / "03" / "01"
    rows_12 = sum(pl.read_parquet(p).height for p in day_dir.glob("12.*parquet"))
    assert rows_12 == 1, "the earlier-hour bucket was dropped because the response was not ascending"


# --- T0046: wall-clock hour finalization for sparse symbols --------------------------------------


def test_liquidations_poll_finalizes_a_stale_open_hour_past_the_finalize_lag(tmp_path, monkeypatch):
    # The lag (31h) is deliberately wider than the 30h catch-up window, so a hour eligible for
    # finalize can never still be reachable by poll_cycle's own re-fetch -- it must already be open
    # from an earlier cycle. Simulated here by appending directly to the writer, like the other
    # SIGTERM/duration tests above.
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")
    monkeypatch.setattr("cli.liquidations.coinalyze._sleep", lambda seconds: None)
    stale_ts = datetime.now(UTC) - timedelta(hours=32)

    def _fake_poll_cycle(api_key, coins, writers, *, now=None, opener=None):
        writers["BTC"].append(
            {
                "ts": stale_ts,
                "symbol": "BTCUSDT_PERP.A",
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": "BTCUSDT_PERP.A-1",
            }
        )
        return 1

    monkeypatch.setattr("cli.liquidations.coinalyze.poll_cycle", _fake_poll_cycle)
    result = runner.invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path), "--duration", "0"])
    assert result.exit_code == 0, result.output

    hour_dir = tmp_path / "BTC" / "liquidations-1m" / f"{stale_ts:%Y}" / f"{stale_ts:%m}" / f"{stale_ts:%d}"
    final = hour_dir / f"{stale_ts:%H}.parquet"
    assert final.exists()
    assert verify_manifest(final) is True


def test_liquidations_poll_leaves_a_recent_open_hour_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")
    monkeypatch.setattr("cli.liquidations.coinalyze._sleep", lambda seconds: None)
    recent_ts = datetime.now(UTC) - timedelta(hours=30)  # inside the 31h lag: must stay open

    def _fake_poll_cycle(api_key, coins, writers, *, now=None, opener=None):
        writers["BTC"].append(
            {
                "ts": recent_ts,
                "symbol": "BTCUSDT_PERP.A",
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": "BTCUSDT_PERP.A-1",
            }
        )
        return 1

    monkeypatch.setattr("cli.liquidations.coinalyze.poll_cycle", _fake_poll_cycle)
    result = runner.invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path), "--duration", "0"])
    assert result.exit_code == 0, result.output

    hour_dir = tmp_path / "BTC" / "liquidations-1m" / f"{recent_ts:%Y}" / f"{recent_ts:%m}" / f"{recent_ts:%d}"
    final = hour_dir / f"{recent_ts:%H}.parquet"
    assert not final.exists()  # not old enough to cross the lag -- still open
    # The graceful shutdown's close() still flushes the buffered row to a part (never a final).
    assert list(hour_dir.glob(f"{recent_ts:%H}.part*.parquet"))


def test_run_survives_a_malformed_bucket_and_retries(tmp_path, monkeypatch):
    """I1: a bucket with null l/s raises TypeError inside poll_cycle -- the CYCLE must fail (no ping)
    while the loop keeps running, instead of the process crash-looping against the same response."""
    from cli.liquidations import coinalyze as mod

    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": 1709294700, "l": None, "s": 1.0}]}]
    calls = {"n": 0}

    def _fake_fetch(api_key, symbols, frm, to, *, opener=None):
        calls["n"] += 1
        return body

    pings = []
    monkeypatch.setattr(mod, "fetch_liquidation_history", _fake_fetch)
    monkeypatch.setattr(mod, "ping_healthcheck", lambda url: pings.append(url))
    monkeypatch.setenv(mod.API_KEY_ENV_VAR, "key")
    monkeypatch.setenv(mod.DATA_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setenv(mod.HEALTHCHECK_ENV_VAR, "https://example.invalid/ping")
    monkeypatch.setenv(mod.POLL_SECONDS_ENV_VAR, "0")

    from typer.testing import CliRunner

    from cli.__main__ import app

    result = CliRunner().invoke(app, ["liquidations-poll", "--data-dir", str(tmp_path), "--duration", "1"])
    assert result.exit_code == 0, result.output
    assert calls["n"] >= 1
    assert pings == []  # a failed cycle must never ping the dead-man
