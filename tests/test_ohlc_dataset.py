import json
from pathlib import Path

import polars as pl
import pytest

from cli.ohlc.dataset import dataset_hash, read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError

_FIXTURES = Path(__file__).parent / "fixtures"
ROWS = json.loads((_FIXTURES / "kraken_ohlc_xxbtzeur_1440.json").read_text())["result"]["XXBTZEUR"]


def test_to_frame_schema_and_dtypes():
    frame = to_frame(ROWS)
    assert frame.columns == ["ts", "open", "high", "low", "close", "vwap", "volume", "count"]
    assert frame.schema["ts"] == pl.Datetime("us", "UTC")
    for col in ("open", "high", "low", "close", "vwap", "volume"):
        assert frame.schema[col] == pl.Float64
    assert frame.schema["count"] == pl.Int64


def test_to_frame_parses_string_decimals_and_epoch_ts():
    frame = to_frame(ROWS)
    first = frame.row(0, named=True)
    assert first["open"] == 59740.4
    assert first["volume"] == 490.10621523
    assert first["count"] == 17570
    assert str(first["ts"]) == "2024-07-17 00:00:00+00:00"


def test_to_frame_sorts_and_dedupes_exact_duplicate_rows():
    shuffled = [ROWS[2], ROWS[0], ROWS[1], ROWS[0]]  # out of order + an exact duplicate
    frame = to_frame(shuffled)
    assert frame.height == 3
    assert frame["ts"].is_sorted()


def test_to_frame_raises_on_nan_value():
    bad_rows = [list(ROWS[0])]
    bad_rows[0][1] = "NaN"
    with pytest.raises(OHLCError):
        to_frame(bad_rows)


def test_to_frame_raises_on_conflicting_duplicate_timestamp():
    conflicting = list(ROWS[0])
    conflicting[4] = "999999.0"  # same ts as ROWS[0], different close
    with pytest.raises(OHLCError):
        to_frame([ROWS[0], conflicting])


def test_write_parquet_read_parquet_roundtrip(tmp_path):
    frame = to_frame(ROWS)
    path = tmp_path / "nested" / "1440.parquet"
    write_parquet(frame, path)
    assert path.exists()
    roundtripped = read_parquet(path)
    assert roundtripped.equals(frame)


def test_dataset_hash_deterministic():
    a = dataset_hash(to_frame(ROWS))
    b = dataset_hash(to_frame(ROWS))
    assert a == b
    assert len(a) == 64


def test_dataset_hash_changes_when_value_changes():
    mutated = list(ROWS)
    mutated[0] = list(mutated[0])
    mutated[0][1] = "1.0"
    assert dataset_hash(to_frame(ROWS)) != dataset_hash(to_frame(mutated))
