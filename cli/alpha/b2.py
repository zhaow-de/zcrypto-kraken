from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial

import numpy as np

from cli.alpha.errors import AlphaError
from cli.features.derivatives import (
    align_asof,
    funding_accrued_carry,
    funding_sign_persistence,
    funding_zscore,
    oi_levels_from_raw,
    oi_log_delta,
    oi_momentum,
    oi_zscore,
    ratio_features,
)
from cli.logging import get_logger
from cli.validation import max_drawdown, stationary_bootstrap_indices

logger = get_logger("alpha.b2")

_BOUNDARY = timedelta(hours=4)
# The 4h marks are the multiples of 4 h from here: the OI grid and every union close stand on them.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# A ruling (docs/specs/00128 D2), not a knob: a print within this of its hour is that hour's settlement.
_STAMP_TOLERANCE = timedelta(seconds=60)
_FUNDING_INTERVAL_HOURS = 8
_SETTLEMENT_INTERVAL = timedelta(hours=_FUNDING_INTERVAL_HOURS)
# Pre-registered 30-day windows (docs/specs/00110 D7, docs/specs/00131 D3), not knobs: a change to one is a new trial.
_CARRY_WINDOW = 90
_OI_ZSCORE_WINDOW = 180
_OI_MOMENTUM_LOOKBACK = 180
# Pre-registered 30-day windows (docs/specs/00138 D5, D6), not knobs: a change to one is a new trial.
_RATIO_ZSCORE_WINDOW = 180
_DAILY_ZSCORE_WINDOW = 30
_HOUR = timedelta(hours=1)
_DAY = timedelta(days=1)
# The imbalance carries no lowerbound_: a ratio of two undercounts bounds nothing (docs/specs/00136 D5).
_LIQUIDATION_COLUMNS = (
    "binperp_liq_lowerbound_long_usd",
    "binperp_liq_lowerbound_short_usd",
    "binperp_liq_lowerbound_total_usd",
    "binperp_liq_imbalance",
)


@dataclass(frozen=True, kw_only=True)
class B2Config:
    """B2 funding-extreme de-risk overlay configuration (docs/specs/00128 D3/D8): pre-registered
    constants, not tuned -- changing one after a result is a new trial."""

    z_threshold: float = 2.0
    derisk_scale: float = 0.5
    z_window: int = 90

    def __post_init__(self) -> None:
        t = self.z_threshold
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t) or t <= 0:
            raise AlphaError(f"z_threshold must be a finite number > 0, got {t!r}")
        s = self.derisk_scale
        if not isinstance(s, (int, float)) or isinstance(s, bool) or not math.isfinite(s) or not 0 < s <= 1:
            raise AlphaError(f"derisk_scale must be a finite number in (0, 1], got {s!r}")
        w = self.z_window
        if not isinstance(w, int) or isinstance(w, bool) or w < 2:
            raise AlphaError(f"z_window must be an int >= 2, got {w!r}")


def _validate_stamps(name: str, ts: list[datetime]) -> None:
    for i, t in enumerate(ts):
        if not isinstance(t, datetime) or t.utcoffset() is None:
            raise AlphaError(f"{name} must be tz-aware datetimes, {name}[{i}] = {t!r}")
    for i in range(1, len(ts)):
        if ts[i] <= ts[i - 1]:
            raise AlphaError(f"{name} must be strictly increasing, violated at index {i}")


def close_grid(union_ts: list[datetime]) -> list[datetime]:
    return [t + _BOUNDARY for t in union_ts[:-1]]


