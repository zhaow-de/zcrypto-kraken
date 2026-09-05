"""The concordance core (spec 00040 SS the concordance core): replay a journaled cycle through the
committed builder, compare the recomputed targets against the journaled ones, and evaluate the
ratified 4h Stage-6a gate over a run of journaled+replayed cycles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from cli.engine.cycle import _expand_to_basket, select_model_inputs
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, validate_record
from cli.portfolio import build_crossfreq_system, build_crossfreq_system_fast

_CYCLE_HOURS = (0, 4, 8, 12, 16, 20)
_FRESHNESS_WINDOW = timedelta(minutes=30)
_GATE_STREAK_DAYS = 14


class HashMismatchError(EngineError):
    """A journaled snapshot's freshly computed content hash does not match its recorded content_hash -- the evidence is
    corrupt, so no target comparison is attempted."""


@dataclass(frozen=True)
class CompareResult:
    """compare_targets' verdict: a structural (asset-set) mismatch never passes, and leaves
    worst_asset None with worst_abs_diff nan -- no shared asset exists to measure a worst diff on."""

    passed: bool
    worst_asset: str | None
    worst_abs_diff: float
    structural_mismatch: bool


@dataclass(frozen=True)
class CycleOutcome:
    """One journaled+replayed cycle's outcome as evaluate_gate consumes it: mismatch is a
    hash-verification failure, validation_failed a validate_record failure, and either breaks the
    day exactly as a missing cycle does."""

    cycle_ts: datetime
    completed_at: datetime
    compare_passed: bool = True
    mismatch: bool = False
    validation_failed: bool = False


@dataclass(frozen=True)
class FailureDetail:
    """The cycle -- boundary timestamp and reason -- that most recently reset evaluate_gate's streak."""

    cycle_ts: datetime
    reason: str


@dataclass(frozen=True)
class GateStatus:
    """evaluate_gate's verdict: the run of consecutive clean days ending at the last evaluable day, whether it meets the
    ratified `_GATE_STREAK_DAYS` gate, and the most recent break that reset it -- reported even when gate_met."""

    streak: int
    gate_met: bool
    last_failure: FailureDetail | None


def replay_cycle(
    record: CycleRecord,
    snapshot_reader: Callable[[SnapshotEntry], tuple[list[datetime], list[float | None]]],
    *,
    path: str = "fast",
) -> dict[str, float]:
    """Recompute the newest-row final_targets a journaled cycle's inputs should produce, reconciling each snapshot's read
    data against its own journaled metadata as well as its content_hash -- validate_record inspects the metadata alone, so
    this is what closes the no-peek hole. Each schema replays and compares in its OWN key space (spec 00094 D3):
    normalizing a v1 replay to symbol keys would make every v1 record a structural mismatch against its own journal."""
    validate_record(record)

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

    def _assemble(grid: str) -> tuple[list[datetime], dict[str, list[float | None]]]:
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

    expected_h4_last = record.cycle_ts - timedelta(hours=4)
    if h4_ts[-1] != expected_h4_last:
        raise EngineJournalError(
            f"the builder's grid does not contain the cycle_ts interval: h4_ts[-1]={h4_ts[-1]!r} != "
            f"cycle_ts - 4h ({expected_h4_last!r})"
        )

    if record.schema_version == 1:
        model_daily_ts, model_daily = daily_ts, daily_prices
        model_h4_ts, model_h4 = h4_ts, h4_prices
    else:
        model_daily_ts, model_daily = select_model_inputs(by_grid["1440"])
        model_h4_ts, model_h4 = select_model_inputs(by_grid["240"])

    if path == "fast":
        result = build_crossfreq_system_fast(model_daily, model_daily_ts, model_h4, model_h4_ts)
    elif path == "verified":
        result = build_crossfreq_system(model_daily, model_daily_ts, model_h4, model_h4_ts)
    else:
        raise EngineError(f"path must be 'fast' or 'verified', got {path!r}")

    model_targets = {asset: series[result.n_periods] for asset, series in result.final_targets.items()}
    return model_targets if record.schema_version == 1 else _expand_to_basket(model_targets)


