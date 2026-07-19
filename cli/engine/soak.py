"""Structural metrics computed from a sequence of per-bar portfolio weights: gross and net
exposure, the fraction of assets held active, per-bar turnover, portfolio concentration (HHI),
and whether either per-asset cap was breached. Also derives, from a per-bar governor multiplier
series, which trading days saw the governor engage at all.

Also builds the REALIZED forward-return observation from the engine's journal + price store: for
each cycle T, the position decided at T is held over [T, T+4h) and scored against that bar's
actual forward return, joined against the store BY TIMESTAMP -- see `realized_series` for the
exact timing model and its off-by-one cross-check (`chain_ok`).

Also builds the backtest NULL the realized series is judged against: `build_null` rebuilds the
same strategy over the full frozen canonical history and derives its P&L under the LIVE cost
convention (`_net_live_from_result`) -- the builder's `governed_net` charges cost on the capped
book's turnover, but a live engine trades `final_targets = mult x capped` and pays cost on THAT
turnover instead, so on a governor multiplier-transition bar the two differ by exactly the
governor's turnover bias. Recasting the null onto the live convention makes that bias cancel in
the realized-vs-null comparison instead of masquerading as an unrelated mismatch. `windowed_null`
and `block_bootstrap_null` turn a null series into reference distributions of a chosen window
length: the former enumerates every overlapping window, the latter draws a stationary
(Politis-Romano) block bootstrap of resampled paths of that length.

Also judges a live metric value against its null distribution: `metric_verdict` applies a
two-sided band (inner band consistent, edge zones weakly-consistent, outside the outer band
inconsistent on EITHER side -- too-low is a bug tell too, not just too-high) with an "n/a" escape
for a degenerate discriminator (zero-width band or a tiny `effective_n`); `degenerate` flags a
near-zero-exposure window that can't be judged at all; `summarize_panel` rolls a panel of verdicts
into a multiplicity-aware summary line, since judging N metrics at a 90% band will show ~N*0.10
outside it by chance alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from cli.engine.cycle import _union_align
from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, SnapshotEntry
from cli.engine.store import GRID_INTERVALS, PAIR_KEYS, read_store_series
from cli.portfolio import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.risk.limits import apply_position_caps


def structural_metrics(
    weights_by_bar: list[dict[str, float]],
    *,
    long_cap: float = 0.20,
    short_cap: float = 0.10,
) -> dict[str, list[float]]:
    """Compute per-bar structural metrics from a series of asset->weight dicts.

    Each bar dict maps the same set of assets to their portfolio weight for that bar. Returns a
    dict of equal-length per-bar series keyed "gross", "net", "active_frac", "turnover", "hhi",
    "cap_breach". An empty input returns each key mapped to an empty list.
    """
    gross: list[float] = []
    net: list[float] = []
    active_frac: list[float] = []
    turnover: list[float] = []
    hhi: list[float] = []
    cap_breach: list[float] = []

    prev_weights: dict[str, float] = {}
    for weights in weights_by_bar:
        bar_gross = sum(abs(w) for w in weights.values())
        bar_net = sum(weights.values())
        n_assets = len(weights)
        n_active = sum(1 for w in weights.values() if abs(w) > 1e-9)
        bar_turnover = sum(abs(w - prev_weights.get(asset, 0.0)) for asset, w in weights.items())
        bar_hhi = sum((abs(w) / bar_gross) ** 2 for w in weights.values()) if bar_gross > 1e-12 else 0.0
        bar_cap_breach = 1.0 if any(w > long_cap + 1e-12 or w < -short_cap - 1e-12 for w in weights.values()) else 0.0

        # Round only the reported gross figure: summing abs(weight) is order-independent in
        # value but not always representable exactly (e.g. 0.10 + 0.05 + 0.0 correctly rounds to
        # one ULP above the literal 0.15) -- clear that float noise for the reported series while
        # keeping the unrounded bar_gross for hhi's own division above.
        gross.append(round(bar_gross, 12))
        net.append(bar_net)
        active_frac.append(n_active / n_assets)
        turnover.append(bar_turnover)
        hhi.append(bar_hhi)
        cap_breach.append(bar_cap_breach)

        prev_weights = weights

    return {
        "gross": gross,
        "net": net,
        "active_frac": active_frac,
        "turnover": turnover,
        "hhi": hhi,
        "cap_breach": cap_breach,
    }


def governor_engaged_daily(mult: list[float], day_index: list[int]) -> list[float]:
    """Roll a per-bar governor multiplier series up to a per-day engagement flag.

    day_index gives each bar's 0-based, non-decreasing day id. For each distinct day, returns
    1.0 if any bar of that day has mult < 1.0, else 0.0. Output length is the number of
    distinct days.
    """
    engaged_by_day: dict[int, bool] = {}
    for m, day in zip(mult, day_index):
        engaged = engaged_by_day.get(day, False) or m < 1.0
        engaged_by_day[day] = engaged

    return [1.0 if engaged else 0.0 for engaged in engaged_by_day.values()]


class SoakError(EngineError):
    """Raised when soak-check inputs are structurally inconsistent: a mismatched final_targets
    asset set across the clean segment, or a journaled 240 (4h) snapshot's last_ts disagreeing
    with the cycle-boundary math."""


@dataclass(frozen=True)
class RealizedSeries:
    """The realized forward-return observation built from a clean run of journal cycles: each
    scored cycle's decided weights and the forward 4h return those weights actually earned,
    joined against the price store by timestamp (never by list index -- see `realized_series`)."""

    cycle_ts: list[datetime]
    weights: list[dict[str, float]]
    gross: list[float]
    turnover: list[float]
    net: list[float]
    dropped_tail: int
    assets: tuple[str, ...]
    chain_ok: bool
    implausible: bool


def select_clean_segment(records: list[CycleRecord]) -> list[CycleRecord]:
    """Sort `records` by cycle_ts and return the longest run of consecutive records whose
    cycle_ts differ by exactly 4h and each fall on a 4h grid boundary (hour in {0,4,8,12,16,20},
    minute=second=0). Ties keep the FIRST longest run; empty input returns []. Success/failure
    filtering is the caller's job -- this only handles boundary contiguity."""
    if not records:
        return []
    ordered = sorted(records, key=lambda r: r.cycle_ts)

    def _on_boundary(ts: datetime) -> bool:
        return ts.hour in {0, 4, 8, 12, 16, 20} and ts.minute == 0 and ts.second == 0

    best_start = best_len = 0
    run_start = run_len = 0
    for i, rec in enumerate(ordered):
        ts = rec.cycle_ts
        continues = run_len > 0 and ts - ordered[i - 1].cycle_ts == timedelta(hours=4)
        if _on_boundary(ts) and (run_len == 0 or continues):
            if run_len == 0:
                run_start = i
            run_len += 1
        else:
            run_start = i
            run_len = 1 if _on_boundary(ts) else 0
        if run_len > best_len:
            best_start, best_len = run_start, run_len

    return ordered[best_start : best_start + best_len]


