from __future__ import annotations


class LiquidationsError(Exception):
    """A liquidations feed (Binance WS recorder or Coinalyze REST poller) failed; the poller retries next
    cycle."""
