"""Tests for the concordance core (cli/engine/concordance.py): compare_targets, evaluate_gate, and
replay_cycle. Everything here is synthetic -- replay_cycle tests use a stub snapshot_reader and a
monkeypatched builder, never the real (dataset-backed, ~2min) build_crossfreq_system[_fast]."""

import types
from datetime import date, datetime, timedelta

import pytest

import cli.engine.concordance as concordance
from cli.engine import (
    CycleOutcome,
    CycleRecord,
    EngineError,
    EngineJournalError,
    HashMismatchError,
    SnapshotEntry,
    compare_targets,
    evaluate_gate,
    replay_cycle,
    snapshot_content_hash,
)

# --- compare_targets ------------------------------------------------------------------------------


def test_compare_targets_pass_within_tolerance():
    result = compare_targets({"BTC": 0.1, "ETH": -0.05}, {"BTC": 0.1000001, "ETH": -0.0500002})
    assert result.passed
    assert not result.structural_mismatch


def test_compare_targets_fail_numeric():
    result = compare_targets({"BTC": 0.1, "ETH": -0.05}, {"BTC": 0.11, "ETH": -0.05})
    assert not result.passed
    assert not result.structural_mismatch
    assert result.worst_asset == "BTC"
    assert result.worst_abs_diff == pytest.approx(0.01)


def test_compare_targets_structural_mismatch_on_asset_set():
    result = compare_targets({"BTC": 0.1}, {"BTC": 0.1, "ETH": 0.0})
    assert not result.passed
    assert result.structural_mismatch
    assert result.worst_asset is None


def test_compare_targets_empty_both_pass():
    result = compare_targets({}, {})
    assert result.passed
    assert not result.structural_mismatch


def test_compare_targets_tolerance_bracketed_both_sides():
    """D3 (spec 00063): the pass/fail cases above sit at ~1e-7 and 1e-2 -- five orders of magnitude
    away from tol's ratified default (1e-6, concordance.py:159), so a divergence 120x over budget
    would still pass at tol=1e-3. Bracket both edges immediately around tol itself: the margins are
    expressed as fractions of tol (not raw literals) so the test states the rule. tol itself has to
    be a hardcoded anchor, not read back from the function -- reading the live default would just
    track a drifted value and never fail (the same tautology PR #162 hit with the streak constant)."""
    tol = 1e-6  # today's ratified default (concordance.py:159) -- the external anchor this pins

    just_inside = tol - tol * 0.1
    just_outside = tol + tol * 0.1

    passing = compare_targets({"BTC": 0.1}, {"BTC": 0.1 + just_inside})
    assert passing.passed

    failing = compare_targets({"BTC": 0.1}, {"BTC": 0.1 + just_outside})
    assert not failing.passed


def test_compare_targets_structural_mismatch_equal_cardinality_different_keys():
    """Equal-cardinality dicts with different keys must still fail structurally, not just the
    differing-cardinality case above. Weakening `set(a) != set(b)` (concordance.py:161) to a length
    check would let this pair fall through to the per-asset comparison, which today is unreached:
    it would then KeyError on the first asset absent from the other side -- an unreached path, not
    a silent-corruption one, so its severity should not be over-read from this test alone."""
    result = compare_targets({"BTC": 0.1, "ETH": 0.0}, {"BTC": 0.1, "SOL": 0.0})
    assert not result.passed
    assert result.structural_mismatch
    assert result.worst_asset is None


# --- evaluate_gate ---------------------------------------------------------------------------------

CYCLE_HOURS = (0, 4, 8, 12, 16, 20)


def _clean_day(day: date, *, start_hour: int = 0) -> list[CycleOutcome]:
    return [
        CycleOutcome(
            cycle_ts=datetime(day.year, day.month, day.day, h),
            completed_at=datetime(day.year, day.month, day.day, h) + timedelta(minutes=2),
        )
        for h in CYCLE_HOURS
        if h >= start_hour
    ]