def compare_targets(a: dict[str, float], b: dict[str, float], *, tol: float = 1e-6) -> CompareResult:
    """Per-asset ABSOLUTE comparison -- most positions sit at exactly 0, so relative error is
    undefined -- against a cross-environment floating-point drift budget; an asset-set mismatch
    fails structurally, not numerically."""
    if set(a) != set(b):
        return CompareResult(passed=False, worst_asset=None, worst_abs_diff=math.nan, structural_mismatch=True)
    if not a:
        return CompareResult(passed=True, worst_asset=None, worst_abs_diff=0.0, structural_mismatch=False)
    worst_asset = max(a, key=lambda asset: abs(a[asset] - b[asset]))
    worst_abs_diff = abs(a[worst_asset] - b[worst_asset])
    return CompareResult(
        passed=worst_abs_diff <= tol, worst_asset=worst_asset, worst_abs_diff=worst_abs_diff, structural_mismatch=False
    )


def _day_boundaries(day: date, tzinfo) -> list[datetime]:
    return [datetime(day.year, day.month, day.day, h, tzinfo=tzinfo) for h in _CYCLE_HOURS]


def evaluate_gate(entries: list[CycleOutcome], *, now: datetime) -> GateStatus:
    """The ratified 4h gate over complete UTC days: a day enters evaluation only once its last cycle's freshness window
    has elapsed, a mid-day start's partial first day is excluded rather than failed, and a day is clean only if every
    `_CYCLE_HOURS` boundary landed inside its window with a trustworthy passing compare -- any break resets the streak.
    A duplicate cycle_ts raises rather than letting the later outcome win, which would hide the writer bug behind it."""
    if not entries:
        return GateStatus(streak=0, gate_met=False, last_failure=None)

    by_cycle_ts: dict[datetime, CycleOutcome] = {}
    for e in entries:
        if e.cycle_ts in by_cycle_ts:
            raise EngineJournalError(
                f"duplicate CycleOutcome for cycle_ts={e.cycle_ts!r} -- a journal must never have two outcomes per cycle"
            )
        by_cycle_ts[e.cycle_ts] = e
    first_cycle_ts = min(by_cycle_ts)
    tzinfo = now.tzinfo

    excluded_day = first_cycle_ts.date() if first_cycle_ts.hour != 0 else None
    start_day = (excluded_day + timedelta(days=1)) if excluded_day else first_cycle_ts.date()

    last_observed_day = max(e.cycle_ts.date() for e in entries)
    upper_bound_day = max(last_observed_day, now.date())

    days = []
    d = start_day
    while d <= upper_bound_day:
        cutoff = datetime(d.year, d.month, d.day, 20, tzinfo=tzinfo) + _FRESHNESS_WINDOW
        if cutoff > now:
            break
        days.append(d)
        d += timedelta(days=1)

    streak = 0
    last_failure: FailureDetail | None = None
    for day in days:
        day_clean = True
        for boundary in _day_boundaries(day, tzinfo):
            entry = by_cycle_ts.get(boundary)
            if entry is None:
                day_clean, last_failure = False, FailureDetail(boundary, "missing cycle")
            elif entry.validation_failed:
                day_clean, last_failure = False, FailureDetail(boundary, "validation failed (schema / boundary invariant)")
            elif entry.mismatch:
                day_clean, last_failure = False, FailureDetail(boundary, "hash mismatch (corrupt evidence)")
            elif not (boundary <= entry.completed_at <= boundary + _FRESHNESS_WINDOW):
                day_clean, last_failure = False, FailureDetail(boundary, "late cycle (outside the 30-minute freshness window)")
            elif not entry.compare_passed:
                day_clean, last_failure = False, FailureDetail(boundary, "compare mismatch")
            if not day_clean:
                break
        streak = streak + 1 if day_clean else 0

    return GateStatus(streak=streak, gate_met=streak >= _GATE_STREAK_DAYS, last_failure=last_failure)
