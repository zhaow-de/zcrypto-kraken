# Universe spread-cap criterion — design (T0024)

**Status:** ratified by the 2026-07-22 `/zcrypto-auto-exec` run (approval gates pre-satisfied by the invocation; decisions recorded here and in `docs/research/02.phase1-decisions.md` — universe selection is Phase-1 data-foundation subject matter, spec `00003`).

## Goal

Retire `spread_cap: "pending-capture"` from the point-in-time universe. Selection currently filters on margin + leverage + median quote volume only, so a thin-book pair can clear the €150k/day volume floor and still be untradeable at our sizing. [[T0014]] (spec `00066`) has now calibrated per-pair effective spread from our own L2, so the criterion has data — "one derivation, two consumers", as the topic put it.

## D1 — Which spread, at which size

Reuse `cli.costs.spread.effective_spread_bps` directly rather than re-deriving from the panel. Two consequences worth stating:

- **The statistic is the mean effective spread at size, not the median top of book.** [[T0014]] measured that BTC/EUR's median is unusable (tick-quantised, mean ÷ median 11.2×). A selection filter built on the median would rank pairs by an artifact of where each sits relative to its tick floor. The topic's own wording asked for "median/percentile top-of-book spread"; that is superseded by the same measurement that superseded it for the cost model.
- **The reference size is €1,400** — not an arbitrary round number. It is the max-size position the *existing* volume floor is already calibrated against (`rules.py`: "a full max-size position (~€1,400 at ~$10k, ≤1.5× gross, ~12 names) ≈ 1 % of median daily EUR volume"). Using the same position for both criteria keeps them commensurable: they answer "can we trade this at our size?" from two different directions.

## D2 — The cap: 10 bps per side, and it binds on nothing today

Derived, not tuned. At the €1,400 reference the round-trip spread must not exceed **~25 % of the tier-1 round-trip maker fee** (2 × 0.40 % = 80 bps) — i.e. 20 bps round trip, **10 bps per side**. Beyond that the spread stops being a rounding error on the fee stack and starts being the dominant cost, which is what "untradeable at our sizing" means in practice.

Measured at €1,400, every current member passes, DOT worst:

| | BTC | ETH | SOL | XRP | DOGE | LINK | ADA | AVAX | LTC | **DOT** |
|---|---|---|---|---|---|---|---|---|---|---|
| bps/side | 0.43 | 0.52 | 1.15 | 1.26 | 2.11 | 2.48 | 2.87 | 3.33 | 3.35 | **6.55** |
| % of RT fee | 1.1 | 1.3 | 2.9 | 3.2 | 5.3 | 6.2 | 7.2 | 8.3 | 8.4 | **16.4** |

**The criterion excludes nothing today, and that is the honest outcome rather than a failure.** A cap tuned tight enough to bite on the current universe would be fitting the rule to the data it is meant to judge; DOT keeps ~35 % headroom under a cap derived from the fee stack. This is a **guard for future refreshes** ([[T0025]]'s pre-live universe refresh re-runs selection), not a filter that changes today's twelve names.

An absolute bps cap is used rather than a live-tier-relative one: at the top fee tiers maker → 0 %, and a "25 % of the maker fee" rule would degenerate to a cap of zero and reject everything. The 25 % figure is the *derivation* of the constant, not a formula evaluated at runtime.

## D3 — A pair with no capture is recorded as unevaluated, never auto-failed

**Two of the twelve selected symbols have no L2 capture at all.** The capture daemon subscribes to EUR-quoted pairs only (`/mnt/zhao-crypto/capture-reconciled/<BASE>/EUR` — verified: every base has `EUR` and nothing else), so `ETH/BTC` and `SOL/BTC` — both real universe members — have no spread data.

Absence of evidence is not evidence of a wide spread, so an uncaptured symbol is **not** rejected. It is recorded as `spread_bps: null` on its entry, which makes the gap visible in the artifact every reader consults rather than hiding it in a comment. Rejecting them would drop two members on a data gap; silently exempting them without the null would let a future reader believe all twelve were screened.

The gap itself is registered as [[T0092]] — the capture set would have to grow before the criterion can cover the whole universe, and that is a capture-config decision with its own cost (two more subscriptions on an unbackfillable pipeline), not something this spec can settle.

## D4 — Backward compatibility

`finalize_universe(..., spreads=None)` applies no spread criterion and produces byte-identical output to today. Existing callers and every existing test are unaffected; the criterion activates only when a caller passes a spread map. `build_universe_file` emits the structured `spread_cap` record in place of the `"pending-capture"` string.

## Out of scope

- **Re-running the live universe build.** `_refresh_universe` calls `fetch_public("AssetPairs")`; a rebuild is a network operation against Kraken and a canonical-dataset write. The selection outcome is instead determined offline from the stored refdata snapshot and reported here.
- Any change to the volume floor, the mandatory-pair rule, or the min/max name bounds.
- The BTC-quoted legs' spreads (D3) — they need capture, not analysis.
