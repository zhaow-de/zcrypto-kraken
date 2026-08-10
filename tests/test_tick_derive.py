"""Deriving 60/240/1440 from the 15m base is EXACT, not approximate (spec 00087 D1)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.aggregate import ticks_to_bars
from cli.tick.materialize import build_day, derive_bars, segment_index


def _tape(tmp_path: Path, pair: str, day: date) -> Path:
    """A day of varied trades -- varied so an averaged vwap and a weighted one differ."""
    root = tmp_path / "p"
    for h in range(24):
        hour = datetime(day.year, day.month, day.day, h, tzinfo=UTC)
        d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
        d.mkdir(parents=True, exist_ok=True)
        n = 4 + (h % 5)
        pl.DataFrame(
            {
                "ts": [hour + timedelta(minutes=3 * i) for i in range(n)],
                "symbol": [pair] * n,
                "side": ["buy"] * n,
                "price": [100.0 + h + i for i in range(n)],
                "qty": [1.0 + 3.0 * ((h + i) % 4) for i in range(n)],  # lopsided on purpose
                "ord_type": ["limit"] * n,
                "trade_id": [h * 100 + i for i in range(n)],
            },
            schema=TRADE_SCHEMA,
        ).write_parquet(d / f"{hour:%H}.parquet")
    return root


@pytest.mark.parametrize("interval", [60, 240, 1440])
def test_derived_equals_direct_aggregation(tmp_path, interval):
    """THE property D1 claims. Derived-from-15m must equal ticks_to_bars run at that interval on the
    same ticks -- every column, not just the ones that trivially telescope."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1))
    derived = derive_bars(base, interval_minutes=interval)

    ticks = (
        pl.concat(pl.read_parquet(p) for p in sorted((root / "BTC" / "EUR" / "trades").rglob("*.parquet")))
        .rename({"qty": "volume"})
        .select("ts", "price", "volume")
    )
    direct = ticks_to_bars(ticks, interval_minutes=interval)

    assert derived.height == direct.height
    for col in ("ts", "open", "high", "low", "close", "count"):
        assert derived[col].to_list() == direct[col].to_list(), col
    for col in ("volume", "vwap"):
        assert derived[col].to_list() == pytest.approx(direct[col].to_list()), col


def test_an_averaged_vwap_would_be_wrong(tmp_path):
    """Guards the formula, not just the result: on lopsided volume the weighted vwap differs from a
    plain mean of sub-bar vwaps, so a naive implementation cannot pass the test above by accident."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1))
    derived = derive_bars(base, interval_minutes=60)
    naive = base.group_by_dynamic("ts", every="60m", closed="left").agg(pl.col("vwap").mean())
    assert derived["vwap"].to_list() != pytest.approx(naive["vwap"].to_list())


def test_a_coarse_window_exists_iff_a_sub_bar_does(tmp_path):
    """Sparse input stays sparse: no gap-filling, and a coarse bar is never invented."""
    root = _tape(tmp_path, "BTC/EUR", date(2026, 8, 1))
    base = build_day(segment_index(root, root.parent / "r"), "BTC/EUR", date(2026, 8, 1)).filter(
        pl.col("ts") >= datetime(2026, 8, 1, 12, tzinfo=UTC)
    )
    derived = derive_bars(base, interval_minutes=60)
    assert derived["ts"].min() >= datetime(2026, 8, 1, 12, tzinfo=UTC)
    assert derived.height == 12
