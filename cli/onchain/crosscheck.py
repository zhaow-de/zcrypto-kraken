"""The cross-check of the snapshot against Coin Metrics at Coin Metrics' own price (spec D13): three ratios a day, their
distributions per year, over all days and over the span, and the tolerance over the span that stops a reading."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import polars as pl

from cli.logging import get_logger
from cli.onchain.freeze import SNAPSHOT_RELPATH
from cli.registry.observed import ObservedReader
from cli.vintage.asof import as_of
from cli.vintage.table import TableRead, read_table

MEDIAN_BAR = 0.02
P99_BAR = 0.10
SPAN = (date(2010, 8, 16), date(2026, 3, 30))
CM_SERIES = ("cm/btc/CapMVRVCur", "cm/btc/PriceUSD", "cm/btc/SplyCur")
RATIOS = ("r_mvrv", "r_price", "r_supply")
SIDES = ("snapshot", "vendor")

log = get_logger("onchain.crosscheck")


def _number(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _divisor(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _served(days: dict[date, str | None], day: date) -> float | None:
    """The vendor's value on `day` from that day's own token: None where it serves no version of the day, or where the
    current one is a retraction, whose token is null."""
    token = days.get(day)
    return None if token is None else float(token)


def _side(ours: bool, theirs: bool) -> str | None:
    if not ours:
        return "snapshot"
    return None if theirs else "vendor"


def ratios(
    snapshot: pl.DataFrame, cm: dict[str, dict[date, str | None]]
) -> tuple[dict[str, dict[date, float]], dict[str, dict[date, str]]]:
    """Over every day the snapshot or the vendor holds, `r_mvrv = (PriceUSD × supply / realized_cap) / CapMVRVCur − 1`,
    `r_price = price / PriceUSD − 1` and `r_supply = supply / SplyCur − 1`; beside them each ratio's left-out days, a
    day the snapshot's where any operand of ours is absent or unusable, else the vendor's. Nothing is filled."""
    ours = {row[0].date(): row[1:] for row in snapshot.select("ts", "price", "supply", "realized_cap").iter_rows()}
    mvrv_days, price_days, supply_days = (cm.get(series, {}) for series in CM_SERIES)
    values: dict[str, dict[date, float]] = {name: {} for name in RATIOS}
    left_out: dict[str, dict[date, str]] = {name: {} for name in RATIOS}
    for day in sorted({*ours, *mvrv_days, *price_days, *supply_days}):
        price, supply, realized = ours.get(day, (None, None, None))
        their_mvrv, their_price, their_supply = (_served(days, day) for days in (mvrv_days, price_days, supply_days))
        sides = {
            "r_mvrv": _side(_number(supply) and _divisor(realized), _number(their_price) and _divisor(their_mvrv)),
            "r_price": _side(_number(price), _divisor(their_price)),
            "r_supply": _side(_number(supply), _divisor(their_supply)),
        }
        for name, side in sides.items():
            if side is not None:
                left_out[name][day] = side
        if sides["r_mvrv"] is None:
            values["r_mvrv"][day] = (their_price * supply / realized) / their_mvrv - 1
        if sides["r_price"] is None:
            values["r_price"][day] = price / their_price - 1
        if sides["r_supply"] is None:
            values["r_supply"][day] = supply / their_supply - 1
    return values, left_out


def _distribution(values: list[float], sides: list[str]) -> dict:
    """The percentiles interpolate linearly between the two nearest ranks; with no value, each statistic is None."""
    absolute = pl.Series(values, dtype=pl.Float64).abs()
    return {
        "n": absolute.len(),
        "median": absolute.median(),
        "p95": absolute.quantile(0.95, "linear"),
        "p99": absolute.quantile(0.99, "linear"),
        "max": absolute.max(),
        "left_out": {side: sides.count(side) for side in SIDES},
    }


def _line(ratios: dict[str, dict[date, float]], left_out: dict[str, dict[date, str]], keep: Callable[[date], bool]) -> dict:
    return {
        name: _distribution(
            [value for day, value in ratios[name].items() if keep(day)],
            [side for day, side in left_out[name].items() if keep(day)],
        )
        for name in RATIOS
    }


def summary(ratios: dict[str, dict[date, float]], left_out: dict[str, dict[date, str]], span: tuple[date, date]) -> dict:
    """A line per calendar year a ratio or a left-out day falls in, keyed by the year, then `all` and `span`: per ratio,
    the count compared, the median, 95th and 99th percentile and maximum of its absolute value, and the days left out
    per side."""
    first, last = span
    years = sorted({day.year for name in RATIOS for day in (*ratios[name], *left_out[name])})
    report = {str(year): _line(ratios, left_out, lambda day, year=year: day.year == year) for year in years}
    report["all"] = _line(ratios, left_out, lambda day: True)
    report["span"] = _line(ratios, left_out, lambda day: first <= day <= last)
    return report


def _vendor(read: TableRead, t: datetime) -> dict[str, dict[date, str | None]]:
    # `as_of` reads a (series, day) from its own series' versions and coverage and from its tick's facts alone, so the
    # three series' rows give their days what the whole table would.
    kept = (pl.col("provider") == "coinmetrics") & pl.col("series").is_in(list(CM_SERIES))
    current = as_of(read.versions.filter(kept), read.coverage.filter(kept), read.later_facts, t)
    cm: dict[str, dict[date, str | None]] = {series: {} for series in CM_SERIES}
    for row in current.iter_rows(named=True):
        cm[row["series"]][row["ts"].date()] = row["token"]
    return cm


def _shown(value: float | None) -> str:
    return "none" if value is None else f"{value:.6g}"


def _printed(line: dict) -> str:
    return " ".join(
        f"{name} n={s['n']} median={_shown(s['median'])} p95={_shown(s['p95'])} p99={_shown(s['p99'])} max={_shown(s['max'])} "
        f"left_out=snapshot:{s['left_out']['snapshot']},vendor:{s['left_out']['vendor']}"
        for name, s in line.items()
    )


def _failures(compared: dict, left_out: dict[date, str]) -> list[str]:
    first, last = SPAN
    failures = []
    if compared["n"] == 0:
        failures.append(f"the span {first}..{last} holds no day r_mvrv compares")
    else:
        if compared["median"] > MEDIAN_BAR:
            failures.append(f"the span's median |r_mvrv| {_shown(compared['median'])} is above {MEDIAN_BAR}")
        if compared["p99"] > P99_BAR:
            failures.append(f"the span's 99th percentile of |r_mvrv| {_shown(compared['p99'])} is above {P99_BAR}")
    for day, side in sorted(left_out.items()):
        if first <= day <= last and side == "snapshot":
            failures.append(f"{day} is inside the span and the snapshot leaves it out of r_mvrv")
    return failures


def crosscheck(snapshot_dir: Path, versions_root: Path, *, generation: int, head: str) -> int:
    """The snapshot read as a frozen set and Coin Metrics' three series read through `head` as of its latest row, the
    summary logged a line each; 1 where the span fails the tolerance, each reason its own ERROR line, else 0."""
    snapshot = ObservedReader(snapshot_dir.parent).read_series(snapshot_dir.name, SNAPSHOT_RELPATH)
    read = read_table(versions_root, generation, head)
    # A head's tick stamp is the tick's start, and its own rows are knowable after it: `t` at the stamp would leave out
    # the head's own tick.
    t = pl.concat([read.versions["knowable_at"], read.coverage["knowable_at"]]).max()
    values, left_out = ratios(snapshot, _vendor(read, t))
    report = summary(values, left_out, SPAN)
    first, last = SPAN
    for label, line in report.items():
        shown = f"span={first}..{last}" if label == "span" else label if label == "all" else f"year={label}"
        log.info("onchain crosscheck %s %s", shown, _printed(line))
    failures = _failures(report["span"]["r_mvrv"], left_out["r_mvrv"])
    for failure in failures:
        log.error("onchain crosscheck failed snapshot=%s reason=%s", snapshot_dir.name, failure)
    if failures:
        return 1
    log.info("onchain crosscheck passed snapshot=%s head=%s span=%s..%s", snapshot_dir.name, head, first, last)
    return 0
