---
status: partial
ripe_when: rung 1 produces real fills — the maker-first ruling is made, so what remains is measuring the realized maker/taker blend and re-pricing against it. The quoted baseline stays a RANGE (0.51–0.91 conditional) until that measurement exists; no further estimate improves it
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

## Done so far

- **The execution ruling (owner, 2026-08-03): MAKER-FIRST with a taker fallback.** Post-only inside the spread with a time-box; cross only if still unfilled. The reasoning that carried it: resting post-only orders are **free until filled** (fee schedule, verified), so attempting maker costs nothing; the master plan's own thesis is already maker-first; and — decisively — [[T0119]]'s accumulation formula (`delta = target − actually held`) *is* the mechanism that absorbs an unfilled delta, so maker fill risk is precisely the risk that design already handles. Maker-only-never-cross was rejected: an unfilled delta would never place, turning accumulation from a mechanism into an unbounded journal-vs-venue gap. Taker-only was rejected as paying ~44 % of the conditional baseline for executor simplicity. **The realized blend is not assumed — it is measured in rung 1**, which is also [[T0018]]'s cost-recalibration input.
- **The cost model is split (owner ruling, same day; commit `936db6c3`)**: `spot_fee_per_side = 0.006` — a 40 bps fee fused to a 20 bps spread **guess** — became `fee_per_side = 0.0040` + `spread_per_side = 0.0020`. Purely representational: `0.0040 + 0.0020 == 0.006` at **0 ulp**, and neutrality was proven past the pinned tolerance (`approx(abs=0.005)` would survive a 1-ulp shift) by sha256 over the raw IEEE-754 bytes of `governed_net`, `ungoverned_net`, `multipliers` and `final_targets` on both builders — byte-identical. Guards added and **proven by defect injection** to discriminate per field. The defaults deliberately keep the pre-measurement 20 bps so every registered figure reproduces; re-pricing to the measured spread is a separate, deliberate step.
- **The record re-quoted across the execution range** (committed builder, instrument validated first against all three registered anchors — ×1.0 → 1.5609, ×1.5 → 1.3029, ×2.0 → 1.2106, all reproduced exactly):

| basis | multiplier | headline Sharpe | **conditional (what the gate reads)** |
| --- | --- | --- | --- |
| maker @€1k (42.1 bps/side) | ×0.7017 | 1.6304 | **0.9072** |
| maker @€10k (44.2 bps/side) | ×0.7367 | 1.6186 | — |
| **registered headline** | ×1.0 | **1.5609** | **0.7509** |
| taker @€1k (82.1 bps/side) | ×1.3683 | 1.3772 | **0.5201** |
| taker @€10k (84.2 bps/side) | ×1.4033 | **1.3641** | **0.5066** |

- **The execution decision matters ~2.7× more for the live book than the headline shows.** Across the range the headline falls **16.3 %** while the conditional live-state baseline falls **44.2 %** — the one-sleeve book runs at ⅙ gross and carries more turnover per unit of return, so cost bites hardest in exactly the state the live book occupies. Anyone reading only the headline curve underestimates the stake by nearly a factor of three. The conditional figures were validated against [[T0124]]'s registered values on the same window (0.75 conditional, 1.94 multi-sleeve, 1.5609 headline — all reproduced; the state split nests exactly, live 6,885 + fully-flat 3,680 = 10,565 = 38.6 % of 27,337 bars).
- **A numerical coincidence worth naming so it is not tripped over.** [[T0116]]'s amendment registered the go/no-go band as "roughly 0.5–0.75" to express *estimation* uncertainty (IID SE ≈ 0.44, CI spanning zero). That interval is almost exactly the *cost-basis* range from taker up to ×1.0. **Two unrelated uncertainties, one interval** — so at the taker end the baseline sits at the band's floor with no room left for the statistical uncertainty the band was written for. The honest quote is two-dimensional: conditional **and** cost-basis-dependent.
- **Fee axis verified, not assumed**: Kraken tier 1 = **0.40 % maker / 0.80 % taker** under the schedule effective 2026-07-09 (`docs/reference/kraken-fee-schedule.md`, checked against Kraken's own article); our 30-day volume is $0.00 and tier 4's 0.20 %/0.35 % needs $25k, unreachable at a €1,000 book. Margin legs pay the spot fee on **both** open and close.

- **The "cheap, autonomous re-read of the 43-vs-44 ordering" is NOT POSSIBLE, and that is the topic's most consequential finding.** Trial 43's construction does not exist in version control: `git log --all -S"adaptive" -- cli/` returns nothing, both trials' `run_ref` name **scratchpad** scripts (`crossfreq_run.py`, `trial44_run.py`) that are gone, and `_inverse_vol_weights` survives only for *asset-basket* weighting inside sleeves — never for the **sleeve-level** weighting trial 43 used (`weight_warmup_bars = 180`, `weight_zero_vol_fallback_bars = 10638`). Re-reading that ordering therefore means **reconstructing an unversioned instrument from a registry variant string** and trusting it to reproduce a number nobody can check — not a re-read. **Consequence: trial 44 is reproducible from committed code, trial 43 is not, so the ADOPT decision that made 44 the deployable can never be re-examined at a different cost basis.** Same failure class as [[T0065]]'s reproducibility round ("record 1 is not reproducible from committed code + manifest alone"), now reaching the deployable record's own adoption criterion.

## Suggested next steps

- **(autonomous — rides [[T0018]]'s executor iteration)** Implement maker-first with a taker fallback: post-only inside the spread, a time-box, and the cross-on-timeout policy as code. The fallback policy's parameters are executor design, not a re-derivation of this topic.
- **(autonomous, at the same time)** Relax `spread_per_side`'s `> 0` validator to `>= 0`. It is a carry-over from the blended constant, where `> 0` was obviously right; on a split term a **zero spread is legitimate** (a maker fill at mid). Deliberately not done in the split commit, whose whole contract was bit-identical neutrality. Until then a zero-spread config fails loud with a named `PortfolioError`, never a silent wrong number.
- **(autonomous — the measurement, ripe at rung 1)** Derive the realized maker/taker blend from real fills and re-price against it. Until then the quoted baseline is the **range 0.51–0.91 conditional**, not a point.
- **(decision — carried, not resolved here)** [[T0116]]'s registered "0.5–0.75" band conflates estimation uncertainty with the cost range. Whoever next amends §12 must decide whether the band widens to carry both, or whether the two are quoted separately. Recorded here because this topic produced the collision; §12 is not edited from here.
- *(registered elsewhere, so it survives this topic's eventual close)* The unreproducibility of trial 43 is now [[T0125]]. It moved out because it outlives T0090: this topic resolves once the realized blend is measured, and archiving it would have taken a permanent gap in the deployable's provenance with it.
