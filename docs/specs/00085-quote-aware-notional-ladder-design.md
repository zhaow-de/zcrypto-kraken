# Quote-aware notional ladder, and the /BTC spread calibration it unblocks

Resolves the [[T0092]] remainder. The panel's fill ladder is quote-denominated but EUR-labelled and EUR-scoped; the two `/BTC` universe legs have been captured since 2026-07-23 and cannot be calibrated until the ladder understands their quote. This spec makes the ladder quote-aware, recalibrates all twelve legs on one common window, and re-keys `SPREAD_CALIBRATION` from base to full symbol.

## Context

The `/BTC` legs (`ETH/BTC`, `SOL/BTC`) were added to capture on the owner's 2026-07-23 ruling because L2 is unbackfillable and the start date is the whole cost of waiting. Their book runs **330 hourly segments on each leg, contiguous with no gaps** — genesis hour 2026-07-23 13:00Z through 2026-08-06 06:00Z, measured on the pulled copy; the tail is pull lag, not loss. That is 13.7 days spanning two weekends: the ≥2-week trigger completes at 2026-08-06 13:00Z, before any number is fitted, since the calibration (D4) runs after the ladder is built and regenerated. The design work is not gated on it; the fitted window is.

What blocks the calibration is not the data but the ladder. `NOTIONALS_EUR = (100.0, 1_000.0, 10_000.0)` (`cli/panel/primitives.py`) is walked as `price × qty`, which is denominated in the pair's **quote** currency. On a BTC-quoted pair those rungs read as 100/1k/10k **BTC** — the @100 rung alone asks roughly 10× `ETH/BTC`'s and 25× `SOL/BTC`'s entire daily volume, so `_fill_bps` returns `None` on insufficient depth and all six `fill_bps_*` columns go null. The panel is therefore scoped to `PANEL_QUOTE = "EUR"` and the calibration query reads `<BASE>/EUR/**` by design.

The harm today is a dead ladder and an out-of-scope tree, **not a wrong number** — the guards hold. The harm this spec prevents is the one that appears if the guards are lifted in the wrong order: `_refresh_universe` looks up `SPREAD_REFERENCE_NOTIONAL_EUR` (€1,400) against a BTC-denominated ladder, gets a plausible large bps, and rejects a universe member for fake illiquidity.

## Decisions

### D1 — BTC rungs are EUR-equivalent at a pinned FX reference

The per-quote ladder holds, for BTC, the BTC quantities whose value equals €100 / €1,000 / €10,000 at a **pinned BTC/EUR reference** derived from this repo's own `BTC/EUR` panel mids over the calibration window (D4), stored as a provenance-stamped constant beside the ladder.

Rejected: round BTC quantities (0.001/0.01/0.1 BTC). Clean labels, but the rungs drift from EUR-equivalence as BTC/EUR moves, the €1,400 lookup needs an FX conversion at read time anyway, and `_PINNED_SIZES` would have to become per-symbol — the FX question returns downstream instead of being settled once, here, with provenance.

Rejected: per-hour FX-converted rungs. Most faithful, but it breaks fixed column identity and the generation manifest's fixed-notional semantics.

**Consequence that makes D1 cheap:** because the rungs remain EUR-equivalent, `SPREAD_CALIBRATION`'s inner keys stay the EUR notionals, `_PINNED_SIZES` stays one shared grid, and `effective_spread_bps(symbol, notional_eur)` keeps its signature. Spread values are dimensionless bps; the inner key names a grid point, not a currency amount in the quote.

### D2 — Column names are unchanged; the ladder lives in the meta

`fill_bps_{bid,ask}_{100,1k,10k}` keep their names, with per-quote meaning. The per-quote ladder is recorded in `panel-meta.json`.

Renaming columns per quote would break the uniform shape the calibration query depends on, for no gain. The meaning is recoverable from the meta, which is where generation identity already lives.

### D3 — `SPREAD_CALIBRATION` is keyed by full symbol

Keys become `"BTC/EUR"`, …, `"ETH/BTC"`, `"SOL/BTC"` — twelve rows. `cli/data/rebuild.py` passes the full symbol, and its quote guard (`symbol.split("/")[1] == "EUR" and base in SPREAD_CALIBRATION`) collapses to plain membership.

This was already ruled and predates this branch: a base-keyed table returns the EUR row for `"ETH"` while raising for `"ETH/BTC"`, so the current shape's failure mode is a silently wrong value. Re-keying converts it to a loud one. `round_trip_cost` (no callers outside tests) inherits that for free.

### D4 — One common calibration window for all twelve rows

Recalibrate every row over a single new window: **first full hour after the `/BTC` genesis** (2026-07-23 14:00Z, the genesis hour being partial and annotated-not-booked) through the last settled hour available at execution time. Uniform provenance; `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS` survive as single module constants with their single test pins.

The EUR values will move slightly — T0091's restamp precedent moved them under 2 %. That is a deliberate, documented restamp, which the recalibration discipline permits: table, provenance constants, and `docs/reference/captured-spread-calibration.md` move together.

