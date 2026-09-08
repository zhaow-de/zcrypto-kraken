from __future__ import annotations

import zipfile

import pytest

from cli.tick.errors import TickError
from cli.tick.read import read_trades_csv


def test_read_trades_csv_headered(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text(
        "Price,Volume,Timestamp,Type,Miscellaneous,Trade ID\n100.5,1.0,1700000000.123456,b,,1\n101.0,2.0,1700000060.5,s,,2\n"
    )

    frame = read_trades_csv(path)

    assert frame.columns == ["ts", "price", "volume", "side"]
    assert frame["price"].to_list() == [100.5, 101.0]
    assert frame["volume"].to_list() == [1.0, 2.0]
    assert frame["side"].to_list() == ["b", "s"]
    assert str(frame["ts"].dtype) == "Datetime(time_unit='us', time_zone='UTC')"
    assert frame["ts"][0].isoformat() == "2023-11-14T22:13:20.123456+00:00"


def test_read_trades_csv_headerless(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.5,1.0,1700000000.123456,b\n101.0,2.0,1700000060.5,s\n")

    frame = read_trades_csv(path)

    assert frame.height == 2
    assert frame["price"].to_list() == [100.5, 101.0]
    assert frame["side"].to_list() == ["b", "s"]


def test_read_trades_csv_ignores_extra_trailing_columns(tmp_path):
    # the real quarterly ZIPs carry extra columns beyond Price,Volume,Timestamp,Type (order type,
    # misc, trade id) that the header row doesn't even fully name — ignored positionally.
    path = tmp_path / "XBTEUR.csv"
    path.write_text("Price,Volume,Timestamp,Type,Miscellaneous,Trade ID\n100.5,1.0,1700000000.0,b,l,,1\n")

    frame = read_trades_csv(path)

    assert frame.columns == ["ts", "price", "volume", "side"]
    assert frame["price"].to_list() == [100.5]


def test_read_trades_csv_raises_on_bad_numeric_value(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("abc,1.0,1700000000.0,b\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_raises_on_bad_numeric_value_on_a_data_row(tmp_path):
    # a valid first row makes this headerless (sniff sees numeric leading fields), so the bad numeric
    # on row 2 reaches the numeric-cast guard rather than being skipped as a header
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.0,1.0,1700000000.0,b\nabc,1.0,1700000060.0,s\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_headerless_corrupted_first_row_raises_not_silently_dropped(tmp_path):
    # headerless; row 1's Price field is garbage but Volume/Timestamp are numeric — it must NOT be
    # sniffed as a header and silently dropped; it must raise (the never-silent-misparse contract)
    path = tmp_path / "XBTEUR.csv"
    path.write_text("garbage,1.0,1700000000.0,b\n100.5,2.0,1700000060.0,s\n101.0,1.5,1700000120.0,b\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_raises_on_row_missing_a_field(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.0,1.0,1700000000.0,b\n100.0,1.0,1700000060.0\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_raises_when_every_row_is_too_short(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.0,1.0,1700000000.0\n100.0,1.0,1700000060.0\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_complete_3col_format(tmp_path):
    # the complete dataset is headerless 3-field ts,price,volume (different order, no side)
    path = tmp_path / "XBTEUR.csv"
    path.write_text("1378856831,97.0,1.0\n1378859634,99.9,0.1\n")

    frame = read_trades_csv(path)

    assert frame.height == 2
    assert frame["price"].to_list() == [97.0, 99.9]
    assert frame["volume"].to_list() == [1.0, 0.1]
    assert frame["ts"][0].year == 2013  # field 0 is the timestamp, not the price
    assert frame["side"].to_list() == [None, None]  # side is unavailable in this schema


def test_read_trades_csv_complete_3col_from_zip_member(tmp_path):
    zip_path = tmp_path / "Kraken_Trading_History.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("TimeAndSales_Combined/XBTEUR.csv", "1378856831,97.0,1.0\n")

    frame = read_trades_csv((zip_path, "TimeAndSales_Combined/XBTEUR.csv"))

    assert frame.height == 1
    assert frame["price"].to_list() == [97.0]
    assert frame["side"].to_list() == [None]


def test_read_trades_csv_raises_on_invalid_side(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.0,1.0,1700000000.0,x\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_raises_on_nan_price(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("NaN,1.0,1700000000.0,b\n")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_raises_on_empty_file(tmp_path):
    path = tmp_path / "XBTEUR.csv"
    path.write_text("")

    with pytest.raises(TickError):
        read_trades_csv(path)


def test_read_trades_csv_from_zip_member(tmp_path):
    zip_path = tmp_path / "Kraken_Trading_History_Q1_2099.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("XBTEUR.csv", "Price,Volume,Timestamp,Type,Miscellaneous,Trade ID\n100.5,1.0,1700000000.0,b,,1\n")
        zf.writestr("ETHEUR.csv", "Price,Volume,Timestamp,Type,Miscellaneous,Trade ID\n2000.0,0.5,1700000000.0,s,,2\n")

    frame = read_trades_csv((zip_path, "XBTEUR.csv"))

    assert frame.height == 1
    assert frame["price"].to_list() == [100.5]
    assert frame["side"].to_list() == ["b"]


def test_read_trades_csv_from_zip_member_str_path(tmp_path):
    # the zip path may be a str, not only a Path — coerced internally
    zip_path = tmp_path / "Kraken_Trading_History_Q1_2099.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("XBTEUR.csv", "Price,Volume,Timestamp,Type,Miscellaneous,Trade ID\n100.5,1.0,1700000000.0,b,,1\n")

    frame = read_trades_csv((str(zip_path), "XBTEUR.csv"))

    assert frame.height == 1
    assert frame["price"].to_list() == [100.5]


def test_read_trades_csv_zip_member_not_found_raises(tmp_path):
    zip_path = tmp_path / "Kraken_Trading_History_Q1_2099.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("XBTEUR.csv", "100.5,1.0,1700000000.0,b\n")

    with pytest.raises(TickError):
        read_trades_csv((zip_path, "ETHEUR.csv"))


def test_read_trades_csv_corrupted_zip_raises(tmp_path):
    zip_path = tmp_path / "broken.zip"
    zip_path.write_bytes(b"not a zip file")

    with pytest.raises(TickError):
        read_trades_csv((zip_path, "XBTEUR.csv"))


@pytest.mark.parametrize(
    ("name", "first_field"),
    [
        ("milliseconds", "1699999999000"),
        ("microseconds", "1699999999000000"),
        ("nanoseconds", "1699999999000000000"),
        ("overflowing float", "1e300"),
        ("infinity", "inf"),
    ],
)
def test_read_trades_csv_refuses_a_ts_that_is_not_epoch_seconds(tmp_path, name, first_field):
    """A `ts` outside the plausible epoch-SECONDS range is refused, whichever way it fails.

    Milliseconds is the case that used to PASS: read as ~year 55000, filtered out by the caller's
    window, reported as 0% coverage rather than as unreadable input."""
    path = tmp_path / "XBTEUR.csv"
    path.write_text(f"{first_field},100.5,2.0\n{first_field},101.0,1.0\n")

    with pytest.raises(TickError) as caught:
        read_trades_csv(path)
    assert "epoch seconds" in str(caught.value)
    assert "XBTEUR.csv" in str(caught.value)


def test_read_trades_csv_refuses_a_ts_below_the_epoch_floor(tmp_path):
    """The floor at its VALUE: one second below it still casts and converts, so only the floor refuses
    it and any lowering at all accepts it. The row is quarterly-shaped because a 3-field row whose
    first field is below `_MIN_UNIX_TS` is not "complete" by `_detect_schema`, and dies as a short row
    before any value check sees it."""
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.5,2.0,999999999,b\n101.0,1.0,999999999,s\n")

    with pytest.raises(TickError) as caught:
        read_trades_csv(path)
    assert "epoch seconds" in str(caught.value)


def test_read_trades_csv_bounds_are_the_values_the_constants_name(tmp_path):
    """Both endpoints accepted at their exact values, and the ceiling refused one second above. The
    floor's refusing side is `test_read_trades_csv_refuses_a_ts_below_the_epoch_floor`, feeding the
    second below it -- a copy of that case here would be one pin counted twice, not two."""

    def _read(name: str, text: str):
        path = tmp_path / f"XBTEUR-{name}.csv"
        path.write_text(text)
        return read_trades_csv(path)

    with pytest.raises(TickError, match="epoch seconds"):  # one second past the ceiling
        _read("past-ceiling", "4000000001,100.5,2.0\n4000000001,101.0,1.0\n")
    assert _read("floor", "1000000000,100.5,2.0\n1000000000,101.0,1.0\n").height == 2
    assert _read("ceiling", "4000000000,100.5,2.0\n4000000000,101.0,1.0\n").height == 2


def test_read_trades_csv_refuses_a_nan_ts_as_nan_not_as_out_of_range(tmp_path):
    """Pins the check's POSITION: it must sit below the NaN check, or a NaN ts is reported as a range
    fault -- a message naming a neighbouring problem, which is what the guard exists to avoid."""
    path = tmp_path / "XBTEUR.csv"
    path.write_text("100.5,2.0,nan,b\n101.0,1.0,nan,s\n")

    with pytest.raises(TickError, match="NaN price/volume/ts"):
        read_trades_csv(path)


def test_read_trades_csv_still_reads_a_valid_seconds_file(tmp_path):
    """The true positive: the range guard must not refuse the data it exists to protect."""
    path = tmp_path / "XBTEUR.csv"
    path.write_text("1700000000.123456,100.5,2.0\n1700000060.5,101.0,1.0\n")

    frame = read_trades_csv(path)

    assert frame["ts"][0].isoformat() == "2023-11-14T22:13:20.123456+00:00"
    assert frame["price"].to_list() == [100.5, 101.0]
