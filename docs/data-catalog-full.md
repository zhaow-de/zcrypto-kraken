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

- See `docs/ohlcvt-backfill-reconciliation.md` — 36 overlapping series, min OHLC match rate 1.0000 over 9120 overlap rows.
