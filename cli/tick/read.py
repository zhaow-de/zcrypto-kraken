from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from cli.tick.errors import TickError

_QUARTERLY_COLUMNS = ["price", "volume", "ts", "side"]
_COMPLETE_COLUMNS = ["ts", "price", "volume"]
_VALID_SIDES = ["b", "s"]
_MIN_UNIX_TS = 1e9  # a plausible Unix timestamp (2001+); crypto prices/volumes are far smaller


def _sniff_has_header(data: bytes) -> bool:
    """True when none of line 1's first three fields parses as a float — a data row with one corrupted leading
    field is then still read, and errors, rather than being dropped as a header row by `skip_rows`."""
    first_line = data.split(b"\n", 1)[0].split(b"\r", 1)[0]
    for field in first_line.split(b",")[:3]:
        try:
            float(field)
        except ValueError:
            continue
        return False  # a numeric leading field means this is a data row, not a header
    return True


def _detect_schema(data: bytes, has_header: bool) -> str:
    """`"complete"` — headerless 3-field `Timestamp,Price,Volume`, the `TimeAndSales_Combined/*.csv` full-history
    dump — or `"quarterly"`, `Price,Volume,Timestamp,Type[,...]`; a 3-field row is complete only when its first
    field is a plausible Unix timestamp (`>= _MIN_UNIX_TS`), so a quarterly row with a dropped side stays quarterly
    and is rejected there rather than reinterpreted."""
    lines = data.split(b"\n")
    idx = 1 if has_header else 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines):
        fields = lines[idx].split(b",")
        if len(fields) == 3:
            try:
                if float(fields[0]) >= _MIN_UNIX_TS:
                    return "complete"
            except ValueError:
                pass
    return "quarterly"


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
    """Read a Kraken trades CSV — a bare file, or a `(zip_path, member_name)` pair read out of the ZIP without full extraction —
    into a `ts` (`Datetime("us", "UTC")`)/`price`/`volume`/`side` frame, rows in the order read, neither de-duplicated nor
    re-sorted — `cli.tick.aggregate` sorts before bucketing. The layout is auto-detected (`_detect_schema`) and `side` is null
    throughout the complete one. Raises `TickError` on an empty, malformed or unparseable input."""
    data, label = _read_bytes(source)
    has_header = _sniff_has_header(data)
    schema = _detect_schema(data, has_header)
    skip_rows = 1 if has_header else 0

    try:
        if schema == "complete":
            raw = pl.read_csv(
                data,
                has_header=False,
                skip_rows=skip_rows,
                columns=[0, 1, 2],
                new_columns=_COMPLETE_COLUMNS,
                truncate_ragged_lines=True,
                infer_schema=False,
            ).with_columns(pl.lit(None, dtype=pl.Utf8).alias("side"))
        else:
            raw = pl.read_csv(
                data,
                has_header=False,
                skip_rows=skip_rows,
                columns=[0, 1, 2, 3],
                new_columns=_QUARTERLY_COLUMNS,
                truncate_ragged_lines=True,
                infer_schema=False,
            )
    except pl.exceptions.PolarsError as exc:
        raise TickError(f"unreadable trades CSV {label}: {exc}") from exc

    # A null in a required field means a row was too short; `side` is required only in the quarterly layout, where a
    # missing side is malformed, not the complete layout's legitimate absence.
    null_cols = _COMPLETE_COLUMNS if schema == "complete" else _QUARTERLY_COLUMNS
    if raw.select(pl.any_horizontal(pl.col(null_cols).is_null())).to_series().any():
        raise TickError(f"malformed row (missing a required field) in {label}")

    try:
        frame = raw.with_columns(pl.col("price", "volume", "ts").cast(pl.Float64, strict=True))
    except pl.exceptions.InvalidOperationError as exc:
        raise TickError(f"unparseable numeric value in {label}: {exc}") from exc

    if frame.select(pl.any_horizontal(pl.col("price", "volume", "ts").is_nan())).to_series().any():
        raise TickError(f"NaN price/volume/ts in {label}")

    if schema == "quarterly" and not frame.filter(~pl.col("side").is_in(_VALID_SIDES)).is_empty():
        raise TickError(f"side value other than 'b'/'s' in {label}")

    return frame.with_columns(pl.from_epoch(pl.col("ts"), time_unit="s").dt.replace_time_zone("UTC")).select(
        ["ts", "price", "volume", "side"]
    )
