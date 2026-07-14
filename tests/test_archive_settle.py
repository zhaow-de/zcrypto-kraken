from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.settle import (
    LATE_MINT_HOURS,
    SETTLE_HOURS,
    fleet_dark_windows,
    hour_path,
    is_late,
    is_total_loss,
    newest_hour,
    scan_hours,
    settled_hours,
)

H = datetime(2026, 7, 16, 9, tzinfo=UTC)
HOUR_END = H + timedelta(hours=1)


def _at(seconds: float) -> datetime:
    return H + timedelta(seconds=seconds)


# --- the settle rule -----------------------------------------------------------------------------


def test_an_hour_younger_than_the_settle_delay_is_never_offered():
    # 09:00 finalizes at 10:00 and is pulled by ~11:00; at 11:30 it is settled, 10:00 is not.
    hours = settled_hours(now=datetime(2026, 7, 16, 11, 30, tzinfo=UTC), window_hours=48)
    assert hours[-1] == H
    assert H + timedelta(hours=1) not in hours


def test_the_settle_boundary_is_inclusive_at_exactly_h_plus_two():
    assert settled_hours(now=H + timedelta(hours=SETTLE_HOURS), window_hours=1) == [H]
    # one microsecond earlier and the hour is still in flight
    assert settled_hours(now=H + timedelta(hours=SETTLE_HOURS, microseconds=-1), window_hours=1) == [H - timedelta(hours=1)]


def test_the_window_is_a_trailing_run_of_hours_oldest_first():
    hours = settled_hours(now=H + timedelta(hours=SETTLE_HOURS), window_hours=48)
    assert len(hours) == 48
    assert hours == sorted(hours)  # oldest first: the ledger reads in time order
    assert hours[0] == H - timedelta(hours=47)


def test_the_late_deadline_unlocks_a_secondary_only_mint():
    assert is_late(H, now=H + timedelta(hours=LATE_MINT_HOURS - 1)) is False
    assert is_late(H, now=H + timedelta(hours=LATE_MINT_HOURS)) is True


# --- the tree scan -------------------------------------------------------------------------------


def _final(root: Path, pair: str, kind: str, hour: datetime, name: str | None = None) -> Path:
    path = hour_path(root, pair, kind, hour)
    if name is not None:
        path = path.with_name(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"ts": [hour]}).write_parquet(path)
    return path


def test_scan_hours_never_matches_a_part_or_held_file(tmp_path):
    # THE T0038 TRAP: a bare `*.parquet` glob also matches `09.part0003.parquet` (the live hour) and
    # the stale merged parts rsync never deleted, so the hour would look present when it is not —
    # and, for the reconciler, an un-finalized part would be read as a complete hour.
    _final(tmp_path, "BTC/EUR", "book", H)
    _final(tmp_path, "BTC/EUR", "book", H, name="10.part0003.parquet")
    _final(tmp_path, "BTC/EUR", "book", H, name="10.held0000.parquet")
    assert scan_hours(tmp_path, "book") == {"BTC/EUR": {H}}


def test_scan_hours_buckets_by_pair_and_kind(tmp_path):
    _final(tmp_path, "BTC/EUR", "book", H)
    _final(tmp_path, "BTC/EUR", "book", H + timedelta(hours=1))
    _final(tmp_path, "ETH/EUR", "book", H)
    _final(tmp_path, "ETH/EUR", "trades", H)
    assert scan_hours(tmp_path, "book") == {"BTC/EUR": {H, H + timedelta(hours=1)}, "ETH/EUR": {H}}
    assert scan_hours(tmp_path, "trades") == {"ETH/EUR": {H}}


def test_scan_hours_of_a_missing_root_is_empty(tmp_path):
    assert scan_hours(tmp_path / "nope", "book") == {}


def test_newest_hour_spans_every_scan(tmp_path):
    _final(tmp_path, "BTC/EUR", "book", H)
    _final(tmp_path, "ETH/EUR", "trades", H + timedelta(hours=5))
    assert newest_hour(scan_hours(tmp_path, "book"), scan_hours(tmp_path, "trades")) == H + timedelta(hours=5)
    assert newest_hour({}) is None


# --- both_streams_silent: the correlated-loss detector that needs no witness ----------------------


def test_a_fleet_that_never_goes_dark_has_no_window():
    stamps = [_at(s) for s in range(0, 3600, 5)]
    assert fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == []


