"""The vintage exchange: the retries and their waits, the breakers, the deadlines and the size cap, the keyed host's
budget rules, and the key's one path, over urllib's real openers with a fake HTTPS handler beneath them."""

from __future__ import annotations

import gzip
import io
import signal
import socket
import threading
import time
import urllib.request
import zlib
from compression import zstd
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from urllib.error import URLError

import pytest

from cli.vintage.credential import ApiKey, decode_for_scan, holds_key, key_forms, read_key
from cli.vintage.fetch import REDACTED_AUTHORIZATION, Deadline, SystemClock, build_openers, fetch_all, header
from cli.vintage.sources import SOURCE_BY_ID, SOURCES
from tests.vintage_fixtures import SENTINEL_FORMS, SENTINEL_KEY, body
from tests.vintage_stub import FakeClock, FakeHTTPS, Reply

START = datetime(2026, 11, 11, 7, 37, tzinfo=UTC)
USER_AGENT = "zcrypto-vintage/test"
KEY = ApiKey(SENTINEL_KEY)
KEYED_HOST = "api.bitcoin-data.com"
KEYED_IDS = ("bg-sopr", "bg-asopr", "bg-sth-sopr", "bg-lth-sopr")
CM_SOURCES = tuple(source for source in SOURCES if source.host == "community-api.coinmetrics.io")


def _default_body(source) -> bytes:
    if source.kind == "bg":
        return body("bg-sopr")
    if source.kind == "cm-asset":
        return body("cm-btc")
    return body(source.id)


def _run(overrides=None, *, sources=SOURCES, key=KEY, key_reason=None, tick_deadline=1200.0, only=None, handler=FakeHTTPS):
    clock = FakeClock(START)
    script = {source.url: [Reply(200, _default_body(source))] for source in sources}
    for source_id, items in (overrides or {}).items():
        script[SOURCE_BY_ID[source_id].url] = items
    https = handler(script, clock)
    exchanges = fetch_all(
        sources,
        key=key,
        key_reason=key_reason,
        openers=build_openers(https),
        clock=clock,
        tick_deadline=tick_deadline,
        user_agent=USER_AGENT,
        only=only,
    )
    assert [exchange.source for exchange in exchanges] == list(sources)
    return {exchange.source.id: exchange for exchange in exchanges}, https, clock


def _urls(https) -> list[str]:
    return [seen.url for seen in https.seen]


def _url(source_id: str) -> str:
    return SOURCE_BY_ID[source_id].url


def _http_date(seconds: float) -> str:
    return format_datetime(START + timedelta(seconds=seconds), usegmt=True)


def _echo(form: bytes) -> bytes:
    return b'[{"d":"2026-11-10","note":"' + form + b'"}]'


@pytest.mark.parametrize(
    ("source_id", "replies", "slept"),
    [
        ("fng", [Reply(503, b"busy", [("Retry-After", "7")]), Reply(200, b"ok")], [7]),
        ("fng", [Reply(503, b"busy", [("Retry-After", "900")]), Reply(200, b"ok")], [300]),
        ("fng", [Reply(503, b"busy", [("Retry-After", _http_date(40))]), Reply(200, b"ok")], [40]),
        ("fng", [Reply(503, b"busy"), Reply(503, b"busy"), Reply(200, b"ok")], [30, 120]),
        ("cm-btc", [Reply(429, b"slow down", [("Retry-After", "7")]), Reply(200, b"ok")], [7]),
    ],
    ids=["seconds", "capped", "http-date", "none", "429"],
)
def test_retry_after_is_honoured_and_capped(source_id, replies, slept):
    exchanges, _, clock = _run({source_id: replies}, sources=[SOURCE_BY_ID[source_id]])
    exchange = exchanges[source_id]
    assert exchange.not_fetched is None
    assert (exchange.status, exchange.body) == (200, b"ok")
    assert clock.slept == slept


