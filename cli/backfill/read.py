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

    **Also the REST `/Trades` altname** — `cli/trades/rest.py` depends on this (verified live: the
    derived name is accepted for the irregular pairs too, Kraken answering under its own key, e.g.
    `XBTEUR` -> `XXBTZEUR`). The name says "dump" for historical reasons; do NOT specialise this for
    a dump-specific quirk without checking that consumer, which has no local signal if you do.
    """
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
    """Parse a row's fields for value comparison, so formatting (e.g. `1.5` vs `1.50`) doesn't count
    as a difference — only genuinely different numeric values do."""
    return (r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6]))


def read_minute_rows(source_dir: Path, symbol: str) -> list[list]:
    """Read + merge `symbol`'s 1-minute OHLCVT rows from the base dump and quarterly updates.

    Locates `{altname}_1.csv` in `source_dir/Kraken_OHLCVT.zip` (entry `master_q4/{altname}_1.csv`)
    and in every `source_dir/Kraken_OHLCVT_Q*_*.zip` (entry `{altname}_1.csv`), skipping `__MACOSX/`
    cruft entries.

    The base dump is the latest full export and is authoritative for its entire ts range: on the real
    archive it carries higher, more-complete volume/trade counts than the quarterly updates, which are
    staler snapshots generated at each quarter and can disagree with the base on volume/trades for a
    shared ts (OHLC still matches). So a quarterly zip's rows are kept only where ts is strictly
    greater than the base's last ts — i.e. only the quarterlies' extension past the base dump's end is
    used, never a competing value inside the base's range. If `symbol` is absent from the base dump,
    all quarterly rows are kept.

    Concatenates base rows + kept quarterly rows, sorts by ts, and drops duplicate rows sharing a ts
    whose parsed numeric values match (formatting differences like `1.5` vs `1.50` don't count as a
    difference) — a defensive guard for any residual same-ts collision (e.g. across two quarterlies,
    which should not happen since quarters don't overlap). Raises `BackfillError` if `symbol` is absent
    from every zip, if two rows still share a ts with genuinely differing numeric OHLCVT data, or if a
    zip is corrupted or a row fails to parse.
    """
    alt = dump_pair_name(symbol)
    base_zip = source_dir / "Kraken_OHLCVT.zip"
    base_rows: list[list] = []
    found = False

    if base_zip.exists():
        try:
            with zipfile.ZipFile(base_zip) as zf:
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
