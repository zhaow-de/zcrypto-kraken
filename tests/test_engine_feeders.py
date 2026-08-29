import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.cycle import _expand_to_basket
from cli.engine.feeders import (
    CycleStages,
    _render_accumulation,
    _render_decompose,
    accumulation_payload,
    accumulation_report,
    cancellation_ratio,
    decompose_payload,
    decompose_report,
    load_minimums,
    replay_stages,
    stage_grosses,
)
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json
from cli.engine.store import BASKET
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig
from tests import basket_fixture


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


def _two_asset_record(final_targets: dict[str, float]) -> tuple[CycleRecord, object]:
    """A CycleRecord carrying both grids for BTC and ETH on the module's shared calendars, so
    `replay_stages`'s hash, metadata and no-peek checks all pass and the builder is the only thing
    left to fake. Returns (record, reader)."""
    entries = []
    for pair in ("BTC", "ETH"):
        entries.append(
            SnapshotEntry(
                pair=pair,
                grid="240",
                n_bars=len(H4_TS),
                first_ts=H4_TS[0],
                last_ts=H4_TS[-1],
                content_hash=snapshot_content_hash(H4_TS, H4_CLOSES),
                path=f"{pair}240",
            )
        )
        entries.append(
            SnapshotEntry(
                pair=pair,
                grid="1440",
                n_bars=len(DAILY_TS),
                first_ts=DAILY_TS[0],
                last_ts=DAILY_TS[-1],
                content_hash=snapshot_content_hash(DAILY_TS, DAILY_CLOSES),
                path=f"{pair}1440",
            )
        )
    record = CycleRecord(
        schema_version=1,
        cycle_ts=CYCLE_TS,
        snapshots=tuple(entries),
        final_targets=final_targets,
        started_at=CYCLE_TS,
        completed_at=CYCLE_TS + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )

    def reader(entry: SnapshotEntry):
        return (list(DAILY_TS), list(DAILY_CLOSES)) if entry.grid == "1440" else (list(H4_TS), list(H4_CLOSES))

    return record, reader


def test_replay_stages_identity_holds_when_a_whole_book_limit_binds(monkeypatch):
    """The forming-row recomputation must run the builder's WHOLE stack -- per-asset caps AND the
    §10 whole-book limits. Stopping at the caps agrees only while nothing binds; the first cycle a
    limit does bind, `stage identity broken` fires on a cycle the engine got exactly right, i.e.
    the alarm inverts and calls the engine broken precisely when the risk layer is doing its job."""
    import types

    import cli.engine.feeders as feeders
    from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, apply_whole_book_limits
    from cli.risk import apply_position_caps

    # Two assets at a 100% per-asset long cap: the caps do NOT clip, so the ONLY thing that can move
    # the book is the whole-book stack -- gross 2.0 breaches the 1.5x soft cap, then net 1.5
    # breaches the +1.0 band.
    cfg = CrossfreqSystemConfig(assets=("BTC", "ETH"), long_cap=1.0, short_cap=0.5)
    n = 1
    mult = [1.0, 0.8]
    sleeves = {name: {a: [1.0] * (n + 1) for a in cfg.assets} for name in ("B", "A1", "A2")}

    third = 1 / 3
    combined = {
        a: [third * sleeves["B"][a][k] + third * sleeves["A1"][a][k] + third * sleeves["A2"][a][k] for k in range(n + 1)]
        for a in cfg.assets
    }
    capped = apply_position_caps(combined, long_cap=cfg.long_cap, short_cap=cfg.short_cap)
    limited = apply_whole_book_limits(capped)
    final_targets = {a: [mult[k] * limited[a][k] for k in range(n + 1)] for a in cfg.assets}

    # The premise: without this the identity below would hold for the wrong reason.
    assert limited != capped, "the whole-book limits must actually bind, or this test proves nothing"
    assert capped == combined, "the per-asset caps must NOT clip here, or the limits are not isolated"

    fake = types.SimpleNamespace(
        final_targets=final_targets,
        multipliers=mult,
        sleeve_positions=sleeves,
        n_periods=n,
    )
    monkeypatch.setattr(feeders, "build_crossfreq_system_fast", lambda *a, **kw: fake)

    record, reader = _two_asset_record({a: final_targets[a][n] for a in cfg.assets})
    stages = replay_stages(record, reader, config=cfg)  # must not raise

    assert stages.final == {a: final_targets[a][n] for a in cfg.assets}
    assert stages.cap_bound is False  # only the whole-book limits bit
    # What the caps-only recomputation used to compare against -- it disagrees, which is why the
    # pre-fix code raised here.
    assert all(mult[n] * capped[a][n] != stages.final[a] for a in cfg.assets)