@pytest.mark.parametrize(
    "failure", [lambda: TimeoutError("timed out"), lambda: URLError(TimeoutError("timed out"))], ids=["raw", "wrapped"]
)
def test_a_socket_timeout_is_retried_and_named(failure):
    fng = [SOURCE_BY_ID["fng"]]
    exchanges, _, _ = _run({"fng": [failure(), failure(), failure()]}, sources=fng)
    assert exchanges["fng"].not_fetched == "timeout after 3 attempts"
    assert [attempt.status for attempt in exchanges["fng"].attempts] == [None, None, None]
    assert all(attempt.error for attempt in exchanges["fng"].attempts)

    exchanges, _, _ = _run({"fng": [failure(), failure(), Reply(200, b"ok")]}, sources=fng)
    assert exchanges["fng"].not_fetched is None
    assert exchanges["fng"].body == b"ok"
    assert len(exchanges["fng"].attempts) == 3


@pytest.mark.parametrize(
    "value",
    ["0", "-5", _http_date(-60), "soon", "9" * 5000, "\x1f0", "\x1c0", "\x1e0"],
    ids=["zero", "negative", "past-date", "unparseable", "too-many-digits", "x1f", "x1c", "x1e"],
)
def test_a_retry_after_in_the_past_or_unparseable_falls_back(value):
    busy = Reply(503, b"busy", [("Retry-After", value)])
    exchanges, _, clock = _run({"fng": [busy, busy, Reply(200, b"ok")]}, sources=[SOURCE_BY_ID["fng"]])
    assert exchanges["fng"].not_fetched is None
    assert clock.slept == [30, 120]


@pytest.mark.parametrize(
    ("source_id", "status", "fixture"),
    [("cm-btc", 403, "second/cm-btc-403"), ("bg-sopr", 404, "second/bg-sopr-404"), ("fng", 404, None)],
    ids=["cm-btc-403", "bg-sopr-404", "fng-404"],
)
def test_a_403_or_404_is_never_retried(source_id, status, fixture):
    served = body(fixture) if fixture is not None else b"404 page not found"
    exchanges, https, _ = _run({source_id: [Reply(status, served, reason="Refused")]}, sources=[SOURCE_BY_ID[source_id]])
    exchange = exchanges[source_id]
    assert len(exchange.attempts) == 1
    assert len(https.seen) == 1
    assert exchange.status == status
    assert exchange.body == served
    assert exchange.not_fetched == f"HTTP {status} (no retry)"


def test_a_non_2xx_final_answer_is_kept_whole():
    bodies = [bytes([ord("a") + n]) * 5000 for n in range(3)]
    exchanges, _, _ = _run({"fng": [Reply(503, served) for served in bodies]}, sources=[SOURCE_BY_ID["fng"]])
    exchange = exchanges["fng"]
    assert exchange.not_fetched == "HTTP 503 after 3 attempts"
    assert exchange.status == 503
    assert exchange.body == bodies[2]
    assert [attempt.head for attempt in exchange.attempts] == [bodies[0][:4096], bodies[1][:4096], None]


def test_a_retried_attempt_keeps_its_first_4_kib():
    served = bytes(range(256)) * 40
    exchanges, _, _ = _run({"fng": [Reply(503, served), Reply(200, b"ok")]}, sources=[SOURCE_BY_ID["fng"]])
    attempts = exchanges["fng"].attempts
    assert attempts[0].head == served[:4096]
    assert attempts[1].head is None


def _refused():
    return URLError(ConnectionRefusedError(111, "Connection refused"))


