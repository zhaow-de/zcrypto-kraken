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


def test_window_one_maps_to_its_golden_rows():
    mapped = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1))
    assert mapped.refusals == []
    assert blockpit.render_csv(mapped.rows) == (FIXTURES / "window-1-blockpit.csv").read_bytes()


def _mapped_rows() -> list[dict[str, str]]:
    body = blockpit.render_csv(blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows).decode()
    return list(csv.DictReader(io.StringIO(body)))


def test_every_label_the_mapping_writes_is_a_template_label():
    mapped = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1))
    assert {row.label for row in mapped.rows} <= set(_template_labels())
    assert {row.label for row in mapped.rows} == {
        "Trade",
        "Deposit",
        "Non-Taxable In",
        "Staking",
        "Margin Profit",
        "Margin Loss",
        "Margin Fee",
    }


def test_a_label_outside_the_template_is_refused_as_the_file_is_written():
    stray = blockpit.OutRow(
        "2031-03-03 09:00:00", "Unlabeled", "", "", "EUR", "1250.0", "", "", "kraken deposit", "LFX001-SYNTH-LEDGER", (0, 0)
    )
    with pytest.raises(TaxExportError, match="'Unlabeled' is not one of the template's labels"):
        blockpit.render_csv([stray])


def test_every_asset_moves_in_the_mapped_rows_as_in_the_ledger():
    want, got = {}, {}
    for row in read_ledger(LEDGER_1):
        want[row.asset] = want.get(row.asset, Decimal(0)) + Decimal(row.amount) - Decimal(row.fee)
    for row in blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows:
        for asset, moved in blockpit._moves(row):
            got[asset] = got.get(asset, Decimal(0)) + moved
    assert got == want


def test_no_assets_balance_runs_below_zero_in_the_written_order():
    held = {}
    for row in blockpit._written(blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows):
        for asset, moved in blockpit._moves(row):
            held[asset] = held.get(asset, Decimal(0)) + moved
            assert held[asset] >= 0, (asset, row.trx_id)


def test_a_margin_close_with_pnl_splits_its_fee_into_its_own_row():
    rows = [row for row in _mapped_rows() if row["Trx. ID (optional)"].startswith("LFX015-")]
    assert [
        (r["Label"], r["Incoming Amount"], r["Outgoing Amount"], r["Fee Amount (optional)"], r["Trx. ID (optional)"]) for r in rows
    ] == [
        ("Margin Profit", "1.75", "", "", "LFX015-SYNTH-LEDGER"),
        ("Margin Fee", "", "0.065", "", "LFX015-SYNTH-LEDGER-fee"),
    ]


def test_a_conversion_pair_is_one_trade_from_eur_to_eurc():
    (row,) = [row for row in _mapped_rows() if row["Trx. ID (optional)"] == "TFX009-SYNTH-TRADES"]
    assert (row["Label"], row["Outgoing Asset"], row["Outgoing Amount"], row["Incoming Asset"], row["Incoming Amount"]) == (
        "Trade",
        "EUR",
        "0.825",
        "EURC",
        "0.825",
    )
    assert row["Comment (optional)"].endswith("position TFX008-SYNTH-TRADES")


def test_a_small_balance_conversion_shares_the_receive_by_amountusd():
    rows = [row for row in _mapped_rows() if "dustsweeping" in row["Comment (optional)"]]
    assert [(r["Outgoing Asset"], r["Incoming Amount"]) for r in rows] == [("XTZ", "0.000201923"), ("NEAR", "0.000098077")]


def test_a_one_leg_trade_writes_the_absent_leg_at_zero():
    (row,) = [row for row in _mapped_rows() if row["Trx. ID (optional)"] == "TFX003-SYNTH-TRADES"]
    assert (row["Outgoing Asset"], row["Outgoing Amount"], row["Incoming Asset"], row["Incoming Amount"]) == (
        "EUR",
        "0",
        "XTZ",
        "0.00004",
    )


