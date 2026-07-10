"""Cross-frequency system builder — the adopted deployable P1 system (registry record 44) as one
composed pipeline: the verified path.

A faithful transcription of the iter-081 trial-44 driver (which reproduced trial 43's machinery
bit-identically before the weight change), per docs/specs/00040-crossfreq-builder-design.md. The
exact feed map is registered-trial truth, not an ordered ffill step: RAW union prices (Nones
preserved) feed the B-sleeve primitives (dynamic_inverse_vol_basket, _inverse_vol_weights) and the
record-33 build_combined_system elementwise QA comparator; BTC-only forward-filled prices feed
a1_book_returns (both the price dict and the BTC regime series) and a2_book_returns; the per-asset
return grid is _asset_returns over the BTC-ffilled set with None -> 0.0.

Construction: B sleeve = daily w*l3 (basket 30 -> 200d SMA gate on the basket's own equity ->
vol target 0.10/sqrt(365) lookback 30 on the raw basket, gate applied after -> inverse-vol
weights); A1 sleeve = A1-lf weekly v0.12 7-offset-mean positions; both expanded to the 4h calendar
via expand_daily_positions with close-time-shifted boundaries (daily_ts+1d, h4_ts+4h); A2 sleeve =
equal-weight per-asset mean of the three adopted arms; fixed 1/3 combination -> per-asset caps
20%/10% -> net-of-cost at 0.006/side -> daily-cadence governor on dense present-day ranks of
date(h4_ts[k+1]). All turnover loops start from a flat book (prev = 0.0; bar 0 charged full entry).

The newest-row contract (the row the engine trades): a synthetic next boundary + dummy close is
appended to EACH grid before construction, so every sleeve yields one extra position row — the
interval forming at the snapshot's last close, computed from real data through that close and
insensitive to the dummy value. final_targets and multipliers therefore have n_periods + 1 rows;
the net series cover completed bars only, and their figures are identical to a no-append build.

P&L convention disclosure: governed_net reproduces the registered trial's returns-overlay cost
convention — multiplier-transition turnover is deliberately unpriced (record 33's ratified
governor semantics). A live engine trading final_targets pays fee on |delta(mult x capped)|, which
exceeds the overlay's mult x fee x |delta capped| on governor engage/disengage days.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

# Deliberate cross-package import of a1's private helpers: the builder must run the SAME code path
# the QA-gated drivers and registry record 44 ran — a reimplementation could silently diverge.
from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.portfolio.builder import CombinedSystemConfig, build_combined_system
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.portfolio.errors import PortfolioError
from cli.risk import GovernorConfig, apply_position_caps

# Fixed record-44 constants — not knobs (a future adopted record revises the builder under its own
# trial discipline).
_PPY_DAILY = 365
_PPY_4H = 2190
_B_BASKET_LOOKBACK = 30
_B_GATE_WINDOW = 200
_B_TARGET_VOL_ANNUAL = 0.10
_B_VOL_LOOKBACK = 30
_B_MAX_LEVERAGE = 1.0
_A1_CADENCE = 7
_A2_LOOKBACK = 180  # vol_lookback = basket_lookback = 180 for every adopted arm


@dataclass(frozen=True)
class CrossfreqSystemConfig:
    """Record 44's frozen parameters as defaults; validated on use (PortfolioError on bad values)."""

    assets: tuple[str, ...] = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")
    spot_fee_per_side: float = 0.006
    long_cap: float = 0.20
    short_cap: float = 0.10
    a2_arms: tuple[tuple[tuple[int, int, int], float], ...] = (
        ((20, 50, 100), 0.12),
        ((60, 120, 240), 0.10),
        ((60, 120, 240), 0.12),
    )
    governor: GovernorConfig = GovernorConfig()