@pytest.mark.parametrize(
    ("first", "reason", "tripped"),
    [
        ([_refused(), _refused(), _refused()], "transport error after 3 attempts", "host"),
        ([Reply(503, b"down"), Reply(503, b"down"), Reply(503, b"down")], "HTTP 503 after 3 attempts", "endpoint"),
        ([Reply(429, b"slow"), Reply(429, b"slow"), Reply(429, b"slow")], "HTTP 429 after 3 attempts", "endpoint"),
        ([Reply(503, b"down"), Reply(200, b"ok")], None, None),
    ],
    ids=["transport", "503", "429", "recovered"],
)
def test_the_breaker(first, reason, tripped):
    exchanges, https, _ = _run({"cm-btc": first}, sources=CM_SOURCES)
    assert exchanges["cm-btc"].not_fetched == reason
    later_assets = [source.id for source in CM_SOURCES[1:-1]]
    assert len(later_assets) == 9
    btc = [_url("cm-btc")] * len(first)
    if tripped is None:
        assert _urls(https) == btc + [source.url for source in CM_SOURCES[1:]]
        assert all(exchanges[source_id].not_fetched is None for source_id in [*later_assets, "cm-catalog"])
        return
    for source_id in later_assets:
        assert exchanges[source_id].not_fetched == "breaker"
        assert exchanges[source_id].attempts == []
    if tripped == "host":
        assert exchanges["cm-catalog"].not_fetched == "breaker"
        assert _urls(https) == btc
    else:
        assert exchanges["cm-catalog"].not_fetched is None
        assert _urls(https) == [*btc, _url("cm-catalog")]


def test_the_body_deadline_cuts_a_trickle():
    trickle = Reply(200, b"0123456789" * 100, chunk_bytes=10, chunk_seconds=30)
    exchanges, _, _ = _run({"fng": [trickle]}, sources=[SOURCE_BY_ID["fng"]])
    exchange = exchanges["fng"]
    attempt = exchange.attempts[0]
    assert exchange.body is None
    assert attempt.withheld[0] == "body deadline"
    assert attempt.withheld[1] <= 50
    assert attempt.duration_seconds <= 150
    assert exchange.not_fetched == f"body deadline {attempt.withheld[1]}"

    clock = FakeClock(START)
    plain, _ = build_openers(FakeHTTPS({_url("fng"): [trickle]}, clock))
    response = plain.open(_url("fng"), timeout=30)
    assert len(response.read(65536)) == 1000
    assert clock.monotonic() == 3000


@pytest.mark.parametrize(
    ("reply", "tick_deadline", "withheld", "duration"),
    [
        (Reply(200, body("fng"), stall_after=10), 1200.0, ("body deadline", 10), 120),
        (Reply(200, body("fng"), stall_open=True), 1200.0, ("body deadline", 0), 120),
        (Reply(200, body("fng"), stall_open=True), 50.0, ("tick deadline", 0), 50),
    ],
    ids=["read", "open", "open-past-the-tick-deadline"],
)
def test_a_call_that_never_returns_ends_at_the_watchdog(reply, tick_deadline, withheld, duration):
    sources = [SOURCE_BY_ID["fng"], SOURCE_BY_ID["mempool-hashrate"]]
    exchanges, https, clock = _run({"fng": [reply]}, sources=sources, tick_deadline=tick_deadline)
    fng = exchanges["fng"]
    assert fng.body is None
    assert [attempt.withheld for attempt in fng.attempts] == [withheld]
    assert fng.attempts[0].duration_seconds == duration
    assert clock.armed[0] == duration
    assert clock.alarm is None
    if withheld[0] == "tick deadline":
        assert fng.not_fetched == "tick deadline"
        assert exchanges["mempool-hashrate"].not_fetched == "tick deadline"
        assert _urls(https) == [_url("fng")]
    else:
        assert fng.not_fetched == f"body deadline {withheld[1]}"


def _trickle_server(prefix: bytes, byte: bytes, stop: threading.Event) -> tuple[socket.socket, threading.Thread]:
    server = socket.create_server(("127.0.0.1", 0))

    def serve() -> None:
        try:
            connection, _ = server.accept()
        except OSError:
            return
        with connection:
            try:
                connection.recv(65536)
                connection.sendall(prefix)
                until = time.monotonic() + 5
                while not stop.is_set() and time.monotonic() < until:
                    connection.sendall(byte)
                    time.sleep(0.1)
            except OSError:
                return

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return server, thread


_CHUNKED_HEAD = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"