# --- decompose: the attribution table -----------------------------------------------------------


def test_decompose_payload_reports_every_stage_and_the_ratios():
    stages = [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 12, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.12}, "A1": {"BTC": 0.06}, "A2": {"BTC": 0.0}},
            combined={"BTC": 0.06},
            capped={"BTC": 0.06},
            limited={"BTC": 0.06},  # no whole-book limit binds in this fixture
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
            limited={"BTC": 0.12},  # no whole-book limit binds in this fixture
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
            limited={"BTC": 0.0},  # no whole-book limit binds in this fixture
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
    # `capped -> limited` is the whole-book limits' own share and `limited -> final` the governor's.
    # Before they were split, the governor's column carried both, so a binding limit would have been
    # reported as the governor de-levering -- the one event the limit-bound counter exists to name.
    for label, value in (
        ("sleeve -> combined", "0.500"),
        ("combined -> capped", "1.000"),
        ("capped -> limited", "1.000"),
        ("limited -> final", "0.750"),
    ):
        line = next(ln for ln in text.splitlines() if label in ln)
        assert value in line
    assert "capped -> final" not in text, "the merged label attributes the limits' share to the governor"
    assert "cap-bound cycles: 0 of 2" in text


def test_a_binding_whole_book_limit_is_attributed_to_the_limits_not_the_governor():
    """The non-degenerate case: `limited` < `capped`, so the two shares differ.

    Every other fixture has no limit binding, where `capped -> limited` is 1.000 and the merged
    `capped -> final` label happened to read correctly. This is the cycle that separates them --
    the limits take a quarter of the book and the governor half, and each share must land on its
    own line. Under the old single column the governor would have been reported at 0.375, i.e.
    de-levering twice as hard as it did.
    """
    stages = [
        CycleStages(
            cycle_ts=datetime(2026, 8, 1, 12, tzinfo=UTC),
            sleeve_positions={"B": {"BTC": 0.16}, "A1": {"BTC": 0.16}, "A2": {"BTC": 0.16}},
            combined={"BTC": 0.16},
            capped={"BTC": 0.16},
            limited={"BTC": 0.12},  # a whole-book limit takes a quarter
            final={"BTC": 0.06},  # the governor then halves what the limits left
            multiplier=0.5,
            closes={"BTC": 50000.0},
            cap_bound=False,
        )
    ]
    payload = decompose_payload(stages)
    row = payload["cycles"][0]
    assert row["limited_gross"] == pytest.approx(0.12)
    assert row["limited_ratio"] == pytest.approx(0.75)
    assert row["governed_ratio"] == pytest.approx(0.5)
    # The shares must not be equal here, or this fixture proves nothing the degenerate one did not.
    assert row["limited_ratio"] != pytest.approx(row["governed_ratio"])

    text = _render_decompose(payload)
    limits_line = next(ln for ln in text.splitlines() if "capped -> limited" in ln)
    governor_line = next(ln for ln in text.splitlines() if "limited -> final" in ln)
    assert "0.750" in limits_line
    assert "0.500" in governor_line


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


# --- accumulation: the venue-minimum drift floor -------------------------------------------------


def _stage(ts, weight, close):
    return CycleStages(
        cycle_ts=ts,
        sleeve_positions={s: {"BTC": 0.0} for s in ("B", "A1", "A2")},
        combined={"BTC": 0.0},
        capped={"BTC": 0.0},
        limited={"BTC": 0.0},  # no whole-book limit binds in this fixture
        final={"BTC": weight},
        multiplier=1.0,
        closes={"BTC": close},
        cap_bound=False,
    )


