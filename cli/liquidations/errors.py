from __future__ import annotations


class LiquidationsError(Exception):
    """The Binance liquidations recorder (WS client or recorder) hit a fatal error."""
