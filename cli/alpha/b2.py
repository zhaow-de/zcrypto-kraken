from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from cli.alpha.errors import AlphaError
from cli.features.derivatives import align_asof, funding_zscore
from cli.logging import get_logger

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


# The close of return index k, never the bar-open ts[k] (one bar stale) nor ts[k + 1] + 4h (a 4h look-ahead).
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
