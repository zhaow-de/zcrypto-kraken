import asyncio
import logging
from decimal import Decimal

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.http11 import Response

from cli.capture.errors import CaptureError
from cli.capture.ws_client import (
    CaptureClient,
    build_subscribe_message,
    build_unsubscribe_message,
    classify,
    compute_backoff,
    parse_message,
)


def test_build_subscribe_message_book_includes_depth():
    msg = build_subscribe_message("book", ["BTC/EUR", "ETH/EUR"], depth=100)
    assert msg == {
        "method": "subscribe",
        "params": {"channel": "book", "symbol": ["BTC/EUR", "ETH/EUR"], "snapshot": True, "depth": 100},
    }


def test_build_subscribe_message_trade_omits_depth():
    msg = build_subscribe_message("trade", ["BTC/EUR"])
    assert msg == {
        "method": "subscribe",
        "params": {"channel": "trade", "symbol": ["BTC/EUR"], "snapshot": True},
    }
    assert "depth" not in msg["params"]


def test_build_subscribe_message_includes_req_id_when_given():
    msg = build_subscribe_message("book", ["BTC/EUR"], depth=10, req_id=7)
    assert msg["req_id"] == 7


def test_build_unsubscribe_message_book_includes_depth_and_no_snapshot():
    msg = build_unsubscribe_message("book", ["BTC/EUR"], depth=100)
    assert msg == {
        "method": "unsubscribe",
        "params": {"channel": "book", "symbol": ["BTC/EUR"], "depth": 100},
    }
    assert "snapshot" not in msg["params"]


def test_parse_message_preserves_trailing_zero_precision():
    parsed = parse_message('{"price": 0.30000000, "n": 3}')
    assert parsed["price"] == Decimal("0.30000000")
    assert str(parsed["price"]) == "0.30000000"
    assert parsed["n"] == 3
    assert isinstance(parsed["n"], int)


def test_parse_message_raises_capture_error_on_invalid_json():
    with pytest.raises(CaptureError):
        parse_message("not json")


@pytest.mark.parametrize(
    "msg,expected",
    [
        ({"channel": "book", "type": "snapshot"}, "book_snapshot"),
        ({"channel": "book", "type": "update"}, "book_update"),
        ({"channel": "trade", "type": "snapshot"}, "trade_snapshot"),
        ({"channel": "trade", "type": "update"}, "trade_update"),
        ({"channel": "heartbeat"}, "heartbeat"),
        ({"method": "subscribe", "success": True}, "subscribe_ack"),
        ({"method": "subscribe", "success": False}, "subscribe_error"),
        ({"method": "unsubscribe", "success": True}, "unsubscribe_ack"),
        ({"method": "unsubscribe", "success": False}, "unsubscribe_error"),
        # Was "other" until T0101: dropping the venue's own status meant nothing recorded whether an
        # outage had been announced, so the question was unanswerable rather than answered.
        ({"channel": "status"}, "status"),
    ],
)
def test_classify(msg, expected):
    assert classify(msg) == expected


def test_compute_backoff_doubles_and_caps():
    assert compute_backoff(0) == 1.0
    assert compute_backoff(1) == 2.0
    assert compute_backoff(2) == 4.0
    assert compute_backoff(10, max_delay=60.0) == 60.0


def test_compute_backoff_rejects_negative_attempt():
    with pytest.raises(CaptureError):
        compute_backoff(-1)


def test_capture_client_rejects_invalid_depth():
    with pytest.raises(CaptureError):
        CaptureClient(["BTC/EUR"], 99)


def test_capture_client_rejects_empty_pairs():
    with pytest.raises(CaptureError):
        CaptureClient([], 100)


class _FakeConnection:
    """A minimal stand-in for a `websockets` connection: records sent frames, and yields a
    canned list of messages before optionally raising `ConnectionClosedError`."""

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


def test_stream_subscribes_and_yields_parsed_messages():
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, calls = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)

        results = []
        async for msg in client.stream():
            results.append(msg)
            break

        assert calls == ["wss://fake"]
        assert results == [{"channel": "heartbeat"}]
        assert len(conn.sent) == 2  # book subscribe + trade subscribe
        import json

        book_msg = json.loads(conn.sent[0])
        trade_msg = json.loads(conn.sent[1])
        assert book_msg["params"]["channel"] == "book"
        assert book_msg["params"]["depth"] == 100
        assert trade_msg["params"]["channel"] == "trade"

    asyncio.run(run())


