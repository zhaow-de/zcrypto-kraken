"""Structural metrics computed from a sequence of per-bar portfolio weights: gross and net
exposure, the fraction of assets held active, per-bar turnover, portfolio concentration (HHI),
and whether either per-asset cap was breached. Also derives, from a per-bar governor multiplier
series, which trading days saw the governor engage at all.

Also builds the REALIZED forward-return observation from the engine's journal + price store: for
each cycle T, the position decided at T is held over [T, T+4h) and scored against that bar's
actual forward return, joined against the store BY TIMESTAMP -- see `realized_series` for the
exact timing model and its off-by-one cross-check (`chain_ok`).

Also recovers the strategy's per-bar INTERNALS (governor multiplier, cap-breach) at each scored
cycle -- the journal only carries `final_targets`, not the pre-cap combined position or the
multiplier the two gating metrics governor-engagement and cap-breach need. `realized_internals`
rebuilds ONCE on the latest journaled cycle's own hash-verified snapshot history (long enough to
reach every earlier scored cycle's decision row) and resolves each scored cycle's row BY
TIMESTAMP from a `{ts: index}` dict, never by offset arithmetic -- see its docstring for the D2
window-wide identity proof.

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
for a degenerate discriminator (zero-width band, a tiny `effective_n`, or -- given an optional
`domain` -- a band spanning the metric's ENTIRE attainable range, e.g. [0,1] for a rate: nothing
could ever fall outside it, zero discriminating power in the opposite direction from a zero-width
band); `degenerate` flags a near-zero-exposure window that can't be judged at all; `summarize_panel`
rolls a panel of verdicts into a multiplicity-aware summary line, since judging N metrics at a 90%
band will show ~N*0.10 outside it by chance alone.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from cli.engine.concordance import HashMismatchError, replay_cycle
from cli.engine.cycle import _union_align
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json, snapshot_content_hash, validate_record
from cli.engine.store import GRID_INTERVALS, PAIR_KEYS, read_store_series
from cli.portfolio import CrossfreqSystemConfig, PortfolioError, build_crossfreq_system, build_crossfreq_system_fast
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


def _net_live_from_result(result, *, fee_builder: float, fee: float) -> tuple[list[float], bool, list[float]]:
    """Recompute a crossfreq-system result's net P&L under the LIVE cost convention: cost charged
    on `final_targets = mult x capped` turnover instead of the builder's `governed_net` convention
    (cost on the capped book's own turnover). The gross legs are identical either way, so only the
    turnover cost differs -- that difference is exactly the governor's turnover bias:

        net_live[k] = governed_net[k] + mult[k]*fee_builder*turn_capped[k] - fee*turn_final[k]

    `capped` is reconstructed from `result.sleeve_positions` (the 1/3-combined B/A1/A2 sleeves,
    position-capped) rather than read from `final_targets`/`multipliers` directly, since dividing
    final_targets by multipliers is undefined on a governor-disengaged (mult==0) bar. `combined` is
    built with the builder's own `third = 1 / 3` three-multiply form (`crossfreq_system.py:633-634`),
    not `/3.0`, so the cap-breach predicate below (threshold 1e-15) never disagrees with the
    builder's own `cap_breach_bars` on a bit-level rounding difference. Returns (net_live over the
    n_periods completed bars, reconcile_ok, cap_breach), where reconcile_ok cross-checks that
    mult[k]*capped[a][k] == final_targets[a][k] for every asset and row (including the forming
    interval) -- proof the reconstruction faithfully matches the builder's internal capped book --
    and cap_breach[k] is 1.0 iff any asset's pre-cap `combined` book was clipped at bar k (over the
    n_periods completed bars), using the same `> 1e-15` predicate as `crossfreq_system.py:636`.
    """
    n = result.n_periods
    assets = tuple(result.final_targets)
    sleeves = result.sleeve_positions
    third = 1 / 3
    combined = {
        a: [third * sleeves["B"][a][k] + third * sleeves["A1"][a][k] + third * sleeves["A2"][a][k] for k in range(n + 1)]
        for a in assets
    }
    capped = apply_position_caps(combined)
    mult = result.multipliers
    final_targets = result.final_targets

    reconcile_ok = all(abs(mult[k] * capped[a][k] - final_targets[a][k]) <= 1e-9 for a in assets for k in range(n + 1))

    net_live: list[float] = []
    for k in range(n):
        turn_capped = sum(abs(capped[a][k] - (capped[a][k - 1] if k > 0 else 0.0)) for a in assets)
        turn_final = sum(abs(final_targets[a][k] - (final_targets[a][k - 1] if k > 0 else 0.0)) for a in assets)
        net_live.append(result.governed_net[k] + mult[k] * fee_builder * turn_capped - fee * turn_final)

    cap_breach = [1.0 if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in assets) else 0.0 for k in range(n)]

    return net_live, reconcile_ok, cap_breach


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
    governed_net: list[float]  # n_periods
    cap_breach: list[float]  # n_periods; 1.0 on a bar where the pre-cap book was clipped
    cap_breach_bars: int


def _canonical_present(canonical_dir: Path) -> bool:
    """True iff the frozen canonical dataset looks present at `canonical_dir` (checked via BTC's
    240 store file, the same file every canonical-gated test in this suite skips on)."""
    return (canonical_dir / "BTC" / "EUR" / "240.parquet").exists()


def _load_canonical(
    canonical_dir: Path,
) -> tuple[dict[str, list[float | None]], list[datetime], dict[str, list[float | None]], list[datetime]]:
    """Load the frozen canonical dataset's daily and 4h price panels, shared by `build_null` and
    `instrument_self_check` so the two never drift apart on how the canonical is read."""
    raw = {(a, iv): read_store_series(canonical_dir, a, iv) for a in PAIR_KEYS for iv in GRID_INTERVALS}
    daily_ts, daily_prices = _union_align(raw, 1440)
    h4_ts, h4_prices = _union_align(raw, 240)
    return daily_prices, daily_ts, h4_prices, h4_ts


def build_null(
    canonical_dir: Path, config: CrossfreqSystemConfig = CrossfreqSystemConfig(), *, fee: float = 0.006, path: str = "fast"
) -> NullSystem:
    """Load the frozen canonical dataset, rebuild the SAME strategy, and derive the live-cost-convention
    null (`NullSystem`) the realized series is compared against. `path` selects the builder (spec 00061
    D5): `build_crossfreq_system_fast` ("fast", the default) or `build_crossfreq_system` ("verified", the
    daily oracle spot replay) -- mirrors `concordance.replay_cycle`'s own path selection."""
    daily_prices, daily_ts, h4_prices, h4_ts = _load_canonical(canonical_dir)
    if path == "fast":
        result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    elif path == "verified":
        result = build_crossfreq_system(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    else:
        raise SoakError(f"path must be 'fast' or 'verified', got {path!r}")

    net_live, reconcile_ok, cap_breach = _net_live_from_result(result, fee_builder=config.spot_fee_per_side, fee=fee)
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
        governed_net=result.governed_net,
        cap_breach=cap_breach,
        cap_breach_bars=result.cap_breach_bars,
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
    given `seed` -- one `numpy.random.default_rng(seed)` drives the whole call.

    This is the secondary-null robustness primitive: `windowed_null`'s overlapping windows share
    observations across windows and so understate the true sampling variance, while this block
    bootstrap resamples independent paths and gives a cross-check reference distribution. Provided
    for a planned follow-up that compares verdicts under both nulls side by side; not yet consumed
    by `analyze_soak`/`soak_report`, which drive their verdicts from `windowed_null` alone.
    """
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
    domain: tuple[float, float] | None = None,
) -> MetricVerdict:
    """Judge `live` against the null distribution `null_values` using a two-sided band.

    `band` sets the outer interval: `lo_out = (1-band)/2` and `hi_out = 1-lo_out` percentiles
    (0.90 -> p5/p95) bound "inconsistent" on either side (too-low is a bug tell too, not just
    too-high). The inner half-width interval `[lo_out*2, 1-lo_out*2]` percentiles (0.90 -> p10/p90)
    bounds "consistent"; the two edge zones between inner and outer bound "weakly-consistent".
    A degenerate discriminator -- zero-width outer band or `effective_n < 3` -- is "n/a"
    regardless of where `live` falls. Empty/singleton `null_values` is also "n/a" (width 0).

    `domain`, when given, is the metric's attainable range (e.g. `(0.0, 1.0)` for a rate). If the
    computed outer band covers the FULL domain -- `lo <= domain[0] + eps` AND `hi >= domain[1] -
    eps` -- no possible value could ever fall outside it, so the band has zero discriminating
    power just as surely as a zero-width one: also "n/a" (computed stats are kept so the row still
    renders its numbers).
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

    eps = 1e-12
    full_range = domain is not None and lo <= domain[0] + eps and hi >= domain[1] - eps

    if width == 0.0 or effective_n < 3 or full_range:
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


def _full_range_disclosure(name: str, verdict: MetricVerdict, domain: tuple[float, float] | None) -> str | None:
    """If `verdict` is "n/a" because its outer band spans the FULL `domain` (Fix 1 in
    `metric_verdict`) rather than being zero-width or having a tiny `effective_n`, return the
    disclosure line naming it -- `width > 0` and `effective_n >= 3` rule out `metric_verdict`'s
    other two "n/a" triggers, isolating this one."""
    if domain is None or verdict.verdict != "n/a" or verdict.width <= 0.0 or verdict.effective_n < 3:
        return None
    return (
        f"{name}: the null band spans the full [{domain[0]:g},{domain[1]:g}] range at this window "
        "length -- the test has no discriminating power here"
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
    "inconsistent" against how many would be expected by chance alone at this band, plus (spec
    00061 D3) how many reconciled to an opposite-extremes split (`indeterminate` -- see
    `reconcile_verdicts`)."""

    n_metrics: int
    n_outside: int  # count of "inconsistent"
    n_indeterminate: int  # count reconciled to "indeterminate (instrument-fragile)" (D3)
    expected_by_chance: float  # n_metrics * (1 - band)
    line: str  # e.g. "1 of 7 outside band (~0.7 expected by chance at 90%)"
    indeterminate_line: str  # e.g. "1 of 7 indeterminate -- ..."; "" when n_indeterminate == 0


def summarize_panel(
    verdicts: dict[str, MetricVerdict], *, band: float = 0.90, dual_verdicts: dict[str, DualVerdict] | None = None
) -> PanelSummary:
    """Summarize a panel of per-metric verdicts, resisting multiplicity: judging N DISCRIMINATING
    metrics at `band` will show ~N*(1-band) outside the band by chance alone, so the summary reports
    the observed count against that expectation rather than alarming on any single worst-of-N metric.

    `n_metrics` counts only verdicts that actually discriminate (`verdict != "n/a"`, spec D6) -- a
    degenerate band or an unavailable internals rebuild can't contribute a false positive, so
    counting it would overstate the expected-by-chance baseline. This also makes a degraded run
    self-consistent with no special-casing: with 2 of 7 metrics `"n/a"`, the line reads "... of 5"
    automatically.

    `dual_verdicts` (spec 00061 D3, keyed like `verdicts`) names which metrics reconciled to
    `"indeterminate (instrument-fragile)"`: those metrics still count toward `n_metrics` (both nulls
    DID discriminate -- they simply disagreed) but NEVER toward `n_outside`, even when the primary
    null's own raw verdict happens to be `"inconsistent"` -- there is no agreed finding to count.
    Omitted (the default `None`, or a metric absent from the dict) means no reconciliation ran for
    that metric, matching today's behavior.
    """
    dual_verdicts = dual_verdicts or {}
    discriminating = [(m, v) for m, v in verdicts.items() if v.verdict != "n/a"]
    n_metrics = len(discriminating)
    indeterminate = {
        m
        for m, _ in discriminating
        if dual_verdicts.get(m) is not None and dual_verdicts[m].verdict == "indeterminate (instrument-fragile)"
    }
    n_indeterminate = len(indeterminate)
    n_outside = sum(1 for m, v in discriminating if v.verdict == "inconsistent" and m not in indeterminate)
    expected_by_chance = n_metrics * (1.0 - band)
    line = f"{n_outside} of {n_metrics} outside band (~{expected_by_chance:.1f} expected by chance at {band * 100:.0f}%)"
    indeterminate_line = (
        f"{n_indeterminate} of {n_metrics} indeterminate -- the verdict depends on how the null was constructed"
        if n_indeterminate
        else ""
    )
    return PanelSummary(
        n_metrics=n_metrics,
        n_outside=n_outside,
        n_indeterminate=n_indeterminate,
        expected_by_chance=expected_by_chance,
        line=line,
        indeterminate_line=indeterminate_line,
    )


_SEVERITY = {"consistent": 0, "weakly-consistent": 1, "inconsistent": 2}


@dataclass(frozen=True)
class DualVerdict:
    """The reconciliation of a metric's two independently-constructed null verdicts (spec 00061
    D1): `primary` from the windowed null, `secondary` from the block-bootstrap null. Agreement
    keeps the shared label; an adjacent disagreement (severity differs by 1) takes the MILDER
    (lower-severity) label -- the reading less likely to claim a divergence; a `consistent` vs
    `inconsistent` split (severity differs by 2) degrades to `"indeterminate
    (instrument-fragile)"`, since asserting either label would claim more than the two
    constructions agree on. `disclosure` is `""` exactly when `primary == secondary`."""

    verdict: str  # reconciled label, or "indeterminate (instrument-fragile)"
    primary: str  # the windowed null's label
    secondary: str  # the bootstrap null's label
    disclosure: str  # "" when the two agree


def reconcile_verdicts(primary: str, secondary: str) -> DualVerdict:
    """Reconcile two per-metric null verdicts under spec 00061 D1. Pure: no metric knowledge, no
    I/O -- just the two label strings in, a `DualVerdict` out.

    Equal labels (including both `"n/a"`, and two equal but UNRECOGNIZED labels) short-circuit to
    that label with no disclosure -- agreement never needs the severity order, so an unrecognized
    label used consistently by both nulls still reconciles cleanly. Exactly one `"n/a"` takes the
    other (discriminating) null's label, disclosing that only one construction had power here.
    A label outside `_SEVERITY` that DIFFERS from the other side can't be placed on the severity
    order at all -- rather than raise a bare `KeyError`, it is treated the same as an
    opposite-extremes split (`"indeterminate (instrument-fragile)"`, disclosed by name): reconciling
    something we don't understand would claim more confidence than we have.
    """
    if primary == secondary:
        return DualVerdict(verdict=primary, primary=primary, secondary=secondary, disclosure="")

    if primary == "n/a" or secondary == "n/a":
        discriminating = secondary if primary == "n/a" else primary
        disclosure = (
            f"only one null construction discriminated here (primary={primary!r}, secondary={secondary!r}) -- "
            "the other's band had no power"
        )
        return DualVerdict(verdict=discriminating, primary=primary, secondary=secondary, disclosure=disclosure)

    if primary not in _SEVERITY or secondary not in _SEVERITY:
        disclosure = (
            f"unrecognized verdict label (primary={primary!r}, secondary={secondary!r}) -- "
            "cannot place it on the severity order, treating as instrument-fragile"
        )
        return DualVerdict(
            verdict="indeterminate (instrument-fragile)", primary=primary, secondary=secondary, disclosure=disclosure
        )

    gap = abs(_SEVERITY[primary] - _SEVERITY[secondary])
    if gap == 1:
        milder = primary if _SEVERITY[primary] < _SEVERITY[secondary] else secondary
        disclosure = f"the two null constructions disagree: primary={primary!r}, secondary={secondary!r} -- reporting the milder"
        return DualVerdict(verdict=milder, primary=primary, secondary=secondary, disclosure=disclosure)

    disclosure = f"the two null constructions give opposite verdicts: primary={primary!r}, secondary={secondary!r}"
    return DualVerdict(verdict="indeterminate (instrument-fragile)", primary=primary, secondary=secondary, disclosure=disclosure)


@dataclass(frozen=True)
class SelfTestReport:
    """Before any verdict is read, the instrument must prove itself: `instrument_ok` reproduces a
    known registry result, `identity_ok` shows the journaled positions reproduce under replay,
    `reconcile_ok` shows the null and the realized series' own internal bookkeeping check out, and
    `plausibility_checks` (folded into `messages`) shows every value sits within bounds. `void`
    REFUSES the run (rather than emit a plausible-but-wrong verdict) the moment any self-test
    RAN and FAILED -- `None` (skipped, e.g. no canonical data or nothing to replay) never VOIDs by
    itself, only an explicit `False` does."""

    instrument_ok: bool | None  # None = canonical absent (skipped, NOT a fail)
    identity_ok: bool | None  # None = no cycle could be replayed (e.g. snapshots absent)
    reconcile_ok: bool
    messages: tuple[str, ...]

    @property
    def void(self) -> bool:
        return self.instrument_ok is False or self.identity_ok is False or self.reconcile_ok is False


def _load_registry_record(registry_path: Path, trial_id: int) -> dict:
    """Return the JSON object in `registry_path` (JSON-lines) whose `trial_id == trial_id`."""
    with registry_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("trial_id") == trial_id:
                return record
    raise SoakError(f"no trial_id={trial_id} record in {registry_path}")


def _instrument_expectations(registry_path: Path) -> dict[str, int]:
    """{'governor_engaged_bars': ..., 'cap_breach_bars': ...} from record 44's metrics -- the
    ratified deployable-system trial (docs/reference/trial-registry.jsonl) the frozen engine build
    must reproduce exactly."""
    metrics = _load_registry_record(registry_path, 44)["metrics"]
    return {
        "governor_engaged_bars": int(metrics["governor_engaged_bars"]),
        "cap_breach_bars": int(metrics["cap_breach_bars"]),
    }


def instrument_self_check(
    canonical_dir: Path, registry_path: Path, config: CrossfreqSystemConfig = CrossfreqSystemConfig()
) -> tuple[bool | None, str]:
    """Rebuild the frozen strategy over the full canonical history (the same load `build_null`
    uses, via `_load_canonical`) and assert its `governor_engaged_bars`/`cap_breach_bars` EXACTLY
    match record 44's registry values. Returns (None, 'canonical absent') without building
    anything when `canonical_dir` has no data (skip, not fail) -- this is expected on a host
    without `data/ohlc-full`."""
    if not _canonical_present(canonical_dir):
        return None, "canonical absent"

    daily_prices, daily_ts, h4_prices, h4_ts = _load_canonical(canonical_dir)
    result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    expected = _instrument_expectations(registry_path)

    mismatches = [
        f"{key}={getattr(result, key)} != registry {value}" for key, value in expected.items() if getattr(result, key) != value
    ]
    if mismatches:
        return False, "instrument mismatch: " + "; ".join(mismatches)
    return True, "instrument reproduces record 44"


def identity_self_check(record, snapshot_reader, *, tol: float = 1e-6, path: str = "fast") -> tuple[bool, str]:
    """Recompute `record`'s newest-row targets via `replay_cycle(record, snapshot_reader, path=path)`
    and compare against `record.final_targets`, per asset, within `tol`. `path` (spec 00061 D5)
    selects the builder `replay_cycle` runs -- 'fast' (default) or 'verified' (the daily oracle spot
    replay). A replay failure (missing or corrupt journaled snapshots) is NOT caught here -- it
    propagates to the caller (`self_tests`), which treats "could not be checked" (identity_ok=None)
    as distinct from this function's only failure mode, a genuine value mismatch (identity_ok=False)."""
    replayed = replay_cycle(record, snapshot_reader, path=path)
    mismatches = [
        f"{asset}: replayed={replayed.get(asset)!r} recorded={value!r}"
        for asset, value in record.final_targets.items()
        if asset not in replayed or abs(replayed[asset] - value) > tol
    ]
    if mismatches:
        return False, "identity mismatch: " + "; ".join(mismatches)
    return True, "identity check passed"


@dataclass(frozen=True)
class RealizedInternals:
    """The strategy's per-bar internals (governor multiplier, cap-breach) at each SCORED cycle's
    resolved row, recovered by rebuilding on the latest journaled cycle's own hash-verified
    snapshot history (see `realized_internals`) -- the journal itself only carries
    `final_targets`, not the pre-cap combined position or the multiplier the two new gating
    metrics need. `available=False` DEGRADES the run (missing/corrupt snapshots, an invalid record,
    a builder EngineError/PortfolioError) rather than voiding it -- the caller decides what an
    unavailable rebuild means for the overall soak verdict. `identity_ok`/`cap_consistent` are D2's
    window-wide proof that each resolved row `k` really is that scored cycle's decision row -- see
    `realized_internals`."""

    available: bool
    reason: str  # why unavailable ("" when available)
    mult_by_cycle: dict[datetime, float]
    breach_by_cycle: dict[datetime, bool]
    identity_ok: bool
    identity_detail: str
    cap_consistent: bool
    cap_detail: str


def _assemble_latest_grids(
    record: CycleRecord, snapshot_reader
) -> tuple[list[datetime] | None, dict[str, list[float | None]], list[datetime] | None, dict[str, list[float | None]]]:
    """Mirror `concordance.replay_cycle`'s snapshot assembly for `record`'s own snapshots: read
    each SnapshotEntry via `snapshot_reader`, hash-verify it against its declared content_hash
    (HashMismatchError on mismatch -- corrupt evidence), reconcile the read data against the
    entry's own len/first_ts/last_ts metadata (EngineJournalError on disagreement), then group by
    grid ("1440"/"240") and assert every pair on a grid shares one calendar (EngineJournalError on
    disagreement). A parallel implementation, not a shared import -- `replay_cycle` itself is
    untouched and unaffected. Returns (daily_ts, daily_prices, h4_ts, h4_prices)."""
    by_grid: dict[str, dict[str, tuple[list[datetime], list[float | None]]]] = {"1440": {}, "240": {}}
    for entry in record.snapshots:
        ts, closes = snapshot_reader(entry)
        if snapshot_content_hash(ts, closes) != entry.content_hash:
            raise HashMismatchError(f"content hash mismatch for pair={entry.pair!r} grid={entry.grid!r} -- corrupt evidence")
        if len(ts) != entry.n_bars or ts[0] != entry.first_ts or ts[-1] != entry.last_ts:
            raise EngineJournalError(
                f"pair={entry.pair!r} grid={entry.grid!r}: read data disagrees with its own journaled metadata -- "
                f"n_bars={len(ts)} vs {entry.n_bars!r}, first_ts={ts[0]!r} vs {entry.first_ts!r}, "
                f"last_ts={ts[-1]!r} vs {entry.last_ts!r}"
            )
        by_grid[entry.grid][entry.pair] = (ts, closes)

    def _assemble(grid: str) -> tuple[list[datetime] | None, dict[str, list[float | None]]]:
        shared_ts: list[datetime] | None = None
        prices: dict[str, list[float | None]] = {}
        for pair, (ts, closes) in by_grid[grid].items():
            if shared_ts is None:
                shared_ts = ts
            elif ts != shared_ts:
                raise EngineJournalError(f"pair={pair!r} grid={grid!r} ts calendar disagrees with the grid's shared calendar")
            prices[pair] = closes
        return shared_ts, prices

    daily_ts, daily_prices = _assemble("1440")
    h4_ts, h4_prices = _assemble("240")
    return daily_ts, daily_prices, h4_ts, h4_prices


def realized_internals(
    scored_records: list[CycleRecord],
    latest_record: CycleRecord,
    snapshot_reader,
    *,
    tol: float = 1e-6,
) -> RealizedInternals:
    """Recover each SCORED cycle's governor multiplier and cap-breach flag by rebuilding ONE
    `build_crossfreq_system_fast` over `latest_record`'s own snapshots -- its 240 (4h) history
    reaches `latest_record.cycle_ts - 4h`, i.e. every earlier scored cycle's decision row -- and
    reading each scored cycle's row back out of that single rebuild.

    THE KEYSTONE: the row for the decision made at cycle T is the index k where h4_ts[k] ==
    T - 4h, resolved from a `{ts: index}` dict -- NEVER by offset arithmetic. If T - 4h is absent
    from the rebuilt grid, raises SoakError naming T -- a genuine inconsistency, not a degrade.
    Likewise, if a scored cycle's final_targets names an asset outside the rebuilt universe
    (plausible across a universe change), raises SoakError naming the asset and cycle rather than
    letting a bare KeyError escape.

    D2 (the proof): at that same k, the rebuild's `final_targets[a][k]` must equal the journaled
    cycle's `final_targets[a]` to `tol`, for every scored cycle and every asset -- `identity_ok` is
    that window-wide check; any ±1 shift, grid misalignment, or wrong-record rebuild breaks it.
    `identity_detail` names the worst |diff| and where it occurred.

    Cap-breach mirrors `crossfreq_system.py`'s own `cap_breach_bars` formula exactly, over all
    `len(h4_ts)` rows: `combined[a][k]` is the 1/3-mean of the B/A1/A2 sleeves (pre-cap, from
    `result.sleeve_positions`), `capped = apply_position_caps(combined)`, and `breach[k]` is True
    iff any asset's `|capped - combined| > 1e-15` at that row. This is computed from the
    pre-multiplier sleeves rather than from `final_targets` because `final_targets = mult *
    capped` is always in-cap by construction (capping happens before the governor multiply) and so
    can never itself show a breach. `cap_consistent` cross-checks the completed-bar breach count
    (`breach[:result.n_periods]`) against the rebuild's own `cap_breach_bars`.

    Record validation (`validate_record`), assembly, and build (the snapshot read/hash-verify and
    the builder call) DEGRADE the run on any `EngineError` (missing/corrupt snapshots, a
    grid-assembly disagreement, a schema/boundary violation) or `PortfolioError` (e.g. the
    rebuilt grid's asset set disagreeing with the builder's universe): returns `available=False`
    with `reason=str(exc)` and empty/void fields, never voiding the whole soak-check outright --
    that decision belongs to the caller. A `SoakError` from a missing T-4h stamp or an asset
    outside the rebuilt universe is a genuine inconsistency in the per-cycle loop below and
    propagates instead.
    """
    try:
        validate_record(latest_record)
        daily_ts, daily_prices, h4_ts, h4_prices = _assemble_latest_grids(latest_record, snapshot_reader)
        result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts)
    except (EngineError, PortfolioError) as exc:
        return RealizedInternals(
            available=False,
            reason=str(exc),
            mult_by_cycle={},
            breach_by_cycle={},
            identity_ok=False,
            identity_detail="",
            cap_consistent=False,
            cap_detail="",
        )

    idx = {ts: k for k, ts in enumerate(h4_ts)}
    assets = tuple(result.final_targets)
    n_rows = len(h4_ts)
    sleeves = result.sleeve_positions
    third = 1 / 3
    combined = {
        a: [third * sleeves["B"][a][k] + third * sleeves["A1"][a][k] + third * sleeves["A2"][a][k] for k in range(n_rows)]
        for a in assets
    }
    capped = apply_position_caps(combined)
    breach = [any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in assets) for k in range(n_rows)]

    mult_by_cycle: dict[datetime, float] = {}
    breach_by_cycle: dict[datetime, bool] = {}
    identity_ok = True
    worst_diff = 0.0
    worst_detail = "n/a"
    for rec in scored_records:
        t = rec.cycle_ts
        k = idx.get(t - timedelta(hours=4))
        if k is None:
            raise SoakError(f"cycle {t!r}: T - 4h not found in the rebuilt h4 grid")
        mult_by_cycle[t] = result.multipliers[k]
        breach_by_cycle[t] = breach[k]
        for a, value in rec.final_targets.items():
            if a not in result.final_targets:
                raise SoakError(f"cycle {t!r}: asset {a!r} not in the rebuilt universe {sorted(result.final_targets)}")
            diff = abs(result.final_targets[a][k] - value)
            if diff >= worst_diff:
                worst_diff = diff
                worst_detail = f"cycle={t!r} asset={a!r}"
            if diff > tol:
                identity_ok = False

    identity_detail = f"worst |diff|={worst_diff!r} at {worst_detail}"

    completed_breaches = sum(1 for b in breach[: result.n_periods] if b)
    cap_consistent = completed_breaches == result.cap_breach_bars
    cap_detail = f"completed-bar breach count={completed_breaches} vs result.cap_breach_bars={result.cap_breach_bars}"

    return RealizedInternals(
        available=True,
        reason="",
        mult_by_cycle=mult_by_cycle,
        breach_by_cycle=breach_by_cycle,
        identity_ok=identity_ok,
        identity_detail=identity_detail,
        cap_consistent=cap_consistent,
        cap_detail=cap_detail,
    )


