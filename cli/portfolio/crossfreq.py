"""Cross-frequency combination primitives — 00038 §Construction items 1 and 4.

Two index-mapping helpers the P1 cross-frequency fold-in needs: a daily book's per-asset positions
held across their day's intraday bars (interval mapping (daily_ts[k], daily_ts[k+1]] — no look-ahead
by construction, since position[k] was decided AT daily_ts[k] and every intraday bar receiving it
ends strictly after daily_ts[k]); and the §10 governor evaluated at its ratified daily cadence on a
calendar-day-compounded intraday series, broadcast back to that day's own bars (day t's multiplier
is fixed from governed state through day t-1, per the governor's own no-look-ahead contract —
unchanged here, only broadcast). See docs/specs/00038-cross-frequency-combination-design.md and the
decisions log [iter-077].
"""

from __future__ import annotations

import math

from cli.portfolio.errors import PortfolioError
from cli.risk import GovernorConfig, drawdown_governor


def expand_daily_positions(daily_positions: dict[str, list[float]], daily_ts: list, intraday_ts: list) -> dict[str, list[float]]:
    """Hold each daily position across the intraday bars inside its (daily_ts[k], daily_ts[k+1]] interval.

    Intraday return bar j (moving intraday_ts[j] -> intraday_ts[j+1]) gets daily_positions[.][k] where
    daily_ts[k] < intraday_ts[j+1] <= daily_ts[k+1]. Bars whose end lies at-or-before daily_ts[0], or
    after daily_ts[-1], get 0.0. Both ts arrays must be sorted; a single forward scan exploits that.
    """
    if not isinstance(daily_positions, dict) or not daily_positions:
        raise PortfolioError(f"daily_positions must be a non-empty dict, got {daily_positions!r}")
    lengths = {len(series) for series in daily_positions.values()}
    if len(lengths) != 1:
        raise PortfolioError(f"daily_positions series must all have equal length, got lengths {lengths!r}")
    n_days = lengths.pop()
    if not isinstance(daily_ts, list) or len(daily_ts) != n_days + 1:
        raise PortfolioError(f"daily_ts must have length {n_days + 1} (len(daily_positions)+1), got {daily_ts!r}")
    if not isinstance(intraday_ts, list):
        raise PortfolioError(f"intraday_ts must be a list, got {intraday_ts!r}")
    for name, ts in (("daily_ts", daily_ts), ("intraday_ts", intraday_ts)):
        if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
            raise PortfolioError(f"{name} must be strictly sorted ascending, got {ts!r}")
    for asset, series in daily_positions.items():
        for p in series:
            if not isinstance(p, (int, float)) or not math.isfinite(p):
                raise PortfolioError(f"daily_positions[{asset!r}] must contain finite numbers, got {p!r}")

    n_intraday = len(intraday_ts) - 1
    out = {a: [0.0] * n_intraday for a in daily_positions}
    k = 0
    for j in range(n_intraday):
        end = intraday_ts[j + 1]
        while k < n_days and end > daily_ts[k + 1]:
            k += 1
        if k >= n_days or end <= daily_ts[k]:
            continue  # outside the daily book's life -> stays 0.0
        for a, series in daily_positions.items():
            out[a][j] = series[k]
    return out


def daily_cadence_governor(
    intraday_returns: list[float], day_index: list[int], config: GovernorConfig = GovernorConfig()
) -> list[float]:
    """Compound intraday returns within each calendar day, govern the day series, broadcast per-bar.

    day_index[j] is the calendar-day ordinal of intraday return bar j (non-decreasing, no gaps
    required). day_return[d] = prod(1 + r_j for j in day d) - 1; the unchanged drawdown_governor
    runs on that day series; bar j gets its own day's multiplier.
    """
    if not isinstance(intraday_returns, list) or not intraday_returns:
        raise PortfolioError(f"intraday_returns must be a non-empty list, got {intraday_returns!r}")
    if not isinstance(day_index, list) or len(day_index) != len(intraday_returns):
        raise PortfolioError(
            f"day_index must be a list the same length as intraday_returns ({len(intraday_returns)}), got {day_index!r}"
        )
    for r in intraday_returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r) or r <= -1.0:
            raise PortfolioError(f"intraday_returns must be finite numbers > -1, got {r!r}")
    if not isinstance(day_index[0], int) or day_index[0] < 0:
        raise PortfolioError(f"day_index must start at an int >= 0, got {day_index[0]!r}")
    for i in range(1, len(day_index)):
        if not isinstance(day_index[i], int) or day_index[i] < day_index[i - 1]:
            raise PortfolioError(f"day_index must be non-decreasing ints, got {day_index!r}")

    unique_days: list[int] = []
    day_returns: list[float] = []
    cur_day = None
    cur_compound = 1.0
    for j, d in enumerate(day_index):
        if d != cur_day:
            if cur_day is not None:
                day_returns.append(cur_compound - 1.0)
            unique_days.append(d)
            cur_day = d
            cur_compound = 1.0
        cur_compound *= 1.0 + intraday_returns[j]
    day_returns.append(cur_compound - 1.0)

    gov = drawdown_governor(day_returns, config=config)
    mult_by_day = dict(zip(unique_days, gov.multipliers))
    return [mult_by_day[d] for d in day_index]
