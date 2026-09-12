---
status: resolved
---

# Dynamic-composition inverse-vol basket (full-history B2 variant)

## Resolution

Resolved in **iter-044** (PR TBD). Built the look-ahead-free `dynamic_inverse_vol_basket`
(`cli/benchmark/strategies.py`) over the union calendar with per-asset presence + warm-up, and ran
the full-history finding-1 comparison (`docs/research/04.phase3-benchmark-b2-dynamic-report.md`). **Verdict:** over the
full 2013→2026 history the dynamic 2→10 basket is *statistically indistinguishable* from single-asset
BTC risk-adjusted (Sharpe 1.100 raw / 1.147 vol-targeted vs BTC 1.075 / 1.111; all four bootstrap CIs
strictly positive but heavily overlapping). The fixed-window "basket loses to BTC" (0.68×, Sharpe
0.194) — and even the 4-major ~9yr proxy's residual drag (0.798<0.929) — were **window artifacts**;
the basket is a co-equal viable base for A1's finding-1, not a decisive winner. `gated-B1` stays the
bar-to-beat. B3 (gate × basket) / B4 (basket + short) dynamic variants noted as a follow-up.

**Correction (2026-09-12), on the sweep's read of the archive:** "`gated-B1` stays the bar-to-beat" is
contradicted by the tree: the frozen benchmark is **B3+vt-dynamic**, adopted by the human on the 2026-07-09
PR-74 review in supersession of gated-B1, shown by
`grep -no 'adopt B3+vt-dynamic as the frozen benchmark' docs/research/10.phase4-decisions.md` →
`138:adopt B3+vt-dynamic as the frozen benchmark`. The sentence held when this topic closed at iter-044; the
bar moved at iter-055, and `docs/research/00.master-plan.md`'s kill bar and
`docs/research/12.phase5-system-spec-runbook.md:36` both name B3+vt-dynamic now. Nothing else in this
paragraph is affected — the verdict, the figures and the window-artifact finding stand.

**The steps this topic carried at its close, kept verbatim with what answered each:**

- Build a `dynamic_inverse_vol_basket(prices_by_asset, *, lookback)` (or extend `inverse_vol_basket` with an alignment mode) that takes per-asset series on a **union** calendar with explicit presence (e.g. `None`/NaN before listing), and for each date weights inverse-vol over assets that are both present and have ≥ `lookback` in-window returns, renormalizing over that day's qualifying set; all-absent/warmup day → flat. — **ANSWERED:** committed as `dynamic_inverse_vol_basket(prices_by_asset: dict[str, list[float | None]], *, lookback: int)` (`cli/benchmark/strategies.py:120`), on the union calendar with explicit absence and each day's set qualified on presence plus warm-up; four callers consume it (`cli/portfolio/builder.py`, `crossfreq_system.py`, `record43_book.py`, `record44_legs.py`).
- TDD the composition edge cases specifically: an asset entering mid-window (weight 0 until it warms up, then joins), an asset with a data gap, the 2→10 growth boundary — plus the same look-ahead invariance test (a day's weights invariant to that day's realized returns). — **ANSWERED:** `tests/test_benchmark_dynamic_basket.py` carries exactly those — `test_dynamic_basket_entry_warmup`, `test_dynamic_basket_gap_disqualifies_until_reaccrual`, `test_dynamic_basket_known_answer_two_assets_entry`, `test_dynamic_basket_renormalization_sums_to_one`, `test_dynamic_basket_all_absent_or_warmup_is_zero`, `test_dynamic_basket_no_look_ahead` and `test_dynamic_basket_reduces_to_fixed`, beside the guard cases.
- Re-run the B2 (and later B3/B4) bar-to-beat over the full 2013→2026 horizon and compare against both the fixed-window basket and the single-asset BTC benchmarks over matched windows. — **ANSWERED:** the full-history re-run is `docs/research/04.phase3-benchmark-b2-dynamic-report.md` (2013-09-10 → 2026-03-31, 4581 returns) against both the fixed-window basket and the single-asset BTC benchmarks, with the verdict logged at `docs/research/10.phase4-decisions.md` [iter-044]. The bullet's parenthetical "and later B3/B4" was registered as [[T0010]] rather than left here, and delivered in that same report's §"B3 and B4".

## Context — what

The B2 benchmark (inverse-vol majors basket, master plan §9) is being built (iter-030) as a **fixed 10-asset basket over the common window** (intersection calendar 2021-12-21 → 2026-03-31, ~1560 days — the span where all 10 EUR majors exist). This topic parks the richer **dynamic-composition** variant: align all majors to BTC's full 2013→2026 calendar, mark pre-listing periods absent, and each day inverse-vol-weight over only the currently-listed-and-warmed-up assets, so the basket grows from 2 assets (BTC+LTC, 2013) to 10 (2021+).

## Why this matters

The fixed-window basket drops ~8 years of history (BTC/LTC from 2013, ETH 2015, XRP 2017, ADA 2018, …) and tests only ~4.3 years / one bull→bear→recovery cycle. The dynamic basket (a) uses all available history for a much longer-horizon risk-adjusted read, (b) mirrors how a live basket would actually operate — you can only hold what's listed — and (c) lets B3 (gate × basket) and B4 (basket + short) inherit the full-history horizon the single-asset BTC benchmarks already enjoy (2013→2026). A one-cycle basket benchmark is a materially weaker bar-to-beat than the 12-year single-asset ones.

**Elevated at the Phase-4 kickoff.** The Phase-4 orientation memo (`docs/research/05.phase4-orientation.md`, finding 1) promotes this from a nice-to-have richer benchmark to **the critical first A/B of the first alpha family (A1)**: Phase 3 found the fixed-window majors basket (B2) *underperformed* single-asset BTC, but over a single BTC-unfavorable window — so it is not yet established whether the basket's weakness is *structural* (alt-vs-BTC beta) or a *window artifact*, and the bootstrap CIs showed that 4.3-year window lacks the statistical power to tell. A1's premise is a "vol-targeted majors basket"; whether that base beats a BTC-anchored book is A1's opening question, and it can only be answered honestly on the full-history universe this topic builds. Until then A1's basket-vs-BTC A/B rests on the underpowered common window.

## Why it's parked (not done now)

Chosen against in iter-030 (`.tmp/decisions.md` [iter-030], Decision 2) to **isolate the look-ahead-critical inverse-vol weighting from variable-composition churn** at the deepest context of a very long session. The dynamic variant adds a per-day presence mask, renormalization over a changing asset set, and a wider look-ahead / edge-case surface (assets entering mid-window, warmup per-asset-not-global) — the highest-risk piece to get right, better revisited with fresh context.

## Findings so far

- Data is present and sufficient: 10 EUR-quoted majors with daily parquets under `data/ohlc-full/<BASE>/EUR/1440.parquet`, common end 2026-03-31, starts ADA 2018-09-28 / AVAX 2021-12-21 / BTC 2013-09-10 / DOGE 2019-12-19 / DOT 2020-08-18 / ETH 2015-08-07 / LINK 2019-09-25 / LTC 2013-09-14 / SOL 2021-06-17 / XRP 2017-05-18.
- The fixed-window `inverse_vol_basket` generator (iter-030) establishes the look-ahead-free inverse-vol weighting mechanism the dynamic variant reuses per-day; only the composition/alignment layer differs.