def plausibility_checks(realized, null) -> list[str]:
    """Scan `realized`/`null` for out-of-bounds diagnostics; returns one message per violation
    found (empty = all in bounds). Bounds: `realized.implausible` (already flags any |r_fwd| > 0.5
    in the scored segment); every `realized.gross` bar within [-2, 2] (a book beyond 200% gross is
    instrument breakage, not strategy); every `null.net_live` value finite; and both reconcile
    flags (`realized.chain_ok`, `null.reconcile_ok`) on."""
    messages: list[str] = []
    if realized.implausible:
        messages.append("realized: implausible forward return |r_fwd| > 0.5 in the scored segment")
    messages.extend(f"realized: gross {g!r} outside plausibility bound [-2, 2]" for g in realized.gross if not (-2.0 <= g <= 2.0))
    messages.extend(f"null: net_live value {v!r} is not finite" for v in null.net_live if not math.isfinite(v))
    if not realized.chain_ok:
        messages.append("realized: chain_ok is False (forward join integrity broken)")
    if not null.reconcile_ok:
        messages.append("null: reconcile_ok is False (live-cost reconstruction diverged)")
    return messages


def self_tests(
    records: list[CycleRecord],
    null: NullSystem,
    *,
    realized: RealizedSeries,
    canonical_dir: Path,
    registry_path: Path,
    snapshot_reader,
    config: CrossfreqSystemConfig = CrossfreqSystemConfig(),
    path: str = "fast",
) -> SelfTestReport:
    """Run the instrument, identity, and reconcile self-tests plus the plausibility scan, and roll
    them into a `SelfTestReport`. Extends the sketched signature with a required keyword-only
    `realized: RealizedSeries` -- `plausibility_checks` and the chain-of-custody half of
    `reconcile_ok` both need it, and `NullSystem` alone doesn't carry it.

    `identity_self_check` replays the NEWEST record in `records` (by `cycle_ts`) -- the journaled
    cycle closest to the live edge, where a replay break matters most. An empty `records`, or a
    replay that raises `EngineError` (missing/corrupt snapshots), both skip identity
    (`identity_ok=None`) rather than failing it -- matching instrument's None-on-absent-data
    convention. `reconcile_ok = null.reconcile_ok and realized.chain_ok`: the backtest null's own
    internal bookkeeping and the realized series' forward-join integrity must both hold. `path`
    (spec 00061 D5) threads to `identity_self_check`'s own builder-path selection; `instrument_self_check`
    is untouched (it always reproduces record 44 via the fast path).
    """
    messages: list[str] = []

    instrument_ok, instrument_msg = instrument_self_check(canonical_dir, registry_path, config=config)
    messages.append(f"instrument: {instrument_msg}")

    if not records:
        identity_ok: bool | None = None
        messages.append("identity: skipped, no records to replay")
    else:
        newest = max(records, key=lambda r: r.cycle_ts)
        try:
            identity_ok, identity_msg = identity_self_check(newest, snapshot_reader, path=path)
            messages.append(f"identity: {identity_msg}")
        except EngineError as exc:
            identity_ok = None
            messages.append(f"identity: skipped, replay failed: {exc}")

    reconcile_ok = null.reconcile_ok and realized.chain_ok
    messages.append(f"reconcile: {'ok' if reconcile_ok else 'FAILED'}")

    messages.extend(plausibility_checks(realized, null))

    return SelfTestReport(
        instrument_ok=instrument_ok,
        identity_ok=identity_ok,
        reconcile_ok=reconcile_ok,
        messages=tuple(messages),
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True)
class SoakAnalysis:
    """The full soak-check analysis tying the realized series to its backtest null: a verdict per
    GATING metric -- gross/net/active_frac/turnover/hhi (computable from the journaled weights
    alone) plus governor_engagement/cap_breach (computed from `internals` when available, else
    `"n/a"` with `internals_reason` naming why -- D7 degrade, not void) -- 7 keys total, the panel
    summary over the DISCRIMINATING subset (`summarize_panel` excludes `"n/a"`, spec D6), the D4
    governed-vs-live P&L gap, the NON-GATING realized-vs-null P&L verdict, and `disclosures`:
    human-readable interpretation notes (constant realized multiplier/cap-breach, the weight-derived
    metric cluster's overstated independence, governor day-granularity exactness, a vacuous
    full-[0,1]-range band) that change no verdict."""

    L: int  # scored realized bars
    gating_verdicts: dict[str, MetricVerdict]  # keys: gross, net, active_frac, turnover, hhi, governor_engagement, cap_breach
    panel: PanelSummary  # summarize_panel over the discriminating (non-"n/a") gating verdicts
    null_gov_rate: float  # backtest CONTEXT: fraction of null days governor-engaged
    null_cap_rate: float  # backtest CONTEXT: cap_breach_bars / n_periods
    d4_gap_bps: float  # mean(governed_net - net_live) over frozen history, in bps (x1e4)
    d4_active: bool  # governor engaged anywhere in the null (any mult < 1)
    pnl_mean: float  # realized interior mean net/cycle
    pnl_cum: float  # realized compounded cumulative net over ALL bars: prod(1+net)-1
    pnl_verdict: MetricVerdict  # NON-GATING: realized interior mean net vs null net_live windows
    is_degenerate: bool  # degenerate(structural_metrics(realized.weights)["gross"]) -- exposure, not P&L
    effective_n: dict[str, float]  # per gating metric (7) + "pnl"
    internals_available: bool  # False -> governor_engagement/cap_breach degraded to "n/a" (D7)
    internals_reason: str  # why internals is unavailable ("" when available)
    disclosures: tuple[str, ...]  # human-readable interpretation notes; never changes a verdict
    dual_verdicts: dict[str, DualVerdict]  # spec 00061: keyed like gating_verdicts, plus "pnl"; empty unless null_mode="both"