def _days(start: date, n: int) -> list[date]:
    return [start + timedelta(days=k) for k in range(n)]


def _past_cutoff(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 21, 0)


START = date(2026, 1, 1)


def test_gate_met_on_14_consecutive_clean_days():
    days = _days(START, 14)
    entries = [e for d in days for e in _clean_day(d)]
    status = evaluate_gate(entries, now=_past_cutoff(days[-1]))
    assert status.streak == 14
    assert status.gate_met
    assert status.last_failure is None


def test_missed_cycle_resets_streak():
    days = _days(START, 15)
    missing_day = days[5]
    entries = [e for d in days for e in _clean_day(d) if not (e.cycle_ts.date() == missing_day and e.cycle_ts.hour == 12)]
    status = evaluate_gate(entries, now=_past_cutoff(days[-1]))
    assert status.streak == len(days) - 1 - 5  # days after missing_day, all clean
    assert not status.gate_met
    assert status.last_failure.cycle_ts == datetime(missing_day.year, missing_day.month, missing_day.day, 12)
    assert status.last_failure.reason == "missing cycle"


def test_late_cycle_resets_streak():
    day0, day1 = _days(START, 2)
    entries = _clean_day(day0)
    for e in _clean_day(day1):
        if e.cycle_ts.hour == 8:
            e = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.cycle_ts + timedelta(minutes=31))
        entries.append(e)
    status = evaluate_gate(entries, now=_past_cutoff(day1))
    assert status.streak == 0
    assert status.last_failure.cycle_ts == datetime(day1.year, day1.month, day1.day, 8)
    assert "late" in status.last_failure.reason


def test_compare_mismatch_resets_streak():
    day0, day1 = _days(START, 2)
    entries = _clean_day(day0)
    for e in _clean_day(day1):
        if e.cycle_ts.hour == 16:
            e = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.completed_at, compare_passed=False)
        entries.append(e)
    status = evaluate_gate(entries, now=_past_cutoff(day1))
    assert status.streak == 0
    assert status.last_failure.cycle_ts == datetime(day1.year, day1.month, day1.day, 16)
    assert status.last_failure.reason == "compare mismatch"


def test_boundary_invariant_violation_classified_as_failed_cycle():
    day0, day1 = _days(START, 2)
    entries = _clean_day(day0)
    for e in _clean_day(day1):
        if e.cycle_ts.hour == 0:
            e = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.completed_at, validation_failed=True)
        entries.append(e)
    status = evaluate_gate(entries, now=_past_cutoff(day1))
    assert status.streak == 0
    assert status.last_failure.cycle_ts == datetime(day1.year, day1.month, day1.day, 0)
    assert "validation" in status.last_failure.reason


def test_hash_mismatch_resets_streak():
    day0, day1 = _days(START, 2)
    entries = _clean_day(day0)
    for e in _clean_day(day1):
        if e.cycle_ts.hour == 20:
            e = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.completed_at, mismatch=True)
        entries.append(e)
    status = evaluate_gate(entries, now=_past_cutoff(day1))
    assert status.streak == 0
    assert status.last_failure.cycle_ts == datetime(day1.year, day1.month, day1.day, 20)
    assert "mismatch" in status.last_failure.reason


def test_intra_day_evaluation_excludes_in_progress_day_without_breaking_streak():
    days = _days(START, 5)
    entries = [e for d in days for e in _clean_day(d)]  # day 4's entries exist but aren't due yet
    now = datetime(days[4].year, days[4].month, days[4].day, 9, 0)  # well before day 4's 20:30 cutoff
    status = evaluate_gate(entries, now=now)
    assert status.streak == 4
    assert not status.gate_met
    assert status.last_failure is None


