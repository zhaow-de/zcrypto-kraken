"""The soak check: the realized forward-return series recovered from the engine's journal, the backtest
null it is judged against, and the per-metric verdicts and report they produce."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from cli.engine.concordance import HashMismatchError, replay_cycle
from cli.engine.cycle import _MODEL_SYMBOLS, _expand_to_basket, select_model_inputs, symbol_keyed_targets
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json, snapshot_content_hash, validate_record
from cli.engine.store import BASKET, GRID_INTERVALS, read_store_series
from cli.portfolio import CrossfreqSystemConfig, PortfolioError, build_crossfreq_system, build_crossfreq_system_fast
from cli.portfolio.crossfreq_system import apply_whole_book_limits
from cli.risk.limits import apply_position_caps


def structural_metrics(
    weights_by_bar: list[dict[str, float]],
    *,
    long_cap: float = 0.20,
    short_cap: float = 0.10,
) -> dict[str, list[float]]:
    """Per-bar gross, net, active_frac, turnover, hhi and cap_breach over a series of asset->weight
    dicts, each bar keyed by the same asset set."""
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

        # Round only the REPORTED gross: summing abs(weight) is order-independent in value but not always
        # exactly representable, and hhi's division above needs the unrounded bar_gross.
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
    """Roll a per-bar governor multiplier series up to one flag per distinct `day_index` day, in
    first-appearance order: 1.0 if any of that day's bars has mult < 1.0, else 0.0."""
    engaged_by_day: dict[int, bool] = {}
    for m, day in zip(mult, day_index):
        engaged = engaged_by_day.get(day, False) or m < 1.0
        engaged_by_day[day] = engaged

    return [1.0 if engaged else 0.0 for engaged in engaged_by_day.values()]


class SoakError(EngineError):
    """Raised when a soak-check input or an internal contract is structurally inconsistent."""


@dataclass(frozen=True)
class RealizedSeries:
    """The realized forward-return observation over a clean run of journal cycles: each scored cycle's decided weights
    and the forward 4h return they earned, joined to the price store BY TIMESTAMP. The last four fields say what ENDED
    the window, which `dropped_tail` alone never says: `window_bound` is `"journal"` (the clean segment's own end),
    `"store"` (the store ran out first) or `"clock"` (the trailing cycles' successors postdate `now`)."""

    cycle_ts: list[datetime]
    weights: list[dict[str, float]]
    gross: list[float]
    turnover: list[float]
    net: list[float]
    dropped_tail: int
    assets: tuple[str, ...]
    chain_ok: bool
    implausible: bool
    window_bound: str
    store_last_ts: datetime | None
    journal_last_cycle_ts: datetime | None
    store_bound_cycles: int


def select_clean_segment(records: list[CycleRecord]) -> list[CycleRecord]:
    """Sort `records` by cycle_ts and return the longest run of consecutive records 4h apart, each on a 4h
    grid boundary; ties keep the FIRST longest run. Success/failure filtering is the caller's job -- this
    only handles boundary contiguity."""
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
    """True iff consecutive SCORED cycles chain: each asset's exit price at T_i is the same store entry as
    its entry price at T_next (closes[a][T_i] == closes[a][T_next - 4h]), which holds trivially while the
    scored sequence is 4h-contiguous and breaks on a gap in it."""
    for i in range(len(scored_ts) - 1):
        t_i = scored_ts[i]
        start_of_next = scored_ts[i + 1] - timedelta(hours=4)
        for closes in closes_by_asset.values():
            if closes[t_i] != closes[start_of_next]:
                return False
    return True


def _store_last_usable(closes_by_asset: dict[str, dict[datetime, float]]) -> datetime | None:
    """The newest store stamp at which EVERY asset has a finite close, `None` when there is none --
    intersected across assets, since one asset's series ending early bounds the window just as hard as all
    of them ending early."""
    common: set[datetime] | None = None
    for closes in closes_by_asset.values():
        usable = {ts for ts, v in closes.items() if v is not None and math.isfinite(v)}
        common = usable if common is None else common & usable
    return max(common) if common else None