_NULL_MODES = ("windows", "block-bootstrap", "both")


def _judge_dual(
    live: float,
    null_series: list[float],
    window: int,
    *,
    band: float,
    effective_n: float,
    domain: tuple[float, float] | None,
    null_mode: str,
) -> tuple[MetricVerdict, DualVerdict | None]:
    """Judge `live` against `null_series` under `null_mode` (spec 00061 D4), one call per gating
    call site in `analyze_soak`. `"windows"` judges against `windowed_null` alone -- the bootstrap is
    never computed, so this reproduces today's verdicts byte-for-byte. `"block-bootstrap"` judges
    against `block_bootstrap_null` alone. `"both"` computes BOTH nulls and reconciles their verdicts
    (D1), returning the WINDOWED `MetricVerdict` (D2: the reported numeric stats stay the windowed
    null's) alongside the `DualVerdict` reconciliation. The second element is `None` whenever only one
    null was computed -- no reconciliation to report (D4: "there is no reconciliation").

    `window <= 0` (e.g. an empty/degenerate realized window) skips `block_bootstrap_null` entirely
    and judges against an empty null list instead, mirroring `windowed_null`'s own `window <= 0`
    guard -- `block_bootstrap_null` has no such guard of its own (spec 00061: "no change to either
    null primitive") and would divide by zero building a length-0 path.
    """
    if null_mode == "windows":
        return metric_verdict(live, windowed_null(null_series, window), band=band, effective_n=effective_n, domain=domain), None
    if null_mode == "block-bootstrap":
        bootstrap_values = block_bootstrap_null(null_series, window) if window > 0 else []
        return metric_verdict(live, bootstrap_values, band=band, effective_n=effective_n, domain=domain), None

    windowed_v = metric_verdict(live, windowed_null(null_series, window), band=band, effective_n=effective_n, domain=domain)
    bootstrap_values = block_bootstrap_null(null_series, window) if window > 0 else []
    bootstrap_v = metric_verdict(live, bootstrap_values, band=band, effective_n=effective_n, domain=domain)
    return windowed_v, reconcile_verdicts(windowed_v.verdict, bootstrap_v.verdict)


