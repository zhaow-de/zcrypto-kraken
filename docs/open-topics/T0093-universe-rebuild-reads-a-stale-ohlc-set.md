---
status: partial
ripe_when: before the pre-live universe refresh ([[T0025]]) — that refresh is the operation this breaks. The silent-shrink path is closed by a fail-closed guard (landed 2026-07-22); the remainder is the DATA gap, and it is NOT dischargeable by ingesting dumps — the OHLCVT dumps are quarterly, so even a freshly-ingested just-closed quarter leaves the frontier weeks stale and the guard still fires. Ripe when a LIVE-TAILED volume source exists for the rebuild: either [[T0065]]'s live-trades→bars materializer or a REST volume pull in the rebuild path. Also ripe if any decision starts leaning on the committed universe's `median_quote_volume` figures as current
---

# The universe rebuild reads an OHLC set that stops months short, so its volume floor measures the past

## Context — what

`cli/data/rebuild.py::_refresh_universe` reads quote volumes from `data/ohlc-full/`. The committed artifact `data/universe/point-in-time-universe.json` (`as_of: 2026-07-07`) records a different provenance:

- artifact provenance: `ohlc_basket_sha256 = 407d2ed8…`, `ohlc_manifest_fetched_at = 2026-07-07T04:12:55Z`, sourced from **`data/ohlc/manifest.json`** (the provenance note names that path explicitly)
- on disk today: **`data/ohlc/` does not exist**; `data/ohlc-full/manifest.json` carries `basket_sha256 = 70c2728e…`, `fetched_at = 2026-07-07T21:17:30Z`

**Corrected 2026-07-22, after registering this topic on an unverified reading.** The missing directory is *not* an orphan or a loss, and this topic originally implied it was. `data/ohlc` was **deliberately retired** on 2026-07-18 (iter-103, spec `00056` D4) and the retirement is documented in `docs/reference/data-catalog.md`: *"the on-disk `data/ohlc` set was deleted. It is the v0 REST seed, fully superseded by `ohlc-full` … so it carried no unique data."* The dangling hash in the artifact's provenance is a stale pointer left by that retirement, nothing more.

**The real defect is that the supersession is incomplete in one direction, and the direction matters here.** `ohlc-full` is reconstructed from the Kraken OHLCVT dumps and stops where they stop — **every symbol's last daily bar is 2026-03-31** (`data-catalog-full.md`'s own table). The retired v0 set was pulled from the REST API and was live through its 2026-07-07 fetch. So "bit-identical supersession" holds on the **overlap**, but `ohlc-full` does not cover 2026-04-01 → present at all; that is precisely the hole [[T0065]]'s REACH round exists to close (Q2/Q3 dumps un-ingested).

For most consumers that is fine — the deployable strategy is backtested on history. For a **trailing-30-day median** it is fatal: the window silently becomes 2026-03-02…03-31, and the criterion answers "was this liquid four months ago?" while claiming to answer "can we trade this now?".

**And the swap happened in a single iteration, unnoticed.** `cli/data/rebuild.py` — which introduced `_refresh_universe`, reading `ohlc-full` — was added **2026-07-18**, the same iteration (spec `00056` D3) that deleted `data/ohlc`. The universe artifact predates both: it was built 2026-07-07 by the earlier path, from the then-live v0 REST set. Nobody noticed the recency regression because the new path had never been run.

## Why this matters

A rebuild today does not reproduce the committed universe, and the difference crosses a selection boundary:

| symbol | committed `median_quote_volume` | recomputed from `data/ohlc-full` | floor 150,000 |
|---|---|---|---|
| AVAX/EUR | 272,540.96 | **132,274.82** | **fails** |
| DOT/EUR | 182,168.24 | 277,602.49 | passes |
| ADA/EUR | 1,299,998.00 | 864,628.44 | passes |
| ETH/BTC | 579,963.79 | 1,079,523.50 | passes |

**A rebuild run today selects eleven names, not twelve** — it drops AVAX/EUR on volume. `escalate` stays `false` (11 ≥ `MIN_NAMES` 8), so nothing would flag it: the universe would silently shrink, and the drop would be attributed to liquidity when its actual cause is a stale window on an orphaned dataset.

Every recomputed figure differs from the committed one, in both directions, so this is not one bad symbol — the two sets simply are not the same data. [[T0025]]'s pre-live universe refresh is exactly the operation that would run this path.

