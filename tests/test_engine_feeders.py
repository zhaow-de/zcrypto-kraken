import math
from datetime import datetime, timedelta

import pytest

from cli.engine.feeders import CycleStages, cancellation_ratio, replay_stages, stage_grosses
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash


def test_stage_grosses_sums_absolute_positions():
    sleeves = {"B": {"BTC": 0.10, "ETH": -0.04}, "A1": {"BTC": 0.02, "ETH": 0.0}, "A2": {"BTC": 0.0, "ETH": 0.06}}
    g = stage_grosses(sleeves)
    assert g["B"] == pytest.approx(0.14)
    assert g["A1"] == pytest.approx(0.02)
    assert g["A2"] == pytest.approx(0.06)


def test_cancellation_ratio_is_one_when_sleeves_agree():
    # Identical sleeves: the 1/3 combination reproduces them exactly, so nothing cancels.
    one = {"BTC": 0.09, "ETH": 0.03}
    ratio, combined_gross, mean_sleeve_gross = cancellation_ratio({"B": one, "A1": one, "A2": one})
    assert ratio == pytest.approx(1.0)
    assert combined_gross == pytest.approx(0.12)
    assert mean_sleeve_gross == pytest.approx(0.12)


def test_cancellation_ratio_below_one_when_sleeves_oppose():
    # B and A1 cancel on BTC; A2 is flat there. Combined BTC = 0, so gross drops.
    sleeves = {"B": {"BTC": 0.09}, "A1": {"BTC": -0.09}, "A2": {"BTC": 0.0}}
    ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(sleeves)
    assert combined_gross == pytest.approx(0.0)
    assert mean_sleeve_gross == pytest.approx(0.06)
    assert ratio == pytest.approx(0.0)


def test_cancellation_ratio_is_a_ratio_of_sums_not_a_mean_of_per_asset_ratios():
    # BTC cancels entirely while ETH agrees; the two definitions diverge sharply here.
    sleeves = {"B": {"BTC": 0.30, "ETH": 0.01}, "A1": {"BTC": -0.30, "ETH": 0.01}, "A2": {"BTC": 0.0, "ETH": 0.01}}
    ratio, combined_gross, mean_sleeve_gross = cancellation_ratio(sleeves)
    assert combined_gross == pytest.approx(0.01)
    assert mean_sleeve_gross == pytest.approx(0.21)
    assert ratio == pytest.approx(0.01 / 0.21)  # ~0.0476, not the 0.5 a per-asset mean would give


def test_cancellation_ratio_is_nan_on_a_flat_book():
    # All sleeves flat: the ratio is 0/0. Report NaN rather than inventing 1.0 or crashing.
    flat = {"BTC": 0.0}
    ratio, _, _ = cancellation_ratio({"B": flat, "A1": flat, "A2": flat})
    assert math.isnan(ratio)


def test_stage_identity_raises_when_the_recomputation_disagrees():
    from cli.engine.feeders import _check_stage_identity

    _check_stage_identity(0.5, {"BTC": 0.10}, {"BTC": 0.05}, cycle_ts="t")  # holds, no raise
    with pytest.raises(Exception, match="stage identity broken"):
        _check_stage_identity(0.5, {"BTC": 0.10}, {"BTC": 0.06}, cycle_ts="t")


# --- replay_stages: the metadata-vs-data reconciliation -----------------------------------------

CYCLE_TS = datetime(2026, 7, 10, 8, 0)
H4_TS = [datetime(2026, 7, 9, 20, 0), datetime(2026, 7, 10, 0, 0), datetime(2026, 7, 10, 4, 0)]
H4_CLOSES = [100.0, 101.0, 102.0]
DAILY_TS = [datetime(2026, 7, 7, 0, 0), datetime(2026, 7, 8, 0, 0), datetime(2026, 7, 9, 0, 0)]
DAILY_CLOSES = [50.0, 51.0, 52.0]
# What the reader actually hands back for the 4h grid: every stamp one bar later, so the data runs
# through cycle_ts itself -- look-ahead, behind metadata that still declares the honest boundary.
PEEKED_H4_TS = [t + timedelta(hours=4) for t in H4_TS]


def _peeked_h4_record() -> CycleRecord:
    """A record whose 4h metadata is honest -- so validate_record's no-peek invariant passes -- but
    whose content_hash is computed over the PEEKED data the reader returns, so the hash check passes
    too. Only the read-data-vs-declared-metadata reconciliation can catch it."""
    h4 = SnapshotEntry(
        pair="BTC",
        grid="240",
        n_bars=len(H4_TS),
        first_ts=H4_TS[0],
        last_ts=H4_TS[-1],  # == cycle_ts - 4h: the invariant is satisfied on paper
        content_hash=snapshot_content_hash(PEEKED_H4_TS, H4_CLOSES),
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
    return CycleRecord(
        schema_version=1,
        cycle_ts=CYCLE_TS,
        snapshots=(h4, daily),
        final_targets={"BTC": 0.1},
        started_at=CYCLE_TS,
        completed_at=CYCLE_TS + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )


def test_replay_stages_reconciles_read_data_against_its_journaled_metadata():
    record = _peeked_h4_record()

    def peeking_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(PEEKED_H4_TS), list(H4_CLOSES)
        return list(DAILY_TS), list(DAILY_CLOSES)

    # The premise: the hash check must PASS on this fixture, or the raise below would prove nothing
    # about the reconciliation.
    h4_entry = next(e for e in record.snapshots if e.grid == "240")
    assert snapshot_content_hash(PEEKED_H4_TS, H4_CLOSES) == h4_entry.content_hash

    with pytest.raises(Exception, match="disagrees with its own journaled metadata"):
        replay_stages(record, peeking_reader)
