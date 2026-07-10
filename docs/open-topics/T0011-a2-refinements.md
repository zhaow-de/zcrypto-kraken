---
status: partial
ripe_when: next research iteration (the T0009 gate fired and was consumed in iter-074; the fold-in item additionally needs the cross-frequency construction design it names)
---

# A2 refinements — native 4h band, breakout-hold sweep (2026 probe done)

## Context — what

Report `docs/research/09` closed the daily A2 verdict ("no significant beat, apples-to-apples") and noted three autonomous follow-ups, parked here because each would register new A-family trials (8 of A=40 remain) against a bar whose worst-slice/window/SPA legs are pending T0009.

## Why this matters

A2's premise survived contact with data (Donchian is genuinely ~1.6–2.5× cheaper on spot turnover, and its long/flat arms beat gated-B1's net-of-cost point estimate in every window) — the family is parked, not dead. Master-plan §5 names 4h–1d as A2's band; the daily run alone hasn't tested its native frequency.

## Findings so far

iter-053: long/flat A2 net-of-cost 1.23–1.33 vs gated-B1 1.047 (point), corrected family SPA p=0.057; short arms cost-killed (margin carry 6.2–8.5 %/yr); A2 holds longs through visible-2026 while gated-B1 sits it out (−0.19 pp-Sharpe slice on 89 periods). 240.parquet (4h) exists for all 10 majors.

## Done so far

- **4h A2 — done, iter-074** (registry trial_ids 36–39, family-n 34–37; 3 of A=40 remain): the frozen benchmark rebuilt at 4h (time-preserving mapping; noc 1.2128 full / 1.2447 decisive k≥1380), then four long/flat arms under the ratified bar. **Three ADOPT** — (20,50,100)v0.12 at 1.3274, (60,120,240)v0.10 at 1.3017, (60,120,240)v0.12 at **1.3585** — one reject on SPA. Family K=4 multiplicity-corrected p = **0.0145/0.0165** (blocks 30/102): the first family-level significant beat of the frozen bar. Two instrument holds resolved pre-verdict (DSR cross-periodicity units; SPA block/seed robustness — both pre-registered and held). Decisions log `[iter-074]`.

- **2026 probe — done, iter-065** (no trial spend; decision-support run per the decomposition rule since it feeds T0009, not waits on it). Result: in the 2026 stub (Jan-Mar, ~90 bars) **every benchmark and the combined system sat at literal zero exposure** (gate off; their slices are degenerate and the worst-slice leg skips them), while the parked A2 long/flat arms diverged **(corrected in iter-066 — the first probe ran A2 at ~1/19 scale via a double √365 division)**: the fast arms (10–40) lost **−10.6 %/−12.7 %** (in-slice DD 12–14 %) at **~19 % mean gross exposure** — an economically real 2026 loss — while the slow arms (20–100) lost **−2.5 %** at **1.6 % exposure** (slice Sharpes −3.4…−4.0 across all four). Base-rate evidence for the stub question: across the full history, a 1.33-full-Sharpe book (the combined system) shows negative **89-bar** windows **41 %** of the time and negative **365-bar** windows **27 %** (rolling, step 10; benchmarks similar) — a negative quarter-length stub carries near-zero disqualifying information about a healthy book. Recorded in the iter-065 history entry; feeds T0009's worst-slice option (c).
- **Breakout-hold/cadence sweep — done, iter-075** (registry trials 40–42, family-n 38–40; **the A-family budget is fully spent, 40/40**): all three cadence-held daily arms REJECT under the ratified bar — the fast grid on SPA; both (20,50,100) held arms on the **benchmark-relative worst-slice leg** (their worst year, 2018, is materially worse than the bench's worst: −0.145/−0.138 vs −0.089), the C=14 arm despite the project's highest recorded net-of-cost Sharpe (1.4348 full). The turnover mechanism worked (drag 2.86 → 1.72 %/yr); the tail cost of slow de-risking is why the ratified guard exists. Decisions log `[iter-075]`.

## Suggested next steps

- **Fold the adopted 4h arms into the combined system**: a new P1 combination trial (§12 default inverse-vol of sleeves; the `[iter-073]` pre-registered DD-aware adopt criterion applies) — requires a **cross-frequency construction design** first (a 4h sleeve beside the daily record-33 book: union-calendar/resampling semantics, cost attribution, governor cadence). Not conflicting survivors (same-direction books), so autonomous when picked.
