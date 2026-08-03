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
20%/10% -> the §10 whole-book limits (see apply_whole_book_limits) -> net-of-cost at 0.006/side ->
daily-cadence governor on dense present-day ranks of date(h4_ts[k+1]). All turnover loops start
from a flat book (prev = 0.0; bar 0 charged full entry).

The newest-row contract (the row the engine trades): a synthetic next boundary + dummy close is
appended to EACH grid before construction, so every sleeve yields one extra position row — the
interval forming at the snapshot's last close, computed from real data through that close and
insensitive to the dummy value. final_targets and multipliers therefore have n_periods + 1 rows;
the net series cover completed bars only, and their figures are identical to a no-append build.

P&L convention disclosure: governed_net reproduces the registered trial's returns-overlay cost
convention — multiplier-transition turnover is deliberately unpriced (record 33's ratified
governor semantics). A live engine trading final_targets pays fee on |delta(mult x limited)|, which
exceeds the overlay's mult x fee x |delta limited| on governor engage/disengage days.

Two callables, one truth: build_crossfreq_system (the verified path above) and
build_crossfreq_system_fast (the equivalence-gated fast path — same signature, same result type,
bit-identical layer values; see its docstring for how it stays equal).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

# The one correctly-rounded sqrt-of-fraction CPython's statistics.stdev itself finishes with: the
# fast path reproduces stdev's exact rational sum-of-squares with rolling big-integer sums, then
# MUST round through the same function to stay bit-identical to the verified path's stdev calls.
from statistics import _float_sqrt_of_frac

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