def test_day_cutoff_anchor_discriminates_alternate_boundaries():
    """D3 (spec 00063): the intra-day test above uses now=09:00, which sits below every plausible
    day-cutoff anchor (20:00 flat, 20:30 with the freshness window, next midnight, ...) so it can't
    tell them apart. Position `now` just after the true 20:30 anchor (20:00 + the 30-minute
    freshness window) -- under the correct anchor the final day is already due and clean, so it
    counts too; a boundary shifted even one hour later would still exclude it, giving a different
    streak."""
    days = _days(START, 5)
    entries = [e for d in days for e in _clean_day(d)]
    now = datetime(days[4].year, days[4].month, days[4].day, 20, 35)  # 5 min past the 20:30 anchor
    status = evaluate_gate(entries, now=now)
    assert status.streak == 5  # day 4 is due (past 20:30) and clean, so it counts too
    assert not status.gate_met
    assert status.last_failure is None


def test_day_cutoff_requires_the_freshness_window_not_just_the_hour():
    """The anchor test above uses now=20:35, which is past BOTH the true 20:30 cutoff and a
    window-dropped 20:00 one, so it cannot tell them apart -- verified: deleting `+
    _FRESHNESS_WINDOW` from the day cutoff left the whole suite green. Position `now` BETWEEN the
    two: at 20:15 the correct cutoff (20:00 + 30m) has not passed, so the final day is still in
    progress and must be excluded; drop the window and it is wrongly counted as complete, flipping
    the gate 30 minutes early. The per-cycle freshness bound is separately pinned by
    test_late_cycle_resets_streak -- this covers only the DAY cutoff, which was not."""
    days = _days(START, 5)
    entries = [e for d in days for e in _clean_day(d)]
    now = datetime(days[4].year, days[4].month, days[4].day, 20, 15)  # inside 20:00-20:30
    status = evaluate_gate(entries, now=now)
    assert status.streak == 4, "day 4 is not due until 20:30 -- the freshness window is part of the cutoff"
    assert not status.gate_met
    assert status.last_failure is None


def test_mid_day_start_excludes_partial_first_day_not_fails_it():
    days = _days(START, 4)
    day0 = days[0]
    entries = _clean_day(day0, start_hour=8)  # node started mid-day: only 08/12/16/20 present
    for d in days[1:]:
        entries.extend(_clean_day(d))
    status = evaluate_gate(entries, now=_past_cutoff(days[-1]))
    assert status.streak == 3  # day0 excluded, not failed; days 1-3 count
    assert not status.gate_met
    assert status.last_failure is None


def test_gate_streak_threshold_pinned_both_directions():
    # Pins the ratified threshold's current value: gate_met is *defined* as streak >=
    # _GATE_STREAK_DAYS, so building inputs from the constant and comparing against the same live
    # constant is a tautology that holds for any value -- it can never fail if the constant itself
    # silently moves. This explicit value check is what makes the boundary assertions below able to
    # catch that. Update this line deliberately if the ratified rule (spec 00040) changes.
    assert concordance._GATE_STREAK_DAYS == 14

    days_at = _days(START, concordance._GATE_STREAK_DAYS)
    entries_at = [e for d in days_at for e in _clean_day(d)]
    status_at = evaluate_gate(entries_at, now=_past_cutoff(days_at[-1]))
    assert status_at.streak == concordance._GATE_STREAK_DAYS
    assert status_at.gate_met is True

    days_below = _days(START, concordance._GATE_STREAK_DAYS - 1)
    entries_below = [e for d in days_below for e in _clean_day(d)]
    status_below = evaluate_gate(entries_below, now=_past_cutoff(days_below[-1]))
    assert status_below.streak == concordance._GATE_STREAK_DAYS - 1
    assert status_below.gate_met is False


def test_gate_dead_engine_after_5_days_silence_resets_streak_not_stale_streak():
    days = _days(START, concordance._GATE_STREAK_DAYS)
    entries = [e for d in days for e in _clean_day(d)]
    now = _past_cutoff(days[-1] + timedelta(days=5))
    status = evaluate_gate(entries, now=now)
    assert status.streak == 0
    assert status.gate_met is False


