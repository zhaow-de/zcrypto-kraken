from __future__ import annotations

import zipfile
from pathlib import Path

from cli.backfill.errors import BackfillError

# Kraken OHLCVT dump altnames apply these aliases to both legs of the pair.
_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}


def dump_pair_name(symbol: str) -> str:
    """Map a canonical `"BASE/QUOTE"` symbol to its Kraken OHLCVT dump altname.

    Applies the Kraken aliases BTC->XBT, DOGE->XDG to both legs, then concatenates (e.g.
    `"BTC/EUR"` -> `"XBTEUR"`, `"DOGE/EUR"` -> `"XDGEUR"`, `"ETH/BTC"` -> `"ETHXBT"`).
    """
    try:
        base, quote = symbol.split("/")
    except ValueError as exc:
        raise BackfillError(f"not a BASE/QUOTE symbol: {symbol!r}") from exc
    return _ALIAS.get(base, base) + _ALIAS.get(quote, quote)


def _parse_csv(text: str) -> list[list]:
    out = []
    for line in text.splitlines():
        if not line:
            continue
        t, o, h, l, c, v, n = line.split(",")
        out.append([int(t), o, h, l, c, v, n])
    return out


def read_minute_rows(source_dir: Path, symbol: str) -> list[list]:
    """Read + merge `symbol`'s 1-minute OHLCVT rows from the base dump and quarterly updates.

    Locates `{altname}_1.csv` in `source_dir/Kraken_OHLCVT.zip` (entry `master_q4/{altname}_1.csv`)
    and in every `source_dir/Kraken_OHLCVT_Q*_*.zip` (entry `{altname}_1.csv`), skipping `__MACOSX/`
    cruft entries. Concatenates, sorts by ts, and drops exact-duplicate rows sharing a ts (the
    base/quarterly overlap window). Raises `BackfillError` if `symbol` is absent from every zip, or
    if two rows share a ts with differing OHLCVT data — an unresolvable conflict between sources.
    """
    alt = dump_pair_name(symbol)
    base_zip = source_dir / "Kraken_OHLCVT.zip"
    rows: list[list] = []
    found = False

    if base_zip.exists():
        with zipfile.ZipFile(base_zip) as zf:
            name = f"master_q4/{alt}_1.csv"
            if name in zf.namelist():
                rows += _parse_csv(zf.read(name).decode())
                found = True

    for qz in sorted(source_dir.glob("Kraken_OHLCVT_Q*_*.zip")):
        with zipfile.ZipFile(qz) as zf:
            name = f"{alt}_1.csv"
            if name in zf.namelist():
                rows += _parse_csv(zf.read(name).decode())
                found = True

    if not found:
        raise BackfillError(f"no 1-minute data for {symbol} ({alt}) under {source_dir}")

    rows.sort(key=lambda r: r[0])
    deduped: list[list] = []
    for r in rows:
        if deduped and deduped[-1][0] == r[0]:
            if deduped[-1] != r:
                raise BackfillError(f"conflicting rows at ts={r[0]} for {symbol}")
            continue
        deduped.append(r)
    return deduped
