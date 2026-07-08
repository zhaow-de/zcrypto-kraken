from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from cli.tick.errors import TickError

_COLUMN_NAMES = ["price", "volume", "ts", "side"]
_VALID_SIDES = ["b", "s"]


def _sniff_has_header(data: bytes) -> bool:
    """A trades CSV data row's leading fields (Price, Volume, Timestamp) are all numeric; a header
    row's (`"Price"`, `"Volume"`, `"Timestamp"`) are all text. Treat line 1 as a header only when
    *none* of its first three fields parses as a float — so a data row with a single corrupted leading
    field (e.g. a garbled Price but a still-numeric Volume/Timestamp) is NOT mistaken for a header and
    silently dropped via `skip_rows`; it instead flows to the malformed-row / cast-error guards below,
    which raise `TickError`. Empty input parses as "has a header" (the caller ends up with zero data
    rows either way, which the CSV read below turns into a `TickError`)."""
    first_line = data.split(b"\n", 1)[0].split(b"\r", 1)[0]
    for field in first_line.split(b",")[:3]:
        try:
            float(field)
        except ValueError:
            continue
        return False  # a numeric leading field means this is a data row, not a header
    return True


def _read_bytes(source: str | Path | tuple[str | Path, str]) -> tuple[bytes, str]:
    if isinstance(source, tuple):
        zip_path, member = source
        zip_path = Path(zip_path)
        label = f"{zip_path.name}:{member}"
        try:
            with zipfile.ZipFile(zip_path) as zf:
                return zf.read(member), label
        except zipfile.BadZipFile as exc:
            raise TickError(f"corrupted zip {zip_path.name} while reading {member}") from exc
        except KeyError as exc:
            raise TickError(f"{member} not found in {zip_path.name}") from exc
    path = Path(source)
    return path.read_bytes(), str(path)


def read_trades_csv(source: str | Path | tuple[str | Path, str]) -> pl.DataFrame:
    """Read a Kraken trades CSV — a bare file at `source`, or a `(zip_path, member_name)` pair read
    directly out of a ZIP without full extraction — into a canonical tick frame.

    Columns are `Price,Volume,Timestamp,Type[,Misc,TradeID]` (Timestamp = unix seconds with a
    fractional part; Type = `"b"`/`"s"`); any further Kraken columns are ignored positionally, so
    rows with extra trailing fields still parse. The complete Kraken trades dump is headerless; the
    quarterly incremental ZIPs carry a header row — this is auto-detected by sniffing whether the
    first line's first field parses as a number (see `_sniff_has_header`), not by a fixed source
    convention.

    Returns a frame with `ts` (`Datetime("us", "UTC")`), `price`/`volume` (`Float64`), `side` (`Utf8`,
    `"b"`/`"s"`), sorted by `ts` order as read (no de-duplication or re-sort — `cli.tick.aggregate`
    sorts before bucketing). Raises `TickError` on an empty input, a row with fewer than 4 fields, an
    unparseable numeric value, a NaN price/volume/ts, or a `side` value other than `"b"`/`"s"`.
    """
    data, label = _read_bytes(source)

    try:
        raw = pl.read_csv(
            data,
            has_header=False,
            skip_rows=1 if _sniff_has_header(data) else 0,
            columns=[0, 1, 2, 3],
            new_columns=_COLUMN_NAMES,
            truncate_ragged_lines=True,
            infer_schema=False,
        )
    except pl.exceptions.PolarsError as exc:
        raise TickError(f"unreadable trades CSV {label}: {exc}") from exc

    if raw.select(pl.any_horizontal(pl.all().is_null())).to_series().any():
        raise TickError(f"malformed row (fewer than 4 fields) in {label}")

    try:
        frame = raw.with_columns(pl.col("price", "volume", "ts").cast(pl.Float64, strict=True))
    except pl.exceptions.InvalidOperationError as exc:
        raise TickError(f"unparseable numeric value in {label}: {exc}") from exc

    if frame.select(pl.any_horizontal(pl.col("price", "volume", "ts").is_nan())).to_series().any():
        raise TickError(f"NaN price/volume/ts in {label}")

    if not frame.filter(~pl.col("side").is_in(_VALID_SIDES)).is_empty():
        raise TickError(f"side value other than 'b'/'s' in {label}")

    return frame.with_columns(pl.from_epoch(pl.col("ts"), time_unit="s").dt.replace_time_zone("UTC")).select(
        ["ts", "price", "volume", "side"]
    )
