# Budgeted-holdout ledger (master-plan §9 item 7)

One row per look at the pre-registered holdout. **Look budget: 1. Remaining after the row below: 0.**

| # | Date (UTC) | Window | Data | Present | Subject | Result | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-07-10 ~01:35 | 2026-04-01 → 2026-07-09 (100 bars; ratified T0017, decisions log `[iter-072]`) | fresh pull `data/ohlc-holdout-2026-07-10`, manifest sha256 `4e251df2442db4121f675ddb8060cc35e08af806d2886316e6281176810ea126`; 621 overlap bars/pair verified exact vs the canonical | the human (attended session) + Claude Fable 5 | **Record 33** (one-sleeve combined system) vs the frozen benchmark B3+vt-dynamic, both via `cli.portfolio.build_combined_system`, parameters frozen | **Degenerate window: both systems at literal zero exposure every bar** (the 200-day gate off since before April). Returns identically 0 both sides; difference constant 0; CI trivially [0, 0]. Governor state carried into the window: multiplier 0.5 (the trailing-DD ladder from the 2025 drawdown — the book would deploy at half size on the next gate-on). | **EQUALS** — the exit bar's beats-or-equals reading is met, trivially; the window contains no discriminating information beyond confirming the system correctly sat out a gate-off regime. |

Procedure: the pre-registered mechanics in `12.phase5-system-spec-runbook.md` §Holdout-look protocol, executed verbatim (`holdout_pull.py` + `holdout_look.py`, scratchpad). No parameter changed after any number was seen; the only post-hoc edit was a report-formatting guard for the all-zero case, added after the substantive result was already printed.