def _snapshot_240(record: CycleRecord) -> SnapshotEntry:
    for entry in record.snapshots:
        if entry.grid == "240":
            return entry
    raise SoakError(f"cycle {record.cycle_ts!r} has no grid=='240' snapshot")


def _chain_consistent(scored_ts: list[datetime], closes_by_asset: dict[str, dict[datetime, float]]) -> bool:
    """True iff for every pair of consecutive SCORED cycle timestamps (T_i, T_next), each asset's
    end price for T_i and start price for T_next are the SAME store entry: closes[a][T_i] ==
    closes[a][T_next - 4h]. When scored cycles are 4h-contiguous these resolve to the identical
    dict key and the check trivially holds; a gap in the scored sequence (a cycle skipped by the
    realizability gate) makes T_i and T_next - 4h different keys, and this returns False."""
    for i in range(len(scored_ts) - 1):
        t_i = scored_ts[i]
        start_of_next = scored_ts[i + 1] - timedelta(hours=4)
        for closes in closes_by_asset.values():
            if closes[t_i] != closes[start_of_next]:
                return False
    return True


def realized_series(
    records: list[CycleRecord],
    store_dir: Path,
    *,
    fee: float = 0.006,
    now: datetime,
) -> RealizedSeries:
    """Compute the realized forward-4h-return series from a run of journal cycles.

    Timing model: cycle T decides q_a(T) = final_targets[a], held over [T, T+4h) and scored
    against the store's closes[T-4h] (entry price) and closes[T] (exit price), looked up BY
    TIMESTAMP against a `{ts: close}` map built once per asset from `read_store_series`. The last
    clean-segment cycle never scores (no successor); a cycle whose successor postdates `now`, or
    whose asset closes aren't all present/finite at both boundary stamps, is also skipped and
    counted in `dropped_tail`. `chain_ok` cross-checks the forward join wasn't shifted by a bar --
    see `_chain_consistent`.
    """
    clean = select_clean_segment(records)
    if not clean:
        raise SoakError("no contiguous clean cycle segment in the journal")
    assets = tuple(sorted(clean[0].final_targets))
    for rec in clean:
        if tuple(sorted(rec.final_targets)) != assets:
            raise SoakError(f"cycle {rec.cycle_ts!r} final_targets asset set {sorted(rec.final_targets)} != {list(assets)}")

    closes: dict[str, dict[datetime, float]] = {a: dict(zip(*read_store_series(store_dir, a, 240))) for a in assets}

    cycle_ts: list[datetime] = []
    weights: list[dict[str, float]] = []
    gross: list[float] = []
    turnover: list[float] = []
    net: list[float] = []
    implausible = False
    prev_weights: dict[str, float] = dict.fromkeys(assets, 0.0)

    for i in range(len(clean) - 1):
        rec, nxt = clean[i], clean[i + 1]
        t = rec.cycle_ts
        h4 = _snapshot_240(rec)
        h4_next = _snapshot_240(nxt)
        if h4.last_ts != t - timedelta(hours=4):
            raise SoakError(f"cycle {t!r}: 240 snapshot last_ts {h4.last_ts!r} != cycle_ts - 4h")
        if h4_next.last_ts != t:
            raise SoakError(f"cycle {nxt.cycle_ts!r}: 240 snapshot last_ts {h4_next.last_ts!r} != {t!r}")

        if nxt.cycle_ts > now:
            continue
        start_ts, end_ts = t - timedelta(hours=4), t
        if not all(
            start_ts in closes[a]
            and end_ts in closes[a]
            and closes[a][start_ts] is not None
            and math.isfinite(closes[a][start_ts])
            and closes[a][end_ts] is not None
            and math.isfinite(closes[a][end_ts])
            for a in assets
        ):
            continue

        r_fwd = {a: closes[a][end_ts] / closes[a][start_ts] - 1.0 for a in assets}
        if any(abs(v) > 0.5 for v in r_fwd.values()):
            implausible = True

        q = rec.final_targets
        bar_gross = sum(q[a] * r_fwd[a] for a in assets)
        bar_turnover = sum(abs(q[a] - prev_weights[a]) for a in assets)

        cycle_ts.append(t)
        weights.append(dict(q))
        gross.append(bar_gross)
        turnover.append(bar_turnover)
        net.append(bar_gross - fee * bar_turnover)
        prev_weights = dict(q)

    return RealizedSeries(
        cycle_ts=cycle_ts,
        weights=weights,
        gross=gross,
        turnover=turnover,
        net=net,
        dropped_tail=len(clean) - len(cycle_ts),
        assets=assets,
        chain_ok=_chain_consistent(cycle_ts, closes),
        implausible=implausible,
    )


