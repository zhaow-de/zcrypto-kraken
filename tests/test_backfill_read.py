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


def test_read_minute_rows_merges_base_and_quarterly_sorted_deduped(tmp_path):
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
            # overlapping ts with the base dump — exact duplicate, must be de-duped
            "XBTEUR_1.csv": (
                "1700000060,42005.0,42020.0,42000.0,42015.0,2.0,8\n1700000120,42015.0,42030.0,42010.0,42025.0,1.0,5\n"
            ),
        },
    )

    rows = read_minute_rows(tmp_path, "BTC/EUR")

    assert [r[0] for r in rows] == [1700000000, 1700000060, 1700000120]
    assert rows[0] == [1700000000, "42000.0", "42010.0", "41990.0", "42005.0", "1.5", "12"]


def test_read_minute_rows_raises_on_missing_pair(tmp_path):
    _write_zip(tmp_path / "Kraken_OHLCVT.zip", {"master_q4/ETHEUR_1.csv": "1700000000,1,1,1,1,1,1\n"})

    with pytest.raises(BackfillError):
        read_minute_rows(tmp_path, "BTC/EUR")


def test_read_minute_rows_raises_on_same_ts_conflict(tmp_path):
    _write_zip(
        tmp_path / "Kraken_OHLCVT.zip",
        {"master_q4/XBTEUR_1.csv": "1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12\n"},
    )
    _write_zip(
        tmp_path / "Kraken_OHLCVT_Q1_2099.zip",
        # same ts, different OHLC — an unresolvable conflict between sources
        {"XBTEUR_1.csv": "1700000000,99999.0,99999.0,99999.0,99999.0,1.5,12\n"},
    )

    with pytest.raises(BackfillError):
        read_minute_rows(tmp_path, "BTC/EUR")
