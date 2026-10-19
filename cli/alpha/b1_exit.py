"""B1 trial 5 (docs/specs/00135-b1-hourly-channel-exits-design.md): the hourly exit check on A2's own channel (D2), arm B's
slot positions, price paths and split costing (D1, D3) and the engagement counts (D8).

Each return index has four slots: slot 0 runs from the boundary close to the interval's first interior close, slot `i` from
the interior close at offset `i` to the next, slot 3 ending at the next boundary close.
"""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime

from cli.alpha.a1 import _map_to_union_index, _validate_prices_by_asset
from cli.alpha.a2 import A2Config
from cli.alpha.errors import AlphaError
from cli.features import channel_position


def new_low(prior: list[float], close: float, *, band: float) -> bool:
    lo, hi = min(min(prior), close), max(max(prior), close)
    return hi > lo and 2 * (close - lo) / (hi - lo) - 1 <= -band


def donchian_signal_hourly_exit(
    prices: list[float],
    interior: list[tuple[float | None, float | None, float | None]],
    *,
    window: int,
    band: float,
) -> tuple[list[tuple[float, float, float, float]], list[tuple[int, int, bool]]]:
    cp = channel_position(prices, window=window)
    held, out, exits = 0.0, [], []
    for j in range(len(cp)):
        if cp[j] >= band:
            held = 1.0
        elif cp[j] <= -band:
            held = -1.0
        slots = [held]
        for offset, h in enumerate(interior[j + 1], start=1):
            if held == 1.0 and h is not None:
                # held reached +1 at some j' <= j with j' >= window - 1, so the window is whole.
                prior = prices[j + 2 - window : j + 1]
                if new_low(prior, h, band=band):
                    held = -1.0
                    exits.append((j, offset, new_low(prior, prices[j + 1], band=band)))
            slots.append(held)
        out.append((slots[0], slots[1], slots[2], slots[3]))
    return out, exits


