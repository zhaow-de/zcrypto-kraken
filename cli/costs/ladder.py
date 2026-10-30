"""The engine's execution cost read from its ladder replayed at the cycle boundaries (spec 00153 D3): a side's cost
against the mid at its post, signed against the order, by side, size and month, and its blend over the legs."""

from __future__ import annotations

import numpy
import polars as pl

from cli.validation.bootstrap import bootstrap_ci

MAKER_FEE = 0.0040
TAKER_FEE = 0.0080
REGISTERED_PER_SIDE = 0.006
# `apply_trade`'s float subtraction can leave a residue on an order the prints met none of (spec 00153 D3).
MET_TOLERANCE = 1e-9
MONTHS = ("2026-08", "2026-09", "2026-10")
MEAN_BLOCK = 6
N_RESAMPLES = 2000
SEED = 42
_SIDES = ("bid", "ask")
_SIZES = (0, 1)


def side_costs(frame: pl.DataFrame) -> pl.DataFrame:
    """`cost` is null on an unfilled row whose box end recorded no touch, an unpriced one."""
    sign = pl.when(pl.col("side") == "bid").then(1.0).otherwise(-1.0)
    fallback = ~pl.col("filled")
    price = pl.when(fallback).then(pl.col("box_end_touch_price")).otherwise(pl.col("fill_price"))
    fee = pl.when(fallback).then(TAKER_FEE).otherwise(MAKER_FEE)
    return frame.with_columns(cost=sign * (price - pl.col("mid_at_post")) / pl.col("mid_at_post") + fee)


def _interval(series: list[float]) -> dict:
    if not series:
        return {}
    ci = bootstrap_ci(series, numpy.mean, mean_block=MEAN_BLOCK, n_resamples=N_RESAMPLES, alpha=0.05, seed=SEED)
    return {"mean_cost": float(ci["point"]), "cost_ci_low": float(ci["lower"]), "cost_ci_high": float(ci["upper"])}


def _cell(rows: pl.DataFrame) -> dict:
    filled = rows.filter(pl.col("filled"))
    fallbacks = rows.filter(~pl.col("filled"))
    unpriced = fallbacks.filter(pl.col("box_end_touch_price").is_null())
    priced = fallbacks.filter(pl.col("box_end_touch_price").is_not_null())
    cell = {"posts": rows.height, "unpriced": unpriced.height}
    if rows.height:
        cell["maker_share"] = filled.height / rows.height
    if filled.height:
        cell["median_time_to_fill_s"] = filled["time_to_fill_s"].median()
    cell |= _interval(rows["cost"].drop_nulls().to_list())
    if priced.height:
        larger = priced.filter(pl.col("box_end_touch_qty") < pl.col("our_qty"))
        partly_met = priced.filter(pl.col("met_qty") > MET_TOLERANCE * pl.col("our_qty"))
        cell["fallback_larger_share"] = larger.height / priced.height
        cell["fallback_partly_met_share"] = partly_met.height / priced.height
    return cell


def cost_table(frame: pl.DataFrame) -> dict:
    """A figure over no row is an absent key, never None: the registry refuses a null leaf, and `bootstrap_ci` an empty
    series."""
    costs = side_costs(frame).sort("ts").with_columns(month=pl.col("ts").dt.strftime("%Y-%m"))
    table = {}
    for side in _SIDES:
        for size in _SIZES:
            posts = costs.filter((pl.col("side") == side) & (pl.col("size") == size))
            table[f"{side}|S{size}"] = {
                "span": _cell(posts),
                **{month: _cell(posts.filter(pl.col("month") == month)) for month in MONTHS},
            }
    return table


def blend(frames: dict[str, pl.DataFrame], legs: tuple[str, ...]) -> dict:
    """Legs sum in name order: polars leaves a group_by's order unfixed, and a float sum moves with it."""
    costs = pl.concat([side_costs(frames[leg]).select("ts", "side", "size", "cost").with_columns(leg=pl.lit(leg)) for leg in legs])
    table = {}
    for size in _SIZES:
        series = (
            costs.filter(pl.col("size") == size)
            .group_by("ts", "leg")
            .agg(leg_cost=pl.col("cost").mean())
            .sort("ts", "leg")
            .group_by("ts", maintain_order=True)
            .agg(cost=pl.col("leg_cost").mean())
            .drop_nulls("cost")
            .sort("ts")["cost"]
            .to_list()
        )
        table[f"S{size}"] = {"boundaries": len(series), **_interval(series)}
    return table
