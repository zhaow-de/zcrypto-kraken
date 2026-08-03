---
status: resolved
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

## Resolution

**Ruled 2026-08-03 (owner): ACCEPT the limitation, and narrow what the gate claims.** The go/no-go now states in §12 that it certifies **execution** and explicitly does **not** certify **edge**, and names both limitations it inherits — this one, and [[T0125]]'s unrebuildable adoption criterion. The limitation now lives where the decision is actually taken, rather than in a ledger nobody opens at the moment of deciding, which is the gap this topic was opened to close.

**Mitigation was not rejected as too costly — it was measured as unavailable.** A ratified budget expansion would buy a holdout look over the only window that exists, 2026-04-01 → 2026-08-03, which is **124 days = 0.34 years**. At that length a Sharpe estimate returns:

| true Sharpe | 95 % CI from that window | years needed to separate from zero |
| --- | --- | --- |
| 1.5609 (registered headline) | [−3.45, +6.57] | 3.5 |
| 0.75 (conditional, registered window) | [−3.06, +4.56] | 8.8 |
| 0.63 (conditional, extended) | [−3.05, +4.31] | 11.6 |

So a fresh look could not discriminate, would repeat the degenerate-window failure that wasted the first one, and would burn the option for a window that might one day be long enough. **Accepting is the only choice that buys anything**, and it forecloses nothing: the budget expansion stays available.

**The decision-support read was run at full window (2026-08-03) and it is honest about its own limits.** `zcrypto engine soak-check` over the live journal: **L = 140 scored bars, 23.17 days**, all three self-tests `ok`, chain consistent. Fingerprint: **1 of 7 outside band, 2 of 7 indeterminate**. Realized cumulative net **−0.4559 %** (non-gating, near-vacuous at this length). Both disagreements trace to already-registered conditions rather than new findings — `governor_engagement` reads inconsistent because the multiplier is 0.5 on all 140 cycles with zero variance, the carried state [[T0018]] records; `gross`/`net` sit at 0.0501 against a null median of 0.0829 — a level consistent with the one-sleeve book [[T0124]] measured, since a single live sleeve at fixed ⅓ weights carries less gross than the diversified combination the null samples. **The *level* is attributed; the *verdict* is not.** "Indeterminate" is a severity label meaning the two null constructions disagree — instrument fragility — and nothing here demonstrates that composition causes that disagreement. Attributing it would be explaining away a result rather than reading it. The instrument's own closing line is the operative one: *these are structural-conformance checks — does the live book look like the backtest book — not evidence of edge.*

**The read had to be repaired before it could be believed, and that is the finding worth carrying.** Run against the configured store it scored **54 bars ending 2026-07-19**, silently dropping **87 of 141 cycles** — because iter-103 retired the workstation soak, which was what kept that store warm, and nothing replaced it. The report printed `dropped_tail` but never said the window was bounded by the **store** rather than the journal, so the result read as current when it was a read on 38 % of the evidence. **The verdict genuinely differed**: 0 of 6 outside band on the stale window, where `governor_engagement`'s band spanned all of [0,1] and had no discriminating power at all. `soak-check` now classifies what bounded the window and warns loudly when it was the store, naming both bounds and the cycle cost (commit `de708d7d`). It deliberately does not refuse — a partial pulled store is legitimate; the failure was silence.

*(Operational note, since it will recur: the default `--store-dir` still points at the workstation store, which stays cold by design — the engine's own store lives on the VPS. A workstation run is therefore store-bound and now says so; pass `--store-dir` pointing at a pulled VPS store to read the full window.)*

## Suggested next steps

_(none — resolved. The ruling is made and recorded in §12; the decision-support read was run at full window and its instrument repaired. The holdout budget stays at 0 and a fresh look remains a §12 escalation, deliberately unspent because no available window can discriminate.)_
