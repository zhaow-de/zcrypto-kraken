# 00095 — the twelve-leg deployable: re-ratifying record 44's book on the widened basket

**Goal:** register the deployable trading system on the twelve-leg basket `00094` builds, as one P1 trial. What is traded has changed shape; what computes the targets has not. This document is the successor to `docs/specs/00038-cross-frequency-combination-design.md` — the spec registry record 44 pins — and is the spec the successor record pins in turn.

## Why a spec at all, when the strategy did not change

Record 44 ratified a **ten-leg** deployable: the ten `/EUR` pairs, targets computed by `build_crossfreq_system_fast` over those same ten. `00094` re-keys the engine to full symbols and widens the traded basket to twelve, adding `ETH/BTC` and `SOL/BTC`. The model is untouched, but the *set of instruments the engine is authorised to hold* is not what record 44's evidence covers, and the registry's unit is the deployable, not the model. A basket change therefore re-opens the ratification even when every number is identical — which is the claim this spec exists to state, and the record exists to carry.

The alternative — trading twelve under a record that names ten — would leave the deployed system unratified in exactly the dimension that changed, with nothing in the repo able to detect it.

## The basket — twelve legs

```
ADA/EUR  AVAX/EUR  BTC/EUR  DOGE/EUR  DOT/EUR  ETH/BTC
ETH/EUR  LINK/EUR  LTC/EUR  SOL/BTC   SOL/EUR  XRP/EUR
```

Sorted, and the single committed source of truth is `cli/engine/store.py::BASKET`; `PAIR_KEYS`, `INSTRUMENT_IDS`, `COSTMIN` and the venue gauges all derive from it rather than restate it.

**`DOT/EUR` is deliberately kept.** The 2026-08-13 universe refresh deselected it — median quote volume 146,957.37 against the 150,000 floor, a real decline rather than a measurement artifact — and the owner ruled on 2026-08-14 (recorded on [[T0137]]) that it stays traded. The floor is a *footprint-sizing* rule, calibrated so a full €1,400 maximum-size position sits at roughly 1 % of median daily volume; DOT is 2 % under that calibration, and Phase-6b rung sizes sit far below the calibrated footprint, so the economic exposure of keeping it is nil. Retiring it would have meant a basket mask zeroing a computed target in the cycle and in the gate replay alike — a standing deviation between the live book and record 44's own evidence base, created to honour a 2 % miss. `tests/test_basket_concordance.py` keeps `DOT/EUR` as its sole traded-but-deselected exception, and that exception now encodes the ruling rather than an open question: any future refresh that changes selection turns the test red and forces a conscious edit, DOT's re-entry included.

**`ETH/BTC` and `SOL/BTC` are addressable and tradeable, and held at exactly zero.** They enter the basket so the engine can express them; no sleeve computes a weight for either.

## Construction — the model is unchanged, the widening is downstream

1. **The model.** `CrossfreqSystemConfig.assets` remains the ten EUR bases `("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")`, and `cli/portfolio/` is byte-identical across the whole `00094` branch (verified by an empty `git diff` against the merge base). Every sleeve — B, A1, A2 — the caps, the costing and the §10 governor are record 44's, unmodified. Spec `00038`'s construction is this system's construction.
2. **The builder-input contraction.** `cli/engine/cycle.py::select_model_inputs` picks the ten `/EUR` series out of the twelve-symbol store, re-keys them by base for `CrossfreqSystemConfig`, and **unions the calendar over the ten EUR pairs only** — a stamp enters iff some EUR leg carries a non-`None` close there. A `/BTC` stamp the EUR legs lack must never shift an EUR SMA or stdev window. One implementation, three consumers: the cycle, the gate replay, and the soak's loaders.
3. **The expansion.** `cli/engine/cycle.py::_expand_to_basket` takes the model's ten base-keyed targets and returns twelve symbol-keyed ones: each base carries its value onto `<base>/EUR`; every `BASKET` member the model produced nothing for — `ETH/BTC`, `SOL/BTC` — emits exactly `0.0`. A model base with no `<base>/EUR` leg in the basket raises rather than being silently dropped.

The zeros are **structural**, not an output: they are a property of the expansion, not of any weight the model computed. That is what makes this a basket change and not a strategy change, and it is why a future relative-value sleeve for those legs must arrive with its own evidence bar and its own ratified record rather than inheriting this one.

## Verdict protocol — the criterion is identity, not a search

**Adopt iff all four hold**, each measured rather than asserted:

