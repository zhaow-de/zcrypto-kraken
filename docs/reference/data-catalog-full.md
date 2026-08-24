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

### `ohlc-reach`

**A mixed set by construction — read the manifest before treating any file as continuous.** Produced by `zcrypto data rebuild ohlc-reach` (`cli/ohlc/reach.py`, T0065), which carries the **live** `ohlc-full` forward from Kraken's public REST OHLC window rather than from a dump. It exists because the dump timetable does not fit the data's expiry: REST serves only the most recent ~720 bars per interval, so a bar not captured before the window recedes past it is unavailable until the next quarterly dump.

The window's reach depends on the interval (~720 d daily, ~120 d at 4h, ~30 d at 1h, ~7.5 d at 15m), so each series lands one of two ways, and the **filename is the contract**:

- `<interval>.parquet` — **continuous**: the REST window still overlapped the canonical tail, the seam was verified (≥ 6 shared stamps, every shared close equal), and the merged series is drop-in compatible with any `ohlc-full` reader.
- `<interval>.detached.parquet` — **detached**: the window no longer reached the canonical tail. The bars are kept (they expire) but sit under a name no `ohlc-full` reader globs, so a detached segment can never be silently spliced across the gap. Promote deliberately once an intervening dump closes it.

`manifest.json` carries **two separate basket hashes** — `basket_sha256` over the continuous series and `detached_sha256` over the detached ones, so the basket hash never absorbs a segment the round refused to join — plus a per-series row (`symbol`, `interval`, `status`, `overlap_bars`, `appended`, `gap_bars`, REST extent, and `sha256`/`rows`/`first_ts`/`last_ts` for parity with `backfill_basket`). There is never one set-wide continuity claim. A seam that *overlaps but does not hold* is a hard error, not a fallback to detached: the canonical set is authoritative, so a disagreeing close is a data-integrity failure.

Dataset root `data/ohlc-reach/` — the canonical, **unstamped** name, like every other live set. `data rebuild ohlc-reach` mints a dated sibling (`ohlc-reach-<stamp>`) which is promoted into the canonical name once verified; the path is stable and the manifest's hashes carry the identity, so a backtest pins the hash, never the path. First promoted run (identity digest `356826a172dd33ca…` over the **continuous** series, `subset_sha256["detached"]` `dc8beef0e01bfb40…` — the two are deliberately separate hashes, so the set's identity never absorbs a segment the round refused to join; per-series `sha256`/`rows`/`first_ts`/`last_ts` accompany each row, and the manifest now declares which digest identifies it rather than leaving that to a consumer's per-set knowledge, per spec `00099`). **The continuous value moved on 2026-08-24** — it was `8a826898241a5f1e…` under the old writer, which ordered by symbol then integer interval; the contract orders by the series key, i.e. the relative path, and no single recipe could reproduce both because `backfill.py` sorted the same interval keys as strings. The content did not move: the converter recomputes every series hash and refuses the whole set unless each matches what the legacy manifest attested, so the new value is provably a re-ordering of identical bytes, and the old one is preserved verbatim under `provenance.legacy`. The detached value is unchanged, its series being single-interval: 30 series, **20 continuous** (daily → 2026-07-22, 4h → 2026-07-23T12:00, closing the 2026-03-31 → 07-08 hole at both grids with zero irregular steps after the seam) and **10 detached** (every 1h series, gap ≈ 83.7 d, a standalone 720-bar segment 2026-06-23 → 2026-07-23). Consumers: the intraday families via the daily/4h tail, and the universe rebuild — wired 2026-08-11 (iter-136, spec `00093`, [[T0093]]): `_refresh_universe` resolves its source through `resolve_ohlc_source`, which reads the newest stamped `ohlc-reach-<stamp>` sibling directly and ignores this unstamped canonical name (the hub's promoted copy is frozen by the additive-only transport), falling back to `ohlc-full` only when no stamped sibling exists. A fresh reach round is therefore a precondition of each universe refresh — the per-symbol 7-day staleness budget refuses anything older, `ohlc-full` included.

### `derivatives-funding`

10 USDT-M perpetuals' full realized-funding history from Binance Vision monthly `fundingRate` dumps, checksum-verified per file, via `cli/derivatives/funding.py` (iter-090, spec/plan `00047`). Dataset root `data/derivatives-funding/`; `basket_sha256` `e08ea1a9…`. 68,281 funding prints; balanced-panel start 2020-09-22 (AVAX); zero cadence gaps except SOL's 2022-11-09→18 window of 4h→2h funding (a real venue action around the FTX collapse, preserved via `interval_hours`). Staged for the B2 derivatives-positioning family ([[T0023]]) — this substrate is funding-only; OI and liquidations are separate.