def realized_series(
    records: list[CycleRecord],
    store_dir: Path,
    *,
    fee: float = 0.006,
    now: datetime,
) -> RealizedSeries:
    """The realized forward-4h-return series over a run of journal cycles: cycle T's `final_targets` are held
    over [T, T+4h) and scored on the store's closes[T-4h] (entry) and closes[T] (exit), joined BY TIMESTAMP.
    The last clean-segment cycle never scores; a cycle whose successor postdates `now`, or whose closes are
    not all present and finite at both stamps, is skipped too and counted in `dropped_tail`."""
    clean = select_clean_segment(records)
    if not clean:
        raise SoakError("no contiguous clean cycle segment in the journal")
    # Targets are read in the CURRENT symbol key space, as the cycle's own previous-targets read is: the
    # store is keyed `<base>/<quote>`, so a schema-1 record's bare "BTC" resolves to no path.
    targets = {rec.cycle_ts: symbol_keyed_targets(rec) for rec in clean}
    assets = tuple(sorted(set().union(*targets.values())))
    for rec in clean:
        missing = set(assets) - set(targets[rec.cycle_ts])
        if rec.schema_version == 1:
            # A v1 record is base-keyed and STRUCTURALLY cannot carry a `/BTC` leg -- the schema boundary the
            # window may straddle (spec 00094 D3), filled 0.0 below, which is the position the engine actually
            # held. Any OTHER absence is a genuinely inconsistent segment.
            missing = {a for a in missing if a.endswith("/EUR")}
        if missing:
            raise SoakError(f"cycle {rec.cycle_ts!r} final_targets asset set {sorted(targets[rec.cycle_ts])} != {list(assets)}")

    closes: dict[str, dict[datetime, float]] = {a: dict(zip(*read_store_series(store_dir, a, 240))) for a in assets}

    cycle_ts: list[datetime] = []
    weights: list[dict[str, float]] = []
    gross: list[float] = []
    turnover: list[float] = []
    net: list[float] = []
    implausible = False
    prev_weights: dict[str, float] = dict.fromkeys(assets, 0.0)
    # Why each candidate cycle was skipped, recorded at the gate that fired rather than re-derived
    # afterwards, and read after the loop to decide what bounded the window.
    skipped_because: dict[datetime, str] = {}

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
            skipped_because[t] = "clock"
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
            skipped_because[t] = "store"
            continue

        r_fwd = {a: closes[a][end_ts] / closes[a][start_ts] - 1.0 for a in assets}
        if any(abs(v) > 0.5 for v in r_fwd.values()):
            implausible = True

        # Materialized over the whole window's asset union, so every bar's weight dict has the same
        # keys whichever schema wrote it -- `structural_metrics`' active_frac divides by len(bar).
        q = {a: targets[t].get(a, 0.0) for a in assets}
        bar_gross = sum(q[a] * r_fwd[a] for a in assets)
        bar_turnover = sum(abs(q[a] - prev_weights[a]) for a in assets)

        cycle_ts.append(t)
        weights.append(dict(q))
        gross.append(bar_gross)
        turnover.append(bar_turnover)
        net.append(bar_gross - fee * bar_turnover)
        prev_weights = dict(q)

    # What bounded the window: only candidates AFTER the last scored cycle can have -- "store" if any was
    # skipped for absent/non-finite closes, else "clock" if any successor postdated `now`, else "journal", the
    # clean segment's own end. An interior drop inflates dropped_tail but leaves the window's END where the journal put it.
    trailing = [rec.cycle_ts for rec in clean[:-1] if not cycle_ts or rec.cycle_ts > cycle_ts[-1]]
    store_bound_cycles = sum(1 for t in trailing if skipped_because.get(t) == "store")
    if store_bound_cycles:
        window_bound = "store"
    elif any(skipped_because.get(t) == "clock" for t in trailing):
        window_bound = "clock"
    else:
        window_bound = "journal"

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
        window_bound=window_bound,
        store_last_ts=_store_last_usable(closes),
        journal_last_cycle_ts=clean[-1].cycle_ts,
        store_bound_cycles=store_bound_cycles,
    )


def _net_live_from_result(result, *, fee_builder: float, fee: float) -> tuple[list[float], bool, list[float]]:
    """Recompute a result's net P&L under the LIVE cost convention -- cost on `final_targets = mult x limited`
    turnover, not on the limited book's own -- so the governor's turnover bias cancels in the realized-vs-null
    comparison. `combined` is rebuilt from `result.sleeve_positions` in the builder's own `third = 1 / 3` form
    and `capped` from it (dividing `final_targets` by a disengaged 0.0 multiplier is undefined), so the returned
    `cap_breach` cannot disagree with `cap_breach_bars` on a rounding bit; like that count, it stops at the
    PER-ASSET caps. `limited` is that book through `apply_whole_book_limits`, the book the builder itself costs
    and multiplies -- stopping at the caps diverges the moment a whole-book limit binds."""
    n = result.n_periods
    assets = tuple(result.final_targets)
    sleeves = result.sleeve_positions
    third = 1 / 3
    combined = {
        a: [third * sleeves["B"][a][k] + third * sleeves["A1"][a][k] + third * sleeves["A2"][a][k] for k in range(n + 1)]
        for a in assets
    }
    capped = apply_position_caps(combined)
    limited = apply_whole_book_limits(capped)
    mult = result.multipliers
    final_targets = result.final_targets

    reconcile_ok = all(abs(mult[k] * limited[a][k] - final_targets[a][k]) <= 1e-9 for a in assets for k in range(n + 1))

    net_live: list[float] = []
    for k in range(n):
        turn_limited = sum(abs(limited[a][k] - (limited[a][k - 1] if k > 0 else 0.0)) for a in assets)
        turn_final = sum(abs(final_targets[a][k] - (final_targets[a][k - 1] if k > 0 else 0.0)) for a in assets)
        net_live.append(result.governed_net[k] + mult[k] * fee_builder * turn_limited - fee * turn_final)

    cap_breach = [1.0 if any(abs(capped[a][k] - combined[a][k]) > 1e-15 for a in assets) else 0.0 for k in range(n)]

    return net_live, reconcile_ok, cap_breach


@dataclass(frozen=True)
class NullSystem:
    """The backtest reference the realized series is judged against: the same strategy rebuilt over the full
    frozen canonical history, its P&L recast onto the live cost convention."""

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
    """True iff the frozen canonical dataset looks present at `canonical_dir`, probed by BTC's 240 store file
    alone."""
    return (canonical_dir / "BTC" / "EUR" / "240.parquet").exists()


