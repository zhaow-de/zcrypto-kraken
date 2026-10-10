import ast
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
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
# The template's two files as fetched (spec 00126 D8).
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


def test_a_trades_row_without_its_ledger_rows_is_refused(tmp_path):
    trades = read_trades(_edited(tmp_path, TRADES_1, [("TFX003-SYNTH-TRADES", "ledgers", "LFX999-SYNTH-LEDGER")]))
    (refusal,) = blockpit.check_cross(read_ledger(LEDGER_1), trades)
    assert refusal.txids == ("TFX003-SYNTH-TRADES",) and refusal.kind == "trades"


def test_a_trades_row_naming_one_present_ledger_id_is_enough():
    assert blockpit.check_cross(read_ledger(LEDGER_1), read_trades(TRADES_1)) == []


def _run(
    tmp_path: Path, ledger: Path = LEDGER_1, trades: Path = TRADES_1, after: Path | None = None, name: str = "window-1-blockpit.csv"
):
    return blockpit.transform(ledger, trades, tmp_path / name, after)


def _provenance(path: Path) -> dict:
    record = json.loads(path.read_text())
    return {key: value for key, value in record.items() if key not in ("zcrypto", "previous")}


def test_a_run_writes_window_ones_golden_rows_and_provenance(tmp_path):
    written = _run(tmp_path)
    assert written.out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()
    assert _provenance(written.provenance) == json.loads((FIXTURES / "window-1-blockpit.csv.provenance.json").read_text())
    text = written.provenance.read_text()
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    record = json.loads(text)
    assert record["zcrypto"] == version("zcrypto") and record["previous"] is None


def test_two_runs_are_byte_equal(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    one, two = _run(first), _run(second)
    assert one.out.read_bytes() == two.out.read_bytes()
    assert one.provenance.read_bytes() == two.provenance.read_bytes()


def test_a_run_over_the_trades_rows_reordered_writes_the_same_file(tmp_path):
    header, *rows = TRADES_1.read_text().splitlines()
    (tmp_path / "reordered").mkdir()
    reordered = tmp_path / "reordered" / TRADES_1.name
    reordered.write_text("\n".join([header, *reversed(rows)]) + "\n")
    plain, shuffled = _run(tmp_path), _run(tmp_path, trades=reordered, name="reordered.csv")
    assert shuffled.out.read_bytes() == plain.out.read_bytes()


def test_the_provenance_hashes_are_the_files(tmp_path):
    written = _run(tmp_path)
    record = json.loads(written.provenance.read_text())
    assert record["output"]["sha256"] == hashlib.sha256(written.out.read_bytes()).hexdigest()
    assert record["inputs"]["ledgers"]["sha256"] == hashlib.sha256(LEDGER_1.read_bytes()).hexdigest()
    assert record["inputs"]["trades"]["sha256"] == hashlib.sha256(TRADES_1.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "edits",
    [[("LFX005-SYNTH-LEDGER", "balance", "320.0")], [("LFX013-SYNTH-LEDGER", None, None)]],
    ids=["balance_edited", "row_removed"],
)
def test_a_broken_balance_chain_is_refused_and_nothing_is_written(tmp_path, edits):
    ledger = _edited(tmp_path, LEDGER_1, edits)
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger)
    assert "balance" in {refusal.kind for refusal in caught.value.refusals}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["window-1-ledgers.csv"]


@pytest.mark.parametrize("source,edits,reason", [case[1:] for case in REFUSALS], ids=[case[0] for case in REFUSALS])
def test_each_refused_shape_writes_nothing(tmp_path, source, edits, reason):
    ledger, trades = _refusal_inputs(tmp_path, source, edits)
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger, trades=trades)
    assert any(reason in refusal.reason for refusal in caught.value.refusals), [r.line() for r in caught.value.refusals]
    assert sorted(tmp_path.iterdir()) == before