### `derivatives-oi`

10 USDT-M perpetuals' 5-minute open-interest history from Binance Vision **daily `metrics`** dumps, checksum-verified per file, via `cli/derivatives/oi.py` (the `derivatives-oi` `data rebuild` target; sibling of the funding backfill). Dataset root `data/derivatives-oi/`; `basket_sha256` `e9f7344c…`; ~189 MB, 5,010,882 rows. Columns: `ts` (5-min, aware-UTC), `sum_open_interest`, `sum_open_interest_value`, plus the four free ratios (`count_toptrader_long_short_ratio`, `sum_toptrader_long_short_ratio`, `count_long_short_ratio`, `sum_taker_long_short_vol_ratio`). Raw 5-minute cadence is stored as-is — resampling to the 1h/4h/8h decision grid is the B2 harness's job.

**Coverage — the binding constraint on a balanced B2 panel.** Only **BTCUSDT** reaches back to **2020-09-01** (618,850 rows); **every other symbol starts 2021-12-01** (~488,000 rows each) — verified against the CDN, not inferred: ETH/SOL/LTC all 404 before 2021-12-01 and 200 from it, so Binance simply began publishing metrics for the non-BTC perps on that date. A **balanced 10-name OI panel therefore starts 2021-12-01**, which is *later* than the funding panel's 2020-09-22 — **OI, not funding, bounds the balanced B2 window.** All series end 2026-07-22 (the 07-23 dump was not yet published; Binance's daily metrics lag ~1-2 days).

**Null semantics.** `sum_open_interest`/`_value` are **complete (zero nulls)**. The four ancillary ratio columns carry genuine Binance gaps — e.g. BTCUSDT has 92,226 null `count_toptrader_long_short_ratio` (~15%) — because early metrics leave them absent in two forms (bare-empty and quoted-empty `""`). Those absences parse to **null** so a missing auxiliary ratio never discards a valid OI reading; a consumer must treat the ratio columns as nullable and the OI columns as dense.

### `ohlc-holdout-2026-07-10`

The pre-registered out-of-time holdout pull: 100 bars/pair, 2026-04-01 → 2026-07-09 (621 overlap bars/pair verified exact against the canonical `ohlc-full`). Dataset root `data/ohlc-holdout-2026-07-10/`; manifest sha256 `4e251df2…`. The holdout look budget is spent (1 → 0, executed 2026-07-10); see `docs/research/13.phase5-holdout-ledger.md` for the full ledger and the (degenerate) result. **Its freeze manifest exposes no per-series hash**, so the per-series `dataset_hash` values live in `docs/reference/vouched-dataset-hashes.jsonl` instead — that file is what arms the read-time cross-check in `cli/registry/observed.py`, which is otherwise a no-op for this set ([[T0133]]).

### `snapshots` + `universe`

**`snapshots`** — venue point-in-time reference snapshots (`AssetPairs`/`Assets`: margin/leverage, order minimums, symbol aliases) from `cli/snapshot/`, each content-hashed. Dataset root `data/snapshots/`; see `docs/reference/kraken-snapshot-register.md` for the live register and provenance.
**`universe`** — the derived mechanical universe selection (`cli/universe/`), built from a snapshot plus the OHLC basket's median volume. Dataset root `data/universe/`; see `docs/universe/point-in-time-universe.md` for the current point-in-time selection.

## custody

The NAS (`/volume1/ZhaoCrypto`) keeps everything forever; both research nodes read it in place over their aligned `nfs_mount_dir` mount (`/mnt/zhao-crypto`) rather than fetching a local copy — the read-in-place OHLCVT-dumps path (now derived from `nfs_mount_dir`) is the standing precedent. Append-only per each producer's own contract; accruing caches are final-once-written under their settle discipline, tree-regenerable on a generation bump. No fetch-cache of accruing sets (owner: YAGNI) and no change from the new `zcrypto data` tool, which never transmits this cluster (spec `00056` D1a).

Unlike the frozen `hot` baskets (pinned at the file level), the accruing operational members below are **hash-versioned at consumption**: a research iteration extracts its window and records that frame's `dataset_hash` in the trial registry (never "latest").

