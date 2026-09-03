"""Derivatives-positioning features over Binance USDT-M perpetuals, mapped to Kraken spot bases by
`PERP_SYMBOLS` in `cli/derivatives/funding.py`. Two module-wide obligations a caller cannot see from
a bare `list[float | None]`:

Anything emitting these as columns prefixes them `binperp_` -- the books are Binance's, not the
Kraken spot book they will sit beside, and a column called `oi_zscore` next to Kraken columns invites
the wrong reading (spec 00110 D8). `ratio_features` is the only function here that emits names, so
for the rest the obligation lands on whatever builds the frame.

BACKTEST ONLY. The substrate is Binance's daily `metrics` dumps, published days after the fact, so
none of these features exists at live decision time from this source (spec 00110 D9). A live B2 needs
an API path that does not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from cli.features.errors import FeatureError


def align_asof(
    source_ts: list[datetime],
    source_values: list[float | None],
    grid_ts: list[datetime],
) -> list[float | None]:
    """As-of forward fill onto a decision grid: out[k] is the value of the latest source row with
    ts <= grid_ts[k], or None before the first such row. Uses only source rows at or before each
    grid stamp -> no look-ahead. Never interpolates: an interpolated value is a number the venue
    never showed (spec 00110 D2)."""
    if len(source_ts) != len(source_values):
        raise FeatureError(f"source_ts and source_values must be equal length, got {len(source_ts)} and {len(source_values)}")
    if any(b < a for a, b in zip(source_ts, source_ts[1:])):
        raise FeatureError("source_ts must be sorted ascending")
    if any(b < a for a, b in zip(grid_ts, grid_ts[1:])):
        raise FeatureError("grid_ts must be sorted ascending")
    out: list[float | None] = []
    i = 0
    carried: float | None = None
    for g in grid_ts:
        while i < len(source_ts) and source_ts[i] <= g:
            carried = source_values[i]
            i += 1
        out.append(carried)
    return out