@pytest.mark.parametrize(
    ("prefix", "byte"),
    [(_CHUNKED_HEAD, b"f"), (_CHUNKED_HEAD + b"0\r\n", b"X"), (b"HTTP/1.1 200 ", b"K"), (None, None)],
    ids=["chunk-size-line", "trailer", "status-line", "left-at-once"],
)
def test_the_system_watchdog_ends_a_trickled_framing_read(prefix, byte):
    previous = signal.getsignal(signal.SIGALRM)
    if prefix is None:
        try:
            with SystemClock().watchdog(5):
                pass
            assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
            assert signal.getsignal(signal.SIGALRM) == previous
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        return
    stop = threading.Event()
    server, thread = _trickle_server(prefix, byte, stop)
    url = f"http://127.0.0.1:{server.getsockname()[1]}/"
    loopback = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        started = time.monotonic()
        with pytest.raises(Deadline):
            with SystemClock().watchdog(0.5):
                response = loopback.open(url, timeout=30)
                while response.read1(65536):
                    pass
        assert time.monotonic() - started < 2
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
        assert signal.getsignal(signal.SIGALRM) == previous
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        stop.set()
        server.close()
        thread.join(timeout=10)


def test_a_late_alarm_still_restores_the_handler(monkeypatch):
    previous = signal.getsignal(signal.SIGALRM)
    setitimer = signal.setitimer

    def alarm_at_the_disarm(which, seconds, *interval):
        result = setitimer(which, seconds, *interval)
        if seconds == 0:
            raise Deadline
        return result

    monkeypatch.setattr(signal, "setitimer", alarm_at_the_disarm)
    try:
        with pytest.raises(Deadline):
            with SystemClock().watchdog(5):
                pass
        assert signal.getsignal(signal.SIGALRM) == previous
    finally:
        setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class _CreepingClock(FakeClock):
    def monotonic(self) -> float:
        now = super().monotonic()
        self.advance(1.0)
        return now


def test_the_watchdog_is_armed_with_the_tick_left_its_dial_was_checked_against():
    clock = _CreepingClock(START)
    https = FakeHTTPS({_url("fng"): [Reply(200, b"ok")]}, clock)
    fetch_all(
        [SOURCE_BY_ID["fng"]],
        key=None,
        key_reason=None,
        openers=build_openers(https),
        clock=clock,
        tick_deadline=1.5,
        user_agent=USER_AGENT,
    )
    assert clock.armed == [1.5]


def test_the_tick_deadline():
    slow = Reply(200, b"ok", chunk_seconds=5)
    exchanges, https, clock = _run({"fng": [slow]}, tick_deadline=8.0)
    assert clock.monotonic() == 8.0
    assert exchanges["fng"].not_fetched is None
    assert _urls(https) == [*(_url(source_id) for source_id in KEYED_IDS), _url("fng")]
    for source in SOURCES[5:]:
        assert exchanges[source.id].not_fetched == "tick deadline"
        assert exchanges[source.id].attempts == []
        assert exchanges[source.id].request_headers == []

    busy = [Reply(503, b"busy", [("Retry-After", "300")]) for _ in range(3)]
    exchanges, https, clock = _run({"fng": busy}, sources=SOURCES[4:], tick_deadline=400.0)
    assert exchanges["fng"].not_fetched == "tick deadline"
    assert len(exchanges["fng"].attempts) == 2
    assert exchanges["fng"].request_headers == [("Accept-Encoding", "identity"), ("User-Agent", USER_AGENT)]
    assert clock.monotonic() == 400.0
    assert _urls(https) == [_url("fng")] * 2
    assert all(exchanges[source.id].not_fetched == "tick deadline" for source in SOURCES[5:])


def test_the_size_cap():
    size = 64 * 1024 * 1024 + 1
    exchanges, _, _ = _run({"fng": [Reply(200, b"x" * size)]}, sources=[SOURCE_BY_ID["fng"]])
    exchange = exchanges["fng"]
    assert exchange.body is None
    assert exchange.attempts[0].withheld == ("oversize", size)
    assert exchange.not_fetched == f"oversize {size}"