def test_delta_below_ordermin_is_not_placed_and_accumulates():
    # target 0.001 BTC/cycle against an ordermin of 0.005: nothing places until it crosses.
    stages = [_stage(datetime(2026, 8, 1, h, tzinfo=UTC), 0.001 * (i + 1), 1000.0) for i, h in enumerate((0, 4, 8, 12, 16, 20))]
    payload = accumulation_payload(stages, {"BTC": (0.005, 0.45)}, [1000.0])
    placed = [c["placed"] for c in payload["by_nav"][1000.0]["cycles"]]
    assert placed[:4] == [False, False, False, False]  # 1..4 units of 0.001 < 0.005
    assert placed[4] is True  # the 5th crosses the floor
    assert payload["by_nav"][1000.0]["cycles"][4]["drift_eur"] == pytest.approx(0.0)


def test_costmin_refuses_a_delta_that_clears_the_quantity_floor():
    # target_qty = 0.1*1.0/0.10 = 1.0 unit: clears ordermin 0.5, but is worth EUR 0.10 < costmin.
    # (An earlier draft used weight=1.0, giving 10 units worth EUR 1.00 -- which places, so the
    # test was red against correct code. The arithmetic is the test here; check it, don't eyeball.)
    stages = [_stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 0.1, 0.10)]
    payload = accumulation_payload(stages, {"BTC": (0.5, 0.45)}, [1.0])
    assert payload["by_nav"][1.0]["cycles"][0]["placed"] is False


def test_a_price_move_alone_changes_drift_with_no_order_placed():
    # THE HELD POSITION MUST BE NONZERO or this test proves nothing: at held_qty=0 the drift is
    # target_qty*close = weight*NAV, the close CANCELS, and a EUR-denominated held state gives
    # byte-identical output. So: cycle 1 places (held=10.0 units), then the close moves by less
    # than the floor, so cycle 2 places nothing and its drift is pure re-pricing.
    stages = [
        _stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 1.0, 100.0),
        _stage(datetime(2026, 8, 1, 4, tzinfo=UTC), 1.0, 100.5),
    ]
    payload = accumulation_payload(stages, {"BTC": (0.1, 0.0)}, [1000.0])
    cycles = payload["by_nav"][1000.0]["cycles"]
    assert cycles[0]["placed"] is True
    assert cycles[0]["drift_eur"] == pytest.approx(0.0)  # placed -> exactly on target
    assert cycles[1]["placed"] is False  # |delta| ~ 0.0498 < ordermin 0.1
    assert cycles[1]["target_qty"]["BTC"] == pytest.approx(1000.0 / 100.5)
    # held 10.0 units vs target ~9.9502 -> ~0.0498 units * 100.5 ~= EUR 5.00 of pure re-pricing.
    # A EUR-denominated held state would report 0.0 here: it would carry held_eur = 1000.0 from
    # cycle 1, meet target_eur = weight*NAV = 1000.0 again, and see no delta at all.
    assert cycles[1]["drift_eur"] == pytest.approx(5.0, abs=0.05)


def test_an_unplaced_asset_cycle_always_sits_below_its_floor():
    # The true invariant (spec Verification). NAV-monotonicity is NOT one and must not be asserted:
    # held histories diverge across NAV rungs, so a lower NAV just after placing can beat a higher
    # one carrying a fresh sub-floor residual.
    stages = [_stage(datetime(2026, 8, 1, h, tzinfo=UTC), 0.001 * (i + 1), 100.0) for i, h in enumerate((0, 4, 8, 12))]
    payload = accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [1000.0])
    for cycle in payload["by_nav"][1000.0]["cycles"]:
        if not cycle["placed"]:
            assert cycle["drift_eur"] < max(0.05 * 100.0, 0.45)


def test_the_accumulation_replays_chronologically_whatever_order_it_is_handed():
    # The policy carries held_qty across cycles, so the order is load-bearing, not cosmetic. Every
    # other fixture in this file is already sorted, so nothing else would notice the sort going
    # missing: reversed input must still produce the forward answer.
    stages = [_stage(datetime(2026, 8, 1, h, tzinfo=UTC), 0.001 * (i + 1), 1000.0) for i, h in enumerate((0, 4, 8, 12, 16, 20))]
    minimums = {"BTC": (0.005, 0.45)}
    assert accumulation_payload(list(reversed(stages)), minimums, [1000.0]) == accumulation_payload(stages, minimums, [1000.0])