Rejected: keeping the EUR rows on their old window and adding `/BTC` rows on their own. It preserves the exact numbers T0024's measured effect cites, at the cost of turning three module constants into per-symbol structures and leaving two windows to explain forever.

**Named caveat for the restamp:** Kraken's first observed venue maintenance (2026-08-06 07:01–07:18Z) falls inside this window. The venue emitted nothing, neither daemon restarted, and no archive gap was booked — but those ~17 minutes are panel seconds computed off a frozen book, and the mean includes them. This is the same shared-gap class as the EUR table's existing 0.602 % caveat and is recorded the same way, not silently averaged in.

### D5 — The calibration query becomes committed, runnable code

The current provenance is a polars query living only as prose in `docs/reference/captured-spread-calibration.md`. This iteration must run it for twelve rows now and again at every future restamp, so it ships as a small committed script producing the table and the three provenance constants.

This closes, for this dataset, the execution-reproducibility gap [[T0065]] already names: a hash recipe or calibration that exists only in prose is not reproducible from committed code.

### D6 — Guard-lift order is load-bearing

The EUR scope guards lift in this iteration: the sweep's `pairs_out_of_scope` skip, the non-EUR `--pair` refusal, the stray-out-of-scope abort in `_check_generation`, and the `_affected_pairs` filter.

`cli/data/rebuild.py`'s quote guard lifts **only with the re-key**, after the ladder is live and the table has `/BTC` rows. Lifting it earlier feeds €1,400 into a BTC-denominated ladder and fake-rejects a universe member. This ordering predates the branch and is not reopened here.

### D7 — The universe rebuild is NOT run

This iteration changes what a rebuild *would* read. Running `_refresh_universe` is [[T0025]]'s single execution, inside the attended cluster T0092 → [[T0093]] → T0025 → [[T0024]]. Nothing here regenerates the universe artifact.

### D8 — Review floor is Opus, by owner ruling

`spec-plan-locations.md` would put the Fable floor on this iteration through its canonical-data arm. The owner ruled **Opus floor, no Fable**, for the cold spec+plan review and every review in this iteration. Recorded here so the floor does not silently revert on a later reading.

The ruling is defensible on the facts: the live engine imports none of this (its cost basis is the frozen `spread_per_side = 0.0020`, carrying an explicit do-not-correct comment), and D7 keeps the canonical universe artifact unwritten this iteration.

## Rollout

The panel's generation dict contains `notionals_eur`, so **any** ladder change triggers `_check_generation`'s refusal even without a `SCHEMA_VERSION` bump; a column-set change would additionally demand the bump. Either way a whole-tree regeneration is owed.

**Paths do not change.** Quote is already a path level (`<BASE>/<QUOTE>/panel-1s/...`), so the `/BTC` subtrees are additive and nothing is orphaned. This is the first real exercise of the regeneration checklist rewritten on 2026-08-06, whose stated rule — "a schema or ladder bump forces a regeneration but rewrites identical paths, so it orphans nothing" — this iteration puts to the test rather than trusting.

Order: build and review → ops image → ops converge → attended `zcrypto-panel-regenerate` (healthchecks pause as a typed gate, ETA-vs-02:25 refusal, `-e ops_panel_timer_hold=true` on any converge during the window) → calibrate from the **pulled** copy once the 7 h settle admits the full window → re-key → docs rewrite.

## Verification

- The ladder: a BTC-quoted pair produces non-null `fill_bps_*` for rungs its book can actually fill, and the pinned FX reference reproduces from the committed script.
- The scope lift: each of the four lifted guards has a test that fails against the pre-lift behaviour, and `rebuild.py`'s guard is proven *still closed* until the re-key step.
- The re-key: `effective_spread_bps("ETH/BTC", 1_400)` returns a number where it previously raised; `entries["ETH/BTC"]` in the rebuild test inverts from `None` to a value, and `unevaluated_count` goes 1 → 0.
- The restamp: the three provenance constants match what the committed script emits for the window it was run on — asserted, not transcribed.
- Every guard proven by construction through `infra/scripts/mutate-probe.sh`, never asserted.

## Out of scope

- Running the universe rebuild (D7 — [[T0025]]).
- Re-deriving the 10 bps/side cap or the €1,400 reference position (ruled, iter-115).
- The statistic and interpolation shape (ruled, iter-114): mean effective spread at traded notional, no session term, log-notional interpolation with clamp-below and refuse-above.
- Any change to the live engine's frozen cost basis.

## Known drift to re-resolve during implementation

Every code citation in T0092's closeout list has drifted since it was written. The docs rewrite resolves targets **by content**, not by the topic's line numbers — the quote guard, the "no capture" sites in `cli/data/rebuild.py`, `cli/universe/rules.py`, `cli/universe/build.py` and their tests, `docs/reference/data-catalog-full.md`'s scope clause, and `captured-spread-calibration.md`'s scope and query sites.