def test_evaluate_gate_empty_entries():
    status = evaluate_gate([], now=datetime(2026, 1, 1))
    assert status.streak == 0
    assert not status.gate_met
    assert status.last_failure is None


def test_evaluate_gate_duplicate_cycle_ts_raises():
    day0 = START
    entries = _clean_day(day0)
    entries.append(CycleOutcome(cycle_ts=entries[0].cycle_ts, completed_at=entries[0].completed_at))  # duplicate cycle_ts
    with pytest.raises(EngineJournalError):
        evaluate_gate(entries, now=_past_cutoff(day0))


def test_last_failure_reports_the_most_recent_of_multiple():
    """D5 (spec 00063): every failure test above injects exactly one failure, so `last_failure`'s
    'most recent' ordering is untestable as written -- a mutant that kept the FIRST failure instead
    of the last would pass every one of them too. Inject two failures on different days and assert
    the later one, not the earlier one, is reported."""
    days = _days(START, 3)
    entries = []
    for d in days:
        day_entries = _clean_day(d)
        if d == days[0]:
            for i, e in enumerate(day_entries):
                if e.cycle_ts.hour == 4:
                    day_entries[i] = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.completed_at, mismatch=True)
        if d == days[2]:
            for i, e in enumerate(day_entries):
                if e.cycle_ts.hour == 16:
                    day_entries[i] = CycleOutcome(cycle_ts=e.cycle_ts, completed_at=e.completed_at, compare_passed=False)
        entries.extend(day_entries)
    status = evaluate_gate(entries, now=_past_cutoff(days[-1]))
    assert status.streak == 0
    assert status.last_failure.cycle_ts == datetime(days[2].year, days[2].month, days[2].day, 16)
    assert status.last_failure.reason == "compare mismatch"


# --- replay_cycle ------------------------------------------------------------------------------

CYCLE_TS = datetime(2026, 7, 10, 8, 0)
H4_TS = [datetime(2026, 7, 9, 20, 0), datetime(2026, 7, 10, 0, 0), datetime(2026, 7, 10, 4, 0)]
H4_CLOSES = [100.0, 101.0, 102.0]
DAILY_TS = [datetime(2026, 7, 7, 0, 0), datetime(2026, 7, 8, 0, 0), datetime(2026, 7, 9, 0, 0)]
DAILY_CLOSES = [50.0, 51.0, 52.0]


def _snapshot_entries():
    h4 = SnapshotEntry(
        pair="BTC",
        grid="240",
        n_bars=len(H4_TS),
        first_ts=H4_TS[0],
        last_ts=H4_TS[-1],
        content_hash=snapshot_content_hash(H4_TS, H4_CLOSES),
        path="p240",
    )
    daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=len(DAILY_TS),
        first_ts=DAILY_TS[0],
        last_ts=DAILY_TS[-1],
        content_hash=snapshot_content_hash(DAILY_TS, DAILY_CLOSES),
        path="p1440",
    )
    return h4, daily


def _valid_cycle_record(**overrides) -> CycleRecord:
    h4, daily = _snapshot_entries()
    fields = {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS,
        "snapshots": (h4, daily),
        "final_targets": {"BTC": 0.1},
        "started_at": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=1),
        "code_version": "test",
        "builder_path": "fast",
    }
    fields.update(overrides)
    return CycleRecord(**fields)


def _honest_reader(entry: SnapshotEntry):
    if entry.grid == "240":
        return list(H4_TS), list(H4_CLOSES)
    return list(DAILY_TS), list(DAILY_CLOSES)


def _fake_builder(final_targets, n_periods, calls):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        calls.append((daily_prices, daily_ts, h4_prices, h4_ts))
        return types.SimpleNamespace(final_targets=final_targets, n_periods=n_periods)

    return builder