def _load_canonical(
    canonical_dir: Path,
) -> tuple[dict[str, list[float | None]], list[datetime], dict[str, list[float | None]], list[datetime]]:
    """The canonical's daily and 4h MODEL panels -- `select_model_inputs`' ten base-keyed `/EUR` legs on their own calendar
    (spec 00094 D2), the grid the live engine itself builds on -- read here so `build_null` and `instrument_self_check`
    cannot drift apart. Only the ten are READ: `_canonical_present` probes `BTC/EUR` alone, so reading the `/BTC` legs
    would abort a ten-leg canonical tree on a FileNotFoundError, which no handler degrades into a refusal."""
    raw = {(a, iv): read_store_series(canonical_dir, a, iv) for a in _MODEL_SYMBOLS for iv in GRID_INTERVALS}
    daily_ts, daily_prices = select_model_inputs({a: raw[(a, 1440)] for a in _MODEL_SYMBOLS})
    h4_ts, h4_prices = select_model_inputs({a: raw[(a, 240)] for a in _MODEL_SYMBOLS})
    return daily_prices, daily_ts, h4_prices, h4_ts


def build_null(
    canonical_dir: Path, config: CrossfreqSystemConfig = CrossfreqSystemConfig(), *, fee: float = 0.006, path: str = "fast"
) -> NullSystem:
    """Load the frozen canonical, rebuild the SAME strategy, and derive the live-cost-convention null the
    realized series is judged against. `path` (spec 00061 D5) selects the builder, "fast" or the "verified"
    daily oracle spot replay -- the same choice `concordance.replay_cycle` offers."""
    daily_prices, daily_ts, h4_prices, h4_ts = _load_canonical(canonical_dir)
    if path == "fast":
        result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    elif path == "verified":
        result = build_crossfreq_system(daily_prices, daily_ts, h4_prices, h4_ts, config=config)
    else:
        raise SoakError(f"path must be 'fast' or 'verified', got {path!r}")

    net_live, reconcile_ok, cap_breach = _net_live_from_result(result, fee_builder=config.cost_per_side, fee=fee)
    n = result.n_periods
    # The null's book is cast onto the LIVE key space (spec 00094 D1) by `_expand_to_basket`, the two `/BTC`
    # legs at exactly 0.0: zero legs leave gross/net/turnover/hhi untouched, but active_frac is
    # n_active/len(weights), so a ten-wide null against a twelve-wide realized series would bias every
    # active_frac comparison by the ratio of the two universes.
    weights = [_expand_to_basket({a: series[k] for a, series in result.final_targets.items()}) for k in range(n)]
    assets = tuple(BASKET)

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
    """Every overlapping length-`window` statistic over `series` under `reducer`; [] when `window` is <= 0 or
    longer than `series`."""
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
    """Stationary (Politis-Romano) block bootstrap: `n` resampled length-`window` paths of geometrically
    distributed blocks (mean `mean_block`) at random offsets into `series`, wrapped circularly so every offset
    stays equally likely, each reduced by `reducer` and deterministic given `seed`. The secondary null, since
    `windowed_null`'s overlapping windows share observations and understate the sampling variance."""
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
    """One live metric value judged against its null distribution: the band zone `live` fell in (see
    `metric_verdict`), the null's own summary, and `live`'s percentile rank within it."""

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
    """Judge `live` against `null_values` on a two-sided band: the outer `band` interval bounds "inconsistent"
    on EITHER side -- too-low is a bug tell too -- the inner half-width interval bounds "consistent", and the
    two edges between them "weakly-consistent". A band that cannot discriminate is "n/a" wherever `live` falls:
    zero width, `effective_n < 3`, under two null values, or covering the whole of `domain` when one is given."""
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


def _full_range_disclosure(
    name: str, verdict: MetricVerdict, domain: tuple[float, float] | None, *, effective_verdict: str | None = None
) -> str | None:
    """The disclosure naming a band that spans the FULL `domain`, or `None`: `width > 0` and `effective_n >= 3`
    isolate this "n/a" from `metric_verdict`'s other two triggers, and `effective_verdict` -- the label actually
    rendered, which under a reconciliation (spec 00061 D1) can discriminate where the raw windowed verdict did
    not -- must be "n/a" too, or the line would contradict the verdict printed beside it."""
    if effective_verdict is None:
        effective_verdict = verdict.verdict
    if domain is None or verdict.verdict != "n/a" or verdict.width <= 0.0 or verdict.effective_n < 3 or effective_verdict != "n/a":
        return None
    return (
        f"{name}: the null band spans the full [{domain[0]:g},{domain[1]:g}] range at this window "
        "length -- the test has no discriminating power here"
    )


def degenerate(live_gross_series: list[float], *, floor: float = 1e-6) -> bool:
    """True if the window carries near-zero exposure (mean |gross| < floor) -- a run that never put on a
    position cannot be judged against a null built from an active strategy."""
    if not live_gross_series:
        return True
    return (sum(abs(v) for v in live_gross_series) / len(live_gross_series)) < floor


@dataclass(frozen=True)
class PanelSummary:
    """The panel's multiplicity-aware summary: how many judged metrics landed "inconsistent" against how many
    the band puts outside by chance alone, plus how many reconciled to "indeterminate (instrument-fragile)"
    (spec 00061 D3)."""

    n_metrics: int
    n_outside: int  # count of "inconsistent"
    n_indeterminate: int  # count reconciled to "indeterminate (instrument-fragile)" (D3)
    expected_by_chance: float  # n_metrics * (1 - band)
    line: str  # e.g. "1 of 7 outside band (~0.7 expected by chance at 90%)"
    indeterminate_line: str  # e.g. "1 of 7 indeterminate -- ..."; "" when n_indeterminate == 0


