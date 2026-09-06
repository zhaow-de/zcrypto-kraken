from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from cli.archive.settle import (
    CAPTURE_DIVERGENT,
    INTERIOR_MAX_SECONDS,
    LATE_MINT_HOURS,
    SETTLE_HOURS,
    UNDETERMINED,
    VENUE_SILENT,
    DarkWindow,
    EpisodeVerdict,
    classify_dark_episode,
    containing_dark_window,
    fleet_dark_windows,
    hour_path,
    is_late,
    is_total_loss,
    newest_hour,
    scan_hours,
    settled_hours,
    us_array,
    us_view,
)
from cli.capture.errors import CaptureError

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


def test_scan_hours_skips_a_year_directory_too_large_for_a_c_int(tmp_path):
    """A `2147483648` year directory is skipped, and the well-formed hour beside it is still found."""
    # `int()` is arbitrary-precision, so the throw is `datetime`'s C-int year conversion:
    # `datetime(2**31 - 1, ...)` raises ValueError but `datetime(2**31, ...)` raises OverflowError,
    # which an `except ValueError` does not catch — the scan dies instead of ignoring the directory.
    _final(tmp_path, "BTC/EUR", "book", H)
    oversized = tmp_path / "BTC" / "EUR" / "book" / str(2**31) / f"{H:%m}" / f"{H:%d}" / f"{H:%H}.parquet"
    oversized.parent.mkdir(parents=True)
    pl.DataFrame({"ts": [H]}).write_parquet(oversized)
    assert scan_hours(tmp_path, "book") == {"BTC/EUR": {H}}


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


def test_darkness_of_exactly_the_threshold_is_not_a_window():
    # The predicates must agree: `find_book_gaps` requires silence STRICTLY greater than its
    # threshold, so a window of exactly 30.0 s is not a gap on the way in. Booking it as residual
    # here would make it permanent loss that was never healable -- the one asymmetry that lets
    # `healed + residual` exceed the window it partitions.
    stamps = [_at(s) for s in range(0, 3600, 5) if not 600 < s < 630]
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
# `healed_gap_seconds_total` counts only `minted` records, so in a detect-only cycle the "chronically
# gappy primary" alarm would be pinned at 0 while looking like working alerting. A degrading primary
# whose every gap the secondary quietly heals trips neither the residual-gap rule nor either dead-man;
# the gap RATE is the only thing that reveals it. `would_mint` carries `healed_seconds` (the seconds
# the secondary witnessed and COULD heal), so `healable` counts it in both modes while `healed` stays
# honest and counts only what was actually written.


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
    assert totals["ledger_records"] == 2.0, "both ledger lines count, even the one the dedup `continue` skips"


# --- per-intersection-window booking (T0103) -------------------------------------------------------
#
# `fleet_dark_windows` finds the INTERSECTION -- the window in which every stream was silent -- and
# booking it x stream count under-books every stream but the one that returned first.


def test_the_containing_window_is_the_streams_own_silence_around_the_fleet_window():
    """The stream went quiet before the fleet did and came back after: its own window strictly
    contains the intersection, and that surplus is the loss the intersection cannot see."""
    stamps = [_at(100), _at(400)]  # this stream: silent 100 -> 400
    fleet = DarkWindow(start=_at(150), end=_at(300), seconds=150.0)  # the intersection

    own = containing_dark_window(stamps, fleet, hour_start=H, hour_end=HOUR_END)

    assert (own.start, own.end) == (_at(100), _at(400))
    assert own.seconds == 300.0


def test_the_binding_stream_gets_exactly_the_fleet_window():
    """The stream that returns FIRST defines the intersection's end, so its own window equals it --
    which is why the old booking was right for exactly one stream and short for all the others."""
    stamps = [_at(150), _at(300)]
    fleet = DarkWindow(start=_at(150), end=_at(300), seconds=150.0)

    own = containing_dark_window(stamps, fleet, hour_start=H, hour_end=HOUR_END)

    assert (own.start, own.end, own.seconds) == (_at(150), _at(300), 150.0)


def test_the_hour_bounds_are_edges_for_the_containing_window_too():
    """A stream that never recorded in this hour is dark across the whole of it."""
    fleet = DarkWindow(start=_at(150), end=_at(300), seconds=150.0)

    own = containing_dark_window([], fleet, hour_start=H, hour_end=HOUR_END)

    assert (own.start, own.end, own.seconds) == (H, HOUR_END, 3600.0)