def analyze_soak(
    realized: RealizedSeries,
    null: NullSystem,
    *,
    band: float = 0.90,
    internals: RealizedInternals | None = None,
    null_mode: str = "both",
) -> SoakAnalysis:
    """Judge the realized series against its backtest null and roll the result into a `SoakAnalysis`.

    Gates on 7 structural metrics: gross/net/active_frac/turnover/hhi (from the journaled weights
    alone) plus governor_engagement/cap_breach, recovered from `internals` (see `realized_internals`).
    governor_engagement is judged at DAY granularity (a day is engaged iff any of its scored bars has
    mult < 1.0; window = the realized day count); cap_breach at BAR granularity (window = L). When
    `internals` is `None` or `internals.available` is `False`, both verdicts degrade to `"n/a"` with
    the reason carried in `internals_reason` (D7) -- the other 5 metrics still gate normally, a
    missing rebuild degrades the fingerprint, it does not invalidate it. `summarize_panel` counts
    only DISCRIMINATING verdicts (spec D6), so a degraded run's multiplicity line reads "... of 5"
    with no special-casing. A constant realized multiplier/cap-breach series is a LEGITIMATE verdict
    -- never suppressed to "n/a" -- but is disclosed (`disclosures`) so a reader can interpret it,
    alongside an UNCONDITIONAL cluster note (gross/net/active_frac/hhi are all deterministic
    functions of the same weight vector and turnover is its first difference, so only cap_breach
    probes a separate mechanism -- the panel's metric count overstates independent trials) plus a
    more specific near-redundant gross/net note when it fires (spec D6a, `abs(corr) >= 0.99` OR a
    non-empty long-only book), the governor day-granularity exactness note (the multiplier is
    constant within a day by construction, so a partial realized day carries the same engagement
    information as a full one -- day granularity loses nothing, it is not an approximation), and a
    note naming any RATE metric (active_frac, governor_engagement, cap_breach) whose band went
    "n/a" because it spans the metric's full [0,1] domain (Fix 1: zero discriminating power, not a
    zero-width band).
    Also reports the D4 governed-vs-live gap and judges P&L (realized interior mean net vs null
    net_live windows) as a non-gating verdict. Turnover and P&L are prev-dependent, so both
    aggregate/compare INTERIOR bars (each series' first element dropped) on BOTH the live and null
    sides -- the other gating metrics use all L bars.

    `null_mode` (spec 00061 D4) selects which backtest null construction(s) judge each of the 4
    call sites above (the 5-metric gating loop, governor_engagement, cap_breach, P&L): `"windows"`
    reproduces today's verdicts byte-for-byte (the bootstrap is never computed); `"block-bootstrap"`
    judges against the bootstrap alone; `"both"` (default) judges against both and reconciles them
    via `reconcile_verdicts` (D1) -- `dual_verdicts` carries the reconciliation, keyed like
    `gating_verdicts` plus `"pnl"`, empty for the two single-null modes. A non-empty reconciliation
    disclosure is folded into `disclosures`, named by metric.
    """
    if null_mode not in _NULL_MODES:
        raise SoakError(f"null_mode must be one of {_NULL_MODES}, got {null_mode!r}")

    L = len(realized.net)
    rm = structural_metrics(realized.weights)
    nm = structural_metrics(null.weights)

    # RATE metrics are bounded to [0, 1] by construction -- an outer band spanning that entire
    # attainable range has zero discriminating power (Fix 1: no possible value could ever fall
    # outside it). gross/net/turnover are unbounded above; hhi is bounded in [1/n, 1] but its
    # positive lower bound makes a full-[0,1] band unreachable, so none of them needs a domain.
    rate_domain = (0.0, 1.0)

    gating_verdicts: dict[str, MetricVerdict] = {}
    effective_n: dict[str, float] = {}
    dual_verdicts: dict[str, DualVerdict] = {}
    disclosures: list[str] = []
    for m in ("gross", "net", "active_frac", "turnover", "hhi"):
        if m == "turnover":
            live_series, null_series, window = rm[m][1:], nm[m][1:], L - 1
        else:
            live_series, null_series, window = rm[m], nm[m], L
        eff_n = len(null_series) / window if window > 0 else 0.0
        domain = rate_domain if m == "active_frac" else None
        v, dual = _judge_dual(
            _mean(live_series), null_series, window, band=band, effective_n=eff_n, domain=domain, null_mode=null_mode
        )
        gating_verdicts[m] = v
        effective_n[m] = eff_n
        if dual is not None:
            dual_verdicts[m] = dual
            if dual.disclosure:
                disclosures.append(f"{m}: {dual.disclosure}")

    note = _full_range_disclosure("active_frac", gating_verdicts["active_frac"], rate_domain)
    if note is not None:
        disclosures.append(note)

    # Fix 2: `mult_by_cycle`/`breach_by_cycle` are indexed below by every SCORED cycle_ts. If the
    # internals rebuild's key set ever diverges from `realized.cycle_ts` (it shouldn't, but a bare
    # KeyError escaping here would crash the whole run -- the opposite of the degrade-don't-void
    # contract `realized_internals` itself deliberately upholds via its own named errors), treat
    # the internals as unavailable rather than indexing blind.
    missing_ts = None
    if internals is not None and internals.available:
        missing_ts = next(
            (t for t in realized.cycle_ts if t not in internals.mult_by_cycle or t not in internals.breach_by_cycle), None
        )

    if internals is not None and internals.available and missing_ts is None:
        internals_available = True
        internals_reason = ""

        mult_values = [internals.mult_by_cycle[t] for t in realized.cycle_ts]
        breach_values = [internals.breach_by_cycle[t] for t in realized.cycle_ts]

        engaged_by_day: dict[object, bool] = {}
        for t, m in zip(realized.cycle_ts, mult_values):
            day = t.date()
            engaged_by_day[day] = engaged_by_day.get(day, False) or m < 1.0
        total_days = len(engaged_by_day)
        gov_live = sum(1 for engaged in engaged_by_day.values() if engaged) / total_days if total_days else 0.0
        gov_null = governor_engaged_daily(null.multipliers, null.day_index)
        gov_eff_n = len(gov_null) / total_days if total_days > 0 else 0.0
        gov_v, gov_dual = _judge_dual(
            gov_live, gov_null, total_days, band=band, effective_n=gov_eff_n, domain=rate_domain, null_mode=null_mode
        )
        gating_verdicts["governor_engagement"] = gov_v
        effective_n["governor_engagement"] = gov_eff_n
        if gov_dual is not None:
            dual_verdicts["governor_engagement"] = gov_dual
            if gov_dual.disclosure:
                disclosures.append(f"governor_engagement: {gov_dual.disclosure}")

        cap_live = _mean([1.0 if b else 0.0 for b in breach_values])
        cap_eff_n = len(null.cap_breach) / L if L > 0 else 0.0
        cap_v, cap_dual = _judge_dual(
            cap_live, null.cap_breach, L, band=band, effective_n=cap_eff_n, domain=rate_domain, null_mode=null_mode
        )
        gating_verdicts["cap_breach"] = cap_v
        effective_n["cap_breach"] = cap_eff_n
        if cap_dual is not None:
            dual_verdicts["cap_breach"] = cap_dual
            if cap_dual.disclosure:
                disclosures.append(f"cap_breach: {cap_dual.disclosure}")

        for m in ("governor_engagement", "cap_breach"):
            note = _full_range_disclosure(m, gating_verdicts[m], rate_domain)
            if note is not None:
                disclosures.append(note)

        if mult_values and min(mult_values) == max(mult_values):
            disclosures.append(f"realized multiplier was {mult_values[0]:g} on all {len(mult_values)} scored cycles (no variance)")
        if breach_values and len(set(breach_values)) == 1:
            flag = "1" if breach_values[0] else "0"
            disclosures.append(f"realized cap-breach was {flag} on all {len(breach_values)} scored cycles (no variance)")
        disclosures.append(f"governor-engagement is judged at day granularity over {total_days} realized days")
        disclosures.append(
            "governor-engagement at day granularity is exact, not approximate: the multiplier is constant "
            "within a day by construction (daily_cadence_governor assigns one multiplier per day_index), so "
            "a partial realized day carries the same engagement information as a full one"
        )
    else:
        internals_available = False
        if missing_ts is not None:
            internals_reason = f"internals rebuild missing scored cycle_ts={missing_ts!r} in mult_by_cycle/breach_by_cycle"
        else:
            internals_reason = internals.reason if internals is not None else "no internals rebuild provided"
        na = MetricVerdict(verdict="n/a", live=0.0, median=0.0, lo=0.0, hi=0.0, percentile=0.0, effective_n=0.0, width=0.0)
        gating_verdicts["governor_engagement"] = na
        gating_verdicts["cap_breach"] = na
        effective_n["governor_engagement"] = 0.0
        effective_n["cap_breach"] = 0.0

    # Whole-cluster overstatement: gross/net/active_frac/hhi are all deterministic functions of the
    # SAME weight vector and turnover is that vector's first difference -- only cap_breach probes a
    # mechanism (the pre-cap combined position vs the per-asset cap) genuinely separate from the
    # weights. Unconditional -- unlike the more specific long-only/correlation note below, this is
    # true of every run, so it is appended every time the fingerprint renders (`disclosures` is
    # non-empty on every path from here on, so the DISCLOSURES section always shows it).
    disclosures.append(
        "gross, net, active_frac and hhi are all deterministic functions of the same weight vector "
        "and turnover is its first difference; only cap_breach probes a separate mechanism, so the "
        "metric count overstates the number of independent trials"
    )

    # Fix 3: `long_only` requires a NON-EMPTY book -- `all(...)` over an empty weights sequence is
    # vacuously True, which would wrongly fire the long-only wording on a book that never held any
    # position. The correlation check uses `abs(corr)`, since a strongly ANTI-correlated gross/net
    # is equally redundant (one is derivable from the other) as a positively-correlated pair; the
    # wording names whichever condition actually fired, since the correlation branch can trigger on
    # a book WITH shorts (long_only False) too.
    all_weights = [w for bar in realized.weights for w in bar.values()]
    long_only = bool(all_weights) and all(w >= -1e-12 for w in all_weights)
    near_redundant_corr = False
    if not long_only and len(rm["gross"]) >= 2:
        g_arr, n_arr = np.array(rm["gross"]), np.array(rm["net"])
        if g_arr.std() > 0 and n_arr.std() > 0:
            near_redundant_corr = abs(float(np.corrcoef(g_arr, n_arr)[0, 1])) >= 0.99
    if long_only:
        disclosures.append("gross and net are near-identical on a long-only book — the metric count overstates independent trials")
    elif near_redundant_corr:
        disclosures.append(
            "gross and net are near-identical (|correlation| >= 0.99) — the metric count overstates independent trials"
        )

    panel = summarize_panel(gating_verdicts, band=band, dual_verdicts=dual_verdicts)

    null_gov_rate = _mean(governor_engaged_daily(null.multipliers, null.day_index))
    null_cap_rate = null.cap_breach_bars / null.n_periods if null.n_periods > 0 else 0.0

    d4_gap_bps = _mean([g - n for g, n in zip(null.governed_net, null.net_live)]) * 1e4
    d4_active = any(m < 1.0 for m in null.multipliers)

    null_pnl = null.net_live[1:]
    pnl_window = L - 1
    pnl_eff_n = len(null_pnl) / pnl_window if pnl_window > 0 else 0.0
    pnl_mean = _mean(realized.net[1:])
    pnl_cum = math.prod(1.0 + x for x in realized.net) - 1.0
    pnl_verdict, pnl_dual = _judge_dual(
        pnl_mean, null_pnl, pnl_window, band=band, effective_n=pnl_eff_n, domain=None, null_mode=null_mode
    )
    effective_n["pnl"] = pnl_eff_n
    if pnl_dual is not None:
        dual_verdicts["pnl"] = pnl_dual
        if pnl_dual.disclosure:
            disclosures.append(f"pnl: {pnl_dual.disclosure}")

    return SoakAnalysis(
        L=L,
        gating_verdicts=gating_verdicts,
        panel=panel,
        null_gov_rate=null_gov_rate,
        null_cap_rate=null_cap_rate,
        d4_gap_bps=d4_gap_bps,
        d4_active=d4_active,
        pnl_mean=pnl_mean,
        pnl_cum=pnl_cum,
        pnl_verdict=pnl_verdict,
        is_degenerate=degenerate(rm["gross"]),
        effective_n=effective_n,
        internals_available=internals_available,
        internals_reason=internals_reason,
        disclosures=tuple(disclosures),
        dual_verdicts=dual_verdicts,
    )


