# Full-History OHLCVT Dataset Catalog

Reconstructed from Kraken OHLCVT 1-minute dumps (base + quarterly) at `../zcrypto-kraken-data/kraken-ohlcvt-updates`; generated 2026-07-07T21:17:30.846941+00:00 (⏱).
Cadences 1h/4h/1d reconstructed from 1-minute bars (vwap = Σ(close·vol)/Σvol, a proxy — the dumps carry no vwap).
Dataset root `data/ohlc-full/` (gitignored); `basket_sha256` `70c2728e0badf7015f6a13f6261bb4d41e58a8047afe91aacc0d0f895d0cc9cd`.

| Symbol | Interval | Rows | First | Last | sha256 |
| --- | --- | ---: | --- | --- | --- |
| ADA/EUR | 1440 | 2742 | 2018-09-28 | 2026-03-31 | `29d21a63032de104…` |
| ADA/EUR | 240 | 16446 | 2018-09-28 | 2026-03-31 | `1294fadf55dde877…` |
| ADA/EUR | 60 | 65623 | 2018-09-28 | 2026-03-31 | `30acd82aeba2867e…` |
| AVAX/EUR | 1440 | 1562 | 2021-12-21 | 2026-03-31 | `73fcc356d2c23706…` |
| AVAX/EUR | 240 | 9365 | 2021-12-21 | 2026-03-31 | `c313337bc98809b8…` |
| AVAX/EUR | 60 | 37157 | 2021-12-21 | 2026-03-31 | `dcf1f7215d192617…` |
| BTC/EUR | 1440 | 4581 | 2013-09-10 | 2026-03-31 | `ccb30b64124678e3…` |
| BTC/EUR | 240 | 27332 | 2013-09-10 | 2026-03-31 | `2a278f1a26dbc163…` |
| BTC/EUR | 60 | 108786 | 2013-09-10 | 2026-03-31 | `8bf6faa644020039…` |
| DOGE/EUR | 1440 | 2295 | 2019-12-19 | 2026-03-31 | `99ed97dbf2aae9c1…` |
| DOGE/EUR | 240 | 13710 | 2019-12-19 | 2026-03-31 | `847e7c4311c55d26…` |
| DOGE/EUR | 60 | 53237 | 2019-12-19 | 2026-03-31 | `ed818dca00b99c9f…` |
| DOT/EUR | 1440 | 2052 | 2020-08-18 | 2026-03-31 | `64a92e83d5f16ce1…` |
| DOT/EUR | 240 | 12306 | 2020-08-18 | 2026-03-31 | `cafe52dc61109588…` |
| DOT/EUR | 60 | 49181 | 2020-08-18 | 2026-03-31 | `9ebeff5d66e776c6…` |
| ETH/BTC | 1440 | 3679 | 2016-03-03 | 2026-03-31 | `c8896764c51e44c7…` |
| ETH/BTC | 240 | 22057 | 2016-03-03 | 2026-03-31 | `40fce39783e9936b…` |
| ETH/BTC | 60 | 88174 | 2016-03-03 | 2026-03-31 | `87394e32bc9a6359…` |
| ETH/EUR | 1440 | 3890 | 2015-08-07 | 2026-03-31 | `10392deb7d4e8b58…` |
| ETH/EUR | 240 | 23292 | 2015-08-07 | 2026-03-31 | `354f05522ea510a0…` |
| ETH/EUR | 60 | 92294 | 2015-08-07 | 2026-03-31 | `4d1dbfef1099c666…` |
| LINK/EUR | 1440 | 2380 | 2019-09-25 | 2026-03-31 | `38ce1d5a9a93d19f…` |
| LINK/EUR | 240 | 14267 | 2019-09-25 | 2026-03-31 | `a42253a5c326010e…` |
| LINK/EUR | 60 | 56518 | 2019-09-25 | 2026-03-31 | `96894001a4c58756…` |
| LTC/EUR | 1440 | 4542 | 2013-09-14 | 2026-03-31 | `efe3ccfbc9c01f07…` |
| LTC/EUR | 240 | 26746 | 2013-09-14 | 2026-03-31 | `41bbb9e96ea6f1a1…` |
| LTC/EUR | 60 | 99565 | 2013-09-14 | 2026-03-31 | `c834951b79fa76fc…` |
| SOL/BTC | 1440 | 1749 | 2021-06-17 | 2026-03-31 | `da651ce355d8b29b…` |
| SOL/BTC | 240 | 10487 | 2021-06-17 | 2026-03-31 | `2797c3ff329a0127…` |
| SOL/BTC | 60 | 41839 | 2021-06-17 | 2026-03-31 | `dfc1307112838226…` |
| SOL/EUR | 1440 | 1749 | 2021-06-17 | 2026-03-31 | `aaa8722b2deb62db…` |
| SOL/EUR | 240 | 10486 | 2021-06-17 | 2026-03-31 | `8cfbebc77e4d44e9…` |
| SOL/EUR | 60 | 41918 | 2021-06-17 | 2026-03-31 | `b15123e82cbd5eba…` |
| XRP/EUR | 1440 | 3239 | 2017-05-18 | 2026-03-31 | `69c9236f910dc30f…` |
| XRP/EUR | 240 | 19423 | 2017-05-18 | 2026-03-31 | `7cd898a849056dab…` |
| XRP/EUR | 60 | 77653 | 2017-05-18 | 2026-03-31 | `71cb1883a64062fd…` |

