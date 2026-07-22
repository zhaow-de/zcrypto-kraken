---
status: open
ripe_when: assembling the 6b session brief ([[T0018]]), or any restatement of the deployable record's net-of-cost figures — whichever comes first. Not urgent by verdict (nothing flips at either end of the range) but load-bearing for how the number is presented to a go-live decision, and it turns on a 6b design decision nobody has made
---

# The record's cost assumption is a headroom guess whose direction depends on an unmade execution decision

## Context — what

Trials 43/44 charge `0.006/side`. That figure is **not** a fee: `docs/specs/00036-combined-system-builder-design.md:24` and the Phase-5 runbook decompose it as **tier-1 maker 0.40 % × 1.5**, i.e. **40 bps of maker fee plus 20 bps of explicit "spread/slippage headroom"**. The runbook states the intent plainly: *"T0014 replaces the headroom guess with captured-spread calibration when ripe"*.

[[T0014]] (spec `00066`) has now measured the thing the headroom was guessing at. It is **2.11 bps/side at €1k and 4.15 at €10k** — the 20 bps guess is **5–10× too large**.

That would be a tidy over-provision story, except for the second input: iter-079's only live fill was **taker at 0.80 %/side**, while the 0.006 convention assumes **maker**. The two readings point in opposite directions:

| execution | true cost/side (fee + measured spread) | vs the modeled 60 bps |
|---|---|---|
| **maker** (what 0.006 assumes) | 42.1 bps @€1k · 44.2 @€10k | **×0.70–0.74 — the model over-charges** |
| **taker** (the only fill observed) | 82.1 bps @€1k · 84.2 @€10k | **×1.37–1.40 — the model under-charges** |

## Why this matters

**The spread term is not the lever; execution style is.** The entire calibrated spread (2–4 bps) is small beside the 40 bps maker↔taker delta. So the honest statement is not "the record is quoted too cheap" — it is that **the record's cost basis is directionally unresolved until someone decides whether the executor posts or crosses**, and the number moves ±30–40 % on that decision.

**No verdict flips at either end**, and that is measured rather than argued:

- **Taker end (the adverse one).** At ×1.403 the governed Sharpe is **1.3645**, measured on the committed builder, against the 4h-rebuilt benchmark (1.2128 full / 1.2447 decisive) and the daily frozen 1.2455 alike. A 0.01-grid sweep over [×1.0, ×1.5] bottoms at 1.3016 (×1.498).
- **Maker end** is *cheaper* than what was charged, so the recorded verdicts are conservative there by construction.
- **The monotonicity argument that first carried this was false and is withdrawn.** Sharpe is not monotone in cost here: 13 of 50 grid steps in [×1.0, ×1.5] *increase* it (×1.37 → 1.3768, ×1.38 → 1.4303), because the drawdown governor re-engages on the net-of-cost series; it is non-monotone downward too (×1.9 → 1.1876, below both ×2.0 and the benchmark). Coverage is therefore **swept points only** — the grid's margin to the benchmark (0.056) is smaller than the largest single-step drop observed (0.075).

What is affected is **how the record is quoted**. `1.5609` appears in the runbook, the closeout docs and the 6b brief's build contract, and it is a ×1.0-cost figure resting on a headroom guess now known to be 5–10× too large in one direction and 33 % too small in the other.

## Findings so far

- Registered anchors for trial 44: ×1.0 → 1.5609, ×1.5 → 1.3029, ×2.0 → 1.2106. Benchmarks: 4h-rebuilt 1.2128 full / 1.2447 decisive (trial 44 *is* a 4h construction) and the daily frozen 1.2455 from record 33 — the last is the one usually quoted, and it is **cross-cadence**. At ×2.0 the book is below all three, so the bar is genuinely cost-sensitive.
- **Unread, and named as unread:** trial 44's registered verdict is ADOPT *vs incumbent trial 43* ("1.5609 ≥ 1.5366"), not versus a benchmark. At ×1.5 that lead is +0.0021; at ×2.0 the ordering **reverses** (1.2106 vs 1.2400 — disclosed in the registry row itself). Nobody has re-read the 43-vs-44 ordering at either end of the maker/taker range, and that ordering is the criterion the deployable record actually rests on.
- The 20 bps headroom covered **slippage as well as spread**. T0014 measured the *visible* cost of crossing; market impact beyond the visible book, queue position and maker-fill probability remain unmeasured, so the headroom is not fully retired even at the maker end.
- [[T0018]] already scopes "cost-model recalibration from real fills" for the 6b executor — that is the *post-live* loop. This is the *pre-live* restatement, which happens earlier and feeds the go/no-go.

## Suggested next steps

- **(Decide, 6b — this is the whole topic)** Maker-first or taker execution. It sets whether the per-side fee is 0.40 %, 0.80 % or a measured blend, and it moves the record's cost basis by ±30–40 % — an order of magnitude more than the entire spread term.
- **(With the 6b brief)** Quote the record at both ends rather than at ×1.0 alone: the modeled 1.5609, and the measured **1.3645 at the taker end (×1.403)**, against the 4h benchmark rather than the cross-cadence daily 1.2455.
- **(Cheap, autonomous)** Re-read the **43-vs-44 ordering** at ×1.40 — the criterion the record rests on, and the one thing still unread. No new trial: a re-read of an existing verdict at a different cost input spends no budget.
- **(Only if the bracket must carry weight)** Re-sweep finer than 0.01 near the minimum, or keep the claim point-estimate-only — with monotonicity withdrawn, a 0.01 grid cannot exclude a sub-grid dip.
- **(Consider with the decision)** Whether `spot_fee_per_side` should stop being a single blended constant and become fee + calibrated spread as separate terms, now that the second is measured rather than guessed.