def test_one_pair_quiet_while_another_ticks_is_not_a_fleet_window():
    # THE false positive this detector must not have. BTC goes quiet for 300 s; ETH keeps ticking
    # through it. That is an ordinary thin market on one pair, not a correlated outage — and a
    # detector that counted per-pair silences (with no window) could not tell the two apart.
    btc = [_at(0), _at(600)]
    eth = [_at(s) for s in range(0, 3600, 10)]
    assert fleet_dark_windows(btc + eth, hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == []


def test_every_pair_dark_in_the_same_window_is_one_fleet_window():
    # both pairs tick every 10 s except across [600, 1200), where both go dark together
    hole = [s for s in range(0, 3600, 10) if not 600 <= s < 1200]
    btc = [_at(s) for s in hole]
    eth = [_at(s + 1) for s in hole]
    windows = fleet_dark_windows(btc + eth, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert [(w.start, w.end) for w in windows] == [(_at(591), _at(1200))]
    assert windows[0].seconds == 609.0


def test_a_fleet_that_dies_mid_hour_is_caught_by_the_hour_end_bound():
    # The crash shape: the last message ever is at :10, then nothing. Without the hour's own bounds
    # as edges there is no "next message" to pair with and the 50-minute tail is invisible.
    windows = fleet_dark_windows([_at(600)], hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert [(w.start, w.end) for w in windows] == [(H, _at(600)), (_at(600), HOUR_END)]


def test_an_hour_with_no_messages_at_all_is_one_whole_dark_window():
    windows = fleet_dark_windows([], hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert [(w.start, w.end, w.seconds) for w in windows] == [(H, HOUR_END, 3600.0)]


def test_darkness_below_the_threshold_is_not_a_window():
    # a 20 s hole in an otherwise 5 s cadence: under the threshold, so not a fleet-dark window
    stamps = [_at(s) for s in range(0, 3600, 5) if not 600 < s < 620]
    assert fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == []


def test_a_row_that_leaked_in_from_an_adjacent_hour_never_fabricates_a_window():
    # A late event can carry a `ts` outside its file's hour. Clamping to the hour's bounds keeps the
    # timeline honest; a negative-length window would otherwise be reported as darkness.
    stamps = [_at(s) for s in range(0, 3600, 5)] + [HOUR_END + timedelta(seconds=30)]
    assert fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == []


# --- total_loss ----------------------------------------------------------------------------------


def test_an_hour_missing_between_two_captured_hours_is_a_total_loss():
    available = {H - timedelta(hours=1), H + timedelta(hours=1)}
    assert is_total_loss(H, available=available, span=(min(available), max(available))) is True


def test_a_captured_hour_is_never_a_total_loss():
    available = {H - timedelta(hours=1), H, H + timedelta(hours=1)}
    assert is_total_loss(H, available=available, span=(min(available), max(available))) is False


def test_the_hours_before_a_pair_was_ever_captured_are_not_a_total_loss():
    # Adding a pair to the universe would otherwise page a permanent-loss alarm for every hour of the
    # window that predates its first capture — and book them into a counter that can never be walked
    # back. An absence is only a HOLE when real data brackets it on BOTH sides.
    available = {H + timedelta(hours=1), H + timedelta(hours=2)}
    assert is_total_loss(H, available=available, span=(min(available), max(available))) is False


def test_the_trailing_edge_of_a_still_dead_fleet_is_not_a_total_loss():
    # Both hosts died at H and are still dead. An hour that has not arrived is indistinguishable from
    # one that never will; source_lag and the dead-men own that case and do not have to guess.
    available = {H - timedelta(hours=2), H - timedelta(hours=1)}
    assert is_total_loss(H, available=available, span=(min(available), max(available))) is False


def test_a_stream_with_no_data_at_all_is_not_a_total_loss():
    assert is_total_loss(H, available=set(), span=None) is False


# --- total_loss must not fire on a legitimately EMPTY trades hour ---------------------------------
#
# Found in production on 2026-07-14, on the very first reconcile cycle: LINK/EUR trades hour 02 was
# ledgered `total_loss` -- permanent, unrecoverable loss -- and logged at ERROR, which pages through
# the archive-pull ERROR rule and books into the monotonic residual counter Task 11 wires to a
# permanent-loss alarm. It was nothing of the kind: LINK/EUR traded 8 times in hour 01 and 9 times in
# hour 04, and simply had ZERO prints in hour 02. The book segment for that same pair+hour EXISTS, so
# the stream was demonstrably connected the whole time.
#
# Book updates are continuous; trades are event-driven and sparse. `is_total_loss`'s bracketing rule
# ("an absence is only a HOLE when real data brackets it") is right for a continuous stream and wrong
# for an event-driven one. The book hour is the witness that settles it: if the book committed a final
# for that hour, the connection was alive and an absent trades hour means nobody traded.


def test_absent_trades_hour_is_not_a_loss_when_the_book_hour_proves_the_stream_was_alive() -> None:
    available = {H - timedelta(hours=1), H + timedelta(hours=1)}  # trades: hour H absent, bracketed
    book_hours = {H - timedelta(hours=1), H, H + timedelta(hours=1)}  # book committed hour H

    assert (
        is_total_loss(
            H,
            available=available,
            span=(min(available), max(available)),
            alive_witness=book_hours,
        )
        is False
    )


def test_absent_trades_hour_IS_a_loss_when_the_book_hour_is_also_gone() -> None:
    """Both streams absent for the hour = the stream really was dark. That is a genuine hole."""
    available = {H - timedelta(hours=1), H + timedelta(hours=1)}
    book_hours = {H - timedelta(hours=1), H + timedelta(hours=1)}  # book ALSO missing hour H

    assert (
        is_total_loss(
            H,
            available=available,
            span=(min(available), max(available)),
            alive_witness=book_hours,
        )
        is True
    )


def test_book_stream_keeps_the_old_behaviour_when_it_has_no_witness() -> None:
    """The book IS the witness, so it is judged on bracketing alone -- unchanged."""
    available = {H - timedelta(hours=1), H + timedelta(hours=1)}

    assert is_total_loss(H, available=available, span=(min(available), max(available)), alive_witness=None) is True


# --- the gap-rate signal must exist in DETECT-ONLY, or its alert is a decoration ------------------
#
# `healed_gap_seconds_total` counts only `minted` records, and minting stays OFF for the whole T0039
# soak. So the "chronically gappy primary" alarm -- the one the plan says discharges T0003's
# gap-rate-alert item -- would be pinned at 0 for the entire period it is most needed, while looking
# like working alerting. A degrading primary whose every gap the secondary quietly heals trips neither
# the residual-gap rule nor either dead-man; the gap RATE is the only thing that reveals it.
#
# `would_mint` already carries `healed_seconds` (the seconds the secondary witnessed and COULD heal),
# so the signal exists in the ledger -- it just was not exported. `healable` counts it in both modes;
# `healed` stays honest and counts only what was actually written. The per-(pair,kind,hour) dedup
# matters because the flip to --mint re-ledgers the same hour as `minted`: one gap, not two.


def _totals_of(records: list[dict]) -> dict[str, float]:
    from cli.archive.command import _totals

    return _totals(records)


def test_healable_gap_seconds_counts_would_mint_so_the_gap_rate_is_visible_in_detect_only() -> None:
    records = [
        {"state": "would_mint", "pair": "BTC/EUR", "kind": "book", "hour": "2026-07-14T02:00:00+00:00", "healed_seconds": 120.0},
        {"state": "would_mint", "pair": "ETH/EUR", "kind": "book", "hour": "2026-07-14T02:00:00+00:00", "healed_seconds": 80.0},
    ]
    totals = _totals_of(records)

    assert totals["healable_seconds"] == 200.0, "detect-only must still expose the gap rate"
    assert totals["healed_seconds"] == 0.0, "nothing was minted, so nothing was healed -- keep that honest"


def test_healable_does_not_double_count_when_a_would_mint_hour_is_later_minted() -> None:
    """The flip to --mint re-ledgers the same hour. One gap, not two."""
    records = [
        {"state": "would_mint", "pair": "BTC/EUR", "kind": "book", "hour": "2026-07-14T02:00:00+00:00", "healed_seconds": 120.0},
        {"state": "minted", "pair": "BTC/EUR", "kind": "book", "hour": "2026-07-14T02:00:00+00:00", "healed_seconds": 120.0},
    ]
    totals = _totals_of(records)

    assert totals["healable_seconds"] == 120.0, "the same hour measured twice is still one gap"
    assert totals["healed_seconds"] == 120.0, "it WAS minted, so it was genuinely healed"