BANNER = (
    "Trial 44 has ZERO out-of-time holdout evidence — the one budgeted holdout look (budget now 0) tested the "
    "SUPERSEDED record 33 in a degenerate [0,0] window and discriminated nothing; paper trading is its only "
    "genuine OOS test."
)

_HONESTY_FOOTER = (
    "A 'consistent' row only means the realized behaviour sits inside the backtest's own range; an overfit "
    "strategy lands in-band most of the time at L≈84, so this is not out-of-sample evidence.\n"
    "These are structural-conformance checks -- does the live book look like the backtest book -- not "
    "evidence of edge."
)

_FORBIDDEN = ("validated", "passed", "confirmed", "proven")


def _scrub(text: str) -> str:
    """Neutralize vocabulary-locked words in free-form text (exception messages) before it reaches
    the rendered report. The lock is a core honesty invariant, so it is enforced structurally here
    rather than relying on upstream messages happening to be clean."""
    for word in _FORBIDDEN:
        text = re.sub(word, "<redacted-term>", text, flags=re.IGNORECASE)
    return text


def _fmt_flag(value: bool | None) -> str:
    if value is None:
        return "skipped"
    return "ok" if value else "FAILED"


def render_report(
    analysis: SoakAnalysis | None,
    realized: RealizedSeries | None,
    null: NullSystem | None,
    self_test: SelfTestReport | None,
    *,
    void_reasons: list[str],
    band: float = 0.90,
    null_mode: str = "both",
    path: str = "fast",
) -> str:
    """Render a soak-check analysis to a text report. Section order: BANNER (verbatim, every run),
    the null-construction/builder-path line, provenance, self-tests, the NO-VERDICT gate (suppresses
    every downstream section -- the structural fingerprint table, disclosures, D4 gap, P&L -- the
    moment `void_reasons` is non-empty, so a short/untrustworthy run never prints a per-metric
    conclusion), then the 7-row fingerprint table + multiplicity line, DISCLOSURES (when
    `analysis.disclosures` is non-empty), the D4 gap, non-gating P&L, and an honesty footer. When
    `analysis.internals_available` is False, the governor_engagement/cap_breach rows render `n/a`
    across every column (D7 degrade, not void) and a line states `_scrub(analysis.internals_reason)`
    -- `internals_reason` carries `str(exc)` from an arbitrary `EngineError`/`PortfolioError`. TWO
    free-form paths reach this function's rendered text, and both are run through `_scrub`
    (structural vocabulary-lock enforcement) before interpolation: `internals_reason` above, and the
    NO-VERDICT line's joined `void_reasons` (which itself carries `str(exc)` from a `SoakError` when
    `soak_report`'s `realized_series` call raised one, e.g. `f"realized series: {exc}"`). Both stay
    UNSCRUBBED in the JSON payload's copies (JSON is not vocabulary-locked). Never `RealizedInternals`'
    `identity_detail`/`cap_detail`, which are diagnostic strings that may carry vocabulary-locked
    words and are never passed to this function. `analysis`/`null`/`self_test` are all `None` when
    the canonical dataset is absent (no null to judge against); `realized` is additionally `None`
    when the journal is empty or `realized_series` itself raised `SoakError` -- both render a
    banner-and-void-reasons-only report via this same function.

    `null_mode`/`path` (spec 00061 D4/D5) are the caller's own choice of construction(s) and builder
    path -- stated up front regardless of void status, since even a void/no-verdict run reflects a
    specific choice a re-run might want to reproduce. In `"both"` mode, the fingerprint table's
    `verdict` column shows the RECONCILED label (`analysis.dual_verdicts[m].verdict`, e.g.
    `"indeterminate (instrument-fragile)"` on a fragile metric) rather than the windowed null's raw
    verdict -- identical to the raw verdict whenever the two nulls agree (reconciliation is a no-op
    on agreement), diverging only on genuine disagreement. A new `secondary` column shows the
    bootstrap null's own verdict label; `"-"` when no reconciliation ran for that metric (single-null
    mode, or an internals-degraded governor_engagement/cap_breach). The multiplicity line is followed
    by `analysis.panel.indeterminate_line` when non-empty (D3).
    """
    lines: list[str] = [BANNER, "", f"null mode: {null_mode}  |  builder path: {path}", ""]

    # Section header avoids the word "provenance" -- it contains "proven" as a substring, which
    # would trip the vocabulary lock below.
    lines.append("REALIZED-SERIES WINDOW")
    if realized is not None and realized.cycle_ts:
        span_days = (realized.cycle_ts[-1] - realized.cycle_ts[0]).total_seconds() / 86400.0
        lines.append(f"  first cycle_ts : {realized.cycle_ts[0].isoformat()}")
        lines.append(f"  last  cycle_ts : {realized.cycle_ts[-1].isoformat()}")
        lines.append(f"  L (scored bars): {len(realized.net)}")
        lines.append(f"  span           : {span_days:.2f} days")
        lines.append(f"  dropped_tail   : {realized.dropped_tail}")
        lines.append(f"  chain_ok       : {realized.chain_ok}")
    else:
        lines.append("  no realized series available")
    lines.append("")

    lines.append("SELF-TESTS")
    if self_test is None:
        lines.append("  instrument_ok  : skipped")
        lines.append("  identity_ok    : skipped")
        lines.append("  reconcile_ok   : skipped")
    else:
        lines.append(f"  instrument_ok  : {_fmt_flag(self_test.instrument_ok)}")
        lines.append(f"  identity_ok    : {_fmt_flag(self_test.identity_ok)}")
        lines.append(f"  reconcile_ok   : {_fmt_flag(self_test.reconcile_ok)}")
        if self_test.void:
            lines.append("  self-tests VOID -- a ran-and-failed instrument/identity/reconcile check; see NO VERDICT below")
    lines.append("")

    if void_reasons:
        lines.append(f"NO VERDICT -- {_scrub('; '.join(void_reasons))}")
        if analysis is not None and analysis.is_degenerate:
            lines.append("INDETERMINATE -- DEGENERATE WINDOW")
        lines.append("")
        lines.append(_HONESTY_FOOTER)
        return "\n".join(lines)

    assert analysis is not None  # not void => Part B always built one alongside a present canonical

    lines.append(f"STRUCTURAL FINGERPRINT (live realized vs backtest null, band={band:.0%})")
    lines.append(
        f"  {'metric':<12}{'live':>10}{'median':>10}{'band [lo,hi]':>24}{'pctile':>9}{'eff-n':>9}{'width':>10}"
        f"{'verdict':>18}{'secondary':>16}"
    )
    for m in ("gross", "net", "active_frac", "turnover", "hhi", "governor_engagement", "cap_breach"):
        v = analysis.gating_verdicts[m]
        if m in ("governor_engagement", "cap_breach") and not analysis.internals_available:
            lines.append(f"  {m:<12}{'n/a':>10}{'n/a':>10}{'n/a':>24}{'n/a':>9}{'n/a':>9}{'n/a':>10}{'n/a':>18}{'n/a':>16}")
            continue
        band_str = f"[{v.lo:.4f},{v.hi:.4f}]"
        dual = analysis.dual_verdicts.get(m)
        effective_verdict = dual.verdict if dual is not None else v.verdict
        secondary_label = dual.secondary if dual is not None else "-"
        lines.append(
            f"  {m:<12}{v.live:>10.4f}{v.median:>10.4f}{band_str:>24}{v.percentile:>8.1f}%{v.effective_n:>9.2f}"
            f"{v.width:>10.4f}{effective_verdict:>18}{secondary_label:>16}"
        )
    lines.append(f"  {analysis.panel.line}")
    if analysis.panel.indeterminate_line:
        lines.append(f"  {analysis.panel.indeterminate_line}")
    if not analysis.internals_available:
        lines.append(f"  governor_engagement/cap_breach unavailable: {_scrub(analysis.internals_reason)}")
    lines.append("")

    if analysis.disclosures:
        lines.append("DISCLOSURES")
        for d in analysis.disclosures:
            lines.append(f"  {d}")
        lines.append("")

    lines.append("D4 GAP (governed vs live-cost null)")
    bias = "bias ACTIVE" if analysis.d4_active else "bias INACTIVE"
    lines.append(f"  d4_gap_bps: {analysis.d4_gap_bps:.4f} bps/cycle ({bias})")
    lines.append("  the null P&L uses the live cost convention, so the governor bias cancels by construction")
    lines.append("")

    lines.append("P&L (NON-GATING)")
    lines.append(f"  realized cumulative net : {analysis.pnl_cum:+.4%}")
    lines.append(f"  realized mean net/cycle : {analysis.pnl_mean:+.6f}")
    pnl_dual = analysis.dual_verdicts.get("pnl")
    pnl_effective_verdict = pnl_dual.verdict if pnl_dual is not None else analysis.pnl_verdict.verdict
    pnl_secondary_note = f" (secondary null: {pnl_dual.secondary})" if pnl_dual is not None else ""
    lines.append(f"  pnl verdict (non-gating, near-vacuous at this L): {pnl_effective_verdict}{pnl_secondary_note}")
    lines.append("")

    lines.append(_HONESTY_FOOTER)
    return "\n".join(lines)


