# Symbol & Corporate-Action Ledger (⏱ 2026-07-07)

The §3-required ledger of symbol aliases and corporate actions for the 12-name universe — **a hard dependency of every backtest** (a redenomination or unrecorded rename injects a spurious price/volume discontinuity into any series that spans it). Scoped to the universe basket; re-audit when the dataset extends (new pairs, full-exchange breadth) or a new corporate action occurs.

## Kraken symbol aliases (bite in every export + API mapping)

Kraken's internal codes differ from the common tickers, and the downloadable OHLCVT dumps use *altnames*. For the universe (from iter-002's snapshot register + the iter-008 dump-name resolution):

| Common | Kraken base | Dump altname (EUR / BTC pair) |
| --- | --- | --- |
| BTC | **XBT** | `XBTEUR` |
| DOGE | **XDG** | `XDGEUR` |
| ETH, SOL, XRP, ADA, LINK, LTC, DOT, AVAX | (unchanged) | `ETHEUR`, `SOLEUR`, `XRPEUR`, `ADAEUR`, `LINKEUR`, `LTCEUR`, `DOTEUR`, `AVAXEUR` |
| ETH/BTC, SOL/BTC (RV legs) | — | `ETHXBT`, `SOLXBT` |

The canonical dataset uses the common `BASE/QUOTE` symbols (`BTC/EUR`, `DOGE/EUR`, …); `cli.backfill.dump_pair_name` and `cli.snapshot`'s alias ledger own the XBT↔BTC / XDG↔DOGE mapping.

## Corporate actions

- **DOT 1:100 redenomination (Aug 2020)** — **not in our price history.** Polkadot redenominated at genesis (Aug 2020) *before* Kraken listed DOT/EUR, so `DOT/EUR` carries no pre-redenomination prices and shows **no discontinuity** (confirmed by the scan below). No adjustment needed.
- **No splits / redenominations / reverse-splits** were found in any of the 12 EUR/BTC pairs' full histories (see the audit). Our EUR- and BTC-quoted legs are unaffected by the redenominations/renames that can afflict other Kraken markets.

## Quote-book migrations

- **USDT EEA delisting (post-MiCA)** — a market-structure fact tracked per §3, but it affects **USDT-quoted** pairs, **none of which are in our EUR/BTC universe**. Not applicable to the traded legs; noted only because it shifted volume into EUR/USD books (a liquidity-feature discontinuity for anyone modelling USDT pairs).

## Discontinuity audit (distrust-the-instrument)

`cli.ohlc.qa.price_discontinuities` (max_ratio = 3.0) over the full-history dataset `data/ohlc-full/` (iter-008), daily closes. It flags bar-over-bar close moves beyond 3× or below 1/3× — candidate corporate actions or data errors. **Two flags across all 12 symbols, both genuine market events (not corporate actions):**

| Series | Date | Close | Ratio | Classification |
| --- | --- | ---: | ---: | --- |
| ETH/EUR | 2015-08-08 | €0.65 | 0.25 (−75%) | **Genuine** — ETH's chaotic launch weeks (listed Jul 2015; extreme thin-market volatility). |
| DOGE/EUR | 2021-01-28 | €0.030 | 4.89 (+389%) | **Genuine** — the Jan-2021 WSB/Elon DOGE mania pump. |

Every other universe symbol shows **no** >3× / <1/3× daily move. **Conclusion:** the full-history dataset is clean of corporate-action price artifacts for the universe; **no price adjustments are required for backtesting.**

## Maintenance

Re-run `price_discontinuities` (and re-check aliases) whenever the dataset extends or a new pair is admitted. A new >3× flag must be classified — genuine market move vs corporate action vs data error — before any series that spans it is used in a backtest.
