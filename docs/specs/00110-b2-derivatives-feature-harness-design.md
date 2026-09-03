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

### D5 — Dense columns are dense; ratio columns propagate null; a zero OI is not a level

`sum_open_interest*` are complete — **measured, zero nulls in all ten symbols**. The four ratios are nullable, and any feature derived from them yields null where its input is null. **No imputation** — filling a missing ratio with zero or the trailing mean manufactures a reading the venue never published.

**Zero is not null, and in `sum_open_interest*` it is not a reading either.** Measured 2026-09-03 across all ten `oi.parquet` files: `sum_open_interest` is exactly `0.0` on **2,329 rows** (BTCUSDT 502, ADAUSDT 229, DOGEUSDT 225, LINKUSDT 216, DOTUSDT 212, ETHUSDT 208, SOLUSDT 197, XRPUSDT 196, LTCUSDT 176, AVAXUSDT 168) and `sum_open_interest_value` on **2,430**, every symbol represented in both. **The two sets NEST rather than coincide**: every `sum_open_interest` zero carries a `sum_open_interest_value` zero on the same stamp, and **101 further rows** read a zero notional against a healthy positive `sum_open_interest` — one incident, 2023-04-10 08:25→09:40 UTC, simultaneous across all ten symbols. A count or a guard written for one OI column is therefore not written for the other.

**What produced the zeros is NOT established, and the ruling does not rest on it.** Binance publishes no gap flag, and the account-ratio columns do **not** corroborate: of the 2,329 rows, **zero** have all four ratio columns null and only **338** have the three account ratios null, so **1,991 carry at least one non-null account ratio**. BTCUSDT's first zero row (2021-05-22T04:25Z — both OI columns `0.0`, the three account ratios `null`, the bar before reading `26167.781`) is one of the 338, not the population's shape. **So no detection may key on the ratios being absent; the predicate is `sum_open_interest == 0.0` (or `sum_open_interest_value == 0.0`) alone.** What the shape does show is that these are not ten books independently emptying: the zeros arrive in 647 runs, 497 of them a single 5-minute bar, and the longest — 116 consecutive bars, 2022-03-07T15:30→2022-03-08T01:05Z — is identical across all ten symbols. A perp with zero open interest is not a market.

**So a `0.0` in `sum_open_interest*` maps to `None` before anything treats it as a level** — and the reason is arithmetic, not provenance: a zero level is unusable whatever wrote it, because `oi_log_delta` would take `log(0)` and `oi_momentum` would divide by it — **while `oi_zscore` would do neither: it would score the zero as an ordinary observation and publish a finite, plausible, extreme reading computed on a venue artefact, with nothing raising.** That third case is the dangerous one, and it is the function this plan calls load-bearing; so the choice is between mapping it to `None` and letting real substrate rows raise. Mapping is the opposite of imputation: it removes a reading rather than inventing one. This spec and its plan call such a zero a **venue hole** — shorthand for *a zero in a level column that cannot be used as a level*, naming the effect rather than a confirmed venue incident. The OI validator therefore stays strictly positive, and a `0.0` reaching it is a caller that skipped the mapping, not a data shape to accommodate.

**`sum_taker_long_short_vol_ratio == 0.0` is the opposite case and must be ACCEPTED.** 45 rows carry it, and not one of them sits on a zero-OI bar (measured: 0 of 45 coincide) — an all-sell 5-minute bar is a real reading. The other three ratio columns carry no zeros at all. The ratio family is therefore validated as **finite or null**, never as positive: gating it on the OI validator would reject 45 rows the venue did publish.

