# Universe spread-cap criterion — design (T0024)

**Status:** ratified by the 2026-07-22 `/zcrypto-auto-exec` run (approval gates pre-satisfied by the invocation; decisions recorded here and in `docs/research/02.phase1-decisions.md` — universe selection is Phase-1 data-foundation subject matter, spec `00003`).

## Goal

Retire `spread_cap: "pending-capture"` from the point-in-time universe. Selection currently filters on margin + leverage + median quote volume only, so a thin-book pair can clear the €150k/day volume floor and still be untradeable at our sizing. [[T0014]] (spec `00066`) has now calibrated per-pair effective spread from our own L2, so the criterion has data — "one derivation, two consumers", as the topic put it.

## D1 — Which spread, at which size

Reuse `cli.costs.spread.effective_spread_bps` directly rather than re-deriving from the panel. Two consequences worth stating:

- **The statistic is the mean effective spread at size, not the median top of book.** [[T0014]] measured that BTC/EUR's median is unusable (tick-quantised, mean ÷ median 11.2×). A selection filter built on the median would rank pairs by an artifact of where each sits relative to its tick floor. The topic's own wording asked for "median/percentile top-of-book spread"; that is superseded by the same measurement that superseded it for the cost model.
- **The reference size is €1,400** — not an arbitrary round number. It is the max-size position the *existing* volume floor is already calibrated against (`rules.py`: "a full max-size position (~€1,400 at ~$10k, ≤1.5× gross, ~12 names) ≈ 1 % of median daily EUR volume"). Using the same position for both criteria keeps them commensurable: they answer "can we trade this at our size?" from two different directions.

## D2 — The cap: 10 bps per side, and it binds on nothing today

Anchored to the fee stack rather than tuned to the data. At the €1,400 reference the round-trip spread must not exceed **25 % of the tier-1 round-trip maker fee** (2 × 0.40 % = 80 bps) — i.e. 20 bps round trip, **10 bps per side**. At that point spread has stopped being a rounding error on the fee stack. It is not yet the *dominant* cost — at the cap spread is 20 % of the 100 bps round trip, and dominance would need ~40 bps/side; the 25 % is a chosen convention, stated as such rather than dressed as a derivation.

At €1,400 every current member passes, DOT worst. These are **log-notional interpolations between the calibration table's €1k and €10k anchors, not measurements at €1,400** — the calibration has no €1,400 column. They carry the stamp of the calibration behind them (`CALIBRATION_WINDOW` 2026-07-08T13:47:33Z … 2026-07-21T15:59:59Z, 315 h); a recalibration ([[T0091]]) moves every number in this table, so it must be re-derived rather than assumed still current:

| | BTC | ETH | SOL | XRP | DOGE | LINK | ADA | AVAX | LTC | **DOT** |
|---|---|---|---|---|---|---|---|---|---|---|
| bps/side | 0.43 | 0.52 | 1.15 | 1.26 | 2.11 | 2.48 | 2.87 | 3.33 | 3.35 | **6.55** |
| % of RT fee | 1.1 | 1.3 | 2.9 | 3.2 | 5.3 | 6.2 | 7.2 | 8.3 | 8.4 | **16.4** |

**The criterion excludes nothing today, and that is the honest outcome rather than a failure.** A cap tuned tight enough to bite on the current universe would be fitting the rule to the data it is meant to judge; DOT keeps ~35 % headroom on the mean. That headroom is a statement about the mean only: DOT's per-second distribution over the same window runs p90 8.35 / p95 9.25 / **p99 10.87**, with 2.54 % of seconds above the cap. Pricing on the mean is deliberate — it is the statistic the cost model charges — but "binds on nothing" is true of the mean, not of the tail. This is a **guard for future refreshes** ([[T0025]]'s pre-live universe refresh re-runs selection), not a filter that changes today's twelve names.

An absolute bps cap is used rather than a live-tier-relative one: at the top fee tiers maker → 0 %, and a "25 % of the maker fee" rule would degenerate to a cap of zero and reject everything. The 25 % figure is the *derivation* of the constant, not a formula evaluated at runtime.