def test_a_stream_that_ticked_inside_the_fleet_window_has_no_containing_window():
    """Impossible for a true fleet intersection -- the fleet window is built from the union of every
    stream's stamps, so a stamp inside it would have split it. Guarded rather than assumed: the
    caller must not silently book a window that does not exist."""
    stamps = [_at(150), _at(200), _at(300)]
    fleet = DarkWindow(start=_at(150), end=_at(300), seconds=150.0)

    assert containing_dark_window(stamps, fleet, hour_start=H, hour_end=HOUR_END) is None


# --- the venue-silence discriminator (spec 00096) -------------------------------------------------
#
# A booked window contains ZERO events by construction -- `fleet_dark_windows` runs over the union
# of both mirrors across every pair -- so the evidence lives in the INTERIOR span: the events
# BETWEEN adjacent booked windows, which exist precisely because some stream ticked there.


def _episode() -> list[DarkWindow]:
    """Two booked windows split by a lone interior event at t=500 -- the 2026-08-20 shape."""
    return [
        DarkWindow(start=_at(0), end=_at(500), seconds=500.0),
        DarkWindow(start=_at(500), end=_at(1000), seconds=500.0),
    ]


def test_mirrors_agreeing_on_the_interior_event_prove_the_venue_went_silent():
    # Both hosts recorded the SAME lone mid-episode message. `ts` is Kraken's own payload timestamp
    # (cli/capture/command.py), never local receipt time, so identical stamps mean both hosts were
    # connected and receiving DURING the episode -- a host that was not receiving cannot invent one.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": [(_at(500), "update")]}},
    )
    assert verdict.verdict == VENUE_SILENT
    assert verdict.interior_updates == 1
    assert verdict.pairs_agreeing == 1
    assert verdict.divergent_pairs == ()


def test_a_mirror_that_missed_an_interior_event_is_a_capture_finding():
    # The secondary lacks what the primary got: one host missed a message the venue sent. That is
    # capture-side, and it must NEVER read as venue silence.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": []}},
    )
    assert verdict.verdict == CAPTURE_DIVERGENT
    assert verdict.divergent_pairs == ("BTC/EUR",)


def test_divergence_on_any_pair_outranks_agreement_on_every_other():
    # Fail-closed ordering: one mirror missing one message is a finding in its own right, and must
    # not be masked by eleven other pairs agreeing.
    verdict = classify_dark_episode(
        _episode(),
        {
            "BTC/EUR": {"primary": [(_at(500), "update")], "secondary": [(_at(500), "update")]},
            "ETH/EUR": {"primary": [(_at(500), "update")], "secondary": []},
        },
    )
    assert verdict.verdict == CAPTURE_DIVERGENT
    assert verdict.divergent_pairs == ("ETH/EUR",)


def test_a_single_booked_window_has_no_interior_and_is_undetermined():
    # Nothing split the episode, so there is no interior span at all. THE fail-closed default: a
    # simultaneous both-host outage looks exactly like this, and must not be excused.
    one = [DarkWindow(start=_at(0), end=_at(1000), seconds=1000.0)]
    verdict = classify_dark_episode(one, {"BTC/EUR": {"primary": [], "secondary": []}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_updates == 0


def test_bracketing_events_never_promote_to_venue_silent():
    # D3. Both mirrors agree on the events immediately BEFORE and AFTER the episode -- which proves
    # only that both hosts were healthy either side of it. A both-host outage that self-healed
    # produces exactly this signature, so the verdict stays undetermined.
    one = [DarkWindow(start=_at(100), end=_at(1000), seconds=900.0)]
    verdict = classify_dark_episode(
        one,
        {
            "BTC/EUR": {
                "primary": [(_at(50), "update"), (_at(1100), "update")],
                "secondary": [(_at(50), "update"), (_at(1100), "update")],
            }
        },
    )
    assert verdict.verdict == UNDETERMINED


def test_a_pair_missing_a_mirror_entirely_contributes_no_evidence():
    # An unreadable/absent segment is not a divergence: there is nothing to compare against.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": None}},
    )
    assert verdict.verdict == UNDETERMINED
    assert verdict.pairs_skipped == 1
    assert verdict.divergent_pairs == ()


def test_a_snapshot_only_interior_never_reads_as_venue_silence():
    # D2a -- THE constructible false positive. A regression that breaks update-row writing while
    # leaving book_snapshot handling intact makes BOTH hosts (same image, by the canary rule)
    # write identical sparse snapshot rows. A snapshot is a periodic/resubscribe artifact and
    # proves nothing about a live feed, so this must NOT read as the venue going quiet.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "snapshot")], "secondary": [(_at(500), "snapshot")]}},
    )
    assert verdict.verdict == UNDETERMINED
    # the counts are still recorded, so the record explains ITSELF without re-running anything
    assert verdict.interior_snapshots == 1
    assert verdict.interior_updates == 0


