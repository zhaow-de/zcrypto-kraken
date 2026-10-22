"""B2 trials 6-7's inputs half against spec 00139's measured basis: no bar, and no return of either arm."""

from __future__ import annotations

import operator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.features.derivatives import coverage_by_year
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; each case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_RETURN_INDICES = 27_337
BLOCK = {
    "b2-liq-reentry": "816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f",
    "b2-funding-reentry": "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8",
}
VOUCHED = {
    "b2-liq-reentry": {"liquidations-daily": "checked (10 vouched hashes)"},
    "b2-funding-reentry": {"derivatives-funding": "checked (10 vouched hashes)"},
}
# The read's start: its return index and close, and the returns from it.
START = {
    "b2-liq-reentry": (19_731, datetime(2022, 10, 11, tzinfo=UTC), 7_606),
    "b2-funding-reentry": (15_843, datetime(2021, 1, 1, tzinfo=UTC), 11_494),
}
# The first return index every asset's signal holds.
_SIGNAL_FROM = {"b2-liq-reentry": 19_731, "b2-funding-reentry": 15_419}
THRESHOLD = {"b2-liq-reentry": 2.5, "b2-funding-reentry": -2.0}
ENGAGED_PER_ASSET = {
    "b2-liq-reentry": {
        "ADA": 114,
        "AVAX": 82,
        "BTC": 139,
        "DOGE": 90,
        "DOT": 163,
        "ETH": 126,
        "LINK": 118,
        "LTC": 120,
        "SOL": 137,
        "XRP": 107,
    },
    "b2-funding-reentry": {
        "ADA": 963,
        "AVAX": 740,
        "BTC": 684,
        "DOGE": 706,
        "DOT": 812,
        "ETH": 710,
        "LINK": 946,
        "LTC": 780,
        "SOL": 723,
        "XRP": 982,
    },
}
ENGAGED_PER_YEAR = {
    "b2-liq-reentry": dict.fromkeys(map(str, range(2013, 2022)), 0)
    | {"2022": 155, "2023": 259, "2024": 301, "2025": 307, "2026": 174},
    "b2-funding-reentry": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 218, "2021": 535, "2022": 2_407, "2023": 1_463, "2024": 1_177, "2025": 1_691, "2026": 555},
}
# Arm B's turnover: a re-entry's size moves it, never the counts above.
TURNOVER_B = {"b2-liq-reentry": 172.92, "b2-funding-reentry": 264.50}
SIGNAL_KEY = {"b2-liq-reentry": "binperp_liq_long_z30d", "b2-funding-reentry": "binperp_funding_z30d"}
_TRIGGERS = {
    "b2-liq-reentry": (subjects._b2_liq_signal, operator.gt, 1),
    "b2-funding-reentry": (subjects._b2_funding_signal, operator.lt, 6),
}


def reentry_inputs(name: str):
    """A re-entry's inputs half over the real sets, with the reader that read them."""
    read_signal, fire, hold = _TRIGGERS[name]
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_reentry_inputs(name, read_signal, fire, hold, THRESHOLD[name], reader, "ohlc-full", None, False)


def coverage(inputs) -> dict[str, dict[str, list[int]]]:
    return {
        asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, values).items()}
        for asset, values in inputs.signal.items()
    }


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set or the frozen daily liquidations block is absent under data/",
)
def test_the_liquidation_reentry_reproduces_the_measured_basis():
    _check("b2-liq-reentry")


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_funding_reentry_reproduces_the_measured_basis():
    _check("b2-funding-reentry")


def _check(name: str) -> None:
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reentry_inputs(name)
    assert compute_hash(reader.block()) == BLOCK[name]
    assert {d: s for d, s in reader.vouched_status().items() if d != "ohlc-full"} == VOUCHED[name]
    index, first, returns = START[name]
    assert (len(inputs.close), inputs.close[index], _RETURN_INDICES - index) == (_RETURN_INDICES, first, returns)
    signal = inputs.signal
    assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == _SIGNAL_FROM[name]
    arm_a, full_long = inputs.arm_a, inputs.full_long
    assert sum(arm_a[a][k] > full_long[a][k] + 1e-12 for a in subjects._ASSETS for k in range(_RETURN_INDICES)) == 0
    assert (
        sum(
            abs(arm_a[a][k] - full_long[a][k]) <= 1e-12 and arm_a[a][k] > 0
            for a in subjects._ASSETS
            for k in range(_RETURN_INDICES)
        )
        == 30_632
    )
    assert subjects._b2_reentry_engagement(inputs, SIGNAL_KEY[name]) == {
        "engaged_per_asset": ENGAGED_PER_ASSET[name],
        "engaged_per_year": ENGAGED_PER_YEAR[name],
        f"{SIGNAL_KEY[name]}_coverage": coverage(inputs),
        "primary_returns": returns,
        "threshold": THRESHOLD[name],
    }
    assert round(subjects.book_turnover(inputs.arm_b), 2) == TURNOVER_B[name]