class _TimedHTTPS(FakeHTTPS):
    def __init__(self, script, clock):
        super().__init__(script, clock)
        self.dialled: list[tuple[str, float]] = []

    def https_open(self, req):
        self.dialled.append((req.host, self._clock.monotonic()))
        return super().https_open(req)


def test_requests_to_a_host_are_a_second_apart_and_ask_identity():
    exchanges, https, _ = _run(handler=_TimedHTTPS)
    assert len(https.seen) == len(SOURCES)
    for seen in https.seen:
        assert seen.headers == {"Accept-encoding": "identity", "User-agent": USER_AGENT}
        assert seen.timeout == 30
        if seen.url.startswith(f"https://{KEYED_HOST}/"):
            assert seen.unredirected["Authorization"] == f"Bearer {SENTINEL_KEY}"
        else:
            assert "Authorization" not in seen.unredirected
    last: dict[str, float] = {}
    for host, at in https.dialled:
        if host in last:
            assert at - last[host] >= 1
        last[host] = at
    assert all(exchange.not_fetched is None for exchange in exchanges.values())


def test_set_cookie_is_dropped_and_duplicates_are_kept():
    headers = [
        ("Set-Cookie", "a=1"),
        ("X-Seen", "1"),
        ("Content-Type", "application/json"),
        ("set-cookie", "b=2"),
        ("x-seen", "2"),
    ]
    exchanges, _, _ = _run({"fng": [Reply(200, b"ok", headers)]}, sources=[SOURCE_BY_ID["fng"]])
    assert exchanges["fng"].headers == [("X-Seen", "1"), ("Content-Type", "application/json"), ("x-seen", "2")]


def test_the_keyed_requests_run_first():
    _, https, _ = _run()
    assert _urls(https)[:4] == [_url(source_id) for source_id in KEYED_IDS]


def test_a_source_outside_only_is_never_dialled():
    exchanges, https, _ = _run(only=frozenset({"cm-eth", "fng"}))
    assert _urls(https) == [_url("fng"), _url("cm-eth")]
    assert exchanges["fng"].not_fetched is None
    assert exchanges["cm-eth"].not_fetched is None
    others = [exchange for source_id, exchange in exchanges.items() if source_id not in {"cm-eth", "fng"}]
    assert len(others) == 16
    for exchange in others:
        assert exchange.not_fetched == "not selected"
        assert exchange.attempts == []


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(lambda: Reply(503, b"down"), "HTTP 503 after 1 attempts"), (_refused, "transport error after 1 attempts")],
    ids=["503", "transport"],
)
def test_one_retry_per_tick_on_the_keyed_host(failure, reason):
    overrides = {"bg-sopr": [failure(), Reply(200, b"[]")], "bg-asopr": [failure()]}
    exchanges, https, clock = _run(overrides, sources=SOURCES[:4])
    assert exchanges["bg-sopr"].not_fetched is None
    assert len(exchanges["bg-sopr"].attempts) == 2
    assert clock.slept[0] == 30
    assert exchanges["bg-asopr"].not_fetched == reason
    assert len(exchanges["bg-asopr"].attempts) == 1
    assert _urls(https).count(_url("bg-asopr")) == 1
    assert exchanges["bg-sth-sopr"].not_fetched is None
    assert exchanges["bg-lth-sopr"].not_fetched is None


@pytest.mark.parametrize(
    "reply",
    [
        Reply(429, body("second/bg-sopr-429"), [("X-RateLimit-Remaining-Day", "3")], reason="Too Many Requests"),
        Reply(401, b'{"status":401,"error":"Unauthorized"}', reason="Unauthorized"),
        Reply(403, b'{"status":403,"error":"Forbidden"}', reason="Forbidden"),
    ],
    ids=["429", "401", "403"],
)
def test_a_429_401_or_403_on_the_keyed_host_trips_its_breaker(reply):
    exchanges, https, _ = _run({"bg-sopr": [reply]})
    assert exchanges["bg-sopr"].not_fetched == f"HTTP {reply.status} (no retry)"
    assert len(exchanges["bg-sopr"].attempts) == 1
    assert exchanges["bg-sopr"].body == reply.body
    for source_id in KEYED_IDS[1:]:
        assert exchanges[source_id].not_fetched == f"breaker (HTTP {reply.status})"
        assert exchanges[source_id].attempts == []
    assert [url for url in _urls(https) if KEYED_HOST in url] == [_url("bg-sopr")]
    assert exchanges["fng"].not_fetched is None


