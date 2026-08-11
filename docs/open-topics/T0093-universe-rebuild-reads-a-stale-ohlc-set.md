---
status: partial
ripe_when: **the data half is DISCHARGED as of 2026-07-23** — `zcrypto data rebuild ohlc-reach` (T0065) mints a live-tailed daily series whose stalest bar is **1 day old** against the 7-day budget, where `data/ohlc-full` sits at 114 days and correctly fails closed. What remains is the WIRING decision, and it is deliberately not autonomous: pointing `_refresh_universe` at the reach set changes which dataset defines the tradeable universe, so it belongs to [[T0025]]'s pre-live refresh with the owner present. Also ripe if any decision starts leaning on the committed universe's `median_quote_volume` figures as current
---

# The universe rebuild reads an OHLC set that stops months short, so its volume floor measures the past

## Context — what

`cli/data/rebuild.py::_refresh_universe` computes the universe's volume floor — a **trailing 30-day median** — from `data/ohlc-full/`. That dataset is reconstructed from the Kraken OHLCVT dumps and stops where they stop: **every symbol's last daily bar is 2026-03-31** (`data-catalog-full.md`'s own table). So the "last 30 days" silently becomes **2026-03-02…03-31**, and the criterion answers *"was this liquid four months ago?"* while claiming to answer *"can we trade this at our size now?"*.

For most consumers the dump extent is fine — the deployable strategy is backtested on history. For a recency-dependent criterion it is not.

**The committed artifact was built from a different, live source.** `data/universe/point-in-time-universe.json` (`as_of: 2026-07-07`) cites `ohlc_basket_sha256 = 407d2ed8…` from **`data/ohlc/`**, the v0 REST seed, which was pulled from the API and current through its 2026-07-07 fetch. `data/ohlc-full/` carries a different hash (`70c2728e…`) because it is a different dataset, not the same bytes under another name.

**`data/ohlc/` is gone, and that was deliberate — not a loss.** It was retired 2026-07-18 (iter-103, spec `00056` D4), documented in `docs/reference/data-catalog.md`: *"the on-disk `data/ohlc` set was deleted. It is the v0 REST seed, fully superseded by `ohlc-full` … so it carried no unique data."* The dangling hash in the artifact's provenance is a stale pointer left by that retirement.

**The defect is that the supersession is incomplete in the one direction this criterion depends on.** It was verified bit-identical on **prices over the overlap** — `02.phase1-ohlcvt-backfill-reconciliation.md` reports `OHLC match rate 1.0000`, but `Volume rel diff max` up to **0.068363** (ETH/EUR/1440), and the floor computes `volume × vwap`. And `ohlc-full` does not cover 2026-04-01 → present **at all**, while the set it replaced did.

**The swap shipped in one iteration.** `cli/data/rebuild.py`, which introduced `_refresh_universe` reading `ohlc-full`, was added **2026-07-18** — the same iteration that deleted `data/ohlc`. The artifact predates both.

**It was not overlooked; it was assessed and misjudged.** From 2026-07-11 until this topic corrected it, `docs/universe/point-in-time-universe.md` declared the question *"resolved / dropped"* on the premise that *"the volume signal uses a 30-day median window whose recent data is identical in the REST and full-history datasets, so the selection is unchanged"*. Both halves are false — the windows (2026-06-08…07-07 vs ending 2026-03-31) share **zero** rows, and the selection is 12 → 11. That sentence is why nothing re-ran the build, and it was already false when written.

## Why this matters

Absent the guard, a rebuild does not reproduce the committed universe, and the difference crosses a selection boundary:

| symbol | committed `median_quote_volume` | recomputed from `data/ohlc-full` | floor 150,000 |
|---|---|---|---|
| AVAX/EUR | 272,540.96 | **132,274.82** | **fails** |
| DOT/EUR | 182,168.24 | 277,602.49 | passes |
| ADA/EUR | 1,299,998.00 | 864,628.44 | passes |
| ETH/BTC | 579,963.79 | 1,079,523.50 | passes |

**Absent the guard, a rebuild would select eleven names, not twelve** — dropping AVAX/EUR on volume. `escalate` stays `false` (11 ≥ `MIN_NAMES` 8), so nothing flags it: the universe would silently shrink, and the drop would read as a liquidity move when its actual cause is a months-stale window.

Every recomputed figure differs from the committed one, in both directions. [[T0025]]'s pre-live universe refresh is exactly the operation that runs this path.

## Findings so far

- Measured 2026-07-22 by running `_refresh_universe`'s own volume path (`quote_volume_in_eur` over `data/ohlc-full/<BASE>/<QUOTE>/1440.parquet`, BTC/EUR as the FX leg) against all twelve committed entries — the table above. `data/ohlc-full/` holds 4,581 BTC/EUR daily bars ending 2026-03-31.
- Daily-bar gaps measured across all 12 pairs: only LTC/EUR has ever exceeded 7 days (twice, both in 2013); over the last 365 bars every symbol's max gap is 1 day. So the guard's per-symbol strictness has an empirically zero false-positive rate on listed universe candidates.
- Not a defect of [[T0024]]'s spread cap: the cap is applied *after* the volume filter and does not reject AVAX (AVAX = 3.33 bps/side, well inside the 10 bps cap). The spec `00067` "12 → 12" result is a replay of the committed entries and is correct **as scoped**; it says nothing about a rebuild.

## Done so far

**Guard landed 2026-07-22** (branch `fix/t0093-universe-rebuild-stale-ohlc-guard`). `_refresh_universe` now refuses to build when any symbol's newest daily bar is more than `UNIVERSE_MAX_OHLC_STALENESS_DAYS` (7) before the rebuild stamp, checked **per symbol** on the stalest rather than on the basket's newest bar — one fresh symbol must not vouch for stale ones. Verified against the live set, not only fixtures: it raises *"BTC/EUR's newest daily bar is 2026-03-31, 113 days before the rebuild stamp 2026-07-22"*. The freshness check runs **before** the medians, so a set that is both stale and short reports the staleness rather than a row count.

Also corrected in the same change: `docs/universe/point-in-time-universe.md`'s "Full-history volume — resolved / dropped" bullet, which had declared this very question closed on a false premise since 2026-07-11.

Provenance hardened 2026-07-22/23 in the same spirit (completed by [[T0094]]): the artifact now records `ohlc_dataset_dir` and `ohlc_stalest_daily_bar`, and a set that cannot produce a resolvable hash is refused outright rather than published with an empty one — so a future reader can see which set a build read and where its trailing window ended, instead of inferring it from a bare hash that may no longer resolve. The remaining hole — an empty `ohlc_dataset_hash` when the manifest is missing — is [[T0094]].

**This closes the silent-shrink path, not the data gap** — a rebuild now fails loudly instead of quietly selecting eleven. The gap itself is the remainder below.

## Done so far

- **The live-tailed volume source now exists (2026-07-23).** This topic's `ripe_when` named exactly two acceptable discharges — [[T0065]]'s live-trades→bars materializer, or *a REST volume pull in the rebuild path*. The second landed as `zcrypto data rebuild ohlc-reach` (`cli/ohlc/reach.py`), and it clears the freshness budget with room to spare:

  | set | stalest daily bar | staleness | `_require_fresh_ohlc` |
  |---|---|---|---|
  | `data/ohlc-full` | ETH @ 2026-03-31 | 114 d | **fails closed** (budget 7 d) |
  | `data/ohlc-reach` | ETH @ 2026-07-22 | **1 d** | **passes** |

  Note this vindicates the guard rather than working around it: the rebuild was *correctly* refusing, and the fix was to supply a fresh source, not to relax the budget.

- **The remainder is a wiring decision, and it is deliberately parked.** `_refresh_universe` still reads `ohlc-full` via `_require_ohlc_full`. Repointing it at a reach set changes **which dataset defines the tradeable universe** — a research-relevant choice (the reach set's tail is REST-derived rather than dump-derived), so it rides [[T0025]]'s pre-live refresh with the owner present rather than being switched autonomously. Until then a universe rebuild continues to fail closed, which is the safe state.

## Suggested next steps

- **(The remaining blocker — and dump ingestion does NOT discharge it)** The OHLCVT dumps are **quarterly** (`Kraken_OHLCVT_Q<N>_<YYYY>.zip`; newest on the NAS is Q1 2026, with Q2 still absent 22 days after the quarter closed). A dump-derived frontier is therefore always a quarter boundary: ingesting Q2 today gives 2026-06-30, still 22 days stale against a 7-day budget, so the guard fires anyway. **A universe rebuild needs a live-tailed volume source, not a fresher dump.**
- **(The real options, one of which T0025 must pick)** (a) a REST volume pull in the rebuild path, which is what the 2026-07-07 build effectively did — decouples selection from the dump cadence, but reintroduces a network dependency; (b) [[T0065]]'s live-trades→bars materializer, which per [[T0092]] feeds **EUR pairs only**, so the two BTC-quoted legs would still need a source; (c) widen the staleness budget, which is the option that quietly reintroduces the defect and is recorded here to be rejected explicitly rather than drifted into.
- ~~**(Cheap, independent)** Record the resolved dataset path + hash in the universe provenance from the same handle the builder actually read, so the artifact cannot cite a set the code does not use.~~ **Done 2026-07-22** — *partially*: provenance now carries `ohlc_dataset_dir` (the directory read, taken from `ohlc_root` itself) and `ohlc_stalest_daily_bar` (the stalest symbol's newest bar — the value the staleness guard tests, and the only one supporting "every symbol's window ends at or after this"). The bullet's success criterion is **now fully met** (2026-07-23): the residual — a directory name is not an identity, so an artifact whose `ohlc_dataset_hash` was empty still cited nothing resolvable — was split out as [[T0094]] and **resolved**, so a rebuild whose OHLC set carries no usable `manifest.json` fails closed instead of publishing an unciteable artifact. Provenance is no longer this topic's problem; the remainder below is purely the DATA gap.

- **(Registered remainder — retire the legacy `universe/` fallback; ripe when: the first stamped `universe-<stamp>/` set is published to the hub and verified — the resolver selects it and the sitting's post-publish checks pass)** Spec `00093` D5 turns the canonical artifact into immutable `universe-<stamp>/` sets resolved newest-wins, keeping the legacy `universe/` directory — frozen at its 2026-07-07 content — as the resolver's fallback so nothing breaks before the first stamped publish. Once the trigger fires the fallback is dead weight that can mask a resolution bug as a silent time-travel to 2026-07-07: remove the legacy fallback branch from `resolve_universe_path` in `cli/capture/command.py` (and its fallback test), and record here which verified stamped set licensed the removal. Two couplings to respect: repo-side only — the hub's `universe/` copy stays, since the additive-only transport never deletes from the hub; and `tests/test_data_rebuild.py::test_every_rebuildable_dataset_is_an_authored_set` requires the `universe` REBUILDABLE name to stay in `authored_sets`, so decide that half deliberately rather than deleting the entry blind.
