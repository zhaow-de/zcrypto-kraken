"""The on-chain day file's columns, each pinned to its BRK series id, and the two series computed outside BRK, MVRV-Z
and the STH supply share (spec 00164 D3, D7, D8)."""

from __future__ import annotations

import math
import statistics

import polars as pl

COLUMNS: tuple[str, ...] = (
    "ts",
    "last_height",
    "last_hash",
    "price",
    "supply",
    "market_cap",
    "realized_cap",
    "mvrv",
    "nupl",
    "sopr",
    "asopr",
    "sth_sopr",
    "sth_asopr",
    "lth_sopr",
    "sth_supply",
    "lth_supply",
    "sth_mvrv",
    "lth_mvrv",
    "sth_nupl",
    "lth_nupl",
    "mvrv_z",
    "sth_supply_share",
)
SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "last_height": pl.Int64(),
    "last_hash": pl.String(),
} | {column: pl.Float64() for column in COLUMNS[3:]}

# The ids at the pinned BRK commit. A `_24h` series is the trailing 24 hours ending at the day's last block, not the
# calendar day; `price`, `market_cap` and `realized_cap` are USD, `circulating_supply` and the cohorts' supplies BTC.
BRK_SERIES: dict[str, str] = {
    "price": "price",
    "supply": "circulating_supply",
    "market_cap": "market_cap",
    "realized_cap": "realized_cap",
    "mvrv": "mvrv",
    "nupl": "nupl",
    "sopr": "sopr_24h",
    "asopr": "adjusted_sopr_24h",
    "sth_sopr": "sth_sopr_24h",
    "sth_asopr": "sth_adjusted_sopr_24h",
    "lth_sopr": "lth_sopr_24h",
    "sth_supply": "sth_supply",
    "lth_supply": "lth_supply",
    "sth_mvrv": "sth_mvrv",
    "lth_mvrv": "lth_mvrv",
    "sth_nupl": "sth_nupl",
    "lth_nupl": "lth_nupl",
}
MVRV_Z_MIN_VALUES = 365


def priced(value: float | None) -> bool:
    """The test of a value a quotient or a valuation rests on: BRK serves a price, a market cap and a realized cap as
    0 before its first price, and null where a value is undefined."""
    return value is not None and math.isfinite(value) and value > 0


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def mvrv_z(market_cap: list[float | None], realized_cap: list[float | None]) -> list[float | None]:
    """Each day's σ is the sample standard deviation of the priced market caps through that day alone; `None` until
    `MVRV_Z_MIN_VALUES` are priced, and where the day's market cap is not priced or its realized cap not finite."""
    caps: list[float] = []
    z: list[float | None] = []
    for cap, realized in zip(market_cap, realized_cap, strict=True):
        if priced(cap):
            caps.append(cap)
        counts = len(caps) >= MVRV_Z_MIN_VALUES and priced(cap) and _finite(realized)
        z.append((cap - realized) / statistics.stdev(caps) if counts else None)
    return z


def sth_supply_share(sth: list[float | None], supply: list[float | None]) -> list[float | None]:
    return [part / whole if priced(whole) and _finite(part) else None for part, whole in zip(sth, supply, strict=True)]