def test_replay_cycle_hash_mismatch_raises_and_skips_build(monkeypatch):
    def corrupt_reader(entry: SnapshotEntry):
        ts, closes = _honest_reader(entry)
        if entry.grid == "240":
            closes = [c + 1.0 if c is not None else c for c in closes]  # corrupt the 4h snapshot
        return ts, closes

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))
    with pytest.raises(HashMismatchError):
        replay_cycle(_valid_cycle_record(), corrupt_reader, path="fast")
    assert calls == []  # the builder must never run on corrupt evidence


def test_replay_cycle_locates_newest_row_by_cycle_ts(monkeypatch):
    calls = []
    # 4 rows with n_periods=2: series[2] (0.1) is genuinely distinct from series[-1] (0.2), so a
    # blind [-1] read would silently return the wrong value instead of failing.
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0, 0.05, 0.1, 0.2]}, 2, calls))
    out = replay_cycle(_valid_cycle_record(), _honest_reader, path="fast")
    assert out == {"BTC": 0.1}  # row index n_periods=2, never a blind [-1]
    assert len(calls) == 1
    daily_prices, daily_ts, h4_prices, h4_ts = calls[0]
    assert daily_ts == DAILY_TS
    assert h4_ts == H4_TS
    assert daily_prices == {"BTC": DAILY_CLOSES}
    assert h4_prices == {"BTC": H4_CLOSES}


def test_replay_cycle_path_selects_builder(monkeypatch):
    fast_calls, verified_calls = [], []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0, 0.0, 0.1]}, 2, fast_calls))
    monkeypatch.setattr(concordance, "build_crossfreq_system", _fake_builder({"BTC": [0.0, 0.0, 0.2]}, 2, verified_calls))

    assert replay_cycle(_valid_cycle_record(), _honest_reader, path="fast") == {"BTC": 0.1}
    assert len(fast_calls) == 1 and len(verified_calls) == 0

    assert replay_cycle(_valid_cycle_record(), _honest_reader, path="verified") == {"BTC": 0.2}
    assert len(verified_calls) == 1


def test_replay_cycle_invalid_path(monkeypatch):
    with pytest.raises(EngineError):
        replay_cycle(_valid_cycle_record(), _honest_reader, path="quick")


def test_replay_cycle_boundary_violation_raises_before_any_build(monkeypatch):
    def unreachable_reader(entry: SnapshotEntry):
        raise AssertionError("snapshot_reader must not be called when validate_record already failed")

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    h4, daily = _snapshot_entries()
    bad_h4 = SnapshotEntry(
        pair="BTC",
        grid="240",
        n_bars=h4.n_bars,
        first_ts=h4.first_ts,
        last_ts=h4.last_ts - timedelta(hours=4),  # violates cycle_ts - 4h
        content_hash=h4.content_hash,
        path=h4.path,
    )
    record = _valid_cycle_record(snapshots=(bad_h4, daily))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, unreachable_reader, path="fast")
    assert calls == []


def test_replay_cycle_daily_peek_disagrees_with_metadata_raises_before_build(monkeypatch):
    """validate_record only ever inspects a SnapshotEntry's declared metadata, never the data it
    describes -- so a daily snapshot whose DATA still carries the in-progress candle (real last_ts
    == the cycle's own midnight) while its METADATA declares the honest, invariant-satisfying
    boundary sails through validate_record. If the content_hash is computed over that same real
    (peeked) data, the hash-verification step can't catch it either. replay_cycle must reconcile
    the read data's own (len, first, last) against the entry's declared metadata and raise
    EngineJournalError before any build."""
    peeked_daily_ts = [*DAILY_TS, datetime(2026, 7, 10, 0, 0)]  # cycle's own midnight -- in-progress candle
    peeked_daily_closes = [*DAILY_CLOSES, 53.0]

    h4, honest_daily = _snapshot_entries()
    peeked_daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=honest_daily.n_bars,  # declares the honest (non-peeked) count
        first_ts=honest_daily.first_ts,
        last_ts=honest_daily.last_ts,  # declares the honest, invariant-satisfying boundary
        content_hash=snapshot_content_hash(peeked_daily_ts, peeked_daily_closes),  # hash over the REAL peeked data
        path=honest_daily.path,
    )
    record = _valid_cycle_record(snapshots=(h4, peeked_daily))

    def peeking_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(H4_TS), list(H4_CLOSES)
        return list(peeked_daily_ts), list(peeked_daily_closes)

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, peeking_reader, path="fast")
    assert calls == []  # the builder must never run on data that disagrees with its own metadata