def test_one_interior_update_is_enough_even_beside_snapshots():
    verdict = classify_dark_episode(
        _episode(),
        {
            "BTC/EUR": {
                "primary": [(_at(500), "snapshot"), (_at(500), "update")],
                "secondary": [(_at(500), "snapshot"), (_at(500), "update")],
            }
        },
    )
    assert verdict.verdict == VENUE_SILENT
    assert verdict.interior_updates == 1
    assert verdict.interior_snapshots == 1


def test_two_disjoint_blips_in_one_hour_never_promote_on_the_healthy_middle():
    # F3, constructed. A both-host crash-loop (same image on both hosts by the canary rule, systemd
    # restart backoff) makes TWO fleet-dark windows far apart. The dense healthy traffic between them
    # is bracketing evidence for each blip -- and each blip alone is exactly the single-window shape
    # D3 says must stay undetermined. The silence must DOMINATE the episode, or it is not one episode.
    far = [DarkWindow(start=_at(300), end=_at(340), seconds=40.0), DarkWindow(start=_at(3000), end=_at(3040), seconds=40.0)]
    healthy = [(_at(t), "update") for t in range(341, 3000, 2)]
    verdict = classify_dark_episode(far, {"BTC/EUR": {"primary": healthy, "secondary": list(healthy)}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_updates == 1330  # it SAW them; it refused to be convinced by them
    assert verdict.interior_seconds > sum(w.seconds for w in far)


def test_a_pair_whose_mirror_has_not_landed_caps_the_verdict():
    # F4, constructed. Single-mirror hours exist BY CONSTRUCTION (a pair is added primary-first), and
    # `both_streams_silent` is decided ONCE -- so a mirror arriving next cycle that would have shown
    # divergence could never demote a venue_silent already written. Excusing on partial evidence is
    # the forbidden direction, so an unlanded mirror caps the verdict.
    verdict = classify_dark_episode(
        _episode(),
        {
            "BTC/EUR": {"primary": [(_at(500), "update")], "secondary": [(_at(500), "update")]},
            "ETH/EUR": {"primary": [(_at(500), "update")], "secondary": None},
        },
    )
    assert verdict.verdict == UNDETERMINED
    assert verdict.pairs_skipped == 1
    assert verdict.pairs_agreeing == 1


def test_three_or_more_windows_are_never_classified():
    # THE re-derivation. With 3+ windows there is no way to tell which gaps are the episode's own
    # sputtering and which are healthy traffic separating unrelated incidents -- and an aggregate
    # dominance check lets one large genuine outage's dark time carry an unrelated pair of disjoint
    # blips to venue_silent.
    three = [
        DarkWindow(start=_at(0), end=_at(3000), seconds=3000.0),
        DarkWindow(start=_at(3001), end=_at(3002), seconds=1.0),
        DarkWindow(start=_at(3599), end=_at(3600), seconds=1.0),
    ]
    verdict = classify_dark_episode(
        three,
        {"BTC/EUR": {"primary": [(_at(3000), "update")], "secondary": [(_at(3000), "update")]}},
    )
    assert verdict.verdict == UNDETERMINED


def test_a_long_healthy_interior_is_two_incidents_not_one_episode():
    # The survivor of a per-gap dominance rule: 600 s dark, 1,000 s of PERFECTLY HEALTHY traffic on
    # both mirrors, 600 s dark. Relative dominance passes it (1,000 < 1,200); the absolute bound
    # refuses it. Interior evidence is bracket evidence -- it proves both hosts were receiving
    # BETWEEN the darks, never during them -- so only a BRIEF interior makes a synchronised two-host
    # failure-and-recovery implausible enough to weigh.
    two = [DarkWindow(start=_at(0), end=_at(600), seconds=600.0), DarkWindow(start=_at(1600), end=_at(2200), seconds=600.0)]
    healthy = [(_at(t), "update") for t in range(601, 1600)]
    verdict = classify_dark_episode(two, {"BTC/EUR": {"primary": healthy, "secondary": list(healthy)}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_seconds == 1000.0
    assert verdict.interior_seconds > INTERIOR_MAX_SECONDS


def test_a_healthy_hour_with_no_windows_is_undetermined_and_never_classifies():
    # THE true-positive: a production-shaped healthy hour books nothing, so the classifier must not
    # manufacture a verdict. An always-classifying implementation fails here.
    verdict = classify_dark_episode(
        [],
        {
            "BTC/EUR": {
                "primary": [(_at(s), "update") for s in range(0, 3600, 5)],
                "secondary": [(_at(s), "update") for s in range(0, 3600, 5)],
            }
        },
    )
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_updates == 0


# --- the int64-microsecond derivation (spec 00097 D3) ---------------------------------------------
#
# Both fleet-dark functions now run on int64-microsecond arrays so the reconcile cycle stops scaling
# with the hour's message count. The datetime path is the equivalence anchor: what any hour DECIDES
# and BOOKS must be byte-identical to what the list-of-datetimes implementation decided, because the
# seconds land in `residual_gap_seconds_total` -- monotone, and unwalkbackable.


def test_fleet_dark_windows_accepts_us_arrays_identically():
    stamps = [_at(0), _at(10), _at(600), _at(3600)]
    as_dt = fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    as_us = fleet_dark_windows(us_array(stamps), hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert as_dt == as_us and as_dt  # identical AND non-empty (a vacuous equality proves nothing)


def test_containing_dark_window_accepts_us_arrays_identically():
    stamps = [_at(0), _at(100), _at(700)]
    window = fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)[0]
    a = containing_dark_window(stamps, window, hour_start=H, hour_end=HOUR_END)
    b = containing_dark_window(us_array(stamps), window, hour_start=H, hour_end=HOUR_END)
    assert a == b and a is not None


# Microsecond widths whose correctly-rounded quotient `us / 1e6` differs in the last bit from the
# product `us * 1e-6`; no whole-second width does, which is why these are not round numbers.
_DIVERGENT_US = (30_000_001, 2_999_999_999, 3_599_999_999)


@pytest.mark.parametrize("width_us", _DIVERGENT_US)
def test_fleet_dark_window_seconds_is_the_microsecond_quotient_not_the_reciprocal_product(width_us):
    """`diff_us / 1e6`, never `diff_us * 1e-6`: 1e-6 is not exactly representable, so the product is
    a DIFFERENT float from the quotient the datetime path (`timedelta.total_seconds()`, an integer
    division by 10**6) produced. These seconds are booked into a monotone counter, so an off-by-one-
    ulp booking can never be walked back -- and the swap is invisible to every whole-second test."""
    mark = H + timedelta(microseconds=width_us)
    window = fleet_dark_windows([mark], hour_start=H, hour_end=HOUR_END, min_seconds=30.0)[0]

    assert (window.start, window.end) == (H, mark)
    assert window.seconds.hex() == (width_us / 1_000_000).hex()
    assert window.seconds == (window.end - window.start).total_seconds()


@pytest.mark.parametrize("width_us", _DIVERGENT_US)
def test_containing_dark_window_seconds_is_the_microsecond_quotient_too(width_us):
    """The same pin on the second `/1e6` in this module -- this one sizes ONE stream's own silence,
    which is what actually reaches `residual_gap_seconds_total` per stream."""
    start = H + timedelta(microseconds=1)
    end = start + timedelta(microseconds=width_us)
    fleet = DarkWindow(start=start + timedelta(microseconds=10), end=end - timedelta(microseconds=10), seconds=0.0)

    own = containing_dark_window([start, end], fleet, hour_start=H, hour_end=HOUR_END)

    assert (own.start, own.end) == (start, end)
    assert own.seconds.hex() == (width_us / 1_000_000).hex()
    assert own.seconds == (own.end - own.start).total_seconds()


@pytest.mark.parametrize("width_us", _DIVERGENT_US)
def test_the_two_input_paths_agree_at_microsecond_resolution(width_us):
    """The equivalence anchor at the resolution where the two paths COULD differ: whole seconds
    survive any arithmetic, sub-second widths do not."""
    stamps = [H + timedelta(microseconds=width_us)]
    assert fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == fleet_dark_windows(
        us_array(stamps), hour_start=H, hour_end=HOUR_END, min_seconds=30.0
    )


def test_us_array_passes_an_int64_array_through_untouched():
    arr = np.array([1, 2, 3], dtype=np.int64)
    out = us_array(arr)
    assert out is arr  # no defensive copy: callers hand it a fresh array they no longer own


def test_us_array_converts_datetimes_exactly():
    stamps = [H, H + timedelta(microseconds=1), HOUR_END]
    assert us_array(stamps).tolist() == [1784192400000000, 1784192400000001, 1784196000000000]


@pytest.mark.parametrize("dtype", ["datetime64[ns]", "datetime64[us]", "float64", "int32"])
def test_us_array_refuses_an_ndarray_that_is_not_already_int64_microseconds(dtype):
    """THE unit trap, the same one `_message_ts` refuses: `astype(np.int64)` on a `datetime64[ns]`
    array yields NANOSECONDS, which mix with microsecond hour bounds in one `edges` array. Measured
    consequence of the `ns` direction on the sibling path: a fabricated ~1.78e18 us window anchored
    in 1970. A caller owes the conversion; guessing it here is how the two scales meet silently."""
    with pytest.raises(CaptureError, match="int64 microseconds"):
        us_array(np.array([0, 1], dtype=dtype))


# --- `us_view`: the column-unit guard the hot loop leans on ---------------------------------------
#
# `.view(np.int64)` reads the column's OWN unit, so `us_array` cannot catch a wrong one -- by then
# the array is already int64. Nothing downstream catches it either: `command.py` books the fleet-dark
# residual BEFORE the heal block ever hands the same frame to `_message_ts`, so a `ms` column would
# shrink a real outage 1000x below the threshold and book a fabricated 1970-anchored window into a
# counter that can never be walked back.


def _book_ts(offsets: list[float], *, unit: str = "us", tz: str | None = "UTC") -> pl.Series:
    stamps = [None if o is None else _at(o) for o in offsets]
    return pl.Series("ts", stamps, dtype=pl.Datetime("us", "UTC")).cast(pl.Datetime(unit, tz))


def test_us_view_reads_a_production_shaped_microsecond_column_exactly():
    """The true positive: the dtype `segment_writer` actually writes, at microsecond resolution."""
    offsets = [0.0, 10.000001, 599.999999, 3599.999999]
    out = us_view(_book_ts(offsets))
    assert out.dtype == np.int64
    assert out.tolist() == us_array([_at(o) for o in offsets]).tolist()


def test_a_microsecond_column_drives_the_same_windows_as_the_datetime_path():
    """The equivalence anchor at the call site's own granularity: same decision, same booking."""
    offsets = [0.0, 10.0, 600.0, 3600.0]
    stamps = [_at(o) for o in offsets]
    assert fleet_dark_windows(us_view(_book_ts(offsets)), hour_start=H, hour_end=HOUR_END, min_seconds=30.0) == (
        fleet_dark_windows(stamps, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    )


@pytest.mark.parametrize(("unit", "tz"), [("ms", "UTC"), ("ns", "UTC"), ("us", None)])
def test_us_view_refuses_any_column_that_is_not_microseconds_utc(unit, tz):
    with pytest.raises(CaptureError, match="not Datetime"):
        us_view(_book_ts([0.0, 3300.0], unit=unit, tz=tz))


def test_a_millisecond_column_would_book_a_healthy_hour_as_wholly_dark():
    """Why the refusal is typed and not a cast: the `ms` direction does not raise on its own. Its
    integers are 1000x too small for the microsecond hour bounds, so on THIS path every real stamp
    falls below `hour_start` and is clamped away -- and a busy hour with one 40 s hole is booked as
    3600 s of fleet darkness per stream, into a monotone counter that cannot be walked back."""
    offsets = [float(s) for s in range(0, 3600, 10) if not 600 < s < 640]
    honest = fleet_dark_windows(us_view(_book_ts(offsets)), hour_start=H, hour_end=HOUR_END, min_seconds=30.0)
    assert [w.seconds for w in honest] == [40.0]

    raw = _book_ts(offsets, unit="ms").to_numpy().view(np.int64)  # what us_view exists to stop
    assert [w.seconds for w in fleet_dark_windows(raw, hour_start=H, hour_end=HOUR_END, min_seconds=30.0)] == [3600.0]


def test_us_view_refuses_a_null_ts():
    with pytest.raises(CaptureError, match="null ts"):
        us_view(_book_ts([0.0, None, 3300.0]))
