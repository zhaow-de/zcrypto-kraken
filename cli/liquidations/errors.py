from __future__ import annotations


class LiquidationsError(Exception):
    """A liquidations feed (the Binance WS client/recorder, or the Coinalyze REST poller) hit a fatal error."""
