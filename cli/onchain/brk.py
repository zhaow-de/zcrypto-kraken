"""The routes of the pinned BRK the on-chain writer reads: the series list, a series by UTC day, each height's monotonic
UTC day, a height's block hash, and the sync route's indexed height and node tip."""

from __future__ import annotations

import http.client
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

BITVIEW_URL = "http://zcrypto-onchain-bitview:3110"
DAY1_EPOCH = date(2009, 1, 1)
SERIES_PAGE = 1000
# BRK answers 400 to a read whose rows times its value's bytes pass `--maxweight`, 320,000 by default; a height's day
# is 2 bytes, so one read carries at most 160,000 heights. The page is held here, never by widening the host's cap.
HEIGHT_PAGE = 100_000
_BLOCK_HASH = re.compile(r"[0-9a-f]{64}")


class BrkError(Exception):
    """A route read that returns no value: the index unreached, or an answer the client refuses; its text names the
    route and the cause."""


def _field(body: object, key: str, route: str, kind: type) -> object:
    if not isinstance(body, dict) or key not in body:
        raise BrkError(f"{route}: the answer has no {key!r}")
    value = body[key]
    if type(value) is not kind:
        raise BrkError(f"{route}: {key!r} is not a {kind.__name__}")
    return value


def _value(value: object, route: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise BrkError(f"{route}: {value!r} is not a number")
    return float(value)


def _day(index: object, route: str) -> date:
    if type(index) is not int:
        raise BrkError(f"{route}: {index!r} is not a day index")
    return DAY1_EPOCH + timedelta(days=index)


@dataclass(frozen=True)
class BrkClient:
    base_url: str
    opener: urllib.request.OpenerDirector | None = None
    timeout: float = 30.0

    def _get(self, route: str, query: dict[str, object]) -> bytes:
        url = self.base_url.rstrip("/") + route + (f"?{urllib.parse.urlencode(query)}" if query else "")
        opener = urllib.request.build_opener() if self.opener is None else self.opener
        try:
            with opener.open(url, timeout=self.timeout) as response:
                if response.status != 200:
                    raise BrkError(f"{route}: HTTP {response.status}")
                return response.read()
        # `URLError` and `HTTPError` are `OSError`s; a read past the timeout raises `TimeoutError` unwrapped, and a
        # connection cut mid-answer an `http.client.HTTPException`.
        except (OSError, http.client.HTTPException) as exc:
            raise BrkError(f"{route}: {exc}") from exc

    def _json(self, route: str, query: dict[str, object]) -> object:
        body = self._get(route, query)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise BrkError(f"{route}: unparseable answer: {exc}") from exc

    def series_ids(self) -> frozenset[str]:
        route = "/api/series/list"
        ids: set[str] = set()
        page = 0
        while True:
            body = self._json(route, {"page": page, "per_page": SERIES_PAGE})
            names = _field(body, "series", route, list)
            if not all(type(name) is str for name in names):
                raise BrkError(f"{route}: a series id that is not a string")
            ids.update(names)
            if not _field(body, "has_more", route, bool):
                return frozenset(ids)
            if not names:
                raise BrkError(f"{route}: page {page} holds no series and has_more is true")
            page += 1

    def read_days(self, series_id: str, first: date, last: date) -> dict[date, float | None]:
        route = f"/api/series/{urllib.parse.quote(series_id, safe='')}/day1"
        body = self._json(route, {"start": first.isoformat(), "end": (last + timedelta(days=1)).isoformat()})
        start = _day(_field(body, "start", route, int), route)
        values = _field(body, "data", route, list)
        return {start + timedelta(days=offset): _value(value, route) for offset, value in enumerate(values)}

    def height_days(self, first: int, last: int) -> list[date]:
        route = "/api/series/block_day1/height"
        days: list[date] = []
        for start in range(first, last + 1, HEIGHT_PAGE):
            end = min(start + HEIGHT_PAGE, last + 1)
            body = self._json(route, {"start": start, "end": end})
            values = _field(body, "data", route, list)
            if _field(body, "start", route, int) != start or len(values) != end - start:
                raise BrkError(f"{route}: asked heights {start} to {end - 1}, answered {len(values)} heights")
            days.extend(_day(value, route) for value in values)
        return days

    def block_hash(self, height: int) -> str:
        route = f"/api/block-height/{height}"
        text = self._get(route, {}).decode("utf-8", "replace").strip()
        if not _BLOCK_HASH.fullmatch(text):
            raise BrkError(f"{route}: {text[:80]!r} is not a block hash")
        return text

    def _sync(self, key: str) -> int:
        route = "/api/server/sync"
        return _field(self._json(route, {}), key, route, int)

    def indexed_height(self) -> int:
        return self._sync("indexed_height")

    def node_tip(self) -> int:
        return self._sync("tip_height")
