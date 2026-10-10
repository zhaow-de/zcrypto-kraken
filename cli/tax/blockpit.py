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
