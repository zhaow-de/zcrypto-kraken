"""Test doubles for the Loki push endpoint: a recording+scriptable fake server, and a silent
one that accepts the TCP connection and then does nothing (for read-timeout tests)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer


def handler_factory(status_code: int = 200, location: str | None = None) -> type[BaseHTTPRequestHandler]:
    """Build a fresh request-handler class: records each POST/GET's `(path, headers, body)` on
    its own `.requests` list and replies with the given status (+ `Location`, for redirect
    tests). A fresh class per call keeps `.requests` isolated between servers/tests."""

    class _RecordingHandler(BaseHTTPRequestHandler):
        requests: list[tuple[str, dict, bytes]] = []

        def _record_and_respond(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            _RecordingHandler.requests.append((self.path, dict(self.headers), body))
            self.send_response(status_code)
            if location is not None:
                self.send_header("Location", location)
            self.end_headers()

        def do_POST(self) -> None:
            self._record_and_respond()

        def do_GET(self) -> None:
            # A followed 302/303 redirect rewrites POST->GET; without this the follow would
            # 501 unrecorded, making "the second server saw nothing" a weak assertion.
            self._record_and_respond()

        def log_message(self, format: str, *args) -> None:
            pass  # silence the default per-request stderr line; tests assert on .requests instead

    return _RecordingHandler


@contextmanager
def FakeLoki(handler_cls: type[BaseHTTPRequestHandler] | None = None) -> Iterator[str]:
    """Threaded HTTP server on an OS-assigned port. Pass a `handler_factory(...)` class to
    script a status/redirect and read back recorded requests; omit it for a plain 200 OK sink."""
    server = HTTPServer(("127.0.0.1", 0), handler_cls or handler_factory())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@contextmanager
def SilentServer() -> Iterator[str]:
    """Accepts the TCP connection and then goes silent -- never reads, never responds -- so
    callers can exercise the client's read-timeout path. Closes all held connections on exit."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = sock.getsockname()[1]
    stop = threading.Event()
    conns: list[socket.socket] = []

    def _accept_forever() -> None:
        sock.settimeout(0.1)
        while not stop.is_set():
            try:
                conn, _addr = sock.accept()
            except TimeoutError:
                continue
            conns.append(conn)  # held open, untouched -- silence is the point

    thread = threading.Thread(target=_accept_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        stop.set()
        thread.join()
        for conn in conns:
            conn.close()
        sock.close()
