"""B1 trial 3 (docs/specs/00132-b1-hourly-rv-weights-design.md): the hourly realized-variance inverse weights (D2), arm B's
A2 book on given weights (D3) and the engagement helpers (D7).

Every stamp is its bar's open: the weights read the hourly bars closing in arm A's span, each return reaching back across a gap.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from datetime import datetime, timedelta

from cli.alpha.a1 import _asset_returns, _inverse_vol_weights, _validate_prices_by_asset
from cli.alpha.a2 import A2Config, _asset_directions_a2
from cli.alpha.errors import AlphaError
from cli.benchmark.strategies import vol_target

_H1 = timedelta(hours=1)
_H4 = timedelta(hours=4)


def _squared_log_returns(stamps: list[datetime], closes: list[float]) -> list[float]:
    for i, h in enumerate(stamps):
        if h.tzinfo is None:
            raise AlphaError(f"hourly stamps must be tz-aware, got {h!r} at index {i}")
        if i and h <= stamps[i - 1]:
            raise AlphaError(f"hourly stamps must be strictly increasing, violated at index {i} ({h.isoformat()})")
    for i, c in enumerate(closes):
        if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) or c <= 0:
            raise AlphaError(f"hourly closes must be finite numbers above 0, got {c!r} at index {i}")
    # Index 0 is a placeholder: the no-predecessor refusal keeps every window off it.
    return [0.0] + [math.log(closes[i] / closes[i - 1]) ** 2 for i in range(1, len(closes))]


def hourly_rv_inverse_vol_weights(
    prices_by_asset: dict[str, list[float | None]],
    union_ts: list[datetime],
    hourly_by_asset: dict[str, tuple[list[datetime], list[float]]],
    *,
    lookback: int,
) -> list[dict[str, float]]:
    """One dict per return index. An asset is weighted at `t` exactly when `_inverse_vol_weights` weights it there, so the
    two arms' asset sets are identical by construction, and a window this estimator cannot read is refused, never dropped."""
    _validate_prices_by_asset(prices_by_asset)
    n = len(next(iter(prices_by_asset.values())))
    if len(union_ts) != n:
        raise AlphaError(f"union_ts must have the price lists' length {n}, got {len(union_ts)}")
    for k, ts in enumerate(union_ts):
        if ts.tzinfo is None:
            raise AlphaError(f"union_ts stamps must be tz-aware, got {ts!r} at index {k}")
        if k and ts <= union_ts[k - 1]:
            raise AlphaError(f"union_ts must be strictly increasing, violated at index {k} ({ts.isoformat()})")
    if set(hourly_by_asset) != set(prices_by_asset):
        raise AlphaError(
            f"hourly_by_asset must hold exactly the price assets {sorted(prices_by_asset)}, got {sorted(hourly_by_asset)}"
        )

    weights_a = _inverse_vol_weights(prices_by_asset, lookback=lookback)
    squared = {asset: _squared_log_returns(stamps, closes) for asset, (stamps, closes) in hourly_by_asset.items()}
    closes_at = {asset: [h + _H1 for h in stamps] for asset, (stamps, _) in hourly_by_asset.items()}

    weights: list[dict[str, float]] = []
    for t in range(len(weights_a)):
        inv: dict[str, float] = {}
        for asset in weights_a[t]:
            lo = bisect_right(closes_at[asset], union_ts[t - lookback] + _H4)
            hi = bisect_right(closes_at[asset], union_ts[t] + _H4)
            where = f"{asset!r} at {union_ts[t].isoformat()} (return index {t})"
            if hi == lo:
                raise AlphaError(f"{where}: no hourly bar closes inside the window")
            if lo == 0:
                raise AlphaError(f"{where}: the window's first hourly bar has no predecessor row")
            rv = math.fsum(squared[asset][lo:hi])
            if rv == 0:
                raise AlphaError(f"{where}: the window's hourly realized variance is 0")
            inv[asset] = 1.0 / math.sqrt(rv / lookback)
        total = sum(inv.values())
        weights.append({asset: v / total for asset, v in inv.items()})
    return weights


