from __future__ import annotations

import zipfile
from pathlib import Path

from cli.backfill.errors import BackfillError

# Kraken OHLCVT dump altnames apply these aliases to both legs of the pair.
_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}


def dump_pair_name(symbol: str) -> str:
    """Map a canonical `"BASE/QUOTE"` symbol to its Kraken OHLCVT dump altname.

    `cli/trades/rest.py` derives the REST `/Trades` altname from this too, so despite the name never specialise it for
    a dump-only quirk — that consumer has no local signal if you do."""
    try:
        base, quote = symbol.split("/")
    except ValueError as exc:
        raise BackfillError(f"not a BASE/QUOTE symbol: {symbol!r}") from exc
    return _ALIAS.get(base, base) + _ALIAS.get(quote, quote)


def _parse_csv(text: str, *, zip_path: Path, entry: str, symbol: str) -> list[list]:
    out = []
    for line in text.splitlines():
        if not line:
            continue
        try:
            t, o, h, l, c, v, n = line.split(",")
            out.append([int(t), o, h, l, c, v, n])
        except ValueError as exc:
            raise BackfillError(f"malformed row for {symbol} in {zip_path.name}:{entry}: {line!r}") from exc
    return out


def _numeric_values(r: list) -> tuple:
    """Parse a row's fields so comparison sees values, not formatting (`1.5` and `1.50` are equal)."""
    return (r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6]))


def read_minute_rows(source_dir: Path, symbol: str) -> list[list]:
    """Read and merge `symbol`'s 1-minute OHLCVT rows from the base dump and the quarterly updates.

    The base dump is authoritative over its whole ts range — quarterlies are staler and can disagree on volume/trades
    at a shared ts — so a quarterly row is kept only past the base's last ts, and the same-ts dedup below is defensive."""
    alt = dump_pair_name(symbol)
    base_zip = source_dir / "Kraken_OHLCVT.zip"
    base_rows: list[list] = []
    found = False

    if base_zip.exists():
        try:
            with zipfile.ZipFile(base_zip) as zf:
                # Entry lookups are exact: a suffix match would also take the `__MACOSX/._*` cruft such zips can carry.
                name = f"master_q4/{alt}_1.csv"
                if name in zf.namelist():
                    base_rows += _parse_csv(zf.read(name).decode(), zip_path=base_zip, entry=name, symbol=symbol)
                    found = True
        except zipfile.BadZipFile as exc:
            raise BackfillError(f"corrupted zip {base_zip.name} while reading {symbol} ({alt})") from exc

    base_max_ts = max((r[0] for r in base_rows), default=None)

    quarterly_rows: list[list] = []
    for qz in sorted(source_dir.glob("Kraken_OHLCVT_Q*_*.zip")):
        try:
            with zipfile.ZipFile(qz) as zf:
                name = f"{alt}_1.csv"
                if name in zf.namelist():
                    rows = _parse_csv(zf.read(name).decode(), zip_path=qz, entry=name, symbol=symbol)
                    if base_max_ts is not None:
                        rows = [r for r in rows if r[0] > base_max_ts]
                    quarterly_rows += rows
                    found = True
        except zipfile.BadZipFile as exc:
            raise BackfillError(f"corrupted zip {qz.name} while reading {symbol} ({alt})") from exc

    if not found:
        raise BackfillError(f"no 1-minute data for {symbol} ({alt}) under {source_dir}")

    rows = base_rows + quarterly_rows
    rows.sort(key=lambda r: r[0])
    deduped: list[list] = []
    for r in rows:
        if deduped and deduped[-1][0] == r[0]:
            if _numeric_values(deduped[-1]) != _numeric_values(r):
                raise BackfillError(f"conflicting rows at ts={r[0]} for {symbol}")
            continue
        deduped.append(r)
    return deduped