@pytest.mark.parametrize(
    ("name", "value", "stops"),
    [
        ("X-RateLimit-Remaining-Day", "0", True),
        ("X-RateLimit-Remaining-Hour", "0", True),
        ("x-ratelimit-remaining-day", "0", True),
        ("X-RateLimit-Remaining-Day", "soon", False),
        ("X-RateLimit-Remaining-Day", "0" * 5000, False),
        ("X-RateLimit-Remaining-Day", "\x1f0", True),
        ("X-RateLimit-Remaining-Day", "\x1c0", True),
        ("X-RateLimit-Remaining-Day", "\x1e0", True),
    ],
    ids=["day", "hour", "lower-case", "not-a-number", "too-many-digits", "x1f", "x1c", "x1e"],
)
def test_a_remaining_header_at_zero_stops_the_keyed_host(name, value, stops):
    served = body("bg-sopr")
    exchanges, https, _ = _run({"bg-sopr": [Reply(200, served, [(name, value)])]})
    assert exchanges["bg-sopr"].not_fetched is None
    assert exchanges["bg-sopr"].body == served
    for source_id in KEYED_IDS[1:]:
        if stops:
            assert exchanges[source_id].not_fetched == "budget exhausted"
            assert exchanges[source_id].attempts == []
        else:
            assert exchanges[source_id].not_fetched is None
    assert len([url for url in _urls(https) if KEYED_HOST in url]) == (1 if stops else 4)


def test_a_remaining_header_at_zero_stops_a_keyed_retry():
    spent = Reply(503, b"down", [("X-RateLimit-Remaining-Day", "0")])
    exchanges, https, _ = _run({"bg-sopr": [spent, Reply(200, b"[]")]}, sources=SOURCES[:4])
    assert exchanges["bg-sopr"].not_fetched == "HTTP 503 after 1 attempts"
    assert len(exchanges["bg-sopr"].attempts) == 1
    for source_id in KEYED_IDS[1:]:
        assert exchanges[source_id].not_fetched == "budget exhausted"
    assert _urls(https) == [_url("bg-sopr")]


def test_header_joins_every_field_line_of_a_name_in_any_case():
    pairs = [("Content-Encoding", "gzip"), ("Date", "Thu, 12 Nov 2026 07:37:03 GMT"), ("content-encoding", "br")]
    assert header(pairs, "CONTENT-ENCODING") == "gzip, br"
    assert header(pairs, "Retry-After") is None


def test_a_repeated_remaining_header_is_read_whole():
    headers = [("X-RateLimit-Remaining-Day", "3"), ("X-RateLimit-Remaining-Day", "0")]
    exchanges, https, _ = _run({"bg-sopr": [Reply(200, body("bg-sopr"), headers)]})
    for source_id in KEYED_IDS[1:]:
        assert exchanges[source_id].not_fetched == "budget exhausted"
    assert [url for url in _urls(https) if KEYED_HOST in url] == [_url("bg-sopr")]


def test_a_keyed_request_follows_no_redirect():
    moved = Reply(302, b"moved", [("Location", "https://elsewhere.example/v1/sopr")], reason="Found")
    exchanges, https, _ = _run({"bg-sopr": [moved]}, sources=[SOURCE_BY_ID["bg-sopr"]])
    exchange = exchanges["bg-sopr"]
    assert exchange.status == 302
    assert exchange.body == b"moved"
    assert exchange.final_url == _url("bg-sopr")
    assert exchange.not_fetched == "HTTP 302 redirect not followed"
    assert _urls(https) == [_url("bg-sopr")]


