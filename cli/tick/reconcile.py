from __future__ import annotations

import polars as pl

from cli.tick.errors import TickError

# Kraken legacy trades-CSV pair-name altnames -> canonical tickers (mirrors
# cli.backfill.read's OHLCVT dump aliases, applied here to the base leg only).
KRAKEN_TICKER_MAP = {"XBT": "BTC", "XDG": "DOGE"}

_QUOTE_SUFFIXES = ("EUR", "USD")
_OHLC_COLUMNS = ["open", "high", "low", "close"]
_LOOSE_TOL = 1e-3
_WORST_N = 5


def csv_pair_to_canonical(name: str) -> tuple[str, str]:
    """Map a Kraken trades-CSV pair name (e.g. `"XBTEUR"`) to a canonical `(base, quote)` pair
    (e.g. `("BTC", "EUR")`): strip the `EUR`/`USD` quote suffix, then map the remaining base ticker
    through `KRAKEN_TICKER_MAP` (Kraken's legacy `XBT`/`XDG` altnames -> `BTC`/`DOGE`; any other base
    ticker passes through unchanged, e.g. `"ETHEUR"` -> `("ETH", "EUR")`).

    Raises `TickError` if `name` doesn't end in a recognized quote suffix.
    """
    for quote in _QUOTE_SUFFIXES:
        if name.endswith(quote) and len(name) > len(quote):
            base_raw = name[: -len(quote)]
            return KRAKEN_TICKER_MAP.get(base_raw, base_raw), quote
    raise TickError(f"unrecognized quote suffix for pair name: {name!r}")


def _rel_diff(col: str) -> pl.Expr:
    """Relative difference of a tick-bar field against its OHLCVT counterpart, denominator floored
    at 1e-12 so a zero-valued OHLCVT field doesn't divide by zero."""
    return (pl.col(col) - pl.col(f"{col}_ohlcvt")).abs() / pl.col(f"{col}_ohlcvt").abs().clip(lower_bound=1e-12)


def _match_stats(joined: pl.DataFrame, tol: float) -> tuple[int, float]:
    match = joined.select(pl.all_horizontal([_rel_diff(c) <= tol for c in _OHLC_COLUMNS]).alias("match"))
    n_matched = int(match["match"].sum())
    n = joined.height
    return n_matched, (100.0 * n_matched / n if n else 100.0)


def reconcile(tick_bars: pl.DataFrame, ohlcvt_bars: pl.DataFrame, *, tol: float = 1e-6) -> dict:
    """Compare tick-derived bars (`cli.tick.aggregate.ticks_to_bars` output) against canonical
    OHLCVT bars (`cli.ohlc.dataset.read_parquet` output) over their `ts` overlap.

    Inner-joins on `ts`; an interval "matches" when every OHLC field's relative difference
    (`|tick - ohlcvt| / |ohlcvt|`, see `_rel_diff`) is within `tol`. Reports the match rate at `tol`
    (the exit-bar check — default 1e-6, near-exact since both series derive from the same trades) and,
    for context, the same at a looser `1e-3` band. `worst_mismatches` lists the top few
    `{ts, field, tick, ohlcvt, rel_diff}` entries among fields that miss the strict `tol`, sorted by
    `rel_diff` descending (a single interval can contribute more than one entry if several of its
    O/H/L/C fields mismatch).

    Returns `{n_intervals, tol, n_matched, pct_within_tol, loose_tol, n_matched_loose,
    pct_within_tol_loose, worst_mismatches}`. Zero overlap reports `pct_within_tol(_loose) == 100.0`
    vacuously (mirroring `cli.backfill.reconcile.reconcile_series`) and an empty `worst_mismatches`.
    """
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