# Deliberate cross-package import of a1's private helpers: the builder must run the SAME code path
# the QA-gated drivers and registry record 44 ran — a reimplementation could silently diverge.
from cli.alpha import A1Config, A2Config, a1_book_returns, a2_book_returns
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.portfolio.builder import CombinedSystemConfig, build_combined_system
from cli.portfolio.crossfreq import daily_cadence_governor, expand_daily_positions
from cli.portfolio.errors import PortfolioError
from cli.risk import (
    GovernorConfig,
    apply_gross_leverage_cap,
    apply_margin_floor,
    apply_net_exposure_band,
    apply_position_caps,
)

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
    fee_per_side: float = 0.0040  # Kraken tier-1 MAKER, schedule effective 2026-07-09
    # DO NOT "correct" this to the T0014-measured spread (2.11 bps/side at EUR 1k). The default
    # deliberately keeps the pre-measurement headroom so registry record 44's figures reproduce:
    # 0.0040 + 0.0020 is bit-exactly the registered 0.006 basis. The measured spread is what the
    # go/no-go quote uses; re-pricing the builder default would invalidate every registered figure.
    spread_per_side: float = 0.0020
    long_cap: float = 0.20
    short_cap: float = 0.10
    a2_arms: tuple[tuple[tuple[int, int, int], float], ...] = (
        ((20, 50, 100), 0.12),
        ((60, 120, 240), 0.10),
        ((60, 120, 240), 0.12),
    )
    governor: GovernorConfig = GovernorConfig()

    @property
    def cost_per_side(self) -> float:
        """The one effective per-side cost every net-of-cost site charges — a fee-tier change and a
        spread re-calibration are separate events, but they are summed in exactly one place here so
        no call site can accumulate a 1-ulp difference of its own."""
        return self.fee_per_side + self.spread_per_side


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
    for name, value in (
        ("fee_per_side", c.fee_per_side),
        ("spread_per_side", c.spread_per_side),
        ("long_cap", c.long_cap),
        ("short_cap", c.short_cap),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
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
        if (
            isinstance(target_vol, bool)
            or not isinstance(target_vol, (int, float))
            or not math.isfinite(target_vol)
            or target_vol <= 0
        ):
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
    listed); the last close is reused because it is always a valid price. A None last close stays
    None (honest delisted-tail semantics: an asset absent at the snapshot's edge stays absent on
    the forming bar instead of being resurrected from an older price)."""
    return series[-1]


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


def apply_whole_book_limits(capped: dict[str, list[float]]) -> dict[str, list[float]]:
    """The §10 whole-book ceilings on the already per-asset-capped book, at their §10 defaults.

    Order: per-asset caps (the caller's) -> gross leverage -> net exposure band -> margin floor, and
    the whole stack sits INSIDE the governor. The governor is a pure returns overlay by design, so
    clamping after it would silently re-scale the multiplier's own effect; per-asset shaping runs
    first, then the whole-book ceilings apply to the shaped book. This adds no new config surface:
    every threshold is the corresponding limit's own default in cli/risk/limits.py, left unpassed.

    Public because every out-of-builder recomputation of the traded book (the engine's stage-identity
    replay, the soak's live-cost reconstruction) must run this identical stack — a copy of the three
    calls would drift, and the divergence only surfaces once a limit actually binds.

    Each limit is per-bar independent, so a single-bar book gives the same answer as the whole series
    indexed at that bar — what lets the engine replay one forming row on its own.

    Verdict-neutral on any book that breaches none of them: each limit copies its input and only
    touches the bars it scales, so an unbreached book comes back bit-identical.
    """
    return apply_margin_floor(apply_net_exposure_band(apply_gross_leverage_cap(capped)))


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
    cost = c.cost_per_side  # summed once; every net-of-cost site below charges this same float

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
        noc_b.append(bench_gross[k] - turnover * cost)
    bench = build_combined_system(
        d_prices,
        config=CombinedSystemConfig(
            basket_lookback=_B_BASKET_LOOKBACK,
            gate_window=_B_GATE_WINDOW,
            target_vol_annual=_B_TARGET_VOL_ANNUAL,
            vol_lookback=_B_VOL_LOOKBACK,
            max_leverage=_B_MAX_LEVERAGE,
            periods_per_year=_PPY_DAILY,
            # record 33's frozen benchmark construction takes the summed cost — its interface is
            # unchanged by this split.
            spot_fee_per_side=cost,
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

    # ---- fixed 1/3 combination -> caps -> §10 whole-book limits -> net-of-cost (completed bars) -> governor ----
    third = 1 / 3
    combined = {a: [third * b_h[a][k] + third * a1_h[a][k] + third * a2_h[a][k] for k in range(n_rows_h)] for a in c.assets}
    capped = apply_position_caps(combined, long_cap=c.long_cap, short_cap=c.short_cap)
    cap_breach_bars = sum(1 for k in range(n_periods) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in c.assets))
    limited = apply_whole_book_limits(capped)

    noc: list[float] = []
    prev = dict.fromkeys(c.assets, 0.0)
    for k in range(n_periods):
        gross, turnover = 0.0, 0.0
        for a in c.assets:
            p = limited[a][k]
            gross += p * ret_h[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        noc.append(gross - turnover * cost)

    # Dense present-day ranks of date(h4_ts[k+1]) over the extended grid; the forming interval's
    # multiplier comes from appending a zero return for its day (value-insensitive by the
    # governor's day-t-from-t-1 contract), leaving every completed bar's multiplier unchanged.
    dates = [h_ts[k + 1].date() for k in range(n_rows_h)]
    seen: dict = {}
    day_index = [seen.setdefault(d, len(seen)) for d in dates]
    multipliers = daily_cadence_governor(noc + [0.0], day_index, config=c.governor)
    governed_net = [multipliers[k] * noc[k] for k in range(n_periods)]
    governor_engaged_bars = sum(1 for m in multipliers[:n_periods] if m < 1.0)
    final_targets = {a: [multipliers[k] * limited[a][k] for k in range(n_rows_h)] for a in c.assets}

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


# --- the fast path ------------------------------------------------------------------------------
# Bit-identical reimplementations of the verified path's hot layers (statistics.stdev/mean are 78%
# of its profile). CPython's statistics.stdev/mean compute EXACT rational sums and round once, so
# the fast path keeps exactness — rolling big-integer sums of the window's floats scaled to a
# common power of two, finished by the same rounding step — instead of refactoring float
# arithmetic, which would drift. numpy is used only where elementwise IEEE-754 ops reproduce the
# scalar operation order exactly (rolling max/min, momentum, the Donchian channel expression, and
# accumulations kept in the verified path's asset order with +0.0 no-op fills for skipped assets).


def _exact_mean(values: list[float]) -> float:
    """statistics.mean for a list of floats, bit-identically: the exact integer sum of the values
    scaled to a common power of two, divided once (int/int true division is correctly rounded, the
    same rounding Fraction.__float__ applies)."""
    ratios = [v.as_integer_ratio() for v in values]
    shift = max(r[1].bit_length() - 1 for r in ratios)
    total = 0
    for num, den in ratios:
        total += num << (shift - (den.bit_length() - 1))
    return total / (len(values) << shift)


def _trailing_stdevs(values: list[float | None], lookback: int) -> list[float]:
    """out[t] = statistics.stdev(values[t-lookback:t]) — bit-identically — for every t whose trailing
    window is full and None-free; nan marks warm-up (t < lookback) and windows containing a None.
    Rolling exact integer sums (floats scaled to a common power of two) reproduce statistics._ss's
    exact sum of squared deviations; the gcd reduction yields the same lowest-terms fraction that
    statistics.stdev feeds to _float_sqrt_of_frac."""
    n = len(values)
    out = [math.nan] * n
    ratios = [None if v is None else v.as_integer_ratio() for v in values]
    exps = [r[1].bit_length() - 1 for r in ratios if r is not None]
    if not exps:
        return out
    shift = max(exps)
    q = [None if r is None else r[0] << (shift - (r[1].bit_length() - 1)) for r in ratios]
    q2 = [None if x is None else x * x for x in q]
    denom = lookback * (lookback - 1) << (2 * shift)
    sum_q = sum_q2 = 0
    nones = 0
    for t in range(n):
        if t >= lookback:
            if not nones:
                ssd = lookback * sum_q2 - sum_q * sum_q
                g = math.gcd(ssd, denom)
                out[t] = _float_sqrt_of_frac(ssd // g, denom // g)
            x = q[t - lookback]
            if x is None:
                nones -= 1
            else:
                sum_q -= x
                sum_q2 -= q2[t - lookback]
        x = q[t]
        if x is None:
            nones += 1
        else:
            sum_q += x
            sum_q2 += q2[t]
    return out


def _rolling_sma(prices: list[float], window: int) -> list[float]:
    """out[k] = statistics.mean(prices[k-window+1:k+1]) — bit-identically (exact integer window sum,
    one correctly-rounded int/int division) — aligned like sma_gate (length len(prices)-1, nan
    warm-up for k < window-1)."""
    n = len(prices)
    out = [math.nan] * (n - 1)
    ratios = [p.as_integer_ratio() for p in prices]
    shift = max(r[1].bit_length() - 1 for r in ratios)
    q = [r[0] << (shift - (r[1].bit_length() - 1)) for r in ratios]
    denom = window << shift
    sum_q = 0
    for k in range(n - 1):
        sum_q += q[k]
        if k >= window:
            sum_q -= q[k - window]
        if k >= window - 1:
            out[k] = sum_q / denom
    return out


def _donchian_held(own_prices: np.ndarray, window: int, band: float) -> np.ndarray:
    """Vectorized _donchian_signal (channel_position + the held-state carry), bit-identical: rolling
    max/min are exact, the channel expression reproduces the scalar operation order, and the hold
    is a forward-fill of the last breakout trigger."""
    m = own_prices.size
    cp = np.zeros(m - 1)
    if m - 1 >= window:
        sw = sliding_window_view(own_prices, window)
        hi = sw.max(axis=1)[: m - window]
        lo = sw.min(axis=1)[: m - window]
        pk = own_prices[window - 1 : m - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            cp[window - 1 :] = np.where(hi > lo, 2 * (pk - lo) / (hi - lo) - 1, 0.0)
    trig = np.where(cp >= band, 1.0, np.where(cp <= -band, -1.0, 0.0))
    idx = np.where(trig != 0.0, np.arange(m - 1), -1)
    np.maximum.accumulate(idx, out=idx)
    return np.where(idx >= 0, trig[np.maximum(idx, 0)], 0.0)


def _map_own_to_union(own_values: np.ndarray, present: np.ndarray) -> np.ndarray:
    """Vectorized _map_to_union_index for an own calendar that is a subset of an integer union
    calendar: union period k maps to the asset's own value iff both endpoints are present (adjacent
    union stamps are automatically adjacent in the compressed own calendar). nan marks None."""
    j0 = np.cumsum(present) - 1
    valid = present[:-1] & present[1:]
    out = np.full(present.size - 1, np.nan)
    kk = np.nonzero(valid)[0]
    out[kk] = own_values[j0[kk]]
    return out


def _inverse_vol_weight_arrays(
    rets_by_asset: dict[str, list[float | None]], lookback: int
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Vectorized _inverse_vol_weights over per-asset return series: (weights, returns-with-0.0,
    return-validity) arrays, bit-identical to the scalar path — exact trailing stdevs feed the same
    vol > 0 qualification, and the renormalization total accumulates in asset order (skipped assets
    contribute an exact +0.0 no-op, matching the scalar path's skip)."""
    n = len(next(iter(rets_by_asset.values())))
    ret_np: dict[str, np.ndarray] = {}
    ret_valid: dict[str, np.ndarray] = {}
    inv: dict[str, np.ndarray] = {}
    total = np.zeros(n)
    for a, rets in rets_by_asset.items():
        ret_np[a] = np.array([0.0 if r is None else r for r in rets])
        ret_valid[a] = np.array([r is not None for r in rets])
        vols = np.array(_trailing_stdevs(rets, lookback))
        qual = ret_valid[a] & (vols > 0)  # nan (warm-up / None in window) compares False
        inv[a] = np.where(qual, 1.0 / np.where(qual, vols, 1.0), 0.0)
        total += inv[a]
    total_safe = np.where(total > 0.0, total, 1.0)
    weights = {a: np.where(inv[a] > 0.0, inv[a] / total_safe, 0.0) for a in rets_by_asset}
    return weights, ret_np, ret_valid


def _vol_target_positions(rv: np.ndarray, target_vol: float, max_leverage: float) -> np.ndarray:
    """vol_target from exact trailing stdevs: min(target_vol/rv, max_leverage) where rv > 0, else
    0.0 (nan marks warm-up and compares False)."""
    live = rv > 0
    return np.where(live, np.minimum(target_vol / np.where(live, rv, 1.0), max_leverage), 0.0)


def _b_daily_positions_fast(prices_by_asset: dict[str, list[float | None]], assets: tuple[str, ...]) -> dict[str, list[float]]:
    """The B sleeve on the (extended) daily grid: dynamic_inverse_vol_basket -> equity -> sma_gate
    -> vol_target -> inverse-vol weights, each layer bit-identical to the verified construction.
    The verified path's internal QA comparator (a transcription check against record 33's
    build_combined_system, redundant here) is not re-run — the fast-vs-verified equivalence tests
    subsume it."""
    rets = {a: _asset_returns(prices_by_asset[a]) for a in assets}
    n = len(rets[assets[0]])
    weights, ret_np, _ = _inverse_vol_weight_arrays(rets, _B_BASKET_LOOKBACK)
    basket = np.zeros(n)
    for a in assets:
        basket += np.where(weights[a] > 0.0, weights[a] * ret_np[a], 0.0)
    basket_list = basket.tolist()
    equity = [1.0]
    for r in basket_list:
        equity.append(equity[-1] * (1 + r))
    sma = np.array(_rolling_sma(equity, _B_GATE_WINDOW))
    gate = np.where(np.array(equity[:n]) > sma, 1.0, 0.0)  # nan warm-up compares False -> 0.0
    rv = np.array(_trailing_stdevs(basket_list, _B_VOL_LOOKBACK))
    vt = _vol_target_positions(rv, _B_TARGET_VOL_ANNUAL / math.sqrt(_PPY_DAILY), _B_MAX_LEVERAGE)
    l3 = gate * vt
    return {a: (weights[a] * l3).tolist() for a in assets}


def _a1_asset_positions_fast(prices_by_asset: dict[str, list[float | None]], assets: tuple[str, ...]) -> dict[str, list[float]]:
    """a1_book_returns(...)["asset_positions"] for the fixed record-44 A1 configuration
    (equal_risk_basket base, ensemble regime, short off, target_vol 0.12, defaults 200-day gate /
    30 vol and basket lookbacks / (20, 60, 120) trend lookbacks / max leverage 1.0 / ppy 365),
    bit-identical: exact SMA gate on BTC, vectorized trend agreement, exact inverse-vol weights,
    asset-order book accumulation, exact vol targeting. The bear leg is skipped (short="off" never
    reads it); the book's run_backtest metrics are not recomputed (the builder never uses them)."""
    btc = prices_by_asset["BTC"]
    n = len(btc) - 1
    sma = np.array(_rolling_sma(btc, 200))
    gate = np.where(np.array(btc[:n]) > sma, 1.0, 0.0)  # BTC has full union coverage -> never None

    rets = {a: _asset_returns(prices_by_asset[a]) for a in assets}
    weights, ret_np, ret_valid = _inverse_vol_weight_arrays(rets, 30)
    book = np.zeros(n)
    directions: dict[str, np.ndarray] = {}
    for a in assets:
        own = np.array([p for p in prices_by_asset[a] if p is not None], dtype=np.float64)
        m = own.size
        sign_sum = np.zeros(m - 1)
        for lb in (20, 60, 120):
            mom = np.zeros(m - 1)
            if m - 1 > lb:
                mom[lb:] = own[lb : m - 1] / own[: m - 1 - lb] - 1
            sign_sum = sign_sum + np.sign(mom)
        present = np.array([p is not None for p in prices_by_asset[a]])
        ta = _map_own_to_union(sign_sum / 3.0, present)
        d = np.where(ret_valid[a], np.where((gate == 1.0) & (ta > 0), 1.0, 0.0), np.nan)
        directions[a] = d
        book += np.where(ret_valid[a], (weights[a] * d) * ret_np[a], 0.0)
    rv = np.array(_trailing_stdevs(book.tolist(), 30))
    pos = _vol_target_positions(rv, 0.12 / math.sqrt(_PPY_DAILY), 1.0)
    return {a: ((weights[a] * np.where(ret_valid[a], directions[a], 0.0)) * pos).tolist() for a in assets}


def _a2_arm_asset_positions_fast(
    prices_by_asset: dict[str, list[float | None]],
    assets: tuple[str, ...],
    arms: tuple[tuple[tuple[int, int, int], float], ...],
) -> list[dict[str, list[float]]]:
    """a2_book_returns(...)["asset_positions"] per arm, bit-identical and shared where the verified
    path repeats itself: the inverse-vol weights (lookback 180) are computed once for all arms, the
    Donchian held signals once per (asset, window), and the directions/book/realized-vol once per
    distinct lookbacks tuple (record 44's second and third arms differ only in target_vol)."""
    rets = {a: _asset_returns(prices_by_asset[a]) for a in assets}
    n = len(rets[assets[0]])
    weights, ret_np, ret_valid = _inverse_vol_weight_arrays(rets, _A2_LOOKBACK)
    present = {a: np.array([p is not None for p in prices_by_asset[a]]) for a in assets}
    own = {a: np.array([p for p in prices_by_asset[a] if p is not None], dtype=np.float64) for a in assets}
    windows = {w for lookbacks, _ in arms for w in lookbacks}
    signal = {(a, w): _map_own_to_union(_donchian_held(own[a], w, band=1.0), present[a]) for a in assets for w in windows}

    directions_by_lb: dict[tuple[int, ...], dict[str, np.ndarray]] = {}
    rv_by_lb: dict[tuple[int, ...], np.ndarray] = {}
    for lookbacks, _ in arms:
        if lookbacks in directions_by_lb:
            continue
        directions: dict[str, np.ndarray] = {}
        book = np.zeros(n)
        for a in assets:
            ens = signal[(a, lookbacks[0])]
            for w in lookbacks[1:]:
                ens = ens + signal[(a, w)]
            directions[a] = np.maximum(ens / float(len(lookbacks)), 0.0)  # short="off"; nan stays nan
            book += np.where(ret_valid[a], (weights[a] * directions[a]) * ret_np[a], 0.0)
        directions_by_lb[lookbacks] = directions
        rv_by_lb[lookbacks] = np.array(_trailing_stdevs(book.tolist(), _A2_LOOKBACK))

    arm_positions = []
    for lookbacks, target_vol in arms:
        pos = _vol_target_positions(rv_by_lb[lookbacks], target_vol / math.sqrt(_PPY_4H), 1.0)
        directions = directions_by_lb[lookbacks]
        arm_positions.append({a: ((weights[a] * np.where(ret_valid[a], directions[a], 0.0)) * pos).tolist() for a in assets})
    return arm_positions


def build_crossfreq_system_fast(
    daily_prices: dict[str, list[float | None]],
    daily_ts: list[datetime],
    h4_prices: dict[str, list[float | None]],
    h4_ts: list[datetime],
    *,
    config: CrossfreqSystemConfig = CrossfreqSystemConfig(),
) -> CrossfreqSystemResult:
    """The equivalence-gated fast path: same signature, same result type, same values as
    build_crossfreq_system — the tests pin elementwise <= 1e-12 over the full frozen history with
    identical integer diagnostics (the layers are in fact bit-identical by construction).

    Error-behavior asymmetry: outputs are gated, error paths are not — on degenerate inputs the
    verified path may raise where this path returns a result (e.g. the zero-variance book check
    inside its internal QA comparator, which this path skips per the replay policy). Inputs that
    pass validation and produce results produce EQUAL results on both paths.

    How it stays equal (spec 00040 §fast path): every discrete decision layer — SMA gates, basket
    qualification, inverse-vol weight fallbacks, cap clipping, Donchian breakout comparisons,
    governor rungs — is fed values computed bit-identically to the verified path. The heavy
    statistics.stdev/mean calls (78% of the verified profile) are replaced by the same exact
    rational arithmetic those functions perform internally, done incrementally (rolling big-integer
    window sums) and finished by the same rounding step; per-asset rolling primitives are
    vectorized only where elementwise IEEE-754 ops reproduce the scalar operation order; every
    accumulation feeding a threshold keeps the verified path's summation order. Repeated work is
    shared across the A2 arms, and the B sleeve's internal QA comparator (redundant given the
    equivalence gate) is not re-run. Everything downstream of the sleeves (combination, caps,
    whole-book limits, costing, governor, targets) is the verified code verbatim.

    Measured on the full frozen history (2026-07-10): verified 111.5 s, fast 1.9 s (~58x).
    Production replay policy (spec 00040): engine cycles run this path; at least one cycle per day
    replays through the verified path, which remains the oracle.
    """
    c = config
    _validate_config(c)
    _validate_grid("daily", daily_prices, daily_ts, c.assets)
    _validate_grid("h4", h4_prices, h4_ts, c.assets)
    cost = c.cost_per_side  # summed once; every net-of-cost site below charges this same float

    d_ts = list(daily_ts) + [daily_ts[-1] + timedelta(days=1)]
    h_ts = list(h4_ts) + [h4_ts[-1] + timedelta(hours=4)]
    d_prices = {a: list(daily_prices[a]) + [_dummy_close(daily_prices[a])] for a in c.assets}
    h_prices = {a: list(h4_prices[a]) + [_dummy_close(h4_prices[a])] for a in c.assets}
    n_periods = len(h4_ts) - 1
    n_rows_d = len(d_ts) - 1
    n_rows_h = len(h_ts) - 1

    d_pf = _ffill_btc(d_prices)
    h_pf = _ffill_btc(h_prices)
    ret_h = {a: [r if r is not None else 0.0 for r in _asset_returns(h_pf[a])] for a in c.assets}

    # ---- the three sleeves, fast (bit-identical layer values) ----
    b_daily = _b_daily_positions_fast(d_prices, c.assets)
    ap_a1 = _a1_asset_positions_fast(d_pf, c.assets)
    held = [{a: [ap_a1[a][_block_start(k, o)] for k in range(n_rows_d)] for a in c.assets} for o in range(_A1_CADENCE)]
    a1_daily = {a: [_exact_mean([held[o][a][k] for o in range(_A1_CADENCE)]) for k in range(n_rows_d)] for a in c.assets}
    arm_positions = _a2_arm_asset_positions_fast(h_pf, c.assets, c.a2_arms)
    a2_h = {a: [_exact_mean([ap[a][k] for ap in arm_positions]) for k in range(n_rows_h)] for a in c.assets}

    # ---- everything downstream of the sleeves: the verified path's code verbatim ----
    d_close = [t + timedelta(days=1) for t in d_ts]
    h_close = [t + timedelta(hours=4) for t in h_ts]
    b_h = expand_daily_positions(b_daily, d_close, h_close)
    a1_h = expand_daily_positions(a1_daily, d_close, h_close)

    third = 1 / 3
    combined = {a: [third * b_h[a][k] + third * a1_h[a][k] + third * a2_h[a][k] for k in range(n_rows_h)] for a in c.assets}
    capped = apply_position_caps(combined, long_cap=c.long_cap, short_cap=c.short_cap)
    cap_breach_bars = sum(1 for k in range(n_periods) if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in c.assets))
    limited = apply_whole_book_limits(capped)

    noc: list[float] = []
    prev = dict.fromkeys(c.assets, 0.0)
    for k in range(n_periods):
        gross, turnover = 0.0, 0.0
        for a in c.assets:
            p = limited[a][k]
            gross += p * ret_h[a][k]
            turnover += abs(p - prev[a])
            prev[a] = p
        noc.append(gross - turnover * cost)

    dates = [h_ts[k + 1].date() for k in range(n_rows_h)]
    seen: dict = {}
    day_index = [seen.setdefault(d, len(seen)) for d in dates]
    multipliers = daily_cadence_governor(noc + [0.0], day_index, config=c.governor)
    governed_net = [multipliers[k] * noc[k] for k in range(n_periods)]
    governor_engaged_bars = sum(1 for m in multipliers[:n_periods] if m < 1.0)
    final_targets = {a: [multipliers[k] * limited[a][k] for k in range(n_rows_h)] for a in c.assets}

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
