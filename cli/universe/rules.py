from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MIN_LEVERAGE = 2
# EUR/day; a full max-size position (~€1,400 at ~$10k, ≤1.5x gross, ~12 names) ≈ 1% of median daily
# EUR volume — our microstructure-impact floor. Tunable.
DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 150_000.0
# bps per side, effective spread at the SAME max-size position the volume floor above is calibrated
# against (~EUR 1,400), so the two criteria are commensurable -- both answer "can we trade this at
# our size?". Anchored to the fee stack rather than tuned to the data: a round trip crossing twice
# at this cap costs 25% of the tier-1 round-trip maker fee (2 x 0.40% = 80bps), at which point
# spread has stopped being a rounding error on the fee stack. The 25% itself is a chosen
# convention, not a derivation -- at the cap spread is 20% of the 100bps round trip, so "dominant"
# would need ~40bps/side. Held as an ABSOLUTE constant rather than evaluated against the live tier:
# at the top tiers maker -> 0%, and a "25% of the maker fee" formula would degenerate to a cap of
# zero and reject everything.
# Calibrated over 2026-07-08..07-21 (T0014, spec 00066): every current member passes, DOT worst at
# 6.55 bps/side (16.4% of the RT fee) -- i.e. this criterion excludes nothing today and is a guard
# for future refreshes, not a filter that changes the current names. That 6.55 is a log-notional
# interpolation between the table's EUR 1k and 10k anchors, not a measurement at EUR 1,400.
DEFAULT_MAX_SPREAD_BPS = 10.0
# The reference position the cap is priced at, matching the volume floor's own sizing note.
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
    spreads: dict[str, float] | None = None,
    max_spread_bps: float = DEFAULT_MAX_SPREAD_BPS,
) -> UniverseSelection:
    """Apply the §3 mechanical selection rule to each candidate `cli.snapshot` `PairSnapshot`.

    A candidate is selected iff margin-enabled, its best leverage tier clears `min_leverage`, and
    its median quote volume (`volumes.get(symbol, 0)`) clears `min_median_quote_volume`. A
    `mandatory` EUR-quoted leg (BTC/ETH by default) is always selected regardless, flagged in
    `reasons` only when it would otherwise have failed.

    `spreads` maps symbol -> effective spread in bps per side at `SPREAD_REFERENCE_NOTIONAL_EUR`
    (T0024, spec 00067). It is OPT-IN: omit it and no spread criterion applies -- the selection
    OUTCOME (`selected`, `escalate`, every `reasons` list) is unchanged, though the output is NOT
    byte-identical: every entry gains a `spread_bps` key, null on that path. A symbol ABSENT from
    the map is recorded `spread_bps: None` and is **not** rejected -- the capture daemon subscribes
    to EUR-quoted pairs only, so the BTC-quoted universe legs have no L2 at all, and absence of
    evidence is not evidence of a wide spread. The null is deliberate: it makes the unscreened
    symbols visible in the artifact instead of letting a reader assume all twelve were screened.
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