**And the gaps are not where the catalog says.** `data-catalog-full.md` **called** them an *early metrics* artifact. Measured 2026-09-02 and re-verified 2026-09-03, they are **one year, and panel-wide**: `count_toptrader_long_short_ratio` is **87.3 % null across 2022 for nine symbols and 87.0 % for XRPUSDT** — 91,733 of 105,120 rows missing, identically — and ~0 % in every other year. Within 2022 the first present row is 2022-01-30; read absolutely the column is populated from each series' first row, so the hole is 2022-scoped and not a late start. **Panel-wide null is 18.4 %** (921,890/5,010,882); BTCUSDT's 14.9 % is the lowest only because 15 extra months of dense history dilute it, so quoting BTC's rate understates the panel. **The four ratios differ by an order of magnitude, and the difference lives inside 2022**: measured panel-wide over 2022's 1,051,199 rows, `count_toptrader_long_short_ratio` and `sum_toptrader_long_short_ratio` are each **87.24 %** null, `sum_taker_long_short_vol_ratio` **35.03 %**, and `count_long_short_ratio` **5.09 %** — so `count_long_short_ratio` is 94.9 % *present* through 2022 and is the one ratio usable across that regime. Quoting one figure for "the ratios" overstates the hole 17× for it. (Read whole-series on BTCUSDT the same contrast is 0.9 % against 14.9 %.) **A feature on the toptrader ratios is therefore blind through 2022** — the bear market and the FTX collapse, which is the regime a de-risking family exists for. A trial reading a Sharpe off that column would compute it on a sample silently missing its most informative year, and a CPCV fold covering 2022 would be near-empty. The catalog said otherwise and was corrected in this spec's own commit (`523a4034`), so a reader checking `data-catalog-full.md` now finds the corrected text, not the claim this paragraph refutes.

### D6 — Every emitted feature carries its coverage, and a trial cannot run blind to it

D5 makes the 2022 hole real rather than hypothetical, so the harness does not leave a consumer to discover it. Each feature frame is emitted with a per-column coverage summary — non-null count, first and last non-null timestamp, and the null fraction **per calendar year** — because a single overall figure hides exactly this shape: 14.9 % null reads as a nuisance, 87.3 % in one year reads as a missing regime. A downstream trial that ignores it is a choice someone made; a trial that could not see it is an instrument defect.

**This spec delivers the summary; the emission that carries it lands with the family.** The harness is pure functions on lists — no frames, no I/O — so what ships here is `coverage_by_year`, returning per calendar year the non-null count, the total, and the **first and last non-null timestamp** (the null fraction follows from the first two, so it is derived rather than stored). Reading the substrate into lists and shipping the summary alongside the frame is `## Out of scope` and registered on [[T0023]]. The summary's *shape* is fixed here so the family cannot narrow it later: a count alone cannot separate a late start from an interior outage, and that is the distinction deciding whether a 2022 CPCV fold is unusable or merely thin.

### D7 — Feature families, all per-asset

- **funding**: z-score over a trailing window of prints; sign persistence (consecutive same-sign prints); accrued carry over a trailing window.
- **OI**: log-delta; momentum over a trailing window; z-score.
- **ratios**: the four Binance ratios carried through, null-propagating.

**The level is `align_asof`'s output, not a separate feature.** An earlier draft listed `level` first in both families; a pass-through over the as-of aligned series is the identity function, so the aligned series **is** the level and no `funding_level` / `oi_level` is built. For OI the aligned input is the hole-mapped series (D5): the raw `0.0` placeholders become `None` first.

**Windows are pre-registered here, in days, so they are grid-independent and fixed before any result is seen: 30 d for every trailing window** (funding z-score and accrued carry ≈ 90 prints; OI z-score and momentum = 720 bars at 1h, 180 at 4h). The number is a pre-registration, not an optimum — nothing here justifies 30 over 20 or 45, and that is the point: **changing it after seeing a result is a new trial and spends budget.** Sign persistence takes no window; it counts consecutive same-sign prints.

**The window's semantics are pinned here, because leaving them open made the plan's own thresholds unfalsifiable.** A trailing window at index `k` is the `window` observations **ending at and including `k`** — inclusive, because the observation at `k` is knowable at bar close `k` and excluding it is a different feature, not a safer one. Dispersion is the **sample** standard deviation (`ddof=1`). A z-score is `None` where the window is not yet full or where any member is `None`, and **`0.0` where the window has zero variance** — a constant series is not extreme. Under these rules a single observation eight base units above nine identical ones scores **2.8460498941515410**, not `3.0`; the population form gives exactly `3.0` and the exclusive form is undefined. Any test asserting a threshold must use the pinned definition's value.

**An undefined window yields `None`, never `0.0` — and that is a different rule from null propagation.** A null *input* yields a null output (D5); a *window that is not yet full* also yields `None`, so the head of every windowed output is `None` up to the warm-up. Stated because the in-repo template invites the other answer: `cli/features/momentum.py` fills its warm-up with `0.0` because it returns plain floats. These return `float | None`, and a `0.0` z-score does not mean "unknown" — it means *exactly average*, which is the reading a de-risking trigger acts on as safe. Thirty days of manufactured calm per symbol is the failure this sentence exists to prevent, and `coverage_by_year` cannot flag it either, because `0.0` is not null.

