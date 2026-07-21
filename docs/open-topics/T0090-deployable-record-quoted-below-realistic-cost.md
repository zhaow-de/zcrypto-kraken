---
status: open
ripe_when: assembling the 6b session brief ([[T0018]]), or any restatement of the deployable record's net-of-cost figures — whichever comes first. Not urgent by verdict (nothing flips) but load-bearing for how the number is presented to a go-live decision
---

# The deployable record's headline is quoted at a cost assumption below realistic execution

## Context — what

Trials 43/44 charge **0.006/side (60 bps)** — "full per-asset costing 0.006/side" in the registry — and assume **zero spread**. Two measurements since say that stack is optimistic:

- **Fees:** iter-079's live adapter-verification fill measured a **taker fee of exactly 0.80 %/side** at zero 30-day volume (€0.08000 on €9.99997, from `TradesHistory`), against the modeled 0.60 %. Tier-1 maker is 0.40 % and taker 0.80 %, so 0.60 % is a maker-leaning blend the live fill did not exhibit.
- **Spread:** now calibrated ([[T0014]], spec `00066`) at an equal-weight basket mean of **2.11 bps/side at €1k** and **4.15 bps/side at €10k**.

Combined, the realistic per-side cost is **×1.37–1.40** of what the headline was computed at.

## Why this matters

**No verdict flips, and that is measured rather than assumed** — trial 44 already carries registered cost-stress runs, and the worst realistic multiplier (×1.403) lies strictly *inside* the ×1.5 anchor, whose governed Sharpe **1.3029 still clears the frozen benchmark 1.2455**. Since Sharpe is monotone decreasing in cost, everything between ×1.0 and ×1.5 clears too. The adopt stands.

What is affected is **how the record is quoted**. `1.5609` is the number in the runbook, the closeout docs and the 6b brief's build contract, and it is a ×1.0-cost figure. A go-live decision read off it is reading a Sharpe the live fee schedule does not deliver. The honest headline for a taker-executed book at €1k tickets is bounded below by 1.3029 and is probably ≈1.35.

Note the inversion worth remembering: **the fee-tier gap (×1.333) is six times larger than the spread term (×1.035–1.069)**. T0014 was opened because spread was the known-missing term; the calibration showed the larger error was in the term we thought we had.

## Findings so far

- Registered anchors for trial 44: ×1.0 → 1.5609, ×1.5 → 1.3029, ×2.0 → 1.2106; frozen benchmark 1.2455 (daily, QA-reproduced). At ×2.0 the book is **below** the benchmark — so the bar is genuinely cost-sensitive, which is why the exact multiplier matters.
- The unresolved input is **execution style**: maker-first vs taker. 0.60 % ≈ a maker-leaning blend; the only live fill observed was taker. Whether the Phase-6 executor posts or crosses is a 6b design decision ([[T0018]] constraint 4), not something the cost model can settle.
- [[T0018]] already scopes "cost-model recalibration from real fills" for the 6b executor — that is the *post-live* loop. This topic is the *pre-live* restatement, which happens earlier and feeds the go/no-go.

## Suggested next steps

- **(With the 6b brief)** State the deployable record's net-of-cost figures at the realistic stack, not only at ×1.0: quote 1.5609 as the modeled figure and the ≥1.3029 bracket as the realistic one, with the multiplier and its two components shown.
- **(Decide, 6b)** Maker-first or taker execution. It sets whether 0.40 %, 0.80 % or a measured blend is the right per-side fee, and it is the single largest lever on the cost stack — larger than the entire spread term.
- **(Cheap, autonomous, do with either of the above)** Re-run the trial-44 governed series at the exact realistic multiplier rather than relying on the ×1.5 bracket, so the brief can quote a point estimate instead of a bound. No new trial is registered — it is a re-read of an existing verdict at a different cost input.
