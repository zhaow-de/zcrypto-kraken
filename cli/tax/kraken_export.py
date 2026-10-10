"""Kraken's ledger and trades CSV exports, read by header name into the export's own decimal strings."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cli.tax.errors import TaxExportError

LEDGER_COLUMNS = (
    "txid",
    "refid",
    "time",
    "type",
    "subtype",
    "wallet",
    "asset",
    "amount",
    "fee",
    "balance",
    "amountusd",
    "feecurrency",
)
TRADES_COLUMNS = ("txid", "pair", "misc", "ledgers", "posttxid")
LEDGER_TIME = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LedgerRow:
    txid: str
    refid: str
    time: str
    type: str
    subtype: str
    wallet: str
    asset: str
    amount: str
    fee: str
    balance: str
    amountusd: str
    feecurrency: str

    def dec(self, column: str) -> Decimal:
        return Decimal(getattr(self, column))


@dataclass(frozen=True)
class TradeRow:
    txid: str
    pair: str
    misc: tuple[str, ...]
    ledgers: tuple[str, ...]
    posttxid: str

    @property
    def closing(self) -> bool:
        return "closing" in self.misc


def _rows(path: Path, columns: tuple[str, ...], data: bytes | None) -> list[dict[str, str]]:
    # `utf-8-sig`: a file opened and saved in a spreadsheet gains a byte-order mark glued to its first column name.
    # `data` is the file's bytes where the caller has read them to hash, so the rows parse the bytes it hashed.
    try:
        text = (path.read_bytes() if data is None else data).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TaxExportError(f"{path} is not UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [column for column in columns if column not in (reader.fieldnames or [])]
    if missing:
        raise TaxExportError(f"{path} has no {', '.join(missing)} column")
    rows = list(reader)
    width = len(reader.fieldnames)
    for number, raw in enumerate(rows, start=1):
        # Read a row only at the header's field count: DictReader puts a long row's extras under None, a short row's gaps as None.
        if None in raw or None in raw.values():
            count = width + len(raw[None]) if None in raw else sum(value is not None for value in raw.values())
            fields = f"{count} field{'' if count == 1 else 's'}"
            raise TaxExportError(f"{path} data row {number} ({raw['txid']}): {fields} where the header names {width}")
    return rows


def read_ledger(path: Path, data: bytes | None = None) -> list[LedgerRow]:
    rows = []
    for number, raw in enumerate(_rows(path, LEDGER_COLUMNS, data), start=1):
        row = LedgerRow(*(raw[column] for column in LEDGER_COLUMNS))
        try:
            datetime.strptime(row.time, LEDGER_TIME)
            if not all(row.dec(column).is_finite() for column in ("amount", "fee", "balance")):
                raise InvalidOperation
        except (ValueError, InvalidOperation) as exc:
            raise TaxExportError(f"{path} data row {number} ({row.txid}): a time or an amount the export does not write") from exc
        rows.append(row)
    return rows


def read_trades(path: Path, data: bytes | None = None) -> dict[str, TradeRow]:
    trades = {}
    for raw in _rows(path, TRADES_COLUMNS, data):
        misc = tuple(word for word in raw["misc"].split(",") if word)
        ledgers = tuple(txid for txid in raw["ledgers"].split(",") if txid)
        trades[raw["txid"]] = TradeRow(raw["txid"], raw["pair"], misc, ledgers, raw["posttxid"])
    return trades
