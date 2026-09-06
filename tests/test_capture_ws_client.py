import asyncio
import json
import logging
from decimal import Decimal

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.frames import Close
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
# `InvalidStatus` — what Kraken answers the reconnect handshake with (HTTP 503) while its WS service
# restarts — is not a `ConnectionClosed`, so the drop handler alone would let it crash the process.


def _invalid_status_503():
    """The real exception production saw: `InvalidStatus: server rejected WebSocket connection: HTTP 503`."""
    return InvalidStatus(Response(503, "Service Unavailable", Headers()))


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
    # A genuinely prolonged venue outage must be LOUD: one ERROR per 10 consecutive failed attempts.
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

        agen = client.stream()
        async for _ in agen:
            break
        await agen.aclose()  # close it explicitly: its `finally` clears `_ws`, and we want that
        # settled BEFORE re-attaching, or the T0102 waiter can find a cleared socket mid-flight and
        # correctly decline to send (the reconnect resubscribes everything in that real case).
        client._ws = conn

        sent_before = len(conn.sent)
        await client.resubscribe_book("BTC/EUR")
        import json

        # T0102: the subscribe is released by the unsubscribe's ack, not sent back-to-back.
        await asyncio.sleep(0)
        req_id = json.loads(conn.sent[sent_before])["req_id"]
        client.note_reply({"method": "unsubscribe", "success": True, "req_id": req_id})
        await client.drain_pending_resubscribes(timeout=1.0)

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


# --- T0101: a venue-announced restart must not be reconnected into at 1.0 s ----------------------
#
# The other close-path tests raise `ConnectionClosedError(None, None)` -- `rcvd is None`, no close code --
# so they never reach the branch that reads it. These drive a real `Close` frame through `stream()`.


class _ClosingConnection(_FakeConnection):
    """Raises a close carrying a real `Close` frame, the way `websockets` does on a venue close."""

    def __init__(self, messages, close_code):
        super().__init__(messages)
        self._close_code = close_code

    async def _gen(self):
        for m in self._messages:
            yield m
        rcvd = Close(self._close_code, "Kraken websockets restarting, please reconnect.")
        raise ConnectionClosedError(rcvd, None)


def _delays_after_close(close_code, *, messages):
    """Run `stream()` across one close carrying `close_code`; return the observed backoff delays."""
    conn1 = _ClosingConnection(messages, close_code)
    conn2 = _FakeConnection(messages)
    connect_fn, _ = _connect_fn_returning(conn1, conn2)
    sleep_calls: list[float] = []

    async def fake_sleep(delay):
        sleep_calls.append(delay)

    async def run():
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=fake_sleep)
        seen = []
        async for msg in client.stream():
            seen.append(msg)
            if len(seen) == 2:
                break

    asyncio.run(run())
    return sleep_calls


def test_a_1012_service_restart_floors_the_first_reconnect_at_five_seconds():
    msg = json.dumps({"channel": "heartbeat"})
    assert _delays_after_close(1012, messages=[msg]) == [5.0]


def test_an_ordinary_close_still_reconnects_fast():
    """Ordinary drops are the daily case: flooring them at 5 s would trade a rare venue restart for a
    daily cost on the unbackfillable path."""
    msg = json.dumps({"channel": "heartbeat"})
    assert _delays_after_close(1006, messages=[msg]) == [1.0]


# --- T0102: req_id-correlated resubscribe (observability + prevention) ---------------------------
#
# `resubscribe_book` NEVER awaits its ack: rung 1 calls it from inside the message handler, i.e. from
# the task that drives `stream()`, where awaiting would block the very loop that delivers the ack.
# The second frame goes to a short-lived task, released by the ack or by a timeout -- which is why
# the tests below hand-deliver replies through `note_reply` and `drain_pending_resubscribes`.


def test_resubscribe_correlates_both_frames_with_req_ids():
    async def run():
        conn = _FakeConnection([])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)
        client._ws = conn
        await client.resubscribe_book("BTC/EUR")
        await asyncio.sleep(0)
        client.note_reply({"method": "unsubscribe", "success": True, "req_id": json.loads(conn.sent[0])["req_id"]})
        await client.drain_pending_resubscribes(timeout=1.0)

        sent = [json.loads(s) for s in conn.sent]
        assert [m["method"] for m in sent] == ["unsubscribe", "subscribe"]
        assert all("req_id" in m for m in sent), "both frames must be correlatable"
        assert sent[0]["req_id"] != sent[1]["req_id"], "distinct requests need distinct ids"

    asyncio.run(run())


def test_the_subscribe_waits_for_the_unsubscribe_ack():
    """Prevention: the ordering race disappears if the second frame is not sent until the first is
    acknowledged."""

    async def run():
        conn = _FakeConnection([])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)
        client._ws = conn
        await client.resubscribe_book("BTC/EUR")
        await asyncio.sleep(0)  # let the waiter task start

        assert len(conn.sent) == 1, f"subscribe went out before the ack: {conn.sent}"
        req_id = json.loads(conn.sent[0])["req_id"]
        client.note_reply({"method": "unsubscribe", "success": True, "req_id": req_id})
        await client.drain_pending_resubscribes(timeout=0.2)
        assert len(conn.sent) == 2, "the ack did not release the subscribe"

    asyncio.run(run())


def test_a_lost_ack_still_subscribes_after_the_timeout():
    """A never-arriving ack must not strand the pair -- the exact failure T0008's ladder exists to
    remove."""

    async def run():
        conn = _FakeConnection([])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep, ack_timeout=0.05)
        client._ws = conn
        await client.resubscribe_book("BTC/EUR")
        await client.drain_pending_resubscribes(timeout=1.0)  # no ack is ever delivered

        assert len(conn.sent) == 2, "a lost ack stranded the pair -- recovery must degrade, not stop"
        assert client.resubscribe_ack_timeouts_total == 1

    asyncio.run(run())


def test_an_error_reply_is_counted_and_does_not_hang():
    """Observability: an explicit rejection is counted, and it still releases the waiter."""

    async def run():
        conn = _FakeConnection([])
        connect_fn, _ = _connect_fn_returning(conn)
        client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake", connect_fn=connect_fn, sleep_fn=asyncio.sleep)
        client._ws = conn
        await client.resubscribe_book("BTC/EUR")
        await asyncio.sleep(0)
        req_id = json.loads(conn.sent[0])["req_id"]
        client.note_reply({"method": "unsubscribe", "success": False, "error": "nope", "req_id": req_id})
        await client.drain_pending_resubscribes(timeout=0.2)

        assert client.resubscribe_errors_total == 1
        assert len(conn.sent) == 2, "a rejected unsubscribe still tries the subscribe (the old path)"

    asyncio.run(run())


def test_note_reply_ignores_uncorrelated_and_unknown_replies():
    """Kraken's own subscribe acks for the initial subscription carry no req_id of ours. An unknown
    or absent id must be a no-op, never a KeyError out of the consumer task."""
    client = CaptureClient(["BTC/EUR"], 100, uri="wss://fake")
    client.note_reply({"method": "subscribe", "success": True})  # no req_id at all
    client.note_reply({"method": "subscribe", "success": True, "req_id": 999999})  # not ours
    assert client.resubscribe_errors_total == 0
