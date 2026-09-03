# 00110 — the B2 derivatives-positioning feature harness (funding + OI)

Builds the instrument B2 will be measured with. It registers no trials and spends no budget; the family and its hypotheses come after, against a harness that has already proven itself on known answers.

## The measured basis

Both substrates exist and are catalogued. Read from `docs/reference/data-catalog-full.md` and the code, not recalled:

- **`derivatives-funding`** — 10 USDT-M perps, 68,281 realized-funding prints, 8h cadence, balanced from 2020-09-22. One real venue action is preserved rather than smoothed: SOL ran 4h→2h funding across 2022-11-09→18, carried in `interval_hours`.
- **`derivatives-oi`** — 5-minute open interest, 5,010,882 rows, ending 2026-07-22. `sum_open_interest` and `sum_open_interest_value` are **dense**; the four ratio columns carry genuine Binance gaps — **18.4 % panel-wide**, concentrated in one year (D5); BTCUSDT's 14.9 % is the panel's LOWEST rate, not its headline.
- **Coverage is the binding constraint.** Only BTCUSDT reaches 2020-09-01; every other perp starts **2021-12-01**, verified against the CDN. So **OI, not funding, bounds a balanced panel.**
- **The venue gap is already bridged**: `PERP_SYMBOLS` in `cli/derivatives/funding.py` maps each Kraken spot base to its Binance USDT-M perp for all ten legs.
- **B2's shape is fixed by master-plan §5** (Strategy Design Space, line 156 — *not* §12, which begins at line 307 and mentions B2 only in the approval calendar and in a ranked-queue pointer that itself cites §5; note §9 line 261 uses "B2" for an unrelated benchmark): *"funding extremes and OI/liquidation spikes as short-horizon de-risking / re-entry triggers for the spot book"* — a **conditioning** family, like B1, not a standalone system.
- **Budget**: B = 25 shared; B1 has spent 2; **23 remain**. This spec spends none.

## Decisions

### D1 — The harness computes features and nothing else

No family, no hypotheses, no registry entries. Separating the instrument from the verdict is what lets a harness bug be found *before* it can contaminate a registry entry — and the registry is append-only, so a contaminated entry is permanent.

### D2 — Alignment is as-of and causal: a feature at bar close `T` reads only rows stamped `≤ T`

Funding prints on an 8h grid, OI on 5m, the decision grid is 1h/4h. Both are forward-filled to the grid, never interpolated — an interpolated OI value is a number the market never showed. **This is the decision the tests exist to police**, and D8 makes it a property test rather than a review promise.

### D3 — The grid is 1h and 4h

The spot book's cadence. **Not B1's band** — spec `00045` conditions on the adopted A2-**4h** ensemble over `hour ∈ {0,4,8,12,16,20}`, and its 15m substrate feeds the vol scaler rather than a decision grid, so B1 is 4h-only. Both grids are nonetheless buildable (`60.parquet`, `240.parquet` both present), and 1h is kept because B2's trigger horizon is shorter than B1's conditioning horizon: a liquidation-cascade or funding-extreme response measured only at 4h cannot express a same-hour de-risk. 8h funding into a 1h grid means each print is carried forward across eight bars; that is intended, and the sign-persistence feature is defined over prints rather than bars so it cannot be inflated by the carry.

### D4 — The balanced panel starts 2021-12-01

OI-bound. A harness that silently used BTC's longer history would emit a panel whose first fifteen months hold one name, and every cross-sectional feature over that window would be a BTC statistic wearing a panel's name.

### D5 — Dense columns are dense; ratio columns propagate null

`sum_open_interest*` are complete — **measured, zero nulls in all ten symbols**. The four ratios are nullable, and any feature derived from them yields null where its input is null. **No imputation** — filling a missing ratio with zero or the trailing mean manufactures a reading the venue never published.

**And the gaps are not where the catalog says.** `data-catalog-full.md` **called** them an *early metrics* artifact. Measured 2026-09-02 and re-verified 2026-09-03, they are **one year, and panel-wide**: `count_toptrader_long_short_ratio` is **87.3 % null across 2022 for nine symbols and 87.0 % for XRPUSDT** — 91,733 of 105,120 rows missing, identically — and ~0 % in every other year. Within 2022 the first present row is 2022-01-30; read absolutely the column is populated from each series' first row, so the hole is 2022-scoped and not a late start. **Panel-wide null is 18.4 %** (921,890/5,010,882); BTCUSDT's 14.9 % is the lowest only because 15 extra months of dense history dilute it, so quoting BTC's rate understates the panel. The four ratios also differ by an order of magnitude — `count_long_short_ratio` 0.9 % null against the two toptrader ratios' 14.9 %. **A feature on the toptrader ratios is therefore blind through 2022** — the bear market and the FTX collapse, which is the regime a de-risking family exists for. A trial reading a Sharpe off that column would compute it on a sample silently missing its most informative year, and a CPCV fold covering 2022 would be near-empty. The catalog said otherwise and was corrected in this spec's own commit (`523a4034`), so a reader checking `data-catalog-full.md` now finds the corrected text, not the claim this paragraph refutes.

