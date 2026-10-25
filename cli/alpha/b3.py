"""B3 trial 1's compute (docs/specs/00147-b3-rank-tilt-design.md D3): the A2 book with its long weights tilted at each
close by a cross-sectional momentum rank."""

from __future__ import annotations

import math

from cli.alpha.a1 import _asset_returns, _check_window, _inverse_vol_weights, _validate_prices_by_asset
from cli.alpha.a2 import A2Config, _asset_directions_a2
from cli.alpha.errors import AlphaError
from cli.backtest import run_backtest
from cli.benchmark.strategies import vol_target


def momentum_scores(prices: list[float | None], *, lookback: int) -> list[float | None]:
    """Per return index k, `p[k] / p[k - lookback] - 1`, known at close k; None where either close is missing."""
    _check_window("lookback", lookback)
    return [
        None if k < lookback or prices[k] is None or prices[k - lookback] is None else prices[k] / prices[k - lookback] - 1
        for k in range(len(prices) - 1)
    ]


def centred_ranks(scores: dict[str, float]) -> dict[str, float]:
    """Each score's ascending rank, ties at their average rank, as `(2 * rank - (n + 1)) / (n - 1)`: the weakest -1, the
    strongest +1."""
    n = len(scores)
    if n < 2:
        raise AlphaError(f"a rank needs 2 scores or more, got {n}")
    order = sorted(scores, key=scores.__getitem__)
    out: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        rank = (i + j + 2) / 2
        for asset in order[i : j + 1]:
            out[asset] = (2 * rank - (n + 1)) / (n - 1)
        i = j + 1
    return out


def rank_tilt(
    weights: dict[str, float],
    directions: dict[str, float | None],
    scores: dict[str, float | None],
    *,
    strength: float,
    floor: int,
) -> tuple[dict[str, float], int, int]:
    """The basket — every asset with a weight above 0 and a score — ranked; at `floor` assets or more and 2 longs or more,
    each long's weight times `1 + strength * z`, rescaled to the longs' untilted sum, every other weight as it is;
    otherwise the weights themselves. Returns the weights, the basket's size and the count of longs tilted."""
    basket = [a for a, w in weights.items() if w > 0 and scores[a] is not None]
    if len(basket) < floor:
        return weights, len(basket), 0
    longs = [a for a in basket if directions[a] is not None and directions[a] > 0]
    if len(longs) < 2:
        return weights, len(basket), 0
    z = centred_ranks({a: scores[a] for a in basket})
    raw = {a: weights[a] * (1 + strength * z[a]) for a in longs}
    scale = math.fsum(weights[a] for a in longs) / math.fsum(raw.values())
    return weights | {a: w * scale for a, w in raw.items()}, len(basket), len(longs)


def b3_book_returns(
    prices_by_asset: dict[str, list[float | None]], *, config: A2Config, score_lookback: int, strength: float, floor: int
) -> dict:
    """`a2_book_returns` with each close's inverse-vol weights passed through `rank_tilt` before the base returns, the vol
    target and the positions read them; `ranked` holds each close's basket size and `tilted` its count of longs tilted."""
    if not isinstance(config, A2Config):
        raise AlphaError(f"config must be an A2Config, got {type(config)!r}")
    _validate_prices_by_asset(prices_by_asset)
    _check_window("score_lookback", score_lookback)
    _check_window("floor", floor)
    if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not 0 <= strength < 1:
        raise AlphaError(f"strength must be a number in [0, 1), got {strength!r}")
    length = len(prices_by_asset["BTC"])

    union_ts = list(range(length))
    asset_ts: dict[str, list] = {
        asset: [k for k, p in enumerate(prices) if p is not None] for asset, prices in prices_by_asset.items()
    }

    directions = _asset_directions_a2(prices_by_asset, union_ts, asset_ts, config=config)
    returns = {asset: _asset_returns(prices) for asset, prices in prices_by_asset.items()}
    scores = {asset: momentum_scores(prices, lookback=score_lookback) for asset, prices in prices_by_asset.items()}
    weights: list[dict[str, float]] = []
    ranked: list[int] = []
    tilted_longs: list[int] = []
    for k, untilted in enumerate(_inverse_vol_weights(prices_by_asset, lookback=config.basket_lookback)):
        tilted, basket, longs = rank_tilt(
            untilted,
            {asset: directions[asset][k] for asset in prices_by_asset},
            {asset: scores[asset][k] for asset in prices_by_asset},
            strength=strength,
            floor=floor,
        )
        weights.append(tilted)
        ranked.append(basket)
        tilted_longs.append(longs)

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
    asset_positions: dict[str, list[float]] = {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * positions[k] for k in range(length - 1)]
        for asset in prices_by_asset
    }
    backtest = run_backtest(book_base_returns, positions, fee_rate=0.0, periods_per_year=config.periods_per_year)
    return {
        "book_base_returns": book_base_returns,
        "vol_target_positions": positions,
        "asset_positions": asset_positions,
        "net_returns": backtest["net_returns"],
        "metrics": {k: v for k, v in backtest.items() if k != "net_returns"},
        "ranked": ranked,
        "tilted": tilted_longs,
    }
