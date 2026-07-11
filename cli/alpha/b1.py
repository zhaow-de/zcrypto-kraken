from __future__ import annotations

import math
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from cli.alpha.errors import AlphaError
from cli.logging import get_logger

logger = get_logger("alpha.b1")

_BOUNDARY = timedelta(hours=4)
_BAR_15M = timedelta(seconds=900)


@dataclass(frozen=True, kw_only=True)
class B1Config:
    """B1 conditioning-overlay configuration (docs/specs/00045): the vol-state scaler's fixed,
    pre-registered constants plus the gate's minimum-observation rule. None of these are tuned --
    they are pinned by the spec (F2/F4/F7) and validated at construction."""

    vol_lookback_bars: int = 96  # 15m bars = 24h
    vol_median_lookback: int = 180  # 4h boundaries = 30d
    vol_state_threshold: float = 1.5
    vol_scale_high: float = 0.5
    min_cell_obs: int = 100
    min_vol_bars: int = 48

    def __post_init__(self) -> None:
        for name in ("vol_lookback_bars", "vol_median_lookback", "min_cell_obs", "min_vol_bars"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise AlphaError(f"{name} must be an int >= 1, got {value!r}")
        for name in ("vol_state_threshold", "vol_scale_high"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise AlphaError(f"{name} must be a finite number > 0, got {value!r}")


def _validate_union_ts(union_ts: list[datetime]) -> None:
    if not isinstance(union_ts, list) or len(union_ts) < 2:
        raise AlphaError(
            f"union_ts must be a list of >= 2 stamps, got {len(union_ts) if isinstance(union_ts, list) else union_ts!r}"
        )
    for i in range(1, len(union_ts)):
        if union_ts[i] <= union_ts[i - 1]:
            raise AlphaError(f"union_ts must be strictly increasing, violated at index {i}")


def seasonality_gates(arm_noc_returns: list[float], union_ts: list[datetime], *, config: B1Config) -> list[int]:
    """Walk-forward seasonality gate per return index k (docs/specs/00045 sec"The overlay" 1-2):
    1 = favorable (update stamp), 0 = hold. Lists are indexed on the return index; position k
    applies to the move close[k] -> close[k+1], executed at the decision boundary union_ts[k] + 4h.

    - Slot key (F3): cell = (hour, weekday) of the DECISION BOUNDARY union_ts[k] + 4h, never of the
      bar-start stamp -- 6 hours x 7 days = 42 purely calendar cells.
    - Completion-time rule (F7): the gate table for calendar year Y is trained on exactly the
      returns whose interval closes at or before Y-01-01T00:00Z, where a return's interval close is
      its decision boundary union_ts[j] + 4h (so the Dec-31 20:00 stamp, closing Jan-1 00:00, IS in
      year Y+1's training set; the first stamp of Y+1, closing Jan-1 04:00, is NOT).
    - Fold assignment: return k is gated by the table of year(union_ts[k]) (the bar-start stamp's
      year). The New-Year boundary-crossing stamp (ts Dec-31 20:00, boundary Jan-1 00:00) is thus
      gated by the OLD year's table -- its own return sits exactly on the new year's training cut,
      so gating it with the new table would be a one-stamp self-leak.
    - Estimation rule (fixed): a cell is favorable iff the summed train net-of-cost return is > 0
      AND the cell has >= min_cell_obs train observations; thin cells default OPEN (1).
    """
    if not isinstance(config, B1Config):
        raise AlphaError(f"config must be a B1Config, got {type(config)!r}")
    _validate_union_ts(union_ts)
    if not isinstance(arm_noc_returns, list) or len(arm_noc_returns) != len(union_ts) - 1:
        raise AlphaError(
            f"arm_noc_returns must be a list of len(union_ts) - 1 = {len(union_ts) - 1} returns, "
            f"got {len(arm_noc_returns) if isinstance(arm_noc_returns, list) else arm_noc_returns!r}"
        )
    for r in arm_noc_returns:
        if not isinstance(r, (int, float)) or isinstance(r, bool) or not math.isfinite(r):
            raise AlphaError(f"arm_noc_returns must be finite numbers, got {r!r}")

    boundaries = [ts + _BOUNDARY for ts in union_ts[:-1]]
    cells = [(b.hour, b.weekday()) for b in boundaries]
    tzinfo = union_ts[0].tzinfo

    sums: dict[tuple[int, int], float] = {}
    counts: dict[tuple[int, int], int] = {}
    tables: dict[int, dict[tuple[int, int], int]] = {}
    trained_upto = 0
    for year in sorted({ts.year for ts in union_ts[:-1]}):
        cutoff = datetime(year, 1, 1, tzinfo=tzinfo)
        while trained_upto < len(boundaries) and boundaries[trained_upto] <= cutoff:
            cell = cells[trained_upto]
            sums[cell] = sums.get(cell, 0.0) + arm_noc_returns[trained_upto]
            counts[cell] = counts.get(cell, 0) + 1
            trained_upto += 1
        tables[year] = {cell: (1 if counts[cell] < config.min_cell_obs or sums[cell] > 0 else 0) for cell in counts}

    # A cell unseen in a year's training has 0 observations -> thin -> open.
    gates = [tables[union_ts[k].year].get(cells[k], 1) for k in range(len(boundaries))]
    logger.debug("seasonality gates: %d fold years, %d/%d stamps held", len(tables), gates.count(0), len(gates))
    return gates


def _validate_m15(m15_closes_by_asset: dict[str, tuple[list[datetime], list[float]]]) -> None:
    if not isinstance(m15_closes_by_asset, dict) or not m15_closes_by_asset:
        raise AlphaError("m15_closes_by_asset must be a non-empty dict of asset -> (ts_list, close_list)")
    for asset, pair in m15_closes_by_asset.items():
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise AlphaError(f"asset {asset!r} must map to a (ts_list, close_list) tuple, got {type(pair)!r}")
        ts_list, closes = pair
        if not isinstance(ts_list, list) or not isinstance(closes, list) or not ts_list or len(ts_list) != len(closes):
            raise AlphaError(f"asset {asset!r} must have non-empty, equal-length ts/close lists")
        for i in range(1, len(ts_list)):
            if ts_list[i] <= ts_list[i - 1]:
                raise AlphaError(f"asset {asset!r} 15m stamps must be strictly increasing, violated at index {i}")
        for c in closes:
            if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) or c <= 0:
                raise AlphaError(f"asset {asset!r} closes must be finite numbers > 0, got {c!r}")


def vol_state_scale(
    m15_closes_by_asset: dict[str, tuple[list[datetime], list[float]]],
    union_ts: list[datetime],
    *,
    config: B1Config,
) -> list[float]:
    """Composition-invariant vol-state scaler per return index k (docs/specs/00045 sec"The overlay"
    4-5): vol_scale_high (0.5) when the boundary's vol state exceeds vol_state_threshold (1.5),
    else 1.0. Active from the start of the series (unfitted -- only the gates have burn-in, F2).

    At each decision boundary T = union_ts[k] + 4h, per asset: realized vol = sample stdev of the
    log returns between consecutive qualifying closes in the trailing vol_lookback_bars 15m window
    (bar-START stamps; a bar qualifies iff ts + 900s <= T, fully closed at decision time -- F7),
    divided by the rolling median of the asset's OWN measure over its prior vol_median_lookback
    boundaries (own-normalization makes listings step-free -- F4). The boundary state is the mean
    of the per-asset states over assets with data. Edge cases (F7): an asset with fewer than
    vol_median_lookback own defined PRIOR boundary measures contributes a neutral state (1.0); an
    asset with fewer than min_vol_bars bars in the window contributes nothing that boundary; no
    qualifying asset -> the boundary state is neutral. Runtime assertion (F8): the substrate's last
    close must reach the last decision boundary, else a refreshed substrate with a shorter cut
    would silently un-condition the tail.
    """
    if not isinstance(config, B1Config):
        raise AlphaError(f"config must be a B1Config, got {type(config)!r}")
    _validate_union_ts(union_ts)
    _validate_m15(m15_closes_by_asset)

    boundaries = [ts + _BOUNDARY for ts in union_ts[:-1]]
    last_close = max(ts_list[-1] + _BAR_15M for ts_list, _ in m15_closes_by_asset.values())
    if last_close < boundaries[-1]:
        raise AlphaError(
            f"15m substrate ends at {last_close} but the last 4h decision boundary is {boundaries[-1]}; "
            "refresh the substrate before conditioning (F8)"
        )

    window = _BAR_15M * config.vol_lookback_bars
    histories: dict[str, list[float]] = {asset: [] for asset in m15_closes_by_asset}
    scales: list[float] = []
    for boundary in boundaries:
        states: list[float] = []
        for asset, (ts_list, closes) in m15_closes_by_asset.items():
            lo = bisect_left(ts_list, boundary - window)
            hi = bisect_right(ts_list, boundary - _BAR_15M)
            # < 3 bars leave < 2 returns (stdev undefined); only reachable with min_vol_bars < 3.
            if hi - lo < config.min_vol_bars or hi - lo < 3:
                continue
            rv = statistics.stdev(math.log(closes[i] / closes[i - 1]) for i in range(lo + 1, hi))
            history = histories[asset]
            if len(history) >= config.vol_median_lookback:
                median = statistics.median(history[-config.vol_median_lookback :])
                states.append(rv / median if median > 0 else 1.0)
            else:
                states.append(1.0)
            history.append(rv)
        state = statistics.fmean(states) if states else 1.0
        scales.append(config.vol_scale_high if state > config.vol_state_threshold else 1.0)
    logger.debug("vol-state scaler: %d/%d boundaries down-scaled", sum(1 for s in scales if s != 1.0), len(scales))
    return scales


def condition_positions(asset_positions: dict[str, list[float]], gates: list[int], scales: list[float]) -> dict[str, list[float]]:
    """Hold-through conditioning (docs/specs/00045 sec"The overlay" 3): at a favorable stamp
    (gate 1) every asset's conditioned position is its ensemble target times the vol scale; at an
    unfavorable stamp (gate 0) it carries its PREVIOUS conditioned position verbatim -- no trade,
    no turnover, never a forced flat. Books start flat: the held value before any update is 0.0."""
    if not isinstance(asset_positions, dict) or not asset_positions:
        raise AlphaError("asset_positions must be a non-empty dict of asset -> positions")
    if len(scales) != len(gates):
        raise AlphaError(f"gates and scales must have equal lengths, got {len(gates)} and {len(scales)}")
    for asset, positions in asset_positions.items():
        if not isinstance(positions, list) or len(positions) != len(gates):
            raise AlphaError(f"asset {asset!r} positions must be a list of len(gates) = {len(gates)} values")

    conditioned: dict[str, list[float]] = {}
    for asset, positions in asset_positions.items():
        held = 0.0
        out: list[float] = []
        for k in range(len(gates)):
            if gates[k]:
                held = positions[k] * scales[k]
            out.append(held)
        conditioned[asset] = out
    return conditioned


def per_year_gated_counts(gates: list[int], union_ts: list[datetime]) -> dict[int, int]:
    """Engagement helper (docs/specs/00045 F2): held-stamp (gate 0) count per fold year -- keyed by
    year(union_ts[k]), the same fold assignment seasonality_gates applies. Every fold year present
    appears, zero counts included (an all-zero year is the dead-knob signal)."""
    if len(gates) != len(union_ts) - 1:
        raise AlphaError(f"gates must have len(union_ts) - 1 = {len(union_ts) - 1} entries, got {len(gates)}")
    counts: dict[int, int] = {}
    for k, gate in enumerate(gates):
        year = union_ts[k].year
        counts[year] = counts.get(year, 0) + (1 if gate == 0 else 0)
    return counts


def per_year_scaled_counts(scales: list[float], union_ts: list[datetime]) -> dict[int, int]:
    """Engagement helper (docs/specs/00045 F2): down-scaled (scale != 1.0) stamp count per fold
    year, keyed by year(union_ts[k]); zero counts included."""
    if len(scales) != len(union_ts) - 1:
        raise AlphaError(f"scales must have len(union_ts) - 1 = {len(union_ts) - 1} entries, got {len(scales)}")
    counts: dict[int, int] = {}
    for k, scale in enumerate(scales):
        year = union_ts[k].year
        counts[year] = counts.get(year, 0) + (1 if scale != 1.0 else 0)
    return counts


def book_turnover(asset_positions: dict[str, list[float]]) -> float:
    """Engagement helper: total book turnover = sum over stamps and assets of |position change|,
    each asset starting from flat (0.0) -- the same per-asset convention the inline 0.006/side
    costing charges, so arm-B-vs-arm-A reduction reads directly off two calls."""
    if not isinstance(asset_positions, dict) or not asset_positions:
        raise AlphaError("asset_positions must be a non-empty dict of asset -> positions")
    total = 0.0
    for positions in asset_positions.values():
        previous = 0.0
        for position in positions:
            total += abs(position - previous)
            previous = position
    return total
