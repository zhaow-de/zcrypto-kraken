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


def _wsname_index(assetpairs_result: dict) -> dict[str, tuple[str, dict]]:
    return {pair["wsname"]: (key, pair) for key, pair in assetpairs_result.items() if pair.get("wsname")}


def _altname(assets_result: dict, asset_code: str | None) -> str | None:
    asset = assets_result.get(asset_code) if asset_code else None
    return asset["altname"] if asset else None


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
            )
        )
    return rows
