"""C1's maker-fill reading: the fill table and the reversal surface over one pair's fill-model rows
(docs/specs/00151-c1-maker-fill-reading-design.md D4)."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from cli.alpha.c2 import cell_reads, log_returns, moves, signals, trailing_std

PAIRS = (
    "ADA/EUR",
    "AVAX/EUR",
    "BTC/EUR",
    "DOGE/EUR",
    "DOT/EUR",
    "ETH/EUR",
    "LINK/EUR",
    "LTC/EUR",
    "SOL/EUR",
    "XRP/EUR",
    "ETH/BTC",
    "SOL/BTC",
)
SPAN = (datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC))  # half-open
MONTHS = ("2026-08", "2026-09", "2026-10")  # 2026-10 through the 25th, a partial window
MAKER_ROUND_TRIP = 0.0080
HORIZONS_S = (60, 300, 900)
THRESHOLDS = (1, 2)
SIZES = (0, 1)
SIDES = ("bid", "ask")
MEAN_BLOCK = 30
N_RESAMPLES = 4000
SEED = 42
SIGMA_WINDOW = 96
LAG = 1
TRADE_FILL_S = 900
ADVERSE_OFFSETS_S = (60, 900)


def cell_name(pair: str, threshold: int, size: int, side: str) -> str:
    return f"{pair}|th{threshold}|S{size}|{side}"


def _fill_leaves(posts: pl.DataFrame, horizon: int, sign: int) -> dict:
    """A figure over no post or no fill is an absent key, never None: the registry refuses a null leaf. A censored post
    has `filled` false, so it counts as a post unfilled."""
    filled = posts.filter(pl.col("filled") & (pl.col("time_to_fill_s") <= horizon))
    leaves = {"posts": posts.height, "n_filled": filled.height}
    if posts.height:
        leaves["fill_rate"] = filled.height / posts.height
    if filled.height:
        leaves["median_time_to_fill_s"] = filled["time_to_fill_s"].median()
    for offset in ADVERSE_OFFSETS_S:
        column = f"mid_at_fill_plus_{offset}s"
        marked = filled.filter(pl.col(column).is_not_null()).select(
            (sign * (pl.col("fill_price") - pl.col(column)) / pl.col("fill_price") * 1e4).alias("bps")
        )["bps"]
        if marked.len():
            leaves[f"adverse_{offset}_bps"] = marked.mean()
        leaves[f"n_unmarked_{offset}"] = filled.height - marked.len()
    return leaves


def fill_table(frame: pl.DataFrame) -> dict:
    """The adverse selection is signed against the order: a bid's fill followed by a lower mid, or an ask's by a higher
    one, is positive."""
    frame = frame.with_columns(month=pl.col("ts").dt.strftime("%Y-%m"))
    table = {}
    for side in SIDES:
        sign = 1 if side == "bid" else -1
        for size in SIZES:
            posts = frame.filter((pl.col("side") == side) & (pl.col("size") == size))
            for horizon in HORIZONS_S:
                table[f"{side}|S{size}|H{horizon}"] = {
                    "months": {month: _fill_leaves(posts.filter(pl.col("month") == month), horizon, sign) for month in MONTHS},
                    "span": _fill_leaves(posts, horizon, sign),
                }
    return table


def quarter_hour_mids(frame: pl.DataFrame) -> tuple[list[datetime], list[float]]:
    """A boundary with no post is left out, never None, so `log_returns` reads None across it by its step check."""
    bars = (
        frame.filter(pl.col("ts") == pl.col("ts").dt.truncate("15m"))
        .sort("ts", maintain_order=True)
        .unique("ts", keep="first", maintain_order=True)
    )
    return bars["ts"].to_list(), bars["mid_at_post"].to_list()


def reversal_cells(frame: pl.DataFrame, *, threshold: int, size: int, side: str) -> dict:
    """The order posted against a 15m move -- a bid after a down move, an ask after an up one -- traded where it filled
    within `TRADE_FILL_S`; its gross is the move from its fill price to the mid an hour after the post in its favour, the
    half-spread already in the fill at the touch. An unfilled signal bar is no trade, and a filled one whose hour-after mid
    the data does not reach is counted apart, out of `n` and the means."""
    ts, mids = quarter_hour_mids(frame)
    returns = log_returns(ts, mids)
    signal = signals(moves(returns, lag=LAG), trailing_std(returns, window=SIGMA_WINDOW), lag=LAG, threshold=threshold)
    against = -1 if side == "bid" else 1
    bars = [i for i, s in enumerate(signal) if s == against]
    posts = frame.filter((pl.col("side") == side) & (pl.col("size") == size) & pl.col("ts").is_in([ts[i] for i in bars]))
    trades = {row["ts"]: row for row in posts.to_dicts()}
    marked = [0] * len(ts)
    gross_at: list[float | None] = [None] * len(ts)
    n_filled = n_unmarked = 0
    for i in bars:
        row = trades.get(ts[i])
        if row is None or not row["filled"] or row["time_to_fill_s"] > TRADE_FILL_S:
            continue
        n_filled += 1
        mid = row["mid_at_post_plus_3600s"]
        if mid is None:
            n_unmarked += 1
            continue
        move = (mid - row["fill_price"]) / row["fill_price"]
        gross_at[i] = move if side == "bid" else -move
        marked[i] = 1
    months_at = [f"{stamp:%Y-%m}" for stamp in ts]
    # Side "up" takes each gross as signed here.
    read = cell_reads(
        marked,
        "up",
        gross_at,
        months_at,
        cost=MAKER_ROUND_TRIP,
        mean_block=MEAN_BLOCK,
        n_resamples=N_RESAMPLES,
        seed=SEED,
    )
    cell = {"n_signals": len(bars), "n_unmarked": n_unmarked}
    if bars:
        cell["fill_rate_900"] = n_filled / len(bars)
    cell["months"] = {month: read["per_year"].get(month, {"n": 0}) for month in MONTHS}
    cell["span"] = {key: value for key, value in read.items() if key != "per_year"}
    return cell
