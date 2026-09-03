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

import math
import statistics
from datetime import datetime
from typing import NamedTuple

from cli.features._validate import _validate_levels, _validate_rates, _validate_window
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


def oi_levels_from_raw(values: list[float | None]) -> list[float | None]:
    """Map the substrate's `0.0` open-interest placeholders to None; pass everything else through.
    A `0.0` open interest is a hole the venue wrote as a zero, not a market with no open interest,
    and the zero itself is the only predicate available -- the account-ratio columns do not mark
    those rows (spec 00110 D5). Mapping is the opposite of imputation: it removes a reading rather
    than inventing one, which is why D5 permits it where dropping or filling the rows is forbidden.

    Runs BEFORE validation and validates nothing itself -- calling `_validate_levels` here would
    reject the very rows it exists to map. It is a step the CALLER has to remember: skip it and
    `oi_log_delta` takes log(0), `oi_momentum` divides by zero, and `oi_zscore` would take a mean
    and a sample stdev over the fabricated zero and return a finite, plausible, large negative
    reading -- which is what the `_validate_levels` call in each of the three refuses."""
    return [None if v == 0.0 else v for v in values]


def oi_log_delta(levels: list[float | None]) -> list[float | None]:
    """Log ratio of consecutive open-interest levels: log(levels[k] / levels[k-1]), same length as
    the input. None at k=0, which has no predecessor, and None wherever either endpoint is null --
    an undefined reading is unknown, never 0.0 (spec 00110 D5/D7). Uses only levels[<= k] -> no
    look-ahead.

    `levels` is the GRID series -- `align_asof`'s output over `oi_levels_from_raw`, on the 1h or 4h
    grid -- not the raw 5-minute source series (spec 00110 D3/D7). Each delta therefore spans one
    BAR; on the raw series it spans five minutes instead, so the readings are a twelfth of the
    intended horizon and their scale is wrong -- perfectly causal, and so invisible to the
    truncating-prefix guard."""
    _validate_levels("levels", levels)
    out: list[float | None] = []
    for k in range(len(levels)):
        if k == 0:
            out.append(None)
            continue
        prev = levels[k - 1]
        if prev is None or levels[k] is None:
            out.append(None)
            continue
        out.append(math.log(levels[k] / prev))
    return out


def oi_zscore(levels: list[float | None], *, window: int) -> list[float | None]:
    """Trailing z-score of the open-interest level at k over the inclusive window ending at k:
    (levels[k] - mean(w)) / stdev(w) for w = levels[k-window+1 .. k], sample stdev (spec 00110 D7).
    None until the window is full, and None wherever that window holds a null -- an undefined
    window is unknown, never 0.0 (spec 00110 D5/D7). A zero-variance window scores 0.0: flat is
    exactly average, which is a reading rather than an absence. Uses only levels[<= k] -> no
    look-ahead.

    `levels` is the GRID series -- `align_asof`'s output over `oi_levels_from_raw`, on the 1h or 4h
    grid -- not the raw 5-minute source series (spec 00110 D3/D7). `window` counts BARS, which is
    why it is registered as 720 at 1h and 180 at 4h rather than as a print count; feed the raw
    series and 720 covers 2.5 days instead of 30, with nothing raising -- perfectly causal, and so
    invisible to the truncating-prefix guard."""
    _validate_levels("levels", levels)
    _validate_window("window", window)
    out: list[float | None] = []
    for k in range(len(levels)):
        if k < window - 1:
            out.append(None)
            continue
        w = levels[k - window + 1 : k + 1]
        if any(v is None for v in w):
            out.append(None)
            continue
        sd = statistics.stdev(w)
        out.append(0.0 if sd == 0.0 else (levels[k] - statistics.mean(w)) / sd)
    return out


