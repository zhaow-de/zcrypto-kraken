"""B1 trial 4 (docs/specs/00134-b1-volume-confirmation-design.md): the hour-of-week volume norm (D3, D4), the A2 entry gate
it confirms (D2), arm B's positions on arm A's weights and vol scalar (D1) and the engagement counts (D8).

A bar's stamp is its open, so its hour-of-week cell is that of `ts + 4h`, the boundary at which its volume and close are known.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta

from cli.alpha.a1 import _map_to_union_index, _validate_prices_by_asset
from cli.alpha.a2 import A2Config
from cli.alpha.errors import AlphaError
from cli.features import channel_position


def volume_confirmations(stamps: list[datetime], volumes: list[float | None], *, lookback: int, min_cell_obs: int) -> list[bool]:
    for name, value in (("lookback", lookback), ("min_cell_obs", min_cell_obs)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise AlphaError(f"{name} must be an int >= 1, got {value!r}")
    if len(stamps) != len(volumes):
        raise AlphaError(f"stamps and volumes differ in length: {len(stamps)} and {len(volumes)}")
    for i, (t, v) in enumerate(zip(stamps, volumes, strict=True)):
        if t.tzinfo is None:
            raise AlphaError(f"stamps must be tz-aware, got {t!r} at index {i}")
        if i and t <= stamps[i - 1]:
            raise AlphaError(f"stamps must be strictly increasing, violated at {t.isoformat()}")
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0):
            raise AlphaError(f"volume must be a finite number above 0, got {v!r} at {t.isoformat()}")
    rows: list[float] = []
    ratios: dict[tuple[int, int], list[float]] = {}
    out: list[bool] = []
    for t, v in zip(stamps, volumes, strict=True):
        if len(rows) < lookback:
            out.append(True)  # fewer than 180 prior bars: accepted, a fill among them (D4)
            if v is not None:
                rows.append(v)
            continue
        if v is None:
            out.append(False)  # a forward-filled BTC stamp: no volume, never confirms, no bar
            continue
        level = statistics.median(rows[-lookback:])
        b = t + timedelta(hours=4)
        cell = ratios.setdefault((b.hour, b.weekday()), [])
        shape = statistics.median(cell) if len(cell) >= min_cell_obs else 1.0
        out.append(v >= level * shape)
        cell.append(v / level)
        rows.append(v)
    return out


def confirmations_by_asset(
    fed: dict[str, list[float | None]],
    h4_prices: dict[str, list[float | None]],
    union_ts: list[datetime],
    volumes: dict[str, list[float | None]],
    *,
    lookback: int,
    min_cell_obs: int,
) -> dict[str, list[bool]]:
    """One flag per own bar of `fed[a]`. Presence is read against the raw close, so a BTC fill carries no volume."""
    _validate_prices_by_asset(fed)
    if set(volumes) != set(fed):
        raise AlphaError(f"volumes' assets {sorted(volumes)} are not the prices' {sorted(fed)}")
    out: dict[str, list[bool]] = {}
    for a, prices in fed.items():
        for k, t in enumerate(union_ts):
            if (volumes[a][k] is None) != (h4_prices[a][k] is None):
                mismatch = (
                    "a volume where the close is absent" if volumes[a][k] is not None else "no volume where the close is present"
                )
                raise AlphaError(f"{a}: {mismatch} at {t.isoformat()}")
        own = [k for k, p in enumerate(prices) if p is not None]
        try:
            out[a] = volume_confirmations(
                [union_ts[k] for k in own], [volumes[a][k] for k in own], lookback=lookback, min_cell_obs=min_cell_obs
            )
        except AlphaError as exc:
            raise AlphaError(f"{a}: {exc}") from exc
    return out


def donchian_signal_confirmed(
    prices: list[float], confirm: list[bool], *, window: int, band: float
) -> tuple[list[float], list[tuple[int, bool]]]:
    if len(confirm) != len(prices):
        raise AlphaError(f"confirm holds {len(confirm)} flags for {len(prices)} prices")
    cp = channel_position(prices, window=window)
    held, out, events = 0.0, [], []
    for j in range(len(cp)):
        if cp[j] >= band:
            if held != 1.0:
                events.append((j, confirm[j]))
                if confirm[j]:
                    held = 1.0
        elif cp[j] <= -band:
            held = -1.0
        out.append(held)
    return out, events


def asset_directions_confirmed(
    prices_by_asset: dict[str, list[float | None]],
    union_ts: list,
    asset_ts: dict[str, list],
    confirm_by_asset: dict[str, list[bool]],
    *,
    config: A2Config,
) -> tuple[dict[str, list[float | None]], dict[str, dict[int, list[tuple[int, bool]]]]]:
    """`_asset_directions_a2` under short="off" with each lookback's entries gated by `confirm_by_asset[asset]`, and each
    lookback's entry events `(own bar, accepted)` under `events[asset][lookback]`."""
    if config.short != "off":
        raise AlphaError(f"the confirmed directions need short='off', got {config.short!r}")
    if set(confirm_by_asset) != set(prices_by_asset):
        raise AlphaError(f"confirm's assets {sorted(confirm_by_asset)} are not the prices' {sorted(prices_by_asset)}")
    directions: dict[str, list[float | None]] = {}
    events: dict[str, dict[int, list[tuple[int, bool]]]] = {}
    for asset, prices in prices_by_asset.items():
        confirm = confirm_by_asset[asset]
        if len(confirm) != len(asset_ts[asset]):
            raise AlphaError(f"{asset}: confirm holds {len(confirm)} flags for {len(asset_ts[asset])} bars")
        own_prices = [p for p in prices if p is not None]
        events[asset] = {}
        mapped = []
        for w in config.lookbacks:
            states, events[asset][w] = donchian_signal_confirmed(own_prices, confirm, window=w, band=config.band)
            mapped.append(_map_to_union_index(asset_ts[asset], states, union_ts))
        d: list[float | None] = []
        for k in range(len(union_ts) - 1):
            values = [m[k] for m in mapped]
            if any(v is None for v in values):
                d.append(None)
                continue
            ensemble = statistics.mean(values)
            d.append(max(ensemble, 0.0))
        directions[asset] = d
    return directions, events