@dataclass(frozen=True)
class CrossfreqSystemResult:
    """final_targets, multipliers, sleeve_positions and day_index carry n_periods + 1 rows (completed
    bars + the forming interval); the net series cover completed bars only (n_periods rows)."""

    final_targets: dict[str, list[float]]
    governed_net: list[float]
    ungoverned_net: list[float]
    multipliers: list[float]
    sleeve_positions: dict[str, dict[str, list[float]]]
    cap_breach_bars: int
    governor_engaged_bars: int
    day_index: list[int]
    n_periods: int


def _validate_config(c: CrossfreqSystemConfig) -> None:
    if not isinstance(c.assets, tuple) or not c.assets or len(set(c.assets)) != len(c.assets):
        raise PortfolioError(f"assets must be a non-empty tuple of unique names, got {c.assets!r}")
    for a in c.assets:
        if not isinstance(a, str) or not a:
            raise PortfolioError(f"assets must be non-empty strings, got {a!r}")
    if "BTC" not in c.assets:
        raise PortfolioError("assets must include 'BTC' (the A-sleeve books and the ffill feed require it)")
    for name, value in (("spot_fee_per_side", c.spot_fee_per_side), ("long_cap", c.long_cap), ("short_cap", c.short_cap)):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise PortfolioError(f"{name} must be a finite number > 0, got {value!r}")
    if not isinstance(c.a2_arms, tuple) or not c.a2_arms:
        raise PortfolioError(f"a2_arms must be a non-empty tuple of (lookbacks, target_vol) pairs, got {c.a2_arms!r}")
    for arm in c.a2_arms:
        if not isinstance(arm, tuple) or len(arm) != 2:
            raise PortfolioError(f"each a2 arm must be a (lookbacks, target_vol) pair, got {arm!r}")
        lookbacks, target_vol = arm
        if (
            not isinstance(lookbacks, tuple)
            or not lookbacks
            or any(not isinstance(lb, int) or isinstance(lb, bool) or lb < 2 for lb in lookbacks)
        ):
            raise PortfolioError(f"a2 arm lookbacks must be a non-empty tuple of ints >= 2, got {lookbacks!r}")
        if not isinstance(target_vol, (int, float)) or not math.isfinite(target_vol) or target_vol <= 0:
            raise PortfolioError(f"a2 arm target_vol must be a finite number > 0, got {target_vol!r}")


def _validate_grid(name: str, prices: dict[str, list[float | None]], ts: list[datetime], assets: tuple[str, ...]) -> None:
    if not isinstance(prices, dict) or not prices:
        raise PortfolioError(f"{name}_prices must be a non-empty dict, got {prices!r}")
    if set(prices) != set(assets):
        raise PortfolioError(f"{name}_prices keys must equal config.assets, got {sorted(prices)!r} vs {sorted(assets)!r}")
    if not isinstance(ts, list) or len(ts) < 2:
        raise PortfolioError(f"{name}_ts must be a list of >= 2 bar-start stamps, got {ts!r}")
    for t in ts:
        if not isinstance(t, datetime):
            raise PortfolioError(f"{name}_ts stamps must be datetimes, got {t!r}")
    if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
        raise PortfolioError(f"{name}_ts must be strictly sorted ascending")
    for asset in assets:
        series = prices[asset]
        if not isinstance(series, list) or len(series) != len(ts):
            raise PortfolioError(f"{name}_prices[{asset!r}] must be a list of length {len(ts)} (one close per stamp)")


def _dummy_close(series: list[float | None]) -> float | None:
    """The synthetic forming-bar close appended to a grid. Any valid price works — forming-interval
    positions consume data strictly before that close (its value only marks the asset as still
    listed); the last real close is used because it is always a valid price. All-None stays None."""
    for value in reversed(series):
        if value is not None:
            return value
    return None


def _ffill_btc(prices: dict[str, list[float | None]]) -> dict[str, list[float | None]]:
    """BTC-only forward fill (the trial drivers' convention): BTC's genuine mid-history union gaps
    are bridged for the A-sleeve books; every other asset keeps its raw Nones."""
    btc = list(prices["BTC"])
    last = None
    for i, value in enumerate(btc):
        if value is None:
            btc[i] = last
        else:
            last = value
    out = dict(prices)
    out["BTC"] = btc
    return out