def oi_momentum(levels: list[float | None], *, lookback: int) -> list[float | None]:
    """Past return of the open-interest level over `lookback` bars: levels[k] / levels[k-lookback]
    - 1, same length as the input. None until the lookback is available (k < lookback) and None
    wherever either endpoint is null -- an undefined window is unknown, never 0.0, which is where
    this departs from `cli/features/momentum.py`'s 0.0-filled warm-up head and its length of
    len(prices)-1 (spec 00110 D5/D7). Uses only levels[<= k] -> no look-ahead.

    `levels` is the GRID series -- `align_asof`'s output over `oi_levels_from_raw`, on the 1h or 4h
    grid -- not the raw 5-minute source series (spec 00110 D3/D7). `lookback` counts BARS, so on
    the raw series the same number spans a twelfth of the calendar time the registered value means
    -- perfectly causal, and so invisible to the truncating-prefix guard."""
    _validate_levels("levels", levels)
    _validate_window("lookback", lookback)
    out: list[float | None] = []
    for k in range(len(levels)):
        if k < lookback:
            out.append(None)
            continue
        base = levels[k - lookback]
        if base is None or levels[k] is None:
            out.append(None)
            continue
        out.append(levels[k] / base - 1)
    return out


_RATIO_COLUMNS: tuple[str, ...] = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def ratio_features(ratios: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    """Carry Binance's four ratio columns through under `binperp_` names. No arithmetic and no
    imputation: these columns carry genuine venue gaps, concentrated in one year and differing by
    an order of magnitude between columns, and filling one would manufacture a reading the venue
    never published (spec 00110 D5). Call `coverage_by_year` to see the shape for the substrate in
    hand rather than trusting a figure written here. All four are required: a caller that dropped
    one would otherwise get a silently smaller frame. The prefix is spec D8 -- the features
    describe Binance perpetuals, not the Kraken spot book they will sit beside."""
    unknown = set(ratios) - set(_RATIO_COLUMNS)
    if unknown:
        raise FeatureError(f"unknown ratio column(s): {sorted(unknown)}")
    missing = set(_RATIO_COLUMNS) - set(ratios)
    if missing:
        raise FeatureError(f"missing ratio column(s): {sorted(missing)}")
    for name, values in ratios.items():
        # A ratio is finite or null -- never gated as a positive level: a zero is a real all-sell
        # bar, while a zero OI is a venue hole (spec 00110 D5).
        _validate_rates(name, values)
    return {f"binperp_{name}": list(values) for name, values in ratios.items()}


class YearCoverage(NamedTuple):
    """Coverage of one column inside one calendar year: how many rows carried a reading, how many
    rows there were, and the stamps of the earliest and latest reading -- None for both when the
    year carried none. A NamedTuple rather than a dataclass so it reads by field name and still
    compares equal to the plain 4-tuple a caller writes in an assertion.

    The null fraction is DERIVED (`1 - non_null / total`), never a fifth field: stored beside the
    counts it is a second answer to the same question and free to disagree with them (spec 00110
    D6)."""

    non_null: int
    total: int
    first_non_null: datetime | None
    last_non_null: datetime | None


def coverage_by_year(ts: list[datetime], values: list[float | None]) -> dict[int, YearCoverage]:
    """Per-year coverage of one column, so a trial can see WHERE a column is missing rather than
    only how much (spec 00110 D6). The counts alone cannot separate a late start from an interior
    outage -- both can read `(2, 10)`, and they mean opposite things for a fold over that year --
    so the two stamps travel with them.

    Raises FeatureError on a length mismatch, `align_asof`'s rule: the derived null fraction is
    only as good as `total`, and a zip that truncates to the shorter input under-counts it and
    reports a healthier column than the substrate holds, with nothing raising.

    The stamps are the EARLIEST and LATEST non-null row of the year, not the positionally first
    and last, so an out-of-order input still reports the span it covers rather than a narrower
    one."""
    if len(ts) != len(values):
        raise FeatureError(f"ts and values must be equal length, got {len(ts)} and {len(values)}")
    totals: dict[int, int] = {}
    stamps: dict[int, list[datetime]] = {}
    for t, v in zip(ts, values):
        totals[t.year] = totals.get(t.year, 0) + 1
        if v is not None:
            stamps.setdefault(t.year, []).append(t)
    out: dict[int, YearCoverage] = {}
    for year, total in totals.items():
        seen = stamps.get(year, [])
        # An empty year has no stamps to take a min() over -- None twice, not a crash.
        out[year] = YearCoverage(len(seen), total, min(seen) if seen else None, max(seen) if seen else None)
    return out
