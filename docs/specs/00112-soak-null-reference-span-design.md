# The soak's null reference spans only the era its basket exists in

## Problem

`analyze_soak` judges the live engine's structural metrics against a null built by `build_null` over the whole of `data/ohlc-full`, 2013-09-10 to 2026-03-31. The basket that null trades does not exist for most of that span. Its ten legs enter one at a time, the last on 2021-12-21, so the first two thirds of the null is a book of one to nine names.

For a cross-sectional statistic this is not a smaller sample of the same thing, it is a different quantity. Concentration is the case that surfaced it: HHI over a single name is 1.0 by construction whatever the strategy does, and in the null's first decile 88.2% of active bars hold exactly one name. Asset count alone explains 98.8% of the gap between that decile and the late span. The metric is arithmetically pinned across a region the verdict nevertheless averages in.

The consequence is a reference the live engine cannot be compared against. The engine trades ten legs; two thirds of its null does not.

## Decisions

**D1. The null's reference span starts at the first bar where every basket asset has a price, and the bars before it are dropped from the null's series.** The soak's null covers the complete-basket era only.

**D2. The cut is applied to the null's OUTPUT, never to the builder's input.** `build_crossfreq_system_fast` still receives the full canonical history, so every lookback is warm at the first retained bar; the retained series is then sliced. Slicing the input instead would restart the system's own warm-up inside the retained window and reintroduce the leading flat run this change exists to remove — the failure mode is the one the change is aimed at, so the distinction is load-bearing rather than stylistic.

**D3. The cut is derived from the loaded canonical arrays, never written as a date.** It is the first index at which every asset in `CrossfreqSystemConfig().assets` has a finite price. A constant is wrong the day the basket changes, and the basket is expected to change.

**D4. The realized series is untouched, and so is the per-bar sentinel.** `structural_metrics` keeps returning `0.0` for a bar with no book; this change alters which null bars are judged, not what any bar means. Whether the surviving sentinels should be averaged is a separate open decision in `T0184`, deliberately not settled here.

**D5. The report states the span the null covers.** A verdict compared against a different reference than last quarter's run must say so on its own face, or two runs are silently incomparable.

**D6. The cost is recorded, not hidden: the null's sample falls by two thirds, and with it the horizon before the gate becomes unusable.** `metric_verdict` returns `n/a` once `effective_n < 3`, and `effective_n` is the null's bar count over the realized length, so a shorter null reaches that cutoff at a shorter soak.

## The measured basis

Every figure below was produced by a command at write time, from the tree at this branch's tip, and re-derives from the cached per-bar series or from the canonical dataset. They drift when either changes.

**The basket completes on 2021-12-21, and AVAX is the binding leg.** `_load_canonical(data/ohlc-full)` yields 4582 daily and 27338 four-hourly stamps; the first daily index at which all ten legs carry a price is 3020 and the first four-hourly index is 17971, both 2021-12-21. The per-asset first stamps run BTC 2013-09-10, LTC 2013-09-14, ETH 2015-08-07, XRP 2017-05-18, ADA 2018-09-28, LINK 2019-09-25, DOGE 2019-12-19, DOT 2020-08-18, SOL 2021-06-17, AVAX 2021-12-21. These match `docs/reference/data-catalog-full.md`'s own per-symbol table.

**What the cut does to the null**, at the realized window length of 358 bars:

| | full span | era-matched |
|---|---|---|
| null bars | 27337 | 9366 |
| flat bars | 13.46% | 8.36% |
| concentration mean | 0.323623 | 0.240745 |
| band p95 | 0.663393 | 0.400653 |
| band width | 0.542712 | 0.284267 |
| `effective_n` | 76.360 | 26.162 |
| the live reading's percentile | 30.55 | 44.47 |

**The verdict cutoff is far away but nearer than it was.** `metric_verdict` returns `n/a` at `effective_n < 3`, so era-matching leaves 8.7 times the cutoff. Expressed as a horizon, the full-span null reaches the cutoff at a realized length of 9112 bars, about 4.2 years of live running, and the era-matched null at 3122 bars, about 1.4 years.

**The realized series needs nothing.** It spans 2026-07-11 to 2026-09-08, entirely inside the complete-basket era, and carries no flat bar: 358 scored bars, smallest gross exposure 0.0124, against a branch that fires at 1e-12.

**This changes the reference more than the aggregation question does, and in the opposite direction.** The best aggregation candidate moves the band's p95 from 0.663393 to 0.921380 on the full span; the cut moves it to 0.400653. Applying that candidate on top of the cut gives 0.473955, so the widening it was criticised for shrinks from 38.9% to 18.3% of the base it acts on.

## Out of scope

The aggregation of the surviving sentinel bars, which is `T0184`'s open decision and the owner's. The same span question in the deployable's committed validation basis, which uses the same builder over the same span: `cli/portfolio/record44_legs.py` is not touched here; the question it raises is already registered in `T0184`, whose file records that the builder is shared and that the deployable inherits the same composition effect.