def _net_live_from_result(result, *, fee_builder: float, fee: float) -> tuple[list[float], bool]:
    """Recompute a crossfreq-system result's net P&L under the LIVE cost convention: cost charged
    on `final_targets = mult x capped` turnover instead of the builder's `governed_net` convention
    (cost on the capped book's own turnover). The gross legs are identical either way, so only the
    turnover cost differs -- that difference is exactly the governor's turnover bias:

        net_live[k] = governed_net[k] + mult[k]*fee_builder*turn_capped[k] - fee*turn_final[k]

    `capped` is reconstructed from `result.sleeve_positions` (the 1/3-combined B/A1/A2 sleeves,
    position-capped) rather than read from `final_targets`/`multipliers` directly, since dividing
    final_targets by multipliers is undefined on a governor-disengaged (mult==0) bar. Returns
    (net_live over the n_periods completed bars, reconcile_ok), where reconcile_ok cross-checks
    that mult[k]*capped[a][k] == final_targets[a][k] for every asset and row (including the
    forming interval) -- proof the reconstruction faithfully matches the builder's internal capped
    book.
    """
    n = result.n_periods
    assets = tuple(result.final_targets)
    sleeves = result.sleeve_positions
    combined = {a: [(sleeves["B"][a][k] + sleeves["A1"][a][k] + sleeves["A2"][a][k]) / 3.0 for k in range(n + 1)] for a in assets}
    capped = apply_position_caps(combined)
    mult = result.multipliers
    final_targets = result.final_targets

    reconcile_ok = all(abs(mult[k] * capped[a][k] - final_targets[a][k]) <= 1e-9 for a in assets for k in range(n + 1))

    net_live: list[float] = []
    for k in range(n):
        turn_capped = sum(abs(capped[a][k] - (capped[a][k - 1] if k > 0 else 0.0)) for a in assets)
        turn_final = sum(abs(final_targets[a][k] - (final_targets[a][k - 1] if k > 0 else 0.0)) for a in assets)
        net_live.append(result.governed_net[k] + mult[k] * fee_builder * turn_capped - fee * turn_final)

    return net_live, reconcile_ok