def test_same_length_peek_is_still_rejected(monkeypatch):
    """THE KEYSTONE (spec D2). Today's peek fixture above trips n_bars AND last_ts together --
    deleting either term alone still leaves the suite green. This one swaps the trailing settled
    bar for the in-progress candle at EQUAL length: n_bars and first_ts both still agree with the
    declared metadata, only last_ts differs. If the `ts[-1] != entry.last_ts` term were dropped
    from line 118's disjunction, the builder would run on lookahead data and -- because n_bars and
    first_ts still match -- nothing else here would catch it: the targets would simply come out
    wrong, not loudly rejected. That silent-contamination failure mode is what makes this the
    keystone, not just a third conjunct."""
    in_progress_ts = datetime(2026, 7, 10, 0, 0)  # cycle's own midnight -- the in-progress candle
    swapped_daily_ts = [DAILY_TS[0], DAILY_TS[1], in_progress_ts]  # same length, trailing bar swapped
    swapped_daily_closes = [DAILY_CLOSES[0], DAILY_CLOSES[1], 53.0]

    h4, honest_daily = _snapshot_entries()
    same_length_daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=honest_daily.n_bars,  # 3 == len(swapped_daily_ts): matches
        first_ts=honest_daily.first_ts,  # == swapped_daily_ts[0]: matches
        last_ts=honest_daily.last_ts,  # declared honest boundary -- the actual last_ts differs
        content_hash=snapshot_content_hash(swapped_daily_ts, swapped_daily_closes),  # hash over the REAL data
        path=honest_daily.path,
    )
    record = _valid_cycle_record(snapshots=(h4, same_length_daily))

    def swapping_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(H4_TS), list(H4_CLOSES)
        return list(swapped_daily_ts), list(swapped_daily_closes)

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, swapping_reader, path="fast")
    assert calls == []  # the builder must never run on lookahead data


def test_replay_cycle_n_bars_mismatch_alone_raises(monkeypatch):
    """n_bars alone (spec D1). An extra bar inserted mid-series changes the count while both
    endpoints -- ts[0] and ts[-1] -- still agree with the declared metadata. Isolates the
    `len(ts) != entry.n_bars` conjunct: the other two terms in line 118's disjunction stay
    satisfied, so only deleting this exact term can make this test pass again."""
    extra_ts = datetime(2026, 7, 7, 12, 0)  # inserted between DAILY_TS[0] and DAILY_TS[1]
    padded_daily_ts = [DAILY_TS[0], extra_ts, DAILY_TS[1], DAILY_TS[2]]
    padded_daily_closes = [DAILY_CLOSES[0], 50.5, DAILY_CLOSES[1], DAILY_CLOSES[2]]

    h4, honest_daily = _snapshot_entries()
    padded_daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=honest_daily.n_bars,  # 3 != len(padded_daily_ts)=4: mismatches
        first_ts=honest_daily.first_ts,  # == padded_daily_ts[0]: matches
        last_ts=honest_daily.last_ts,  # == padded_daily_ts[-1]: matches
        content_hash=snapshot_content_hash(padded_daily_ts, padded_daily_closes),
        path=honest_daily.path,
    )
    record = _valid_cycle_record(snapshots=(h4, padded_daily))

    def padding_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(H4_TS), list(H4_CLOSES)
        return list(padded_daily_ts), list(padded_daily_closes)

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, padding_reader, path="fast")
    assert calls == []