def test_accumulation_refuses_a_zero_nav():
    stages = [_stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 0.1, 100.0)]
    with pytest.raises(Exception, match="finite and positive"):
        accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [0.0])


def test_accumulation_refuses_a_negative_nav():
    # The worse of the two, because it never raises on its own: a negative NAV signs every
    # drift_bps, and those are what the reported median and p95 -- the gate band -- are read from.
    stages = [_stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 0.1, 100.0)]
    with pytest.raises(Exception, match="finite and positive"):
        accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [1000.0, -1000.0])


def test_accumulation_raises_when_a_traded_asset_has_no_floor():
    # A silently absent floor would place every delta and understate the drift to zero.
    stages = [_stage(datetime(2026, 8, 1, 0, tzinfo=UTC), 0.1, 100.0)]
    with pytest.raises(Exception, match="no venue minimums"):
        accumulation_payload(stages, {"ETH": (0.001, 0.45)}, [1000.0])


# --- accumulation: the weekly aggregation --------------------------------------------------------

# 2026-07-13 00:00 is the Monday of ISO week 2026-W29 -- the journal's own first full week.
WEEK29_MONDAY = datetime(2026, 7, 13, tzinfo=UTC)


def _weekly_payload(n_cycles: int) -> dict:
    stages = [_stage(WEEK29_MONDAY + timedelta(hours=4 * i), 0.0, 100.0) for i in range(n_cycles)]
    return accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [1000.0])


def test_weekly_rows_flag_a_short_week_and_report_no_weekly_p95():
    # 45 four-hourly cycles from a Monday: 42 fill W29 exactly, 3 spill into W30.
    weeks = _weekly_payload(45)["by_nav"][1000.0]["weeks"]
    assert [(w["iso_year"], w["iso_week"], w["n_cycles"]) for w in weeks] == [(2026, 29, 42), (2026, 30, 3)]
    assert weeks[0]["partial"] is False  # 42 = 6 cycles/day x 7 days: the full complement
    assert weeks[1]["partial"] is True
    # The flag is DERIVED from the cycle count, never a hardcoded week number.
    assert _weekly_payload(41)["by_nav"][1000.0]["weeks"][0]["partial"] is True
    # No weekly p95: 4 weeks cannot support a percentile, and this number becomes a gate band.
    assert not any("p95" in key for w in weeks for key in w)


def test_per_cycle_median_and_p95_are_reported_over_the_full_window():
    stages = [_stage(WEEK29_MONDAY + timedelta(hours=4 * i), 0.001 * (i + 1), 100.0) for i in range(20)]
    nav_payload = accumulation_payload(stages, {"BTC": (0.05, 0.45)}, [1000.0])["by_nav"][1000.0]
    drifts = sorted(c["drift_bps"] for c in nav_payload["cycles"])
    assert nav_payload["median_drift_bps"] == pytest.approx((drifts[9] + drifts[10]) / 2)
    # Nearest rank over 20 points: ceil(0.95*20) = 19 -> the 19th smallest, an OBSERVED value.
    assert nav_payload["p95_drift_bps"] == pytest.approx(drifts[18])


def test_accumulation_render_stamps_the_minimums_and_refuses_a_weekly_p95():
    payload = _weekly_payload(45)
    payload["minimums_fetched_at"] = "2026-07-07T03:29:00+00:00"
    text = _render_accumulation(payload)
    assert "2026-07-07" in text  # spec D8: the floors move; the table says when it was read
    assert "2026-W29" in text and "2026-W30" in text
    assert "no weekly p95" in text


# --- accumulation: reading the venue minimums from the snapshot ----------------------------------

CANONICAL_SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "kraken-refdata-20260707T032900Z.json"

# The real snapshot's shape, cut to the two traps. The BTC-denominated rows come AFTER their EUR
# twins, exactly as in the file, so a base-keyed loader without the quote filter OVERWRITES the EUR
# floors rather than being shadowed by them -- the direction that silently understates the floor.
TRAP_UNIVERSE = [
    {"base": "ETH", "quote": "EUR", "ordermin": "0.001", "costmin": "0.45", "wsname": "ETH/EUR"},
    {"base": "SOL", "quote": "EUR", "ordermin": "0.06", "costmin": "0.45", "wsname": "SOL/EUR"},
    {"base": "DOGE", "quote": "EUR", "ordermin": "50", "costmin": "0.45", "wsname": "XDG/EUR"},
    {"base": "ETH", "quote": "BTC", "ordermin": "0.001", "costmin": "0.00002", "wsname": "ETH/XBT"},
    {"base": "SOL", "quote": "BTC", "ordermin": "0.06", "costmin": "0.00002", "wsname": "SOL/XBT"},
]