def a2_positions_on_directions(
    weights: list[dict[str, float]], directions: dict[str, list[float | None]], scalar: list[float]
) -> dict[str, list[float]]:
    """`a2_book_returns`' asset positions on given weights, directions and vol scalar."""
    if len(weights) != len(scalar) or any(len(d) != len(scalar) for d in directions.values()):
        raise AlphaError("weights, directions and scalar differ in length")
    return {
        asset: [weights[k].get(asset, 0.0) * (directions[asset][k] or 0.0) * scalar[k] for k in range(len(scalar))]
        for asset in directions
    }


def entry_events_per_year(
    events: dict[str, dict[int, list[tuple[int, bool]]]], own_stamps: dict[str, list[datetime]]
) -> dict[str, dict[str, dict[str, list[int]]]]:
    """`[events, rejected]` per asset, lookback and bar-start year of the event bar, every year in which the asset has a state
    zeros included."""
    out: dict[str, dict[str, dict[str, list[int]]]] = {}
    for asset, by_lookback in events.items():
        years = sorted({own_stamps[asset][j].year for j in range(len(own_stamps[asset]) - 1)})
        out[asset] = {}
        for w, evs in by_lookback.items():
            counts = {str(year): [0, 0] for year in years}
            for j, accepted in evs:
                count = counts[str(own_stamps[asset][j].year)]
                count[0] += 1
                if not accepted:
                    count[1] += 1
            out[asset][str(w)] = counts
    return out


def directions_differ_per_year(
    directions_a: list[dict[str, list[float | None]]],
    directions_b: list[dict[str, list[float | None]]],
    union_ts: list[datetime],
) -> dict[str, int]:
    """The return indices at which any arm's direction on any asset differs, per bar-start year, every year zeros included."""
    out = {str(t.year): 0 for t in union_ts[:-1]}
    for k in range(len(union_ts) - 1):
        if any(da[a][k] != db[a][k] for da, db in zip(directions_a, directions_b) for a in da):
            out[str(union_ts[k].year)] += 1
    return out
