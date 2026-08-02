import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.engine.feeders import (
    CycleStages,
    _render_decompose,
    cancellation_ratio,
    decompose_payload,
    decompose_report,
    replay_stages,
    stage_grosses,
)
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


# --- decompose: the attribution table -----------------------------------------------------------


def test_decompose_payload_reports_every_stage_and_the_ratios():
    stages = [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 12, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.12}, "A1": {"BTC": 0.06}, "A2": {"BTC": 0.0}},
            combined={"BTC": 0.06},
            capped={"BTC": 0.06},
            final={"BTC": 0.03},
            multiplier=0.5,
            closes={"BTC": 50000.0},
            cap_bound=False,
        )
    ]
    payload = decompose_payload(stages)
    row = payload["cycles"][0]
    assert row["combined_gross"] == pytest.approx(0.06)
    assert row["capped_gross"] == pytest.approx(0.06)
    assert row["final_gross"] == pytest.approx(0.03)
    assert row["multiplier"] == pytest.approx(0.5)
    assert row["n_active"] == 1
    # mean sleeve gross = (0.12 + 0.06 + 0.0)/3 = 0.06; combined = 0.06 -> ratio 1.0
    assert row["cancellation_ratio"] == pytest.approx(1.0)
    # EXACTLY 1.0, not approx: the caps did not bind, and numerator and denominator are summed off
    # the same floats. An approx here would pass a mixed-basis ratio reporting gross GROWING
    # through the caps -- which cannot happen.
    assert row["capped_ratio"] == 1.0
    assert row["governed_ratio"] == pytest.approx(0.5)  # == the governor multiplier
    assert payload["n_cycles"] == 1


def _two_asymmetric_cycles() -> list[CycleStages]:
    """Cycle 1: sleeves agree, governor off. Cycle 2: sleeves cancel, governor halves.

    Chosen so median-of-ratios and ratio-of-medians disagree on BOTH the sleeve->combined and the
    capped->final ratios; a single-cycle fixture cannot discriminate, since there they coincide.
    """
    return [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 0, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.12}, "A1": {"BTC": 0.12}, "A2": {"BTC": 0.12}},
            combined={"BTC": 0.12},
            capped={"BTC": 0.12},
            final={"BTC": 0.12},
            multiplier=1.0,
            closes={"BTC": 100.0},
            cap_bound=False,
        ),
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 4, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.09}, "A1": {"BTC": -0.09}, "A2": {"BTC": 0.0}},
            combined={"BTC": 0.0},
            capped={"BTC": 0.0},
            final={"BTC": 0.0},
            multiplier=0.5,
            closes={"BTC": 100.0},
            cap_bound=False,
        ),
    ]


def test_stage_ratios_use_the_median_of_per_cycle_ratios():
    # Two asymmetric cycles: median-of-ratios and ratio-of-medians differ, so this pins the basis.
    # A single-cycle fixture cannot -- there the two definitions coincide.
    payload = decompose_payload(_two_asymmetric_cycles())
    # per-cycle cancellation ratios are 1.0 and 0.0 -> median 0.5.
    # ratio-of-medians would be median(combined)/median(mean_sleeve) = 0.06/0.09 = 0.667.
    assert payload["median"]["cancellation_ratio"] == pytest.approx(0.5)
    # per-cycle multipliers are 1.0 and 0.5 -> median 0.75.
    # ratio-of-medians would be median(final)/median(capped) = 0.06/0.06 = 1.0.
    assert payload["median"]["governed_ratio"] == pytest.approx(0.75)
    # cycle 1's caps do not bind, so its capped ratio is EXACTLY 1.0 -- the shared-basis pin.
    assert payload["cycles"][0]["capped_ratio"] == 1.0
    # cycle 2's combined gross is 0, so its capped ratio is NaN and contributes no evidence about
    # the caps -- filtered out rather than counted as the 1.0 a flat cycle would fake.
    assert math.isnan(payload["cycles"][1]["capped_ratio"])
    assert payload["median"]["capped_ratio"] == 1.0


def test_decompose_render_names_each_consecutive_stage_ratio():
    text = _render_decompose(decompose_payload(_two_asymmetric_cycles()))
    assert "MEDIAN" in text
    # Each value pinned to ITS OWN label: asserting the labels alone would pass a summary whose
    # three ratios were rendered against the wrong lines.
    for label, value in (("sleeve -> combined", "0.500"), ("combined -> capped", "1.000"), ("capped -> final", "0.750")):
        line = next(ln for ln in text.splitlines() if label in ln)
        assert value in line
    assert "cap-bound cycles: 0 of 2" in text


def test_decompose_report_counts_a_record_that_fails_to_replay():
    # A silently dropped cycle would bias every aggregate: the failure must be named and counted.
    record = _peeked_h4_record()

    def peeking_reader(entry: SnapshotEntry):
        if entry.grid == "240":
            return list(PEEKED_H4_TS), list(H4_CLOSES)
        return list(DAILY_TS), list(DAILY_CLOSES)

    text, payload = decompose_report([record], peeking_reader)
    assert payload["n_cycles"] == 0
    assert payload["n_failed"] == 1
    assert payload["failures"][0]["cycle_ts"] == CYCLE_TS.isoformat()
    assert "disagrees with its own journaled metadata" in payload["failures"][0]["error"]
    assert "failed to replay: 1" in text
