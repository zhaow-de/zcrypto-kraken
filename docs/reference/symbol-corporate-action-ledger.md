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

- **DOT 1:100 redenomination (Aug 2020)** — **IN our price history, in the first bar's `open` and `high`, and invisible to the close-based audit.** Corrected 2026-08-28 (T0025); the previous claim here was "not in our price history", reasoning that Polkadot redenominated before Kraken listed DOT/EUR. The dump says otherwise. `DOT/EUR`'s first daily bar is **2020-08-18** and reads `open=29.0000 high=45.0000 low=2.5100 close=2.6095` — an ~11x intraday collapse into the book every later bar trades in. At 60 m the whole transition sits inside the **first hourly bar** (`17:00 open=29.000 high=45.000 low=2.510 close=2.750`); every subsequent hour trades 2.5–3.4.
  - **What is measured, and what is not.** Measured: bar one's `open`/`high` sit **11.1x and 17.2x** above its own close, and above every subsequent print, inside the redenomination window. NOT measured: which denomination those prints are in. A 1:100 old-unit price would be ~**261 EUR** (2.6095 x 100), and 29–45 matches no clean ratio — consistent with denomination-confused orders hitting a thin new-DOT book, not with a tidy old-unit tape. The artifact is certain; its mechanism is not, and this bullet says so rather than inferring one.
  - **NEVER rescale bar one — exclude it or distrust it.** Reading "old unit" literally invites a 1/100 correction, which would turn 29.00 into **0.29** — an order of magnitude below the true price and worse than the artifact it repairs. The safe handling is the same under every explanation: bar one's `open` and `high` are unusable for DOT/EUR; its `close` is not, at any resolution.
  - **Consequence, and it is narrow but real**: any series reading DOT/EUR's `open` or `high` on 2020-08-18 reads a number no later bar can be compared against. Closes are unaffected at every resolution — the first close already trades in the surviving book — so a close-only strategy is untouched.
  - **Why the audit missed it, which is the transferable part**: `price_discontinuities` tests bar-over-bar **closes**. A corporate action that completes *within the first bar of a listing* leaves no close-to-close ratio to flag, at any bar size. The instrument cannot see this class, so the ledger has to carry it by hand. **Look at the first bar of every newly admitted pair** — a `high/close` or `open/close` ratio far from 1 on bar one is this signature.
- **No splits / redenominations / reverse-splits** were found in any of the 12 EUR/BTC pairs' full histories (see the audit). Our EUR- and BTC-quoted legs are unaffected by the redenominations/renames that can afflict other Kraken markets.

## Quote-book migrations

- **USDT EEA delisting (post-MiCA)** — a market-structure fact tracked per §3, but it affects **USDT-quoted** pairs, **none of which are in our EUR/BTC universe**. Not applicable to the traded legs; noted only because it shifted volume into EUR/USD books (a liquidity-feature discontinuity for anyone modelling USDT pairs).

## Point-in-time coverage (listing dates & span)

Per-pair first and last bar from the canonical daily dump `data/ohlc-full/<BASE>/<QUOTE>/1440.parquet`, measured 2026-08-28. **The first bar is a coverage floor, not a listing date** — it is the earliest bar Kraken's dump carries, which is the listing date only where the two coincide; treat it as "no history before this" rather than "listed on this day". The last bar is the quarterly dump's freeze, identical across pairs, and is **not** evidence a pair still trades — that is `AssetPairs`' `status`, checked every sweep.

| Pair | Daily bars | First bar | Last bar |
| --- | ---: | --- | --- |
| ADA/EUR | 2742 | 2018-09-28 | 2026-03-31 |
| AVAX/EUR | 1562 | 2021-12-21 | 2026-03-31 |
| BTC/EUR | 4581 | 2013-09-10 | 2026-03-31 |
| DOGE/EUR | 2295 | 2019-12-19 | 2026-03-31 |
| DOT/EUR | 2052 | 2020-08-18 | 2026-03-31 |
| ETH/BTC | 3679 | 2016-03-03 | 2026-03-31 |
| ETH/EUR | 3890 | 2015-08-07 | 2026-03-31 |
| LINK/EUR | 2380 | 2019-09-25 | 2026-03-31 |
| LTC/EUR | 4542 | 2013-09-14 | 2026-03-31 |
| SOL/BTC | 1749 | 2021-06-17 | 2026-03-31 |
| SOL/EUR | 1749 | 2021-06-17 | 2026-03-31 |
| XRP/EUR | 3239 | 2017-05-18 | 2026-03-31 |

**Survivorship**: every pair here is currently selected and currently listed, so this table cannot show the failure it exists to guard — a delisted pair leaves the dump. Detection is `sweep_refusals` (a selected pair absent from `AssetPairs`) and `scan_delistings` (the venue's own announcement — 93–116 days ahead for an asset delisting, though a funding-rail discontinuation can be published after it takes effect), both run by `/zcrypto-refdata-sweep`. When one fires, the pair's row is frozen here with its delisting date.

## Discontinuity audit (distrust-the-instrument)

`cli.ohlc.qa.price_discontinuities` (max_ratio = 3.0) over the full-history dataset `data/ohlc-full/` (iter-008), daily closes. It flags bar-over-bar close moves beyond 3× or below 1/3× — candidate corporate actions or data errors. **Two flags across all 12 symbols, both genuine market events (not corporate actions):**

| Series | Date | Close | Ratio | Classification |
| --- | --- | ---: | ---: | --- |
| ETH/EUR | 2015-08-08 | €0.65 | 0.25 (−75%) | **Genuine** — ETH's chaotic launch weeks (listed Jul 2015; extreme thin-market volatility). |
| DOGE/EUR | 2021-01-28 | €0.030 | 4.89 (+389%) | **Genuine** — the Jan-2021 WSB/Elon DOGE mania pump. |

Every other universe symbol shows **no** >3× / <1/3× daily move. **Conclusion:** the full-history dataset is clean of corporate-action price artifacts for the universe; **no price adjustments are required for backtesting.**

## Maintenance

Re-run `price_discontinuities` (and re-check aliases) whenever the dataset extends or a new pair is admitted. A new >3× flag must be classified — genuine market move vs corporate action vs data error — before any series that spans it is used in a backtest.

**And read the FIRST bar of every newly admitted pair by hand — the ratio test cannot.** `price_discontinuities` compares bar-over-bar closes, so a corporate action completing inside the first bar of a listing leaves nothing for it to flag at any bar size; DOT/EUR is the worked example above. The signature is a first bar whose `open` or `high` sits far from its `close` — DOT/EUR's reads `open=29.00 high=45.00 close=2.61`, ~11×. One look per admitted pair, and only ever on bar one.

**A delisting is the other half, and it does not arrive through this dataset at all** — a delisted pair simply stops appearing, which no audit over the dump can distinguish from a pair that was never there. `/zcrypto-refdata-sweep` owns it: `sweep_refusals` on the venue's own pair list, and `scan_delistings` on its announcements.