@dataclass(frozen=True)
class NullSystem:
    """The backtest reference the realized series is judged against: the same strategy rebuilt
    over the full frozen canonical history, with P&L recast onto the live cost convention (see
    `_net_live_from_result`)."""

    weights: list[dict[str, float]]  # final_targets transposed to per-bar dicts, completed bars only (n_periods)
    net_live: list[float]  # n_periods
    multipliers: list[float]  # n_periods (sliced from the n_periods+1 result)
    day_index: list[int]  # n_periods
    assets: tuple[str, ...]
    reconcile_ok: bool
    n_periods: int


def build_null(canonical_dir: Path, config: CrossfreqSystemConfig = CrossfreqSystemConfig(), *, fee: float = 0.006) -> NullSystem:
    """Load the frozen canonical dataset, rebuild the SAME strategy with `build_crossfreq_system_fast`,
    and derive the live-cost-convention null (`NullSystem`) the realized series is compared against."""
    raw = {(a, iv): read_store_series(canonical_dir, a, iv) for a in PAIR_KEYS for iv in GRID_INTERVALS}
    daily_ts, daily_prices = _union_align(raw, 1440)
    h4_ts, h4_prices = _union_align(raw, 240)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)

    net_live, reconcile_ok = _net_live_from_result(result, fee_builder=config.spot_fee_per_side, fee=fee)
    assets = tuple(result.final_targets)
    n = result.n_periods
    weights = [{a: result.final_targets[a][k] for a in assets} for k in range(n)]

    return NullSystem(
        weights=weights,
        net_live=net_live,
        multipliers=list(result.multipliers[:n]),
        day_index=list(result.day_index[:n]),
        assets=assets,
        reconcile_ok=reconcile_ok,
        n_periods=n,
    )


def _reduce(values: list[float], reducer: str) -> float:
    if reducer == "mean":
        return sum(values) / len(values)
    raise SoakError(f"unsupported reducer {reducer!r}")


def windowed_null(series: list[float], window: int, *, reducer: str = "mean") -> list[float]:
    """All contiguous overlapping length-`window` window statistics over `series` (len(series) -
    window + 1 windows). reducer 'mean' reduces each window to its mean. Returns [] if window >
    len(series) or window <= 0."""
    if window <= 0 or window > len(series):
        return []
    return [_reduce(series[i : i + window], reducer) for i in range(len(series) - window + 1)]


def block_bootstrap_null(
    series: list[float],
    window: int,
    *,
    n: int = 10000,
    mean_block: int = 6,
    seed: int = 0,
    reducer: str = "mean",
) -> list[float]:
    """Stationary (Politis-Romano) block bootstrap: `n` resampled length-`window` paths, each
    built by concatenating blocks of geometrically-distributed length (mean `mean_block`) starting
    at random offsets into `series` and wrapping circularly (so every offset stays equally
    likely), truncated to exactly `window`; each path is reduced via `reducer`. Deterministic
    given `seed` -- one `numpy.random.default_rng(seed)` drives the whole call."""
    rng = np.random.default_rng(seed)
    n_obs = len(series)
    p = 1.0 / mean_block
    out: list[float] = []
    for _ in range(n):
        path: list[float] = []
        while len(path) < window:
            start = int(rng.integers(0, n_obs))
            block_len = int(rng.geometric(p))
            for j in range(block_len):
                if len(path) >= window:
                    break
                path.append(series[(start + j) % n_obs])
        out.append(_reduce(path, reducer))
    return out