**A zero funding print is its own sign.** 659 of the 68,281 realized-funding prints are exactly `0.0` (measured 2026-09-03; the column has no nulls). Sign persistence counts consecutive prints sharing a sign drawn from `{-1, 0, +1}`, so a zero breaks a positive run and starts its own run at 1. Left open, the counter is implementation-defined at 659 real prints — `v > 0` and `v >= 0` and a three-way sign each give a different answer there and no dense fixture can separate them.

**Output length is `len(input)`, not `len(input) - 1`.** The existing `cli/features/` functions return `len(prices) - 1` because they align to `returns_from_prices`; these align to the **input grid** — a level, a delta, a coverage row — so they return one value per input stamp with `None` where undefined. Stated because "match the existing convention" would otherwise import the wrong one.

### D8 — Every feature name carries its venue

[[T0023]] requires the venue gap to be carried explicitly, and a column called `oi_zscore` sitting beside Kraken spot columns invites a reader to assume it is Kraken's. Every emitted column is prefixed `binperp_` — the features describe **Binance USDT-M perpetuals**, mapped to Kraken bases through `PERP_SYMBOLS`, and the two venues' books are not the same book. The prefix is the cheapest possible reminder and survives every downstream join.

### D9 — This substrate is BACKTEST-ONLY and cannot serve live

Binance publishes the daily `metrics` dumps with a 1–2 day lag. Every feature here is computable for history and **none is available at live decision time from this source**. A live B2 would need an API path that does not yet exist. Recorded because "the harness is done" otherwise reads as "B2 is deployable", and it is not.

### D10 — The harness proves itself on known answers before any verdict counts

Per the loop's instrument discipline. Each is a test, not a claim:

- **A planted signal is recovered** — a synthetic OI series with a known z-score returns it.
- **A null series produces no signal** — constant input yields zero/undefined, never a finite spurious value.
- **Look-ahead is impossible** — recompute over a **truncated prefix**: for every prefix length `n`, `f(x[:n], **kw)` must equal `f(x, **kw)[:n]` element-for-element. This is the guard for D2 and the one whose failure would be invisible in a plausible-looking result. Two things it is not. It is **not** the appended-future form ("append rows past the end, assert unchanged"), which a backward-fill defect passes as readily as the correct implementation — measured on both arms, which is why the truncating form replaced it. And it is **not** an assertion on `out[-1]`: at the final index a window that peeks one bar ahead *clamps* to the correct window, so a `[-1]`-only assertion passes under look-ahead. **Every function that computes over a window carries this property, not just the alignment helper** — one inert or absent instance is a look-ahead shipped green.
- **Nulls propagate** — a null ratio input yields a null feature, never 0.0.
- **The panel starts 2021-12-01, and the venue holes are counted** — asserted **as a data-gated test**, since it reads the substrate rather than a pure function: it belongs beside the `cli/derivatives/` substrate tests and skips where the mount is absent, so it runs locally and never in CI (`CLAUDE.md`). **The gate is the canonical root, which is the NFS mount, not `data/`** — `data/derivatives-oi` is absent from the workstation's data root, so a test gated on it would skip everywhere and the skip would be recorded as coverage. The same test counts D5's zero rows over a closed past window — **both** OI columns, because D5's two zero sets nest rather than coincide and a guard on one is blind to the other's 101 extra rows — so a refresh cannot move the hole count silently either. A skip is not a pass: the gate is proven only by running it once with the mount present and reading `passed`.

## Out of scope

- **Liquidations.** Coinalyze covers only live liquidations; the historical leg is deferred and stays with [[T0023]].
- **Substrate→feature emission.** Reading `read_funding_series` / `read_oi_series` frames into the lists these functions consume, building the 1h/4h grid of D3, and shipping each feature frame with its `coverage_by_year` summary (D6). The harness is pure functions; this glue lands with the B2 family and is **registered as a next step on [[T0023]]**, because a deferral whose only home is prose is not tracked.
- **The B2 family, its hypotheses, and any trial.** They come next, against this harness.
- **Live serving** (D9).
- **Tuning any window.** A tuned window is a trial.
