from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from cli.capture.errors import CaptureError
from cli.logging import get_logger

logger = get_logger("capture.ws_client")

DEFAULT_URI = "wss://ws.kraken.com/v2"
# Depths Kraken's WS v2 `book` channel accepts.
# https://docs.kraken.com/api/docs/websocket-v2/book
ALLOWED_DEPTHS = (10, 25, 100, 500, 1000)

_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 60.0
_RECONNECT_ERROR_EVERY = 10  # log an ERROR every N consecutive failed reconnect attempts (T0035)
# Kraken's documented floor for reconnecting after maintenance or extended downtime (T0101).
_SERVICE_RESTART_MIN_DELAY_SECONDS = 5.0
# How long a resubscribe waits for its `unsubscribe` ack before sending `subscribe` anyway (T0102).
# A lost ack must degrade to the old fire-and-forget ordering, never strand the pair -- that is the
# exact failure T0008's ladder exists to remove.
_ACK_TIMEOUT_SECONDS = 5.0
# WebSocket close code 1012 "service restart" -- the venue announcing its own restart. Measured
# twice in 19.3 days (2026-07-13, 2026-07-27), both times arriving AFTER the silence, not before.
_WS_CLOSE_SERVICE_RESTART = 1012


def build_subscribe_message(
    channel: str, symbols: list[str], *, depth: int | None = None, snapshot: bool = True, req_id: int | None = None
) -> dict:
    """Build a WS v2 `subscribe` request for `channel` (`"book"` or `"trade"`) over `symbols`.

    See https://docs.kraken.com/api/docs/websocket-v2/book and .../trade for the request shape:
    `{"method": "subscribe", "params": {"channel": ..., "symbol": [...], ...}}`.
    """
    params: dict = {"channel": channel, "symbol": list(symbols), "snapshot": snapshot}
    if depth is not None:
        params["depth"] = depth
    message: dict = {"method": "subscribe", "params": params}
    if req_id is not None:
        message["req_id"] = req_id
    return message


def build_unsubscribe_message(channel: str, symbols: list[str], *, depth: int | None = None, req_id: int | None = None) -> dict:
    """Build a WS v2 `unsubscribe` request for `channel` over `symbols` — the inverse of
    `build_subscribe_message`. Kraken rejects a re-`subscribe` of an already-active channel with
    "Already subscribed" and sends no snapshot, so forcing a fresh book snapshot (desync recovery)
    requires unsubscribe-then-subscribe. `depth` must match the original book subscription. There is
    no `snapshot` param (it is subscribe-only)."""
    params: dict = {"channel": channel, "symbol": list(symbols)}
    if depth is not None:
        params["depth"] = depth
    message: dict = {"method": "unsubscribe", "params": params}
    if req_id is not None:
        message["req_id"] = req_id
    return message


def parse_message(raw: str | bytes) -> dict:
    """Parse one WS v2 text frame. Uses `parse_float=Decimal` so price/qty retain their exact
    wire-format precision (trailing zeros survive) — required for the book CRC32 checksum to be
    reproducible; a plain `float` would silently corrupt it (see `cli.capture.book`)."""
    try:
        return json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"invalid JSON frame from Kraken WS: {exc}") from exc


def classify(msg: dict) -> str:
    """Coarse category for a parsed WS v2 message, used to route it to the right handler."""
    channel = msg.get("channel")
    mtype = msg.get("type")
    if channel == "book":
        return "book_snapshot" if mtype == "snapshot" else "book_update"
    if channel == "trade":
        return "trade_snapshot" if mtype == "snapshot" else "trade_update"
    if channel == "heartbeat":
        return "heartbeat"
    if channel == "status":
        # Kraken pushes this automatically on connect and on every trading-engine state change
        # (online / cancel_only / maintenance / post_only), and its planned-downtime notification
        # carries an `effectiveTime`. It used to fall through to "other" and be dropped unlogged,
        # which is why "did the venue announce the 2026-07-27 outage?" is unanswerable rather than
        # answered no (T0101, spec 00073 D1). Recorded as `zcrypto_capture_venue_status_total`, which
        # two alert rules page on -- one named the cause of the 2026-08-06 Kraken maintenance outage.
        return "status"
    if msg.get("method") == "subscribe":
        return "subscribe_ack" if msg.get("success") else "subscribe_error"
    if msg.get("method") == "unsubscribe":
        return "unsubscribe_ack" if msg.get("success") else "unsubscribe_error"
    return "other"


