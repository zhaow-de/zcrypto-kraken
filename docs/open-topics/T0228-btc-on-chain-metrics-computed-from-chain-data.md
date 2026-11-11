---
status: open
ripe_when: 'an activity — rung 3''s entry recorded, `docs/reference/rung3/days.md` reaching `develop` with week 1''s records pull request, its first entry the birth; check: `test -f docs/reference/rung3/days.md` exits 0'
---

# BTC on-chain metrics computed from chain data — C3's first step

## Context — what

C3's first step: compute BTC's on-chain valuation series — MVRV, MVRV-Z, realized cap, NUPL, SOPR, aSOPR and the STH/LTH split — ourselves from public chain data, with Bitcoin Core and a pinned, self-hosted Bitview/BRK (Bitcoin Research Kit), each output valued at our own Kraken EUR closes, each day cut by block height and written once as its vintage; then LTC and DOGE the same way. It is the free version on which C3 asks its one question, the marginal value of on-chain regime features inside the A1 gate (`docs/research/00.master-plan.md` §5, C3).

## Why this matters

Every vendor's multi-year on-chain history is restated in place and keeps no vintages, so a C3 backtest on vendor data reads values nobody could have read at the time; computing from chain data is point-in-time by construction from 2013, on public data with MIT-licensed tooling (https://raw.githubusercontent.com/bitcoinresearchkit/mono/main/docs/README.md), the only route the sourcing studies found that also allows trading. Its result decides money: C3 justifies the first paid data dollar "only if the free version shows a signal worth sharpening" (`docs/research/00.master-plan.md` §5, C3), so any Glassnode purchase waits on this topic's BTC reading.

## Findings so far

- The sourcing that chose this route — the vendors' restatements, Glassnode's `_pit` start of 2025-06-27, the per-coin coverage, the licences and the costs — is [[T0016]]'s findings bullet **C3's data sources, studied 2026-10-31 to 2026-11-11**, which also quotes the owner's decision of 2026-11-11 registering this topic.

## Suggested next steps

- Write C3's spec and plan, pre-registering every frozen choice below.
- Host and disk: Bitcoin Core plus Bitview/BRK at a pinned version, self-hosted, the spec naming the host and measuring its free disk and RAM against BRK's needs, about 290 GiB plus the node and 16 GB RAM (https://raw.githubusercontent.com/bitcoinresearchkit/mono/main/docs/README.md), and never a capture host, `zcrypto` or `zcrypto-red`, where capture stops appending below 1 GiB free. Never read hosted bitview.space values, which are reset on a format change; blocks come from our own node, and any AWS public BTC partition used instead is snapshotted and hashed ([[T0016]]'s findings).
- Valuation: each output valued at our Kraken BTC/EUR closes, the spec naming the dataset and its hash. Kraken's BTC/EUR starts 2013-09-10 (https://reference-data-api.kaiko.io/v1/instruments?exchange_code=krkn&class=spot), so outputs created before it need a price from another series; that choice is made once, in the pre-registration, and never re-made.
- Day cut and vintage: each UTC day is cut at a block height by one rule the spec freezes, and its values are written once, with the height and the run's time, as that day's vintage; a recompute writes a new vintage beside it, never over it.
- MVRV-Z's σ is expanding, each day's over data to that day only — Glassnode computes its σ "to the present day" (https://docs.glassnode.com/further-information/metric-guides/mvrv/mvrv-z-score.md), and Coin Metrics does not state its window.
- STH/LTH: the 155-day split is fixed in the pre-registration and never tuned, since vendors set it after seeing the data (inferred in the off-list search).
- Cross-check: compute a USD MVRV beside the EUR one and diff it day by day against Coin Metrics Community `CapMVRVCur` for BTC, served from 2010-07-18 (https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur&frequency=1d&page_size=2&paging_from=start) and priced at its 00:00Z `PriceUSD` (https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/market/market-capitalization.md), the spec naming the USD close ours uses; the diff checks our build and shows how far a vendor's numbers sit from a chain-exact computation. Coin Metrics Community is CC BY-NC (https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data.md), so this is research use.
- Then LTC and DOGE: the same computation, exact on UTXO chains apart from LTC's MWEB amounts, one opaque bucket since 2022 (https://github.com/litecoin-project/lips/blob/master/lip-0003.mediawiki); inputs from our own nodes or Blockchair's daily dumps (https://gz.blockchair.com/dogecoin/, licence not read), Google's supported-datasets page no longer listing crypto_dogecoin or crypto_litecoin (https://docs.cloud.google.com/blockchain-analytics/docs/supported-datasets).
- The gate: if BTC's on-chain regime adds nothing inside the A1 gate, nothing is bought for C3; if it does, [[T0016]]'s Glassnode step opens, `_pit` diff first.