def test_a_mapping_that_loses_a_movement_is_refused_by_conservation(tmp_path, monkeypatch):
    monkeypatch.setitem(blockpit.SINGLE, ("rollover", ""), lambda row, trades, mapped: None)
    with pytest.raises(Refused) as caught:
        _run(tmp_path)
    assert [refusal.line() for refusal in caught.value.refusals] == [
        "refused - [conservation]: EUR moves 1174.1203 in the output and 1174.1133 in the ledger"
    ]


def test_two_rows_with_one_trx_id_are_refused():
    row = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows[0]
    (refusal,) = blockpit.check_unique([row, row])
    assert refusal.kind == "trx-id" and refusal.txids == (row.trx_id,)


def test_a_run_refuses_a_trades_row_without_its_ledger_rows(tmp_path):
    trades = _edited(tmp_path, TRADES_1, [("TFX003-SYNTH-TRADES", "ledgers", "LFX999-SYNTH-LEDGER")])
    with pytest.raises(Refused) as caught:
        _run(tmp_path, trades=trades)
    assert [refusal.kind for refusal in caught.value.refusals] == ["trades"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["window-1-trades.csv"]


def test_a_run_refuses_two_rows_with_one_trx_id(tmp_path, monkeypatch):
    deposit = blockpit.SINGLE[("deposit", "")]

    def twice(row, trades, mapped):
        deposit(row, trades, mapped)
        deposit(row, trades, mapped)

    monkeypatch.setitem(blockpit.SINGLE, ("deposit", ""), twice)
    with pytest.raises(Refused) as caught:
        _run(tmp_path)
    assert "trx-id" in {refusal.kind for refusal in caught.value.refusals}


@pytest.mark.parametrize(
    "existing", ["window-1-blockpit.csv", "window-1-blockpit.csv.provenance.json"], ids=["out_file", "provenance_file"]
)
def test_an_existing_output_is_never_overwritten(tmp_path, existing):
    (tmp_path / existing).write_text("{}")
    with pytest.raises(TaxExportError, match="never overwrites"):
        _run(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == [existing]
    assert (tmp_path / existing).read_text() == "{}"


def test_a_row_moving_nothing_is_counted_and_written_nowhere(tmp_path):
    edits = [
        ("LFX013-SYNTH-LEDGER", "fee", "0.0"),
        ("LFX013-SYNTH-LEDGER", "balance", "1189.065"),
        ("LFX014-SYNTH-LEDGER", "fee", "0.007"),
    ]
    written = _run(tmp_path, ledger=_edited(tmp_path, LEDGER_1, edits))
    assert json.loads(written.provenance.read_text())["no_movement"] == 1
    assert "LFX013-SYNTH-LEDGER" not in written.out.read_text()


def test_a_run_over_a_ledger_without_a_column_writes_nothing(tmp_path):
    ledger = _without(tmp_path, LEDGER_1, "wallet")
    before = sorted(tmp_path.iterdir())
    with pytest.raises(TaxExportError, match="wallet"):
        _run(tmp_path, ledger=ledger)
    assert sorted(tmp_path.iterdir()) == before


def _moved(path: Path, txid: str, before: str) -> Path:
    header, *rows = path.read_text().splitlines()
    (row,) = [line for line in rows if line.startswith(f"{txid},")]
    rows.remove(row)
    rows.insert(next(at for at, line in enumerate(rows) if line.startswith(f"{before},")), row)
    path.write_text("\n".join([header, *rows]) + "\n")
    return path


def test_a_written_order_that_runs_an_asset_below_zero_is_refused(tmp_path):
    # The sell's EUR credit first and its ALGO debit after the buy, one second: each balance chains, and the sell,
    # written at its first row, spends ALGO the buy has not yet credited.
    at = "2031-03-03 10:00:00"
    edits = [
        ("LFX006-SYNTH-LEDGER", "time", at),
        ("LFX006-SYNTH-LEDGER", "balance", "1309.76"),
        ("LFX003-SYNTH-LEDGER", "balance", "1189.28"),
        ("LFX005-SYNTH-LEDGER", "time", at),
    ]
    ledger = _moved(_edited(tmp_path, LEDGER_1, edits), "LFX006-SYNTH-LEDGER", before="LFX003-SYNTH-LEDGER")
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger)
    assert [refusal.line() for refusal in caught.value.refusals] == [
        "refused TFX002-SYNTH-TRADES [order]: ALGO runs to -160 at this row in the written order"
    ]
    assert sorted(tmp_path.iterdir()) == before


@pytest.mark.parametrize("source", [LEDGER_1, TRADES_1], ids=["ledgers", "trades"])
def test_each_input_is_read_once_and_its_rows_parse_the_bytes_it_hashed(tmp_path, monkeypatch, source):
    (tmp_path / "inputs").mkdir()
    copy = tmp_path / "inputs" / source.name
    copy.write_bytes(source.read_bytes())
    read_bytes = Path.read_bytes

    def read_then_empty(path: Path) -> bytes:
        data = read_bytes(path)
        if path == copy:
            copy.write_bytes(b"")
        return data

    monkeypatch.setattr(Path, "read_bytes", read_then_empty)
    ledger, trades = (copy, TRADES_1) if source == LEDGER_1 else (LEDGER_1, copy)
    written = _run(tmp_path, ledger=ledger, trades=trades)
    assert written.out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()
    assert _provenance(written.provenance) == json.loads((FIXTURES / "window-1-blockpit.csv.provenance.json").read_text())


def test_a_run_over_a_trades_export_without_a_column_writes_nothing(tmp_path):
    trades = _without(tmp_path, TRADES_1, "pair")
    before = sorted(tmp_path.iterdir())
    with pytest.raises(TaxExportError, match="has no pair column"):
        _run(tmp_path, trades=trades)
    assert sorted(tmp_path.iterdir()) == before


def test_window_two_after_window_one_maps_to_its_golden(tmp_path):
    first = _run(tmp_path)
    second = _run(tmp_path, LEDGER_2, TRADES_2, after=first.provenance, name="window-2-blockpit.csv")
    assert second.out.read_bytes() == (FIXTURES / "window-2-blockpit.csv").read_bytes()
    assert _provenance(second.provenance) == json.loads((FIXTURES / "window-2-blockpit.csv.provenance.json").read_text())
    assert json.loads(second.provenance.read_text())["previous"] == hashlib.sha256(first.provenance.read_bytes()).hexdigest()


def test_window_two_without_after_is_refused(tmp_path):
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, name="window-2-blockpit.csv")
    assert {refusal.reason for refusal in caught.value.refusals} == {
        "ATOM opens at 11.1025 and no --after names the window before",
        "EUR opens at 1174.1133 and no --after names the window before",
    }
    assert sorted(tmp_path.iterdir()) == before