def _write_snapshot(tmp_path: Path, universe: list[dict]) -> Path:
    path = tmp_path / "kraken-refdata.json"
    path.write_text(json.dumps({"fetched_at": "2026-07-07T03:29:00+00:00", "universe": universe}))
    return path


def test_load_minimums_filters_the_quote_and_does_not_match_on_wsname(tmp_path):
    minimums, fetched_at = load_minimums(_write_snapshot(tmp_path, TRAP_UNIVERSE))
    assert fetched_at == "2026-07-07T03:29:00+00:00"
    # DOGE resolves although Kraken's wsname is XDG/EUR -- there is no DOGE/EUR pair to match on.
    assert minimums["DOGE"] == (50.0, 0.45)
    # The EUR costmin survives the BTC-denominated row sharing its base: 0.45 euros, not 0.00002
    # BTC read as euros, which is four orders of magnitude of understated floor.
    assert minimums["ETH"] == (0.001, 0.45)
    assert minimums["SOL"] == (0.06, 0.45)


def test_load_minimums_raises_on_two_eur_pairs_for_one_base(tmp_path):
    universe = [
        {"base": "ETH", "quote": "EUR", "ordermin": "0.001", "costmin": "0.45"},
        {"base": "ETH", "quote": "EUR", "ordermin": "0.002", "costmin": "0.45"},
    ]
    with pytest.raises(Exception, match="duplicate EUR pair"):
        load_minimums(_write_snapshot(tmp_path, universe))


@pytest.mark.skipif(not CANONICAL_SNAPSHOT.exists(), reason="gitignored snapshots dataset absent")
def test_load_minimums_against_the_canonical_snapshot():
    # The numbers the measurement is quoted from, read off the real file rather than a fixture.
    minimums, fetched_at = load_minimums(CANONICAL_SNAPSHOT)
    assert fetched_at.startswith("2026-07-07")
    assert minimums["DOGE"] == (50.0, 0.45)
    assert minimums["BTC"] == (0.00005, 0.45)
    assert minimums["ADA"] == (20.0, 0.45)
    assert minimums["ETH"] == (0.001, 0.45)
    assert all(costmin == 0.45 for _, costmin in minimums.values())


# --- the two CLI commands ------------------------------------------------------------------------

runner = CliRunner()

CLI_CYCLE_TS = datetime(2026, 8, 1, 8, tzinfo=UTC)


