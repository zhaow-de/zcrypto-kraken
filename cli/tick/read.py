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


def _detect_schema(data: bytes, has_header: bool) -> str:
    """Which Kraken trades layout is this — `"complete"` or `"quarterly"`?

    - **complete** — the full-history dump (`Kraken_Trading_History.zip:TimeAndSales_Combined/*.csv`):
      headerless, **3** fields `Timestamp,Price,Volume` (no side).
    - **quarterly** — the incremental ZIPs: **>= 4** fields `Price,Volume,Timestamp,Type[,...]`
      (Type = `b`/`s`), with or without a header row.

    A 3-field row is the complete schema only when its first field is a plausible Unix timestamp
    (`>= 1e9`); a 3-field row whose first field is a small number is a malformed 4-field row (a
    dropped side), which the quarterly path then rejects — so genuinely-short rows still error rather
    than being silently reinterpreted as the complete layout."""
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
    """Read a Kraken trades CSV — a bare file at `source`, or a `(zip_path, member_name)` pair read
    directly out of a ZIP without full extraction — into a canonical tick frame.

    Two real Kraken layouts are handled (auto-detected, see `_detect_schema`):

    - **quarterly** incremental ZIPs — `Price,Volume,Timestamp,Type[,OrderType,Misc,TradeID]`
      (Timestamp = unix seconds with a fractional part; Type = `"b"`/`"s"`), with or without a header
      row; any further Kraken columns are ignored positionally.
    - **complete** full-history dump (`TimeAndSales_Combined/*.csv`) — headerless `Timestamp,Price,
      Volume` (no side); `side` is returned as null for these rows.

    Returns a frame with `ts` (`Datetime("us", "UTC")`), `price`/`volume` (`Float64`), `side` (`Utf8`,
    `"b"`/`"s"`, or null for the complete layout), in the order read (no de-duplication or re-sort —
    `cli.tick.aggregate` sorts before bucketing). Raises `TickError` on an empty input, a row missing a
    required price/volume/timestamp field, an unparseable numeric value, a NaN price/volume/ts, or (in
    the quarterly layout) a `side` value other than `"b"`/`"s"`.
    """
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

    # A null in a required field means a row was too short. `side` is checked here for the quarterly
    # layout (a dropped side is malformed) but not for the complete layout (side is legitimately null).
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
