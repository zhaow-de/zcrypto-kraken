from __future__ import annotations

import socket
import struct
import threading
import time

from tests import kraken_loopback as lb


class _Asked(dict):
    def __init__(self, stalls: dict[str, float]):
        super().__init__(stalls)
        self.asked = threading.Event()

    def get(self, key, default=None):
        self.asked.set()
        return super().get(key, default)


def _connect(venue: lb.KrakenLoopback) -> socket.socket:
    return socket.create_connection(("127.0.0.1", int(venue.base_url.rsplit(":", 1)[1])), timeout=5)


def _post(venue: lb.KrakenLoopback, endpoint: str) -> socket.socket:
    sock = _connect(venue)
    sock.sendall(f"POST /0/private/{endpoint} HTTP/1.0\r\nContent-Length: 0\r\n\r\n".encode())
    return sock


def _started_since(before: set[threading.Thread]) -> list[str]:
    return [t.name for t in threading.enumerate() if t not in before and t.is_alive()]


def test_serve_returns_only_after_a_handler_still_answering_has_finished():
    entered, finish = threading.Event(), threading.Event()
    before = set(threading.enumerate())
    with lb.serve() as venue:
        venue.on_add_order = lambda form, txid: (entered.set(), finish.wait(1))
        sock = _post(venue, "AddOrder")
        assert entered.wait(5)
    left = _started_since(before)
    finish.set()
    sock.close()

    assert left == []


def test_a_stalled_answer_ends_as_the_venue_closes_and_its_hung_up_client_prints_nothing(capfd):
    before = set(threading.enumerate())
    with lb.serve() as venue:
        venue.stalls = _Asked({"OpenOrders": 10.0})
        sock = _post(venue, "OpenOrders")
        assert venue.stalls.asked.wait(5)
        # A reset, so the handler's first write at the close fails every time.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        sock.close()
        closing = time.monotonic()
    took = time.monotonic() - closing

    assert _started_since(before) == []
    assert took < 5
    assert capfd.readouterr().err == ""


def test_a_client_that_sends_nothing_cannot_hold_the_close(monkeypatch):
    monkeypatch.setattr(lb, "_HANDLER_TIMEOUT", 0.2)
    before = set(threading.enumerate())
    accepted, closed = threading.Event(), threading.Event()
    silent: list[socket.socket] = []

    def close_a_venue_holding_a_silent_client():
        with lb.serve() as venue:
            silent.append(_connect(venue))
            accepted.wait(5)
        closed.set()

    closer = threading.Thread(target=close_a_venue_holding_a_silent_client, daemon=True)
    closer.start()
    deadline = time.monotonic() + 5
    while (
        not (handling := any("process_request_thread" in name for name in _started_since(before))) and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    accepted.set()
    held = not closed.wait(5)
    for sock in silent:
        sock.close()
    closer.join(5)

    assert handling
    assert not held
