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


def check_chain(ledger: list[LedgerRow]) -> tuple[dict[str, Decimal], dict[str, Decimal], list[Refusal]]:
    opening: dict[str, Decimal] = {}
    closing: dict[str, Decimal] = {}
    refusals = []
    for row in ledger:
        moved = row.dec("amount") - row.dec("fee")
        if row.asset not in closing:
            opening[row.asset] = row.dec("balance") - moved
        elif closing[row.asset] + moved != row.dec("balance"):
            reason = (
                f"{row.asset} balance {row.balance} is not the previous {_plain(closing[row.asset])} + {row.amount} - {row.fee}"
            )
            refusals.append(Refusal((row.txid,), "balance", reason))
        closing[row.asset] = row.dec("balance")
    return opening, closing, refusals


def check_conservation(ledger: list[LedgerRow], rows: list[OutRow]) -> list[Refusal]:
    want: dict[str, Decimal] = defaultdict(Decimal)
    got: dict[str, Decimal] = defaultdict(Decimal)
    for row in ledger:
        want[row.asset] += row.dec("amount") - row.dec("fee")
    for row in rows:
        for asset, moved in _moves(row):
            got[asset] += moved
    return [
        Refusal((), "conservation", f"{asset} moves {_plain(got[asset])} in the output and {_plain(want[asset])} in the ledger")
        for asset in sorted(set(want) | set(got))
        if got[asset] != want[asset]
    ]


def check_order(opening: dict[str, Decimal], rows: list[OutRow]) -> list[Refusal]:
    held = dict(opening)
    refusals = []
    for row in _written(rows):
        moved: dict[str, Decimal] = defaultdict(Decimal)
        for asset, amount in _moves(row):
            moved[asset] += amount
        for asset, amount in moved.items():
            held[asset] = held.get(asset, Decimal(0)) + amount
            if held[asset] < 0:
                reason = f"{asset} runs to {_plain(held[asset])} at this row in the written order"
                refusals.append(Refusal((row.trx_id,), "order", reason))
    return refusals


def check_unique(rows: list[OutRow]) -> list[Refusal]:
    counts = Counter(row.trx_id for row in rows)
    return [
        Refusal((trx_id,), "trx-id", f"{count} output rows carry this Trx. ID")
        for trx_id, count in sorted(counts.items())
        if count > 1
    ]


def _label_sums(rows: list[OutRow]) -> dict:
    sums: dict = {}
    for row in rows:
        for asset, amount, column in (
            (row.in_asset, row.in_amount, "incoming"),
            (row.out_asset, row.out_amount, "outgoing"),
            (row.fee_asset, row.fee_amount, "fee"),
        ):
            if asset:
                entry = sums.setdefault(row.label, {}).setdefault(
                    asset, {"rows": 0, "incoming": Decimal(0), "outgoing": Decimal(0), "fee": Decimal(0)}
                )
                entry[column] += Decimal(amount)
        for asset in {row.in_asset, row.out_asset} - {""}:
            sums[row.label][asset]["rows"] += 1
    return {
        label: {
            asset: {key: value if key == "rows" else _plain(value) for key, value in entry.items()}
            for asset, entry in assets.items()
        }
        for label, assets in sums.items()
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Written:
    out: Path
    provenance: Path
    rows: int
    label_rows: dict[str, int]
    closing: dict[str, str]
    sha256: str
    provenance_sha256: str


def transform(ledgers: Path, trades: Path, out: Path) -> Written:
    provenance_path = out.with_name(out.name + ".provenance.json")
    for path in (out, provenance_path):
        if path.exists():
            raise TaxExportError(f"{path} exists, and a run never overwrites a file")
    ledger_bytes, trades_bytes = ledgers.read_bytes(), trades.read_bytes()
    ledger, trade_rows = read_ledger(ledgers, ledger_bytes), read_trades(trades, trades_bytes)
    mapped = map_rows(ledger, trade_rows)
    opening, closing, chain = check_chain(ledger)
    first_time = ledger[0].time if ledger else None
    refusals = [
        *mapped.refusals,
        *check_cross(ledger, trade_rows),
        *chain,
        *check_conservation(ledger, mapped.rows),
        *check_order(opening, mapped.rows),
        *check_unique(mapped.rows),
    ]
    if refusals:
        raise Refused(refusals)
    body = render_csv(mapped.rows)
    closing_all = {asset: _plain(value) for asset, value in sorted(closing.items())}
    last_time = ledger[-1].time if ledger else None
    record = {
        "inputs": {
            "ledgers": {
                "file": ledgers.name,
                "sha256": _sha256(ledger_bytes),
                "rows": len(ledger),
                "first_time": first_time,
                "last_time": last_time,
            },
            "trades": {"file": trades.name, "sha256": _sha256(trades_bytes), "rows": len(trade_rows)},
        },
        "output": {"file": out.name, "sha256": _sha256(body), "rows": len(mapped.rows)},
        "labels": _label_sums(mapped.rows),
        "opening": {asset: _plain(value) for asset, value in sorted(opening.items())},
        "closing": closing_all,
        "positions": {position: sorted(txids) for position, txids in sorted(mapped.positions.items())},
        "no_movement": mapped.no_movement,
        "previous": None,
        "zcrypto": version("zcrypto"),
    }
    provenance = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    out.write_bytes(body)
    provenance_path.write_bytes(provenance)
    label_rows = dict(Counter(row.label for row in mapped.rows))
    return Written(out, provenance_path, len(mapped.rows), label_rows, closing_all, _sha256(body), _sha256(provenance))