def test_replay_cycle_first_ts_mismatch_alone_raises(monkeypatch):
    """first_ts alone (spec D1). The leading bar is swapped for an earlier date while the count
    and the trailing bar stay put. Isolates the `ts[0] != entry.first_ts` conjunct: n_bars and
    last_ts both still agree with the declared metadata."""
    shifted_first_ts = datetime(2026, 7, 6, 0, 0)  # one day earlier than DAILY_TS[0]
    shifted_daily_ts = [shifted_first_ts, DAILY_TS[1], DAILY_TS[2]]
    shifted_daily_closes = [49.0, DAILY_CLOSES[1], DAILY_CLOSES[2]]

    h4, honest_daily = _snapshot_entries()
    shifted_daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=honest_daily.n_bars,  # 3 == len(shifted_daily_ts): matches
        first_ts=honest_daily.first_ts,  # != shifted_daily_ts[0]: mismatches
        last_ts=honest_daily.last_ts,  # == shifted_daily_ts[-1]: matches
        content_hash=snapshot_content_hash(shifted_daily_ts, shifted_daily_closes),
        path=honest_daily.path,
    )
    record = _valid_cycle_record(snapshots=(h4, shifted_daily))

    def shifting_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(H4_TS), list(H4_CLOSES)
        return list(shifted_daily_ts), list(shifted_daily_closes)

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, shifting_reader, path="fast")
    assert calls == []


def test_replay_cycle_multi_pair_calendar_mismatch_raises(monkeypatch):
    """D4 (spec 00063): every replay_cycle test above uses exactly one pair, so the multi-pair
    guard at _assemble's `ts != shared_ts` branch has never executed in this suite -- a guard that
    never runs in CI is indistinguishable from one that was deleted, and production is multi-pair.
    ETH's 4h snapshot ends on the same journaled boundary as BTC's (validate_record only checks the
    LAST stamp against cycle_ts - 4h) but carries a different bar count/spacing before it, so the
    two pairs' 4h calendars disagree once assembled."""
    h4_btc, daily_btc = _snapshot_entries()

    eth_h4_ts = [
        datetime(2026, 7, 9, 16, 0),
        datetime(2026, 7, 9, 20, 0),
        datetime(2026, 7, 10, 0, 0),
        datetime(2026, 7, 10, 4, 0),  # same last stamp as BTC's h4 grid (cycle_ts - 4h)
    ]
    eth_h4_closes = [9.0, 10.0, 11.0, 12.0]
    eth_h4 = SnapshotEntry(
        pair="ETH",
        grid="240",
        n_bars=len(eth_h4_ts),
        first_ts=eth_h4_ts[0],
        last_ts=eth_h4_ts[-1],
        content_hash=snapshot_content_hash(eth_h4_ts, eth_h4_closes),
        path="p240-eth",
    )
    eth_daily = SnapshotEntry(
        pair="ETH",
        grid="1440",
        n_bars=daily_btc.n_bars,
        first_ts=daily_btc.first_ts,
        last_ts=daily_btc.last_ts,
        content_hash=daily_btc.content_hash,
        path="p1440-eth",
    )
    record = _valid_cycle_record(snapshots=(h4_btc, daily_btc, eth_h4, eth_daily))

    def two_pair_reader(entry: SnapshotEntry):
        if entry.pair == "ETH" and entry.grid == "240":
            return list(eth_h4_ts), list(eth_h4_closes)
        return _honest_reader(entry)

    calls = []
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder({"BTC": [0.0]}, 0, calls))

    with pytest.raises(EngineJournalError):
        replay_cycle(record, two_pair_reader, path="fast")
    assert calls == []  # the builder must never run once the pairs' calendars disagree
