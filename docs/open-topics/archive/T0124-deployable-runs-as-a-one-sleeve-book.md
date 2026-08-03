---
status: resolved
---

# The deployable is operating as a one-sleeve book, and no document says so

## Context — what

Registry record 44 — the system Stage 6b would take live — is **three sleeves combined at fixed ⅓ weights**: B (record 33's daily `w·l3`, intraday-held), A1 (A1-lf weekly v0.12 offset-mean), and A2 (the equal-weight native-4h ensemble). Measured across all **136** journaled shadow cycles (2026-07-11 → 2026-08-02, spec `00081`'s attribution run): **B and A1 hold exactly zero in every cycle.** Only A2 carries exposure.

This is not a defect. Both sleeves were live for much of the backtest — B non-zero on **51.4 %** of its 28,079 rows, A1 on **57.0 %** — and each went flat and stayed flat: B last held a position around **2025-10-30**, A1 around **2025-11-09**. B sits behind a 200-day SMA gate that `13.phase5-holdout-ledger.md` already records as *"off since before April"*; these are long-only sleeves correctly sitting out a sustained downtrend.

What no document records is the **compound consequence**: because the combination is fixed ⅓ weights, a single live sleeve contributes one third of its own gross, and the governor then halves that. The book that would go live is structurally a **one-sleeve book at ⅙ of that sleeve's gross**, not the diversified three-sleeve system whose Sharpe, drawdown and stress figures were registered.

## Why this matters

Three consequences, none of which the go/no-go currently sees:

- **The validated object and the operating object differ in structure, not just in parameters.** Record 44's registered figures (net-of-cost Sharpe 1.5609, maxDD 13.57 %, the ×1.5/×2 stress results, the SPA grid) were earned by a three-sleeve combination. A one-sleeve realization has different risk characteristics, and record 44's diversification thesis — the reason ⅓/⅓/⅓ was adopted over a single sleeve — is dormant in exactly the regime the sleeve would go live in.
- **It is the mechanism behind the placeability problem**, which was previously attributed only to sizing. The chain measured per cycle: A2 alone at **32.2 %** median gross → ÷3 by the fixed weights → **10.7 %** combined → position caps bind on **0 of 136** cycles → ×0.5 governor → **5.37 %** final. That ~5 % is why 0 of 801 intended orders cleared Kraken's minimums at tiny-live size ([[T0116]]).
- **Nothing observes it.** No metric, alert, or report states how many sleeves are contributing. The condition arrived ~9 months ago and was found only because a measurement iteration happened to decompose the book; it could equally reverse — B and A1 re-arming would roughly triple gross without anything announcing that either.

## Findings so far

- Measured 2026-08-02 by `zcrypto engine decompose` over the full journal (spec `00081`): sleeve→combined ratio **1.000** on every cycle — trivially, because two of three sleeves are zero, so there is nothing to cancel. The iteration's own spec had predicted sleeve *disagreement* as the likely mechanism; that hypothesis is refuted, and the real answer is dormancy.
- Per-sleeve backtest occupancy and last-non-zero rows above are from `build_crossfreq_system_fast` on the newest journaled cycle's snapshots (28,079 rows).
- Both known pieces were already recorded separately — the 200-day gate being off (holdout ledger) and the governor entering live at ×0.5 ([[T0018]]). Neither document draws the consequence for the live book's composition, and A1's dormancy is recorded nowhere.
- The governor's ×0.5 is itself carried from the 2025 drawdown, so two independent regime facts are compounding.

## Done so far

