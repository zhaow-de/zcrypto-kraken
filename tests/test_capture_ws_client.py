import asyncio
from decimal import Decimal

import pytest
from websockets.exceptions import ConnectionClosedError

from cli.capture.errors import CaptureError
from cli.capture.ws_client import (
    CaptureClient,
    build_subscribe_message,
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
        ({"channel": "status"}, "other"),
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


def test_resubscribe_book_sends_single_pair_subscribe():
    async def run():
        conn = _FakeConnection(['{"channel": "heartbeat"}'])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR", "ETH/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)

        async for _ in client.stream():
            break

        await client.resubscribe_book("BTC/EUR")
        import json

        last = json.loads(conn.sent[-1])
        assert last["params"]["symbol"] == ["BTC/EUR"]
        assert last["params"]["channel"] == "book"

    asyncio.run(run())


def test_resubscribe_book_is_noop_when_not_connected():
    async def run():
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=lambda uri: None, sleep_fn=asyncio.sleep)
        await client.resubscribe_book("BTC/EUR")  # must not raise

    asyncio.run(run())
