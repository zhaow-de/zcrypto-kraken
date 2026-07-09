"""§10 portfolio limits — the per-asset cap as a pure pre-trade clip.

Clip only, no redistribution (a §10 limit is a pre-trade governor, not an optimizer; the excess
sits in cash). Inclusive: a position exactly at the cap passes unclipped. The gross/net/margin-floor
limits are deliberately absent — they never bind on the current long-only book (see
docs/specs/00035-combination-trial-design.md) and return with a short-carrying or levered sleeve.
"""

from __future__ import annotations

import math

from cli.risk.errors import RiskError


def apply_position_caps(
    positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10
) -> dict[str, list[float]]:
    """Clip each asset's per-bar position to [-short_cap, +long_cap]; §10 defaults 20%/10% NAV."""
    if not isinstance(positions, dict) or not positions:
        raise RiskError(f"positions must be a non-empty dict, got {positions!r}")
    for cap_name, cap in (("long_cap", long_cap), ("short_cap", short_cap)):
        if not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
            raise RiskError(f"{cap_name} must be a finite number > 0, got {cap!r}")
    lengths = set()
    for asset, series in positions.items():
        if not isinstance(series, list) or not series:
            raise RiskError(f"positions[{asset!r}] must be a non-empty list, got {series!r}")
        for p in series:
            if not isinstance(p, (int, float)) or not math.isfinite(p):
                raise RiskError(f"positions[{asset!r}] must contain finite numbers, got {p!r}")
        lengths.add(len(series))
    if len(lengths) != 1:
        raise RiskError(f"all assets must have equal-length series, got lengths {sorted(lengths)}")
    return {asset: [min(p, long_cap) if p >= 0 else max(p, -short_cap) for p in series] for asset, series in positions.items()}
