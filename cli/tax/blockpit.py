"""Kraken's ledger and trades exports mapped onto Blockpit's manual-import rows, the provenance written beside them."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path

from cli.tax.errors import Refusal, Refused, TaxExportError
from cli.tax.kraken_export import LEDGER_TIME, LedgerRow, TradeRow, read_ledger, read_trades

# The template's first row and its Label dropdown, the data validation on C2:C986.
HEADER = (
    "Date (UTC)",
    "Integration Name",
    "Label",
    "Outgoing Asset",
    "Outgoing Amount",
    "Incoming Asset",
    "Incoming Amount",
    "Fee Asset (optional)",
    "Fee Amount (optional)",
    "Comment (optional)",
    "Trx. ID (optional)",
)
TEMPLATE_LABELS = (
    "Trade",
    "Deposit",
    "Airdrop",
    "Bounty",
    "Gift Received",
    "Hard Fork",
    "Masternode",
    "Mining",
    "Staking",
    "Interest",
    "Derivative Profit",
    "Withdrawal",
    "Payment",
    "Gift Sent",
    "Derivative Fee",
    "Derivative Loss",
    "Non-Taxable In",
    "Non-Taxable Out",
    "Lost",
    "Income",
    "Cashback",
    "Fee",
    "Repay Loan",
    "Receive Loan",
    "Margin Profit",
    "Margin Loss",
    "Margin Fee",
    "Stock Purchase",
    "Stock Sale",
    "Prediction Profit",
    "Prediction Loss",
    "Open Perp",
    "Close Perp",
)


OUTPUT_DATE = "%d.%m.%Y %H:%M:%S"
INTEGRATION = "Kraken manual import"
SPOT_WALLET = "spot / main"
EURO = "EUR"
EURC = "EURC"
ALLOCATION_QUANTUM = Decimal("1e-10")


@dataclass(frozen=True)
class OutRow:
    time: str
    label: str
    out_asset: str
    out_amount: str
    in_asset: str
    in_amount: str
    fee_asset: str
    fee_amount: str
    comment: str
    trx_id: str
    order: tuple[int, int]


@dataclass
class Mapped:
    index: dict[str, int] = field(default_factory=dict)
    rows: list[OutRow] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    positions: dict[str, list[str]] = field(default_factory=dict)
    no_movement: int = 0

    def refuse(self, rows: list[LedgerRow], kind: str, reason: str) -> None:
        self.refusals.append(Refusal(tuple(sorted(row.txid for row in rows)), kind, reason))

    def at(self, rows: list[LedgerRow], ordinal: int = 0) -> tuple[int, int]:
        return (min(self.index[row.txid] for row in rows), ordinal)


def _unsigned(text: str) -> str:
    return text[1:] if text.startswith("-") else text


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _fee(row: LedgerRow) -> tuple[str, str]:
    return (row.asset, row.fee) if row.dec("fee") != 0 else ("", "")


def _position(trade: TradeRow, rows: list[LedgerRow], kind: str, mapped: Mapped) -> str | None:
    if not trade.closing:
        return trade.txid
    if not trade.posttxid:
        mapped.refuse(rows, kind, f"closing trade {trade.txid} names no position")
        return None
    return trade.posttxid


def _trade_of(refid: str, rows: list[LedgerRow], kind: str, trades: dict[str, TradeRow], mapped: Mapped) -> TradeRow | None:
    trade = trades.get(refid)
    if trade is None:
        mapped.refuse(rows, kind, f"no row of the trades export is {refid}")
    return trade


def _deposit(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") <= 0:
        mapped.refuse([row], "deposit", "a deposit that credits nothing")
        return
    label = "Non-Taxable In" if row.asset == EURO else "Deposit"
    mapped.rows.append(
        OutRow(row.time, label, "", "", row.asset, row.amount, *_fee(row), "kraken deposit", row.txid, mapped.at([row]))
    )


def _reward(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") <= 0:
        mapped.refuse([row], "earn/reward", "a reward that credits nothing")
        return
    mapped.rows.append(
        OutRow(row.time, "Staking", "", "", row.asset, row.amount, *_fee(row), "kraken earn/reward", row.txid, mapped.at([row]))
    )


def _rollover(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") != 0:
        mapped.refuse([row], "rollover", "a rollover that moves an amount")
        return
    mapped.positions.setdefault(row.refid, []).append(row.txid)
    trade = trades.get(row.refid)
    pair = f" {trade.pair}" if trade else ""
    comment = f"kraken rollover{pair} position {row.refid}"
    mapped.rows.append(OutRow(row.time, "Margin Fee", row.asset, row.fee, "", "", "", "", comment, row.txid, mapped.at([row])))


def _margin(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(row.refid, [row], "margin", trades, mapped)
    position = _position(trade, [row], "margin", mapped) if trade else None
    if position is None:
        return
    mapped.positions.setdefault(position, []).append(row.txid)
    comment = f"kraken margin {trade.pair} position {position}"
    amount = row.dec("amount")
    if amount > 0:
        mapped.rows.append(
            OutRow(row.time, "Margin Profit", "", "", row.asset, row.amount, "", "", comment, row.txid, mapped.at([row]))
        )
    if amount < 0:
        out = _unsigned(row.amount)
        mapped.rows.append(OutRow(row.time, "Margin Loss", row.asset, out, "", "", "", "", comment, row.txid, mapped.at([row])))
    if row.dec("fee") != 0:
        trx_id = f"{row.txid}-fee" if amount != 0 else row.txid
        mapped.rows.append(OutRow(row.time, "Margin Fee", row.asset, row.fee, "", "", "", "", comment, trx_id, mapped.at([row], 1)))


def _legs(rows: list[LedgerRow], kind: str, mapped: Mapped) -> tuple[LedgerRow, LedgerRow, tuple[str, str]] | None:
    if len(rows) != 2:
        mapped.refuse(rows, kind, f"{len(rows)} ledger rows where a pair is two")
        return None
    outs = [row for row in rows if row.dec("amount") < 0]
    ins = [row for row in rows if row.dec("amount") > 0]
    if len(outs) != 1 or len(ins) != 1:
        mapped.refuse(rows, kind, "the two rows are not one out and one in")
        return None
    if outs[0].asset == ins[0].asset:
        mapped.refuse(rows, kind, "the two rows are one asset")
        return None
    fees = [row for row in rows if row.dec("fee") != 0]
    if len(fees) > 1:
        mapped.refuse(rows, kind, "a fee on both rows")
        return None
    return outs[0], ins[0], _fee(fees[0]) if fees else ("", "")


def _pair_trade(legs: tuple[LedgerRow, LedgerRow, tuple[str, str]], comment: str, refid: str, order: tuple[int, int]) -> OutRow:
    out, into, fee = legs
    return OutRow(out.time, "Trade", out.asset, _unsigned(out.amount), into.asset, into.amount, *fee, comment, refid, order)


def _trade(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "trade/tradespot", trades, mapped)
    if trade is None:
        return
    order = mapped.at(rows)
    if len(rows) == 1:
        (leg,) = rows
        base, _, quote = trade.pair.partition("/")
        if leg.asset not in (base, quote):
            mapped.refuse(rows, "trade/tradespot", f"{leg.asset} is neither side of {trade.pair}")
            return
        other = quote if leg.asset == base else base
        comment = f"kraken trade/tradespot {trade.pair} one leg booked"
        if leg.dec("amount") > 0:
            row = OutRow(leg.time, "Trade", other, "0", leg.asset, leg.amount, *_fee(leg), comment, refid, order)
        else:
            row = OutRow(leg.time, "Trade", leg.asset, _unsigned(leg.amount), other, "0", *_fee(leg), comment, refid, order)
        mapped.rows.append(row)
        return
    legs = _legs(rows, "trade/tradespot", mapped)
    if legs is not None:
        comment = f"kraken trade/tradespot {trade.pair}"
        mapped.rows.append(_pair_trade(legs, comment, refid, order))


def _settled(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "settled", trades, mapped)
    legs = _legs(rows, "settled", mapped) if trade else None
    position = _position(trade, rows, "settled", mapped) if legs else None
    if position is None:
        return
    mapped.positions.setdefault(position, []).extend(row.txid for row in rows)
    comment = f"kraken settled {trade.pair} position {position}"
    mapped.rows.append(_pair_trade(legs, comment, refid, mapped.at(rows)))


def _conversion(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "collateralconversion", trades, mapped)
    if trade is None:
        return
    outs = [row for row in rows if row.asset == EURO and row.dec("amount") < 0]
    ins = [row for row in rows if row.asset == EURC and row.dec("amount") > 0]
    if len(rows) != 2 or len(outs) != 1 or len(ins) != 1 or any(row.dec("fee") != 0 for row in rows):
        mapped.refuse(rows, "collateralconversion", "not one EUR row out and one EURC row in, without a fee")
        return
    position = _position(trade, rows, "collateralconversion", mapped)
    if position is None:
        return
    mapped.positions.setdefault(position, []).extend(row.txid for row in rows)
    comment = f"kraken collateralconversion {trade.pair} position {position}"
    order = mapped.at(rows)
    mapped.rows.append(
        OutRow(outs[0].time, "Trade", EURO, _unsigned(outs[0].amount), EURC, ins[0].amount, "", "", comment, refid, order)
    )


def _sweep(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    kind = "spend/receive dustsweeping"
    spends = sorted((row for row in rows if row.type == "spend"), key=lambda row: row.txid)
    receives = [row for row in rows if row.type == "receive"]
    if len(receives) != 1 or not spends or receives[0].dec("fee") != 0:
        mapped.refuse(rows, kind, "not one receive without a fee and at least one spend")
        return
    if receives[0].dec("amount") <= 0 or any(row.dec("amount") >= 0 for row in spends):
        mapped.refuse(rows, kind, "a receive that credits nothing, or a spend that debits nothing")
        return
    try:
        values = [abs(row.dec("amountusd")) for row in spends]
    except InvalidOperation:
        values = []
    total = sum(values, Decimal(0))
    if not all(value.is_finite() for value in values) or total == 0:
        mapped.refuse(rows, kind, "the spends' amountusd are not decimals summing above zero, so the receive cannot be shared")
        return
    received = receives[0].dec("amount")
    shares = [(received * value / total).quantize(ALLOCATION_QUANTUM, rounding=ROUND_DOWN) for value in values[:-1]]
    shares.append(received - sum(shares, Decimal(0)))
    for ordinal, (spend, share) in enumerate(zip(spends, shares)):
        comment = f"kraken spend/dustsweeping {refid}"
        out = _unsigned(spend.amount)
        row = OutRow(
            spend.time,
            "Trade",
            spend.asset,
            out,
            receives[0].asset,
            _plain(share),
            *_fee(spend),
            comment,
            spend.txid,
            mapped.at(rows, ordinal),
        )
        mapped.rows.append(row)


SINGLE = {("deposit", ""): _deposit, ("earn", "reward"): _reward, ("rollover", ""): _rollover, ("margin", ""): _margin}


GROUPED = {
    ("trade", "tradespot"): _trade,
    ("settled", ""): _settled,
    ("collateralconversion", ""): _conversion,
    ("spend", "dustsweeping"): _sweep,
    ("receive", "dustsweeping"): _sweep,
}


def map_rows(ledger: list[LedgerRow], trades: dict[str, TradeRow]) -> Mapped:
    mapped = Mapped(index={row.txid: number for number, row in enumerate(ledger)})
    groups: dict[tuple[object, str], list[LedgerRow]] = defaultdict(list)
    for row in ledger:
        kind = f"{row.type}/{row.subtype}" if row.subtype else row.type
        key = (row.type, row.subtype)
        if row.wallet != SPOT_WALLET:
            mapped.refuse([row], kind, f"wallet {row.wallet!r} is not {SPOT_WALLET!r}")
        elif row.dec("fee") < 0 or (row.dec("fee") != 0 and row.feecurrency != row.asset):
            mapped.refuse([row], kind, f"a fee of {row.fee} {row.feecurrency} on a row in {row.asset}")
        elif key not in SINGLE and key not in GROUPED:
            mapped.refuse([row], kind, "no mapping is written for this type and subtype")
        elif row.dec("amount") == 0 and row.dec("fee") == 0:
            mapped.no_movement += 1
        elif key in SINGLE:
            SINGLE[key](row, trades, mapped)
        else:
            groups[(GROUPED[key], row.refid)].append(row)
    for (mapper, refid), rows in groups.items():
        if len({row.time for row in rows}) != 1:
            mapped.refuse(rows, rows[0].type, f"the rows under {refid} carry different times")
        else:
            mapper(refid, rows, trades, mapped)
    return mapped


def _moves(row: OutRow):
    for asset, amount, sign in (
        (row.in_asset, row.in_amount, 1),
        (row.out_asset, row.out_amount, -1),
        (row.fee_asset, row.fee_amount, -1),
    ):
        if asset:
            yield asset, sign * Decimal(amount)


def _written(rows: list[OutRow]) -> list[OutRow]:
    return sorted(rows, key=lambda row: (row.time, row.order))


def render_csv(rows: list[OutRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for row in _written(rows):
        if row.label not in TEMPLATE_LABELS:
            raise TaxExportError(f"{row.label!r} is not one of the template's labels")
        date = datetime.strptime(row.time, LEDGER_TIME).strftime(OUTPUT_DATE)
        writer.writerow(
            (
                date,
                INTEGRATION,
                row.label,
                row.out_asset,
                row.out_amount,
                row.in_asset,
                row.in_amount,
                row.fee_asset,
                row.fee_amount,
                row.comment,
                row.trx_id,
            )
        )
    return buffer.getvalue().encode("utf-8")


def check_cross(ledger: list[LedgerRow], trades: dict[str, TradeRow]) -> list[Refusal]:
    present = {row.txid for row in ledger}
    return [
        Refusal((trade.txid,), "trades", "none of its ledger ids is in the ledger export")
        for trade in trades.values()
        if not present.intersection(trade.ledgers)
    ]
