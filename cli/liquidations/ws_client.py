from __future__ import annotations

import asyncio
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


def compute_backoff(attempt: int, *, base: float = _BACKOFF_BASE_SECONDS, max_delay: float = _BACKOFF_MAX_SECONDS) -> float:
    """Exponential backoff delay (seconds) for the `attempt`-th (0-indexed) reconnect, capped at `max_delay`."""
    if attempt < 0:
        raise LiquidationsError(f"attempt must be >= 0, got {attempt}")
    return min(base * (2**attempt), max_delay)


class BinanceLiquidationClient:
    """Thin async client for Binance USD-M futures' keyless `!forceOrder@arr` combined stream: connect, receive, parse,
    auto-reconnect with exponential backoff on any drop, mirroring `cli.capture.ws_client.CaptureClient`'s reconnect loop.
    `connect_fn`/`sleep_fn` are injected so that loop is unit-testable without a real socket or real delays."""

    def __init__(
        self,
        uri: str = DEFAULT_URI,
        *,
        connect_fn: Callable[[str], object] | None = None,
        sleep_fn: Callable[[float], object] | None = None,
    ) -> None:
        self._uri = uri
        self._connect = connect_fn or websockets.connect
        self._sleep = sleep_fn or asyncio.sleep
        self._ws = None

    @property
    def connected(self) -> bool:
        """True while a live WS connection is established; False during reconnect/backoff, so the dead-man gate stops pinging."""
        return self._ws is not None

    async def stream(self) -> AsyncIterator[dict]:
        """Yield parsed forceOrder row dicts forever, reconnecting (with backoff) on any drop. Cancel the consuming task
        to stop — there is no internal stop condition."""
        attempt = 0
        while True:
            try:
                async with self._connect(self._uri) as ws:
                    self._ws = ws
                    attempt = 0
                    async for raw in ws:
                        row = parse_force_order(raw)
                        if row is not None:
                            yield row
            except ConnectionClosed as exc:
                logger.warning("WS connection closed, reconnecting: %s", exc)
            except (WebSocketException, OSError, TimeoutError) as exc:
                # A failed connection *attempt* — an HTTP-error handshake (InvalidStatus), a refused/unroutable connect
                # (OSError), or a handshake timeout — backs off and retries exactly like a drop of an established
                # connection; `asyncio.CancelledError` deliberately propagates as the designed stop signal.
                logger.warning("WS connect attempt failed, reconnecting: %s", exc)
            finally:
                self._ws = None
            delay = compute_backoff(attempt)
            attempt += 1
            logger.info("reconnecting in %.1fs (attempt %d)", delay, attempt)
            if attempt % _RECONNECT_ERROR_EVERY == 0:
                logger.error("WS reconnect still failing after %d consecutive attempts", attempt)
            await self._sleep(delay)
