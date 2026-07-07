from __future__ import annotations

from cli.backfill.errors import BackfillError

# Kraken OHLCVT dump altnames apply these aliases to both legs of the pair.
_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}


def dump_pair_name(symbol: str) -> str:
    """Map a canonical `"BASE/QUOTE"` symbol to its Kraken OHLCVT dump altname.

    Applies the Kraken aliases BTC->XBT, DOGE->XDG to both legs, then concatenates (e.g.
    `"BTC/EUR"` -> `"XBTEUR"`, `"DOGE/EUR"` -> `"XDGEUR"`, `"ETH/BTC"` -> `"ETHXBT"`).
    """
    try:
        base, quote = symbol.split("/")
    except ValueError as exc:
        raise BackfillError(f"not a BASE/QUOTE symbol: {symbol!r}") from exc
    return _ALIAS.get(base, base) + _ALIAS.get(quote, quote)
