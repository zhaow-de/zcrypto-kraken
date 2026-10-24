"""B4 trial 1 (docs/specs/00144-b4-ratio-legs-design.md): a ratio leg's EUR return (D4), the per-base exposures an
instrument book decomposes into and the quote's shortfall and its carry (D5), §10's limits as one factor per bar (D6), the
legs held to the book's own quote (D7) and the per-year engagement counts (D9).

A position is a fraction of NAV in EUR notional held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from datetime import datetime

from cli.alpha.errors import AlphaError
from cli.risk.limits import apply_gross_leverage_cap, apply_margin_floor, apply_net_exposure_band

LIMITS = ("gross", "net", "margin")


def _check_price(name: str, k: int, p: float | None, *, missing: bool) -> None:
    if p is None and missing:
        return
    if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p <= 0:
        raise AlphaError(f"{name} must hold finite numbers above 0{' or None' if missing else ''}, got {p!r} at index {k}")


def ratio_eur_returns(ratio: list[float | None], quote_eur: list[float]) -> list[float | None]:
    """Per unit of EUR notional set at the bar's open, `(R[k+1]/R[k] - 1) * (Q[k+1]/Q[k])`: the gain in the quote's units
    converted at the bar's closing quote price, which equals the base's EUR return less the quote's; None where the ratio
    has no close at either end."""
    if len(ratio) != len(quote_eur):
        raise AlphaError(f"the ratio's {len(ratio)} closes and the quote's {len(quote_eur)} must be equal in number")
    for k, (r, q) in enumerate(zip(ratio, quote_eur)):
        _check_price("the ratio's closes", k, r, missing=True)
        _check_price("the quote's EUR closes", k, q, missing=False)
    return [
        None if ratio[k] is None or ratio[k + 1] is None else (ratio[k + 1] / ratio[k] - 1) * (quote_eur[k + 1] / quote_eur[k])
        for k in range(len(ratio) - 1)
    ]


def _check_lengths(positions: Mapping[str, list[float]]) -> int:
    lengths = {len(v) for v in positions.values()}
    if len(lengths) != 1:
        raise AlphaError(f"every instrument's positions must be equal in number, got lengths {sorted(lengths)}")
    return lengths.pop()


def base_exposures(positions: Mapping[str, list[float]], legs: Mapping[str, tuple[str, str]]) -> dict[str, list[float]]:
    """A leg `(base, quote)` at `p` adds `+p` to its base and `-p` to its quote; any other instrument is its own base."""
    _check_lengths(positions)
    out = {i: list(v) for i, v in positions.items() if i not in legs}
    for leg, (base, quote) in legs.items():
        if base not in out or quote not in out:
            raise AlphaError(f"{leg}'s base {base} and quote {quote} must each be an instrument of the book")
        if leg not in positions:
            continue
        for k, p in enumerate(positions[leg]):
            out[base][k] += p
            out[quote][k] -= p
    return out


def limit_factors(exposures: dict[str, list[float]]) -> tuple[list[float], dict[str, list[bool]]]:
    """§10's gross cap, net band and margin floor at their ratified values, in the order gross cap, net band, margin floor,
    with no position caps: each scales a bar whole, so the bar's factor is 1.0 where none engages, else the limited gross
    over the unlimited; and each limit's engaged bars."""
    n = _check_lengths(exposures)
    gross = apply_gross_leverage_cap(exposures, soft_cap=1.5, hard_cap=2.0)
    net = apply_net_exposure_band(gross, short_bound=-0.5, long_bound=1.0)
    floor = apply_margin_floor(net, floor=2.5)
    engaged = {
        name: [any(before[a][k] != after[a][k] for a in before) for k in range(n)]
        for name, before, after in zip(LIMITS, (exposures, gross, net), (gross, net, floor), strict=True)
    }
    factors = [
        1.0
        if all(floor[a][k] == exposures[a][k] for a in exposures)
        else math.fsum(abs(floor[a][k]) for a in floor) / math.fsum(abs(exposures[a][k]) for a in exposures)
        for k in range(n)
    ]
    return factors, engaged


def scale_bars(positions: Mapping[str, list[float]], factors: list[float]) -> dict[str, list[float]]:
    if _check_lengths(positions) != len(factors):
        raise AlphaError(f"{len(factors)} factors for positions of another length")
    return {i: [p * f for p, f in zip(v, factors)] for i, v in positions.items()}


def quote_shortfall(exposures: Mapping[str, list[float]], quote: str) -> list[float]:
    """What the book borrows of `quote`: its net exposure's short part, the book's own holding netted first."""
    return [max(0.0, -e) for e in exposures[quote]]


def shortfall_carry(shortfall: list[float], *, rate: float) -> list[float]:
    """Each bar's rollover on the amount borrowed, plus the opening charge on what the bar adds to it:
    `rate * (S[k] + max(0, S[k] - S[k-1]))`, nothing borrowed before the first bar."""
    if not math.isfinite(rate) or rate < 0:
        raise AlphaError(f"rate must be a finite number >= 0, got {rate!r}")
    previous = [0.0, *shortfall[:-1]]
    return [rate * (s + max(0.0, s - p)) for s, p in zip(shortfall, previous)]


def borrow_unavailable(
    positions: Mapping[str, list[float]], legs: Mapping[str, tuple[str, str]], quote: str
) -> dict[str, list[float]]:
    """The legs on `quote` scaled each bar by `min(1, holding / their sum)`, the holding the book's own `quote` instrument,
    1 where the legs hold nothing: their short of the quote never exceeds what the book holds of it."""
    n = _check_lengths(positions)
    on_quote = [leg for leg, (_, q) in legs.items() if q == quote and leg in positions]
    if quote not in positions:
        raise AlphaError(f"the book holds no {quote} instrument to cover its legs")
    scales = []
    for k in range(n):
        total = sum(positions[leg][k] for leg in on_quote)
        scales.append(1.0 if total == 0 else min(1.0, max(0.0, positions[quote][k]) / total))
    return {i: [p * s for p, s in zip(v, scales)] if i in on_quote else list(v) for i, v in positions.items()}


def per_year_counts(flags: list[bool], close_ts: list[datetime]) -> dict[str, int]:
    """True flags per close year, every year the closes span keyed."""
    if len(flags) != len(close_ts):
        raise AlphaError(f"{len(flags)} flags for {len(close_ts)} closes")
    counts = dict.fromkeys((str(t.year) for t in close_ts), 0)
    for flag, t in zip(flags, close_ts):
        counts[str(t.year)] += int(flag)
    return counts


def _by_year(values: list[float], close_ts: list[datetime]) -> dict[str, list[float]]:
    if len(values) != len(close_ts):
        raise AlphaError(f"{len(values)} values for {len(close_ts)} closes")
    out: dict[str, list[float]] = {}
    for v, t in zip(values, close_ts):
        out.setdefault(str(t.year), []).append(v)
    return out


def per_year_sums(values: list[float], close_ts: list[datetime]) -> dict[str, float]:
    return {year: math.fsum(vs) for year, vs in _by_year(values, close_ts).items()}


def per_year_means(values: list[float], close_ts: list[datetime]) -> dict[str, float]:
    return {year: statistics.fmean(vs) for year, vs in _by_year(values, close_ts).items()}
