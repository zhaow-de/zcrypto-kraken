from __future__ import annotations

from decimal import Decimal, InvalidOperation
from zlib import crc32

from cli.capture.errors import CaptureError

# Kraken's WS v2 book checksum covers only the top 10 price levels per side, regardless of the
# subscribed depth. See https://docs.kraken.com/api/docs/guides/spot-ws-book-v2 (the "Book
# checksum" guide): "CRC32 checksum for the top 10 bids and asks."
_CHECKSUM_LEVELS = 10


def _to_decimal(value: Decimal | str | int | float) -> Decimal:
    # Values must reach here as `Decimal` (parsed upstream with `json.loads(..., parse_float=Decimal)`)
    # so trailing zeros in Kraken's wire format survive — a plain `float` (e.g. 0.3 for "0.30000000")
    # would silently corrupt the checksum. `str`/`int` are accepted as a convenience for tests.
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise CaptureError(f"not a valid decimal price/qty: {value!r}") from exc


def _format_level(value: Decimal) -> str:
    """Format one price/qty per Kraken's checksum recipe: strip the decimal point, then strip
    leading zeros (e.g. `Decimal("0.00100000")` -> `"100000"`, `Decimal("45283.5")` -> `"452835"`).
    """
    digits = f"{value:f}".replace(".", "").replace("-", "").lstrip("0")
    return digits or "0"


def _extract_level(raw: dict) -> tuple[Decimal, Decimal]:
    try:
        price, qty = raw["price"], raw["qty"]
    except (KeyError, TypeError) as exc:
        raise CaptureError(f"book level missing 'price'/'qty': {raw!r}") from exc
    return _to_decimal(price), _to_decimal(qty)


class OrderBook:
    """Per-pair L2 book state, rebuilt from a WS v2 snapshot and kept current via updates.

    The book is kept **congruent with Kraken's subscribed depth window** (`depth` levels per side)
    -- see `_prune`. `ingest_snapshot`/`ingest_update` apply the payload and validate Kraken's
    per-message CRC32 `checksum`, tracking `desynced` so the caller (the WS client / gap monitor)
    can react to a mismatch.

    `depth` is deliberately **required**: a depth-limited book cannot be maintained correctly
    without it, and defaulting it would silently reintroduce T0008 (below).
    """

    def __init__(self, symbol: str, depth: int) -> None:
        self.symbol = symbol
        self.depth = depth
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.desynced = False

    def _prune(self) -> None:
        """Drop everything beyond the subscribed depth, so the book mirrors Kraken's window exactly.

        Load-bearing (T0008). Kraken only sends deltas for levels **inside** the depth-N window; a
        level we retain beyond it is one Kraken has stopped telling us about, so it goes stale --
        its quantity changes, or it is cancelled, and we never hear. When the window later shifts
        back, that stale level re-enters our top-10 as a **phantom** and the checksum fails. The
        daemon then calls it a "desync", resubscribes for a fresh snapshot, and immediately starts
        re-accumulating.

        Measured on three independent hosts (2026-07-13): without this the live book grew to 810
        bids / 468 asks against Kraken's 100, and replaying one real captured hour produced 482
        checksum failures. Pruning takes that to **zero** on every host. T0008's ~200 "desyncs"/day
        were never network loss -- they were this.
        """
        if len(self.asks) > self.depth:  # asks: best == lowest price
            self.asks = dict(sorted(self.asks.items())[: self.depth])
        if len(self.bids) > self.depth:  # bids: best == highest price
            self.bids = dict(sorted(self.bids.items(), reverse=True)[: self.depth])

    def ingest_snapshot(self, data: dict) -> bool:
        """Replace the book with a `type: snapshot` payload's `bids`/`asks`. Returns whether the
        rebuilt book's checksum matches `data["checksum"]`."""
        self.bids = dict(_extract_level(level) for level in data.get("bids", []))
        self.asks = dict(_extract_level(level) for level in data.get("asks", []))
        self._prune()
        return self.validate(data["checksum"])

    def ingest_update(self, data: dict) -> bool:
        """Apply a `type: update` payload's bid/ask deltas (qty `0` removes the level), prune back
        to the subscribed depth, then validate the resulting book's checksum against
        `data["checksum"]`."""
        self._apply_side(self.bids, data.get("bids", []))
        self._apply_side(self.asks, data.get("asks", []))
        self._prune()
        return self.validate(data["checksum"])

    @staticmethod
    def _apply_side(side: dict[Decimal, Decimal], levels: list[dict]) -> None:
        for raw in levels:
            price, qty = _extract_level(raw)
            if qty == 0:
                side.pop(price, None)
            else:
                side[price] = qty

    def checksum(self) -> int:
        """Kraken's CRC32 book checksum: format+concatenate the top-10 asks (low-to-high) then
        the top-10 bids (high-to-low), CRC32 the ASCII bytes, cast to unsigned 32-bit."""
        top_asks = sorted(self.asks.items())[:_CHECKSUM_LEVELS]
        top_bids = sorted(self.bids.items(), reverse=True)[:_CHECKSUM_LEVELS]
        asks_str = "".join(_format_level(price) + _format_level(qty) for price, qty in top_asks)
        bids_str = "".join(_format_level(price) + _format_level(qty) for price, qty in top_bids)
        return crc32((asks_str + bids_str).encode("ascii")) & 0xFFFFFFFF

    def validate(self, expected_checksum: int) -> bool:
        ok = self.checksum() == expected_checksum
        self.desynced = not ok
        return ok