def _block_start(k: int, offset: int) -> int:
    """The trial-34 weekly-cadence rule: day k holds the position decided at its 7-day block start."""
    return 0 if k < offset else offset + _A1_CADENCE * ((k - offset) // _A1_CADENCE)


def build_crossfreq_system(
    daily_prices: dict[str, list[float | None]],
    daily_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    *,
    config: CrossfreqSystemConfig = CrossfreqSystemConfig(),
) -> CrossfreqSystemResult:
    """Build the record-44 cross-frequency system from union-calendar closes (bar-START stamps)."""
    c = config
    _validate_config(c)
    _validate_grid("daily", daily_prices, daily_ts, c.assets)
    _validate_grid("h4", h4_prices, h4_ts, c.assets)

    # Newest-row contract: append a synthetic next boundary + dummy close to EACH grid so every
    # sleeve computes one extra position row — the interval forming at the snapshot's last close.
    d_ts = list(daily_ts) + [daily_ts[-1] + timedelta(days=1)]
    h_ts = list(h4_ts) + [h4_ts[-1] + timedelta(hours=4)]
    d_prices = {a: list(daily_prices[a]) + [_dummy_close(daily_prices[a])] for a in c.assets}
    h_prices = {a: list(h4_prices[a]) + [_dummy_close(h4_prices[a])] for a in c.assets}
    n_periods = len(h4_ts) - 1  # completed 4h bars
    n_rows_d = len(d_ts) - 1  # daily position rows incl. the forming one
    n_rows_h = len(h_ts) - 1  # 4h position rows incl. the forming one == n_periods + 1

    # Feed map: BTC-only-ffilled for the A-sleeve books; raw (Nones preserved) for the B primitives.
    d_pf = _ffill_btc(d_prices)
    h_pf = _ffill_btc(h_prices)
    ret_h = {a: [r if r is not None else 0.0 for r in _asset_returns(h_pf[a])] for a in c.assets}

    # ---- B sleeve: record 33's benchmark construction (basket -> gate -> vol target -> weights) ----
    basket = dynamic_inverse_vol_basket(d_prices, lookback=_B_BASKET_LOOKBACK)
    equity = [1.0]
    for r in basket:
        equity.append(equity[-1] * (1 + r))
    gate = sma_gate(equity, window=_B_GATE_WINDOW)
    vt = vol_target(
        basket,
        target_vol=_B_TARGET_VOL_ANNUAL / math.sqrt(_PPY_DAILY),
        lookback=_B_VOL_LOOKBACK,
        max_leverage=_B_MAX_LEVERAGE,
    )
    l3 = [gate[k] * vt[k] for k in range(n_rows_d)]
    w_d = _inverse_vol_weights(d_prices, lookback=_B_BASKET_LOOKBACK)
    b_daily = {a: [w_d[k].get(a, 0.0) * l3[k] for k in range(n_rows_d)] for a in c.assets}

    # Internal QA comparator (the trial drivers' gate, dataset-independent): the B sleeve's daily
    # net-of-cost must equal record 33's benchmark elementwise on the same raw prices.
    bench_gross = [l3[k] * basket[k] for k in range(n_rows_d)]
    noc_b: list[float] = []
    prev = dict.fromkeys(c.assets, 0.0)
    for k in range(n_rows_d):
        turnover = 0.0
        for a in c.assets:
            p = b_daily[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        noc_b.append(bench_gross[k] - turnover * c.spot_fee_per_side)
    bench = build_combined_system(
        d_prices,
        config=CombinedSystemConfig(
            basket_lookback=_B_BASKET_LOOKBACK,
            gate_window=_B_GATE_WINDOW,
            target_vol_annual=_B_TARGET_VOL_ANNUAL,
            vol_lookback=_B_VOL_LOOKBACK,
            max_leverage=_B_MAX_LEVERAGE,
            periods_per_year=_PPY_DAILY,
            spot_fee_per_side=c.spot_fee_per_side,
        ),
    ).benchmark_net_of_cost
    drift = max(abs(noc_b[k] - bench[k]) for k in range(n_rows_d))
    if drift > 1e-12:
        raise PortfolioError(f"B-sleeve QA failed: daily net-of-cost drifts {drift!r} from record 33's benchmark (> 1e-12)")

    # ---- A1 sleeve: A1-lf weekly v0.12 — 7-offset-mean positions ----
    ap_a1 = a1_book_returns(
        d_pf, d_pf["BTC"], config=A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    )["asset_positions"]
    held = [{a: [ap_a1[a][_block_start(k, o)] for k in range(n_rows_d)] for a in c.assets} for o in range(_A1_CADENCE)]
    a1_daily = {a: [statistics.mean(held[o][a][k] for o in range(_A1_CADENCE)) for k in range(n_rows_d)] for a in c.assets}

    # ---- A2 sleeve: equal-weight per-asset mean of the adopted arms ----
    arm_positions = []
    for lookbacks, target_vol in c.a2_arms:
        arm_config = A2Config(
            lookbacks=lookbacks,
            short="off",
            target_vol=target_vol,
            vol_lookback=_A2_LOOKBACK,
            basket_lookback=_A2_LOOKBACK,
            periods_per_year=_PPY_4H,
        )
        arm_positions.append(a2_book_returns(h_pf, config=arm_config)["asset_positions"])
    a2_h = {a: [statistics.mean(ap[a][k] for ap in arm_positions) for k in range(n_rows_h)] for a in c.assets}

    # ---- expansion to the 4h calendar (close-time-shifted boundaries — the pinned contract) ----
    d_close = [t + timedelta(days=1) for t in d_ts]
    h_close = [t + timedelta(hours=4) for t in h_ts]
    b_h = expand_daily_positions(b_daily, d_close, h_close)
    a1_h = expand_daily_positions(a1_daily, d_close, h_close)

    # ---- fixed 1/3 combination -> caps -> net-of-cost (completed bars) -> governor ----
    third = 1 / 3
    combined = {a: [third * b_h[a][k] + third * a1_h[a][k] + third * a2_h[a][k] for k in range(n_rows_h)] for a in c.assets}
    capped = apply_position_caps(combined, long_cap=c.long_cap, short_cap=c.short_cap)
    cap_breach_bars = sum(1 for k in range(n_periods) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in c.assets))

    noc: list[float] = []
    prev = dict.fromkeys(c.assets, 0.0)
    for k in range(n_periods):
        gross, turnover = 0.0, 0.0
        for a in c.assets:
            p = capped[a][k]
            gross += p * ret_h[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        noc.append(gross - turnover * c.spot_fee_per_side)

    # Dense present-day ranks of date(h4_ts[k+1]) over the extended grid; the forming interval's
    # multiplier comes from appending a zero return for its day (value-insensitive by the
    # governor's day-t-from-t-1 contract), leaving every completed bar's multiplier unchanged.
    dates = [h_ts[k + 1].date() for k in range(n_rows_h)]
    seen: dict = {}
    day_index = [seen.setdefault(d, len(seen)) for d in dates]
    multipliers = daily_cadence_governor(noc + [0.0], day_index, config=c.governor)
    governed_net = [multipliers[k] * noc[k] for k in range(n_periods)]
    governor_engaged_bars = sum(1 for m in multipliers[:n_periods] if m < 1.0)
    final_targets = {a: [multipliers[k] * capped[a][k] for k in range(n_rows_h)] for a in c.assets}

    return CrossfreqSystemResult(
        final_targets=final_targets,
        governed_net=governed_net,
        ungoverned_net=noc,
        multipliers=multipliers,
        sleeve_positions={"B": b_h, "A1": a1_h, "A2": a2_h},
        cap_breach_bars=cap_breach_bars,
        governor_engaged_bars=governor_engaged_bars,
        day_index=day_index,
        n_periods=n_periods,
    )
