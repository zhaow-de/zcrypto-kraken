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
    """The A1 book's four toggles (base, regime, short, target_vol) plus the knobs every trial shares (docs/specs/00031).

    `target_vol` is ANNUALIZED (0.10 = 10 %/yr) and `a1_book_returns` divides by sqrt(periods_per_year) itself, so a caller
    that pre-divides runs the book mis-scaled (`docs/research/13.phase5-decisions.md` [iter-066] records such a run)."""

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
    """Remap a per-move series from an asset's own gap-compressed calendar onto the union return index, adding no look-ahead.

    `own_values[j]` is the causal value for the move `own_ts[j] -> own_ts[j+1]`; union period k takes it iff `union_ts[k]` and
    `union_ts[k+1]` are adjacent in `own_ts` — the asset was present for both endpoints of that exact move — else None."""
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
    """Causal confirmed-bear mirror of `sma_gate` (docs/specs/00031, finding 2): 1.0 where the price is below its SMA by `band`,
    on `sma_gate`'s alignment and warm-up; a positive `band` opens a neutral zone between SMA*(1-band) and the SMA where neither
    this signal nor `sma_gate`'s long signal fires. Trusts an already-validated `btc_prices` (`_validate_btc_prices`)."""
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
    """Per-asset direction `d[asset][k]` on the union return index, causal, and None where the asset has no return that period.

    Assumes BTC covers `union_ts` with no gaps — `_validate_prices_by_asset` enforces that at `a1_book_returns`'s boundary."""
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
            # ta[k] is non-None here: both prices present means union_ts[k] and union_ts[k+1] are adjacent in asset_ts[asset].
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
    """Per-period renormalized inverse-vol weights over a union calendar, qualifying exactly as `dynamic_inverse_vol_basket`
    does (`test_inverse_vol_weights_reduces_to_basket` holds the two in sync); weights rather than a combined return series, so
    `a1_book_returns` can apply per-asset directions before combining. Trusts an already-validated, equal-length, non-empty
    `prices_by_asset`."""
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
    """Refuse a `btc_prices` that is not `prices_by_asset["BTC"]` element-for-element: `_asset_directions` reads `btc_prices`
    while the BTC leg's returns and weights come from that column, so a same-length-but-different series would silently compute
    the regime gate off other data than the book trades; the strictness is deliberate — `docs/research/10.phase4-decisions.md`
    [iter-046] chose forward-filling BTC's one missing union day over relaxing this check to "agrees where BTC is present"."""
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
