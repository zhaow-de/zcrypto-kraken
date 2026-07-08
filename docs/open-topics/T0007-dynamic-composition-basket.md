---
status: open
---

# Dynamic-composition inverse-vol basket (full-history B2 variant)

## Context — what

The B2 benchmark (inverse-vol majors basket, master plan §9) is being built (iter-030) as a **fixed 10-asset basket over the common window** (intersection calendar 2021-12-21 → 2026-03-31, ~1560 days — the span where all 10 EUR majors exist). This topic parks the richer **dynamic-composition** variant: align all majors to BTC's full 2013→2026 calendar, mark pre-listing periods absent, and each day inverse-vol-weight over only the currently-listed-and-warmed-up assets, so the basket grows from 2 assets (BTC+LTC, 2013) to 10 (2021+).

## Why this matters

The fixed-window basket drops ~8 years of history (BTC/LTC from 2013, ETH 2015, XRP 2017, ADA 2018, …) and tests only ~4.3 years / one bull→bear→recovery cycle. The dynamic basket (a) uses all available history for a much longer-horizon risk-adjusted read, (b) mirrors how a live basket would actually operate — you can only hold what's listed — and (c) lets B3 (gate × basket) and B4 (basket + short) inherit the full-history horizon the single-asset BTC benchmarks already enjoy (2013→2026). A one-cycle basket benchmark is a materially weaker bar-to-beat than the 12-year single-asset ones.

## Why it's parked (not done now)

Chosen against in iter-030 (`.tmp/decisions.md` [iter-030], Decision 2) to **isolate the look-ahead-critical inverse-vol weighting from variable-composition churn** at the deepest context of a very long session. The dynamic variant adds a per-day presence mask, renormalization over a changing asset set, and a wider look-ahead / edge-case surface (assets entering mid-window, warmup per-asset-not-global) — the highest-risk piece to get right, better revisited with fresh context.

## Findings so far

- Data is present and sufficient: 10 EUR-quoted majors with daily parquets under `data/ohlc-full/<BASE>/EUR/1440.parquet`, common end 2026-03-31, starts ADA 2018-09-28 / AVAX 2021-12-21 / BTC 2013-09-10 / DOGE 2019-12-19 / DOT 2020-08-18 / ETH 2015-08-07 / LINK 2019-09-25 / LTC 2013-09-14 / SOL 2021-06-17 / XRP 2017-05-18.
- The fixed-window `inverse_vol_basket` generator (iter-030) establishes the look-ahead-free inverse-vol weighting mechanism the dynamic variant reuses per-day; only the composition/alignment layer differs.

## Suggested next steps

- Build a `dynamic_inverse_vol_basket(prices_by_asset, *, lookback)` (or extend `inverse_vol_basket` with an alignment mode) that takes per-asset series on a **union** calendar with explicit presence (e.g. `None`/NaN before listing), and for each date weights inverse-vol over assets that are both present and have ≥ `lookback` in-window returns, renormalizing over that day's qualifying set; all-absent/warmup day → flat.
- TDD the composition edge cases specifically: an asset entering mid-window (weight 0 until it warms up, then joins), an asset with a data gap, the 2→10 growth boundary — plus the same look-ahead invariance test (a day's weights invariant to that day's realized returns).
- Re-run the B2 (and later B3/B4) bar-to-beat over the full 2013→2026 horizon and compare against both the fixed-window basket and the single-asset BTC benchmarks over matched windows.