def test_stream_reconnects_with_backoff_after_connection_closed():
    async def run():
        conn1 = _FakeConnection(['{"channel": "heartbeat"}'], raise_at_end=True)
        conn2 = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, calls = _connect_fn_returning(conn1, conn2)
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        results = []
        async for msg in client.stream():
            results.append(msg)
            if len(results) == 2:
                break

        assert calls == ["wss://fake", "wss://fake"]
        assert len(results) == 2
        assert sleep_calls == [1.0]  # backoff(attempt=0) before the single reconnect
        assert conn1.sent == conn2.sent  # both connections got identical subscribe frames

    asyncio.run(run())


# --- T0035: a rejected reconnect ATTEMPT must back off and retry, not kill the daemon ------------
#
# Kraken restarted its WS service (close 1012) on 2026-07-13 and answered the reconnect handshake
# with HTTP 503 while coming back up. `InvalidStatus` is not a `ConnectionClosed`, so pre-fix it
# escaped stream()'s sole handler, propagated out of the async generator, and crashed the process —
# the backoff/retry loop built for exactly this never ran past attempt 1.


def _invalid_status_503():
    """The real exception production saw: `InvalidStatus: server rejected WebSocket connection: HTTP 503`."""
    return InvalidStatus(Response(503, "Service Unavailable", Headers()))


def _connect_fn_scripted(*script):
    """A connect_fn following `script` per call: raise the item if it is an exception, return it otherwise."""
    calls = []
    remaining = list(script)

    def connect_fn(uri):
        calls.append(uri)
        item = remaining.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    return connect_fn, calls


def test_stream_backs_off_and_reconnects_after_rejected_handshake():
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, calls = _connect_fn_scripted(_invalid_status_503(), _invalid_status_503(), conn)
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        results = []
        async for msg in client.stream():
            results.append(msg)
            break

        assert results == [{"channel": "heartbeat"}]
        assert calls == ["wss://fake"] * 3  # two rejected handshakes, then the successful connect
        assert sleep_calls == [1.0, 2.0]  # compute_backoff(0), compute_backoff(1) across the failures

    asyncio.run(run())


def test_stream_backs_off_and_reconnects_after_os_error():
    # ConnectionRefusedError / DNS failures surface as OSError from the connect call — same treatment.
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, calls = _connect_fn_scripted(ConnectionRefusedError("connection refused"), conn)
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)

        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        results = []
        async for msg in client.stream():
            results.append(msg)
            break

        assert results == [{"channel": "heartbeat"}]
        assert calls == ["wss://fake"] * 2
        assert sleep_calls == [1.0]

    asyncio.run(run())


def test_stream_lets_cancellation_propagate():
    # CancelledError is the designed stop signal — the widened handler must never swallow it.
    async def run():
        connect_fn, _ = _connect_fn_scripted(asyncio.CancelledError())
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)

        with pytest.raises(asyncio.CancelledError):
            async for _ in client.stream():
                pass

    asyncio.run(run())


def test_stream_logs_error_every_10_consecutive_failed_reconnects(caplog):
    # A genuinely prolonged venue outage must be LOUD: one ERROR per 10 consecutive failed
    # attempts (not one per failure, and not merely the per-attempt INFO line).
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, _ = _connect_fn_scripted(*[_invalid_status_503() for _ in range(10)], conn)

        async def fake_sleep(delay):
            pass

        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)

        async for _ in client.stream():
            break

    with caplog.at_level(logging.INFO, logger="zcrypto.capture.ws_client"):
        asyncio.run(run())

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1  # fired exactly at the 10th consecutive failure, not on every failure
    assert "10" in errors[0].getMessage()


def test_resubscribe_book_unsubscribes_then_subscribes():
    # Kraken rejects a bare re-subscribe of an active channel ("Already subscribed") and sends no
    # snapshot, so recovery must unsubscribe THEN subscribe (in that order) to force a fresh snapshot.
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR", "ETH/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)

        async for _ in client.stream():
            break

        sent_before = len(conn.sent)
        await client.resubscribe_book("BTC/EUR")
        import json

        new_frames = [json.loads(f) for f in conn.sent[sent_before:]]
        assert [f["method"] for f in new_frames] == ["unsubscribe", "subscribe"]
        for frame in new_frames:
            assert frame["params"]["channel"] == "book"
            assert frame["params"]["symbol"] == ["BTC/EUR"]
            assert frame["params"]["depth"] == 100

    asyncio.run(run())


def test_resubscribe_book_is_noop_when_not_connected():
    async def run():
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=lambda uri: None, sleep_fn=asyncio.sleep)
        await client.resubscribe_book("BTC/EUR")  # must not raise

    asyncio.run(run())