def test_a_one_leg_debit_writes_the_absent_leg_incoming_at_zero(tmp_path):
    ledger = _edited(tmp_path, LEDGER_1, [("LFX007-SYNTH-LEDGER", "amount", "-0.00004")])
    rows = blockpit.map_rows(read_ledger(ledger), read_trades(TRADES_1)).rows
    (row,) = [row for row in rows if row.trx_id == "TFX003-SYNTH-TRADES"]
    assert (row.out_asset, row.out_amount, row.in_asset, row.in_amount) == ("XTZ", "0.00004", "EUR", "0")


REFUSALS = [
    (
        "unknown_type",
        LEDGER_1,
        [("LFX027-SYNTH-LEDGER", "type", "adjustment"), ("LFX027-SYNTH-LEDGER", "subtype", "")],
        "no mapping is written",
    ),
    ("unknown_subtype", LEDGER_1, [("LFX027-SYNTH-LEDGER", "subtype", "allocation")], "no mapping is written"),
    (
        "unknown_type_at_zero",
        LEDGER_1,
        [("LFX013-SYNTH-LEDGER", "type", "adjustment"), ("LFX013-SYNTH-LEDGER", "fee", "0.0")],
        "no mapping is written",
    ),
    ("wallet", LEDGER_1, [("LFX027-SYNTH-LEDGER", "wallet", "earn / flexible")], "is not 'spot / main'"),
    ("fee_currency", LEDGER_1, [("LFX003-SYNTH-LEDGER", "feecurrency", "ALGO")], "a fee of 0.48 ALGO on a row in EUR"),
    ("negative_fee", LEDGER_1, [("LFX003-SYNTH-LEDGER", "fee", "-0.48")], "a fee of -0.48 EUR on a row in EUR"),
    ("split_times", LEDGER_1, [("LFX004-SYNTH-LEDGER", "time", "2031-03-03 10:00:01")], "carry different times"),
    (
        "three_rows",
        LEDGER_1,
        [("LFX007-SYNTH-LEDGER", "refid", "TFX001-SYNTH-TRADES"), ("LFX007-SYNTH-LEDGER", "time", "2031-03-03 10:00:00")],
        "3 ledger rows where a pair is two",
    ),
    ("trade_one_sign", LEDGER_1, [("LFX003-SYNTH-LEDGER", "amount", "120.0")], "not one out and one in"),
    ("settled_one_sign", LEDGER_1, [("LFX024-SYNTH-LEDGER", "amount", "-2.6")], "not one out and one in"),
    ("trade_zero_leg", LEDGER_1, [("LFX003-SYNTH-LEDGER", "amount", "0.0")], "not one out and one in"),
    ("trade_zero_credit", LEDGER_1, [("LFX006-SYNTH-LEDGER", "amount", "0.0")], "not one out and one in"),
    ("one_asset", LEDGER_1, [("LFX004-SYNTH-LEDGER", "asset", "EUR")], "the two rows are one asset"),
    (
        "fee_on_both_legs",
        LEDGER_1,
        [("LFX004-SYNTH-LEDGER", "fee", "0.105"), ("LFX004-SYNTH-LEDGER", "feecurrency", "ALGO")],
        "a fee on both rows",
    ),
    ("one_leg_off_its_pair", TRADES_1, [("TFX003-SYNTH-TRADES", "pair", "NEAR/EUR")], "XTZ is neither side of NEAR/EUR"),
    ("conversion_not_eur_to_eurc", LEDGER_1, [("LFX010-SYNTH-LEDGER", "asset", "USDC")], "not one EUR row out and one EURC row in"),
    ("conversion_not_from_eur", LEDGER_1, [("LFX009-SYNTH-LEDGER", "asset", "USDC")], "not one EUR row out and one EURC row in"),
    (
        "conversion_with_a_fee",
        LEDGER_1,
        [("LFX016-SYNTH-LEDGER", "fee", "0.0035"), ("LFX016-SYNTH-LEDGER", "feecurrency", "EUR")],
        "not one EUR row out and one EURC row in, without a fee",
    ),
    (
        "conversion_with_a_third_row",
        LEDGER_1,
        [
            ("LFX018-SYNTH-LEDGER", "type", "collateralconversion"),
            ("LFX018-SYNTH-LEDGER", "amount", "-0.075"),
            ("LFX018-SYNTH-LEDGER", "fee", "0.0"),
            ("LFX018-SYNTH-LEDGER", "feecurrency", ""),
        ],
        "not one EUR row out and one EURC row in, without a fee",
    ),
    (
        "margin_without_its_trade",
        LEDGER_1,
        [("LFX011-SYNTH-LEDGER", "refid", "TFX099-SYNTH-TRADES")],
        "no row of the trades export is TFX099-SYNTH-TRADES",
    ),
    ("closing_without_a_position", TRADES_1, [("TFX006-SYNTH-TRADES", "posttxid", "")], "names no position"),
    ("deposit_credits_nothing", LEDGER_1, [("LFX001-SYNTH-LEDGER", "amount", "-1250.0")], "a deposit that credits nothing"),
    ("reward_credits_nothing", LEDGER_1, [("LFX026-SYNTH-LEDGER", "amount", "-0.35")], "a reward that credits nothing"),
    ("rollover_moves_an_amount", LEDGER_1, [("LFX013-SYNTH-LEDGER", "amount", "0.0035")], "a rollover that moves an amount"),
    ("sweep_without_a_receive", LEDGER_1, [("LFX031-SYNTH-LEDGER", None, None)], "not one receive without a fee"),
    ("sweep_with_two_receives", LEDGER_1, [("LFX029-SYNTH-LEDGER", "type", "receive")], "not one receive without a fee"),
    (
        "sweep_without_a_spend",
        LEDGER_1,
        [("LFX029-SYNTH-LEDGER", None, None), ("LFX030-SYNTH-LEDGER", None, None)],
        "at least one spend",
    ),
    (
        "sweep_receive_with_a_fee",
        LEDGER_1,
        [("LFX031-SYNTH-LEDGER", "fee", "0.0003"), ("LFX031-SYNTH-LEDGER", "feecurrency", "EUR")],
        "not one receive without a fee",
    ),
    ("sweep_receive_credits_nothing", LEDGER_1, [("LFX031-SYNTH-LEDGER", "amount", "-0.0003")], "a receive that credits nothing"),
    ("sweep_spend_debits_nothing", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amount", "0.00004")], "a spend that debits nothing"),
    ("sweep_amountusd_missing", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amountusd", "-")], "cannot be shared"),
    ("sweep_amountusd_not_finite", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amountusd", "NaN")], "cannot be shared"),
    (
        "sweep_amountusd_zero",
        LEDGER_1,
        [("LFX029-SYNTH-LEDGER", "amountusd", "0.0"), ("LFX030-SYNTH-LEDGER", "amountusd", "0.0")],
        "cannot be shared",
    ),
    (
        "sweep_of_one_spend_amountusd_zero",
        LEDGER_1,
        [("LFX030-SYNTH-LEDGER", None, None), ("LFX029-SYNTH-LEDGER", "amountusd", "0.0")],
        "cannot be shared",
    ),
]


def _refusal_inputs(tmp_path: Path, source: Path, edits: list[tuple[str, str | None, str | None]]) -> tuple[Path, Path]:
    return (
        _edited(tmp_path, LEDGER_1, edits) if source == LEDGER_1 else LEDGER_1,
        _edited(tmp_path, TRADES_1, edits) if source == TRADES_1 else TRADES_1,
    )


@pytest.mark.parametrize("source,edits,reason", [case[1:] for case in REFUSALS], ids=[case[0] for case in REFUSALS])
def test_each_unmappable_shape_is_refused_by_the_mapping(tmp_path, source, edits, reason):
    ledger, trades = _refusal_inputs(tmp_path, source, edits)
    mapped = blockpit.map_rows(read_ledger(ledger), read_trades(trades))
    assert any(reason in refusal.reason for refusal in mapped.refusals), [r.line() for r in mapped.refusals]


def test_a_rollover_and_a_close_whose_open_is_an_earlier_windows_are_no_refusal():
    mapped = blockpit.map_rows(read_ledger(LEDGER_2), read_trades(TRADES_2))
    assert mapped.refusals == []
    assert mapped.positions == {"TFX012-SYNTH-TRADES": ["LFX101-SYNTH-LEDGER", "LFX102-SYNTH-LEDGER"]}