def summarize_panel(
    verdicts: dict[str, MetricVerdict], *, band: float = 0.90, dual_verdicts: dict[str, DualVerdict] | None = None
) -> PanelSummary:
    """Roll per-metric verdicts into a multiplicity-aware summary: judging N discriminating metrics at `band`
    puts ~N*(1-band) outside it by chance alone, so the line reports the observed count against that
    expectation rather than alarming on the worst of N. `n_metrics` counts only discriminating verdicts (spec
    00059 D6) -- an "n/a" can contribute no false positive -- and both counts read the RECONCILED label
    `render_report` renders, never the raw windowed one, which would let table and summary disagree. A metric
    reconciled to "indeterminate (instrument-fragile)" counts toward `n_metrics` -- both nulls discriminated,
    they disagreed -- never toward `n_outside`."""
    dual_verdicts = dual_verdicts or {}
    effective = {m: (dual_verdicts[m].verdict if dual_verdicts.get(m) is not None else v.verdict) for m, v in verdicts.items()}
    discriminating = {m: eff for m, eff in effective.items() if eff != "n/a"}
    n_metrics = len(discriminating)
    n_indeterminate = sum(1 for eff in discriminating.values() if eff == "indeterminate (instrument-fragile)")
    n_outside = sum(1 for eff in discriminating.values() if eff == "inconsistent")
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
# `metric_verdict`'s closed vocabulary. `_SEVERITY` orders only the three comparable labels -- "n/a" is valid
# but sits outside that order, so membership and severity are separate questions.
_VERDICT_LABELS = frozenset(_SEVERITY) | {"n/a"}


@dataclass(frozen=True)
class DualVerdict:
    """A metric's two null verdicts reconciled (spec 00061 D1): `primary` from the windowed null, `secondary`
    from the block-bootstrap null, `verdict` the label `reconcile_verdicts` settled on, and `disclosure` empty
    exactly when the two agree."""

    verdict: str  # reconciled label, or "indeterminate (instrument-fragile)"
    primary: str  # the windowed null's label
    secondary: str  # the bootstrap null's label
    disclosure: str  # "" when the two agree


def reconcile_verdicts(primary: str, secondary: str) -> DualVerdict:
    """Reconcile two per-metric null verdicts (spec 00061 D1) -- pure: two labels in, a `DualVerdict` out. An
    adjacent disagreement reports the MILDER label, the reading less likely to claim a divergence; opposite
    extremes claim neither. Vocabulary validity is an UNCONDITIONAL PRECONDITION, checked before every early
    return, because a label's validity and its position on the severity order are separate questions;
    `metric_verdict`'s vocabulary being closed, an unrecognized label is an internal contract violation, and
    the `SoakError` raised for it aborts rather than letting a code defect render as a data finding."""
    if primary not in _VERDICT_LABELS or secondary not in _VERDICT_LABELS:
        raise SoakError(
            f"reconcile_verdicts: unrecognized verdict label (primary={primary!r}, secondary={secondary!r}) -- "
            "metric_verdict's vocabulary is closed to 'consistent'/'weakly-consistent'/'inconsistent'/'n/a'; "
            "an unrecognized label is an internal contract violation, not a real-world disagreement"
        )

    if primary == secondary:
        return DualVerdict(verdict=primary, primary=primary, secondary=secondary, disclosure="")

    if primary == "n/a" or secondary == "n/a":
        discriminating = secondary if primary == "n/a" else primary
        disclosure = (
            f"only one null construction discriminated here (primary={primary!r}, secondary={secondary!r}) -- "
            "the other's band had no power"
        )
        return DualVerdict(verdict=discriminating, primary=primary, secondary=secondary, disclosure=disclosure)

    gap = abs(_SEVERITY[primary] - _SEVERITY[secondary])
    if gap == 1:
        milder = primary if _SEVERITY[primary] < _SEVERITY[secondary] else secondary
        disclosure = f"the two null constructions disagree: primary={primary!r}, secondary={secondary!r} -- reporting the milder"
        return DualVerdict(verdict=milder, primary=primary, secondary=secondary, disclosure=disclosure)

    disclosure = f"the two null constructions give opposite verdicts: primary={primary!r}, secondary={secondary!r}"
    return DualVerdict(verdict="indeterminate (instrument-fragile)", primary=primary, secondary=secondary, disclosure=disclosure)


@dataclass(frozen=True)
class SelfTestReport:
    """The instrument's own proof, read before any verdict: `instrument_ok` reproduces a known registry result,
    `identity_ok` replays a journaled cycle's positions, `reconcile_ok` covers the null's and the realized
    series' internal bookkeeping, and `messages` carries the plausibility scan. `void` REFUSES the run on a
    self-test that RAN and FAILED -- `None` (skipped) never voids by itself."""

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
    """`governor_engaged_bars`/`cap_breach_bars` from record 47's metrics -- the ratified deployable-system
    trial (`docs/reference/trial-registry.jsonl`) the frozen engine build must reproduce exactly."""
    metrics = _load_registry_record(registry_path, 47)["metrics"]
    return {
        "governor_engaged_bars": int(metrics["governor_engaged_bars"]),
        "cap_breach_bars": int(metrics["cap_breach_bars"]),
    }


