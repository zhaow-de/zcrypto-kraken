---
status: open
ripe_when: 'an activity: the owner picks B1''s next step after trial 3''s park, recorded in the decisions log; check: `git grep -c -E ''^\[iter-[0-9]+\] B1.s next step after trial 3'' -- docs/research/10.phase4-decisions.md` prints at least 1'
---

# B1 — intraday trend + time-of-day/day-of-week seasonality (the family topic)

## Context — what

Split out of the T0016 umbrella per its own rule when B1's prerequisites fired (T0009's protocol legs iter-072; the 15m substrate iter-085 — `data/ohlc-15m`, `basket_sha256 0fed24a6…`). The master plan §5's design brief is binding: **seasonality as conditioning features on the adopted signals** (trade only at favorable windows; scale by intraday-vol state), **never a standalone high-turnover system** — the family lives or dies on maker-fill realism and turnover control, so every verdict is net-of-cost from the first read.

## Why this matters

B1 is the §5 ranked queue's top un-started family — the "genuinely new frequency band" where the residual-alpha probability is concentrated after the A-family kill. Its cheapest failure mode is the classic one: a seasonality overlay that looks good in-sample because the favorable windows were picked on the full sample. Leak-free, fold-internal window estimation is the family's core engineering requirement, pinned in spec 00045.

## Findings so far

- **Trial 3 (iter-177): PARK** — registry trial 48 (`B1`, n=3), spec/plan `00132`: candidate A of the survey, the adopted A2 ensemble's per-asset weights estimated from hourly realized volatility over the same 180 four-hour bars, against the ensemble unchanged. Matrix row 3 fired: arm B passes the kill bar, its head-to-head against arm A is positive and not significant (SPA p 0.1769), and it trades slightly less (turnover −0.58 %); the weights are about a fifth smoother (total variation ratio 0.7933), so the mechanism engaged as predicted. The figures are the decisions log's `[iter-177]` verdict.
- **Trial 2 (iter-087): REJECT** — registry trial 46 (`B1`, n=2). The window-only arm passes the kill bar at every grid point (edge inheritance) but B ≤ A on both head-to-head windows. Mechanism finding #2: hold-through *defers* rather than eliminates trades — catch-up trades on gate-reopen cancel the savings (turnover −1.6%), adding drift risk (maxDD 24.25% vs 21.54%). **Joint state: both overlay mechanisms attributed non-additive on the A2 book.**
- **Trial 1 (iter-086): REJECT** — registry trial 45 (`B1`, n=1). Arm B failed the kill bar's SPA leg uniformly (p ≈ 0.31 across the grid) while arm A passed the identical bar; head-to-head B ≤ A (p 1.0). **The mechanism inverted**: the vol scaler's state flips ADDED +33.8% turnover (the hypothesized reduction), and hold-through worsened maxDD (30.07% vs 21.54%). Engagement was proven before the verdict; the benchmark and all three arms reconstructed elementwise < 1e-12 against the iter-074 caches. The informative residue: the seasonality-gate mechanism alone (window-only, no scaler) remains untested — the scaler is what added the turnover.

- Hypothesis + trial-1 pre-registration: decisions log `[iter-086]` — the conditioning A/B on the adopted A2-4h ensemble (arm A = trials 37–39 equal-weight as adopted; arm B = + hour-of-day/day-of-week favorable-window gating and intraday-vol-state scaling from the 15m substrate), one knob, judged per T0009's revised kill bar vs the frozen B3+vt-dynamic benchmark.
- Substrate QA input (iter-085): AVAX/LINK/DOT recent-year 15m density 88–97% (omitted no-trade slots) — the vol-state features must define behavior on missing 15m bars explicitly.
- Budget: **B = 25 shared across Bucket B** (pre-registered, hard); B1 trials count against it under the family's registry key.
- **Candidate survey** (the owner's disposition of 2026-07-23, to have new candidates drafted): `docs/research/10.phase4-b1-candidate-hypotheses.md` writes three candidates up for pre-registration, none seen against a return, and argues that no trial beats two of them and narrowly beats the third.

## Suggested next steps

- **The owner picks B1's next step after trial 3's park, or closes the family**: a park variant of trial 3 — 15m sampling, or the hourly estimator also in the book vol target — each a new trial of the shared B budget; the survey's candidate B or C, pre-registered with the common decisions the survey lists; or this topic archived as attributed out. The pick is recorded in the decisions log as `[iter-<NNN>] B1's next step after trial 3 — <the pick> (Decision: N)`.
- **The adoption path goes to the owner at the next B1 pre-registration that can adopt.** Spec 00132's D9 settled it for trial 3 without the owner's word: an adopt is a registry fact on the A2 ensemble alone, and deploying it needs a combination trial over record 47's book and an hourly grid in the engine's store. The survey had left that to the owner (`docs/research/10.phase4-b1-candidate-hypotheses.md:60`). A park variant's pre-registration asks the owner rather than inheriting D9.
- Kill discipline: an honest kill closes this topic (archive with the verdict); budget exhaustion or a family kill-bar hit does the same. Expanding past the shared B budget is a parked human decision, never autonomous.