**How the registry references a dataset, since schema 4 (spec `00086`, 2026-08-09):** a record carries a `datasets` block of the per-file sha256 of the bytes the run actually read, plus the rows and span it returned; `dataset_hash` is **derived** from that block by the registry itself and cannot be supplied by a caller. Records are written through `zcrypto research eval --register`, which computes the block as it loads. Pre-schema-4 hashes are explained by `docs/reference/legacy-dataset-pins.jsonl`, which marks each one reproduced / inferred / unrecoverable **in the referent value itself** — two of the four are accepted as permanently unverifiable. Spec `00035`'s "`dataset_hash` == record 1's input else STOP" gate is **superseded** by that derivation: its home is immutable (its sha256 is pinned as a `spec_hash` on committed records), so the supersession is stated here rather than edited there.

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
- **Grid/schema:** 1-second state samples, ~20 Float64 columns per row: `spread, spread_bps, mid, microprice, imbalance_l1, fill_bps_{bid,ask}_{100,1k,10k} (effective-spread-at-size, EUR notionals, null when the visible book is too shallow), depth_qty_{bid,ask}_{l1,l5,l10}, updates, stale_seconds`. Generation params pinned in `l2-panel/panel-meta.json` (**schema_version 2**, grid 1s); a generation change regenerates the whole tree (`f(raw)`, recomputable). **`stale_seconds` (T0104) is seconds since the last message applied to the book — the column that distinguishes a genuinely quiet second from an archive hole, which `updates == 0` alone cannot: a hole emits a carried-forward FROZEN book. Filter `stale_seconds > 30` to drop fabricated rows; null means unknown (no message yet, or a pre-T0104 state sidecar) and polars drops nulls from BOTH sides of such a filter, so handle them explicitly.**
- **Scope: every quote with a notional ladder** (`NOTIONALS_BY_QUOTE`, `cli/panel/primitives.py`) — today `EUR` and `BTC`, i.e. all twelve universe legs. The `fill_bps_*` ladder walks `price × qty` in the pair's QUOTE currency, so the rungs are **per-quote**: EUR pairs use 100/1k/10k EUR, and BTC-quoted pairs use the BTC quantities worth those EUR amounts at a pinned FX reference (`BTC_EUR_REFERENCE = 55876.28413495087`). Column names are unchanged and the labels stay EUR, so `fill_bps_bid_1k` names the same grid point on every pair and the values stay comparable across quotes. **The FX reference is pinned to its own fixed window and must never be moved to match a recalibration** — it defines what every BTC `fill_bps_*` column already in the tree means, and changing it makes `_check_generation` refuse the whole tree at the next sweep. Before spec `00085` the panel was EUR-only and both `/BTC` legs carried six null columns; the 2026-08-07 regeneration built them for real (7,836 hours, `hours_unanchored=0`), and a ladder change rewrites identical paths, so nothing was orphaned.
- **Layout:** `l2-panel/<BASE>/<QUOTE>/panel-1s/<YYYY>/<MM>/<DD>/<HH>.parquet` + `.sha256` (+ `.state.json`). First-look sanity (2026-07-15, 1,740 hours): median `spread_bps` BTC 0.18 · ETH 0.83 · SOL 1.48 · XRP 1.36 · LTC 2.60 · DOGE 2.97 · LINK 3.00 · AVAX 3.40 · ADA 3.73 · DOT 5.33.
- **Consumers:** [[T0014]] spread calibration — **delivered 2026-07-22** (spec `00066`; `cli/costs/spread.py` + [`captured-spread-calibration.md`](captured-spread-calibration.md), calibrated over 315 hours × 10 pairs of this set); [[T0024]] universe spread-cap; future microstructure features (`cli/features/` derivations, hot→hot). Caveats: honest gaps (an archive gap or pre-first-snapshot hour has no rows); no CRC re-attestation (T0045 owns that). **Reading caveat learned in the T0014 pass:** the *median* `spread_bps` is unstable for tick-quantised pairs — BTC/EUR sits at exactly one tick 42–58 % of the time, so its median swings ~15× on a small change in that share (mean ÷ median 11.2×, against 0.9–1.3× elsewhere). Cite the mean, or `fill_bps` (effective spread at size), never the median top-of-book for BTC.

### Tape-bars — 15m OHLCV from the captured trade tape (`tape-bars/`, since 2026-07-08; daily finals)