def instrument_self_check(
    canonical_dir: Path, registry_path: Path, config: CrossfreqSystemConfig = CrossfreqSystemConfig()
) -> tuple[bool | None, str]:
    """Rebuild the frozen strategy over the full canonical history (`_load_canonical`, as `build_null` does)
    and assert its `governor_engaged_bars`/`cap_breach_bars` EXACTLY match record 47's registry values.
    Returns (None, 'canonical absent') without building anything where the canonical has no data -- a skip,
    not a failure."""
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
    return True, "instrument reproduces record 47"


def identity_self_check(record, snapshot_reader, *, tol: float = 1e-6, path: str = "fast") -> tuple[bool, str]:
    """Recompute `record`'s newest-row targets via `replay_cycle` and compare them against
    `record.final_targets`, per asset, within `tol`; `path` (spec 00061 D5) selects the builder. A replay
    failure is deliberately NOT caught -- `self_tests` turns it into identity_ok=None, distinct from this
    function's own only failure, a genuine value mismatch."""
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
    """Each SCORED cycle's governor multiplier and cap-breach flag, rebuilt by `realized_internals` because the journal
    carries only `final_targets`, not the pre-cap position or the multiplier those two gating metrics need.
    `available=False` DEGRADES the run rather than voiding it -- the caller decides what that means; `identity_ok` is spec
    00059 D2's window-wide proof that each resolved row is that cycle's own, `cap_consistent` D3's builder cross-check."""

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
    """Assemble `record`'s own snapshots into the MODEL's daily and 4h grids -- a parallel implementation of
    `concordance.replay_cycle`'s assembly, not a shared import. A schema-1 record's journaled pairs already ARE
    the ten base keys; a schema-2 record's twelve are contracted by `select_model_inputs`, the cycle's own
    contraction, so the rebuild lands on the grid the cycle built on rather than on a PortfolioError."""
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
    if record.schema_version != 1:
        daily_ts, daily_prices = select_model_inputs(by_grid["1440"])
        h4_ts, h4_prices = select_model_inputs(by_grid["240"])
    return daily_ts, daily_prices, h4_ts, h4_prices


def realized_internals(
    scored_records: list[CycleRecord],
    latest_record: CycleRecord,
    snapshot_reader,
    *,
    tol: float = 1e-6,
) -> RealizedInternals:
    """Recover each SCORED cycle's governor multiplier and cap-breach flag from ONE rebuild over `latest_record`'s own
    snapshots, whose 240 history reaches every earlier scored cycle's decision row. That row is the index k where
    h4_ts[k] == T - 4h, from a `{ts: index}` dict and NEVER by offset arithmetic; a missing stamp or an asset
    outside the rebuilt universe raises `SoakError` as a genuine inconsistency, while a validate/assemble/build
    failing on `EngineError`/`PortfolioError` returns `available=False` and leaves the void decision to the caller.
    `identity_ok` is spec 00059 D2's window-wide check that the rebuilt row equals the journaled `final_targets` to
    `tol`. Breach is read from the pre-cap sleeves -- `final_targets = mult * limited` is in-cap by construction
    and could never show one -- and stops at the per-asset caps, mirroring the builder's own `cap_breach_bars`."""
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
        # Row k in the scored record's OWN key space (spec 00094 D3), exactly as the gate compares: a schema-1
        # record against the base-keyed model row it was written from, a schema-2 record against that row
        # expanded onto the twelve-symbol basket.
        row = {a: series[k] for a, series in result.final_targets.items()}
        if rec.schema_version != 1:
            row = _expand_to_basket(row)
        for a, value in rec.final_targets.items():
            if a not in row:
                raise SoakError(f"cycle {t!r}: asset {a!r} not in the rebuilt universe {sorted(row)}")
            diff = abs(row[a] - value)
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
    """One message per out-of-bounds diagnostic over `realized`/`null`, empty when everything is in bounds --
    a book beyond 200% gross is instrument breakage, not strategy."""
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
    """Run the instrument, identity and reconcile self-tests plus the plausibility scan into a `SelfTestReport`.
    Identity replays the NEWEST record, the journaled cycle closest to the live edge; no records at all, or a
    replay raising `EngineError`, skips it (`identity_ok=None`) rather than failing it. `path` (spec 00061 D5)
    reaches `identity_self_check` only -- `instrument_self_check` always reproduces record 47 via the fast path."""
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
    """The soak analysis: one verdict per GATING metric -- the five read from the journaled weights plus
    governor_engagement/cap_breach, which degrade to "n/a" with `internals_reason` when the internals rebuild is
    unavailable (spec 00059 D7) -- the panel summary over the discriminating subset (spec 00059 D6), the
    spec 00058 D4 governed-vs-live gap, the NON-GATING P&L verdict, and `disclosures`, which change no verdict."""

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

