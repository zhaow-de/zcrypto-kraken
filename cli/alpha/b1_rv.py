"""B1 trial 3's hourly realized-variance inverse weights (docs/specs/00132-b1-hourly-rv-weights-design.md, D2).

Every stamp is its bar's open, so the window at return index `t` holds the hourly bars whose close stamp `h + 1h` lies in
`(union_ts[t - lookback] + 4h, union_ts[t] + 4h]`: arm A's span, its last close the decision instant.
Each windowed bar's log return reaches back to the asset's previous present hourly bar however many hours back, so a gap's
move is counted once, never dropped.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import datetime, timedelta

from cli.alpha.a1 import _inverse_vol_weights, _validate_prices_by_asset
from cli.alpha.errors import AlphaError

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