def interior_closes_by_asset(
    fed: dict[str, list[float | None]],
    h4_prices: dict[str, list[float | None]],
    union_ts: list[datetime],
    hourly: dict[str, tuple[list[datetime], list[float]]],
) -> dict[str, list[tuple[float | None, float | None, float | None]]]:
    """One triple per own bar of `fed[a]`, `None` where the hour is missing. An hourly bar must lie in a 4h bar the raw
    `h4_prices[a]` holds, so one in a BTC fill's span is refused, never read as the fill's interior."""
    _validate_prices_by_asset(fed)
    if set(hourly) != set(fed):
        raise AlphaError(f"hourly's assets {sorted(hourly)} are not the prices' {sorted(fed)}")
    union_pos = {t: k for k, t in enumerate(union_ts)}
    out: dict[str, list[tuple[float | None, float | None, float | None]]] = {}
    for a, prices in fed.items():
        stamps, closes = hourly[a]
        if len(stamps) != len(closes):
            raise AlphaError(f"{a}: hourly stamps and closes differ in length: {len(stamps)} and {len(closes)}")
        own_pos = {k: j for j, k in enumerate(k for k, p in enumerate(prices) if p is not None)}
        triples: list[list[float | None]] = [[None, None, None] for _ in own_pos]
        for i, (h, c) in enumerate(zip(stamps, closes, strict=True)):
            if h.tzinfo is None:
                raise AlphaError(f"{a}: hourly stamps must be tz-aware, got {h!r} at index {i}")
            if i and h <= stamps[i - 1]:
                raise AlphaError(f"{a}: hourly stamps must be strictly increasing, violated at {h.isoformat()}")
            if h.timestamp() % 3_600 != 0:
                raise AlphaError(f"{a}: hourly stamp off the hour at {h.isoformat()}")
            if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) or c <= 0:
                raise AlphaError(f"{a}: hourly close must be a finite number above 0, got {c!r} at {h.isoformat()}")
            k = union_pos.get(datetime.fromtimestamp(int(h.timestamp()) // 14_400 * 14_400, UTC))
            if k is None or h4_prices[a][k] is None:
                raise AlphaError(f"{a}: an hourly bar at {h.isoformat()} lies in a 4h bar the 240 series lacks")
            offset = int(h.timestamp()) % 14_400 // 3_600
            if offset < 3:
                triples[own_pos[k]][offset] = c
        out[a] = [(t[0], t[1], t[2]) for t in triples]
    return out


def asset_directions_hourly_exit(
    prices_by_asset: dict[str, list[float | None]],
    union_ts: list,
    asset_ts: dict[str, list],
    interior_by_asset: dict[str, list[tuple[float | None, float | None, float | None]]],
    *,
    config: A2Config,
) -> tuple[dict[str, list[tuple[float, float, float, float] | None]], dict[str, dict[int, list[tuple[int, int, bool]]]]]:
    """`_asset_directions_a2` under short="off" on `donchian_signal_hourly_exit`'s four-slot states, clipped per slot, and
    each lookback's exit events `(own bar, offset, early)` under `events[asset][lookback]`."""
    if config.short != "off":
        raise AlphaError(f"the hourly-exit directions need short='off', got {config.short!r}")
    if set(interior_by_asset) != set(prices_by_asset):
        raise AlphaError(f"interior's assets {sorted(interior_by_asset)} are not the prices' {sorted(prices_by_asset)}")
    directions: dict[str, list[tuple[float, float, float, float] | None]] = {}
    events: dict[str, dict[int, list[tuple[int, int, bool]]]] = {}
    for asset, prices in prices_by_asset.items():
        own_prices = [p for p in prices if p is not None]
        if len(interior_by_asset[asset]) != len(own_prices):
            raise AlphaError(f"{asset}: interior holds {len(interior_by_asset[asset])} triples for {len(own_prices)} prices")
        events[asset] = {}
        mapped = []
        for w in config.lookbacks:
            states, events[asset][w] = donchian_signal_hourly_exit(own_prices, interior_by_asset[asset], window=w, band=config.band)
            mapped.append(_map_to_union_index(asset_ts[asset], states, union_ts))
        d: list[tuple[float, float, float, float] | None] = []
        for k in range(len(union_ts) - 1):
            values = [m[k] for m in mapped]
            if any(v is None for v in values):
                d.append(None)
                continue
            d.append(tuple(max(statistics.mean(v[i] for v in values), 0.0) for i in range(4)))
        directions[asset] = d
    return directions, events


def a2_slot_positions(
    weights: list[dict[str, float]], slot_directions: dict[str, list[tuple[float, float, float, float] | None]], scalar: list[float]
) -> dict[str, list[tuple[float, float, float, float]]]:
    """`a2_book_returns`' asset-positions expression per slot, on given weights, slot directions and vol scalar."""
    if len(weights) != len(scalar) or any(len(d) != len(scalar) for d in slot_directions.values()):
        raise AlphaError("weights, slot directions and scalar differ in length")
    return {
        asset: [
            tuple(weights[k].get(asset, 0.0) * (0.0 if d[k] is None else d[k][i]) * scalar[k] for i in range(4))
            for k in range(len(scalar))
        ]
        for asset, d in slot_directions.items()
    }


def price_paths(
    fed: dict[str, list[float | None]], interior_by_asset: dict[str, list[tuple[float | None, float | None, float | None]]]
) -> dict[str, list[tuple[float, float, float, float, float] | None]]:
    """`(P0, P1, P2, P3, P4)` per return index, a missing hour carrying the previous close; `None` where either boundary
    close is."""
    out: dict[str, list[tuple[float, float, float, float, float] | None]] = {}
    for a, prices in fed.items():
        triples = interior_by_asset[a]
        paths: list[tuple[float, float, float, float, float] | None] = []
        j = -1
        for k in range(len(prices) - 1):
            if prices[k] is not None:
                j += 1
            if prices[k] is None or prices[k + 1] is None:
                paths.append(None)
                continue
            path = [prices[k]]
            for h in triples[j + 1]:
                path.append(path[-1] if h is None else h)
            path.append(prices[k + 1])
            paths.append((path[0], path[1], path[2], path[3], path[4]))
        out[a] = paths
    return out


def net_of_cost_hourly(
    slot_positions: dict[str, list[tuple[float, float, float, float]]],
    paths: dict[str, list[tuple[float, float, float, float, float] | None]],
    *,
    cost_per_side: float,
) -> list[float]:
    assets = list(slot_positions)
    previous = [0.0] * len(assets)
    net: list[float] = []
    for k in range(len(slot_positions[assets[0]])):
        gross, traded = 0.0, 0.0
        for i, asset in enumerate(assets):
            ps, path = slot_positions[asset][k], paths[asset][k]
            if path is not None:
                if ps[0] == ps[1] == ps[2] == ps[3]:
                    gross += ps[0] * (path[4] / path[0] - 1)
                else:
                    gross += sum(ps[s] * (path[s + 1] - path[s]) / path[0] for s in range(4))
            for p in ps:
                traded += abs(p - previous[i])
                previous[i] = p
        net.append(gross - traded * cost_per_side)
    return net


def intra_turnover(slot_positions: dict[str, list[tuple[float, float, float, float]]]) -> float:
    return sum(abs(ps[i] - ps[i - 1]) for slots in slot_positions.values() for ps in slots for i in range(1, 4))


def exit_events_per_year(
    events: dict[str, dict[int, list[tuple[int, int, bool]]]], own_stamps: dict[str, list[datetime]]
) -> dict[str, dict[str, dict[str, list[int]]]]:
    """`[events, early, false]` per asset, lookback and bar-start year of the own bar opening the event's interval, every
    year the asset has a state, zeros included."""
    out: dict[str, dict[str, dict[str, list[int]]]] = {}
    for asset, by_lookback in events.items():
        years = sorted({own_stamps[asset][j].year for j in range(len(own_stamps[asset]) - 1)})
        out[asset] = {}
        for w, evs in by_lookback.items():
            counts = {str(year): [0, 0, 0] for year in years}
            for j, _, early in evs:
                count = counts[str(own_stamps[asset][j].year)]
                count[0] += 1
                count[1 if early else 2] += 1
            out[asset][str(w)] = counts
    return out


def hourly_closes_differ_per_year(
    directions_a: list[dict[str, list[float | None]]],
    slot_directions_b: list[dict[str, list[tuple[float, float, float, float] | None]]],
    union_ts: list[datetime],
) -> dict[str, int]:
    """Per bar-start year, zeros included, the count of hourly closes `(k, offset)`, offset 0 the boundary close, at which
    any arm's slot direction on any asset differs from arm A's direction at `k`, `None` equal to `None`."""
    out = {str(t.year): 0 for t in union_ts[:-1]}
    for k in range(len(union_ts) - 1):
        for i in range(4):
            if any(
                (db[a][k] is None) != (da[a][k] is None) or (db[a][k] is not None and db[a][k][i] != da[a][k])
                for da, db in zip(directions_a, slot_directions_b)
                for a in da
            ):
                out[str(union_ts[k].year)] += 1
    return out
