import polars as pl
import pytest

from cli.universe.errors import UniverseError
from cli.universe.volume import median_quote_volume, quote_volume_in_eur


def _daily_frame(vwaps: list[float], volumes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"ts": list(range(len(vwaps))), "vwap": vwaps, "volume": volumes})


def _fx_frame(closes: list[float], *, start_ts: int = 0) -> pl.DataFrame:
    return pl.DataFrame({"ts": list(range(start_ts, start_ts + len(closes))), "close": closes})


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


def test_quote_volume_in_eur_without_fx_equals_median_quote_volume():
    frame = _daily_frame([100.0] * 30, [2.0] * 30)
    assert quote_volume_in_eur(frame) == median_quote_volume(frame) == 200.0


def test_quote_volume_in_eur_converts_btc_quoted_leg_via_fx():
    daily = _daily_frame([5.0] * 30, [2.0] * 30)  # 10.0 BTC/day
    fx_daily = _fx_frame([50_000.0] * 30)
    assert quote_volume_in_eur(daily, fx_daily=fx_daily) == 500_000.0


def test_quote_volume_in_eur_raises_if_daily_has_fewer_rows_than_window():
    frame = _daily_frame([100.0] * 10, [1.0] * 10)
    with pytest.raises(UniverseError):
        quote_volume_in_eur(frame, window=30)


def test_quote_volume_in_eur_raises_if_fx_join_yields_fewer_aligned_rows_than_window():
    daily = _daily_frame([100.0] * 30, [1.0] * 30)  # ts 0..29
    fx_daily = _fx_frame([50_000.0] * 30, start_ts=10)  # ts 10..39, overlap is only ts 10..29 (20 rows)
    with pytest.raises(UniverseError):
        quote_volume_in_eur(daily, fx_daily=fx_daily, window=30)


def test_quote_volume_in_eur_sorts_joined_rows_by_ts_before_taking_the_tail():
    # polars join output order is not guaranteed to preserve ts order, so quote_volume_in_eur must sort
    # the fx-joined frame by ts before .tail(window). The oldest 20 rows differ on purpose - with every
    # row equal, an unsorted tail would land on the right answer by accident.
    vwaps = [99.0] * 20 + [5.0] * 30
    volumes = [99.0] * 20 + [2.0] * 30
    daily = _daily_frame(vwaps, volumes)  # ts 0..49, ascending

    # Same 50 ts values as daily, but reversed - i.e. shuffled/non-ascending row order.
    fx_daily = pl.DataFrame({"ts": list(reversed(range(50))), "close": [50_000.0] * 50})

    assert quote_volume_in_eur(daily, fx_daily=fx_daily, window=30) == 500_000.0
