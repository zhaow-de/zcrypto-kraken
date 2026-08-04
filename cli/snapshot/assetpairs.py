from __future__ import annotations

from dataclasses import dataclass

# Kraken's wsname/legacy asset codes spell these two differently from the common ticker (§3).
_COMMON_TO_KRAKEN = {"BTC": "XBT", "DOGE": "XDG"}

CANDIDATE_SYMBOLS: tuple[str, ...] = (
    "BTC/EUR",
    "ETH/EUR",
    "SOL/EUR",
    "XRP/EUR",
    "ADA/EUR",
    "LINK/EUR",
    "DOGE/EUR",
    "LTC/EUR",
    "DOT/EUR",
    "AVAX/EUR",
    "ETH/BTC",
    "SOL/BTC",
)


@dataclass(frozen=True, kw_only=True)
class PairSnapshot:
    symbol: str
    base: str
    quote: str
    found: bool
    pair_key: str | None
    wsname: str | None
    base_altname: str | None
    quote_altname: str | None
    margin_enabled: bool
    leverage_buy: tuple[int, ...]
    leverage_sell: tuple[int, ...]
    ordermin: str | None
    costmin: str | None
    status: str | None
    # The ⏱ facts the master plan calls externally owned, which the first cut of this register did
    # not capture: the public volume-tiered fee ladders, the per-asset borrow rate, and the margin
    # /position bands. Kept as full ladders (not just the base tier) so a drift diff can name WHICH
    # tier moved; the rendered doc shows the base tier and the ladder depth.
    fees_taker: tuple[tuple[float, float], ...]
    fees_maker: tuple[tuple[float, float], ...]
    fee_taker_base: float | None
    fee_maker_base: float | None
    base_margin_rate: float | None
    base_collateral_value: float | None
    margin_call: int | None
    margin_stop: int | None
    long_position_limit: int | None
    short_position_limit: int | None


def _wsname_index(assetpairs_result: dict) -> dict[str, tuple[str, dict]]:
    return {pair["wsname"]: (key, pair) for key, pair in assetpairs_result.items() if pair.get("wsname")}


def _altname(assets_result: dict, asset_code: str | None) -> str | None:
    asset = assets_result.get(asset_code) if asset_code else None
    return asset["altname"] if asset else None


def _tiers(raw) -> tuple[tuple[float, float], ...]:
    """Kraken renders a fee ladder as [[volume, percent], ...]; normalise to a tuple of pairs."""
    return tuple((float(v), float(pct)) for v, pct in (raw or []))


def _asset_field(assets_result: dict, asset_code: str | None, field: str) -> float | None:
    asset = assets_result.get(asset_code) if asset_code else None
    value = asset.get(field) if asset else None
    return float(value) if value is not None else None


def _not_found(symbol: str, base: str, quote: str) -> PairSnapshot:
    return PairSnapshot(
        symbol=symbol,
        base=base,
        quote=quote,
        found=False,
        pair_key=None,
        wsname=None,
        base_altname=None,
        quote_altname=None,
        margin_enabled=False,
        leverage_buy=(),
        leverage_sell=(),
        ordermin=None,
        costmin=None,
        status=None,
        fees_taker=(),
        fees_maker=(),
        fee_taker_base=None,
        fee_maker_base=None,
        base_margin_rate=None,
        base_collateral_value=None,
        margin_call=None,
        margin_stop=None,
        long_position_limit=None,
        short_position_limit=None,
    )


def derive_universe(assetpairs_result: dict, assets_result: dict, symbols: list[str]) -> list[PairSnapshot]:
    """Resolve each `BASE/QUOTE` candidate symbol to its Kraken pair via `wsname`.

    Tolerates Kraken's alias spellings (XBT for BTC, XDG for DOGE) when building the wsname lookup
    key, and resolves the base/quote asset aliases from `assets_result` (ground truth, not transcribed).
    Symbols that are absent or non-margin are flagged (`found`/`margin_enabled`), never dropped.
    """
    index = _wsname_index(assetpairs_result)
    rows = []
    for symbol in symbols:
        base, quote = symbol.split("/")
        ws_key = f"{_COMMON_TO_KRAKEN.get(base, base)}/{_COMMON_TO_KRAKEN.get(quote, quote)}"
        hit = index.get(ws_key)
        if hit is None:
            rows.append(_not_found(symbol, base, quote))
            continue
        pair_key, pair = hit
        leverage_buy = tuple(pair.get("leverage_buy", []))
        fees_taker = _tiers(pair.get("fees"))
        fees_maker = _tiers(pair.get("fees_maker"))
        rows.append(
            PairSnapshot(
                symbol=symbol,
                base=base,
                quote=quote,
                found=True,
                pair_key=pair_key,
                wsname=pair.get("wsname"),
                base_altname=_altname(assets_result, pair.get("base")),
                quote_altname=_altname(assets_result, pair.get("quote")),
                margin_enabled=bool(leverage_buy),
                leverage_buy=leverage_buy,
                leverage_sell=tuple(pair.get("leverage_sell", [])),
                ordermin=pair.get("ordermin"),
                costmin=pair.get("costmin"),
                status=pair.get("status"),
                fees_taker=fees_taker,
                fees_maker=fees_maker,
                fee_taker_base=fees_taker[0][1] if fees_taker else None,
                fee_maker_base=fees_maker[0][1] if fees_maker else None,
                # The borrow/rollover rate is a property of the ASSET, not the pair — reading it
                # off the pair would silently yield None for every row.
                base_margin_rate=_asset_field(assets_result, pair.get("base"), "margin_rate"),
                base_collateral_value=_asset_field(assets_result, pair.get("base"), "collateral_value"),
                margin_call=pair.get("margin_call"),
                margin_stop=pair.get("margin_stop"),
                long_position_limit=pair.get("long_position_limit"),
                short_position_limit=pair.get("short_position_limit"),
            )
        )
    return rows
