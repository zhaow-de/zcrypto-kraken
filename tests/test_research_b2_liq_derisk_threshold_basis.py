"""B2 trial 8's inputs half against spec 00143's measured basis: positions, scales and turnover, and no return of either
arm."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.alpha.b2 import B2Config, derisk_scales, per_year_engaged_counts, per_year_positions_differ, scale_positions
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_RETURN_INDICES = 27_337
BLOCK = "816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f"
VOUCHED = {"liquidations-daily": "checked (10 vouched hashes)"}
# The signal's own start: its return index and close, and the returns from it.
START = (19_731, datetime(2022, 10, 11, tzinfo=UTC), 7_606)
THRESHOLD = 3.0
SIGNAL_KEY = "binperp_liq_long_z30d"
ENGAGED_PER_ASSET = {
    "ADA": 102,
    "AVAX": 109,
    "BTC": 109,
    "DOGE": 155,
    "DOT": 84,
    "ETH": 78,
    "LINK": 109,
    "LTC": 106,
    "SOL": 108,
    "XRP": 120,
}
ENGAGED_PER_YEAR = dict.fromkeys(map(str, range(2013, 2022)), 0) | {"2022": 67, "2023": 362, "2024": 363, "2025": 252, "2026": 36}
# Arm B's positions at 3.0: the closes where they differ from arm A's, and their turnover at two decimals.
POSITIONS_DIFFER = 566
TURNOVER_B = 150.32


def trial_inputs():
    """The trial's inputs half over the real sets, with the reader that read them."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_overlay_inputs(
        "b2-liq-z3-derisk", subjects._b2_liq_signal, THRESHOLD, reader, "ohlc-full", None, False
    )


def coverage() -> dict[str, dict[str, list[int]]]:
    """The signal's per-asset, per-close-year coverage as record 54 stored it: the same block and signal."""
    return _trials()[54]["metrics"][f"{SIGNAL_KEY}_coverage"]


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set or the frozen daily liquidations block is absent under data/",
)
def test_the_de_risk_at_3_0_reproduces_the_measured_basis_and_record_54_at_2_5():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert {d: s for d, s in reader.vouched_status().items() if d != "ohlc-full"} == VOUCHED
    index, first, returns = START
    assert (len(inputs.close), inputs.close[index], subjects._b2_overlay_start(inputs)) == (_RETURN_INDICES, first, index)
    assert subjects._b2_overlay_engagement(inputs, SIGNAL_KEY) == {
        "engaged_per_asset": ENGAGED_PER_ASSET,
        "engaged_per_year": ENGAGED_PER_YEAR,
        f"{SIGNAL_KEY}_coverage": coverage(),
        "primary_returns": returns,
        "threshold": THRESHOLD,
    }
    arm_b = scale_positions(inputs.arm_a, inputs.scales)
    differ = per_year_positions_differ(inputs.arm_a, arm_b, inputs.close)
    assert (sum(differ.values()), round(subjects.book_turnover(arm_b), 2)) == (POSITIONS_DIFFER, TURNOVER_B)
    # Record 54's threshold over the same inputs gives its stored engagement, closes and turnovers.
    record_54 = _trials()[54]["metrics"]
    scales = derisk_scales(inputs.signal, config=B2Config(z_threshold=2.5))
    arm_b_54 = scale_positions(inputs.arm_a, scales)
    assert (
        per_year_engaged_counts(inputs.arm_a, scales, inputs.close),
        sum(per_year_positions_differ(inputs.arm_a, arm_b_54, inputs.close).values()),
        subjects.book_turnover(inputs.arm_a),
        subjects.book_turnover(arm_b_54),
    ) == tuple(record_54[key] for key in ("engaged_per_year", "stamps_positions_differ", "turnover_a", "turnover_b"))