_VERDICT_NUMERIC_FIELDS = ("live", "median", "lo", "hi", "percentile", "effective_n", "width")


def _verdict_payload(name: str, verdict: MetricVerdict, *, internals_available: bool, dual: DualVerdict | None = None) -> dict:
    """`asdict(verdict)`, except (Fix 4): a `governor_engagement`/`cap_breach` verdict whose
    `"n/a"` comes from an internals rebuild that never ran (`internals_available=False`) reports
    `None` (JSON `null`) for every numeric field, since `live=0.0` there is a placeholder, not a
    computed value -- a JSON consumer otherwise cannot tell "unavailable" from "genuinely 0.0".
    An `"n/a"` that instead arose from a computed-but-undiscriminating band (Fix 1's full-range
    domain check, or a zero-width band, or a tiny `effective_n`) keeps its real numbers -- those
    are meaningful (e.g. a full-[0,1]-range band still reports where `live` actually sat).

    `dual` (spec 00061) is the metric's `DualVerdict` reconciliation when one ran (`null_mode="both"`);
    added under a `"dual"` key, `None` when no reconciliation ran for this metric -- a stable key
    present in every payload shape so a consumer never has to branch on `null_mode` to find it."""
    d = asdict(verdict)
    if name in ("governor_engagement", "cap_breach") and not internals_available:
        for key in _VERDICT_NUMERIC_FIELDS:
            d[key] = None
    d["dual"] = asdict(dual) if dual is not None else None
    return d


