---
status: open
---

# §12's "Ongoing" register is prose-only — kill criteria, revalidation, decay tests

## Context — what

The master plan's post-go-live regime ("Ongoing — Operate, Monitor, Revalidate") names monthly revalidation on rolling data (registered as trials), quarterly decay tests (CUSUM on live-vs-expected P&L), and **pre-registered production kill criteria** (DD-ladder floor, N-month underperformance beyond CI vs its own simulation) "so the retire-decision is mechanical, not emotional". None of it is registered anywhere — it lives only as plan prose, the same hole [[T0113]] closed for the snapshot register. The kill criteria in particular must exist, with numbers, before capital scales past the first ramp step.

## Why this matters

A retire-decision without pre-registered criteria is taken under drawdown stress by a human reading a losing book — precisely the condition pre-registration exists to remove. And unregistered monthly revalidation means the live system's edge is never re-tested on schedule: decay is discovered by P&L instead of by instrument, months late. The plan says the right things; nothing makes them happen.

## Findings so far

- The revalidation cadence has natural registry mechanics already (trials in the append-only registry, DSR at true trial count) — the gap is the schedule and its trigger, not the instrumentation.
- The kill criteria's numeric inputs exist: the DD ladder is deployed config (the governor's `((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))`), and the validation CI comes from the deployable record's registered verdict. What is missing is the owner-ratified thresholds and where they live so the check is mechanical.
- [[T0049]]'s runbook is the operating surface for recurring routines (it already carries [[T0113]]'s monthly sweep) — the register lands there, not in a new document.

## Suggested next steps

- **(autonomous — feeds the decision below, runnable now)** Derive and present the candidate kill-criteria numbers for ratification, from the deployed governor ladder and the deployable record's registered CI.
- **(decision)** Owner ratifies the kill-criteria numbers (DD floor, underperformance window and CI bound) — a decision-register entry, before ramp past 25 %.
- **(autonomous)** Register the monthly revalidation and quarterly decay-test routines in [[T0049]]'s runbook with the same bump-the-stamp discipline as T0113's sweep, each naming its instrument (`soak-check`, the registry, CUSUM harness — the last needs building).
- **(autonomous)** Build the CUSUM live-vs-expected harness if no existing instrument covers it (small; the realized series exists via `soak-check`'s machinery).
