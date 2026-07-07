from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cli.backfill.errors import BackfillError
from cli.backfill.read import dump_pair_name, read_minute_rows


def test_dump_pair_name_maps_all_universe_pairs():
    cases = {
        "BTC/EUR": "XBTEUR",
        "ETH/EUR": "ETHEUR",
        "SOL/EUR": "SOLEUR",
        "XRP/EUR": "XRPEUR",
        "ADA/EUR": "ADAEUR",
        "LINK/EUR": "LINKEUR",
        "DOGE/EUR": "XDGEUR",
        "LTC/EUR": "LTCEUR",
        "DOT/EUR": "DOTEUR",
        "AVAX/EUR": "AVAXEUR",
        "ETH/BTC": "ETHXBT",
        "SOL/BTC": "SOLXBT",
    }
    for sym, want in cases.items():
        assert dump_pair_name(sym) == want


def test_dump_pair_name_rejects_non_base_quote_symbol():
    with pytest.raises(BackfillError):
        dump_pair_name("BTCEUR")


def _write_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_read_minute_rows_quarterly_extends_past_base_max_ts(tmp_path):
    _write_zip(
        tmp_path / "Kraken_OHLCVT.zip",
        {
            "master_q4/XBTEUR_1.csv": (
                "1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12\n1700000060,42005.0,42020.0,42000.0,42015.0,2.0,8\n"
            ),
            "__MACOSX/master_q4/._XBTEUR_1.csv": "garbage",
        },
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        {
            # ts=1700000060 duplicates the base's last ts with a DIFFERENT volume/trades — dropped
            # outright (base wins, no conflict check); ts=1700000120 is beyond the base's range and
            # extends the series.
            "XBTEUR_1.csv": (
                "1700000060,42005.0,42020.0,42000.0,42015.0,9.9,99\n1700000120,42015.0,42030.0,42010.0,42025.0,1.0,5\n"
            ),
        },
    )

    rows = read_minute_rows(tmp_path, "BTC/EUR")

    assert [r[0] for r in rows] == [1700000000, 1700000060, 1700000120]
    assert rows[1] == [1700000060, "42005.0", "42020.0", "42000.0", "42015.0", "2.0", "8"]  # base wins
    assert rows[2] == [1700000120, "42015.0", "42030.0", "42010.0", "42025.0", "1.0", "5"]  # quarterly extension


def test_read_minute_rows_raises_on_missing_pair(tmp_path):
    _write_zip(tmp_path / "Kraken_OHLCVT.zip", {"master_q4/ETHEUR_1.csv": "1700000000,1,1,1,1,1,1\n"})

    with pytest.raises(BackfillError):
        read_minute_rows(tmp_path, "BTC/EUR")


def test_read_minute_rows_base_wins_within_overlap_range(tmp_path):
    # the base dump is authoritative for its own ts range; a quarterly row at the same ts with a
    # DIFFERENT volume/trades count (the base<->quarterly overlap disagreement seen on the real
    # archive) is ignored outright — the base's value wins, no conflict raised.
    _write_zip(
        tmp_path / "Kraken_OHLCVT.zip",
        {"master_q4/XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12\n"},
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,0.5,3\n"},
    )

    rows = read_minute_rows(tmp_path, "BTC/EUR")

    assert rows == [[1700000000, "42000.0", "42010.0", "41990.0", "42005.0", "1.5", "12"]]


def test_read_minute_rows_uses_all_quarterly_rows_when_pair_absent_from_base(tmp_path):
    _write_zip(tmp_path / "Kraken_OHLCVT.zip", {"master_q4/ETHEUR_1.csv": "1700000000,1,1,1,1,1,1\n"})
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12\n"},
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q2_2099.zip",
        {"XBTEUR_1.csv": "1700000060,42005.0,42020.0,42000.0,42015.0,2.0,8\n"},
    )

    rows = read_minute_rows(tmp_path, "BTC/EUR")

    assert [r[0] for r in rows] == [1700000000, 1700000060]


def test_read_minute_rows_dedupes_same_ts_formatting_difference_across_quarterlies(tmp_path):
    # pair absent from the base dump, so both quarterlies' rows are kept in full; they disagree only
    # on trailing-zero formatting (1.50 vs 1.5) at the same ts — numerically identical, so the
    # defensive same-ts dedup (now only exercised across sibling quarterlies) must not treat this as
    # a conflict.
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.50,12\n"},
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q2_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12\n"},
    )

    rows = read_minute_rows(tmp_path, "BTC/EUR")

    assert [r[0] for r in rows] == [1700000000]


def test_read_minute_rows_raises_on_genuine_numeric_conflict_across_quarterlies(tmp_path):
    # pair absent from the base dump; two quarterlies disagree genuinely (not just formatting) at the
    # same ts — an unresolvable conflict, so this must still raise even though neither side is the base.
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.50,12\n"},
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q2_2099.zip",
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42006.0,1.5,12\n"},
    )

    with pytest.raises(BackfillError):
        read_minute_rows(tmp_path, "BTC/EUR")


def test_read_minute_rows_raises_backfill_error_on_malformed_row(tmp_path):
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        # malformed line: only 6 fields (missing trades count)
        {"XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.5\n"},
    )

    with pytest.raises(BackfillError) as exc_info:
        read_minute_rows(tmp_path, "BTC/EUR")
    assert not isinstance(exc_info.value, ValueError)
