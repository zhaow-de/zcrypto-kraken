from __future__ import annotations


class BackfillError(Exception):
    """OHLCVT backfill reading, aggregating, or reconciling failed."""