def _patch_config(monkeypatch, tmp_path: Path) -> AppConfig:
    cfg = AppConfig(
        data_dir=tmp_path / "data",
        nfs_mount_dir=Path("/mnt/zhao-crypto"),
        fetch=FetchConfig(),
        engine=EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal"),
        data=DataConfig(),
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    return cfg


def _write_unreplayable_record(journal_dir: Path, cycle_ts: datetime = CLI_CYCLE_TS) -> Path:
    """One schema-valid journaled cycle whose snapshot parquet is ABSENT from the journal tree, so
    the replay fails inside the reader (the partial-rsync failure mode). The command must name and
    count it, never drop it -- and the path it names is built from the reader's journal root, which
    is what pins `--journal-dir` to the reader rather than to the configured journal."""
    h4 = SnapshotEntry(
        pair="BTC",
        grid="240",
        n_bars=3,
        first_ts=cycle_ts - timedelta(hours=12),
        last_ts=cycle_ts - timedelta(hours=4),
        content_hash="0" * 64,
        path="absent-240.parquet",
    )
    daily = SnapshotEntry(
        pair="BTC",
        grid="1440",
        n_bars=3,
        first_ts=cycle_ts.replace(hour=0) - timedelta(days=3),
        last_ts=cycle_ts.replace(hour=0) - timedelta(days=1),
        content_hash="0" * 64,
        path="absent-1440.parquet",
    )
    record = CycleRecord(
        schema_version=1,
        cycle_ts=cycle_ts,
        snapshots=(h4, daily),
        final_targets={"BTC": 0.1},
        started_at=cycle_ts,
        completed_at=cycle_ts + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"cycle-{cycle_ts:%H}.json"
    path.write_text(to_json(record) + "\n")
    return path


def _strict_json(text: str) -> dict:
    """Parse as JSON, refusing the non-standard NaN/Infinity tokens `json.dumps` emits by default.

    Python's own parser accepts them, so a plain `json.loads` would pass against exactly the defect
    this pins -- `parse_constant` is the only way to make the check strict from Python."""

    def reject(token):
        raise AssertionError(f"non-standard JSON token {token!r} -- this payload is not valid JSON")

    return json.loads(text, parse_constant=reject)


def test_decompose_help_states_what_it_measures():
    result = runner.invoke(app, ["engine", "decompose", "--help"])
    assert result.exit_code == 0, result.output
    assert "Attribute each journaled cycle's gross across the pipeline stages." in " ".join(result.output.split())


def test_accum_replay_help_states_what_it_measures():
    result = runner.invoke(app, ["engine", "accum-replay", "--help"])
    assert result.exit_code == 0, result.output
    normalized = " ".join(result.output.split())
    assert "Measure the position drift the venue's order minimums impose at each portfolio size." in normalized


def test_decompose_refuses_an_empty_journal(tmp_path, monkeypatch):
    # An empty table would read as "nothing to see", which is not what an empty journal means.
    _patch_config(monkeypatch, tmp_path)
    empty = tmp_path / "empty-journal"
    empty.mkdir()
    result = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(empty)])
    assert result.exit_code != 0, result.output
    assert "no cycle records found" in result.output


def test_accum_replay_refuses_an_empty_journal(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    empty = tmp_path / "empty-journal"
    empty.mkdir()
    result = runner.invoke(app, ["engine", "accum-replay", "--journal-dir", str(empty)])
    assert result.exit_code != 0, result.output
    # The journal is the primary input: it must be the thing complained about, not the minimums
    # snapshot that also happens to be absent under this tmp data dir.
    assert "no cycle records found" in result.output


def test_decompose_names_counts_and_fails_on_a_record_that_cannot_replay(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)

    result = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(journal)])

    out = result.output
    assert result.exit_code != 0, out  # a silent skip would render an empty table and exit 0
    assert "failed to replay: 1" in out
    assert CLI_CYCLE_TS.isoformat() in out  # the cycle is named, not just tallied
    # The reader resolves snapshot paths under the --journal-dir root: wiring it to the configured
    # journal_dir instead would name a path under tmp_path/"journal", not this one.
    assert str(journal / "absent-240.parquet") in " ".join(out.split())


def test_decompose_json_is_strictly_valid_and_maps_non_finite_to_null(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)

    result = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(journal), "--json"])

    assert result.exit_code != 0, result.output
    payload = _strict_json(result.output)
    assert payload["n_cycles"] == 0
    assert payload["n_failed"] == 1
    assert payload["failures"][0]["cycle_ts"] == CLI_CYCLE_TS.isoformat()
    # Every median is 0/0 over an empty window: NaN in the payload, `null` on the wire. Asserting
    # the KEY IS PRESENT and the value is None is the discriminating pair -- a dropped key would
    # also parse, and `json.dumps`' bare NaN token would parse under Python but not as JSON.
    assert "cancellation_ratio" in payload["median"]
    assert payload["median"]["cancellation_ratio"] is None


def test_accum_replay_stamps_the_minimums_and_counts_the_failure(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)
    snapshot = _write_snapshot(tmp_path, TRAP_UNIVERSE)

    result = runner.invoke(app, ["engine", "accum-replay", "--journal-dir", str(journal), "--minimums", str(snapshot)])

    out = result.output
    assert result.exit_code != 0, out
    assert "2026-07-07" in out  # the floors move; the table says when they were read
    assert "failed to replay: 1" in out


