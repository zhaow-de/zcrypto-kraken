"""Structural metrics computed from a sequence of per-bar portfolio weights: gross and net
exposure, the fraction of assets held active, per-bar turnover, portfolio concentration (HHI),
and whether either per-asset cap was breached. Also derives, from a per-bar governor multiplier
series, which trading days saw the governor engage at all.

Also builds the REALIZED forward-return observation from the engine's journal + price store: for
each cycle T, the position decided at T is held over [T, T+4h) and scored against that bar's
actual forward return, joined against the store BY TIMESTAMP -- see `realized_series` for the
exact timing model and its off-by-one cross-check (`chain_ok`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, SnapshotEntry
from cli.engine.store import read_store_series


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