def compute_backoff(
    attempt: int,
    *,
    base: float = _BACKOFF_BASE_SECONDS,
    max_delay: float = _BACKOFF_MAX_SECONDS,
    after_service_restart: bool = False,
) -> float:
    """Exponential backoff delay (seconds) for the `attempt`-th (0-indexed) reconnect, capped at `max_delay`.

    `after_service_restart` floors the delay at `_SERVICE_RESTART_MIN_DELAY_SECONDS`. Kraken's
    guidance is to reconnect instantly a handful of times on a random drop but no faster than once
    every 5 s after maintenance -- and on 2026-07-27 the primary's first attempt fired 1.0 s after
    the 1012 and was answered HTTP 503, costing ~3.9 s of extra silence on the unbackfillable path
    while the secondary, whose attempt landed later, connected first try. It is a FLOOR, never a
    cap: a genuinely escalating backoff is left alone, and ordinary drops (~8.2/day) keep the fast
    path untouched.
    """
    if attempt < 0:
        raise CaptureError(f"attempt must be >= 0, got {attempt}")
    delay = min(base * (2**attempt), max_delay)
    if after_service_restart:
        return max(delay, _SERVICE_RESTART_MIN_DELAY_SECONDS)
    return delay


class CaptureClient:
    """Thin async client for Kraken's public WS v2 feed: subscribes `book` (at `depth`) + `trade`
    for `pairs`, auto-reconnecting with exponential backoff on any drop.

    `connect_fn`/`sleep_fn` are injectable so the reconnect/backoff orchestration is unit-testable
    without a real socket or real delays.
    """

    def __init__(
        self,
        pairs: list[str],
        depth: int,
        *,
        uri: str = DEFAULT_URI,
        connect_fn: Callable[[str], object] | None = None,
        sleep_fn: Callable[[float], object] | None = None,
        ack_timeout: float = _ACK_TIMEOUT_SECONDS,
    ) -> None:
        if depth not in ALLOWED_DEPTHS:
            raise CaptureError(f"depth must be one of {ALLOWED_DEPTHS}, got {depth}")
        if not pairs:
            raise CaptureError("pairs must be non-empty")
        self._pairs = list(pairs)
        self._depth = depth
        self._uri = uri
        self._connect = connect_fn or websockets.connect
        self._sleep = sleep_fn or asyncio.sleep
        self._ws = None
        # Additive, state-only (spec 00069 D5/T3): no behavioral change, plain ints a metrics
        # collector reads at scrape time -- never mutated from anywhere but the two sites below.
        self.reconnects_total = 0
        self.resubscribes_total = 0
        # T0102: req_id correlation. `_pending` maps our own req_id -> the future a waiter task
        # awaits; `note_reply` resolves it. The waiter exists because rung 1 calls
        # `resubscribe_book` from the task that drives `stream()` -- awaiting the ack inline would
        # block the loop that delivers it.
        self._ack_timeout = ack_timeout
        self._req_seq = 0
        self._issued: set[int] = set()  # every id WE minted -- Kraken's own bulk acks carry none
        self._pending: dict[int, asyncio.Future] = {}
        self._resub_tasks: set[asyncio.Task] = set()
        self.resubscribe_errors_total = 0
        self.resubscribe_ack_timeouts_total = 0

    @property
    def connected(self) -> bool:
        """True while a live WS connection is established; False during reconnect/backoff. Lets the
        liveness heartbeat stop pinging on a connectivity loss, not only on checksum desyncs."""
        return self._ws is not None

    async def stream(self) -> AsyncIterator[dict]:
        """Yield parsed messages forever, reconnecting (with backoff) on any drop. Cancel the
        consuming task to stop — there is no internal stop condition."""
        attempt = 0
        service_restart = False
        while True:
            try:
                async with self._connect(self._uri) as ws:
                    self._ws = ws
                    await self._subscribe_all(ws)
                    attempt = 0
                    service_restart = False
                    async for raw in ws:
                        yield parse_message(raw)
            except ConnectionClosed as exc:
                # A 1012 is the venue announcing its own restart; reconnecting at 1.0 s into it is
                # what earned the HTTP 503 on 2026-07-27. Sticky across attempts until a connection
                # actually succeeds -- the endpoint stays unready for longer than one attempt.
                service_restart = service_restart or getattr(exc.rcvd, "code", None) == _WS_CLOSE_SERVICE_RESTART
                logger.warning("WS connection closed, reconnecting: %s", exc)
            except (WebSocketException, OSError, TimeoutError) as exc:
                # A failed connection *attempt* — e.g. InvalidStatus on the HTTP 503 Kraken's
                # endpoint answers with while restarting (T0035), a refused/unroutable connect
                # (OSError), or a handshake timeout — backs off and retries exactly like a drop
                # of an established connection. asyncio.CancelledError deliberately propagates:
                # it is the designed stop signal, and swallowing it would break shutdown.
                logger.warning("WS connect attempt failed, reconnecting: %s", exc)
            finally:
                self._ws = None
            self.reconnects_total += 1
            delay = compute_backoff(attempt, after_service_restart=service_restart)
            attempt += 1
            logger.info("reconnecting in %.1fs (attempt %d)", delay, attempt)
            if attempt % _RECONNECT_ERROR_EVERY == 0:
                logger.error("WS reconnect still failing after %d consecutive attempts", attempt)
            await self._sleep(delay)

    async def _subscribe_all(self, ws) -> None:
        await ws.send(json.dumps(build_subscribe_message("book", self._pairs, depth=self._depth)))
        await ws.send(json.dumps(build_subscribe_message("trade", self._pairs)))

    async def force_reconnect(self) -> None:
        """Drop the live connection so `stream()` rebuilds it — the recovery ladder's last rung.

        Closing the socket makes `stream()`'s `async for` raise `ConnectionClosed`, which its
        existing handler already treats as an ordinary drop: reconnect, re-subscribe everything,
        fresh snapshots for every pair. Reusing that path rather than adding a second reconnect
        implementation is the point — there is exactly one way this daemon reconnects.

        A no-op when nothing is connected: `stream()` is already mid-reconnect, which is what this
        would have asked for anyway.
        """
        ws = self._ws
        if ws is None:
            return
        with contextlib.suppress(Exception):
            await ws.close()

    def note_reply(self, msg: dict) -> None:
        """Route a `subscribe`/`unsubscribe` reply back to the waiter that asked for it (T0102).

        Called from the consumer for every ack/error frame. A reply with no `req_id`, or one we did
        not issue (Kraken's acks for the initial bulk subscription), is a deliberate no-op — never a
        KeyError out of the single task the whole daemon runs on.
        """
        req_id = msg.get("req_id")
        if req_id is None or req_id not in self._issued:
            return
        self._issued.discard(req_id)
        if not msg.get("success", False):
            # An EXPLICIT rejection -- of either frame. Before correlation this left no trace of its
            # own and was inferable only from the pair staying desynced.
            self.resubscribe_errors_total += 1
            logger.error("resubscribe reply rejected: %s", msg)
        future = self._pending.pop(req_id, None)
        if future is not None and not future.done():
            future.set_result(bool(msg.get("success", False)))

    async def _subscribe_after_ack(self, pair: str, future: asyncio.Future, socket: object, req_id: int) -> None:
        """Send the `subscribe` once the `unsubscribe` is acknowledged — or once the wait times out.

        Runs as its own task so `resubscribe_book` never blocks its caller: rung 1 fires from inside
        the message handler, i.e. from the task driving `stream()`, and awaiting there would block
        the loop that delivers the very ack being waited on.
        """
        try:
            try:
                await asyncio.wait_for(future, self._ack_timeout)
            except TimeoutError:
                self._pending.pop(req_id, None)  # nothing will resolve it now; do not leak the entry
                self.resubscribe_ack_timeouts_total += 1
                logger.warning(
                    "resubscribe: no unsubscribe ack for pair=%s in %.1fs -- subscribing anyway", pair, self._ack_timeout
                )
            # IDENTITY, not None-ness. A reconnect inside the ack window installs a NEW socket and
            # `_subscribe_all` has already resubscribed every pair on it, so sending here would be a
            # duplicate: Kraken answers "Already subscribed", which is logged at ERROR and counted as
            # a rejection -- and the ops log rule pages on any capture ERROR. A benign reconnect must
            # not page, and the new counter must not report a fault that did not happen.
            if self._ws is not socket:
                return
            self._req_seq += 1
            sub_id = self._req_seq
            self._issued.add(sub_id)  # nothing awaits this one; it exists so a REJECTED subscribe is counted
            await self._ws.send(json.dumps(build_subscribe_message("book", [pair], depth=self._depth, req_id=sub_id)))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- a bare task: an escaping exception would be silent
            logger.exception("resubscribe: sending subscribe failed for pair=%s", pair)

    async def resubscribe_book(self, pair: str) -> None:
        """Force a fresh `book` snapshot for one pair to recover from a checksum desync without
        dropping the whole connection: **unsubscribe then re-subscribe**. A bare re-`subscribe` of an
        already-active channel is rejected by Kraken ("Already subscribed") and yields no snapshot, so
        the desynced book could never heal — the unsubscribe first is what forces the new snapshot
        (`ingest_snapshot` then rebuilds the book and clears `desynced`). A no-op if not currently
        connected (the next reconnect resubscribes everything anyway).

        Both frames carry a `req_id` (T0102), and the `subscribe` is deferred to a waiter task until
        the `unsubscribe` is acknowledged — closing the race where the subscribe overtakes the
        unsubscribe server-side and is rejected. This method itself never awaits the reply.
        """
        socket = self._ws
        if socket is None:
            return
        self._req_seq += 1
        req_id = self._req_seq
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._issued.add(req_id)
        self._pending[req_id] = future
        await socket.send(json.dumps(build_unsubscribe_message("book", [pair], depth=self._depth, req_id=req_id)))
        self.resubscribes_total += 1

        task = asyncio.create_task(self._subscribe_after_ack(pair, future, socket, req_id))
        self._resub_tasks.add(task)  # a bare create_task can be garbage-collected mid-flight
        task.add_done_callback(self._resub_tasks.discard)

    async def drain_pending_resubscribes(self, timeout: float = 10.0) -> None:
        """Await the in-flight resubscribe waiters (shutdown, and the tests' determinism hook)."""
        if not self._resub_tasks:
            return
        await asyncio.wait(set(self._resub_tasks), timeout=timeout)
