import asyncio
import json
import logging

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.frames import Close
from websockets.http11 import Response

from cli.capture import ws_client as capture_ws_client
from cli.liquidations import ws_client as liquidations_ws_client
from cli.liquidations.errors import LiquidationsError
from cli.liquidations.ws_client import DEFAULT_URI, BinanceLiquidationClient, compute_backoff


def _force_order(*, symbol="BTCUSDT", t_ms):
    return json.dumps(
        {
            "stream": "!forceOrder@arr",
            "data": {
                "e": "forceOrder",
                "o": {"s": symbol, "S": "SELL", "q": "1", "p": "100", "ap": "100", "X": "FILLED", "T": t_ms},
            },
        }
    )


def test_default_uri_is_keyless_combined_force_order_stream():
    assert DEFAULT_URI == "wss://fstream.binance.com/stream?streams=!forceOrder@arr"


def test_compute_backoff_doubles_and_caps():
    assert compute_backoff(0) == 1.0
    assert compute_backoff(1) == 2.0
    assert compute_backoff(10, max_delay=60.0) == 60.0


def test_compute_backoff_rejects_negative_attempt():
    with pytest.raises(LiquidationsError):
        compute_backoff(-1)


class _FakeConnection:
    """A minimal stand-in for a `websockets` connection: yields canned frames, optionally raising
    `ConnectionClosedError` at the end. There is no subscribe frame for Binance (the stream is in
    the URL), so nothing is sent."""

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
    calls = []
    remaining = list(connections)

    def connect_fn(uri):
        calls.append(uri)
        return remaining.pop(0)

    return connect_fn, calls


def test_stream_yields_parsed_force_orders_and_skips_noise():
    async def run():
        conn = _FakeConnection([_force_order(t_ms=1568014460893), '{"stream":"x","data":{"e":"aggTrade"}}', "not json"])
        connect_fn, calls = _connect_fn_returning(conn)
        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)

        results = []
        async for row in client.stream():
            results.append(row)
            break

        assert calls == ["wss://fake"]
        assert len(results) == 1  # the aggTrade + garbage frames parsed to None and were skipped
        assert results[0]["symbol"] == "BTCUSDT"
        assert conn.sent == []  # no subscribe frame — subscription is in the URL

    asyncio.run(run())


def test_stream_reconnects_with_backoff_after_connection_closed():
    async def run():
        conn1 = _FakeConnection([_force_order(t_ms=1568014460000)], raise_at_end=True)
        conn2 = _FakeConnection([_force_order(t_ms=1568014461000)])
        connect_fn, calls = _connect_fn_returning(conn1, conn2)
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        results = []
        async for row in client.stream():
            results.append(row)
            if len(results) == 2:
                break

        assert calls == ["wss://fake", "wss://fake"]  # reconnected after the drop
        assert len(results) == 2
        assert sleep_calls == [1.0]  # backoff(attempt=0) reset on the successful first connect

    asyncio.run(run())


def _connect_fn_scripted(*script):
    calls = []
    remaining = list(script)

    def connect_fn(uri):
        calls.append(uri)
        item = remaining.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    return connect_fn, calls


def _invalid_status_503():
    return InvalidStatus(Response(503, "Service Unavailable", Headers()))


def test_stream_backs_off_and_reconnects_after_rejected_handshake():
    async def run():
        conn = _FakeConnection([_force_order(t_ms=1568014460000)])
        connect_fn, calls = _connect_fn_scripted(_invalid_status_503(), _invalid_status_503(), conn)
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        async for _ in client.stream():
            break

        assert calls == ["wss://fake"] * 3  # two rejected handshakes then success
        assert sleep_calls == [1.0, 2.0]

    asyncio.run(run())


def test_stream_lets_cancellation_propagate():
    async def run():
        connect_fn, _ = _connect_fn_scripted(asyncio.CancelledError())
        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)
        with pytest.raises(asyncio.CancelledError):
            async for _ in client.stream():
                pass

    asyncio.run(run())


def test_stream_logs_error_every_10_consecutive_failed_reconnects(caplog):
    async def run():
        conn = _FakeConnection([_force_order(t_ms=1568014460000)])
        connect_fn, _ = _connect_fn_scripted(*[_invalid_status_503() for _ in range(10)], conn)

        async def fake_sleep(delay):
            pass

        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)
        async for _ in client.stream():
            break

    with caplog.at_level(logging.INFO, logger="zcrypto.liquidations.ws_client"):
        asyncio.run(run())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "10" in errors[0].getMessage()


def test_connected_property_tracks_the_socket():
    client = BinanceLiquidationClient(connect_fn=lambda uri: None, sleep_fn=asyncio.sleep)
    assert client.connected is False


