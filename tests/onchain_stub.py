"""A fake BRK under urllib's real opener, serving the five routes the on-chain client reads over a scripted chain, and
holding BRK's weight cap, so the status and paging paths a test proves are the ones that ship."""

from __future__ import annotations

import http.client
import io
import json
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from http import HTTPStatus
from urllib.parse import parse_qs, urlsplit

from cli.onchain.brk import BITVIEW_URL, DAY1_EPOCH, BrkClient

# BRK's default `--maxweight`: a read whose rows times its value's bytes pass it is answered 400.
MAX_WEIGHT = 320_000
HEIGHT_DAY_BYTES = 2
DAY_VALUE_BYTES = 8
MAX_PER_PAGE = 1000


@dataclass(frozen=True)
class Answer:
    status: int
    body: bytes
    content_type: str = "application/json"


def _json(value: object) -> Answer:
    return Answer(200, json.dumps(value).encode())


def _error(status: int, text: str) -> Answer:
    return Answer(status, text.encode(), "text/plain")


def _ints(query: dict[str, list[str]], *names: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(query[name][0]) for name in names)
    except KeyError, ValueError:
        return None


def _dates(query: dict[str, list[str]], *names: str) -> tuple[date, ...] | None:
    try:
        return tuple(date.fromisoformat(query[name][0]) for name in names)
    except KeyError, ValueError:
        return None


def _day1(day: date) -> int:
    return (day - DAY1_EPOCH).days


class FakeBrk(urllib.request.HTTPHandler):
    """Every attribute may be changed between calls. `days[h]` and `hashes[h]` are height h's monotonic UTC day and
    block hash; `series` maps a series id to its value by day, a planted `None` served `null`; `ids` is the series
    list, the series' own ids when `None`; `planted` maps a path to the answer served in place of the route's; with
    `unreachable`, every request fails as a refused connection does."""

    def __init__(
        self,
        *,
        days: Sequence[date] = (),
        hashes: Sequence[str] | None = None,
        series: Mapping[str, Mapping[date, float | None]] | None = None,
        ids: Sequence[str] | None = None,
        indexed_height: int = 0,
        tip_height: int = 0,
    ) -> None:
        super().__init__()
        self.days = list(days)
        self.hashes = [f"{height:064x}" for height in range(len(self.days))] if hashes is None else list(hashes)
        self.series = {series_id: dict(values) for series_id, values in (series or {}).items()}
        self.ids = None if ids is None else list(ids)
        self.indexed_height = indexed_height
        self.tip_height = tip_height
        self.planted: dict[str, Answer] = {}
        self.unreachable = False
        self.seen: list[str] = []

    def http_open(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        url = req.full_url
        self.seen.append(url)
        if self.unreachable:
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))
        parts = urlsplit(url)
        answer = self.planted.get(parts.path) or self._route(parts.path, parse_qs(parts.query))
        headers = http.client.HTTPMessage()
        headers["Content-Type"] = answer.content_type
        response = urllib.response.addinfourl(io.BytesIO(answer.body), headers, url, answer.status)
        response.msg = HTTPStatus(answer.status).phrase
        return response

    def _route(self, path: str, query: dict[str, list[str]]) -> Answer:
        segments = path.strip("/").split("/")
        match segments:
            case ["api", "series", "list"]:
                return self._series_list(query)
            case ["api", "series", "block_day1", "height"]:
                return self._height_days(query)
            case ["api", "series", series_id, "day1"] if series_id in self.series:
                return self._series_days(self.series[series_id], query)
            case ["api", "block-height", height] if height.isdigit() and int(height) < len(self.hashes):
                return Answer(200, self.hashes[int(height)].encode(), "text/plain")
            case ["api", "server", "sync"]:
                return _json({"indexed_height": self.indexed_height, "tip_height": self.tip_height})
        return _error(404, f"not found: {path}")

    def _series_list(self, query: dict[str, list[str]]) -> Answer:
        asked = _ints(query, "page", "per_page")
        if asked is None:
            return _error(400, "page and per_page")
        page, per_page = asked[0], min(asked[1], MAX_PER_PAGE)
        ids = sorted(self.series) if self.ids is None else self.ids
        max_page = max(0, (len(ids) - 1) // per_page)
        return _json(
            {
                "current_page": page,
                "max_page": max_page,
                "total_count": len(ids),
                "per_page": per_page,
                "has_more": page < max_page,
                "series": ids[page * per_page : (page + 1) * per_page],
            }
        )

    def _height_days(self, query: dict[str, list[str]]) -> Answer:
        asked = _ints(query, "start", "end")
        if asked is None:
            return _error(400, "start and end")
        start, end = asked[0], min(asked[1], len(self.days))
        if (end - start) * HEIGHT_DAY_BYTES > MAX_WEIGHT:
            return _error(400, "WeightExceeded")
        data = [_day1(day) for day in self.days[start:end]]
        return _json({"index": "height", "start": start, "end": end, "data": data})

    def _series_days(self, values: Mapping[date, float | None], query: dict[str, list[str]]) -> Answer:
        asked = _dates(query, "start", "end")
        if asked is None:
            return _error(400, "start and end")
        start = _day1(asked[0])
        end = min(_day1(asked[1]), _day1(max(values)) + 1) if values else start
        if (end - start) * DAY_VALUE_BYTES > MAX_WEIGHT:
            return _error(400, "WeightExceeded")
        data = [values.get(DAY1_EPOCH + timedelta(days=index)) for index in range(start, end)]
        return _json({"index": "day1", "start": start, "end": max(start, end), "data": data})


def fake_client(fake: FakeBrk) -> BrkClient:
    return BrkClient(BITVIEW_URL, opener=urllib.request.build_opener(fake))