def _json_payload(
    analysis: SoakAnalysis | None,
    realized: RealizedSeries | None,
    null: NullSystem | None,
    self_test: SelfTestReport | None,
    *,
    void_reasons: list[str],
    band: float,
    now: datetime,
    internals: RealizedInternals | None = None,
    null_mode: str = "both",
    path: str = "fast",
) -> dict:
    """Every number the report renders, as a `json.dumps`-able dict -- the machine-readable twin
    of `render_report`'s text, plus fields the (vocabulary-locked) text never carries: `internals`
    (raw `RealizedInternals` diagnostics -- `identity_detail`/`cap_detail` included, since the JSON
    is not vocabulary-locked) and `disclosures`. `null` is accepted (mirroring `render_report`'s
    signature) but carries nothing of its own in the payload; every null-derived number already
    lives in `analysis` (gating verdicts, context, D4, P&L). `internals` is `None` exactly when
    `analysis` is (the canonical was absent, so `soak_report` never built either). `null_mode`/`path`
    (spec 00061 D4/D5) mirror `render_report`'s own provenance line; each `gating_verdicts[m]` and
    `pnl.pnl_verdict` carry a `"dual"` sub-key with the metric's reconciliation (see `_verdict_payload`)."""
    del null
    payload: dict = {
        "generated_at": now.isoformat(),
        "band": band,
        "void_reasons": list(void_reasons),
        "null_mode": null_mode,
        "path": path,
    }

    payload["internals"] = (
        None
        if internals is None
        else {
            "available": internals.available,
            "reason": internals.reason,
            "identity_ok": internals.identity_ok,
            "identity_detail": internals.identity_detail,
            "cap_consistent": internals.cap_consistent,
            "cap_detail": internals.cap_detail,
            "n_scored_cycles": len(internals.mult_by_cycle),
        }
    )

    if realized is not None and realized.cycle_ts:
        payload["provenance"] = {
            "L": len(realized.net),
            "first_cycle_ts": realized.cycle_ts[0].isoformat(),
            "last_cycle_ts": realized.cycle_ts[-1].isoformat(),
            "span_days": (realized.cycle_ts[-1] - realized.cycle_ts[0]).total_seconds() / 86400.0,
            "dropped_tail": realized.dropped_tail,
            "chain_ok": realized.chain_ok,
        }
    else:
        payload["provenance"] = None

    payload["self_test"] = (
        None
        if self_test is None
        else {
            "instrument_ok": self_test.instrument_ok,
            "identity_ok": self_test.identity_ok,
            "reconcile_ok": self_test.reconcile_ok,
            "void": self_test.void,
            "messages": list(self_test.messages),
        }
    )

    if analysis is None:
        payload["gating_verdicts"] = None
        payload["panel"] = None
        payload["context"] = None
        payload["d4"] = None
        payload["pnl"] = None
        payload["is_degenerate"] = None
        payload["effective_n"] = None
        payload["disclosures"] = None
    else:
        payload["gating_verdicts"] = {
            m: _verdict_payload(m, v, internals_available=analysis.internals_available, dual=analysis.dual_verdicts.get(m))
            for m, v in analysis.gating_verdicts.items()
        }
        payload["panel"] = asdict(analysis.panel)
        payload["context"] = {
            "null_gov_rate": analysis.null_gov_rate,
            "null_cap_rate": analysis.null_cap_rate,
            "note": (
                "null_gov_rate/null_cap_rate are the null's GLOBAL rates (D9) -- do not use them as the "
                "comparison reference; the windowed null distribution behind gating_verdicts is the reference"
            ),
        }
        payload["d4"] = {"d4_gap_bps": analysis.d4_gap_bps, "d4_active": analysis.d4_active}
        payload["pnl"] = {
            "pnl_mean": analysis.pnl_mean,
            "pnl_cum": analysis.pnl_cum,
            "pnl_verdict": _verdict_payload(
                "pnl",
                analysis.pnl_verdict,
                internals_available=analysis.internals_available,
                dual=analysis.dual_verdicts.get("pnl"),
            ),
        }
        payload["is_degenerate"] = analysis.is_degenerate
        payload["effective_n"] = dict(analysis.effective_n)
        payload["disclosures"] = list(analysis.disclosures)

    return payload


