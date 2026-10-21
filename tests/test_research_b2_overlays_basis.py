"""B2 trials 3-5's inputs half against spec 00138's bases: no bar, and no position or return of arm B."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import B2Config, derisk_scales, net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the basis test's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_SIDECAR = Path(__file__).resolve().parents[1] / "docs" / "reference" / "vouched-dataset-hashes.jsonl"
_SPEC = Path(__file__).resolve().parents[1] / "docs" / "specs" / "00138-b2-three-overlays-design.md"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf"
_RETURN_INDICES = 27_337
_CLOSES_PER_YEAR = {
    "2013": 509,
    "2014": 2_190,
    "2015": 2_190,
    "2016": 2_195,
    "2017": 2_190,
    "2018": 2_183,
    "2019": 2_190,
    "2020": 2_196,
    "2021": 2_190,
    "2022": 2_190,
    "2023": 2_190,
    "2024": 2_195,
    "2025": 2_189,
    "2026": 540,
}
# Per overlay: the first close every asset's signal holds, the returns from it, and per asset the closes holding the
# signal in each close year that holds any.
_START = {
    "b2-oi-derisk": (datetime(2021, 12, 30, 20, tzinfo=UTC), 9_311),
    "b2-ratio-derisk": (datetime(2023, 1, 13, 12, tzinfo=UTC), 7_039),
}
_OI_NINE = {"2021": 7, "2022": 2_008, "2023": 2_010, "2025": 2_189, "2026": 540}
_RATIO_NINE = {"2023": 1_755, "2024": 1_835, "2025": 2_009, "2026": 540}
_HELD = {
    "b2-oi-derisk": {
        "ADA": _OI_NINE | {"2024": 1_830},
        "AVAX": _OI_NINE | {"2024": 2_015},
        "BTC": {"2020": 553, "2021": 2_010, "2022": 2_008, "2023": 2_010, "2024": 1_815, "2025": 2_189, "2026": 540},
        "DOGE": _OI_NINE | {"2024": 2_015},
        "DOT": _OI_NINE | {"2024": 2_015},
        "ETH": _OI_NINE | {"2024": 1_835},
        "LINK": _OI_NINE | {"2024": 2_015},
        "LTC": _OI_NINE | {"2024": 1_816},
        "SOL": _OI_NINE | {"2024": 1_829},
        "XRP": _OI_NINE | {"2024": 1_835},
    },
    "b2-ratio-derisk": {
        "ADA": _RATIO_NINE | {"2023": 1_575},
        "AVAX": _RATIO_NINE,
        "BTC": _RATIO_NINE | {"2020": 553, "2021": 2_002},
        "DOGE": _RATIO_NINE,
        "DOT": _RATIO_NINE | {"2023": 1_575},
        "ETH": _RATIO_NINE | {"2025": 1_829},
        "LINK": _RATIO_NINE,
        "LTC": _RATIO_NINE,
        "SOL": _RATIO_NINE,
        "XRP": _RATIO_NINE,
    },
}
ENGAGED_PER_ASSET = {
    "b2-oi-derisk": {
        "ADA": 210,
        "AVAX": 224,
        "BTC": 262,
        "DOGE": 489,
        "DOT": 159,
        "ETH": 237,
        "LINK": 333,
        "LTC": 319,
        "SOL": 181,
        "XRP": 371,
    },
    "b2-ratio-derisk": {
        "ADA": 411,
        "AVAX": 381,
        "BTC": 515,
        "DOGE": 436,
        "DOT": 459,
        "ETH": 224,
        "LINK": 492,
        "LTC": 435,
        "SOL": 418,
        "XRP": 385,
    },
}
ENGAGED_PER_YEAR = {
    "b2-oi-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 31, "2021": 40, "2022": 556, "2023": 636, "2024": 639, "2025": 725, "2026": 158},
    "b2-ratio-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 39, "2021": 116, "2022": 0, "2023": 1_394, "2024": 1_236, "2025": 1_139, "2026": 232},
}
_SIGNAL_KEY = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d"}
# Record 50's arm A and benchmark, unrounded; record 51 lacks the spot drag and keys arm_a_max_drawdown from 2021.
ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


def daily_basis() -> dict:
    """The daily block's figures as the spec's completed basis prints them on its one `DAILY_BASIS` line."""
    lines = [line for line in _SPEC.read_text().splitlines() if line.startswith("DAILY_BASIS ")]
    assert len(lines) == 1, f"the spec holds {len(lines)} DAILY_BASIS lines, and its completed basis prints one"
    return json.loads(lines[0].removeprefix("DAILY_BASIS "))


def attested(dataset: str) -> dict[str, dict]:
    return {row["relpath"]: row for row in map(json.loads, _SIDECAR.read_text().splitlines()) if row["dataset"] == dataset}


def coverage(name: str) -> dict[str, dict[str, list[int]]]:
    """A signal's per-asset, per-close-year `[non_null, total]` as the basis measured it."""
    return {
        asset: {year: [held.get(year, 0), total] for year, total in _CLOSES_PER_YEAR.items()} for asset, held in _HELD[name].items()
    }


