# Benchmark B2 Basket Bar-to-Beat Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write a new committed report `docs/research/04.phase3-benchmark-b2-basket-report.md` recording the **B2 inverse-vol majors-basket bar-to-beat** on real data — the basket run on the 10 EUR majors over their common window, compared to single-asset BTC B0/B1 over the *same* window — with the honest finding that naive diversification did **not** beat BTC (the raw basket lost money with a deeper drawdown), and only vol-targeting delivers the risk profile.

**Architecture:** No new code — a throwaway scratchpad run script that loads the 10 majors, intersects their calendars, runs the already-reviewed `inverse_vol_basket` + BTC `buy_and_hold`/`vol_target` through `run_backtest`, and a new committed markdown report. Light doc iteration (no spec).

**Tech Stack:** Python 3.14, stdlib + polars (`cli.ohlc.dataset.read_parquet`). The report is NOT on the mdformat allowlist — hand-write clean markdown.

## Global Constraints

- **No code change.** The run script is a THROWAWAY scratchpad (session scratchpad dir, not committed); the committed artifact is `docs/research/04.phase3-benchmark-b2-basket-report.md` (new). No CLI/README change.
- **Report the honest finding, not a headline.** The raw inverse-vol basket UNDERPERFORMED single-asset BTC over this window (lost money, deeper drawdown). The report must state this plainly and explain the mechanism (the alts were devastated in 2022 and mostly didn't recover); do NOT spin diversification as a win.
- **Common-window alignment:** align the 10 majors by intersecting their `ts` (datetime) values, sorted; the common window is 2021-12-21 → 2026-03-31 (1562 closes → 1561 returns), driven by AVAX being the newest listing. All four strategies are computed over this same window for apples-to-apples.
- **lookback=30** for both the basket's per-asset vol and B1/B2's vol-target (consistent with the family). B1/B2-voltarget target 10%/yr (`target_vol=0.10/(365**0.5)`), `max_leverage=1.0`.

---

### Task 1: Run + write the report

**Files:** Create `docs/research/04.phase3-benchmark-b2-basket-report.md`.

- [ ] **Step 1: Write + run** a scratchpad script (session scratchpad dir, NOT committed) that:
  - Loads `data/ohlc-full/<BASE>/EUR/1440.parquet` for `BASE ∈ {ADA, AVAX, BTC, DOGE, DOT, ETH, LINK, LTC, SOL, XRP}`; builds `{ts: close}` per asset (the `ts` column is a timezone-aware datetime — use it directly as the dict key, do NOT `int()` it).
  - Intersects the `ts` sets across all 10, sorts → the common calendar; builds `prices_by_asset = {base: [close at each common ts]}`.
  - Computes: `b2 = inverse_vol_basket(prices_by_asset, lookback=30)`; `btc_rets = returns_from_prices(prices_by_asset["BTC"])`; `b1 = vol_target(btc_rets, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`; `b2vt = vol_target(b2, target_vol=0.10/(365**0.5), lookback=30, max_leverage=1.0)`.
  - Runs each through `run_backtest(rets, positions, fee_rate=0.0, periods_per_year=365)`: B0 = `buy_and_hold(len(btc_rets))` on `btc_rets`; B1 = `b1` on `btc_rets`; B2 = `buy_and_hold(len(b2))` on `b2`; B2-voltarget = `b2vt` on `b2`.
  - Also computes each asset's raw buy-hold multiple over the window (`prices[-1]/prices[0]`).

  **Expected values (verify — if any diverges materially, STOP and report):**

  Window: **2021-12-21 → 2026-03-31**, 1562 closes → 1561 returns, all 10 majors present.

  | Strategy | Total | Annualized | Sharpe | Max DD |
  |---|---:|---:|---:|---:|
  | B0 — BTC buy-and-hold | 1.36× | 7.49% | 0.397 | 65.8% |
  | B1 — BTC vol-target (10%/yr) | 1.21× | 4.61% | 0.456 | 17.5% |
  | **B2 — inverse-vol basket (10 majors)** | **0.68×** | **−8.57%** | **0.194** | **69.4%** |
  | B2 + vol-target (10%/yr) | 1.21× | 4.49% | 0.453 | 14.6% |

  Per-asset buy-hold multiple over the window (context — only 2 of 10 gained): BTC 1.36×, XRP 1.38×, DOGE 0.53×, ETH 0.51×, SOL 0.45×, LINK 0.44×, LTC 0.34×, ADA 0.18×, AVAX 0.07×, DOT 0.05×.

- [ ] **Step 2: Write `docs/research/04.phase3-benchmark-b2-basket-report.md`** with these sections:
  - **Title + intro:** the B2 inverse-vol majors-basket bar-to-beat; the 10 EUR majors over their common window (2021-12-21 → 2026-03-31, the span where all 10 exist — AVAX is the newest); why this window (apples-to-apples with BTC over the same span); zero-fee idealization; lookback=30, inverse-vol weighting per `inverse_vol_basket`.
  - **Results table:** the four-row table above (real numbers from your run).
  - **Per-asset context:** a short table or list of the 10 per-asset buy-hold multiples, noting only BTC and XRP gained; the rest lost 47–95%.
  - **Interpretation (honest):**
    - The **raw inverse-vol basket underperformed single-asset BTC** — it *lost* money (0.68×, −8.6%/yr) with a *deeper* max drawdown (69.4%) than BTC buy-and-hold (65.8%). Naive diversification across the majors was no free lunch over this window.
    - **Mechanism:** the window opens near the November-2021 top; the 2022 bear (LUNA/FTX) devastated the altcoins and most never recovered by 2026 — 8 of the 10 majors ended below their window-start price (AVAX −93%, DOT −95%, ADA −82%). An inverse-vol basket still *holds* those losers (at risk-normalized weights), so BTC and XRP (the only two winners) can't carry it.
    - **Vol-targeting is the edge, not asset selection.** Both B1 (vol-targeted BTC) and the vol-targeted basket land at Sharpe ~0.45, maxDD ~15–18% — far better than either raw strategy — reinforcing the master plan's §1/§5 thesis that disciplined risk control, not diversification, is what delivers the risk-adjusted profile.
    - **Window caveat.** This is a single, BTC-unfavorable window: BTC B0's Sharpe here is 0.40 versus **1.075 over the full 2013–2026 history** (see `docs/research/04.phase3-benchmark-b0-b1-report.md`). Conclusions are specific to 2021-12 → 2026-03; a full-history dynamic-composition basket (open topic **T0007**) would test whether the basket's underperformance is structural or window-specific.
    - **B2's place in the family:** B2 does **not** raise the bar — the deployable target stays the vol-targeted / gated family from the single-asset BTC panel. Any Phase-4 alpha still clears B0/B1/gated-B1, not the raw basket.
  - **Distrust-the-instrument note:** the stack (10 real parquets → common-calendar intersection → `inverse_vol_basket` → `run_backtest` → metrics) ran end-to-end; the basket's loss is corroborated by the per-asset multiples (8 of 10 majors down 47–95%), so it reflects real 2022 alt carnage, not an internal artifact.
  - **Caveats:** single common window (2021-12 → 2026-03), ~4.3 yr; zero-fee (the basket rebalances daily → its net returns are the most fee-sensitive of the panel; a basket-turnover cost model + §9.6 stress is a later iteration); fixed 10-asset intersection composition (the dynamic full-history variant is T0007); B3 (gate × basket) + B4 (short) + the DSR/PBO/SPA significance comparison deferred.

- [ ] **Step 3: Full gate** — `git add docs/research/04.phase3-benchmark-b2-basket-report.md` (report only; NOT the scratchpad); `uv run pre-commit run -a` clean; `uv run pytest -q` green (no code change ⇒ unchanged **469 passed**).

- [ ] **Step 4: Commit** — `docs(benchmark): add the B2 inverse-vol basket bar-to-beat report`.

---

### Task 2: iterations-history closeout

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1:** Append `## 2026-07-08 — iter-031: B2 inverse-vol basket bar-to-beat (Phase 3)` with bullets covering: the new `docs/research/04.phase3-benchmark-b2-basket-report.md` running `inverse_vol_basket` on the 10 EUR majors over the common window (2021-12-21 → 2026-03-31) vs BTC B0/B1 over the same window; the honest finding — **the raw basket underperformed single-asset BTC** (0.68×, Sharpe 0.194, maxDD 69.4% — *deeper* than BTC's 65.8%), because 8 of 10 majors ended 47–95% below their window-start price and inverse-vol weighting still holds them; **vol-targeting (on BTC or the basket) is the edge** (both ~0.45 Sharpe, ~15–18% maxDD); the window caveat (BTC Sharpe 0.40 here vs 1.075 full-history) and the T0007 full-history pointer; B2 does not raise the bar (deployable target stays the vol-targeted/gated family). No new code (composes the reviewed generator). Plan `00023`. Eighth Phase-3 component. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-031 closeout — B2 basket bar-to-beat`.