def soak_report(
    *,
    journal_dir: Path,
    store_dir: Path,
    canonical_dir: Path,
    registry_path: Path,
    fee: float = 0.006,
    band: float = 0.90,
    floor: int = 30,
    null_mode: str = "both",
    path: str = "fast",
    now: datetime | None = None,
) -> tuple[str, dict]:
    """Orchestrate the full soak-check: load the journal, build the realized series, gate it
    (self-tests, plausibility, `L < floor`, degeneracy, and -- when the internals rebuild succeeded
    -- its own `identity_ok`/`cap_consistent` window-wide proofs) against a backtest null rebuilt
    from the frozen canonical dataset (skipped -- and gated void -- when the canonical is absent),
    and render both the text report and its JSON twin. The internals rebuild itself
    (`realized_internals`) is built from the scored cycles' own journal records and the newest
    record's snapshots, once per call; its `available=False` DEGRADES governor_engagement/cap_breach
    to "n/a" (D7) rather than voiding the run, but `available=True` with `identity_ok=False` or
    `cap_consistent=False` DOES void -- the instrument would be lying about alignment. Never raises
    on a short/void/absent-canonical run -- those are refusals, not failures; only an unreadable
    journal record or a genuine `EngineError` (including a `SoakError` from `realized_internals`,
    e.g. a missing T-4h stamp) propagates to the caller.

    `null_mode` (spec 00061 D4) threads to `analyze_soak`. `path` (D5) threads to `build_null` (the
    null build) and `self_tests` (the identity self-check) -- both are the caller's responsibility to
    validate against the accepted vocabulary (the CLI does so before calling in); an invalid value
    surfaces as a `SoakError` from whichever of those two first rejects it.
    """
    now = now or datetime.now(UTC)
    # Local import: cli.engine.command imports `soak_report` from this module, so a module-level
    # import here would form an import cycle -- deferred to call time, after both modules are fully
    # loaded.
    from cli.engine.command import _journal_artifacts, _snapshot_reader

    arts = _journal_artifacts(journal_dir, "*", "cycle-*.json")
    records = [from_json(p.read_text()) for _, p in arts]
    if not records:
        void_reasons = ["no journaled cycles found"]
        text = render_report(None, None, None, None, void_reasons=void_reasons, band=band, null_mode=null_mode, path=path)
        payload = _json_payload(
            None, None, None, None, void_reasons=void_reasons, band=band, now=now, null_mode=null_mode, path=path
        )
        return text, payload

    try:
        realized = realized_series(records, store_dir, fee=fee, now=now)
    except SoakError as exc:
        void_reasons = [f"realized series: {exc}"]
        text = render_report(None, None, None, None, void_reasons=void_reasons, band=band, null_mode=null_mode, path=path)
        payload = _json_payload(
            None, None, None, None, void_reasons=void_reasons, band=band, now=now, null_mode=null_mode, path=path
        )
        return text, payload

    void_reasons: list[str] = []
    if len(realized.net) < floor:
        void_reasons.append(f"L={len(realized.net)} < floor={floor}")

    if _canonical_present(canonical_dir):
        null = build_null(canonical_dir, fee=fee, path=path)
        reader = _snapshot_reader(journal_dir)

        by_ts = {r.cycle_ts: r for r in records}
        scored_records = [by_ts[t] for t in realized.cycle_ts]
        latest_record = max(records, key=lambda r: r.cycle_ts)
        internals = realized_internals(scored_records, latest_record, reader)

        self_test = self_tests(
            records,
            null,
            realized=realized,
            canonical_dir=canonical_dir,
            registry_path=registry_path,
            snapshot_reader=reader,
            path=path,
        )
        if self_test.void:
            if self_test.instrument_ok is False:
                void_reasons.append("self-test VOID: instrument_ok=False")
            if self_test.identity_ok is False:
                void_reasons.append("self-test VOID: identity_ok=False")
            if self_test.reconcile_ok is False:
                void_reasons.append("self-test VOID: reconcile_ok=False")
        void_reasons += plausibility_checks(realized, null)
        if internals.available and not internals.identity_ok:
            void_reasons.append("realized-internals identity mismatch")
        if internals.available and not internals.cap_consistent:
            void_reasons.append("cap-breach inconsistent")
        analysis = analyze_soak(realized, null, band=band, internals=internals, null_mode=null_mode)
        if analysis.is_degenerate:
            void_reasons.append("degenerate window")
    else:
        null = None
        analysis = None
        self_test = None
        internals = None
        void_reasons.append("canonical absent — null unavailable")

    text = render_report(analysis, realized, null, self_test, void_reasons=void_reasons, band=band, null_mode=null_mode, path=path)
    payload = _json_payload(
        analysis,
        realized,
        null,
        self_test,
        void_reasons=void_reasons,
        band=band,
        now=now,
        internals=internals,
        null_mode=null_mode,
        path=path,
    )
    return text, payload
