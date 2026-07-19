---
status: partial
ripe_when: the Stage-6a/6b paper-trading evidence accumulates (the de-facto out-of-sample test), or before any live-capital go/no-go decision on the deployable
---

# The deployed strategy (trial 44) has no out-of-time holdout evidence

## Context — what

The system the Phase-6 engine deploys is **registry record 44** (the P1 cross-frequency combination, fixed 1/3 weights). Its only formal out-of-sample gate — the pre-registered holdout — was **never run on it**:

- The single budgeted holdout look (`docs/research/13.phase5-holdout-ledger.md`, 2026-07-10 ~01:35 UTC, look budget **1 → 0**, now spent) tested **record 33** — the *superseded* daily-only system — not the cross-frequency system that deploys.
- It ran on the ratified out-of-time window 2026-04-01 → 2026-07-09 (100 bars, fresh pull `data/ohlc-holdout-2026-07-10`, manifest `4e251df2…`) and was a **degenerate window**: both the system and the benchmark held **literal zero exposure every bar** (the 200-day gate had been off since before April), returns identically 0, CI trivially [0, 0]. Verdict EQUALS — the exit bar was met **trivially**.

So the deployable (trial 44) — a *different construction* from record 33 (it adds the weekly A1 sleeve and the native-4h A2 ensemble on the 4h calendar) — carries **no out-of-time validation at all**. Its in-sample metrics (Sharpe 1.5609 full / 1.5583 decisive, DSR ~1.0 at n=4, SPA max-p 0.0060) are on the frozen 2013-09-10 → 2026-03-31 canonical only.

## Why this matters

The one artifact meant to guard against overfitting on the deployed system was spent on a different, superseded system in a window where nothing traded — so it discriminated nothing. The deployable therefore goes to paper/live with **paper trading as its only genuine out-of-sample test**. And the holdout **budget is now 0**: any fresh holdout look is a human-ratified budget expansion (a §12 escalation trigger), not an autonomous act. This is a go-live-confidence fact the human decision-maker should hold explicitly, not one buried in a ledger — it is honestly disclosed in the registry/runbook notes, but its *consequence* (deployed system unvalidated OOS) is not surfaced anywhere actionable.

## Findings so far

- `13.phase5-holdout-ledger.md`: the look tested record 33, degenerate [0,0], EQUALS, budget 1→0.
- Trial 44 (`docs/reference/trial-registry.jsonl` record 44) construction differs materially from record 33 (adds A1-weekly + A2-4h sleeves on the 4h union calendar), so record 33's holdout — even had it discriminated — would not transfer.
- The Phase-6 concordance/tracking gates (specs 00039/00040) compare *execution fidelity* (positions, |Δweight| ≤ 1e-6) and a P&L tracking band — they are **not** out-of-sample strategy validation; they check the engine reproduces the backtest, not that the backtest generalizes.
- Related: [[T0063]] (the deployable's identity is itself mis-stated in the closeout/runbook body, compounding the "what was actually validated?" confusion).

## Done so far

- **The realized-OOS-vs-backtest instrument is built** — `zcrypto engine soak-check` (spec/plan `00058`, iter-107, PR #154). It places the deployed strategy's realized shadow-soak behaviour against its backtest expectation on the frozen canonical, net of the disclosed governor-turnover P&L bias (spec `00040` — the null is recast onto the live cost convention so the D4 bias cancels by construction). It self-proves before reporting (reproduces registry record 44's exact diagnostics, journaled==replay identity, null reconciles — VOID on failure), refuses on a degenerate/short window, prints the zero-OOS banner every run, and is vocabulary-locked (never claims validation). Verified end-to-end on the live journal 2026-07-20: all self-tests `ok`, and it correctly refused (L=14 < floor=30 — not enough consecutive clean cycles yet).
- This closes the **tooling** half of the decision-support sub-item: the substitute-for-the-holdout can now be *read* with real forward data. What remains is running it once the evidence accumulates, plus the human judgment.

## Suggested next steps

- **(Human, go-live)** Decide explicitly whether trial 44's lack of out-of-time evidence is acceptable to proceed on paper (likely yes — paper trading *is* the intended OOS test) and, if/when live capital is on the table, whether any additional validation is warranted first. This is a judgment call reserved to the human — the holdout budget is spent, so a fresh look requires a ratified budget expansion.
- **(Autonomous, decision-support)** Run `zcrypto engine soak-check` once the shadow-soak has ≥ the floor (30) of consecutive clean 4h cycles (the gate approaches ~2026-07-25) and record its verdict against the backtest fingerprint as the substitute-for-holdout read; fold its 5-metric result + P&L line into the go-live evidence. Fingerprint completeness is tracked separately: [[T0072]] (realized governor/cap comparison) and [[T0073]] (secondary block-bootstrap null).