def test_accum_replay_json_keys_the_drift_table_by_nav_string(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)
    snapshot = _write_snapshot(tmp_path, TRAP_UNIVERSE)

    result = runner.invoke(
        app,
        [
            "engine",
            "accum-replay",
            "--journal-dir",
            str(journal),
            "--minimums",
            str(snapshot),
            "--nav",
            "500",
            "--nav",
            "2500",
            "--json",
        ],
    )

    assert result.exit_code != 0, result.output
    payload = _strict_json(result.output)
    # --nav actually threads through: the five-rung default would give a different list entirely.
    assert payload["navs"] == [500.0, 2500.0]
    # The float keys are stringified deliberately, in this exact spelling.
    assert set(payload["by_nav"]) == {"500.0", "2500.0"}
    # ...and the numeric NAV stays recoverable from the row itself, so a consumer never has to
    # parse the key back into a float.
    assert payload["by_nav"]["2500.0"]["nav"] == 2500.0
    assert payload["by_nav"]["2500.0"]["median_drift_bps"] is None  # NaN over an empty window


def test_the_day_window_excludes_a_cycle_outside_it(tmp_path, monkeypatch):
    # A no-op filter would replay the record and report it; only a filter that actually filters
    # leaves nothing to report.
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)  # 2026-08-01

    before = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(journal), "--until", "2026-07-31"])
    assert before.exit_code != 0 and "no cycle records found" in before.output

    after = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(journal), "--since", "2026-08-02"])
    assert after.exit_code != 0 and "no cycle records found" in after.output

    # The window's own edges are inclusive -- the same day on both sides still selects the cycle.
    inside = runner.invoke(
        app, ["engine", "decompose", "--journal-dir", str(journal), "--since", "2026-08-01", "--until", "2026-08-01"]
    )
    assert "no cycle records found" not in inside.output
    assert "failed to replay: 1" in inside.output


def test_a_malformed_cycle_record_aborts_instead_of_being_skipped(tmp_path, monkeypatch):
    # Skipping it would leave a smaller window reported as if it were the whole one.
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    day_dir = journal / "2026-08-01"
    day_dir.mkdir(parents=True)
    (day_dir / "cycle-08.json").write_text("{not json")

    result = runner.invoke(app, ["engine", "decompose", "--journal-dir", str(journal)])

    out = " ".join(result.output.split())
    assert result.exit_code != 0, out
    assert "unreadable cycle record" in out
    assert str(day_dir / "cycle-08.json") in out  # named, so it can be repaired


def test_accum_replay_aborts_cleanly_on_a_malformed_minimums_file(tmp_path, monkeypatch):
    # `"ordermin": null` reaches float(None) inside load_minimums. Malformed evidence must come back
    # as the module's one-line exit, never as a traceback out of an operator-facing command.
    _patch_config(monkeypatch, tmp_path)
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)
    snapshot = _write_snapshot(tmp_path, [{"base": "ETH", "quote": "EUR", "ordermin": None, "costmin": "0.45"}])

    result = runner.invoke(app, ["engine", "accum-replay", "--journal-dir", str(journal), "--minimums", str(snapshot)])

    out = result.output
    assert result.exit_code != 0, out
    # SystemExit, not the raw TypeError: an uncaught one would surface as a traceback and this
    # message would never be printed at all.
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert "could not read the venue order minimums" in out
    assert "Traceback" not in out


def test_accum_replay_defaults_to_the_newest_venue_snapshot(tmp_path, monkeypatch):
    # Two snapshots under the configured data dir: the command must read the newer one. Picking the
    # older would quote the drift band off a superseded floor table -- silently, since both parse.
    cfg = _patch_config(monkeypatch, tmp_path)
    snapshots_dir = cfg.data_dir / "snapshots"
    snapshots_dir.mkdir(parents=True)
    for stamp, fetched_at in (("20260601T000000Z", "2026-06-01T00:00:00+00:00"), ("20260707T032900Z", "2026-07-07T03:29:00+00:00")):
        (snapshots_dir / f"kraken-refdata-{stamp}.json").write_text(
            json.dumps({"fetched_at": fetched_at, "universe": TRAP_UNIVERSE})
        )
    journal = tmp_path / "pulled-journal"
    _write_unreplayable_record(journal)

    result = runner.invoke(app, ["engine", "accum-replay", "--journal-dir", str(journal)])

    out = result.output
    assert "2026-07-07" in out, out
    assert "2026-06-01" not in out, out