@dataclass(frozen=True)
class MetricVerdict:
    """The judgment of a single live metric value against its null distribution: which band zone
    `live` falls in (see `metric_verdict`), plus the null summary (`median`/`lo`/`hi`/`width`) and
    `live`'s percentile rank within it."""

    verdict: str  # "consistent" | "weakly-consistent" | "inconsistent" | "n/a"
    live: float
    median: float
    lo: float  # p5
    hi: float  # p95
    percentile: float  # the percentile rank of `live` within the null (0..100)
    effective_n: float
    width: float  # hi - lo


def metric_verdict(
    live: float,
    null_values: list[float],
    *,
    band: float = 0.90,
    effective_n: float = float("inf"),
) -> MetricVerdict:
    """Judge `live` against the null distribution `null_values` using a two-sided band.

    `band` sets the outer interval: `lo_out = (1-band)/2` and `hi_out = 1-lo_out` percentiles
    (0.90 -> p5/p95) bound "inconsistent" on either side (too-low is a bug tell too, not just
    too-high). The inner half-width interval `[lo_out*2, 1-lo_out*2]` percentiles (0.90 -> p10/p90)
    bounds "consistent"; the two edge zones between inner and outer bound "weakly-consistent".
    A degenerate discriminator -- zero-width outer band or `effective_n < 3` -- is "n/a"
    regardless of where `live` falls. Empty/singleton `null_values` is also "n/a" (width 0).
    """
    if len(null_values) < 2:
        return MetricVerdict(
            verdict="n/a", live=live, median=live, lo=live, hi=live, percentile=50.0, effective_n=effective_n, width=0.0
        )

    lo_out_q = (1.0 - band) / 2.0
    hi_out_q = 1.0 - lo_out_q
    lo_in_q = lo_out_q * 2.0
    hi_in_q = 1.0 - lo_in_q

    lo = float(np.percentile(null_values, lo_out_q * 100.0, method="linear"))
    hi = float(np.percentile(null_values, hi_out_q * 100.0, method="linear"))
    inner_lo = float(np.percentile(null_values, lo_in_q * 100.0, method="linear"))
    inner_hi = float(np.percentile(null_values, hi_in_q * 100.0, method="linear"))
    median = float(np.percentile(null_values, 50.0, method="linear"))
    width = hi - lo
    percentile = (sum(1 for v in null_values if v <= live) / len(null_values)) * 100.0

    if width == 0.0 or effective_n < 3:
        verdict = "n/a"
    elif inner_lo <= live <= inner_hi:
        verdict = "consistent"
    elif lo <= live <= hi:
        verdict = "weakly-consistent"
    else:
        verdict = "inconsistent"

    return MetricVerdict(
        verdict=verdict, live=live, median=median, lo=lo, hi=hi, percentile=percentile, effective_n=effective_n, width=width
    )


def degenerate(live_gross_series: list[float], *, floor: float = 1e-6) -> bool:
    """True if the window carries near-zero exposure (mean |gross| < floor) -- echoes the [0,0]
    holdout: a run where the strategy never actually put on a position can't be judged against a
    null built from an active strategy."""
    if not live_gross_series:
        return True
    return (sum(abs(v) for v in live_gross_series) / len(live_gross_series)) < floor


@dataclass(frozen=True)
class PanelSummary:
    """The panel-level multiplicity-aware summary: how many of the judged metrics landed
    "inconsistent" against how many would be expected by chance alone at this band."""

    n_metrics: int
    n_outside: int  # count of "inconsistent"
    expected_by_chance: float  # n_metrics * (1 - band)
    line: str  # e.g. "1 of 7 outside band (~0.7 expected by chance at 90%)"


def summarize_panel(verdicts: dict[str, MetricVerdict], *, band: float = 0.90) -> PanelSummary:
    """Summarize a panel of per-metric verdicts, resisting multiplicity: judging N metrics at
    `band` will show ~N*(1-band) outside the band by chance alone, so the summary reports the
    observed count against that expectation rather than alarming on any single worst-of-N metric.
    """
    n_metrics = len(verdicts)
    n_outside = sum(1 for v in verdicts.values() if v.verdict == "inconsistent")
    expected_by_chance = n_metrics * (1.0 - band)
    line = f"{n_outside} of {n_metrics} outside band (~{expected_by_chance:.1f} expected by chance at {band * 100:.0f}%)"
    return PanelSummary(n_metrics=n_metrics, n_outside=n_outside, expected_by_chance=expected_by_chance, line=line)