@pytest.fixture(scope="module")
def _reads():
    reader = ObservedReader(_DATA_ROOT)
    oi = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-full", None, False)
    ratio = subjects._b2_ratio_signal(reader, oi.h4_ts)
    by_overlay = {
        "b2-oi-derisk": oi,
        "b2-ratio-derisk": oi._replace(signal=ratio, scales=derisk_scales(ratio, config=B2Config(z_threshold=2.5)), threshold=2.5),
    }
    return by_overlay, reader.block()


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_oi_and_ratio_signals_reproduce_the_measured_basis(_reads):
    assert _DATA_ROOT == research_command._DATA_ROOT
    by_overlay, block = _reads
    assert compute_hash(block) == _BLOCK_HASH
    assert {dataset: (len(entry["files"]), entry["rows"], entry["span"]) for dataset, entry in block.items()} == {
        "derivatives-oi": (10, 5_010_882, ["2020-09-01 00:00:00+00:00", "2026-07-22 23:55:00+00:00"]),
        "ohlc-full": (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"]),
    }
    for name, inputs in by_overlay.items():
        first, returns = _START[name]
        assert (len(inputs.close), inputs.close[_RETURN_INDICES - returns]) == (_RETURN_INDICES, first), name
        assert subjects._b2_overlay_engagement(inputs, _SIGNAL_KEY[name]) == {
            "engaged_per_asset": ENGAGED_PER_ASSET[name],
            "engaged_per_year": ENGAGED_PER_YEAR[name],
            f"{_SIGNAL_KEY[name]}_coverage": coverage(name),
            "primary_returns": returns,
            "threshold": 2.5,
        }, name


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-oi set or the frozen daily liquidations block is absent under data/",
)
def test_the_daily_block_is_attested_and_its_signal_reproduces_the_completed_basis(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    reader = ObservedReader(_DATA_ROOT)
    signal = subjects._b2_liq_signal(reader, inputs.h4_ts)
    block, rows = reader.block()["liquidations-daily"], attested("liquidations-daily")
    assert set(reader.block()) == {"liquidations-daily"} and set(block["files"]) == set(rows)
    assert set(rows) == {f"{asset}/daily.parquet" for asset in subjects._ASSETS}
    assert block["rows"] == sum(row["rows"] for row in rows.values())
    assert reader.vouched_status() == {"liquidations-daily": "checked (10 vouched hashes)"}
    basis = daily_basis()
    threshold = subjects._b2_engagement_threshold(signal, inputs.arm_a)
    held = inputs._replace(signal=signal, scales=derisk_scales(signal, config=B2Config(z_threshold=threshold)), threshold=threshold)
    keys = ("engaged_per_asset", "engaged_per_year", "binperp_liq_long_z30d_coverage", "primary_returns", "threshold")
    assert subjects._b2_overlay_engagement(held, "binperp_liq_long_z30d") == {key: basis[key] for key in keys}
    # The fetch's window is longer than trial 4's for a fetch up to 95 days after the probe (D6).
    assert basis["primary_returns"] > _START["b2-ratio-derisk"][1]


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "liquidations-frozen/*/buckets.parquet"),
    reason="the frozen 1-minute liquidations block is absent under data/",
)
def test_the_tape_block_is_attested_file_by_file():
    reader = ObservedReader(_DATA_ROOT)
    for relpath in ("covered-hours.parquet", *(f"{asset}/buckets.parquet" for asset in subjects._ASSETS)):
        reader.read_series("liquidations-frozen", relpath)
    block, rows = reader.block()["liquidations-frozen"], attested("liquidations-frozen")
    assert set(block["files"]) == set(rows) and len(rows) == 11
    assert block["rows"] == sum(row["rows"] for row in rows.values())
    assert reader.vouched_status() == {"liquidations-frozen": "checked (11 vouched hashes)"}


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_overlays_arm_a_reproduces_records_50_and_51s_arm_a(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    net_a = net_of_cost(inputs.arm_a, subjects._b2_returns(inputs.h4_prices), cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a = book_turnover(inputs.arm_a)

    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / _RETURN_INDICES * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == ARM_A
    assert {key: _trials()[50]["metrics"][key] for key in ARM_A} == ARM_A
    shared = (
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "turnover_a",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    )
    assert {key: _trials()[51]["metrics"][key] for key in shared} == {key: ARM_A[key] for key in shared}
