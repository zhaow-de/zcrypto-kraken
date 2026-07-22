---
status: partial
ripe_when: before the pre-live universe refresh ([[T0025]]) — that refresh is the operation this breaks. The silent-shrink path is now closed by a fail-closed guard (landed 2026-07-22), so the remainder is the DATA gap: ripe when [[T0065]]'s REACH round ingests the Q2/Q3 dumps and `ohlc-full` reaches the present. Also ripe if any decision starts leaning on the committed universe's `median_quote_volume` figures as current
---

# The universe rebuild computes its volume floor over a months-stale window

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
- **Guard landed 2026-07-22**: `_refresh_universe` now fails closed when the OHLC set's newest daily bar is more than `UNIVERSE_MAX_OHLC_STALENESS_DAYS` (7) before the rebuild stamp. Verified against the live set: it raises with *"newest daily bar is 2026-03-31, 113 days before the rebuild stamp 2026-07-22"*. The silent-shrink path is closed; the underlying data gap is not.

## Suggested next steps

- **(The remaining blocker — precondition for [[T0025]])** Ingest the Q2/Q3 OHLCVT dumps so `ohlc-full` reaches the present ([[T0065]]'s REACH round, already ripe and autonomous). Until then the guard makes a universe rebuild **fail** rather than silently shrink — correct, but it means T0025's refresh is blocked on REACH, which was not previously stated as a dependency between them.
- **(Cheap, independent)** Decide whether a universe rebuild should read a *live* REST pull for volumes rather than the dump-derived set, as the 2026-07-07 build effectively did. That would decouple selection from the dump cadence entirely; it also reintroduces a network dependency in the rebuild path, so it is a real trade rather than an obvious fix.
- **(Cheap, independent)** Record the resolved dataset path + hash in the universe provenance from the same handle the builder actually read, so the artifact cannot cite a set the code does not use.