- **G1 — the grids are identical.** The daily and 4h grids reaching the builder through `select_model_inputs` over the twelve-symbol dataset equal, element for element and stamp for stamp, the grids record 44's own loader (`cli/portfolio/record44_legs.py::load_union`) produces over the ten EUR series.
- **G2 — the book is identical.** `governed_net`, `ungoverned_net` and every row of `final_targets` compare **exactly equal** (`==`, not a tolerance) between the widened path and the ten-asset path, over the full frozen history. `cap_breach_bars` and `governor_engaged_bars` equal record 44's registered integers.
- **G3 — record 44's own legs reproduce.** Every leg `cli/portfolio/record44_legs.py::rederive_record44_legs` re-derives — annualised and decisive Sharpe, the frozen 4h benchmark, the SPA grid at blocks {30, 102} × seeds {42, 7, 1234}, DSR, and the benchmark-relative worst-slice diagnostic — is exactly equal between the two paths, and matches record 44's registered values at the precision each was registered to.
- **G4 — the `/BTC` legs are exactly zero.** Both read `0.0` in the expansion, and a target of `0.0` against a previous target of `0.0` emits no order row, so the widening is silent in the executor as well as in the book.

Any inequality at any precision — including a last-bit difference — fails the criterion. There is no tolerance band, because a difference of any size would mean the contraction is feeding the model something other than record 44's inputs, and the size of the discrepancy would say nothing about the cause.

**Registration:** `family="P1"`, `n_trials_in_family=5`, `seeds=[42, 7, 1234]`, verdict `adopt` on the owner's word. Failing any of G1–G4 → `reject`, and record 44 stays the deployable with the widening reverted rather than deployed.

## What was measured

The four gates were run over `data/ohlc-full` — the frozen record-44 oracle, 24 files across the twelve symbols on both grids, spanning 2013-09-10 to 2026-03-31 — driving the real production surfaces (`read_store_series` → `select_model_inputs` → `build_crossfreq_system_fast` → `_expand_to_basket`) against `record44_legs`' ten-asset loader as the baseline.

| gate | result |
| --- | --- |
| G1 grids | daily 4,582 stamps, 4h 27,338 stamps; timestamp lists equal, 0 close mismatches, max abs difference `0.0` |
| G2 book | `governed_net` and `ungoverned_net` 0 differing of 27,337 bars; `final_targets` 0 differing of 10 × 27,338; max abs difference `0.0`; `cap_breach_bars` 1318, `governor_engaged_bars` 7302 |
| G3 legs | every re-derived leg exactly equal across the two paths; `ann_sharpe_noc` 1.560907676587497, decisive 1.5583341567194398, `maxdd` 0.1356768814775332, pre-governor 0.18657983630785457, benchmark 1.2128451567638199 / 1.2446890489958136, SPA headline `spa_p_full` 0.001999000499750125 and `spa_p_decisive` 0.004497751124437781, worst-slice diagnostic identical |
| G4 zeros | `ETH/BTC` and `SOL/BTC` both `0.0`, and no order row for either |

Every value the registry stored at full precision — `per_period_sharpe_4h`, all seven SPA readings, `var_trials_4h` — reproduces record 44 **bit for bit**; every value the registry stored rounded reproduces it to the registered digit. The cost-stress arms re-run at 1.5× and 2× cost read 1.3028688330561256 and 1.2106292366788787, matching record 44's registered 1.3029 / 1.2106 and equal across both paths.

**Verdict on the criterion: identical, exactly.** Not "within tolerance" — the difference is `0.0` on every series and every leg.

## Disclosures — what this evidence is and is not

- **Not blind, and it could not be.** The identity was measured before the record was prepared. This is a construction check, not a hypothesis test: no parameter was selected from the outcome, and there is no alternative the measurement could have favoured. Record 44 carries a comparable disclosure about its own headline figure; the same honesty applies here for a different reason.
- **The calendar contraction is not exercised by this dataset.** `data/ohlc-full` carries **zero** `/BTC`-only stamps on either grid — every `/BTC` timestamp is already in the ten-EUR union — so the "a `/BTC` stamp must not move an EUR window" property is *unfalsified* here rather than *proven* here. It is proven instead by a constructed fixture in the cycle test suite, where the twelve-symbol union deliberately differs from the ten-EUR union. Nothing in the data constructs today's coincidence, which is exactly why the contraction exists.
- **`spot_drag_pct_yr` is not re-derived.** No committed code reproduces it; record 44's registered 0.0315 remains registry-asserted and is deliberately absent from the successor record's metrics rather than copied forward unmeasured.
- **The DSR leg weakens slightly by construction.** Declaring a fifth P1 trial raises the family's multiple-testing count, so DSR falls from 0.9999994822040257 at n=4 to 0.9999992100303082 at n=5. This is honest bookkeeping — the family ledger counts registered trials — and it does not approach any decision boundary.
- **Record 43's comparison remains unrebuildable.** Record 44 registered its verdict against incumbent trial 43, whose construction was never committed ([[T0125]]). This spec's criterion is benchmark- and identity-relative and needs no such comparison; nothing here recovers it.

## Out of scope

- Any relative-value sleeve for the `/BTC` legs — an explicit drop, not a deferral. The structural zeros stand until someone proposes a sleeve, which arrives with its own evidence and its own record.
- Order placement, sizing and fill ingestion for the `/BTC` legs — `00090`'s, consuming `00094`'s FX term and per-symbol costmin.
- Re-pricing the builder's cost basis, re-deriving governor constants, or any change to `cli/portfolio/`.
- Re-litigating `DOT/EUR` before the concordance test forces it.
