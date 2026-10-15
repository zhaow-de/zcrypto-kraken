"""B1 trial 3's reads on the data root the run reads: the subject's reads half reproduces spec 00132's measured basis — the
block, the union, the hourly rows and the seam between the two grids — and computes no weight, so it runs before the spec's
hash is taken."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the test's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1"
_HOURLY_ROWS = {
    "ADA": 65_623,
    "AVAX": 37_157,
    "BTC": 108_786,
    "DOGE": 53_237,
    "DOT": 49_181,
    "ETH": 92_294,
    "LINK": 56_518,
    "LTC": 99_565,
    "SOL": 41_918,
    "XRP": 77_653,
}
_H4 = timedelta(hours=4)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/60.parquet"),
    reason="the frozen ohlc-full set's hourly files are absent under data/",
)
def test_the_b1_hourly_rv_reads_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(reader, "ohlc-full", None, None, False, subject="b1-hourly-rv")

    block = reader.block()
    assert compute_hash(block) == _BLOCK_HASH
    assert (len(block["ohlc-full"]["files"]), block["ohlc-full"]["rows"]) == (20, 855_305)

    assert len(h4_ts) == 27_338
    assert (h4_ts[0], h4_ts[-1]) == (datetime(2013, 9, 10, 20, tzinfo=UTC), datetime(2026, 3, 31, 20, tzinfo=UTC))
    assert sum(later - earlier != _H4 for earlier, later in zip(h4_ts, h4_ts[1:])) == 63
    assert {asset: len(stamps) for asset, (stamps, _) in hourly.items()} == _HOURLY_ROWS

    present, agree = 0, 0
    for asset, (stamps, closes) in hourly.items():
        # Both grids bucket the same minutes at `ts // interval * interval`, so an hourly bar's 4h bar opens at its own
        # stamp floored to 4h. A later row's close overwrites an earlier one in its bucket, so each bucket keeps the close
        # of its last row in file order: its last present hourly close where the file's stamps ascend.
        last = {int(h.timestamp()) // 14_400 * 14_400: close for h, close in zip(stamps, closes)}
        h4 = {int(t.timestamp()): close for t, close in zip(h4_ts, h4_prices[asset]) if close is not None}
        assert set(last) == set(h4), f"{asset}: a 4h bar with no hourly bar, or an hourly bar in a 4h bar the asset lacks"
        present += len(h4)
        agree += sum(last[t] == close for t, close in h4.items())
    assert present == agree == 173_373
