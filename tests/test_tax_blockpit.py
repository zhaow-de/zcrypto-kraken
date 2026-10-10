import ast
import csv
import hashlib
import io
import json
import re
import zipfile
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.tax import blockpit
from cli.tax.errors import Refused, TaxExportError
from cli.tax.kraken_export import read_ledger, read_trades

FIXTURES = Path(__file__).parent / "fixtures" / "tax_blockpit"
LEDGER_1 = FIXTURES / "window-1-ledgers.csv"
TRADES_1 = FIXTURES / "window-1-trades.csv"
LEDGER_2 = FIXTURES / "window-2-ledgers.csv"
TRADES_2 = FIXTURES / "window-2-trades.csv"
# The template's two files as fetched 2026-10-09 (spec 00126 D8), held byte for byte.
TEMPLATE_SHA256 = {
    "blockpit-template.xlsx": "fa48315e27f1b6413418d6964793e4b5841e4a336fcf9064ae921eedd3f61acf",
    "blockpit-template-gid0.csv": "914ab78ebd09b88ad899f75429e6ed107b2ceb79ab61ebf74c06d3ec304e078a",
}


def _template_labels() -> list[str]:
    sheet = zipfile.ZipFile(FIXTURES / "blockpit-template.xlsx").read("xl/worksheets/sheet1.xml").decode()
    (formula,) = re.findall(r'<dataValidation type="list"[^>]*sqref="C2:C986"><formula1>(.*?)</formula1>', sheet)
    return "".join(re.findall(r"&quot;(.*?)&quot;", formula)).split(",")


def _edited(tmp_path: Path, source: Path, edits: list[tuple[str, str | None, str | None]]) -> Path:
    """`source` with each (txid, column, value) applied; a None column drops the row."""
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for txid, column, value in edits:
        (row,) = [row for row in rows if row["txid"] == txid]
        if column is None:
            rows.remove(row)
        else:
            row[column] = value
    target = tmp_path / source.name
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return target


def _without(tmp_path: Path, source: Path, column: str) -> Path:
    rows = [line.split(",") for line in source.read_text().splitlines()]
    at = rows[0].index(f'"{column}"')
    target = tmp_path / source.name
    target.write_text("\n".join(",".join(row[:at] + row[at + 1 :]) for row in rows) + "\n")
    return target


@pytest.mark.parametrize("name", sorted(TEMPLATE_SHA256))
def test_the_templates_files_are_as_fetched(name):
    assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == TEMPLATE_SHA256[name]


def test_the_header_is_the_templates_first_row():
    with (FIXTURES / "blockpit-template-gid0.csv").open(newline="", encoding="utf-8") as handle:
        assert tuple(next(csv.reader(handle))) == blockpit.HEADER


def test_the_labels_are_the_templates_dropdown():
    assert list(blockpit.TEMPLATE_LABELS) == _template_labels()
    assert len(blockpit.TEMPLATE_LABELS) == 33


def test_the_ledger_reader_keeps_the_exports_own_strings():
    rows = read_ledger(LEDGER_1)
    assert len(rows) == 31
    first = rows[0]
    assert (first.txid, first.type, first.asset, first.amount, first.wallet) == (
        "LFX001-SYNTH-LEDGER",
        "deposit",
        "EUR",
        "1250.0",
        "spot / main",
    )
    assert read_ledger(LEDGER_2)[2].amountusd == "-"


def test_the_trades_reader_reads_the_closing_flag_the_position_and_the_ledger_ids():
    trades = read_trades(TRADES_1)
    assert len(trades) == 12
    close = trades["TFX006-SYNTH-TRADES"]
    assert close.closing and close.posttxid == "TFX004-SYNTH-TRADES" and close.ledgers == ("LFX012-SYNTH-LEDGER",)
    opening = trades["TFX004-SYNTH-TRADES"]
    assert not opening.closing
    assert opening.ledgers == ("LFX010-SYNTH-LEDGER", "LFX009-SYNTH-LEDGER", "LFX008-SYNTH-LEDGER")


def test_a_missing_column_is_refused_by_name(tmp_path):
    with pytest.raises(TaxExportError, match="wallet"):
        read_ledger(_without(tmp_path, LEDGER_1, "wallet"))


@pytest.mark.parametrize(
    "column,value",
    [("time", "2031-03-03T09:00:00Z"), ("amount", "abc"), ("balance", "NaN")],
    ids=["time_the_export_does_not_write", "amount_the_export_does_not_write", "balance_not_finite"],
)
def test_a_value_the_export_does_not_write_is_refused(tmp_path, column, value):
    with pytest.raises(TaxExportError, match="LFX001-SYNTH-LEDGER"):
        read_ledger(_edited(tmp_path, LEDGER_1, [("LFX001-SYNTH-LEDGER", column, value)]))
