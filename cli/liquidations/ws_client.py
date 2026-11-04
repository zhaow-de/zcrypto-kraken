from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from cli.liquidations.errors import LiquidationsError
from cli.liquidations.recorder import parse_force_order
from cli.logging import get_logger

logger = get_logger("liquidations.ws_client")

# Keyless all-symbol combined stream: no auth and no subscribe frame — the subscription lives in the URL (spec 00051 OPS-2).
# https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
DEFAULT_URI = "wss://fstream.binance.com/stream?streams=!forceOrder@arr"

_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 60.0
_RECONNECT_ERROR_EVERY = 10  # log an ERROR every N consecutive failed reconnect attempts
# WebSocket close code 1012 "service restart": a close worth a warning on its own, as the capture client logs it.
_WS_CLOSE_SERVICE_RESTART = 1012
# The capture client's bound, Kraken's 5 s restart floor; raising it hides a degrading link.
_ROUTINE_RECONNECT_MAX_SECONDS = 5.0


def compute_backoff(attempt: int, *, base: float = _BACKOFF_BASE_SECONDS, max_delay: float = _BACKOFF_MAX_SECONDS) -> float:
    """Seconds before the `attempt`-th (0-indexed) reconnect, capped at `max_delay`; a negative `attempt` is
    refused."""
    if attempt < 0:
        raise LiquidationsError(f"attempt must be >= 0, got {attempt}")
    return min(base * (2**attempt), max_delay)


def _log_reconnected(attempts: int, seconds: float) -> None:
    if attempts == 1 and seconds <= _ROUTINE_RECONNECT_MAX_SECONDS:
        logger.info("reconnected after %.2f s", seconds)
    else:
        logger.warning("reconnected after %d %s, %.2f s", attempts, "attempt" if attempts == 1 else "attempts", seconds)


class BinanceLiquidationClient:
    """Async client for Binance USD-M futures' `!forceOrder@arr` stream — a parallel implementation of
    `cli.capture.ws_client.CaptureClient`'s reconnect loop, not a shared import. `connect_fn`/`sleep_fn`/`clock_fn`
    are injected so that loop is unit-testable without a real socket or real delays."""

    def __init__(
        self,
        uri: str = DEFAULT_URI,
        *,
        connect_fn: Callable[[str], object] | None = None,
        sleep_fn: Callable[[float], object] | None = None,
        clock_fn: Callable[[], float] | None = None,
    ) -> None:
        self._uri = uri
        self._connect = connect_fn or websockets.connect
        self._sleep = sleep_fn or asyncio.sleep
        self._clock = clock_fn or time.monotonic
        self._ws = None

    @property
    def connected(self) -> bool:
        """False during reconnect and backoff, so the dead-man gate stops pinging."""
        return self._ws is not None

    async def stream(self) -> AsyncIterator[dict]:
        """Yield forceOrder rows forever, silently dropping everything else; reconnects on any disconnect.
        Cancel the consuming task to stop — there is no internal stop condition."""
        attempt = 0
        dropped_at: float | None = None
        while True:
            try:
                async with self._connect(self._uri) as ws:
                    self._ws = ws
                    if dropped_at is not None:
                        _log_reconnected(attempt, self._clock() - dropped_at)
                        dropped_at = None
                    attempt = 0
                    async for raw in ws:
                        row = parse_force_order(raw)
                        if row is not None:
                            yield row
            except ConnectionClosed as exc:
                # Any close but a service restart is an ordinary drop; the reconnect line says whether it healed.
                restart_close = getattr(exc.rcvd, "code", None) == _WS_CLOSE_SERVICE_RESTART
                logger.log(logging.WARNING if restart_close else logging.INFO, "WS connection closed, reconnecting: %s", exc)
            except (WebSocketException, OSError, TimeoutError) as exc:
                # A failed connection *attempt* — an HTTP-error handshake (InvalidStatus), a refused/unroutable connect
                # (OSError), or a handshake timeout — backs off and retries exactly like a drop of an established
                # connection; `asyncio.CancelledError` deliberately propagates as the designed stop signal.
                logger.warning("WS connect attempt failed, reconnecting: %s", exc)
            finally:
                self._ws = None
            if dropped_at is None:
                dropped_at = self._clock()
            delay = compute_backoff(attempt)
            attempt += 1
            logger.info("reconnecting in %.1fs (attempt %d)", delay, attempt)
            if attempt % _RECONNECT_ERROR_EVERY == 0:
                logger.error("WS reconnect still failing after %d consecutive attempts", attempt)
            await self._sleep(delay)