def _funding_on_close_grid(
    label: str,
    feature: Callable[[list[float | None]], list],
    prints_ts: list[datetime],
    prints_rate: list[float | None],
    prints_interval_hours: list[int],
    union_ts: list[datetime],
) -> list:
    """Every funding emitter's one print pipeline (docs/specs/00131 D2), where docs/specs/00128 D2's two stamp rulings
    live: the print stamp truncated to its hour, and `feature`'s print-indexed output as-of on `close_grid`, a print
    reaching a close only before the next settlement is due (docs/specs/00131 D5) -- past a series' last print the
    as-of would carry it on. An off-cadence print is mapped to None before `feature`, never dropped: dropping it would
    let a window span a different horizon under the same label."""
    if not len(prints_ts) == len(prints_rate) == len(prints_interval_hours):
        raise AlphaError(
            "prints_ts, prints_rate and prints_interval_hours must be equal length, "
            f"got {len(prints_ts)}, {len(prints_rate)} and {len(prints_interval_hours)}"
        )
    _validate_stamps("prints_ts", prints_ts)
    _validate_stamps("union_ts", union_ts)

    normalised: list[datetime] = []
    for i, t in enumerate(prints_ts):
        hour = t.replace(minute=0, second=0, microsecond=0)
        if t - hour > _STAMP_TOLERANCE:
            raise AlphaError(
                f"prints_ts[{i}] = {t.isoformat()} is {t - hour} past its hour, beyond the "
                f"{_STAMP_TOLERANCE.total_seconds():.0f} s settlement tolerance"
            )
        normalised.append(hour)

    rates = [r if h == _FUNDING_INTERVAL_HOURS else None for r, h in zip(prints_rate, prints_interval_hours)]
    values = feature(rates)
    logger.debug(
        "funding %s grid feature: %d prints, %d off-cadence mapped to None, %d return indices",
        label,
        len(prints_ts),
        sum(h != _FUNDING_INTERVAL_HOURS for h in prints_interval_hours),
        len(union_ts) - 1,
    )
    closes = close_grid(union_ts)
    # The as-of over print indices, so the bound below reads the hour of the print each close takes.
    latest = align_asof(normalised, list(range(len(normalised))), closes)
    return [None if j is None or normalised[j] <= c - _SETTLEMENT_INTERVAL else values[j] for j, c in zip(latest, closes)]


def funding_grid_feature(
    prints_ts: list[datetime],
    prints_rate: list[float | None],
    prints_interval_hours: list[int],
    union_ts: list[datetime],
    *,
    config: B2Config,
) -> list[float | None]:
    """The trailing funding z-score as-of each return index's close (docs/specs/00128 D2): the union's bar-open stamps
    in, `len(union_ts) - 1` values out, the stamps raw -- a caller shifts none itself."""
    if not isinstance(config, B2Config):
        raise AlphaError(f"config must be a B2Config, got {type(config)!r}")
    zscore = partial(funding_zscore, window=config.z_window)
    return _funding_on_close_grid("z-score", zscore, prints_ts, prints_rate, prints_interval_hours, union_ts)


def funding_sign_grid_feature(
    prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], union_ts: list[datetime]
) -> list[int | None]:
    return _funding_on_close_grid("sign run", funding_sign_persistence, prints_ts, prints_rate, prints_interval_hours, union_ts)


def funding_carry_grid_feature(
    prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], union_ts: list[datetime]
) -> list[float | None]:
    carry = partial(funding_accrued_carry, window=_CARRY_WINDOW)
    return _funding_on_close_grid("accrued carry", carry, prints_ts, prints_rate, prints_interval_hours, union_ts)


def _mark_at_or_after(t: datetime) -> datetime:
    return _EPOCH - (_EPOCH - t) // _BOUNDARY * _BOUNDARY


