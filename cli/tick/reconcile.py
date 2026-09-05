from __future__ import annotations

import polars as pl

from cli.tick.errors import TickError

# Kraken legacy trades-CSV altnames -> canonical tickers, base leg only; cli.backfill.read's _ALIAS maps the other way.
KRAKEN_TICKER_MAP = {"XBT": "BTC", "XDG": "DOGE"}

_QUOTE_SUFFIXES = ("EUR", "USD")
_OHLC_COLUMNS = ["open", "high", "low", "close"]
_LOOSE_TOL = 1e-3
_WORST_N = 5


def csv_pair_to_canonical(name: str) -> tuple[str, str]:
    """Map a Kraken trades-CSV pair name (`XBTEUR`) to canonical `(base, quote)`; `TickError` on an unrecognized quote suffix."""
    for quote in _QUOTE_SUFFIXES:
        if name.endswith(quote) and len(name) > len(quote):
            base_raw = name[: -len(quote)]
            return KRAKEN_TICKER_MAP.get(base_raw, base_raw), quote
    raise TickError(f"unrecognized quote suffix for pair name: {name!r}")


def _rel_diff(col: str) -> pl.Expr:
    """Relative difference of a tick-bar field against its OHLCVT counterpart, its denominator floored so a
    zero-valued OHLCVT field cannot divide by zero."""
    return (pl.col(col) - pl.col(f"{col}_ohlcvt")).abs() / pl.col(f"{col}_ohlcvt").abs().clip(lower_bound=1e-12)


def _match_stats(joined: pl.DataFrame, tol: float) -> tuple[int, float]:
    match = joined.select(pl.all_horizontal([_rel_diff(c) <= tol for c in _OHLC_COLUMNS]).alias("match"))
    n_matched = int(match["match"].sum())
    n = joined.height
    return n_matched, (100.0 * n_matched / n if n else 100.0)


def reconcile(tick_bars: pl.DataFrame, ohlcvt_bars: pl.DataFrame, *, tol: float = 1e-6) -> dict:
    """Compare tick-derived bars against canonical OHLCVT bars (`cli.ohlc.dataset.read_parquet`) over their `ts` overlap: an
    interval matches when every OHLC field's relative difference is within `tol`, near-exact by default since both series derive
    from the same trades, and again at the looser `_LOOSE_TOL`. Zero overlap reports `pct_within_tol(_loose)` 100.0 vacuously,
    mirroring `cli.backfill.reconcile.reconcile_series`."""
    joined = tick_bars.join(ohlcvt_bars, on="ts", how="inner", suffix="_ohlcvt")
    n_intervals = joined.height

    if n_intervals == 0:
        return {
            "n_intervals": 0,
            "tol": tol,
            "n_matched": 0,
            "pct_within_tol": 100.0,
            "loose_tol": _LOOSE_TOL,
            "n_matched_loose": 0,
            "pct_within_tol_loose": 100.0,
            "worst_mismatches": [],
        }

    n_matched, pct = _match_stats(joined, tol)
    n_matched_loose, pct_loose = _match_stats(joined, _LOOSE_TOL)

    long = pl.concat(
        [
            joined.select(
                pl.col("ts"),
                pl.lit(c).alias("field"),
                pl.col(c).alias("tick"),
                pl.col(f"{c}_ohlcvt").alias("ohlcvt"),
                _rel_diff(c).alias("rel_diff"),
            )
            for c in _OHLC_COLUMNS
        ]
    )
    worst = long.filter(pl.col("rel_diff") > tol).sort("rel_diff", descending=True).head(_WORST_N)

    return {
        "n_intervals": n_intervals,
        "tol": tol,
        "n_matched": n_matched,
        "pct_within_tol": pct,
        "loose_tol": _LOOSE_TOL,
        "n_matched_loose": n_matched_loose,
        "pct_within_tol_loose": pct_loose,
        "worst_mismatches": worst.to_dicts(),
    }
