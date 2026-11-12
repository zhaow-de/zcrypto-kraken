"""The vintage exchange: every source dialled in the order given, each attempt bounded by a socket timeout, a deadline
and a size cap, retried and broken per host or endpoint, and the keyed host's budget rules and the key's one path, a
keyed answer scanned for the key before anything of it is kept."""

from __future__ import annotations

import contextlib
import http.client
import io
import re
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol

from cli.vintage.credential import ApiKey, decode_for_scan, holds_key, key_forms
from cli.vintage.sources import Source

SOCKET_TIMEOUT_SECONDS = 30
BODY_DEADLINE_SECONDS = 120
MAX_ATTEMPTS = 3
RETRY_AFTER_CAP_SECONDS = 300
BACKOFF_SECONDS = (30, 120)
HOST_SPACING_SECONDS = 1
SIZE_CAP_BYTES = 64 * 1024 * 1024
HEAD_BYTES = 4096
KEYED_RETRY_WAIT_SECONDS = 30
KEYED_RETRIES_PER_TICK = 1
REDACTED_AUTHORIZATION = ("Authorization", "Bearer <redacted>")

READ_BYTES = 65536
REDACTED = "<redacted>"
_KEYED_TRIPS = frozenset({401, 403, 429})
_REMAINING = ("X-RateLimit-Remaining-Day", "X-RateLimit-Remaining-Hour")
# A server's integer header is read only up to this many digits: past Python's 4,300-digit limit `int()` raises.
_MAX_DIGITS = 18
_DECIMAL = re.compile(rf"[0-9]{{1,{_MAX_DIGITS}}}")
_HTTP_VERSIONS = {10: "HTTP/1.0", 11: "HTTP/1.1"}
_UNCOUNTED = frozenset({"tick deadline", "credential echoed", "credential unscannable"})
_SCAN = frozenset({"credential echoed", "credential unscannable"})


class Deadline(Exception):
    """An attempt's deadline, raised from the watchdog's alarm: no `OSError`, so neither urllib's `URLError` wrapping
    nor the transport-error catch takes it."""


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

    def watchdog(self, seconds: float) -> contextlib.AbstractContextManager[None]: ...


def _raise_deadline(signum, frame) -> None:
    raise Deadline


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    @contextlib.contextmanager
    def watchdog(self, seconds: float):
        """Ends whatever call blocks inside it once `seconds` pass; main thread only, where Python runs a handler."""
        previous = signal.signal(signal.SIGALRM, _raise_deadline)
        try:
            signal.setitimer(signal.ITIMER_REAL, seconds)
            yield
        finally:
            # Disarmed before the handler is restored, so a late alarm never meets the default action, which ends the process;
            # the restore in its own finally, so an alarm landing at the disarm still restores it.
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
            finally:
                signal.signal(signal.SIGALRM, previous)


@dataclass
class Attempt:
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    status: int | None
    error: str | None
    head: bytes | None
    withheld: tuple[str, int] | None


@dataclass
class Exchange:
    source: Source
    request_headers: list[tuple[str, str]]
    attempts: list[Attempt]
    final_url: str | None
    http_version: str | None
    status: int | None
    reason: str | None
    headers: list[tuple[str, str]]
    body: bytes | None
    not_fetched: str | None


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_openers(
    https_handler: urllib.request.BaseHandler | None = None,
) -> tuple[urllib.request.OpenerDirector, urllib.request.OpenerDirector]:
    """The plain opener and the keyed one, whose 3xx arrives as an `HTTPError` and is the final answer."""
    handlers = [] if https_handler is None else [https_handler]
    return urllib.request.build_opener(*handlers), urllib.request.build_opener(*handlers, _RefuseRedirect())


def _dial(opener: urllib.request.OpenerDirector, request: urllib.request.Request):
    return opener.open(request, timeout=SOCKET_TIMEOUT_SECONDS)


@dataclass
class _Response:
    status: int
    reason: str
    headers: list[tuple[str, str]]
    http_version: str | None
    url: str
    stream: object


def _pairs(message) -> list[tuple[str, str]]:
    return [(name, value) for name, value in message.items() if name.lower() != "set-cookie"]


