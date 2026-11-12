"""The vintage fetch's test doubles: a clock whose time moves only when told, and a fake HTTPS handler that sits under
urllib's real opener, so the redirect and header paths a test proves are the ones that ship; and the record builders,
one tick per call over a body per source, and the standard six-tick record."""

from __future__ import annotations

import contextlib
import http.client
import urllib.request
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

from cli.vintage.credential import ApiKey
from cli.vintage.fetch import Deadline
from cli.vintage.record import Published, record_tick
from cli.vintage.sources import ASSET_METRICS, SOURCE_BY_ID, SOURCES
from tests.vintage_fixtures import BASE_TICK_START, SENTINEL_KEY, body, dumps_compact, loads_tokens

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


_BG_VALUE_KEYS = {"bg-asopr": "asopr", "bg-sth-sopr": "sthSopr", "bg-lth-sopr": "lthSopr"}
_OWN_FIXTURE = ("cm-btc", "cm-dot", "cm-avaxc")


def _lines(data: bytes) -> list[dict]:
    return [loads_tokens(line) for line in data.split(b"\n") if line.strip()]


def _stream_like(base: bytes, rows: list[dict]) -> bytes:
    return b"\n".join(dumps_compact(row) for row in rows) + (b"\n" if base.endswith(b"\n") else b"")


def _cm_from_btc(asset: str) -> bytes:
    """`cm-btc`'s rows carrying the asset's pinned metrics alone; a `ReferenceRate*` btc lacks takes `ReferenceRate`'s token."""
    base = body("cm-btc")
    rows = []
    for row in _lines(base):
        out = {"asset": asset, "time": row["time"]}
        for metric in ASSET_METRICS[asset]:
            if metric in row:
                out[metric] = row[metric]
            elif metric.startswith("ReferenceRate") and "ReferenceRate" in row:
                out[metric] = row["ReferenceRate"]
        rows.append(out)
    return _stream_like(base, rows)


def _cm_avaxp() -> bytes:
    base = body("cm-avaxc")
    return _stream_like(base, [{**row, "asset": "avaxp"} for row in _lines(base)])


def _bg_renamed(value_key: str, data: bytes) -> bytes:
    return dumps_compact([{(value_key if k == "sopr" else k): v for k, v in row.items()} for row in loads_tokens(data)])


@cache
def _default_bodies() -> tuple[tuple[str, bytes], ...]:
    bodies = {}
    for source in SOURCES:
        if source.id in _BG_VALUE_KEYS:
            bodies[source.id] = _bg_renamed(_BG_VALUE_KEYS[source.id], body("bg-sopr"))
        elif source.id == "cm-avaxp":
            bodies[source.id] = _cm_avaxp()
        elif source.kind == "cm-asset" and source.id not in _OWN_FIXTURE:
            bodies[source.id] = _cm_from_btc(source.asset)
        else:
            bodies[source.id] = body(source.id)
    return tuple(bodies.items())


def default_bodies() -> dict[str, bytes]:
    """A body per source id, each meeting its check at `BASE_TICK_START`."""
    return dict(_default_bodies())


def _replies(items: Reply | bytes | BaseException | Sequence) -> list[Reply | BaseException]:
    if isinstance(items, (Reply, bytes, BaseException)):
        items = [items]
    return [Reply(200, item) if isinstance(item, bytes) else item for item in items]


def run_tick(
    data_dir: Path,
    at: datetime,
    replies: Mapping[str, Reply | bytes | BaseException | Sequence] | None = None,
    *,
    key: str | None = SENTINEL_KEY,
) -> Published:
    """One tick at `at`, every source answering 200 with its default body but where `replies` names its own."""
    clock = FakeClock(at)
    script = {SOURCE_BY_ID[source_id].url: [Reply(200, data)] for source_id, data in default_bodies().items()}
    for source_id, items in (replies or {}).items():
        script[SOURCE_BY_ID[source_id].url] = _replies(items)
    return record_tick(
        data_dir,
        key=None if key is None else ApiKey(key),
        key_reason="no credential" if key is None else None,
        clock_prom=None,
        https_handler=FakeHTTPS(script, clock),
        clock=clock,
        version="0.0.0",
        revision="",
    )


def build_record(data_dir: Path, plan: Sequence[tuple[datetime, Mapping]]) -> list[Published]:
    return [run_tick(data_dir, at, replies) for at, replies in plan]


STANDARD_HOURS = (0, 3, 7, 10, 18, 22)
# Each leg puts every body edited from the base before the one whose newer days the base would fall behind, so every
# body grades ok against the last ok body before it but cm-btc-metric-gone and bg-sopr-newest-back, graded 2 by design.
_STANDARD_LEGS = {
    "cm-btc": ("cm-btc", "cm-btc-restatement", "cm-btc-retraction", "cm-btc", "cm-btc-metric-gone", "cm-btc-next"),
    "bg": ("bg-sopr", "bg-sopr-restatement", "bg-sopr-newest-back", "bg-sopr", "bg-sopr-rolled", "bg-sopr-rolled"),
    "mempool-hashrate": ("mempool-hashrate", "mempool-hashrate-restated-big", *["mempool-hashrate"] * 4),
    "fng": ("fng", *["fng-next"] * 5),
}


def _leg_body(name: str) -> bytes:
    return body(name if name in SOURCE_BY_ID else f"second/{name}")


def standard_record(data_dir: Path) -> list[Published]:
    """Six ticks on `BASE_TICK_START`'s date at uneven gaps, each source's body along its leg, every other source its
    `default_bodies()` body."""
    plan = []
    for i, hours in enumerate(STANDARD_HOURS):
        replies = {source_id: _leg_body(leg[i]) for source_id, leg in _STANDARD_LEGS.items() if source_id != "bg"}
        bg = _leg_body(_STANDARD_LEGS["bg"][i])
        for source in SOURCES:
            if source.kind == "bg":
                replies[source.id] = _bg_renamed(_BG_VALUE_KEYS[source.id], bg) if source.id in _BG_VALUE_KEYS else bg
        plan.append((BASE_TICK_START + timedelta(hours=hours), replies))
    return build_record(data_dir, plan)