# `_json_payload`'s context.note names which null construction(s) actually produced `gating_verdicts` under each
# `null_mode` -- naming one that never ran would be the JSON disagreeing with what was computed.
_CONTEXT_NOTE_REFERENCE_BY_MODE = {
    "windows": "the windowed null distribution behind gating_verdicts is the reference",
    "block-bootstrap": "the block-bootstrap null distribution behind gating_verdicts is the reference",
    "both": (
        "the windowed null distribution behind gating_verdicts supplies the numbers; the "
        "block-bootstrap null's own verdict is reconciled into each metric's 'dual' key"
    ),
}


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
    """Judge `live` against `null_series` under `null_mode` (spec 00061 D4), one call per gating call site in
    `analyze_soak`: a single-null mode judges against that null alone and reconciles nothing; `"both"` computes
    both and returns the WINDOWED `MetricVerdict` (D2: the reported stats stay the windowed null's) beside the
    reconciliation. A non-positive `window` or an empty `null_series` skips the bootstrap -- which has no guard
    of its own and would raise -- and judges an empty null, "n/a", as `soak_report` never raises on a short run."""
    if null_mode == "windows":
        return metric_verdict(live, windowed_null(null_series, window), band=band, effective_n=effective_n, domain=domain), None
    if null_mode == "block-bootstrap":
        bootstrap_values = block_bootstrap_null(null_series, window) if window > 0 and null_series else []
        return metric_verdict(live, bootstrap_values, band=band, effective_n=effective_n, domain=domain), None

    windowed_v = metric_verdict(live, windowed_null(null_series, window), band=band, effective_n=effective_n, domain=domain)
    bootstrap_values = block_bootstrap_null(null_series, window) if window > 0 and null_series else []
    # `effective_n` is computed ONCE by the caller and passed unchanged into BOTH calls, never recomputed
    # per-null: `block_bootstrap_null` wraps circularly, so with window > len(null_series) it fabricates a
    # full-size distribution where `windowed_null` returns [] -- sharing the windowed null's tiny effective_n
    # is what makes `metric_verdict`'s `effective_n < 3` guard fire for the bootstrap verdict too.
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
    """Judge the realized series against its backtest null and roll the result into a `SoakAnalysis`. Gates on the
    structural metrics gross/net/active_frac/turnover/hhi from the journaled weights, plus governor_engagement
    (judged at DAY granularity, window = the realized day count) and cap_breach (at BAR granularity, window = L)
    from `internals`, which degrade to "n/a" with `internals_reason` when the rebuild is unavailable (spec 00059 D7) -- a
    missing rebuild degrades the fingerprint, it does not invalidate it. Turnover and P&L are prev-dependent, so
    both aggregate INTERIOR bars (each series' first element dropped) on the live and null sides alike, while the
    other metrics use all L bars. `null_mode` (spec 00061 D4) picks the null construction(s) for all four judging
    call sites; under `"both"` each metric's reconciliation lands in `dual_verdicts`, its disclosure in
    `disclosures`."""
    if null_mode not in _NULL_MODES:
        raise SoakError(f"null_mode must be one of {_NULL_MODES}, got {null_mode!r}")

    L = len(realized.net)
    rm = structural_metrics(realized.weights)
    nm = structural_metrics(null.weights)

    # RATE metrics are bounded to [0, 1], so an outer band spanning that whole range discriminates nothing.
    # gross/net/turnover are unbounded above and hhi's positive lower bound puts a full-[0,1] band out of
    # reach, so none of them needs a domain.
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

    active_frac_dual = dual_verdicts.get("active_frac")
    note = _full_range_disclosure(
        "active_frac",
        gating_verdicts["active_frac"],
        rate_domain,
        effective_verdict=active_frac_dual.verdict if active_frac_dual is not None else None,
    )
    if note is not None:
        disclosures.append(note)

    # If the internals rebuild's key set ever diverges from `realized.cycle_ts`, treat the internals as
    # unavailable rather than indexing blind: a bare KeyError here would crash the whole run, the opposite of
    # the degrade-don't-void contract `realized_internals` upholds.
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
            m_dual = dual_verdicts.get(m)
            note = _full_range_disclosure(
                m, gating_verdicts[m], rate_domain, effective_verdict=m_dual.verdict if m_dual is not None else None
            )
            if note is not None:
                disclosures.append(note)

        # A constant realized multiplier/cap-breach series is a legitimate verdict, never suppressed
        # to "n/a" -- disclosed so a reader can weigh it.
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

    # Unconditional: gross/net/active_frac/hhi are deterministic functions of the SAME weight vector and
    # turnover is that vector's first difference, so only cap_breach probes a separate mechanism. True of every
    # run, so `disclosures` is non-empty from here on and the DISCLOSURES section always renders.
    disclosures.append(
        "gross, net, active_frac and hhi are all deterministic functions of the same weight vector "
        "and turnover is its first difference; only cap_breach probes a separate mechanism, so the "
        "metric count overstates the number of independent trials"
    )

    # (spec 00059 D6a) `long_only` requires a NON-EMPTY book -- `all(...)` over an empty sequence is vacuously True
    # and would fire the long-only wording on a book that never held a position. The correlation check uses
    # `abs(corr)`, a strongly ANTI-correlated gross/net being just as redundant, and can fire on a book WITH shorts,
    # so the wording names whichever condition actually fired.
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
    "Trial 47 has ZERO out-of-time holdout evidence — the one budgeted holdout look (budget now 0) tested the "
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

# The three free-text columns are sized to the LONGEST label each can carry: a right-justified field gets its
# gap only from its OWN leading padding, so a label reaching its column's width abuts its neighbour with no
# separator at all.
_VERDICT_COL_W = len("indeterminate (instrument-fragile)")  # 34; the reconciled column's longest label
# `primary`/`secondary` each hold a RAW single-null label (never the reconciled
# "indeterminate (instrument-fragile)"), so both share this one width -- the longest of the four.
_RAW_VERDICT_COL_W = len("weakly-consistent")  # 17
# The fingerprint table's rows, and its name column sized to the longest of them rather than a hardcoded width:
# adding a metric widens the column instead of shifting that row's numbers out of alignment.
_METRIC_ROWS = ("gross", "net", "active_frac", "turnover", "hhi", "governor_engagement", "cap_breach")
_METRIC_COL_W = max(len(m) for m in _METRIC_ROWS)