def test_the_key_rides_an_unredirected_header_alone():
    exchanges, https, _ = _run(sources=[SOURCE_BY_ID["bg-sopr"]])
    [seen] = https.seen
    assert seen.unredirected["Authorization"] == f"Bearer {SENTINEL_KEY}"
    assert "Authorization" not in seen.headers
    assert not any(SENTINEL_KEY in value for value in seen.headers.values())
    assert not any(form.decode() in seen.url for form in SENTINEL_FORMS)
    assert REDACTED_AUTHORIZATION == ("Authorization", "Bearer <redacted>")
    assert ("Authorization", "Bearer <redacted>") in exchanges["bg-sopr"].request_headers
    assert not any(SENTINEL_KEY in value for _, value in exchanges["bg-sopr"].request_headers)


@pytest.mark.parametrize("reason", ["no credential", "malformed credential"])
def test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host(reason):
    exchanges, https, _ = _run(key=None, key_reason=reason)
    for source_id in KEYED_IDS:
        assert exchanges[source_id].not_fetched == reason
        assert exchanges[source_id].attempts == []
    assert not [url for url in _urls(https) if KEYED_HOST in url]
    assert all(exchange.not_fetched is None for source_id, exchange in exchanges.items() if source_id not in KEYED_IDS)


class _Unreadable:
    def read(self) -> bytes:
        raise OSError("unreadable")


def test_read_key():
    key, reason = read_key(io.BytesIO(SENTINEL_KEY.encode() + b"\n"))
    assert reason is None
    assert key.reveal() == SENTINEL_KEY
    assert str(key) == repr(key) == "<redacted>"
    for stream in (io.BytesIO(b""), None, _Unreadable()):
        assert read_key(stream) == (None, "no credential")
    assert read_key(io.BytesIO(b"two words\n")) == (None, "malformed credential")


def _raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def test_the_scan_reads_every_form_and_every_decodable_encoding():
    assert key_forms(KEY) == SENTINEL_FORMS
    for form in SENTINEL_FORMS:
        assert holds_key(b"before " + form + b" after", SENTINEL_FORMS)
    assert not holds_key(b"nothing here", SENTINEL_FORMS)

    payload = b'{"sopr":"1.0"}' * 50
    echo = _echo(SENTINEL_FORMS[0])
    decodable = {
        None: payload,
        "identity": payload,
        "gzip": gzip.compress(payload),
        "deflate": zlib.compress(payload),
        "zstd": zstd.compress(payload),
        "gzip, zstd": zstd.compress(gzip.compress(payload)),
    }
    for encoding, served in decodable.items():
        assert decode_for_scan(served, encoding, max_bytes=1 << 20) == payload, encoding
    assert decode_for_scan(_raw_deflate(payload), "deflate", max_bytes=1 << 20) == payload

    undecodable = [
        (payload, "br"),
        (b"not gzip at all", "gzip"),
        (gzip.compress(b"x" * 2048), "gzip"),
        (gzip.compress(payload) + gzip.compress(echo), "gzip"),
        (gzip.compress(payload) + echo, "gzip"),
        (zlib.compress(payload) + zlib.compress(echo), "deflate"),
        (_raw_deflate(payload) + echo, "deflate"),
        (zstd.compress(payload) + zstd.compress(echo), "zstd"),
        (gzip.compress(payload)[:-8], "gzip"),
    ]
    for served, encoding in undecodable:
        assert decode_for_scan(served, encoding, max_bytes=1024) is None, (served[:16], encoding)


@pytest.mark.parametrize(
    ("served", "cap"),
    [(b"this is not gzip", None), (gzip.compress(b"\0" * (2 * 1024 * 1024)), 1024 * 1024)],
    ids=["not-gzip", "expands-past-the-cap"],
)
def test_an_undecodable_or_expanding_keyed_body_is_unscannable(monkeypatch, served, cap):
    if cap is not None:
        monkeypatch.setattr("cli.vintage.fetch.SIZE_CAP_BYTES", cap)
    exchanges, _, _ = _run({"bg-sopr": [Reply(200, served, [("Content-Encoding", "gzip")])]})
    assert exchanges["bg-sopr"].body is None
    assert exchanges["bg-sopr"].not_fetched == "credential unscannable"
    assert all(exchange.not_fetched is None for source_id, exchange in exchanges.items() if source_id != "bg-sopr")


