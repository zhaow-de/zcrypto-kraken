import polars as pl
import pytest

from cli.universe.errors import UniverseError
from cli.universe.volume import median_quote_volume


def _daily_frame(vwaps: list[float], volumes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"ts": list(range(len(vwaps))), "vwap": vwaps, "volume": volumes})


def test_median_quote_volume_is_median_of_volume_times_vwap():
    vwaps = [100.0] * 29 + [200.0]  # 29 days at qv=1000, one day at qv=2000
    volumes = [10.0] * 30
    frame = _daily_frame(vwaps, volumes)
    assert median_quote_volume(frame, window=30) == 1000.0


def test_median_quote_volume_uses_only_the_last_window_rows():
    vwaps = [1_000_000.0] * 10 + [100.0] * 30  # older, huge-vwap rows must be excluded
    volumes = [1.0] * 40
    frame = _daily_frame(vwaps, volumes)
    assert median_quote_volume(frame, window=30) == 100.0


def test_median_quote_volume_raises_if_fewer_rows_than_window():
    frame = _daily_frame([100.0] * 10, [1.0] * 10)
    with pytest.raises(UniverseError):
        median_quote_volume(frame, window=30)