### D6 — Every emitted feature carries its coverage, and a trial cannot run blind to it

D5 makes the 2022 hole real rather than hypothetical, so the harness does not leave a consumer to discover it. Each feature frame is emitted with a per-column coverage summary — non-null count, first and last non-null timestamp, and the null fraction **per calendar year** — because a single overall figure hides exactly this shape: 14.9 % null reads as a nuisance, 87.3 % in one year reads as a missing regime. A downstream trial that ignores it is a choice someone made; a trial that could not see it is an instrument defect.

### D7 — Feature families, all per-asset

- **funding**: level; z-score over a trailing window of prints; sign persistence (consecutive same-sign prints); accrued carry over a trailing window.
- **OI**: level; log-delta; momentum over a trailing window; z-score.
- **ratios**: the four Binance ratios carried through, null-propagating.

**Windows are pre-registered here, in days, so they are grid-independent and fixed before any result is seen: 30 d for every trailing window** (funding z-score and accrued carry ≈ 90 prints; OI z-score and momentum = 720 bars at 1h, 180 at 4h). The number is a pre-registration, not an optimum — nothing here justifies 30 over 20 or 45, and that is the point: **changing it after seeing a result is a new trial and spends budget.** Sign persistence takes no window; it counts consecutive same-sign prints.

**The window's semantics are pinned here, because leaving them open made the plan's own thresholds unfalsifiable.** A trailing window at index `k` is the `window` observations **ending at and including `k`** — inclusive, because the observation at `k` is knowable at bar close `k` and excluding it is a different feature, not a safer one. Dispersion is the **sample** standard deviation (`ddof=1`). A z-score is `None` where the window is not yet full or where any member is `None`, and **`0.0` where the window has zero variance** — a constant series is not extreme. Under these rules a single observation eight base units above nine identical ones scores **2.8460498941515410**, not `3.0`; the population form gives exactly `3.0` and the exclusive form is undefined. Any test asserting a threshold must use the pinned definition's value.

**Output length is `len(input)`, not `len(input) - 1`.** The existing `cli/features/` functions return `len(prices) - 1` because they align to `returns_from_prices`; these align to the **input grid** — a level, a delta, a coverage row — so they return one value per input stamp with `None` where undefined. Stated because "match the existing convention" would otherwise import the wrong one.

### D8 — Every feature name carries its venue

[[T0023]] requires the venue gap to be carried explicitly, and a column called `oi_zscore` sitting beside Kraken spot columns invites a reader to assume it is Kraken's. Every emitted column is prefixed `binperp_` — the features describe **Binance USDT-M perpetuals**, mapped to Kraken bases through `PERP_SYMBOLS`, and the two venues' books are not the same book. The prefix is the cheapest possible reminder and survives every downstream join.

### D9 — This substrate is BACKTEST-ONLY and cannot serve live

Binance publishes the daily `metrics` dumps with a 1–2 day lag. Every feature here is computable for history and **none is available at live decision time from this source**. A live B2 would need an API path that does not yet exist. Recorded because "the harness is done" otherwise reads as "B2 is deployable", and it is not.

### D10 — The harness proves itself on known answers before any verdict counts

Per the loop's instrument discipline. Each is a test, not a claim:

- **A planted signal is recovered** — a synthetic OI series with a known z-score returns it.
- **A null series produces no signal** — constant input yields zero/undefined, never a finite spurious value.
- **Look-ahead is impossible** — recompute a feature at bar `T` with future rows appended and the value must be **bit-identical**. This is the guard for D2 and the one whose failure would be invisible in a plausible-looking result.
- **Nulls propagate** — a null ratio input yields a null feature, never 0.0.
- **The panel starts 2021-12-01** — asserted **as a data-gated test**, since it reads the substrate rather than a pure function: it belongs beside the `cli/derivatives/` substrate tests and skips where the mount is absent, so it runs locally and never in CI (`CLAUDE.md`). A future refresh that extends coverage therefore cannot silently move the panel start, but only a local run will say so.

## Out of scope

- **Liquidations.** Coinalyze covers only live liquidations; the historical leg is deferred and stays with [[T0023]].
- **The B2 family, its hypotheses, and any trial.** They come next, against this harness.
- **Live serving** (D9).
- **Tuning any window.** A tuned window is a trial.
