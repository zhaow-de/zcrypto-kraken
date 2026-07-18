# Full-History OHLCVT Dataset Catalog

Datasets are organized into three clusters by sync behavior and mutability (spec `00056` D1) — **custody** (the NAS keeps everything forever; read it where it lies), **hot** (the small working set every research node carries; fetch all of it, push what you authored), **private** (this machine's own state; never synced). Provenance (which team, which producer) is a per-set column within each cluster, never the structuring principle.

## hot

The `~140 MB` stable working set every research node needs local at start. Append-only at file level (hash-stable-at-file, additive-at-set): any revision mints a **sibling** (a new dir or dated file), never an overwrite, so the registry's file-level pins stay valid forever (spec `00056` D1c). The `zcrypto data` command group is the standard exchange for this cluster: `fetch` mirrors the NAS `hot/` into `data/` (additive, idempotent, verify-manifests-after), `push` transmits a node's authored-set allowlist back to `hot/`, `rebuild` re-freezes/refreshes a named set from the existing library code, minting a new sibling rather than touching the live dir (spec `00056` D2/D3).

### `ohlc-full`

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

#### QA (coverage / gaps over the reconstructed grid)

- Series: 36  ·  total gaps: 7807  ·  min coverage: 90.5465623863223

#### Reconciliation vs v0 REST

- See `docs/research/02.phase1-ohlcvt-backfill-reconciliation.md` — 36 overlapping series, min OHLC match rate 1.0000 over 9120 overlap rows.

### `ohlc-15m`

12 pairs, full dump history (BTC from 2013-09) at 15-minute cadence, ~3.12M bars, derived from the 1-minute OHLCVT dumps via `cli/backfill/substrate15m.py` (iter-085, spec/plan `00044`). Dataset root `data/ohlc-15m/`; `basket_sha256` `0fed24a6…`. Tick-reconciled bit-exact against Q1-2026 windows across all 12 pairs (100,759 comparisons); the 15m→1h seam is bit-identical on prices, ≤1 ULP on volume, zero Int64 count-leg mismatches over 25,909 hours. Consumer: the B1 seasonality-conditioning family, trials 45–46 ([[T0022]]).

### `derivatives-funding`

10 USDT-M perpetuals' full realized-funding history from Binance Vision monthly `fundingRate` dumps, checksum-verified per file, via `cli/derivatives/funding.py` (iter-090, spec/plan `00047`). Dataset root `data/derivatives-funding/`; `basket_sha256` `e08ea1a9…`. 68,281 funding prints; balanced-panel start 2020-09-22 (AVAX); zero cadence gaps except SOL's 2022-11-09→18 window of 4h→2h funding (a real venue action around the FTX collapse, preserved via `interval_hours`). Staged for the B2 derivatives-positioning family ([[T0023]]) — this substrate is funding-only; OI and liquidations are separate.

### `ohlc-holdout-2026-07-10`

The pre-registered out-of-time holdout pull: 100 bars/pair, 2026-04-01 → 2026-07-09 (621 overlap bars/pair verified exact against the canonical `ohlc-full`). Dataset root `data/ohlc-holdout-2026-07-10/`; manifest sha256 `4e251df2…`. The holdout look budget is spent (1 → 0, executed 2026-07-10); see `docs/research/13.phase5-holdout-ledger.md` for the full ledger and the (degenerate) result.

### `snapshots` + `universe`

**`snapshots`** — venue point-in-time reference snapshots (`AssetPairs`/`Assets`: margin/leverage, order minimums, symbol aliases) from `cli/snapshot/`, each content-hashed. Dataset root `data/snapshots/`; see `docs/research/01.1.kraken-snapshot-register.md` for the live register and provenance.
**`universe`** — the derived mechanical universe selection (`cli/universe/`), built from a snapshot plus the OHLC basket's median volume. Dataset root `data/universe/`; see `docs/universe/point-in-time-universe.md` for the current point-in-time selection.

## custody

The NAS (`/volume1/ZhaoCrypto`) keeps everything forever; both research nodes read it in place (workstation `../zcrypto-kraken-data`, ops `/mnt/zhao-crypto`) rather than fetching a local copy — the `ohlcvt_source_dir` config is the standing precedent. Append-only per each producer's own contract; accruing caches are final-once-written under their settle discipline, tree-regenerable on a generation bump. No fetch-cache of accruing sets (owner: YAGNI) and no change from the new `zcrypto data` tool, which never transmits this cluster (spec `00056` D1a).

### Source dumps

- `kraken-ohlcvt-updates` (13G) — Kraken's downloadable OHLCVT ZIP archive (base + quarterly), the source `ohlc-full` reconstructs from.
- `kraken-trades` (15G) — Kraken's downloadable trades dumps, read in place by the trade-backfill tooling.

### Canonical trades — healed (`capture-reconciled/…/trades/`, since 2026-07-08; daily)

- **Read it reconciled-first, never the raw mirror alone.** `canonical_segments(primary_root, reconciled_root, kind="trades")` yields the healed view; a bare glob over `capture-segments/` returns the **un-healed** stream and, for pre-2026-07-16 hours, silently double-counts (10,986 duplicate `trade_id`s existed archive-wide before this pass).
- **Producer:** `zcrypto archive reconcile` + `zcrypto archive backfill-trades`, run on the **ops node** (spec `00054`, OPS-5 offload, iter-100/101), reading the canonical trees through the NAS's read-only NFS export (T0058); the NAS **pulls** the overlay back — it never receives a push, the same pull-only grain as the `PANEL_*` channels. Detects `trade_id` gaps + duplicates from the archive itself, fetches only the missing ids from Kraken's public REST `/Trades`, unions via `union_trades` (dedupe on `trade_id`, keep-first, **primary priority**), mints whole hours atomically with `<HH>.provenance.json` (`tool: zcrypto archive backfill-trades`, `recovered_id_ranges`).
- **The invariant, and why it is the check:** per pair, canonical `trade_id` is **contiguous and unique** across the captured span. Kraken's `trade_id` is dense per pair, so a hole IS missing data. **Do not trust the `.sha256`**: a minted hour's manifest is *regenerated*, so it verifies while being wrong (this is exactly how the T0026 trade overwrite stayed invisible). Re-run `--detect-only` to check the invariant; it is the only honest test.
- **State (2026-07-16):** `gaps=0 missing=0 duplicates=0` across all 10 pairs; 17,362 trades recovered, 10,986 duplicates collapsed, 391 hours minted, raw mirrors byte-identical.
- **Caveat for consumers:** a **recovered** row's `ts` comes from REST and sits ~+1 µs from what the WS would have recorded (venue offset; float64 ULP at this epoch is 0.238 µs, so no rounding closes it — spec `00053` D6a). Rows present in both keep their WS `ts` (dedupe is `trade_id`-keyed with primary priority). Irrelevant at any research horizon here, but do not treat trade `ts` as sub-microsecond truth. Provenance names which ids came from REST.

### L2 primitive panel (`l2-panel/`, since 2026-07-08 capture start; accruing hourly)

- **Producer:** `zcrypto panel materialize` (spec `00052`, iter-098) over the canonical (reconciled-first) depth-100 book capture; hourly ops-node timer, per-pair watermarks + `<HH>.state.json` carry (state threads across update-opening hours — ~96% of hours; decision `[iter-098]` + its correction).
- **Grid/schema:** 1-second state samples, ~20 Float64 columns per row: `spread, spread_bps, mid, microprice, imbalance_l1, fill_bps_{bid,ask}_{100,1k,10k} (effective-spread-at-size, EUR notionals, null when the visible book is too shallow), depth_qty_{bid,ask}_{l1,l5,l10}, updates`. Generation params pinned in `l2-panel/panel-meta.json` (schema_version 1, grid 1s); a generation change regenerates the whole tree (`f(raw)`, recomputable).
- **Layout:** `l2-panel/<BASE>/<QUOTE>/panel-1s/<YYYY>/<MM>/<DD>/<HH>.parquet` + `.sha256` (+ `.state.json`). First-look sanity (2026-07-15, 1,740 hours): median `spread_bps` BTC 0.18 · ETH 0.83 · SOL 1.48 · XRP 1.36 · LTC 2.60 · DOGE 2.97 · LINK 3.00 · AVAX 3.40 · ADA 3.73 · DOT 5.33.
- **Consumers:** [[T0014]] spread calibration (ripe ≈2026-07-22), [[T0024]] universe spread-cap, future microstructure features (`cli/features/` derivations, hot→hot). Caveats: honest gaps (an archive gap or pre-first-snapshot hour has no rows); no CRC re-attestation (T0045 owns that).

### Binance liquidations, 1-minute buckets (`liquidations/`, since ≈2026-07-14T12Z; accruing per 5-min poll)

- **Producer:** `zcrypto liquidations-poll` (spec 00051 OPS-2 / plan Task 10, the T0023 Coinalyze fallback — Binance geo-fences its futures WS from every egress we own). Coinalyze `/v1/liquidation-history`, `interval=1min`, `convert_to_usd=true`, the 10 Binance USDT perps (`<COIN>USDT_PERP.A`), closed-bucket discipline (`t+60 ≤ now−120`).
- **Schema:** `ts, symbol, long_usd, short_usd, event_id` per bucket; **zero-liquidation minutes have no bucket** (sparse by source design). Layout `liquidations/<COIN>/liquidations-1m/<YYYY>/…/<HH>.parquet` + manifests; sparse hours finalize at a 31 h wall-clock lag (T0046).
- **Hard caveat:** the stream is a **lower-bound proxy, not the tape** (Binance's own feed has been lossy since 2021), and Coinalyze retains only ~25–33 h of 1-min bars — **poller downtime beyond ~30 h is a permanent gap** (dead-man `zcrypto-liquidations` pages on silence). Consumer: the B2 derivatives-positioning family ([[T0023]]/[[T0016]]).

## private

This machine's own state; never synced by `zcrypto data` or any other channel.

- **`engine-store`** — rebuildable from the hot cluster on demand (`engine seed`); no durability requirement of its own.
- **`engine-journal`** — per-host, unreproducible (the one private-cluster member with no local backup); the VPS journal is pulled to custody by the existing Role-B channel, host-scoped.
- **scratch** — working files with no contract at all.