def test_an_opening_unequal_to_the_previous_closing_is_refused(tmp_path):
    first = _run(tmp_path)
    record = json.loads(first.provenance.read_text())
    record["closing"]["EUR"] = "1174.1130"
    edited = tmp_path / "edited.provenance.json"
    edited.write_text(json.dumps(record))
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, after=edited, name="window-2-blockpit.csv")
    assert [refusal.reason for refusal in caught.value.refusals] == [
        "EUR opens at 1174.1133 where the window before closed at 1174.113"
    ]
    assert sorted(tmp_path.iterdir()) == before


def test_a_previous_window_that_does_not_end_before_this_one_is_refused(tmp_path):
    first = _run(tmp_path)
    record = json.loads(first.provenance.read_text())
    record["inputs"]["ledgers"]["last_time"] = "2031-04-01 10:00:00"
    edited = tmp_path / "edited.provenance.json"
    edited.write_text(json.dumps(record))
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, after=edited, name="window-2-blockpit.csv")
    assert [refusal.reason for refusal in caught.value.refusals] == [
        "this ledger's first time 2031-04-01 10:00:00 is not after the window before's last, 2031-04-01 10:00:00"
    ]
    assert sorted(tmp_path.iterdir()) == before


def _empty_window(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "empty").mkdir()
    ledger, trades = tmp_path / "empty" / LEDGER_1.name, tmp_path / "empty" / TRADES_1.name
    ledger.write_text(LEDGER_1.read_text().splitlines()[0] + "\n")
    trades.write_text(TRADES_1.read_text().splitlines()[0] + "\n")
    return ledger, trades