- **Why it exists:** below 4h nothing else reaches the present. REST's OHLC window *recedes* (~30 d at 1h, ~7.5 d at 15m — the 2026-07-23 reach round proved it: 1h came back detached at a 83.7-day gap, 15m could not reach at all) and the OHLCVT dumps are quarterly. The captured tape *accrues*, so it is the only fine-cadence source whose reach does not expire.
- **Producer:** `zcrypto tick materialize <primary-root> <out-root> --reconciled-root <overlay>` (spec/plan `00087`), on an hourly ops timer at `*:52`. Reads the healed archive **reconciled-first** via `canonical_segments(..., kind="trades")` — never a bare glob, which would return the un-healed stream and double-count pre-2026-07-16 hours.
- **Layout:** `<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` + a `.sha256` sidecar per final; 96 rows for a fully-traded day. Columns are `ticks_to_bars`' own order `[ts, open, high, low, close, volume, count, vwap]` — the same *set* as `ohlc-full`'s but a different *order*, so any union selects by name, never by position. **No set-level manifest**, deliberately: provenance for a trial comes from `ObservedReader` hashing the bytes it reads (spec `00086`), and a sixth manifest writer would grow the zoo [[T0132]] tracks for no consumer.
- **Grid:** 15m base only. 60/240/1440 are *derived on demand* via `derive_bars`, never materialized — 15m divides all three evenly, and the derivation is exact because `ticks_to_bars` computes a true tick-weighted vwap, so `Σ(vwapᵢ·volᵢ)/Σ(volᵢ)` re-derives it. A plain mean of sub-bar vwaps is the tempting form and is wrong on non-uniform volume.
- **Publish gate — measured, not clocked.** A day is published only once `cli/trades/gaps.py::detect` proves its `trade_id` sequence contiguous and duplicate-free, reading the day **plus the nearest present segment each side** (detect treats first/last observed ids as endpoints, so a one-day span is blind to a boundary hole). `TAPE_SETTLE = 26 h` past day end survives only as a cheap pre-filter. An absent hour means **quiet**, not missing: the capture writer commits no final for an hour with no events, and zero-print trades hours are production-measured.
- **Caveats:** final-once-written, **no rewrite path** — a day is published once and never re-derived. A day whose tape carries an unrecoverable hole is refused indefinitely (`days_unhealed`), and once the re-scan window passes it, reported forever as `days_gap`, which is the only durable signal of a permanent hole. Coverage starts **2026-07-08**, the tape's own start; earlier fine-grain history has no source but the Q2/Q3 dumps. Currently **ops-host only** — it is fully derived, and its source archive is NAS custody kept forever, so a lost copy costs a re-materialization, not data.
- **Consumers:** none yet — built for the next intraday/microstructure family and for a future canonical re-freeze's live tail.

### Binance liquidations, 1-minute buckets (`liquidations/`, since ≈2026-07-14T12Z; accruing per 5-min poll)

- **Producer:** `zcrypto liquidations-poll` (spec 00051 OPS-2 / plan Task 10, the T0023 Coinalyze fallback — Binance geo-fences its futures WS from every egress we own). Coinalyze `/v1/liquidation-history`, `interval=1min`, `convert_to_usd=true`, the 10 Binance USDT perps (`<COIN>USDT_PERP.A`), closed-bucket discipline (`t+60 ≤ now−120`).
- **Schema:** `ts, symbol, long_usd, short_usd, event_id` per bucket; **zero-liquidation minutes have no bucket** (sparse by source design). Layout `liquidations/<COIN>/liquidations-1m/<YYYY>/…/<HH>.parquet` + manifests; sparse hours finalize at a 31 h wall-clock lag (T0046).
- **Hard caveat:** the stream is a **lower-bound proxy, not the tape** (Binance's own feed has been lossy since 2021), and Coinalyze retains only ~25–33 h of 1-min bars — **poller downtime beyond ~30 h is a permanent gap** (dead-man `zcrypto-liquidations` pages on silence). Consumer: the B2 derivatives-positioning family ([[T0023]]/[[T0016]]).

## private

This machine's own state; never synced by `zcrypto data` or any other channel.

- **`engine-store`** — rebuildable from the hot cluster on demand (`engine seed`); no durability requirement of its own. **Rebuildable is not identical, and two legs are not canonical-backed**: `engine seed` reads canonical only where a store file is absent, and `data/ohlc-full` is frozen at its last quarterly dump (2026-03-31) while Kraken's REST 4h window reaches back only to ~2026-04-17. The two `/BTC` legs' **4h** grids were therefore seeded **REST-only** at the twelve-leg widening — 720 bars from 2026-04-17, no canonical tail behind them — while every `/EUR` leg and both `/BTC` **daily** grids are canonical-backed (REST reaches 2024-08-25 on the daily grid). Harmless to the model today because `select_model_inputs` contracts to the ten `/EUR` legs, so no `/BTC` datum reaches it — but a loop that starts consuming a `/BTC` series must not assume history before 2026-04-17 exists, and a re-seed reproduces the same hole until the quarterly dump is republished. `engine seed` is **workstation-only** — the image carries no canonical dataset, so a host cannot rebuild this itself.
- **`engine-journal`** — per-host, unreproducible (the one private-cluster member with no local backup); the VPS journal is pulled to custody by the existing Role-B channel, host-scoped.
- **scratch** — working files with no contract at all.
