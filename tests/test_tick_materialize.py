"""The tape-bars day builder (spec 00087 D1/D4)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.tick.errors import TickError
from cli.tick.materialize import build_day, segment_index


def _seg(root: Path, pair: str, hour: datetime, rows: list[tuple[float, float, int]]) -> None:
    """Write one canonical trades segment.

    The canonical layout is <root>/<BASE>/<QUOTE>/<kind>/<Y>/<m>/<d>/<H>.parquet -- the pair spans
    TWO path levels. `canonical_segments` globs `*/*/{kind}/*/*/*/*.parquet` and reads the pair from
    parts[-7]/parts[-6], so a flattened `BTCEUR/` tree is INVISIBLE to it and every positive test
    would fail against a correct implementation.
    """
    d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"
    d.mkdir(parents=True, exist_ok=True)
    frame = pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=s) for _, _, s in rows],
            "symbol": [pair] * len(rows),
            "side": ["buy"] * len(rows),
            "price": [p for p, _, _ in rows],
            "qty": [q for _, q, _ in rows],
            "ord_type": ["limit"] * len(rows),
            "trade_id": list(range(len(rows))),
        },
        schema=TRADE_SCHEMA,
    )
    frame.write_parquet(d / f"{hour:%H}.parquet")


def _full_day(root: Path, pair: str, day: date, *, per_hour=((10.0, 2.0, 5),)) -> None:
    for h in range(24):
        _seg(root, pair, datetime(day.year, day.month, day.day, h, tzinfo=UTC), list(per_hour))


def test_a_full_day_yields_one_bar_per_traded_window(tmp_path):
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert list(bars.columns) == ["ts", "open", "high", "low", "close", "volume", "count", "vwap"]
    # One trade per hour at :05 -> exactly one 15m bar per hour, not 96: empty windows emit NO row.
    assert bars.height == 24
    assert bars["ts"][0] == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


def test_volume_comes_from_qty_not_a_missing_column(tmp_path):
    """The archive's TRADE_SCHEMA says `qty`; ticks_to_bars consumes `volume`. Without the rename
    the aggregation raises or produces null volume -- and a null vwap silently follows."""
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1), per_hour=((10.0, 3.0, 5),))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert bars["volume"].sum() == pytest.approx(72.0)  # 24 hours x 3.0
    assert bars["vwap"].null_count() == 0
    assert bars["vwap"][0] == pytest.approx(10.0)


def test_the_reconciled_overlay_wins_over_the_primary(tmp_path):
    """D4: reconciled-first. The healed hour must be the one that reaches the bars."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _full_day(primary, "BTC/EUR", date(2026, 8, 1), per_hour=((10.0, 1.0, 5),))
    _seg(overlay, "BTC/EUR", datetime(2026, 8, 1, 3, tzinfo=UTC), [(99.0, 1.0, 5)])
    bars = build_day(segment_index(primary, overlay), "BTC/EUR", date(2026, 8, 1))
    hour3 = bars.filter(pl.col("ts") == datetime(2026, 8, 1, 3, 0, tzinfo=UTC))
    assert hour3["close"][0] == pytest.approx(99.0)


def test_a_day_with_no_segments_is_refused(tmp_path):
    """Unreachable through the sweep (the calendar only lists days WITH segments) but reachable by
    direct callers such as the REST control -- so the refusal is pinned here, or its probe has
    nothing to kill."""
    (tmp_path / "data").mkdir()
    with pytest.raises(TickError, match="no trade segments"):
        build_day(segment_index(tmp_path / "data", tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))


def test_only_the_named_day_is_included(tmp_path):
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 1))
    _full_day(tmp_path, "BTC/EUR", date(2026, 8, 2))
    bars = build_day(segment_index(tmp_path, tmp_path / "r"), "BTC/EUR", date(2026, 8, 1))
    assert bars["ts"].min() >= datetime(2026, 8, 1, tzinfo=UTC)
    assert bars["ts"].max() < datetime(2026, 8, 2, tzinfo=UTC)