def test_an_echoing_reason_phrase_or_header_name_is_redacted():
    exchanges, _, _ = _run({"bg-sopr": [Reply(401, b"{}", reason=f"bad {SENTINEL_KEY}")]}, sources=[SOURCE_BY_ID["bg-sopr"]])
    assert exchanges["bg-sopr"].reason == "<redacted>"

    named = Reply(200, b"[]", [(SENTINEL_KEY, "1"), ("Content-Type", "application/json")])
    exchanges, _, _ = _run({"bg-sopr": [named]}, sources=[SOURCE_BY_ID["bg-sopr"]])
    assert exchanges["bg-sopr"].headers == [("<redacted>", "1"), ("Content-Type", "application/json")]
    assert exchanges["bg-sopr"].body == b"[]"


@pytest.mark.parametrize(
    ("served", "headers"),
    [
        (_echo(SENTINEL_FORMS[0]), []),
        (_echo(SENTINEL_FORMS[1]), []),
        (_echo(SENTINEL_FORMS[2]), []),
        (_echo(SENTINEL_FORMS[3]), []),
        (gzip.compress(_echo(SENTINEL_FORMS[0])), [("Content-Encoding", "gzip")]),
        (gzip.compress(_echo(SENTINEL_FORMS[0])), [("content-encoding", "gzip")]),
        (gzip.compress(gzip.compress(_echo(SENTINEL_FORMS[0]))), [("Content-Encoding", "gzip"), ("Content-Encoding", "gzip")]),
    ],
    ids=["raw", "json-escaped", "percent-upper", "percent-lower", "gzip", "gzip-lower-case-name", "gzip-on-two-lines"],
)
def test_an_echoing_keyed_answer_is_withheld(served, headers):
    bg_sopr = [SOURCE_BY_ID["bg-sopr"]]
    exchanges, _, _ = _run({"bg-sopr": [Reply(200, served, headers)]}, sources=bg_sopr)
    exchange = exchanges["bg-sopr"]
    assert exchange.body is None
    assert exchange.attempts[0].withheld == ("credential echoed", len(served))
    assert exchange.not_fetched == "credential echoed"

    challenge = Reply(401, b"{}", [("WWW-Authenticate", f'Bearer error="invalid_token" token="{SENTINEL_KEY}"')])
    exchanges, _, _ = _run({"bg-sopr": [challenge]}, sources=bg_sopr)
    assert exchanges["bg-sopr"].headers == [("WWW-Authenticate", "<redacted>")]

    exchanges, _, _ = _run({"bg-sopr": [Reply(200, b"\x8b\x00\x01", [("Content-Encoding", "br")])]}, sources=bg_sopr)
    assert exchanges["bg-sopr"].body is None
    assert exchanges["bg-sopr"].not_fetched == "credential unscannable"

    echoing = b"x" * 1000 + SENTINEL_FORMS[0] + b"y" * 9000
    exchanges, _, _ = _run({"bg-sopr": [Reply(503, echoing), Reply(200, b"[]")]}, sources=bg_sopr)
    assert exchanges["bg-sopr"].not_fetched is None
    assert exchanges["bg-sopr"].attempts[0].head is None


def test_an_exception_on_the_keyed_path_is_recorded_by_its_class():
    raised = ValueError("Invalid header value %r" % (b"Bearer " + SENTINEL_KEY.encode()))
    exchanges, _, _ = _run({"bg-sopr": [raised, Reply(200, b"[]")]}, sources=[SOURCE_BY_ID["bg-sopr"]])
    assert exchanges["bg-sopr"].attempts[0].error == "ValueError"
