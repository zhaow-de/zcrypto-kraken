import math
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _readings

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUBJECT = "c3-asopr-reentry"
DATASET = "btc-onchain-20261124T162656Z"

# docs/specs/00165-c3-trial-1-asopr-reentry-design.md's measured basis, read from positions, events and sizes alone.
BLOCK = "19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a"
VOUCHED = {DATASET: "checked (1 vouched hashes)", "ohlc-full": "checked (36 vouched hashes)"}
AS_OF_LINE = {"relpath": "index/2026/11/23.json", "sha256": "2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2"}
RETURN_INDICES = 4581
TURNOVER_A = 46.72757036801258
ENGAGEMENT = {
    "reentry_first_engaged": 97,
    "primary_returns": 4484,
    "stamps_positions_differ": 977,
    "positions_differ_per_year": {
        "2013": 10,
        "2014": 189,
        "2015": 114,
        "2016": 0,
        "2017": 7,
        "2018": 183,
        "2019": 112,
        "2020": 40,
        "2021": 52,
        "2022": 170,
        "2023": 35,
        "2024": 7,
        "2025": 14,
        "2026": 44,
    },
    "events_per_year": {
        "2013": 4,
        "2014": 125,
        "2015": 76,
        "2016": 0,
        "2017": 1,
        "2018": 294,
        "2019": 146,
        "2020": 76,
        "2021": 59,
        "2022": 580,
        "2023": 30,
        "2024": 8,
        "2025": 20,
        "2026": 130,
    },
    "reentered_per_year": {
        "2013": 20,
        "2014": 374,
        "2015": 228,
        "2016": 0,
        "2017": 7,
        "2018": 726,
        "2019": 516,
        "2020": 243,
        "2021": 283,
        "2022": 1700,
        "2023": 166,
        "2024": 56,
        "2025": 140,
        "2026": 440,
    },
    "reentry_entries": 367,
    "events_without_size": 29,
    "turnover_b": 69.84081467289158,
    "gross_max": 0.7648558752122554,
}
REENTERED_PER_ASSET = {
    "ADA": 483,
    "AVAX": 254,
    "BTC": 913,
    "DOGE": 326,
    "DOT": 289,
    "ETH": 559,
    "LINK": 333,
    "LTC": 902,
    "SOL": 246,
    "XRP": 594,
}


def trial_inputs():
    reader = ObservedReader(_DATA_ROOT)
    provenance, snapshot, daily_ts, daily_prices = subjects._c3_reads(reader, DATASET, SUBJECT)
    return reader, provenance, subjects._c3_reentry_inputs(snapshot, daily_ts, daily_prices)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "btc-onchain-*/BTC/onchain.parquet"),
    reason="the frozen btc-onchain snapshot is absent under data/",
)
def test_the_c3_reentry_inputs_reproduce_the_measured_basis_on_reading_10s_block_and_events():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, provenance, inputs = trial_inputs()
    reading = _readings()[10]
    assert reading["invocation"]["subject"] == "c3-onchain-reading"
    block = reader.block()
    assert compute_hash(block) == BLOCK == reading["dataset_hash"] and block == reading["datasets"]
    assert reader.vouched_status() == VOUCHED and reader.holes() == {}
    assert provenance["as_of_line"] == AS_OF_LINE
    arm_a, arm_b, n = inputs.arm_a, inputs.arm_b, len(inputs.close)
    assert n == RETURN_INDICES
    # Never the computes half here: docs/specs/00165 D15's hash rule.
    assert {a: sum(fired) for a, fired in inputs.fires.items()} == {
        a: counts["events"] for a, counts in reading["metrics"]["counts"]["asopr|low|flat"].items()
    }
    engagement = subjects._c3_reentry_engagement(inputs)
    by_year = engagement.pop("turnover_b_per_year")
    assert engagement == ENGAGEMENT
    assert set(by_year) == set(ENGAGEMENT["events_per_year"]) and math.fsum(by_year.values()) == pytest.approx(
        ENGAGEMENT["turnover_b"]
    )
    assert sum(ENGAGEMENT["events_per_year"].values()) == 1549
    assert book_turnover(arm_a) == TURNOVER_A
    first = ENGAGEMENT["reentry_first_engaged"]
    assert all(arm_b[a][:first] == arm_a[a][:first] for a in arm_a)
    assert all(p >= 0 for held in arm_b.values() for p in held)
    reentered = {a: [arm_a[a][k] == 0 and arm_b[a][k] > 0 for k in range(n)] for a in arm_a}
    assert {a: sum(held) for a, held in reentered.items()} == REENTERED_PER_ASSET
    assert sum(held[k] for held in reentered.values() for k in range(199)) == 52
    assert sum(held[k] for held in reentered.values() for k in range(230)) == 114
    assert sum(any(arm_a[a][k] > 0.20 for a in arm_a) for k in range(n)) == 224
    assert sum(any(arm_b[a][k] > 0.20 for a in arm_b) for k in range(n)) == 238