def _scrub(text: str) -> str:
    """Neutralize vocabulary-locked words in free-form text before it reaches the rendered report -- a core
    honesty invariant, enforced structurally here rather than trusted to upstream messages."""
    for word in _FORBIDDEN:
        text = re.sub(word, "<redacted-term>", text, flags=re.IGNORECASE)
    return text


def _fmt_flag(value: bool | None) -> str:
    if value is None:
        return "skipped"
    return "ok" if value else "FAILED"


def _fmt_ts(value: datetime | None) -> str:
    return "none" if value is None else value.isoformat()


def _render_lines(lines: list[str]) -> str:
    """Join `lines` and strip EACH rendered line's trailing whitespace: the fingerprint table's last column is
    left-justified, so every row and the header carry trailing padding. Splits on "\\n" because some entries are
    themselves multi-line; internal alignment spacing is untouched."""
    return "\n".join(line.rstrip() for line in "\n".join(lines).split("\n"))


def _dual_columns(v: MetricVerdict, dual: DualVerdict | None, null_mode: str) -> tuple[str, str, str]:
    """The `(verdict, primary, secondary)` columns for one `render_report` row: `verdict` is the RECONCILED label
    `summarize_panel` and the JSON payload count, `primary`/`secondary` the raw labels the windowed and bootstrap nulls
    produced -- rendering the reconciled label beside only one raw one lets a disagreeing row read as an agreeing one.
    Under a single-null mode the construction that never ran renders `"-"` (not computed), never `"n/a"` (undiscriminating)."""
    if dual is not None:
        return dual.verdict, dual.primary, dual.secondary
    if null_mode == "block-bootstrap":
        return v.verdict, "-", v.verdict
    return v.verdict, v.verdict, "-"  # "windows"


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
    """Render a soak-check analysis to a text report. `analysis`/`null`/`self_test` are `None` when the canonical
    is absent, `realized` too when the journal is empty or `realized_series` raised `SoakError`; the report then
    stops at the NO VERDICT line, with the window block and self-tests still rendered above it, and
    `null_mode`/`path` (spec 00061 D4/D5) are stated up front even so, since a void run still reflects a choice a
    re-run would want to reproduce. A non-empty `void_reasons` suppresses every section below the gate, so an
    untrustworthy run never prints a per-metric conclusion, while the STORE-BOUND WINDOW warning sits ABOVE that
    gate, in the window block itself: a stale window's numbers are read top-down and a caveat below them arrives
    after the damage. Both free-form paths into the rendered text -- `internals_reason` and the joined `void_reasons`,
    each able to carry `str(exc)` -- go through `_scrub`, while their JSON copies stay unscrubbed."""
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
    # Rendered whenever a series exists at all, the zero-scored-bars case included: a window the store closed
    # to nothing is exactly when the reader most needs to know the store closed it.
    if realized is not None:
        lines.append(f"  window_bound   : {realized.window_bound}")
        lines.append(f"  store last bar : {_fmt_ts(realized.store_last_ts)}")
        lines.append(f"  journal last   : {_fmt_ts(realized.journal_last_cycle_ts)}")
        if realized.window_bound == "store":
            lines.append("")
            lines.append("  !! STORE-BOUND WINDOW -- the price store, not the journal, ended this window.")
            lines.append(f"     store's last usable bar : {_fmt_ts(realized.store_last_ts)}")
            lines.append(f"     journal's last cycle    : {_fmt_ts(realized.journal_last_cycle_ts)}")
            lines.append(f"     cycles this cost        : {realized.store_bound_cycles}")
            lines.append("     Everything below is a read on a STALE window, not on the journal's current")
            lines.append("     extent. Re-run against a store that covers the journal before reading it as")
            lines.append("     the present state of the evidence.")
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
        return _render_lines(lines)

    assert analysis is not None  # not void => Part B always built one alongside a present canonical

    lines.append(f"STRUCTURAL FINGERPRINT (live realized vs backtest null, band={band:.0%})")
    # Every column is joined by an explicit space rather than by padding alone -- a right-justified field gets
    # its gap only from its OWN padding -- and the verdict columns are additionally sized to the longest label
    # each can carry, so the overflow cannot arise in the first place.
    lines.append(
        f"  {'metric':<{_METRIC_COL_W}} {'live':>10} {'median':>10} {'band [lo,hi]':>24} {'pctile':>9} {'eff-n':>9} {'width':>10} "
        f"{'verdict':<{_VERDICT_COL_W}} {'primary':<{_RAW_VERDICT_COL_W}} {'secondary':<{_RAW_VERDICT_COL_W}}"
    )
    for m in _METRIC_ROWS:
        v = analysis.gating_verdicts[m]
        if m in ("governor_engagement", "cap_breach") and not analysis.internals_available:
            # Neither null was ever queried for this metric -- "-" ("not computed"), never a
            # fabricated "n/a" ("computed but undiscriminating"), for primary/secondary.
            lines.append(
                f"  {m:<{_METRIC_COL_W}} {'n/a':>10} {'n/a':>10} {'n/a':>24} {'n/a':>9} {'n/a':>9} {'n/a':>10} "
                f"{'n/a':<{_VERDICT_COL_W}} {'-':<{_RAW_VERDICT_COL_W}} {'-':<{_RAW_VERDICT_COL_W}}"
            )
            continue
        band_str = f"[{v.lo:.4f},{v.hi:.4f}]"
        dual = analysis.dual_verdicts.get(m)
        verdict_label, primary_label, secondary_label = _dual_columns(v, dual, null_mode)
        lines.append(
            f"  {m:<{_METRIC_COL_W}} {v.live:>10.4f} {v.median:>10.4f} {band_str:>24} {v.percentile:>8.1f}% {v.effective_n:>9.2f} "
            f"{v.width:>10.4f} {verdict_label:<{_VERDICT_COL_W}} {primary_label:<{_RAW_VERDICT_COL_W}} "
            f"{secondary_label:<{_RAW_VERDICT_COL_W}}"
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

    # "Governor-bias gap" is D4 in the spec vocabulary; the token stays off the report surface.
    lines.append("GOVERNOR-BIAS GAP (governed vs live-cost null)")
    bias = "bias ACTIVE" if analysis.d4_active else "bias INACTIVE"
    lines.append(f"  d4_gap_bps: {analysis.d4_gap_bps:.4f} bps/cycle ({bias})")
    lines.append("  the null P&L uses the live cost convention, so the governor bias cancels by construction")
    lines.append("")

    lines.append("P&L (NON-GATING)")
    lines.append(f"  realized cumulative net : {analysis.pnl_cum:+.4%}")
    lines.append(f"  realized mean net/cycle : {analysis.pnl_mean:+.6f}")
    pnl_dual = analysis.dual_verdicts.get("pnl")
    pnl_effective_verdict, pnl_primary_label, pnl_secondary_label = _dual_columns(analysis.pnl_verdict, pnl_dual, null_mode)
    # Both raw labels, in every null_mode, as in the table's own columns (`_dual_columns`): naming one
    # construction beside the reconciled label hides the other, and where the reconciled label equals one raw
    # label that reads as agreement when the two nulls disagreed -- a suppressed 'inconsistent'.
    pnl_secondary_note = f" (primary null: {pnl_primary_label}, secondary null: {pnl_secondary_label})"
    lines.append(f"  pnl verdict (non-gating, near-vacuous at this L): {pnl_effective_verdict}{pnl_secondary_note}")
    lines.append("")

    lines.append(_HONESTY_FOOTER)
    return _render_lines(lines)


_VERDICT_NUMERIC_FIELDS = ("live", "median", "lo", "hi", "percentile", "effective_n", "width")


def _verdict_payload(name: str, verdict: MetricVerdict, *, internals_available: bool, dual: DualVerdict | None = None) -> dict:
    """`asdict(verdict)`, except: a governor_engagement/cap_breach verdict whose "n/a" comes from an internals
    rebuild that never ran reports `None` for every numeric field, `live=0.0` there being a placeholder a
    consumer could not otherwise tell from a computed 0.0 -- an "n/a" from a computed but undiscriminating band
    keeps its real numbers. `dual` (spec 00061) lands under a stable `"dual"` key and overrides the top-level
    `"verdict"` with the RECONCILED label the table renders, the windowed null's raw one staying at
    `dual["primary"]`."""
    d = asdict(verdict)
    if name in ("governor_engagement", "cap_breach") and not internals_available:
        for key in _VERDICT_NUMERIC_FIELDS:
            d[key] = None
    d["dual"] = asdict(dual) if dual is not None else None
    if dual is not None:
        d["verdict"] = dual.verdict
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
    """Every number the report renders, as a `json.dumps`-able dict -- the machine-readable twin of
    `render_report`'s text, plus the raw `RealizedInternals` diagnostics the vocabulary-locked text cannot
    carry. `null` is accepted to mirror `render_report`'s signature but contributes nothing; every
    null-derived number already lives in `analysis`. `internals` is `None` exactly when `analysis` is."""
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
            # A machine consumer gates on `window_bound == "store"` the way a reader gates on the text report's
            # STORE-BOUND WINDOW warning.
            "window_bound": realized.window_bound,
            "store_last_ts": None if realized.store_last_ts is None else realized.store_last_ts.isoformat(),
            "journal_last_cycle_ts": (
                None if realized.journal_last_cycle_ts is None else realized.journal_last_cycle_ts.isoformat()
            ),
            "store_bound_cycles": realized.store_bound_cycles,
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
                "null_gov_rate/null_cap_rate are the null's GLOBAL rates -- do not use them as the "  # D9
                f"comparison reference; {_CONTEXT_NOTE_REFERENCE_BY_MODE[null_mode]}"
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
    """Orchestrate the full soak-check: load the journal, build the realized series, gate it (self-tests, plausibility,
    `L < floor`, degeneracy, and the internals rebuild's own `identity_ok`/`cap_consistent`) against a backtest null
    rebuilt from the frozen canonical -- absent canonical, no null and a void run -- and render both the text report and
    its JSON twin. An unavailable internals rebuild DEGRADES governor_engagement/cap_breach to "n/a" (spec 00059 D7); an
    available one failing either proof VOIDS, since the instrument would be lying about alignment. Never raises on a short,
    void or absent-canonical run -- those are refusals, not failures -- while everything else propagates, an unreadable
    record included: the one exception `soak_report` itself catches is the `SoakError` out of `realized_series`.
    `null_mode`/`path` are validated only when the canonical is present, by whichever callee first rejects them."""
    now = now or datetime.now(UTC)
    # Local import: `cli.engine.command` imports `soak_report` from this module, so a module-level import here
    # would form a cycle.
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
