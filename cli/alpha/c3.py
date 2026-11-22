"""C3's on-chain reading: the pure functions (docs/specs/00164-t0228-btc-onchain-design.md D6, D12)."""

from __future__ import annotations

import bisect
import math
import statistics
from datetime import date, datetime, timedelta

from cli.alpha.a1 import A1Config, a1_book_returns
from cli.portfolio.crossfreq_system import _A1_CADENCE, _block_start, _dummy_close, _ffill_btc

FEATURES = ("mvrv", "mvrv_z", "asopr", "sth_supply_share")
TAILS = ("low", "high")
STATES = ("long", "flat")
HORIZONS = (7, 30)
LOW = 0.10
HIGH = 0.90
MIN_HISTORY = 365
LAG_DAYS = 1
MEAN_BLOCK = 102
N_RESAMPLES = 10_000
SEED = 42
FAR = (0.078125, 99.921875)
COST_ROUND_TRIP = 0.012
MIN_EVENT_YEARS = 4


def bands(values: list[float | None]) -> list[str | None]:
    seen: list[float] = []
    out: list[str | None] = []
    for v in values:
        if v is None or not math.isfinite(v):
            out.append(None)
            continue
        bisect.insort(seen, v)
        n = len(seen)
        p = bisect.bisect_right(seen, v) / n
        if n < MIN_HISTORY:
            out.append(None)
        elif p <= LOW:
            out.append("low")
        elif p >= HIGH:
            out.append("high")
        else:
            out.append("mid")
    return out


def lagged[T](by_day: dict[date, T], grid: list[datetime]) -> list[T | None]:
    return [by_day.get(stamp.date() - timedelta(days=LAG_DAYS)) for stamp in grid]


def a1_daily_positions(daily_prices: dict[str, list[float | None]]) -> dict[str, list[float]]:
    """`build_crossfreq_system`'s A1 rows before their expansion, `daily_prices` in its `config.assets` order:
    `a1_book_returns` sums over the assets in the dict's order."""
    d_pf = _ffill_btc({a: list(closes) + [_dummy_close(closes)] for a, closes in daily_prices.items()})
    n_rows_d = len(d_pf["BTC"]) - 1
    ap_a1 = a1_book_returns(
        d_pf, d_pf["BTC"], config=A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    )["asset_positions"]
    held = [{a: [ap_a1[a][_block_start(k, o)] for k in range(n_rows_d)] for a in d_pf} for o in range(_A1_CADENCE)]
    return {a: [statistics.mean(held[o][a][k] for o in range(_A1_CADENCE)) for k in range(n_rows_d)] for a in d_pf}


def states(positions: dict[str, list[float]], prices: dict[str, list[float | None]]) -> dict[str, list[str | None]]:
    out: dict[str, list[str | None]] = {}
    for asset, held in positions.items():
        out[asset] = [None if close is None else "long" if p > 0 else "flat" for p, close in zip(held, prices[asset], strict=True)]
    return out


def flags(band: list[str | None], state: list[str | None], *, tail: str, in_state: str) -> list[bool | None]:
    return [None if s != in_state or b is None else b == tail for b, s in zip(band, state, strict=True)]


def forwards(prices: list[float | None], horizon: int) -> tuple[list[float | None], list[float | None]]:
    """The summed returns count a missing return 0, as `net_of_cost` counts it (spec 00140 D5)."""
    returns = [None if a is None or b is None else b / a - 1 for a, b in zip(prices, prices[1:])]
    log: list[float | None] = []
    summed: list[float | None] = []
    for k, close in enumerate(prices):
        end = k + horizon
        if end >= len(prices) or close is None or prices[end] is None:
            log.append(None)
            summed.append(None)
        else:
            log.append(math.log(prices[end] / close))
            summed.append(sum(0.0 if r is None else r for r in returns[k:end]))
    return log, summed


def cell_name(feature: str, tail: str, state: str, horizon: int) -> str:
    return f"{feature}|{tail}|{state}|H{horizon}"


def event_years(flags: dict[str, list[bool | None]], forwards: dict[str, list[float | None]], years: list[int]) -> dict[str, int]:
    """The years of the events `event_contrast_blocks` pools: an asset's count only where it keeps two events and two
    others whose forward is read."""
    counts: dict[str, int] = {}
    for asset, flag in flags.items():
        read = list(zip(flag, forwards[asset], years, strict=True))
        events = [year for f, v, year in read if f is True and v is not None]
        others = sum(1 for f, v, _ in read if f is False and v is not None)
        if len(events) >= 2 and others >= 2:
            for year in events:
                counts[str(year)] = counts.get(str(year), 0) + 1
    return dict(sorted(counts.items()))