## QA (coverage / gaps over the reconstructed grid)

- Series: 36  ·  total gaps: 7807  ·  min coverage: 90.5465623863223

## Reconciliation vs v0 REST

- See `docs/research/02.phase1-ohlcvt-backfill-reconciliation.md` — 36 overlapping series, min OHLC match rate 1.0000 over 9120 overlap rows.

## Live-accruing operational datasets (ops node + NAS replica)

Unlike the frozen baskets above, these accrue continuously and are **hash-versioned at consumption**: a research iteration extracts its window and records that frame's `dataset_hash` in the trial registry (never "latest"). Primary copies live on the **ops node** (`/var/lib/zcrypto-ops/`), hash-verified replicas on the NAS (`/volume1/ZhaoCrypto/`); the workstation holds neither by default (pull on demand — and OPS-6 migrates the research loop to the ops node where these are local).

### L2 primitive panel (`l2-panel/`, since 2026-07-08 capture start; accruing hourly)

- **Producer:** `zcrypto panel materialize` (spec `00052`, iter-098) over the canonical (reconciled-first) depth-100 book capture; hourly ops-node timer, per-pair watermarks + `<HH>.state.json` carry (state threads across update-opening hours — ~96% of hours; decision `[iter-098]` + its correction).
- **Grid/schema:** 1-second state samples, ~20 Float64 columns per row: `spread, spread_bps, mid, microprice, imbalance_l1, fill_bps_{bid,ask}_{100,1k,10k} (effective-spread-at-size, EUR notionals, null when the visible book is too shallow), depth_qty_{bid,ask}_{l1,l5,l10}, updates`. Generation params pinned in `l2-panel/panel-meta.json` (schema_version 1, grid 1s); a generation change regenerates the whole tree (`f(raw)`, recomputable).
- **Layout:** `l2-panel/<BASE>/<QUOTE>/panel-1s/<YYYY>/<MM>/<DD>/<HH>.parquet` + `.sha256` (+ `.state.json`). First-look sanity (2026-07-15, 1,740 hours): median `spread_bps` BTC 0.18 · ETH 0.83 · SOL 1.48 · XRP 1.36 · LTC 2.60 · DOGE 2.97 · LINK 3.00 · AVAX 3.40 · ADA 3.73 · DOT 5.33.
- **Consumers:** [[T0014]] spread calibration (ripe ≈2026-07-22), [[T0024]] universe spread-cap, future microstructure features (`cli/features/` derivations, hot→hot). Caveats: honest gaps (an archive gap or pre-first-snapshot hour has no rows); no CRC re-attestation (T0045 owns that).

### Binance liquidations, 1-minute buckets (`liquidations/`, since ≈2026-07-14T12Z; accruing per 5-min poll)

- **Producer:** `zcrypto liquidations-poll` (spec 00051 OPS-2 / plan Task 10, the T0023 Coinalyze fallback — Binance geo-fences its futures WS from every egress we own). Coinalyze `/v1/liquidation-history`, `interval=1min`, `convert_to_usd=true`, the 10 Binance USDT perps (`<COIN>USDT_PERP.A`), closed-bucket discipline (`t+60 ≤ now−120`).
- **Schema:** `ts, symbol, long_usd, short_usd, event_id` per bucket; **zero-liquidation minutes have no bucket** (sparse by source design). Layout `liquidations/<COIN>/liquidations-1m/<YYYY>/…/<HH>.parquet` + manifests; sparse hours finalize at a 31 h wall-clock lag (T0046).
- **Hard caveat:** the stream is a **lower-bound proxy, not the tape** (Binance's own feed has been lossy since 2021), and Coinalyze retains only ~25–33 h of 1-min bars — **poller downtime beyond ~30 h is a permanent gap** (dead-man `zcrypto-liquidations` pages on silence). Consumer: the B2 derivatives-positioning family ([[T0023]]/[[T0016]]).
