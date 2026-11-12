"""The vintage fetch's test doubles: a clock whose time moves only when told, and a fake HTTPS handler that sits under
urllib's real opener, so the redirect and header paths a test proves are the ones that ship."""

from __future__ import annotations

import contextlib
import http.client
import urllib.request
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from cli.vintage.fetch import Deadline

STALL_SECONDS = 3000.0


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self._start = start
        self._elapsed = 0.0
        self.slept: list[float] = []
        self.armed: list[float] = []
        self.alarm: float | None = None

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._elapsed)

    def monotonic(self) -> float:
        return self._elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self._elapsed += seconds

    def advance(self, seconds: float) -> None:
        self._elapsed += seconds

    @contextlib.contextmanager
    def watchdog(self, seconds: float):
        self.armed.append(seconds)
        self.alarm = self.monotonic() + seconds
        try:
            yield
        finally:
            self.alarm = None

    def stall(self) -> None:
        """A call that never returns: the open watchdog's alarm ends it, or, with none open, it returns 3,000 s later."""
        if self.alarm is not None:
            self._elapsed = max(self._elapsed, self.alarm)
            raise Deadline
        self.advance(STALL_SECONDS)


@dataclass
class Reply:
    status: int = 200
    body: bytes = b""
    headers: Sequence[tuple[str, str]] = ()
    reason: str = "OK"
    chunk_seconds: float = 0.0
    chunk_bytes: int = 65536
    stall_after: int | None = None
    stall_open: bool = False


@dataclass
class Seen:
    url: str
    headers: dict
    unredirected: dict
    timeout: float | None


class _Response:
    def __init__(self, reply: Reply, url: str, clock: FakeClock) -> None:
        self.status = self.code = reply.status
        self.reason = self.msg = reply.reason
        self.version = 11
        self.headers = http.client.HTTPMessage()
        for name, value in reply.headers:
            self.headers[name] = value
        self.url = url
        self._clock = clock
        self._chunk_seconds = reply.chunk_seconds
        self._chunks = deque(reply.body[at : at + reply.chunk_bytes] for at in range(0, len(reply.body), reply.chunk_bytes))
        self._stall_after = reply.stall_after
        self._position = 0

    def info(self) -> http.client.HTTPMessage:
        return self.headers

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        pass

    def _rest(self) -> bytes:
        rest = b"".join(self._chunks)
        self._chunks.clear()
        self._position += len(rest)
        return rest

    def read1(self, n: int = -1) -> bytes:
        if self._stall_after is not None and self._position >= self._stall_after:
            self._stall_after = None
            self._clock.stall()
            return self._rest()
        if not self._chunks:
            return b""
        chunk = self._chunks.popleft()
        size = len(chunk) if n is None or n < 0 else n
        if self._stall_after is not None:
            size = min(size, self._stall_after - self._position)
        if size < len(chunk):
            self._chunks.appendleft(chunk[size:])
            chunk = chunk[:size]
        self._clock.advance(self._chunk_seconds)
        self._position += len(chunk)
        return chunk

    def read(self, n: int | None = -1) -> bytes:
        want = None if n is None or n < 0 else n
        out = bytearray()
        while want is None or len(out) < want:
            chunk = self.read1(-1 if want is None else want - len(out))
            if not chunk:
                break
            out += chunk
        return bytes(out)


class FakeHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, script: Mapping[str, Sequence[Reply | BaseException]], clock: FakeClock) -> None:
        super().__init__()
        self._script = {url: deque(items) for url, items in script.items()}
        self._clock = clock
        self.seen: list[Seen] = []

    def https_open(self, req: urllib.request.Request) -> _Response:
        url = req.full_url
        self.seen.append(Seen(url, dict(req.headers), dict(req.unredirected_hdrs), getattr(req, "timeout", None)))
        queue = self._script.get(url)
        if not queue:
            raise AssertionError(f"no reply scripted for {url}")
        item = queue.popleft()
        if isinstance(item, BaseException):
            raise item
        if item.stall_open:
            self._clock.stall()
        return _Response(item, url, self._clock)
