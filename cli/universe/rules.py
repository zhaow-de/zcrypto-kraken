from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MIN_LEVERAGE = 2
# EUR/day; the floor at which a max-size position (`SPREAD_REFERENCE_NOTIONAL_EUR`) is ≈1% of a
# name's median daily EUR volume — our microstructure-impact bar. Tunable.
DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 150_000.0
# effective-spread bps per side at `SPREAD_REFERENCE_NOTIONAL_EUR`, so this and the volume floor
# both answer "can we trade this at our size?". Anchored to the fee stack, not fitted to the data: a
# round trip crossing twice at the cap costs a quarter of the tier-1 maker round trip (2 x 0.40%,
# `docs/reference/kraken-fee-schedule.md`) -- a chosen convention, not a derivation: the point where
# spread stops being a rounding error on the fee stack. Absolute, never re-derived from the live
# tier: maker -> 0% at the top tiers would cap at zero and reject everything. T0014 (spec 00066,
# resolved) holds the calibration, T0024 (spec 00067, resolved) the cap's convention.
DEFAULT_MAX_SPREAD_BPS = 10.0
# The max-size position the volume floor and the spread cap are both priced at: ~$10k account, ≤1.5x
# gross, ~12 names.
SPREAD_REFERENCE_NOTIONAL_EUR = 1_400.0
MANDATORY = ("BTC", "ETH")
MIN_NAMES = 8
MAX_NAMES = 15


@dataclass(frozen=True, kw_only=True)
class UniverseSelection:
    entries: tuple[dict, ...]

    @property
    def selected(self) -> tuple[str, ...]:
        return tuple(entry["symbol"] for entry in self.entries if entry["selected"])

    @property
    def escalate(self) -> bool:
        count = len(self.selected)
        return count < MIN_NAMES or count > MAX_NAMES


def _is_mandatory(pair, mandatory: tuple[str, ...]) -> bool:
    # "BTC/ETH mandatory" (master plan §3) means the flagship EUR-quoted legs; a BTC-quoted
    # relative-value leg on the same base (e.g. ETH/BTC) stays subject to the normal rule.
    return pair.base in mandatory and pair.quote == "EUR"


def finalize_universe(
    pairs: list,
    volumes: dict[str, float],
    *,
    min_leverage: int = DEFAULT_MIN_LEVERAGE,
    min_median_quote_volume: float = DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
    mandatory: tuple[str, ...] = MANDATORY,
    spreads: dict[str, float] | None = None,
    max_spread_bps: float = DEFAULT_MAX_SPREAD_BPS,
) -> UniverseSelection:
    """Apply the master plan §3 mechanical selection rule to each `cli.snapshot` `PairSnapshot`.
    A symbol absent from the opt-in `spreads` map (effective-spread bps per side at
    `SPREAD_REFERENCE_NOTIONAL_EUR`) is recorded `spread_bps: None`, never rejected: absence of
    evidence is not evidence of a wide spread, and the null keeps an unscreened symbol visible in
    the artifact (T0024, spec 00067, resolved)."""
    entries = []
    for pair in pairs:
        max_leverage = max(pair.leverage_buy) if pair.leverage_buy else 0
        quote_volume = volumes.get(pair.symbol, 0.0)

        reasons = []
        if not pair.margin_enabled:
            reasons.append("margin not enabled")
        if max_leverage < min_leverage:
            reasons.append(f"max leverage {max_leverage} below floor {min_leverage}")
        if quote_volume < min_median_quote_volume:
            reasons.append(f"median quote volume {quote_volume} below floor {min_median_quote_volume}")

        spread_bps = None if spreads is None else spreads.get(pair.symbol)
        if spread_bps is not None and spread_bps > max_spread_bps:
            reasons.append(f"effective spread {spread_bps} bps/side above cap {max_spread_bps}")

        passes = not reasons
        forced = _is_mandatory(pair, mandatory) and not passes
        if forced:
            reasons.append("mandatory: kept despite failing the selection rule")

        entries.append(
            {
                "symbol": pair.symbol,
                "selected": passes or forced,
                "margin_enabled": pair.margin_enabled,
                "max_leverage": max_leverage,
                "median_quote_volume": quote_volume,
                "spread_bps": spread_bps,
                "reasons": reasons,
            }
        )

    return UniverseSelection(entries=tuple(entries))
