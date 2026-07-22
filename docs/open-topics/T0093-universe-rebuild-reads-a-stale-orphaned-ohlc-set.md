---
status: open
ripe_when: before the pre-live universe refresh ([[T0025]]) — that refresh is the operation this breaks, and it must not run against a 3.5-month-stale volume window. Also ripe if any decision starts leaning on the committed universe's `median_quote_volume` figures as current
---

# The universe rebuild path reads a different — and stale — OHLC set than the committed artifact was built from

## Context — what

`cli/data/rebuild.py::_refresh_universe` reads quote volumes from `data/ohlc-full/`. The committed artifact `data/universe/point-in-time-universe.json` (`as_of: 2026-07-07`) records a different provenance:

- artifact provenance: `ohlc_basket_sha256 = 407d2ed8…`, `ohlc_manifest_fetched_at = 2026-07-07T04:12:55Z`, sourced from **`data/ohlc/manifest.json`** (the provenance note names that path explicitly)
- on disk today: **`data/ohlc/` does not exist**; `data/ohlc-full/manifest.json` carries `basket_sha256 = 70c2728e…`, `fetched_at = 2026-07-07T21:17:30Z`

So the artifact cites a dataset that is gone, and the rebuild path reads one the artifact was never built from.

Worse, `data/ohlc-full`'s **last daily bar is 2026-03-31**. Its trailing-30-day median window is therefore 2026-03-02…03-31 — about 3.5 months stale relative to the artifact's own `as_of`. (The 2026-03-31 → 07-08 gap is the hole [[T0065]]'s REACH round exists to close.)

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
- Unknown (not yet measured): whether `data/ohlc` was renamed to `ohlc-full`, superseded by a different builder, or lost. The two manifests' hashes differ, so they are not the same bytes under two names.

## Suggested next steps

- **(Diagnose first)** Establish what `data/ohlc/` was and why the artifact cites it — check the rebuild history and the dataset catalog. Either the artifact's provenance is wrong, or a dataset was retired without updating the artifact that depends on it; the fix differs.
- **(Precondition for [[T0025]])** Refresh `ohlc-full` through the present before any universe rebuild, so the 30-day window means the last 30 days. A refresh depends on the 2026-03-31 → present gap being closed ([[T0065]]).
- **(Guardrail)** Have `_refresh_universe` fail closed when `ohlc-full`'s last bar is older than the window it is about to compute — a silent stale-window rebuild is the failure mode that makes this expensive, and it is cheap to assert.
- **(Cheap, independent)** Record the resolved dataset path + hash in the universe provenance from the same handle the builder actually read, so the artifact cannot cite a set the code does not use.