def a2_positions_with_weights(
    prices_by_asset: dict[str, list[float | None]], weights: list[dict[str, float]], *, config: A2Config
) -> dict[str, list[float]]:
    """`a2_book_returns`' body with `weights` in place of its `_inverse_vol_weights` call, returning the asset positions alone."""
    if not isinstance(config, A2Config):
        raise AlphaError(f"config must be an A2Config, got {type(config)!r}")
    _validate_prices_by_asset(prices_by_asset)
    length = len(prices_by_asset["BTC"])
    if len(weights) != length - 1:
        raise AlphaError(f"weights must hold one dict per return index, {length - 1}, got {len(weights)}")
    for k, w in enumerate(weights):
        if not set(w) <= set(prices_by_asset):
            raise AlphaError(f"weights at return index {k} name assets the prices lack: {sorted(set(w) - set(prices_by_asset))}")

    union_ts = list(range(length))
    asset_ts: dict[str, list] = {
        asset: [k for k, p in enumerate(prices) if p is not None] for asset, prices in prices_by_asset.items()
    }

    directions = _asset_directions_a2(prices_by_asset, union_ts, asset_ts, config=config)
    returns = {asset: _asset_returns(prices) for asset, prices in prices_by_asset.items()}

    book_base_returns: list[float] = []
    for k in range(length - 1):
        total = 0.0
        for asset in prices_by_asset:
            r = returns[asset][k]
            d = directions[asset][k]
            if r is None or d is None:
                continue
            total += weights[k].get(asset, 0.0) * d * r
        book_base_returns.append(total)

    positions = vol_target(
        book_base_returns,
        target_vol=config.target_vol / math.sqrt(config.periods_per_year),
        lookback=config.vol_lookback,
        max_leverage=config.max_leverage,
    )
    return {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * positions[k] for k in range(length - 1)]
        for asset in prices_by_asset
    }


def weights_differ_count(weights_a: list[dict[str, float]], weights_b: list[dict[str, float]]) -> int:
    if len(weights_a) != len(weights_b):
        raise AlphaError(f"weights_a and weights_b must have equal length, got {len(weights_a)} and {len(weights_b)}")
    for k, (wa, wb) in enumerate(zip(weights_a, weights_b)):
        if set(wa) != set(wb):
            raise AlphaError(
                "weights_a and weights_b must weight the same assets at every return index, "
                f"differ at return index {k}: {sorted(wa)} against {sorted(wb)}"
            )
    return sum(wa != wb for wa, wb in zip(weights_a, weights_b))


def weight_total_variation(weights: list[dict[str, float]]) -> float:
    terms: list[float] = []
    previous: dict[str, float] = {}
    for w in weights:
        terms += [abs(w.get(a, 0.0) - previous.get(a, 0.0)) for a in set(w) | set(previous)]
        previous = w
    return math.fsum(terms)


def per_year_mean_weights(
    weights_a: list[dict[str, float]], weights_b: list[dict[str, float]], union_ts: list[datetime], assets: list[str]
) -> dict[str, dict[str, list[float]]]:
    """`{asset: {year: [arm B's mean, arm A's mean]}}`, arm B's first though `weights_a` is the first argument; the year is
    `union_ts[k]`'s, the bar's start."""
    if len(union_ts) != len(weights_a) + 1 or len(weights_b) != len(weights_a):
        raise AlphaError(
            "union_ts must hold one stamp more than weights_a has dicts, and weights_b as many dicts as weights_a; "
            f"got {len(union_ts)} stamps, {len(weights_a)} and {len(weights_b)} dicts"
        )
    indices_by_year: dict[str, list[int]] = {}
    for k in range(len(weights_a)):
        indices_by_year.setdefault(str(union_ts[k].year), []).append(k)
    means: dict[str, dict[str, list[float]]] = {}
    for asset in assets:
        means[asset] = {}
        for year, ks in indices_by_year.items():
            mean_b = statistics.fmean([weights_b[k].get(asset, 0.0) for k in ks])
            mean_a = statistics.fmean([weights_a[k].get(asset, 0.0) for k in ks])
            means[asset][year] = [mean_b, mean_a]
    return means
