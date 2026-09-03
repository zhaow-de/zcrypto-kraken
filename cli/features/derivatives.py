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

import statistics
from datetime import datetime

from cli.features._validate import _validate_rates, _validate_window
from cli.features.errors import FeatureError


def align_asof(
    source_ts: list[datetime],
    source_values: list[float | None],
    grid_ts: list[datetime],
) -> list[float | None]:
    """As-of forward fill onto a decision grid: out[k] is the value of the latest source row with
    ts <= grid_ts[k], or None before the first such row. Uses only source rows at or before each
    grid stamp -> no look-ahead. Never interpolates: an interpolated value is a number the venue
    never showed (spec 00110 D2). A null source value is carried forward as a null -- it replaces
    the carry rather than being skipped, so one null source row erases the carry for every later
    grid stamp until the next non-null source row."""
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


def funding_zscore(rates: list[float | None], *, window: int) -> list[float | None]:
    """Trailing z-score of the funding print at k over the inclusive window ending at k:
    (rates[k] - mean(w)) / stdev(w) for w = rates[k-window+1 .. k], sample stdev (spec 00110 D7).
    None until the window is full, and None wherever that window holds a null -- an undefined
    window is unknown, never 0.0 (spec 00110 D5/D7). A zero-variance window scores 0.0: flat is
    exactly average, which is a reading rather than an absence. Uses only rates[<= k] -> no
    look-ahead.

    `rates` is the realized-funding PRINT series at a constant settlement interval, not
    `align_asof`'s grid-aligned carry (spec 00110 D3/D7). On a grid finer than the settlement
    interval each print repeats across several bars, which shrinks the sample stdev this divides
    by and shortens the calendar span `window` covers -- and both are perfectly causal, so the
    truncating-prefix guard cannot see either."""
    _validate_rates("rates", rates)
    _validate_window("window", window)
    out: list[float | None] = []
    for k in range(len(rates)):
        if k < window - 1:
            out.append(None)
            continue
        w = rates[k - window + 1 : k + 1]
        if any(v is None for v in w):
            out.append(None)
            continue
        sd = statistics.stdev(w)
        out.append(0.0 if sd == 0.0 else (rates[k] - statistics.mean(w)) / sd)
    return out


def funding_sign_persistence(rates: list[float | None]) -> list[int | None]:
    """Run length of consecutive same-sign funding prints ending at k, counting the print at k --
    1 at every sign change. Sign is drawn from {-1, 0, +1}, so a 0.0 print breaks the run either
    side of it and starts its own (spec 00110 D7). A null is None and breaks the run without
    joining one, so the next non-null print restarts at 1 (spec 00110 D5). Takes no window, hence
    no warm-up head. Uses only rates[<= k] -> no look-ahead.

    `rates` is the realized-funding PRINT series at a constant settlement interval, not
    `align_asof`'s grid-aligned carry (spec 00110 D3/D7). On a grid finer than the settlement
    interval each print repeats across several bars, so runs inflate by that factor and can never
    break inside a print -- perfectly causal, and so invisible to the truncating-prefix guard."""
    _validate_rates("rates", rates)
    out: list[int | None] = []
    prev: int | None = None
    run = 0
    for v in rates:
        if v is None:
            prev, run = None, 0
            out.append(None)
            continue
        sign = (v > 0) - (v < 0)
        run = run + 1 if sign == prev else 1
        prev = sign
        out.append(run)
    return out


def funding_accrued_carry(rates: list[float | None], *, window: int) -> list[float | None]:
    """Sum of the funding prints in the inclusive window ending at k -- what a position held across
    those prints accrued (spec 00110 D7). None until the window is full, and None wherever that
    window holds a null: a sum over the non-null part would wear a full window's label while
    covering less (spec 00110 D5/D7). Uses only rates[<= k] -> no look-ahead.

    `rates` is the realized-funding PRINT series at a constant settlement interval, not
    `align_asof`'s grid-aligned carry (spec 00110 D3/D7). The window counts PRINTS, so the span it
    sums is `window` x the settlement interval; a grid-aligned input counts each print once per
    bar and the sum reports a span it does not cover -- perfectly causal, and so invisible to the
    truncating-prefix guard."""
    _validate_rates("rates", rates)
    _validate_window("window", window)
    out: list[float | None] = []
    for k in range(len(rates)):
        if k < window - 1:
            out.append(None)
            continue
        w = rates[k - window + 1 : k + 1]
        if any(v is None for v in w):
            out.append(None)
            continue
        out.append(sum(w))
    return out
