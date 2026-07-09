---
status: partial
ripe_when: T0009 is resolved — these spend reserved A-family trials, which are held while the kill bar is known-unable-to-discriminate
---

# A2 refinements — native 4h band, breakout-hold sweep (2026 probe done)

## Context — what

Report `docs/research/09` closed the daily A2 verdict ("no significant beat, apples-to-apples") and noted three autonomous follow-ups, parked here because each would register new A-family trials (8 of A=40 remain) against a bar whose worst-slice/window/SPA legs are pending T0009.

## Why this matters

A2's premise survived contact with data (Donchian is genuinely ~1.6–2.5× cheaper on spot turnover, and its long/flat arms beat gated-B1's net-of-cost point estimate in every window) — the family is parked, not dead. Master-plan §5 names 4h–1d as A2's band; the daily run alone hasn't tested its native frequency.

## Findings so far

iter-053: long/flat A2 net-of-cost 1.23–1.33 vs gated-B1 1.047 (point), corrected family SPA p=0.057; short arms cost-killed (margin carry 6.2–8.5 %/yr); A2 holds longs through visible-2026 while gated-B1 sits it out (−0.19 pp-Sharpe slice on 89 periods). 240.parquet (4h) exists for all 10 majors.

## Done so far

- **2026 probe — done, iter-065** (no trial spend; decision-support run per the decomposition rule since it feeds T0009, not waits on it). Result: in the 2026 stub (Jan-Mar, ~90 bars) **every benchmark and the combined system sat at literal zero exposure** (gate off; their slices are degenerate and the worst-slice leg skips them), while the four parked A2 long/flat arms held **0.7–1.8 % mean gross exposure** and lost **0.61-1.06 % total** (in-slice DD ≤ 1.1 %) — yet those sub-1 % losses annualize to slice Sharpes of **−2.2 … −4.3**. Base-rate evidence for the stub question: across the full history, a 1.33-full-Sharpe book (the combined system) shows negative **89-bar** windows **41 %** of the time and negative **365-bar** windows **27 %** (rolling, step 10; benchmarks similar) — a negative quarter-length stub carries near-zero disqualifying information about a healthy book. Recorded in the iter-065 history entry; feeds T0009's worst-slice option (c).

## Suggested next steps

- **4h A2**: first rebuild the **frozen benchmark at 4h** — since 2026-07-09 that is **B3+vt-dynamic** (basket + own-equity 200d gate + vol-target, master-plan §9; T0009 item 1 decided), not gated-B1 — with warm-up/vol-target recalibrated to the band, then run the A2 grid at 4h — sized within the remaining budget (or park for expansion, a §12 trigger).
- **Breakout-hold / cadence sweep** on the long/flat arms (offset-averaged, per the iter-048 method).