## Findings so far

- Measured 2026-07-22 by running `_refresh_universe`'s own volume path (`quote_volume_in_eur` over `data/ohlc-full/<BASE>/<QUOTE>/1440.parquet`, BTC/EUR as the FX leg) against all twelve committed entries — the table above.
- `data/ohlc/` absent; `data/ohlc-full/` present with 4,581 BTC/EUR daily bars ending 2026-03-31.
- Not a defect of [[T0024]]'s spread cap: the cap is applied *after* the volume filter and does not reject AVAX (AVAX = 3.33 bps/side, well inside the 10 bps cap). The spec `00067` "12 → 12" result is a replay of the committed entries and is correct **as scoped**; it says nothing about a rebuild.
- Resolved: `data/ohlc` was deliberately deleted (iter-103, spec `00056` D4), documented in `data-catalog.md`. The manifests differ because they are different datasets — a REST seed vs a dump reconstruction — not the same bytes under two names.
- **The recency gap was not overlooked — it was assessed and misjudged.** `docs/universe/point-in-time-universe.md` carried, from 2026-07-11 until this topic corrected it, a bullet declaring the question *"resolved / dropped"* because *"the volume signal uses a 30-day median window whose recent data is identical in the REST and full-history datasets"*. The two windows share zero rows. That sentence is why nothing re-ran the build.
- **"Bit-identical" was measured on PRICES, not on what this criterion reads.** `02.phase1-ohlcvt-backfill-reconciliation.md` reports `OHLC match rate 1.0000` but `Volume rel diff max` up to **0.068363** (ETH/EUR/1440). The floor computes `volume × vwap`, so even inside the overlap the two sets disagree by up to ~7 % on the worst daily bar — the stale window is the dominant term in the 12→11 change, but not the only one.
- **Guard landed 2026-07-22**: `_refresh_universe` now fails closed when the OHLC set's newest daily bar is more than `UNIVERSE_MAX_OHLC_STALENESS_DAYS` (7) before the rebuild stamp. Verified against the live set: it raises with *"newest daily bar is 2026-03-31, 113 days before the rebuild stamp 2026-07-22"*. The silent-shrink path is closed; the underlying data gap is not.

## Done so far

**Guard landed 2026-07-22** (branch `fix/t0093-universe-rebuild-stale-ohlc-guard`). `_refresh_universe` now refuses to build when any symbol's newest daily bar is more than `UNIVERSE_MAX_OHLC_STALENESS_DAYS` (7) before the rebuild stamp, checked **per symbol** on the stalest rather than on the basket's newest bar — one fresh symbol must not vouch for stale ones. Verified against the live set, not only fixtures: it raises *"BTC/EUR's newest daily bar is 2026-03-31, 113 days before the rebuild stamp 2026-07-22"*. The freshness check runs **before** the medians, so a set that is both stale and short reports the staleness rather than a row count.

Also corrected in the same change: `docs/universe/point-in-time-universe.md`'s "Full-history volume — resolved / dropped" bullet, which had declared this very question closed on a false premise since 2026-07-11.

**This closes the silent-shrink path, not the data gap** — a rebuild now fails loudly instead of quietly selecting eleven. The gap itself is the remainder below.

## Suggested next steps

- **(The remaining blocker — and dump ingestion does NOT discharge it)** The OHLCVT dumps are **quarterly** (`Kraken_OHLCVT_Q<N>_<YYYY>.zip`; newest on the NAS is Q1 2026, with Q2 still absent 22 days after the quarter closed). A dump-derived frontier is therefore always a quarter boundary: ingesting Q2 today gives 2026-06-30, still 22 days stale against a 7-day budget, so the guard fires anyway. **A universe rebuild needs a live-tailed volume source, not a fresher dump.**
- **(The real options, one of which T0025 must pick)** (a) a REST volume pull in the rebuild path, which is what the 2026-07-07 build effectively did — decouples selection from the dump cadence, but reintroduces a network dependency; (b) [[T0065]]'s live-trades→bars materializer, which per [[T0092]] feeds **EUR pairs only**, so the two BTC-quoted legs would still need a source; (c) widen the staleness budget, which is the option that quietly reintroduces the defect and is recorded here to be rejected explicitly rather than drifted into.
- **(Cheap, independent)** Record the resolved dataset path + hash in the universe provenance from the same handle the builder actually read, so the artifact cannot cite a set the code does not use.