def _open(opener: urllib.request.OpenerDirector, request: urllib.request.Request) -> _Response:
    try:
        response = _dial(opener, request)
    except urllib.error.HTTPError as answer:
        stream = answer.fp if answer.fp is not None else io.BytesIO()
        version = _HTTP_VERSIONS.get(getattr(stream, "version", None))
        return _Response(answer.code, answer.reason, _pairs(answer.headers), version, answer.geturl(), stream)
    version = _HTTP_VERSIONS.get(getattr(response, "version", None))
    return _Response(response.status, response.reason, _pairs(response.headers), version, response.geturl(), response)


def header(headers: list[tuple[str, str]], name: str) -> str | None:
    """Every field line of `name`, in any case, joined in order with a comma, as RFC 9110 combines repeated lines."""
    wanted = name.lower()
    values = [value for key, value in headers if key.lower() == wanted]
    return ", ".join(values) if values else None


def _endpoint(url: str) -> tuple[str, str, str]:
    return urllib.parse.urlsplit(url)[:3]


def _plain_headers(user_agent: str) -> list[tuple[str, str]]:
    return [("Accept-Encoding", "identity"), ("User-Agent", user_agent)]


def _request(source: Source, key: ApiKey | None, user_agent: str) -> urllib.request.Request:
    request = urllib.request.Request(source.url, headers=dict(_plain_headers(user_agent)))
    if source.keyed:
        request.add_unredirected_header("Authorization", f"Bearer {key.reveal()}")
    return request


def _request_headers(source: Source, user_agent: str) -> list[tuple[str, str]]:
    headers = _plain_headers(user_agent) + ([REDACTED_AUTHORIZATION] if source.keyed else [])
    return sorted(headers, key=lambda pair: pair[0].lower())


def _retryable(status: int | None) -> bool:
    return status is None or status == 429 or status >= 500


def _keyed_retryable(status: int | None) -> bool:
    return status is None or status >= 500


def _failure_kind(exc: BaseException) -> str:
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
        return "timeout"
    return "transport error"


def _header_int(text: str) -> int | None:
    """A server header's text as an integer, None unless its stripped text is all digits; the stripped text is the
    one converted, since `strip()` removes characters `int()` refuses."""
    digits = text.strip()
    return int(digits) if _DECIMAL.fullmatch(digits) else None


def _retry_after(value: str | None, now: datetime) -> float | None:
    """The seconds a `Retry-After` asks for, capped; None where it is absent, unreadable, zero or past."""
    if value is None:
        return None
    delta = _header_int(value)
    if delta is not None:
        return min(delta, RETRY_AFTER_CAP_SECONDS) if delta > 0 else None
    text = value.strip()
    try:
        when = parsedate_to_datetime(text)
    except TypeError, ValueError, IndexError, OverflowError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    seconds = (when - now).total_seconds()
    return min(seconds, RETRY_AFTER_CAP_SECONDS) if seconds > 0 else None


def _budget_spent(headers: list[tuple[str, str]]) -> bool:
    for name in _REMAINING:
        value = header(headers, name)
        if value is not None and any(_header_int(part) == 0 for part in value.split(",")):
            return True
    return False


def _redacted(text: str, forms) -> str:
    return REDACTED if holds_key(text.encode("utf-8", "replace"), forms) else text


@dataclass
class _Answer:
    attempt: Attempt
    response: _Response | None
    failure: str | None
    body: bytes | None
    raw_headers: list[tuple[str, str]] = field(default_factory=list)

    @property
    def status(self) -> int | None:
        return None if self.failure is not None or self.response is None else self.response.status

    def withhold(self, reason: str) -> None:
        self.attempt.withheld = (reason, len(self.body))
        self.body = None