- **The quantification (2026-08-02, feeding the ruling below; refined by review the same day).** Conditioning the record's own backtest on live-observable sleeve state (positions are known every bar — a regime filter, no look-ahead; the construction is proven to be the registered one, since truncating to the registered window reproduces Sharpe **1.5609** exactly). The one-sleeve state (B and A1 both zero) covers **38.6 % of the registered validation window**, 40.3 % of the extended 28,079-bar backtest — the 742 post-registration bars are *all* one-sleeve, which is also why the current contiguous stretch reads **8.7 months**. **A first cut put the conditional Sharpe at 0.47, and review showed that number was diluted**: a third of the one-sleeve bars (3,811 of 11,307) have **A2 flat too** — a no-position state the live book is not in (its standalone Sharpe is −4.88, the fee cost of prudent non-participation). Conditioned on the **actual live state** (B, A1 flat; A2 active): governed Sharpe **0.63** on the extended window, **0.75** on the registered window, against **1.94** multi-sleeve. **The interval matters more than the point**: IID SE ≈ 0.44, so the 95 % CI spans zero; the *state-dependence* is solid (disjoint samples, difference ≈1.5 ± 0.6), the point value is not. The honest baseline is **roughly 0.5–0.75 with a CI spanning zero — the gate must be written as a band, never a point comparison**. Drawdown, on real paths only: worst contiguous one-sleeve episode **4.25 %** maxDD; the current 8.7-month stretch realized **−4.20 %**. (A stitched-subset maxDD is larger but describes an equity path that never existed, and is not cited.)
- **The ruling (owner, 2026-08-02): PROCEED KNOWINGLY — rung 3 goes live on the book as-is**, on the reasoning that the one-sleeve state is a *normal state of the validated system* (40.3 % of its own validation window), the dormant sleeves cost nothing to carry (zero positions, zero turnover) and re-arm mechanically, the 22-day concordance streak describes exactly this book, and 6b proves execution rather than alpha. Waiting was rejected as an unbounded market-coupled delay; re-assembling around A2 was rejected as regime-chasing (dropping sleeves *because* they are currently flat is selecting on recent state — the anti-pattern T0019's fixed weights were adopted against) that would also discard the concordance evidence and force a re-gate. **Three conditions attach**, recorded in [[T0116]] where the amendment is written: (1) the go/no-go's model-consistency baseline is the **conditional live-state expectation — roughly 0.5–0.75 with a CI spanning zero, written as a band, never a point** — and never the 1.56 headline, against which a perfectly-executing 6b reads as a ~60–70 % shortfall and could false-fail the gate; (2) the amendment states the structural divergence explicitly; (3) the sleeve-occupancy gauge below lands **before rung 3**, so a re-arming — which roughly triples gross and moves both the band and placeability — is announced, not discovered.

- **The gauge is BUILT (2026-08-02, commit `193b2043`) — it did not need to wait for [[T0018]].** The plan had it riding the executor's metrics families; in fact the engine already serves `/metrics` with its own instrument set, so it shipped standalone the same day the ruling landed. What exists: `zcrypto_engine_sleeve_gross{sleeve}` and `zcrypto_engine_active_sleeves`, set from the builder result every cycle; the keep-list entry (guard-proven — without it the published-vs-admitted test fails naming both families); alert `zcrypto-engine-sleeve-count-changed` (`changes(...[26h])`, warning, `noDataState: OK`) with its runbook section. Two honesty properties are structural, not incidental: **zero series are published before the first cycle** (the labelled family is silent until `.labels()`, the unlabelled one registers lazily — a fresh Gauge's `0.0` would claim "no sleeves active", which is a claim, not an absence), and a failed cycle leaves both families untouched rather than zeroing them. Review proved the cycle path cannot be broken by this (the builder's own arithmetic already consumes every value the extraction reads) and caught that the extraction had **no end-to-end coverage** — a wrong row index passed all 81 tests and would have shipped a false "book is flat"; now pinned with a negative sleeve position so the index *and* the `abs()` both discriminate.

## Resolution

**Shipped and verified by value, 2026-08-03. The rung-3 precondition is discharged.**

The gauge went live on the engine converge to `c7ed09020fe1` (2026-08-03 04:45:41Z, read from the container's `.State.StartedAt`, not the converge command's return time). The image was canary-baked as *capture* on `zcrypto-red` first — there is no engine secondary, so that bake is the engine's gate — with the prune taking the **strong** form (`deleted=720`), 36 of 36 book streams beginning at `:00:00.0x` across three rotation hours, and red's RSS settling **below** its own old-image steady state (136.4 MB vs 150.0 MB, −9.1 %). The naive comparison would have triggered a false rollback: against the cold baseline of 107.1 MB taken one minute after restart, the three-hour-warm readings of 138.5 MB (host scrape) and 136.4 MB (Cloud scrape, moments apart) look like a +29.3 % / +27.3 % climb.

**The first sample, read BY VALUE on both surfaces after the 08:00Z cycle** (`cycle-08.json` completed 08:01:40.845Z, inside `[08:00, 08:30]`; engine unrestarted since the converge):

| series | host `127.0.0.1:9102` | Grafana Cloud |
| --- | --- | --- |
| `zcrypto_engine_active_sleeves` | **1.0** | **1** |
| `zcrypto_engine_sleeve_gross{sleeve="B"}` | 0.0 | 0 |
| `zcrypto_engine_sleeve_gross{sleeve="A1"}` | 0.0 | 0 |
| `zcrypto_engine_sleeve_gross{sleeve="A2"}` | 0.10002169357501955 | 0.10002169357501955 |

**Exactly 1** — the value this topic predicted, not merely a series that appeared. Reading presence as success would have repeated the very failure the gauge exists to catch. B and A1 at float-exact zero with A2 alone carrying the book confirms the one-sleeve state live, matching all 136 journaled shadow cycles.

**The silence before that first cycle was correct, not a fault.** Both families published nothing between the 04:45 converge and the 08:00 cycle, by construction: the labelled family stays silent until `.labels()` and the unlabelled one registers lazily, because a fresh Gauge's `0.0` would *claim* "no sleeves active" rather than be absent.

Two operational notes the converge produced, recorded so they are not re-derived: the Alloy keep-list lives in the **capture** role, so an engine-only converge (`--tags engine`) would have published these families while leaving them unadmitted — the by-value check would have had nothing to read; and the primary's capture was deliberately **not** re-pinned, since the payload is engine-side and restarting live capture would spend risk on the unbackfillable path for nothing.

*(Known and accepted, recorded so nobody re-derives it)* The alert watches the sleeve **count**, not gross — a live sleeve doubling while staying non-zero fires nothing. Deliberate: no per-sleeve level threshold is meaningful, and the count is what changes the ⅓-divisor arithmetic. `sleeve_gross` is not journaled either, so its history lives only in Grafana Cloud.
