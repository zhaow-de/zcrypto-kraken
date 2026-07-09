---
status: open
ripe_when: T0009 is resolved — these spend reserved A-family trials, which are held while the kill bar is known-unable-to-discriminate
---

# A2 refinements — native 4h band, breakout-hold sweep, 2026 probe

## Context — what

Report `docs/research/09` closed the daily A2 verdict ("no significant beat, apples-to-apples") and noted three autonomous follow-ups, parked here because each would register new A-family trials (8 of A=40 remain) against a bar whose worst-slice/window/SPA legs are pending T0009.

## Why this matters

A2's premise survived contact with data (Donchian is genuinely ~1.6–2.5× cheaper on spot turnover, and its long/flat arms beat gated-B1's net-of-cost point estimate in every window) — the family is parked, not dead. Master-plan §5 names 4h–1d as A2's band; the daily run alone hasn't tested its native frequency.

## Findings so far

iter-053: long/flat A2 net-of-cost 1.23–1.33 vs gated-B1 1.047 (point), corrected family SPA p=0.057; short arms cost-killed (margin carry 6.2–8.5 %/yr); A2 holds longs through visible-2026 while gated-B1 sits it out (−0.19 pp-Sharpe slice on 89 periods). 240.parquet (4h) exists for all 10 majors.

## Suggested next steps

- **4h A2**: first rebuild the **frozen benchmark at 4h** — since 2026-07-09 that is **B3+vt-dynamic** (basket + own-equity 200d gate + vol-target, master-plan §9; T0009 item 1 decided), not gated-B1 — with warm-up/vol-target recalibrated to the band, then run the A2 grid at 4h — sized within the remaining budget (or park for expansion, a §12 trigger).
- **Breakout-hold / cadence sweep** on the long/flat arms (offset-averaged, per the iter-048 method).
- **2026 probe**: characterize A2's long-holding drawdown in the 2026 stub vs the benchmarks' behavior (gated-B1 sat it out flat; check B3+vt-dynamic, the adopted bar, too) — feeds T0009's partial-year-stub question.
