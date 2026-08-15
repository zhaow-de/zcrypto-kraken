"""The concordance core (spec 00040 SS the concordance core): replay a journaled cycle through the
committed builder, compare recomputed targets against the journaled ones, and evaluate the
ratified 4h Stage-6a gate over a run of journaled+replayed cycles.

replay_cycle never trusts a journal's own claims blindly: it validates the record's schema and
snapshot-boundary invariant first (a violation is a failed cycle, raised before any snapshot read
or build), verifies every snapshot's content hash against freshly read data (a mismatch is
corrupt evidence -- HashMismatchError, distinct from a validation failure), reconciles that same
read data against the entry's own declared metadata (len/first/last, EngineJournalError on
disagreement -- validate_record only ever inspects the metadata, so this closes the no-peek hole
for both grids at once), and locates the newest-row targets by an independently re-derived
cycle_ts boundary rather than by raw last-index.

Both journal schemas replay here, each in its OWN key space (spec 00094 D3): base-keyed v1 through
the ten-asset path, symbol-keyed v2 through the cycle's own contraction/expansion pair. Nothing is
normalized across the two -- see replay_cycle.
"""

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
    """A journaled snapshot's freshly computed content hash does not match its recorded
    content_hash -- corrupt evidence, classified as MISMATCH by evaluate_gate (distinct from a
    journal-validation failure, which is a missed cycle)."""


@dataclass(frozen=True)
class CompareResult:
    """compare_targets' verdict. On a structural (asset-set) mismatch, worst_asset is None and
    worst_abs_diff is nan -- undefined, since there is no shared asset to measure a worst diff on;
    passed is always False in that case."""

    passed: bool
    worst_asset: str | None
    worst_abs_diff: float
    structural_mismatch: bool


@dataclass(frozen=True)
class CycleOutcome:
    """One journaled+replayed cycle's outcome, as evaluate_gate consumes it -- independent of how
    the caller produced it (replay_cycle + compare_targets in production; hand-built in tests).
    mismatch is a hash-verification failure (corrupt evidence); validation_failed is a
    validate_record failure (schema or the snapshot-boundary invariant); both count as the cycle
    not having produced a trustworthy, on-time, matching target -- a missed cycle for the gate."""

    cycle_ts: datetime
    completed_at: datetime
    compare_passed: bool = True
    mismatch: bool = False
    validation_failed: bool = False


@dataclass(frozen=True)
class FailureDetail:
    """The cycle (boundary timestamp + reason) that most recently reset the streak evaluate_gate is
    reporting -- None when no reset occurred anywhere in the evaluated day range."""

    cycle_ts: datetime
    reason: str


@dataclass(frozen=True)
class GateStatus:
    """evaluate_gate's verdict: the current run of consecutive clean days ending at the last
    evaluable day, whether that meets the ratified >= 14-day gate, and the most recent break (if
    any) that reset the streak to its current run."""

    streak: int
    gate_met: bool
    last_failure: FailureDetail | None


def replay_cycle(
    record: CycleRecord,
    snapshot_reader: Callable[[SnapshotEntry], tuple[list[datetime], list[float | None]]],
    *,
    path: str = "fast",
) -> dict[str, float]:
    """Recompute the newest-row final_targets a journaled cycle's inputs should produce.

    (1) validate_record(record) -- schema + the snapshot-boundary invariant; a violation raises
    before any snapshot is read or any builder runs. (2) for every journaled SnapshotEntry,
    snapshot_reader(entry) -> (ts, closes); snapshot_content_hash(ts, closes) is compared against
    entry.content_hash -- any mismatch raises HashMismatchError. The read (ts, closes) is then
    reconciled against the entry's own declared metadata -- len(ts) == entry.n_bars, ts[0] ==
    entry.first_ts, ts[-1] == entry.last_ts -- raising EngineJournalError on disagreement; this is
    what closes the no-peek hole for both grids at once, since validate_record only ever inspects
    the metadata, never the data it describes. (3) the per-pair (ts, closes) are assembled into the
    builder's daily/4h price dicts and shared ts lists (every pair on a grid must share that grid's
    exact calendar, or assembly itself raises EngineJournalError). (4) path selects
    build_crossfreq_system_fast ("fast", the default) or build_crossfreq_system ("verified", the
    daily oracle spot replay); both run with the builder's default CrossfreqSystemConfig (the
    journal does not carry a config -- record 44's fixed constants are the only ones in play).
    (5) the newest row is located BY cycle_ts, never by raw last-index: the assembled h4 grid's own
    last stamp must equal cycle_ts - 4h (re-derived from the data just read, hash-verified, and
    metadata-reconciled -- not trusted from the journal's SnapshotEntry metadata) or this raises
    EngineJournalError -- only then is final_targets[asset][n_periods] (the builder's own
    forming-row index) read and returned.

    EACH SCHEMA REPLAYS AND COMPARES IN ITS OWN NATIVE KEY SPACE (spec 00094 D3). A schema-1
    record's journaled pairs ARE the ten-asset model's base keys, so its assembled grids go to the
    builder untouched and the base-keyed forming row comes straight back. A schema-2 record's pairs
    are the twelve full symbols, so `select_model_inputs` contracts them to the ten `/EUR` legs on
    the model's own calendar and `_expand_to_basket` maps the result back onto the twelve -- both
    imported from `cli.engine.cycle`, the one implementation the cycle itself runs, so a replay can
    never diverge from the build it is checking.

    What this deliberately does NOT do is normalize one schema's output into the other's key space:
    the gate compares a record against ITS OWN replay, never against another record, and a v1
    replay lifted to symbol keys would be a structural mismatch against the base-keyed record that
    produced it -- every pre-deploy cycle would fail and the ratified streak would zero at exactly
    the moment the schema turned over. `compare_targets` stays key-agnostic for the same reason.
    """
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
    """Per-asset absolute comparison (most positions sit at exactly 0, so relative error is
    undefined; 1e-6 is the cross-environment floating-point drift budget, ~5e-6 of the 0.2 cap).
    An asset-set mismatch fails STRUCTURALLY, not numerically."""
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
    """The ratified 4h gate over a complete-UTC-days universe (spec 00040 SS the concordance core).

    A day enters evaluation only after its 20:00 cycle's 30-minute freshness window has elapsed
    (relative to `now`); days before and including a mid-day start's partial first day (detected
    from the earliest entry's cycle_ts not falling on 00:00) are excluded, not failed. Two
    CycleOutcomes sharing the same cycle_ts raise EngineJournalError immediately -- a journal must
    never have two outcomes per cycle, and silently letting the later one win would hide a writer
    bug. A day is clean iff all 6 cycles (00/04/08/12/16/20 UTC) are present in `entries`, each
    cycle's completed_at falls within [boundary, boundary + 30min], and each cycle's outcome
    carries no validation failure, no hash mismatch, and a passing compare. Any miss/mismatch
    resets the running streak; the gate is met at >= 14 consecutive clean days ending at the last
    evaluable day. last_failure reports the boundary + reason of the most recent reset, if any --
    even when gate_met is True (diagnostic: how far the current clean run is from the last blip).
    """
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
