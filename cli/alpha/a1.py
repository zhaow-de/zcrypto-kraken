from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from cli.alpha.errors import AlphaError
from cli.backtest import run_backtest
from cli.benchmark.strategies import sma_gate, vol_target
from cli.features import trend_agreement

_BASES = frozenset({"btc_only", "equal_risk_basket"})
_REGIMES = frozenset({"single_gate", "ensemble"})
_SHORTS = frozenset({"off", "confirmed_bear"})


def _check_enum(name: str, value: str, allowed: frozenset[str]) -> None:
    if value not in allowed:
        raise AlphaError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


def _check_positive_number(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise AlphaError(f"{name} must be a finite number > 0, got {value!r}")


def _check_window(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 2:
        raise AlphaError(f"{name} must be an int >= 2, got {value!r}")


@dataclass(frozen=True, kw_only=True)
class A1Config:
    """A1 book configuration (docs/specs/00031): the four toggles (base, regime, short, target_vol)
    plus the fixed knobs shared by every trial. Validated at construction; every field is immutable
    thereafter."""

    base: str
    regime: str
    short: str
    target_vol: float
    gate_window: int = 200
    vol_lookback: int = 30
    basket_lookback: int = 30
    trend_lookbacks: tuple[int, ...] = (20, 60, 120)
    short_exposure: float = 0.5
    short_band: float = 0.0
    max_leverage: float = 1.0
    periods_per_year: int = 365

    def __post_init__(self) -> None:
        _check_enum("base", self.base, _BASES)
        _check_enum("regime", self.regime, _REGIMES)
        _check_enum("short", self.short, _SHORTS)
        _check_positive_number("target_vol", self.target_vol)
        _check_window("gate_window", self.gate_window)
        _check_window("vol_lookback", self.vol_lookback)
        _check_window("basket_lookback", self.basket_lookback)
        if not isinstance(self.trend_lookbacks, tuple) or not self.trend_lookbacks:
            raise AlphaError(f"trend_lookbacks must be a non-empty tuple of ints, got {self.trend_lookbacks!r}")
        for lb in self.trend_lookbacks:
            _check_window("trend_lookbacks element", lb)
        if (
            not isinstance(self.short_exposure, (int, float))
            or isinstance(self.short_exposure, bool)
            or not math.isfinite(self.short_exposure)
            or not (0 < self.short_exposure <= 1)
        ):
            raise AlphaError(f"short_exposure must be a finite number in (0, 1], got {self.short_exposure!r}")
        if (
            not isinstance(self.short_band, (int, float))
            or isinstance(self.short_band, bool)
            or not math.isfinite(self.short_band)
            or not (0.0 <= self.short_band < 1.0)
        ):
            raise AlphaError(f"short_band must be a finite number in [0.0, 1.0), got {self.short_band!r}")
        _check_positive_number("max_leverage", self.max_leverage)
        if not isinstance(self.periods_per_year, int) or isinstance(self.periods_per_year, bool) or self.periods_per_year < 1:
            raise AlphaError(f"periods_per_year must be an int >= 1, got {self.periods_per_year!r}")


def _map_to_union_index(own_ts: list, own_values: list[float], union_ts: list) -> list[float | None]:
    """Map a feature/gate computed on an asset's own CONTIGUOUS (gap-compressed) calendar (`own_ts`,
    length N; `own_values[j]` = the causal value for the move own_ts[j] -> own_ts[j+1], length N-1)
    onto the union return index (`union_ts`, length M; union period k = the move union_ts[k] ->
    union_ts[k+1]). Union period k gets own_values[own_pos[union_ts[k]]] iff BOTH union_ts[k] and
    union_ts[k+1] are present in own_ts AND are adjacent there (own_pos[union_ts[k+1]] ==
    own_pos[union_ts[k]] + 1) -- the asset was present for both endpoints of that exact move with
    nothing dropped in between; else None. Introduces no look-ahead: own_values[j] itself only used
    data at <= own_ts[j] (inherited from the source feature/gate); this only remaps by timestamp.
    """
    own_pos = {ts: j for j, ts in enumerate(own_ts)}
    mapped: list[float | None] = []
    for k in range(len(union_ts) - 1):
        j0 = own_pos.get(union_ts[k])
        j1 = own_pos.get(union_ts[k + 1])
        if j0 is not None and j1 is not None and j1 == j0 + 1:
            mapped.append(own_values[j0])
        else:
            mapped.append(None)
    return mapped


def _btc_market_bear(btc_prices: list[float], *, window: int, band: float) -> list[float]:
    """Causal confirmed-bear "band" signal (docs/specs/00031, finding-2): the strict-below-SMA-by-band
    mirror of sma_gate's above-SMA long signal, same alignment/warm-up convention (cli/benchmark/
    strategies.py:sma_gate). Element k = 1.0 if btc_prices[k] < mean(btc_prices[k-window+1:k+1]) *
    (1.0 - band) else 0.0, using only btc_prices[<= k] (no look-ahead). Warm-up (k < window-1) is 0.0.
    Returns length len(btc_prices)-1, aligned with sma_gate/returns_from_prices. band == 0.0 reduces to
    the plain below-SMA test; band > 0.0 opens a flat neutral zone between SMA*(1-band) and SMA where
    neither this signal nor sma_gate's long signal fires. Private helper: trusts a validated btc_prices
    (mirrors a1_book_returns's own _validate_btc_prices boundary).
    """
    signal: list[float] = []
    for k in range(len(btc_prices) - 1):
        if k < window - 1:
            signal.append(0.0)
            continue
        sma = statistics.mean(btc_prices[k - window + 1 : k + 1])
        signal.append(1.0 if btc_prices[k] < sma * (1.0 - band) else 0.0)
    return signal


def _asset_directions(
    prices_by_asset: dict[str, list[float | None]],
    btc_prices: list[float],
    union_ts: list,
    asset_ts: dict[str, list],
    *,
    config: A1Config,
) -> dict[str, list[float | None]]:
    """Per-asset direction d_i[k] on the union return index (docs/specs/00031). Every value uses only
    prices/features at <= union index k -> no look-ahead. None where the asset itself has no valid
    return that period (either endpoint's price is None). Assumes btc_prices/asset_ts["BTC"] have
    full coverage of union_ts (no internal gaps) -- true for the real BTC series; a1_book_returns
    (Task 4) enforces this at its validation boundary."""
    g_btc_own = sma_gate(btc_prices, window=config.gate_window)
    g_btc = _map_to_union_index(asset_ts["BTC"], g_btc_own, union_ts)
    bear_own = _btc_market_bear(btc_prices, window=config.gate_window, band=config.short_band)
    market_bear = _map_to_union_index(asset_ts["BTC"], bear_own, union_ts)

    directions: dict[str, list[float | None]] = {}
    for asset, prices in prices_by_asset.items():
        own_prices = [p for p in prices if p is not None]
        ta_own = trend_agreement(own_prices, lookbacks=list(config.trend_lookbacks))
        ta = _map_to_union_index(asset_ts[asset], ta_own, union_ts)

        d: list[float | None] = []
        for k in range(len(union_ts) - 1):
            if prices[k] is None or prices[k + 1] is None:
                d.append(None)
                continue
            gate = g_btc[k] if g_btc[k] is not None else 0.0
            bear = market_bear[k] if market_bear[k] is not None else 0.0
            # ta[k] is guaranteed non-None here: prices[k] and prices[k+1] both present means
            # union_ts[k]/union_ts[k+1] are adjacent in this asset's own compressed calendar too.
            ta_k = ta[k]
            if config.regime == "single_gate":
                long_ok = gate == 1.0
            else:
                long_ok = gate == 1.0 and ta_k > 0
            if long_ok:
                d.append(1.0)
            elif config.short == "confirmed_bear" and bear == 1.0 and ta_k < 0:
                d.append(-config.short_exposure)
            else:
                d.append(0.0)
        directions[asset] = d
    return directions


def _asset_returns(prices: list[float | None]) -> list[float | None]:
    """Per-asset union-calendar returns: ret[t] = prices[t+1]/prices[t]-1 iff both present, else None."""
    return [
        (prices[t + 1] / prices[t] - 1) if prices[t] is not None and prices[t + 1] is not None else None
        for t in range(len(prices) - 1)
    ]


def _inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]:
    """Per-period renormalized inverse-vol qualifying weights over a union calendar (SAME qualifying
    rule as dynamic_inverse_vol_basket, kept in sync by test_inverse_vol_weights_reduces_to_basket):
    asset i qualifies at period t iff ret_i[t] is present, its trailing window ret_i[t-lookback:t]
    (strictly before t) is fully non-None, and that window has positive stdev; weight 1/stdev,
    renormalized over qualifiers. No qualifier -> {}. Returns weights (not a pre-combined return
    series) so a1_book_returns (Task 4) can apply per-asset directions before combining. Private
    helper: trusts a validated, equal-length, non-empty prices_by_asset (mirrors
    dynamic_inverse_vol_basket's own private _inverse_vol_weight)."""
    length = len(next(iter(prices_by_asset.values())))
    returns_by_asset = {asset: _asset_returns(prices) for asset, prices in prices_by_asset.items()}

    weights: list[dict[str, float]] = []
    for t in range(length - 1):
        inv_weights: dict[str, float] = {}
        if t >= lookback:
            for asset, rets in returns_by_asset.items():
                if rets[t] is None:
                    continue
                window = rets[t - lookback : t]
                if any(r is None for r in window):
                    continue
                vol = statistics.stdev(window)
                if vol > 0:
                    inv_weights[asset] = 1.0 / vol
        if not inv_weights:
            weights.append({})
            continue
        total = sum(inv_weights.values())
        weights.append({asset: inv / total for asset, inv in inv_weights.items()})
    return weights


def _validate_prices_by_asset(prices_by_asset: dict[str, list[float | None]]) -> None:
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise AlphaError("prices_by_asset must be a non-empty dict of price series")
    if "BTC" not in prices_by_asset:
        raise AlphaError("prices_by_asset must include 'BTC'")
    lengths: set[int] = set()
    for asset, prices in prices_by_asset.items():
        if not isinstance(prices, list):
            raise AlphaError(f"prices for {asset!r} must be a list, got {type(prices)!r}")
        for p in prices:
            if p is not None and (not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0):
                raise AlphaError(f"prices must be None or finite positive numbers, got {p!r}")
        lengths.add(len(prices))
    if len(lengths) != 1:
        raise AlphaError(f"all price series must have equal length, got {sorted(lengths)}")
    if any(p is None for p in prices_by_asset["BTC"]):
        raise AlphaError("BTC must have full coverage on the union calendar (no None gaps)")


def _validate_btc_prices(btc_prices: list[float], prices_by_asset: dict[str, list[float | None]]) -> None:
    """Validate the standalone btc_prices argument used to compute the regime gate (_asset_directions
    reads btc_prices, not prices_by_asset["BTC"]). Under the current no-gap contract the two must be
    the same series, so this checks btc_prices == prices_by_asset["BTC"] element-for-element -- a
    same-length-but-different btc_prices would otherwise silently compute the gate off different data
    than the BTC leg's own return/weight contribution. NOTE (iter-046): once BTC's real 1-day
    union-calendar gap is handled, this will relax to "agrees where BTC is present" instead of a strict
    full-length equality.
    """
    btc_column = prices_by_asset["BTC"]
    if not isinstance(btc_prices, list) or len(btc_prices) != len(btc_column):
        got = len(btc_prices) if isinstance(btc_prices, list) else btc_prices
        raise AlphaError(f"btc_prices must be a list of length {len(btc_column)} (the union length), got {got!r}")
    for p in btc_prices:
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
            raise AlphaError(f"btc_prices must be finite positive numbers, got {p!r}")
    if btc_prices != btc_column:
        raise AlphaError("btc_prices must equal prices_by_asset['BTC'] element-for-element (same series)")


def a1_book_returns(prices_by_asset: dict[str, list[float | None]], btc_prices: list[float], *, config: A1Config) -> dict:
    """Assemble the A1 book (docs/specs/00031): per-asset directions x inverse-vol/BTC-only weights x
    union-calendar returns -> book_base_returns, then vol_target -> run_backtest. Returns
    {book_base_returns, vol_target_positions, asset_positions, net_returns, metrics}."""
    if not isinstance(config, A1Config):
        raise AlphaError(f"config must be an A1Config, got {type(config)!r}")
    _validate_prices_by_asset(prices_by_asset)
    _validate_btc_prices(btc_prices, prices_by_asset)
    length = len(prices_by_asset["BTC"])

    working = {"BTC": prices_by_asset["BTC"]} if config.base == "btc_only" else prices_by_asset
    union_ts = list(range(length))
    asset_ts: dict[str, list] = {"BTC": union_ts}
    for asset, prices in working.items():
        if asset != "BTC":
            asset_ts[asset] = [k for k, p in enumerate(prices) if p is not None]

    directions = _asset_directions(working, btc_prices, union_ts, asset_ts, config=config)
    returns = {asset: _asset_returns(prices) for asset, prices in working.items()}

    if config.base == "btc_only":
        weights = [({"BTC": 1.0} if r is not None else {}) for r in returns["BTC"]]
    else:
        weights = _inverse_vol_weights(working, lookback=config.basket_lookback)

    book_base_returns: list[float] = []
    for k in range(length - 1):
        total = 0.0
        for asset in working:
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
        for asset in working
    }
    backtest = run_backtest(book_base_returns, positions, fee_rate=0.0, periods_per_year=config.periods_per_year)
    return {
        "book_base_returns": book_base_returns,
        "vol_target_positions": positions,
        "asset_positions": asset_positions,
        "net_returns": backtest["net_returns"],
        "metrics": {k: v for k, v in backtest.items() if k != "net_returns"},
    }