class _Tick:
    def __init__(self, *, key, key_reason, openers, clock, tick_deadline, user_agent) -> None:
        self._key = key
        self._key_reason = key_reason
        self._plain_opener, self._keyed_opener = openers
        self._clock = clock
        self._deadline = tick_deadline
        self._user_agent = user_agent
        self._forms = key_forms(key) if key is not None else ()
        self._last: dict[str, float] = {}
        self._tripped_hosts: set[str] = set()
        self._tripped_endpoints: set[tuple[str, str, str]] = set()
        self._keyed_stop: str | None = None
        self._keyed_retries = KEYED_RETRIES_PER_TICK

    def _tick_left(self) -> float:
        return self._deadline - self._clock.monotonic()

    def _spacing(self, host: str) -> float:
        last = self._last.get(host)
        return 0.0 if last is None else HOST_SPACING_SECONDS - (self._clock.monotonic() - last)

    def _wait(self, wait: float) -> None:
        if wait > 0:
            self._clock.sleep(max(0.0, min(wait, self._tick_left())))

    def not_dialled(self, source: Source, reason: str) -> Exchange:
        return Exchange(source, [], [], None, None, None, None, [], None, reason)

    def _exchange(self, source: Source, attempts: list[Attempt], answer: _Answer | None, not_fetched: str | None) -> Exchange:
        response = answer.response if answer is not None and answer.failure is None else None
        return Exchange(
            source=source,
            request_headers=_request_headers(source, self._user_agent) if attempts else [],
            attempts=attempts,
            final_url=None if response is None else (source.url if source.keyed else response.url),
            http_version=None if response is None else response.http_version,
            status=None if response is None else response.status,
            reason=None if response is None else response.reason,
            headers=[] if response is None else response.headers,
            body=answer.body if response is not None else None,
            not_fetched=not_fetched,
        )

    def _read_body(self, stream, received: bytearray, start: float, limit_seconds: float, cut: str) -> tuple[str, int] | None:
        while chunk := stream.read1(READ_BYTES):
            received += chunk
            if len(received) > SIZE_CAP_BYTES:
                return ("oversize", len(received))
            if self._clock.monotonic() - start > limit_seconds:
                return (cut, len(received))
        return None

    def _attempt(self, source: Source, opener: urllib.request.OpenerDirector, tick_left: float) -> _Answer:
        """`tick_left` is the value the dial was checked against, so the watchdog is never armed at or below 0."""
        request = _request(source, self._key, self._user_agent)
        started_at = self._clock.now()
        start = self._clock.monotonic()
        limit_seconds = min(BODY_DEADLINE_SECONDS, tick_left)
        cut = "tick deadline" if tick_left <= BODY_DEADLINE_SECONDS else "body deadline"
        received = bytearray()
        response = None
        withheld = None
        failure = error = None
        try:
            with self._clock.watchdog(limit_seconds):
                response = _open(opener, request)
                withheld = self._read_body(response.stream, received, start, limit_seconds, cut)
        except Deadline:
            withheld = (cut, len(received))
        except (OSError, http.client.HTTPException, ValueError) as exc:
            failure = _failure_kind(exc)
            error = type(exc).__name__ if source.keyed else f"{type(exc).__name__}: {exc}"
        finally:
            if response is not None:
                with contextlib.suppress(OSError, http.client.HTTPException):
                    response.stream.close()
        self._last[source.host] = self._clock.monotonic()
        attempt = Attempt(
            started_at=started_at,
            ended_at=self._clock.now(),
            duration_seconds=self._clock.monotonic() - start,
            status=None if response is None else response.status,
            error=error,
            head=None,
            withheld=withheld,
        )
        complete = withheld is None and failure is None
        answer = _Answer(attempt, response, failure, bytes(received) if complete else None)
        if response is not None:
            answer.raw_headers = response.headers
            if source.keyed:
                self._scan(answer)
        return answer

    def _scan(self, answer: _Answer) -> None:
        """Every field the server's text fills, read for the key before anything of the answer is kept."""
        response = answer.response
        encoding = header(answer.raw_headers, "Content-Encoding")
        response.reason = _redacted(response.reason, self._forms)
        response.headers = [(_redacted(name, self._forms), _redacted(value, self._forms)) for name, value in response.headers]
        if answer.body is None:
            return
        decoded = decode_for_scan(answer.body, encoding, max_bytes=SIZE_CAP_BYTES)
        if decoded is None:
            answer.withhold("credential unscannable")
        elif holds_key(answer.body, self._forms) or holds_key(decoded, self._forms):
            answer.withhold("credential echoed")

    def _final_cut(self, answer: _Answer) -> bool:
        return answer.attempt.withheld is not None and answer.attempt.withheld[0] not in _SCAN

    def _reading(self, answer: _Answer, count: int, exhausted: bool) -> str | None:
        withheld = answer.attempt.withheld
        if withheld is not None:
            return withheld[0] if withheld[0] in _UNCOUNTED else f"{withheld[0]} {withheld[1]}"
        if answer.failure is not None:
            return f"{answer.failure} after {count} attempts"
        status = answer.status
        if 200 <= status < 300:
            return None
        if exhausted:
            return f"HTTP {status} after {count} attempts"
        return f"HTTP {status} (no retry)"

    def _cut_head(self, answer: _Answer) -> None:
        answer.attempt.head = None if answer.body is None else answer.body[:HEAD_BYTES]

    def _trip(self, source: Source, answer: _Answer) -> None:
        if answer.failure is not None:
            self._tripped_hosts.add(source.host)
        else:
            self._tripped_endpoints.add(_endpoint(source.url))

    def plain(self, source: Source) -> Exchange:
        if source.host in self._tripped_hosts or _endpoint(source.url) in self._tripped_endpoints:
            return self.not_dialled(source, "breaker")
        attempts: list[Attempt] = []
        wait = 0.0
        for number in range(1, MAX_ATTEMPTS + 1):
            self._wait(max(wait, self._spacing(source.host)))
            tick_left = self._tick_left()
            if tick_left <= 0:
                return self._exchange(source, attempts, None, "tick deadline")
            answer = self._attempt(source, self._plain_opener, tick_left)
            attempts.append(answer.attempt)
            if self._final_cut(answer) or not _retryable(answer.status):
                return self._exchange(source, attempts, answer, self._reading(answer, number, exhausted=False))
            if number == MAX_ATTEMPTS:
                break
            self._cut_head(answer)
            wait = self._retry_wait(answer, number)
        self._trip(source, answer)
        return self._exchange(source, attempts, answer, self._reading(answer, len(attempts), exhausted=True))

    def _retry_wait(self, answer: _Answer, number: int) -> float:
        after = _retry_after(header(answer.raw_headers, "Retry-After"), self._clock.now())
        return after if after is not None else BACKOFF_SECONDS[number - 1]

    def keyed(self, source: Source) -> Exchange:
        if self._key is None:
            return self.not_dialled(source, self._key_reason or "no credential")
        if self._keyed_stop is not None:
            return self.not_dialled(source, self._keyed_stop)
        attempts: list[Attempt] = []
        wait = 0.0
        while True:
            self._wait(max(wait, self._spacing(source.host)))
            tick_left = self._tick_left()
            if tick_left <= 0:
                return self._exchange(source, attempts, None, "tick deadline")
            answer = self._attempt(source, self._keyed_opener, tick_left)
            attempts.append(answer.attempt)
            if answer.response is not None and _budget_spent(answer.raw_headers):
                self._keyed_stop = "budget exhausted"
            status = answer.status
            if self._final_cut(answer) or status is not None and 200 <= status < 300:
                return self._exchange(source, attempts, answer, self._reading(answer, len(attempts), exhausted=False))
            if status is not None and 300 <= status < 400:
                reading = answer.attempt.withheld[0] if answer.attempt.withheld else f"HTTP {status} redirect not followed"
                return self._exchange(source, attempts, answer, reading)
            retryable = _keyed_retryable(status)
            if retryable and self._keyed_stop is None and self._keyed_retries > 0 and len(attempts) < MAX_ATTEMPTS:
                self._keyed_retries -= 1
                self._cut_head(answer)
                wait = KEYED_RETRY_WAIT_SECONDS
                continue
            if status in _KEYED_TRIPS:
                self._keyed_stop = f"breaker (HTTP {status})"
            return self._exchange(source, attempts, answer, self._reading(answer, len(attempts), exhausted=retryable))


def fetch_all(
    sources: Sequence[Source],
    *,
    key: ApiKey | None,
    key_reason: str | None,
    openers: tuple[urllib.request.OpenerDirector, urllib.request.OpenerDirector],
    clock: Clock,
    tick_deadline: float,
    user_agent: str,
    only: frozenset[str] | None = None,
) -> list[Exchange]:
    """Every source's exchange, in `sources`' order; `tick_deadline` is a `clock.monotonic()` value. Runs in the main
    thread, the one a signal handler is installed from and run in."""
    tick = _Tick(key=key, key_reason=key_reason, openers=openers, clock=clock, tick_deadline=tick_deadline, user_agent=user_agent)
    exchanges = []
    for source in sources:
        if only is not None and source.id not in only:
            exchanges.append(tick.not_dialled(source, "not selected"))
        elif source.keyed:
            exchanges.append(tick.keyed(source))
        else:
            exchanges.append(tick.plain(source))
    return exchanges
