"""B3 trial 3's compute (docs/specs/00149-b3-btc-overlay-design.md D3): A1's confirmed-bear short state on BTC and the BTC
short a long book carries while it holds, alts never shorted.

A position is a fraction of NAV in EUR notional held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
from collections.abc import Mapping

from cli.alpha.a1 import _btc_market_bear, _check_window
from cli.alpha.b4 import _check_lengths
from cli.alpha.errors import AlphaError
from cli.features import trend_agreement


def btc_short_state(btc: list[float], *, window: int, band: float, lookbacks: tuple[int, ...]) -> list[bool]:
    """Per return index k, A1's confirmed bear read on BTC alone at close k: below its `window`-close SMA by `band`, and
    its trend agreement over `lookbacks` below 0."""
    _check_window("window", window)
    if not isinstance(band, (int, float)) or isinstance(band, bool) or not 0.0 <= band < 1.0:
        raise AlphaError(f"band must be a number in [0.0, 1.0), got {band!r}")
    agreement = trend_agreement(btc, lookbacks=list(lookbacks))
    bear = _btc_market_bear(btc, window=window, band=band)
    return [b == 1.0 and a < 0 for b, a in zip(bear, agreement, strict=True)]


def overlay_short(positions: Mapping[str, list[float]], state: list[bool], *, fraction: float) -> list[float]:
    """Per return index, `fraction` of the book's long gross where the state holds, else 0.0."""
    if not isinstance(fraction, (int, float)) or not 0 < fraction <= 0.5:
        raise AlphaError(f"fraction must be a number in (0, 0.5], got {fraction!r}")
    n = _check_lengths(positions)
    if len(state) != n:
        raise AlphaError(f"{len(state)} states for positions of {n} return indices")
    return [fraction * math.fsum(max(0.0, p[k]) for p in positions.values()) if state[k] else 0.0 for k in range(n)]


def with_btc_short(positions: Mapping[str, list[float]], short: list[float], *, borrow: bool) -> dict[str, list[float]]:
    """The book with `short` sold out of its BTC, netted against the BTC the book holds; with `borrow` False the BTC is
    floored at 0, so the book sells only the BTC it holds. Every other instrument as it is."""
    if "BTC" not in positions:
        raise AlphaError("the book holds no BTC to carry the short")
    if len(short) != _check_lengths(positions):
        raise AlphaError(f"{len(short)} shorts for positions of another length")
    btc = [p - s for p, s in zip(positions["BTC"], short, strict=True)]
    if not borrow:
        btc = [max(0.0, p) for p in btc]
    return {i: btc if i == "BTC" else list(v) for i, v in positions.items()}