def _oi_marks(oi_ts: list[datetime]) -> list[datetime]:
    """The regular 4h close grid over the rows' own span (docs/specs/00131 D6)."""
    if not oi_ts:
        return []
    first, last = _mark_at_or_after(oi_ts[0]), _mark_at_or_after(oi_ts[-1])
    return [first + k * _BOUNDARY for k in range((last - first) // _BOUNDARY + 1)]


def _validate_union_marks(union_ts: list[datetime]) -> None:
    _validate_stamps("union_ts", union_ts)
    for i, t in enumerate(union_ts):
        if (t - _EPOCH) % _BOUNDARY:
            raise AlphaError(f"union_ts[{i}] = {t.isoformat()} is not on a 4 h mark")


def _rows_at_union_closes(
    label: str,
    feature: Callable[[list[float | None]], list],
    oi_ts: list[datetime],
    values_name: str,
    levels: list[float | None],
    union_ts: list[datetime],
) -> list:
    """Every emitter over the OI file's 5-minute rows runs this one pipeline (docs/specs/00131 D4-D6, docs/specs/00136
    D2), the union's bar-open stamps in: `feature` runs over the value on `_oi_marks`' grid, never over the raw rows, and
    each union close reads it by exact lookup. A row is read from its own stamp, never truncated as a funding print's is:
    the stamp is when the venue measured the value."""
    if len(oi_ts) != len(levels):
        raise AlphaError(f"oi_ts and {values_name} must be equal length, got {len(oi_ts)} and {len(levels)}")
    _validate_stamps("oi_ts", oi_ts)
    _validate_union_marks(union_ts)
    marks = _oi_marks(oi_ts)
    # The as-of over row indices, so the bound below reads the stamp of the row each mark takes.
    rows = align_asof(oi_ts, list(range(len(oi_ts))), marks)
    grid = [None if j is None or oi_ts[j] <= g - _BOUNDARY else levels[j] for j, g in zip(rows, marks)]
    values = dict(zip(marks, feature(grid)))
    out = [values.get(c) for c in close_grid(union_ts)]
    logger.debug(
        "%s at union closes: %d rows, %d marks, %d return indices, %d None",
        label,
        len(oi_ts),
        len(marks),
        len(out),
        out.count(None),
    )
    return out


def _oi_at_union_closes(
    label: str,
    feature: Callable[[list[float | None]], list],
    oi_ts: list[datetime],
    oi_values: list[float | None],
    union_ts: list[datetime],
) -> list:
    return _rows_at_union_closes(f"oi {label}", feature, oi_ts, "oi_values", oi_levels_from_raw(oi_values), union_ts)


def oi_grid_levels(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    return _oi_at_union_closes("level", list, oi_ts, oi_values, union_ts)


def oi_log_delta_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    return _oi_at_union_closes("log-delta", oi_log_delta, oi_ts, oi_values, union_ts)


def oi_zscore_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    zscore = partial(oi_zscore, window=_OI_ZSCORE_WINDOW)
    return _oi_at_union_closes("z-score", zscore, oi_ts, oi_values, union_ts)


def oi_momentum_grid_feature(oi_ts: list[datetime], oi_values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    momentum = partial(oi_momentum, lookback=_OI_MOMENTUM_LOOKBACK)
    return _oi_at_union_closes("momentum", momentum, oi_ts, oi_values, union_ts)


def ratio_grid_features(
    oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]
) -> dict[str, list[float | None]]:
    """Each ratio is read as a level, unmapped (docs/specs/00136 D2): a `0.0` taker ratio is an all-sell bar the venue
    published, never an OI placeholder."""
    return {
        name: _rows_at_union_closes(name, list, oi_ts, name, values, union_ts) for name, values in ratio_features(ratios).items()
    }


def liquidation_grid_features(
    bucket_ts: list[datetime],
    long_usd: list[float],
    short_usd: list[float],
    union_ts: list[datetime],
    covered: Collection[datetime],
) -> dict[str, list[float | None]]:
    """One coin's 1-minute liquidation buckets, as the subject read them, summed over each union bar (docs/specs/00136
    D3-D6). `covered` holds the hour starts the caller asserts the poller covered for the coin: a bar whose four hours it
    holds sums the buckets stamped inside it, zero where there are none, and any other bar reads None."""
    if not len(bucket_ts) == len(long_usd) == len(short_usd):
        raise AlphaError(
            f"bucket_ts, long_usd and short_usd must be equal length, got {len(bucket_ts)}, {len(long_usd)} and {len(short_usd)}"
        )
    if not bucket_ts:
        raise AlphaError("bucket_ts is empty: every covered bar would sum to zero")
    _validate_stamps("bucket_ts", bucket_ts)
    _validate_union_marks(union_ts)
    asserted = set(covered)
    for t in asserted:
        if t.utcoffset() is None or (t - _EPOCH) % _HOUR:
            raise AlphaError(f"covered must be tz-aware hour starts, got {t.isoformat()}")
    out: dict[str, list[float | None]] = {name: [] for name in _LIQUIDATION_COLUMNS}
    for t in union_ts[:-1]:
        hours = [t + k * _HOUR for k in range(_BOUNDARY // _HOUR)]
        if not asserted.issuperset(hours):
            for values in out.values():
                values.append(None)
            continue
        # A bucket covers its minute, so one stamped on the close is the next bar's (docs/specs/00136 D6).
        lo, hi = bisect_left(bucket_ts, t), bisect_left(bucket_ts, t + _BOUNDARY)
        long_sum = sum(long_usd[lo:hi], 0.0)
        short_sum = sum(short_usd[lo:hi], 0.0)
        total = long_sum + short_sum
        imbalance = None if total == 0 else (long_sum - short_sum) / total
        for name, value in zip(_LIQUIDATION_COLUMNS, (long_sum, short_sum, total, imbalance)):
            out[name].append(value)
    logger.debug(
        "liquidations at union closes: %d buckets, %d asserted hours, %d return indices, %d None",
        len(bucket_ts),
        len(asserted),
        len(union_ts) - 1,
        out[_LIQUIDATION_COLUMNS[0]].count(None),
    )
    return out


def ratio_zscore_grid_features(
    oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]
) -> dict[str, list[float | None]]:
    """Each ratio's trailing z-score over its level on the OI rows' regular grid, read at a union's closes
    (docs/specs/00138 D5)."""
    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)
    return {
        f"{name}_z30d": _rows_at_union_closes(f"{name} z-score", zscore, oi_ts, name, values, union_ts)
        for name, values in ratio_features(ratios).items()
    }


def ratio_max_signal(z_columns: dict[str, list[float | None]]) -> list[float | None]:
    """The columns' maximum at each index, None wherever any column is None (docs/specs/00138 D5)."""
    if not z_columns:
        raise AlphaError("z_columns is empty: the signal reads at least one column")
    n = _check_lengths(z_columns)
    columns = list(z_columns.values())
    return [None if any(column[k] is None for column in columns) else max(column[k] for column in columns) for k in range(n)]


def daily_zscore_grid_feature(day_ts: list[datetime], values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    """A daily series' trailing z-score at each union close (docs/specs/00138 D6): a day's value reaches a close once the
    day has ended, from the close at or after the next day's 00:00Z until the next day's own value is due, and a day the
    series lacks is None, darkening every window holding it."""
    if len(day_ts) != len(values):
        raise AlphaError(f"day_ts and values must be equal length, got {len(day_ts)} and {len(values)}")
    if not day_ts:
        raise AlphaError("day_ts is empty: no close would read a day")
    _validate_stamps("day_ts", day_ts)
    for i, t in enumerate(day_ts):
        if (t - _EPOCH) % _DAY:
            raise AlphaError(f"day_ts[{i}] = {t.isoformat()} is not a UTC day's start")
    _validate_union_marks(union_ts)
    first = day_ts[0]
    grid: list[float | None] = [None] * ((day_ts[-1] - first) // _DAY + 1)
    for t, v in zip(day_ts, values):
        grid[(t - first) // _DAY] = v
    zscores = funding_zscore(grid, window=_DAILY_ZSCORE_WINDOW)
    # The latest day a close has seen end is the one before the day the close falls in.
    days = [(c - first) // _DAY - 1 for c in close_grid(union_ts)]
    return [zscores[k] if 0 <= k < len(grid) else None for k in days]


def liquidation_hourly_totals(
    bucket_ts: list[datetime],
    long_usd: list[float],
    short_usd: list[float],
    hour_ts: list[datetime],
    covered: Collection[datetime],
) -> list[float | None]:
    """One coin's liquidated notional, both legs, in each hour of `hour_ts` (docs/specs/00138 D12): an hour the caller
    asserts covered sums the buckets stamped inside it, zero where there are none, and any other hour reads None."""
    if not len(bucket_ts) == len(long_usd) == len(short_usd):
        raise AlphaError(
            f"bucket_ts, long_usd and short_usd must be equal length, got {len(bucket_ts)}, {len(long_usd)} and {len(short_usd)}"
        )
    if not bucket_ts:
        raise AlphaError("bucket_ts is empty: every covered hour would sum to zero")
    _validate_stamps("bucket_ts", bucket_ts)
    _validate_stamps("hour_ts", hour_ts)
    for name, stamps in (("hour_ts", hour_ts), ("covered", covered)):
        for t in stamps:
            if t.utcoffset() is None or (t - _EPOCH) % _HOUR:
                raise AlphaError(f"{name} must be tz-aware hour starts, got {t.isoformat()}")
    asserted = set(covered)
    out: list[float | None] = []
    for h in hour_ts:
        if h not in asserted:
            out.append(None)
            continue
        lo, hi = bisect_left(bucket_ts, h), bisect_left(bucket_ts, h + _HOUR)
        out.append(sum(long_usd[lo:hi], 0.0) + sum(short_usd[lo:hi], 0.0))
    return out


def event_contrast(
    flags: dict[str, list[bool | None]],
    forwards: dict[str, dict[str, list[float | None]]],
    *,
    mean_block: float,
    n_resamples: int,
    seed: int,
) -> dict[str, dict[str, list[float]]]:
    """Per forward series, per asset and pooled over the assets kept: `[events, others, mean after an event, mean after
    the others, their difference, its 2.5 % and 97.5 % stationary-bootstrap bounds]` over the indices where both the flag
    and the forward value are read (docs/specs/00138 D12). One set of index draws serves every series and asset, so the
    pooled bounds keep the assets' common hours together; an asset with fewer than two events or two others in a series is
    left out of it, and a resample holding no event or no other for a row is skipped for that row."""
    n = _check_lengths({f"flags[{asset!r}]": values for asset, values in flags.items()})
    for series, by_asset in forwards.items():
        _check_paired("flags", flags, f"forwards[{series!r}]", by_asset, n)
    draws = np.array(stationary_bootstrap_indices(n, mean_block=mean_block, n_resamples=n_resamples, seed=seed))
    out: dict[str, dict[str, list[float]]] = {}
    for series, by_asset in forwards.items():
        kept = {}
        for asset, flag in flags.items():
            values = by_asset[asset]
            event = np.array([f is True and v is not None for f, v in zip(flag, values)])
            other = np.array([f is False and v is not None for f, v in zip(flag, values)])
            if event.sum() >= 2 and other.sum() >= 2:
                kept[asset] = (event, other, np.array([0.0 if v is None else v for v in values]))
        rows = {}
        for name, members in [*((asset, [member]) for asset, member in kept.items()), ("pooled", list(kept.values()))]:
            if not members:
                continue
            n_event = sum(int(event.sum()) for event, _, _ in members)
            n_other = sum(int(other.sum()) for _, other, _ in members)
            mean_event = sum(float(x[event].sum()) for event, _, x in members) / n_event
            mean_other = sum(float(x[other].sum()) for _, other, x in members) / n_other
            resampled = [(event[draws], other[draws], x[draws]) for event, other, x in members]
            boot_events = sum(e.sum(axis=1) for e, _, _ in resampled)
            boot_others = sum(o.sum(axis=1) for _, o, _ in resampled)
            usable = (boot_events > 0) & (boot_others > 0)
            if not usable.any():
                continue
            boot_event_means = sum((x * e).sum(axis=1) for e, _, x in resampled)[usable] / boot_events[usable]
            boot_other_means = sum((x * o).sum(axis=1) for _, o, x in resampled)[usable] / boot_others[usable]
            low, high = np.percentile(boot_event_means - boot_other_means, [2.5, 97.5])
            diff = mean_event - mean_other
            rows[name] = [n_event, n_other, mean_event, mean_other, diff, float(low), float(high)]
        out[series] = rows
    return out


def _check_lengths(lists: dict[str, list], expected: int | None = None) -> int:
    for name, values in lists.items():
        if expected is None:
            expected = len(values)
        elif len(values) != expected:
            raise AlphaError(f"{name} has length {len(values)}, expected {expected}")
    return 0 if expected is None else expected


def _check_paired(x_name: str, x: dict[str, list], y_name: str, y: dict[str, list], expected: int | None = None) -> int:
    if set(x) != set(y):
        raise AlphaError(f"{x_name} and {y_name} must hold the same assets, got {sorted(x)} and {sorted(y)}")
    named = {f"{x_name}[{asset!r}]": v for asset, v in x.items()} | {f"{y_name}[{asset!r}]": v for asset, v in y.items()}
    return _check_lengths(named, expected)


def derisk_scales(z_by_asset: dict[str, list[float | None]], *, config: B2Config) -> dict[str, list[float]]:
    """One-sided by ruling (docs/specs/00128 D3): a z below minus the threshold is a later trial's candidate, never read
    here through an `abs`."""
    if not isinstance(config, B2Config):
        raise AlphaError(f"config must be a B2Config, got {type(config)!r}")
    _check_lengths({f"z_by_asset[{asset!r}]": zs for asset, zs in z_by_asset.items()})
    scales = {
        asset: [config.derisk_scale if z is not None and z > config.z_threshold else 1.0 for z in zs]
        for asset, zs in z_by_asset.items()
    }
    logger.debug(
        "derisk scales: %d of %d asset-stamps scaled to %s",
        sum(s != 1.0 for values in scales.values() for s in values),
        sum(len(values) for values in scales.values()),
        config.derisk_scale,
    )
    return scales


def scale_positions(asset_positions: dict[str, list[float]], scales: dict[str, list[float]]) -> dict[str, list[float]]:
    _check_paired("asset_positions", asset_positions, "scales", scales)
    return {asset: [p * s for p, s in zip(asset_positions[asset], scales[asset])] for asset in asset_positions}


def net_of_cost(
    asset_positions: dict[str, list[float]],
    asset_returns: dict[str, list[float | None]],
    *,
    cost_per_side: float,
) -> list[float]:
    """`build_crossfreq_system`'s net-of-cost loop, copied (docs/specs/00128 D5): no test ties the two, so a change to
    that loop is made here too."""
    n = _check_paired("asset_positions", asset_positions, "asset_returns", asset_returns)
    legs = [(asset_positions[asset], asset_returns[asset]) for asset in asset_positions]
    previous = [0.0] * len(legs)
    net: list[float] = []
    for k in range(n):
        gross, turnover = 0.0, 0.0
        for i, (positions, returns) in enumerate(legs):
            p = positions[k]
            r = returns[k]
            gross += p * (0.0 if r is None else r)
            turnover += abs(p - previous[i])
            previous[i] = p
        net.append(gross - turnover * cost_per_side)
    return net


def per_year_engaged_counts(
    asset_positions: dict[str, list[float]], scales: dict[str, list[float]], close_ts: list[datetime]
) -> dict[str, int]:
    """Asset-stamps long under a scale below 1, per close year (docs/specs/00128 D6): a flat stamp at
    z > 2 is no engagement, since the overlay halves nothing there."""
    _check_paired("asset_positions", asset_positions, "scales", scales, len(close_ts))
    counts = dict.fromkeys((str(t.year) for t in close_ts), 0)
    legs = [(asset_positions[asset], scales[asset]) for asset in asset_positions]
    for positions, asset_scales in legs:
        for k, (p, s) in enumerate(zip(positions, asset_scales)):
            if p > 0 and s < 1:
                counts[str(close_ts[k].year)] += 1
    return counts


def per_year_positions_differ(a: dict[str, list[float]], b: dict[str, list[float]], close_ts: list[datetime]) -> dict[str, int]:
    _check_paired("a", a, "b", b, len(close_ts))
    years = [str(t.year) for t in close_ts]
    counts = dict.fromkeys(years, 0)
    legs = [(a[asset], b[asset]) for asset in a]
    for k, year in enumerate(years):
        if any(x[k] != y[k] for x, y in legs):
            counts[year] += 1
    return counts


def per_year_turnover(asset_positions: dict[str, list[float]], close_ts: list[datetime]) -> dict[str, float]:
    _check_lengths({f"asset_positions[{asset!r}]": v for asset, v in asset_positions.items()}, len(close_ts))
    years = [str(t.year) for t in close_ts]
    totals = dict.fromkeys(years, 0.0)
    for positions in asset_positions.values():
        previous = 0.0
        for k, p in enumerate(positions):
            totals[years[k]] += abs(p - previous)
            previous = p
    return totals


def per_year_max_drawdown(returns: list[float], close_ts: list[datetime]) -> dict[str, float]:
    _check_lengths({"returns": returns}, len(close_ts))
    by_year: dict[str, list[float]] = {}
    for r, t in zip(returns, close_ts):
        by_year.setdefault(str(t.year), []).append(r)
    return {year: max_drawdown(slice_) for year, slice_ in by_year.items()}
