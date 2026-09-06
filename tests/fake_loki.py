"""Test doubles for the Loki push endpoint."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer


def handler_factory(status_code: int = 200, location: str | None = None) -> type[BaseHTTPRequestHandler]:
    """Build a fresh request-handler class recording each POST/GET on its own `.requests`, with
    `.request_times` monotonic stamps beside it for measuring retry gaps. `.status_code` is a mutable
    CLASS attribute a test flips mid-run to script a server that fails then recovers; a closure would
    freeze the reply for the server's lifetime, and one shared class would leak `.requests`."""
    initial_status = status_code

    class _RecordingHandler(BaseHTTPRequestHandler):
        requests: list[tuple[str, dict, bytes]] = []
        request_times: list[float] = []
        status_code = initial_status

        def _record_and_respond(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            _RecordingHandler.request_times.append(time.monotonic())
            _RecordingHandler.requests.append((self.path, dict(self.headers), body))
            self.send_response(_RecordingHandler.status_code)
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
    """Accepts the TCP connection and then goes silent -- never reads, never responds -- so callers
    can exercise the client's read-timeout path."""
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