def test_an_empty_window_carries_the_chain_to_the_next(tmp_path):
    first = _run(tmp_path)
    empty = _run(tmp_path, *_empty_window(tmp_path), after=first.provenance, name="empty.csv")
    assert json.loads(empty.provenance.read_text())["inputs"]["ledgers"]["last_time"] == "2031-03-28 22:00:00"
    second = _run(tmp_path, LEDGER_2, TRADES_2, after=empty.provenance, name="window-2-blockpit.csv")
    assert second.out.read_bytes() == (FIXTURES / "window-2-blockpit.csv").read_bytes()


def test_a_window_after_an_empty_first_window_opens_from_zero(tmp_path):
    empty = _run(tmp_path, *_empty_window(tmp_path), name="empty.csv")
    assert json.loads(empty.provenance.read_text())["inputs"]["ledgers"]["last_time"] is None
    first = _run(tmp_path, after=empty.provenance)
    assert first.out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{}",
        '{"closing": {}, "inputs": []}',
        '{"closing": [], "inputs": {"ledgers": {"last_time": null}}}',
        '{"closing": {}, "inputs": {"ledgers": {"last_time": 5}}}',
    ],
    ids=["empty", "no_keys", "inputs_not_a_map", "closing_not_a_map", "last_time_not_a_string"],
)
def test_a_file_that_is_no_provenance_is_refused_as_after(tmp_path, text):
    after = tmp_path / "after.json"
    after.write_text(text)
    with pytest.raises(TaxExportError, match="not a provenance file"):
        _run(tmp_path, LEDGER_2, TRADES_2, after=after, name="window-2-blockpit.csv")


@pytest.mark.parametrize(
    "value",
    [None, 11.1025, "NaN", "abc"],
    ids=["closing_value_null", "closing_value_a_number", "closing_value_not_finite", "closing_value_not_a_decimal"],
)
def test_a_previous_closing_that_is_no_decimal_string_is_refused_by_its_asset(tmp_path, value):
    after = tmp_path / "after.json"
    after.write_text(json.dumps({"closing": {"ATOM": value, "EUR": "1174.1133"}, "inputs": {"ledgers": {"last_time": None}}}))
    with pytest.raises(TaxExportError, match="its closing ATOM is not a decimal string"):
        _run(tmp_path, LEDGER_2, TRADES_2, after=after, name="window-2-blockpit.csv")


@pytest.mark.parametrize(
    "role,shape,reason",
    [
        ("ledgers", "absent", "cannot be read"),
        ("trades", "absent", "cannot be read"),
        ("after", "absent", "cannot be read"),
        ("ledgers", "a_directory", "cannot be read"),
        ("ledgers", "not_utf8", "is not UTF-8 text"),
        ("trades", "not_utf8", "is not UTF-8 text"),
    ],
    ids=["ledgers_absent", "trades_absent", "after_absent", "ledgers_a_directory", "ledgers_not_utf8", "trades_not_utf8"],
)
def test_an_input_that_cannot_be_read_is_refused_by_its_path_and_nothing_is_written(tmp_path, role, shape, reason):
    inputs = {"ledgers": LEDGER_2, "trades": TRADES_2, "after": FIXTURES / "window-1-blockpit.csv.provenance.json"}
    (tmp_path / "inputs").mkdir()
    broken = tmp_path / "inputs" if shape == "a_directory" else tmp_path / "inputs" / inputs[role].name
    if shape == "not_utf8":
        broken.write_bytes(inputs[role].read_bytes() + b"\xff\n")
    inputs[role] = broken
    before = sorted(tmp_path.iterdir())
    with pytest.raises(TaxExportError, match=re.escape(f"{broken} {reason}")):
        _run(tmp_path, inputs["ledgers"], inputs["trades"], after=inputs["after"], name="window-2-blockpit.csv")
    assert sorted(tmp_path.iterdir()) == before


