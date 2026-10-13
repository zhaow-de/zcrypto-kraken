from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from cli.alpha.errors import AlphaError
from cli.features.derivatives import align_asof, funding_zscore
from cli.logging import get_logger
from cli.validation import max_drawdown

logger = get_logger("alpha.b2")

_BOUNDARY = timedelta(hours=4)
# A ruling (docs/specs/00128 D2), not a knob: a print within this of its hour is that hour's settlement.
_STAMP_TOLERANCE = timedelta(seconds=60)
_FUNDING_INTERVAL_HOURS = 8


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


def funding_grid_feature(
    prints_ts: list[datetime],
    prints_rate: list[float | None],
    prints_interval_hours: list[int],
    union_ts: list[datetime],
    *,
    config: B2Config,
) -> list[float | None]:
    """The trailing funding z-score as-of each return index's close (docs/specs/00128 D2): the union's
    bar-open stamps in, `len(union_ts) - 1` values out. Both stamp rulings live here -- the print
    stamp truncated to its hour, and the grid `close_grid` -- so a caller hands raw stamps and
    shifts none itself. An off-cadence print is mapped to None before the z-score, never dropped:
    dropping it would let a window span a different horizon under the same label."""
    if not isinstance(config, B2Config):
        raise AlphaError(f"config must be a B2Config, got {type(config)!r}")
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
    z = funding_zscore(rates, window=config.z_window)
    logger.debug(
        "funding grid feature: %d prints, %d off-cadence mapped to None, %d return indices",
        len(prints_ts),
        sum(h != _FUNDING_INTERVAL_HOURS for h in prints_interval_hours),
        len(union_ts) - 1,
    )
    return align_asof(normalised, z, close_grid(union_ts))


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