# --- a close is logged at the level its outcome deserves ------------------------------------------
#
# Each script item is what one connect returns or raises and the seconds it takes; the fake sleep advances
# the same clock, so the reconnect line's seconds run from the close to the reopened socket.
# `healthy` advances it after each message the consumer reads, the time a connection stays up.


class _ClosingConnection(_FakeConnection):
    def __init__(self, messages, close_code):
        super().__init__(messages)
        self._close_code = close_code

    async def _gen(self):
        for m in self._messages:
            yield m
        raise ConnectionClosedError(Close(self._close_code, "service restart"), None)


def _outcome_lines(caplog, *script, rows, healthy=0.0):
    now = [0.0]
    remaining = list(script)

    def connect_fn(uri):
        item, took = remaining.pop(0)
        now[0] += took
        if isinstance(item, BaseException):
            raise item
        return item

    async def fake_sleep(delay):
        now[0] += delay

    async def run():
        client = BinanceLiquidationClient(uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep, clock_fn=lambda: now[0])
        seen = 0
        async for _ in client.stream():
            seen += 1
            if seen == rows:
                break
            now[0] += healthy

    with caplog.at_level(logging.INFO, logger="zcrypto.liquidations.ws_client"):
        asyncio.run(run())
    return [(r.levelname, r.getMessage()) for r in caplog.records if not r.getMessage().startswith("reconnecting in")]


def test_a_routine_drop_and_its_first_attempt_reconnect_log_at_info(caplog):
    lines = _outcome_lines(
        caplog,
        (_FakeConnection([_force_order(t_ms=1568014460000)], raise_at_end=True), 0.0),
        (_FakeConnection([_force_order(t_ms=1568014461000)]), 0.1),
        rows=2,
    )
    assert lines == [
        ("INFO", "WS connection closed, reconnecting: no close frame received or sent"),
        ("INFO", "reconnected after 1.10 s"),
    ]


def test_a_service_restart_close_logs_at_warning(caplog):
    lines = _outcome_lines(
        caplog,
        (_ClosingConnection([_force_order(t_ms=1568014460000)], 1012), 0.0),
        (_FakeConnection([_force_order(t_ms=1568014461000)]), 0.1),
        rows=2,
    )
    assert lines[0][0] == "WARNING" and lines[0][1].startswith("WS connection closed, reconnecting: received 1012"), lines
    assert lines[1] == ("INFO", "reconnected after 1.10 s")


def test_a_failed_attempt_and_a_reconnect_that_took_two_attempts_log_at_warning(caplog):
    lines = _outcome_lines(
        caplog,
        (_FakeConnection([_force_order(t_ms=1568014460000)], raise_at_end=True), 0.0),
        (_invalid_status_503(), 0.1),
        (_FakeConnection([_force_order(t_ms=1568014461000)]), 0.1),
        rows=2,
    )
    assert lines == [
        ("INFO", "WS connection closed, reconnecting: no close frame received or sent"),
        ("WARNING", "WS connect attempt failed, reconnecting: server rejected WebSocket connection: HTTP 503"),
        ("WARNING", "reconnected after 2 attempts, 3.20 s"),
    ]


def test_a_first_attempt_reconnect_slower_than_the_bound_logs_at_warning(caplog):
    lines = _outcome_lines(
        caplog,
        (_FakeConnection([_force_order(t_ms=1568014460000)], raise_at_end=True), 0.0),
        (_FakeConnection([_force_order(t_ms=1568014461000)]), 4.5),
        rows=2,
    )
    assert lines == [
        ("INFO", "WS connection closed, reconnecting: no close frame received or sent"),
        ("WARNING", "reconnected after 1 attempt, 5.50 s"),
    ]


def test_a_second_drop_times_its_reconnect_from_its_own_close(caplog):
    lines = _outcome_lines(
        caplog,
        (_FakeConnection([_force_order(t_ms=1568014460000)], raise_at_end=True), 0.0),
        (_FakeConnection([_force_order(t_ms=1568014461000)], raise_at_end=True), 0.1),
        (_FakeConnection([_force_order(t_ms=1568014462000)]), 0.1),
        rows=3,
        healthy=3600.0,
    )
    close = ("INFO", "WS connection closed, reconnecting: no close frame received or sent")
    assert lines == [close, ("INFO", "reconnected after 1.10 s"), close, ("INFO", "reconnected after 1.10 s")]


def test_the_poller_s_routine_reconnect_bound_is_the_capture_client_s():
    assert liquidations_ws_client._ROUTINE_RECONNECT_MAX_SECONDS == capture_ws_client._ROUTINE_RECONNECT_MAX_SECONDS