def test_the_fields_a_run_returns_are_its_golden_files(tmp_path):
    first = _run(tmp_path)
    second = _run(tmp_path, LEDGER_2, TRADES_2, after=first.provenance, name="window-2-blockpit.csv")
    for written in (first, second):
        golden = (FIXTURES / written.out.name).read_bytes()
        record = json.loads((FIXTURES / written.provenance.name).read_text())
        assert written.rows == record["output"]["rows"]
        assert written.label_rows == dict(Counter(row["Label"] for row in csv.DictReader(io.StringIO(golden.decode()))))
        assert list(written.closing.items()) == sorted(record["closing"].items())
        assert written.sha256 == hashlib.sha256(golden).hexdigest()
        assert written.provenance_sha256 == hashlib.sha256(written.provenance.read_bytes()).hexdigest()


RUNNER = CliRunner()


def test_the_command_writes_both_files_and_exits_0(tmp_path):
    out = tmp_path / "window-1-blockpit.csv"
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()
    assert f"wrote 26 rows to {out}" in result.output
    assert "  Trade: 9 rows\n" in result.output
    assert "closing balances: ALGO 160.245, ATOM 11.1025, EUR 1174.1133, EURC 0, NEAR 0, XTZ 0" in result.output


def test_the_command_prints_each_refusal_and_exits_1(tmp_path):
    ledger = _edited(tmp_path, LEDGER_1, [("LFX027-SYNTH-LEDGER", "subtype", "allocation")])
    result = RUNNER.invoke(
        app, ["tax", "blockpit", "--ledgers", str(ledger), "--trades", str(TRADES_1), "--out", str(tmp_path / "o.csv")]
    )
    assert result.exit_code == 1
    assert "refused LFX027-SYNTH-LEDGER [earn/allocation]: no mapping is written for this type and subtype" in result.output
    assert not (tmp_path / "o.csv").exists()


def test_the_command_refuses_an_unreadable_input_with_exit_1(tmp_path):
    result = RUNNER.invoke(
        app,
        ["tax", "blockpit", "--ledgers", str(tmp_path / "absent.csv"), "--trades", str(TRADES_1), "--out", str(tmp_path / "o.csv")],
    )
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert f"{tmp_path / 'absent.csv'} cannot be read" in result.output
    assert not (tmp_path / "o.csv").exists()


def test_the_command_refuses_an_out_under_an_absent_directory_with_exit_1(tmp_path):
    out = tmp_path / "absent" / "o.csv"
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1), "--out", str(out)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert str(out) in result.output
    assert not out.parent.exists()


def test_the_command_refuses_an_existing_output_with_exit_1(tmp_path):
    out = tmp_path / "o.csv"
    out.write_text("{}")
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1), "--out", str(out)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert out.read_text() == "{}"


def test_the_command_refuses_a_usage_error_with_exit_2():
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1)])
    assert result.exit_code == 2
    assert "Missing option" in result.output


def test_the_transform_imports_nothing_outside_its_allowlist():
    allowed = {
        "__future__",
        "csv",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "hashlib",
        "importlib.metadata",
        "io",
        "json",
        "pathlib",
        "typing",
        "typer",
        "cli.logging",
    }
    paths = sorted((Path(__file__).resolve().parents[1] / "cli" / "tax").glob("*.py"))
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name in allowed or name.startswith("cli.tax."), (path.name, name)


def test_the_readme_names_the_tax_command_and_each_of_its_options():
    section = (Path(__file__).resolve().parents[1] / "README.md").read_text().split("### `zcrypto tax`", 1)[1].split("\n## ", 1)[0]
    assert "zcrypto tax blockpit --ledgers <PATH> --trades <PATH> --out <PATH> [--after <PATH>]" in section
    for option in ("--ledgers", "--trades", "--out", "--after"):
        assert f"| `{option} <PATH>` |" in section, option