## D3 — A pair with no capture is recorded as unevaluated, never auto-failed

**Two of the twelve selected symbols have no L2 capture at all.** The capture daemon subscribes to EUR-quoted pairs only (`/mnt/zhao-crypto/capture-reconciled/<BASE>/EUR` — verified: every base has `EUR` and nothing else), so `ETH/BTC` and `SOL/BTC` — both real universe members — have no spread data.

Absence of evidence is not evidence of a wide spread, so an uncaptured symbol is **not** rejected. It is recorded as `spread_bps: null` on its entry, which makes the gap visible rather than hiding it in a comment. Rejecting them would drop two members on a data gap; silently exempting them without the null would let a future reader believe all twelve were screened.

**Where that null is actually visible, precisely:** in the universe **JSON**, which `_refresh_universe` writes and which is the file `cli/capture/command.py` reads. `cli.universe.render_markdown` also renders it as a table cell, but that function has **no production caller** — the committed `docs/universe/point-in-time-universe.md` is hand-authored and is regenerated by hand at the next rebuild. So "visible in the artifact every reader consults" overstates it until the renderer is wired; the JSON is the delivered surface.

The gap itself is registered as [[T0092]] — the capture set would have to grow before the criterion can cover the whole universe, and that is a capture-config decision with its own cost (two more subscriptions on an unbackfillable pipeline), not something this spec can settle.

## D4 — Backward compatibility

`finalize_universe(..., spreads=None)` applies no spread criterion: the **selection outcome** — `selected`, `escalate`, every `reasons` list — is unchanged for existing callers. Output is *not* byte-identical: every entry gains a `spread_bps` key (null on this path), unconditionally. Existing callers and every existing test are unaffected; the criterion activates only when a caller passes a spread map. `build_universe_file` emits the structured `spread_cap` record in place of the `"pending-capture"` string.

## Out of scope

- **Re-running the live universe build.** `_refresh_universe` is now *wired* for the criterion (it builds the spread map and passes the cap record), but calling it is a network operation against Kraken plus a canonical-dataset write — outside this run's boundary. The artifact carries `"pending-capture"` until that rebuild.
- Any change to the volume floor, the mandatory-pair rule, or the min/max name bounds.
- The BTC-quoted legs' spreads (D3) — they need capture, not analysis.

## How the "selection unchanged" result was obtained, and what it does not prove

Determined offline by replaying the stored `data/universe/point-in-time-universe.json` entries back through `finalize_universe`, once without the criterion and once with it.

**The replay is faithful, and that was checked rather than assumed**: without the criterion it reproduces the live file's `selected` tuple, its `escalate` flag **and every entry's `reasons` list** exactly. So the spread cap is the only variable between the two runs, which is what makes the comparison meaningful.

**The residual limit, stated plainly:** `max_leverage` and `median_quote_volume` are read *from* that output file, so this re-derives the same decision from the same inputs. It establishes that **adding the criterion changes nothing given those inputs** — the question T0024 asked. It does **not** establish that a fresh rebuild against today's Kraken refdata and updated volumes would select the same twelve.

**And it would not — measured, not assumed (2026-07-22).** Running `_refresh_universe`'s own volume path against the live `data/ohlc-full` gives **AVAX/EUR = 132,274.82 EUR/day, below the 150,000 floor** — a rebuild today selects **eleven** names, not twelve, for a volume reason that has nothing to do with this spec. Two things make that number untrustworthy as a liquidity statement, which is why it is a registered finding ([[T0093]]) rather than a universe change here: the committed artifact's provenance cites `ohlc_basket_sha256 407d2e…` from `data/ohlc/`, a directory that **no longer exists**, while `_refresh_universe` reads `data/ohlc-full/` (`70c272…`); and `ohlc-full`'s last daily bar is **2026-03-31**, so its trailing-30-day window is 2026-03-02…03-31 — roughly 3.5 months stale against the artifact's `as_of: 2026-07-07`. The "12 → 12" result in this spec is therefore scoped to the replay, and any claim about a *rebuilt* universe must wait for a refreshed `ohlc-full`.