# --- schema 2: the twelve-symbol journal, through the REAL builder ---------------------------------
#
# Every other CycleRecord in this file is schema_version=1 with a stubbed builder -- which is exactly
# why the widening's PortfolioError went unnoticed here. That raise is NOT an EngineError (its MRO is
# PortfolioError -> Exception), so `decompose_report`'s per-record `except EngineError` and the
# command's own catch would BOTH have missed it: the first schema-2 record killed the whole command
# with an unhandled traceback instead of being counted as one named failed cycle. The builder must be
# real here -- a stub keyed by whatever it is handed accepts the twelve-symbol panel the real one
# refuses, so it cannot see the defect at all.


def _v2_record_and_reader() -> tuple[CycleRecord, object, dict[str, float]]:
    """A genuine schema-2 record: twelve symbol-keyed snapshots on one calendar per grid, and
    final_targets from a REAL ten-asset build expanded onto the basket -- exactly the shape
    `run_cycle` journals. Returns (record, reader, model_targets)."""
    grids = basket_fixture.grids()
    result = basket_fixture.build(grids)
    record = basket_fixture.record(grids, schema_version=2, result=result)
    return record, basket_fixture.reader(grids), basket_fixture.targets_at(result, result.n_periods, 1)


def test_replay_stages_rebuilds_a_schema_2_record_and_stays_base_keyed():
    """The v2 round trip. `replay_stages` contracts the journaled twelve to the model's ten, and its
    JOURNAL identity is met in the record's own key space via `_expand_to_basket` -- while the
    returned `CycleStages` stays BASE-keyed, which is what both consumers need: `accumulation_payload`
    looks its floors up in `load_minimums`' output, and the refdata snapshot keys that by base."""
    record, reader, model_targets = _v2_record_and_reader()

    stages = replay_stages(record, reader)

    assets = set(CrossfreqSystemConfig().assets)
    assert set(stages.final) == assets  # base-keyed ten, not the journaled twelve
    assert set(stages.closes) == assets and set(stages.combined) == assets
    # The identity the function itself enforces, restated here so the test fails loudly rather than
    # relying on an internal raise: the rebuild expanded IS what the record journals.
    assert _expand_to_basket(stages.final) == record.final_targets
    assert stages.final == pytest.approx(model_targets)
    # Discriminating: the ten are non-zero and pairwise distinct, so none is confusable with the
    # structural zero `_expand_to_basket` writes for the two /BTC legs.
    assert 0.0 not in set(stages.final.values()) and len(set(stages.final.values())) == 10
    assert all(record.final_targets[leg] == 0.0 for leg in BASKET if not leg.endswith("/EUR"))


def test_replay_stages_carries_the_records_journaled_nav():
    """The REPORT path must score a cycle under the same NAV the engine's trip does.

    `executor._stage` and `replay_stages` are the two producers of `CycleStages`, and they feed the
    same `realized_drift`. If only one carries `nav`, a `shadow_nav_eur` change bands the human off
    the weekly report at the LIVE value while the engine trips at the journaled one -- the exact
    divergence `drift_bps`'s docstring says the shared core exists to prevent.
    """
    from dataclasses import replace

    record, reader, _ = _v2_record_and_reader()
    assert replay_stages(replace(record, nav=1234.5), reader).nav == 1234.5
    # A record written before the widening carries no NAV; the caller's scalar is the fallback.
    assert replay_stages(replace(record, nav=None), reader).nav is None


def test_decompose_and_accum_replay_survive_a_schema_2_record():
    """Both feeder reports, end to end on a v2 record. Before the contraction landed, the builder
    raised PortfolioError here -- and because that is not an EngineError, `n_failed` would never
    have reached 1: the report call itself died."""
    record, reader, _ = _v2_record_and_reader()

    _, decompose = decompose_report([record], reader)
    assert decompose["n_failed"] == 0 and decompose["failures"] == []
    assert decompose["n_cycles"] == 1
    assert decompose["cycles"][0]["final_gross"] > 0.0  # a real book, not an all-zero rebuild

    minimums = {a: (1e-9, 0.0) for a in CrossfreqSystemConfig().assets}
    _, accum = accumulation_report([record], reader, minimums, [100_000.0], fetched_at="2026-07-10T00:00:00Z")
    assert accum["n_failed"] == 0 and accum["failures"] == []
    assert accum["n_cycles"] == 1
    assert accum["by_nav"][100_000.0]["cycles"][0]["placed"] is True
