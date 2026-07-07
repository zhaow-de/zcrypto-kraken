from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MIN_LEVERAGE = 2
DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 1_000_000.0  # EUR/day, documented, tunable
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
    # "BTC/ETH mandatory" (master plan §3) means the flagship EUR-quoted legs. A BTC-quoted
    # relative-value leg sharing the same base (e.g. ETH/BTC) stays subject to the normal rule.
    return pair.base in mandatory and pair.quote == "EUR"


def finalize_universe(
    pairs: list,
    volumes: dict[str, float],
    *,
    min_leverage: int = DEFAULT_MIN_LEVERAGE,
    min_median_quote_volume: float = DEFAULT_MIN_MEDIAN_QUOTE_VOLUME,
    mandatory: tuple[str, ...] = MANDATORY,
) -> UniverseSelection:
    """Apply the §3 mechanical selection rule to each candidate `cli.snapshot` `PairSnapshot`.

    A candidate is selected iff margin-enabled, its best leverage tier clears `min_leverage`, and
    its median quote volume (`volumes.get(symbol, 0)`) clears `min_median_quote_volume`. A
    `mandatory` EUR-quoted leg (BTC/ETH by default) is always selected regardless, flagged in
    `reasons` only when it would otherwise have failed.
    """
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
                "reasons": reasons,
            }
        )

    return UniverseSelection(entries=tuple(entries))
